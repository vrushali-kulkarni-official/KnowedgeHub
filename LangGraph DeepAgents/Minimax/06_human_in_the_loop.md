# Module 06 — Human-in-the-Loop

## Prerequisites

- Modules 04 and 05 (ReAct + persistence)

## Why this module matters

Some actions shouldn't happen without a human's say-so: send an email, charge a card, post to social, delete data, deploy code. LangGraph's HITL primitives let you **pause the graph mid-execution, surface the decision to a human, and resume** — without writing a state machine by hand.

This is the module that lets you ship agents that do real, irreversible things.

## Learning objectives

By the end of this module you can:

1. Use `interrupt()` to pause a graph mid-execution.
2. Resume a graph with `Command(resume=...)`.
3. Distinguish dynamic interrupts from static `interrupt_before`/`interrupt_after`.
4. Build a tool-approval flow.
5. Build a multi-stage approval flow with edits.
6. Handle HITL cleanly from FastAPI (or any web framework).

---

## 6.1 The two kinds of interrupt

### 6.1.1 Static interrupts (declared at compile time)

```python
g = builder.compile(
    checkpointer=checkpointer,
    interrupt_before=["send_email"],       # pause before this node
    interrupt_after=["plan"],              # pause after this node
)
```

Good for: "I always want a human to approve this step."

### 6.1.2 Dynamic interrupts (the `interrupt()` function)

```python
from langgraph.types import interrupt, Command

def maybe_send_email(state: State) -> dict:
    decision = interrupt({
        "question": "Send this email?",
        "to": state["draft"]["to"],
        "subject": state["draft"]["subject"],
        "body": state["draft"]["body"],
    })
    if decision["approved"]:
        return {"messages": [send(state["draft"])]}
    return {"messages": [AIMessage(content="Email canceled by user.")]}
```

When execution hits `interrupt(...)`:
1. The graph **pauses**.
2. The state is **saved** (with a `__interrupt__` marker).
3. Control returns to the caller.
4. The caller can inspect, modify, and `invoke` again with `Command(resume=...)`.

Good for: "I want to pause *this particular* run because the data needs review."

---

## 6.2 Resuming with `Command`

To resume, pass a `Command` with the data the interrupt should receive:

```python
from langgraph.types import Command

# In a web route:
@app.post("/chat/{thread_id}/approve")
def approve(thread_id: str, payload: dict):
    config = {"configurable": {"thread_id": thread_id}}
    return g.invoke(Command(resume={"approved": True, "by": "user"}), config=config)
```

The `resume` value becomes the return value of the `interrupt(...)` call in the paused node.

You can also resume via `astream`, which is how you'll build real-time UIs.

---

## 6.3 Detecting "this run is paused"

In a web service, you need to know if the graph finished or paused:

```python
try:
    result = g.invoke(input, config=config)
    return {"status": "done", "result": result}
except GraphInterrupt as e:
    interrupts = e.interrupts
    return {"status": "paused", "interrupts": [i.value for i in interrupts]}
```

Or use `get_state(config)` to inspect:

```python
state = g.get_state(config)
if state.next:
    # graph is paused
    pass
```

`state.tasks` contains the pending tasks. Each has an `interrupts` attribute with the payload.

---

## 6.4 Tool approval pattern (the most common use case)

The "human approves before a side-effecting tool runs" pattern:

```python
from langgraph.prebuilt import ToolNode
from langgraph.types import interrupt, Command

def call_with_approval(state: State):
    last = state["messages"][-1]
    decision = interrupt({
        "tool_calls": [
            {"id": tc["id"], "name": tc["name"], "args": tc["args"]}
            for tc in last.tool_calls
        ]
    })
    if decision["approved"]:
        return {}     # proceed; next node will run the tool
    # deny: return a synthetic ToolMessage
    return {"messages": [
        ToolMessage(
            content="Tool execution denied by user.",
            tool_call_id=tc["id"],
        )
        for tc in last.tool_calls
    ]}

# Graph:
# START → agent → approval → tools → agent → ...
```

The approval node sits **between** the agent and the actual `ToolNode`. On resume, the graph continues through tools.

### Why this is better than `interrupt_before` for tools

`interrupt_before=["tools"]` works but is binary — all tools paused. A custom approval node lets you:
- Pause only on specific tools.
- Show the user the tool call details.
- Allow edits to args.
- Allow the user to add a comment that's fed back to the LLM.

---

## 6.5 Editing state on resume

You can update state *and* resume in one call:

```python
g.invoke(
    Command(
        resume={"approved": True},
        update={"messages": [HumanMessage(content="I changed my mind, add this context.")]}
    ),
    config=config,
)
```

The `update` is merged into state before the graph continues. Useful for "approve AND add a note."

---

## 6.6 Multi-stage approval (plan → execute)

For high-stakes workflows:

```
plan_node → [interrupt: review plan] → execute_node → [interrupt: review output] → done
```

```python
def plan_node(state):
    plan = generate_plan(state)
    decision = interrupt({"type": "plan", "plan": plan})
    if not decision["approved"]:
        return {"messages": [AIMessage(content="Plan rejected.")]}
    return {"plan": plan}

def execute_node(state):
    decision = interrupt({"type": "execution", "plan": state["plan"]})
    if not decision["approved"]:
        return {"messages": [AIMessage(content="Execution canceled.")]}
    return {"messages": [execute(state["plan"])]}
```

Each `interrupt` is a separate pause. Each resume continues the graph.

---

## 6.7 Streaming HITL flows

`astream` lets you render progress to the user in real time:

```python
async for event in g.astream(Command(resume={"approved": True}), config=config, stream_mode="updates"):
    yield event
```

In a FastAPI route:

```python
from fastapi.responses import StreamingResponse

@app.post("/chat/{thread_id}/resume")
async def resume(thread_id: str, payload: dict):
    config = {"configurable": {"thread_id": thread_id}}
    async def gen():
        async for event in g.astream(Command(resume=payload), config=config, stream_mode="updates"):
            yield f"data: {json.dumps(event)}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")
```

This is the "interrupt UI" pattern: a chat-like surface where the user can see what the agent wants to do, approve/edit/reject, and watch execution continue.

---

## 6.8 The `human_in_the_loop` patterns cheatsheet

| Pattern | Where to put the pause | Resume data |
|---|---|---|
| Always pause before a node | `interrupt_before=["node"]` at compile | (no data needed) |
| Pause for tool approval | Custom node between `agent` and `tools` | `{approved: bool, edit?: {...}}` |
| Multi-stage (plan → execute) | `interrupt()` in each stage node | Stage-specific data |
| Auto-approve some, pause others | Conditional `interrupt()` | Varies |
| Pause and let user edit state | `Command(resume=..., update=...)` | Both resume and update |

---

## 6.9 Production considerations

### 6.9.1 Timeouts

If a user doesn't respond, what happens? Two options:

- **Soft timeout:** show "still waiting" in UI. Graph stays paused forever (or until retention job).
- **Hard timeout:** scheduled job that auto-resumes with a rejection.

```python
# In a cron job:
state = g.get_state(config)
if state.next and state.created_at < now() - timedelta(hours=24):
    g.invoke(Command(resume={"approved": False, "reason": "timeout"}), config=config)
```

### 6.9.2 Authorization

Make sure the user resuming a thread is allowed to. Validate `user_id` in the resume route:

```python
@app.post("/chat/{thread_id}/resume")
def resume(thread_id: str, user: User = Depends(current_user), payload: dict):
    state = g.get_state({"configurable": {"thread_id": thread_id}})
    if state.values.get("user_id") != user.id:
        raise HTTPException(403)
    ...
```

### 6.9.3 Audit trail

Every interrupt + resume should be logged. Either:
- Rely on the checkpoint history (it records all state).
- Add a structured log line in your approval node.

### 6.9.4 Idempotency

If a user double-clicks "Approve," you'll get two resumes. Use a "decision_id" stored in state and check it.

---

## 6.10 Common HITL pitfalls

| Pitfall | Fix |
|---|---|
| `interrupt()` outside a node (in a tool) | Works but data flow is awkward; prefer a node |
| Forgetting `Command(resume=...)` shape | Match the `interrupt()` payload shape |
| Resume on wrong `thread_id` | Graph resumes a different conversation |
| No way to distinguish "paused" from "done" | Always check `state.next` or catch `GraphInterrupt` |
| `interrupt_before` blocks streaming | Use dynamic `interrupt()` for streaming flows |
| Pause without a UX | Don't ship HITL if users can't see the prompt |

---

## Hands-on project

**Goal:** Build an "email assistant" with tool approval.

1. Define a `send_email(to, subject, body)` tool. It does NOT actually send — just returns a fake success.
2. Build a graph: `agent → approval → tool_executor → agent → END`.
3. The approval node uses `interrupt` to show the user the proposed email.
4. FastAPI routes:
   - `POST /chat` — start a new turn.
   - `POST /chat/{thread_id}/decide` — approve, reject, or edit-and-approve.
5. Test the full flow: user says "send John an email about Tuesday's meeting" → graph pauses → user sees draft → user edits subject → approves → graph resumes → tool runs.

## Exercises

1. **Multi-stage:** add a `summarize_thread` stage before the email-send stage. The user must approve both.
2. **Conditional approval:** only pause on `send_email`. Let `search_docs` and `get_weather` run freely.
3. **State editing on resume:** allow the user to add a "cc" field on resume. Merge it into the tool args.
4. **Timeout handling:** write a scheduled job that auto-rejects pauses older than 1 hour.
5. **Audit log:** every approval/rejection logged as a JSON line. What fields should it have?

## Production checklist

- [ ] All side-effecting tools (email, payment, write to DB, deploy) have approval.
- [ ] Every approval node emits an audit log line.
- [ ] Resume routes check authorization.
- [ ] Timeouts configured (soft UI + hard cleanup).
- [ ] Users can edit the proposed action before approving.
- [ ] The "paused" vs "done" state is clear in your API contract.

## Key takeaways

- `interrupt()` is the pause primitive. `Command(resume=...)` is the resume.
- Static `interrupt_before`/`after` is for unconditional pauses. Dynamic `interrupt()` is for context-specific ones.
- The "approval node between agent and tools" pattern is the workhorse for HITL.
- Streaming + HITL = real-time approval UIs.
- Always authorize the resumer and audit every decision.

## Resources

- LangGraph HITL: https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/
- `Command` reference: https://langchain-ai.github.io/langgraph/reference/types/#langgraph.types.Command
- LangGraph Studio (Module 09) lets you click "Resume" interactively — great for dev.
