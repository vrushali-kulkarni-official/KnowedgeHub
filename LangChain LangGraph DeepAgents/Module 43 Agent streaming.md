Absolutely. This is an important module because once you understand streaming properly, LangChain/LangGraph agents stop feeling like a black box. You start seeing the agent as a running graph whose model output, tool execution, state changes, and nested agents can all be observed as they happen.

One terminology correction before we start: the current LangChain/LangGraph documentation places `values`, `updates`, and `messages` under the lower-level **stream-mode API**, while recommending **Event Streaming** for new applications. Event Streaming was introduced as a typed-projection layer so you can consume messages, state, tool calls, subgraphs, etc. independently instead of manually branching on stream-mode chunks. ([Docs by LangChain][1])

# PHASE 6 — Agents with `create_agent`

## Module 43 — Agent Streaming and Event Streaming

We will build this from the ground up:

1. What streaming actually means in an agent
2. Why agent streaming is different from normal LLM token streaming
3. `stream()` vs `astream()`
4. `stream_mode="values"`
5. `stream_mode="updates"`
6. `stream_mode="messages"`
7. Token streaming in `messages`
8. Streaming tool calls
9. Multiple stream modes
10. `astream_events()`
11. Anatomy of a `StreamEvent`
12. Filtering events
13. Mapping events to your own schema
14. Modern Event Streaming with `version="v3"`
15. Typed projections
16. Multiple concurrent consumers
17. Sub-agents and nested graphs
18. Production architecture for FastAPI
19. Old vs current APIs
20. What you should memorize

---

# 1. First: what does "streaming" actually mean?

Let's start with a normal agent.

Suppose you have:

```text
User
  |
  v
Agent
  |
  +----> LLM
  |        |
  |        +----> "I should call weather tool"
  |
  +----> Tool
  |        |
  |        +----> "32°C, sunny"
  |
  +----> LLM
           |
           +----> "It is 32°C and sunny."
```

Without streaming, your application might do:

```python
result = agent.invoke(...)
```

and wait.

You only get the result when the whole execution is complete.

Conceptually:

```text
time ---------------------------------------------------->

request
  |
  |......................thinking......................|
  |........................tool........................|
  |.................final answer.......................|
  |
                                    result arrives here
```

With streaming, information leaves the agent during execution:

```text
time ---------------------------------------------------->

request
   |
   +--> model step
   |      +--> tool-call chunk
   |      +--> tool-call argument chunk
   |
   +--> tool step
   |      +--> tool result
   |
   +--> model step
          +--> "The"
          +--> " weather"
          +--> " is"
          +--> " sunny"
```

So streaming is not just:

> "print tokens faster."

It is better understood as:

> **Expose pieces of the agent's execution while the execution is still running.**

This distinction is extremely important.

---

# 2. Agent streaming has several different things that can be streamed

An agent has many kinds of information.

For example:

```text
Agent execution

    State
      |
      +---- messages
      +---- user input
      +---- tool results
      +---- intermediate information

    LLM
      |
      +---- text
      +---- reasoning content
      +---- tool-call arguments

    Tools
      |
      +---- start
      +---- progress
      +---- result

    Graph
      |
      +---- node updates
      +---- state snapshots
      +---- subgraph execution
```

Therefore there is no single "stream".

There are different **projections of execution**.

This is why LangGraph provides stream modes such as:

```text
values
updates
messages
custom
checkpoints
tasks
debug
```

and why newer Event Streaming provides typed projections such as:

```text
messages
values
tool_calls
subgraphs
output
extensions
```

The current docs explicitly describe Event Streaming as a layer above the low-level Pregel stream modes. ([Docs by LangChain][2])

---

# 3. `stream()` vs `astream()`

You already know Python async, so this should be straightforward.

## Synchronous

```python
for chunk in agent.stream(...):
    print(chunk)
```

## Asynchronous

```python
async for chunk in agent.astream(...):
    print(chunk)
```

Think:

```text
stream()
   ↓
Iterator

astream()
   ↓
AsyncIterator
```

For a FastAPI backend, you'll very often prefer:

```python
async for chunk in ...
```

because your endpoint can continue participating in the async event loop while the model/tool execution is happening.

---

# 4. `stream_mode`

Now we reach the core of this module.

You can tell LangGraph:

> "What kind of information do I want streamed?"

with:

```python
    stream_mode="values"
```

or:

```python
stream_mode="updates"
```

or:

```python
stream_mode="messages"
```

You can also combine them:

```python
stream_mode=["messages", "updates"]
```

The current low-level stream-mode API supports these modes and more. ([Docs by LangChain][3])

---

# 5. `stream_mode="values"`

## What does `values` mean?

`values` means:

> Give me the **entire state** after each graph step.

This is one of the easiest concepts to understand.

Imagine the state is:

```python
{
    "topic": "ice cream",
    "joke": ""
}
```

First node changes the topic:

```python
{
    "topic": "ice cream and cats"
}
```

The complete state becomes:

```python
{
    "topic": "ice cream and cats",
    "joke": ""
}
```

Then another node creates the joke:

```python
{
    "joke": "This is a joke about ice cream and cats"
}
```

Complete state becomes:

```python
{
    "topic": "ice cream and cats",
    "joke": "This is a joke about ice cream and cats"
}
```

`values` streams the complete state snapshots:

```text
snapshot 1:
{
    topic: "ice cream",
    joke: ""
}

snapshot 2:
{
    topic: "ice cream and cats",
    joke: ""
}

snapshot 3:
{
    topic: "ice cream and cats",
    joke: "This is a joke about ice cream and cats"
}
```

LangGraph's documentation describes `values` exactly this way: full state after each step. ([Docs by LangChain][3])

---

# 6. `values` example

```python
for chunk in agent.stream(
    {
        "messages": [
            {
                "role": "user",
                "content": "What's the weather in Mumbai?"
            }
        ]
    },
    stream_mode="values",
    version="v2",
):
    if chunk["type"] == "values":
        state = chunk["data"]
        print(state)
```

The important mental model is:

```text
values
  |
  +---- current entire state
```

Not:

```text
values
  |
  +---- individual token
```

---

# 7. Why would you use `values`?

`values` is useful when you need to understand or observe the state of the whole graph.

For example:

```text
frontend dashboard
        |
        v
"Current agent state"

messages = [...]
current_tool = ...
retrieved_documents = [...]
answer = ...
```

It can also be useful while learning/debugging.

For example, imagine an agent has state:

```python
{
    "messages": [...],
    "documents": [...],
    "search_results": [...],
    "answer": "...",
    "status": "..."
}
```

You can observe how that state evolves.

---

# 8. But `values` has a major cost

Suppose your state contains:

```python
messages = [
    # 200 previous messages
]
documents = [
    # 50 documents
]
```

Now imagine sending the entire state after every step.

You can end up repeatedly transmitting a large payload.

Conceptually:

```text
Step 1 → 5 KB
Step 2 → 7 KB
Step 3 → 10 KB
Step 4 → 15 KB
Step 5 → 18 KB
```

That's why for a user-facing UI:

```text
values
```

is often not your first choice.

---

# 9. `stream_mode="updates"`

Now we move to:

```python
stream_mode="updates"
```

This is fundamentally different.

Instead of:

> "Give me the whole state"

it means:

> "Tell me what each node just changed."

LangGraph describes `updates` as state updates returned by nodes after each step. ([Docs by LangChain][3])

---

# 10. `values` vs `updates`

Suppose current state is:

```python
{
    "topic": "ice cream",
    "joke": ""
}
```

Node executes:

```python
return {
    "topic": "ice cream and cats"
}
```

With `values`:

```python
{
    "topic": "ice cream and cats",
    "joke": ""
}
```

With `updates`:

```python
{
    "refine_topic": {
        "topic": "ice cream and cats"
    }
}
```

That's the essential distinction:

```text
values
  ↓
"Here is the whole state."

updates
  ↓
"Here is what changed."
```

---

# 11. Example of `updates`

```python
for chunk in agent.stream(
    {
        "messages": [
            {
                 "role": "user",
                "content": "What's the weather in Mumbai?"
            }
        ]
   },
    stream_mode="updates",
    version="v2",
):
    if chunk["type"] == "updates":
        print(chunk["data"])
```

An agent using a tool can conceptually produce:

```python
{
    "model": {
        "messages": [
            AIMessage(...)
        ]
    }
}
```

then:

```python
{
    "tools": {
        "messages": [
            ToolMessage(...)
        ]
    }
}
```

then:

```python
{
    "model": {
        "messages": [
            AIMessage(...)
        ]
    }
}
```

The current LangChain agent streaming documentation shows this model → tools → model progression. ([Docs by LangChain][1])

---

# 12. Why `updates` is extremely useful for agents

Suppose your frontend wants to show:

```text
🤖 Agent is thinking...

🔧 Calling weather tool...

✅ Weather tool finished.

🤖 Preparing final response...
```

You don't necessarily need every token.

You often just need state transitions.

That's where `updates` shines.

For example:

```python
if node_name == "model":
    show("Agent is thinking")

elif node_name == "tools":
    show("Executing tools")
```

---

# 13. `updates` means node/step progress, not token progress

This distinction is essential.

Suppose the LLM generates:

```text
The weather in Mumbai is currently 29°C.
```

`updates` does not mean:

```text
T
Th
The
The weather
...
```

Instead you may get one completed model update:

```text
model updated
```

So:

```text
updates = execution/state progress
messages = LLM message streaming
```

---

# 14. `stream_mode="messages"`

This is the mode people usually mean when they say:

> "I want token streaming."

Current LangGraph documentation describes `messages` as streaming LLM outputs along with metadata. ([Docs by LangChain][3])

For example:

```python
for chunk in agent.stream(
    {
        "messages": [
            {
                "role": "user",
                "content": "Explain quantum computing simply."
            }
        ]
    },
    stream_mode="messages",
    version="v2",
):
    ...
```

Each message-stream chunk contains conceptually:

```text
(message_chunk, metadata)
```

---

# 15. Important: "token" does not necessarily mean one tokenizer token

This is a subtle but important point.

You might see:

```text
"Hello"
" there"
"!"
```

or:

```text
"Hel"
"lo"
" there"
```

or larger chunks.

So don't design your frontend around:

> "Every chunk equals exactly one token."

Instead think:

> "Each chunk is an incremental piece of the model's streamed output."

---

# 16. `messages` gives you more than text

This is where many beginners make a mistake.

They assume:

```python
messages
```

means:

```text
just final answer text
```

No.

An LLM can generate:

```text
text
reasoning content
tool calls
tool-call arguments
other content blocks
```

The modern message/content-block APIs expose these separately. The current LangChain streaming docs show tool-call chunks and text chunks flowing through `messages`. ([Docs by LangChain][1])

---

# 17. Example: normal text streaming

Conceptually:

```text
model
 ↓
"Here"
 ↓
" is"
 ↓
" the"
 ↓
" answer"
```

Your UI can immediately render:

```text
Here is the answer
```

instead of waiting for the complete answer.

That dramatically changes perceived latency.

---

# 18. Example: tool-call streaming

This is much more interesting.

Suppose the model decides:

```python
get_weather(city="Mumbai")
```

The LLM may not generate the whole JSON tool call in one chunk.

You may receive:

```text
name=get_weather
args="{"
args='"city"'
args=':"'
args='Mumbai'
args='"}'
```

LangChain's current docs explicitly show incremental tool-call chunks followed by a finalized parsed tool call. ([Docs by LangChain][1])

So:

```text
messages
```

can let you observe the model constructing the tool call.

---

# 19. This gives us two different levels

Think about it like this:

## Level 1 — raw model generation

```text
tool_call_chunk
tool_call_chunk
tool_call_chunk
...
```

## Level 2 — completed tool call

```python
{
    "name": "get_weather",
    "args": {
        "city": "Mumbai"
    }
}
```

You need to understand this distinction because they solve different problems.

For UI:

```text
"Agent is preparing a tool call..."
```

For execution:

```text
parsed tool call
```

---

# 20. `messages` also gives metadata

An important part of the `messages` stream is:

```python
token, metadata = chunk["data"]
```

Metadata can tell you things such as:

```python
metadata["langgraph_node"]
```

and may contain tags and other information identifying the LLM invocation.

The current docs specifically show filtering by `langgraph_node` and tags. ([Docs by LangChain][3])

---

# 21. Why metadata matters

Imagine your agent has three models:

```text
planner
researcher
final_answer
```

All three generate tokens.

If you simply do:

```python
print(token)
```

you may see:

```text
I
need
to
search
...
The
answer
is
...
```

all mixed together.

Metadata lets you differentiate:

```text
planner → token
researcher → token
final_answer → token
```

That is extremely important in multi-agent systems.

---

# 22. Filtering `messages` by node

Example:

```python
for chunk in agent.stream(
    inputs,
    stream_mode="messages",
    version="v2",
):
    if chunk["type"] != "messages":
        continue

    token, metadata = chunk["data"]

    if metadata.get("langgraph_node") == "model":
        print(token.text, end="", flush=True)
```

The current documentation demonstrates node filtering through `metadata["langgraph_node"]`. ([Docs by LangChain][3])

---

# 23. Filtering with tags

You can also tag model invocations.

Conceptually:

```python
model = model.with_config(
    {"tags": ["final_answer"]}
)
```

Then inspect:

```python
metadata["tags"]
```

and only stream:

```python
if "final_answer" in metadata.get("tags", []):
    ...
```

The current streaming documentation explicitly supports associating tags with LLM invocations and using them to filter streamed messages. ([Docs by LangChain][3])

This is generally much cleaner than hard-coding node names when you want a reusable architecture.

---

# 24. Combining modes

This is extremely useful:

```python
stream_mode=["messages", "updates"]
```

Now you get both:

```text
messages
    ↓
LLM token-level output

updates
    ↓
completed state/node updates
```

The current API returns a unified v2 `StreamPart` structure:

```python
{
    "type": "...",
    "ns": ...,
    "data": ...
}
```

so you can type-narrow based on `chunk["type"]`. ([Docs by LangChain][3]) 

---

# 25. Example: `messages + updates`

```python
for chunk in agent.stream(
    inputs,
    stream_mode=["messages", "updates"],
    version="v2",
):
    kind = chunk["type"]

    if kind == "messages":
        message_chunk, metadata = chunk["data"]

        if message_chunk.text:
            print(message_chunk.text, end="", flush=True)

    elif kind == "updates":
        print("\nSTATE UPDATE:")
        print(chunk["data"])
```

Now you can have:

```text
The weather ...
              ↑
        streamed token

STATE UPDATE
{
    "tools": {
        ...
    }
}
```

---

# 26. Very important architecture distinction

You should mentally separate:

```text
stream modes
```

from:

```text
events
```

They are related, but they're not the same thing.

Think:

```text
                    Agent execution
                           |
             +-------------+-------------+
             |             |             |
             v             v             v
          values        updates       messages
```

These are projections of execution.

`astream_events()` goes deeper.

---

# 27. What is `astream_events()`?

`astream_events()` is the lower-level event stream API from LangChain's Runnable ecosystem.

It gives you execution events such as:

```text
on_chain_start
on_chain_stream
on_chain_end

on_chat_model_start
on_chat_model_stream
on_chat_model_end

on_tool_start
on_tool_end

on_retriever_start
on_retriever_end
```

The current LangChain reference documents this event shape and the event naming scheme. ([LangChain Reference][4])

This is much more detailed than merely:

```text
"something changed"
```

---

# 28. The mental model for `astream_events`

Think of your agent as a huge tree:

```text
Agent
│
├── Model
│   ├── start
│   ├── stream
│   └── end
│
├── Tool
│   ├── start
│   └── end
│
└── Model
    ├── start
    ├── stream
    └── end
```

`astream_events()` lets you watch this lifecycle.

---

# 29. Anatomy of an event

For the v2 event API, an event looks conceptually like:

```python
{
    "event": "on_chat_model_stream",
    "name": "model",
    "run_id": "....",
    "parent_ids": ["...."],
    "tags": [...],
    "metadata": {...},
    "data": {...},
}
```

Current LangChain documents these fields as:

```text
event
name
run_id
parent_ids
tags
metadata
data
```

with `parent_ids` available in v2 rather than v1. ([LangChain Reference][4])

---

# 30. `event`

Example:

```python
event["event"]
```

could be:

```text
on_chat_model_start
on_chat_model_stream
on_chat_model_end
```

or:

```text
on_tool_start
on_tool_end
```

or:

```text
on_chain_start
on_chain_stream
on_chain_end
```

Think:

```text
event
  =
what happened?
```

---

# 31. `name`

Example:

```python
event["name"]
```

might be:

```text
model
get_weather
retriever
format_docs
```

Think:

```text
name
  =
which runnable produced this event?
```

---

# 32. `run_id`

Every runnable execution gets its own identifier.

Suppose:

```text
Agent
  |
  +-- Model run
  |
  +-- Tool run
  |
  +-- Model run
```

Each can have its own:

```text
run_id
```

Example:

```text
agent run = A
model run = B
tool run  = C
model run = D
```

This is extremely useful for:

```text
tracing
debugging
correlation
observability
log aggregation
latency analysis
```

---

# 33. `parent_ids`

This is one of the most important advanced fields.

Suppose:

```text
Agent
└── Model
    └── Tool
```

You can conceptually have:

```text
Agent:
run_id = A
parent_ids = []

Model:
run_id = B
parent_ids = [A]

Tool:
run_id = C
parent_ids = [A, B]
```

This lets you reconstruct execution hierarchy.

The current reference explicitly describes `parent_ids` as ordered from root to immediate parent and available in the v2 API. ([LangChain Reference][5])

---

# 34. Why `parent_ids` becomes incredibly important later

When you build your enterprise AI harness, you'll eventually have:

```text
HTTP request
  |
  +-- supervisor agent
       |
       +-- research agent
       |    |
       |    +-- web search
       |
       +-- CRM agent
       |    |
       |    +-- Salesforce tool
       |
       +-- final response model
```

Without hierarchy information, logs become very difficult to understand.

With:

```text
run_id
parent_ids
```

you can reconstruct:

```text
request
  └── supervisor
       ├── researcher
       │    └── search
       ├── crm
       │    └── salesforce
       └── final model
```

This is one of the reasons event streaming is much more powerful than just printing tokens.

---

# 35. `tags`

Events can also carry tags.

For example:

```python
tags = ["customer-facing", "final-answer"]
```

You can then filter or route events.

This is useful for:

```text
UI streams
logging
monitoring
security
tracing
tenant routing
```

The event reference supports inclusion/exclusion by names, types, and tags. ([LangChain Reference][4])

---

# 36. `metadata`

Metadata is contextual information attached to a run.

For example:

```python
{
    "langgraph_node": "model",
    ...
}
```

You may also attach your own metadata through configuration.

Think:

```text
tags
  =
labels/categories

metadata
  =
structured contextual information
```

---

# 37. `data`

This is the interesting part.

`data` contains the actual payload associated with the event.

For:

```text
on_chat_model_start
```

you may see input.

For:

```text
on_chat_model_stream
```

you may get an `AIMessageChunk`.

For:

```text
on_chat_model_end
```

you get the output.

For:

```text
on_tool_start
```

you get tool input.

For:

```text
on_tool_end
```

you get tool output.

This is documented in the current event reference. ([LangChain Reference][4])

---

# 38. Typical model event lifecycle

Imagine:

```text
on_chat_model_start
        |
        v
on_chat_model_stream
        |
        v
on_chat_model_stream
        |
        v
on_chat_model_stream
        |
        v
on_chat_model_end
```

For example:

```python
{
    "event": "on_chat_model_start",
    ...
}
```

then:

```python
{
    "event": "on_chat_model_stream",
    "data": {
        "chunk": AIMessageChunk(...)
    },
    ...
}
```

then finally:

```python
{
    "event": "on_chat_model_end",
    "data": {
        "output": ...
    },
    ...
}
```

---

# 39. Tool lifecycle

Likewise:

```text
on_tool_start
      |
      v
      tool executes
      |
      v
on_tool_end
```

For example:

```python
{
    "event": "on_tool_start",
    "name": "get_weather",
    "data": {
        "input": {
            "city": "Mumbai"
        }
    }
}
```

followed by:

```python
{
    "event": "on_tool_end",
    "name": "get_weather",
    "data": {
        "output": "29°C and sunny"
    }
}
```

---

# 40. Why use `astream_events()` instead of `messages`?

This distinction is critical.

Use `messages` when your problem is:

> "I want model output."

Use `astream_events` when your problem is:

> "I want to observe execution."

For example:

```text
messages
    ↓
"Hello world"
```

while events give you:

```text
model started
model streamed
model streamed
tool started
tool ended
model started
model streamed
model ended
```

---

# 41. `astream_events()` and filtering

Suppose you only care about tools.

The current API supports filters such as:

```python
include_names
include_types
include_tags

exclude_names
exclude_types
exclude_tags
```

These are part of the documented `astream_events` interface. ([LangChain Reference][4])

Example:

```python
async for event in agent.astream_events(
    inputs,
    version="v2",
    include_types=["tool"],
):
    print(event)
```

Conceptually:

```text
model events ❌

retriever events ❌

tool events ✅
```

---

# 42. Filter by tool name

```python
async for event in agent.astream_events(
    inputs,
    version="v2",
    include_names=["get_weather"],
):
    print(event)
```

Now your consumer only sees events from the desired runnable.

---

# 43. Filter by tag

Suppose a model has:

```python
tags=["final-answer"]
```

Then:

```python
async for event in agent.astream_events(
    inputs,
    version="v2",
    include_tags=["final-answer"],
):
    ...
```

This becomes very powerful when you have a complex graph.

---

# 44. Excluding events

You can also do:

```python
exclude_types=["retriever"]
```

or:

```python
exclude_tags=["internal"]
```

This is especially useful when your internal agent has a lot of noisy activity but the frontend only needs a small subset.

---

# 45. Don't send raw LangChain events directly to your frontend

This is a very important production lesson.

It is tempting to do:

```text
LangChain event
       ↓
JSON
       ↓
Frontend
```

I would not make your frontend depend directly on LangChain's internal event schema.

Instead:

```text
LangChain
   ↓
event adapter
   ↓
your application event schema
   ↓
SSE/WebSocket
   ↓
frontend
```

This gives you a stable contract.

---

# 46. Your own application event schema

Since you already know Pydantic, define something like:

```python
from typing import Any, Literal
from pydantic import BaseModel

class AgentStreamEvent(BaseModel):
    type: Literal[
        "token",
        "tool_start",
        "tool_end",
        "state_update",
        "error",
    ]
    run_id: str
    node: str | None = None
    content: Any = None
```

Now your frontend doesn't need to know what:

```text
on_chat_model_stream
```

means.

Instead it receives:

```json
{
  "type": "token",
  "run_id": "abc",
  "node": "model",
  "content": "Hello"
}
```

---

# 47. Mapping raw events into your schema

For `astream_events(version="v2")`:

```python
from collections.abc import AsyncIterator

async def stream_agent_events(
    agent,
    inputs: dict,
) -> AsyncIterator[AgentStreamEvent]:

    async for event in agent.astream_events(
        inputs,
        version="v2",
    ):
        event_name = event["event"]
 
        if event_name == "on_chat_model_stream":
            chunk = event["data"]["chunk"]

            yield AgentStreamEvent(
                type="token",
                run_id=event["run_id"],
                node=event["name"],
                content=chunk.text,
            )

        elif event_name == "on_tool_start":
            yield AgentStreamEvent(
                type="tool_start",
                run_id=event["run_id"],
                node=event["name"],
                content=event["data"].get("input"),
            )

        elif event_name == "on_tool_end":
            yield AgentStreamEvent(
                type="tool_end",
                run_id=event["run_id"],
                node=event["name"],
                content=event["data"].get("output"),
            )
```

Now you have an adapter layer.

---

# 48. Why the adapter architecture is important

Your backend might currently use:

```text
LangChain
```

Later you may use:

```text
LangGraph
```

then:

```text
Deep Agents
```

then another execution system.

You don't want the frontend coupled to:

```python
on_chat_model_stream
```

or:

```python
ToolCallTransformer
```

or:

```python
MessagesStreamPart
```

Instead:

```text
Internal framework events
          ↓
Application event model
          ↓
API transport
```

This is a very strong enterprise architecture pattern.

---

# 49. One subtle problem with token mapping

Suppose the event contains:

```python
chunk.text
```

but it is:

```text
"Hello"
```

then:

```text
" world"
```

then:

```text
"!"
```

Your frontend should append:

```python
current_text += chunk
```

rather than replace:

```python
current_text = chunk
```

Otherwise you'll get:

```text
!
```

instead of:

```text
Hello world!
```

This is a basic streaming implementation rule.

---

# 50. Token stream ≠ final response

You also need to understand that streamed text is incremental.

During streaming:

```text
token 1
token 2
token 3
...
```

At the end:

```text
final AIMessage
```

Your application often needs both:

```text
live deltas
+
final structured result
```

This becomes particularly important for:

```text
usage metadata
tool calls
structured output
citations
final message IDs
```

---

# 51. The current major evolution: Event Streaming

Now we reach the most important modern distinction.

Current LangChain documentation says:

> for new applications, use Event Streaming.

The newer system gives you typed projections rather than forcing you to inspect every low-level stream-mode chunk. ([Docs by LangChain][6])

---

# 52. Think of Event Streaming as a higher-level API

Old mental model:

```text
agent
  ↓
stream_mode
  ↓
mixed chunks
  ↓
you inspect chunk["type"]
```

New mental model:

```text
agent
  ↓
Event Stream
  ├── messages
  ├── tool_calls
  ├── values
  ├── subgraphs
  ├── output
  └── extensions
```

Much cleaner.

---

# 53. Modern `version="v3"`

For a current `create_agent`, you can do:

```python
stream = agent.stream_events(
    inputs,
    version="v3",
)
```

Then:

```python
for message in stream.messages:
    ...
```

instead of:

```python
for chunk in agent.stream(...):
    if chunk["type"] == "messages":
        ...
```

The current Event Streaming documentation recommends `version="v3"` for application/frontend use. ([Docs by LangChain][6])

There is an important nuance, however: the current Python reference still marks v3 as beta/experimental, so it is the newest/recommended direction but not as mature/stable as the older v2 event schema. ([LangChain Reference][7])

---

# 54. `stream.messages`

Modern API:

```python
stream = agent.stream_events(
    inputs,
    version="v3",
)

for message in stream.messages:
    for text_delta in message.text:
        print(text_delta, end="", flush=True)
```

This is much easier than manually parsing:

```python
event["event"]
event["data"]
event["chunk"]
```

---

# 55. `message.text`

Modern message streams provide:

```python
message.text
```

which exposes text deltas.

You can think:

```text
message
   |
   +--- text
   +--- reasoning
   +--- tool_calls
   +--- output
```

The current API documents all of these projections. ([Docs by LangChain][6])

---

# 56. `message.reasoning`

For models that expose reasoning content:

```python
for message in stream.messages:
    for delta in message.reasoning:
        ...
```

This is separate from normal text.

Current LangChain normalizes provider-specific reasoning formats into standard content-block types. ([Docs by LangChain][1])

Do not build an application assuming every model exposes reasoning.

Provider/model support varies.

---

# 57. `message.tool_calls`

Modern typed streaming also exposes tool-call chunks:

```python
for message in stream.messages:
    for chunk in message.tool_calls:
        print(chunk)
```

Then you can obtain finalized tool calls:

```python
finalized = message.tool_calls.get()
```

The current Event Streaming docs explicitly distinguish model-side streamed tool-call arguments from tool execution lifecycle events. ([Docs by LangChain][6])

This distinction is important:

```text
message.tool_calls
    =
model is generating the tool call

stream.tool_calls
    =
tool execution lifecycle
```

---

# 58. `stream.tool_calls`

This is a really useful projection.

```python
for call in stream.tool_calls:
    print(call.tool_name)
    print(call.input)

    for delta in call.output_deltas:
        print(delta, end="")

    print(call.output)
```

Conceptually:

```text
model says:
  "call get_weather(city=Mumbai)"

        ↓

tool starts

        ↓

tool streams output/progress

        ↓

tool finishes
```

---

# 59. `stream.values`

Modern Event Streaming also provides:

```python
for snapshot in stream.values:
    print(snapshot)
```

So the conceptual relationship becomes:

```text
old/low-level:

stream_mode="values"

modern Event Streaming:

stream.values
```

Event Streaming therefore isn't removing the concept of state snapshots.

It's exposing them through a cleaner projection.

The current docs explicitly show `stream.values` for state snapshots and `stream.output` for the final state. ([Docs by LangChain][6])

---

# 60. `stream.output`

At the end:

```python
final_state = stream.output
```

This gives the final agent state.

This is distinct from:

```python
stream.values
```

which produces intermediate snapshots.

Think:

```text
stream.values
    ↓
many snapshots

stream.output
    ↓
one final result
```

---

# 61. `stream.subgraphs`

This becomes particularly important when you reach Deep Agents.

Suppose:

```text
Supervisor
   |
   +---- Research Agent
   |
   +---- CRM Agent
   |
   +---- Email Agent
```

You don't want to manually parse namespace strings everywhere.

Modern Event Streaming provides:

```python
stream.subgraphs
```

and dedicated named-agent/subgraph projections.

The current documentation describes `stream.subgraphs` for nested graph executions and `stream.subagents` for named `create_agent` sub-agents. ([Docs by LangChain][6])

---

# 62. Async Event Streaming

This is important for your FastAPI backend.

With the current v3 API:

```python
stream = await agent.astream_events(
    inputs,
    version="v3",
)
```

Then:

```python
async for message in stream.messages:
    ...
```

The current reference documents `astream_events(version="v3")` as returning an async run stream for compiled graphs. ([LangChain Reference][8])

So don't confuse these two APIs:

### Older/raw v2 event API

```python
async for event in agent.astream_events(
    inputs,
    version="v2",
):
    ...
```

### Modern v3 typed Event Streaming

```python
stream = await agent.astream_events(
    inputs,
    version="v3",
)

async for message in stream.messages:
    ...
```

That's a very important distinction.

---

# 63. Multiple projections concurrently

This is one of the best features of the modern architecture.

Imagine you want:

```text
messages
+
tool calls
+
state
```

You don't necessarily need to merge all of those yourself.

The modern event stream supports multiple projections independently.

For example:

```python
import asyncio

stream = await agent.astream_events(
    inputs,
    version="v3",
)


async def consume_messages():
    async for message in stream.messages:
        async for text in message.text:
            print("[TEXT]", text)


async def consume_tools():
    async for call in stream.tool_calls:
        print("[TOOL]", call.tool_name)


await asyncio.gather(
    consume_messages(),
    consume_tools(),
)
```

The current docs explicitly show concurrent projection consumption with `asyncio.gather`. ([Docs by LangChain][6])

---

# 64. Why this is better than a giant `if/elif`

With low-level streaming:

```python
async for chunk in ...:
    if chunk["type"] == "messages":
        ...
    elif chunk["type"] == "updates":
        ...
    elif chunk["type"] == "custom":
        ...
```

With Event Streaming:

```python
stream.messages
stream.tool_calls
stream.values
stream.subgraphs
```

Each consumer has one responsibility.

This matches good software architecture:

```text
message consumer
      ≠
tool consumer
      ≠
state consumer
```

---

# 65. Raw v3 events still exist

You may eventually need something that doesn't have a convenient typed projection.

You can iterate the raw protocol stream:

```python
for event in stream:
    ...
```

The current docs show the raw structure as:

```python
event["method"]
event["params"]["namespace"]
event["params"]["data"]
```

This is useful when debugging or building a custom transformer/projection. ([Docs by LangChain][6])

So even the new system doesn't take away low-level access.

It adds higher-level access.

---

# 66. Mapping Event Streaming to your own schema

This is where I recommend you go in your enterprise harness.

Suppose your frontend only understands:

```python
class UIEvent(BaseModel):
    type: Literal[
        "assistant_text",
        "tool_started",
        "tool_finished",
        "agent_started",
        "agent_finished",
    ]

    run_id: str
    agent: str | None = None
    tool: str | None = None
    text: str | None = None
    data: dict | None = None
```

Then your infrastructure owns the contract.

For example:

```text
LangChain / LangGraph
        |
        v
Stream adapter
        |
        v
UIEvent
        |
        v
SSE
        |
        v
React frontend
```

That's much more maintainable.

---

# 67. SSE architecture for FastAPI

For your project, a common production architecture would be:

```text
                    ┌──────────────────┐
HTTP request ──────>│ FastAPI endpoint │
                    └────────┬─────────┘
                             |
                             v
                        create_agent
                             |
                             v
                     Event Streaming
                             |
               ┌─────────────┼──────────────┐
               v             v              v
           messages      tool_calls       values
               \             |              /
                \            |             /
                 └────── adapter ─────────┘
                             |
                             v
                       UIEvent schema
                             |
                             v
                         SSE stream
                             |
                             v
                         frontend
```

This is a very natural architecture for your AI-harness project.

---

# 68. Example FastAPI-style event adapter

Conceptually:

```python
from collections.abc import AsyncIterator
from pydantic import BaseModel


class UIEvent(BaseModel):
    type: str
    run_id: str
    data: dict


async def generate_events(
    agent,
    inputs: dict,
) -> AsyncIterator[UIEvent]:

    stream = await agent.astream_events(
        inputs,
        version="v3",
    )

    async for message in stream.messages:
        async for delta in message.text:
            yield UIEvent(
                type="assistant_text",
                run_id=message.message_id,
                data={
                    "text": delta,
                },
            )
```

Then another consumer can deal with:

```python
stream.tool_calls
```

and create:

```python
UIEvent(
    type="tool_started",
    ...
)
```

Your frontend never needs to know LangGraph internals.

---

# 69. Very important: don't leak sensitive event data

This is especially relevant to your enterprise AI harness.

Raw events can contain:

```text
tool inputs
tool outputs
metadata
prompts
retrieved documents
internal state
potentially sensitive information
```

You generally should **not** blindly forward:

```python
event
```

to the browser.

Instead:

```text
raw event
   ↓
authorization
   ↓
redaction
   ↓
mapping
   ↓
UI event
```

This is also one reason the current Event Streaming system provides transformer hooks; the documentation specifically describes output transformations and PII redaction use cases. ([Docs by LangChain][6])

---

# 70. Custom streaming

Sometimes none of the standard projections express what you want.

Suppose your tool performs a 1000-row synchronization:

```text
Fetching records...

100 / 1000

200 / 1000

300 / 1000
```

The LLM isn't generating those messages.

The tool itself is doing work.

You can use:

```python
from langgraph.config import get_stream_writer
```

and emit custom data.

For example:

```python
def sync_records():
    writer = get_stream_writer()

    writer({
        "type": "progress",
        "completed": 100,
        "total": 1000,
    })
```

The low-level API exposes this through `stream_mode="custom"`. ([Docs by LangChain][3])

---

# 71. Why custom streaming matters to agents

Imagine:

```text
Agent
 |
 +-- search tool
 |
 +-- database tool
 |
 +-- Salesforce sync tool
 |
 +-- document processing tool
```

Not every useful event comes from the LLM.

You may want:

```text
document 1 processed
document 2 processed
document 3 processed
```

or:

```text
CRM sync: 47/1000
```

That is a **domain event**, not an LLM token.

This is an important architectural distinction:

```text
LLM stream
    ≠
application progress stream
```

---

# 72. `messages` vs `custom`

Use:

```text
messages
```

when the source is LLM-generated content.

Use:

```text
custom
```

when your application/tool/node generates its own progress or domain data.

For example:

```text
"Here is the answer..."
       ↓
messages

"Downloaded 17 of 20 files"
       ↓
custom
```

---

# 73. `values` vs `updates` vs `messages` in one picture

Memorize this:

```text
                    Agent execution
                           |
        ┌──────────────────┼──────────────────┐
        |                  |                  |
        v                  v                  v
      values            updates           messages
        |                  |                  |
        v                  v                  v
  whole state        changed state      LLM chunks
  snapshots            updates          + metadata
```

And:

```text
custom
   ↓
your own application-generated events
```

---

# 74. The deeper architecture: Pregel → events → projections

The current LangGraph architecture documents the relationship roughly as:

```text
Pregel execution engine
        |
        v
raw graph events
        |
        v
event router
        |
        v
stream transformers
        |
        v
typed projections
```

The underlying low-level events include:

```text
updates
values
messages
custom
checkpoints
tasks
debug
```

and the Event Streaming layer turns them into projections such as:

```text
stream.messages
stream.values
stream.subgraphs
stream.output
stream.extensions
```

This architecture is explicitly described in the current LangGraph event-streaming documentation. ([Docs by LangChain][2])

---

# 75. This explains why `stream_mode` still exists

You might reasonably ask:

> "If Event Streaming is recommended, why hasn't `stream_mode` disappeared?"

Because the two solve different levels of problems.

### Low-level control

```python
stream_mode="updates"
```

Useful when you want direct access to graph execution semantics.

### Application-friendly abstraction

```python
stream.messages
stream.values
stream.tool_calls
```

Useful when you're building an application/UI.

Current LangGraph documentation explicitly says to use low-level streaming modes when you need direct access to graph-runtime events, and Event Streaming when your application benefits from typed projections. ([Docs by LangChain][3])

---

# 76. Current vs old/deprecated/experimental

This part is especially important because you asked me not to teach deprecated patterns.

| API/pattern                      | Current status                                     | What you should learn         |
| -------------------------------- | -------------------------------------------------- | ----------------------------- |
| `stream()`                       | Current                                            | Yes                           |
| `astream()`                      | Current                                            | Yes                           |
| `stream_mode="values"`           | Current                                            | Yes                           |
| `stream_mode="updates"`          | Current                                            | Yes                           |
| `stream_mode="messages"`         | Current                                            | Yes                           |
| `stream_mode="custom"`           | Current                                            | Yes                           |
| `version="v2"` for stream output | Current/stable low-level format                    | Yes                           |
| legacy v1 stream output shape    | Compatibility/older style                          | Avoid for new code            |
| `astream_events(version="v2")`   | Current low-level event API                        | Yes, understand deeply        |
| `astream_events(version="v1")`   | Backward compatibility                             | Avoid in new code             |
| `stream_events(version="v3")`    | New typed Event Streaming                          | Learn now                     |
| `astream_events(version="v3")`   | New typed async Event Streaming                    | Learn now                     |
| v3 typed event protocol          | Current direction, but currently beta/experimental | Learn, but know it can evolve |

The current references retain v1 for backwards compatibility, while v2 is the unified raw event/stream shape and v3 is the newer typed projection protocol. The current Python reference marks v3 as beta/experimental. ([Docs by LangChain][3])

So I would **not** teach you:

```python
version="v1"
```

as your normal implementation style.

---

# 77. One very important distinction: `version` is NOT model version

This is a frequent beginner confusion.

When you write:

```python
version="v2"
```

you are **not** saying:

```text
Gemini v2
```

or:

```text
LLM version 2
```

It refers to the **streaming protocol/output format**.

For example:

```python
stream_mode="messages"
version="v2"
```

means:

```text
what do I want?
    messages

how should the stream chunks be represented?
    v2 format
```

---

# 78. Gemini example

Since you prefer Gemini, the current official LangChain integration is:

```python
from langchain_google_genai import ChatGoogleGenerativeAI
```

and the current documentation shows models such as:

```python
model = ChatGoogleGenerativeAI(
    model="gemini-3.7-flash"
)
```

The integration currently uses Google's consolidated `google-genai` SDK in `langchain-google-genai` 4.x. ([Docs by LangChain][9])

A basic agent could therefore look like:

```python
from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI


model = ChatGoogleGenerativeAI(
    model="gemini-3.7-flash",
)

agent = create_agent(
    model=model,
    tools=[],
)
```

The streaming architecture itself is provider-independent.

---

# 79. Gemini doesn't change the streaming concepts

Your architecture remains:

```text
Gemini
   ↓
ChatGoogleGenerativeAI
   ↓
create_agent
   ↓
LangGraph execution
   ↓
streaming
```

So if later you replace Gemini with:

```text
Ollama
OpenAI-compatible endpoint
another provider
self-hosted model
```

your higher-level streaming architecture can remain largely the same.

This is very relevant to your vendor-independent AI harness goal.

---

# 80. A production mental model I want you to memorize

Think of an agent execution as producing **four broad categories of information**:

```text
1. STATE

   "What is the graph's current state?"

   ↓
   values / state projection


2. PROGRESS

   "What did the graph/node just do?"

   ↓
   updates


3. MODEL OUTPUT

   "What is the LLM generating right now?"

   ↓
   messages


4. DOMAIN EVENTS

   "What is my application/tool doing?"

   ↓
   custom / extensions
```

Then Event Streaming gives you higher-level typed access to those concerns.

---

# 81. Example: real enterprise agent

Imagine your future enterprise harness handles:

> "Find the latest sales report, summarize it, and send it to my manager."

Your agent might do:

```text
User
 |
 v
Supervisor
 |
 +--> Google Drive search
 |
 +--> Document retrieval
 |
 +--> summarization model
 |
 +--> email tool
 |
 +--> final model
```

What would you stream?

### `messages`

```text
"Searching your Drive..."
"Found the report..."
"Here is the summary..."
```

### `updates`

```text
search node completed
retrieval node completed
email node completed
```

### `values`

```text
entire graph state
```

### `tool_calls`

```text
google_drive.search(...)
email.send(...)
```

### `custom`

```text
Downloaded 5 / 5 documents
Parsing report...
Sending email...
```

This is why learning streaming now is foundational for your larger system.

---

# 82. What I would use for your project

For your AI enterprise harness, I'd think about it like this:

### Learning/debugging

```python
stream_mode="values"
```

or:

```python
stream_mode="updates"
```

### Basic user token streaming

```python
stream_mode="messages"
```

### Advanced low-level instrumentation

```python
astream_events(..., version="v2")
```

### New application/frontend architecture

```python
astream_events(..., version="v3")
```

with:

```python
stream.messages
stream.tool_calls
stream.values
stream.subgraphs
stream.output
```

### Production API

```text
LangGraph/LangChain stream
        ↓
your typed Pydantic event model
        ↓
SSE/WebSocket
        ↓
frontend
```

---

# 83. A common beginner mistake

Don't do this:

```python
async for event in agent.astream_events(...):
    print(event)
```

and then expose all of it directly to the frontend.

That couples:

```text
frontend
    ↓
LangChain internals
```

Instead:

```text
LangChain
    ↓
stream adapter
    ↓
Pydantic application events
    ↓
transport
    ↓
frontend
```

The frontend should understand **your application protocol**, not LangChain internals.

---

# 84. Another common mistake

Don't assume:

```python
messages = final answer tokens
```

Messages can also carry:

```text
tool-call chunks
reasoning content
other content blocks
model metadata
```

So robust handling usually starts with:

```python
message_chunk.content_blocks
```

or, in the newer typed API:

```python
message.text
message.reasoning
message.tool_calls
message.output
```

The current LangChain docs emphasize these separate content/projection types. ([Docs by LangChain][6])

---

# 85. Another common mistake

Don't use `values` when you really need text streaming.

This:

```python
stream_mode="values"
```

is not a replacement for:

```python
stream_mode="messages"
```

They answer different questions.

```text
values:
"What is the complete state now?"

messages:
"What is the model emitting right now?"
```

---

# 86. Another common mistake

Don't assume streaming happens only when using `.stream()`.

LangGraph's message streaming system can expose LLM messages even when the internal LLM invocation itself uses `.invoke()`, because the graph streaming layer observes the model execution. The current documentation explicitly notes this behavior. ([Docs by LangChain][3])

That is a subtle but useful concept:

```text
your node:
    model.invoke()

graph:
    stream_mode="messages"

→ message stream can still be observed
```

---

# 87. Another advanced issue: sub-agents

Suppose:

```text
Supervisor
   |
   +-- Research Agent
   |
   +-- Coding Agent
```

If you simply consume:

```python
stream.messages
```

you may need to know which model invocation produced each message.

Modern Event Streaming gives you subgraph/sub-agent projections and namespaces/metadata so you can identify nested execution. ([Docs by LangChain][6])

This will become especially important when you reach:

```text
Deep Agents
sub-agents
middleware
handoffs
MCP
multi-agent systems
```

---

# 88. Another advanced issue: exact arrival order

Suppose you have:

```text
messages
tool_calls
values
```

and consume them independently.

You are asking different projections different questions.

If you need:

> "Give me everything in the exact order it arrived."

then you want the raw event stream / interleaving facility rather than independently reading separate projections.

The current Event Streaming API provides `stream.interleave(...)` for synchronous use, while async code can consume projections concurrently. ([Docs by LangChain][6])

---

# 89. `interleave`

For example:

```python
stream = agent.stream_events(
    inputs,
    version="v3",
)

for kind, item in stream.interleave(
    "messages",
    "tool_calls",
    "values",
):
    if kind == "messages":
        print(item.text)

    elif kind == "tool_calls":
        print(item.tool_name)

    elif kind == "values":
        print(item)
```

Conceptually:

```text
message
message
message
tool_call
tool_call
value
message
```

instead of:

```text
all messages first
all tools later
all state later
```

This makes `interleave()` valuable for event-driven UI rendering. ([Docs by LangChain][6])

---

# 90. The relationship between old and modern APIs

Here's the picture I want you to remember:

```text
                LangGraph execution
                        |
                        v
              ┌─────────────────┐
              │ Low-level stream│
              └─────────────────┘
                 /      |      \
                /       |       \
           values     updates   messages
                \       |       /
                 \      |      /
                  \     |     /
                   v    v    v
              Event Streaming
                      |
         ┌────────────┼─────────────┐
         v            v             v
      messages    tool_calls     subgraphs
         |
         v
     text/reasoning/tool_calls
```

So the newer system is not a completely separate mechanism.

It is a higher-level projection architecture over the execution stream.

---

# 91. The most important conceptual difference

I want you to be able to answer this without looking it up:

### `values`

> "Give me the entire state after each step."

### `updates`

> "Give me the state changes produced by each step."

### `messages`

> "Give me model message chunks as they are produced."

### `astream_events(v2)`

> "Give me detailed lifecycle events from the execution tree."

### `stream_events(v3)`

> "Give me typed projections of the execution stream so I can consume messages, tool calls, values, subgraphs, output, etc. independently."

That is the conceptual foundation of this module.

---

# 92. Recommended learning order for you

Because you've already completed tools/MCP and `create_agent`, I recommend you mentally learn this module in exactly this order:

```text
1. stream()
2. astream()
3. stream_mode
4. values
5. updates
6. messages
7. message metadata
8. tool-call chunks
9. multiple modes
10. astream_events(v2)
11. event anatomy
12. run_id / parent_ids
13. filtering
14. event → Pydantic mapping
15. Event Streaming v3
16. typed projections
17. tool_calls projection
18. subgraphs
19. concurrent consumers
20. FastAPI SSE architecture
```

Don't jump straight to v3 without understanding `values`, `updates`, and `messages`.

Otherwise you'll know the API but not understand what it is abstracting.

---

# 93. Your "cheat sheet"

```text
agent.invoke()
    ↓
wait for final result

agent.stream()
    ↓
synchronous streaming

agent.astream()
    ↓
asynchronous streaming
```

### Low-level stream modes

```text
values
    = complete state snapshot

updates
    = state changes

messages
    = LLM message chunks

custom
    = application-defined streaming data
```

### Raw event API

```text
astream_events(version="v2")
    ↓
on_* lifecycle events
```

Example:

```text
on_chat_model_start
on_chat_model_stream
on_chat_model_end

on_tool_start
on_tool_end
```

### Modern typed Event Streaming

```text
astream_events(version="v3")
        ↓
stream.messages
stream.tool_calls
stream.values
stream.subgraphs
stream.output
stream.extensions
```

---

# 94. Final recommendation for your current stack

Given your stack:

```text
Python
FastAPI
Pydantic
uv
LangChain
LangGraph
Deep Agents
Langfuse
MCP
```

I'd make your architecture evolve toward:

```text
                         create_agent
                              |
                              v
                         LangGraph
                              |
                    Event Streaming
                              |
          ┌───────────────────┼──────────────────┐
          |                   |                  |
          v                   v                  v
       messages          tool_calls           values
          |                   |                  |
          └───────────────────┼──────────────────┘
                              v
                     Application Adapter
                              |
                              v
                        Pydantic events
                              |
                 ┌────────────┴────────────┐
                 v                         v
                SSE                    WebSocket
                 |                         |
                 └────────────┬────────────┘
                              v
                           Frontend
```

And separately:

```text
LangGraph/LangChain
       |
       +---- Langfuse
       |
       +---- logs
       |
       +---- metrics
       |
       +---- security/audit
```

That gives you a clean separation between:

```text
agent execution
      ≠
observability
      ≠
application streaming protocol
      ≠
frontend transport
```

That separation will pay off enormously when you add MCP servers, multiple agents, sub-agents, human-in-the-loop, enterprise integrations, and provider switching.

### Current-status summary

The important modern guidance from the current docs is:

**Learn `values`, `updates`, and `messages` deeply because they are still current and form the low-level LangGraph streaming model. Use v2 when you need the unified `StreamPart` format. For new application/frontend code, learn the newer Event Streaming API and its typed projections; `v3` is the current direction but is presently marked beta/experimental in the Python reference. Avoid v1 compatibility formats for new code.** ([Docs by LangChain][3])

The next natural topic after this module is **how streaming actually travels through a `create_agent` execution: model → tool call → tool execution → model → final state, including `AIMessageChunk`, `ToolCallChunk`, `ToolMessage`, metadata, namespaces, subgraphs, and how to build a production FastAPI SSE endpoint around it**.

[1]: https://docs.langchain.com/oss/python/langchain/streaming "Streaming - Docs by LangChain"
[2]: https://docs.langchain.com/oss/python/langgraph/event-streaming "Event streaming - Docs by LangChain"
[3]: https://docs.langchain.com/oss/python/langgraph/streaming "Streaming - Docs by LangChain"
[4]: https://reference.langchain.com/python/langchain-core/runnables/base/Runnable/astream_events?utm_source=chatgpt.com "astream_events | langchain_core | LangChain Reference"
[5]: https://reference.langchain.com/python/langchain-core/runnables/schema/BaseStreamEvent?utm_source=chatgpt.com "BaseStreamEvent | langchain_core | LangChain Reference"
[6]: https://docs.langchain.com/oss/python/langchain/event-streaming "Event streaming - Docs by LangChain"
[7]: https://reference.langchain.com/python/langchain-core/language_models/chat_models/BaseChatModel/stream_events?utm_source=chatgpt.com "stream_events | langchain_core | LangChain Reference"
[8]: https://reference.langchain.com/python/langgraph/pregel/main/Pregel/astream_events?utm_source=chatgpt.com "astream_events | langgraph | LangChain Reference"
[9]: https://docs.langchain.com/oss/python/integrations/chat/google_generative_ai "ChatGoogleGenerativeAI integration - Docs by LangChain"
