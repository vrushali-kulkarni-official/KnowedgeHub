# L08 · Parallelism, fan-in and `Send`

> **Module M51 (part 1) · ~2.5h**
> Goal: run work concurrently and merge the results correctly.

---

## 1. Fan-out with plain edges

Give a node multiple outgoing edges and they all fire in the same superstep.

```python
builder.add_edge(START, "search_web")
builder.add_edge(START, "search_docs")
builder.add_edge(START, "search_db")
```

All three run **concurrently** in superstep 1. Verified: two 0.4-second nodes
completed in 0.41 seconds total (L01).

> **They only actually run concurrently if the node functions are async, or
> if the runtime can use threads.** In a sync graph, LangGraph executes
> independent sync nodes in a thread pool, so they still overlap. If you are
> doing blocking I/O in an async graph, you will serialise them by accident
> — that is L09.

---

## 2. Fan-in — the join

```python
builder.add_edge(["search_web", "search_docs", "search_db"], "synthesize")
```

The list form of `add_edge` means: *`synthesize` runs after **all three**
have finished.* That is the join.

### The join needs a reducer

All three search nodes write to the same key (say `results`). They run in the
same superstep, so that key receives three writes at once.

```python
class State(TypedDict):
    results: Annotated[list[str], operator.add]   # <-- REQUIRED
```

Without the reducer you get:

```
InvalidUpdateError: At key 'results': Can receive only one value per step.
Use an Annotated key to handle multiple values.
```

**This is the single most common error in parallel LangGraph code**, and it is
the direct bridge from L04.

### The arrival-order problem

> **Parallel nodes finish in whatever order they finish. The reducer sees
> writes in that order, not in the order you declared the edges.**

This means:

```python
def merge(left, right): return left + right
```

gives you a list whose order is **not deterministic**. If you need a
deterministic order, sort in the joining node:

```python
def synthesize(state):
    ordered = sorted(state["results"], key=lambda r: r["rank"])
    return {"answer": build(ordered)}
```

Or give each parallel node a *different* key, and merge explicitly in the
joiner. That is often clearer than relying on a reducer.

```python
class State(TypedDict):
    web: list[str]
    docs: list[str]
```

```python
def synthesize(state):
    return {"answer": build(state["web"] + state["docs"])}   # deterministic order
```

**Rule of thumb:** if the order of the merged results matters, do not use an
append reducer — use distinct keys and merge explicitly.

---

## 3. The `Send` API — dynamic fan-out

Plain edges fan out to a **fixed** set of nodes. `Send` fans out to a
**dynamic** set, one task per item.

```python
from langgraph.types import Send

def continue_to_process(state: State) -> list[Send]:
    return [Send("process", {"doc": doc}) for doc in state["documents"]]

builder.add_conditional_edges("split", continue_to_process, ["process"])
```

`Send(node, arg)` means: *run node `process`, but give it `arg` as its
input, instead of the normal state.*

### The complete map-reduce example

```python
from typing import Annotated
from typing_extensions import TypedDict
import operator
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

class OverallState(TypedDict):
    topic: str
    subjects: list[str]
    jokes: Annotated[list[str], operator.add]     # fan-in reducer
    best_selected_joke: str

def generate_topics(state: OverallState) -> dict:
    return {"subjects": ["lions", "elephants", "penguins"]}

def generate_joke(state: OverallState) -> dict:
    # NOTE: this node receives ONLY {"subject": ...} because Send overrode
    # the input, not the whole state.
    return {"jokes": [jokes_for(state["subject"])]}

def continue_to_jokes(state: OverallState) -> list[Send]:
    return [Send("generate_joke", {"subject": s}) for s in state["subjects"]]

def best_joke(state: OverallState) -> dict:
    return {"best_selected_joke": "penguins"}

builder = StateGraph(OverallState)
builder.add_node("generate_topics", generate_topics)
builder.add_node("generate_joke", generate_joke)
builder.add_node("best_joke", best_joke)
builder.add_edge(START, "generate_topics")
builder.add_conditional_edges("generate_topics", continue_to_jokes, ["generate_joke"])
builder.add_edge("generate_joke", "best_joke")
builder.add_edge("best_joke", END)
graph = builder.compile()
```

**What happens:**

1. `generate_topics` runs → `subjects = ["lions", "elephants", "penguins"]`
2. The router returns three `Send` objects.
3. `generate_joke` runs **three times in parallel**, once per subject, each
   receiving only `{"subject": "<one>"}`.
4. Each run writes one joke to `jokes`. The `operator.add` reducer merges
   them.
5. `best_joke` runs after all three finish (the `add_edge` from
   `generate_joke` is a join — and because there are three *instances* of
   the same node, LangGraph waits for all of them).

### Critical detail: the input of a `Send` target

`Send("generate_joke", {"subject": s})` means the target node's `state` is
**exactly** `{"subject": s}` — *not* the parent state.

If the target node needs more than the sent payload, include it:

```python
[Send("process", {"doc": d, "style": state["style"], "depth": state["depth"]})
 for d in state["documents"]]
```

Or, better, give the target node a dedicated `input_schema` and send only
what it needs. The `Send` payload must satisfy the node's input schema.

### `Send` vs `Command`

```python
# via a conditional edge (classic)
def route(state): return [Send("process", {"doc": d}) for d in state["docs"]]
builder.add_conditional_edges("split", route, ["process"])

# via Command (modern style, same thing)
def split(state) -> Command:
    return Command(goto=[Send("process", {"doc": d}) for d in state["docs"]])
```

Both work. `Command` keeps the fan-out next to the node that produced the
work list, which reads better when the list is computed in that node.

---

## 3a. ⚠️ The static diagram and `Send` — a verified gotcha

This one cost me an afternoon, so it gets its own section. **Verified
numbers, not theory.**

### The problem

If a node is reached **only** via `Send`, LangGraph's *static* graph drawing
omits it **and every edge downstream of it**:

```python
b.add_node("dispatch", lambda s: Command(goto=[Send("worker", {"x": 1})]))
b.add_node("worker", worker)
b.add_edge("worker", "after")     # <- this edge VANISHES from the diagram
b.add_edge("after", END)
```

```
EDGES: [('__start__', 'dispatch'), ('dispatch', '__end__')]
```

`worker` and `after` are missing, and `dispatch` has a bogus
`dispatch -> __end__` edge. **The graph still runs perfectly** — the runtime
uses the real routing — but your diagram lies to you.

### The three patterns, measured

Same fan-out of **3** items, three ways of writing it:

| Pattern | `worker` runs | Edges drawn |
|---|---|---|
| `add_conditional_edges(src, router_returning_sends, ["worker"])` | **3×** ✅ | **full** ✅ |
| `Command(goto=[Send(...)])` only | 3× ✅ | **worker + downstream missing** ❌ |
| `Command(goto=[Send(...)])` + `add_conditional_edges(dispatch, router, ["worker"])` | 3× ✅ | **full** ✅ |

### ❌ The "documentation-only" static edge is a trap

The tempting fix — add `add_edge("dispatch", "worker")` so the diagram shows
it — **causes an extra execution**:

```
add_static=False: worker ran 2x  (correct)
add_static=True:  worker ran 3x  (one extra!)
```

A static edge is a *real* edge, not a comment. It schedules the node.

### ✅ The two correct patterns

**Pattern 1 — the official docs style (recommended).** The *router* returns
the `Send`s, and the path_map declares the target:

```python
def dispatch(state) -> dict:
    return {"work_items": [...]}

def route_research(state) -> list[Send]:
    return [Send("research", {"question": q}) for q in state["work_items"]]

builder.add_conditional_edges("dispatch", route_research, ["research"])
```

This is the pattern used in the LangGraph docs and in this course's
capstone. The `Send` list controls the **count**; the path_map controls the
**diagram**.

**Pattern 2 — keep the `Command`, declare the target separately.**

```python
def dispatch(state) -> Command:
    return Command(goto=[Send("research", {"question": q}) for q in state["items"]])

# Declare the target so the static graph can draw it.
builder.add_conditional_edges("dispatch", lambda s: [], ["research"])
```

The router returns `[]` (take no branch) but the path_map registers the
target, so the edge is drawn — and the `Command`'s `Send`s still control the
actual fan-out count. **Verified: 3 runs for 3 Sends, full diagram.**

### What to take away

> The static diagram describes **declared** edges. `Send` is **dynamic**
> routing. When the two disagree, trust the runtime (Studio, `stream_mode=
> "debug"`, `get_state_history`) over the picture.

For a full picture including subgraph internals:

```python
graph.get_graph(xray=True)          # expands subgraphs
graph.get_graph(xray=2)             # two levels deep
```

---

## 4. `defer=True` — run last

Sometimes a node must run *after* everything else in the superstep — for
example a cleanup or summary node that depends on parallel results.

```python
builder.add_node("summarize", summarize, defer=True)
```

A deferred node is scheduled at the **end** of the current superstep, after
all non-deferred nodes have finished. Use it when a node must see every
parallel branch's output.

> **Note:** `defer` is about *ordering within a superstep*, not about
> parallelism. It does not create a new superstep by itself.

---

## 5. A realistic pattern: parallel retrieval + synthesis

```python
class RagState(TypedDict):
    question: str
    web_results: Annotated[list[str], operator.add]
    doc_results: Annotated[list[str], operator.add]
    answer: str

def search_web(state): 
    return {"web_results": [hit(state["question"])]}

def search_docs(state):
    return {"doc_results": [chunk for chunk in retrieve(state["question"])]}

def synthesize(state):
    # explicit, deterministic merge order
    sources = state["web_results"] + state["doc_results"]
    return {"answer": llm_answer(state["question"], sources)}
```

Because `web_results` and `doc_results` are **different keys**, there is no
`InvalidUpdateError` and no order ambiguity.

---

## 6. The per-document map-reduce pattern

The most common real use of `Send`: process N documents independently, then
reduce.

```python
class DocState(TypedDict):
    documents: list[dict]
    summaries: Annotated[list[str], operator.add]
    report: str

def split(state) -> Command:
    return Command(goto=[Send("summarize_doc", {"doc": d}) for d in state["documents"]])

def summarize_doc(state) -> dict:
    # state here is {"doc": {...}} - only what Send provided
    return {"summaries": [llm_summary(state["doc"]["text"])]}

def build_report(state):
    return {"report": llm_report(state["summaries"])}
```

This scales to hundreds of documents, and each `summarize_doc` run is an
independent unit of work — perfect for a queue, a worker pool, or a batch
API.

---

## 7. When *not* to parallelise

- **The steps are not independent.** If B needs A's output, they are
  sequential. Parallelising them is a data race, not a speed-up.
- **The order matters.** Use explicit keys and merge, not an append reducer.
- **The writes collide.** Two parallel nodes writing the same key without a
  reducer is an error by design.
- **Rate limits.** 50 parallel calls will hit an API's rate limit. Use a
  smaller fan-out, or a queue-backed server.
- **Debuggability.** A 20-way fan-out makes traces hard to read. Split it.

---

## 8. Debugging parallelism

```python
# 1. See which nodes actually ran, in what order
for chunk in graph.stream(inp, stream_mode="updates"):
    print(chunk)

# 2. See the superstep boundaries and the task ids
for event in graph.stream(inp, stream_mode="debug"):
    if event["type"] == "task":
        print(event["step"], event["payload"]["name"], event["payload"]["id"])
```

Nodes in the same superstep share a `step` number. If you expected a
sequence and see the same step number, they ran in parallel.

```python
# 3. Inspect the checkpoint timeline
for snap in graph.get_state_history(config):
    print(snap.metadata.get("step"), snap.next)
```

---

## 9. Checkpoint

- [ ] I can create a fan-out with multiple `add_edge` calls and a fan-in with
      `add_edge([...], node)`.
- [ ] I know a fan-in requires a reducer on the shared key, and I recognise
      the `InvalidUpdateError` when it is missing.
- [ ] I know parallel arrival order is undefined and I know how to make the
      merge deterministic.
- [ ] I can write a `Send`-based map-reduce and explain what input the target
      node receives.
- [ ] I know `Send` payloads must satisfy the target's input schema.
- [ ] I know what `defer=True` does.
- [ ] I can list the cases where parallelising is the wrong call.

---

**Next → [L09 · Async and streaming](./L09-async-and-streaming.md)** — async
nodes, the blocking-in-async trap, and every stream mode.
