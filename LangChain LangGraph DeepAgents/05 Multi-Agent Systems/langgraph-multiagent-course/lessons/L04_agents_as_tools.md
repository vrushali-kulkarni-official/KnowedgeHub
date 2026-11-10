# L04 — Agents-as-Tools: The Modern Supervisor

**Module:** M67 · **Time:** ~2h · **Example:** `examples/ex06_agents_as_tools.py`, `examples/ex07_structured_routing.py`

---

## 0. Why this lesson exists: `langgraph-supervisor` is dead

The old way to build a supervisor team was the `langgraph-supervisor`
package. Here is its status as of **2026-11-05**, checked against PyPI:

| package | latest version | last release | status |
|---|---|---|---|
| `langgraph-supervisor` | 0.0.31 | **2025-11-19** | ~1 year stale; built on the pre-v1 agent API |
| `langgraph-swarm` | 0.1.0 | **2025-12-04** | ~11 months stale; built on the **deprecated** `create_react_agent` |
| `langgraph` | 1.2.20 | 2026-11-05 | current |
| `langchain` | 1.4.9 | 2026-11-04 | current |

And the base agent API itself:

```python
from langgraph.prebuilt import create_react_agent
# WARNING: This function is deprecated in favor of
#   `create_agent` from the `langchain` package, which provides an
#   equivalent agent factory with a flexible middleware system.
```

`create_react_agent` is **deprecated** in LangChain v1. `langgraph-swarm` is
built on it. So `langgraph-swarm` is built on a deprecated API. That is the
whole reason to build handoffs yourself (L06).

**The modern replacement is the subagents pattern**, and it is about forty
lines of code. You already know every piece of it.

---

## 1. The pattern in one screen

```python
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage

# 1. Build each specialist as an ordinary agent.
researcher = create_agent(model, tools=[web_search], name="researcher")
billing    = create_agent(model, tools=[read_invoice], name="billing")

# 2. Wrap each specialist so the supervisor can call it as a tool.
def agent_as_tool(name, description, agent):
    @tool(f"ask_{name}", description=description)
    def ask(task: str) -> str:
        result = agent.invoke({"messages": [HumanMessage(content=task)]})
        return result["messages"][-1].content
    return ask

# 3. Give the supervisor those tools.
supervisor = create_agent(
    model,
    tools=[agent_as_tool("researcher", "Delegate research.", researcher),
           agent_as_tool("billing",    "Delegate billing.", billing)],
    name="supervisor",
)
```

That is the entire `langgraph-supervisor` package, reimplemented in a way
that will still be maintained.

---

## 2. The adapter's contract

The adapter is where multi-agent systems are won or lost. It has exactly
two obligations.

### 2.1 Output: a plain STRING

```python
return text_of(result["messages"][-1])
```

**Not** the state dict. **Not** a JSON blob of the agent's internal state.
The supervisor's model receives this string as a tool result and has to
decide what to do with it. If you hand it `{"messages": [...15 messages...],
"internal_field": ...}`, it will flounder.

**Rule: return the specialist's final answer and nothing else.** If the
answer is long, that is an *artifact* problem — park the payload in the
store and return a handle (L08).

### 2.2 Input: a SELF-CONTAINED brief

The specialist receives `HumanMessage(content=task)`. It sees **nothing
else** — not the user's original question, not the supervisor's reasoning,
not the other specialists' findings.

So the brief must contain everything the specialist needs:

```
BAD   "look into the billing issue"
GOOD  "Customer A (a@b.com, plan=pro) was charged 49 EUR on 2026-11-01
       for invoice INV-77, but their plan does not include usage billing.
       Find out which usage incurred the charge. Report the usage
       breakdown in at most 5 bullet points."
```

The three rules of a good brief (from `ex08`):

1. **Self-contained** — the receiver cannot see your context. Repeat what it needs.
2. **Explicit contract** — say what shape the answer should be in.
3. **Bounded** — say when to stop. ("<= 5 bullets", "one paragraph")

---

## 3. Why it works: context isolation, measured

In `ex06`, the researcher's own conversation (system prompt + tool call +
tool result) lives **inside** the researcher. The supervisor sees only the
researcher's final string.

```
TEAM STATE
  findings      : ['LangGraph supervisor patterns: 3 approaches.']
  top-level messages: 2
```

Two messages. The supervisor never paid for the researcher's tool call.

That is **benefit #1 from L01 (context isolation)**, achieved not by
clever prompt engineering but by the *shape of the code*.

---

## 4. Two ways a supervisor can route

### 4.1 Free-form routing — the tool IS the decision

The supervisor model is given one tool per specialist and chooses. Nothing
else to build.

**Use when** the routing *is* the work. The model can even call two
specialists in one turn, which gives you fan-out for free.

**Costs:** the routing decision is buried inside tool-call arguments. You
cannot easily log it, validate it, or override it.

### 4.2 Structured routing — you get a typed object

```python
from pydantic import BaseModel, Field

class Route(BaseModel):
    """Which specialist should handle this request, and why."""
    specialist: Literal["researcher", "billing", "support", "human"]
    reason: str = Field(description="One sentence explaining the routing")
    urgency: Literal["low", "normal", "high"] = "normal"

supervisor = create_agent(model, tools=[...], response_format=Route)
result = supervisor.invoke({"messages": [("user", question)]})
route = result["structured_response"]      # a Route instance
```

Now you hold a typed object. You can:

- validate it before spending money,
- log routing accuracy,
- route to something that is **not** an agent (a queue, a REST call),
- apply business rules (`if route.urgency == "high": escalate_to_human()`),
- switch to a different specialist without re-prompting the model.

**Use when** you need to make a *decision about* the routing.

### 4.3 The two strategies behind `response_format`

| strategy | how it works | use when |
|---|---|---|
| `ToolStrategy` (default) | the schema becomes a synthetic **tool** the model calls | every model, including Gemini |
| `ProviderStrategy` | the provider's **native** JSON-schema mode | the provider supports it (Gemini does) |

With `ToolStrategy`:

* The synthetic tool is named **after your schema class**. `class Route`
  → the model must call a tool named `Route`.
* The agent forces `tool_choice="any"`, so the model must use it.
* The parsed result appears in `result["structured_response"]`.

```python
# the model must emit a tool call named exactly "Route"
AIMessage(content="", tool_calls=[{
    "name": "Route",
    "args": {"specialist": "billing", "reason": "invoice question", "urgency": "normal"},
    "id": "r1", "type": "tool_call",
}])
```

With Gemini you can use the native mode:

```python
from langchain.agents.structured_output import ProviderStrategy

supervisor = create_agent(model, tools=[...],
                          response_format=ProviderStrategy(Route))
```

### 4.4 The silent-retry trap (important!)

If the model returns **plain prose** instead of the structured tool call,
the agent does **not** fail. It silently re-asks, over and over, until the
recursion limit:

```
observed: GraphRecursionError: Recursion limit of 12 reached without
           hitting a stop condition.
```

This is `ToolStrategy`'s `handle_errors=True` default doing a retry.

**In production:** validate `structured_response` yourself, cap the
retries, and consider a cheaper/faster model for the routing step.

---

## 5. Putting the supervisor in a graph

The supervisor is usually a **node** in a team graph, so the team can have
shared state.

```python
class TeamState(AgentState):
    findings: Annotated[list[str], lambda a, b: a + b]
    final_answer: str

def supervisor_node(state: TeamState):
    result = supervisor.invoke({"messages": state["messages"]})
    answer = result["messages"][-1].content
    return {
        "messages": [result["messages"][-1]],
        "findings": [answer],        # only the NEW item (append reducer!)
        "final_answer": answer,
    }

g = StateGraph(TeamState)
g.add_node("supervisor", supervisor_node)
g.add_edge(START, "supervisor")
g.add_edge("supervisor", END)
```

> **Reminder (L02):** with an append reducer, return only the new item.
> `findings=[answer]`, not `state["findings"] + [answer]`.

---

## 6. When the subagents pattern is NOT enough

The pattern gives you exactly one thing: **the supervisor picks a specialist
and reads a string back.** Reach for something else when you need:

| you need | reach for |
|---|---|
| the specialist must **write** into a shared record | a hand-built `StateGraph` (L05) |
| control must **move** to the specialist (it talks to the user) | `Command(graph=Command.PARENT, goto=...)` (L06) |
| independent subtasks run **simultaneously** | `Send` fan-out (L09) |
| different models / budgets per agent | you already have it — each worker is its own `create_agent` |
| a human must approve mid-run | `interrupt` + checkpointer (Phase 8) |

**The escape-hatch rule, restated:**

> When the supervisor needs to pass more than a string back, stop
> stringifying. Give the team a real shared state.

---

## 7. Anti-patterns

| anti-pattern | why it hurts | instead |
|---|---|---|
| The supervisor returns the specialist's whole state dict | the supervisor model drowns in JSON | return the final message text only |
| The brief is 3 words | the specialist guesses, or hallucinates | a self-contained brief |
| The supervisor has 12 specialist tools | routing accuracy collapses | hierarchical supervisors (L07) |
| One giant "super agent" plus 12 thin wrappers | no isolation, all the cost | real specialists with narrow tools |
| The supervisor re-reads every finding each turn | prompt stuffing | summarise into shared state |
| No `name=` on any agent | your traces are unreadable | `create_agent(..., name="researcher")` |

---

## 8. Run it

```bash
PYTHONPATH=examples .venv/bin/python examples/ex06_agents_as_tools.py
PYTHONPATH=examples .venv/bin/python examples/ex07_structured_routing.py
```

`ex06` builds the modern supervisor and prints the context-isolation effect.
`ex07` demonstrates structured routing with `ToolStrategy`, reproduces the
silent-retry trap, and shows a router dispatching to real specialists.

---

## What you should be able to do now

- Explain why `langgraph-supervisor` is not the answer any more, and what
  replaced it.
- Write the agent-as-tool adapter correctly (string out, self-contained
  brief in).
- Choose between free-form and structured routing, and justify it.
- Explain `ToolStrategy` vs `ProviderStrategy`, and when the synthetic tool
  name matters.
- Diagnose the silent-retry trap.
- Say when to abandon the subagents pattern and what to use instead.

**Next:** L05 — hand-built supervisors with a real shared team state, and
the art of the handoff brief.
