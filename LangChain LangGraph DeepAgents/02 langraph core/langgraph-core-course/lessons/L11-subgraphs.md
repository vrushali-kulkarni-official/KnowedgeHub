# L11 · Subgraphs

> **Module M50 (part 3) · ~2.5h**
> Goal: compose graphs, and understand the two completely different ways to
> wire a subgraph in.

---

## 1. Why subgraphs

A graph gets big. Subgraphs let you:

- **Encapsulate** a reusable workflow behind one node.
- **Reuse** the same pipeline in different parents.
- **Give a team** a boundary they can own.
- **Isolate state** so a sub-workflow's internals do not pollute the parent.

LangGraph subgraphs are real graphs — they have their own nodes, edges, state
and (optionally) their own checkpointer.

---

## 2. Two ways to add a subgraph — this is the key decision

| Pattern | When | State schemas |
|---|---|---|
| **Add the subgraph as a node** | Parent and subgraph **share state keys** | same keys; no wrapper needed |
| **Call the subgraph inside a node** | Schemas are **different**, or you need to transform state | you write the mapping |

> **Verified behaviour of pattern A** (subgraph as a node, shared keys):
> the subgraph's nodes read and write the parent's channels directly, and the
> parent's final state contains the subgraph's writes. No wrapper function
> required.

---

## 3. Pattern A — the subgraph as a node

```python
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END

class State(TypedDict):
    foo: str
    bar: str

# --- the subgraph ---
def subgraph_node_1(state: State) -> dict:
    return {"bar": "bar-value"}

def subgraph_node_2(state: State) -> dict:
    # reads the parent's 'foo' AND the 'bar' set by node 1
    return {"foo": state["foo"] + state["bar"]}

subgraph = (
    StateGraph(State)
    .add_node("subgraph_node_1", subgraph_node_1)
    .add_node("subgraph_node_2", subgraph_node_2)
    .add_edge(START, "subgraph_node_1")
    .add_edge("subgraph_node_1", "subgraph_node_2")
    .add_edge("subgraph_node_2", END)
    .compile()
)

# --- the parent ---
parent = (
    StateGraph(State)
    .add_node("parent_node_1", lambda s: {"foo": "hi " + s["foo"]})
    .add_node("subgraph_node", subgraph)      # <- the compiled subgraph
    .add_edge(START, "parent_node_1")
    .add_edge("parent_node_1", "subgraph_node")
    .add_edge("subgraph_node", END)
    .compile()
)

print(parent.invoke({"foo": "world", "bar": ""}))
# {'foo': 'hi worldbar-value', 'bar': 'bar-value'}
```

**What happened:** the parent's `foo` was `"hi world"`. The subgraph's first
node set `bar`. The subgraph's second node read *both* `foo` (from the
parent) and `bar` (from the sibling node) and wrote `foo` back. The parent
ends with the subgraph's writes.

### You can also share *some* keys

```python
class SubgraphState(TypedDict):
    foo: str      # shared with the parent
    bar: str      # private to the subgraph

class ParentState(TypedDict):
    foo: str
```

The subgraph can write a key the parent does not declare — it just does not
appear in the parent's output. (The parent's state channels are the
authority on what is visible at the top level.)

---

## 4. Pattern B — calling the subgraph inside a node

Use this when the schemas differ, or when you need to transform state on the
way in and out.

```python
class SubgraphState(TypedDict):
    bar: str

class ParentState(TypedDict):
    a: str
    out: str

subgraph = (
    StateGraph(SubgraphState)
    .add_node("s1", lambda s: {"bar": "hi " + s["bar"]})
    .add_edge(START, "s1")
    .add_edge("s1", END)
    .compile()
)

def call_subgraph(state: ParentState) -> dict:
    # transform parent state -> subgraph input
    result = subgraph.invoke({"bar": state["a"]})
    # transform subgraph output -> parent update
    return {"out": result["bar"]}

parent = (
    StateGraph(ParentState)
    .add_node("call_subgraph", call_subgraph)
    .add_edge(START, "call_subgraph")
    .add_edge("call_subgraph", END)
    .compile()
)

print(parent.invoke({"a": "world", "out": ""}))
# {'a': 'world', 'out': 'hi world'}
```

**Verified output:** `{'a': 'world', 'out': 'hi world'}`.

This is the pattern for **multi-agent systems**: each specialist agent gets
its own private message history, and the parent coordinates.

---

## 5. Namespace isolation

Each subgraph runs in its own **namespace** — a separate checkpoint
namespace, so the subgraph's internal state does not collide with the
parent's.

**Verified:** with `stream_mode="updates", subgraphs=True`:

```
ns= ()                            chunk= {'p1': {'foo': 'hi x'}}
ns= ('sub:69e49dd8-...',)         chunk= {'sub1': {'bar': 'bar-from-sub'}}
ns= ('sub:69e49dd8-...',)         chunk= {'sub2': {'foo': 'hi xbar-from-sub'}}
ns= ()                            chunk= {'sub': {'foo': 'hi xbar-from-sub', 'bar': 'bar-from-sub'}}
```

Without `subgraphs=True` you only see the parent's two events — the
subgraph's internals are invisible.

The namespace tuple is the *path* to the subgraph. Deeper nesting produces
longer tuples.

---

## 6. Subgraph persistence — three modes

This is the decision that trips people up, so read it carefully.

| Mode | `compile(checkpointer=...)` on the subgraph | Behaviour |
|---|---|---|
| **Stateful** (default) | the subgraph's own checkpointer | the subgraph persists its own state across calls, keyed by the parent's `thread_id` |
| **Stateless** | `checkpointer=None` | the subgraph starts fresh each time it is invoked |
| **Per-call** | `checkpointer=False` | a new checkpointer for each call |

**The question to ask:** *"should the billing expert subagent remember the
customer's earlier questions, or start fresh each time it's called?"*

- **Start fresh** → stateless. Simplest to reason about; this is the default
  choice for a reusable pipeline.
- **Remember across turns of the same conversation** → stateful.
- **Remember across the whole session but not forever** → per-call.

> **Important:** if the parent graph has a checkpointer and the subgraph is
> compiled *without* one, the subgraph still participates in the parent's
> checkpointing at the superstep level — it just does not keep its own
> private state between separate invocations.

---

## 7. How a subgraph inherits `thread_id` and config

The subgraph runs with the parent's config, including `thread_id`. That is
why a stateful subgraph's memory is scoped to the conversation.

If the subgraph needs a **different** thread (e.g. a long-lived background
job), pass an explicit config:

```python
def call_subgraph(state):
    return subgraph.invoke(
        {"x": state["x"]},
        {"configurable": {"thread_id": f"job-{state['job_id']}"}},
    )
```

---

## 8. Shared state vs shared *schema* — a checklist

Before adding a subgraph, answer:

1. **Do parent and subgraph share state keys?**
   - Yes → Pattern A (as a node). Much less code.
   - No → Pattern B (call in a node). You write the mapping.
2. **Does the subgraph need to remember things between calls?**
   - No → stateless.
   - Yes → stateful, and think about the thread id.
3. **Do you need to see inside the subgraph?**
   - Yes → `subgraphs=True` in the stream, and use Studio (M53) which
     renders nested graphs.

---

## 9. Common mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| Compiling the parent *inside* the subgraph builder | confusing errors | compile the subgraph first, then `add_node("name", subgraph)` |
| Forgetting the subgraph has its own `START`/`END` | the subgraph does nothing | wire the subgraph fully before compiling it |
| Sharing a key the parent does not declare | the value vanishes at the top level | declare it in the parent, or use Pattern B and map explicitly |
| Assuming a stateless subgraph remembers | "it forgot the last message" | give it a checkpointer, or pass state explicitly |
| Expecting `stream_mode="updates"` to show subgraph internals | you only see the parent | pass `subgraphs=True` |

---

## 10. Checkpoint

- [ ] I can choose between "subgraph as a node" and "call the subgraph in a
      node" based on whether the schemas share keys.
- [ ] I can write both patterns and explain the state flow in each.
- [ ] I understand namespace isolation and how to see inside a subgraph in a
      stream.
- [ ] I know the three persistence modes and can pick one deliberately.
- [ ] I know the subgraph inherits the parent's `thread_id` unless told
      otherwise.

---

**Next → [L12 · Fault tolerance, timeouts and caching](./L12-fault-tolerance.md)**
— retries, per-node timeouts, error handlers and node caching.
