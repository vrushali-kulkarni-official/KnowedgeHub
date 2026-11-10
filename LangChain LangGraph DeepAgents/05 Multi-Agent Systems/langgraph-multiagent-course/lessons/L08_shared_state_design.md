# L08 — Shared State Design at Scale

**Module:** M69 (part 2) · **Time:** ~2h · **Example:** `examples/ex11_shared_state_design.py`

---

## 0. Two diseases of multi-agent state

### Disease 1 — prompt stuffing

Every agent gets the full `messages` transcript. Every agent pays for every
previous turn, on every model call, forever.

`ex11` measured it:

```
prior turns   msgs seen   chars seen
          0           3           23
          5          13         3273
         20          43        13023
         50         103        32523
```

In a team of N agents, this is the dominant cost — and it grows with the
number of turns, so it gets worse exactly when your system is busiest.

### Disease 2 — the graveyard schema

Every agent needs one more field, so the schema grows forever. Nobody
knows which fields are still read. Every node's `input_schema` ends up
being the whole schema, so context isolation quietly dies.

Both diseases have the same cure: **decide deliberately where each piece
of data lives, and enforce it with schemas.**

---

## 1. The three homes, and the decision procedure

When a piece of data must cross a boundary, ask three questions in order:

```
Q1. Is it a TURN (something someone said) or a FACT?
    TURN -> messages
    FACT -> Q2

Q2. Is it BIG (bigger than a few hundred characters)?
    YES -> the store, and pass the ID
    NO  -> Q3

Q3. Does every agent need it?
    YES -> shared state, no input_schema narrowing
    NO  -> shared state + a NARROW input_schema on each node
```

### Worked examples

| data | home | why |
|---|---|---|
| "Customer said: my login is broken" | `messages` | it is a turn |
| "ticket_id = 9001" | shared state, typed field | it is a fact, not a turn |
| a 40 KB PDF | the store, id in state | too big for a prompt |
| the full web-search dump | the store | too big; the summary is what matters |
| the researcher's three findings | shared state, `list[str]` | structured fact |
| the current user's plan name | shared state, `str` | small fact, needed by one agent |

---

## 2. Schema design rules

### Rule 1 — `messages` holds the conversation and nothing else

If a value is a fact, not a turn, it does not belong in `messages`. Every
message in `messages` is re-sent, re-read, and re-paid-for on every model
call of every agent.

### Rule 2 — every fact gets a type

```python
class TeamState(AgentState):
    findings: Annotated[list[dict], lambda a, b: a + b]
    verdict:  str
    score:    float
```

vs. the graveyard:

```python
class TeamState(AgentState):
    research_output: str
    analysis_output: str
    writing_output: str
    review_output: str
    scratchpad: str
    debug_notes: str
    everything: str
```

Both grow forever. The second one is worse because nobody can tell which
field is authoritative.

### Rule 3 — give every node a narrow `input_schema`

This is the **only** mechanism LangGraph gives you for context isolation
(L02 rule 1). A node without one receives the whole schema.

```python
class ReviewerInput(AgentState):
    draft: str
    verdict: str

g.add_node("reviewer", reviewer_node, input_schema=ReviewerInput)
```

### Rule 4 — choose the reducer deliberately

| you want | reducer | example |
|---|---|---|
| accumulate | `lambda a, b: a + b` | findings from parallel branches |
| merge per key | `lambda a, b: {**a, **b}` | counters, per-agent status |
| last write wins | (no annotation) | a single "current stage" field |
| sum | `lambda a, b: a + b` (ints) | a shared budget spent in parallel |

> **The parallel-increment pattern** (from the `ex17` capstone): when N
> branches each spend 1 unit of budget, use a **sum** reducer and have each
> branch write the **increment**, not the new total.
>
> ```python
> budget_used: Annotated[int, lambda a, b: a + b]
> # branch writes:  {"budget_used": 1}      <- the increment
> ```
>
> If each branch wrote the absolute total, the branches would overwrite
> each other and the total would be wrong.

### Rule 5 — keep append-reducer lists out of an agent's `state_schema`

The echo trap (L02 §3). Mergers are safe; appenders are not.

### Rule 6 — summarise at every boundary

A mid-tier supervisor should receive a **summary** of its leaves, not their
raw transcripts. A top tier should receive a **summary** of its mid tiers.

This is the same rule as L07's progress reporting, applied to *content*:
information flows up as summaries, down as tasks.

### Rule 7 — give every field a default

```python
class TeamState(AgentState):
    findings: Annotated[list[dict], lambda a, b: a + b]
    final_answer: str = ""
```

A partial state (a resumed run, a branch that returned early) should not
explode with `KeyError` at 3am. This matters especially with a
checkpointer, where a resumed run may start from a partially-populated
state.

---

## 3. Artifacts: the store

```python
from langgraph.store.memory import InMemoryStore

store = InMemoryStore()
store.put(("artifacts",), "report-v1", {"text": BIG_PAYLOAD})
```

Namespaces are tuples — `("artifacts",)`, `("docs", "2026")`,
`("tenant", "acme", "files")`. That is how you keep tenants apart.

### The pattern

```python
@tool
def fetch_artifact(artifact_id: str) -> str:
    """Fetch a stored artifact by id."""
    return f"[handle to {artifact_id}]"
```

```python
def researcher(state):
    item = store.get(("artifacts",), "report-v1")
    payload = item.value["text"]
    store.put(("artifacts",), "report-summary-v1", {"text": summarise(payload)})
    return {"artifact_ids": ["report-summary-v1"]}    # ids only
```

### Why this is not just "a database"

Three reasons specific to agents:

1. **The store is not the checkpoint.** A checkpoint is a snapshot of the
   graph state; the store is a long-lived, addressable key-value space
   that survives across threads and runs.
2. **Tools can address it directly.** `InjectedStore` gives a tool the
   store, so an agent can pull an artifact on demand without it ever being
   in the prompt.
3. **It is what makes context isolation real.** An agent that receives a
   4 KB document and one that receives a 12-character ID are worlds apart
   in cost.

### When the store is NOT enough

If the artifact is *the* thing being reasoned about and it must be in the
prompt every time, the store does not help — you need to summarise it
first. The store moves the problem, it does not solve it.

---

## 4. Keeping `messages` bounded

Three tools, in increasing order of intrusiveness.

### 4.1 `SummarizationMiddleware` — rewrite the state transcript

```python
from langchain.agents.middleware import SummarizationMiddleware

agent = create_agent(
    model, tools=tools,
    middleware=[
        SummarizationMiddleware(
            model=cheap_model,
            trigger={"fraction": 0.5},        # summarise at 50% of the window
        ),
    ],
)
```

* It **rewrites the state**. The checkpoint holds the summary.
* A fractional trigger needs the model's token limit, which comes from the
  model's `profile`. A real Gemini model carries this automatically; a
  custom model must declare it:
  `profile={"max_input_tokens": 1_048_576}`.
* Otherwise you get: `ValueError: Model profile information is required to
  use fractional token limits`.

### 4.2 `ContextEditingMiddleware` — trim only the model request

It edits what the model sees **for that call**; the checkpoint keeps the
full transcript. Use it when you need the full history for replay but a
shorter prompt for the model.

### 4.3 Don't build the history in the first place

The most effective option: keep the *conversation* short and put the
*knowledge* in shared state.

```python
# BAD - every turn is in messages forever
messages = transcript + [new_turn]

# GOOD - the summary is in state; messages holds only the recent exchange
return {
    "messages": [new_turn],                      # short
    "summary": updated_summary,                  # grows slowly, is bounded
}
```

---

## 5. A worked schema

```python
class TeamState(AgentState):
    # --- the conversation (short) ---
    messages: Annotated[list, add_messages]

    # --- structured facts ---
    plan: list[str]
    findings: Annotated[list[dict], lambda a, b: a + b]     # append
    artifacts: Annotated[dict[str, str], lambda a, b: {**a, **b}]   # merge
    brief: str = ""
    final_answer: str = ""
    status: Literal["routing", "working", "done"] = "routing"

    # --- budgets and bookkeeping ---
    budget_used: Annotated[int, lambda a, b: a + b]         # sum
    trace: Annotated[list[str], lambda a, b: a + b]         # append
```

And per-node inputs:

```python
class PlannerInput(AgentState):
    question: str

class WorkerInput(AgentState):
    task: str
    brief: str

class AggregatorInput(AgentState):
    findings: list[dict]
```

---

## 6. Reviewing a schema

```
[ ] Is every field either a fact or a turn?  (Not both.)
[ ] Does every node have a narrow input_schema?
[ ] Does every parallel branch write to a MERGING channel?
[ ] Are append-reducer lists out of every agent's state_schema?
[ ] Is any payload over ~1 KB still travelling as a value rather than an id?
[ ] Does every field have a default?
[ ] Could a mid tier receive raw leaf output instead of a summary?
[ ] If the transcript grows without bound, is there a summarisation step?
```

---

## 7. Run it

```bash
PYTHONPATH=examples .venv/bin/python examples/ex11_shared_state_design.py
```

---

## What you should be able to do now

- Decide where any given piece of data lives, and justify it.
- Write a state schema with correct reducers, including the parallel
  increment pattern.
- Explain prompt stuffing and the graveyard schema, and prevent both.
- Use the store to keep big payloads out of the prompt.
- Choose between `SummarizationMiddleware` and `ContextEditingMiddleware`.

**Next:** L09 — parallel agents and aggregation: the one benefit a single
agent cannot get, and how to merge the results without drowning in them.
