# L09 · Async and streaming

> **Module M51 (part 2) · ~2.5h**
> Goal: get real concurrency, and stream results to a user as they happen.

---

## 1. Async nodes

A node can be a coroutine:

```python
async def fetch(state: State) -> dict:
    resp = await httpx.AsyncClient().get(state["url"])
    return {"body": resp.text}
```

LangGraph detects it and schedules it on the event loop.

**The hard rule (verified):** a graph containing an async node **cannot** be
run with the synchronous `invoke()`.

```
TypeError: No synchronous function provided to "asyn".
Either initialize with a synchronous function or invoke via the async API
(ainvoke, astream, etc.)
```

So the rule is simple:

| Graph contains  | Use                       |
| --------------- | ------------------------- |
| only sync nodes | `invoke()` / `stream()`   |
| any async node  | `ainvoke()` / `astream()` |

---

## 2. The blocking-in-async trap ⚠️

This is the most common async bug in LangGraph, and it is silent — your
graph still works, it is just **not concurrent**.

```python
async def bad_node(state):
    time.sleep(0.5)            # BLOCKS THE EVENT LOOP
    return {"out": ["done"]}
```

`time.sleep` inside a coroutine freezes the entire event loop. Every other
async node in that superstep waits.

**Verified measurement** (`examples/L09_async_and_streaming.py`):

```
3 async nodes, all `await asyncio.sleep(0.5)`  ->  0.51s   (concurrent)
3 async nodes, all `time.sleep(0.5)`           ->  1.50s   (serialised)
```

A 3× difference, with no error message anywhere.

### The fixes

| Blocking call                    | Async replacement                           |
| -------------------------------- | ------------------------------------------- |
| `time.sleep(x)`                  | `await asyncio.sleep(x)`                    |
| `requests.get(url)`              | `httpx.AsyncClient().get(url)`              |
| `open(...).read()`               | `await asyncio.to_thread(path.read_text)`   |
| `subprocess.run(...)`            | `await asyncio.create_subprocess_exec(...)` |
| a sync SDK with no async version | `await asyncio.to_thread(sync_call)`        |

`asyncio.to_thread` is the universal escape hatch: it runs a blocking
function in a thread pool so the event loop stays free.

```python
import asyncio

async def node(state):
    text = await asyncio.to_thread(expensive_sync_function, state["arg"])
    return {"text": text}
```

> **Rule of thumb:** if you are writing `async def`, every I/O call inside it
> must be awaited. If you cannot await it, wrap it in `asyncio.to_thread`.

---

## 3. Streaming — the seven modes

`graph.stream(input, stream_mode="...")`. The authoritative list in LangGraph
1.2 is:

```python
StreamMode = Literal['values', 'updates', 'checkpoints', 'tasks', 'debug', 'messages', 'custom']
```

### `values` — the full state after each superstep

```python
for state in graph.stream(inp, stream_mode="values"):
    print(state)
```

Yields the **entire state** after every superstep. Simple, but the payload
grows with the state.

### `updates` — only what changed

```python
for chunk in graph.stream(inp, stream_mode="updates"):
    print(chunk)
# {'node_name': {'key': 'value'}}
```

**The most useful mode for debugging.** The key is the node that ran; the
value is that node's partial update. This is how you see the actual path a
run took through your graph.

### `checkpoints` — a full `StateSnapshot` per superstep

```python
for snap in graph.stream(inp, stream_mode="checkpoints"):
    print(snap.next, snap.values)
```

The streaming form of `get_state_history`.

> **Requires a checkpointer.** Verified: with `checkpointer=None` the mode
> yields **0 chunks**; with `InMemorySaver()` it yields one snapshot per
> superstep. There is nothing to checkpoint if nothing is being checkpointed.

### `messages` — LLM token streaming

```python
for token, metadata in graph.stream(inp, stream_mode="messages"):
    print(token.content, end="", flush=True)
```

This is the mode you want for a chat UI. It streams **LLM tokens** as they
are produced, from any node that calls a chat model.

> Yields **0 chunks** if no node in the graph calls a chat model — the mode
> only emits for LLM calls, not for plain state updates.

### `tasks` — task-level events

```python
for task in graph.stream(inp, stream_mode="tasks"):
    print(task)
```

Finer-grained than `updates`: reports individual task starts and results
(important when one node fans out into many `Send` tasks).

### `debug` — the firehose

```python
for event in graph.stream(inp, stream_mode="debug"):
    print(event["type"], event.get("step"))
```

Everything: chain starts/ends, task starts/ends, writes. Verbose, but it is
where the **step number** lives, which is how you identify superstep
boundaries (L01).

### `messages` — LLM token streaming

```python
for token, metadata in graph.stream(inp, stream_mode="messages"):
    print(token.content, end="", flush=True)
```

This is the mode you want for a chat UI. It streams **LLM tokens** as they
are produced, from any node that calls a chat model.

### `custom` — your own events

Emitted by `runtime.stream_writer(...)` (or `get_stream_writer()`) inside a
node:

```python
def node(state, runtime: Runtime) -> dict:
    runtime.stream_writer({"progress": "50% done"})
    return {...}
```

```python
for event in graph.stream(inp, stream_mode="custom"):
    print(event)
```

### Which one to use

| You want                     | Mode          |
| ---------------------------- | ------------- |
| see the final state evolving | `values`      |
| see which nodes ran          | `updates`     |
| debug a stuck run            | `debug`       |
| stream tokens to a user      | `messages`    |
| show a progress bar          | `custom`      |
| inspect checkpoints live     | `checkpoints` |
| per-task detail with `Send`  | `tasks`       |

### Multiple modes at once

```python
for mode, chunk in graph.stream(inp, stream_mode=["updates", "messages"]):
    ...
```

Each chunk becomes a `(mode, payload)` tuple.

### Async streaming

```python
async for mode, chunk in graph.astream(inp, stream_mode=["updates", "messages"]):
    ...
```

---

## 4. Streaming from a subgraph

Subgraph events are namespaced. Turn them on with `subgraphs=True`:

```python
for ns, chunk in graph.stream(inp, stream_mode="updates", subgraphs=True):
    print(ns, chunk)
```

`ns` is a tuple describing the path, e.g. `("parent_node", "child_node")`.
Without `subgraphs=True` you only see the parent's view.

(There is also a newer `langgraph.stream` module with `GraphRunStream` /
`AsyncGraphRunStream` objects and `transformers=`. That is the forward-looking
API; the `stream_mode=` API above is stable, current, and what you should
use today.)

---

## 5. Async in practice — parallel retrieval

```python
import asyncio
import httpx

class State(TypedDict):
    query: str
    results: Annotated[list[str], operator.add]

async def search_web(state: State) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get("https://api.example.com/search", params={"q": state["query"]})
    return {"results": [r.text]}

async def search_docs(state: State) -> dict:
    hits = await asyncio.to_thread(vector_store.similarity_search, state["query"], k=3)
    return {"results": [h.page_content for h in hits]}
```

Both nodes are async, both run concurrently in one superstep, and the
`operator.add` reducer merges the results.

---

## 6. Common async mistakes

| Mistake                                      | Symptom                                       | Fix                       |
| -------------------------------------------- | --------------------------------------------- | ------------------------- |
| `time.sleep` in an async node                | everything serialises, no error               | `await asyncio.sleep`     |
| `requests` in an async node                  | serialises, plus thread-safety issues         | `httpx.AsyncClient`       |
| `graph.invoke()` on a graph with async nodes | `TypeError: No synchronous function provided` | use `ainvoke()`           |
| `await` inside a sync node                   | `SyntaxError` / coroutine never awaited       | make the node `async def` |
| unbounded `asyncio.gather` over 1000 items   | rate limit, memory spike                      | bound the concurrency     |

### Bounding concurrency

```python
sem = asyncio.Semaphore(10)

async def fetch_limited(state):
    async with sem:
        return await do_fetch(state["url"])
```

---

## 7. When to go async

**Go async when:**

- your nodes do network I/O (the common case),
- you fan out over many items with `Send`,
- you are serving a web app and want to handle many requests per process,
- you are streaming tokens to a user.

**Stay sync when:**

- the graph is a short batch job,
- your dependencies are sync-only (use `asyncio.to_thread`),
- you are learning the basics — sync is easier to debug.

**You can migrate later.** A sync graph can be converted node by node; the
API surface is identical.

---

## 8. Checkpoint

- [ ] I know a graph with an async node requires `ainvoke`/`astream`.
- [ ] I can explain the blocking-in-async trap and show the measurement.
- [ ] I know the seven stream modes and what each is for.
- [ ] I can stream LLM tokens with `stream_mode="messages"`.
- [ ] I can emit custom progress events with `runtime.stream_writer`.
- [ ] I can enable subgraph events with `subgraphs=True`.

---

**Next → [L10 · The Functional API](./L10-functional-api.md)** — `@entrypoint`
and `@task`, wrapping existing code, and mixing it with `StateGraph`.
