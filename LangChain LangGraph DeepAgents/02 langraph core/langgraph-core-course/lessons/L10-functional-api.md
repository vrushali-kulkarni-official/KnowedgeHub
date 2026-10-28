# L10 · The Functional API

> **Module M52 · ~2h**
> Goal: use ordinary Python control flow and still get persistence, streaming,
> and human-in-the-loop.

---

## 1. The idea

The Graph API says: *"declare your nodes and edges, and I will run them."*
The Functional API says: *"write normal Python; I will make it checkpointable."*

Both run on the **same Pregel runtime**. They interoperate freely.

```python
from langgraph.func import entrypoint, task
```

| Decorator | What it means |
|---|---|
| `@task` | "this is a discrete unit of work" — a function whose result is checkpointed |
| `@entrypoint` | "this is the workflow" — the function that LangGraph runs |

---

## 2. `@task` — a unit of work

```python
from langgraph.func import task

@task
def fetch(url: str) -> str:
    return requests.get(url).text
```

Calling `fetch(url)` **does not execute it immediately**. It returns a
future-like object. You resolve it with `.result()`:

```python
body = fetch(url).result()      # sync
body = await fetch(url)          # async
```

**Why the indirection?** Because the result is written to the checkpoint. If
the workflow is interrupted and later resumed, the task's result is **loaded
from the checkpoint instead of being recomputed**. That is how you avoid
re-paying for an expensive API call after a human review.

```python
essay = write_essay("cats").result()      # computed once, ever
is_approved = interrupt({"essay": essay}) # may pause for days
# ... resume later ...
# write_essay is NOT called again - its result was checkpointed
```

### Rules for tasks

- A task's arguments and return value must be **serialisable** (they go into
  the checkpoint).
- A task can call other tasks.
- A task should be **idempotent-ish** if it has side effects, because a
  resumed run may... actually no: with a checkpointer, a completed task is
  not re-run. Without a checkpointer, it is.

---

## 3. `@entrypoint` — the workflow

```python
from langgraph.func import entrypoint

@entrypoint()
def workflow(topic: str) -> dict:
    outline = create_outline(topic).result()
    if len(outline["points"]) < 3:
        outline = expand_outline(outline).result()
    draft = write_draft(outline).result()
    return {"essay": draft}
```

That is a normal Python function. `if`, `for`, `try/except`, helper functions,
recursion — all of it works.

### The `@entrypoint` signature (LangGraph 1.2, verified)

```python
@entrypoint(
    checkpointer=None,      # persistence
    store=None,             # long-term memory
    cache=None,             # node cache
    context_schema=None,    # runtime context (L07)
    cache_policy=None,      # CachePolicy
    retry_policy=None,      # RetryPolicy
    timeout=None,           # float | timedelta | TimeoutPolicy
)
```

> **Deprecated:** `config_schema=` (removed in v2.0 — use `context_schema=`)
> and `retry=` (use `retry_policy=`). Both emit a
> `LangGraphDeprecatedSinceV10` / `LangGraphDeprecatedSinceV05` warning.

### Parameters the entrypoint function can receive

| Parameter | What it is |
|---|---|
| your own arguments | whatever you pass to `invoke()` |
| `previous` | the previous run's return value **for this thread** (needs a checkpointer) |
| `runtime` | the `Runtime` object (context, store, stream writer) |

```python
@entrypoint(checkpointer=InMemorySaver())
def counter(x: int, previous: int | None) -> int:
    return (previous or 0) + x
```

**Verified:** with a checkpointer and a fixed `thread_id`, `previous` was
`None` → `3` → `7` → `12` across three `invoke()` calls. Without a
checkpointer, `previous` is always `None`.

> **Gotcha (verified):** `previous` is a **function parameter**, not an
> attribute. `counter.previous` raises
> `AttributeError: 'Pregel' object has no attribute 'previous'`.

### `entrypoint.final` — return one thing, save another

```python
@entrypoint(checkpointer=InMemorySaver())
def fin(x: int, previous: int | None):
    entrypoint.final(value=x, save=100)   # return x, persist 100
    return x
```

**Verified:** the caller gets `x`, and the *next* run's `previous` is `100`.
Both `value` and `save` are **required keyword arguments** —
`entrypoint.final(saved_value=100)` raises
`TypeError: entrypoint.final.__init__() got an unexpected keyword argument
'saved_value'`.

---

## 4. Async entrypoints

```python
@entrypoint()
async def workflow(topic: str) -> dict:
    outline = await create_outline(topic)
    draft = await write_draft(outline)
    return {"essay": draft}
```

Tasks become awaitable instead of `.result()`-able. Run with `ainvoke()`.

---

## 5. What the Functional API does *not* give you

| Feature | Functional API | Graph API |
|---|---|---|
| Persistence / checkpointing | ✅ | ✅ |
| Human-in-the-loop (`interrupt`) | ✅ | ✅ |
| Streaming | ✅ | ✅ |
| Memory store | ✅ | ✅ |
| **Visualisation** (`draw_mermaid`) | ❌ | ✅ |
| **Explicit shared state** | ❌ (function-scoped) | ✅ |
| **Static graph structure** | ❌ (built at runtime) | ✅ |

The graph is built *dynamically* in the Functional API, so there is no fixed
topology to draw. That is the real trade-off: you lose the picture, you gain
the code you would have written anyway.

---

## 6. Mixing the two APIs

This is supported and encouraged. Two directions:

### Functional inside Graph

```python
from langgraph.func import entrypoint

@entrypoint()
def heavy_pipeline(data: dict) -> dict:
    cleaned = clean(data).result()
    return transform(cleaned).result()

def node_run_pipeline(state):
    return {"result": heavy_pipeline.invoke(state["data"])}
```

### Graph inside Functional

```python
graph = StateGraph(State).add_node("a", a).compile()

@entrypoint()
def workflow(x: int) -> dict:
    result = graph.invoke({"x": x})
    return {"out": result}
```

A compiled graph *is* a Runnable, so it has `.invoke()` / `.ainvoke()` /
`.stream()` like anything else.

---

## 7. When to prefer the Functional API

**Use it when:**

1. **You have existing imperative code.** Wrapping it in `@task`s is a
   small diff; restructuring it into a graph is a rewrite.
2. **The workflow is linear** with a couple of `if`s.
3. **You are prototyping** and want the least boilerplate.
4. **The state is naturally function-scoped** — each function needs only a
   couple of values, and there is no shared mutable state to coordinate.
5. **You want to wrap a library.** A library call becomes one `@task`, and
   you get checkpointing around it for free.

**Use the Graph API when:**

1. You need the **visualisation** (Studio, Mermaid, reviews).
2. You need **explicit shared state** that many nodes read and write.
3. You need **parallel fan-out/fan-in** with clear join semantics.
4. You need **per-node policies** (retry, timeout, cache) — the Functional
   API has `retry_policy`/`timeout` at the *entrypoint* level, not per task.
5. The **shape of the workflow is the thing you are designing.**

---

## 8. A migration story

Functional workflows tend to grow. The usual path:

```
@entrypoint with 3 tasks  ->  @entrypoint with a branch and 8 tasks
                            ->  StateGraph, because the branching is now
                                the interesting part of the system
```

The docs' own guidance: *"When your functional workflow grows complex, migrate
to the Graph API."* And the reverse — *"when your graph becomes overly complex
for simple linear processes"* — simplify to Functional.

Neither is a regression. They are two tools for the same runtime.

---

## 9. Checkpoint

- [ ] I can explain `@task` vs `@entrypoint` and why tasks return a future.
- [ ] I know `.result()` (sync) vs `await` (async).
- [ ] I know that a completed task's result is restored from the checkpoint
      instead of being recomputed.
- [ ] I know `previous` is a parameter, not an attribute.
- [ ] I know `entrypoint.final(value=..., save=...)` and that both are
      required keywords.
- [ ] I can mix the two APIs in either direction.
- [ ] I can explain what the Functional API gives up (visualisation, explicit
      shared state, per-node policies).

---

**Next → [L11 · Subgraphs](./L11-subgraphs.md)** — composing graphs, mapping
state between them, and namespace isolation.
