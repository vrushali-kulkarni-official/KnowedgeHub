# L12 — The Capstone and the Production Checklist

**Module:** M70 (final) · **Time:** ~2h · **Example:** `examples/ex17_capstone.py`, `examples/ex18_gemini_real.py`

---

## 0. What you have built

Across twelve lessons you have assembled every construct needed to ship a
multi-agent system:

| lesson | construct | example |
|---|---|---|
| L01 | the decision framework | ex01, ex02 |
| L02 | state / messages / artifacts, the four filters, the echo trap | ex03, ex04 |
| L03 | `Command`, `Send`, the four traps | ex05 |
| L04 | agents-as-tools, structured routing | ex06, ex07 |
| L05 | hand-built teams, handoff briefs | ex08 |
| L06 | handoffs, swarms, loop guards | ex09 |
| L07 | hierarchies, progress, escalation | ex10 |
| L08 | schema design, the store, summarisation | ex11 |
| L09 | parallel fan-out, vote/judge aggregation | ex12, ex13 |
| L10 | budgets, limits, failure modes | ex14 |
| L11 | Langfuse trees, streaming debug | ex15, ex16 |

`ex17` puts them all together. Read it top to bottom — it is the shape of a
system you could ship.

---

## 1. The capstone, explained

`ex17` is a support team for a software product.

```
START
  ↓
planner ──────────────► produces a structured Plan (2 subtasks)
  ↓
fanout (Send ×2) ─────► investigators run CONCURRENTLY
  ↓
aggregate ────────────► bounded fan-in
  ↓
supervisor ───────────► final answer
  ↓
END
```

### The five things it gets right

**1. Planning is structured, not hard-coded.**

```python
class Plan(BaseModel):
    subtasks: list[str]
    brief: str

planner = create_agent(model, tools=[], response_format=Plan, name="planner")
```

The plan drives the fan-out. Change the model, and the plan changes.

**2. The branches are genuinely isolated.**

```python
def fanout(state: TeamState):
    return [
        Send("investigator", {"task": t, "brief": state["brief"],
                              "messages": state["messages"]})
        for t in state["plan"]
    ]
```

Each branch receives only `task` and `brief`. It does not receive the other
branch's findings, and it does not receive the whole state.

> **Remember (L02 rule 2):** the `Send` payload bypasses `input_schema`. It
> is built from explicit fields here on purpose. Note that `budget_used` is
> **not** in the payload — which is exactly why the budget uses a **sum
> reducer** and each branch writes the *increment*:
>
> ```python
> budget_used: Annotated[int, lambda a, b: a + b]
> # branch writes:  {"budget_used": 1}
> ```

**3. Long outputs live in the store.**

```python
store.put(("artifacts",), topic, {"text": answer})
return {"artifacts": {topic: f"artifact:{topic}"}}    # id, not payload
```

**4. The fan-in is bounded.**

```python
def aggregate(state: TeamState):
    lines = [f"{f['topic']}: {f['summary'][:70]}" for f in state["findings"]]
    return {"final_answer": "; ".join(lines)}
```

One summary, not a concatenation.

**5. There are three layers of budget.**

```python
middleware=[ModelCallLimitMiddleware(thread_limit=6, exit_behavior="end")]  # per agent
budget_used: Annotated[int, lambda a, b: a + b]                           # per team
{"recursion_limit": 40}                                                   # per graph
```

### What it does NOT do

Knowing what a good system leaves out is as important as knowing what it
does:

* **No HITL approval.** The capstone is not allowed to email the customer.
  In production, `interrupt()` + a checkpointer would gate that (Phase 8).
* **No persistence.** The checkpointer here is `InMemorySaver`; production
  needs Postgres.
* **No auth on the tools.** `search_docs` returns a canned string.
* **No token accounting.** The budget counts dispatches, not tokens.

---

## 2. Swapping in Gemini — the whole delta

```python
from langchain.chat_models import init_chat_model

model = init_chat_model("google_genai:gemini-3.8-flash")
```

That is the entire difference. The state schema, the `Send` fan-out, the
reducers, the handoff tools, the middleware, the store — all identical.

### The current Gemini model line (verified 2026-11-05)

| model ID | stage | context | max output | $/1M in / out |
|---|---|---|---|---|
| `gemini-4-argon` | Stable (2026-10-13) | 1,048,576 | 65,536 | $2 / $10 (intro) |
| `gemini-3.8-flash` | Stable (2026-09-02) | 1,048,576 | 65,536 | $0.75 / $3.75 (intro) |
| `gemini-3.6-flash` | Stable | 1,048,576 | 65,536 | $0.75 / $3.75 |
| `gemini-3.5-flash-lite` | Stable | 1,048,576 | 65,536 | **$0.30 / $2.50** |

### Model choices per role

| role | model | why |
|---|---|---|
| routing / classification | `gemini-3.5-flash-lite` | $0.30/$2.50; it only picks a name |
| summarisation | `gemini-3.5-flash-lite` | same |
| specialist reasoning | `gemini-3.8-flash` | the current GA workhorse |
| hard reasoning / the final answer | `gemini-4-argon` | the most capable model |

**Different agents can use different models.** That is one of the best
reasons to split an agent in the first place — a routing step on
Flash-Lite costs roughly a quarter of the same step on Flash.

### Retired or auto-routed — do not target these

| old ID | what happens |
|---|---|
| `gemini-2.5-pro` | auto-routes to `gemini-3.8-flash` from 2026-12-01 |
| `gemini-2.5-flash` | auto-routes to `gemini-3.5-flash-lite` from 2026-12-01 |
| `gemini-2.5-flash-lite` | superseded — use `gemini-3.5-flash-lite` |
| `gemini-3.5-flash` | auto-routes to `gemini-3.6-flash` |
| `gemini-3.7-flash` | auto-routes to `gemini-3.8-flash` |

> Google made the **Interactions API** the default interface in June 2026;
> `generateContent` is now considered legacy. `langchain-google-genai`
> handles that for you — you still just call `init_chat_model(...)`.

`ex18` is the runnable version of this.

---

## 3. The production checklist

Print this. Put it next to your code.

### Design

- [ ] I can name which of the three reasons (isolation / parallelism / specialization) justifies the split.
- [ ] I measured the single-agent baseline.
- [ ] The expected model-call count per request is written down and enforced.
- [ ] Every agent has a **narrow** tool set. A reviewer has no tools.
- [ ] Every handoff brief is self-contained, has an explicit contract, and is bounded.
- [ ] The topology is the simplest one that works (pipeline → supervisor → hierarchy → swarm).

### State

- [ ] `messages` holds only turns; facts live in typed fields.
- [ ] Every node has a narrow `input_schema`.
- [ ] Every parallel branch writes to a **merging** channel.
- [ ] Append-reducer lists are **out** of every agent's `state_schema` (echo trap).
- [ ] `Send` payloads are built from explicit fields, never `dict(state)`.
- [ ] Every field has a default.
- [ ] Payloads over ~1 KB live in the store, referenced by id.

### Routing

- [ ] Every `Command` from inside a nested agent uses `graph=Command.PARENT`.
- [ ] Every `Command` from a tool includes a `ToolMessage` with the right `tool_call_id`.
- [ ] `tool_call_id` is `Annotated[str, InjectedToolCallId]`.
- [ ] No node has both a `Command(goto=)` and a routing edge.
- [ ] The routing decision is derived in exactly one place.

### Limits

- [ ] Every agent has `ModelCallLimitMiddleware` and `ToolCallLimitMiddleware`.
- [ ] Every `invoke` passes an explicit `recursion_limit`.
- [ ] Flaky nodes have a `retry_policy` with a narrow `retry_on`.
- [ ] The team has a shared budget counter.
- [ ] Swarms have a visit counter **and** a `RemainingSteps` check.
- [ ] Fan-out width is capped.

### Failure handling

- [ ] Tools catch their own exceptions and return error strings.
- [ ] Failures escalate **upward**, never downward.
- [ ] The top tier returns partial results with a note, not an error page.

### Observability

- [ ] Every agent has `name=`.
- [ ] Langfuse (or equivalent) is attached to every run.
- [ ] The four streaming modes are in your debugging muscle memory.
- [ ] Limit hits are counted and alerted on.

---

## 4. The four questions to ask in code review

1. **What crosses each boundary, and what does the schema allow?**
2. **What stops this from looping?**
3. **What happens when this agent fails?**
4. **How much does one request cost, and what enforces that?**

If a reviewer cannot answer all four from the code, the code is not ready.

---

## 5. Where to go next

### Deepen what you just learned

| topic | what to read |
|---|---|
| HITL inside a team | Phase 8: `interrupt()`, `HumanInTheLoopMiddleware` |
| durable teams | Phase 8: Postgres checkpointer + store |
| production deployment | Phase 9: `langgraph dev`, the LangGraph SDK, streaming in a server |
| deep agents | the `deepagents` package (v0.7.x) — file-system-based agents on top of LangGraph |

### The `deepagents` package

Worth knowing about since you are studying it alongside this phase.
`deepagents` (v0.7.32, actively released) builds on LangGraph's agent
runtime and adds a **virtual filesystem**, **task planning** and
**subagent delegation** as first-class primitives.

The mapping to what you learned:

| what you learned | its counterpart in `deepagents` |
|---|---|
| agents-as-tools (L04) | built-in subagent delegation |
| the store / artifacts (L08) | the virtual filesystem |
| the shared state schema (L05, L08) | the todo list / planning tools |
| budgets (L10) | the same middleware stack |

The primitives you learned here — `create_agent`, `Command`, `Send`,
middleware, the store — are exactly the ones `deepagents` composes. So
Phase 10 is the foundation it assumes.

---

## 6. Run it

```bash
PYTHONPATH=examples .venv/bin/python examples/ex17_capstone.py
PYTHONPATH=examples .venv/bin/python examples/ex18_gemini_real.py
```

`ex17` runs the whole system offline and prints the trace, the plan, the
findings, the budget and the artifacts. `ex18` is the live Gemini version —
it prints the swap-in instructions when no API key is present.

---

## What you should be able to do now

- Build a multi-agent system from scratch using current APIs only.
- Choose a topology and a state schema with justification.
- Explain every non-obvious LangGraph behaviour this course covered, and
  recognise it when you meet it.
- Apply the production checklist to your own code.
- Know exactly which packages are deprecated and what replaced them.

**That is Phase 10. You now understand multi-agent systems at the level
where you can design one, debug one, and explain to someone else why it is
shaped the way it is.**
