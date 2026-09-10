# Module 12 — Deep Agents: Planning & Todos

## Prerequisites

- Module 11 (you have a basic Deep Agent)

## Why this module matters

The single biggest difference between an agent that wanders and one that ships is **planning**. A planning agent breaks a complex goal into steps, executes them, and updates the plan as it learns.

This module is the deep dive on the `write_todos` tool and how to get the most out of it.

## Learning objectives

By the end of this module you can:

1. Explain how `write_todos` works internally.
2. Read the `todos` channel in state and understand its schema.
3. Prompt the agent to plan well.
4. Customize the planning prompt.
5. Inject your own planning logic (custom system prompt fragments).
6. Debug plans that go wrong.
7. Build a "plan-first" UX for users.

---

## 12.1 The `write_todos` tool

When you call `create_deep_agent`, the `write_todos` tool is injected automatically. Its schema:

```python
write_todos(todos: list[dict])
# each todo:
# {
#   "content": str,         # what to do
#   "status": "pending" | "in_progress" | "completed",
#   "activeForm": str       # present-tense form for display
# }
```

The agent calls this tool to:
- Create the initial plan.
- Mark items in progress / completed.
- Update the plan based on new info.

The tool's return value is the same list, which becomes the new `todos` channel in state.

---

## 12.2 The `todos` channel in state

The Deep Agent state extends `MessagesState` with:

```python
class DeepAgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    todos:    Annotated[list[Todo], ...]    # reducer handles writes
    files:    dict[str, str]                # file system state
```

You can read it from any node (or in your app code):

```python
result = agent.invoke({"messages": [...]})
for todo in result["todos"]:
    print(todo)
```

You can also stream it:

```python
async for event in agent.astream(..., stream_mode="values"):
    if "todos" in event:
        render_plan(event["todos"])
```

This is the foundation of a "plan-first" UX: show the plan to the user, update as it progresses.

---

## 12.3 Prompting for good plans

The model's planning behavior is shaped almost entirely by your instructions. Templates that work:

### 12.3.1 The "always plan first" pattern

```
PROCESS:
- ALWAYS start by calling write_todos to lay out your plan.
- Then execute the plan step by step.
- Update the todo list as you go (mark in_progress when starting, completed when done).
- If you discover new information, update the plan with new todos.
```

### 12.3.2 The "decompose first" pattern

```
Before any action, decompose the user's request into a plan with write_todos.
Each todo should be:
- Specific (a clear deliverable, not a vague action).
- Independent where possible (so you can parallelize).
- Verifiable (you know when it's done).
```

### 12.3.3 The "small todos" pattern

```
Each todo should take no more than 3-5 tool calls to complete.
If a todo is too big, break it down further.
```

This is the key insight: small todos = focused execution = better results.

### 12.3.4 The "verify before moving on" pattern

```
After completing each todo, verify the result is correct before marking it completed.
If verification fails, either fix the issue or split the todo.
```

---

## 12.4 Customizing the planning prompt

The default instructions include a planning section. To customize it, just include your own in `instructions`:

```python
instructions = """
... your role, constraints, etc. ...

PLANNING:
You have access to the write_todos tool. Use it like this:
1. Before doing anything, create a plan.
2. Each todo should be a discrete, verifiable step.
3. Aim for 3-8 todos for a typical task. More for complex tasks.
4. Mark a todo in_progress when you start, completed when done.
5. Add new todos if the plan needs to change.
6. NEVER skip the plan. Even for "simple" tasks, write one — it forces clarity.

EXAMPLE:
For "Research X and write a summary":
- todo[0]: Identify 3-5 authoritative sources on X (in_progress)
- todo[1]: Read each source and take notes (pending)
- todo[2]: Synthesize notes into a coherent summary (pending)
- todo[3]: Write the summary to /output/summary.md (pending)
- todo[4]: Verify the summary covers all key points (pending)
"""
```

---

## 12.5 Injecting a custom planning node (advanced)

If you want to enforce planning in a way the model can't bypass, add a node **before** the agent that requires a plan. This is raw LangGraph:

```python
from langgraph.graph import StateGraph, START, END
from deepagents.graph import create_deep_agent_graph

# Build the deep agent graph, then wrap it
inner = create_deep_agent_graph(model, tools, instructions)

def plan_gate(state):
    if not state.get("todos"):
        # Force the agent to plan first
        return {"messages": [SystemMessage(content="You must call write_todos first.")]}
    return {}

wrapped = (
    StateGraph(DeepAgentState)
    .add_node("plan_gate", plan_gate)
    .add_node("agent", inner)
    .add_edge(START, "plan_gate")
    .add_conditional_edges(
        "plan_gate",
        lambda s: "agent" if s.get("todos") else "plan_gate"
    )
    .compile()
)
```

This is a "guard" — a node that forces the model to plan. In practice the well-crafted prompt is enough.

---

## 12.6 Surfacing plans to the user

The killer feature for UX: show the plan as it evolves.

```python
# In your FastAPI route, streaming:
async def stream_with_plan(thread_id, body):
    config = {"configurable": {"thread_id": thread_id}}
    async for event in agent.astream(input, config, stream_mode="values"):
        if "todos" in event and event["todos"] != last_todos:
            yield f"event: plan\ndata: {json.dumps([t.dict() for t in event['todos']])}\n\n"
            last_todos = event["todos"]
```

Client side: a checklist UI that updates in real time. The user sees the agent's plan before the agent even finishes a step.

---

## 12.7 Debugging bad plans

A bad plan is usually caused by:

| Symptom | Likely cause | Fix |
|---|---|---|
| No plan at all | Instructions don't emphasize planning | Add explicit "ALWAYS plan first" |
| Plan is too vague | Prompts don't say what makes a good todo | Add the "decompose first" pattern |
| Plan is too long | No limit mentioned | "Aim for 3-8 todos" |
| Plan is never updated | No "update as you learn" instruction | Add it |
| Agent skips plan, goes straight to action | Plan is optional in the prompt | "NEVER skip the plan" |
| Plan is good but execution drifts | Lack of "verify before moving on" | Add it |

---

## 12.8 The "plan-first UX" pattern

For a chat interface, the workflow is:

1. User sends a message.
2. Server returns a stream.
3. First event: the plan (todos).
4. UI shows the plan as a checklist, in_progress items highlighted.
5. As the agent executes, plan updates stream in.
6. Final event: the answer.

Implementation:

```python
async def event_gen():
    plan_sent = False
    last_todos = []
    async for mode, data in agent.astream(input, config, stream_mode=["values", "messages"]):
        if mode == "values":
            todos = data.get("todos", [])
            if todos and todos != last_todos:
                yield f"event: plan\ndata: {json.dumps([t for t in todos])}\n\n"
                last_todos = todos
        elif mode == "messages":
            token, _ = data
            if token.content:
                yield f"event: token\ndata: {json.dumps({'t': token.content})}\n\n"
    yield "event: done\ndata: {}\n\n"
```

---

## 12.9 Planning + HITL

You can put a HITL interrupt after the plan is created:

```python
# In the wrapped graph (Module 12.5):
def plan_review(state):
    decision = interrupt({"plan": state["todos"]})
    if not decision["approved"]:
        return {"messages": [AIMessage(content="Plan rejected.")]}
    return {}
```

User sees the plan, can edit it (via `Command(resume={"approved": True, "update": ...})`), then the agent executes the approved plan.

This is the **plan → approve → execute** pattern from Module 06.

---

## 12.10 The "plan as artifact" pattern

For long-running agents, save the plan to the file system:

```python
instructions = """
... after writing the plan with write_todos ...
ALSO save the plan to /plan.md so the user can review it.
"""
```

Then `result["files"]["/plan.md"]` is the human-readable plan. You can show this in the UI as a side panel.

---

## 12.11 Planning metrics

Track in production:
- **Plan length** (avg todos per task).
- **Plan churn** (how often the plan changes).
- **Plan vs outcome** (did the plan predict success?).
- **Time to first plan** (latency before the first todo is written).

If plans are churning a lot, your instructions are too vague. If plans are short, your tasks are too easy (or the agent is not planning enough).

---

## 12.12 Common planning pitfalls

| Pitfall | Fix |
|---|---|
| Agent skips planning | Make it mandatory in instructions |
| Plan is one giant todo | "Each todo takes 3-5 tool calls" |
| Plan never updates | "Update the plan as you learn new information" |
| Plan is irrelevant after a few steps | Add "verify after each step" |
| Plan is just a copy of the user message | Add "decompose the request — don't just restate it" |
| Plan is hallucinated (todos that can't be done) | "Only create todos for things your available tools can do" |

---

## Hands-on project

**Goal:** Build a "plan-first" research agent with rich UX.

1. Create a Deep Agent for "Research a topic and produce a structured report."
2. Write instructions that enforce detailed planning, 3-8 todos, and verification.
3. Build a FastAPI endpoint that streams plan + answer events.
4. Build a minimal frontend (or just a CLI viewer) that shows the plan updating live.
5. Test with 5 different topics. For each:
   - Was the plan reasonable?
   - Did the plan update as the agent learned?
   - Was the final answer consistent with the plan?

## Exercises

1. **Plan quality test:** run the same task 5 times. Compare the plans. How stable are they? (They should be very similar with temperature=0.)
2. **Plan interruption:** put a HITL interrupt after the plan. Have a user edit the plan (add a todo, change one). Resume. Compare outcome.
3. **Custom plan gate:** build a node that *forces* the model to call `write_todos` before it can do anything else.
4. **Plan artifact:** make the agent save its plan to `/plan.md`. Show this in the UI mock.
5. **Plan vs no plan:** turn off the planning instruction. Compare cost, latency, and quality.

## Production checklist

- [ ] Instructions explicitly require planning first.
- [ ] Plan surfaced to the user (live update).
- [ ] Plan saved as artifact (for audit / review).
- [ ] Plan HITL available for high-stakes tasks.
- [ ] Plan metrics tracked (length, churn, time-to-plan).
- [ ] Plan instructions tuned based on observed behavior.

## Key takeaways

- Planning is the difference between aimless and effective agents.
- `write_todos` is a tool the model uses to maintain state about its own work.
- The `todos` channel is in state, persistent, streamable.
- Prompt engineering for planning: small todos, verify, update as you learn.
- Show the plan to the user. It's a UX feature, not just an internal detail.

## Resources

- Deep Agents planning: see the library's `prompts.py` for the default instructions.
- LangChain "Plan-and-Execute" paper: https://arxiv.org/abs/2305.04091
- Anthropic's prompt engineering for agents: https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/extended-thinking-tips
