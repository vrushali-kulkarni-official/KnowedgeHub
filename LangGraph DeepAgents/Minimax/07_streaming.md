# Module 07 — Streaming

## Prerequisites

- Module 04 (ReAct agent)
- Module 05 (persistence — needed for resumed streams)

## Why this module matters

Users don't want to wait 30 seconds for a complete answer. They want tokens as they come. They want to see tool calls happen. They want to interrupt if the agent is going off the rails. Streaming is the difference between a chatbot that *feels* alive and one that feels like a CLI.

This module covers all the streaming modes LangGraph gives you, and how to wire them into FastAPI SSE or WebSockets.

## Learning objectives

By the end of this module you can:

1. Use the five stream modes: `values`, `updates`, `messages`, `events`, `custom`.
2. Stream tokens from an LLM node.
3. Stream tool events.
4. Emit custom progress events from your own nodes.
5. Serve a stream from FastAPI using SSE.
6. Handle backpressure, cancellation, and resume from checkpoint.
7. Build a "thinking → tool → answer" UI flow.

---

## 7.1 The five stream modes

| Mode | What you get | When to use |
|---|---|---|
| `values` | Full state after each step | Simple "what's the state now?" |
| `updates` | The dict update from each node | Watch progress, drive UIs |
| `messages` | LLM token chunks + metadata | Live token streaming |
| `events` | Internal events (broad) | Deep observability, debugging |
| `custom` | Whatever you emit via `writer` | Custom progress, side-channel info |

You can combine them:

```python
async for event in g.astream(input, config, stream_mode=["updates", "messages"]):
    mode, data = event
    ...
```

---

## 7.2 `values` — the full state

```python
for state in g.stream(input, config, stream_mode="values"):
    print(state["messages"][-1])
```

Easiest mode. You get the state after every step. Verbose but predictable.

---

## 7.3 `updates` — per-node deltas

```python
for event in g.stream(input, config, stream_mode="updates"):
    # event = {"node_name": {...update...}}
    node, update = next(iter(event.items()))
    print(f"[{node}] {update}")
```

This is the workhorse for UIs. You can show "agent thinking," "running tool X," "agent answering."

---

## 7.4 `messages` — LLM token streaming

The most important mode for UX. You get each token as the model produces it.

```python
for msg, metadata in g.stream(input, config, stream_mode="messages"):
    # msg is a ChatGenerationChunk or similar
    if msg.content:
        print(msg.content, end="", flush=True)
```

In an async context:

```python
async for msg, metadata in g.astream(input, config, stream_mode="messages"):
    if msg.content:
        # yield token to the client
        ...
```

To make token streaming work, your LLM node must not buffer. `llm.invoke` returns the full message at once. For tokens, use `llm.stream` (or the framework handles it under the hood — LangGraph's `messages` mode does this automatically when bound to a streaming-capable chat model).

**Heads up:** some chat models don't stream; some require extra config. Test early.

---

## 7.5 `events` — deep internals

```python
async for event in g.astream_events(input, config, version="v2"):
    print(event["event"], event.get("name"), event.get("data"))
```

You get dozens of events: `on_chain_start`, `on_llm_stream`, `on_tool_start`, `on_tool_end`, etc. Great for debugging and observability. Don't use it for primary UX — too noisy.

---

## 7.6 `custom` — your own events

Inside a node:

```python
from langgraph.types import StreamWriter

def long_node(state: State, writer: StreamWriter):
    writer({"progress": "starting", "step": 1})
    ...
    writer({"progress": "halfway", "step": 2})
    ...
    writer({"progress": "done", "step": 3})
    return {"messages": [...]}
```

Consume:

```python
for event in g.stream(input, config, stream_mode="custom"):
    print(event)
```

Use this for progress reporting on long nodes, status updates, or passing side-channel data to the UI.

---

## 7.7 Streaming from FastAPI (SSE)

The cleanest pattern for a web client is Server-Sent Events:

```python
# app/main.py
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import json
from langchain_core.messages import HumanMessage
from app.graph.graph import make_graph
from app.config import settings

app = FastAPI()

@app.post("/chat/{thread_id}/stream")
async def chat_stream(thread_id: str, body: dict):
    config = {"configurable": {"thread_id": thread_id}}
    g = make_graph(app.state.checkpointer)

    async def event_gen():
        async for mode, data in g.astream(
            {"messages": [HumanMessage(content=body["message"])]},
            config,
            stream_mode=["messages", "updates"],
        ):
            if mode == "messages":
                token, meta = data
                if token.content:
                    yield f"event: token\ndata: {json.dumps({'t': token.content})}\n\n"
            elif mode == "updates":
                node, update = next(iter(data.items()))
                yield f"event: step\ndata: {json.dumps({'node': node, 'update': str(update)})}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")
```

Client side (browser JS, sketch):

```javascript
const es = new EventSource("/chat/abc/stream");
es.addEventListener("token", e => appendToChat(e.data));
es.addEventListener("step", e => showProgress(e.data));
es.addEventListener("done", e => es.close());
```

---

## 7.8 Streaming + persistence

Streams can be **resumed** thanks to the checkpointer. If the connection drops mid-stream, you can reconnect and replay from the last checkpoint.

For SSE specifically, this is harder than for WebSockets (SSE can't resume by spec). Workarounds:

- **Short streams**: don't worry about resumption; just regenerate.
- **Long streams**: use WebSockets with custom resume logic via `thread_id` + last-seen checkpoint id.

The LangGraph Platform (Module 09) handles this for you with `threads.stream`.

---

## 7.9 Cancellation

If the client disconnects, you want the graph to stop (especially expensive LLM calls).

```python
async def event_gen():
    try:
        async for ...:
            yield ...
    except asyncio.CancelledError:
        # FastAPI raises this when client disconnects
        # LangGraph will continue running unless you explicitly stop
        pass
```

To actively stop, you can store the running task in `app.state` and cancel it.

---

## 7.10 Backpressure and rate

If clients can't keep up, your event queue grows. Strategies:

- **Heartbeats:** yield `: keep-alive\n\n` periodically to keep the connection open.
- **Buffer size limits:** cap on the framework side.
- **Batching:** yield every N tokens instead of every token.
- **HTTP/2** if SSE is the bottleneck (most browsers support it now).

---

## 7.11 Stream mode cheatsheet

| Want | Mode |
|---|---|
| Show a token-by-token chat | `messages` |
| Show "agent is running tool X" | `updates` |
| Emit "75% done" on a long node | `custom` |
| Debug what's actually happening | `events` |
| "Just show me the latest state" | `values` |
| Combined UX (tokens + steps) | `["messages", "updates"]` |

---

## 7.12 Streaming gotchas

| Gotcha | Fix |
|---|---|
| Tokens don't appear | Check that the LLM supports streaming; try a different model |
| `messages` mode misses tool calls | Combine with `updates` to catch tool events |
| Custom events never arrive | Make sure your node signature includes `writer: StreamWriter` |
| SSE connection dies after 60s | Heartbeats, or use WebSockets |
| Stream gets slower with persistence | Profile; sometimes JSONB writes are the bottleneck |
| Two streams on same thread | Pick one — concurrent writes to a thread are not safe |

---

## Hands-on project

**Goal:** Build a real-time streaming chat endpoint with full observability.

1. Take your ReAct agent.
2. Add a FastAPI `/chat/{thread_id}/stream` endpoint that emits SSE.
3. Stream modes: `messages` for tokens, `updates` for step events, `custom` for a "thinking..." progress bar emitted by a slow mock node.
4. Add a heartbeat every 15 seconds.
5. Test: open in browser, send a message, watch tokens appear, see tool calls, see final answer.
6. Test: kill the server mid-stream, restart, reconnect — does the conversation still make sense?

## Exercises

1. **Token-level tool events:** when a tool is called, emit the tool name and args as a structured event. Show it in your UI mock.
2. **Cancellation:** write a `/chat/{thread_id}/stop` endpoint that cancels the running task. Verify the graph actually stops (use a mock LLM that sleeps).
3. **Backpressure:** write a slow client (Python script) that reads SSE slowly. Watch what happens. Add buffering.
4. **`custom` event for progress:** a node that processes N items, emitting `{progress: i/N}` each time. Stream this to a UI mock.
5. **Two stream modes at once:** combine `messages` and `custom`. How do you distinguish events?

## Production checklist

- [ ] Token streaming enabled and tested with your actual model provider.
- [ ] SSE heartbeats in place.
- [ ] Disconnect handling (cancel running tasks).
- [ ] Rate limiting per thread/user (Module 10).
- [ ] Authorization on stream endpoints.
- [ ] Stream + checkpointer integration tested (kill server, reconnect).
- [ ] Cost: streaming uses more input tokens if retries happen — monitor.

## Key takeaways

- Five modes: `values`, `updates`, `messages`, `events`, `custom`. Most apps use `messages` + `updates`.
- `messages` mode gives you tokens. `updates` gives you per-node deltas. `custom` is your channel.
- FastAPI + SSE is the simplest web streaming path. WebSockets if you need bi-directional or resumption.
- Always plan for disconnect, backpressure, and rate.
- Streams + checkpointers = resumable conversations.

## Resources

- LangGraph streaming: https://langchain-ai.github.io/langgraph/concepts/streaming/
- FastAPI SSE: https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse
- `astream_events` reference: https://langchain-ai.github.io/langgraph/reference/graphs/#langgraph.graph.graph.CompiledGraph.astream_events
