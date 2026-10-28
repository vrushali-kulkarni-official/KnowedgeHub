# L18 · Human-in-the-Loop Part 1 — Interrupts

> **Phase 8 — Persistence, Memory & Human-in-the-Loop**
> Module M57 · *HITL part 1: interrupts*
>
> Run: `python examples/ex09_interrupt_basics.py`
> Run: `python examples/ex10_functional_and_breakpoints.py`
> Run: `python examples/ex11_agent_hitl_middleware.py`

---

## 0. The mechanism in 30 seconds

```python
from langgraph.types import interrupt, Command

def node(state):
    answer = interrupt({"question": "Approve this refund?",
                        "amount": state["amount"]})
    # first call: raises, pauses the run, hands `answer` to the caller
    # after resume: `answer` IS the human's response
    return {"decision": answer}
```

```python
config = {"configurable": {"thread_id": "t1"}}

out = graph.invoke({"amount": 250}, config, version="v2")
out.interrupts        # (Interrupt(value={...}, id='...'),)

graph.invoke(Command(resume="approve"), config, version="v2")
```

Three rules cover 95% of the confusion:

1. **`interrupt()` raises on the first call**, returns the resume value on the
   second.
2. **The node restarts from the top on resume.** Code above the `interrupt()`
   call runs again.
3. **You need a checkpointer.** Without one there is nowhere to pause.

---

## 1. What a paused run looks like

### 1.1 The modern shape: `version="v2"`

```python
out = graph.invoke({"amount": 250}, config, version="v2")

type(out)            # <class 'langgraph.types.GraphOutput'>
out.value            # {'log': ['prepare:validated'], 'amount': 250}
out.interrupts       # (Interrupt(value={...}, id='...', response_schema=None),)
```

`GraphOutput` is a typed container:

| Attribute | Meaning |
|---|---|
| `.value` | the graph state so far |
| `.interrupts` | tuple of pending `Interrupt` objects |

### 1.2 The legacy shape: `__interrupt__`

Without `version="v2"`, `invoke()` returns a plain dict with a magic key:

```python
out = graph.invoke({"amount": 250}, config)
out["__interrupt__"]   # [Interrupt(value={...}, id='...')]
```

**Current vs. old:** `version="v2"` with `GraphOutput` is the modern,
explicit API. The `__interrupt__` key still works and is not hard-deprecated,
but new code should use `version="v2"`. (In LangChain 1.x agent code you will
see `version="v2"` used consistently.)

### 1.3 `Interrupt` objects

```python
Interrupt(value=..., id=..., response_schema=...)
```

| Field | Meaning |
|---|---|
| `value` | the payload you passed to `interrupt()` — show this to the human |
| `id` | a stable id for *this* interrupt; use it to answer precisely |
| `response_schema` | JSON Schema of the expected answer (if you set one) |

### 1.4 The paused thread from the outside

```python
snap = graph.get_state(config)

snap.values      # {'log': ['prepare:validated'], 'amount': 250}
snap.next        # ('gate',)      <- the node that is waiting
snap.interrupts  # (Interrupt(...),)
snap.tasks       # [PregelTask(name='gate', state=None, interrupts=(...))]
```

> **`snap.next` is what your API should key off.** If `snap.next` is
> non-empty and `snap.interrupts` is non-empty, the thread is waiting on a
> human.

---

## 2. Resuming

### 2.1 `Command(resume=...)`

```python
from langgraph.types import Command

graph.invoke(Command(resume="approve"), config, version="v2")
```

### 2.2 Answer by ID or by order

| Resume value | Matching |
|---|---|
| a bare value (`"approve"`) | **by order** — the next waiting interrupt gets it |
| a dict (`{interrupt_id: value}`) | **by ID** — precise, use this in production |

```python
ids = [i.id for i in out.interrupts]
graph.invoke(Command(resume={ids[0]: "A"}), config, version="v2")
```

The resume list is **scoped to the task that raised the interrupt**, so two
parallel branches never steal each other's answers.

### 2.3 ⚠️ The node restarts from the top

This is the single most important gotcha. Verified in `ex09`:

```
3. Resume with Command(resume=...)
   .value : {'log': ['prepare:validated', 'gate:approve', 'execute:approve'], ...}

   -> 'prepare:validated' appears TWICE: the node restarted from the top.
```

The `prepare` node ran once before the interrupt and again after the resume.

**⇒ Keep everything above the `interrupt()` call idempotent.**

```python
# ❌ charges twice
def charge_node(state):
    charge_customer(state["customer_id"])          # runs again on resume!
    decision = interrupt("approve?")
    ...

# ✅ the effect is guarded by an idempotency key (L17)
def charge_node(state):
    if not already_charged(state["op_key"]):
        charge_customer(state["customer_id"])
    decision = interrupt("approve?")
    ...
```

Better still: put the side effect **after** the interrupt, so it only runs
once the human has approved.

### 2.4 Multiple interrupts in one node

They pause **one at a time**:

```
5. Multiple interrupts in ONE node: they pause ONE AT A TIME
   pause #1 interrupts: [('3f5d8409', {'question': 'first?'})]
   -> Only ONE interrupt is exposed. The second one has not been
      reached yet, so there is nothing to answer.
```

Answer the first, and the second appears:

```
6. Answering by interrupt ID
   pause #2 interrupts: [('3f5d8409', {'question': 'second?'})]
   final: {'log': ['got:A,B'], 'decision': 'A/B'}
```

### 2.5 Structured answers: `response_schema`

```python
from pydantic import BaseModel

class Decision(BaseModel):
    approve: bool
    reason: str

def gate(state):
    d = interrupt({"question": "Approve?"}, response_schema=Decision)
    # d is a Decision instance
    return {"decision": str(d.approve)}
```

The interrupt exposes the JSON Schema, so your frontend can render a form:

```
interrupt: {'question': 'Approve?'}
response_schema: {'properties': {'approve': {...}, 'reason': {...}},
                  'required': ['approve', 'reason'], 'title': 'Decision',
                  'type': 'object'}
```

Resume with a plain dict — LangGraph validates it against the schema:

```python
graph.invoke(Command(resume={"approve": True, "reason": "looks fine"}), config, version="v2")
# -> {'log': ['typed:True:looks fine'], 'decision': 'True'}
```

---

## 3. Editing state before resuming

Sometimes the human wants to *change* something, not just answer a question.

```python
graph.update_state(cfg, {"amount": 10})     # lower the amount
graph.invoke(Command(resume="approve"), cfg, version="v2")
```

Verified in `ex09` §7:

```
before  : {'log': ['prepare:validated'], 'amount': 500}
after   : {'log': ['prepare:validated'], 'amount': 10}
final   : {'log': ['prepare:validated', 'gate:approve', 'execute:approve'],
           'decision': 'approve', 'amount': 10}
```

⚠️ **Important subtlety:** the interrupt's *value* (the question) was rendered
from the **old** state (amount 500). The edit changes the state the node
reads *after* the interrupt. If the question itself should reflect the edit,
render the question from state after `update_state`, or pause again.

---

## 4. The functional API works the same way

```python
from langgraph.func import entrypoint, task

@task
def prepare() -> str:
    return "prepared"

@task
def gate() -> str:
    answer = interrupt({"question": "ship it?"})
    return f"gate:{answer}"

@entrypoint(checkpointer=InMemorySaver())
def workflow(x: str) -> str:
    prep = prepare().result()
    g = gate().result()
    return f"{x} | {prep} | {g}"
```

### 4.1 ⚠️ A subtle but important difference

| | `StateGraph` node | Functional API |
|---|---|---|
| The function containing `interrupt()` re-runs from the top | ✅ yes | ✅ yes (the `@entrypoint` body re-runs) |
| A completed `@task` re-runs | ✅ yes | ❌ **no** — its result is replayed from the checkpoint |

Verified in `ex10`:

```
body executions so far: {'prep': 1, 'entrypoint': 1}
body executions now  : {'prep': 1, 'entrypoint': 2}

>>> IMPORTANT DIFFERENCE FROM GRAPH NODES:
  * the @entrypoint body re-ran  (entrypoint: 1 -> 2)
  * the completed @task did NOT re-run (prep stayed at 1)
    -> LangGraph replayed its result from the checkpoint.
```

**Practical upshot:** in the functional API, a `@task`'s side effect happens
**once**, even if the entrypoint restarts. In a `StateGraph`, a node's side
effect can happen **twice** (once before the interrupt, once after the
resume). Both are still at-least-once across a *crash* (L17).

---

## 5. Static breakpoints (`interrupt_before` / `interrupt_after`)

```python
graph = builder.compile(checkpointer=saver, interrupt_before=["b"])
```

These are **debugging breakpoints**, not a HITL mechanism.

Verified behaviour (`ex10`):

```
paused before 'b':
  value     : {'log': ['a']}
  interrupts: ()          <- NO payload. There is nothing to answer.
  next      : ('b',)
```

| | `interrupt()` (dynamic) | `interrupt_before` (static) |
|---|---|---|
| Carries a payload | ✅ | ❌ |
| A human answers it | ✅ `Command(resume=...)` | ❌ you just resume |
| Fires on every run | only where you placed it | ✅ always at that node |
| Declared at | run time, inside the node | compile time |
| Use for | **production HITL** | **local debugging** |

`interrupt_after=["b"]` behaves the same, stopping once `b` has run.

**Status:** still supported and **not deprecated** in LangGraph 1.2.18 — but
they are a developer tool. Don't ship them.

---

## 6. ⚠️ Deprecated: `NodeInterrupt`

```python
from langgraph.errors import NodeInterrupt
```

**Deprecated since LangGraph 1.0.** Verified in the installed package:

```python
@deprecated(
    "NodeInterrupt is deprecated. Please use [`interrupt`][langgraph.types.interrupt] instead.",
    category=None,
)
class NodeInterrupt(GraphInterrupt):
    def __init__(self, value, id=None):
        warn("NodeInterrupt is deprecated. Please use `langgraph.types.interrupt` instead.",
             LangGraphDeprecatedSinceV10, stacklevel=2)
```

Raising it yourself emits a `LangGraphDeprecatedSinceV10` warning. **Use
`interrupt()`.**

Also internal — never raise these yourself:
`GraphInterrupt`, `GraphBubbleUp`.

### 6.1 Current vs. deprecated summary

| Old | Current | Notes |
|---|---|---|
| `raise NodeInterrupt(value)` | `interrupt(value)` | `NodeInterrupt` deprecated since 1.0 |
| `out["__interrupt__"]` | `out.interrupts` with `version="v2"` | legacy shape still works |
| `interrupt_before`/`interrupt_after` for HITL | `interrupt()` | static ones = debugging only |
| `graph.get_state(cfg).next` | unchanged | ✅ current |
| `update_state(cfg, values)` | unchanged | ✅ current |

---

## 7. HITL for agents: `HumanInTheLoopMiddleware`

In LangChain 1.x you don't have to hand-roll `interrupt()` in an agent.
`HumanInTheLoopMiddleware` gates **tool calls** and uses the same interrupt
machinery.

```python
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware

agent = create_agent(
    model=model,
    tools=[send_email, delete_file],
    middleware=[
        HumanInTheLoopMiddleware(
            interrupt_on={"send_email": True, "delete_file": True},
            interrupt_mode="batched",     # or "per_call"
        )
    ],
    checkpointer=InMemorySaver(),
)
```

### 7.1 The two modes

| Mode | Interrupt value | How to answer |
|---|---|---|
| `"batched"` (default) | `HITLRequest` — lists every gated call in the turn | `Command(resume={"decisions": [...]})`, one decision per call **in order** |
| `"per_call"` | `ToolApprovalRequest` — one call per interrupt | `Command(resume={interrupt_id: decision})` |

⚠️ `"per_call"` is **planned to become the default in the next major
release** — so prefer it for new code if you can.

### 7.2 The four decision types

```python
{"type": "approve"}                            # run the tool as-is
{"type": "reject", "message": "..."}           # don't run it; tell the model why
{"type": "edit", "edited_action": {            # run it with different args
    "name": "delete_file", "args": {"path": "/tmp/report-ARCHIVED.pdf"}}}
{"type": "respond", "message": "..."}          # answer AS the tool; it never runs
```

### 7.3 Worked example (verified in `ex11`)

**Batched:**

```
1. BATCHED mode: one interrupt per model turn
   interrupts: 1
   payload type: HITLRequest
      action: send_email {'to': 'alice@example.com', 'subject': 'Report'}
      action: delete_file {'path': '/tmp/report.pdf'}
   review_configs: [{'action_name': 'send_email',
                     'allowed_decisions': ['approve','edit','reject','respond']}, ...]
   tools run so far: []

2. Answer with a HITLResponse: approve one, reject the other
   tools run now: ['email to alice@example.com: Report']
   -> The email ran, the delete did NOT.
```

**Per-call** — and note the important detail that an approval executes its
tool *immediately*, while the next gated call is still waiting:

```
5. Answer the first one, the second appears next
   interrupts now: 1
   tools run after approving the FIRST call: ['email to alice@example.com: Report']
   -> in per_call mode an approval executes that tool IMMEDIATELY,
      while the next gated call is still waiting for a decision.
```

### 7.4 Finding paused agents from your API

```python
snap = agent.get_state(cfg)
snap.next        # ('HumanInTheLoopMiddleware.after_model',)
snap.interrupts  # the pending HITLRequest
```

The `next` value tells you it is a *tool approval* pause (the middleware node)
rather than a custom node pause.

---

## 8. Putting it together: a minimal HITL API

```python
from fastapi import FastAPI
from langgraph.types import Command

app = FastAPI()

@app.post("/threads/{thread_id}/resume")
def resume(thread_id: str, body: dict):
    config = {"configurable": {"thread_id": thread_id}}
    decision = body["decision"]

    # answer by id if the client sent one, else by order
    snap = graph.get_state(config)
    if body.get("interrupt_id"):
        resume_value = {body["interrupt_id"]: decision}
    else:
        resume_value = decision

    out = graph.invoke(Command(resume=resume_value), config, version="v2")
    return {"value": out.value, "interrupts": [i.value for i in out.interrupts]}
```

L19 turns this into a production approval system with authorization, timeouts
and an audit trail.

---

## 9. Common mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| Side effect above `interrupt()` | it runs twice | move it below, or make it idempotent |
| No checkpointer | nothing to resume from | always compile with one |
| Reading `out["__interrupt__"]` in new code | legacy shape | use `version="v2"` → `out.interrupts` |
| Answering by order when there are 2 interrupts | wrong branch gets it | answer by `interrupt_id` |
| Expecting the interrupt value to reflect a later `update_state` | stale question | re-render after the edit |
| Raising `NodeInterrupt` | deprecation warning | use `interrupt()` |
| Using static breakpoints for HITL | no payload, no answer | use `interrupt()` |

---

## 10. Checkpoint yourself

- [ ] I can write the `interrupt()` / `Command(resume=...)` pair from memory.
- [ ] I know the difference between `out.value`/`out.interrupts` (v2) and
      `out["__interrupt__"]`.
- [ ] I know that the node restarts from the top on resume.
- [ ] I know that multiple interrupts pause one at a time.
- [ ] I know `response_schema` gives me a JSON Schema for the frontend.
- [ ] I know `NodeInterrupt` is deprecated and static breakpoints are for
      debugging.

**Next → [L19: HITL part 2 — production approval flows](./L19-hitl-production-approval-flows.md)**
