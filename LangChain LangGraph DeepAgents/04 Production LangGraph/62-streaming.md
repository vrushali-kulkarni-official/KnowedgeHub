# M62 — Streaming deep dive

**Time: 2.5 hours.** The goal of this module is not "know the stream modes".
It is: **ship a streaming API whose frontend never has to know that LangGraph
exists.**

---

## 1. The problem with "just stream it"

The naive production streaming endpoint is:

```python
@app.post("/chat")
async def chat(req: ChatRequest):
    async def gen():
        async for chunk in graph.astream(req.payload, stream_mode="messages"):
            yield f"data: {chunk[0].content}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")
```

It works. It is also wrong in five ways, and each wrongness becomes a
production incident:

| #   | Problem                   | Consequence                                                                                                                 |
| --- | ------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| 1   | Only tokens are forwarded | The frontend cannot show "calling tool X", cannot render an approval prompt, cannot distinguish *thinking* from *answering* |
| 2   | No sequence numbers       | A dropped connection loses events forever; the client cannot resume                                                         |
| 3   | No terminal event         | The client does not know when to stop listening, or whether the run finished or is waiting for a human                      |
| 4   | Raw LangGraph shape leaks | When LangGraph 1.1 changed the multi-mode output format, your frontend broke                                                |
| 5   | No error event            | A mid-stream failure hangs the client forever                                                                               |

M62 fixes all five by introducing **one thing**: a *contract*.

---

## 2. The shape of the answer

```
LangGraph internals          YOUR TRANSLATOR            YOUR CONTRACT
─────────────────────        ──────────────            ─────────────
StreamPart {type,ns,data} ──▶ StreamTranslator ──▶ SSEEvent {event,seq,…}
messages / updates / custom                                 │
v3 protocol events                                           ▼
                                                     sse_frame()  ──▶ browser
```

Two rules:

1. **Nothing from LangGraph reaches the client unchanged.** The translator is
   a hard boundary.
2. **The contract is a closed set.** A frontend can `switch` on it; TypeScript
   can derive a union type from it.

In this course that translator lives in `src/p9/sse.py` and the contract is
declared as data, so it can be published and tested:

```python
EVENT_SPECS: dict[EventType, EventSpec] = {
    "status":           EventSpec("status",           "Coarse lifecycle signal.", ("phase",)),
    "token":            EventSpec("token",            "Append-only assistant text.", ("text",), incremental=True),
    "thought":          EventSpec("thought",          "Model reasoning deltas.", ("text",), incremental=True),
    "tool_call":        EventSpec("tool_call",        "The model decided to call a tool.", ("tool_name", "call_id")),
    "tool_result":      EventSpec("tool_result",      "A tool finished.", ("tool_name", "call_id")),
    "artifact":         EventSpec("artifact",         "A durable output worth persisting.", ("name", "mime_type")),
    "approval_request": EventSpec("approval_request", "The graph is paused and needs an answer.", ("interrupt_id", "question")),
    "error":            EventSpec("error",            "Something failed.", ("message",)),
    "done":             EventSpec("done",             "Terminal event. Always last.", ("status",)),
}
```

`contract_as_json()` prints it. A frontend team can generate types from it.
`validate_event()` enforces it. `test_sse_contract.py` tests it.

---

## 3. The stream modes — the full list

`graph.stream()` / `graph.astream()` accept `stream_mode` as a single mode or a
**list** of modes. The full set in LangGraph 1.2:

| Mode          | Payload shape (v2)          | What it is for                                   |
| ------------- | --------------------------- | ------------------------------------------------ |
| `values`      | full state dict             | Snapshots of state after each step. **Large.**   |
| `updates`     | `{node_name: state_delta}`  | What changed, per node. The bread and butter.    |
| `messages`    | `(message_chunk, metadata)` | LLM tokens + tool-call chunks + reasoning deltas |
| `custom`      | whatever you wrote          | Your own events, from inside nodes               |
| `checkpoints` | checkpoint envelope         | Branching, time travel                           |
| `tasks`       | task descriptors            | Pregel task creation/results (debugging)         |
| `debug`       | detailed step records       | Very verbose; debugging only                     |

Let me see each one for real.

### 3.1 Setup

```python
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.config import get_stream_writer

class State(TypedDict):
    topic: str
    joke: str

def generate_joke(state: State):
    writer = get_stream_writer()
    writer({"status": "thinking of a joke..."})
    return {"joke": f"Why did the {state['topic']} go to school? To get a sundae education!"}

graph = (
    StateGraph(State)
    .add_node(generate_joke)
    .add_edge(START, "generate_joke")
    .add_edge("generate_joke", END)
    .compile()
)
```

### 3.2 `custom` — your own channel

`get_stream_writer()` gives you a writer from *anywhere* inside the graph —
node, tool, or a helper five calls deep. It is the only way to push
application events.

```python
for chunk in graph.stream({"topic": "ice cream"}, stream_mode="custom", version="v2"):
    print(chunk)
# {'type': 'custom', 'ns': (), 'data': {'status': 'thinking of a joke...'}}
```

Two rules that people learn the hard way:

* **`custom` mode must be requested.** If you do not include `"custom"` in
  `stream_mode`, your custom events are simply never emitted. This is not an
  error; it is silence.
* **The writer is a no-op outside a graph run.** Calling
  `get_stream_writer()` outside a node raises. If you call a helper both
  inside and outside a graph, guard it.

### 3.3 `updates` — what changed

```python
for chunk in graph.stream({"topic": "ice cream"}, stream_mode="updates", version="v2"):
    print(chunk)
# {'type': 'updates', 'ns': (), 'data': {'generate_joke': {'joke': 'Why did the ice cream...'}}}
```

The payload is `{node_name: delta}`. This is the mode you use for step
assertions in tests (M64).

### 3.4 `values` — full snapshots

```python
for chunk in graph.stream({"topic": "ice cream"}, stream_mode="values", version="v2"):
    print(chunk["data"])
# {'topic': 'ice cream'}                       # before any node ran
# {'topic': 'ice cream', 'joke': 'Why did...'} # after
```

Warning: `values` is the **whole state, every step**. For a conversation with
50 messages, that is 50 snapshots of 50 messages. In production you almost
always want `updates` for the client and `values` only internally (to capture
the final state).

This course's worker does exactly that: it requests `values` to capture the
final state, then **filters them out** before writing to the event log.

### 3.5 `messages` — LLM tokens

The payload is a **tuple** `(message_chunk, metadata)`:

```python
for chunk in graph.stream({"topic": "x"}, stream_mode="messages", version="v2"):
    message_chunk, metadata = chunk["data"]
    print(message_chunk.content, end="", flush=True)
    print(metadata["langgraph_node"])
```

The `metadata` dict is where the useful bits live:

| Key                  | Meaning                                                           |
| -------------------- | ----------------------------------------------------------------- |
| `langgraph_node`     | Which node produced this                                          |
| `langgraph_step`     | Which superstep                                                   |
| `langgraph_triggers` | What triggered the node                                           |
| `langgraph_path`     | Path through the graph                                            |
| `tags`               | Tags passed to the model (`model.bind_tools(..., tags=["joke"])`) |
| `ls_model_name`      | Which model                                                       |

The `tags` trick is genuinely useful: it lets you filter tokens by *which
logical call* produced them when a node makes several model calls.

**The subtlety that will bite you:** the `messages` channel carries *both*
streamed token chunks (`AIMessageChunk`) **and whole messages** that a node
returned (`AIMessage`). A frontend that blindly appends every chunk
double-counts. Our translator flags this:

```python
is_chunk = isinstance(chunk, AIMessageChunk)
self.emit("token", 
        {"text": content, 
         "node": node, 
         "complete": not is_chunk})
```

So the frontend can `append` when `complete` is false and `replace` when it
is true.

### 3.6 `checkpoints`, `tasks`, `debug`

* `checkpoints` — a lightweight envelope per checkpoint. Useful for
  implementing "rewind to step N" in the UI.
* `tasks` — Pregel task lifecycle. Very useful for a "what is it doing right
  now?" debug panel.
* `debug` — the most verbose mode: detailed step records including
  channel writes. Use it when you are stuck; never ship it to a client.

---

## 4. The output format: v1 vs v2 (**important**)

This is the part where most tutorials go stale.

### v1 (still the default, now legacy)

The shape **changes depending on your options**:

```python
# single mode → raw data
graph.stream(inputs, stream_mode="updates")
# {'node': {'key': 'value'}}

# multiple modes → (mode, data) tuples
graph.stream(inputs, stream_mode=["updates", "custom"])
# ('custom', {...})
# ('updates', {'node': {...}})

# subgraphs → (namespace, data) tuples
graph.stream(inputs, stream_mode="updates", subgraphs=True)
# (('research:abc123',), {'research_node': {...}})
```

Your code has to branch on "am I in single or multi mode?" and "am I in a
subgraph?" That is exactly the kind of shape-dependence that breaks when
LangGraph changes a default.

### v2 (LangGraph ≥ 1.1) — the modern format

```python
graph.stream(inputs, stream_mode=["updates", "custom"], version="v2")
```

Every chunk is the **same shape**, always:

```python
{
    "type": "values" | "updates" | "messages" | "custom" | "checkpoints" | "tasks" | "debug",
    "ns": (),     # namespace tuple, populated for subgraph events
    "data": ...,  # the payload (varies by mode)
}
```

Verified output from our own lab:

```
{'type': 'custom',  'ns': (), 'data': {'status': 'thinking of a joke...'}}
{'type': 'updates', 'ns': (), 'data': {'generate_joke': {'joke': 'Why did the ice cream...'}}}
```

and with a subgraph:

```
{'type': 'custom', 'ns': ('research:ea3493d5-58d4-64d9-bf3d-e8c583a62c6d',),
 'data': {'type': 'status', 'phase': 'researching', 'topic': 'ingest backlog'}}
```

**Why this matters:** your branching logic becomes `chunk["type"]`, full stop.
No mode-count checks, no namespace-shape checks. And LangGraph ships typed
dicts for it (`ValuesStreamPart`, `UpdatesStreamPart`, `MessagesStreamPart`,
`CustomStreamPart`, `CheckpointStreamPart`, `TasksStreamPart`, `DebugStreamPart`,
and the union `StreamPart`), so a type checker can narrow on
`part["type"]`.

> **Modern style:** always pass `version="v2"` for new code. Keep v1 only if
> you are migrating an existing codebase and cannot change it yet.

---

## 5. Subgraphs and namespaces

When a node is itself a compiled graph, its output is namespaced:

```
ns = ()                                        # root graph
ns = ('research:ea3493d5-58d4-...',)            # inside the research subgraph
```

The format is `"<node_name>:<runtime_id>"` — the **name** is stable, the
runtime id changes per invocation. So:

* **Do** match on the name (`ns[0].split(":")[0]`).
* **Do not** match on the whole tuple.

You need `subgraphs=True` to see them at all:

```python
graph.stream(inputs, stream_mode="custom", version="v2", subgraphs=True)   # sees the subgraph
graph.stream(inputs, stream_mode="custom", version="v2", subgraphs=False)  # does not
```

Our translator turns the namespace into a friendly node name:

```python
def _node_from_ns(ns: tuple[str, ...]) -> str | None:
    if not ns:
        return None
    last = ns[-1]
    return last.split(":", 1)[0] if ":" in last else last
```

For Deep Agents, the subagent appears as its own namespace too — that is how
you label it in the UI ("the researcher said…").

---

## 6. The new v3 event protocol (beta)

LangGraph 1.2 introduced `stream_events(version="v3")`, a **typed-projection**
API. It is the shape the docs now recommend for new applications.

> ⚠️ **It is still experimental.** Calling it emits:
> `LangChainBetaWarning: The v3 streaming protocol on Pregel is experimental.`
>
> Treat it as the path to watch, not the path to bet the product on.

### What it gives you

```python
stream = graph.stream_events({"messages": [...]}, version="v3")

stream.messages      # chat model messages and token deltas
stream.values        # state snapshots; await the final value
stream.output        # await the final output
stream.subgraphs     # nested graph executions
stream.interrupts    # human-in-the-loop payloads
stream.interrupted   # did the run pause?
stream.extensions    # your own custom projections
```

Multiple consumers can read these **concurrently** — reading `stream.messages`
does not consume events needed by `stream.values`:

```python
import asyncio

stream = await graph.astream_events(input, version="v3")

async def consume_messages():
    async for message in stream.messages:
        print(f"[llm] node={message.node}")

async def consume_subgraphs():
    async for subgraph in stream.subgraphs:
        print(f"[subgraph] path={subgraph.path}")

await asyncio.gather(consume_messages(), consume_subgraphs())
```

In synchronous code, `stream.interleave(...)` consumes several projections in
strict arrival order:

```python
for name, item in stream.interleave("values", "messages", "subgraphs"):
    ...
```

### The v3 channel model

Under the hood, v3 normalises everything into **protocol events** with a
`method` (the channel name) and a `params` payload:

```python
class ProtocolEvent(TypedDict):
    seq: int
    method: str     # "messages", "values", "updates", "custom", "tools", "lifecycle", ...
    params: ProtocolEventParams

class ProtocolEventParams(TypedDict):
    namespace: list[str]   # path from the root; [] is the root
    timestamp: int         # wall-clock ms - can drift, do NOT rely on it for ordering
    data: Any
```

The channels are `values`, `updates`, `messages`, `tools`, `lifecycle`,
`checkpoints`, `input`, `tasks`, `custom`, and `custom:<name>`.

### Resuming an interrupt with v3

```python
stream = graph.stream_events(input, version="v3")

for message in stream.messages:
    print(message.text)

if stream.interrupted:
    print(stream.interrupts)

stream = graph.stream_events(
    Command(resume={"decisions": [{"type": "approve"}]}),
    version="v3",
)
final_state = stream.output
```

### The v2/v3 equivalence — the important part for you

**Both dialects must produce the same contract.** That is the whole point of
having a translator. Here is the proof from our own code — the v2 path:

```python
def _translate_message(self, data, ns):
    chunk, metadata = data
    node = metadata.get("langgraph_node") or _node_from_ns(ns)
    ...
    self.emit("token", {"text": content, "node": node, "complete": not is_chunk})
```

and the v3 path:

```python
def translate_v3_message(self, message):
    node = getattr(message, "node", None)
    text = getattr(message, "text", None)
    if text:
        events.append(self.emit("token", {"text": str(text), "node": node}))
    ...
```

**Same events, different internals.** When v3 graduates from beta, you change
one function in `sse.py`. Your frontend does not change. That is the payoff of
the contract-first design.

---

## 7. Building the contract: the eight event types

Let me justify each one, because a contract is only as good as its reasons.

### `status` — the workhorse

Lifecycle noise that the frontend may show or ignore. It exists so that a
client is never silent for more than a few seconds.

```json
{"event": "status", "seq": 12, "data": {"phase": "researching", "progress": 1, "total": 2}}
```

### `token` — append-only assistant text

```json
{"event": "token", "seq": 13, "data": {"text": "Restart ", "node": "route", "complete": false}}
```

`complete: true` means "this is the whole message, replace rather than append".

### `thought` — reasoning deltas

Gemini's thinking models, OpenAI's reasoning models — the reasoning text is
usually *not* meant for the user. But it is invaluable for debugging and for
"show my work" UIs. Keep it separate from `token` so the frontend can render
it collapsed, or filter it out.

### `tool_call` — the model decided to call a tool

```json
{"event": "tool_call", "seq": 8, "data": {"tool_name": "lookup_docs", "call_id": "call-1", "args": {...}}}
```

The `call_id` is what lets you match a result back to its call. Both
`tool_call` and `tool_result` carry it.

### `tool_result` — a tool finished

```json
{"event": "tool_result", "seq": 27, "data": {"tool_name": "lookup_docs", "call_id": "call-1", "result": "..."}}
```

### `artifact` — a durable output

Some outputs are worth *storing*, not just displaying: a generated report, a
file, a SQL query the user might want to run later.

```json
{"event": "artifact", "seq": 3, "data": {"name": "answer.md", "mime_type": "text/markdown", "content": "..."}}
```

The backend persists it; the frontend renders a download link.

### `approval_request` — human-in-the-loop

This is the event that makes HITL work over a network.

```json
{"event": "approval_request", "seq": 30,
 "data": {"interrupt_id": "c5c2b6d73a721521012de87e3418c542",
          "question": "Publish the answer about ingest backlog?",
          "options": ["approve", "reject"]}}
```

The frontend renders buttons; the click POSTs the answer to your resume
endpoint; the graph continues.

### `error` and `done` — the terminal pair

```json
{"event": "error", "seq": 40, "data": {"message": "ConnectionResetError: ..."}}
{"event": "done",  "seq": 41, "data": {"status": "completed"}}
```

`done.status` is one of `completed`, `paused`, `failed`, `cancelled`.

> ### The single most common streaming bug
>
> **Reporting `done` with status `completed` when the graph actually paused.**
>
> The client sees `done`, stops listening, and the human's answer arrives
> into a closed connection. The run then sits in `paused` forever.
>
> Our translator gets this right automatically:
>
> ```python
> def final_status_for(parts):
>     status = "completed"
>     for part in parts:
>         if part.get("type") == "updates":
>             data = part.get("data") or {}
>             if isinstance(data, dict) and "__interrupt__" in data:
>                 status = "paused"
>     return status
> ```
>
> Verified output from the lab: `done {"status": "paused"}`.

---

## 8. The wire format

SSE frames are trivial but the details matter:

```
event: token
id: 13
data: {
       "event":"token",
       "seq":13,
       "run_id":"run-1",
       "thread_id":"th-1",
       "ts":"2026-11-04T10:18:37.107198+00:00",
       "data":{"text":"Restart",
               "node":"route",
               "complete":false
               }
      }
```

* `event:` — the browser's `EventSource` dispatches on this.
* `id:` — the resume cursor. `EventSource` sends it back as
  `Last-Event-ID` on reconnect.
* `data:` — one JSON object.
* **A blank line terminates the frame.** Forget it and the client hangs.

Our serializer:

```python
def sse_frame(event: SSEEvent) -> str:
    payload = json.dumps(event, separators=(",", ":"), default=str)
    return f"event: {event['event']}\nid: {event['seq']}\ndata: {payload}\n\n"
```

Note `default=str`: a tool result may contain a non-JSON-serialisable object,
and a 500 error in your serializer is a 500 for the whole stream.

### The envelope

```python
class SSEEvent(TypedDict, total=False):
    event: EventType
    seq: int
    run_id: str
    thread_id: str
    ts: str
    data: dict[str, Any]
```

* `seq` — **monotonic, gap-free, per run.** This is what makes
  `?after_seq=N` resume work.
* `run_id` — ties every event to a run. Essential when several runs share a
  connection.
* `thread_id` — ties it to a conversation.
* `ts` — ISO-8601 UTC. Informational only: **never order by it** (clocks
  drift). Order by `seq`.

---

## 9. End-to-end: the lab

```bash
python scripts/demo_m62.py
```

Real output (abridged):

```
3. Translated into our SSE contract
  1  status           {"phase": "thinking"}
  2  status           {"phase": "researching", "topic": "ingest backlog"}
  3  status           {"phase": "researching", "progress": 1, "total": 2}
  6  token            {"text": "Restart ", "node": "route", "complete": false}
 ...
 27  tool_result      {"tool_name": "lookup_docs", "call_id": "call-lookup-1", "result": "3 internal docs..."}
 30  approval_request {"interrupt_id": "c5c2b6d...", "question": "Publish the answer about ingest backlog?"}
 31  done             {"status": "paused"}

5. Resuming the paused run (human-in-the-loop)
  1  status           {"phase": "resumed", "decision": "approve"}
  3  artifact         {"name": "answer-ingest backlog.md", "mime_type": "text/markdown", ...}
  5  done             {"status": "completed"}
```

And the raw frame:

```
'event: status\nid: 1\ndata: {"event":"status","seq":1,"run_id":"run-demo-1",...}\n\n'
```

---

## 10. Production checklist

Before you ship a streaming endpoint, confirm every line:

- [ ] `version="v2"` on `stream()`/`astream()` (or the v3 protocol, knowingly)
- [ ] A **translator layer** — no LangGraph types in your API response
- [ ] A **closed set** of event types, published to the frontend
- [ ] **Monotonic `seq`** on every event
- [ ] A **terminal `done`** event, with the *correct* status
- [ ] `approval_request` emitted on interrupts
- [ ] `error` emitted on failures, followed by `done`
- [ ] Events **persisted**, not just streamed — so a client can replay
- [ ] `subgraphs=True` if you have subgraphs, and namespace handling
- [ ] Reconnect support via `?after_seq=` / `Last-Event-ID`
- [ ] A heartbeat or keep-alive if a step can exceed your proxy's idle timeout
- [ ] `Cache-Control: no-cache` and `X-Accel-Buffering: no` on the response

---

## 11. Traps

| Trap                                  | Symptom                                 | Fix                              |
| ------------------------------------- | --------------------------------------- | -------------------------------- |
| Forgetting `stream_mode="custom"`     | Your custom events silently vanish      | Include `"custom"` in the list   |
| `get_stream_writer()` outside a graph | `RuntimeError`                          | Only call it inside a node/tool  |
| v1 multi-mode tuples                  | `ValueError: too many values to unpack` | `version="v2"`                   |
| Treating whole messages as tokens     | Duplicated text in the UI               | Check `complete`                 |
| Reporting `done` on a pause           | The run hangs in `paused` forever       | Use `final_status_for()`         |
| Matching on the full namespace        | Breaks when the runtime id changes      | Match the name before the `:`    |
| Serialising a non-JSON object         | The whole stream 500s                   | `default=str`                    |
| No `seq`                              | Cannot resume after a disconnect        | Always emit it                   |
| Assuming `EventSource` retries        | It does not; you must implement resume  | `?after_seq=` + persisted events |

---

## 12. Exercise

1. **Add an event type.** Add a `"warning"` event to `EVENT_SPECS`, emit it
   from a node with `writer({"type": "warning", ...})`, and add a test.
   (Note: `_translate_custom` fills in missing required fields, so you must
   decide what `warning` requires.)

2. **Break the contract on purpose.** Emit an event without `seq` and watch
   `validate_event` reject it. Then decide: should the translator be able to
   emit invalid events at all?

3. **Write the frontend.** In TypeScript, generate a union type from
   `contract_as_json()` and write the `switch` that consumes it. Then add a
   new event type on the backend and see how much the frontend has to change.
   (Answer: none. That is the point.)

4. **Measure.** Count the events your graph emits for one request. Then
   estimate the cost of storing them all (M63's `run_events` table does
   exactly this) at your request volume.

---

**Next: [M63 — Long-running graphs](63-long-running.md) →**
