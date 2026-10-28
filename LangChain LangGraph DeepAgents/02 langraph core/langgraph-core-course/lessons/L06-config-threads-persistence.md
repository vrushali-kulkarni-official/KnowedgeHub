# L06 · Config, threads, persistence and time travel

> **Module M50 (part 1) · ~3h**
> Goal: make your graph stateful across invocations, and control the runtime
> knobs you actually need.

---

## 1. `RunnableConfig` — the runtime control panel

Every `invoke`/`stream` accepts a `config`:

```python
graph.invoke(
    {"question": "hi"},
    config={"configurable": {"thread_id": "user-42"}, "recursion_limit": 25},
)
```

`RunnableConfig` comes from `langchain_core.runnables` and is the *framework's*
configuration channel. It has three families of keys:

| Key                             | Type   | What it does                                                    |
| ------------------------------- | ------ | --------------------------------------------------------------- |
| `configurable`                  | `dict` | Framework + app settings that may be read by callbacks          |
| `recursion_limit`               | `int`  | Max supersteps before `GraphRecursionError` (default **10000**) |
| `tags`, `metadata`, `callbacks` | —      | Tracing / observability                                         |

The `configurable` sub-dict is where `thread_id` lives. `thread_id` is the
**identity of a conversation**.

> **Note on `configurable`:** in LangGraph 1.x, `configurable` is for
> *framework* concerns (`thread_id`, `checkpoint_ns`, …). Your **own**
> application values (user id, tenant, db handle) now belong in
> **runtime context** — L07. Storing them in `configurable` still works, but
> it is the older style and it mixes namespaces.

---

## 2. Threads and checkpointers — what "memory" means in LangGraph

### The model

```
thread_id  =  a conversation
checkpointer = the thing that stores a thread's state
checkpoint    = one snapshot of a thread's state at a point in time
superstep     = one tick of the graph (a checkpoint is written at each boundary)
```

### The checkpointer is opt-in

```python
from langgraph.checkpoint.memory import InMemorySaver

graph = builder.compile(checkpointer=InMemorySaver())
```

Without a checkpointer:

- every `invoke` starts from a blank state;
- `thread_id` is ignored;
- `get_state` / `update_state` / time travel do not work;
- `interrupt()` cannot resume.

With a checkpointer:

- state is saved after every superstep;
- the same `thread_id` resumes where it left off;
- you can inspect, edit and rewind history.

### `thread_id` is mandatory once you have a checkpointer

```python
config = {"configurable": {"thread_id": "1"}}
graph.invoke(input, config)
```

Without it you get:

```
ValueError: Checkpointer requires one or more of the following 'configurable'
keys: thread_id, checkpoint_ns, checkpoint_id
```

(Verified. Note that `checkpoint_ns` and `checkpoint_id` are also accepted —
`thread_id` is simply what you want in application code.)

> `InMemorySaver` is for tests and demos. It is named that way for a reason:
> everything is lost when the process exits. For anything real:
>
> | Checkpointer    | Package                         | Use                    |
> | --------------- | ------------------------------- | ---------------------- |
> | `InMemorySaver` | `langgraph` (built in)          | tests, notebooks       |
> | `SqliteSaver`   | `langgraph-checkpoint-sqlite`   | local dev, single node |
> | `PostgresSaver` | `langgraph-checkpoint-postgres` | production, multi-node |
>
> The user-facing name changed: older code says `MemorySaver`. It still works
> as an alias, but `InMemorySaver` is the current name.

---

## 3. Multi-turn conversation — the payoff

```python
graph = builder.compile(checkpointer=InMemorySaver())
config = {"configurable": {"thread_id": "chat-1"}}

graph.invoke({"messages": [HumanMessage("My name is Ada")]}, config)
graph.invoke({"messages": [HumanMessage("What is my name?")]}, config)
# -> the model remembers "Ada" because it's the same thread
```

Each `invoke` on the same thread **continues** the conversation. The
`add_messages` reducer appends, so the history accumulates.

**New thread = new memory.** Use a new `thread_id` and the model forgets.

---

## 4. Inspecting and editing state

### `get_state` — what is the current state?

```python
snapshot = graph.get_state(config)
snapshot.values        # the current state dict
snapshot.next          # tuple of node names that will run next
snapshot.config        # the config of this checkpoint
snapshot.metadata      # step count, writes, source, etc.
snapshot.interrupts    # any pending interrupts
snapshot.tasks         # the tasks in the current superstep
```

> **Verified API note:** the state dict is on `snapshot.values`, **not**
> `snapshot.state`. `StateSnapshot` exposes: `config, count, created_at,
> index, interrupts, metadata, next, parent_config, tasks, values`.

### `get_state_history` — the timeline

```python
for snap in graph.get_state_history(config):
    print(snap.metadata.get("step"), snap.next, snap.values)
```

Each entry is a checkpoint. This is the raw material for time travel.

### `update_state` — write to a thread

```python
graph.update_state(config, {"category": "billing"})
```

This writes a value as if a node had returned it, creating a new checkpoint.
Use it to:

- correct state after a human review;
- seed a thread with initial data;
- patch a value and re-run from there.

> `update_state` uses the same reducers as a normal node write. Appending a
> message via `update_state` goes through `add_messages`.

---

## 5. Time travel

Because a checkpoint is written at every superstep boundary, you can rewind
to any point and re-run.

```python
# 1. find the checkpoint you want
history = list(graph.get_state_history(config))
target = history[2]        # some earlier checkpoint

# 2. re-run from there with a new input
graph.invoke({"messages": [HumanMessage("Actually, say something else")]},
             config=target.config)
```

The graph resumes from that checkpoint with the *new* input, producing a new
branch of history.

> **Important:** you can only resume from a **superstep boundary**, i.e. from
> a full checkpoint. LangGraph also persists per-node *task writes* (for
> fault tolerance), but those are not resumable points.

This is one of LangGraph's genuinely superpower features: you can rewind a
production conversation, change one piece of state, and replay the rest of the
workflow.

---

## 6. The recursion limit

`recursion_limit` bounds the number of **supersteps** in a run.

```python
graph.invoke(input, {"recursion_limit": 5})
```

Default is **10000**. When exceeded:

```
GraphRecursionError: Recursion limit of 5 reached without hitting a stop
condition. You can increase the limit by setting the `recursion_limit` config key.
```

**What this is really for:** a graph with a cycle that has no termination
condition. It is a safety net, not a normal control.

> **Remember:** it counts *supersteps*, not nodes. A fan-out of 10 parallel
> nodes is still one superstep.

### The proactive way to stop: `RemainingSteps`

Rather than waiting for the limit to be hit, you can ask "how many steps do I
have left?" and stop gracefully.

```python
from langgraph.managed import RemainingSteps

class State(TypedDict):
    steps: RemainingSteps
```

`RemainingSteps` is a managed channel: it exists only for the duration of the
run and is never persisted. Its value is the number of supersteps remaining
before the limit.

```python
def agent(state: State):
    if state["steps"] <= 1:      # last chance
        return {"answer": "giving up"}
    return {"answer": agent_call(state)}
```

**Verified behaviour:** with `recursion_limit=7`, a node read
`state["steps"] == 6` — i.e. the number of supersteps still available. The
value is *not* written into the persisted state (it is a managed, run-scoped
channel), so it never bloats your checkpoints.

### ⚠️ The headroom rule (verified, and it will bite you)

Measured on langgraph 1.2.17, with a loop that stops when
`state["steps"] <= margin`:

| margin | `recursion_limit=20`    | `recursion_limit=50`    |
| ------ | ----------------------- | ----------------------- |
| **1**  | `GraphRecursionError` ❌ | `GraphRecursionError` ❌ |
| **2**  | OK ✅                    | OK ✅                    |
| 3      | OK ✅                    | OK ✅                    |
| 5      | OK ✅                    | OK ✅                    |

**With `margin == 1`, the run raises `GraphRecursionError` even though the
graph finished correctly** — the final state was right and `next` was `()`.
The stop decision lands on the very last tick, and the terminal transition
needs one more.

**So: stop when `steps <= 2`, and give `recursion_limit` plenty of headroom.**

> **How many supersteps does a run actually use?** A "simple cycle" that hits
> the limit executes the node exactly `recursion_limit` times (verified:
> limit 4 → 4 runs, limit 20 → 20 runs). The count includes the initial
> input write and the terminal transition, so budget accordingly.

```python
from langgraph.errors import GraphRecursionError

try:
    graph.invoke(input, {"recursion_limit": 10})
except GraphRecursionError:
    # the reactive fallback
    ...
```

> **The reactive fallback is worse**: by the time the limit is hit, you have
> already burned `recursion_limit` LLM calls. The proactive approach is
> almost always better. Use `RemainingSteps`.

---

## 7. `interrupt_before` / `interrupt_after` — the debugging knobs

```python
graph = builder.compile(interrupt_before=["search_docs"])
```

The graph stops *before* running `search_docs`, and the state is checkpointed.
You can then inspect the state, modify it, and resume.

This is a blunt instrument for debugging. The precise version is
`interrupt()` inside a node (Phase 8, human-in-the-loop). But `interrupt_before`
is a two-word fix for "I want to see the state right before this step" and it
works today.

---

## 8. Durability modes

LangGraph 1.x lets you choose *when* state is written to the checkpointer.

```python
graph.invoke(input, config, durability="sync")     # default-ish
graph.invoke(input, config, durability="async")    # write in the background
graph.invoke(input, config, durability="exit")     # only at the end of the run
```

| Mode    | When state is persisted               | Trade-off                                    |
| ------- | ------------------------------------- | -------------------------------------------- |
| `sync`  | at every superstep, before continuing | safest, slowest                              |
| `async` | at every superstep, in the background | fast; a crash can lose the last step         |
| `exit`  | only when the run finishes            | fastest; no time travel, no interrupt resume |

Use `sync` for anything with human-in-the-loop or side effects. Use `async`
for long, read-only pipelines where losing the last step is acceptable.

---

## 9. Configuration reference

| What                  | Where                                     | Example                    |
| --------------------- | ----------------------------------------- | -------------------------- |
| Conversation identity | `config["configurable"]["thread_id"]`     | `"chat-1"`                 |
| Subgraph namespace    | `config["configurable"]["checkpoint_ns"]` | set automatically          |
| Max supersteps        | `config["recursion_limit"]`               | `25`                       |
| Tracing tags          | `config["tags"]`                          | `["prod", "v2"]`           |
| Tracing metadata      | `config["metadata"]`                      | `{"user": "u-1"}`          |
| Callbacks             | `config["callbacks"]`                     | for custom instrumentation |
| Your app's own values | **`context=`** (L07)                      | `{"user_id": "u-1"}`       |

### The `invoke` signature in LangGraph 1.2

```python
graph.invoke(
    input,
    config=None,
    *,
    context=None,          # runtime context (L07)
    stream_mode="values",
    print_mode=(),
    output_keys=None,
    interrupt_before=None,
    interrupt_after=None,
    durability=None,       # "sync" | "async" | "exit"
    control=None,          # RunControl - run-scoped control
    version="v1",          # "v1" (default) | "v2"
)
```

Two things worth knowing:

- `durability` is a **keyword-only** argument, so it goes *after* the config
  dict: `graph.invoke(inp, config, durability="async")`. Passing it
  positionally raises `TypeError: Pregel.invoke() takes from 2 to 3
  positional arguments but 4 were given`.
- `version="v2"` opts into the newer streaming/event protocol. Leave it at
  the default `"v1"` unless a doc you are reading specifically calls for
  `version="v2"` (the `stream_events(..., version="v3")` style in some
  examples belongs to that newer protocol).

---

## 10. Gotchas

1. **The checkpointer stores *all* threads.** With `InMemorySaver` that is a
   memory leak in a long-running process. Use a real checkpointer.
2. **State grows.** Every checkpoint stores the whole state. Long message
   histories mean big checkpoints. Trim messages with `RemoveMessage` (L04).
3. **`thread_id` collisions.** Two different users sharing a thread id will
   see each other's state. Generate ids per conversation.
4. **`get_state` needs a checkpointer.** Without one it raises.
5. **`update_state` is not a node.** It does not run your node's logic — it
   just writes values. If you need side effects, call them explicitly.

---

## 11. Checkpoint

- [ ] I know what a thread, checkpoint, checkpointer and superstep are.
- [ ] I can compile with a checkpointer and run a multi-turn conversation.
- [ ] I know `thread_id` is required once a checkpointer is present.
- [ ] I can use `get_state`, `get_state_history` and `update_state`.
- [ ] I understand time travel and its superstep-boundary limitation.
- [ ] I know `recursion_limit` counts supersteps, and I prefer
  `RemainingSteps` over catching `GraphRecursionError`.
- [ ] I know the difference between `InMemorySaver`, `SqliteSaver` and
  `PostgresSaver`, and that `MemorySaver` is the old name.

---

**Next → [L07 · Runtime context](./L07-runtime-context.md)** — `context_schema`,
`Runtime`, and why `configurable` is the old way.
