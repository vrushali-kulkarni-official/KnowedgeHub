# PHASE 9 — Orientation: what "production" actually means for an agent

**Time: 30 minutes.** Read this before M62. It sets up the mental model that
makes the rest of the phase click.

---

## 1. The notebook-to-production gap

Everything up to Phase 8 had this shape:

```python
graph = build_graph()
result = graph.invoke({"question": "..."})
print(result["answer"])
```

That code is *correct*. It is also useless in production, because in
production you have four problems the notebook does not have:

```
THE FOUR PROBLEMS
──────────────────────────────────────────────────────────────────────
1. LATENCY      The answer takes 40 seconds. The user is watching a
                spinner. Do they see progress? Can they cancel?

2. INTERRUPTION The user's browser closed. The network dropped. The
                pod was evicted. Now what?

3. REGRESSION   You changed one word in a prompt. Did the agent still
                work? How would you even know?

4. OPERATIONS   It is 3am. The agent is stuck. What is it doing? Can
                you stop it? Can you resume it after the fix?
```

M62 solves (1). M63 solves (2). M64 solves (3). M65 deals with (4) and with
the question of whether you should be running this yourself at all.

---

## 2. The single most important architectural idea

Here is the mental model that organises the whole phase:

```
┌─────────────────────────────────────────────────────────────────┐
│  YOUR LAYER (the part you own)                                  │
│                                                                  │
│   HTTP API  ──▶  runs table  ──▶  worker  ──▶  compiled graph   │
│      │                │              │                │          │
│      │                │              │                │          │
│      ▼                ▼              ▼                ▼          │
│   SSE events      durable log    cancellation      checkpoints    │
│   (contract)      (replayable)   (drain/abort)    (resumable)   │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│  LANGGRAPH (the part you do not own)                             │
│                                                                  │
│   Pregel engine · nodes · edges · state · reducers · checkpointer │
└─────────────────────────────────────────────────────────────────┘
```

**The rule:** LangGraph owns the *execution*. You own everything around it —
the admission record, the event contract, the worker, the cancellation, the
database schema, the tests, and the deployment.

The moment you let a LangGraph detail leak into your frontend contract, you
have coupled your UI to a library's internal release cadence. That is the
mistake M62 is designed to prevent.

---

## 3. Three time horizons

Production agent systems are usually three systems wearing a trench coat.

| Horizon | What lives here | Typical lifetime | Store |
|---|---|---|---|
| **Request** | One HTTP request, one SSE connection | seconds | memory |
| **Run** | One graph execution, possibly paused for a human | minutes → hours | Postgres (checkpointer + runs table) |
| **Business** | Users, preferences, knowledge, audit | forever | Postgres + object storage + vector store |

Phase 8 gave you the *Run* horizon (checkpoints, threads). Phase 9 makes the
Run horizon **operational**: it has a status, it can be cancelled, it survives
a restart, and it can be replayed.

Most production incidents in agent systems are Run-horizon incidents:
a run stuck in `running` forever, a resume that never arrived, a cancel that
was ignored. M63 is entirely about that horizon.

---

## 4. What "durable" means, precisely

The word gets used loosely. Let's be exact, because the difference decides
whether you can page yourself at 3am.

A run is **durable** if, after the process dies, you can still:

1. **tell** what it was doing — → the `runs` table
2. **read** the state it had reached — → the checkpointer
3. **continue** it from where it stopped — → `Command(resume=...)` /
   `invoke(None, config)`
4. **show the user** what they already received — → the durable event log

Note (1) is *not* provided by the checkpointer. The LangGraph docs say this
outright:

> If you need to distinguish "never accepted" from "accepted but lost", record
> admission outside the checkpointer, for example by committing an outbox row
> to your own store before you call `invoke`.

That sentence is the entire justification for M63's `runs` table. Before the
first checkpoint becomes durable, a thread that was accepted and a thread that
was never invoked are *indistinguishable*. Only your own table can tell them
apart.

---

## 5. The two axes of the deployment decision (M65 preview)

Every production LangGraph deployment sits somewhere on two axes:

**Axis 1 — Who owns the HTTP surface?**

| | You own it | Platform owns it |
|---|---|---|
| Your event contract | ✅ free | ❌ you get theirs |
| Your auth, your routes | ✅ free | ⚠️ custom auth is Enterprise |
| Your API shape | ✅ free | ⚠️ assistants/threads/runs model |
| Cost | infra only | infra + (maybe) licence |

**Axis 2 — Who owns the run lifecycle?**

| | You own it | Platform owns it |
|---|---|---|
| Durable queue | you build it | ✅ built in |
| Worker autoscaling | you build it | ✅ built in |
| Cancel/resume semantics | you define them | ✅ defined for you |
| Observability | you wire it | ✅ built in |

The honest summary, which M65 unpacks in detail:

> **The Agent Server is genuinely good infrastructure — the durable task
> queue and the queue-worker architecture are the hardest parts of building a
> long-running agent service, and they are solved there.** The question is
> whether the licence and the API constraints fit *your* product, not
> whether the platform is good.

---

## 6. A quick inventory of what you already know

| You know | Used in |
|---|---|
| `StateGraph`, nodes, edges, conditional edges | everywhere |
| `add_messages` and custom reducers | M64 (reducer tests) |
| Checkpointers, `thread_id`, `get_state`, `get_state_history` | M63, M64 |
| `interrupt()` / `Command(resume=...)` | M63 (resume), M64 (tests) |
| `create_agent`, tools, middleware | M62 (tool events), Deep Agents |
| FastAPI, async Python | M62 (SSE), M63 (worker + API) |
| Pydantic v2 | the request/response models in `api.py` |
| `uv` | the whole toolchain |

**Nothing in Phase 9 requires a new framework.** It requires the same tools,
used at a different altitude.

---

## 7. How to use this course

Each module is written in four layers, so you can read at whatever depth you
need:

1. **The mental model** — *why* this exists. Read this.
2. **The mechanics** — the exact API, with verified code.
3. **The traps** — the bugs I hit, or that are waiting for you.
4. **The exercise** — change something and predict the result.

There are runnable labs for each module:

```bash
python scripts/demo_m62.py
python scripts/demo_m63.py
python scripts/demo_deep_agents.py
python -m pytest tests/ -v
```

The labs need **no API key**. They use a deterministic fake model from
`src/p9/models.py`. That is not a shortcut for the course — it is the same
technique M64 teaches for your own test suite.

---

## 8. A last framing thought

An agent is a **long-running, resumable, stateful function that talks to a
non-deterministic third party.**

Every hard part of production agent engineering follows from that sentence:

* *long-running* → you need streaming, cancellation, and a queue (M62, M63)
* *resumable* → you need checkpoints and a checkpointer (M63)
* *stateful* → you need a state model and reducers (M64)
* *non-deterministic* → you need fakes, assertions, and evaluation (M64)

Keep that sentence in mind. It explains every design decision in the next
four modules.

---

**Next: [M62 — Streaming deep dive](62-streaming.md) →**
