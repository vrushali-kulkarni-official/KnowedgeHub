# L01 — Should You Even Use Multiple Agents?

**Module:** M66 (part 1) · **Time:** ~1.5h · **Example:** `examples/ex01_decision_matrix.py`, `examples/ex02_topologies.py`

---

## 0. The uncomfortable truth

Most "multi-agent frameworks" tutorials start by showing you a supervisor
routing to three specialists, and they never ask whether that was a good
idea. So let's start where nobody starts: **with the case against it.**

The default answer for any agentic problem is:

> **One agent, with really good tools.**

Not because multi-agent is a fad, but because splitting an agent has a
hard, measurable cost and a soft, speculative benefit.

### The cost side (all measured in `ex01`)

| | single agent | supervisor team |
|---|---|---|
| agents | 1 | 4 |
| **LLM round trips** | **2** | **4** |
| tool calls | 1 | 1 |
| top-level transcript | 4 messages | 4 messages |

Two extra LLM round trips to answer the same question. On a real model that
is real money and real latency, and it happens on *every* request.

### The benefit side (three reasons, and only three)

Multi-agent earns its keep for exactly these reasons. If you cannot name
one of them for your specific problem, **do not split the agent.**

1. **Context isolation.**
   A specialist that only ever sees its own slice of the world is not
   distracted by the rest of it. In `ex01` the supervisor's transcript stayed
   at 4 messages even though the researcher did a full tool round trip,
   because the researcher's conversation stayed *inside* the researcher.

2. **Parallelism.**
   Independent subtasks can run at the same time. `ex12` measured a **~3.9x
   speed-up** with four branches doing 0.35s of work each. This is the only
   benefit a single agent genuinely cannot get.

3. **Specialization.**
   One focused prompt beats one muddled prompt. A "billing specialist" that
   is told *"never speculate, look it up"* behaves measurably better than a
   generalist asked to do billing among eleven other things.

There is no fourth reason. "It feels more modular" is not a reason. "It's
how the papers do it" is not a reason.

---

## 1. The decision framework

Work through this in order. Stop at the first "yes".

```
Q1. Are the subtasks INDEPENDENT of each other?
    YES -> you may want a parallel fan-out (L09), even with NO supervisor.
    NO  -> continue.

Q2. Does one part of the work need a DIFFERENT, focused prompt (or a
    different model, or a different set of tools) than the rest?
    YES -> a specialist agent is justified (L04).
    NO  -> continue.

Q3. Does one part of the work produce so much output that including it in
    the main agent's context would swamp it?
    YES -> isolate it (L02: artifacts + store).
    NO  -> continue.

Q4. Do you need an AUDIT TRAIL of who did what, or a human approval step
    in the middle?
    YES -> you need a shared state, which usually means a graph (L08).
    NO  -> STOP. Use one agent with good tools.
```

**The escape-hatch rule.** There is always a way to split later. Start with
one agent, get it correct, measure it, and split only the part that is
actually hurting. A single agent is a *supervisor with one worker* — it is
one refactor away from a team.

---

## 2. The four topologies (all four are real, runnable graphs)

`ex02_topologies.py` builds and runs each of these. The names matter,
because you will see them in every framework's docs.

### Pipeline — fixed sequence, zero routing

```
START -> extract -> summarise -> publish -> END
```

* **Routing cost:** zero. No LLM decides anything.
* **When to use:** the steps are known and fixed. This is the most
  under-used multi-agent pattern and often the *best* answer.
* **Watch out for:** it cannot handle "this document is a complaint, route
  it to legal instead".

### Supervisor — one router owns the work

```
           -> researcher ->\
START -> supervisor -> billing  -> END
           -> writer    ->/
```

* **Routing cost:** one LLM decision per dispatch.
* **When to use:** one coordinator must decide "who handles this?" and the
  specialists are genuinely different.
* **Strength:** it is easy to observe, easy to bound, easy to debug.
* **Watch out for:** a flat supervisor with 10 specialists has a huge tool
  list and degrading routing accuracy. Split into a hierarchy (L07).

### Hierarchical — supervisors of supervisors

```
              -> content_supervisor -> writer
START -> top  -> content_supervisor -> reviewer
              -> research_supervisor -> researcher
```

* **Routing cost:** one decision per level, but each level has fewer options.
* **When to use:** more than ~6 specialists.
* **Strength:** routing quality does not degrade with team size, because
  each router only sees its own domain.
* **Watch out for:** latency compounds with depth, and errors must
  escalate *upward* only.

### Swarm / handoffs — peers hand control to each other

```
START -> triage -> researcher -> writer -> END
                     |            |
                     +-- handoff -+
```

* **Routing cost:** one decision per handoff, and the path length is
  unpredictable.
* **When to use:** the experts genuinely need to talk to each other in a
  conversation you do not want to script.
* **Strength:** no bottleneck; a peer can talk directly to a peer.
* **Watch out for:** **ping-pong**. Two peers that keep handing back to
  each other will burn your entire budget. This is the #1 swarm bug and
  `ex09` shows the fix.

---

## 3. The cost / latency / complexity math

Do this arithmetic *before* you build. It is 5 minutes and it will save you
a day.

Let:
- `A` = number of agents
- `T` = average turns per agent
- `C` = average cost of one model call (input + output tokens)
- `L` = average latency of one model call
- `P` = depth of the longest path (the critical path)

**Cost** = `A × T × C` (roughly — parallel branches still cost the same)
**Latency** ≈ `P × L` (NOT `A × L` — parallel branches overlap)
**Complexity** grows with the number of *routed* edges, not nodes.

Worked example, a 4-agent supervisor team:

| | single agent | supervisor team |
|---|---|---|
| model calls | 4 | 4 × 2 = 8 (supervisor + specialist) |
| cost | `4C` | `8C` — **2x** |
| latency | `4L` | `2L + L = 3L` (supervisor, then specialist) |
| worst case | — | supervisor may call 3 specialists sequentially: `4L` |

The brutal truth: **a supervisor team usually costs 2x and is often slower**,
because the supervisor adds a hop. It only wins when:
- the specialist's narrow focus makes the answer *better*, or
- the branches run in *parallel* (latency win, no extra cost), or
- the isolation prevents a specific failure you have actually observed.

### The complexity explosion

Routing is a graph edge. If each of your 4 specialists can hand off to any
of the other 3, you have 12 possible handoffs, and the number of distinct
conversation *paths* is combinatorial. That is why swarms need explicit
guards (`ex09`) and why hierarchies beat swarms at scale.

---

## 4. What "specialization" actually means

Specialization is not "a different agent with a different name". It is a
genuinely different **contract**:

```
SUPERVISOR   decides WHO.  Sees only summaries.  Never reads raw data.
RESEARCHER   finds FACTS.  Has the search tools.  Must cite.
REVIEWER     judges QUALITY.  Has no tools at all - it only reads.
```

The reviewer's power comes from what it does **not** have. A reviewer with
a web-search tool will go and look things up instead of reviewing. Give
each specialist the narrowest possible toolset.

**The best test for whether a specialist is real:** if you removed its
system prompt and gave it the same tools as everybody else, would it
produce a different answer? If not, you have not created a specialist — you
have created a second copy of the same agent with extra latency.

---

## 5. Decision table

| Situation | Recommendation |
|---|---|
| "The agent gets confused when it has too many tools" | Split by tool domain, supervisor + specialists (L04) |
| "It takes 40s to answer, it should take 10s" | Parallel fan-out (L09) |
| "Research output overwhelms the final answer" | Artifacts + store (L02, L08) |
| "We must show the user which expert handled what" | Shared state with a trace field (L08) |
| "A human must approve before we send the email" | Shared state + interrupt (Phase 8) |
| "The tool list is 12 items and routing is 60% accurate" | Hierarchical supervisors (L07) |
| "Two of our domains need different models" | Split those two out only (L04) |
| "It just feels like it should be multi-agent" | **Don't.** One agent + good tools |

---

## 6. Checklist before you commit

- [ ] I can name which of the three reasons applies (isolation / parallelism / specialization).
- [ ] I have measured the single-agent baseline.
- [ ] I have written down the expected model-call count for the team version.
- [ ] I have a plan for what happens when a specialist fails (L10).
- [ ] I know my budget cap and where it is enforced (L10).
- [ ] I can see the team in a trace (L11).

---

## 7. Run it

```bash
PYTHONPATH=examples .venv/bin/python examples/ex01_decision_matrix.py
PYTHONPATH=examples .venv/bin/python examples/ex02_topologies.py
```

`ex01` prints the measured table. `ex02` runs all four topologies end to
end and prints the path each one took.

---

## What you should be able to do now

- Explain, with numbers, why "single agent + good tools" is the default.
- Name the three (and only three) reasons multi-agent pays off.
- Draw the four topologies and say when each is right.
- Compute cost, latency and critical path for a proposed team.
- Decide, for a given problem, whether to split — and defend the decision.

**Next:** L02 — where information actually lives when it moves between
agents. State, messages, or artifacts. Get this wrong and every later
lesson will feel mysterious.
