# Module 2 — Chat Models in LangChain

You are at exactly the right point to learn this now.

Since your eventual goal is **LangGraph + Deep Agents**, understanding LangChain's chat-model layer deeply is much more valuable than memorizing a few `ChatGoogleGenerativeAI(...)` examples. LangGraph nodes, agent loops, tool calls, structured output, streaming, retries, fallbacks, and model switching all sit on top of this abstraction.

I’ll therefore teach this in layers:

> **Provider API → LangChain chat model → messages → Runnable interface → tools/structured output → streaming → reliability → accounting → testing → LangGraph/Deep Agents**

I have also checked the current LangChain documentation and reference APIs rather than relying on older tutorials. As of the current 2026 documentation, `langchain-core` is in the 1.x line, `BaseChatModel` is the central abstraction, `init_chat_model` is the modern provider-agnostic factory, and `langchain-classic` versions of some APIs are explicitly deprecated. ([LangChain Reference Docs][1])

I’ll use **Gemini as the primary hosted-model example**, as you requested, and **Ollama** for your local/FOSS setup.

---

# 0. What you should understand before writing code

The most important mental model of this entire module is:

```text
Your application
      │
      ▼
LangChain model interface
      │
      │  invoke / ainvoke
      │  stream / astream
      │  batch / abatch
      ▼
Chat Model
      │
      ├── Gemini
      ├── OpenAI-compatible endpoint
      ├── Ollama
      ├── Groq
      ├── OpenRouter
      ├── Bedrock
      └── many others
           │
           ▼
      Provider API / local server
           │
           ▼
       Actual model
```

The important part is that **your application does not have to know the provider's native API**.

For example, your application can conceptually do:

```python
response = await model.ainvoke(messages)
```

and `model` could be:

```text
Gemini
Ollama
Groq
OpenRouter
vLLM
etc.
```

That abstraction is one of the reasons LangChain is useful.

---

# 1. First: what exactly is a Chat Model?

You probably already know the old mental model:

```text
prompt -> LLM -> text
```

That is incomplete for modern agent systems.

The modern mental model is:

```text
messages
   │
   ▼
Chat Model
   │
   ├── text
   ├── tool calls
   ├── structured data
   ├── metadata
   └── usage information
```

For example:

```text
System:
You are a helpful assistant.

Human:
What's the weather in Pune?

AI:
I need to call the weather tool.

Tool call:
get_weather(location="Pune")

Tool:
32°C, sunny

AI:
It is currently 32°C and sunny.
```

That is why LangChain uses **messages**, rather than treating everything as one giant string.

---

# 2. The standard `BaseChatModel` interface

The central abstraction is:

```python
BaseChatModel
```

from:

```python
from langchain_core.language_models import BaseChatModel
```

Current LangChain's `BaseChatModel` defines the standard imperative operations around chat models, including `invoke`, `ainvoke`, `stream`, and `astream`. ([LangChain Reference Docs][1])

The simplest mental model is:

```text
invoke()
    one complete answer

stream()
    answer piece-by-piece

ainvoke()
    asynchronous complete answer

astream()
    asynchronous streaming answer
```

And then:

```text
batch()
    many requests

abatch()
    many asynchronous requests
```

---

# 3. `invoke()` — the simplest operation

Example with Gemini:

```python
from langchain_google_genai import ChatGoogleGenerativeAI

model = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0,
)

response = model.invoke("Explain RAG in simple terms.")

print(response)
```

The important thing is:

> `response` is not merely a string.

It is an `AIMessage`.

Conceptually:

```python
AIMessage(
    content="RAG means...",
    ...
)
```

This distinction becomes extremely important later.

You can do:

```python
print(response.content)
```

but you should also learn to inspect:

```python
response.tool_calls
response.usage_metadata
response.response_metadata
response.content_blocks
```

The current `AIMessage` API standardizes things such as `tool_calls` and `usage_metadata`. ([LangChain Reference Docs][2])

---

# 4. Why not just return a string?

Imagine an agent receives:

```text
What's the weather?
```

Suppose the model answers:

```text
I'll check the weather.
```

That's text.

But an agent-capable model might instead return something conceptually like:

```python
AIMessage(
    content="",
    tool_calls=[
        {
            "name": "get_weather",
            "args": {"location": "Pune"},
            "id": "call_123",
        }
    ]
)
```

That is not ordinary text.

It's an instruction from the model:

> "Please execute this tool."

So the standardized `AIMessage` abstraction allows LangChain to represent both:

```text
normal answer
```

and:

```text
tool invocation
```

without making the application provider-specific.

---

# 5. Messages — one of the most important concepts

LangChain's standard message classes include:

```python
SystemMessage
HumanMessage
AIMessage
ToolMessage
```

These are all forms of `BaseMessage`. ([LangChain Reference Docs][3])

Think of a conversation as a list:

```python
messages = [
    SystemMessage(content="You are a helpful assistant."),
    HumanMessage(content="What is RAG?"),
    AIMessage(content="RAG means Retrieval Augmented Generation."),
    HumanMessage(content="Why is it useful?"),
]
```

Then:

```python
response = model.invoke(messages)
```

---

# 6. `SystemMessage`

The system message describes the model's high-level behavior.

Example:

```python
from langchain_core.messages import SystemMessage

SystemMessage(
    content="You are a senior Python teacher. Explain concepts simply."
)
```

Conceptually:

```text
SYSTEM
    ↓
"You are a senior Python teacher."

HUMAN
    ↓
"What is async?"

AI
    ↓
"async allows..."
```

Don't confuse system messages with application authorization or security boundaries.

A system message is still model input.

It is not a cryptographic security mechanism.

That distinction becomes particularly important once we get to agents and tool security.

---

# 7. `HumanMessage`

This represents user input:

```python
from langchain_core.messages import HumanMessage

HumanMessage(
    content="Explain LangGraph."
)
```

---

# 8. `AIMessage`

This represents model output.

Example:

```python
from langchain_core.messages import AIMessage

AIMessage(
    content="LangGraph is a framework..."
)
```

But the modern `AIMessage` may contain much more than text:

```python
response.content
response.tool_calls
response.invalid_tool_calls
response.usage_metadata
response.response_metadata
response.content_blocks
```

The important idea:

> **AIMessage is the model's structured result, not merely its prose.**

The current API explicitly provides standardized usage metadata and tool-call fields. ([LangChain Reference Docs][4])

---

# 9. `ToolMessage`

This one is extremely important for LangGraph.

Suppose the AI says:

```text
Call:
get_weather("Pune")
```

Your application executes:

```python
result = "32°C, sunny"
```

That result is sent back to the model as a `ToolMessage`.

Conceptually:

```python
ToolMessage(
    content="32°C, sunny",
    tool_call_id="call_123",
)
```

The `tool_call_id` associates the tool result with the specific tool request. ([LangChain Reference Docs][5])

So the full conversation can become:

```text
SystemMessage
        ↓
HumanMessage
        ↓
AIMessage(tool_call)
        ↓
ToolMessage(tool_result)
        ↓
AIMessage(final answer)
```

That sequence is the foundation of modern tool-using agents.

And this is exactly why understanding chat models before learning LangGraph deeply is worthwhile.

---

# 10. Tuple shorthand

LangChain also lets you express messages more compactly:

```python
messages = [
    ("system", "You are a helpful assistant."),
    ("human", "Explain RAG."),
]
```

This is convenient.

But while learning, I recommend understanding the actual classes:

```python
SystemMessage(...)
HumanMessage(...)
AIMessage(...)
ToolMessage(...)
```

because later you will inspect and manipulate message objects directly.

---

# 11. Async: `ainvoke()`

For your eventual FastAPI application, this is particularly important.

Instead of:

```python
response = model.invoke(messages)
```

you can do:

```python
response = await model.ainvoke(messages)
```

Example:

```python
async def answer(question: str):
    response = await model.ainvoke(
        [
            ("system", "You are a helpful assistant."),
            ("human", question),
        ]
    )

    return response
```

---

# 12. Why async matters for AI applications

Imagine your FastAPI server has 100 requests:

```text
Request 1 → waiting for Gemini
Request 2 → waiting for Gemini
Request 3 → waiting for Gemini
...
```

If your architecture is synchronous everywhere, you can waste worker time waiting on network I/O.

With async:

```text
Request 1 ── awaiting Gemini
Request 2 ── awaiting Gemini
Request 3 ── processing
Request 4 ── awaiting tool
Request 5 ── awaiting DB
```

The event loop can continue servicing other work.

That makes the `ainvoke()` / `astream()` interface especially useful in FastAPI and LangGraph systems.

---

# 13. `stream()` vs `invoke()`

`invoke()`:

```python
response = model.invoke("Tell me a story")
```

You get the completed message.

With streaming:

```python
for chunk in model.stream("Tell me a story"):
    print(chunk.content, end="", flush=True)
```

Instead of waiting:

```text
................................................
[full answer appears]
```

you get:

```text
Once
Upon
a
time
...
```

Conceptually:

```text
model
 │
 ├── chunk 1
 ├── chunk 2
 ├── chunk 3
 ├── chunk 4
 └── final chunk
```

The chunks are generally `AIMessageChunk` objects rather than final `AIMessage` objects. ([LangChain Reference Docs][1])

---

# 14. `astream()`

Async version:

```python
async for chunk in model.astream("Explain LangGraph"):
    print(chunk.content, end="", flush=True)
```

For a FastAPI streaming endpoint, this pattern becomes very useful.

---

# 15. `batch()` and `abatch()`

Suppose you need to ask a model to summarize 100 documents.

Instead of:

```python
for document in documents:
    model.invoke(document)
```

LangChain provides:

```python
results = model.batch(documents)
```

and:

```python
results = await model.abatch(documents)
```

The exact throughput behavior still depends on the provider and integration. `batch()` is an abstraction, not a magical guarantee that your provider will suddenly execute 100 requests optimally.

That distinction matters.

---

# 16. The Runnable mental model

This is one of the most important things to understand before LangGraph.

LangChain models are also **Runnables**.

A Runnable provides a common behavioral interface:

```text
invoke
ainvoke
stream
astream
batch
abatch
```

But it also allows you to construct wrappers.

For example:

```python
model
    .with_retry(...)
```

or:

```python
model
    .with_fallbacks(...)
```

or:

```python
model
    .bind(...)
```

This is what people mean by LangChain's **chainable configuration/declarative pattern**.

Current LangChain's `Runnable` abstraction explicitly supports methods such as `bind`, `with_config`, `with_retry`, and `with_fallbacks`. ([LangChain Reference Docs][6])

---

# 17. `.bind()` — adding execution parameters

Conceptually:

```python
model_with_params = model.bind(
    temperature=0,
)
```

You haven't modified `model`.

You've created another Runnable around it.

This is similar to:

```text
original model
       │
       ▼
   binding
       │
       ▼
configured model
```

This is why these APIs are composable.

---

# 18. `.bind_tools()` — the gateway to agents

This is one of the biggest concepts in the entire module.

Suppose you define:

```python
from langchain.tools import tool


@tool
def get_weather(location: str) -> str:
    """Get weather for a location."""
    return f"The weather in {location} is sunny."
```

Then:

```python
model_with_tools = model.bind_tools([get_weather])
```

Now you haven't actually executed `get_weather`.

You've told the model:

> "This tool exists, and you are allowed to request it."

Very important distinction:

```text
bind_tools()
      ≠
execute tool
```

Instead:

```text
bind_tools()
      ↓
model knows about tool
      ↓
model may produce a tool call
      ↓
your agent/runtime executes tool
      ↓
ToolMessage returned
      ↓
model continues
```

This distinction is absolutely fundamental to understanding LangGraph agents.

---

# 19. What actually happens internally?

Suppose user says:

```text
What's the weather in Pune?
```

Your model has:

```python
model_with_tools
```

The model might return:

```python
AIMessage(
    content=[],
    tool_calls=[
        {
            "name": "get_weather",
            "args": {
                "location": "Pune"
            },
            "id": "call_123"
        }
    ]
)
```

Then LangGraph/agent runtime sees:

```python
if response.tool_calls:
    ...
```

and executes the tools.

That's the conceptual bridge:

```text
Chat Model
     ↓
AIMessage
     ↓
tool_calls
     ↓
LangGraph tool node
     ↓
ToolMessage
     ↓
Chat Model
```

---

# 20. Why models differ so much with tool calling

Tool calling is not simply:

```text
"all LLMs can do tools"
```

Different models differ substantially in:

* tool-call syntax
* parallel tool calling
* argument generation
* schema adherence
* structured output
* streaming tool calls
* malformed arguments
* reasoning/tool interaction

This is why a model can be excellent at normal chat and frustrating as an agent.

Current LangChain's model capability information explicitly tracks capabilities such as tool calling and structured output, and Deep Agents uses capability information when validating models. ([Docs by LangChain][7])

---

# 21. `.with_structured_output()`

Suppose you want:

```text
user:
Extract the person's name and age.
```

Instead of:

```text
"John is 34 years old."
```

you want:

```python
Person(
    name="John",
    age=34,
)
```

Define:

```python
from pydantic import BaseModel


class Person(BaseModel):
    name: str
    age: int
```

Then:

```python
structured_model = model.with_structured_output(Person)
```

and:

```python
result = structured_model.invoke(
    "My name is John and I am 34 years old."
)

print(result)
```

The current LangChain model APIs support structured output using schemas such as Pydantic models, TypedDict, and JSON schema. ([Docs by LangChain][7])

---

# 22. Why structured output is so important

Imagine your backend receives:

```text
Customer wants to cancel order #932.
```

Without structured output:

```text
Probably order 932 cancellation.
```

Your application has to parse natural language.

With structured output:

```python
class CustomerRequest(BaseModel):
    intent: str
    order_id: int
    urgency: str
```

You can get:

```python
CustomerRequest(
    intent="cancel_order",
    order_id=932,
    urgency="normal",
)
```

Now Python can operate on the data reliably.

This is particularly useful in:

* LangGraph routing
* agent planning
* classification
* information extraction
* API orchestration
* /database operations
* validation

---

# 23. Structured output is not the same thing as "JSON mode"

These are different concepts.

### JSON mode

You essentially tell the model:

```text
return JSON
```

You may get:

```json
{
  "name": "John",
  "age": 34
}
```

But you still need to validate it.

### Structured output

You specify a schema:

```python
class Person(BaseModel):
    name: str
    age: int
```

Then LangChain/provider can enforce and/or validate that structure.

Modern LangChain's structured-output abstractions distinguish native provider strategies from tool-based strategies. ([Docs by LangChain][8])

---

# 24. Native structured output vs tool-based structured output

This is an advanced but important concept.

There are basically two broad strategies.

### Strategy A — provider-native

The model provider has an actual structured-output capability.

```text
LangChain
   ↓
provider structured-output feature
   ↓
validated response
```

### Strategy B — tool calling

LangChain represents your requested schema as a tool-like function.

```text
schema
  ↓
tool definition
  ↓
model generates tool call
  ↓
LangChain extracts arguments
  ↓
structured object
```

The best strategy depends on the provider/model.

LangChain's current agent API can choose between provider-native and tool-based strategies based on the model's capabilities. ([Docs by LangChain][8])

---

# 25. `.with_retry()`

Suppose Gemini temporarily returns:

```text
429 Too Many Requests
```

or:

```text
503 Service Unavailable
```

Instead of manually writing:

```python
try:
    ...
except:
    ...
```

you can create:

```python
reliable_model = model.with_retry(
    stop_after_attempt=3,
)
```

Current LangChain's `Runnable.with_retry()` supports configurable exception types, exponential jitter, and attempt limits. ([LangChain Reference Docs][9])

---

# 26. Why retry is not just "try again"

This is important.

Suppose:

```text
request
   ↓
429
   ↓
retry immediately
   ↓
429
   ↓
retry immediately
   ↓
429
```

You may make the provider's overload worse.

That's why good retry systems use:

```text
exponential backoff
+
jitter
```

For example:

```text
attempt 1
wait ~1 sec

attempt 2
wait ~2 sec

attempt 3
wait ~4 sec
```

with randomized jitter.

LangChain's current retry implementation supports exponential jitter. ([LangChain Reference Docs][9])

---

# 27. Do not retry everything

This is a common production mistake.

Good retry candidates:

```text
429
502
203
504
network timeout
temporary connection failure
```

Bad retry candidates:

```text
401 unauthorized
403 forbidden
invalid API key
400 malformed request
invalid schema caused by your code
```

Retrying a bad API key three times accomplishes nothing.

LangChain's model documentation also describes automatic retries for network errors, rate limits and server-side 5xx errors while client errors such as 401/404 are not automatically retried. ([Docs by LangChain][7])

---

# 28. `.with_fallbacks()`

Suppose your architecture is:

```text
Primary:
Gemini

Fallback:
local Ollama
```

You can conceptually build:

```python
reliable_model = gemini.with_fallbacks(
    [ollama]
)
```

If Gemini fails with an exception that your fallback policy handles:

```text
Gemini
   ↓
failure
   ↓
Ollama
   ↓
response
```

Current `RunnableWithFallbacks` tries the original Runnable and then fallbacks in order. You can also specify which exception types should trigger fallback. ([LangChain Reference Docs][10])

---

# 29. Retry + fallback together

Production systems commonly do:

```text
Gemini
   │
   ├─ transient error
   │      ↓
   │   retry
   │      ↓
   │   retry
   │      ↓
   │   retry
   │
   └─ still unavailable
          ↓
       fallback
          ↓
       Ollama
```

The key design principle is:

> **Retry the same provider for transient failures; fallback when staying with that provider is no longer useful.**

---

# 30. A subtle problem with fallbacks

Suppose the primary model produces:

```text
a perfectly valid answer
```

but it takes:

```text
25 seconds
```

Should you fallback?

Maybe.

But `with_fallbacks()` is fundamentally exception-driven.

It does not magically understand:

```text
"this response is too slow for my business SLA."
```

For latency-driven fallback you often need an explicit timeout policy.

---

# 31. Timeouts

At model level:

```python
model = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    timeout=30,
)
```

The exact timeout parameter depends on the integration.

For application-level async deadlines, modern Python also has:

```python
async with asyncio.timeout(30):
    result = await model.ainvoke(...)
```

Python's current asyncio documentation recommends `asyncio.timeout()` for new code over older `wait_for()` patterns. ([Python documentation][11])

---

# 32. Retry, timeout and fallback are different

Do not merge these concepts mentally.

```text
TIMEOUT
    How long am I willing to wait?

RETRY
    Should I try the same operation again?

FALLBACK
    Should I use another implementation/provider?

CIRCUIT BREAKER
    Should I stop calling this failing provider temporarily?
```

These solve different problems.

---

# 33. Circuit breaker

Imagine Gemini is down.

Without a circuit breaker:

```text
request 1 → Gemini → fail
request 2 → Gemini → fail
request 3 → Gemini → fail
...
request 10000 → Gemini → fail
```

A circuit breaker changes this to:

```text
healthy
   ↓
failures increase
   ↓
OPEN
   ↓
stop calling Gemini
   ↓
fallback / fail fast
   ↓
wait
   ↓
HALF OPEN
   ↓
test Gemini
   ↓
healthy? → CLOSED
```

A Python library such as `aiobreaker` implements the circuit-breaker pattern and supports asyncio usage. ([GitHub][12])

For your architecture, however, I would first learn:

```text
LangChain retry/fallback
```

then:

```text
LiteLLM routing/fallback
```

and only then decide whether your application needs its own circuit breaker.

---

# 34. Provider-agnostic model creation

Now we reach:

```python
init_chat_model()
```

This is one of the APIs I strongly recommend learning.

Current LangChain exposes:

```python
from langchain.chat_models import init_chat_model
```

and supports provider-qualified model specifications. ([LangChain Reference Docs][13])

For example:

```python
model = init_chat_model(
    "google_genai:gemini-2.5-flash"
)
```

The exact provider/model identifiers should be checked against the installed integration because provider support evolves.

---

# 35. Why `init_chat_model()` is useful

Suppose your application contains:

```python
def generate_answer(model, question):
    return model.invoke(question)
```

Now your configuration can say:

```text
production:
    google Gemini

development:
    Ollama

testing:
    fake model
```

Your application code doesn't need to become:

```python
if provider == "gemini":
    ...

elif provider == "ollama":
    ...

elif provider == "openai":
    ...
```

Instead:

```text
configuration
    ↓
model factory
    ↓
BaseChatModel
    ↓
application
```

This is excellent architecture for your AI SaaS.

---

# 36. Important deprecated/current distinction

There are several older tutorials you will encounter.

Older patterns may show:

```python
from langchain_classic.chat_models import init_chat_model
```

or older package structures.

Current documentation explicitly marks the `langchain-classic` `init_chat_model` as deprecated and says to use:

```python
from langchain.chat_models import init_chat_model
```

instead. `langchain-classic` is maintained for compatibility, not where new features should be expected to land. ([reference.langchain.com][14])

So when following a YouTube tutorial and you see `langchain_classic`, stop and verify the current equivalent.

---

# 37. Partner packages

Modern LangChain deliberately splits provider integrations into packages.

For Gemini:

```text
langchain-google-genai
```

For Ollama:

```text
langchain-ollama
```

For OpenAI:

```text
langchain-openai
```

etc.

The purpose is that the core abstraction remains relatively provider-independent.

Current Gemini integration documentation uses `langchain-google-genai` and the consolidated Google `google-genai` SDK. The docs specifically note that this supersedes older Vertex-specific integration paths for this use case. ([Docs by LangChain][15])

---

# 38. Gemini: recommended starting model for your learning

For examples I'm going to use:

```python
from langchain_google_genai import ChatGoogleGenerativeAI

model = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0,
)
```

The current integration supports:

* tool calling
* structured output
* image input
* audio input
* video input
* token-level streaming
* native async
* token usage

according to the current integration documentation. ([Docs by LangChain][15])

Gemini 2.5 uses `thinking_budget`; newer Gemini model families use their current thinking controls, so do not copy one model's thinking parameter blindly to another. ([Docs by LangChain][15])

---

# 39. Gemini credentials

Current documentation recognizes:

```text
GOOGLE_API_KEY
```

and:

```text
GEMINI_API_KEY
```

with `GOOGLE_API_KEY` taking priority in the documented integration behavior. ([Docs by LangChain][15])

For your application I'd keep credentials outside source code:

```env
GOOGLE_API_KEY=...
```

and load them through your existing Pydantic settings system.

---

# 40. OpenAI-compatible APIs

You asked specifically about:

```text
Groq
OpenRouter
vLLM
LM Studio
```

This is where you need an important architectural distinction.

Many providers expose an OpenAI-compatible HTTP interface.

That means:

```text
your code
   ↓
OpenAI-compatible client
   ↓
third-party endpoint
```

For basic compatibility, `ChatOpenAI` can point at a custom `base_url`.

However, current LangChain documentation explicitly warns that `ChatOpenAI` targets the official OpenAI API specification and does not necessarily preserve provider-specific extensions such as custom reasoning fields. For extended features, provider-specific integrations are preferable. ([Docs by LangChain][16])

So:

```text
"compatible with OpenAI"
```

does **not** mean:

```text
"identical to OpenAI"
```

This distinction will save you a lot of debugging.

---

# 41. Example: local vLLM

Conceptually:

```python
from langchain_openai import ChatOpenAI

model = ChatOpenAI(
    model="my-model",
    base_url="http://localhost:8000/v1",
    api_key="dummy",
)
```

The specific endpoint must expose a compatible API.

The interesting architecture is:

```text
LangChain
   ↓
ChatOpenAI
   ↓
OpenAI-compatible HTTP API
   ↓
vLLM
   ↓
your local GPU
```

---

# 42. Ollama

Ollama is especially relevant to your FOSS preference.

The modern LangChain integration is:

```python
from langchain_ollama import ChatOllama
```

not an old `langchain_community` path.

The current integration package is:

```bash
uv add langchain-ollama
```

and LangChain's current docs list `ChatOllama` as supporting tool calling, structured output, streaming, async and token usage. ([Docs by LangChain][17])

---

# 43. Ollama architecture

Think of Ollama as a local model server:

```text
Your Python application
        │
        │ HTTP
        ▼
     Ollama
        │
        ▼
    model weights
        │
        ▼
CPU / GPU / RAM / VRAM
```

Your Python application isn't loading the model itself.

Ollama is doing that.

---

# 44. Ollama in Docker

For your infrastructure style, a simplified Compose architecture is:

```yaml
services:
  ollama:
    image: ollama/ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    restart: unless-stopped

volumes:
  ollama_data:
```

You would normally add GPU-specific configuration when using an NVIDIA GPU.

The important architectural concept is persistent model storage:

```text
Docker container
       │
       ▼
persistent volume
       │
       ▼
downloaded models survive container recreation
```

Never assume the model weights should disappear when the container does.

---

# 45. Ollama model lifecycle

Typical workflow:

```bash
ollama pull <model>
```

Then:

```bash
ollama list
```

Then:

```bash
ollama run <model>
```

The LangChain integration's current documentation follows this model-management approach. ([Docs by LangChain][18])

---

# 46. What is quantization?

This is essential for local models.

Suppose a model has billions of parameters.

Full precision might store parameters with something like:

```text
FP16
16 bits / parameter
```

Quantization attempts to reduce the number of bits needed.

For example:

```text
FP16
↓
INT8
↓
Q6
↓
Q5
↓
Q4
```

This reduces memory consumption.

But the trade-off is generally:

```text
less memory
      ↕
potentially lower quality / altered behavior
```

---

# 47. What does `Q4_K_M` mean?

A tag such as:

```text
Q4_K_M
```

is a quantization format used in the GGUF ecosystem.

A beginner-level approximation:

```text
Q4
```

means roughly four-bit quantization.

But do **not** calculate model RAM simply as:

```text
parameters × 4 bits
```

and assume that's your real runtime requirement.

Why?

Because actual memory usage also includes:

```text
quantized weights
+
runtime overhead
+
KV cache
+
context
+
temporary buffers
+
GPU/CPU execution memory
```

---

# 48. A much better RAM mental model

Think:

```text
Total RAM/VRAM requirement
≈
weights
+
KV cache
+
runtime overhead
+
context-dependent memory
```

The model weight is only one part.

As context size increases:

```text
context ↑
    ↓
KV cache ↑
    ↓
memory ↑
```

And when an agent uses tools:

```text
long conversation
+
tool outputs
+
system prompt
+
schemas
+
previous AI messages
```

you can suddenly have a large context.

This is directly relevant to Deep Agents.

---

# 49. `keep_alive`

Ollama supports:

```text
keep_alive
```

which determines how long the model stays loaded in memory after a request.

Current Ollama documentation shows a default of roughly five minutes and supports values such as `5m` or `0`; the server also exposes `OLLAMA_KEEP_ALIVE`. ([Ollama][19])

Conceptually:

```text
without long keep_alive

request
 ↓
load model
 ↓
generate
 ↓
unload

next request
 ↓
load model again
```

That can be expensive.

With a longer keep-alive:

```text
request
 ↓
load model
 ↓
generate
 ↓
KEEP IN MEMORY
 ↓
next request is faster
```

But you pay memory.

---

# 50. Preloading

For a production-ish local service:

```text
container starts
      ↓
healthcheck
      ↓
Ollama ready
      ↓
model pulled
      ↓
model loaded
      ↓
application starts accepting traffic
```

This avoids the first real user request paying the cold-start cost.

---

# 51. Ollama healthcheck

A Docker Compose healthcheck can ensure the service is alive before dependent services use it.

At a conceptual level:

```yaml
healthcheck:
  test:
    - CMD
    - curl
    - -f
    - http://localhost:11434/api/version
  interval: 10s
  timeout: 5s
  retries: 5
```

The exact image may not include `curl`, so choose the healthcheck command according to the actual image contents.

The key lesson:

> Healthcheck the service, don't assume container "running" means application "ready."

---

# 52. Ollama embeddings

You specifically mentioned:

```text
nomic-embed-text
bge-m3
```

These are not chat models.

They turn text into vectors.

Conceptually:

```text
"LangGraph is a framework..."
             ↓
        embedding model
             ↓
[0.021, -0.113, 0.883, ...]
```

Those vectors go into:

```text
Qdrant
pgvector
FAISS
Milvus
etc.
```

Current Ollama documents provide a dedicated `/api/embed` endpoint for embeddings. ([Ollama][20])

---

# 53. `nomic-embed-text`

Ollama's model library lists `nomic-embed-text` as an embedding-only model. ([Ollama][21])

You should therefore conceptually separate:

```text
Chat model
    ChatOllama

Embedding model
    OllamaEmbeddings
```

For example:

```python
from langchain_ollama import OllamaEmbeddings

embeddings = OllamaEmbeddings(
    model="nomic-embed-text"
)
```

---

# 54. `bge-m3`

`bge-m3` is especially interesting for multilingual/RAG work.

Ollama currently lists it as:

```text
~567M parameters
~1.2 GB model size
8K context
```

and describes it as multilingual with dense, multi-vector and sparse retrieval capabilities. ([Ollama][22])

That makes it an interesting model to experiment with for your future:

```text
Qdrant
+
hybrid retrieval
+
RRF
```

architecture.

---

# 55. But don't blindly use the same embedding model forever

Embedding model changes are not trivial.

Suppose your existing Qdrant collection was built with:

```text
embedding_model_A
```

and you switch to:

```text
embedding_model_B
```

The vectors may have different dimensionality and semantic space.

You generally need to re-embed your corpus.

So treat the embedding model as part of your data schema.

For example:

```text
collection:
documents_v1

embedding_model:
bge-m3

embedding_dimensions:
1024
```

Record this metadata.

---

# 56. LiteLLM

Now the optional-but-recommended layer.

I think LiteLLM is highly relevant to your eventual AI SaaS architecture.

It acts as a model gateway:

```text
                 ┌── Gemini
                 │
Your application ├── Ollama
                 │
                 ├── OpenRouter
                 │
                 └── other providers
                       ▲
                       │
                    LiteLLM
                       ▲
                       │
                  single API
```

Instead of your application having provider-specific credentials everywhere:

```text
FastAPI
  ↓
LiteLLM
  ↓
providers
```

---

# 57. Why a gateway is useful

Without gateway:

```text
FastAPI
 ├── Gemini credentials
 ├── Groq credentials
 ├── OpenRouter credentials
 ├── Anthropic credentials
 └── Ollama connection
```

With gateway:

```text
FastAPI
    ↓
LiteLLM
    ↓
provider credentials
```

That centralizes:

* model routing
* budgets
* keys
* provider fallback
* spend
* observability
* rate limiting

depending on your configuration.

---

# 58. LiteLLM virtual keys

Current LiteLLM proxy documentation supports virtual keys with:

```text
model access
rate limits
budgets
spend tracking
```

and requires a database for key/budget functionality. ([GitHub][23])

This is extremely useful for your SaaS.

Imagine:

```text
AI SaaS tenant A
    ↓
virtual key A
    ↓
LiteLLM
    ↓
Gemini
```

and:

```text
AI SaaS tenant B
    ↓
virtual key B
    ↓
LiteLLM
    ↓
Ollama
```

You can control them independently.

---

# 59. Important LiteLLM production detail

Do not run a budget-sensitive LiteLLM installation without understanding its database requirements.

Current LiteLLM documentation explicitly warns that budgets are not enforced correctly on a DB-less deployment; virtual keys also require a database. ([GitHub][23])

For your architecture:

```text
LiteLLM
+
PostgreSQL
```

is a much more appropriate production learning architecture.

---

# 60. Spend tracking

LiteLLM can track spend by things such as:

```text
key
user
team
model
provider
```

Current documentation describes automatic spend tracking and model-based cost calculation. ([GitHub][24])

It also exposes Prometheus metrics for spend and token information. ([GitHub][25])

That fits nicely into your future:

```text
FastAPI
↓
LangGraph
↓
LiteLLM
↓
models
↓
Prometheus/Grafana
```

---

# 61. Streaming in depth

Now let's go much deeper.

Suppose the model response is:

```text
Hello, how are you today?
```

The stream may conceptually produce:

```text
"H"
"ello"
", "
"how"
" are"
" you"
" today"
"? "
```

The exact chunk boundaries are provider-dependent.

Therefore:

> Never write application logic assuming one chunk equals one word or one token.

---

# 62. What is an `AIMessageChunk`?

A chunk represents a piece of the eventual message.

You can think of:

```python
chunk_1
+
chunk_2
+
chunk_3
+
...
```

eventually becoming:

```python
AIMessage
```

LangChain's message system explicitly includes `AIMessageChunk`, which is the streaming counterpart to `AIMessage`. ([LangChain Reference Docs][26])

---

# 63. Accumulating chunks

You can conceptually do:

```python
full_message = None

for chunk in model.stream("Explain RAG"):
    if full_message is None:
        full_message = chunk
    else:
        full_message = full_message + chunk
```

LangChain's message chunks are designed to be combinable.

The important idea is:

```text
chunk
+
chunk
+
chunk
=
complete message
```

---

# 64. The classic tool-call streaming gotcha

This is one of the most important advanced topics.

Suppose the final tool call should be:

```json
{
  "name": "get_weather",
  "args": {
    "location": "Pune"
  }
}
```

Streaming might produce pieces like:

```text
chunk 1:
name = "get_weather"

chunk 2:
args = "{"

chunk 3:
args = "{\"location\""

chunk 4:
args = "{\"location\":\"Pune\"}"
```

You **cannot** assume every tool-call chunk contains a complete JSON object.

You must accumulate the chunks.

---

# 65. Why tool call streaming is harder than text streaming

Text can be rendered immediately:

```text
H
He
Hel
Hell
Hello
```

Tool arguments can't necessarily be executed immediately.

Imagine receiving:

```text
{"location":
```

That isn't complete JSON.

So the runtime has to assemble the complete tool invocation before execution.

Current LangChain's event-streaming documentation explicitly describes tool-call argument chunks being streamed while the model generates the call. ([Docs by LangChain][27])

---

# 66. Conceptual tool-call accumulation

Think:

```python
tool_args_buffer = ""
```

Then:

```text
chunk 1 → "{"
chunk 2 → '{"loc'
chunk 3 → '{"location"'
chunk 4 → '{"location":"Pune"'
chunk 5 → '{"location":"Pune"}'
```

Only after complete accumulation do you have a safe candidate for parsing.

Modern LangChain integrations do this conversion for you when possible, so your normal agent code should generally consume the standardized tool-call representation rather than reimplementing provider-specific parsers.

That is exactly the sort of edge-case handling you said you prefer libraries to handle.

---

# 67. Streaming usage metadata

Token usage during streaming has historically been inconsistent between providers.

Modern integrations can expose usage information, but you should always verify the provider's support.

The current chat-model integration matrix explicitly indicates whether token usage is supported for a provider/model integration. ([Docs by LangChain][15])

The end result you're looking for is something such as:

```python
AIMessage(
    ...
    usage_metadata={
        "input_tokens": ...,
        "output_tokens": ...,
        "total_tokens": ...,
    }
)
```

The current `UsageMetadata` abstraction standardizes token counts across providers where available. ([LangChain Reference Docs][28])

---

# 68. Why `usage_metadata` matters

Suppose your AI SaaS receives:

```text
100,000 requests
```

You need to answer:

```text
Which customer consumed the most tokens?

Which model costs the most?

Which workflow is expensive?

How much did yesterday's RAG pipeline cost?
```

You can't answer those reliably from:

```python
response.content
```

You need:

```python
response.usage_metadata
```

---

# 69. Your usage ledger

I recommend thinking of each model invocation as producing a usage event.

Conceptually:

```python
UsageEvent(
    request_id="abc",
    tenant_id="customer_123",
    model="gemini-2.5-flash",
    provider="google",
    input_tokens=1200,
    output_tokens=450,
    total_tokens=1650,
    timestamp=...,
)
```

Then store that in your database.

This becomes:

```text
LLM call
   ↓
AIMessage
   ↓
usage_metadata
   ↓
usage event
   ↓
PostgreSQL
   ↓
billing/analytics
```

---

# 70. Cost calculation

Do not confuse:

```text
tokens
```

with:

```text
money
```

You need a pricing table.

Conceptually:

```python
cost = (
    input_tokens * input_price_per_token
    +
    output_tokens * output_price_per_token
)
```

For example:

```python
input_cost = 1200 * 0.000001
output_cost = 450 * 0.000004

total_cost = input_cost + output_cost
```

But do not hard-code today's provider prices into your codebase without versioning.

Pricing changes.

Instead maintain:

```text
model
provider
effective_date
input_price
output_price
cached_input_price
...
```

---

# 71. Why cached tokens matter

Some providers charge differently for:

```text
input tokens
cached input tokens
output tokens
reasoning tokens
```

Therefore a production usage ledger should not assume:

```text
input + output
```

is always the whole story.

LangChain's `UsageMetadata` can include more detailed input/output token information depending on the provider. ([LangChain Reference Docs][26])

---

# 72. Feeding this into Langfuse

Since you already plan to use Langfuse later, your architecture can eventually be:

```text
Chat model
    ↓
AIMessage
    ↓
usage_metadata
    │
    ├── internal usage ledger
    │
    └── Langfuse trace/span
```

The important principle is:

> Don't make Langfuse your only source of business billing truth.

Keep an application-owned usage ledger.

Observability systems can change.

Your billing data shouldn't depend entirely on one observability provider.

---

# 73. Testing LLM applications

This is where many beginners make a major mistake.

They write:

```python
def test_agent():
    real_gemini_call()
```

That is usually a terrible unit test.

Why?

Because the model:

```text
can change
can be unavailable
costs money
has nondeterminism
can return different wording
can hit rate limits
```

Instead:

```text
unit test
    ↓
fake model
```

And:

```text
integration test
    ↓
real model
```

Keep these separate.

---

# 74. Current fake chat models

Current `langchain-core` provides fake chat-model implementations specifically for testing.

The current reference includes:

```text
FakeListChatModel
FakeMessagesListChatModel
GenericFakeChatModel
```

and other testing helpers. ([LangChain Reference Docs][29])

---

# 75. `GenericFakeChatModel`

The idea is:

```text
your code
   ↓
fake chat model
   ↓
predefined responses
```

So your test becomes deterministic.

Example conceptual usage:

```python
fake_model = GenericFakeChatModel(...)
```

Then your graph can be tested without calling Gemini.

---

# 76. `FakeMessagesListChatModel`

This is useful when you want to simulate a sequence.

Imagine your agent should behave like:

```text
call 1 → AI requests weather tool
call 2 → AI gives final answer
```

You can construct fake messages corresponding to that sequence.

Then:

```text
test
 ↓
fake AIMessage(tool_call)
 ↓
fake tool result
 ↓
fake AIMessage(final answer)
```

That allows you to test your LangGraph control flow.

---

# 77. Fake tool calls

This is particularly important for your future LangGraph tests.

Suppose a graph contains:

```text
START
  ↓
agent
  ↓
tools?
 ├── yes → tool
 │          ↓
 │        agent
 │
 └── no → END
```

You don't need Gemini to test whether the graph routes correctly.

Make the fake model produce:

```python
AIMessage(
    content="",
    tool_calls=[
        {
            "name": "get_weather",
            "args": {"location": "Pune"},
            "id": "test-call-1",
        }
    ],
)
```

Then assert:

```text
tool executed
```

and:

```text
final model called
```

This is deterministic graph testing.

---

# 78. Why this is enormously important for LangGraph

Consider a LangGraph workflow:

```text
START
 ↓
classify
 ↓
route
 ├── billing
 ├── support
 └── technical
```

Your unit tests shouldn't ask Gemini:

```text
"Please classify this."
```

and hope it chooses:

```text
technical
```

Instead:

```text
FakeChatModel
      ↓
"technical"
```

Then test the graph.

This allows you to verify **your graph logic**, not the intelligence of the LLM.

---

# 79. `SimpleChatModel`: old vs modern

The current LangChain reference explicitly says that `SimpleChatModel` is primarily retained for backwards compatibility and recommends implementing `BaseChatModel` directly for new implementations. ([LangChain Reference Docs][29])

So if an older tutorial teaches:

```python
class MyModel(SimpleChatModel):
```

do not automatically copy it.

Modern custom chat model implementations should understand `BaseChatModel`.

---

# 80. Modern vs old API cheat sheet

| Older pattern you may encounter                    | Current direction                                |
| -------------------------------------------------- | ------------------------------------------------ |
| `langchain-classic` APIs                           | Prefer `langchain` 1.x APIs                      |
| old provider integrations in `langchain-community` | Prefer dedicated provider packages               |
| legacy Gemini SDK patterns                         | `langchain-google-genai` / Google `google-genai` |
| `Ollama` community integration                     | `langchain-ollama`                               |
| `OllamaLLM` for ordinary chat                      | Prefer `ChatOllama`                              |
| `SimpleChatModel` for new custom models            | `BaseChatModel`                                  |
| manually parsing provider tool-call JSON           | use standardized `AIMessage.tool_calls`          |
| manually parsing normal JSON output                | `.with_structured_output()` where appropriate    |
| retry loops everywhere                             | Runnable `.with_retry()`                         |
| manually switching providers everywhere            | `.with_fallbacks()` / gateway                    |
| provider-specific application code everywhere      | `BaseChatModel` / `init_chat_model`              |

Current Ollama documentation labels `OllamaLLM` as the legacy text-completion interface and directs modern chat use toward `ChatOllama`. ([Docs by LangChain][30])

---

# 81. The most important architectural pattern for you

Given your AI SaaS project, I would eventually structure your model layer roughly like this:

```text
src/
└── ai_rag/
    ├── core/
    │   └── config.py
    │
    ├── domains/
    │   └── chat/
    │       ├── ports/
    │       │   └── llm_port.py
    │       │
    │       ├── services/
    │       │   └── chat_service.py
    │       │
    │       └── models/
    │
    └── infrastructure/
        └── llm/
            ├── factory.py
            ├── gemini.py
            ├── ollama.py
            ├── gateway.py
            └── usage.py
```

This fits very naturally with the `Protocol`/port architecture you've already been studying.

---

# 82. Why your `LLMPort` idea makes sense

Conceptually:

```python
class LLMPort(Protocol):
    async def astream_response(...):
        ...
```

Your domain/application layer depends on:

```text
LLMPort
```

not:

```text
ChatGoogleGenerativeAI
```

Then infrastructure implements it using:

```text
Gemini
Ollama
LiteLLM
Fake model
```

That gives you:

```text
Domain
   ↓
Port
   ↓
Adapter
   ↓
LangChain
   ↓
Provider
```

This is a very good architecture for the product you're building.

---

# 83. A practical Gemini model wrapper

A simple starting point:

```python
from langchain_google_genai import ChatGoogleGenerativeAI


def create_gemini_model() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0,
        timeout=30,
        max_retries=3,
    )
```

Then:

```python
model = create_gemini_model()

response = model.invoke(
    [
        ("system", "You are a helpful assistant."),
        ("human", "Explain LangGraph in one paragraph."),
    ]
)

print(response.content)
print(response.usage_metadata)
```

The current Gemini integration supports native async, streaming and token usage. ([Docs by LangChain][15])

---

# 84. Add tools

```python
from langchain.tools import tool


@tool
def get_weather(location: str) -> str:
    """Get the current weather for a location."""
    return f"{location}: sunny, 30°C"


model_with_tools = model.bind_tools(
    [get_weather]
)
```

Then:

```python
response = model_with_tools.invoke(
    "What is the weather in Pune?"
)

print(response.tool_calls)
```

The important thing is that:

```python
bind_tools()
```

doesn't execute anything.

It changes what the model is allowed to request.

---

# 85. Add structured output

```python
from pydantic import BaseModel, Field


class Answer(BaseModel):
    answer: str = Field(description="The answer to the user's question")
    confidence: float = Field(
        ge=0,
        le=1,
        description="Confidence from 0 to 1",
    )


structured_model = model.with_structured_output(Answer)

result = structured_model.invoke(
    "Explain what RAG is."
)

print(result.answer)
print(result.confidence)
```

This is dramatically better than:

```python
json.loads(model.invoke(...).content)
```

because you're explicitly describing the contract between the model and your application.

---

# 86. Compose resilience

Conceptually:

```python
reliable_model = (
    model
    .with_retry(
        stop_after_attempt=3,
    )
)
```

Then:

```python
reliable_model = reliable_model.with_fallbacks(
    [local_model]
)
```

That produces:

```text
Gemini
 ↓
retry
 ↓
retry
 ↓
retry
 ↓
fallback
 ↓
Ollama
```

---

# 87. The ordering matters

Generally think carefully about:

```python
model.with_retry(...).with_fallbacks(...)
```

versus:

```python
model.with_fallbacks([...]).with_retry(...)
```

They do not express the exact same policy.

Conceptually:

### Retry around primary, then fallback

```text
Gemini
 ├── retry
 ├── retry
 └── retry
       ↓
    fallback
```

### Fallback inside a retry

```text
try whole strategy
  ↓
Gemini
  ↓
Ollama
  ↓
retry whole chain
```

The exact semantics depend on how you compose the Runnables.

So do not chain methods randomly.

Decide:

> What constitutes one attempt?

That is an important production design question.

---

# 88. Batch architecture

Suppose you have:

```python
questions = [
    "What is RAG?",
    "What is MCP?",
    "What is LangGraph?",
]
```

You can use:

```python
responses = model.batch(questions)
```

For asynchronous systems:

```python
responses = await model.abatch(questions)
```

Then each result is an `AIMessage`.

---

# 89. Why batch is not always best

Imagine a provider has:

```text
rate limit: 10 requests/sec
```

You call:

```python
await model.abatch(1000_questions)
```

You still need to understand provider concurrency and throttling.

Therefore production applications may need:

```text
batch
+
concurrency limits
+
rate limiting
+
retry
```

rather than blindly spawning hundreds of requests.

---

# 90. Concurrency is another concept

There are three related concepts:

```text
batching
concurrency
rate limiting
```

They are not identical.

### Batching

```text
give many inputs to a Runnable API
```

### Concurrency

```text
multiple requests active simultaneously
```

### Rate limiting

```text
don't exceed provider allowance
```

This distinction becomes very important for agent swarms and Deep Agents.

---

# 91. Model capability matrix

Before selecting an LLM for an agent, I recommend maintaining a mental table like:

| Capability        | Gemini         | Ollama model           | Model X        |
| ----------------- | -------------- | ---------------------- | -------------- |
| normal chat       | ✅              | ✅                      | ✅              |
| streaming         | ✅              | ✅                      | ✅              |
| async             | ✅              | ✅                      | ✅              |
| tool calling      | ✅              | depends/model-specific | ✅              |
| structured output | ✅              | depends/model-specific | ✅              |
| vision            | model-specific | model-specific         | model-specific |
| audio             | model-specific | model-specific         | model-specific |
| usage metadata    | ✅              | integration-dependent  | varies         |
| reasoning         | model-specific | model-specific         | varies         |

The exact capability should be checked for the **specific model**, not merely the provider.

Current LangChain model documentation exposes capability information, and the Gemini/Ollama integration pages document their current feature matrices. ([Docs by LangChain][7])

---

# 92. Why model choice becomes critical for Deep Agents

Deep Agents need reliable:

```text
tool calling
+
structured interaction
+
long context
+
streaming
+
consistent tool arguments
```

If you choose a model that is amazing at writing prose but poor at tool calls:

```text
Deep Agent
  ↓
tool call malformed
  ↓
tool fails
  ↓
agent loops
```

So for agent systems:

> **tool-calling reliability often matters more than benchmark intelligence.**

---

# 93. A complete architecture for your future AI SaaS

I would eventually aim for:

```text
                    ┌───────────────┐
                    │   FastAPI     │
                    └───────┬───────┘
                            │
                            ▼
                    ┌───────────────┐
                    │   LangGraph   │
                    └───────┬───────┘
                            │
                            ▼
                    ┌───────────────┐
                    │ Model Port    │
                    └───────┬───────┘
                            │
              ┌─────────────┼──────────────┐
              │             │              │
              ▼             ▼              ▼
          Gemini         Ollama        Fake Model
              │             │
              │             │
              └──────┬──────┘
                     ▼
                  LiteLLM
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
      Gemini       Groq       OpenRouter
```

Although whether LiteLLM sits between LangChain and Ollama/Gemini for every environment is an architectural decision, not a requirement.

---

# 94. Development architecture I recommend for you

Because you prefer free/open-source tools:

### Local development

```text
FastAPI
   ↓
LangGraph
   ↓
ChatOllama
   ↓
local model
```

No API cost.

### Learning provider integration

```text
FastAPI
   ↓
LangGraph
   ↓
ChatGoogleGenerativeAI
   ↓
Gemini
```

Use this to learn provider capabilities.

### More production-like architecture

```text
FastAPI
   ↓
LangGraph
   ↓
LangChain model interface
   ↓
LiteLLM
   ↓
providers
```

That gives you provider abstraction and centralized spend/routing control.

---

# 95. Testing architecture I recommend

Your test pyramid should look like:

```text
              E2E tests
             /         \
         integration  real model
             \
          graph tests
             \
           unit tests
              ↓
          fake models
```

Most tests should be:

```text
deterministic
fast
free
offline
```

Only a smaller set should call real Gemini.

---

# 96. Unit test example concept

Suppose:

```python
async def classify(model, text):
    response = await model.ainvoke(text)
    return response.content
```

Unit test:

```python
fake_model
     ↓
"technical"
     ↓
assert result == "technical"
```

No Gemini.

No API key.

No network.

No bill.

---

# 97. Integration test

Then separately:

```text
test_real_gemini_integration
        ↓
real Gemini
        ↓
verify provider integration
```

This might be:

```text
pytest -m integration
```

rather than running on every commit.

---

# 98. Testing tool calls

For an agent:

```text
Fake model
   ↓
AIMessage(tool_calls=[...])
   ↓
tool node
   ↓
ToolMessage
   ↓
Fake final AIMessage
```

Then assert:

```text
tool was called
correct arguments were passed
tool result entered state
final answer generated
```

This is dramatically more valuable than testing the exact wording of the model's answer.

---

# 99. What should you assert?

Bad:

```python
assert result == (
    "LangGraph is a framework for..."
)
```

This is brittle.

Better:

```python
assert result.route == "technical"
```

or:

```python
assert len(tool_calls) == 1
assert tool_calls[0]["name"] == "get_weather"
assert tool_calls[0]["args"]["location"] == "Pune"
```

Test **behavior and contracts**, not prose.

---

# 100. A very important distinction: model test vs application test

Suppose Gemini gives an unexpectedly weird answer.

That does not necessarily mean your application is broken.

Separate tests:

```text
MODEL QUALITY
    "Does Gemini answer well?"

APPLICATION CORRECTNESS
    "Does my code react correctly to Gemini's output?"
```

Your unit tests should primarily target the second.

---

# 101. What I recommend you install now

For this module, your environment can start with:

```bash
uv add langchain
uv add langchain-google-genai
uv add langchain-ollama
```

For testing:

```bash
uv add --dev pytest pytest-asyncio
```

For later:

```text
litellm
langfuse
qdrant-client
```

You don't need to install everything immediately.

---

# 102. Your first practical exercise

Create:

```text
module_2/
├── 01_basic_chat.py
├── 02_messages.py
├── 03_async.py
├── 04_streaming.py
├── 05_tools.py
├── 06_structured_output.py
├── 07_retry.py
├── 08_fallback.py
├── 09_ollama.py
├── 10_usage.py
└── tests/
    ├── test_basic.py
    ├── test_tools.py
    └── test_graph_behavior.py
```

This will teach you much more effectively than one giant application.

---

# 103. Exercise 1 — basic Gemini

```python
from langchain_google_genai import ChatGoogleGenerativeAI


model = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0,
)


response = model.invoke(
    "Explain LangGraph like I am a beginner."
)

print("TYPE:", type(response))
print("CONTENT:", response.content)
print("USAGE:", response.usage_metadata)
```

Your goal is not merely:

```text
"it worked"
```

You should inspect:

```python
type(response)
response.content
response.usage_metadata
response.response_metadata
```

---

# 104. Exercise 2 — inspect messages

```python
from langchain_core.messages import (
    SystemMessage,
    HumanMessage,
)


messages = [
    SystemMessage(
        content="You are a beginner-friendly Python teacher."
    ),
    HumanMessage(
        content="Explain dependency injection."
    ),
]

response = model.invoke(messages)

print(response)
```

Then inspect:

```python
print(type(response))
print(response.content)
print(response.usage_metadata)
```

---

# 105. Exercise 3 — async

```python
import asyncio

from langchain_google_genai import ChatGoogleGenerativeAI


model = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0,
)


async def main():
    response = await model.ainvoke(
        "What is LangGraph?"
    )

    print(response.content)


asyncio.run(main())
```

---

# 106. Exercise 4 — streaming

```python
for chunk in model.stream(
    "Explain LangGraph in detail."
):
    print(chunk.content, end="", flush=True)
```

Then change it to:

```python
async for chunk in model.astream(
    "Explain LangGraph in detail."
):
    print(chunk.content, end="", flush=True)
```

Notice the difference between:

```python
for
```

and:

```python
async for
```

---

# 107. Exercise 5 — structured output

```python
from pydantic import BaseModel


class Concept(BaseModel):
    name: str
    explanation: str
    difficulty: str


structured_model = model.with_structured_output(
    Concept
)


result = structured_model.invoke(
    "Explain what LangGraph is and classify its difficulty."
)

print(result)
```

Now you are beginning to build a machine-readable LLM interface.

---

# 108. Exercise 6 — tool calling

```python
from langchain.tools import tool


@tool
def get_weather(location: str) -> str:
    """Return fake weather data."""
    return f"{location}: sunny, 30°C"


model_with_tools = model.bind_tools(
    [get_weather]
)

response = model_with_tools.invoke(
    "What is the weather in Pune?"
)

print(response)
print(response.tool_calls)
```

Do **not** expect LangChain to automatically execute your Python function merely because you used:

```python
bind_tools()
```

That distinction is essential.

---

# 109. Exercise 7 — retry

```python
reliable_model = model.with_retry(
    stop_after_attempt=3,
)
```

Then test it with a fake model that deliberately fails.

That teaches retry behavior much better than waiting for Gemini to randomly fail.

---

# 110. Exercise 8 — fallback

Create:

```text
Gemini
```

and:

```text
Ollama
```

Then:

```python
model_with_fallback = gemini.with_fallbacks(
    [ollama]
)
```

Then intentionally make Gemini fail in a test.

Observe:

```text
Gemini fails
     ↓
Ollama answers
```

---

# 111. Exercise 9 — usage ledger

After every call:

```python
response = await model.ainvoke(...)

usage = response.usage_metadata
```

Convert it into your own internal schema:

```python
class UsageRecord(BaseModel):
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
```

Now you are learning the foundation of AI billing.

---

# 112. Exercise 10 — fake model

Replace:

```python
Gemini
```

with a fake model.

Then test:

```text
tool call
→
tool execution
→
final answer
```

without touching the internet.

This is the exercise I especially recommend before you build complicated LangGraph workflows.

---

# 113. How all of this connects to LangGraph

Once you understand Module 2, LangGraph becomes much easier to understand.

A LangGraph node might essentially do:

```python
async def llm_node(state):
    response = await model.ainvoke(
        state["messages"]
    )

    return {
        "messages": [response]
    }
```

Then another node examines:

```python
response.tool_calls
```

and routes:

```text
tool call?
   │
   ├── yes → tools
   │
   └── no  → END
```

So:

```text
LangGraph is not replacing the chat model.

LangGraph orchestrates what happens around the chat model.
```

That is a hugely important mental model.

---

# 114. How this connects to Deep Agents

Deep Agents add increasingly sophisticated orchestration around these same foundations:

```text
chat model
   +
tools
   +
state
   +
middleware
   +
subagents
   +
planning
   +
memory
   +
streaming
   +
persistence
```

The underlying model still needs to reliably produce:

```text
AIMessage
```

containing:

```text
content
tool_calls
usage_metadata
```

So the concepts you're learning here are not introductory fluff.

They are the low-level contract that your future agents will depend on.

---

# 115. The 10 concepts I want you to be able to explain yourself

Before moving to the next LangGraph module, you should be able to explain these without documentation:

### 1.

Why is:

```python
AIMessage
```

better than simply:

```python
str
```

?

### 2.

What is the difference between:

```text
invoke
ainvoke
stream
astream
batch
abatch
```

?

### 3.

What is:

```text
SystemMessage
HumanMessage
AIMessage
ToolMessage
```

?

### 4.

What does:

```python
bind_tools()
```

actually do?

### 5.

What does:

```python
with_structured_output()
```

actually do?

### 6.

What is the difference between:

```text
retry
fallback
timeout
circuit breaker
```

?

### 7.

Why can't you treat streamed tool-call chunks as complete tool calls?

### 8.

What is:

```python
usage_metadata
```

and why should your application store it?

### 9.

Why should unit tests use fake chat models?

### 10.

Why is:

```text
BaseChatModel
```

more important to your architecture than:

```text
ChatGoogleGenerativeAI
```

?

If those ten are crystal clear, you have genuinely learned Module 2 rather than memorized it.

---

# 116. Your modern stack for this module

For **your specific learning path**, I would use:

```text
Python
  ↓
uv
  ↓
LangChain 1.x
  ↓
langchain-core 1.x
  ↓
Gemini via langchain-google-genai
  │
  ├── primary hosted model
  │
  └── tool/structured-output learning
  ↓
Ollama + langchain-ollama
  │
  └── local/FOSS development
  ↓
LiteLLM
  │
  └── optional centralized model gateway
  ↓
LangGraph
  ↓
Deep Agents
```

And for testing:

```text
pytest
+
LangChain fake chat models
```

This keeps the stack aligned with your preference for mature, reusable infrastructure rather than writing provider adapters and retry machinery yourself.

---

# 117. The most important "modern vs deprecated" rules to remember

Keep this little checklist:

```text
✅ langchain 1.x
✅ langchain-core 1.x
✅ langchain-google-genai
✅ langchain-ollama
✅ ChatGoogleGenerativeAI
✅ ChatOllama
✅ init_chat_model
✅ BaseChatModel
✅ AIMessage / ToolMessage
✅ bind_tools
✅ with_structured_output
✅ with_retry
✅ with_fallbacks
✅ FakeMessagesListChatModel / GenericFakeChatModel
```

Be suspicious of tutorials using:

```text
⚠️ langchain-classic for new development
⚠️ old provider integrations from community packages
⚠️ legacy Google SDK patterns
⚠️ OllamaLLM for modern chat applications
⚠️ SimpleChatModel for new custom model implementations
⚠️ manually parsing provider-specific tool-call JSON
⚠️ manually writing retry loops everywhere
```

The current docs are explicit about several of these transitions. ([LangChain Reference Docs][14])

---

# 118. One final mental model

I want you to remember this diagram more than any individual API:

```text
                         YOUR APPLICATION
                               │
                               ▼
                         BaseChatModel
                               │
               ┌───────────────┼────────────────┐
               │               │                │
             invoke          stream          batch
               │               │                │
             ainvoke         astream          abatch
               │
               ▼
           AIMessage
               │
       ┌───────┼─────────┐
       │       │         │
     text   tool_calls  usage
       │       │         │
       │       │         ▼
       │       │    cost / ledger
       │       │
       │       ▼
       │     Tool
       │       │
       │       ▼
       │  ToolMessage
       │       │
       └───────┴──────────────┐
                              ▼
                         LangGraph
                              │
                ┌─────────────┼─────────────┐
                │             │             │
              retry        fallback      routing
                │             │             │
                └─────────────┼─────────────┘
                              ▼
                        Deep Agents
```

That is the conceptual foundation you want before going deeper into LangGraph.

### What I would study next

The most useful next lesson is **a hands-on Module 2 lab**, where we build one small project incrementally with **Gemini + Ollama + tools + structured output + streaming + retries + fallbacks + fake models + pytest**, and inspect the actual `AIMessage`, `AIMessageChunk`, `ToolMessage`, and usage objects at every step. That will turn the concepts above into something you can actually use in your LangGraph/Deep Agents work.

[1]: https://reference.langchain.com/python/langchain-core/language_models/chat_models/BaseChatModel?utm_source=chatgpt.com "BaseChatModel | langchain_core | LangChain Reference"
[2]: https://reference.langchain.com/python/langchain-core/messages/ai/AIMessage/tool_calls?utm_source=chatgpt.com "tool_calls | langchain_core | LangChain Reference"
[3]: https://reference.langchain.com/python/langchain-core/messages/utils?utm_source=chatgpt.com "utils | langchain_core | LangChain Reference"
[4]: https://reference.langchain.com/python/langchain-core/messages/ai/AIMessage?utm_source=chatgpt.com "AIMessage | langchain_core | LangChain Reference"
[5]: https://reference.langchain.com/python/langchain-core/utils/function_calling?utm_source=chatgpt.com "function_calling | langchain_core | LangChain Reference"
[6]: https://reference.langchain.com/python/langchain-core/runnables/base?utm_source=chatgpt.com "base | langchain_core | LangChain Reference"
[7]: https://docs.langchain.com/oss/python/langchain/models?utm_source=chatgpt.com "Models - Docs by LangChain"
[8]: https://docs.langchain.com/oss/python/langchain/structured-output?utm_source=chatgpt.com "Structured output - Docs by LangChain"
[9]: https://reference.langchain.com/python/langchain-core/runnables/base/Runnable/with_retry?utm_source=chatgpt.com "with_retry | langchain_core | LangChain Reference"
[10]: https://reference.langchain.com/python/langchain-core/runnables/fallbacks/RunnableWithFallbacks?utm_source=chatgpt.com "RunnableWithFallbacks | langchain_core | LangChain Reference"
[11]: https://docs.python.org/3/library/asyncio-task.html?highlight=n&utm_source=chatgpt.com "Coroutines and tasks — Python 3.14.7 documentation"
[12]: https://github.com/arlyon/aiobreaker?utm_source=chatgpt.com "GitHub - arlyon/aiobreaker: Python implementation of the Circuit Breaker pattern. · GitHub"
[13]: https://reference.langchain.com/python/langchain/chat_models/base?utm_source=chatgpt.com "base | langchain | LangChain Reference"
[14]: https://reference.langchain.com/python/langchain-classic/chat_models/base/init_chat_model?utm_source=chatgpt.com "init_chat_model | langchain_classic | LangChain Reference"
[15]: https://docs.langchain.com/oss/python/integrations/chat/google_generative_ai?utm_source=chatgpt.com "ChatGoogleGenerativeAI integration - Docs by LangChain"
[16]: https://docs.langchain.com/oss/python/integrations/chat?utm_source=chatgpt.com "Chat model integrations - Docs by LangChain"
[17]: https://docs.langchain.com/oss/python/integrations/chat/ollama?utm_source=chatgpt.com "ChatOllama integration - Docs by LangChain"
[18]: https://docs.langchain.com/oss/python/integrations/embeddings/ollama?utm_source=chatgpt.com "OllamaEmbeddings integration - Docs by LangChain"
[19]: https://docs.ollama.com/api/generate?utm_source=chatgpt.com "Generate a response - Ollama"
[20]: https://docs.ollama.com/api/embed?utm_source=chatgpt.com "Generate embeddings - Ollama"
[21]: https://ollama.com/library/nomic-embed-text?utm_source=chatgpt.com "nomic-embed-text"
[22]: https://ollama.com/library/bge-m3?utm_source=chatgpt.com "bge-m3"
[23]: https://github.com/BerriAI/litellm-docs/blob/main/docs/proxy/docker_quick_start.md?utm_source=chatgpt.com "litellm-docs/docs/proxy/docker_quick_start.md at main · BerriAI/litellm-docs · GitHub"
[24]: https://github.com/BerriAI/litellm-docs/blob/main/docs/proxy/virtual_keys.md?utm_source=chatgpt.com "litellm-docs/docs/proxy/virtual_keys.md at main · BerriAI/litellm-docs · GitHub"
[25]: https://github.com/BerriAI/litellm-docs/blob/main/docs/proxy/prometheus.md?utm_source=chatgpt.com "litellm-docs/docs/proxy/prometheus.md at main · BerriAI/litellm-docs · GitHub"
[26]: https://reference.langchain.com/python/langchain-core/messages?utm_source=chatgpt.com "messages | langchain_core | LangChain Reference"
[27]: https://docs.langchain.com/oss/python/langchain/event-streaming?utm_source=chatgpt.com "Event Streaming - Docs by LangChain"
[28]: https://reference.langchain.com/python/langchain-core/callbacks/usage?utm_source=chatgpt.com "usage | langchain_core | LangChain Reference"
[29]: https://reference.langchain.com/python/langchain-core/language_models/fake_chat_models?utm_source=chatgpt.com "fake_chat_models | langchain_core | LangChain Reference"
[30]: https://docs.langchain.com/oss/python/integrations/providers/ollama?utm_source=chatgpt.com "Ollama integrations - Docs by LangChain"
