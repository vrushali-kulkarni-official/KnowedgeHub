# L06 — Handoffs and Swarms, Built the Modern Way

**Module:** M68 · **Time:** ~2.5h · **Example:** `examples/ex09_handoffs.py`

---

## 0. Handoff ≠ agents-as-tools

These two look similar and behave very differently.

| | agents-as-tools (L04) | handoff (this lesson) |
|---|---|---|
| who calls whom | supervisor → specialist | specialist → specialist |
| control afterwards | stays with the supervisor | **moves** to the specialist |
| the specialist speaks to the user? | no — it answers the supervisor | **yes** — it owns the conversation |
| implemented as | a tool that calls an agent | a tool that returns `Command(goto=...)` |

**Use a handoff when the specialist needs to talk to the user** — ask for a
missing detail, confirm an action, collect data. The supervisor pattern
cannot do this: the specialist's words go to the supervisor, not to the user.

**Use agents-as-tools when the specialist is a subroutine** — it does a job
and returns a result.

---

## 1. Why not `langgraph-swarm`?

| package | version | last release | status |
|---|---|---|---|
| `langgraph-swarm` | 0.1.0 | **2025-12-04** | built on the **deprecated** `langgraph.prebuilt.create_react_agent` |
| `langgraph` | 1.2.20 | 2026-11-05 | current |

`create_react_agent` itself says:

> **WARNING**: This function is deprecated in favor of
> `create_agent` from the `langchain` package.

So `langgraph-swarm` is pinned to an API that no longer receives updates.
Building the handoff yourself is ~40 lines, and you get current features
(middleware, budgets, structured output) for free.

---

## 2. The modern handoff primitive

```python
from typing import Annotated
from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.types import Command

@tool
def hand_off_to_billing(
    question: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Give control to the billing specialist. Use for invoices/payments."""
    return Command(
        graph=Command.PARENT,        # <-- THE crucial part
        goto="billing",
        update={
            "messages": [
                ToolMessage(content=f"Handing over: {question}",
                            tool_call_id=tool_call_id, name="hand_off_to_billing")
            ],
            "handoff_log": ["triage -> billing"],
            "current_agent": "billing",
        },
    )
```

Four things to notice:

1. **`graph=Command.PARENT`** — the agent is a nested graph; the goto must
   target the parent. Without it, the goto is silently dropped (L03 trap 1).
2. **`ToolMessage` with the tool call id** — required (L03 trap 2).
3. **`Annotated[str, InjectedToolCallId]`** — the bare class does not work
   (L03 trap 3).
4. **The update carries context** — `handoff_log` and `current_agent` tell
   the rest of the team what happened.

### The graph

```python
g = StateGraph(TeamState)
g.add_node("triage", triage)        # the agent with the handoff tool
g.add_node("billing", billing)      # the agent that takes over
g.add_node("support", support)
g.add_edge(START, "triage")
g.add_edge("billing", END)
g.add_edge("support", END)
```

Note: **`triage` has no outgoing edge.** The `Command(goto=...)` is the only
thing that moves control. That is important — see §5, Rule A.

### The result

```
handoff_log   : ['triage -> billing']
current_agent : billing
transcript:
   human | Why was I charged 12 EUR?
   tool  | Handing over: invoice?
   ai    | Invoice INV-9 is 12 EUR, paid on the 3rd.
```

The user sees a single continuous conversation. The billing agent's answer
goes straight to them.

---

## 3. What actually crosses a handoff

This is the "state filters" question from L02, applied to handoffs.

The handoff's `update` is filtered by the **parent graph's** state schema.
Keys that are not declared are **silently dropped** (L02 rule 3).

```
messages      - the WHOLE transcript, including the handoff ToolMessage
handoff_log   - appended by the reducer
visits        - merged by the reducer
answer        - NOT set by the handoff (the specialist sets it later)
undeclared_key- DROPPED, silently
```

**Practical consequence:** if you want the specialist to know something, you
must declare a field for it **in the parent's schema**. Writing
`update={"my_field": x}` without declaring `my_field` in the parent's
`TypedDict` does nothing, with no error.

---

## 4. Building a swarm — and the four rules

A swarm is several peers that can hand off to each other. `ex09` builds
one with three peers and a loop guard.

### Rule A — a node with `Command(goto=)` must NOT also have a routing edge

If a node has both a `Command(goto=X)` **and** a conditional edge, both
fire. The target node runs **twice in parallel**, and two writes to a
last-value channel raise:

```
InvalidUpdateError: At key 'current_agent': Can receive only one value
per step. Use an Annotated key to handle multiple values.
```

So: a peer that hands off has **no** conditional edge. The `Command` is the
only router.

```python
g.add_node(p, agents[p])          # no add_conditional_edges for these
g.add_edge(START, "triage")
```

### Rule B — the loop guard belongs in the tool

The guard reads the visit counter with `InjectedState` and refuses to hand
off when the target has been visited too often:

```python
@tool(f"hand_off_from_{name}", description="Give control to another specialist.")
def hand_off(
    target: str,
    note: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[PeerAgentState, InjectedState],
) -> Command:
    visits = dict((state or {}).get("visits", {}) or {})
    seen = visits.get(target, 0)

    if seen >= MAX_VISITS:
        return Command(graph=Command.PARENT, goto=END,
                       update={"handoff_log": [f"{name} -> STOP (visit limit)"]})

    visits[target] = seen + 1
    return Command(graph=Command.PARENT, goto=target,
                   update={"handoff_log": [f"{name} -> {target}"],
                           "current_agent": target,
                           "visits": visits})
```

The guard's output, from `ex09`:

```
handoff path : ['triage -> researcher', 'researcher -> writer', 'writer -> triage',
                'triage -> researcher', 'researcher -> writer', 'writer -> triage',
                'triage -> STOP (visit limit for researcher)']
visits       : {'researcher': 2, 'writer': 2, 'triage': 2}
```

### Rule C — `InjectedState` needs the key in the agent's `state_schema`

```python
create_agent(model, tools=[hand_off], name=name, state_schema=PeerAgentState)
```

Without it: `KeyError: 'visits'`. The default schema (`AgentState`) has
only `messages`, `jump_to` and `structured_response`.

### Rule D — the agent's state schema must be narrow

The agent echoes its state back to the parent (L02 §3). Keep append-reducer
lists out of it:

```python
class TeamState(AgentState):
    visits:      Annotated[dict[str, int], lambda a, b: {**a, **b}]   # merge: safe
    handoff_log: Annotated[list[str], lambda a, b: a + b]              # parent only

class PeerAgentState(AgentState):
    visits: Annotated[dict[str, int], lambda a, b: {**a, **b}]       # merge only
```

---

## 5. Ping-pong: the #1 swarm bug

Two peers that keep handing back to each other will burn your entire
budget. Use **all three** defences:

### Defence 1 — a visits counter

Cheap, explicit, and it shows up in your traces so you can see the loop
after the fact.

### Defence 2 — `RemainingSteps`

LangGraph's built-in "how many steps do I have left" primitive. Inject it
into a tool and refuse to hand off when it is low:

```python
from langgraph.managed import RemainingSteps

@tool
def hand_off(target: str, remaining: RemainingSteps) -> Command:
    if remaining <= 2:
        return Command(graph=Command.PARENT, goto=END, update={...})
    ...
```

### Defence 3 — `ModelCallLimitMiddleware` / `ToolCallLimitMiddleware`

A hard backstop at the model layer, whatever the graph does (L10).

> **Never rely on `recursion_limit` alone.** `create_agent` ships with
> 9999 (L03 trap 4). A ping-pong loop will make thousands of model calls
> before anything stops it.

---

## 6. Handoff vs agents-as-tools — the decision

```
Does the specialist need to TALK TO THE USER?
    YES -> handoff.
    NO  -> does it need to WRITE into shared state?
             YES -> hand-built team (L05)
             NO  -> agents-as-tools (L04)
```

| symptom | pattern |
|---|---|
| the user has to repeat themselves to every specialist | handoff (one continuous conversation) |
| the specialist's answer should not be shown to the user raw | agents-as-tools (the supervisor filters it) |
| you need an audit trail of the conversation | handoff (one transcript) |
| you need per-specialist artifacts | either — but artifacts go in the store (L08) |

---

## 7. The design of a handoff tool's description

The description is the prompt that decides when the handoff fires. Write
it like a routing rule:

```python
@tool("hand_off_to_billing",
      description="Give control to the billing specialist. "
                  "Use ONLY for invoices, payments, refunds and plan changes. "
                  "Do not use for login problems - use support.")
```

Bad: `"Hand off to billing"`.

The tool description is the cheapest, most reliable routing mechanism you
have, because the model sees it on every single turn.

---

## 8. Run it

```bash
PYTHONPATH=examples .venv/bin/python examples/ex09_handoffs.py
```

---

## What you should be able to do now

- Explain the difference between a handoff and agents-as-tools, and pick
  the right one.
- Write a handoff tool that actually navigates the parent graph.
- Say what crosses a handoff and what gets silently dropped.
- Build a swarm with a working loop guard.
- Explain the four swarm rules (A–D) and the `InvalidUpdateError` that
  Rule A prevents.
- List the three ping-pong defences.

**Next:** L07 — hierarchical teams: supervisors of supervisors, progress
reporting, and failure escalation.
