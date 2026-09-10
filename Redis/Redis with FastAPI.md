# Redis + FastAPI: The Complete Beginner's Guide

Great choice! Let's build this up step by step, from "how do I even connect?" to "how do professionals structure this in production." I'll explain each approach, why it exists, and what problems the older approaches had.

---

## 1. What Problem Are We Even Solving?

Before code, understand *why* Redis is used with FastAPI:

- **Caching**: Your endpoint hits a database doing a slow query. Redis stores the result so the next request is instant.
- **Rate limiting**: "Allow only 100 requests per minute per user."
- **Sessions**: Store login state without a database hit.
- **Background jobs / queues**: Hand work off to workers (Celery, RQ, arq).
- **Pub/Sub**: Real-time features like chat or live notifications.

The core idea: Redis is an **in-memory** data store — it's fast (microseconds) because data lives in RAM, not on disk.

---

## 2. The Async Client (`redis-py` with asyncio)

### First, a quick story: why the modern client matters

There are actually **two generations** of Redis clients for Python:

**Generation 1: `redis` (the classic client)** — synchronous. This is a problem in FastAPI because:

```python
# ❌ BAD: This BLOCKS the event loop
@app.get("/user/{user_id}")
def get_user(user_id: int):
    data = redis_client.get(f"user:{user_id}")  # Blocks! Event loop frozen.
    ...
```

When a synchronous client runs in an async framework, the entire event loop freezes until Redis responds. Your server can't handle any other request during that time — a disaster under load.

**Generation 2: `redis.asyncio`** — a native async client introduced in `redis-py` v4.2+. Every operation is a coroutine, so while Redis is being queried, the event loop can serve thousands of other requests.

### Setup

```bash
pip install redis fastapi uvicorn
```

If you have Docker, start Redis locally:

```bash
docker run --name myredis -p 6379:6379 -d redis:7
```

### Basic async usage

```python
import redis.asyncio as redis

async def main():
    r = redis.Redis(host="localhost", port=6379, decode_responses=True)
    await r.set("name", "Alice")
    value = await r.get("name")  # "Alice"
    await r.close()
```

Two things to notice:

1. **`decode_responses=True`** — Redis stores raw bytes by default. With this flag, you get Python `str` back instead of `b"Alice"`. This saves you from writing `.decode()` everywhere (the old manual approach, which was error-prone and ugly).
2. **Everything is awaited** — `await r.set(...)`, `await r.get(...)`.

### ⚠️ Important: don't create a client per request

```python
# ❌ BAD: New TCP connection every request = slow
@app.get("/")
async def endpoint():
    r = redis.Redis()
    ...
```

Creating a Redis connection involves a TCP handshake + optional AUTH. Doing this hundreds of times per second is wasteful. This leads us to the next topic...

---

## 3. Lifespan Management (Modern approach)

### The old way: `@app.on_event("startup")` / `("shutdown")`

```python
# ❌ DEPRECATED approach (still works, but discouraged)
@app.on_event("startup")
async def startup():
    app.state.redis = redis.Redis(...)

@app.on_event("shutdown")
async def shutdown():
    await app.state.redis.close()
```

**Why was this replaced?** The `on_event` system had problems:
- Multiple handlers could fire in **non-deterministic order**.
- No clean error propagation — if startup failed, the app might hang.
- It couldn't guarantee **async cleanup** ran properly.
- It was officially **deprecated** in favor of lifespan.

### The new way: `lifespan` context manager

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
import redis.asyncio as redis

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ===== STARTUP =====
    # Create ONE client, reuse it for the whole app's life
    app.state.redis = redis.Redis(
        host="localhost",
        port=6379,
        decode_responses=True,
    )
    # Ping to fail fast if Redis is down (better than discovering at request time)
    await app.state.redis.ping()
    yield  # <-- The app runs here
    # ===== SHUTDOWN =====
    await app.state.redis.aclose()  # Gracefully close connections

app = FastAPI(lifespan=lifespan)
```

**Why is this better?**

1. **Deterministic order** — setup → app runs → cleanup, always in that order, guaranteed.
2. **Fail fast** — `ping()` at startup means your app refuses to start if Redis is down, instead of throwing errors at users.
3. **Guaranteed cleanup** — even if the app crashes, the `aclose()` after `yield` runs (as long as shutdown is signaled), preventing connection leaks.
4. **One client, many requests** — the client holds a **connection pool** internally, so all requests share TCP connections.

> 💡 Note: `aclose()` is the modern method (added in redis-py 5). Older code uses `close()`, which still works but `aclose()` is the explicit async version.

---

## 4. Dependency Injection — The Clean Way to Share Redis

### The naive way: `request.app.state.redis`

```python
# ❌ Works, but tightly couples your route to app internals
@app.get("/users/{user_id}")
async def get_user(request: Request, user_id: int):
    r = request.app.state.redis
    ...
```

Problems:
- Your route "knows" about `app.state` — if you restructure the app, everything breaks.
- Hard to test — you can't easily swap in a mock Redis.
- No type hints for the editor.

### The better way: `Depends`

```python
from typing import Annotated
from fastapi import Depends, FastAPI, Request
import redis.asyncio as redis

# A small dependency function
async def get_redis(request: Request) -> redis.Redis:
    return request.app.state.redis

RedisDep = Annotated[redis.Redis, Depends(get_redis)]

@app.get("/users/{user_id}")
async def get_user(user_id: int, r: RedisDep):
    cached = await r.get(f"user:{user_id}")
    ...
```

**Why is this better?**

1. **Testability** — in tests, override the dependency:
```python
app.dependency_overrides[get_redis] = lambda: fake_redis
```
Now your tests never touch a real Redis.

2. **Loose coupling** — routes only ask for "something that behaves like a Redis client." If tomorrow you switch providers or add wrappers, only `get_redis` changes.

3. **Self-documenting** — the function signature `r: RedisDep` tells readers and IDEs exactly what's available.

### An even cleaner pattern: custom `Request` subclass

```python
class RedisRequest(Request):
    @property
    def redis(self) -> redis.Redis:
        return self.app.state.redis

@app.get("/users/{user_id}")
async def get_user(request: RedisRequest, user_id: int):
    cached = await request.redis.get(f"user:{user_id}")
```

This is a nice middle ground — no `Depends` boilerplate, still explicit.

---

## 5. The JSON Helper (and Its Limits)

Redis values are strings/bytes. So how do you store a Python dict?

### The manual (old) way: `json.dumps` everywhere

```python
# ❌ Verbose, repetitive, error-prone
import json

data = {"name": "Alice", "age": 30}
await r.set("user:1", json.dumps(data))
raw = await r.get("user:1")
user = json.loads(raw) if raw else None
```

Problems:
- Repetitive serialization code scattered across your app.
- If you forget `json.loads` and store a raw string, everything breaks confusingly.
- No type safety — `json.loads` returns plain dicts.

### The better way: built-in JSON commands

Since Redis 6.2 and redis-py 4+, there's native JSON support (RedisJSON module):

```python
# Store a dict directly — the client handles serialization
await r.json().set("user:1", "$", {"name": "Alice", "age": 30})

# Get it back — already a Python dict
user = await r.json().get("user:1")

# Partial updates and queries — impossible with plain strings!
await r.json().set("user:1", "$.age", 31)          # Update just the age
names = await r.json().get("users", "$[*].name")    # Query across an array
```

**Why this is better:**

| Feature | Plain strings (`json.dumps`) | `r.json()` |
|---|---|---|
| Whole-object store/get | ✅ manual | ✅ built-in |
| Update one field | ❌ fetch → modify → rewrite | ✅ one command |
| Query nested data | ❌ | ✅ JSONPath |
| Atomic operations | risky | ✅ single command = atomic |

However, there's a **trade-off**: `r.json()` requires the RedisJSON module (available in Redis Stack, or `redis/redis-stack` Docker image; not in plain `redis` image). For simple caching, plain strings with `json.dumps` are still perfectly fine.

---

## 6. Pydantic Serialization — Type-Safe Redis

The JSON helper gives you dicts. But dicts are dumb — they don't validate. Enter Pydantic.

### The problem with dicts

```python
user = {"name": "Alice", "age": "30"}  # age is a string! Nothing catches this.
```

### The solution: models as the single source of truth

```python
from pydantic import BaseModel

class User(BaseModel):
    id: int
    name: str
    age: int

# ---- Writing to Redis ----
async def cache_user(r: RedisDep, user: User):
    # model_dump(mode="json") converts to a JSON-safe dict
    # (handles datetime, UUID, enums automatically — json.dumps alone would fail)
    await r.set(f"user:{user.id}", user.model_dump_json())

# ---- Reading from Redis ----
async def get_user(r: RedisDep, user_id: int) -> User | None:
    raw = await r.get(f"user:{user.id}")
    if raw is None:
        return None
    return User.model_validate_json(raw)  # Validates! Raises if data is corrupt
```

**Why this approach wins:**

1. **Validation on read** — if the cached data is corrupted or schema drifted, `model_validate_json` raises a clear error instead of silently giving you garbage.
2. **Handles tricky types** — `datetime`, `UUID`, `Decimal` — `model_dump(mode="json")`/`model_dump_json()` serialize them properly. Raw `json.dumps` would throw `TypeError`.
3. **One schema for everything** — your API responses (`response_model=User`), your database layer, and your cache all use the same Pydantic model. Change the model once, everything stays consistent.

### Pydantic v1 vs v2 (important!)

| Pydantic v1 (old) | Pydantic v2 (new, 2023+) |
|---|---|
| `user.json()` | `user.model_dump_json()` |
| `User.parse_raw(raw)` | `User.model_validate_json(raw)` |
| `user.dict()` | `user.model_dump()` |

v2 is 5–50x faster (rewritten in Rust). Modern FastAPI uses v2, and you'll see both in old tutorials — now you know why.

### Complete working cache pattern

```python
@app.get("/users/{user_id}", response_model=User)
async def get_user(user_id: int, r: RedisDep, db: DbDep):
    # 1. Check cache
    if raw := await r.get(f"user:{user_id}"):
        return User.model_validate_json(raw)  # cache HIT — fast path

    # 2. Cache MISS — hit the database
    user = await db.fetch_user(user_id)
    if not user:
        raise HTTPException(404)

    # 3. Store in cache with expiry (1 hour) — prevents stale data forever
    await r.set(f"user:{user_id}", user.model_dump_json(), ex=3600)
    return user
```

Key detail: **`ex=3600`** sets a TTL (time-to-live). Without TTLs, your cache grows forever and serves stale data indefinitely. **Always set an expiry on cache entries.**

---

## 7. `fastapi-cache2` — Declarative Caching

### Why does this exist?

The manual pattern above (check cache → query DB → store cache) works, but you repeat it in *every* endpoint. `fastapi-cache2` wraps it in a **decorator**.

### Setup

```bash
pip install fastapi-cache2[redis]
```

### Usage

```python
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from fastapi_cache.decorator import cache
from fastapi_cache.coder import PickleCoder

@asynccontextmanager
async def lifespan(app: FastAPI):
    r = redis.from_url("redis://localhost:6379", decode_responses=False)
    # ⚠️ Note: fastapi-cache2 needs BYTES (decode_responses=False)
    # because it may store pickled objects
    FastAPICache.init(RedisBackend(r), prefix="myapi-cache")
    app.state.redis = r
    yield
    await r.aclose()

app = FastAPI(lifespan=lifespan)

@app.get("/products")
@cache(expire=60)  # ← That's it. Cached for 60 seconds.
async def list_products():
    return await expensive_database_query()
```

**Why decorators are nice here:**
- Zero boilerplate in the route body.
- Cache key is auto-generated from the route + query params.
- `expire=60` TTL built in.

### Handling Pydantic responses

By default it uses Pickle, which stores bytes. If you want human-readable JSON in Redis, swap the coder:

```python
@cache(expire=60, coder=JsonCoder)  # stores JSON, easier to debug
async def list_products():
    ...
```

### ⚠️ Honest disadvantages of fastapi-cache2 (so you know when NOT to use it)

1. **Less control** — cache keys are auto-generated; fine-tuning eviction per-key is awkward.
2. **Two Redis clients dilemma** — it wants `decode_responses=False`, but your hand-written code often wants `decode_responses=True`. Many projects keep *two* clients, or just use one client with `decode_responses=False` and handle decoding manually.
3. **Staleness on writes** — if you update a product in the DB, the cached version is stale until TTL expires. You must manually invalidate: `await FastAPICache.clear(namespace="...")` or use the lower-level backend API. Manual patterns give you finer invalidation control (e.g., delete the exact key after a DB write).
4. **Maintenance pace** — the library has had periods of slow maintenance; the manual pattern has zero external dependencies.

**Rule of thumb:** use `@cache` for simple, read-heavy endpoints where slight staleness is acceptable. Use the manual pattern when you need precise invalidation, complex keys, or cache-aside logic with fallbacks.

---

## 8. Connection Pool Tuning

### What is a connection pool?

A connection pool is a set of **pre-opened, reusable** TCP connections to Redis. Instead of "open → use → close" per request, you "borrow → use → return" a connection. It's like a library for connections.

`redis.asyncio.Redis()` **already creates a pool internally by default** (`max_connections=None` — meaning unlimited, which is a subtle danger). Most people don't even realize it's there.

### Why tune it?

Imagine 10,000 concurrent users. With an unlimited pool, your app opens 10,000 connections to Redis. Redis itself can handle it, but:
- Each connection costs memory on both sides (~KBs per connection, plus buffers).
- Your OS runs out of file descriptors.
- Connection churn causes latency spikes.

Tuning = set a **sane ceiling** and a timeout so excess requests **queue briefly** instead of exploding resources.

### The knobs that matter

```python
pool = redis.ConnectionPool(
    host="localhost",
    port=6379,
    max_connections=50,       # Max simultaneous connections
    socket_timeout=5,         # Max seconds to wait for a Redis response
    socket_connect_timeout=2, # Max seconds to establish the TCP connection
    retry_on_timeout=True,    # Retry once on a timeout (transient network blips)
    health_check_interval=30, # Ping idle connections periodically, drop dead ones
)

r = redis.Redis(connection_pool=pool)
```

| Setting | What it prevents | When to care |
|---|---|---|
| `max_connections=50` | Connection explosion | Always, in production |
| `socket_timeout` | Requests hanging forever on a sick Redis | Always |
| `socket_connect_timeout` | Slow TCP handshake blocking startup | High-latency networks |
| `retry_on_timeout` | One-off network blips killing requests | Production |
| `health_check_interval` | Using silently-dead connections | Long-running servers, NAT/firewalls that kill idle connections |

### Async pool gotcha: blocking the loop

In async code, don't use **blocking** pool implementations (like older `redis.BlockingConnectionPool` — it's thread-based). The async client handles concurrency differently: async connections are cheap because while one coroutine awaits Redis, others use the loop.

**Practical starting values** for a typical FastAPI service:
- `max_connections=50` (tune up based on real concurrency; 10–100 per instance is typical)
- `socket_timeout=5`
- `socket_connect_timeout=2`
- Monitor with `redis-cli info clients` or `CLIENT LIST`.

---

## 9. Putting It All Together — A Production-Ready Skeleton

```python
from contextlib import asynccontextmanager
from typing import Annotated
import redis.asyncio as redis
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel

# ---------- Config ----------
REDIS_URL = "redis://localhost:6379/0"

# ---------- Models ----------
class User(BaseModel):
    id: int
    name: str
    age: int

# ---------- Lifespan ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = redis.ConnectionPool.from_url(
        REDIS_URL,
        decode_responses=True,
        max_connections=50,
        socket_timeout=5,
        socket_connect_timeout=2,
        retry_on_timeout=True,
        health_check_interval=30,
    )
    app.state.redis = redis.Redis(connection_pool=pool)
    await app.state.redis.ping()  # fail fast
    print("✅ Redis connected")
    yield
    await app.state.redis.aclose()
    print("🛑 Redis closed")

app = FastAPI(lifespan=lifespan)

# ---------- Dependency ----------
async def get_redis(request: Request) -> redis.Redis:
    return request.app.state.redis

RedisDep = Annotated[redis.Redis, Depends(get_redis)]

# ---------- Routes ----------
@app.get("/users/{user_id}", response_model=User)
async def get_user(user_id: int, r: RedisDep):
    # Cache-aside pattern, fully typed
    if raw := await r.get(f"user:{user_id}"):
        return User.model_validate_json(raw)

    user = await fake_db_lookup(user_id)  # your DB call
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await r.set(f"user:{user_id}", user.model_dump_json(), ex=3600)
    return user

@app.post("/users/{user_id}")
async def update_user(user_id: int, update: User, r: RedisDep):
    await fake_db_update(user_id, update)
    # Invalidate cache on write — prevents stale reads
    await r.delete(f"user:{user_id}")
    return {"status": "updated"}

async def fake_db_lookup(user_id: int) -> User | None:
    return User(id=user_id, name="Alice", age=30) if user_id == 1 else None

async def fake_db_update(user_id: int, user: User):
    pass
```

---

## 10. Summary — "When to Use What and Why"

| Topic | Old approach | Modern approach | Why the new one wins |
|---|---|---|---|
| Client | Sync `redis.Redis` | `redis.asyncio` | Doesn't block FastAPI's event loop |
| Client lifetime | Per-request creation | One client via `lifespan` | Reuses pooled connections; fail-fast at startup |
| App lifecycle | `@app.on_event` | `lifespan` context manager | Deterministic order, guaranteed cleanup, official replacement |
| Sharing client | `request.app.state.redis` | `Depends(get_redis)` | Testable (mock via `dependency_overrides`), loosely coupled |
| Serialization | `json.dumps` everywhere | `r.json()` or `model_dump_json()` | Less boilerplate; partial updates; validation on read |
| Data safety | Plain dicts | Pydantic models | Type checking, corruption detection, consistent schema |
| Endpoint caching | Manual check/store in every route | `@cache` decorator | Zero boilerplate; auto keys/TTL |
| Connections | Default unlimited pool | Tuned `ConnectionPool` | Prevents resource exhaustion; resilience via timeouts/retries |

**Golden rules to remember:**

1. Always use `redis.asyncio` in FastAPI — never the sync client.
2. One client per app, created in `lifespan`, closed on shutdown.
3. Inject via `Depends`, never reach into `app.state` directly in routes.
4. Always set TTLs (`ex=`) on cache entries.
5. Validate what comes out of the cache with Pydantic.
6. Delete/overwrite cache keys when the underlying data changes.
7. Tune the pool and set timeouts — defaults are fine for dev, risky for production.

Want to go deeper next? Good follow-ups would be: **cache invalidation strategies**, **Redis Streams for background jobs**, **rate limiting with Redis**, or **using Redis Pub/Sub with FastAPI WebSockets**. Just tell me which one!
