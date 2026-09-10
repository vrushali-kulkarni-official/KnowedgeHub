# Module 01 — LangGraph Mental Model

## Prerequisites

- Module 00 complete (you have a working dev env, can call an LLM via LangChain, can define a tool).

## Why this module matters

Before writing a single line of graph code, you need the **mental model**. Without it, every LangGraph concept in later modules will feel arbitrary. With it, you'll be able to read any LangGraph program and predict its behavior.

This module is theory-heavy on purpose. It will pay off in Modules 02–16.

## Learning objectives

By the end of this module you can:

1. Explain what a LangGraph "graph" actually is, in graph-theory terms.
2. Differentiate LangGraph from LCEL chains, raw function calls, and other agent frameworks.
3. Identify when a problem is and isn't a good fit for LangGraph.
4. Describe the three primitives: **state**, **nodes**, **edges**.
5. Read a LangGraph diagram and trace execution step by step.

---

## 1.1 The big idea: graphs for LLM apps

### 1.1.1 A graph is nodes + edges + state

Forget AI for a second. A directed graph has:

- **Nodes** — units of work. Each one is a pure-ish function: takes the current state, returns an update.
- **Edges** — connections. They say "after node A, go to node B." Some edges are *conditional*: "after A, go to B or C depending on the state."
- **State** — the shared data that flows through the graph. It's the "memory" of the computation.

```
    ┌──────┐    always    ┌──────┐    always    ┌──────┐
───▶│ Node1│─────────────▶│ Node2│─────────────▶│ Node3│───▶ END
    └──────┘              └──────┘              └──────┘
         │                    │
         │  if state.x>0      │  if state.y=="retry"
         ▼                    ▼
    ┌──────┐              ┌──────┐
    │ AltA │              │ AltB │
    └──────┘              └──────┘
```

That's it. **LangGraph is a Python library for building and running these graphs where the nodes are LLM calls, tool calls, or arbitrary Python, and the state is a typed dict that gets persisted.**

### 1.1.2 The "stateful" part

Most "agent" frameworks treat each LLM call as independent. LangGraph treats the *whole conversation* as one ongoing computation against a state object.

This matters because:
- Memory is structural, not a hack.
- Human approval can pause the graph and resume later.
- Multiple actors (LLM, tools, humans) can be orchestrated explicitly.
- You can rewind, branch, and inspect state at any point.

### 1.1.3 The "multi-actor" part

A LangGraph app isn't just "LLM calls a tool." It's:

- LLM agents
- Tool nodes
- Human reviewers (HITL)
- Other agents (multi-agent)
- Deterministic business logic
- External systems via APIs

All of them are just **nodes**. The graph is the orchestrator.

---

## 1.2 LangGraph vs the alternatives

### 1.2.1 vs LCEL chains

LCEL (LangChain Expression Language) chains look like:

```python
chain = prompt | llm | parser
```

Chains are **DAGs** (no cycles) where data flows one way. Great for pipelines. Awful for:

- Loops (agent → tool → agent again)
- Branching based on intermediate results
- Multi-turn conversations with memory
- Human-in-the-loop pauses

LangGraph is "chains + cycles + persistence + control flow."

### 1.2.2 vs raw Python with if/else

You can write an agent in 50 lines of Python. The problems:

- No persistence out of the box.
- No inspection / time travel.
- No streaming.
- No standardized way to add human approval.
- No multi-agent composition.
- You'll reinvent the wheel badly.

Use LangGraph when the wheel is what you're standing on.

### 1.2.3 vs other agent frameworks (Autogen, CrewAI, etc.)

Each has its opinions. LangGraph's opinions:

- **Explicit > implicit.** You draw the graph, you see the control flow.
- **State > message passing.** State is typed and inspectable.
- **Production > prototype.** Persistence, streaming, deployment are first-class.
- **Vendor-neutral.** Built on LangChain's model abstraction.
- **Composable.** Subgraphs, handoffs, multi-agent — all just more graphs.

If you want maximum expressiveness and production-readiness, LangGraph is a strong default. Deep Agents (later) is the opinionated layer on top for the "give an agent a goal and let it figure it out" pattern.

---

## 1.3 When to use LangGraph (and when not to)

### 1.3.1 Use LangGraph when:

- ✅ You need a **loop**: agent → tool → agent.
- ✅ You need **branching**: "if the search returned nothing, try a different query."
- ✅ You need **persistence**: conversations, time travel, resume.
- ✅ You need **human-in-the-loop**.
- ✅ You have **multiple agents or actors** that coordinate.
- ✅ You want to **deploy** this as a long-running service with a Studio UI.

### 1.3.2 Don't use LangGraph when:

- ❌ It's a single LLM call. Use `llm.invoke()`.
- ❌ It's a fixed pipeline with no cycles. Use LCEL.
- ❌ You're prototyping a UI before you know the logic. Sketch in code first.
- ❌ The "graph" is just a rephrasing of normal control flow. Don't add a framework to feel smart.

### 1.3.3 The decision flowchart

```
Do you have multiple steps?
├── No  → Just call the LLM.
└── Yes
    ├── Are there cycles (loops)?
    │   ├── No  → LCEL chain.
    │   └── Yes
    │       ├── Do you need persistence / HITL / multi-agent?
    │       │   ├── No  → LangGraph (it's still the cleanest way to do loops)
    │       │   └── Yes → LangGraph
    │       └── Is the agent a single "do whatever it takes" goal-seeking system?
    │           └── Yes → Deep Agents (built on LangGraph)
```

---

## 1.4 The three primitives in detail

### 1.4.1 State

State is a typed dict. You define its shape (Module 02 is the deep dive). The key idea:

- The state is **passed to every node**.
- Each node returns **a partial update** (a dict of only the keys it wants to change).
- LangGraph **merges** that update into the state using **reducers** (one per key).
- After merging, the new state is passed to the next node.

```python
class State(TypedDict):
    messages: list          # default reducer: overwrite
    messages: Annotated[list, add_messages]   # reducer: append
    user_id: str            # default reducer: overwrite
```

### 1.4.2 Nodes

A node is a callable that takes the current state and returns a partial update.

```python
def my_node(state: State) -> dict:
    # do work
    return {"messages": [new_message]}
```

Three common node types:

- **LLM nodes** — call the model, return an `AIMessage`.
- **Tool nodes** — `ToolNode` from `langgraph.prebuilt`, executes tool calls.
- **Logic nodes** — pure Python: search a DB, transform data, call an API, decide a route.

### 1.4.3 Edges

Edges define control flow.

- **Normal edges** — unconditional: `add_edge("A", "B")`.
- **Conditional edges** — function maps state to next node: `add_conditional_edges("A", route_fn)`.
- **Entry edges** — `add_edge(START, "A")`.
- **Exit** — `add_edge("Z", END)`.

That's the whole API surface for edges. Module 03 goes deep on patterns.

---

## 1.5 Anatomy of a LangGraph program

Here's a labeled diagram of a tiny but realistic graph:

```
                  ┌──────────────────────────────────────┐
                  │ State: { messages, next_step, ... }  │
                  └──────────────────────────────────────┘
                                   │
        ┌──────────────────────────┴──────────────────────────┐
        │                                                     │
        ▼                                                     ▼
   ┌─────────┐   tool_calls?   ┌──────────────┐   answer?  ┌─────────┐
   │  llm    │ ──────────────▶ │  tool_node   │            │ final   │
   │ (agent) │                 │ (run tools)  │            │ answer  │
   └─────────┘ ◀────────────── └──────────────┘            └─────────┘
        │                                                     ▲
        │ "no tool calls"                                      │
        └─────────────────────────────────────────────────────┘
```

Reading top-to-bottom: state flows in, LLM thinks, if it wants tools we execute them and loop back, if not we end.

This is the **classic ReAct loop**. You'll build it in Module 04.

---

## 1.6 The compile / invoke / stream lifecycle

Every LangGraph program follows the same shape:

```python
# 1. Define
builder = StateGraph(State)
builder.add_node(...)
builder.add_edge(...)
graph = builder.compile()       # validates the graph

# 2. Run
result = graph.invoke({"messages": [...]})
# or
for event in graph.stream({"messages": [...]}, stream_mode="values"):
    ...
# or
async for event in graph.astream(...):
    ...
```

`compile()` is critical:
- It validates that all edges point to real nodes.
- It injects runtime infrastructure (checkpointers, interrupt points, etc.).
- It produces a `Pregel` object (yes, named after Google's Pregel — LangGraph uses BSP-style execution under the hood).

The graph is **immutable** post-compile. To change it, rebuild and recompile.

---

## 1.7 Mental model exercise: trace this

Given this graph:

```python
class State(TypedDict):
    n: int

def inc(state): return {"n": state["n"] + 1}
def double(state): return {"n": state["n"] * 2}
def route(state): return "double" if state["n"] < 10 else "inc"

g = (
    StateGraph(State)
    .add_node("inc", inc)
    .add_node("double", double)
    .add_edge(START, "inc")
    .add_conditional_edges("inc", route)
    .add_edge("double", "inc")
    .compile()
)
g.invoke({"n": 1})
```

Without running it: trace the values of `n` step by step. What's the final value? (Answer in Exercises.)

---

## Hands-on project

**Goal:** Build a tiny "echo with branching" graph to internalize the model.

1. Define a `State` with one field: `count: int`.
2. Add three nodes: `increment`, `double`, `triple`.
3. Add a conditional edge from `increment` that routes to `double` if `count` is even, else `triple`.
4. After `double`/`triple`, route back to `increment`.
5. Compile. Invoke with `count=1`. Print the sequence of `count` values.
6. Add a max-iterations guard (use a `steps` field, increment each node, end when `steps >= 10`).

## Exercises

1. **Trace M1.7 by hand**, then run it. Did you predict correctly?
2. **Convert M1.7 to an LCEL chain.** Why does it become awkward or impossible?
3. **Draw a graph diagram** for: "User asks a question. If it's about weather, call weather tool. If it's about math, call calculator. Otherwise just answer. Loop if the tool result indicates an error."
4. **Identify three "this should be a LangGraph" cases** and three "this should be plain Python" cases in your current AI SaaS plans. Justify each.

## Production checklist

- [ ] You can sketch a graph on paper before writing code.
- [ ] You know which problems in your SaaS need a graph vs a chain vs raw LLM call.
- [ ] You understand that `compile()` is the validation step.

## Key takeaways

- LangGraph = state + nodes + edges. That's it. Everything else is composition.
- The state is **typed** and **persistent** (with a checkpointer). This is the superpower.
- Use LangGraph when you need loops, branching, persistence, HITL, or multi-actor coordination. Skip it otherwise.
- The lifecycle is always: **define → compile → invoke/stream**.

## Resources

- LangGraph concepts: https://langchain-ai.github.io/langgraph/concepts/
- "Why LangGraph" essay: https://blog.langchain.com/langgraph/
- LangGraph is to agents as Airflow is to data pipelines (community analogy worth understanding).
