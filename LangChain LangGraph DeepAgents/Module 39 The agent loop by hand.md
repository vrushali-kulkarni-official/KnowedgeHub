# PHASE 5 — Tools & MCP

## Module 39: The Agent Loop by Hand

This is one of the most important modules in your entire LangChain/LangGraph learning path.

Once you understand the manual agent loop, a lot of things that otherwise feel like “magic” become straightforward:

* `bind_tools()`
* `AIMessage.tool_calls`
* `ToolMessage`
* tool dispatch
* parallel tool execution
* repeated model/tool cycles
* max-iteration limits
* duplicate-call protection
* token budgets
* tool errors
* why LangGraph has `ToolNode`
* why LangChain has `create_agent`
* where MCP fits
* what an agent actually is underneath the framework

The current LangChain documentation describes an agent very directly: **a model calling tools in a loop until a stopping condition is reached**. The surrounding harness provides the prompt, tools, middleware, state, and other controls. ([Docs by LangChain][1])

---

# 1. First: forget the word “agent” for a moment

The easiest mistake is to think:

> “An agent is some special AI object.”

It isn't.

At the fundamental level, an agent can be reduced to:

```text
LLM
 ↓
Does the model want a tool?
 ↓
YES ──→ execute tool
          ↓
        result
          ↓
        give result back to LLM
          ↓
        LLM again
          ↓
        ...
          ↓
NO ───→ final answer
```

That is the agent loop.

The framework is mostly there to make this loop:

* safer
* stateful
* observable
* interruptible
* retryable
* persistent
* scalable
* easier to compose
* less error-prone

LangChain's current docs explicitly describe tool calling as a process where the model requests a tool call, your application executes it, and the result is passed back so the model can continue reasoning. ([docs.langchain.com][2])

---

# 2. The single most important mental model

Suppose the user asks:

> “What is the weather in Mumbai?”

You have this Python tool:

```python
@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return "Mumbai is 29°C and cloudy."
```

A beginner often imagines:

```text
User
  ↓
LLM
  ↓
Python function executes
  ↓
LLM
```

That is **not actually what happens**.

The model cannot magically execute your Python function.

Instead:

```text
User
  ↓
LLM
  ↓
"Please call get_weather(city='Mumbai')"
  ↓
YOUR PYTHON PROGRAM
  ↓
get_weather("Mumbai")
  ↓
"Mumbai is 29°C and cloudy."
  ↓
YOUR PYTHON PROGRAM
  ↓
LLM
  ↓
"Currently Mumbai is 29°C and cloudy."
```

The model **requests** the tool.

Your program **executes** the tool.

This distinction is fundamental.

---

# 3. What `bind_tools()` actually does

Consider:

```python
model_with_tools = model.bind_tools([get_weather])
```

A common misconception is:

> "`bind_tools()` connects the model directly to my Python function."

Not exactly.

What happens conceptually is:

```text
get_weather()
     ↓
LangChain creates tool schema
     ↓
name
description
arguments
     ↓
provider-compatible tool definition
     ↓
LLM
```

The model receives something conceptually similar to:

```json
{
  "name": "get_weather",
  "description": "Get the current weather for a city.",
  "parameters": {
    "type": "object",
    "properties": {
      "city": {
        "type": "string"
      }
    },
    "required": ["city"]
  }
}
```

The model then decides whether it wants to request that tool.

Current LangChain documentation uses exactly this pattern:

```python
model_with_tools = model.bind_tools([get_weather])

response = model_with_tools.invoke(
    "What's the weather like in Boston?"
)

response.tool_calls
```

The returned message contains normalized tool calls such as:

```python
[
    {
        "name": "get_weather",
        "args": {"city": "Boston"},
        "id": "call_123",
        "type": "tool_call",
    }
]
```

([docs.langchain.com][2])

So:

```python
bind_tools()
```

means approximately:

> “Make the model aware of these tools and give it the ability to request them.”

It does **not** mean:

> “Automatically execute these functions.”

---

# 4. The four fundamental objects

For this module, keep these four concepts in your head:

```text
HumanMessage
AIMessage
ToolCall
ToolMessage
```

The flow looks like this:

```text
HumanMessage
      ↓
    Model
      ↓
   AIMessage
   + tool_calls
      ↓
   ToolCall
      ↓
 execute Python
      ↓
 ToolMessage
      ↓
    Model
      ↓
   AIMessage
   + possibly more tool_calls
      ↓
     ...
      ↓
final AIMessage
```

---

# 5. `AIMessage`

The model returns an `AIMessage`.

For example:

```python
ai_msg = model_with_tools.invoke(messages)
```

You might receive:

```python
AIMessage(
    content="",
    tool_calls=[
        {
            "name": "get_weather",
            "args": {"city": "Mumbai"},
            "id": "abc123",
            "type": "tool_call",
        }
    ]
)
```

The important part is:

```python
ai_msg.tool_calls
```

If:

```python
ai_msg.tool_calls
```

is empty:

```python
[]
```

then the model is saying:

> “I don't need another client-side tool. I'm done.”

That becomes our loop termination condition.

LangChain standardizes tool calls into `AIMessage.tool_calls`, and the docs explicitly use that property rather than requiring you to parse raw provider JSON yourself. ([docs.langchain.com][2])

---

# 6. `ToolCall`

A tool call is basically a structured instruction from the model:

```python
{
    "name": "get_weather",
    "args": {
        "city": "Mumbai"
    },
    "id": "abc123",
    "type": "tool_call",
}
```

Think:

```text
name = WHAT to execute

args = WITH WHAT INPUT

id = WHICH request this belongs to
```

That `id` becomes extremely important when multiple tools are called.

For example, the model might request:

```python
[
    {
        "name": "get_weather",
        "args": {"city": "Mumbai"},
        "id": "call_001",
        "type": "tool_call",
    },
    {
        "name": "get_weather",
        "args": {"city": "Delhi"},
        "id": "call_002",
        "type": "tool_call",
    }
]
```

These are two separate requests.

---

# 7. `ToolMessage`

After your Python program executes a tool, the result is returned to the model as a `ToolMessage`.

For example:

```python
ToolMessage(
    content="Mumbai is 29°C and cloudy.",
    tool_call_id="call_001",
)
```

Notice:

```python
tool_call_id="call_001"
```

This tells the model:

> “This result belongs to the tool call whose ID was `call_001`.”

This matters enormously when multiple tools are being executed in parallel. The current `ToolMessage` reference explicitly describes `tool_call_id` as the association between a tool request and its response. ([LangChain Reference Docs][3])

---

# 8. Why the `tool_call_id` matters

Imagine:

```text
AIMessage

call_001 → get_weather(Mumbai)
call_002 → get_weather(Delhi)
call_003 → get_population(Mumbai)
```

The tools return:

```text
ToolMessage(call_001) → Mumbai weather

ToolMessage(call_002) → Delhi weather

ToolMessage(call_003) → Mumbai population
```

The model can therefore correlate:

```text
call_001 ↔ result 1
call_002 ↔ result 2
call_003 ↔ result 3
```

That is why you should **never casually throw away the tool-call IDs**.

---

# 9. The basic loop

Now we can write the entire agent ourselves.

```python
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.tools import tool
from langchain.messages import HumanMessage


@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return f"The weather in {city} is 29°C and cloudy."


tools = [get_weather]

model = ChatGoogleGenerativeAI(
    model="gemini-3.6-flash",
)

model_with_tools = model.bind_tools(tools)

messages = [
    HumanMessage(content="What is the weather in Mumbai?")
]

while True:
    ai_msg = model_with_tools.invoke(messages)

    messages.append(ai_msg)

    if not ai_msg.tool_calls:
        break

    for tool_call in ai_msg.tool_calls:
        tool = {
            "get_weather": get_weather,
        }[tool_call["name"]]

        tool_message = tool.invoke(tool_call)

        messages.append(tool_message)

print(ai_msg.content)
```

That is an agent.

Not a simplified analogy.

Not pseudo-code.

The core idea really is that simple.

---

# 10. Let's walk through that code extremely carefully

Initially:

```python
messages = [
    HumanMessage(
        content="What is the weather in Mumbai?"
    )
]
```

State:

```text
messages
└── HumanMessage
    └── "What is the weather in Mumbai?"
```

Then:

```python
ai_msg = model_with_tools.invoke(messages)
```

The model might produce:

```text
AIMessage
└── tool_calls
    └── get_weather(city="Mumbai")
```

We append it:

```python
messages.append(ai_msg)
```

Now:

```text
messages

1. HumanMessage
   "What is the weather in Mumbai?"

2. AIMessage
   tool_calls:
   get_weather("Mumbai")
```

Then:

```python
if not ai_msg.tool_calls:
```

is false.

So we execute the tool.

```python
tool_message = get_weather.invoke(tool_call)
```

Conceptually:

```text
ToolCall
   ↓
get_weather("Mumbai")
   ↓
"The weather in Mumbai is 29°C and cloudy."
   ↓
ToolMessage
```

Now the message history is:

```text
1. HumanMessage
   "What is the weather in Mumbai?"

2. AIMessage
   tool call:
   get_weather("Mumbai")

3. ToolMessage
   "The weather in Mumbai is 29°C and cloudy."
```

Then the loop begins again.

The model receives **all three messages**.

It now knows:

```text
User asked about Mumbai weather.

I requested get_weather(Mumbai).

The tool responded:
Mumbai is 29°C and cloudy.
```

So the model can now answer:

```text
"It's currently 29°C and cloudy in Mumbai."
```

No tool call.

Therefore:

```python
ai_msg.tool_calls == []
```

and the loop ends.

This is exactly the tool execution loop documented by LangChain. ([docs.langchain.com][2])

---

# 11. Very important: why we append the `AIMessage`

This is one of the easiest things to get wrong.

You might be tempted to do:

```python
ai_msg = model.invoke(messages)

for tool_call in ai_msg.tool_calls:
    result = tool.invoke(tool_call)

messages.append(result)
```

That is wrong.

You need:

```python
messages.append(ai_msg)
```

**before** adding the `ToolMessage`.

The history must conceptually be:

```text
Human
  ↓
AI: I want tool X
  ↓
Tool: Here is result X
  ↓
AI: Now I know the result
```

not:

```text
Human
  ↓
Tool: Here is result
  ↓
AI: ...
```

The model needs to see the tool request it previously made.

---

# 12. Gemini has one especially important modern detail

With newer Gemini models, the returned `AIMessage` can contain model-specific reasoning/thought-signature information that needs to survive across tool-call turns.

The current LangChain Gemini reference explicitly says that for Gemini 3+ multi-turn conversations involving tools, you must pass the full `AIMessage` back so that thought signatures are preserved. ([LangChain Reference Docs][4])

That gives you another reason to do:

```python
messages.append(ai_msg)
```

rather than trying to reconstruct the message yourself from:

```python
ai_msg.content
ai_msg.tool_calls
```

For Gemini, a good modern rule is:

> **Preserve the actual `AIMessage` object. Don't manufacture a replacement unless you have a very specific reason.**

---

# 13. You normally do NOT need to manually create `ToolMessage`

Notice I used:

```python
tool_message = tool.invoke(tool_call)
```

instead of:

```python
ToolMessage(
    content=...,
    tool_call_id=...
)
```

Why?

Because LangChain tools understand the model's `ToolCall` structure.

The current tool docs and APIs support invoking tools using the generated tool call, allowing LangChain to produce the corresponding `ToolMessage`. ([Docs by LangChain][2])

So this is preferred:

```python
tool.invoke(tool_call)
```

or:

```python
await tool.ainvoke(tool_call)
```

rather than manually extracting:

```python
tool_call["args"]
```

and then manually constructing everything.

You still need to know how `ToolMessage` works because eventually you'll want custom error handling, interception, security policies, or state manipulation.

---

# 14. `invoke()` versus calling the tool like a function

You might encounter:

```python
get_weather(...)
```

or:

```python
get_weather.invoke(...)
```

Modern LangChain style is based around the Runnable interface:

```python
tool.invoke(...)
tool.ainvoke(...)
tool.batch(...)
tool.abatch(...)
```

The old callable-style interface (`tool(...)`) has been deprecated in LangChain Core in favor of `invoke()`. ([LangChain][5])

So for your learning:

### Modern

```python
tool.invoke(tool_call)
```

### Async modern

```python
await tool.ainvoke(tool_call)
```

### Avoid in new code

```python
tool(...)
```

---

# 15. The next important concept: one model response can contain multiple tool calls

Suppose the user asks:

> “What's the weather in Mumbai and Delhi?”

The model may produce:

```python
ai_msg.tool_calls
```

containing:

```python
[
    {
        "name": "get_weather",
        "args": {"city": "Mumbai"},
        "id": "call_001",
        "type": "tool_call",
    },
    {
        "name": "get_weather",
        "args": {"city": "Delhi"},
        "id": "call_002",
        "type": "tool_call",
    },
]
```

This is called **parallel tool calling**.

Current LangChain documentation notes that many tool-capable models can produce multiple tool calls in a single response, and those tools can be executed concurrently when appropriate. ([docs.langchain.com][2])

---

# 16. Why parallel execution matters

Suppose:

```text
Mumbai API = 500 ms
Delhi API = 700 ms
Pune API = 400 ms
```

Sequential:

```text
500 + 700 + 400
= 1600 ms
```

Parallel:

```text
max(500, 700, 400)
≈ 700 ms
```

Obviously there is overhead in real systems, but the principle is:

```text
Independent work
        ↓
execute concurrently
```

This matters enormously in enterprise agents.

For example:

```text
CRM lookup       ─┐
HR database      ─┤
ERP query        ─┤──→ model
Knowledge search ─┘
```

can often be much faster than:

```text
CRM
 ↓
HR
 ↓
ERP
 ↓
search
 ↓
model
```

---

# 17. But parallel does NOT mean “always execute everything concurrently”

This is a critical advanced concept.

Suppose the model requests:

```text
create_customer()
send_email()
```

Those operations may not be independent.

Or:

```text
create_invoice()
pay_invoice()
```

Clearly:

```text
create_invoice()
        ↓
payment
```

is dependent.

The model shouldn't ideally request both in the same batch because the second operation needs the result of the first.

The safe mental model is:

> **Tools in the same model-generated batch have no knowledge of each other's newly generated results.**

Therefore:

```text
same batch
→ potentially parallel

different model rounds
→ naturally sequential
```

For example:

```text
Round 1:
create_invoice()

Tool result

Round 2:
pay_invoice(invoice_id=...)
```

That's one of the reasons the model/tool loop exists.

---

# 18. Async parallel tool execution

A modern implementation can use:

```python
asyncio.gather()
```

Example:

```python
import asyncio


async def execute_tool(tool_call, tools_by_name):
    tool = tools_by_name[tool_call["name"]]
    return await tool.ainvoke(tool_call)


tool_messages = await asyncio.gather(
    *[
        execute_tool(tool_call, tools_by_name)
        for tool_call in ai_msg.tool_calls
    ]
)
```

Then:

```python
messages.extend(tool_messages)
```

Because `asyncio.gather()` returns results corresponding to the input order, your message ordering remains deterministic.

The model still relies on:

```text
tool_call_id
```

for correlation.

---

# 19. A better parallel implementation: limit concurrency

Imagine a model generates 100 tool calls.

You don't necessarily want:

```python
asyncio.gather(*100_calls)
```

because you might overwhelm:

* APIs
* databases
* internal services
* connection pools
* rate limits

Instead:

```python
semaphore = asyncio.Semaphore(5)
```

Then:

```python
async def execute_tool(tool_call):
    async with semaphore:
        tool = tools_by_name[tool_call["name"]]
        return await tool.ainvoke(tool_call)
```

This gives:

```text
100 requested calls
       ↓
5 at a time
```

This is a very important production pattern.

---

# 20. Now let's build a proper async agent loop

Here is a much more realistic version.

```python
import asyncio

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.tools import tool
from langchain.messages import HumanMessage


@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return f"The weather in {city} is 29°C and cloudy."


@tool
def get_population(city: str) -> str:
    """Get the population of a city."""
    return f"The population of {city} is approximately 20 million."


tools = [
    get_weather,
    get_population,
]

tools_by_name = {
    tool.name: tool
    for tool in tools
}


model = ChatGoogleGenerativeAI(
    model="gemini-3.6-flash",
    timeout=60,
    max_retries=2,
)

model_with_tools = model.bind_tools(tools)


async def run_agent(user_input: str) -> str:

    messages = [
        HumanMessage(content=user_input)
    ]

    max_iterations = 8
    max_parallel_tools = 5

    semaphore = asyncio.Semaphore(max_parallel_tools)

    for iteration in range(max_iterations):

        print(f"\n--- iteration {iteration + 1} ---")

        ai_msg = await model_with_tools.ainvoke(messages)

        messages.append(ai_msg)

        print("Tool calls:", ai_msg.tool_calls)

        # No tool calls means the model has produced
        # its final answer.
        if not ai_msg.tool_calls:
            return ai_msg.text

        async def execute_tool(tool_call):
            tool = tools_by_name.get(tool_call["name"])

            if tool is None:
                raise ValueError(
                    f"Unknown tool: {tool_call['name']}"
                )

            async with semaphore:
                return await tool.ainvoke(tool_call)

        tool_messages = await asyncio.gather(
            *[
                execute_tool(tool_call)
                for tool_call in ai_msg.tool_calls
            ]
        )

        messages.extend(tool_messages)

    raise RuntimeError(
        f"Agent stopped after {max_iterations} iterations."
    )
```

Usage:

```python
answer = await run_agent(
    "What is the weather and population of Mumbai?"
)

print(answer)
```

---

# 21. Understand this loop as a state machine

The code becomes much easier to understand if you visualize it as a state machine:

```text
                 ┌─────────────────┐
                 │  User message   │
                 └────────┬────────┘
                          ↓
                 ┌─────────────────┐
          ┌─────→│   Call model    │
          │      └────────┬────────┘
          │               ↓
          │      ┌─────────────────┐
          │      │  tool_calls ?   │
          │      └───────┬─────────┘
          │              │
       YES│              │NO
          ↓              ↓
 ┌────────────────┐   ┌─────────────┐
 │ execute tools  │   │ final answer│
 └───────┬────────┘   └─────────────┘
         ↓
 ┌────────────────┐
 │ ToolMessages   │
 └───────┬────────┘
         │
         └─────────────→ model
```

This is essentially the architecture that LangGraph formalizes.

---

# 22. What LangGraph adds

When you manually write:

```python
while True:
    ...
```

you are explicitly controlling the orchestration.

LangGraph lets you represent that as graph execution.

Conceptually:

```text
START
  ↓
MODEL
  ↓
does it have tools?
 ↙       ↘
yes       no
 ↓         ↓
TOOLS     END
 ↓
MODEL
```

Current LangGraph has `ToolNode`, which is specifically responsible for executing tool calls, including parallel execution, error handling, state injection, and related functionality. ([LangChain Reference Docs][6])

And current LangChain's `create_agent()` uses that machinery internally for standard agent loops. ([LangChain Reference Docs][6])

So:

```text
your manual loop
       ↓
understand the mechanism
       ↓
LangGraph
       ↓
formalized orchestration
       ↓
create_agent
       ↓
higher-level production harness
```

That is exactly why learning this module is worthwhile.

---

# 23. The stopping condition

The simplest stopping condition is:

```python
if not ai_msg.tool_calls:
    return ai_msg
```

But real systems need more stopping conditions.

For example:

```text
STOP if:
    no tool calls
OR
    maximum iterations reached
OR
    token budget exhausted
OR
    repeated tool call detected
OR
    cancellation requested
OR
    execution deadline reached
OR
    policy violation detected
OR
    unrecoverable tool failure
```

This is where an “agent loop” becomes an actual **agent runtime**.

---

# 24. Max iterations

Imagine the model behaves badly:

```text
model → tool A
model → tool A
model → tool A
model → tool A
...
```

Without a limit, the loop could potentially keep going.

So:

```python
MAX_ITERATIONS = 8
```

and:

```python
for iteration in range(MAX_ITERATIONS):
```

Now you have a deterministic upper bound.

But define what an iteration means.

I recommend:

> **One iteration = one model invocation.**

So:

```text
Iteration 1
    model
    tools

Iteration 2
    model
    tools

Iteration 3
    model
    final answer
```

If `MAX_ITERATIONS=3`, you allow at most three model calls.

That is cleaner than saying:

> “An iteration means one tool call.”

because a single model response can contain five tool calls.

---

# 25. A subtle max-iteration decision

Suppose:

```python
MAX_ITERATIONS = 3
```

On iteration 3 the model says:

```text
Call delete_customer()
```

Should you execute it?

I'd recommend:

**No.**

Why?

Because iteration 3 is already your last allowed model decision.

You don't have enough budget for:

```text
tool execution
    ↓
model call
    ↓
final reasoning
```

And potentially you've just started an external side effect without allowing the agent to finish.

Therefore:

```python
if iteration == MAX_ITERATIONS - 1 and ai_msg.tool_calls:
    raise MaxIterationsExceeded
```

before executing the calls.

This makes your limit a genuine safety boundary.

---

# 26. Duplicate-call detection

Now consider this model behavior:

```text
Iteration 1
get_customer(123)

Iteration 2
get_customer(123)

Iteration 3
get_customer(123)

Iteration 4
get_customer(123)
```

Maybe the tool result is not changing.

The agent may have become stuck.

We therefore need to detect:

```text
same tool
+
same arguments
```

rather than only:

```text
same tool
```

Because:

```python
get_weather("Mumbai")
get_weather("Delhi")
```

are not duplicates.

---

# 27. Do NOT use the tool-call ID to detect duplicates

This is subtle.

Suppose:

```text
call_001
get_weather("Mumbai")
```

and later:

```text
call_002
get_weather("Mumbai")
```

The IDs are different.

But the logical request is identical.

Therefore duplicate detection should use something like:

```text
tool name + normalized arguments
```

not:

```text
tool_call_id
```

For example:

```python
import json


def call_signature(tool_call: dict) -> str:
    return json.dumps(
        {
            "name": tool_call["name"],
            "args": tool_call["args"],
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
```

Now:

```python
call_signature(
    {
        "name": "get_weather",
        "args": {"city": "Mumbai"},
    }
)
```

produces a stable representation.

---

# 28. But duplicate detection is NOT universally safe

This is a very important production concept.

Suppose:

```python
charge_credit_card(...)
```

Two identical calls are **not necessarily duplicates**.

The second call may intentionally be another operation.

Likewise:

```python
send_email(...)
```

Calling it twice has a side effect.

Therefore:

```text
read-only tool
    → duplicate caching/detection can be useful

state-changing tool
    → require idempotency / idempotency keys / stronger policy
```

For example:

```text
get_customer()
search_database()
get_weather()
get_invoice()
```

are usually candidates for caching/deduplication.

Whereas:

```text
create_invoice()
send_email()
delete_file()
charge_card()
submit_expense()
```

need much more careful treatment.

This is particularly important for your enterprise AI harness idea.

---

# 29. A simple duplicate detector

For teaching purposes:

```python
seen_calls: set[str] = set()

signature = call_signature(tool_call)

if signature in seen_calls:
    print("Duplicate tool call detected.")
else:
    seen_calls.add(signature)
    ...
```

But in production I'd go one step further.

Instead of merely saying:

```text
duplicate!
```

for read-only tools, you can cache the result:

```text
first call:

get_weather("Mumbai")
       ↓
API call
       ↓
result cached


second identical call:

get_weather("Mumbai")
       ↓
cache hit
       ↓
reuse result
```

This saves:

* latency
* API calls
* money
* rate limits

---

# 30. Token budget

This is another extremely important part of agent design.

People often think:

```text
LLM call = one cost
```

But an agent may perform:

```text
LLM call 1
Tool
LLM call 2
Tool
LLM call 3
Tool
LLM call 4
Tool
LLM call 5
```

So the total cost can become much larger than a normal chat completion.

You therefore want:

```text
max total tokens per run
```

not just:

```text
max output tokens per model call
```

These are different.

---

# 31. Per-call token limit versus loop token budget

Suppose:

```text
max output per model call = 1000
```

and the agent performs:

```text
10 model calls
```

The model could theoretically generate:

```text
1000 × 10
= 10,000 output tokens
```

So this:

```text
per-call limit
```

does not automatically give you:

```text
per-agent-run limit
```

You need both when you care about total cost.

---

# 32. LangChain usage metadata

Current LangChain `AIMessage`s can expose normalized usage information such as:

```python
ai_msg.usage_metadata
```

For Gemini, current integration examples show:

```python
{
    "input_tokens": ...,
    "output_tokens": ...,
    "total_tokens": ...,
}
```

([Mintlify][7])

So we can accumulate:

```python
total_input_tokens += usage.get("input_tokens", 0)
total_output_tokens += usage.get("output_tokens", 0)
```

and then:

```python
total_tokens = (
    total_input_tokens
    + total_output_tokens
)
```

---

# 33. Token accounting inside the loop

Example:

```python
total_input_tokens = 0
total_output_tokens = 0

ai_msg = await model_with_tools.ainvoke(messages)

usage = ai_msg.usage_metadata or {}

total_input_tokens += usage.get(
    "input_tokens",
    0,
)

total_output_tokens += usage.get(
    "output_tokens",
    0,
)

total_tokens = (
    total_input_tokens
    + total_output_tokens
)

if total_tokens > MAX_TOTAL_TOKENS:
    raise RuntimeError(
        "Agent token budget exceeded."
    )
```

And importantly:

```python
if total_tokens > MAX_TOTAL_TOKENS:
```

should happen **before continuing to execute another round of expensive work**.

---

# 34. But how do we stop BEFORE spending too many tokens?

This is a subtle problem.

After the model responds, you know what it actually used.

Before the model responds, you don't know its exact usage.

So there are two forms of protection:

### Post-call accounting

Use:

```python
ai_msg.usage_metadata
```

to determine actual consumption.

### Pre-call estimation

Use:

```python
count_tokens_approximately()
```

to estimate how large the next input is.

LangChain currently provides:

```python
count_tokens_approximately(
    messages,
    tools=tools,
)
```

and importantly, the function can include tool schemas in its calculation. ([LangChain Reference Docs][8])

That's useful because your tool definitions themselves consume context.

---

# 35. Tool schemas consume tokens

Suppose you have:

```text
5 tools
```

with huge descriptions and complex Pydantic schemas.

Every model call may need to reason with those tool definitions.

So your context isn't simply:

```text
user message
 +
conversation
```

It can effectively include:

```-text
system instructions
+
conversation
+
AI messages
+
tool messages
+
tool calls
+
tool schemas
```

This is one of the reasons large tool collections become expensive.

The approximate counter can explicitly include the tools:

```python
estimated = count_tokens_approximately(
    messages,
    tools=tools,
)
```

([LangChain Reference Docs][8])

---

# 36. Approximate versus exact token counting

`count_tokens_approximately()` is exactly what its name says:

**approximate**.

It does not promise provider-exact billing counts.

LangChain recommends approximate counting as a lightweight hot-path approach, while model-specific token counting can provide more accurate results. ([LangChain Reference Docs][8])

Therefore a good architecture is:

```text
Before model call:
    approximate estimate
         ↓
    should we proceed?


After model call:j
    actual usage_metadata
         ↓
    update cumulative budget
```

---

# 37. Example: full budget policy

Suppose:

```python
MAX_TOTAL_TOKENS = 12_000
RESERVED_OUTPUT_TOKENS = 1_000
```

Before a new model call:

```python
estimated_input_tokens = count_tokens_approximately(
    messages,
    tools=tools,
)

remaining_budget = (
    MAX_TOTAL_TOKENS
    - total_tokens_used
)

if (
    estimated_input_tokens
    + RESERVED_OUTPUT_TOKENS
    > remaining_budget
):
    raise RuntimeError(
        "Not enough token budget for another model iteration."
    )
```

This is conservative.

It says:

> “I want enough budget left for the estimated input plus some room for output.”

That is safer than discovering too late that you've exhausted the budget.

---

# 38. Important: do not blindly trim messages

LangChain has:

```python
trim_messages()
```

which can reduce a conversation to a token limit. ([LangChain Reference Docs][9])

But in a tool-calling agent, message order has semantic constraints.

For example:

```text
AIMessage
  tool_call #123

ToolMessage
  tool_call_id=#123
```

must remain logically associated.

Current LangChain documentation specifically warns that `ToolMessage`s normally occur after the `AIMessage` containing the corresponding tool call. ([LangChain Reference Docs][9])

So don't implement:

```python
messages = messages[-10:]
```

or blindly trim arbitrary messages.

That could leave you with:

```text
ToolMessage
```

without its originating tool-call context.

Later, when you study LangGraph context management and summarization, this becomes important. Current LangChain also has context/summarization middleware specifically designed to manage growing agent histories. ([LangChain Reference Docs][10])

---

# 39. Tool errors

What happens if:

```python
await tool.ainvoke(tool_call)
```

fails?

For example:

```text
database timeout
API unavailable
permission denied
invalid arguments
rate limit
```

You have two broad choices.

### Option A — terminate the agent

```python
raise
```

Useful for critical failures.

### Option B — turn the failure into a `ToolMessage`

For example:

```python
ToolMessage(
    content="The weather service is temporarily unavailable.",
    tool_call_id=tool_call["id"],
    status="error",
)
```

Then:

```text
AI
 ↓
Tool failed
 ↓
ToolMessage(error)
 ↓
AI
 ↓
try another strategy
```

Current LangChain supports error-oriented `ToolMessage`s, and its tool execution infrastructure has configurable error handling. ([LangChain Reference Docs][3])

---

# 40. Don't expose raw internal errors to the model

Suppose your database produces:

```text
psycopg.errors.UniqueViolation:
DETAIL:
Key (customer_id)=(847291) already exists...
```

Do you necessarily want to send this entire message to the model?

Probably not.

Instead:

```python
ToolMessage(
    content=(
        "The customer record could not be created "
        "because the customer already exists."
    ),
    tool_call_id=tool_call["id"],
    status="error",
)
```

This is especially important given what you learned in Module 38:

```text
tool output
    ↓
untrusted data
```

The model shouldn't receive arbitrary internal details unnecessarily.

---

# 41. Unknown tools

Never blindly do:

```python
tool = tools_by_name[tool_call["name"]]
```

without thinking about the failure.

Use:

```python
tool = tools_by_name.get(tool_call["name"])

if tool is None:
    return ToolMessage(
        content="The requested tool is not available.",
        tool_call_id=tool_call["id"],
        status="error",
    )
```

Why?

Because the model is not an authority.

It can theoretically emit an unexpected tool name because of:

* model error
* malformed output
* provider bug
* hallucination
* stale state
* compromised context
* prompt injection

Therefore:

```text
model says:
"execute delete_everything"

your registry says:
"that tool does not exist"

→ reject it
```

The model does not get to define what capabilities exist.

---

# 42. The tool registry is a security boundary

Use:

```python
tools_by_name = {
    tool.name: tool
    for tool in tools
}
```

Then only tools in that registry are callable.

Conceptually:

```text
                 Model
                   ↓
              tool request
                   ↓
           ┌───────────────┐
           │ Tool registry │
           └───────┬───────┘
                   │
          ┌────────┼────────┐
          ↓        ↓        ↓
       search   database   CRM
```

This connects directly to your Module 38 work on allowlists and security gates.

---

# 43. Now combine everything

Let's build a more production-oriented manual loop.

The goal isn't to make this “framework-sized” yet.

The goal is to learn the architecture.

```python
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.messages import HumanMessage, ToolMessage
from langchain.tools import tool
from langchain_core.messages.utils import count_tokens_approximately


@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return f"The weather in {city} is 29°C and cloudy."


@tool
def get_population(city: str) -> str:
    """Get the population of a city."""
    return f"The population of {city} is approximately 20 million."


TOOLS = [
    get_weather,
    get_population,
]

TOOLS_BY_NAME = {
    tool.name: tool
    for tool in TOOLS
}

# Only use this type of caching for tools you know
# are safe to deduplicate.
READ_ONLY_TOOLS = {
    "get_weather",
    "get_population",
}


@dataclass
class LoopBudget:
    max_iterations: int = 8
    max_total_tokens: int = 12_000
    max_parallel_tools: int = 5

    input_tokens: int = 0
    output_tokens: int = 0

    seen_calls: set[str] = field(default_factory=set)
    cached_results: dict[str, str] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def make_call_signature(tool_call: dict) -> str:
    return json.dumps(
        {
            "name": tool_call["name"],
            "args": tool_call["args"],
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def record_usage(budget: LoopBudget, ai_msg) -> None:
    usage = ai_msg.usage_metadata or {}

    budget.input_tokens += usage.get(
        "input_tokens",
        0,
    )

    budget.output_tokens += usage.get(
        "output_tokens",
        0,
    )


model = ChatGoogleGenerativeAI(
    model="gemini-3.6-flash",
    timeout=60,
    max_retries=2,
)

model_with_tools = model.bind_tools(TOOLS)


async def execute_one_tool(
    tool_call: dict,
    budget: LoopBudget,
    semaphore: asyncio.Semaphore,
) -> ToolMessage:

    tool_name = tool_call["name"]

    tool = TOOLS_BY_NAME.get(tool_name)

    # Security boundary:
    if tool is None:
        return ToolMessage(
            content="The requested tool is not available.",
            tool_call_id=tool_call["id"],
            status="error",
        )

    signature = make_call_signature(tool_call)

    # Duplicate protection.
    if tool_name in READ_ONLY_TOOLS:

        cached = budget.cached_results.get(signature)

        if cached is not None:
            return ToolMessage(
                content=cached,
                tool_call_id=tool_call["id"],
            )

    async with semaphore:

        try:
            result = await tool.ainvoke(tool_call)

        except Exception:
            # Never expose raw internal details to the model.
            return ToolMessage(
                content=(
                    "The tool failed while processing the request."
                ),
                tool_call_id=tool_call["id"],
                status="error",
            )

    # Cache only known-safe read-only tools.
    if tool_name in READ_ONLY_TOOLS:
        budget.seen_calls.add(signature)

        if isinstance(result, ToolMessage):
            budget.cached_results[signature] = result.text
        else:
            budget.cached_results[signature] = str(result)

    return result


async def run_agent(
    user_input: str,
) -> str:

    budget = LoopBudget()

    semaphore = asyncio.Semaphore(
        budget.max_parallel_tools
    )

    messages = [
        HumanMessage(content=user_input)
    ]

    for iteration in range(
        budget.max_iterations
    ):

        # --------------------------------------------------
        # 1. PRE-FLIGHT TOKEN CHECK
        # --------------------------------------------------

        estimated_input_tokens = count_tokens_approximately(
            messages,
            tools=TOOLS,
        )

        remaining_budget = (
            budget.max_total_tokens
            - budget.total_tokens
        )

        reserved_output_tokens = 1_000

        if (
            estimated_input_tokens
            + reserved_output_tokens
            > remaining_budget
        ):
            raise RuntimeError(
                "Agent token budget is too low for another "
                "model iteration."
            )

        # --------------------------------------------------
        # 2. MODEL
        # --------------------------------------------------

        ai_msg = await model_with_tools.ainvoke(
            messages
        )

        # Preserve the complete AIMessage.
        messages.append(ai_msg)

        # --------------------------------------------------
        # 3. ACCOUNT FOR ACTUAL USAGE
        # --------------------------------------------------

        record_usage(
            budget,
            ai_msg,
        )

        if (
            budget.total_tokens
            > budget.max_total_tokens
        ):
            raise RuntimeError(
                "Agent token budget exceeded."
            )

        # --------------------------------------------------
        # 4. STOP IF FINAL ANSWER
        # --------------------------------------------------

        if not ai_msg.tool_calls:
            return ai_msg.text

        # --------------------------------------------------
        # 5. STOP BEFORE SIDE EFFECTS IF THIS IS THE
        #    LAST ALLOWED MODEL ITERATION
        # --------------------------------------------------

        if (
            iteration
            == budget.max_iterations - 1
        ):
            raise RuntimeError(
                "Maximum agent iterations reached "
                "before tool execution."
            )

        # --------------------------------------------------
        # 6. PARALLEL TOOL EXECUTION
        # --------------------------------------------------

        tool_messages = await asyncio.gather(
            *[
                execute_one_tool(
                    tool_call,
                    budget,
                    semaphore,
                )
                for tool_call in ai_msg.tool_calls
            ]
        )

        # --------------------------------------------------
        # 7. ADD TOOL RESULTS TO HISTORY
        # --------------------------------------------------

        messages.extend(tool_messages)

    raise RuntimeError(
        "Agent loop terminated unexpectedly."
    )
```

This is now beginning to look like a real agent runtime.

---

# 44. Let's understand the improved implementation

There are now several layers.

```text
                 User
                  ↓
          ┌───────────────┐
          │ token budget  │
          └───────┬───────┘
                  ↓
              AI model
                  ↓
           AIMessage
                  ↓
       ┌──────────┴──────────┐
       │                     │
   no tool calls          tool calls
       │                     │
       ↓                     ↓
     FINAL             security check
                             ↓
                     duplicate check
                             ↓
                      concurrency limit
                             ↓
                       tool execution
                             ↓
                        ToolMessage
                             ↓
                           model
```

That is an actual agent execution architecture.

---

# 45. One subtle problem with duplicate caching

Our example uses:

```python
cached_results
```

This is appropriate for something like:

```text
get_weather()
```

but you should be very careful for:

```text
get_account_balance()
```

because the value might change during the run.

Even more importantly, don't cache:

```text
create_invoice()
send_email()
delete_document()
charge_card()
```

unless you have a deliberate idempotency strategy.

For enterprise systems, you eventually want to think about:

```text
tool classification

READ_ONLY
IDEMPOTENT_WRITE
NON_IDEMPOTENT_WRITE
DESTRUCTIVE
```

Then the runtime can apply different policies.

For example:

```text
READ_ONLY
→ parallel
→ caching allowed

IDEMPOTENT_WRITE
→ parallel only if business semantics allow it

NON_IDEMPOTENT_WRITE
→ often sequential
→ potentially human approval

DESTRUCTIVE
→ explicit approval
→ audit log
→ policy enforcement
```

This connects directly to your enterprise AI harness architecture.

---

# 46. Tool execution and model execution are different trust zones

This is another important architectural concept.

The model is probabilistic:

```text
MODEL
```

Your tool executor is deterministic policy code:

```text
YOUR APPLICATION
```

So you want:

```text
MODEL
   ↓
REQUEST
   ↓
POLICY CHECK
   ↓
VALIDATION
   ↓
AUTHORIZATION
   ↓
EXECUTION
   ↓
SANITIZED RESULT
   ↓
MODEL
```

Not:

```text
MODEL
   ↓
EXECUTE WHATEVER IT ASKED
```

This is exactly why your previous Module 38 topic—tool security—matters so much.

---

# 47. The model is not the security layer

Suppose you have:

```python
delete_employee(
    employee_id: str
)
```

and the model says:

```text
delete_employee("12345")
```

Your application should still verify:

```text
Does this user have permission?
Is this tool allowed?
Is employee 12345 in this user's scope?
Does this action require approval?
Is the request valid?
Is this operation currently permitted?
```

So:

```text
tool calling ≠ authorization
```

This becomes especially important in your planned enterprise harness.

---

# 48. What happens if the tool itself calls another tool?

This is an important architectural boundary.

Suppose:

```text
Agent
  ↓
search_salesforce()
```

and inside that function:

```text
search_salesforce()
  ↓
another API
```

That's normal.

But you generally don't want arbitrary recursive:

```text
tool
 ↓
agent
 ↓
tool
 ↓
agent
 ↓
tool
```

unless you deliberately design that architecture.

A tool should usually be an execution capability, while the agent loop controls reasoning/orchestration.

---

# 49. Why the model may call tools repeatedly

Don't assume:

```text
user
 ↓
one tool
 ↓
final answer
```

A capable agent could instead do:

```text
User:
"Find the customer with the highest unpaid balance,
check their last three support tickets,
and draft a follow-up email."

Iteration 1:
search customers

Iteration 2:
get customer details

Iteration 3:
search support tickets

Iteration 4:
generate draft
```

Each model turn can choose what to do next based on the newly acquired information.

That is the essence of agentic behavior.

---

# 50. The loop is fundamentally a feedback loop

This is perhaps the best conceptual definition:

```text
Model decision
      ↓
Action
      ↓
Observation
      ↓
Model decision
      ↓
Action
      ↓
Observation
      ↓
...
```

In LangChain terms:

```text
AIMessage
   ↓
ToolCall
   ↓
ToolMessage
   ↓
AIMessage
```

And that is why tool calling is much more powerful than simply asking a model to generate JSON.

---

# 51. Tool calling versus structured output

Don't confuse:

```python
with_structured_output()
```

with:

```python
bind_tools()
```

They can look similar because both involve schemas.

But the purpose is different.

### Structured output

You want:

```text
Model
 ↓
structured object
```

For example:

```python
Person(
    name="Alice",
    age=31,
)
```

### Tool calling

You want:

```text
Model
 ↓
request an action
 ↓
your code executes it
 ↓
result goes back to model
```

The current Gemini integration supports both mechanisms, but they represent different workflows. ([Mintlify][7])

---

# 52. Streaming changes the first part of the loop

So far we've used:

```python
ai_msg = await model.ainvoke(...)
```

which waits until the model response is complete.

With streaming:

```python
async for chunk in model.astream(messages):
    ...
```

tool calls can arrive progressively.

LangChain represents progressive tool calls using tool-call chunks and can aggregate those chunks into a complete message. ([Docs by LangChain][2])

Conceptually:

```text
chunk 1:
name = get_weather

chunk 2:
id = abc

chunk 3:
args = {"ci

chunk 4:
args = ty":"Mumbai"}
```

You should **not execute the tool from incomplete tool-call chunks**.

First collect the complete model message.

Then:

```python
ai_msg.tool_calls
```

becomes usable.

---

# 53. Why `invoke()` is actually good for learning this module

For your learning stage, I recommend:

```python
invoke()
ainvoke()
```

before trying to build:

```python
astream()
astream_events()
```

because streaming adds another dimension:

```text
model generation
+
tool-call aggregation
+
execution loop
```

The core agent loop becomes much harder to understand.

First master:

```text
invoke
 ↓
tool_calls
 ↓
tool execution
 ↓
ToolMessage
 ↓
invoke again
```

Then add streaming.

---

# 54. Current LangChain versus older tutorials

This is especially important because LangChain tutorials on YouTube/blogs age very quickly.

## Current pattern

For new LangChain agent applications:

```python
from langchain.agents import create_agent
```

Current LangChain documentation presents `create_agent()` as the configurable agent harness. ([Docs by LangChain][1])

## Older LangGraph pattern

You will frequently see:

```python
from langgraph.prebuilt import create_react_agent
```

The current LangGraph reference explicitly marks `create_react_agent` as deprecated and says to use:

```python
langchain.agents.create_agent
```

instead. ([LangChain Reference Docs][11])

### But `ToolNode` is still current

This is an important distinction.

`create_react_agent`:

```text
deprecated
```

`ToolNode`:

```text
current
```

`ToolNode` remains useful when you're explicitly building a custom LangGraph workflow and want control over execution. ([LangChain Reference Docs][6])

---

# 55. Current versus older tool messages

You may find older examples using:

```python
FunctionMessage
```

That is an older message representation.

Current LangChain reference explicitly describes `FunctionMessage` as an older version of `ToolMessage` and notes that it lacks `tool_call_id`. ([LangChain Reference Docs][12])

So use:

```python
ToolMessage
```

not:

```python
FunctionMessage
```

for new code.

---

# 56. Current versus older runtime injection

You may also encounter:

```python
InjectedState
InjectedStore
get_runtime()
InjectedToolCallId
```

in older tutorials.

Current LangChain tool documentation says to use:

```python
ToolRuntime
```

as the unified runtime interface for state, context, store, execution information, tool-call ID, and related runtime capabilities. ([Docs by LangChain][13])

That connects directly to your previous Module 38 question about:

```python
ToolRuntime[RequestContext]
```

You are learning the newer architecture.

---

# 57. Current versus old agent construction

You will encounter old patterns such as:

```python
initialize_agent(...)
```

and various older agent constructors.

For new learning, focus your mental model on:

```python
create_agent(...)
```

rather than building new projects around legacy agent APIs.

The current LangChain architecture is:

```text
LangChain
 ├── model
 ├── tools
 ├── middleware
 └── create_agent()
        ↓
     LangGraph runtime
```

Current LangChain documentation describes `create_agent()` as the configurable harness and says Deep Agents builds on the same foundation. ([Docs by LangChain][1])

---

# 58. Current Gemini style

For your preferred Gemini ecosystem:

```python
from langchain_google_genai import ChatGoogleGenerativeAI
```

and:

```python
model = ChatGoogleGenerativeAI(
    model="gemini-3.6-flash"
)
```

is current LangChain integration style. ([Mintlify][7])

Google currently lists `gemini-3.8-flash` as the newest stable Flash model, while `gemini-3.6-flash` remains a stable previous-generation model. The API capabilities include function calling. ([Google AI for Developers][14])

For this lesson I would keep `gemini-3.6-flash` because it is explicitly represented in the current LangChain examples and its agent/tool behavior is the same conceptually; changing the model ID doesn't change the loop architecture.

---

# 59. One Gemini-specific thing to stop doing

Older Gemini tutorials frequently contain:

```python
temperature=0
```

or:

```python
top_p=...
top_k=...
```

Google's July 2026 release notes state that these sampling parameters are deprecated for the newer Gemini model generation. ([Google AI for Developers][15])

Therefore my current tutorial examples deliberately don't add:

```python
temperature=0
```

just because you're building an agent.

That's a useful lesson:

> Don't blindly copy configuration from older model tutorials.

---

# 60. `max_retries` versus your agent loop

This is another distinction worth understanding.

You might configure:

```python
model = ChatGoogleGenerativeAI(
    model="gemini-3.6-flash",
    max_retries=2,
)
```

This is for transient model/API failures.

It is **not** the same thing as:

```python
MAX_ITERATIONS = 8
```

They mean different things:

```text
max_retries
    ↓
"What if this model request fails?"

max_iterations
    ↓
"How many reasoning/tool cycles may this agent perform?"
```

Don't confuse the two.

---

# 61. Don't retry the entire agent blindly

This can create nasty side effects.

Imagine:

```text
agent:
create_invoice()
send_email()
```

Then your whole agent crashes after `send_email()`.

You retry the whole agent from the beginning:

```text
create_invoice()   ← AGAIN
send_email()       ← AGAIN
```

Now you've potentially created:

```text
duplicate invoice
duplicate email
```

This is why retries need to be considered at the proper layer.

```text
network retry
    ↓
usually okay

tool retry
    ↓
depends on idempotency

whole agent retry
    ↓
potentially dangerous
```

For enterprise agents, this is a major architectural issue.

---

# 62. Duplicate detection is actually related to idempotency

These concepts are closely connected.

### Idempotent operation

Calling it once:

```text
set_customer_status("active")
```

Calling it twice:

```text
set_customer_status("active")
set_customer_status("active")
```

still leaves the system in:

```text
active
```

### Non-idempotent operation

Calling twice:

```text
charge_customer(1000)
charge_customer(1000)
```

could produce:

```text
₹1000
+
₹1000
=
₹2000
```

So your agent runtime eventually needs to understand not just:

```text
what tool?
```

but:

```text
what is the tool's side-effect class?
```

That is exactly the kind of capability your planned enterprise harness could eventually enforce globally.

---

# 63. A very useful architecture for your future enterprise harness

You could eventually describe every tool with metadata like:

```python
ToolPolicy(
    name="send_email",
    category="external_action",
    risk="medium",
    read_only=False,
    idempotent=False,
    requires_approval=True,
    max_calls_per_run=3,
)
```

Then your runtime can do:

```text
Model requests tool
        ↓
Tool policy lookup
        ↓
Is it allowed?
        ↓
Does user have permission?
        ↓
Is input valid?
        ↓
Is duplicate?
        ↓
Is approval required?
        ↓
Execute
        ↓
Sanitize output
        ↓
ToolMessage
        ↓
Model
```

Now you're no longer just building:

> “an LLM wrapper.”

You are building an actual **agent execution control plane**.

That's very relevant to the enterprise harness you have been designing.

---

# 64. What MCP changes — and what it doesn't

This module is also important for MCP.

MCP doesn't fundamentally change the agent loop.

Conceptually:

```text
Normal LangChain tool

Python function
      ↓
LangChain Tool


MCP tool

MCP server
      ↓
MCP client/adapter
      ↓
LangChain-compatible tool
```

Once the MCP tool is exposed to the agent as a callable tool, your loop still looks like:

```text
AIMessage
 ↓
tool_call
 ↓
MCP tool invocation
 ↓
result
 ↓
ToolMessage
 ↓
AIMessage
```

Current LangChain provides MCP adapters for bringing MCP targets into the LangChain ecosystem. ([LangChain Reference Docs][16])

So your mental model should be:

> MCP is primarily a **tool interoperability/protocol layer**.
> The agent loop remains the agent loop.

---

# 65. Manual loop versus `ToolNode` versus `create_agent`

This distinction is worth memorizing.

| Layer               | What you control                                       |
| ------------------- | ------------------------------------------------------ |
| Manual `while` loop | Everything                                             |
| `ToolNode`          | Tool execution inside a LangGraph workflow             |
| `create_agent()`    | Full standard agent runtime/harness                    |
| Deep Agents         | Higher-level agent system with additional capabilities |

The current LangChain/LangGraph docs describe `ToolNode` as the reusable execution component for custom workflows, while `create_agent()` is the recommended standard agent abstraction. ([LangChain Reference Docs][6])

---

# 66. Why learn the manual loop if `create_agent()` already exists?

This is the question you should ask.

Why write:

```python
while True:
```

when LangChain already does it?

Because otherwise you won't really understand:

```python
create_agent(...)
```

You'll just know:

> “Some magic object makes agents work.”

Knowing the manual loop lets you understand:

```text
middleware
ToolNode
routing
conditional edges
state
tool_call_id
parallel execution
retry behavior
budgets
interrupts
human-in-the-loop
MCP
observability
```

Then frameworks become abstractions you understand rather than abstractions you blindly trust.

---

# 67. The exact conceptual mapping to LangGraph

Your manual loop:

```python
while True:

    ai_msg = model.invoke(messages)

    messages.append(ai_msg)

    if not ai_msg.tool_calls:
        break

    tool_messages = execute_tools(
        ai_msg.tool_calls
    )

    messages.extend(tool_messages)
```

maps almost directly to:

```text
MODEL node
    ↓
tools_condition
    ↓
TOOL node
    ↓
MODEL node
```

The current LangGraph `tools_condition` is specifically described as routing to tool execution when the last `AIMessage` contains tool calls and ending otherwise. ([LangChain Reference Docs][17])

Once you understand that, LangGraph becomes much easier.

---

# 68. One more advanced issue: parallel state updates

Suppose two tools execute in parallel:

```text
tool A → update balance
tool B → update balance
```

They may both attempt to modify shared state.

Now the problem isn't just:

```text
parallel execution
```

It is:

```text
parallel execution + shared mutable state
```

Current LangChain tool documentation specifically notes that when multiple tools can execute in parallel and modify the same state field, a reducer is needed to resolve concurrent updates. ([Docs by LangChain][13])

This is one of the reasons LangGraph exists.

A plain:

```python
asyncio.gather(...)
```

doesn't automatically solve your state consistency problem.

---

# 69. The production agent loop therefore has several layers

At an advanced level, your mental model should become:

```text
                    USER REQUEST
                         │
                         ▼
                ┌─────────────────┐
                │ Context / State  │
                └────────┬────────┘
                         ▼
                ┌─────────────────┐
                │ Budget checks   │
                └────────┬────────┘
                         ▼
                ┌─────────────────┐
                │      MODEL      │
                └────────┬────────┘
                         ▼
                  AIMessage
                         │
                ┌────────┴────────┐
                │                 │
           tool calls          no calls
                │                 │
                │                 ▼
                │              FINAL
                │
                ▼
       ┌────────────────────┐
       │ Security / Policy  │
       └─────────┬──────────┘
                 ▼
       ┌────────────────────┐
       │ Duplicate checking │
       └─────────┬──────────┘
                 ▼
       ┌────────────────────┐
       │ Concurrency limits │
       └─────────┬──────────┘
                 ▼
       ┌────────────────────┐
       │    TOOL EXECUTION  │
       └─────────┬──────────┘
                 ▼
             ToolMessage
                 │
                 └──────────→ MODEL
```

That is the architecture I want you to internalize.

---

# 70. Current production alternative: middleware

Once you move from educational code to a real LangChain agent, you don't need to implement all those controls manually.

The current LangChain middleware system provides things such as:

```text
ModelCallLimitMiddleware
ToolCallLimitMiddleware
ToolRetryMiddleware
ToolErrorMiddleware
SummarizationMiddleware
HumanInTheLoopMiddleware
ContextEditingMiddleware
```

among others. ([LangChain Reference Docs][18])

For example, current LangChain has:

```text
ModelCallLimitMiddleware
```

for limiting model calls and:

```text
ToolCallLimitMiddleware
```

for controlling tool execution counts. ([LangChain Reference Docs][18])

So your learning progression should be:

```text
FIRST:
implement the loop yourself

THEN:
implement your own guardrails

THEN:
learn the built-in middleware

FINALLY:
decide which built-ins to use
and where custom policy is justified
```

That matches your preference for using mature components instead of unnecessarily maintaining custom infrastructure.

---

# 71. Current versus deprecated/legacy — memorize this table

| Older pattern you may see                                | Current direction                  |
| -------------------------------------------------------- | ---------------------------------- |
| `FunctionMessage`                                        | `ToolMessage`                      |
| `tool(...)` callable style                               | `tool.invoke()` / `tool.ainvoke()` |
| `create_react_agent()`                                   | `create_agent()`                   |
| older state injection patterns                           | `ToolRuntime`                      |
| manually parsing raw provider tool JSON                  | `AIMessage.tool_calls`             |
| manually executing a tool with extracted args everywhere | `tool.invoke(tool_call)`           |
| arbitrary last-N message trimming                        | token/context-aware management     |
| old Gemini sampling configs                              | current Gemini model configuration |

The explicit deprecations are especially clear for `FunctionMessage`, `create_react_agent`, and callable tool invocation. ([LangChain Reference Docs][19])

---

# 72. What you should remember from Module 39

At the deepest level, remember only this:

```text
1. Model receives messages + tool definitions.

2. Model may return:
       AIMessage(tool_calls=[...])

3. Your program validates the requested tools.

4. Your program executes those tools.

5. Tool results become:
       ToolMessage(..., tool_call_id=...)

6. Append:
       AIMessage
       ToolMessage(s)

7. Call the model again.

8. Repeat until:
       no tool calls
       OR a safety/budget/iteration limit is reached.
```

The fundamental loop is:

```python
while True:

    ai_msg = model_with_tools.invoke(messages)

    messages.append(ai_msg)

    if not ai_msg.tool_calls:
        return ai_msg

    for tool_call in ai_msg.tool_calls:
        tool_message = tool.invoke(tool_call)
        messages.append(tool_message)
```

Everything else is the engineering needed to make this safe and production-grade.

---

# 73. The three levels you should now distinguish

### Level 1 — basic tool-calling loop

```text
bind_tools
 ↓
AIMessage
 ↓
tool_calls
 ↓
tool.invoke
 ↓
ToolMessage
 ↓
model
```

### Level 2 — controlled agent loop

```text
basic loop
+
max iterations
+
errors
+
parallel execution
+
duplicate detection
+
token budget
```

### Level 3 — production agent runtime

```text
controlled loop
+
authentication
+
authorization
+
tool policy
+
rate limits
+
timeouts
+
idempotency
+
human approval
+
persistent state
+
context management
+
observability
+
tracing
+
retries
+
durable execution
+
MCP
+
middleware
```

That Level 3 architecture is where your LangChain + LangGraph + Langfuse + Deep Agents learning eventually comes together.

---

# 74. One final exercise I strongly recommend

Before moving to Module 40, build this yourself **without using `create_agent()`**:

```text
User:
"What is the population and weather of Mumbai and Delhi?"
```

Give your loop these four tools:

```text
get_weather(city)
get_population(city)
get_exchange_rate(currency_a, currency_b)
search_company(name)
```

Then make your manual runtime support:

```text
✓ bind_tools()
✓ AIMessage.tool_calls
✓ tool dispatch
✓ parallel execution
✓ ToolMessage
✓ max 6 model iterations
✓ max 4 concurrent tools
✓ unknown-tool rejection
✓ duplicate read-only call caching
✓ cumulative token budget
✓ sanitized tool errors
```

Once you can write that loop yourself and explain **why every line exists**, you have genuinely understood the core of tool-using agents—not merely memorized LangChain syntax.

### The most important code pattern to burn into memory

```python
model_with_tools = model.bind_tools(tools)

messages = [HumanMessage(content=user_input)]

while True:

    # MODEL
    ai_msg = model_with_tools.invoke(messages)

    # Preserve the exact AI message
    messages.append(ai_msg)

    # STOP
    if not ai_msg.tool_calls:
        break

    # EXECUTE TOOLS
    for tool_call in ai_msg.tool_calls:

        tool = tools_by_name[tool_call["name"]]

        tool_message = tool.invoke(tool_call)

        # FEED RESULT BACK
        messages.append(tool_message)

final_answer = ai_msg
```

That small loop is the seed from which `ToolNode`, LangGraph agent graphs, `create_agent()`, middleware, and eventually Deep Agents grow. ([Docs by LangChain][2])

### Sources used

Current LangChain tool/model/agent documentation: ([Docs by LangChain][13])
Current LangGraph `ToolNode` and agent references: ([LangChain Reference Docs][6])
Current LangChain message/tool references: ([LangChain Reference Docs][3])
Current Gemini/LangChain integration and Google model documentation: ([LangChain Reference Docs][4])

[1]: https://docs.langchain.com/oss/python/langchain/agents "Agents - Docs by LangChain"
[2]: https://docs.langchain.com/oss/python/langchain/models "Models - Docs by LangChain"
[3]: https://reference.langchain.com/python/langchain-core/messages/tool/ToolMessage?utm_source=chatgpt.com "ToolMessage | langchain_core | LangChain Reference"
[4]: https://reference.langchain.com/python/langchain-google-genai/chat_models/ChatGoogleGenerativeAI?utm_source=chatgpt.com "ChatGoogleGenerativeAI | langchain_google_genai | LangChain Reference"
[5]: https://api.python.langchain.com/en/latest/tools/langchain_community.tools.financial_datasets.cash_flow_statements.CashFlowStatements.html?utm_source=chatgpt.com "langchain_community.tools.financial_datasets.cash_flow_statements.CashFlowStatements — 🦜🔗 LangChain 0.2.17"
[6]: https://reference.langchain.com/python/langgraph.prebuilt/tool_node/ToolNode?utm_source=chatgpt.com "ToolNode | langgraph.prebuilt | LangChain Reference"
[7]: https://xh-cadd36d0.mintlify.app/oss/python/integrations/chat/google_generative_ai?utm_source=chatgpt.com "ChatGoogleGenerativeAI - Docs by LangChain"
[8]: https://reference.langchain.com/python/langchain-core/messages/utils/count_tokens_approximately?utm_source=chatgpt.com "count_tokens_approximately | langchain_core | LangChain Reference"
[9]: https://reference.langchain.com/python/langchain-core/messages/utils/trim_messages?utm_source=chatgpt.com "trim_messages | langchain_core | LangChain Reference"
[10]: https://reference.langchain.com/python/langchain/agents/middleware/summarization/SummarizationMiddleware?utm_source=chatgpt.com "SummarizationMiddleware | langchain | LangChain Reference"
[11]: https://reference.langchain.com/python/langgraph.prebuilt/chat_agent_executor?utm_source=chatgpt.com "chat_agent_executor | langgraph.prebuilt | LangChain Reference"
[12]: https://reference.langchain.com/python/langchain-core/messages/function?utm_source=chatgpt.com "function | langchain_core | LangChain Reference"
[13]: https://docs.langchain.com/oss/python/langchain/tools "Tools - Docs by LangChain"
[14]: https://ai.google.dev/gemini-api/docs/models?utm_source=chatgpt.com "Models  |  Gemini API  |  Google AI for Developers"
[15]: https://ai.google.dev/gemini-api/docs/changelog?authuser=6&utm_source=chatgpt.com "Release notes  |  Gemini API  |  Google AI for Developers"
[16]: https://reference.langchain.com/python/langchain?utm_source=chatgpt.com "langchain | LangChain Reference"
[17]: https://reference.langchain.com/python/langgraph.prebuilt/tool_node?utm_source=chatgpt.com "tool_node | langgraph.prebuilt | LangChain Reference"
[18]: https://reference.langchain.com/python/langchain/middleware?utm_source=chatgpt.com "middleware | langchain | LangChain Reference"
[19]: https://reference.langchain.com/python/langchain-core/messages/function/FunctionMessage?utm_source=chatgpt.com "FunctionMessage | langchain_core | LangChain Reference"
