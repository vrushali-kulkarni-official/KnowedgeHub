# Part 13: Capstone — Ship DocuMind AI End-to-End

> **Continue from:** `06-ADVANCED-PATTERNS.md`
>
> **In this part:** the full shipping checklist. Take everything from Parts 6-12 and turn it into a deployed, monitored, production SaaS.

---

## 13.1 The Capstone: What "Done" Looks Like

By the end of this part, you'll have:

- [ ] All the code from Parts 6-12 working together
- [ ] A clean repo with proper structure
- [ ] Tests passing in CI
- [ ] Docker images building successfully
- [ ] A deployment that anyone can sign up for
- [ ] Monitoring that tells you when things break
- [ ] Documentation that explains what it is and how to use it

## 13.2 The Final Project Structure

```
documind-ai/
├── .env.example
├── .env
├── .gitignore
├── .dockerignore
├── .github/
│   └── workflows/
│       ├── ci.yml                    # Tests on every PR
│       └── deploy.yml                # Deploy on merge to main
├── docker-compose.yml
├── docker-compose.prod.yml
├── Dockerfile
├── Makefile
├── README.md
├── pyproject.toml                     # Modern Python project config
├── requirements.txt                   # Pinned deps for Docker
├── alembic.ini
│
├── app/
│   ├── __init__.py
│   ├── main.py                       # FastAPI app + lifespan + middleware
│   ├── config.py                     # Settings
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py                   # Auth, DB, current user
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py             # Aggregate v1 routes
│   │       ├── auth.py
│   │       ├── users.py
│   │       ├── documents.py
│   │       └── chat.py
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── security.py               # JWT, password hashing
│   │   ├── logging.py                # Structured logging
│   │   ├── exceptions.py             # Custom exceptions + handlers
│   │   ├── rate_limit.py             # Rate limiting
│   │   └── cache.py                  # LLM cache
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── session.py
│   │   └── models/
│   │       ├── __init__.py
│   │       ├── user.py
│   │       ├── document.py
│   │       ├── chat_session.py
│   │       └── message.py
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── token.py
│   │   ├── document.py
│   │   └── chat.py
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── user_service.py
│   │   ├── document_service.py
│   │   ├── chat_service.py
│   │   └── llm/
│   │       ├── __init__.py
│   │       ├── llm_factory.py        # Vendor-agnostic LLM creation
│   │       ├── prompts.py            # All prompt templates
│   │       ├── chains.py             # LCEL chains
│   │       ├── vector_store.py       # ChromaDB wrapper
│   │       ├── tools.py              # Agent tools
│   │       └── agents.py             # Multi-agent workflows
│   │
│   └── workers/
│       ├── __init__.py
│       ├── arq_worker.py             # Background job worker
│       └── pdf_processor.py          # PDF → chunks → embeddings
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                   # Shared fixtures
│   ├── api/
│   │   └── v1/
│   │       ├── test_auth.py
│   │       ├── test_users.py
│   │       ├── test_documents.py
│   │       └── test_chat.py
│   ├── services/
│   │   ├── test_user_service.py
│   │   ├── test_document_service.py
│   │   └── test_chat_service.py
│   └── workers/
│       └── test_pdf_processor.py
│
├── scripts/
│   ├── seed.py                       # Seed test data
│   └── create_superuser.py
│
├── docs/
│   ├── README.md
│   ├── ARCHITECTURE.md
│   ├── DEPLOYMENT.md
│   └── API.md
│
└── uploads/                          # .gitkeep only
    └── .gitkeep
```

## 13.3 The Final pyproject.toml

```toml
# pyproject.toml
# Modern Python project config. Use this for tools config,
# use requirements.txt for Docker (pinned versions).

[project]
name = "documind-ai"
version = "0.1.0"
description = "Chat with your documents. AI SaaS."
requires-python = ">=3.12"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
# Enable these rule sets
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort (import sorting)
    "B",   # flake8-bugbear (common bugs)
    "C4",  # flake8-comprehensions
    "UP",  # pyupgrade (modern Python)
    "N",   # pep8-naming
    "S",   # flake8-bandit (security)
    "T20", # flake8-print (no print statements)
]
# Allow these in specific cases
ignore = [
    "S101",  # Use of assert (fine in tests)
    "B008",  # Function call in default argument (FastAPI uses this)
]

[tool.ruff.lint.per-file-ignores]
# Tests can be more relaxed
"tests/**" = ["S101", "S105", "S106"]

[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["pydantic.mypy"]
ignore_missing_imports = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-v --strict-markers --tb=short"
markers = [
    "unit: unit tests",
    "integration: integration tests",
    "slow: slow tests",
]
```

## 13.4 The Final requirements.txt

```text
# requirements.txt
# Pinned versions for reproducible builds.
# Update with: pip install --upgrade -r requirements.txt
# Then run: pip freeze > requirements.txt

# Web framework
fastapi==0.115.6
uvicorn[standard]==0.34.0

# Database
sqlalchemy[asyncio]==2.0.36
asyncpg==0.30.0
alembic==1.14.0
psycopg2-binary==2.9.10  # For Alembic (sync)

# Validation
pydantic==2.10.4
pydantic-settings==2.7.1
email-validator==2.2.0

# Auth
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
bcrypt==4.0.1  # pin to avoid passlib warning

# File uploads
python-multipart==0.0.20

# LLM
langchain==0.3.20
langchain-core==0.3.49
langchain-google-genai==2.1.5
langchain-openai==0.3.5
langchain-anthropic==0.3.5
langchain-chroma==0.2.2
langchain-text-splitters==0.3.5
google-generativeai==0.8.4

# Vector store
chromadb==0.6.3

# PDF
pypdf==5.1.0

# Background jobs
arq==0.26.3

# Cache + rate limit
redis==5.2.1
slowapi==0.1.9

# Observability
structlog==24.4.0
langfuse==3.0.4

# Resilience
tenacity==9.0.0

# Dev
pytest==8.3.4
pytest-asyncio==0.25.0
pytest-cov==6.0.0
httpx==0.28.1
faker==33.1.0
ruff==0.8.4
mypy==1.14.0
```

## 13.5 The Final docker-compose.yml

```yaml
# docker-compose.yml
# Local development environment.
name: documind

services:
  app:
    build: .
    container_name: documind-app
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    volumes:
      - ./app:/app/app
      - ./uploads:/app/uploads
      - ./chroma_data:/app/chroma_data
    ports:
      - "8000:8000"
    env_file: .env
    environment:
      - DATABASE_URL=postgresql+asyncpg://documind:documind@db:5432/documind
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - documind-net
    restart: unless-stopped

  worker:
    build: .
    container_name: documind-worker
    command: arq app.workers.arq_worker.WorkerSettings
    volumes:
      - ./app:/app/app
      - ./uploads:/app/uploads
    env_file: .env
    environment:
      - DATABASE_URL=postgresql+asyncpg://documind:documind@db:5432/documind
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis
    networks:
      - documind-net
    restart: unless-stopped

  db:
    image: postgres:16-alpine
    container_name: documind-db
    environment:
      POSTGRES_USER: documind
      POSTGRES_PASSWORD: documind
      POSTGRES_DB: documind
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U documind"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - documind-net
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    container_name: documind-redis
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - documind-net
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:

networks:
  documind-net:
    driver: bridge
```

## 13.6 The Final main.py

```python
# app/main.py
"""
The DocuMind AI FastAPI application.

This is the entry point. It wires up:
- The FastAPI app
- Middleware (CORS, logging, etc.)
- Exception handlers
- Rate limiting
- API routers
- Lifecycle events (startup/shutdown)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.v1.router import api_router
from app.config import settings
from app.core.cache import cache
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, logger
from app.core.rate_limit import limiter


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown."""
    # Startup
    configure_logging()
    logger.info(
        "app_starting",
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        llm=f"{settings.llm_provider}/{settings.llm_model}",
    )
    await cache.init()
    yield
    # Shutdown
    logger.info("app_shutting_down")


# Create the app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Chat with your documents using AI.",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url="/redoc" if settings.environment != "production" else None,
    openapi_url="/openapi.json" if settings.environment != "production" else None,
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Custom exception handlers
register_exception_handlers(app)

# CORS
origins = [o.strip() for o in settings.cors_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)


# =========================================
# Health check
# =========================================

@app.get("/health", tags=["health"])
async def health() -> dict:
    """Health check endpoint."""
    # Check that we can talk to the DB
    from app.db.session import AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as session:
            await session.execute("SELECT 1")
        db_healthy = True
    except Exception:
        db_healthy = False
    return {
        "status": "ok" if db_healthy else "degraded",
        "app": settings.app_name,
        "version": settings.app_version,
        "db": db_healthy,
    }


# =========================================
# Mount the API
# =========================================

app.include_router(api_router, prefix=settings.api_v1_prefix)
```

## 13.7 The GitHub Actions Deployment

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  test:
    uses: ./.github/workflows/ci.yml

  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Deploy to Fly.io
        uses: superfly/flyctl-actions/setup-flyctl@master

      - name: Deploy
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
        run: flyctl deploy --remote-only

      - name: Run migrations
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
        run: flyctl ssh console -C "alembic upgrade head"

      - name: Health check
        run: |
          sleep 10
          curl -f https://documind.fly.dev/health || exit 1
```

## 13.8 The README

```markdown
# DocuMind AI

Chat with your documents using AI. Upload PDFs, ask questions, get answers with sources.

## Quick start (local dev)

```bash
git clone https://github.com/yourusername/documind-ai.git
cd documind-ai
cp .env.example .env
# Edit .env with your API keys
make up
# Visit http://localhost:8000/docs
```

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Development

```bash
make up       # Start all services
make logs     # Follow logs
make test     # Run tests
make lint     # Lint and format
make migrate  # Run DB migrations
```

## Production deployment

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## API

See [docs/API.md](docs/API.md) or visit `/docs` after starting the app.

## Stack

- **Backend:** FastAPI, Python 3.12, async
- **Database:** PostgreSQL 16 via SQLAlchemy 2.0
- **AI:** LangChain + Google Gemini (configurable)
- **Vector store:** ChromaDB
- **Background jobs:** ARQ + Redis
- **Auth:** JWT
- **Deployment:** Docker + Fly.io
- **CI/CD:** GitHub Actions

## License

MIT
```

## 13.9 The Pre-Launch Checklist (do all of these)

### Code Quality
- [ ] All tests pass (`make test`)
- [ ] No linter errors (`make lint`)
- [ ] No type errors (`mypy app`)
- [ ] Coverage >80% on services and API
- [ ] No secrets in code (only in env vars)
- [ ] All dependencies pinned in `requirements.txt`

### Security
- [ ] All endpoints require auth (except /health, /auth/*)
- [ ] Passwords are hashed (bcrypt, not MD5/SHA)
- [ ] JWT tokens have expiry
- [ ] CORS is configured (not `*`)
- [ ] File uploads have size and type limits
- [ ] SQL queries use SQLAlchemy (no string concat)
- [ ] User data is filtered by user_id (multi-tenant safety)
- [ ] `.env` is in `.gitignore`
- [ ] `.env.example` has placeholders, no real keys
- [ ] Dependencies are scanned for vulnerabilities (`pip-audit`)

### Performance
- [ ] DB queries have indexes on frequently-filtered columns
- [ ] LLM calls have `max_tokens` set
- [ ] LLM calls have timeouts
- [ ] Expensive operations run in background
- [ ] Rate limits are set on expensive endpoints
- [ ] Database connection pool is sized appropriately

### Observability
- [ ] Structured logging (structlog) configured
- [ ] LLM calls traced (Langfuse)
- [ ] Errors tracked (Sentry or similar)
- [ ] Uptime monitoring set up
- [ ] Health check endpoint works
- [ ] Token usage and cost logged

### Operations
- [ ] Database backups configured
- [ ] Secrets stored in env vars (not in code)
- [ ] CI runs on every PR
- [ ] Deployment is automated
- [ ] Rollback plan documented
- [ ] Disaster recovery plan documented

### Documentation
- [ ] README explains what it is
- [ ] README explains how to run it
- [ ] API is documented (auto-generated by FastAPI)
- [ ] Architecture is documented
- [ ] Deployment is documented

## 13.10 The Launch (deploy it)

```bash
# 1. Make sure your code is on GitHub
git init
git add -A
git commit -m "Initial commit"
git remote add origin https://github.com/yourusername/documind-ai.git
git push -u origin main

# 2. Deploy to Fly.io (or your chosen platform)
fly launch
fly secrets set SECRET_KEY="$(openssl rand -hex 32)" GOOGLE_API_KEY="..."
fly deploy
fly ssh console -C "alembic upgrade head"

# 3. Verify
curl https://your-app.fly.dev/health
open https://your-app.fly.dev/docs

# 4. Set up monitoring
# - Langfuse: sign up, add keys to Fly secrets
# - Sentry: sign up, add DSN
# - Uptime: betterstack.com or similar
```

## 13.11 The First 30 Days (what to watch)

Once you launch, monitor these:

| Metric | What it tells you | Target |
|--------|-------------------|--------|
| Uptime | Is the service reachable? | >99% |
| Error rate | Are requests failing? | <1% |
| p95 latency | How slow is the slow path? | <3s for chat |
| LLM cost per user | Are you going bankrupt? | <$1/user/day |
| Signup rate | Is anyone using it? | Grows over time |
| Activation rate | Do signups become users? | >30% |

**Day 1:** watch the logs. Fix every error. Read every stack trace.

**Week 1:** add 1-2 features based on user feedback. Polish what users actually use.

**Month 1:** look at the metrics. Where are users dropping off? What's slow? What's expensive? Optimize.

## 13.12 What Comes Next (the path forward)

After you ship DocuMind AI, you have a foundation. Here's where you can take it:

| Direction | What to add |
|-----------|-------------|
| **Multi-tenant hardening** | Organizations, teams, role-based access control |
| **Billing** | Stripe integration, usage-based pricing, plan limits |
| **More file types** | Word, PowerPoint, Notion, Google Drive, Confluence |
| **Better RAG** | Hybrid search, reranking, query rewriting, citations |
| **Agents** | Multi-step research, tool use, web search |
| **Voice** | Whisper for input, ElevenLabs for output |
| **Mobile** | React Native app, push notifications |
| **Analytics** | User dashboards, usage reports |
| **Integrations** | Slack bot, browser extension, API for third parties |
| **Compliance** | SOC 2, GDPR, HIPAA (if your users need it) |

## 13.13 The Final Lesson (the most important one)

The single biggest predictor of success in AI SaaS is **shipping and iterating**. Most projects die in planning. The pros:

1. Build the smallest thing that works (MVI — minimum viable implementation)
2. Ship it to real users
3. Watch what they do
4. Fix what hurts
5. Cut what they don't use
6. Repeat

The code in this course is a starting point. The patterns are real. But the only way to truly learn is to build, ship, and iterate. Don't try to make it perfect before you launch. Launch, then make it better.

**The pro move:** every weekend, build a small AI project and ship it. Not for users, for yourself. The repetition is what makes you fast.

## 13.14 Where to Go From Here (resources)

| Resource | What it is | Cost |
|----------|-----------|------|
| [FastAPI docs](https://fastapi.tiangolo.com) | The web framework | Free |
| [LangChain docs](https://python.langchain.com) | The LLM framework | Free |
| [SQLAlchemy 2.0 tutorial](https://docs.sqlalchemy.org/en/20/tutorial/) | The ORM | Free |
| [Karpathy's "Software 3.0" talk](https://www.youtube.com/results?search_query=karpathy+software+3.0) | Vibe coding philosophy | Free |
| [The Pragmatic Engineer newsletter](https://newsletter.pragmaticengineer.com) | Real engineering in tech | $$ |
| [Full Stack FastAPI Template](https://github.com/tiangolo/full-stack-fastapi-template) | Production-ready template | Free |
| [Awesome LLM](https://github.com/Hannibal046/Awesome-LLM) | Curated LLM resources | Free |
| [LangChain templates](https://github.com/langchain-ai/langchain/tree/master/templates) | Starting points for common patterns | Free |

## 13.15 You Did It 🎉

You just learned:
- What vibe coding and agentic AI coding are
- How to set up the right tools
- How to use AI coding assistants effectively
- How to build a FastAPI + PostgreSQL backend
- How to integrate LLMs via LangChain
- How to build RAG (the pattern powering every AI SaaS)
- How to add auth, rate limiting, logging, testing
- How to containerize and deploy
- How to set up CI/CD
- How to use the AI workflow day-to-day
- Advanced patterns (multi-agent, streaming, memory)
- How to ship a complete AI SaaS

**The next step is yours.** Open your editor, spin up Continue, paste in the spec, and start building. You've got this.

---
