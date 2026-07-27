# Part 10: Docker + CI/CD with GitHub Actions

> **Continue from:** `03-PRODUCTION-PATTERNS.md`
>
> **In this part:** package everything in Docker, set up local dev with Compose, and add CI/CD.

---

## 10.1 The Docker Mental Model

Containers solve the "works on my machine" problem by packaging:
- Your code
- Your dependencies
- Your system libraries
- Your environment variables

Into one image that runs the same way everywhere.

**The key concepts:**

| Concept | What it is | Analogy |
|---------|-----------|---------|
| **Image** | A snapshot of your app + deps | A class |
| **Container** | A running instance of an image | An instance of a class |
| **Dockerfile** | Recipe to build an image | Source code |
| **Compose** | Multi-container setup (app + DB + Redis) | A runbook |
| **Volume** | Persistent storage | A USB drive attached to a container |
| **Network** | How containers talk to each other | A virtual LAN |

## 10.2 The Dockerfile

```dockerfile
# Dockerfile
# This is a multi-stage build:
# - The "builder" stage installs deps and compiles anything that needs compiling
# - The "runtime" stage copies only what's needed to run
# Result: smaller, more secure final image

# =========================================
# Stage 1: Builder
# =========================================
FROM python:3.12-slim AS builder

# Set environment variables
# PYTHONDONTWRITEBYTECODE: don't create .pyc files
# PYTHONUNBUFFERED: print logs immediately (important for Docker)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build dependencies (only needed to compile Python packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create a virtual environment in /opt/venv
# We use a venv inside the image so we have a clean place for our packages
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements first — this lets Docker cache the install layer
# if your code changes but requirements don't
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# =========================================
# Stage 2: Runtime
# =========================================
FROM python:3.12-slim AS runtime

# Same env vars
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Create a non-root user (security best practice)
# Running as root inside a container is a security risk
RUN groupadd --gid 1000 app && \
    useradd --uid 1000 --gid app --shell /bin/bash --create-home app

# Install runtime system libraries (just libpq for asyncpg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy the virtual environment from the builder stage
COPY --from=builder /opt/venv /opt/venv

# Set the working directory
WORKDIR /app

# Copy the application code
COPY --chown=app:app ./app ./app
COPY --chown=app:app ./alembic ./alembic
COPY --chown=app:app ./alembic.ini ./alembic.ini
COPY --chown=app:app ./scripts ./scripts

# Create directories for uploads and vector data, owned by app user
RUN mkdir -p /app/uploads /app/chroma_data && \
    chown -R app:app /app

# Switch to the non-root user
USER app

# Expose the port (documentation only; you still need -p when running)
EXPOSE 8000

# Health check — Docker uses this to know if the container is healthy
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

# Default command — run uvicorn
# The 0.0.0.0 is critical: it makes the server listen on all interfaces
# (so Docker can forward traffic to it)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Why multi-stage?**
- The builder stage has build tools (~500MB) we don't need at runtime
- The runtime stage only has what's needed to run (~200MB)
- Smaller images = faster deploys, less attack surface

**Why non-root user?**
- If someone breaks out of the app, they're `app` user, not `root`
- It's a basic security practice

## 10.3 The .dockerignore

```dockerignore
# .dockerignore
# Files NOT to send to Docker. Smaller builds, faster, more secure.

# Git
.git
.gitignore

# Python
__pycache__
*.py[cod]
*$py.class
.pytest_cache
.mypy_cache
.ruff_cache
*.egg-info

# Virtual env
.venv
venv

# Env
.env
.env.local

# IDE
.vscode
.idea

# App data
uploads
chroma_data
*.log
logs

# Docker (don't recurse)
Dockerfile
.dockerignore
docker-compose.yml

# Tests (in prod image)
tests

# Docs
*.md
docs
```

## 10.4 The Docker Compose for Local Dev

```yaml
# docker-compose.yml
# This is your local dev environment.
# One command brings up: app, postgres, redis.

version: "3.9"

services:
  # =========================================
  # The FastAPI app
  # =========================================
  app:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: documind-app
    # Run the app with hot-reload (only in dev)
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    volumes:
      # Mount the code as a volume for hot-reload
      - ./app:/app/app
      - ./uploads:/app/uploads
      - ./chroma_data:/app/chroma_data
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://documind:documind@db:5432/documind
      - REDIS_URL=redis://redis:6379/0
      - ENVIRONMENT=local
      - DEBUG=true
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - documind-net

  # =========================================
  # PostgreSQL
  # =========================================
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
      # Expose to host for direct DB access (e.g., psql, pgAdmin)
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U documind -d documind"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - documind-net

  # =========================================
  # Redis (for ARQ + rate limiting)
  # =========================================
  redis:
    image: redis:7-alpine
    container_name: documind-redis
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - documind-net

  # =========================================
  # ARQ Worker (background jobs)
  # =========================================
  worker:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: documind-worker
    # Run the ARQ worker
    command: arq app.workers.arq_worker.WorkerSettings
    volumes:
      - ./app:/app/app
      - ./uploads:/app/uploads
    environment:
      - DATABASE_URL=postgresql+asyncpg://documind:documind@db:5432/documind
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis
    networks:
      - documind-net

  # =========================================
  # pgAdmin (DB UI, optional, for debugging)
  # =========================================
  pgadmin:
    image: dpage/pgadmin4:latest
    container_name: documind-pgadmin
    environment:
      PGADMIN_DEFAULT_EMAIL: [email protected]
      PGADMIN_DEFAULT_PASSWORD: admin
    ports:
      - "5050:80"
    depends_on:
      - db
    networks:
      - documind-net

# =========================================
# Volumes (persistent data)
# =========================================
volumes:
  postgres_data:
  redis_data:

# =========================================
# Networks
# =========================================
networks:
  documind-net:
    driver: bridge
```

### Using Compose

```bash
# Start everything
docker compose up -d

# See logs
docker compose logs -f app

# Run a command inside the app container
docker compose exec app alembic upgrade head
docker compose exec app pytest

# Stop everything
docker compose down

# Stop and remove all data (careful!)
docker compose down -v
```

## 10.5 Database Migrations with Alembic

Alembic tracks your DB schema changes. Every time you change a model, you make a migration.

```bash
# Initialize Alembic (do this once)
alembic init alembic

# Configure alembic/env.py to use our models
```

```python
# alembic/env.py
"""Alembic environment — runs for every migration."""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import your config and models
from app.config import settings
from app.db.base import Base
# Import every model so Alembic sees them
from app.db.models import *  # noqa: F401, F403

config = context.config
config.set_main_option("sqlalchemy.url", str(settings.database_url))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without an active connection (for SQL generation)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in async mode."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations with a connection."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

```bash
# Create a migration after changing models
docker compose exec app alembic revision --autogenerate -m "add documents and messages tables"

# Apply migrations
docker compose exec app alembic upgrade head

# Roll back one migration
docker compose exec app alembic downgrade -1

# See current state
docker compose exec app alembic current
```

**The rule:** never edit the DB schema manually. Always make a migration. Check the auto-generated migration to make sure it's right.

## 10.6 GitHub Actions (CI/CD)

This is where the magic happens — every push to GitHub runs your tests, every merge to main deploys to production.

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    name: Test
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: test_db
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:7
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install pytest pytest-asyncio pytest-cov httpx

      - name: Run tests
        env:
          DATABASE_URL: postgresql+asyncpg://test:test@localhost:5432/test_db
          REDIS_URL: redis://localhost:6379/0
          SECRET_KEY: test-secret-key
        run: |
          pytest --cov=app --cov-report=xml --cov-report=term-missing

      - name: Upload coverage
        if: always()
        uses: codecov/codecov-action@v4
        with:
          file: coverage.xml
          fail_ci_if_error: false

  lint:
    name: Lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install ruff mypy
      - run: ruff check .
      - run: ruff format --check .
      - run: mypy app
```

**The pipeline:**
1. You push code
2. GitHub spins up a fresh Ubuntu VM
3. Installs Python, your deps
4. Runs pytest against a real PostgreSQL + Redis
5. Runs linters (ruff) and type checker (mypy)
6. Reports pass/fail back to GitHub
7. (Optional) Uploads coverage to Codecov

If any step fails, the PR is blocked. **That's the gate.**

## 10.7 Deployment (the "ship it" part)

Three good free options:

### Option 1: Fly.io (recommended for beginners)

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Login
fly auth signup  # or `fly auth login`

# Launch (in your project dir)
fly launch
# It will detect your Dockerfile and ask questions
# Pick a region, give it a name, don't add a Postgres (we have our own)

# Set secrets
fly secrets set \
  SECRET_KEY="$(openssl rand -hex 32)" \
  GOOGLE_API_KEY="your-key" \
  DATABASE_URL="postgresql+asyncpg://..." \
  REDIS_URL="redis://..."

# Deploy
fly deploy

# See logs
fly logs

# SSH in
fly ssh console
```

### Option 2: Render

- Connect your GitHub repo
- Create a Web Service from the Dockerfile
- Set env vars in the dashboard
- Auto-deploys on push to main

### Option 3: Railway

- Connect GitHub repo
- Click "Deploy"
- Set env vars
- Pay-as-you-go (free tier exists)

### Option 4: Self-host on a VPS

```bash
# On a fresh Ubuntu VPS:
# 1. Install Docker
curl -fsSL https://get.docker.com | sh

# 2. Clone your repo
git clone https://github.com/you/documind-ai.git
cd documind-ai

# 3. Set up .env
cp .env.example .env
nano .env  # fill in real values

# 4. Run
docker compose up -d

# 5. Set up a reverse proxy (Caddy is the easiest)
# Caddyfile:
# yourdomain.com {
#     reverse_proxy localhost:8000
#     encode gzip
# }
```

## 10.8 The Production docker-compose.yml

For production, you want a separate compose file:

```yaml
# docker-compose.prod.yml
# Production overrides — no hot-reload, different env, etc.

services:
  app:
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
    environment:
      - ENVIRONMENT=production
      - DEBUG=false
    # No volumes (use the image as-is)
    restart: unless-stopped

  worker:
    restart: unless-stopped

  db:
    restart: unless-stopped
    # Don't expose port to host
    expose:
      - "5432"

  redis:
    restart: unless-stopped
    expose:
      - "6379"
```

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## 10.9 Backups (don't lose data)

```bash
# Backup the database
docker compose exec db pg_dump -U documind documind > backup_$(date +%Y%m%d).sql

# Restore
cat backup_20260101.sql | docker compose exec -T db psql -U documind documind

# Automate with cron
# 0 3 * * * cd /path/to/project && docker compose exec -T db pg_dump -U documind documind | gzip > /backups/db_$(date +\%Y\%m\%d).sql.gz
```

## 10.10 Quick Recap

You now have:
- A Dockerfile with multi-stage build
- docker-compose for local dev (app + DB + Redis + worker)
- Alembic for DB migrations
- GitHub Actions for CI (test + lint on every push)
- Multiple deployment options

In Part 11 we shift gears and talk about the actual workflow — how to use AI to build all of this.

---
