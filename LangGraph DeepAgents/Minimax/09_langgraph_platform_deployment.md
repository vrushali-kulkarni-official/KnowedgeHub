# Module 09 — LangGraph Platform & Deployment

## Prerequisites

- Modules 05–08 (you have a real agent system to deploy)
- Docker / Docker Compose fluency (you have it)

## Why this module matters

You have an agent. Now you need to run it as a service. The **LangGraph Platform** gives you a managed runtime: API server, Studio UI, persistence, scaling. But you can also self-host the API server on your own infra (which fits your stack: Docker on Ubuntu + Cloudflare Tunnel).

This module is about getting your agent into users' hands.

## Learning objectives

By the end of this module you can:

1. Use **LangGraph Studio** locally for visual debugging.
2. Use `langgraph-cli` to build a deployable graph.
3. Run a LangGraph API server locally.
4. Self-host the API server in Docker Compose.
5. Expose it via Cloudflare Tunnel.
6. Decide when to use the managed platform vs self-host vs raw FastAPI.
7. Add authentication and basic multi-tenancy.

---

## 9.1 The deployment options

| Option | You run | Pros | Cons |
|---|---|---|---|
| **Raw FastAPI + LangGraph** | Everything | Full control, no extra infra | You build: auth, threads API, resume, etc. |
| **LangGraph API server (self-hosted)** | Docker image + Postgres | Pre-built API: threads, runs, cron, Studio, etc. | A bit of opinion; need to learn the API |
| **LangGraph Platform (managed)** | Just your config | Hosted, scales, Studio | Vendor; some limits |

You said you prefer popular open-source infra you control. **Self-hosted LangGraph API server** is your best fit. It gives you the SDK + API + Studio without the managed service.

---

## 9.2 Project layout for the API server

`langgraph-cli` expects a specific structure:

```
ai-saas/
├── pyproject.toml
├── langgraph.json             # graph registry
├── app/
│   ├── graph.py               # defines `graph` (the compiled object)
│   └── ...
├── docker-compose.yml         # for local dev
└── Dockerfile                 # for the API server image
```

`langgraph.json` is the manifest:

```json
{
  "graphs": {
    "agent": "./app/graph.py:graph"
  },
  "env": "./.env",
  "python_version": "3.11",
  "dependencies": ["."]
}
```

`./app/graph.py:graph` means "import the symbol `graph` from `app/graph.py`." That symbol must be a compiled `StateGraph`.

---

## 9.3 Install `langgraph-cli` and run locally

```bash
uv add --dev "langgraph-cli[inmem]"
```

Then in dev:

```bash
langgraph dev
```

This starts:
- A local API server on `http://localhost:2024`.
- LangGraph Studio at the same URL.
- In-memory checkpointer (so state is lost on restart).

For a persistent local dev:

```bash
langgraph dev --config langgraph.json
```

(Behind the scenes, it spins up the API server with the configured graphs.)

---

## 9.4 The API surface

The API server exposes a REST + SDK API for your graphs:

```
POST   /threads                           # create a thread
GET    /threads                           # list threads
GET    /threads/{thread_id}               # get thread state
POST   /threads/{thread_id}/runs          # start a run (stream or wait)
POST   /threads/{thread_id}/runs/stream   # stream a run
POST   /threads/{thread_id}/runs/{run_id}/join   # wait for run
POST   /threads/{thread_id}/state         # update state (rewind/edit)
GET    /threads/{thread_id}/history       # state history (time travel)
```

You typically use the **Python SDK** (`from langgraph_sdk import get_client`) rather than raw HTTP.

```python
from langgraph_sdk import get_client

client = get_client(url="http://localhost:2024")

# Create a thread
thread = await client.threads.create()

# Run the graph
async for event in client.runs.stream(
    thread["thread_id"],
    "agent",                   # graph name from langgraph.json
    input={"messages": [...]},
    stream_mode="messages",
):
    print(event)
```

This is the same API the Studio UI uses. Your FastAPI service can call this SDK to drive the graph server.

---

## 9.5 Dockerizing the API server

`langgraph-cli` can build a Dockerfile for you:

```bash
langgraph build -t my-agent:latest
```

Or write your own (recommended for control). The base image is small:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev
COPY app ./app
COPY langgraph.json ./
EXPOSE 8000
CMD ["uv", "run", "langgraph", "up", "--host", "0.0.0.0", "--port", "8000"]
```

(Note: the exact command matches the CLI's "up" mode; verify against current docs when you deploy.)

---

## 9.6 Docker Compose for the full stack

```yaml
# docker-compose.yml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: langgraph
      POSTGRES_USER: lg
      POSTGRES_PASSWORD: lgpass
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U lg -d langgraph"]
      interval: 5s

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  langgraph:
    build: .
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql://lg:lgpass@postgres:5432/langgraph
      REDIS_URL: redis://redis:6379
    ports:
      - "2024:8000"

volumes:
  pgdata:
```

Run it:

```bash
docker compose up --build
```

The API server is at `localhost:2024`. Studio is at the same URL.

---

## 9.7 Exposing to the internet via Cloudflare Tunnel

You already use Cloudflare Tunnel. Add a new service for the LangGraph server:

```yaml
# docker-compose.cloudflared.yml
services:
  cloudflared:
    image: cloudflare/cloudflared:latest
    command: tunnel --no-autoupdate run
    environment:
      TUNNEL_TOKEN: ${CF_TUNNEL_TOKEN}
    depends_on:
      - langgraph
```

In your Cloudflare Zero Trust dashboard, add a public hostname that routes to `http://langgraph:8000`. Done. The API server is on the internet, behind Cloudflare, no public ports.

**Don't forget:**
- Add auth to the API server (next sub-module).
- Rate limit (Module 10).
- Set up CORS if a separate frontend hits it.

---

## 9.8 Authentication

The LangGraph API server has pluggable auth. The simplest way: a custom `auth.py`:

```python
# app/auth.py
from langgraph_sdk import Auth

auth = Auth()

@auth.authenticate
async def authenticate(authorization: str):
    # verify JWT, etc.
    ...

@auth.on
async def authorize(ctx, value):
    # check thread ownership, etc.
    ...
```

The `Auth` object lets you hook into the request lifecycle. For your SaaS, you'll likely:

- Authenticate via a JWT (issued by your main FastAPI service).
- Authorize per-thread: user can only see/modify their own threads.

### 9.8.1 Alternative: auth in your main FastAPI

If you have an existing FastAPI service, you can run the LangGraph server *behind* it as a private service and proxy through:

```python
@app.post("/chat/{thread_id}/run")
async def proxy(thread_id, user = Depends(current_user)):
    return await lg_client.runs.create(thread_id, "agent", input=...)
```

Your FastAPI does auth, then talks to LangGraph. This is often simpler for a small SaaS.

---

## 9.9 Cron jobs / scheduled tasks

The API server supports cron triggers (kicked off on a schedule). Useful for:

- Daily report agents.
- Cleanup of old threads.
- Periodic memory summarization.

Configured in `langgraph.json`:

```json
{
  "graphs": {...},
  "cron": [
    {
      "path": "./app/cron/cleanup.py:run",
      "schedule": "0 3 * * *"
    }
  ]
}
```

---

## 9.10 LangGraph Studio

When you run `langgraph dev`, Studio opens in your browser. You can:

- See the graph visually.
- Step through node-by-node execution.
- Inspect state at any step.
- Edit state and replay (time travel).
- Test HITL: click "Resume" on a paused graph.

Use it heavily during development. It's the fastest way to debug multi-agent flows.

---

## 9.11 The "raw FastAPI vs API server" decision

| If you have... | Use... |
|---|---|
| Single graph, simple SaaS, want control | Raw FastAPI + LangGraph (you've built this in Modules 05–08) |
| Multiple graphs, need Studio, want threads/runs/cron out of the box | Self-hosted LangGraph API server |
| Want zero infra and accept vendor lock-in | Managed LangGraph Platform |

For your AI SaaS, the most pragmatic path is:

- **Core product:** raw FastAPI service with the LangGraph graph embedded.
- **Internal/ops tools:** separate LangGraph API server for power users, Studio access for your team.

This separation is healthy: you keep the production critical path simple, and you get a powerful dev tool.

---

## 9.12 Deployment checklist

- [ ] `langgraph.json` defines all graphs.
- [ ] Dockerfile builds and runs.
- [ ] Docker Compose has Postgres, Redis, LangGraph, Cloudflared.
- [ ] Auth is enforced.
- [ ] Threads are tenant-isolated.
- [ ] Studio is NOT exposed to the internet (only internally).
- [ ] CORS configured for your frontend.
- [ ] Backups: Postgres volume backup strategy in place.
- [ ] Health checks defined.
- [ ] Logs aggregated (Module 10).

## Key takeaways

- `langgraph-cli` builds a deployable graph server. You can self-host.
- The API server exposes threads / runs / state — same model as raw LangGraph.
- Docker Compose + Cloudflare Tunnel is your deployment pattern.
- Decide between raw FastAPI vs API server based on your complexity.

## Resources

- `langgraph-cli`: https://langchain-ai.github.io/langgraph/concepts/langgraph_cli/
- LangGraph Platform docs: https://langchain-ai.github.io/langgraph/concepts/langgraph_platform/
- Studio: https://langchain-ai.github.io/langgraph/concepts/langgraph_studio/
- Self-hosted Docker setup: https://langchain-ai.github.io/langgraph/concepts/self_hosted/
