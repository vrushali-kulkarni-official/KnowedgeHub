# L09 — Parallel Agents and Aggregation

**Module:** M70 (part 1) · **Time:** ~2.5h · **Example:** `examples/ex12_parallel_fanout.py`, `examples/ex13_aggregation.py`

---

## 0. The one benefit a single agent cannot get

Everything else in this course trades cost for quality or isolation.
**Parallelism trades nothing.** Independent subtasks running concurrently
cost the same tokens as running them one after another, but take a fraction
of the wall-clock time.

`ex12` measured it with four branches, each doing 0.35s of tool work:

```
parallel :    370.3 ms
serial   :   1431.6 ms
speed-up : 3.87x      (3.83-3.87x across runs - it is a real
                     measurement, so it moves a little with machine load)
```

Same tokens. Same agents. Only the **schedule** changed.

> This is the benefit to reach for when a user complains that your agent is
> slow. Context isolation and specialization make answers *better*;
> parallelism makes them *faster*. Only one of those is visible as a
> support ticket.

### But first: are the subtasks actually independent?

Parallelism only works if the branches do not need each other. Check:

- **Do they need the same input?** Yes → fine, fan out with the same input.
- **Do they need each other's output?** Yes → **not independent**. You have
  a pipeline, not a fan-out. Use a pipeline (L01).
- **Do they conflict (write the same resource)?** Yes → serialise that part.

A "parallel" design where branch B secretly needs branch A's output is a
pipeline with extra confusion.

---

## 1. The mechanism

```python
from langgraph.types import Send

def fanout(state: FanState):
    # One Send per branch -> all branches run in the SAME superstep.
    return [
        Send("worker", {"task": t, "question": state["question"],
                        "messages": state["messages"]})
        for t in topics
    ]

g.add_conditional_edges("planner", fanout, ["worker"])
```

That is the whole mechanism. `Send` is "run this node with this input, now".

### The two `Send` rules (from L02/L03, repeated because they bite here)

1. **The payload is the node's entire input.** It does not merge with the
   graph state.
2. **The payload bypasses the target's `input_schema`.** Build it from
   explicit fields — never `dict(state)`.

### The merge

Every branch writes to the same channel, so that channel needs a **merging**
reducer:

```python
results: Annotated[list[dict], lambda a, b: a + b]
```

With a plain last-value channel, the branches would overwrite each other
and you would lose all but one.

---

## 2. One agent instance per branch

This is a subtle and very real bug:

```python
def make_branch_agent(tag):
    model = scripted(router=once_then_final("fetch", {"topic": tag}, final=f"{tag}: ..."))
    return create_agent(model, tools=[fetch], name=f"branch_{tag}")

agents = {t: make_branch_agent(t) for t in topics}    # <- one per branch
```

**Do not share one agent instance across branches.** With a real model the
shared instance is fine (it is stateless between invocations), but with any
stateful component — a scripted model, a cached client, a counter — the
branches interleave and the outputs get mixed up. The symptom is
confusing: one branch gets another branch's answer.

One instance per branch is also what gives you **per-branch budgets**: each
branch can have its own middleware, its own model, its own limits.

---

## 3. Fan-in: merging without drowning

You now have N results. How do you combine them?

### The merge strategies

| shape | what it does | when |
|---|---|---|
| **concat** | keep everything, in order | the default; the branches are complementary |
| **dedupe** | drop exact duplicates | branches may return the same boilerplate |
| **rank** | keep the top N by some score | branches are alternatives, ranked |
| **vote** | keep only the most common answer | the question has one right answer (L09 §4) |
| **judge** | let a model pick the best | quality varies and "best" is subjective (L09 §5) |
| **summarise** | a model condenses them into one | there are many and they are long |

### Always cap the fan-in

Merging 50 branch outputs into one prompt is prompt-stuffing with extra
steps. If the branches are numerous, summarise at the boundary — L08's
"summary flows up" rule.

A good fan-in node produces **one bounded result**, not a concatenation:

```python
def aggregate(state: FanState):
    lines = [f"{f['topic']}: {f['summary'][:70]}" for f in state["findings"]]
    return {"final_answer": "; ".join(lines)}
```

---

## 4. Voting

```python
from collections import Counter

def normalise(text: str) -> str:
    """Make answers comparable."""
    return " ".join(text.lower().strip().rstrip(".").split())

def vote(candidates: list[str]) -> tuple[str, dict]:
    normalised = [normalise(c) for c in candidates]
    counts = Counter(normalised)
    if not counts:
        return "", {}
    winner_norm = counts.most_common(1)[0][0]
    for c, n in zip(candidates, normalised):
        if n == winner_norm:
            return c, dict(counts)
    return candidates[0], dict(counts)
```

### Normalise before counting

"Yes." / "yes" / "YES" must count as the same answer, or your vote is
split for no reason. `ex13` normalises case, whitespace and trailing
punctuation.

### Ties

A tie needs a deterministic rule. `ex13` breaks ties by first-seen, which
is reproducible but arbitrary. For a real system, prefer escalating to a
judge rather than picking arbitrarily.

---

## 5. Judging

```python
class VerdictSchema(BaseModel):
    """Which candidate is best?"""
    index: int = Field(description="0-based index of the best candidate")
    reason: str = Field(description="why it is best")

judge_agent = create_agent(model, tools=[], response_format=VerdictSchema)
out = judge_agent.invoke({"messages": [user(f"Which is best?\n{listing}")]})
verdict = out["structured_response"]
```

> **Remember:** with the default `ToolStrategy`, the synthetic tool is
> named after your **schema class**. `class VerdictSchema` → the model
> must call a tool named `VerdictSchema`. Rename the class and you must
> rename the tool call.

---

## 6. The hybrid — what to actually ship

Running the judge on every request is wasteful when a vote would do. You
are multiplying your cost by N for a decision you could make with
arithmetic.

```python
def hybrid(candidates: list[str], margin: int = 2):
    winner, counts = vote(candidates)
    if not counts:
        return "", "none", counts
    ranked = counts.most_common()
    if len(ranked) == 1:
        return winner, "vote (unanimous)", counts
    top_count = ranked[0][1]
    second_count = ranked[1][1] if len(ranked) > 1 else 0
    if top_count - second_count >= margin:
        return winner, f"vote ({top_count} vs {second_count})", counts
    verdict = judge(candidates)
    return candidates[verdict.index], f"judge (vote was {top_count} vs {second_count})", counts
```

`ex13` output:

```
CLEAR MAJORITY
  candidates : ['LangGraph is a graph framework.', 'LangGraph is a graph framework.', 'It is a DB.']
  votes      : {'langgraph is a graph framework': 2, 'it is a db': 1}
  method     : vote (2 vs 1)

SPLIT VOTE -> JUDGE DECIDES
  votes      : {'langgraph is a graph framework': 1, 'langgraph is a workflow engine': 1, 'it is a database': 1}
  method     : judge (vote was 1 vs 1)
```

**Ship the hybrid.** You pay for the judge only on the hard cases.

---

## 7. Choosing a strategy

| the question | answers look like | use |
|---|---|---|
| "how many bugs?" | a number | **vote** |
| "is this a billing or a support issue?" | a label | **vote** |
| "which of these three drafts is best?" | free text, varying quality | **judge** |
| "what do we know about X?" | complementary facts | **concat** |
| "summarise these 20 documents" | long text | **summarise** |

---

## 8. The cost of parallelism (be honest about it)

Parallelism is free in *latency*, not in *tokens*. N branches = N times the
token spend of one branch.

That means:

- **Do not fan out for work you can do once.** If three branches would all
  call the same expensive tool, do it once and fan out the *analysis*.
- **Cap the fan-out width.** 3-5 branches is usually plenty. 20 branches
  will hit rate limits and produce 20 mediocre answers.
- **Give the branches a budget** (L10).

A practical rule: fan out over **subtasks**, not over **restatements**.

---

## 9. Debugging a fan-out

From L11, fan-out specific:

* **A branch produced nothing.** Stream `updates` with `subgraphs=True` and
  look for a namespace with a `tools` span but no following `model` span.
* **The fan-in has the wrong count.** Check the reducer on the target
  channel — a last-value channel keeps only one.
* **The branches are not actually parallel.** Check the wall-clock time vs
  the sum of the branch times.
* **One branch ran twice.** You probably have both a `Send` and a
  conditional edge pointing at the same node (L06 Rule A).

---

## 10. Run it

```bash
PYTHONPATH=examples .venv/bin/python examples/ex12_parallel_fanout.py
PYTHONPATH=examples .venv/bin/python examples/ex13_aggregation.py
```

---

## What you should be able to do now

- Explain why parallelism is the one benefit a single agent cannot get, with
  a measurement.
- Decide whether a set of subtasks is genuinely independent.
- Write a `Send` fan-out with a correct merge reducer.
- Choose between concat, dedupe, rank, vote and judge — and justify it.
- Implement the hybrid (vote first, judge only on a tie).
- Explain why parallelism is free in latency but not in tokens.

**Next:** L10 — budgets, limits and the failure modes that actually bite.
