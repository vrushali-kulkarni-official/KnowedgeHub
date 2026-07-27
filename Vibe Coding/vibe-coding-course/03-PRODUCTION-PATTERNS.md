# Part 9: Production Concerns (Testing, Logging, Rate Limiting, Error Handling)

> **Continue from:** `02-RAG-DEEP-DIVE.md`
>
> **In this part:** the boring stuff that makes the difference between a prototype and a product.

---

## 9.1 The Production Checklist

Before you ship anything, every item on this list should be addressed:

| Concern | What it means | Why it matters |
|---------|---------------|----------------|
| Testing | Automated tests for your code | Catch bugs before users do |
| Logging | Structured logs of what happened | Debug production issues |
| Error handling | Graceful failures with good messages | Don't leak stack traces to users |
| Rate limiting | Throttle abusive users | Protect from cost overruns |
| Auth & authz | Authentication + authorization | Security 101 |
| Input validation | Sanitize all inputs | Prevent injection attacks |
| CORS | Cross-origin resource sharing | Web security |
| Secrets management | API keys not in code | Don't leak credentials |
| Monitoring | Know when things break | React to incidents |
| Backups | Database backups | Don't lose data |
| Documentation | How to use / deploy | Onboard teammates / your future self |

Let's cover each.

## 9.2 Testing — The Unsexy Superpower

```bash
pip install pytest pytest-asyncio pytest-cov httpx faker
```

### Test Configuration

```python
# pytest.ini or pyproject.toml [tool.pytest.ini_options]
[tool.pytest.ini_options]
asyncio_mode = "auto"  # auto-detect async test functions
testpaths = ["tests"]
addopts = "-v --strict-markers --tb=short"
markers = [
    "unit: unit tests",
    "integration: integration tests",
    "slow: slow tests",
]
```

### Test Fixtures (the shared setup)

```python
# tests/conftest.py
"""
Shared test fixtures.

Fixtures are reusable test setup. Define them once, use them in many tests.
"""

import asyncio
import os
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient  # Async HTTP client
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# Set test environment BEFORE importing the app
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@localhost:5432/test_db"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"

from app.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.models.user import User  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402


# =========================================
# Database setup
# =========================================

# Use a separate test database
TEST_DATABASE_URL = os.environ["DATABASE_URL"]


@pytest_asyncio.fixture(scope="session")
async def engine():
    """Create the test database engine."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    # Drop all tables after tests
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db(engine):
    """Provide a clean DB session for each test."""
    # Use a connection with a transaction that we rollback
    async with engine.connect() as connection:
        transaction = await connection.begin()
        async with AsyncSession(bind=connection) as session:
            yield session
            await transaction.rollback()  # Undo all changes


# =========================================
# HTTP client
# =========================================

@pytest_asyncio.fixture
async def client(db):
    """Provide an HTTP client that talks to our app in-process."""
    # Override the get_db dependency to use our test session
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# =========================================
# Test data factories
# =========================================

@pytest_asyncio.fixture
async def test_user(db) -> User:
    """Create a test user."""
    from app.core.security import get_password_hash

    user = User(
        id=uuid.uuid4(),
        email="[email protected]",
        hashed_password=get_password_hash("testpass123"),
        full_name="Test User",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_headers(test_user) -> dict:
    """Provide auth headers for the test user."""
    from app.core.security import create_access_token

    token = create_access_token(subject=str(test_user.id))
    return {"Authorization": f"Bearer {token}"}
```

### Unit Tests (testing one thing)

```python
# tests/services/test_user_service.py
"""Unit tests for the user service."""

import pytest

from app.core.security import get_password_hash, verify_password
from app.schemas.user import UserCreate
from app.services import user_service


@pytest.mark.asyncio
async def test_create_user_hashes_password(db):
    """Creating a user should hash the password, not store it plain."""
    user_in = UserCreate(
        email="[email protected]",
        password="plain-text-password",
        full_name="New User",
    )
    user = await user_service.create_user(db, user_in)

    # Password should be hashed (not equal to the original)
    assert user.hashed_password != "plain-text-password"

    # And the hash should verify
    assert verify_password("plain-text-password", user.hashed_password)


@pytest.mark.asyncio
async def test_get_user_by_email_returns_none_for_missing(db):
    """Looking up a non-existent email should return None, not raise."""
    result = await user_service.get_user_by_email(db, "[email protected]")
    assert result is None


@pytest.mark.asyncio
async def test_authenticate_with_wrong_password_returns_none(db, test_user):
    """Wrong password should return None (not raise, not return user)."""
    result = await user_service.authenticate(
        db, email=test_user.email, password="wrong-password"
    )
    assert result is None
```

### API Tests (testing endpoints)

```python
# tests/api/v1/test_auth.py
"""Integration tests for auth endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_new_user(client: AsyncClient):
    """Should be able to register a new user."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "[email protected]",
            "password": "secure-password-123",
            "full_name": "New User",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "[email protected]"
    assert "hashed_password" not in data  # CRITICAL: never return this


@pytest.mark.asyncio
async def test_register_duplicate_email_fails(client: AsyncClient, test_user):
    """Registering with an existing email should return 400."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": test_user.email,
            "password": "another-password-123",
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_login_returns_token(client: AsyncClient, test_user):
    """Login with correct credentials returns a JWT."""
    response = await client.post(
        "/api/v1/auth/login",
        data={
            "username": test_user.email,
            "password": "testpass123",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(client: AsyncClient, test_user):
    """Login with wrong password returns 401."""
    response = await client.post(
        "/api/v1/auth/login",
        data={
            "username": test_user.email,
            "password": "wrong-password",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_requires_auth(client: AsyncClient):
    """The /users/me endpoint should require authentication."""
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_returns_current_user(client: AsyncClient, test_user, auth_headers):
    """With a valid token, /users/me returns the current user."""
    response = await client.get("/api/v1/users/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["email"] == test_user.email
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=term-missing

# Run a specific test
pytest tests/api/v1/test_auth.py::test_login_returns_token

# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration
```

**The rule of thumb:** aim for 80%+ coverage on services and API code. Don't chase 100% — focus on the logic that matters.

## 9.3 Structured Logging (know what happened in production)

```bash
pip install structlog
```

```python
# app/core/logging.py
"""
Structured logging with structlog.

Why structured:
- JSON logs are machine-parseable
- You can search, filter, alert on them
- "User 123 logged in" → {"event": "user.login", "user_id": 123}
- Tools like Datadog, Loki, CloudWatch Logs can ingest this directly

Why structlog:
- Best structured logging library for Python
- Plays nice with stdlib logging
- Works with async code
- Pretty console output in dev, JSON in prod
"""

import logging
import sys

import structlog
from structlog.types import EventDict, Processor

from app.config import settings


def add_app_metadata(_, __, event_dict: EventDict) -> EventDict:
    """Add app metadata to every log line."""
    event_dict["app"] = settings.app_name
    event_dict["environment"] = settings.environment
    event_dict["version"] = settings.app_version
    return event_dict


def configure_logging() -> None:
    """Configure structured logging for the app."""

    # The processors run in order on every log call
    shared_processors: list[Processor] = [
        # Add log level (info, warning, error)
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        # Add timestamp
        structlog.processors.TimeStamper(fmt="iso"),
        # Add stack info if there's an exception
        structlog.processors.StackInfoRenderer(),
        # Convert exceptions to formatted tracebacks
        structlog.processors.format_exc_info,
        # Add our custom metadata
        add_app_metadata,
    ]

    if settings.environment == "local":
        # In dev, pretty colors for humans
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    else:
        # In prod, JSON for machines
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Also configure stdlib logging so libraries (uvicorn, sqlalchemy) use it
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level),
    )


# Get a logger you can use anywhere
logger = structlog.get_logger()
```

Usage:

```python
from app.core.logging import logger

# Simple
logger.info("user_registered", user_id=str(user.id), email=user.email)

# With context
logger.bind(request_id="abc-123").info("processing_chat", session_id=session_id)

# Errors
try:
    do_something()
except Exception as e:
    logger.error("processing_failed", error=str(e), exc_info=True)
```

## 9.4 Custom Exception Handling

```python
# app/core/exceptions.py
"""
Custom exceptions and global handlers.

Why custom exceptions:
- Domain-specific errors (e.g., DocumentNotFound) instead of generic ValueError
- Global handler maps them to nice HTTP responses
- Consistent error format across the API
"""

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppException(Exception):
    """Base exception for our app."""
    status_code: int = 500
    message: str = "An unexpected error occurred"

    def __init__(self, message: str | None = None):
        if message:
            self.message = message
        super().__init__(self.message)


class NotFoundError(AppException):
    status_code = 404
    message = "Resource not found"


class UnauthorizedError(AppException):
    status_code = 401
    message = "Not authenticated"


class ForbiddenError(AppException):
    status_code = 403
    message = "Not allowed"


class BadRequestError(AppException):
    status_code = 400
    message = "Bad request"


class RateLimitError(AppException):
    status_code = 429
    message = "Rate limit exceeded"


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the app."""

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        """Handle our custom exceptions."""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.__class__.__name__,
                    "message": exc.message,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Handle Pydantic validation errors."""
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "ValidationError",
                    "message": "Invalid request data",
                    "details": exc.errors(),  # The field-level errors
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        """Catch-all for unexpected errors."""
        # Log the full error for debugging
        from app.core.logging import logger
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            exc_info=True,
        )
        # Return a generic message to the user (don't leak internals)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "InternalServerError",
                    "message": "An unexpected error occurred. Please try again.",
                }
            },
        )
```

Usage in a service:

```python
# Before
if not document:
    raise HTTPException(status_code=404, detail="Document not found")

# After (cleaner)
if not document:
    raise NotFoundError("Document not found")
```

Wire it up in `main.py`:

```python
from app.core.exceptions import register_exception_handlers
register_exception_handlers(app)
```

## 9.5 Rate Limiting (don't go bankrupt)

```bash
pip install slowapi
```

```python
# app/core/rate_limit.py
"""
Rate limiting with slowapi.

Why rate limit:
- Protect against abuse (someone hitting your LLM endpoint 1000x/sec)
- Control costs (LLM API bills add up fast)
- Fairness (one user can't starve others)

We rate limit per IP for unauthenticated endpoints,
per user for authenticated ones.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings


# Key function: how to identify the client
# For unauthenticated: by IP
# For authenticated: by user ID (we'd inject this via dependency)


def get_rate_limit_key(request):
    """Get the key to rate limit on. Uses user ID if authenticated, else IP."""
    # If the user is authenticated, the user_id is set by the auth dep
    if hasattr(request.state, "user_id"):
        return f"user:{request.state.user_id}"
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(
    key_func=get_rate_limit_key,
    default_limits=[settings.default_rate_limit],  # e.g. "100/minute"
    storage_uri=settings.redis_url,  # Required for distributed rate limiting
)
```

Usage in a route:

```python
from fastapi import Request
from app.core.rate_limit import limiter

@router.post("/chat")
@limiter.limit("10/minute")  # Stricter limit for expensive endpoint
async def chat(request: Request, ...):
    ...
```

Wire it up:

```python
# main.py
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.core.rate_limit import limiter

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

## 9.6 CORS Done Right

```python
# In main.py
from fastapi.middleware.cors import CORSMiddleware

# In dev: allow localhost:3000 (the frontend dev server)
# In prod: set CORS_ORIGINS to your actual frontend domain
origins = [o.strip() for o in settings.cors_origins.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # NOT "*" when allow_credentials=True
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],  # Be specific
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,  # Cache preflight for 10 minutes
)
```

**Don't** use `allow_origins=["*"]` with `allow_credentials=True` — browsers will reject it. Be explicit.

## 9.7 The Settings Upgrades

```python
# Add to app/config.py
# CORS
cors_origins: str = "http://localhost:3000"

# Redis (for rate limiting, ARQ, caching)
redis_url: str = "redis://localhost:6379/0"

# Logging
log_level: str = "INFO"
default_rate_limit: str = "100/minute"
```

## 9.8 Documentation (auto-generated, free)

FastAPI gives you Swagger UI and ReDoc for free. Just visit `/docs` and `/redoc`. Make sure to use `tags`, `summary`, and `description` so the docs are useful.

```python
@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Send a chat message",
    description="Send a message to the AI. Uses RAG over the user's documents.",
)
async def chat(...):
    ...
```

For user-facing docs (how to use the API), tools like Mintlify or ReadMe can ingest your OpenAPI spec and generate nice docs.

## 9.9 Monitoring (know when things break)

**Free options for monitoring:**

| Tool | What it does | Free tier |
|------|--------------|-----------|
| Langfuse | LLM tracing (prompt, response, tokens, latency) | ✅ Generous |
| Sentry | Error tracking | ✅ For small apps |
| Betterstack | Uptime monitoring + logs | ✅ |
| Grafana + Loki | Self-hosted logs | ✅ Free if self-hosted |

For LLM apps specifically, **Langfuse is the killer feature** because it shows you:
- The exact prompt sent
- The retrieved context
- The LLM response
- Token usage and cost
- Latency

```bash
pip install langfuse
```

```python
# In config.py
langfuse_public_key: str = ""
langfuse_secret_key: str = ""
langfuse_host: str = "https://cloud.langfuse.com"  # or self-hosted

# In llm_factory.py
from langfuse.callback import CallbackHandler

def get_langfuse_handler():
    if not settings.langfuse_public_key:
        return None
    return CallbackHandler(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )

# Then in your LLM call:
handler = get_langfuse_handler()
config = {"callbacks": [handler]} if handler else {}
response = await llm.ainvoke(messages, config=config)
```

Now every LLM call shows up in your Langfuse dashboard.

## 9.10 Quick Recap

In this part you learned:
- Test setup with pytest (unit + API tests)
- Structured logging with structlog
- Custom exceptions + global handlers
- Rate limiting with slowapi
- CORS done right
- LLM observability with Langfuse

In Part 10 we put it all in Docker and set up CI/CD with GitHub Actions.

---
