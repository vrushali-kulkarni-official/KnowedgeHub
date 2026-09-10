# Module 08 — Subgraphs & Multi-Agent Systems

## Prerequisites

- Modules 04–07 (you have a persistent, streaming, HITL-capable ReAct agent)

## Why this module matters

Single-agent ReAct loops hit ceilings. Real SaaS agents need specialists: a researcher, a coder, a writer, a critic. They need to coordinate. They need to hand off work.

This module teaches you the three core multi-agent patterns in LangGraph:
1. **Subgraphs** — encapsulate a piece of behavior.
2. **Supervisor** — a router that delegates to specialists.
3. **Handoffs** — agents that route control to each other.

## Learning objectives

By the end of this module you can:

1. Build a subgraph and add it as a node in a parent graph.
2. Share state between parent and subgraph.
3. Implement the supervisor pattern.
4. Implement handoffs with `Command(goto=...)`.
5. Implement the network pattern.
6. Choose the right pattern for a given problem.
7. Debug multi-agent traces (with LangSmith in Module 10).

---

## 8.1 Subgraphs

A subgraph is just a `CompiledGraph` used as a node in another graph.

### 8.1.1 The simplest subgraph

```python
# Subgraph
def summarize_node(state):
    return {"summary": llm.invoke(state["text"]).content}

summarizer = (
    StateGraph(SummarizerState)
    .add_node("summarize", summarize_node)
    .add_edge(START, "summarize")
    .add_edge("summarize", END)
    .compile()
)

# Parent
parent = (
    StateGraph(ParentState)
    .add_node("summarizer", summarizer)    # compiled graph as a node
    .add_edge(START, "summarizer")
    .add_edge("summarizer", END)
    .compile()
)
```

That's it. The parent's `summarizer` node is the entire compiled subgraph.

### 8.1.2 State sharing between parent and subgraph

The subgraph has its own state. To pass data, the parent state must contain the subgraph's input fields, and the subgraph must declare an input schema.

```python
# Subgraph declares what it reads and writes
summarizer = (
    StateGraph(SummarizerState, input=SummarizerInput, output=SummarizerOutput)
    ...
    .compile()
)

# Parent state must include both its own fields AND the subgraph's input fields
class ParentState(TypedDict):
    text: str                      # passed to summarizer
    summary: str                   # filled by summarizer
    # ... other parent fields
```

When the parent invokes the subgraph, the matching fields are read from / written to the parent's state automatically.

### 8.1.3 Why use subgraphs

- **Encapsulation:** each subgraph is a self-contained unit with its own state, prompts, tools.
- **Reuse:** the same `summarizer` can be a node in multiple parents.
- **Testability:** test the subgraph in isolation.
- **Clarity:** the parent graph is shorter and clearer when complex pieces are abstracted.

---

## 8.2 The supervisor pattern

The most common multi-agent pattern: a supervisor routes tasks to specialist agents.

```
                ┌──────────────────┐
                │   supervisor     │
                │   (LLM router)   │
                └──────────────────┘
                   │       │       │
                   ▼       ▼       ▼
              ┌─────┐ ┌─────┐ ┌─────┐
              │research│ │writer│ │critic│
              └─────┘ └─────┘ └─────┘
                   │       │       │
                   └───────┴───────┘
                           │
                           ▼
                       supervisor
```

```python
from typing import Literal
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command

class State(TypedDict):
    messages: list
    next: str

def supervisor(state: State) -> Command:
    # LLM picks the next agent
    response = supervisor_llm.invoke(state["messages"] + [
        SystemMessage(content="Route to: research, writer, or critic. Say FINISH when done.")
    ])
    next_agent = parse_agent_choice(response.content)
    return Command(goto=next_agent)

def research_agent(state: State) -> Command:
    result = research_llm.invoke(state["messages"])
    return Command(
        goto="supervisor",
        update={"messages": [result]}
    )

# similar for writer, critic

builder = StateGraph(State)
builder.add_node("supervisor", supervisor)
builder.add_node("research", research_agent)
builder.add_node("writer", writer_agent)
builder.add_node("critic", critic_agent)
builder.add_edge(START, "supervisor")
graph = builder.compile()
```

`Command(goto=...)` is the handoff primitive. The supervisor sends control to `research`; research does its work and returns control to `supervisor`.

### 8.2.1 Ending the loop

The supervisor's router should return `END` (or a `Command(goto=END)`) when the task is complete. The model is taught this via prompt.

---

## 8.3 Handoffs

A handoff is when one agent passes control to another agent with some context.

```python
def triage_agent(state) -> Command:
    # decide
    if state["issue_type"] == "billing":
        return Command(
            goto="billing_agent",
            update={"context": "Customer was transferred from triage. Issue: billing."}
        )
    return Command(goto="support_agent")
```

`Command` lets you:
- `goto=...` — which node runs next.
- `update={...}` — state update before continuing.
- `graph=Command.PARENT` — bubble up to parent graph (escape a subgraph).

### 8.3.1 Handoffs vs subgraphs

- **Subgraph:** parent calls subgraph; subgraph runs; control returns to parent. Hierarchy.
- **Handoff:** agent decides to pass control to a peer. Network.

Use subgraphs when the call site is deterministic ("always do this after that"). Use handoffs when the routing is dynamic.

---

## 8.4 The network pattern

A flat graph where any agent can hand off to any other. No supervisor. Each agent has its own routing logic.

```
  agent_a ←→ agent_b
     ↑          ↓
     └──── agent_c
```

Implementation: each agent returns `Command(goto=...)`. The graph compiles with all nodes; edges are implicit in the `goto` values.

```python
class State(TypedDict):
    messages: list
    next: str

def agent_a(state) -> Command:
    if should_handoff_to_b(state):
        return Command(goto="agent_b")
    return Command(goto=END)

# similar for b, c

builder = StateGraph(State)
builder.add_node("agent_a", agent_a)
builder.add_node("agent_b", agent_b)
builder.add_node("agent_c", agent_c)
builder.add_edge(START, "agent_a")
# no static edges between a, b, c — they route via Command
graph = builder.compile()
```

**Warning:** networks are harder to debug. Use them only when the topology is genuinely dynamic.

---

## 8.5 Multi-agent communication patterns

| Pattern | Topology | When to use |
|---|---|---|
| Subgraph | Hierarchy | Encapsulate a workflow used in many places |
| Supervisor | Star | Clear role split; central routing |
| Handoff | Network | Truly dynamic peer-to-peer |
| Hierarchical supervisor | Tree of supervisors | Large systems with subsystems |

For 90% of SaaS agents, **supervisor + subgraphs** is the right call.

---

## 8.6 Tool design for multi-agent

The supervisor is itself an LLM. Its "tools" are the other agents.

A clean way to think of it: **agents as tools**.

```python
@tool
def research_agent(query: str) -> str:
    """Run the research agent on a query and return its findings."""
    result = research_graph.invoke({"messages": [HumanMessage(content=query)]})
    return result["messages"][-1].content

supervisor_llm_with_agents = llm.bind_tools([research_agent, writer_agent, critic_agent])
```

The supervisor then uses the ReAct loop: it calls a "tool" (which is a full subgraph), gets the result, decides what to do next.

This is conceptually simpler than `Command(goto=...)` and works well for many use cases.

---

## 8.7 State in multi-agent systems

Each agent typically needs:
- The full message history (for context).
- A role-specific prompt.
- Optionally, agent-specific scratchpads (todos, draft outputs).

**Patterns:**

- **Shared state, role-tagged messages:** add a `name` field on each `AIMessage`. Each agent reads messages with its own name.
- **Per-agent state via subgraphs:** each agent is a subgraph with its own state; the parent maintains `messages` only.

---

## 8.8 Debugging multi-agent

This is hard. Tips:

- **Tag every LLM call with the agent name** (via metadata or `tags` on the model call).
- **Stream `updates` mode** — you'll see which node ran when.
- **LangSmith (Module 10) traces** show the full call tree.
- **Keep prompts distinct** — same model, different system messages per agent.
- **Cap iterations** at every level.

---

## 8.9 Multi-agent pitfalls

| Pitfall | Fix |
|---|---|
| Infinite handoffs | Cap iterations; explicit termination prompt |
| Agents stepping on each other | Role isolation; clear contract per agent |
| State explosion | Use subgraphs to scope state |
| Cost multiplies | Each agent = LLM calls; budget them |
| Hard to test | Test each subgraph independently |
| Inconsistent style across agents | Same system prompt template; vary only role |

---

## Hands-on project

**Goal:** Build a "research + write + review" multi-agent team.

1. **Three subgraphs:**
   - `researcher`: searches docs, returns a summary.
   - `writer`: takes a brief, writes a draft.
   - `critic`: reviews a draft, returns a verdict + suggestions.
2. **Supervisor graph:** orchestrates them. Routes: `researcher → writer → critic → (writer if rejected, END if approved)`.
3. **Use `Command(goto=...)`** for routing.
4. **Test:** input a topic. The team should research, draft, and (potentially) revise.
5. **Stream `updates`** and watch the agent transitions.

## Exercises

1. **Convert the supervisor** to the "agents as tools" pattern. Compare both versions.
2. **Add a human reviewer** (HITL) that can intercept after `critic` to override its verdict.
3. **Build a hierarchical supervisor:** top-level "personal assistant" routes to "work agent" or "home agent," each with its own sub-supervisor.
4. **Streaming observability:** tag each agent's LLM calls. Build a trace view in your UI that shows agent transitions.
5. **Loop prevention:** add a hard rule: a draft can be revised at most 3 times. After 3, escalate to a human.

## Production checklist

- [ ] Every agent has a clear, distinct role and prompt.
- [ ] Iterations capped at every level.
- [ ] State scopes are intentional (subgraphs for isolation, parent for shared context).
- [ ] Cost per task estimated and bounded.
- [ ] Each agent independently testable.
- [ ] LangSmith (or equivalent) tracing on for debugging.
- [ ] Termination path is unambiguous (no infinite handoffs).

## Key takeaways

- Subgraphs = encapsulation, hierarchy, reuse.
- Supervisor = central router; handoffs = peer-to-peer.
- For most SaaS agents, supervisor + subgraphs is the right call.
- `Command(goto=..., update=...)` is the handoff primitive.
- Multi-agent systems multiply cost. Budget deliberately.

## Resources

- LangGraph multi-agent: https://langchain-ai.github.io/langgraph/concepts/multi_agent/
- `Command` reference: https://langchain-ai.github.io/langgraph/reference/types/#langgraph.types.Command
- Anthropic's "Building effective agents" essay: https://www.anthropic.com/research/building-effective-agents
