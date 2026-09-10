# Module 05 — Memory & Persistence

## Prerequisites

- Module 04 (you have a ReAct agent)

## Why this module matters

Without persistence, every invocation of your graph starts from scratch. That's a toy. With persistence:

- Conversations continue across requests.
- You can pause a graph and resume it later.
- You can branch, rewind, and inspect state at any step ("time travel").
- You can build long-running workflows that span hours or days.

This module is what turns your agent into a **service**.

## Learning objectives

By the end of this module you can:

1. Attach a checkpointer to a compiled graph.
2. Choose the right checkpointer backend: `MemorySaver`, `SqliteSaver`, `PostgresSaver`.
3. Use thread IDs to scope conversations.
4. Read state at any point: `get_state`, `get_state_history`.
5. Modify and rewind state: `update_state`.
6. Use the cross-thread `Store` for long-term memory.
7. Design a Postgres-backed production deployment.

---

## 5.1 What is a checkpointer?

A checkpointer is a pluggable storage layer that:

- Snapshots the graph's state after every node execution.
- Keys those snapshots by **thread_id** (and optionally other config keys).
- Lets you resume from any snapshot.

Without one, your graph is stateless. With one, it's a database of runs.

---

## 5.2 The three common checkpointers

### 5.2.1 `MemorySaver` (in-process, dev only)

```python
from langgraph.checkpoint.memory import MemorySaver

memory = MemorySaver()
g = builder.compile(checkpointer=memory)
```

State lives in the Python process. Gone when the process dies. Use only for notebooks and unit tests.

### 5.2.2 `SqliteSaver` (single-process, file-backed)

```python
from langgraph.checkpoint.sqlite import SqliteSaver

with SqliteSaver.from_conn_string("checkpoints.db") as checkpointer:
    g = builder.compile(checkpointer=checkpointer)
```

Great for local dev. Survives restarts. Single-writer — don't run multiple processes against the same SQLite file.

### 5.2.3 `PostgresSaver` (production)

```python
from langgraph.checkpoint.postgres import PostgresSaver

DB_URI = "postgresql://user:pass@host:5432/langgraph"

with PostgresSaver.from_conn_string(DB_URI) as checkpointer:
    checkpointer.setup()    # creates tables on first run
    g = builder.compile(checkpointer=checkpointer)
```

This is what you want for production. Multi-process, multi-replica safe.

You'll need to install: `uv add langgraph-checkpoint-postgres` (and psycopg/asyncpg).

### 5.2.4 Async checkpointers

For async apps, use the `a...` variants:

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
```

---

## 5.3 Thread IDs and config

Every invocation of a stateful graph must include a `thread_id`:

```python
config = {"configurable": {"thread_id": "user-42-session-1"}}

result1 = g.invoke({"messages": [HumanMessage(content="Hi, I'm Sam.")]}, config)
result2 = g.invoke({"messages": [HumanMessage(content="What's my name?")]}, config)
print(result2["messages"][-1].content)   # "Sam"
```

Different `thread_id`s = different conversations. Same `thread_id` = one conversation, with full history.

You can add more keys to `configurable`:

```python
config = {
    "configurable": {
        "thread_id": "user-42-session-1",
        "user_id": "42",
        "tenant_id": "acme-corp",
    }
}
```

These become part of the checkpoint key and are accessible in nodes via `runtime.config`.

---

## 5.4 Reading state

### 5.4.1 Current state

```python
state = g.get_state(config)
print(state.values)        # the state dict
print(state.next)          # next node to run (or ())
print(state.config)        # the actual config
```

### 5.4.2 Full history (time travel)

```python
for snapshot in g.get_state_history(config):
    print(snapshot.values, snapshot.next, snapshot.config)
```

Each snapshot is a step. You can rewind, replay, or fork from any one.

---

## 5.5 Updating and rewinding state

### 5.5.1 `update_state` (rewind & patch)

```python
new_config = g.update_state(
    config,                                # which thread
    {"messages": [HumanMessage(content="Actually, ignore that.")]},  # update
    as_node="agent"                        # pretend this update came from this node
)
```

This:
1. Takes the current state.
2. Applies your update.
3. **Rewinds** to the point right after the named node.
4. Resumes from there on the next `invoke`/`stream`.

This is "time travel": go back to step N, change state, replay forward.

### 5.5.2 Fork from history

```python
history = list(g.get_state_history(config))
old_snapshot = history[3]                  # step 3
fork_config = old_snapshot.config

# Continue from step 3 with a fresh "branch"
result = g.invoke(None, fork_config)       # pass None = use existing state
```

This is how you do "branch" in a conversation: replay from a point, take a different path.

### 5.5.3 `as_node` matters

`update_state(..., as_node="X")` tells LangGraph "pretend this update came from node X, so rewind to just after X." This is how you insert / delete / replace a step.

---

## 5.6 The `Store`: cross-thread long-term memory

The checkpointer stores **per-thread** state. For **across-thread** memory (user preferences, knowledge learned in past sessions), use `BaseStore`.

```python
from langgraph.store.memory import InMemoryStore
from langgraph.store.postgres import PostgresStore

# In-memory (dev)
store = InMemoryStore()

# Postgres (prod)
with PostgresStore.from_conn_string(DB_URI) as store:
    store.setup()

g = builder.compile(checkpointer=checkpointer, store=store)
```

In a node:

```python
def remember_user_preference(state, *, store: BaseStore):
    user_id = state["user_id"]
    store.put(("users",), user_id, {"preference": "concise answers"})
    return {}

def recall_user_preference(state, *, store: BaseStore):
    user_id = state["user_id"]
    item = store.get(("users",), user_id)
    if item:
        return {"context": f"User prefers: {item.value['preference']}"}
    return {}
```

Namespace tuple `("users",)` is the "table"; `user_id` is the key. Values are arbitrary JSON.

---

## 5.7 Storage patterns

### 5.7.1 Pattern: per-user store

```python
namespace = ("users", user_id)
store.put(namespace, "profile", {"name": "...", "prefs": {...}})
```

### 5.7.2 Pattern: searchable store

`BaseStore` supports `search` for simple queries:

```python
results = store.search(("docs",), query="weather", limit=5)
```

For semantic search, you'd typically use a vector store (Module 10 covers LangChain vector stores).

### 5.7.3 Pattern: TTL on stored items

`store.put(..., ttl=3600)` for time-bounded memory. Items auto-expire.

---

## 5.8 Designing the production schema

When you deploy with `PostgresSaver`, it creates these tables (simplified):

```
checkpoints
  ├── thread_id
  ├── checkpoint_ns
  ├── checkpoint_id
  ├── parent_checkpoint_id
  ├── type
  ├── checkpoint     (JSONB)
  └── metadata       (JSONB)
checkpoint_writes    (pending writes)
checkpoint_blobs     (large blobs)
```

For your SaaS:
- `thread_id` is your conversation ID.
- Use the same Postgres for application data — one source of truth.
- Add a `tenant_id` to checkpoint metadata via `config` so you can filter.

---

## 5.9 The full persistence pattern

Putting it together for a FastAPI service:

```python
# app/graph/graph.py
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    async with AsyncPostgresSaver.from_conn_string(DB_URI) as cp:
        await cp.setup()
        app.state.checkpointer = cp
        yield

# compile lazily with the checkpointer
def make_graph(checkpointer):
    return builder.compile(checkpointer=checkpointer)

# in the route:
config = {"configurable": {"thread_id": thread_id, "user_id": user.id}}
result = await g.ainvoke(input, config=config)
```

---

## 5.10 Common persistence pitfalls

| Pitfall | Fix |
|---|---|
| Forgetting `thread_id` | Always pass it; raise if missing |
| Using `MemorySaver` in production | Use `PostgresSaver` |
| Not running `checkpointer.setup()` | First deploy needs it to create tables |
| Storing secrets in state | Use references; encrypt at rest at the DB layer |
| Huge blobs in checkpoints | They bloat the DB fast; store paths instead |
| No cleanup strategy | Periodically delete old threads (TTL or scheduled job) |

---

## Hands-on project

**Goal:** Build a multi-turn, persistent chatbot with long-term memory.

1. Add `PostgresSaver` to your ReAct agent (use Docker Compose to run Postgres locally).
2. Add a `user_id` to every config; require it.
3. Implement `store.put` and `store.get` to remember the user's name across sessions (different `thread_id`s).
4. Implement a `/chat` FastAPI route that:
   - Reads `thread_id` from the request.
   - Invokes the graph.
   - Returns the assistant reply.
5. Test: send 3 messages, kill the server, restart, send message 4 — does it remember messages 1–3?

## Exercises

1. **Time travel:** in a running thread, call `get_state_history`, pick step 2, `update_state` to delete a message, then `invoke` again. What happens?
2. **Branching:** fork from step 2 into a new thread with a different user message. Both branches should continue independently.
3. **Cross-thread memory:** in thread A, save a preference. In thread B, read it.
4. **Postgres-only:** migrate from `MemorySaver` to `PostgresSaver`. Run two parallel invocations on the same thread. What happens? On different threads?
5. **TTL test:** store an item with a 5-second TTL. Sleep 6 seconds. Read it. What's returned?

## Production checklist

- [ ] Checkpointer is `PostgresSaver` (or compatible production store).
- [ ] `checkpointer.setup()` runs on first deploy.
- [ ] Every API route requires `thread_id` and validates it.
- [ ] Tenant/user isolation enforced via config keys.
- [ ] No secrets or huge blobs in state.
- [ ] Retention policy for old threads (cleanup job).
- [ ] `Store` namespace strategy is documented.

## Key takeaways

- Checkpointers give you state continuity. Postgres is the production default.
- `thread_id` scopes a conversation. Same thread = one conversation.
- `get_state` / `get_state_history` / `update_state` = time travel.
- `Store` is cross-thread long-term memory. Different abstraction.
- Persistence is what makes the agent a service.

## Resources

- LangGraph persistence: https://langchain-ai.github.io/langgraph/concepts/persistence/
- `PostgresSaver` reference: https://langchain-ai.github.io/langgraph/reference/checkpoints/
- `BaseStore`: https://langchain-ai.github.io/langgraph/reference/store/
- LangGraph Studio (Module 09) uses the same persistence model.
