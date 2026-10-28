# Phase 8 — Persistence, Memory & Human-in-the-Loop

**LangChain · LangGraph · Langfuse · Deep Agents** — the complete Phase 8 course.

Every claim in every lesson was **executed** against the real packages and a
real PostgreSQL while this course was written. Where something surprised me
(the TTL unit, `copy_thread` raising `NotImplementedError`, the two
incompatible langmem value shapes), the lesson says so.

---

## What you already know

Phases 0–7: orientation → models & prompts → ingestion → embeddings & vector
stores → RAG → tools & MCP → `create_agent` → LangGraph Core.

**Phase 8** is where your agent stops being a function call and starts being
a **system**: it remembers, it survives crashes, it waits for humans, and it
can be deleted on request.

| Module | Topic | Lesson |
|---|---|---|
| M54 | Checkpointers & PostgresSaver | [L15](./lessons/L15-checkpoints-and-threads.md) |
| M55 | State inspection & time travel | [L16](./lessons/L16-state-inspection-and-time-travel.md) |
| M56 | Durability, retries & crash recovery | [L17](./lessons/L17-durability-retries-and-crash-recovery.md) |
| M57 | HITL part 1 — interrupts | [L18](./lessons/L18-hitl-interrupts.md) |
| M58 | HITL part 2 — production approval flows | [L19](./lessons/L19-hitl-production-approval-flows.md) |
| M59 | Short-term memory | [L20](./lessons/L20-short-term-memory.md) |
| M60 | Long-term memory — Store & langmem | [L21](./lessons/L21-long-term-memory-store-and-langmem.md) |
| M61 | Multi-tenant memory & data lifecycle | [L22](./lessons/L22-multi-tenant-and-data-lifecycle.md) |

### Why this order

The modules are taught as a **spine**, not as a reference manual:

```
L15  checkpoints & threads        ← the substrate (you cannot inspect what
                                    you cannot store)
L16  inspection & time travel     ← observability on top of the substrate
L17  durability & retries         ← reliability, once you trust the substrate
L18  interrupts                   ← HITL, using the substrate + reliability
L19  approval flows               ← HITL as a product (queues, auth, audit)
L20  short-term memory            ← the first application of persistence
L21  long-term memory (Store)     ← the second application, across threads
L22  multi-tenancy & lifecycle    ← both, at production scale
```

Each lesson only uses what the previous ones taught.

---

## Setup

```bash
# 1. a virtualenv with uv
uv venv --python 3.11 .venv
source .venv/bin/activate

# 2. the exact versions this course was verified against
uv pip install \
  "langgraph==1.2.18" \
  "langchain==1.4.7" \
  "langgraph-checkpoint-postgres==3.2.0" \
  "langchain-postgres==0.0.19" \
  "langmem==0.0.30" \
  "psycopg[binary,pool]==3.3.6" \
  "langfuse==5.0.4" \
  "langchain-google-genai" \
  "python-dotenv"

# optional, only for ex04 (Redis checkpointer)
uv pip install "langgraph-checkpoint-redis==0.5.2"
```

### PostgreSQL (needed by 10 of the 19 examples)

```bash
apt-get install -y postgresql-15 postgresql-15-pgvector
pg_ctlcluster 15 main start

su postgres -c "psql -c \"CREATE ROLE langgraph LOGIN PASSWORD 'langgraph' SUPERUSER;\""
su postgres -c "createdb -O langgraph langgraph"
su postgres -c "createdb -O langgraph langgraph_test"
su postgres -c "psql -d langgraph_test -c 'CREATE EXTENSION vector;'"
```

### Environment

```bash
cp .env.example .env      # then edit it
export LANGGRAPH_PG_URL="postgresql://langgraph:langgraph@127.0.0.1:5432/langgraph"
export LANGGRAPH_PG_URL_TEST="postgresql://langgraph:langgraph@127.0.0.1:5432/langgraph_test"
export GOOGLE_API_KEY="..."   # only if you use a real model
```

---

## Running the examples

Every example runs **offline** — no API key, no cost. They use a small
deterministic chat model (`examples/_common.py`) so you can see exactly what
the model was given.

```bash
cd examples
python ex01_checkpoint_anatomy.py        # what is inside a checkpoint
python ex02_postgres_saver.py            # PostgresSaver end to end
python ex03_agent_with_checkpointer.py   # memory in a real agent
python ex04_redis_checkpointer.py        # the community Redis backend
python ex05_state_inspection.py          # get_state / update_state / time travel
python ex06_replay_production_thread.py  # debugging a production thread
python ex07_durability_modes.py          # sync vs async vs exit, measured
python ex08_retry_idempotency.py         # retries, crash, exactly-once
python ex09_interrupt_basics.py          # interrupt() end to end
python ex10_functional_and_breakpoints.py# functional API + static breakpoints
python ex11_agent_hitl_middleware.py     # HumanInTheLoopMiddleware
python ex12_approval_flow.py             # approvals, sweeper, auth, audit
python ex13_short_term_memory.py         # trimming + context editing
python ex14_summarization_middleware.py  # summarization
python ex15_store_basics.py              # the Store API
python ex16_postgres_store.py            # pgvector semantic search
python ex17_langmem.py                   # langmem tools + manager
python ex18_tenant_isolation.py          # multi-tenant isolation
python ex19_data_lifecycle.py            # TTL + GDPR delete
```

Or run them all:

```bash
python tests/run_all.py
```

### Using a real Gemini model

The course uses a scripted model so it is deterministic and free. To switch:

```python
from langchain.chat_models import init_chat_model

model = init_chat_model("google_genai:gemini-3.8-flash")
```

Current Gemini models (verified Oct 2026):

| Model | Use it for |
|---|---|
| `gemini-3.8-flash` | the main agent — most intelligent Flash, GA, 1M context |
| `gemini-3.6-flash` | a cheaper general Flash |
| `gemini-3.5-flash-lite` | summarization, memory extraction, high-volume work |
| `gemini-3.1-flash-lite` | the cost-optimised workhorse |
| `gemini-3.1-pro-preview` | the hardest reasoning (preview) |
| `gemini-embedding-001` | embeddings for the Store's semantic search |

`gemini-2.5-flash` still works but Google now recommends `gemini-3.8-flash` or
`gemini-3.5-flash-lite` for new projects.

---

## The 60-second summary

```python
# ── persistence ────────────────────────────────────────────────────────────
from langgraph.checkpoint.postgres import PostgresSaver

with PostgresSaver.from_conn_string(DB_URL) as saver:
    saver.setup()
    graph = builder.compile(checkpointer=saver, store=store)

    cfg = {"configurable": {"thread_id": "acme:alice:conv-1"}}
    graph.invoke({"messages": [...]}, cfg)        # continues the thread

    graph.get_state(cfg)                         # current state
    graph.get_state_history(cfg)                 # the whole timeline
    graph.update_state(cfg, {"amount": 10})      # write a new checkpoint
    graph.invoke(None, old_cfg)                  # replay from the past

# ── human in the loop ──────────────────────────────────────────────────────
from langgraph.types import interrupt, Command

def approve(state):
    decision = interrupt({"question": "Approve?", "amount": state["amount"]})
    return {"decision": decision}

out = graph.invoke(state, cfg, version="v2")
out.interrupts                                     # what the human sees
graph.invoke(Command(resume="approve"), cfg, version="v2")

# ── reliability ────────────────────────────────────────────────────────────
from langgraph.types import RetryPolicy

builder.add_node("charge", charge_node,
                 retry_policy=RetryPolicy(max_attempts=5, jitter=True))
graph.invoke(inputs, cfg, durability="sync")       # safest persistence timing

# ── long-term memory ──────────────────────────────────────────────────────
store.put(("tenant", "acme", "users", "alice", "memories"), "pref-1",
          {"kind": "preference", "content": "prefers metric units"})
store.search(("tenant", "acme", "users", "alice"), query="units")
```

---

## Repository layout

```
langgraph-persistence-course/
├── README.md              ← you are here
├── ROADMAP.md             ← what you have learned / what comes next
├── CHEATSHEET.md          ← every API, and what is deprecated
├── pyproject.toml
├── .env.example
├── langgraph.json         ← for `langgraph dev`
├── lessons/
│   ├── L15-checkpoints-and-threads.md
│   ├── L16-state-inspection-and-time-travel.md
│   ├── L17-durability-retries-and-crash-recovery.md
│   ├── L18-hitl-interrupts.md
│   ├── L19-hitl-production-approval-flows.md
│   ├── L20-short-term-memory.md
│   ├── L21-long-term-memory-store-and-langmem.md
│   └── L22-multi-tenant-and-data-lifecycle.md
├── examples/              ← 19 runnable, verified examples
│   ├── _common.py
│   └── ex01..ex19
└── tests/
    └── run_all.py         ← runs every example, checks the output
```

---

## The eight things worth remembering

1. **A checkpoint is a versioned snapshot; a thread is its namespace.**
   Re-invoking a thread *continues* it.
2. **Durability controls *when state is written*, not whether your side
   effects happen once.** Use idempotency keys.
3. **A node restarts from the top when you resume an interrupt.** Keep the
   code above `interrupt()` idempotent.
4. **A thread has one head.** Forking moves it — clone to a scratch thread
   before experimenting.
5. **The Store is namespaced, and the namespace is your isolation boundary.**
   Tenant id first, always.
6. **`copy_thread()` exists but raises `NotImplementedError`** in every
   shipped saver. Copy the rows yourself.
7. **The store's TTL is in minutes, and it slides by default.** Use
   `refresh_on_read=False` for absolute expiry.
8. **Deleting a user is five operations**, not one: threads, memories,
   vectors, traces, app tables.

---

## Verified versions

| Package | Version | Why it matters |
|---|---|---|
| `langgraph` | **1.2.18** | `durability`, `RetryPolicy`, `Command` |
| `langchain` | **1.4.7** | `create_agent`, `langchain.agents.middleware` |
| `langgraph-checkpoint` | **4.3.1** | `BaseCheckpointSaver` |
| `langgraph-checkpoint-postgres` | **3.2.0** | `PostgresSaver` |
| `langgraph-checkpoint-redis` | **0.5.2** | community backend |
| `langmem` | **0.0.30** | still **pre-1.0** — pin it |
| `langfuse` | **5.0.4** | `api.trace.delete_multiple`, `api.observations.get_many` |
| `psycopg` | **3.3.6** | the driver under both Postgres backends |
| `langchain-google-genai` | **4.4.2** | Gemini + `gemini-embedding-001` |

PostgreSQL 15.19 with pgvector 0.8.7.

See **[CHEATSHEET.md](./CHEATSHEET.md)** for the full API surface and the
current-vs-deprecated table.
