# PHASE 9 — Production LangGraph

> **You are here:** you have finished Phase 8 (Persistence, Memory & Human-in-the-Loop).
> Phase 9 turns "it works on my laptop" into "it works in production".

---

## Why this phase exists

Phases 0–8 taught you the *primitives*: models, prompts, retrieval, tools, agents,
graphs, checkpoints, interrupts. Every one of them works beautifully in a notebook.

What none of them taught you is the set of questions that only appear when a real
user is waiting:

| Question | Where it is answered |
|---|---|
| How do I stream tokens to a browser without inventing a protocol? | **M62** |
| My agent takes 4 minutes. The browser closed. Now what? | **M63** |
| How do I know my agent still works after I changed a prompt? | **M64** |
| Do I build my own server, or use the platform? What does it cost? | **M65** |

---

## The module order (and why)

I have reordered the modules slightly from how they were originally listed, and
the reasoning matters:

```
M62  Streaming deep dive          (2.5h)  ── define the CONTRACT first
  │
  ▼
M63  Long-running graphs           (3.0h)  ── the contract must survive minutes
  │
  ▼
M64  Testing graphs                (3.0h)  ── now you have something worth testing
  │
  ▼
M65  The deployment decision       (1.5h)  ── now you know what you actually need
```

**M62 before M63** because a long-running run is useless if the client cannot
tell "still working" from "finished" from "waiting for you". The event contract
is the vocabulary that M63 reuses for `pending`/`running`/`paused`/`done`.

**M64 after M63** because interrupt/resume testing only makes sense once you
have a durable runs table and a checkpointer. Testing a graph against an
in-memory saver is like testing a database against a dictionary.

**M65 last** because the deployment decision is *informed* by everything above.
Once you have written the SSE contract and the runs table, you know exactly how
much of the platform you actually need — and the licensing question becomes a
concrete number instead of a vague worry.

---

## What you will build

A complete, production-shaped reference implementation in `src/p9/`:

```
src/p9/
├── config.py           Settings (env-driven, frozen dataclass)
├── models.py           Model factory: Gemini via init_chat_model + a fake model
├── sse.py              ★ M62: the SSE event contract + translator
├── observability.py    Langfuse wiring (tracing, spans, scores)
├── runs_store.py       ★ M63: the `runs` table (SQLAlchemy 2.0) + async facade
├── worker.py           ★ M63: the background worker (drain, resume, events)
├── api.py              ★ M63/M65: the custom FastAPI runtime
├── deploy.py           The ASGI entry point (uvicorn p9.deploy:app)
├── deploy_graphs.py    Graphs exported for the Agent Server (no checkpointer!)
└── graphs/
    ├── support.py      Demo graph: reducer + subgraph + tool + interrupt
    └── deep_agent_demo.py   Deep Agents: main agent + researcher subagent
```

Every claim in these lessons is backed by code that actually runs, and by
output captured from a real run.

---

## Running it

```bash
cd course/phase9-production-langgraph

# 1. environment
uv venv --python 3.11 .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
uv pip install --python .venv/bin/python -e ".[dev]"

# 2. run the labs (no API key needed - they use a deterministic fake model)
python scripts/demo_m62.py          # streaming
python scripts/demo_m63.py          # long-running graphs
python scripts/demo_deep_agents.py  # Deep Agents

# 3. run the tests
python -m pytest tests/ -v

# 4. re-verify that every API claim in docs/ still holds
#    (run this after upgrading any dependency)
python scripts/verify_claims.py

# 5. optional: real Postgres for the persistence tests
docker compose up -d
python -m pytest tests/ -m docker -v
```

**No API key is required for any lab.** Every lesson runs offline against a
deterministic fake model. Set `GOOGLE_API_KEY` to switch to real Gemini — the
code path is identical.

---

## The lessons

| File | Module | Time | What you learn |
|---|---|---|---|
| [`docs/00-orientation.md`](docs/00-orientation.md) | Orientation | 30m | The production mental model; what "production" actually means for an agent |
| [`docs/62-streaming.md`](docs/62-streaming.md) | **M62** | 2.5h | Every stream mode, the v2 `StreamPart` format, the new v3 event protocol, custom events, subgraphs, and **designing your own SSE contract** |
| [`docs/63-long-running.md`](docs/63-long-running.md) | **M63** | 3.0h | The `runs` table, durability modes, background workers, webhook resume, idempotency, and **cancellation** (cooperative drain vs hard abort) |
| [`docs/64-testing.md`](docs/64-testing.md) | **M64** | 3.0h | Step assertions, state snapshots, reducer tests, interrupt/resume tests, fake models, and **testcontainers** for real Postgres in CI |
| [`docs/65-deployment.md`](docs/65-deployment.md) | **M65** | 1.5h | Custom FastAPI runtime vs the Agent Server; what the platform really adds; the **licensing reality** |
| [`docs/90-versions-and-deprecations.md`](docs/90-versions-and-deprecations.md) | Reference | — | Every version used, verified on 2026-11-04, and the full old-vs-modern table |

---

## The five things to remember

1. **Your frontend contract is yours, not LangGraph's.** LangGraph's stream
   formats change between versions; your event schema should not. Translate
   at the boundary (`src/p9/sse.py`).

2. **The checkpointer answers "what is the state?" — not "what is happening?"**
   A `runs` table answers the second question, and the LangGraph docs
   explicitly tell you to keep it *outside* the checkpointer.

3. **Checkpoint = durability = resumability.** One mechanism gives you all
   three, but only if you also record *admission* yourself.

4. **Never call a synchronous database API from inside `async def`.** It
   blocks the event loop, and the symptom is bizarre: cancellation silently
   stops working. This actually bit us while building M63 — the fix and the
   reasoning are in the lesson.

5. **Test the graph, not the model.** Inject a deterministic fake. A test that
   depends on model output is not testing your code.

---

## Tooling choices (and why)

| Choice | Why not the alternative |
|---|---|
| **Gemini via `init_chat_model("google_genai:...")`** | Not a vendor SDK import: switching providers is a config change, and we never take a dependency on a vendor SDK. Gemini's free tier is generous. |
| **Langfuse for tracing** | MIT-licensed core, self-hostable with Docker Compose, no per-seat pricing. LangSmith is a commercial platform (self-hosting is an Enterprise add-on). Both speak the same LangChain callback protocol, so switching is two lines. |
| **SQLAlchemy 2.0 + Postgres** | The checkpointer needs Postgres anyway; one database for checkpoints + runs + events keeps transactions possible. |
| **testcontainers-python** | Real Postgres in CI, not a mock. (Note: `testcontainers.postgres` is deprecated → `testcontainers.community.postgres`.) |
| **A custom FastAPI runtime** | You own the API, the event contract, and the bill. See M65 for when the platform is worth it. |
| **Deep Agents** | Built on LangGraph, so everything in M62/M63 applies unchanged. |

---

## One warning about versions

This course was written against **LangGraph 1.2.19** (2026-11-04). LangGraph
moves fast. Two things in particular are new and worth knowing about:

* **`version="v2"` on `stream()`** gives a unified `StreamPart` format across
  all stream modes (LangGraph ≥ 1.1). The old shape — where a single mode
  returned raw data and multiple modes returned `(mode, data)` tuples — is
  still the default and is now the *legacy* format.
* **`stream_events(version="v3")`** is a brand-new typed-projection API
  (LangGraph 1.2) that is **still marked experimental** — it emits a
  `LangChainBetaWarning`. The docs recommend it for new applications, but it
  is beta, so M62 teaches the v2 format as the stable path and v3 as the
  path to watch.

[`docs/90-versions-and-deprecations.md`](docs/90-versions-and-deprecations.md)
has the complete table of what is current, what is deprecated, and what
replaces it.
