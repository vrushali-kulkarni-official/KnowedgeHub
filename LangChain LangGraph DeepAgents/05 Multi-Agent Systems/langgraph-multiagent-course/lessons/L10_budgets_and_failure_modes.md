# L10 — Budgets, Limits and the Failure Modes That Actually Bite

**Module:** M70 (part 2) · **Time:** ~2h · **Example:** `examples/ex14_budgets.py`

---

## 0. Why a single agent's safety net is not enough

A single agent can burn money in one way: it loops. One `recursion_limit`
covers that.

A multi-agent system can burn money in **five** ways:

1. N agents × M turns each — the baseline multiplier.
2. A swarm that hands off in a circle, forever.
3. A parallel fan-out where every branch is expensive.
4. A tool that retries internally, inside every branch.
5. A hierarchy where each level multiplies the one below.

So you need **three layers of defence**, each catching what the others miss.

---

## 1. Layer 1 — per-agent limits (the middleware)

These attach to **one agent**, which makes them the natural place for a
per-agent budget.

```python
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware

agent = create_agent(
    model,
    tools=tools,
    middleware=[
        ModelCallLimitMiddleware(thread_limit=8, exit_behavior="end"),
        ToolCallLimitMiddleware(thread_limit=20, exit_behavior="end"),
    ],
)
```

### The two middlewares

| middleware | counts | `exit_behavior` |
|---|---|---|
| `ModelCallLimitMiddleware` | model calls | `"end"` (stop the agent, return what you have) or `"error"` (raise) |
| `ToolCallLimitMiddleware` | tool calls (optionally per `tool_name`) | `"end"` or `"continue"` (skip that tool call) |

Both also take `run_limit` (per `invoke`) as well as `thread_limit` (per
thread/conversation).

### What it looks like when it fires

```
ModelCallLimitMiddleware:
  human | go
  ai    |
  tool  | again
  ai    |
  tool  | again
  ai    |
  tool  | again
  ai    | Model call limits exceeded: thread limit (3/3)
```

The agent stops **gracefully**, with a message explaining why. That message
reaches the user, which is much better than a timeout.

### `exit_behavior="end"` vs `"error"`

* `"end"` — the agent returns what it has, with a note. Use this for
  user-facing agents: a partial answer beats an exception.
* `"error"` — raises. Use this for internal workers where a partial result
  is worse than a failure.

---

## 2. Layer 2 — graph limits (the config)

```python
out = app.invoke(inputs, {"recursion_limit": 30})
```

**`recursion_limit` is the superstep cap, and `create_agent` overrides it
to 9999.** (L03 trap 4.) Always pass your own.

Also per-node:

```python
from langgraph.types import RetryPolicy

g.add_node(
    "call_api", call_api,
    retry_policy=RetryPolicy(
        max_attempts=3,
        initial_interval=0.01,
        backoff_factor=2.0,
        retry_on=(TimeoutError, ConnectionError),
    ),
)
```

`retry_on` is important: retrying a `ValueError` (a bug) just wastes
tokens three times. Retry only *transient* errors.

---

## 3. Layer 3 — team limits (your own code)

Per-agent limits do not know that there are five agents. The **team**
budget lives in the shared state.

```python
class BudgetState(AgentState):
    budget_used: int
    max_budget: int
    results: Annotated[list[str], lambda a, b: a + b]

def supervisor(state: BudgetState):
    if state["budget_used"] >= state["max_budget"]:
        return {"results": ["BUDGET EXHAUSTED - stopping"]}
    return {"budget_used": state["budget_used"] + 1}
```

In the `ex17` capstone this is combined with the parallel-increment
pattern:

```python
budget_used: Annotated[int, lambda a, b: a + b]   # sum reducer
# each branch writes the INCREMENT:  {"budget_used": 1}
```

For a real money budget, track tokens rather than a counter. LangChain
callbacks give you `usage` on every model response; accumulate it in the
state (or in the `BaseStore`) and check it before dispatching more work.

---

## 4. The production budget recipe

```python
# 1. Every agent gets a hard model-call cap.
agent = create_agent(
    model, tools=tools,
    middleware=[
        ModelCallLimitMiddleware(thread_limit=8, exit_behavior="end"),
        ToolCallLimitMiddleware(thread_limit=20, exit_behavior="end"),
    ],
)

# 2. Every graph gets a recursion cap (create_agent's default is 9999!).
app.invoke(inputs, {"recursion_limit": 30})

# 3. Every node that calls a flaky service gets a retry policy.
g.add_node("call_api", call_api,
           retry_policy=RetryPolicy(max_attempts=3, retry_on=(TimeoutError,)))

# 4. The TEAM gets a shared budget counter in the state, and the
#    supervisor checks it before dispatching more work.

# 5. Swarms get a visit counter (L06) AND a RemainingSteps check.

# 6. Fan-outs get a width cap.
assert len(state["plan"]) <= 5
```

---

## 5. The five failure modes

### 5.1 Tool errors: swallowed or fatal?

| the error | outcome |
|---|---|
| **Tool invocation error** (bad arguments, schema validation) | turned into ToolMessage **text**; the model sees it and can retry |
| **any other exception inside the tool body** | **propagates** and crashes the graph |

`ex14`:

```
1a. bad arguments -> "Error invoking tool 'needs_int' with kwargs ...
                     tool_call_id: Field required"      (recoverable)
1b. RuntimeError -> RuntimeError: upstream 503          (graph dies)
1c. THE FIX: catch inside the tool -> "ERROR: upstream 503. Tell the user
     the service is down."                               (recoverable)
```

**Rule: catch inside the tool, return an error string.** An agent can
recover from a message; it cannot recover from a crash.

```python
@tool
def safe_tool(x: str) -> str:
    """Never raises."""
    try:
        return call_service(x)
    except Exception as exc:
        return f"ERROR: {exc}. Tell the user the service is down."
```

### 5.2 Context overflow

A node can legally write 200,000 characters into `messages`. The next
model call then fails on a real model. The graph does not complain.

Prevention: `SummarizationMiddleware` (L08 §4.1), `ContextEditingMiddleware`
(L08 §4.2), and the store for big payloads (L08 §3).

### 5.3 No termination

`create_agent` ships with `recursion_limit = 9999`. A runaway loop makes
~9999 model calls before anything stops it. Always pass an explicit limit,
and always add `ModelCallLimitMiddleware`.

### 5.4 Lost update

Two nodes writing the same last-value channel in the same superstep:

```
InvalidUpdateError: At key 'slot': Can receive only one value per step.
Use an Annotated key to handle multiple values.
```

This is the error you get from a double-dispatch (L06 Rule A) or from two
parallel branches writing the same field. Fix: give the field a merging
reducer, or make sure only one node writes it.

### 5.5 Silent state drop

```python
def writer(state):
    return {"known": "ok", "unknown": "gone"}     # 'unknown' is not in the schema
```

```
unknown in result? False
```

No error, no warning. The key was never in the schema, so it never existed.
(L02 rule 3.) This one wastes the most time, because nothing tells you.

---

## 6. A failure-handling table for a team

| failure | where to handle it | mechanism |
|---|---|---|
| transient API error | the tool | `try/except` → error string; or `retry_policy` |
| bad tool arguments | the tool schema | model retries (ToolInvocationError is recoverable) |
| the model loops | the agent | `ModelCallLimitMiddleware` |
| the graph loops | the graph | `recursion_limit` + a visit counter |
| a specialist fails | the team | the mid tier escalates (L07) |
| the team is broke | the team | the shared budget counter |
| everything failed | the team | return a partial result with a note |

---

## 7. Observability of limits

A limit that fires silently is a bug waiting to happen. Make it visible:

* The middleware's stop message says exactly which limit was hit. Surface
  it to the user (or at least to your logs).
* In Langfuse, a limit that fires shows up as an agent span with an
  unusual number of `model` children. (L11.)
* Count limit hits in production. A sudden spike means a prompt change, a
  tool regression, or an upstream outage — and you want to know before
  your bill does.

---

## 8. Run it

```bash
PYTHONPATH=examples .venv/bin/python examples/ex14_budgets.py
```

---

## What you should be able to do now

- Set up three layers of defence and explain what each one catches.
- Configure `ModelCallLimitMiddleware` and `ToolCallLimitMiddleware`, and
  choose `exit_behavior` correctly.
- Add a node `retry_policy` that only retries transient errors.
- Implement a team-level budget with a correct reducer.
- Distinguish a recoverable tool error from a fatal one, and fix the fatal
  one.
- Recognise all five failure modes from their symptoms.

**Next:** L11 — observability: Langfuse trace trees for multi-agent
systems, and the streaming debugging playbook.
