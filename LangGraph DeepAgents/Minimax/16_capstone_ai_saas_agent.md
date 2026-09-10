# Module 16 — Capstone: Build Your AI SaaS Agent

## Prerequisites

- All previous modules. This is the integration.

## Why this module matters

Everything from Module 00 onward comes together here. You will build a real, deployable, multi-tenant AI SaaS that uses LangGraph, Deep Agents, FastAPI, Postgres, Redis, Docker, GHCR, and Cloudflare Tunnel — exactly the stack you said you wanted.

The product: a **multi-tenant AI research assistant** that:
- Accepts a research request from a logged-in user.
- Plans, delegates to subagents, writes a structured report.
- Streams progress (plan + tokens + file updates) to the user via SSE.
- Persists conversations per user.
- Stores artifacts in per-user file namespaces.
- Has a researcher, writer, and reviewer subagent.
- Has plan approval as HITL.
- Has rate limits, cost caps, and audit logs.
- Deploys via Docker + Cloudflare Tunnel.

By the end of this module you have an MVP you can charge money for.

## Learning objectives

By the end of this module you can:

1. Architect a full-stack AI SaaS on your preferred stack.
2. Implement multi-tenancy and auth.
3. Wire a Deep Agent into a FastAPI service with streaming, persistence, and HITL.
4. Build the file isolation, rate limit, and observability layers.
5. Dockerize and deploy to your Ubuntu server via Cloudflare Tunnel.
6. Set up CI for tests + evals.
7. Operate it: monitor, debug, iterate.

---

## 16.1 The architecture

```
                       ┌──────────────────────┐
                       │   Browser (SPA)      │
                       │  - plan checklist    │
                       │  - token stream      │
                       │  - file tree         │
                       │  - approval UI       │
                       └──────────┬───────────┘
                                  │ HTTPS (Cloudflare)
                                  ▼
                       ┌──────────────────────┐
                       │   Cloudflare Tunnel  │
                       └──────────┬───────────┘
                                  │
                                  ▼
   ┌────────────────────────────────────────────────────────┐
   │  FastAPI service (Docker container)                    │
   │  - auth (JWT)                                          │
   │  - rate limit (Redis)                                  │
   │  - chat routes (SSE)                                  │
   │  - approval routes                                     │
   │  - usage / billing routes                              │
   │  - drives LangGraph / Deep Agent                       │
   └────────┬──────────────────┬──────────────┬────────────┘
            │                  │              │
            ▼                  ▼              ▼
      ┌──────────┐       ┌──────────┐    ┌──────────┐
      │ Postgres │       │  Redis   │    │  MinIO   │
      │(checkpoints│      │ (rate,   │    │ (S3 for  │
      │ + app DB) │      │  cache)  │    │  uploads)│
      └──────────┘       └──────────┘    └──────────┘
```

---

## 16.2 Project layout (final)

```
ai-saas/
├── pyproject.toml
├── uv.lock
├── .env.example
├── .gitignore
├── README.md
├── langgraph.json
├── Dockerfile
├── docker-compose.yml
├── docker-compose.prod.yml
├── .github/workflows/
│   ├── ci.yml
│   └── nightly-evals.yml
├── migrations/
│   └── 001_init.sql
├── app/
│   ├── __init__.py
│   ├── main.py                # FastAPI app
│   ├── config.py              # Settings
│   ├── llm.py                 # Model factory
│   ├── deps.py                # FastAPI dependencies (auth, db)
│   ├── auth/
│   │   ├── jwt.py
│   │   └── routes.py
│   ├── chat/
│   │   ├── routes.py          # /chat endpoints
│   │   ├── streaming.py       # SSE generator
│   │   └── approval.py        # HITL resume
│   ├── usage/
│   │   ├── routes.py          # /usage endpoints
│   │   └── tracker.py
│   ├── rate_limit.py
│   ├── backends/
│   │   ├── s3.py              # MinIO backend
│   │   └── namespaced.py
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── main.py            # create_deep_agent
│   │   ├── subagents.py       # researcher, writer, reviewer
│   │   ├── prompts.py         # versioned instructions
│   │   └── tools/
│   │       ├── search_web.py
│   │       ├── search_docs.py
│   │       └── upload_file.py
│   └── evals/
│       ├── dataset.py         # golden dataset
│       ├── evaluators.py
│       └── run.py
└── tests/
    ├── unit/
    ├── integration/
    └── conftest.py
```

---

## 16.3 Step 1: Auth (JWT)

Use `pyjwt` (FOSS) to issue and verify tokens. Keep it simple — you can swap in Auth0/Clerk later.

```python
# app/auth/jwt.py
import jwt
from datetime import datetime, timedelta, timezone
from app.config import settings

def issue_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")

def verify_token(token: str) -> str:
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    return payload["sub"]
```

FastAPI dependency:

```python
# app/deps.py
from fastapi import Depends, HTTPException, Header
from app.auth.jwt import verify_token

async def current_user(authorization: str = Header(...)) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401)
    return verify_token(authorization[7:])
```

---

## 16.4 Step 2: Database schema

Postgres tables for app data (separate from LangGraph checkpoints, which are auto-created):

```sql
-- migrations/001_init.sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    plan TEXT NOT NULL DEFAULT 'free',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE usage (
    user_id UUID REFERENCES users(id),
    date DATE,
    input_tokens BIGINT DEFAULT 0,
    output_tokens BIGINT DEFAULT 0,
    cost_cents INT DEFAULT 0,
    PRIMARY KEY (user_id, date)
);

CREATE TABLE artifacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    thread_id TEXT,
    path TEXT,
    s3_key TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

Use SQLAlchemy 2.0 (you already do) for the ORM layer. Run migrations with Alembic.

---

## 16.5 Step 3: The agent

`app/agents/main.py`:

```python
from deepagents import create_deep_agent
from deepagents.sub_agent import SubAgent
from app.llm import get_llm
from app.agents.subagents import researcher, writer, reviewer
from app.agents.prompts import MAIN_AGENT_INSTRUCTIONS_V1
from app.agents.tools import search_web, search_docs, upload_file

agent = create_deep_agent(
    model=get_llm(),
    tools=[search_docs, upload_file],
    subagents=[researcher, writer, reviewer],
    instructions=MAIN_AGENT_INSTRUCTIONS_V1,
)
```

`app/agents/subagents.py`:

```python
from deepagents.sub_agent import SubAgent
from app.llm import get_llm
from app.agents.tools import search_web

researcher = SubAgent(
    name="researcher",
    description="Performs deep, citation-backed research on a topic and writes a markdown report to /artifacts/research.md.",
    system_prompt=RESEARCHER_INSTRUCTIONS,
    tools=[search_web],
    model=get_llm(),
)

writer = SubAgent(
    name="writer",
    description="Polishes a draft into a final document.",
    system_prompt=WRITER_INSTRUCTIONS,
    tools=[],
    model=get_llm(),
)

reviewer = SubAgent(
    name="reviewer",
    description="Reviews a draft and returns structured feedback.",
    system_prompt=REVIEWER_INSTRUCTIONS,
    tools=[],
    model=get_llm(cheap=True),
)
```

---

## 16.6 Step 4: FastAPI service with streaming

```python
# app/chat/routes.py
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langchain_core.messages import HumanMessage
from app.deps import current_user
from app.rate_limit import rate_limit
from app.agents.main import agent
from app.backends.namespaced import NamespacedBackend
from app.config import settings
import json

router = APIRouter(prefix="/chat")

@router.post("/{thread_id}/stream")
async def stream_chat(
    thread_id: str,
    body: dict,
    user_id: str = Depends(current_user),
):
    await rate_limit(user_id, "chat")
    config = {
        "configurable": {
            "thread_id": thread_id,
            "user_id": user_id,
        }
    }
    # namespaced backend
    backend = NamespacedBackend(StoreBackend(store=...), user_id, thread_id)
    agent_with_backend = agent.with_config({"configurable": {"backend": backend}})

    async def event_gen():
        async for mode, data in agent_with_backend.astream(
            {"messages": [HumanMessage(content=body["message"])]},
            config,
            stream_mode=["values", "messages"],
        ):
            if mode == "values" and "todos" in data:
                yield f"event: plan\ndata: {json.dumps([t.dict() for t in data['todos']])}\n\n"
            elif mode == "values" and "files" in data:
                yield f"event: files\ndata: {json.dumps(list(data['files'].keys()))}\n\n"
            elif mode == "messages":
                token, _ = data
                if token.content:
                    yield f"event: token\ndata: {json.dumps({'t': token.content})}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")
```

---

## 16.7 Step 5: HITL approval

Add a node in the agent that pauses after the plan and asks for approval:

```python
from langgraph.types import interrupt, Command

def plan_approval_node(state):
    decision = interrupt({
        "type": "plan_approval",
        "todos": state["todos"],
    })
    if not decision.get("approved"):
        return {"messages": [AIMessage(content="Plan rejected by user.")]}
    return {}
```

Wrap the Deep Agent graph (Module 12.5) to include this node.

Resume route:

```python
@router.post("/{thread_id}/resume")
async def resume(thread_id: str, body: dict, user_id: str = Depends(current_user)):
    config = {"configurable": {"thread_id": thread_id, "user_id": user_id}}
    # validate ownership
    state = await get_state(config)
    if state.values.get("user_id") != user_id:
        raise HTTPException(403)
    result = await agent.ainvoke(Command(resume=body["decision"]), config=config)
    return {"ok": True, "result": result}
```

---

## 16.8 Step 6: Rate limiting + cost caps

```python
# app/rate_limit.py
import redis.asyncio as redis
from app.config import settings

r = redis.from_url(settings.REDIS_URL)

LUA = """
local current = tonumber(redis.call('INCR', KEYS[1]))
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""

async def rate_limit(user_id: str, scope: str, limit: int = 60, window_s: int = 60):
    key = f"rl:{scope}:{user_id}"
    n = await r.eval(LUA, 1, key, window_s)
    if int(n) > limit:
        from fastapi import HTTPException
        raise HTTPException(429, "Rate limit exceeded")
```

Cost cap: increment per-user spend in Redis, reject when over budget.

```python
async def check_budget(user_id: str, estimated_cost: float):
    key = f"spend:{user_id}:{today()}"
    cur = float(await r.get(key) or 0)
    if cur + estimated_cost > DAILY_BUDGET[user_plan]:
        raise HTTPException(402, "Daily budget exceeded")
    await r.incrbyfloat(key, estimated_cost)
    await r.expire(key, 86400)
```

---

## 16.9 Step 7: The file system

```python
# app/backends/s3.py (MinIO)
import boto3
from deepagents.backends.protocol import Backend

class S3Backend(Backend):
    def __init__(self, bucket, prefix=""):
        self.s3 = boto3.client(
            "s3",
            endpoint_url="http://minio:9000",  # or AWS endpoint
            aws_access_key_id="...",
            aws_secret_access_key="...",
        )
        self.bucket = bucket
        self.prefix = prefix

    def _key(self, path): return self.prefix + path
    def read(self, path, offset=0, limit=2000): ...
    def write(self, path, content): ...
    def ls(self, path): ...
    def edit(self, path, old, new): ...
```

Wrap with NamespacedBackend for per-user isolation.

---

## 16.10 Step 8: CI

```yaml
# .github/workflows/ci.yml
name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env: { POSTGRES_PASSWORD: test, POSTGRES_DB: test }
        ports: ["5432:5432"]
        options: --health-cmd "pg_isready" --health-interval 5s
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install uv && uv sync
      - run: uv run ruff check .
      - run: uv run mypy app
      - run: uv run pytest -m "not llm"
```

```yaml
# .github/workflows/nightly-evals.yml
name: nightly evals
on: { schedule: [{ cron: "0 3 * * *" }] }
jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install uv && uv sync
      - run: uv run python -m app.evals.run
        env:
          LANGSMITH_API_KEY: ${{ secrets.LANGSMITH_API_KEY }}
      - uses: actions/upload-artifact@v4
        with: { name: eval-report, path: eval-report.json }
```

---

## 16.11 Step 9: Docker + deploy

`Dockerfile`:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN pip install uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY . .
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

`docker-compose.prod.yml`:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ai_saas
      POSTGRES_USER: ai
      POSTGRES_PASSWORD_FILE: /run/secrets/pg_pass
    volumes:
      - pgdata:/var/lib/postgresql/data
    secrets:
      - pg_pass
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ai -d ai_saas"]
      interval: 10s

  redis:
    image: redis:7-alpine

  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minio
      MINIO_ROOT_PASSWORD_FILE: /run/secrets/minio_pass
    volumes:
      - miniodata:/data
    secrets:
      - minio_pass

  app:
    build: .
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_started }
      minio: { condition: service_started }
    environment:
      DATABASE_URL: postgresql://ai:$(cat /run/secrets/pg_pass)@postgres:5432/ai_saas
      REDIS_URL: redis://redis:6379
      S3_ENDPOINT: http://minio:9000
      JWT_SECRET_FILE: /run/secrets/jwt_secret
    secrets:
      - pg_pass
      - minio_pass
      - jwt_secret
    ports:
      - "127.0.0.1:8000:8000"

  cloudflared:
    image: cloudflare/cloudflared:latest
    command: tunnel --no-autoupdate run
    environment:
      TUNNEL_TOKEN_FILE: /run/secrets/cf_token
    secrets:
      - cf_token
    depends_on: [app]

volumes:
  pgdata:
  miniodata:

secrets:
  pg_pass: { file: ./secrets/pg_pass.txt }
  minio_pass: { file: ./secrets/minio_pass.txt }
  jwt_secret: { file: ./secrets/jwt_secret.txt }
  cf_token: { file: ./secrets/cf_token.txt }
```

Deploy:

```bash
# On the Ubuntu server:
git clone https://github.com/you/ai-saas.git
cd ai-saas
docker compose -f docker-compose.prod.yml up -d
```

Then in Cloudflare Zero Trust: route your domain to `http://app:8000`.

---

## 16.12 Step 10: Observability

- `LANGSMITH_TRACING=true` in env. Auto-traces all agent runs.
- Structured JSON logs from FastAPI.
- Sentry for errors.
- Postgres-backed metrics: token usage, costs, error rates (query the `usage` table, Grafana dashboard optional).

---

## 16.13 Step 11: The first user

Once deployed:

1. Sign up yourself (insert into `users` table or write a `/signup` route).
2. Get a token.
3. POST a research request. Watch it work.
4. Check LangSmith for the trace.
5. Approve a plan via the resume endpoint.
6. Download an artifact.
7. Verify the cost is tracked.

---

## 16.14 Step 12: The iteration loop

Now that you have real usage:

1. **Day 1–7:** watch runs in LangSmith. Note the failures.
2. **Day 8–14:** add 5 examples to the eval dataset for each failure mode. Improve the prompt. Re-eval.
3. **Day 15–30:** add a subagent, a tool, a HITL step. Watch the eval score.
4. **Day 30+:** consider pricing tiers, billing, multi-region, autoscaling.

---

## 16.15 The full production checklist

### Code
- [ ] Abstractions: LLM factory, backend factory, agent factory.
- [ ] No vendor SDK leakage outside `app/llm.py`.
- [ ] Type hints + `mypy` clean.
- [ ] `ruff` clean.

### Agent
- [ ] Detailed instructions with examples.
- [ ] 2-4 specialized subagents.
- [ ] Plan approval HITL.
- [ ] Streaming with `messages` + `updates` modes.
- [ ] Compaction for long threads.

### Infra
- [ ] Docker Compose for all services.
- [ ] Cloudflare Tunnel exposing only `app`.
- [ ] Secrets via Docker secrets or env.
- [ ] Health checks.
- [ ] Backups (Postgres volume).

### Operations
- [ ] LangSmith tracing on.
- [ ] Sentry or equivalent.
- [ ] Structured JSON logs.
- [ ] Per-user rate limits.
- [ ] Per-user budget caps.
- [ ] Eval dataset (≥ 30 examples).
- [ ] CI: lint + type-check + unit tests.
- [ ] Nightly: full eval.
- [ ] Runbooks for common failures.

### Security
- [ ] JWT auth on all routes.
- [ ] Per-user file isolation.
- [ ] Input sanitization.
- [ ] Side-effecting tools have HITL.
- [ ] No public ports except via Cloudflare.
- [ ] Secrets in Docker secrets, not env vars in compose file.

---

## 16.16 What's next (beyond this course)

This course gets you to a single-tenant (or simple multi-tenant) MVP. Going further:

- **Billing:** Stripe, metered usage, plan upgrades.
- **Multi-region:** LangGraph Platform or your own Kubernetes.
- **Custom agents per tenant:** let users define their own subagents.
- **Long-running scheduled jobs:** the cron mechanism from Module 09.
- **Voice / multimodal:** add image / audio input.
- **Mobile clients:** the FastAPI backend is already API-first.
- **Enterprise features:** SSO, audit logs, data residency.

But first: ship the MVP. Get paying users. Iterate.

---

## Final hands-on project (this is the real one)

Build, deploy, and exercise the full system. If you do everything in this module, you will have shipped a real AI SaaS.

Suggested 2-week timeline:

| Day | Focus |
|---|---|
| 1 | Project setup, auth, schema |
| 2 | Main agent + researcher subagent |
| 3 | Writer + reviewer subagents |
| 4 | FastAPI routes, streaming |
| 5 | HITL approval flow |
| 6 | File system, MinIO, namespacing |
| 7 | Rate limiting, cost caps, tracking |
| 8 | Docker Compose, deploy locally |
| 9 | CI, evals, dataset |
| 10 | Observability (LangSmith, Sentry) |
| 11 | Polish, error handling, runbooks |
| 12 | Deploy to Ubuntu server |
| 13 | Cloudflare Tunnel + DNS |
| 14 | Smoke test, sign up first user |

After Day 14: you have an AI SaaS. Time to charge money.

---

## Key takeaways

- The course ends, but the architecture stays the same: graph + state + tools + persistence + isolation.
- Every concern from Modules 04–15 maps to a piece of the Capstone.
- Multi-tenancy is mostly: auth + namespacing + per-user limits.
- Ship the MVP. Iterate based on real users.

## Resources

- All previous module resources.
- The full `ai-saas` repo (your build) becomes the canonical reference.
- LangChain / LangGraph Discord: https://discord.gg/langchain
- Cloudflare Tunnel docs: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/
- MinIO docs: https://min.io/docs/
