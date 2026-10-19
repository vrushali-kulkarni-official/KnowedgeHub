Hey! These four pieces are basically the "production hygiene" layer of any FastAPI app. They're not flashy, but they're the difference between an app that runs on your laptop and one that can survive in production. Let me walk through each one.

---

## 1. Structured logging with `structlog`

### The problem first

Regular Python logging looks like this:

```python
print("User42 logged in at 2024-01-15 10:23:00")
```

That's a string. When something breaks in production and you're staring at 10,000 lines of log output, you can't easily do `grep` to find "show me all logins for user 42 in the last hour." You'd have to regex-parse timestamps and ids out of strings. Painful.

**Structured logging** emits each event as key-value data (usually JSON), like:

```json
{"event": "user_login", "user_id": 42, "timestamp": "2024-01-15T10:23:00Z"}
```

Now you can query: "all events where `event=user_login` AND `user_id=42`." Log aggregators like Loki, Datadog, ELK eat this up.

### What `structlog` does

It turns this:

```python
log.info("user_login", user_id=42)
```

Into this JSON:

```json
{"event": "user_login", "user_id": 42, "level": "info", "timestamp": "..."}
```

### Setup

Install via `uv` (you're using uv, so this is the way):
```bash
uv add structlog
```

Then in your app:

```python
# brain/logging_config.py
import structlog
import logging
import sys

def configure_logging():
    # Route stdlib logging through structlog too
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )

    structlog.configure(
        processors=[
            # Adds log level
            structlog.stdlib.add_log_level,
            # Adds timestamp in ISO format
            structlog.processors.TimeStamper(fmt="iso"),
            # Stack info + exception if any
            structlog.processors.StackInfoRenderer(),
            # Final step: turn it into JSON for production,
            # or pretty-print for dev. Pick one:
            structlog.processors.JSONRenderer(),
            # structlog.dev.ConsoleRenderer(),  # <- use during local dev
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

# Get a logger anywhere like this:
log = structlog.get_logger()
```

Then in `main.py` (or wherever you create the app):

```python
from brain.logging_config import configure_logging
configure_logging()  # call once at startup
```

### The killer feature: contextThis is what makes structlog special — you can bind variables that auto-attach to all subsequent log calls:

```python
log = structlog.get_logger().bind(user_id=42, request_id="abc-123")
log.info("login_attempt")
log.info("password_check")
log.warning("invalid_password")
```

All three lines will include `user_id=42, request_id=abc-123` automatically. This is exactly what we need for request-ID propagation later.

### Why `structlog` over `logging` directly?

| | stdlib `logging` | `structlog` |
|---|---|---|
| Default output | Plain strings | Structured (JSON / KV) |
| Context binding | Manual `extra={}` mess | `.bind()` auto-propagates |
| Performance | Slower | Faster (cached, lazy) |
| Production-ready | Needs work | Out of the box |

It's also a common industry choice — you'll see it at companies running Python microservices.

---

## 2. Global exception handlers with a standard error schema

### The problem first

Without a global handler, when something crashes, FastAPI returns something like:

```json
{"detail": "Internal Server Error"}
```

Useless. You don't know what went wrong, the client can't reliably parse it, and your logs have no structure.

### What we want

Every error response should look the same, like:

```json
{
  "error_code": "USER_NOT_FOUND",
  "message": "User with id 42 does not exist",
  "request_id": "abc-123",
  "details": null
}
```

Now clients know exactly what fields they'll get. You can document it. You can version it.

### The code

```python
# brain/errors.py
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import structlog

log = structlog.get_logger()

class ErrorResponse(BaseModel):
    error_code: str
    message: str
    request_id: str | None = None
    details: dict | None = None

def register_exception_handlers(app: FastAPI):
    
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        # exc.status_code + exc.detail come from raise HTTPException(...)
        log.warning(
            "http_exception",
            status_code=exc.status_code,
            path=request.url.path,
            detail=exc.detail,
 )
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error_code=f"HTTP_{exc.status_code}",
                message=str(exc.detail),
                request_id=getattr(request.state, "request_id", None),
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # Catches everything else — this is your safety net
        log.error(
            "unhandled_exception",
            path=request.url.path,
            error_type=type(exc).__name__,
            error_message=str(exc),
            exc_info=True,  # includes full traceback
        )
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error_code="INTERNAL_SERVER_ERROR",
                message="Something went wrong on our end",
                request_id=getattr(request.state, "request_id", None),
            ).model_dump(),
        )
```

Notice I'm reading `request.state.request_id` — that's set by the middleware in section 3. That's why these pieces are taught together.

### Why this matters

- **Predictability**: clients (your Streamlit GUI, or external API consumers) can `try/except` against one schema
- **Debuggability**: every error has a `request_id` linking back to logs
- **No leaked stack traces**: the 500 response hides implementation details but your server logs still have them

---

## 3. Request-ID middleware (propagate to logs)

### The concept

Every incoming request gets a unique ID (UUID). That ID is:
1. Attached to the response headers (so users can quote it when reporting issues)
2. Stored on `request.state` (so other middlewares/handlers can read it)
3. Bound to the structlog context (so every log line for this request auto-includes it)

This is THE standard pattern in production APIs. You'll see `X-Request-ID` headers everywhere.

### The code

```python
# brain/middleware.py
import uuid
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

log = structlog.get_logger()

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Honor an incoming X-Request-ID if the upstream (e.g. a load balancer)
        # already set one. Otherwise generate a new one.
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Make it available everywhere in this request's lifecycle
        request.state.request_id = request_id

        # Bind to structlog so EVERY log line in this request includes request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)

        # Echo it back so the client can see it
        response.headers["X-Request-ID"] = request_id
        return response
```

### A subtle detail: `contextvars`

Why `structlog.contextvars.bind_contextvars(...)` instead of `.bind(...)`?

- `.bind()` returns a new logger. You'd have to pass it around everywhere.
- `contextvars` uses Python's built-in context-local storage. It works across `async` boundaries automatically — even if your handler calls another async function, the context travels with it.

This is the magic that makes request-scoped logging actually work in async code.

---

## 4. Request logging middleware

### What it does

Logs one line per request when it finishes, summarizing:
- method, path, status code
- how long it took
- client IP
- request ID (auto-included because we bound it in section 3)

### The code

```python
# brain/middleware.py (append)
import time

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start) * 1000

        log.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
            client_ip=request.client.host if request.client else None,
            # request_id is auto-included thanks to contextvars!
        )

        # Also expose duration via header (handy for debugging)
        response.headers["X-Response-Time-ms"] = f"{duration_ms:.2f}"
        return response
```

### Why this is gold

Now your logs look like:

```json
{"event": "request_completed", "method": "POST", "path": "/chat", "status_code": 200, "duration_ms": 1234.56, "request_id": "abc-123", "timestamp": "..."}
{"event": "user_login", "user_id": 42, "request_id": "abc-123", "timestamp": "..."}
```

Filter by `request_id=abc-123` and you get the entire trace of that one request across all your log lines. That's how you debug "what happened during request X."

---

## Putting it all together

Wire it up in `main.py`:

```python
from fastapi import FastAPI
from brain.middleware import RequestIDMiddleware, RequestLoggingMiddleware
from brain.errors import register_exception_handlers
from brain.logging_config import configure_logging

configure_logging()
app = FastAPI()

# Order matters! RequestID MUST come first so the request_id exists
# before RequestLogging tries to log anything.
app.add_middleware(RequestIDMiddleware)
app.add_middleware(RequestLoggingMiddleware)

register_exception_handlers(app)

@app.get("/health")
async def health():
    log = structlog.get_logger()
    log.info("health_check")  # automatically gets request_id!
    return {"status": "ok"}
```

### Why this middleware order?

Middleware runs in **reverse order of registration** for the request, and **forward order** for the response. So if you register RequestID first then RequestLogging:

- Request comes in → RequestLogging runs first → RequestID runs → handler → RequestID finishes → RequestLogging finishes → response goes out.

Hmm, that's actually the opposite of what you want. Let me correct that — register RequestID **last** so it runs **first** on the way in:

```python
app.add_middleware(RequestLoggingMiddleware)  # outermost
app.add_middleware(RequestIDMiddleware)        # innermost — runs first
```

Actually wait, let me double check this... in Starlette/FastAPI, middlewares added later wrap the earlier ones. So `add_middleware(B)` then `add_middleware(A)` means A is the outermost. The outermost sees the request first.

You want RequestID to set the context *before* RequestLogging tries to log, so RequestID should be **outermost** = add it **last**. Stick with the second version above. (Classic gotcha — every FastAPI dev hits this once.)

---

## TL;DR — what each piece buys you

| Concept | What it gives you |
|---|---|
| `structlog` | Logs as JSON, machine-parseable, fast |
| Global exception handlers | One error schema clients can rely on |
| Request-ID middleware | Trace any single request across all logs |
| Request logging middleware | One log line per request with timing + status |

They're small code, huge production value. Want me to drop these into your actual `brain/` folder structure and wire them into your existing app? I can match your folder layout (`brain/engine.py`, services, etc.) and make sure it slots in cleanly.
