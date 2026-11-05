# M65 — The deployment decision

**Time: 1.5 hours.** This module answers one question honestly:

> **Do I run the agent server myself, or do I use LangGraph's Agent Server?**

And, crucially: **what does the platform actually give me, and what does it
cost?**

---

## 1. The two options

### Option A — Your own runtime (the FOSS route)

You write the HTTP layer, the queue, the worker, and the tables. You already
built most of it in M63:

```
Browser ──▶ FastAPI (your code) ──▶ runs table (Postgres)
                                          │
                                          ▼
                                     worker (your code) ──▶ compiled graph
                                          │                          │
                                          │                          ▼
                                          └──▶ event log      checkpointer
                                              (Postgres)          (Postgres)
```

**You own:** the API shape, the event contract, the authentication, the
database schema, the queue, the scaling model, the bill.

**You do not own:** the platform's run management, double-texting protection,
Studio UI, cron scheduler, and the battle-tested task queue.

### Option B — LangGraph Agent Server (formerly "LangGraph Platform")

You write the **graph** and nothing else. The platform gives you an HTTP API
with a fixed shape (`assistants`, `threads`, `runs`, `crons`), a durable task
queue, a Studio UI, and (optionally) LangSmith tracing.

---

## 2. What the Agent Server actually is

From the official docs (verified 2026-11-04):

> LangSmith Deployment's **Agent Server** offers an API for creating and
> managing agent-based applications. It is built on the concept of
> **assistants**, which are agents configured for specific tasks, and includes
> built-in persistence and a **task queue**.

### 2.1 The architecture (this is the good part)

```
┌──────────────┐   create run    ┌────────────┐
│ API servers  │─────────────────▶│  Postgres  │
│ (stateless)  │                  │ (runs,     │
└──────┬───────┘                  │  threads,  │
       │  notify (Redis pub/sub)  │  ckpts)    │
       ▼                          └────────────┘
┌──────────────┐   claim run
│ Queue worker │─────────────────▶│  Postgres
│ (executes    │◀─ publish events │
│  your graph) │                  └────────────┘
└──────┬───────┘
       │ publish events
       ▼
    Redis ──▶ API server ──▶ SSE ──▶ client
```

The parts that are genuinely hard, and that the platform gives you:

1. **A durable task queue.** Runs survive an API restart; a worker picks them
   up. Exactly what M63 taught you to build.
2. **Exactly-once execution per thread.** "The queue enforces that at most 1
   run can be executed for a given thread at one time." You get this for free
   — and it is *hard* to get right.
3. **Split API / worker tiers.** API servers scale on request volume, queue
   workers scale on pending-run count. `N_JOBS_PER_WORKER` (default 10)
   bounds concurrency per worker.
4. **Event fan-out over Redis pub/sub**, with the events persisted in
   Postgres so a reconnecting client can replay.
5. **A run lifecycle**: `pending`, `running`, `interrupted`, `success`,
   `error`, `timeout`, `cancelled`.
6. **Cron jobs** for scheduled runs.
7. **Studio** — a visual debugger for graphs.

### 2.2 The API model you inherit

```
POST   /threads                        create a thread
POST   /threads/{tid}/runs             create a run
POST   /threads/{tid}/runs/stream      create + stream (SSE)
POST   /threads/{tid}/runs/{rid}/join  attach to a running run
GET    /threads/{tid}/state            current state
GET    /threads/{tid}/history          state history
POST   /threads/{tid}/runs/{rid}/cancel
POST   /assistants                    create an assistant
POST   /cron                          schedule runs
```

This is a **good** API — it is a superset of what most people need. But it is
*not your API*. Your frontend must speak it.

---

## 3. The licensing reality (verified, 2026-11-04)

This is the part most tutorials get wrong, so here is the primary-source
evidence.

### 3.1 The environment variables

From the standalone-server guide:

| Variable | Required? | Meaning |
|---|---|---|
| `REDIS_URI` | **yes** | Redis for pub/sub |
| `DATABASE_URI` | **yes** | Postgres for everything else |
| `LANGSMITH_API_KEY` | yes (for tracing) | LangSmith API key |
| `LANGGRAPH_CLOUD_LICENSE_KEY` | for production | LangSmith **licence key** |
| `LANGSMITH_ENDPOINT` | optional | Self-hosted LangSmith endpoint |

Plus egress to `https://beacon.langchain.com` for licence verification.

### 3.2 The matrix (from the data-plane docs)

| | Cloud | Hybrid | Self-Hosted |
|---|---|---|---|
| **Licensing** | LangSmith API Key validated against LangSmith SaaS | LangSmith API Key validated against LangSmith SaaS | Air-gapped licence key **or** Platform Licence Key validated against LangSmith SaaS |
| **Telemetry** | → LangSmith SaaS | → LangSmith SaaS | Self-reported usage (audit) for air-gapped licence key; → LangSmith SaaS for a LangSmith Licence Key |
| **Tracing** | Required | Optional | Optional (SaaS or self-hosted LangSmith) |

### 3.3 The important nuance: "lite mode" is gone

Older articles (and still-circulating forum posts) say the standalone server
runs in a restricted "lite mode" unless you have a licence key. **That is
outdated.** From the Agent Server changelog:

> Removes the outdated "running in lite mode" warning that Agent Servers
> logged when validating with a LangSmith API key instead of a license key.
> **These servers already have every feature.**

So the accurate picture is:

* **A LangSmith API key gives you the full feature set** of the standalone
  server (Cloud and Hybrid both validate with an API key).
* **A licence key** is what you need for: self-hosted LangSmith, air-gapped
  operation, custom authentication on self-hosted, and the control-plane
  features of LangSmith Deployment.
* **Self-hosted LangSmith itself is an Enterprise-plan add-on**, and the
  LangSmith licence key is what the server authenticates against at startup.

### 3.4 The honest summary

> **The platform is not "free" and not "locked" either — it is
> *LangSmith-flavoured*.** The standalone server needs a LangSmith account
> (a free-tier API key works for the core), and the things that cost real
> money are the Enterprise-plan features: self-hosted LangSmith, custom auth
> on self-hosted, air-gapped operation, and the control plane.

And the practical numbers:

| Deployment | Cost shape |
|---|---|
| Custom FastAPI runtime | **Your infra only** (Postgres + Redis + compute). Langfuse is MIT-core and self-hostable. Zero licence cost. |
| Standalone Agent Server | Infra + a LangSmith account (free tier works for the core). Licence key needed for enterprise features. |
| LangSmith Deployment (Cloud) | Infra is managed; you pay LangSmith per seat/usage. |
| Self-hosted LangSmith | Enterprise plan. |

For a learner, a solo developer, or a small team, **the custom runtime is
strictly cheaper and strictly more flexible.** For an enterprise that already
pays for LangSmith, the platform is often cheaper than building the queue
themselves.

---

## 4. What the platform adds that you would otherwise build

| Capability | Cost to build yourself | Platform |
|---|---|---|
| Durable task queue | **High** — this is the hard part | ✅ |
| Exactly-once per thread | High | ✅ |
| Run lifecycle + statuses | Medium | ✅ |
| Resume after interrupt | Medium (M63) | ✅ |
| Cancellation | Medium (M63) | ✅ |
| Cron / scheduled runs | Low–medium | ✅ |
| Studio (visual debugger) | High | ✅ |
| Scaling API and workers separately | Medium | ✅ |
| Stream fan-out to many clients | Medium (Redis pub/sub) | ✅ |
| **Your own event contract** | — | ❌ |
| **Your own auth + routes** | — | ⚠️ custom auth = Enterprise on self-hosted |
| **Your own data model** | — | ⚠️ you must fit assistants/threads/runs |
| **Zero licence cost** | — | ❌ |

The row that decides most cases: **the platform owns the HTTP surface.** If
your product needs an API shape that is not "assistants/threads/runs", or if
your frontend's event contract is anything other than the platform's, you
are fighting the platform.

---

## 5. The "double-texting" problem

Worth understanding, because it is the platform's most valuable feature and
the hardest thing to get right yourself.

*Double-texting* = the same thread receiving two overlapping runs, producing
interleaved, duplicated output.

The platform prevents it by enforcing **at most one active run per thread**
and queueing the rest. If you build your own runtime, you must implement
this yourself:

```python
# Postgres: claim a run only if no other run for the same thread is active.
UPDATE runs
SET status = 'running', ...
WHERE id = (
    SELECT id FROM runs
    WHERE status = 'pending'
      AND thread_id NOT IN (
          SELECT thread_id FROM runs WHERE status = 'running'
      )
    ORDER BY created_at
    LIMIT 1
)
RETURNING *;
```

That is one query — but it is one query plus all the edge cases (crashed
workers holding a lock, races between workers, the ordering guarantee).

The `langgraph-sdk` client exposes the platform's own solution:

```python
runs.create(..., multitask_strategy="reject" | "interrupt" | "enqueue" | "rollback")
```

---

## 6. Decision framework

Ask these four questions in order.

### Q1 — Do I need the platform's API to be *my* API?

If your frontend's event contract, routes, or auth are non-negotiable → **build
your own.** You will spend more time fighting the platform than writing the
120 lines of FastAPI that M63 already gave you.

### Q2 — Do I have (or want) a LangSmith relationship?

- Already paying for LangSmith Enterprise → the platform is probably cheaper.
- Free tier only → the custom runtime is free and the platform is free-tier
  limited.
- Want zero vendor dependency → the custom runtime, plus **Langfuse** for
  observability (MIT core, self-hostable, same callback protocol).

### Q3 — Do I need the durable queue, cron, and Studio?

If yes and you have the team → the platform saves weeks.
If you are one person learning → build it; you will understand your system
far better.

### Q4 — What is my concurrency?

- Dozens of runs/minute, short → either works.
- Hundreds of runs/minute, long, bursty → the platform's queue + autoscaling
  is worth real money. Rolling your own is a project.

### 5.1 The summary table

| | Custom runtime (M63) | Agent Server |
|---|---|---|
| Time to first working system | **You already have it** | 1–3 days (licence, Helm, auth) |
| Licence cost | **Zero** | Free tier OK; Enterprise for self-hosted/custom auth |
| Event contract | **Yours** | The platform's |
| Durable queue | You build it | ✅ |
| Cron | You build it (or APScheduler) | ✅ |
| Studio | ❌ | ✅ |
| Scaling | You design it | ✅ Split tiers + autoscaling |
| Observability | Langfuse (FOSS) | LangSmith (or Langfuse alongside) |
| Best for | learning, small teams, bespoke APIs | enterprises already on LangSmith |

---

## 7. Building both

The course's repo contains both, and they are worth comparing.

### 7.1 The custom runtime

```bash
docker compose up -d                     # postgres + redis
uvicorn p9.deploy:app --port 8000
```

```python
# src/p9/deploy.py
app = create_app(
    store=AsyncRunStore(RunStore.from_url(_database_url())),
    graphs={
        "support": lambda saver: build_support_graph(model=default_model(), checkpointer=saver)
    },
    checkpointer_factory=_make_checkpointer,   # created inside the event loop
)
```

Note the **factory** pattern: `AsyncPostgresSaver.from_conn_string` is an
async context manager, so the checkpointer must be created inside the running
loop, not at import time.

### 7.2 The Agent Server

```bash
cd deploy/agent-server
cp ../../.env.example .env
docker compose up --build                 # API server on :8123
```

The application structure:

```
langgraph.json
{
  "dependencies": ["."],
  "graphs": {
    "support": "./src/p9/deploy_graphs.py:support",
    "deep_agent": "./src/p9/deploy_graphs.py:deep_agent"
  },
  "env": ".env",
  "python_version": "3.11"
}
```

And **two rules** the server imposes:

**Rule 1: do not configure a checkpointer or a store in the graph code.**

> In both cases, the server automatically injects the checkpointer and memory
> store configured for that deployment at runtime. **Do not configure these in
> your graph code** because the server needs to manage them for other
> operations.

So `src/p9/deploy_graphs.py` compiles the graphs **without** a checkpointer:

```python
support: Any = build_support_graph(model=default_model())   # no checkpointer!
deep_agent: Any = build_deep_agent(model=default_model())
```

**Rule 2: export a compiled graph, not a builder.**

> **Compiled graph** (recommended): Export an already-compiled `CompiledGraph`
> instance. The server loads it once at container startup and reuses it for
> every run — no compilation overhead per request.
> **Factory function**: … Use this only when you need per-run graph
> customization … Keep factory functions lightweight, since they run on every
> invocation.

### 7.3 The production deployment path

> ⚠️ For production deployments, use Kubernetes with the maintained LangSmith
> Helm chart. This is the production path that LangChain regularly tests.
> LangChain does not regularly test other orchestrators.

The Helm chart: `https://github.com/langchain-ai/helm/tree/main/charts/langgraph-cloud`

And a hard warning from the docs:

> Do not run standalone servers in serverless environments. Scale-to-zero may
> cause task loss and scaling up will not work reliably.

That makes sense: a durable queue needs a warm worker.

### 7.4 Talking to the platform with the SDK

```python
from langgraph_sdk import get_client

client = get_client(url="http://localhost:8123")

# Create a run in the background
run = await client.runs.create(
    thread_id=None,
    assistant_id="support",
    input={"topic": "ingest backlog"},
    stream_mode=["messages", "updates", "custom"],
    after_seconds=0,          # background run
    if_not_exists="create",   # idempotency!
    durability="async",
    multitask_strategy="enqueue",
)

# Stream it
async for chunk in client.runs.stream(
    thread_id=run["thread_id"],
    assistant_id="support",
    input={"topic": "ingest backlog"},
    stream_mode="messages",
    stream_subgraphs=True,
):
    print(chunk)
```

`if_not_exists` is the platform's idempotency primitive, and
`after_seconds` schedules a background run. `client.runs.cancel(...)` and
`client.runs.join(...)` complete the lifecycle.

---

## 8. A hybrid that often wins

You do not have to pick one thing:

```
┌───────────────────────────────────────────────────────────┐
│  YOUR FastAPI (auth, your routes, your event contract)   │
│      │                                                    │
│      ├──▶ LangGraph SDK ──▶ Agent Server (durable queue) │
│      │                                                    │
│      └──▶ your own worker ──▶ your own graphs             │
└───────────────────────────────────────────────────────────┘
```

Or, more commonly:

* **Agent Server** for the run lifecycle, queue, and cron.
* **Your own API** in front of it, translating the platform's stream into
  *your* event contract.
* **Langfuse** for observability, alongside the platform's own tracing.

This gives you the queue and cron without giving up your contract. The cost
is one translation layer — which you already wrote in M62.

---

## 9. Observability: the FOSS choice

Wherever you deploy, you need traces. The two options that matter for this
course:

| | Langfuse | LangSmith |
|---|---|---|
| Licence | **MIT core**, self-hostable | Commercial (free tier; Enterprise for self-host) |
| Self-host | ✅ Docker Compose, Helm | Enterprise add-on |
| LangChain/LangGraph integration | `langfuse.langchain.CallbackHandler` | built in |
| Deep Agents integration | ✅ documented | ✅ |
| Cost at your scale | **Zero** | per seat / usage |

The integration is three lines:

```python
from langfuse import get_client
from langfuse.langchain import CallbackHandler

langfuse = get_client()                  # reads LANGFUSE_PUBLIC_KEY / SECRET_KEY
handler = CallbackHandler()

graph.invoke(payload, config={"callbacks": [handler]})
```

**Always merge the config**, never replace it — replacing it would drop the
`thread_id` and break persistence. That is why `src/p9/observability.py`
exists:

```python
def tracing_config(settings=None) -> dict[str, Any]:
    handler = get_callback_handler(settings)
    if handler is None:
        return {}
    return {"callbacks": [handler]}
```

For a **background worker** the callback handler is not enough — there is no
ambient request context. Wrap the worker body in a manual span:

```python
with trace_run("support-run", run_id=run.id, input=payload) as observation:
    ...execute the graph...
```

And attach user feedback:

```python
score_trace(trace_id, "user_rating", 1.0, comment="helpful")
```

> Langfuse also ships an **OpenTelemetry** ingestion path
> (`POST /api/public/otel/v1/traces`), which is the vendor-neutral option if
> you ever run several observability backends.

---

## 10. The checklist before you deploy either way

### Application

- [ ] The graph is compiled with a **real** checkpointer (Postgres) in production
- [ ] `durability` chosen deliberately per workflow
- [ ] Every node is either sync or async — and the API matches
- [ ] No model client, connection, or file handle is stored in **state**
- [ ] The event contract is versioned and published to the frontend

### Operations

- [ ] A `runs` table (or the platform's equivalent) with an idempotency key
- [ ] Status transitions enforced
- [ ] Cancellation works and is tested
- [ ] Graceful shutdown: in-flight runs drain on SIGTERM (`RunControl`)
- [ ] A heartbeat and a reaper for orphaned runs
- [ ] Structured logs with the `run_id` on every line
- [ ] Traces enabled (Langfuse or LangSmith)
- [ ] Alerts on: runs stuck in `running`, error rate, p95 duration

### Security

- [ ] Authentication and authorisation on every endpoint
- [ ] The SSE endpoint authorises the run's owner
- [ ] No secrets in the repo; `.env` is gitignored
- [ ] Webhook endpoints verify a signature
- [ ] The Langfuse/LangSmith keys are rotated and scoped

---

## 11. Traps

| Trap | Consequence |
|---|---|
| Hard-wiring a checkpointer in graph code | The Agent Server cannot manage persistence |
| Exporting a factory instead of a compiled graph | Compilation overhead per run |
| Deploying the Agent Server on serverless | Task loss on scale-to-zero |
| Assuming "lite mode" still exists | You over-buy a licence (or under-configure auth) |
| Ignoring the licence/validation egress requirement | The server fails to start in a locked-down network |
| Forgetting to merge the tracing config | You lose `thread_id` → persistence breaks |
| One thread, many concurrent runs | Double-texting → duplicated, interleaved output |
| No graceful shutdown | In-flight runs die on deploy |

---

## 12. Exercise

1. **Measure your build.** Count the lines in `src/p9/worker.py` +
   `runs_store.py` + `api.py`. That is the *entire* cost of owning the queue.
   Compare with the days it would take to configure the platform properly.

2. **Deploy both.** Run the custom runtime on `:8000` and the Agent Server on
   `:8123`. Write the *same* frontend against both — with a thin adapter for
   the platform's stream. This will make the "your contract vs their contract"
   trade-off concrete.

3. **Decide.** Write down: (a) your event contract, (b) your concurrency, (c)
   your budget, (d) whether your API is "assistants/threads/runs"-shaped. Then
   answer Q1–Q4 from §6 in writing. You will have to defend it to a colleague
   — that is the point.

4. **Try the licence path.** Run the standalone Agent Server *without* a
   licence key and with one. Note what changes. Read the "lite mode"
   changelog entry and see how much older advice is now wrong.

---

**Next: [90 — Versions and deprecations reference](90-versions-and-deprecations.md) →**
