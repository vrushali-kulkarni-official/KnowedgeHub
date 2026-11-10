# L05 — Hand-Built Supervisors and the Art of the Handoff Brief

**Module:** M67 (part 2) · **Time:** ~2h · **Example:** `examples/ex08_handbuilt_supervisor.py`

---

## 0. When to leave the subagents pattern behind

L04's subagents pattern has one limitation: **the supervisor passes a
string.** Sometimes that is not enough.

You need a hand-built team when:

1. A specialist must **write** into a shared record (a score, a document id,
   an approval flag).
2. Two specialists must contribute to the **same artifact**.
3. You need an **audit trail** of who did what.
4. A human must be able to **inspect and override** intermediate work.
5. The routing decision depends on **state**, not just on the conversation.

The good news: you do **not** give up `create_agent` when you hand-build.
Each specialist is still a `create_agent` — you just own the graph around
them.

```
  subagents pattern          hand-built team
  ---------------            ---------------
  supervisor (agent)         supervisor NODE  (often still an agent)
  workers as tools           workers as NODES (still agents)
  string passing             shared state passing
```

---

## 1. The team state

```python
class TeamState(AgentState):
    task: str
    brief: str
    """The task brief handed to the current specialist."""

    findings: Annotated[list[dict], lambda a, b: a + b]
    """Each specialist's contribution, appended."""

    draft: str
    final_answer: str
    status: Literal["routing", "working", "reviewing", "done"]
    next_agent: str
    """Who the supervisor decided should work next.  The graph dispatches on
    THIS field rather than re-deriving the decision - one source of truth."""

    trace: Annotated[list[str], lambda a, b: a + b]
```

Three design decisions worth calling out:

**a) `messages` holds the conversation. Structured facts live in typed
fields.** (L02 rule 1.) `findings` is a fact, not a turn.

**b) `next_agent` is the single source of truth for routing.** The
supervisor writes it; the conditional edge reads it. Do **not** re-derive
the decision in the edge function — that is how you end up with two
different opinions about who should work next, and an infinite loop.

**c) Every list field uses an append reducer, and every node returns ONLY
the new item.** (L02's reducer rule, and L08's echo trap — see below.)

---

## 2. The supervisor node

```python
def supervisor(state: TeamState):
    """Decide who works next, and write a self-contained brief."""

    def router(messages):
        if len(state["findings"]) == 0:
            who, brief = "researcher", (
                "Find 3 numbered facts about LangGraph multi-agent patterns. "
                "Return them as one line each, no preamble."
            )
        elif not state.get("draft"):
            who, brief = "writer", (
                "Write one closing paragraph (<=40 words) about LangGraph "
                "multi-agent patterns, using these findings: "
                + "; ".join(f["summary"] for f in state["findings"])
            )
        else:
            who, brief = "reviewer", "Review the draft. Reply APPROVED or REQUEST CHANGES."

        return AIMessage(content="", tool_calls=[{
            "name": "Assignment",
            "args": {"specialist": who, "brief": brief, "done": False},
            "id": "assign_1", "type": "tool_call",
        }])

    agent = create_agent(scripted(router=router), tools=[], response_format=Assignment,
                         name="supervisor")
    result = agent.invoke({"messages": state["messages"]})
    decision: Assignment = result["structured_response"]

    return {
        "status": "done" if decision.done else "working",
        "next_agent": decision.specialist,
        "brief": decision.brief,
        # !! append reducer -> return ONLY the new item
        "trace": [f"supervisor -> {decision.specialist}"],
    }
```

Notice the supervisor returns a **structured** decision (L04 §4.2). It
needs to, because it must write two things: *who* and *the brief*.

---

## 3. The worker node — where the handoff happens

```python
def make_worker(name: str):
    agent = specialists[name]

    def worker(state: TeamState):
        # THE HANDOFF: the specialist gets a FRESH, self-contained
        # conversation.  It does NOT see the supervisor's transcript.
        result = agent.invoke({"messages": [HumanMessage(content=state["brief"])]})
        answer = result["messages"][-1].content
        update = {
            "messages": [AIMessage(content=f"[{name}] {answer}")],
            # Only the NEW finding - the reducer appends it.
            "findings": [{"specialist": name, "summary": answer, "brief": state["brief"]}],
            "trace": [f"{name} delivered"],
        }
        if name == "writer":
            update["draft"] = answer
        if name == "reviewer":
            update["status"] = "done"
            update["final_answer"] = state.get("draft", answer)
        return update

    return worker
```

The worker receives exactly one thing: `state["brief"]`. Everything it
needs must be in that brief.

---

## 4. Handoff message design — the most under-rated skill

A handoff is a **prompt**, not a packet. Three rules:

### Rule 1 — SELF-CONTAINED

The receiver cannot see your context. Repeat what it needs.

```
BAD   "check the invoice"
BAD   "the customer from earlier"
GOOD  "Customer A (a@b.com, plan=pro) was charged 49 EUR on 2026-11-01
       for invoice INV-77, but their plan does not include usage billing.
       Find out which usage incurred the charge."
```

### Rule 2 — EXPLICIT CONTRACT

Say what shape the answer should be in.

```
BAD   "find some facts"
GOOD  "Find 3 numbered facts. One line each. No preamble. If you cannot
       find 3, return how many you did find and why."
```

### Rule 3 — BOUNDED

Say when to stop.

```
BAD   "write about LangGraph"
GOOD  "Write one paragraph (<=40 words). Do not include a title."
```

### Rule 4 (bonus) — GROUNDED

Prefer briefs that point at the tool the specialist should use, so the
specialist's job is mechanical rather than interpretive.

### A worked comparison

| brief | outcome |
|---|---|
| "look into the billing issue" | the specialist invents a context, or asks a question the supervisor cannot answer |
| "Customer A (a@b.com, plan=pro) was charged 49 EUR on 2026-11-01 for invoice INV-77, but their plan does not include usage billing. Find out which usage incurred the charge. Report the usage breakdown in at most 5 bullet points." | the specialist knows exactly what to do and what to return |

**A test for a good brief:** could a competent stranger act on it, with no
other context? If yes, it is a good brief.

---

## 5. The graph

```python
def dispatch(state: TeamState):
    """Which worker runs next - straight from the supervisor's decision."""
    if state.get("status") == "done":
        return "finalise"
    return state.get("next_agent") or "researcher"

g = StateGraph(TeamState)
g.add_node("supervisor", supervisor)
g.add_node("researcher", make_worker("researcher"))
g.add_node("writer", make_worker("writer"))
g.add_node("reviewer", make_worker("reviewer"))
g.add_node("finalise", finalise)
g.add_edge(START, "supervisor")
g.add_conditional_edges("supervisor", dispatch,
                         ["researcher", "writer", "reviewer", "finalise"])
g.add_edge("researcher", "supervisor")
g.add_edge("writer", "supervisor")
g.add_edge("reviewer", "supervisor")
g.add_edge("finalise", END)
```

Note the loop shape: `worker → supervisor → worker`. The supervisor is the
only thing that decides, so it must be the only thing in the loop.

`ex08` produced this trace:

```
supervisor -> researcher
researcher delivered
supervisor -> writer
writer delivered
supervisor -> reviewer
reviewer delivered
supervisor -> reviewer        (status already done -> finalise)
finalised
```

---

## 6. The two bugs you will hit while building this

### 6.1 The append-reducer duplication (L02)

```python
# WRONG - the reducer does old + returned, so everything duplicates
"findings": state["findings"] + [{"specialist": name, ...}]

# RIGHT
"findings": [{"specialist": name, ...}]
```

Symptom: your audit log shows everything twice, and it gets worse every
cycle.

### 6.2 The infinite loop

If the dispatch decision is derived from state *in two places* (once in the
supervisor, once in the edge function), they will eventually disagree and
the graph will loop forever.

**The fix is the `next_agent` field.** One writer, one reader.

The other classic loop: a worker that never sets the field the dispatcher
checks. In `ex08` the writer never set `draft`, so `dispatch` always
returned `"writer"` and the graph looped until the recursion limit.

> If your team loops, check in this order:
> 1. Does every worker set the field the dispatcher checks?
> 2. Is the dispatch decision derived in exactly one place?
> 3. Do you have a `ModelCallLimitMiddleware`? (L10)

---

## 7. The echo trap again (L02 §3)

If your specialists are `create_agent`s added as nodes, they echo their
state back. So:

> Keep append-reducer lists **out** of the agent's `state_schema`.

In `ex08` the workers are `create_agent`s with the **default** schema
(`AgentState`), so they have no `findings` channel and there is nothing to
echo. The `findings` list lives only in the parent. Clean.

If you *must* give an agent a custom schema (for `InjectedState`), keep it
narrow and prefer merge reducers over append reducers.

---

## 8. Hand-built vs subagents — the decision

| | subagents (L04) | hand-built team (this lesson) |
|---|---|---|
| code | ~15 lines | ~100 lines |
| what crosses | a string | typed state |
| specialists write to shared state | no | yes |
| audit trail | only in the transcript | structured `trace` field |
| human override | hard | easy |
| routing based on state | no | yes |
| prompt stuffing risk | low | medium (state is wide) |

**Rule of thumb:** start with subagents. Move to a hand-built team the
moment you need a specialist to *write* something.

---

## 9. Run it

```bash
PYTHONPATH=examples .venv/bin/python examples/ex08_handbuilt_supervisor.py
```

The output prints the team trace, the shared state, and — importantly — the
exact brief each specialist received, so you can judge the brief quality
directly.

---

## What you should be able to do now

- Decide between the subagents pattern and a hand-built team.
- Design a team state schema with the right reducers.
- Write a brief that satisfies the four rules.
- Build a supervisor → worker → supervisor loop that terminates.
- Explain the append-reducer duplication and the infinite-loop causes.

**Next:** L06 — handoffs and swarms, built the modern way, with the loop
guards that keep them from burning your budget.
