# L07 · Runtime context

> **Module M50 (part 2) · ~2h**
> Goal: pass your app's own values into nodes cleanly — and understand why
> `configurable` is the old way.

---

## 1. The problem

Before LangGraph 0.6, the way to give a node a `user_id` was to stuff it into
`config["configurable"]`:

```python
# OLD STYLE
config = {
    "configurable": {
        "thread_id": "chat-1",   # <- framework concern
        "user_id": "u-42",       # <- YOUR concern
        "tenant": "acme",        # <- YOUR concern
    }
}
```

and read it in a node with `config["configurable"]["user_id"]`.

**Why this is bad:**

1. **One namespace, two meanings.** `thread_id` is LangGraph's; `user_id` is
   yours. They can collide, and neither is validated.
2. **No schema.** A typo in `"userid"` fails at runtime, deep inside a node.
3. **Easy to leak.** `configurable` is echoed into traces and callbacks.
4. **Easy to mutate.** Nothing stops a node from writing to it.

---

## 2. The modern answer: `context_schema` + `context=` + `Runtime`

```python
from dataclasses import dataclass

@dataclass
class AppContext:
    user_id: str
    tenant: str = "default"

builder = StateGraph(State, context_schema=AppContext)
...
graph.invoke(input, context={"user_id": "u-42", "tenant": "acme"})
```

and in a node:

```python
from langgraph.runtime import Runtime

def my_node(state: State, runtime: Runtime[AppContext]) -> dict:
    user_id = runtime.context.user_id
    ...
```

### Properties of context

| Property      | Behaviour                                                     |
| ------------- | ------------------------------------------------------------- |
| Read-only     | a node can read `runtime.context` but **cannot write to it**  |
| Run-scoped    | fixed for the duration of one invocation                      |
| Not persisted | **never** written into a checkpoint                           |
| Typed         | validated against your schema at the boundary                 |
| Injected      | passed automatically to every node and every conditional edge |

> **The "not persisted" property is the big one.** Secrets and connections
> never land in your checkpoint database.

---

## 3. `config_schema` is deprecated — here is the exact status

| API                                             | Status                                       | Use instead               |
| ----------------------------------------------- | -------------------------------------------- | ------------------------- |
| `config_schema=` on `StateGraph` / `entrypoint` | **Deprecated in v0.6.0, removal in v2.0.0**  | `context_schema=`         |
| `config["configurable"]["user_id"]`             | Works, but old style                         | `runtime.context.user_id` |
| `config["configurable"]["thread_id"]`           | **Still current** — this is framework config | keep it                   |

The deprecation warning you will see if you use the old form:

```
`config_schema` is deprecated and will be removed.
Please use `context_schema` instead.
```

> **Do not confuse the two.** `config_schema` was *about* `configurable`.
> `thread_id` still lives in `configurable` and is not deprecated. What
> changed is that *your application's values* no longer belong there.

---

## 4. Defining a context schema

Any of the three schema types work:

```python
# dataclass (recommended - simple, explicit defaults)
from dataclasses import dataclass, field
from typing import Any

@dataclass
class AppContext:
    user_id: str
    tenant: str = "default"
    model: Any = None                 # a ready-to-use LLM
    flags: dict[str, bool] = field(default_factory=dict)

# TypedDict
from typing_extensions import TypedDict
class AppContext(TypedDict):
    user_id: str
    tenant: str

# Pydantic (if you want validation of the context itself)
from pydantic import BaseModel
class AppContext(BaseModel):
    user_id: str
    tenant: str = "default"
```

> **Note:** `context_schema` is *not* the same as `state_schema`. The state
> schema describes a **dict**; the context schema describes an **object** you
> access with attribute syntax (`runtime.context.user_id`).

---

## 5. Reading context in nodes and edges

### In a node

```python
def node(state: State, runtime: Runtime[AppContext]) -> dict:
    print(runtime.context.user_id)
    return {...}
```

### In a conditional edge

```python
def route(state: State, runtime: Runtime[AppContext]) -> str:
    if runtime.context.tenant == "vip":
        return "fast_track"
    return "standard"
```

### Async nodes

```python
async def node(state: State, runtime: Runtime[AppContext]) -> dict:
    ...
```

### In a tool (LangChain 1.x)

```python
from langchain.tools import tool
from langchain.agents import ToolRuntime

@tool
def get_profile(runtime: ToolRuntime[AppContext]) -> str:
    return lookup(runtime.context.user_id)
```

---

## 6. The four kinds of "context" — and which to use

This is the table to memorise. LangChain's own docs call these the four
context types; they differ in **mutability** and **lifetime**.

| Kind                                  | What it is                        | Mutability | Lifetime       | How to access                   |
| ------------------------------------- | --------------------------------- | ---------- | -------------- | ------------------------------- |
| **Static runtime context**            | user id, db handle, model, flags  | immutable  | one run        | `runtime.context` / `context=`  |
| **Dynamic runtime context (state)**   | messages, intermediate results    | mutable    | one run        | `state["key"]`                  |
| **Cross-conversation memory (store)** | user preferences, long-term facts | mutable    | across threads | `runtime.store` / `get_store()` |
| **LLM context**                       | the text in the prompt            | —          | per call       | the prompt you build            |

**The decision rule:**

- *Does it change during a run?* → **state**.
- *Does it need to survive across conversations?* → **store**.
- *Is it fixed for the run and read-only?* → **context**.
- *Is it text for the model?* → the prompt (built from the above, not stored
  in state — L03).

---

## 7. The Store — cross-conversation memory

The store is a key-value database that outlives a single thread.

```python
from langgraph.store.memory import InMemoryStore

store = InMemoryStore()
graph = builder.compile(store=store)
```

In a node:

```python
def node(state, runtime: Runtime[AppContext]) -> dict:
    # namespace = (user_id, "memories") -> per-user partition
    mem = runtime.store.get(("u-42", "memories"), "preferred_style")
    runtime.store.put(("u-42", "memories"), "preferred_style", {"value": "concise"})
    ...
```

or the standalone helpers:

```python
from langgraph.config import get_store

store = get_store()
```

The store is **not** the same as a checkpointer:

|           | Checkpointer                | Store                           |
| --------- | --------------------------- | ------------------------------- |
| Keyed by  | `thread_id`                 | you choose the namespace + key  |
| Holds     | the graph's state           | arbitrary application data      |
| Lifecycle | one conversation            | long-lived                      |
| Use for   | resuming, time travel, HITL | user memory, preferences, facts |

---

## 8. What else is on `Runtime`?

`Runtime` is more than context. It bundles several run-scoped services:

| Attribute                | What it gives you                                        |
|:------------------------ | -------------------------------------------------------- |
| `runtime.context`        | your typed static context                                |
| `runtime.store`          | the store (if compiled with one)                         |
| `runtime.stream_writer`  | push custom data to the stream                           |
| `runtime.previous`       | the previous return value of a Functional API entrypoint |
| `runtime.execution_info` | metadata about the current run                           |
| `runtime.heartbeat()`    | signal "still alive" for idle timeouts                   |

```python
def node(state, runtime: Runtime) -> dict:
    runtime.stream_writer({"progress": "step 1"})
    return {...}
```

`runtime.stream_writer` is how you emit **custom progress events** from
inside a node — the modern replacement for `get_stream_writer()` (which is
still available in `langgraph.config` and still works).

---

## 9. Practical patterns

### Pattern 1 — inject a ready-made model

```python
@dataclass
class AppContext:
    model: Any

graph.invoke(inp, context={"model": ChatGoogleGenerativeAI(model="gemini-3.8-flash")})
```

Now every node uses `runtime.context.model` and you can swap models per
request without touching the graph.

### Pattern 2 — per-tenant behaviour

```python
@dataclass
class AppContext:
    tenant: str
    tier: str = "standard"

def route(state, runtime: Runtime[AppContext]) -> str:
    return "priority_queue" if runtime.context.tier == "enterprise" else "standard_queue"
```

### Pattern 3 — a secret that must never be persisted

```python
@dataclass
class AppContext:
    api_key: str

def call_service(state, runtime: Runtime[AppContext]) -> dict:
    headers = {"Authorization": f"Bearer {runtime.context.api_key}"}
    ...
```

The key is in memory for the duration of the run and **never** in a
checkpoint. This is strictly better than putting it in state.

---

## 10. Gotchas

1. **Context is not state.** You cannot return `{"user_id": ...}` to "save"
   the context. It is read-only.
2. **Context is not persisted.** A resumed run needs the context passed
   again. (It is re-injected on `invoke`.)
3. **`runtime` is injected by parameter name.** If you name your parameter
   something else, LangGraph will not inject it. The convention is
   `runtime`.
4. **Do not put secrets in state.** State is checkpointed. Use context.
5. **`context` and `config` are separate arguments.** A common bug:
   `graph.invoke(inp, {"user_id": "u-1"})` puts `user_id` in `configurable`,
   where `runtime.context` will not see it.

```python
graph.invoke(inp, {"user_id": "u-1"})                    # WRONG for context
graph.invoke(inp, context={"user_id": "u-1"})             # RIGHT
```

---

## 11. Checkpoint

- [ ] I can explain why `configurable` is the wrong home for app values.
- [ ] I know `config_schema` is deprecated (removed in v2.0) and
  `context_schema` is the replacement.
- [ ] I can define a context schema, pass `context=` and read
  `runtime.context`.
- [ ] I know context is read-only, run-scoped and never persisted.
- [ ] I can pick correctly between context, state, store and prompt.
- [ ] I know the difference between a checkpointer and a store.

---

**Next → [L08 · Parallelism, fan-in and `Send`](./L08-parallel-and-send.md)** —
running nodes in parallel, and the map-reduce pattern.
