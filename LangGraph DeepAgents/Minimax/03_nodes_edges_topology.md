# Module 03 — Nodes, Edges & Topology

## Prerequisites

- Module 02 (state schemas, reducers, `MessagesState`)

## Why this module matters

State is the data. Nodes and edges are the **control flow**. This is where LangGraph goes from "data structure" to "engine." You'll learn the four graph shapes you'll reuse forever: linear, branching, looping, and fan-out/fan-in.

## Learning objectives

By the end of this module you can:

1. Write node functions and understand the runtime contract (sync/async, signature, return types).
2. Use all four edge types: `START`, normal, conditional, `END`.
3. Use `add_conditional_edges` with a router function and a path map.
4. Implement the "agent loop" pattern (the LLM-as-router).
5. Use the `Send` API for map-reduce and dynamic fan-out.
6. Compose the four core graph shapes and know when to use each.
7. Add a max-iterations guard safely.

---

## 3.1 Node fundamentals

### 3.1.1 The node contract

A node is **any callable** that takes the current state (and optionally runtime) and returns a dict update.

```python
def my_node(state: State) -> dict:
    return {"some_field": "new_value"}
```

You can also accept `config` and `runtime`:

```python
from langgraph.runtime import Runtime

def my_node(state: State, runtime: Runtime) -> dict:
    user_id = runtime.config["configurable"].get("user_id")
    return {"some_field": user_id}
```

### 3.1.2 Sync vs async

Nodes can be sync or async. LangGraph detects the type and runs them on the appropriate loop.

```python
async def my_async_node(state: State) -> dict:
    result = await some_http_call(...)
    return {"data": result}
```

**Rule:** Use async when the node does I/O (HTTP, DB, file). Use sync when it's pure CPU. Mixed graphs are fine.

### 3.1.3 The return contract

The return value must be JSON-serializable-friendly. Specifically:

- Dicts, lists, strings, numbers, booleans, None.
- LangChain `BaseMessage` subclasses.
- Pydantic models with `.model_dump()`.
- Custom classes need reducers that know how to merge them.

**Don't** return a class instance that doesn't know how to merge itself.

### 3.1.4 Nodes that don't update state

A node can return an empty dict. It's a "do something side-effecty" node.

```python
def log_node(state: State) -> dict:
    logger.info("reached here", extra={"step": state.get("step_count")})
    return {}
```

But — if you have side effects, also consider the `writer` pattern (Module 02 §2.6) for observability.

### 3.1.5 Decorating nodes

Nodes are just functions. Decorate them freely.

```python
@functools.lru_cache(maxsize=128)
def expensive_node(state: State) -> dict:
    ...
```

Just remember: with persistence, you'll see the same node called with the same state. Caching is fine and often helpful.

---

## 3.2 Edges

### 3.2.1 The four edge operations

```python
from langgraph.graph import START, END, StateGraph

builder = (
    StateGraph(State)
    .add_node("a", node_a)
    .add_node("b", node_b)
    .add_node("c", node_c)

    # 1. Entry
    .add_edge(START, "a")

    # 2. Normal: a → b
    .add_edge("a", "b")

    # 3. Conditional: b → c OR END
    .add_conditional_edges(
        "b",
        route_fn,                 # (state) -> str
        {"continue": "c", "stop": END}   # path map (optional but recommended)
    )

    # 4. Exit
    .add_edge("c", END)
)
```

### 3.2.2 Normal edges

```python
.add_edge("a", "b")
```

After `a` finishes, go to `b`. That's it. Use for deterministic pipeline steps.

### 3.2.3 Conditional edges

```python
def route(state: State) -> str:
    if state["needs_more"]:
        return "search"
    return "answer"

.add_conditional_edges("decide", route)
```

The router returns a **node name** (a string). The path map is optional but recommended — it makes refactors safe.

```python
.add_conditional_edges(
    "decide",
    route,
    {"search": "search_node", "answer": "answer_node"}
)
```

### 3.2.4 `END`

`END` is a sentinel. Edges to `END` terminate that branch.

```python
.add_edge("answer", END)
```

A node with no outgoing edges doesn't auto-end. You need an explicit `END` edge (or a conditional that returns `END`).

### 3.2.5 Conditional entry points

You can have multiple entry nodes. The router picks which one.

```python
.add_conditional_edges(START, classify_query, {"weather": "weather", "math": "math"})
```

---

## 3.3 The four core graph shapes

### 3.3.1 Linear (pipeline)

```
START → A → B → C → END
```

Use for: deterministic transformations.

```python
.add_edge(START, "a").add_edge("a", "b").add_edge("b", "c").add_edge("c", END)
```

### 3.3.2 Branching (router)

```
START → Classify → (A | B | C) → Merge → END
```

Use for: routing to specialist handlers.

```python
def classify(s): return s["topic"]
.add_conditional_edges("classify", classify, {"weather": "a", "math": "b", "other": "c"})
```

### 3.3.3 Looping (the agent loop)

```
START → Agent → (Tool | END)
                ↑     |
                └─────┘ (loop back to Agent)
```

Use for: the ReAct pattern (Module 04 is the full version).

```python
def should_continue(s) -> str:
    last = s["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return END

.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
.add_edge("tools", "agent")
```

### 3.3.4 Fan-out / Fan-in (map-reduce)

```
START → Map → [Worker1 | Worker2 | Worker3] → Reduce → END
```

Use the `Send` API for dynamic fan-out (next sub-module).

---

## 3.4 The `Send` API: dynamic fan-out

Static fan-out (3 workers, fixed):

```python
.add_edge("map", "worker_1")
.add_edge("map", "worker_2")
.add_edge("map", "worker_3")
.add_edge(["worker_1", "worker_2", "worker_3"], "reduce")
```

Dynamic fan-out (N workers depending on state): use `Send`.

```python
from langgraph.types import Send

def fan_out(state: State):
    return [Send("worker", {"item": item}) for item in state["items"]]

.add_conditional_edges("map", fan_out, ["worker"])
.add_edge("worker", "reduce")
```

`Send(node_name, state_subset)` runs that node with the given state subset. Each `Send` runs in parallel (in the same superstep).

**Use case:** "for each document in the result set, summarize it in parallel, then combine summaries."

---

## 3.5 Max iterations guard

Loops need termination. Two patterns:

### 3.5.1 Counter in state

```python
class State(TypedDict):
    step_count: int

def agent(state: State) -> dict:
    return {"step_count": state.get("step_count", 0) + 1, "messages": [...]}

def should_continue(s: State) -> str:
    if s["step_count"] >= 10:
        return END
    if needs_tool(s):
        return "tools"
    return END
```

### 3.5.2 `recursion_limit` (parameter)

```python
graph.invoke(input, config={"recursion_limit": 25})
```

Hard limit. Beyond this, LangGraph raises. Use as a safety net, not the primary control.

---

## 3.6 The "LLM-as-router" pattern

Most production agents are loops. The LLM itself decides what to do next, and the routing function reads its decision.

```python
def agent_node(state: State) -> dict:
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}

def route_after_agent(state: State) -> str:
    last = state["messages"][-1]
    if last.tool_calls:
        return "tools"
    return END

g = (
    StateGraph(State)
    .add_node("agent", agent_node)
    .add_node("tools", tool_node)
    .add_edge(START, "agent")
    .add_conditional_edges("agent", route_after_agent, {"tools": "tools", END: END})
    .add_edge("tools", "agent")
    .compile()
)
```

This is the canonical ReAct loop. Module 04 makes it real.

---

## 3.7 Visualizing graphs

```python
from IPython.display import Image, display
display(Image(g.get_graph().draw_mermaid_png()))
```

You can also export to a file:

```python
png = g.get_graph().draw_mermaid_png()
with open("graph.png", "wb") as f:
    f.write(png)
```

Module 09 (LangGraph Studio) gives you an interactive version.

---

## 3.8 Common topology pitfalls

| Pitfall | Symptom | Fix |
|---|---|---|
| Node with no outgoing edges, but graph doesn't end | Hang | Add an `END` edge (or conditional to `END`) |
| Returning `END` string vs `langgraph.graph.END` | Import error or wrong routing | Always import `END` and use it |
| Fan-out without `Send` API | All workers get same state | Use `Send` for per-item state |
| `recursion_limit` too low | `RecursionError` in production | Bump to a sane number (50–100) and rely on logic |
| Loops without iteration guard | Infinite loop | Always have a max-step guard |
| Path map typos in `add_conditional_edges` | Silent fallthrough to `__end__` | Always provide explicit path map |

---

## Hands-on project

**Goal:** Build a 4-shape "graph sampler" — one subgraph per shape, callable from a dispatcher.

1. **Linear:** `text → uppercase → reverse → done`
2. **Branching:** `classify_intent → [greet | math | weather] → log_topic`
3. **Looping:** `agent → tool_executor → agent` (mock tool, no LLM needed yet)
4. **Fan-out:** `split_input → [worker_1, worker_2, worker_3] → combine`
5. Wrap them in a dispatcher that picks the right one based on a top-level `mode` field.

## Exercises

1. **Trace a graph.** Given the agent-loop code in 3.6, with a `step_count` of 0 and a tool call: what's the order of node executions?
2. **Refactor 3.5.1's counter** to use `operator.add` so multiple parallel nodes can increment it without conflict.
3. **Build a "retry on error" loop.** If a node raises, route to a `retry` node that increments a counter and loops back. After 3 retries, go to `END`.
4. **`Send` challenge:** given a state with a list of URLs, fan out to a "fetch" worker per URL, then reduce the results into a single list.
5. **Convert a real piece of your SaaS backend** to one of these four shapes. Which one? Why?

## Production checklist

- [ ] Every loop has an explicit termination condition.
- [ ] `recursion_limit` is set to a sane value (50–100) on every `invoke`/`stream`.
- [ ] All conditional edges have explicit path maps.
- [ ] Heavy I/O nodes are `async`.
- [ ] You can draw your graph in Mermaid and it matches the code.

## Key takeaways

- Nodes are callables. Edges are the four types. State is what flows.
- The four shapes: linear, branching, looping, fan-out. Most graphs are combinations.
- The LLM-as-router pattern is the heart of every agent.
- `Send` is the API for dynamic fan-out. Use it for map-reduce.
- Always have a termination condition on every loop.

## Resources

- LangGraph graph API: https://langchain-ai.github.io/langgraph/reference/graphs/
- `Send` API: https://langchain-ai.github.io/langgraph/concepts/low_level/#send
- `add_conditional_edges` reference: same page
- Mermaid for diagrams: https://mermaid.js.org/
