Below is a **modern Phase 6 / Module 43: Agent Streaming** tutorial, using the current LangChain/LangGraph APIs as of **October 1, 2026**.

I verified the current references before writing this. The current Python reference versions are around `langchain 1.4.x`, `langchain-core 1.6.x`, `langgraph 1.2.x`, and `langchain-google-genai 4.4.x`. ([LangChain Reference Docs][1])

One important correction to your description up front:

> `stream_events(version="v3")` is the **new typed/projection-oriented API and is intended to remove a lot of manual event parsing**, but it is still **beta/experimental** in Python. It is **not yet a universal replacement for every use of v1/v2 `astream_events`**. In particular, generic Runnable event streaming still uses v2 commonly, while v3 is currently implemented specially by chat models and compiled LangGraph graphs. ([LangChain Reference Docs][2])

---

# PHASE 6 — Agents with `create_agent`

## Module 43 — Agent Streaming

We are going to build your understanding in this order:

1. What streaming actually means
2. `invoke()` vs `stream()` vs `astream()`
3. What an agent is streaming
4. `stream_mode`
5. `values`
6. `updates`
7. `messages`
8. `version="v2"`
9. `StreamPart`
10. Combining multiple stream modes
11. Token streaming and `AIMessageChunk`
12. Metadata and namespaces
13. Async streaming
14. Backpressure and cancellation
15. `stream_events(version="v1"/"v2")`
16. Why v3 exists
17. `stream_events(version="v3")`
18. `run.messages`
19. `run.values`
20. `run.updates`
21. `run.output`
22. Subgraphs and namespaces
23. Filtering and mapping streams into your own schema
24. Production architecture for FastAPI/SSE/WebSockets
25. Old/deprecated patterns vs modern patterns
26. A recommended mental model for your enterprise AI harness

---

# 1. First: what does "streaming" actually mean?

You already understand:

```python
result = agent.invoke(...)
```

That means:

```text
request
   ↓
agent executes
   ↓
LLM/tool/LLM/tool/...
   ↓
everything completes
   ↓
final result
```

The caller sees essentially one result:

```text
FINAL RESULT
```

Streaming changes the interaction to:

```text
request
   ↓
agent starts
   ↓
event/chunk
   ↓
event/chunk
   ↓
event/chunk
   ↓
event/chunk
   ↓
...
   ↓
final result
```

Instead of:

```python
result = agent.invoke(...)
print(result)
```

you do:

```python
for chunk in agent.stream(...):
    print(chunk)
```

or asynchronously:

```python
async for chunk in agent.astream(...):
    print(chunk)
```

LangGraph's streaming infrastructure supports state values, node updates, LLM messages, custom events, checkpoints, tasks, and debug information. ([LangChain Reference Docs][3])

---

# 2. Why streaming matters for agents

Streaming isn't just a UI feature.

For an agent, the execution might actually be:

```text
User
 ↓
Model
 ↓
Tool call
 ↓
Tool execution
 ↓
Model
 ↓
Tool call
 ↓
Tool execution
 ↓
Model
 ↓
Final answer
```

The user may otherwise sit waiting for several seconds.

Streaming lets you expose progress such as:

```text
Thinking...
Calling search tool...
Searching...
Tool completed.
Generating answer...
The answer is...
```

That becomes especially important in your enterprise AI harness because an agent may eventually call:

```text
Microsoft 365
Salesforce
ServiceNow
Google Drive
Slack
Teams
Zoom
MCP servers
internal RAG
databases
...
```

Without streaming, the frontend sees:

```text
[waiting...]
```

With streaming, it can see meaningful execution progress.

---

# 3. `invoke()` vs `stream()` vs `astream()`

Think of the three like this:

| API         | Execution    | Output             |
| ----------- | ------------ | ------------------ |
| `invoke()`  | synchronous  | one final result   |
| `stream()`  | synchronous  | incremental chunks |
| `astream()` | asynchronous | incremental chunks |

Basic:

```python
result = agent.invoke(
    {"messages": [{"role": "user", "content": "Hello"}]}
)
```

Streaming:

```python
for chunk in agent.stream(
    {"messages": [{"role": "user", "content": "Hello"}]}
):
    print(chunk)
```

Async streaming:

```python
async for chunk in agent.astream(
    {"messages": [{"role": "user", "content": "Hello"}]}
):
    print(chunk)
```

For a FastAPI backend, you'll generally care much more about:

```python
agent.astream(...)
```

because HTTP request handling is naturally asynchronous.

---

# 4. The most important concept: `stream_mode`

`stream_mode` answers:

> **"What aspect of the agent execution do I want to receive as the stream?"**

Current LangGraph supports:

```text
values
updates
messages
custom
checkpoints
tasks
debug
```

with their respective semantics documented in the current API. ([LangChain Reference Docs][3])

For this module, the three most important are:

```text
values
updates
messages
```

They answer three different questions.

### `values`

> What is the complete state after each step?

### `updates`

> What did each node change?

### `messages`

> What is the LLM currently streaming?

This distinction is fundamental.

---

# 5. `stream_mode="values"`

Suppose the agent state is conceptually:

```python
{
    "messages": [...]
}
```

With:

```python
agent.stream(
    input,
    stream_mode="values",
)
```

you receive **state snapshots** after graph steps.

The official definition is essentially:

> emit all values in the state after each step. ([LangChain Reference Docs][3])

Conceptually:

```text
Step 1
state = {
    messages: [...]
}

Step 2
state = {
    messages: [..., AIMessage(...)]
}

Step 3
state = {
    messages: [..., AIMessage(...), ToolMessage(...)]
}

Step 4
state = {
    messages: [..., AIMessage(...), ToolMessage(...), AIMessage(...)]
}
```

So `values` is **state-centric**.

---

# 6. Why `values` is useful

Suppose your agent does:

```text
User
 ↓
Model decides to call weather
 ↓
Weather tool
 ↓
Model answers
```

You might receive state snapshots corresponding roughly to:

```python
{
    "messages": [
        HumanMessage(...)
    ]
}
```

then:

```python
{
    "messages": [
        HumanMessage(...),
        AIMessage(tool_calls=[...])
    ]
}
```

then:

```python
{
    "messages": [
        HumanMessage(...),
        AIMessage(tool_calls=[...]),
        ToolMessage(...)
    ]
}
```

then:

```python
{
    "messages": [
        HumanMessage(...),
        AIMessage(tool_calls=[...]),
        ToolMessage(...),
        AIMessage(...)
    ]
}
```

So `values` is extremely useful when you want to understand:

> "What does the agent's state look like right now?"

---

# 7. Important: values are not tokens

This is a common beginner mistake.

This:

```python
stream_mode="values"
```

does **not** mean:

```text
H
He
Hel
Hell
Hello
```

It means more like:

```text
state after step 1
state after step 2
state after step 3
```

Therefore:

```text
values ≠ token streaming
```

For LLM token streaming, use:

```python
stream_mode="messages"
```

---

# 8. `stream_mode="updates"`

`updates` is different.

Instead of giving you the entire state, it tells you:

> What update did the node/task produce?

The current API defines updates as node/task outputs after each step. Multiple updates in the same step can be emitted separately. ([LangChain Reference Docs][3])

For an agent, you might conceptually receive:

```python
{
    "model": {
        "messages": [...]
    }
}
```

then:

```python
{
    "tools": {
        "messages": [...]
    }
}
```

then:

```python
{
    "model": {
        "messages": [...]
    }
}
```

The exact execution structure can vary with middleware, tools, agent configuration, subgraphs, etc., so don't build production logic assuming only `"model"` and `"tools"` will ever exist.

---

# 9. `values` vs `updates`

This distinction is extremely important.

Imagine the current state is:

```python
{
    "counter": 10,
    "messages": [...]
}
```

A node changes:

```python
counter = 11
```

### `values`

you get:

```python
{
    "counter": 11,
    "messages": [...]
}
```

### `updates`

you get something conceptually like:

```python
{
    "some_node": {
        "counter": 11
    }
}
```

So:

```text
values  → snapshot
updates → delta/update
```

A useful mental analogy:

```text
values  = "Here is the whole document now."

updates = "Here is what changed."
```

---

# 10. When should you use `values`?

Use `values` when you need:

* state snapshots
* debugging state evolution
* displaying state to an operator
* checkpoint-like UI behavior
* understanding graph execution
* state reconstruction

For example:

```python
for part in agent.stream(
    input,
    stream_mode="values",
    version="v2",
):
    state = part["data"]
    print(state)
```

---

# 11. When should you use `updates`?

Use `updates` when you care about:

* which node produced something
* state changes
* execution progression
* tool execution updates
* efficient incremental state changes

For an agent observability console, `updates` is often much more useful than repeatedly transmitting the entire state.

---

# 12. `stream_mode="messages"`

Now we reach the most important streaming mode for chat applications.

`messages` means:

> stream LLM message chunks together with metadata.

The current LangGraph API explicitly describes it as emitting LLM messages token-by-token together with metadata for LLM invocations. ([LangChain Reference Docs][3])

This is what you normally think of when you see ChatGPT producing:

```text
Hello
Hello, how
Hello, how can
Hello, how can I
Hello, how can I help?
```

---

# 13. The object you receive from `messages`

With modern v2 streaming:

```python
for part in agent.stream(
    input,
    stream_mode="messages",
    version="v2",
):
    ...
```

the relevant stream part has:

```python
{
    "type": "messages",
    "ns": (...),
    "data": (
        message,
        metadata,
    ),
}
```

The official `MessagesStreamPart` type defines:

```text
type = "messages"
ns   = tuple[str, ...]
data = (message, metadata)
```

and the message may be an `AIMessageChunk`. ([LangChain Reference Docs][4])

---

# 14. What is an `AIMessageChunk`?

An `AIMessage` is the completed response.

An `AIMessageChunk` is a partial response.

For example:

```text
AIMessage
"Hello, how can I help you today?"
```

versus:

```text
AIMessageChunk
"Hello"

AIMessageChunk
", how"

AIMessageChunk
" can"

AIMessageChunk
" I help"

AIMessageChunk
" you today?"
```

The current reference explicitly defines `AIMessageChunk` as the message chunk yielded while streaming. ([LangChain Reference Docs][5])

---

# 15. The modern way to get text

You may see examples like:

```python
message.text()
```

Don't use that for new code.

Current LangChain uses:

```python
message.text
```

The `.text()` method is deprecated; `.text` is the modern property. ([LangChain Reference Docs][6])

So:

```python
print(message.text, end="")
```

is modern.

Not:

```python
print(message.text(), end="")
```

---

# 16. Your first real agent streaming example

Using Gemini as you requested:

```python
from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI

model = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash",
)

agent = create_agent(
    model=model,
    tools=[],
    system_prompt="You are a helpful assistant.",
)

inputs = {
    "messages": [
        {
            "role": "user",
            "content": "Explain LangGraph in three sentences.",
        }
    ]
}

for part in agent.stream(
    inputs,
    stream_mode="messages",
    version="v2",
):
    if part["type"] != "messages":
        continue

    message, metadata = part["data"]

    if message.text:
        print(message.text, end="", flush=True)
```

`ChatGoogleGenerativeAI` is the current LangChain integration for Gemini, and the current integration uses Google's consolidated `google-genai` SDK. ([LangChain Reference Docs][7])

---

# 17. What is `version="v2"`?

There are two separate concepts you must not mix up:

```text
stream mode
```

and:

```text
stream version
```

For example:

```python
stream_mode="messages"
version="v2"
```

These mean:

```text
messages
    ↓
"What kind of information do I want?"

v2
    ↓
"How should each streaming item be represented?"
```

---

# 18. `v1` vs `v2` stream format

Historically LangGraph streaming returned less-uniform structures.

The v2 protocol gives you a discriminated `StreamPart` structure:

```python
{
    "type": ...,
    "ns": ...,
    "data": ...
}
```

The current reference describes `StreamPart` as a discriminated union of the v2 stream-part types. ([LangChain Reference Docs][8])

That is extremely useful.

Instead of guessing what a chunk represents:

```python
if ...
elif ...
```

you have an explicit discriminator:

```python
part["type"]
```

---

# 19. The three fields of a v2 `StreamPart`

The important structure is:

```python
{
    "type": "messages",
    "ns": (),
    "data": (...),
}
```

Let's understand each.

## `type`

Tells you what kind of stream part this is.

Examples:

```text
values
updates
messages
custom
checkpoints
tasks
debug
```

---

## `ns`

Namespace.

It identifies where in the graph the event came from.

For a root graph, this is commonly:

```python
()
```

For nested graphs/subgraphs, it can contain the namespace path.

This becomes very important once you begin building:

* multi-agent systems
* subagents
* nested graphs
* Deep Agents
* enterprise orchestration

---

## `data`

The actual payload.

For example:

### values

```python
part["data"]
```

is the state snapshot.

### updates

```python
part["data"]
```

is the node update mapping.

### messages

```python
message, metadata = part["data"]
```

The v2 `StreamPart` design is deliberately discriminated so you can narrow by `"type"` and then know what kind of `data` you're dealing with. ([LangChain Reference Docs][8])

---

# 20. Why typed stream parts matter

Imagine a future agent that produces:

```text
LLM tokens
tool progress
node updates
custom progress
sub-agent events
state snapshots
```

Without a discriminator you might have to infer:

```text
"What is this object?"
```

With v2:

```python
if part["type"] == "messages":
    ...

elif part["type"] == "updates":
    ...

elif part["type"] == "values":
    ...

elif part["type"] == "custom":
    ...
```

This is essentially a tagged/discriminated union.

That is a much better foundation for production event processing.

---

# 21. Multiple stream modes at the same time

One of the most useful current features is that `stream_mode` can be a list.

The API supports:

```python
stream_mode=[
    "messages",
    "updates",
]
```

so one execution can produce multiple kinds of streaming data. ([LangChain Reference Docs][9])

For example:

```python
for part in agent.stream(
    inputs,
    stream_mode=["messages", "updates"],
    version="v2",
):
    if part["type"] == "messages":
        message, metadata = part["data"]
        print(message.text, end="", flush=True)

    elif part["type"] == "updates":
        print("\nUPDATE:", part["data"])
```

This is much more powerful than thinking of streaming as "just token output".

---

# 22. A better mental model

Think about an agent execution as a river of different event types:

```text
                  AGENT EXECUTION
                         │
             ┌───────────┴────────────┐
             │                        │
          graph                   LLM calls
             │                        │
      ┌──────┼───────┐          token chunks
      │      │       │
    values updates custom
```

Then:

```text
v2
 ↓
one common envelope

{
    type,
    ns,
    data
}
```

This is a very useful architecture for your own backend.

---

# 23. The difference between agent streaming and model streaming

This is another critical concept.

You can stream:

### The model

```python
model.stream(...)
```

or:

```python
model.astream(...)
```

That mostly gives you model output chunks.

But an agent is much larger:

```text
agent
 ├── model
 ├── tools
 ├── middleware
 ├── graph state
 ├── subgraphs
 ├── checkpoints
 └── execution lifecycle
```

Agent streaming therefore gives you access to the execution around the model.

---

# 24. Model-level streaming

At the lowest level:

```python
for chunk in model.stream(
    "Hello"
):
    print(chunk.text)
```

You care about:

```text
LLM → chunks
```

At the agent level:

```python
for part in agent.stream(...):
    ...
```

You care about:

```text
Agent
 ├── model chunks
 ├── tool activity
 ├── state updates
 ├── graph progression
 └── final state
```

This distinction becomes extremely important as you move into LangGraph and Deep Agents.

---

# 25. Metadata in `messages`

`messages` isn't just:

```python
message
```

It is:

```python
message, metadata
```

The metadata can include information about the graph execution, including things such as:

```text
langgraph_step
langgraph_node
langgraph_triggers
...
```

The current `MessagesStreamPart` documentation explicitly describes this metadata. ([LangChain Reference Docs][4])

For example:

```python
message, metadata = part["data"]

print(metadata)
```

You might use:

```python
node = metadata.get("langgraph_node")
step = metadata.get("langgraph_step")
```

This lets your frontend know:

```text
This token came from:
agent step 4
model node
```

rather than merely:

```text
token = "hello"
```

---

# 26. Why metadata is extremely important for your enterprise harness

Imagine:

```text
Supervisor
 ├── HR agent
 ├── Salesforce agent
 └── ServiceNow agent
```

Then:

```text
"Searching Salesforce..."
```

and:

```text
"Searching ServiceNow..."
```

cannot simply be treated as one giant text stream.

You need provenance:

```text
tenant
user
thread
run
agent
subgraph
node
model
tool
timestamp
event type
```

Streaming metadata is therefore part of your future event architecture.

---

# 27. Async agent streaming

For FastAPI, this is particularly important.

Use:

```python
async for part in agent.astream(
    inputs,
    stream_mode="messages",
    version="v2",
):
    ...
```

Example:

```python
async def stream_agent():
    async for part in agent.astream(
        inputs,
        stream_mode="messages",
        version="v2",
    ):
        if part["type"] != "messages":
            continue

        message, metadata = part["data"]

        text = message.text

        if text:
            yield text
```

This is the pattern that naturally maps to:

```text
FastAPI
   ↓
async generator
   ↓
SSE
   ↓
browser
```

---

# 28. A subtle but important issue: token ≠ character

People commonly call everything a "token".

You should mentally distinguish:

```text
LLM provider token
```

from:

```text
LangChain message chunk
```

One `AIMessageChunk` is not necessarily one tokenizer token.

A provider may aggregate pieces.

Therefore don't write architecture that assumes:

```python
one chunk == one token
```

Instead think:

```text
stream chunk
```

or:

```text
text delta
```

That is the safer abstraction.

---

# 29. Tool calls can also stream

Modern LangChain messages aren't limited to text.

The message model now has standardized content blocks such as:

```text
text
reasoning
tool_call
image
audio
video
...
```

and `AIMessageChunk` can contain tool-call chunks as well. ([LangChain Reference Docs][10])

That means an advanced agent stream might look conceptually like:

```text
text delta
text delta
tool call delta
tool call delta
tool call finished
tool result
text delta
text delta
```

So your event architecture should **not** assume every message event is plain text.

---

# 30. This is why `message.text` is useful — but not always sufficient

This:

```python
message.text
```

extracts text blocks.

Current LangChain documents that `.text` only extracts blocks of type `"text"` and ignores other content blocks. ([LangChain Reference Docs][6])

So:

```python
print(message.text)
```

is excellent for a simple chatbot UI.

But for a sophisticated agent UI you eventually want:

```python
message.content_blocks
```

because you may want to distinguish:

```text
text
reasoning
tool_call
server_tool_call
image
...
```

---

# 31. Now: event streaming

So far we discussed:

```python
agent.stream(...)
```

with:

```text
values
updates
messages
```

Now we need:

```python
agent.stream_events(...)
```

The key difference is:

### `stream()`

"What stream representation do I want?"

### `stream_events()`

"Give me the execution/event stream."

---

# 32. Old event streaming: `astream_events`

Historically, LangChain exposed:

```python
astream_events(version="v1")
```

and:

```python
astream_events(version="v2")
```

The v1/v2 event API produces event dictionaries such as:

```python
{
    "event": "on_chat_model_stream",
    "name": "...",
    "run_id": "...",
    "parent_ids": [...],
    "tags": [...],
    "metadata": {...},
    "data": {...},
}
```

The current Runnable reference still documents v1/v2 in detail. ([LangChain Reference Docs][11])

---

# 33. What was annoying about old event APIs?

The problem is that you often had to do things like:

```python
if event["event"] == "on_chat_model_stream":
    ...

elif event["event"] == "on_tool_start":
    ...

elif event["event"] == "on_tool_end":
    ...

elif event["event"] == "on_chain_start":
    ...
```

Then you had to inspect:

```python
event["data"]
```

and figure out what structure was inside.

This works.

But for a large agent system, manually interpreting low-level event dictionaries gets tedious.

---

# 34. Enter `stream_events(version="v3")`

Current LangGraph introduces a new approach.

Instead of returning merely a giant pile of low-level events, v3 produces a typed run object with projections.

Conceptually:

```python
run = agent.stream_events(
    inputs,
    version="v3",
)
```

Then:

```python
run.messages
run.values
run.updates
run.output
run.subgraphs
...
```

The current Python LangGraph API describes v3 as returning a `GraphRunStream` with typed projections. ([LangChain Reference Docs][12])

---

# 35. What is a "projection"?

Think of the raw execution as:

```text
EVERYTHING
│
├── model events
├── tool events
├── state events
├── tasks
├── custom data
├── subgraphs
└── lifecycle
```

A projection gives you one useful view:

```text
run.messages
```

means:

> "Give me the message streams."

Another:

```text
run.values
```

means:

> "Give me state snapshots."

Another:

```text
run.updates
```

means:

> "Give me node/task updates."

This is an excellent abstraction.

---

# 36. `run.messages`

A modern v3 example is conceptually:

```python
run = agent.stream_events(
    inputs,
    version="v3",
)

for message_stream in run.messages:
    for text in message_stream.text:
        print(text, end="", flush=True)
```

The `messages` projection yields a per-LLM-call `ChatModelStream`. That stream exposes typed projections such as:

```text
.text
.reasoning
.tool_calls
.output
```

The current `MessagesTransformer` and `ChatModelStream` references document this architecture. ([LangChain Reference Docs][13])

---

# 37. This is a major conceptual improvement

Old:

```text
event
 ↓
event.event
 ↓
identify model event
 ↓
inspect event.data
 ↓
extract chunk
 ↓
figure out what it means
```

v3:

```text
run.messages
 ↓
ChatModelStream
 ├── text
 ├── reasoning
 ├── tool_calls
 └── output
```

You now consume the thing you're interested in directly.

---

# 38. `ChatModelStream`

This is worth understanding very carefully.

A `ChatModelStream` represents **one LLM response stream**.

It provides:

```python
stream.text
```

for text deltas.

```python
stream.reasoning
```

for reasoning deltas.

```python
stream.tool_calls
```

for tool-call chunks.

```python
stream.output
```

for the final assembled `AIMessage`.

The current reference explicitly describes these projections. ([LangChain Reference Docs][14])

---

# 39. Why `run.messages` can contain multiple streams

An agent may call the model multiple times:

```text
Model call 1
   ↓
tool
   ↓
Model call 2
   ↓
tool
   ↓
Model call 3
```

Therefore:

```python
run.messages
```

is conceptually:

```text
LLM stream #1
LLM stream #2
LLM stream #3
```

not:

```text
one giant string
```

This distinction matters enormously for agent UIs and tracing.

---

# 40. `run.values`

The v3 `values` projection represents state snapshots.

```python
run = agent.stream_events(
    inputs,
    version="v3",
)

for state in run.values:
    print(state)
```

The current `ValuesTransformer` exposes `run.values` as a state-snapshot projection. ([LangChain Reference Docs][15])

So:

```text
run.messages
    ↓
LLM-oriented view

run.values
    ↓
state-oriented view
```

---

# 41. `run.updates`

Similarly:

```python
for update in run.updates:
    print(update)
```

gives node/task updates.

The current `UpdatesTransformer` exposes `run.updates` and describes each item as a mapping of node/task name to its returned update. ([LangChain Reference Docs][16])

---

# 42. `run.output`

This is particularly nice.

Instead of manually waiting for the final stream event, the run object has:

```python
run.output
```

which drives the run to completion and returns the final state. ([LangChain Reference Docs][17])

Conceptually:

```python
run = agent.stream_events(..., version="v3")

for message_stream in run.messages:
    ...

final_state = run.output
```

The stream gives you live information.

`run.output` gives you the final result.

 ---

# 43. Very important: consuming a projection drives the run

This is one of the most interesting implementation details.

The current `GraphRunStream` is **caller-driven**.

That means:

```python
for item in run.messages:
    ...
```

actually advances the execution.

There is no hidden background thread doing the whole run independently.

The caller's iteration drives the pump. ([LangChain Reference Docs][17])

Conceptually:

```text
you request next item
       ↓
Graph executes enough to produce it
       ↓
event produced
       ↓
you receive event
```

This is an important mental model for backpressure.

---

# 44. Projection streams are single-consumer

The current v3 implementation documents that projections are generally **single-consumer**.

For example:

```python
for x in run.values:
    ...
```

and then attempting to iterate:

```python
for x in run.values:
    ...
```

again is not the intended usage.

The API provides `tee()` when you genuinely need fan-out. ([LangChain Reference Docs][17])

So don't casually think:

```python
run.messages
```

is a replayable list.

It behaves more like a live stream/channel.

---

# 45. Async v3

For async code:

```python
run = await agent.astream_events(
    inputs,
    version="v3",
)
```

then:

```python
async for message_stream in run.messages:
    ...
```

The async run stream supports concurrent consumers and uses caller-driven pumping. ([LangChain Reference Docs][18])

That is particularly relevant to FastAPI.

---

# 46. Why v3 is powerful for a frontend

Imagine your frontend needs all of these:

```text
assistant text
reasoning indicator
tool call status
state updates
sub-agent activity
final response
```

Old approach:

```text
raw event stream
     ↓
manually parse
     ↓
classify
     ↓
route
     ↓
construct UI events
```

v3 gives you cleaner building blocks:

```text
run.messages
run.values
run.updates
run.subgraphs
run.output
```

You can then map those into your own API.

---

# 47. Mapping into your own event schema

This is something I strongly recommend for your enterprise harness.

Do **not** make your frontend know every internal LangGraph detail.

Instead create your own protocol.

For example:

```python
from typing import Literal
from pydantic import BaseModel


class AgentEvent(BaseModel):
    type: Literal[
        "text_delta",
        "tool_started",
        "tool_finished",
        "state_update",
        "run_finished",
        "error",
    ]
    run_id: str
    payload: dict
```

Then your frontend receives:

```json
{
  "type": "text_delta",
  "run_id": "abc123",
  "payload": {
    "text": "Hello"
  }
}
```

This is a major architectural principle:

```text
LangGraph stream
       ↓
your adapter
       ↓
your stable event protocol
       ↓
frontend
```

Now LangGraph implementation details stay inside your backend.

---

# 48. Why this matters for your vendor-independent harness

You eventually want:

```text
Gemini
Claude
OpenAI
local model
Azure model
...
```

You do **not** want the frontend to care.

Your frontend should not ask:

```text
"Was this a Gemini chunk?"
```

It should ask:

```text
"What event type is this?"
```

For example:

```json
{
    "type": "text_delta",
    "text": "Hello"
}
```

The model provider disappears behind your agent abstraction.

That's exactly the kind of provider independence you want in your enterprise architecture.

---

# 49. `ns`: namespaces become extremely important

Suppose:

```text
main agent
 ├── researcher
 │    └── search agent
 └── writer
```

A token could originate from:

```text
(.)
```

or:

```text
("researcher",)
```

or:

```text
("researcher", "search")
```

The namespace tells you **where the event lives in the graph hierarchy**.

The v2 `StreamPart` contains `ns`, and v3's projections are also scope-aware. ([LangChain Reference Docs][4])

This is fundamental once you start learning Deep Agents and multi-agent architectures.

---

# 50. Subgraphs in v3

The v3 stream infrastructure also has:

```python
run.subgraphs
```

The current `SubgraphTransformer` discovers nested subgraph executions and gives you handles that themselves expose projections such as:

```python
handle.values
handle.messages
handle.subgraphs
handle.lifecycle
```

recursively. ([LangChain Reference Docs][16])

That is extremely powerful.

Think:

```text
run
│
├── messages
├── values
├── updates
│
└── subgraphs
       │
       ├── researcher
       │     ├── messages
       │     └── values
       │
       └── writer
             ├── messages
             └── values
```

This gives you a much more natural hierarchy than manually reconstructing namespaces from raw events.

---

# 51. `stream_events(v3)` and raw protocol events

Even with v3 projections, LangGraph still has a lower-level protocol underneath.

A `ProtocolEvent` contains fields such as:

```text
type
event_id
seq
method
params
```

The current implementation assigns a monotonic `seq` number so consumers needing total event order should prefer it over wall-clock timestamps. ([LangChain Reference Docs][19])

This is a very advanced concept, but it is useful to understand.

---

# 52. Why `seq` matters

Suppose two events happen extremely close together:

```text
timestamp A = 12:00:00.123
timestamp B = 12:00:00.123
```

Wall-clock time isn't necessarily sufficient to determine strict ordering.

The internal protocol has a monotonic sequence:

```text
seq=41
seq=42
seq=43
```

So:

```text
seq
```

is the ordering mechanism you should trust when reconstructing a precise stream order inside a run. ([LangChain Reference Docs][19])

---

# 53. Filtering events

For the **older/current v1/v2 Runnable event API**, there are built-in filters such as:

```python
include_names
include_types
include_tags

exclude_names
exclude_types
exclude_tags
```

The current Runnable reference documents these filters. ([LangChain Reference Docs][2])

For example, conceptually:

```python
async for event in chain.astream_events(
    input,
    version="v2",
    include_types=["chat_model"],
):
    ...
```

This is useful when you deliberately want the raw event model.

---

# 54. Filtering with v3

Here you should change your mindset.

Rather than:

```text
Give me everything
Then manually remove 90%
```

you can often select the appropriate projection:

```python
run.messages
```

instead of:

```text
all raw events
```

Or:

```python
run.values
```

instead of:

```text
all state-related events
```

For advanced custom requirements, v3 supports a transformer architecture. Current `stream_events(version="v3")` accepts additional transformers, and LangGraph provides built-in transformers for values, updates, messages, custom events, tasks, lifecycle and more. ([LangChain Reference Docs][12])

---

# 55. Custom stream transformation

This is where the API becomes particularly interesting for your project.

LangGraph's current streaming architecture contains:

```text
StreamMux
   ↓
StreamTransformer
   ↓
projection
```

A `StreamTransformer` observes protocol events and constructs derived projections. ([LangChain Reference Docs][20])

That means you can conceptually create:

```text
LangGraph events
       ↓
EnterpriseEventTransformer
       ↓
run.enterprise_events
```

This is much closer to how I'd eventually structure your enterprise harness.

---

# 56. Think of transformers as adapters

You can think:

```text
raw LangGraph stream
        ↓
 transformer
        ↓
 your domain stream
```

For example:

```text
LangGraph:
on_chat_model_stream
        ↓
Transformer
        ↓
enterprise:
TEXT_DELTA
```

Or:

```text
LangGraph tool execution
        ↓
Transformer
        ↓
enterprise:
TOOL_EXECUTION
```

You don't want your frontend coupled directly to LangGraph internals.

---

# 57. Custom event streaming

There is also:

```python
stream_mode="custom"
```

and:

```python
get_stream_writer()
```

for nodes/tasks to emit custom information.

The current API documents custom stream data as user-defined values emitted through the stream writer. ([LangChain Reference Docs][3])

For example, a long-running enterprise tool might emit:

```text
10% downloaded
25% downloaded
50% downloaded
75% downloaded
100% downloaded
```

That isn't an LLM token.

It's application progress.

That is exactly what `custom` is for.

---

# 58. So now we have four different concepts

You should memorize this table:

| Mechanism  | Question                                               |
| ---------- | ------------------------------------------------------ |
| `values`   | What is the current state?                             |
| `updates`  | What changed?                                          |
| `messages` | What is the LLM producing?                             |
| `custom`   | What application-specific progress/data should I emit? |

This is one of the most important pieces of this entire module.

---

# 59. `messages` vs `custom`

Don't use LLM messages for everything.

Bad design:

```text
"Searching Salesforce..." 
```

as fake assistant text.

Better:

```json
{
    "type": "custom",
    "data": {
        "status": "searching_salesforce"
    }
}
```

Then your UI decides how to display it.

This separation becomes incredibly useful for enterprise applications.

---

# 60. `values` vs `updates` vs `messages` — practical example

Suppose the user says:

```text
"Find my latest Salesforce opportunity."
```

Agent executes:

```text
1. model decides Salesforce search
2. Salesforce tool runs
3. model analyzes result
4. model responds
```

### `values`

You might see snapshots:

```text
State after model
State after tool
State after model
```

### `updates`

You might see:

```text
model update
tools update
model update
```

### `messages`

You see model-generated chunks:

```text
"I'll"
" search"
" Salesforce"
...
```

### `custom`

You could emit:

```text
"salesforce_search_started"
"salesforce_search_completed"
```

That is how these mechanisms complement each other.

---

# 61. Agent streaming architecture

Your mental model should now be:

```text
                   create_agent()
                        │
                        ▼
                 Compiled graph
                        │
                 ┌──────┴───────┐
                 │              │
              state          LLM calls
                 │              │
              updates         chunks
                 │              │
                 └──────┬───────┘
                        ▼
                    streaming
                        │
        ┌───────────────┼────────────────┐
        │               │                │
     values          updates          messages
        │               │                │
        └───────────────┼────────────────┘
                        │
                 v2 StreamPart
                        │
                        ▼
                your adapter/API
                        │
                        ▼
                  frontend
```

---

# 62. v2 vs v3 — the distinction you should memorize

This is the most important versioning point in this module.

## v2 stream

```python
agent.astream(
    ...,
    version="v2",
)
```

You receive:

```python
StreamPart
```

with:

```python
type
ns
data
```

You manually dispatch based on:

```python
part["type"]
```

This is **stable and practical for normal graph streaming**.

---

## v3 event stream

```python
await agent.astream_events(
    ...,
    version="v3",
)
```

You get:

```python
AsyncGraphRunStream
```

with projections such as:

```python
run.messages
run.values
run.updates
run.subgraphs
run.output
```

This is more ergonomic and higher-level, but currently **experimental/beta**. ([LangChain Reference Docs][12])

---

# 63. Is v3 replacing v2?

Not completely.

This is an important correction to a common interpretation.

### Don't think:

```text
v2 = obsolete
v3 = replacement
```

Think:

```text
v2 = typed stream-part protocol
v3 = higher-level typed streaming projections
```

And currently:

```text
v3 = beta/experimental
```

The official references explicitly mark v3 experimental/beta. ([LangChain Reference Docs][12])

So for production code today, I would design your code so the internal adapter can support both.

---

# 64. What about `astream_events` v1/v2?

For generic `Runnable` pipelines, v1/v2 still matter.

The current Runnable API says:

```text
v1/v2 → StreamEvent dictionaries
v3 → only subclasses implementing the v3 protocol
```

Current v3 support includes:

```text
BaseChatModel
CompiledGraph
```

rather than every arbitrary Runnable. ([LangChain Reference Docs][2])

So don't write:

```text
"I'm never going to use v2 events again."
```

That would be premature.

---

# 65. Old vs current style

Here is the practical migration table.

| Older style                                            | Current direction                                       |
| ------------------------------------------------------ | ------------------------------------------------------- |
| manually parse v1 event dictionaries                   | prefer typed v2 `StreamPart` when using `stream()`      |
| `astream_events(version="v1")` for new code            | avoid for new designs                                   |
| `message.text()`                                       | `message.text`                                          |
| manually reconstruct graph state from low-level events | use `values` projection                                 |
| manually identify model token events                   | use `messages` / `run.messages`                         |
| manually merge nested agent events                     | use v3 namespace/subgraph projections where appropriate |
| frontend consumes raw LangGraph events                 | map to your own domain event schema                     |
| assume only text is streamed                           | handle standardized content blocks                      |

The `.text()` change is explicitly deprecated in current LangChain Core. ([LangChain Reference Docs][6])

---

# 66. Do not confuse `stream_events(v3)` with OpenTelemetry

They solve different problems.

For example:

```text
LangGraph streaming
```

is primarily about:

```text
live execution output
```

while:

```text
Langfuse
```

is about:

```text
tracing
observability
latency
cost
runs
spans
evaluation
```

Your architecture should eventually look approximately like:

```text
                 Agent execution
                       │
              ┌────────┴─────────┐
              │                  │
          streaming           tracing
              │                  │
        frontend/API          Langfuse
```

Don't use the streaming layer as a replacement for tracing.

---

# 67. Streaming and Langfuse

Conceptually:

```text
Agent
 │
 ├── stream → user
 │
 └── trace → Langfuse
```

The user needs:

```text
text delta
tool status
progress
```

Your observability system needs:

```text
run
trace
span
model
tool
latency
tokens
error
cost
```

They are related, but different.

---

# 68. Production FastAPI architecture

For your current backend, I would eventually structure this approximately as:

```text
FastAPI
   │
   ▼
Agent service
   │
   ▼
create_agent()
   │
   ▼
LangGraph stream
   │
   ▼
stream adapter
   │
   ├── text_delta
   ├── tool_started
   ├── tool_finished
   ├── state_update
   ├── progress
   ├── error
   └── done
   │
   ▼
SSE / WebSocket
   │
   ▼
Frontend
```

---

# 69. Your own event protocol

I'd strongly recommend something like:

```python
from typing import Any, Literal
from pydantic import BaseModel


class AgentStreamEvent(BaseModel):
    type: Literal[
        "text_delta",
        "tool_started",
        "tool_finished",
        "progress",
        "state_update",
        "error",
        "done",
    ]

    run_id: str
    sequence: int
    payload: dict[str, Any]
```

Now your frontend doesn't care whether the internal implementation is:

```text
LangChain
LangGraph
Deep Agents
Gemini
OpenAI
Anthropic
local model
MCP
```

That matches your vendor-independent architecture extremely well.

---

# 70. One important security consideration

Never blindly forward every LangGraph event to the frontend.

For example, internal metadata may contain information that is only appropriate for:

```text
internal logs
tracing
security
debugging
```

rather than:

```text
end-user UI
```

So your adapter should perform:

```text
LangGraph stream
      ↓
filter
      ↓
redact
      ↓
normalize
      ↓
authorize
      ↓
frontend stream
```

This becomes especially important in your enterprise harness where different employees/tenants may have different permissions.

---

# 71. Streaming is also an authorization problem

Imagine:

```text
Agent
 ├── HR database
 ├── Salesforce
 └── ServiceNow
```

A user may be allowed to see:

```text
"Searching Salesforce..."
```

but not:

```text
raw Salesforce query
```

or:

```text
internal tool arguments
```

Therefore don't automatically serialize:

```python
part
```

directly to a browser.

Instead:

```text
LangGraph internal event
       ↓
authorization/redaction
       ↓
public event
```

---

# 72. Tool call streaming deserves special care

A model may emit a tool call like:

```text
name = search_salesforce
args = {
    "account_id": ...
}
```

Those arguments might contain sensitive data.

The UI might only need:

```json
{
    "type": "tool_started",
    "payload": {
        "tool": "search_salesforce"
    }
}
```

rather than:

```json
{
    "type": "tool_started",
    "payload": {
        "tool": "search_salesforce",
        "args": {
            "account_id": "..."
        }
    }
}
```

Streaming therefore intersects directly with the tool-security concepts you learned in Phase 5.

---

# 73. Streaming + MCP

This is particularly important for you.

You learned MCP in Phase 5.

Imagine:

```text
Agent
 ↓
MCP tool
 ↓
ServiceNow
```

Your user might want:

```text
"Searching ServiceNow..."
```

while the actual event flow is:

```text
agent
 ↓
tool call
 ↓
MCP client
 ↓
MCP server
 ↓
ServiceNow
 ↓
result
 ↓
agent
```

Streaming becomes the bridge between this complex internal execution and the user's real-time experience.

---

# 74. Deep Agents will make this more important

As you move into Deep Agents, you'll encounter more complex execution:

```text
supervisor
    ↓
subagent
    ↓
tool
    ↓
subagent
    ↓
tool
    ↓
final synthesis
```

At that point, plain:

```python
print(token)
```

is no longer enough.

You need:

```text
namespace
run
agent
subgraph
node
tool
message
state
```

That is precisely why the newer projection-oriented streaming model is valuable.

---

# 75. v3 projection architecture

A useful picture is:

```text
                   GraphRunStream
                        │
          ┌─────────────┼─────────────┐
          │             │             │
       messages       values       updates
          │             │             │
          ▼             ▼             ▼
   ChatModelStream    state       node deltas
          │
   ┌──────┼────────┐
   │      │        │
 text reasoning tool_calls
```

This is much easier to reason about than:

```text
on_chain_start
on_chain_stream
on_chain_end
on_chat_model_start
on_chat_model_stream
...
```

---

# 76. A practical v2 streaming helper

For learning, I recommend writing a small adapter like this:

```python
from collections.abc import Iterator
from typing import Any


def stream_text(agent, inputs: dict[str, Any]) -> Iterator[str]:
    for part in agent.stream(
        inputs,
        stream_mode="messages",
        version="v2",
    ):
        if part["type"] != "messages":
            continue

        message, _metadata = part["data"]

        if message.text:
            yield message.text
```

Then:

```python
for text in stream_text(agent, inputs):
    print(text, end="", flush=True)
```

You have now separated:

```text
LangGraph implementation
```

from:

```text
your application logic
```

---

# 77. A better production adapter

Eventually:

```python
from collections.abc import AsyncIterator
from typing import Any


async def stream_agent_events(
    agent,
    inputs: dict[str, Any],
) -> AsyncIterator[dict[str, Any]]:

    async for part in agent.astream(
        inputs,
        stream_mode=["messages", "updates"],
        version="v2",
    ):
        event_type = part["type"]

        if event_type == "messages":
            message, metadata = part["data"]

            if message.text:
                yield {
                    "type": "text_delta",
                    "payload": {
                        "text": message.text,
                        "metadata": metadata,
                    },
                }

        elif event_type == "updates":
            yield {
                "type": "state_update",
                "payload": part["data"],
            }
```

Then your FastAPI layer can consume:

```python
async for event in stream_agent_events(agent, inputs):
    ...
```

This is exactly the abstraction boundary I'd recommend learning to build.

---

# 78. Why `v2` is excellent for learning

I actually recommend you learn v2 **before** relying heavily on v3.

Why?

Because v2 teaches you the fundamentals:

```text
type
ns
data
```

and forces you to understand:

```text
state
updates
messages
custom
```

Once you understand that, v3 becomes much easier.

Otherwise, v3 can feel like magic:

```python
run.messages
```

without understanding what is happening underneath.

---

# 79. Then learn v3 as the higher-level abstraction

Your learning progression should therefore be:

```text
1. stream()
       ↓
2. stream_mode
       ↓
3. values / updates / messages
       ↓
4. version=v2
       ↓
5. StreamPart
       ↓
6. metadata / ns
       ↓
7. stream_events
       ↓
8. v1/v2 event model
       ↓
9. stream_events v3
       ↓
10. projections
       ↓
11. transformers
       ↓
12. your own event protocol
```

That progression gives you both conceptual understanding and practical skill.

---

# 80. Current recommendation for you

For your current Phase 6 work, I'd use:

### Learning/basic agent streaming

```python
agent.stream(
    ...,
    stream_mode="messages",
    version="v2",
)
```

### Learning state transitions

```python
agent.stream(
    ...,
    stream_mode="updates",
    version="v2",
)
```

### Learning complete state

```python
agent.stream(
    ...,
    stream_mode="values",
    version="v2",
)
```

### Learning multiple streams

```python
agent.stream(
    ...,
    stream_mode=["messages", "updates"],
    version="v2",
)
```

### Learning the new projection model

```python
agent.stream_events(
    ...,
    version="v3",
)
```

but treat v3 as **experimental/beta** rather than assuming it has already completely replaced v2. ([LangChain Reference Docs][12])

---

# 81. What I would NOT teach you as "modern"

I would not build new code around:

```python
message.text()
```

because current LangChain prefers:

```python
message.text
```

and the method form is deprecated. ([LangChain Reference Docs][6])

I would also not teach you to start new projects with:

```python
astream_events(version="v1")
```

as your primary architecture.

The current v1/v2 event dictionaries remain relevant, but v1 is legacy/backward-compatibility territory; v2 is the more relevant dictionary protocol, while v3 is the new projection-oriented beta API for supported graph/model types. ([LangChain Reference Docs][11])

---

# 82. One more important current change: standardized content blocks

Modern LangChain has increasingly moved toward standardized content blocks.

Instead of assuming:

```python
content == "string"
```

you should be prepared for:

```python
message.content_blocks
```

containing typed blocks such as:

```text
text
reasoning
tool_call
image
...
```

The current message system explicitly provides standardized provider-independent content blocks. ([LangChain Reference Docs][10])

This is particularly important because you want provider independence.

---

# 83. Gemini-specific note

Your preference for Gemini fits this learning module well.

The current `langchain-google-genai` integration provides `ChatGoogleGenerativeAI`, and version 4.x uses the consolidated Google GenAI SDK, supporting both the Gemini Developer API and Vertex AI. ([LangChain Reference Docs][7])

So your architecture can remain:

```text
LangChain
   ↓
ChatGoogleGenerativeAI
   ↓
Gemini
```

rather than directly coupling your application to Google's SDK everywhere.

---

# 84. The most important concepts to memorize

You should be able to explain these without looking them up:

### `stream_mode="values"`

```text
complete state snapshots
```

### `stream_mode="updates"`

```text
node/task updates
```

### `stream_mode="messages"`

```text
LLM message chunks + metadata
```

### `version="v2"`

```text
typed StreamPart envelope
```

with:

```python
type
ns
data
```

### `stream_events(version="v3")`

```text
projection-oriented event streaming
```

### `run.messages`

```text
LLM streams
```

### `run.values`

```text
state snapshots
```

### `run.updates`

```text
node/task updates
```

### `run.output`

```text
final state
```

### `ns`

```text
graph/subgraph namespace
```

### `ChatModelStream`

```text
one LLM response stream
```

with:

```text
text
reasoning
tool_calls
output
```

---

# 85. The deepest mental model

Don't think:

> "Streaming means printing tokens."

That is too shallow.

Think:

> **Streaming is exposing the execution of an agent incrementally.**

There are multiple dimensions of that execution:

```text
              AGENT EXECUTION
                     │
       ┌─────────────┼──────────────┐
       │             │              │
      state       execution         LLM
       │             │              │
    values        updates        messages
       │             │              │
       └─────────────┼──────────────┘
                     │
                 custom data
                     │
                     ▼
                  stream
```

And v3 adds:

```text
                   stream
                     │
              GraphRunStream
                     │
        ┌────────────┼────────────┐
        │            │            │
     messages      values      updates
        │
  ChatModelStream
        │
 ┌──────┼────────┐
text reasoning tools
```

That is the conceptual foundation you want before moving further into LangGraph.

---

# 86. Recommended progression for your next hands-on exercises

Do these in order.

### Exercise 1

Run:

```python
agent.stream(
    inputs,
    stream_mode="values",
    version="v2",
)
```

and print every part.

Understand exactly what changes.

### Exercise 2

Change to:

```python
stream_mode="updates"
```

Understand the difference.

### Exercise 3

Change to:

```python
stream_mode="messages"
```

Print:

```python
message
metadata
```

### Exercise 4

Use:

```python
stream_mode=["messages", "updates"]
```

and dispatch using:

```python
part["type"]
```

### Exercise 5

Add a tool.

Observe:

```text
model
tool
model
```

### Exercise 6

Use:

```python
agent.stream_events(
    inputs,
    version="v3",
)
```

and inspect:

```python
run.messages
run.values
run.updates
run.output
```

### Exercise 7

Build your own:

```text
AgentStreamEvent
```

adapter.

That final exercise is especially valuable for the enterprise harness you're building.

---

# 87. Your "current vs old" cheat sheet

```text
OLD / LEGACY                              CURRENT

message.text()                    →      message.text

raw v1 event parsing              →      v2 StreamPart for graph.stream()

guessing chunk type               →      part["type"]

tuple-only messages handling      →      typed v2 message StreamPart

manual state reconstruction       →      values

manual node update reconstruction →      updates

manual model-token parsing        →      messages

raw event parsing for everything   →      projections when v3 fits

frontend ← raw LangGraph events   →      backend adapter → stable API

one giant text assumption          →      standardized content blocks
```

The `message.text()` deprecation is explicit in current LangChain Core, while v2 `StreamPart` and v3 projections are documented current streaming surfaces. ([LangChain Reference Docs][6])

---

# 88. The architecture I recommend you eventually build

Given your Python/FastAPI/LangChain/LangGraph/Langfuse/MCP/Deep Agents direction, I would aim toward:

```text
                         FastAPI
                            │
                            ▼
                    Agent Application
                            │
                            ▼
                      create_agent()
                            │
              ┌─────────────┴─────────────┐
              │                           │
         LangGraph execution           Langfuse
              │                           │
              │                        tracing
              │
       ┌──────┴─────────┐
       │                 │
     v2 stream         v3 stream
       │                 │
       └────────┬────────┘
                ▼
        Streaming Adapter
                │
        ┌───────┴─────────┐
        │                 │
  authorization       normalization
        │                 │
        └────────┬────────┘
                 ▼
        Enterprise Event Schema
                 │
        ┌────────┴────────┐
        │                 │
       SSE            WebSocket
        │                 │
        └────────┬────────┘
                 ▼
              Frontend
```

That separation will serve you much better than exposing LangGraph's internal structures directly to the UI.

---

## Final takeaway

The single most important distinction for Module 43 is:

```text
stream_mode
    ↓
WHAT are you streaming?

version
    ↓
HOW is the stream represented?

v2 StreamPart
    ↓
WHAT typed chunk did I receive?

stream_events(v3)
    ↓
Give me a higher-level execution stream

projections
    ↓
Which view of that execution do I want?
```

So your core mental model should now be:

```text
                    AGENT
                      │
                ┌─────┴─────┐
                │           │
             state         LLM
                │           │
           ┌────┴────┐      │
           │         │      │
        values    updates messages
                              │
                        ChatModelStream
                              │
                    ┌─────────┼─────────┐
                    │         │         │
                   text    reasoning tool_calls
```

And **v2 and v3 are not competitors**:

```text
v2
→ typed low-level stream parts

v3
→ higher-level typed projections
```

with v3 currently still beta/experimental in Python. ([LangChain Reference Docs][12])

### Sources

The main references I used are the current official LangChain/LangGraph API references: `create_agent`, LangGraph streaming/`StreamMode`, v2 `StreamPart` types, v3 `GraphRunStream`/transformers, `ChatModelStream`, and the current Gemini integration. ([LangChain Reference Docs][1])

[1]: https://reference.langchain.com/python/langchain/agents/factory/create_agent?utm_source=chatgpt.com "create_agent | langchain | LangChain Reference"
[2]: https://reference.langchain.com/python/langchain-core/runnables/base/Runnable/stream_events?utm_source=chatgpt.com "stream_events | langchain_core | LangChain Reference"
[3]: https://reference.langchain.com/python/langgraph/types/StreamMode?utm_source=chatgpt.com "StreamMode | langgraph | LangChain Reference"
[4]: https://reference.langchain.com/python/langgraph/types/MessagesStreamPart?utm_source=chatgpt.com "MessagesStreamPart | langgraph | LangChain Reference"
[5]: https://reference.langchain.com/python/langchain-core/messages/ai/AIMessageChunk?utm_source=chatgpt.com "AIMessageChunk | langchain_core | LangChain Reference"
[6]: https://reference.langchain.com/python/langchain-core/messages/base/BaseMessage/text?utm_source=chatgpt.com "text | langchain_core | LangChain Reference"
[7]: https://reference.langchain.com/python/langchain-google-genai/chat_models/ChatGoogleGenerativeAI?utm_source=chatgpt.com "ChatGoogleGenerativeAI | langchain_google_genai | LangChain Reference"
[8]: https://reference.langchain.com/python/langgraph/pregel/protocol?utm_source=chatgpt.com "protocol | langgraph | LangChain Reference"
[9]: https://reference.langchain.com/python/langgraph/pregel/main/Pregel/stream?utm_source=chatgpt.com "stream | langgraph | LangChain Reference"
[10]: https://reference.langchain.com/python/langchain-core/messages/ai?utm_source=chatgpt.com "ai | langchain_core | LangChain Reference"
[11]: https://reference.langchain.com/python/langchain-core/runnables/base/Runnable/astream_events?utm_source=chatgpt.com "astream_events | langchain_core | LangChain Reference"
[12]: https://reference.langchain.com/python/langgraph/pregel/main/Pregel/stream_events?utm_source=chatgpt.com "stream_events | langgraph | LangChain Reference"
[13]: https://reference.langchain.com/python/langgraph/stream/transformers/MessagesTransformer?utm_source=chatgpt.com "MessagesTransformer | langgraph | LangChain Reference"
[14]: https://reference.langchain.com/python/langchain-core/language_models/chat_model_stream/ChatModelStream?utm_source=chatgpt.com "ChatModelStream | langchain_core | LangChain Reference"
[15]: https://reference.langchain.com/python/langgraph/stream/transformers/ValuesTransformer?utm_source=chatgpt.com "ValuesTransformer | langgraph | LangChain Reference"
[16]: https://reference.langchain.com/python/langgraph/stream/transformers?utm_source=chatgpt.com "transformers | langgraph | LangChain Reference"
[17]: https://reference.langchain.com/python/langgraph/stream/run_stream/GraphRunStream?utm_source=chatgpt.com "GraphRunStream | langgraph | LangChain Reference"
[18]: https://reference.langchain.com/python/langgraph/pregel/main/Pregel/astream_events?utm_source=chatgpt.com "astream_events | langgraph | LangChain Reference"
[19]: https://reference.langchain.com/python/langgraph/stream/_types/ProtocolEvent?utm_source=chatgpt.com "ProtocolEvent | langgraph | LangChain Reference"
[20]: https://reference.langchain.com/python/langgraph/stream/_types/StreamTransformer?utm_source=chatgpt.com "StreamTransformer | langgraph | LangChain Reference"
