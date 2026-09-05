# Redis Mastery for AI SaaS — The Complete Guide

A beginner-to-advanced guide covering every Redis pattern your AI SaaS needs. Built around the stack: **Python · FastAPI · Postgres · MongoDB · Qdrant · LangChain · LangGraph · Deep Agents · Redis · Docker Compose · GitHub Actions · GHCR · WatchTower · Ubuntu 26 · Cloudflare**.

> All libraries recommended here are **free, open source, industry-standard** and battle-tested.

---

## Table of Contents

- **Module 1** — Redis Fundamentals (what it is, install, connect)
- **Module 2** — Data Types (pick the right structure)
- **Module 3** — Redis as a Cache (cache-aside, TTL, stampede prevention)
- **Module 4** — Sessions & Token Management
- **Module 5** — Redis as a Queue (Lists, Pub/Sub, Streams, Celery, RQ)
- **Module 6** — Rate Limiting & Brute Force Protection
- **Module 7** — Distributed Locks (Redlock)
- **Module 8** — Production Hardening (persistence, replication, Sentinel, Cluster)
- **Module 9** — FastAPI Integration (async, pooling, dependency injection)
- **Module 10** — Security Deep Dive (TLS, ACLs, network isolation, secrets)
- **Module 11** — Observability (Redis Insight, Prometheus, SLOWLOG)
- **Module 12** — Capstone: Wire it all into your AI SaaS

---

# Module 1: Fundamentals

## What is Redis?

**RE**mote **DI**ctionary **S**erver. An in-memory data structure server.

| Store | Mental model | Speed |
|---|---|---|
| File on disk | Filing cabinet | Slow |
| PostgreSQL | SQL spreadsheet | Medium |
| MongoDB | JSON folders | Medium |
| **Redis** | **RAM scratchpad** | **Microseconds** |

Redis keeps data **in RAM** (RAM is ~100,000x faster than SSD). It does persist to disk for durability, but the primary store is memory.

## Why your AI SaaS needs Redis

In your stack, Redis will do at least 6 jobs:

1. **Cache expensive LLM responses** — same question asked twice → return cached answer, no Gemini call
2. **Cache embeddings** — same text → same vector, no re-embedding cost
3. **Session store** — logged-in users, JWT refresh tokens
4. **Rate limiter** — protect your Gemini free tier
5. **Job queue** — 50 PDFs uploaded → 50 background ingestion jobs
6. **Distributed locks** — prevent duplicate work across workers

## Install via Docker Compose

Add to your `docker-compose.yml`:

```yaml
services:
  redis:
    image: redis:7.4-alpine
    container_name: yourapp_redis
    restart: unless-stopped
    command: >
      redis-server
      --requirepass ${REDIS_PASSWORD}
      --maxmemory 256mb
      --maxmemory-policy allkeys-lru
      --appendonly yes
      --appendfsync everysec
    volumes:
      - redis_data:/data
    networks:
      - app_network
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    # NO `ports:` — Redis stays on internal network only

volumes:
  redis_data:
    name: yourapp_redis_data

networks:
  app_network:
    driver: bridge
```

**What each line does (recap):**

- `image: redis:7.4-alpine` — official Redis, tiny Alpine base (~13MB)
- `restart: unless-stopped` — auto-restart on crash/reboot
- `--requirepass` — **password required**, no anonymous access
- `--maxmemory 256mb` — cap RAM; without this a bug can OOM your server
- `--maxmemory-policy allkeys-lru` — when full, evict least-recently-used keys
- `--appendonly yes` + `--appendfsync everysec` — AOF persistence, flush every 1s (lose at most 1s of data on crash)
- `volumes: redis_data` — data survives container recreation
- `healthcheck` — Docker marks it healthy only when Redis responds to PING

Add to `.env`:

```bash
REDIS_PASSWORD=<output of: openssl rand -base64 32>
```

Test it:

```bash
docker compose up -d redis
docker compose exec redis redis-cli -a "$REDIS_PASSWORD" ping
# → PONG
```

## Python client

```bash
pip install "redis[hiredis]>=5.0"
```

`redis[hiredis]` = official Python client + C parser (faster). v5+ has `redis.asyncio` for async FastAPI.

```python
# test_redis.py
import redis
r = redis.Redis(host="localhost", port=6379, password="...", decode_responses=True)
r.set("hello", "world")
print(r.get("hello"))  # → world
```

## Security ground rules (we follow these from Day 1)

1. Always set `--requirepass`
2. Never expose Redis to the public internet
3. Always set `--maxmemory`
4. Always enable AOF persistence
5. Always use healthchecks

---

# Module 2: Data Types

Redis isn't just a key-value store. It has 8+ data types, each optimized for different use cases. **Picking the right type is half the battle.**

## 2.1 Strings

The simplest type. A key holding a value (text, number, JSON, binary).

```python
r.set("user:42:name", "Alice")
print(r.get("user:42:name"))  # → Alice

# Atomic counter (super useful)
r.set("page:views", 0)
r.incr("page:views")       # → 1
r.incrby("page:views", 10) # → 11
r.decr("page:views")       # → 10

# TTL — automatic expiration
r.set("otp:alice@example.com", "482910", ex=300)  # expires in 300s
```

**When to use:** caching simple values, counters, locks, single-token storage (OTP, JWT), flags.

**Key naming convention:** `service:entity:id:field` — e.g. `cache:user:42:profile`.

## 2.2 Hashes

A field-value map under one key. Think of it like a row in a table, but in RAM.

```python
r.hset("user:42", mapping={
    "name": "Alice",
    "email": "alice@example.com",
    "plan": "pro",
    "credits": 1000
})

print(r.hget("user:42", "name"))  # → Alice
print(r.hgetall("user:42"))       # → full dict
r.hincrby("user:42", "credits", -100)  # atomic decrement
r.hdel("user:42", "plan")
```

**When to use:** storing objects with multiple fields, when you need partial updates. **More memory-efficient than JSON strings** for many small fields.

## 2.3 Lists

Ordered sequences of strings. Doubly-linked-list under the hood.

```python
# Stack (LIFO)
r.lpush("recent:searches", "redis tutorial")
r.lpush("recent:searches", "fastapi cache")
print(r.lrange("recent:searches", 0, 4))  # latest 5

# Queue (FIFO)
r.rpush("task:queue", "embed_doc_123")
r.rpush("task:queue", "embed_doc_124")

# Blocking pop — wait for work
task = r.blpop("task:queue", timeout=5)  # waits up to 5s
```

**When to use:** activity feeds, recent items, simple queues, pub-sub-lite. **Don't use for large lists** (millions of items) — use Streams instead.

## 2.4 Sets

Unordered collection of unique strings. Set operations (union, intersection, diff) are O(N).

```python
# Track who's seen what
r.sadd("doc:42:viewers", "user:1", "user:2", "user:3")
print(r.scard("doc:42:viewers"))  # → 3
print(r.sismember("doc:42:viewers", "user:1"))  # → True

# Find common interests between two users
r.sadd("user:1:tags", "python", "redis", "ai")
r.sadd("user:2:tags", "redis", "javascript", "ai")
common = r.sinter("user:1:tags", "user:2:tags")  # → {redis, ai}
```

**When to use:** tags, unique visitors, deduplication, social graphs (followers), lottery.

## 2.5 Sorted Sets (ZSets)

Set + score. Sorted by score. **Most versatile type.**

```python
# Leaderboard
r.zadd("game:leaderboard", {"alice": 1500, "bob": 1800, "carol": 1200})
top3 = r.zrevrange("game:leaderboard", 0, 2, withscores=True)
# → [('bob', 1800.0), ('alice', 1500.0), ('carol', 1200.0)]

# Time-series: use timestamp as score
import time
now = time.time()
r.zadd("metrics:api_latency", {f"req:{now}": 0.123, f"req:{now+0.001}": 0.456})
# Get last 100 measurements
recent = r.zrange("metrics:api_latency", -100, -1, withscores=True)

# Rate limiter (we'll use this in Module 6)
# Sliding window with ZSET — store each request as a (timestamp, uuid) member
```

**When to use:** leaderboards, time-series, sliding-window rate limiters, priority queues, delayed tasks.

## 2.6 Streams (Redis 5+)

Append-only log. **Like Kafka-lite built into Redis.** Most powerful type for queues.

```python
# Producer
stream_id = r.xadd("events:user_signup", {
    "user_id": "42",
    "email": "alice@example.com",
    "plan": "pro"
})
# → "1693912345678-0"

# Consumer reads
events = r.xrange("events:user_signup", count=10)

# Consumer group (like Kafka consumer groups — for distributed workers)
try:
    r.xgroup_create("events:user_signup", "worker-group-1", id="0")
except redis.ResponseError:
    pass  # group already exists

# Workers pull new messages
messages = r.xreadgroup(
    "worker-group-1",
    "worker-1",
    streams={"events:user_signup": ">"},
    count=10,
    block=5000  # wait up to 5s for new messages
)
for stream, entries in messages:
    for msg_id, data in entries:
        print(f"Processing {msg_id}: {data}")
        r.xack("events:user_signup", "worker-group-1", msg_id)
```

**When to use:** event sourcing, durable queues, audit logs, **anything you used to do with RabbitMQ/Kafka for small-to-medium volume**.

## 2.7 Bitmaps

Bit operations on strings. Niche but amazing for specific things.

```python
# Daily active users — 1 bit per user per day
# 100M users = 12.5MB of memory
import datetime
day = "2026-09-05"
r.setbit(f"active:{day}", 42, 1)   # user 42 was active
r.setbit(f"active:{day}", 100, 1)  # user 100 was active

# Count active users that day
count = r.bitcount(f"active:{day}")  # → 2

# DAU over a week
week_dau = r.bitop("OR", "active:week",
                    "active:2026-09-01",
                    "active:2026-09-02",
                    "active:2026-09-03")
```

**When to use:** DAU/MAU tracking, feature flags per user, bloom-filter-like use cases.

## 2.8 HyperLogLog

Probabilistic cardinality counter. ~0.81% error. **12KB fixed memory regardless of cardinality.**

```python
# Count unique visitors across 10 million page views, using only 12KB
for user_id in range(10_000_000):
    r.pfadd("unique:visitors:today", f"user:{user_id}")

count = r.pfcount("unique:visitors:today")  # ~10,000,000 (±0.81%)
```

**When to use:** "how many unique X", when exactness doesn't matter.

## 2.9 Quick decision table

| Use case | Type |
|---|---|
| Cache a JSON blob | String |
| User profile with 5+ fields | Hash |
| Recent N search history | List |
| Unique tags, dedup | Set |
| Leaderboard, rate limit, time-series | Sorted Set |
| Durable event log, distributed queue | Stream |
| Daily active users, feature flags | Bitmap |
| Unique counter with tiny memory | HyperLogLog |

---

# Module 3: Redis as a Cache

Caching is **the** most common Redis use case. Done wrong, it's a source of stale data and stampedes. Done right, it's a 10–100x speedup.

## 3.1 The 4 cache patterns

| Pattern | When to use | Complexity |
|---|---|---|
| **Cache-Aside** (lazy) | Most apps. Read-heavy. | Simple |
| Read-Through | App doesn't manage cache directly | Medium |
| Write-Through | Need strong consistency | Medium |
| Write-Behind | Tolerate eventual consistency | Complex |

**For your AI SaaS, use Cache-Aside 90% of the time.** I'll focus on that.

## 3.2 Cache-Aside pattern

```python
async def get_user_profile(user_id: int) -> dict:
    cache_key = f"cache:user:{user_id}:profile"
    
    # 1. Try cache first
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)
    
    # 2. Cache miss → query DB
    user = await db.fetch_user(user_id)
    if not user:
        return None
    
    # 3. Store in cache for next time (TTL = 1 hour)
    await redis.set(cache_key, json.dumps(user), ex=3600)
    return user
```

**Flow:** App asks cache. If hit → return. If miss → read DB → populate cache → return.

## 3.3 Invalidation: the two hard problems

There are only two hard things in Computer Science: cache invalidation and naming things. — Phil Karlton

**The 3 invalidation strategies:**

### a) TTL only (simplest)

```python
await redis.set(key, value, ex=3600)  # expires in 1 hour
```

Good for: data that can be stale for up to TTL. User profile, config, LLM responses (with version).

### b) TTL + explicit invalidation on write

```python
async def update_user(user_id: int, new_data: dict):
    await db.update_user(user_id, new_data)
    # Invalidate cache so next read pulls fresh data
    await redis.delete(f"cache:user:{user_id}:profile")
```

Good for: user-generated data. Posts, profiles, settings.

### c) Event-based invalidation (Pub/Sub)

One service updates → broadcasts "key X changed" → all other services invalidate.

**For your SaaS, use (b).** Simple, correct, sufficient.

## 3.4 Cache stampede prevention

**The problem:** Cache key expires. 1000 requests hit at once. All 1000 miss the cache. All 1000 hit the DB. **Your DB dies.**

### Solution 1: Mutex (lock during rebuild)

```python
async def get_user_profile(user_id: int) -> dict:
    cache_key = f"cache:user:{user_id}:profile"
    lock_key = f"lock:user:{user_id}:profile"
    
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)
    
    # Try to acquire rebuild lock
    got_lock = await redis.set(lock_key, "1", nx=True, ex=10)
    
    if got_lock:
        try:
            # We won the race → rebuild cache
            user = await db.fetch_user(user_id)
            await redis.set(cache_key, json.dumps(user), ex=3600)
            return user
        finally:
            await redis.delete(lock_key)
    else:
        # Another worker is rebuilding — wait briefly then retry cache
        await asyncio.sleep(0.1)
        return await get_user_profile(user_id)  # recursive retry
```

### Solution 2: Stale-While-Revalidate (industry standard)

```python
async def get_with_swr(key: str, loader, ttl: int = 3600, stale_ttl: int = 86400):
    """
    ttl: fresh for this long
    stale_ttl: serve stale while reloading, up to this long
    """
    entry = await redis.get(key)
    if entry:
        data, expires_at = json.loads(entry)
        if time.time() < expires_at:
            return data  # fresh
        # stale but still served
        asyncio.create_task(_refresh(key, loader, ttl))
        return data
    # completely missing → load synchronously
    return await _refresh(key, loader, ttl)

async def _refresh(key, loader, ttl):
    data = await loader()
    payload = json.dumps([data, time.time() + ttl])
    await redis.set(key, payload, ex=ttl + stale_ttl)
    return data
```

## 3.5 Key naming for cache

Use a **prefix convention** so you can bulk-invalidate:

```
cache:user:{id}:profile        # → del cache:user:*:profile to nuke all profiles
cache:llm:response:{hash}      # cache LLM responses by question hash
cache:embed:{text_hash}        # cache embeddings
cache:doc:{id}:metadata
```

This pattern makes ops work later (debugging, manual flush) much easier.

## 3.6 LLM response caching — your secret weapon

For an AI SaaS on Gemini free tier, this saves real money:

```python
import hashlib

def question_hash(question: str, model: str, temperature: float) -> str:
    """Deterministic hash of (question + model config)."""
    payload = f"{model}|{temperature}|{question}"
    return hashlib.sha256(payload.encode()).hexdigest()[:32]

async def chat(question: str, user_id: int) -> str:
    cache_key = f"cache:llm:{question_hash(question, 'gemini-2.5-flash', 0.7)}"
    
    cached = await redis.get(cache_key)
    if cached:
        return cached  # Free!
    
    answer = await call_gemini(question)
    await redis.set(cache_key, answer, ex=86400)  # 24h
    return answer
```

**Caveat:** Only cache when `temperature=0` or when you're OK with same answer for same question. For high-temperature creative use, caching is wrong.

## 3.7 What NOT to cache in Redis

- **Primary data** — Postgres/Mongo are the source of truth. Redis is a hint.
- **Large blobs** — keep individual values under ~1MB. Use S3/Mongo for big files.
- **Anything that must never be stale** — financial transactions, billing.

---

# Module 4: Sessions & Token Management

For your AI SaaS, Redis is the perfect session backend. Fast, TTL-based, perfect for ephemeral auth state.

## 4.1 Session storage pattern (server-side sessions)

```python
import secrets
import json
from datetime import datetime, timedelta

SESSION_TTL = 3600  # 1 hour

async def create_session(user_id: int, metadata: dict = None) -> str:
    """Returns session token (send to client as cookie)."""
    session_id = secrets.token_urlsafe(32)  # cryptographically random
    session_data = {
        "user_id": user_id,
        "created_at": datetime.utcnow().isoformat(),
        "ip": metadata.get("ip") if metadata else None,
        "user_agent": metadata.get("user_agent") if metadata else None,
    }
    await redis.set(
        f"session:{session_id}",
        json.dumps(session_data),
        ex=SESSION_TTL
    )
    return session_id

async def get_session(session_id: str) -> dict | None:
    data = await redis.get(f"session:{session_id}")
    if not data:
        return None
    # Sliding session — extend TTL on access
    await redis.expire(f"session:{session_id}", SESSION_TTL)
    return json.loads(data)

async def destroy_session(session_id: str):
    await redis.delete(f"session:{session_id}")
```

**Why server-side sessions?**

- ✅ Logout everywhere = delete from Redis
- ✅ Revoke compromised sessions instantly
- ✅ Audit who's logged in from where
- ❌ Extra Redis lookup on every request (negligible — sub-ms)

## 4.2 JWT + Redis: refresh token rotation

For stateless APIs, use short-lived JWT access tokens + long-lived refresh tokens stored in Redis.

**Why both?** JWT alone can't be revoked. JWT + Redis blacklist = revocable.

```python
ACCESS_TOKEN_TTL = 900       # 15 min
REFRESH_TOKEN_TTL = 2592000  # 30 days

async def login(user_id: int) -> dict:
    # Short-lived JWT (signed, no DB lookup needed)
    access_token = jwt.encode(
        {"sub": user_id, "exp": datetime.utcnow() + timedelta(seconds=ACCESS_TOKEN_TTL)},
        JWT_SECRET,
        algorithm="HS256"
    )
    
    # Long-lived refresh token, stored in Redis
    refresh_token = secrets.token_urlsafe(64)
    await redis.set(
        f"refresh:{user_id}:{refresh_token[:16]}",  # key by user for easy listing
        json.dumps({
            "user_id": user_id,
            "created_at": datetime.utcnow().isoformat(),
            "user_agent": "..."
        }),
        ex=REFRESH_TOKEN_TTL
    )
    return {"access_token": access_token, "refresh_token": refresh_token}

async def refresh(refresh_token: str) -> str:
    # Look up the refresh token
    # If valid, rotate (delete old, issue new) — this catches stolen tokens
    # Then issue new access token
    ...
```

**Rotation pattern:** every time you use a refresh token, delete it and issue a new one. If an attacker steals a token, the legitimate user's next refresh fails → you know it's compromised.

## 4.3 JWT blacklist (for logout)

```python
async def logout(jwt_payload: dict, token_hash: str):
    """Blacklist a JWT until its natural expiry."""
    remaining = jwt_payload["exp"] - time.time()
    if remaining > 0:
        await redis.set(f"jwt:blacklist:{token_hash}", "1", ex=int(remaining))
```

**On every request:** check the blacklist. Yes, this defeats "stateless" JWTs a bit — but you get real logout. For an AI SaaS, **this is the right trade.**

## 4.4 Cookie security

If using cookies for sessions:

```python
response.set_cookie(
    key="session_id",
    value=session_id,
    max_age=3600,
    httponly=True,      # JS can't read it → XSS can't steal it
    secure=True,        # HTTPS only
    samesite="lax",     # CSRF protection ("strict" breaks OAuth flows)
    path="/",
    domain=".yourapp.com"
)
```

**Always: `httponly=True`, `secure=True`, `samesite="lax"` or `"strict"`.**

---

# Module 5: Redis as a Queue

Your AI SaaS will have async work: PDF ingestion, re-embeddings, email sending, webhooks. Redis queues handle this.

## 5.1 Three flavors

| Flavor | Durability | Use case |
|---|---|---|
| **List + BLPOP** | None (in-memory) | Throwaway tasks, fire-and-forget |
| **Pub/Sub** | None (in-memory) | Real-time notifications, WebSockets |
| **Streams** | **AOF persistence** | **Durable jobs, audit logs, anything that can't be lost** |

**For your SaaS, use Streams 90% of the time.** Pub/Sub for WebSockets, Lists for trivial cases.

## 5.2 Simple queue with List + BLPOP (don't use for important work)

```python
# Producer
await redis.lpush("queue:emails", json.dumps({"to": "user@example.com", "subject": "..."}))

# Consumer (blocks until item available)
while True:
    item = await redis.blpop("queue:emails", timeout=5)
    if item:
        _, payload = item
        await send_email(json.loads(payload))
```

**Problem:** if worker crashes mid-job, message is lost. No retry. No DLQ. Don't use for important work.

## 5.3 Pub/Sub (real-time, no persistence)

```python
# Publisher
await redis.publish("notifications:user:42", json.dumps({"type": "doc_ready"}))

# Subscriber (must be in separate process/connection)
pubsub = redis.pubsub()
await pubsub.subscribe("notifications:user:42")
async for message in pubsub.listen():
    if message["type"] == "message":
        await websocket.send(message["data"])
```

**Use for:** WebSocket fanout, real-time dashboards, in-app notifications. **NOT for job queues** — if no subscriber is connected, message is gone.

## 5.4 Streams — the real queue (Module 2.6, expanded)

**This is what you'll use for background jobs.** Here's the production-grade pattern:

```python
# === PRODUCER ===
async def enqueue_job(job_type: str, payload: dict, priority: str = "default"):
    stream = f"jobs:{priority}"  # jobs:default, jobs:high, jobs:low
    return await redis.xadd(
        stream,
        {
            "type": job_type,
            "payload": json.dumps(payload),
            "enqueued_at": str(time.time()),
            "trace_id": str(uuid.uuid4()),  # for log correlation
        },
        maxlen=100000,  # cap stream size
        approximate=True  # efficient trimming
    )

# === CONSUMER GROUP SETUP (one-time per stream) ===
async def ensure_consumer_group(stream: str, group: str):
    try:
        await redis.xgroup_create(stream, group, id="0", mkstream=True)
    except redis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise

# === WORKER ===
async def worker(worker_id: str, streams: list[str], group: str = "workers"):
    for stream in streams:
        await ensure_consumer_group(stream, group)
    
    while True:
        try:
            messages = await redis.xreadgroup(
                groupname=group,
                consumername=worker_id,
                streams={s: ">" for s in streams},
                count=10,    # batch size
                block=5000,  # wait 5s
            )
            for stream, entries in messages:
                for msg_id, data in entries:
                    try:
                        await process_job(data)
                        await redis.xack(stream, group, msg_id)
                    except Exception as e:
                        # Failed → DON'T ack. Message stays in Pending Entries List.
                        # On next iteration, you'll see it via xreadgroup id="0"
                        # (re-delivery). Build a retry/DLQ policy on top.
                        logger.error(f"Job {msg_id} failed: {e}")
        except Exception as e:
            logger.exception("Worker loop error")
            await asyncio.sleep(1)

async def process_job(data: dict):
    job = json.loads(data["payload"])
    if data["type"] == "ingest_pdf":
        await ingest_pdf(job["doc_id"])
    elif data["type"] == "send_email":
        await send_email(job["to"], job["subject"])
    # ...
```

**Why this is bulletproof:**
- Multiple workers can share the load (consumer group)
- Crashed worker → its messages re-deliver after pending timeout
- Each job is processed at-least-once
- Streams persist to AOF → jobs survive Redis restart

## 5.5 Use Celery for complex workflows (when Streams aren't enough)

For multi-step workflows, scheduled tasks, retries with backoff — use **Celery with Redis as broker**.

```bash
pip install celery[redis]
```

```python
# tasks.py
from celery import Celery

app = Celery(
    "yourapp",
    broker="redis://:password@redis:6379/1",   # db 1 for broker
    backend="redis://:password@redis:6379/2",  # db 2 for results
)

@app.task(bind=True, max_retries=3, autoretry_for=(Exception,), retry_backoff=True)
def ingest_pdf(self, doc_id: int):
    # Heavy work
    ...
```

**When to choose Celery vs raw Streams:**

| Need | Use |
|---|---|
| Fire-and-forget single jobs | Raw Streams |
| Complex retry policies, scheduled tasks | **Celery** |
| DAGs / workflows / chaining | **Celery + LangGraph** |
| Lightweight simple jobs | **RQ** (simpler than Celery) |

**Recommendation for your stack:** Start with raw Streams. Move to Celery when you need scheduled tasks (e.g. nightly re-embed).

## 5.6 RQ — the simpler alternative

`RQ` (Redis Queue) is a much simpler library than Celery. Good for straightforward job queues.

```bash
pip install rq
```

```python
# Enqueue
from rq import Queue
queue = Queue(connection=redis_conn)
job = queue.enqueue(ingest_pdf, doc_id=42, job_timeout="10m")

# Worker (separate process)
# rq worker --url redis://:password@redis:6379/3
```

**RQ vs Celery:** RQ is simpler, less feature-rich. Celery is more powerful but more complex.

---

# Module 6: Rate Limiting & Brute Force Protection

Critical for protecting your Gemini free tier and preventing abuse.

## 6.1 The 4 algorithms

| Algorithm | Precision | Memory | Best for |
|---|---|---|---|
| Fixed window | Coarse | O(1) | Simple per-minute limits |
| Sliding window log | Perfect | O(N) | Strict limits, low traffic |
| Sliding window counter | Good | O(1) | Production standard |
| Token bucket | Good | O(1) | Allow bursts, smooth refill |

**Production pick: Sliding window counter (default) or Token bucket (for bursty APIs).**

## 6.2 Fixed window (simplest)

```python
async def rate_limit_fixed(user_id: int, limit: int, window: int) -> bool:
    """Returns True if allowed, False if rate limited."""
    bucket = int(time.time()) // window
    key = f"rl:{user_id}:{bucket}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window)
    return count <= limit

# Usage: 10 requests per 60 seconds
if not await rate_limit_fixed(user_id, 10, 60):
    raise HTTPException(429, "Too many requests")
```

**Problem:** user can send 10 in last second of one window + 10 in first second of next = 20 in 2 seconds. Not great.

## 6.3 Sliding window counter (production default)

```python
async def rate_limit_sliding(
    user_id: int, 
    limit: int,            # requests per window
    window: int            # window size in seconds
) -> bool:
    now = time.time()
    current_bucket = int(now) // window
    previous_bucket = current_bucket - 1
    
    # How far we are into the current window (0.0 → 1.0)
    elapsed = (now % window) / window
    
    current_key = f"rl:{user_id}:{current_bucket}"
    previous_key = f"rl:{user_id}:{previous_bucket}"
    
    pipe = redis.pipeline()
    pipe.get(current_key)
    pipe.get(previous_key)
    current, previous = await pipe.execute()
    
    current = int(current or 0)
    previous = int(previous or 0)
    
    # Weighted: previous bucket contributes (1 - elapsed) of its count
    weighted = current + previous * (1 - elapsed)
    
    if weighted >= limit:
        return False
    
    # Increment
    pipe = redis.pipeline()
    pipe.incr(current_key)
    pipe.expire(current_key, window * 2)
    await pipe.execute()
    return True
```

## 6.4 Token bucket (allow bursts)

```python
async def rate_limit_token_bucket(
    user_id: int,
    capacity: int,       # bucket size (max burst)
    refill_rate: float   # tokens per second
) -> bool:
    key = f"tb:{user_id}"
    now = time.time()
    
    pipe = redis.pipeline()
    pipe.hgetall(key)
    data = await pipe.execute()
    data = data[0] if data else {}
    
    tokens = float(data.get("tokens", capacity))
    last_refill = float(data.get("last_refill", now))
    
    # Refill bucket based on time elapsed
    tokens = min(capacity, tokens + (now - last_refill) * refill_rate)
    
    if tokens < 1:
        # Not enough tokens
        pipe = redis.pipeline()
        pipe.hset(key, mapping={"tokens": tokens, "last_refill": now})
        pipe.expire(key, 3600)
        await pipe.execute()
        return False
    
    # Consume a token
    tokens -= 1
    pipe = redis.pipeline()
    pipe.hset(key, mapping={"tokens": tokens, "last_refill": now})
    pipe.expire(key, 3600)
    await pipe.execute()
    return True
```

**Use case:** "Free tier gets 10 req/min, but allow bursts of 20."

## 6.5 Use `slowapi` for FastAPI (recommended)

Don't reinvent the wheel. **`slowapi`** is the standard FastAPI rate-limiting library.

```bash
pip install slowapi
```

```python
# main.py
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import FastAPI
from fastapi.responses import JSONResponse

limiter = Limiter(key_func=get_remote_address)  # or your own key (user id from JWT)
app = FastAPI()
app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request, exc):
    return JSONResponse(
        status_code=429,
        content={"error": "rate_limited", "retry_after": exc.detail}
    )

@app.get("/chat")
@limiter.limit("10/minute")  # 10 req/min per IP
async def chat(request: Request, message: str):
    ...
```

**For per-user limits**, use a custom `key_func` that extracts the user ID from the JWT.

## 6.6 Brute force protection (login attempts)

```python
async def check_login_attempts(email: str) -> bool:
    """Lock account after 5 failed attempts in 15 minutes."""
    key = f"login_fail:{email}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 900)  # 15 min
    if count > 5:
        return False  # locked
    return True

async def record_failed_login(email: str):
    await check_login_attempts(email)

async def clear_login_attempts(email: str):
    await redis.delete(f"login_fail:{email}")
```

**Also:** add CAPTCHA after 3 failed attempts. Lock account for 1 hour after 10. This is what AWS/Google do.

---

# Module 7: Distributed Locks

When you have multiple workers, you need to ensure only one does a specific piece of work at a time.

## 7.1 The simple lock (correct version)

```python
import secrets

async def acquire_lock(resource: str, ttl: int = 10) -> str | None:
    """Returns lock token if acquired, None if not."""
    token = secrets.token_urlsafe(16)
    got = await redis.set(f"lock:{resource}", token, nx=True, ex=ttl)
    return token if got else None

async def release_lock(resource: str, token: str) -> bool:
    """Release lock ONLY if we own it (check token)."""
    # Atomic Lua script — prevents releasing someone else's lock
    lua = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """
    result = await redis.eval(lua, 1, f"lock:{resource}", token)
    return result == 1
```

**Why the Lua script?** Without it, your lock could expire, another worker could acquire it, then you delete THEIR lock. Lua makes the get+delete atomic.

## 7.2 Redlock — for when you really need it (probably not)

Single-Redis locks have a problem: if the master goes down before replicating the lock, two workers can think they hold it. Redlock uses **multiple independent Redis nodes** and a quorum.

```bash
pip install redis-lock  # or pottery
```

```python
from redis_lock import Lock

lock = Lock(redis_client, "my-resource", expire=10, auto_renewal=True)
if lock.acquire():
    try:
        # do work
    finally:
        lock.release()
```

**When to use Redlock vs single-node:**
- Single-node: 95% of cases. Job deduplication, cron jobs.
- Redlock: financial transactions, billing, "absolutely must run once" scenarios.

**For your AI SaaS, single-node locks are fine.**

## 7.3 Use `python-redis-lock` (recommended)

```bash
pip install python-redis-lock
```

Handles token generation, atomic release, auto-renewal, blocking. Production-ready.

---

# Module 8: Production Hardening

## 8.1 Persistence: RDB vs AOF

| Type | What | Pros | Cons |
|---|---|---|---|
| **RDB** | Point-in-time snapshots | Compact, fast restart | Can lose minutes of data |
| **AOF** | Log of every write | Lose at most 1s (with everysec) | Larger files, slower restart |

**For your SaaS: enable BOTH.** RDB for backups, AOF for durability.

```yaml
command: >
  redis-server
  --save 900 1            # RDB: if at least 1 key changed in 900s, snapshot
  --save 300 10           # if 10 keys changed in 300s
  --save 60 10000         # if 10000 keys changed in 60s
  --appendonly yes
  --appendfsync everysec
  --appendfilename "appendonly.aof"
  --auto-aof-rewrite-percentage 100
  --auto-aof-rewrite-min-size 64mb
```

## 8.2 Replication: 1 primary + N replicas

```yaml
# Replica service
services:
  redis-replica:
    image: redis:7.4-alpine
    command: redis-server --replicaof redis 6379 --requirepass ${REDIS_PASSWORD} --masterauth ${REDIS_PASSWORD}
    depends_on:
      redis:
        condition: service_healthy
    networks:
      - app_network
```

**Why:** if primary dies, replica can be promoted. **Reads can go to replicas** to scale.

**App-side reads from replica:**

```python
# Two clients
write_redis = redis.Redis(host="redis", port=6379, password=...)
read_redis = redis.Redis(host="redis-replica", port=6379, password=...)

async def get_cached_user(user_id):
    return await read_redis.get(f"cache:user:{user_id}")
```

## 8.3 Sentinel — automatic failover

For production, run **3 Sentinel nodes** that monitor Redis and auto-failover.

```yaml
services:
  redis-sentinel-1:
    image: redis:7.4-alpine
    command: redis-sentinel /etc/redis/sentinel.conf
    volumes:
      - ./sentinel.conf:/etc/redis/sentinel.conf
    networks:
      - app_network
```

`sentinel.conf`:

```
sentinel monitor mymaster redis 6379 2
sentinel down-after-milliseconds mymaster 5000
sentinel parallel-syncs mymaster 1
sentinel failover-timeout mymaster 10000
sentinel auth-pass mymaster ${REDIS_PASSWORD}
```

App-side: use `redis+sentinel://` connection string:

```python
from redis.sentinel import Sentinel
sentinel = Sentinel(
    [("redis-sentinel-1", 26379), ("redis-sentinel-2", 26379), ("redis-sentinel-3", 26379)],
    password=REDIS_PASSWORD
)
master = sentinel.master_for("mymaster")
slave = sentinel.slave_for("mymaster")
```

## 8.4 Cluster — for >25GB or >500K ops/sec

Cluster = auto-sharding across 6+ nodes. Use only when you outgrow Sentinel.

**For your SaaS, single Redis + replicas is plenty until 10K+ active users.**

## 8.5 Backup strategy

```bash
# Cron job: daily RDB dump to S3-compatible storage
docker compose exec redis redis-cli -a "$REDIS_PASSWORD" BGSAVE
docker compose cp redis:/data/dump.rdb /backups/redis-$(date +%F).rdb
# Upload to S3/B2/Backblaze with rclone
```

**Test restores monthly.** A backup you never tested isn't a backup.

## 8.6 Pipelining — 5-10x faster batch ops

```python
# Slow: 1000 round trips
for i in range(1000):
    await redis.set(f"k:{i}", i)

# Fast: 1 round trip
async with redis.pipeline(transaction=False) as pipe:
    for i in range(1000):
        await pipe.set(f"k:{i}", i)
    await pipe.execute()
```

---

# Module 9: FastAPI Integration

## 9.1 The async client

For FastAPI, use `redis.asyncio`. It integrates with your existing `asyncio` event loop.

```python
# redis_client.py
import redis.asyncio as aioredis
from app.config import settings

# Module-level singleton — connection pool reuses connections
redis_client: aioredis.Redis = aioredis.from_url(
    settings.REDIS_URL,  # "redis://:password@redis:6379/0"
    encoding="utf-8",
    decode_responses=True,
    max_connections=50,         # pool size — tune for your load
    socket_connect_timeout=5,
    socket_timeout=5,
    retry_on_timeout=True,
    health_check_interval=30,   # ping every 30s
)
```

## 9.2 Lifespan management

```python
# main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from redis_client import redis_client

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await redis_client.ping()  # verify connection
    yield
    # Shutdown
    await redis_client.aclose()  # close all connections

app = FastAPI(lifespan=lifespan)
```

**Why:** clean startup/shutdown. No leaked connections on restart.

## 9.3 Dependency injection (clean patterns)

```python
from fastapi import Depends
from typing import Annotated

async def get_redis() -> aioredis.Redis:
    yield redis_client

# In a route
@app.get("/me")
async def me(redis: Annotated[aioredis.Redis, Depends(get_redis)], user = Depends(get_current_user)):
    cached = await redis.get(f"user:{user.id}:profile")
    ...
```

## 9.4 JSON helper (you'll use this 1000 times)

```python
import json
from typing import Any

class RedisJSON:
    """Wrapper that handles JSON serialization for you."""
    def __init__(self, redis: aioredis.Redis):
        self.r = redis
    
    async def get_json(self, key: str) -> Any | None:
        data = await self.r.get(key)
        return json.loads(data) if data else None
    
    async def set_json(self, key: str, value: Any, ex: int | None = None):
        await self.r.set(key, json.dumps(value, default=str), ex=ex)
    
    async def get_or_set_json(self, key: str, loader, ex: int = 3600) -> Any:
        cached = await self.get_json(key)
        if cached is not None:
            return cached
        value = await loader()
        await self.set_json(key, value, ex=ex)
        return value
```

## 9.5 Pydantic serialization (production-grade)

```python
from pydantic import BaseModel

class UserProfile(BaseModel):
    id: int
    name: str
    email: str

async def cache_user(user: UserProfile):
    await redis.set(
        f"user:{user.id}:profile",
        user.model_dump_json(),  # pydantic-native serialization
        ex=3600,
    )

async def get_cached_user(user_id: int) -> UserProfile | None:
    data = await redis.get(f"user:{user_id}:profile")
    return UserProfile.model_validate_json(data) if data else None
```

## 9.6 fastapi-cache2 (for endpoint caching)

```bash
pip install fastapi-cache2
```

```python
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from fastapi_cache.decorator import cache

@app.on_event("startup")
async def startup():
    FastAPICache.init(RedisBackend(redis_client), prefix="cache")

@app.get("/docs/{doc_id}")
@cache(expire=300)  # 5 min
async def get_doc(doc_id: int):
    return await db.get_doc(doc_id)
```

## 9.7 Connection pool tuning

| Concurrent users | `max_connections` |
|---|---|
| <100 | 20 |
| 100-1000 | 50 |
| 1000-10000 | 100 |
| >10000 | 200+ (or use Cluster) |

**Rule of thumb:** `max_connections ≈ (expected concurrent requests) × 1.2`

---

# Module 10: Security Deep Dive

**This is the most important module.** AI SaaS = public-facing API = constant attack target.

## 10.1 The 7 layers of Redis security

| Layer | What | Why |
|---|---|---|
| 1. Network isolation | Never expose to internet | Prevent scanning, exploits |
| 2. AUTH (`requirepass`) | Password | Block anonymous access |
| 3. ACLs | Per-user permissions | Limit blast radius |
| 4. TLS | Encrypted transport | Prevent sniffing, MITM |
| 5. Encryption at rest | Encrypted disk/volume | Protect backups |
| 6. Disable admin commands | Rename `FLUSHALL`, `CONFIG` | Prevent sabotage |
| 7. Audit logging | Log who did what | Forensics |

## 10.2 Network isolation

**The single most important rule: NEVER expose Redis to the public internet.**

In your `docker-compose.yml`:

```yaml
services:
  redis:
    # NO `ports:` directive
    # Only accessible from containers on `app_network`
    networks:
      - app_network
```

**Verify with a port scan:** `nmap -p 6379 your-server.com` should return "closed/filtered" from the internet.

## 10.3 AUTH

```bash
# In redis.conf or as command-line arg
--requirepass ${REDIS_PASSWORD}

# Use a STRONG password (32+ random chars)
REDIS_PASSWORD=$(openssl rand -base64 32)
```

**Never:** admin, root, password, your company name, anything from a dictionary.

## 10.4 ACLs (Access Control Lists, Redis 6+)

ACLs let you give different users different permissions. **Use them in production.**

```bash
# Create a read-only user
ACL CREATEUSER readonly_user on ">readonly_password" ~cached:* &* -@all +get +keys

# Create an app user (read+write specific keyspace)
ACL CREATEUSER app_user on ">app_password" ~app:* &* -@all +get +set +del +expire +keys

# Create an admin user (only you)
ACL CREATEUSER admin on ">admin_password" ~* &* +@all

# List users
ACL LIST

# Switch user (in app)
AUTH app_user app_password
```

**Pattern:** your FastAPI uses `app_user` (limited to `app:*` keyspace). Your ops scripts use `admin`. Attackers who compromise your app can't `FLUSHALL` the database.

## 10.5 TLS / SSL

For production, encrypt traffic between your app and Redis. Especially important if Redis is on a different host (not just internal Docker network).

**Generate a cert (use your existing reverse proxy cert, or self-signed for internal):**

```bash
openssl req -x509 -nodes -newkey rsa:2048 \
  -keyout /etc/redis/tls/redis.key \
  -out /etc/redis/tls/redis.crt \
  -days 365 \
  -subj "/CN=redis.internal"
```

**Mount in docker-compose:**

```yaml
services:
  redis:
    command: >
      redis-server
      --tls-port 6380
      --port 0
      --tls-cert-file /etc/redis/tls/redis.crt
      --tls-key-file /etc/redis/tls/redis.key
      --tls-ca-cert-file /etc/redis/tls/ca.crt
      --tls-auth-clients optional
      --requirepass ${REDIS_PASSWORD}
    volumes:
      - ./tls:/etc/redis/tls:ro
```

**Client-side:**

```python
import redis
r = redis.Redis(
    host="redis",
    port=6380,
    password=REDIS_PASSWORD,
    ssl=True,
    ssl_certfile="./tls/client.crt",
    ssl_keyfile="./tls/client.key",
    ssl_ca_certs="./tls/ca.crt",
)
```

## 10.6 Disable dangerous commands

```bash
# Rename dangerous commands to random names so they're unusable
rename-command FLUSHALL ""
rename-command FLUSHDB ""
rename-command CONFIG "x9k2m_config"  # only you know the real name
rename-command DEBUG ""
rename-command SHUTDOWN "x9k2m_shutdown"
```

**Why:** even with AUTH, an attacker who gets in can't `FLUSHALL` your cache or reconfigure your server. Defense in depth.

## 10.7 Encryption at rest

Encrypt the Docker volume (LUKS on Linux host, or use your cloud provider's encrypted storage):

```bash
# On Ubuntu 26 host
sudo cryptsetup luksFormat /dev/sdb
sudo cryptsetup open /dev/sdb redis_encrypted
sudo mkfs.ext4 /dev/mapper/redis_encrypted
sudo mount /dev/mapper/redis_encrypted /var/lib/redis
```

Or use cloud-provider encrypted volumes (AWS EBS, DO volumes, Hetzner volumes all support this).

**Plus:** encrypt your backups (rclone crypt to B2/S3).

## 10.8 Secrets management

**Never** put `REDIS_PASSWORD` in `docker-compose.yml`. Always use `${REDIS_PASSWORD}` and store in `.env` (which is in `.gitignore`).

```bash
# .gitignore
.env
.env.*
!.env.example
```

```bash
# .env.example (committed to repo as a template)
REDIS_PASSWORD=change-me-please
```

**For GitHub Actions / production:**

```yaml
# .github/workflows/deploy.yml
env:
  REDIS_PASSWORD: ${{ secrets.REDIS_PASSWORD }}
```

Store the actual secret in: **GitHub repo → Settings → Secrets and variables → Actions**.

## 10.9 Security checklist

- [ ] Redis NOT exposed to public internet
- [ ] Strong password (32+ random chars)
- [ ] ACLs configured (limited app user, separate admin)
- [ ] TLS enabled for production
- [ ] Dangerous commands disabled
- [ ] Volume encryption at rest
- [ ] Secrets in env vars / GitHub Secrets, not code
- [ ] `.env` in `.gitignore`
- [ ] Healthcheck enabled
- [ ] Backups encrypted
- [ ] `maxmemory` set with `allkeys-lru`
- [ ] Rate limiting on Redis-touching endpoints
- [ ] AOF persistence enabled
- [ ] Regular security updates (`docker compose pull redis:7.4-alpine`)

---

# Module 11: Observability

## 11.1 Redis Insight — the official GUI

Free, official, by Redis. **Use it for debugging.**

```yaml
services:
  redis-insight:
    image: redis/redisinsight:latest
    container_name: yourapp_redis_insight
    restart: unless-stopped
    volumes:
      - redis_insight_data:/db
    ports:
      - "5540:5540"  # only expose on localhost or via Cloudflare Tunnel
    networks:
      - app_network
```

Access at `http://localhost:5540`. Connect to `redis:6379` with your password.

**Use it to:** browse keys, run commands, see memory usage, debug slow commands.

## 11.2 Prometheus + Grafana

```yaml
services:
  redis-exporter:
    image: oliver006/redis_exporter:latest
    environment:
      REDIS_ADDR: redis:6379
      REDIS_PASSWORD: ${REDIS_PASSWORD}
    ports:
      - "9121:9121"  # expose only to monitoring
    networks:
      - app_network
```

Add to `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: redis
    static_configs:
      - targets: ["redis-exporter:9121"]
```

**Key Grafana alerts:**

```yaml
# Hit rate (cache effectiveness)
- alert: RedisHitRateLow
  expr: redis_keyspace_hit_ratio < 0.8
  for: 5m

# Memory usage
- alert: RedisMemoryHigh
  expr: (redis_memory_used_bytes / redis_memory_max_bytes) > 0.85
  for: 5m

# Rejected connections (under attack or misconfigured)
- alert: RedisRejectedConnections
  expr: increase(redis_rejected_connections_total[5m]) > 0

# Connected clients
- alert: RedisClientsTooMany
  expr: redis_connected_clients > 1000
```

## 11.3 SLOWLOG — find slow commands

```python
# Configure at startup
SLOWLOG_THRESHOLD_MS = 10  # log commands slower than 10ms
await redis.config_set("slowlog-log-slower-than", SLOWLOG_THRESHOLD_MS)
await redis.config_set("slowlog-max-len", 1000)

# Read the slow log
slow_commands = await redis.slowlog_get(50)
for entry in slow_commands:
    print(f"Command took {entry['duration']}ms: {entry['command']}")
```

**Investigate anything > 10ms.** Common causes: `KEYS *` (use `SCAN` instead), missing indexes, huge values.

## 11.4 INFO command

```python
info = await redis.info()
print(f"Memory used: {info['used_memory_human']}")
print(f"Connected clients: {info['connected_clients']}")
print(f"Total keys: {info['db0']['keys']}")
print(f"Hit rate: {info['keyspace_hits']} / {info['keyspace_hits'] + info['keyspace_misses']}")
```

**Use in health checks** to surface to your monitoring.

---

# Module 12: Capstone — Wire it all together

## 12.1 The complete `docker-compose.yml` (Redis section)

```yaml
version: "3.9"

services:
  # ... your other services: api, postgres, mongo, qdrant ...

  redis:
    image: redis:7.4-alpine
    container_name: yourapp_redis
    restart: unless-stopped
    command: >
      redis-server
      --requirepass ${REDIS_PASSWORD}
      --maxmemory 512mb
      --maxmemory-policy allkeys-lru
      --appendonly yes
      --appendfsync everysec
      --save 900 1
      --save 300 10
      --save 60 10000
      --rename-command FLUSHALL ""
      --rename-command FLUSHDB ""
      --rename-command CONFIG ""
      --rename-command DEBUG ""
      --slowlog-log-slower-than 10000
      --slowlog-max-len 1000
    volumes:
      - redis_data:/data
    networks:
      - app_network
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    # NO ports — internal network only

  redis-exporter:
    image: oliver006/redis_exporter:latest
    environment:
      REDIS_ADDR: redis:6379
      REDIS_PASSWORD: ${REDIS_PASSWORD}
    restart: unless-stopped
    networks:
      - app_network
    depends_on:
      redis:
        condition: service_healthy

  # Only for dev/staging — REMOVE for production
  redis-insight:
    image: redis/redisinsight:latest
    container_name: yourapp_redis_insight
    restart: unless-stopped
    volumes:
      - redis_insight_data:/db
    ports:
      - "127.0.0.1:5540:5540"  # localhost only
    networks:
      - app_network
    profiles: ["dev"]  # only starts with --profile dev

volumes:
  redis_data:
    name: yourapp_redis_data
  redis_insight_data:
    name: yourapp_redis_insight_data

networks:
  app_network:
    driver: bridge
```

## 12.2 The complete Redis client (production)

```python
# app/core/redis_client.py
import redis.asyncio as aioredis
from app.core.config import settings
from typing import Optional
import json
import logging

logger = logging.getLogger(__name__)

class RedisClient:
    """Production Redis wrapper with JSON helpers."""
    
    def __init__(self):
        self._client: Optional[aioredis.Redis] = None
    
    async def connect(self):
        self._client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30,
        )
        # Verify connection
        await self._client.ping()
        logger.info("Redis connected")
    
    async def disconnect(self):
        if self._client:
            await self._client.aclose()
            logger.info("Redis disconnected")
    
    @property
    def client(self) -> aioredis.Redis:
        if not self._client:
            raise RuntimeError("Redis not connected. Call connect() first.")
        return self._client
    
    # === JSON helpers ===
    async def get_json(self, key: str):
        data = await self.client.get(key)
        return json.loads(data) if data else None
    
    async def set_json(self, key: str, value, ex: Optional[int] = None):
        await self.client.set(key, json.dumps(value, default=str), ex=ex)
    
    async def get_or_set_json(self, key: str, loader, ex: int = 3600):
        cached = await self.get_json(key)
        if cached is not None:
            return cached
        value = await loader()
        await self.set_json(key, value, ex=ex)
        return value

redis_client = RedisClient()
```

## 12.3 The complete FastAPI integration

```python
# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request, HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.redis_client import redis_client

@asynccontextmanager
async def lifespan(app: FastAPI):
    await redis_client.connect()
    yield
    await redis_client.disconnect()

app = FastAPI(lifespan=lifespan)
limiter = Limiter(key_func=get_remote_address, storage_uri="redis://...")
app.state.limiter = limiter

@app.get("/chat")
@limiter.limit("30/minute")
async def chat(
    request: Request,
    message: str,
    user = Depends(get_current_user),
):
    # Try cache first
    cache_key = f"chat:{user.id}:{hash(message)}"
    cached = await redis_client.get_json(cache_key)
    if cached:
        return {"response": cached, "cached": True}
    
    # Call LLM
    response = await call_gemini(message)
    
    # Cache for 1 hour
    await redis_client.set_json(cache_key, response, ex=3600)
    
    return {"response": response, "cached": False}
```

## 12.4 Production checklist

**Setup**
- [ ] Redis in docker-compose with healthcheck
- [ ] Internal network only (no exposed ports)
- [ ] Strong password in `.env` (32+ random chars)
- [ ] AOF + RDB persistence enabled
- [ ] `maxmemory` set with `allkeys-lru`
- [ ] Dangerous commands renamed/disabled
- [ ] `.env` in `.gitignore`

**Security**
- [ ] ACLs for app user (limited keyspace)
- [ ] TLS for multi-host deployments
- [ ] Volume encryption at rest
- [ ] Backups encrypted
- [ ] Secrets in GitHub Secrets, not code

**Performance**
- [ ] Connection pooling configured
- [ ] Cache-aside pattern implemented
- [ ] LLM response caching
- [ ] Pipelining for batch ops
- [ ] `KEYS *` never used (use `SCAN`)

**Reliability**
- [ ] Rate limiting on all public endpoints
- [ ] Healthcheck endpoint exposed
- [ ] Sentinel/backup plan documented
- [ ] Daily backup to encrypted off-site storage
- [ ] Tested restore procedure

**Observability**
- [ ] Redis Insight for dev
- [ ] redis_exporter for Prometheus
- [ ] SLOWLOG enabled
- [ ] Grafana dashboard with hit rate, memory, connections
- [ ] Alerts for: low hit rate, high memory, rejected connections

**Operations**
- [ ] Documented runbook (how to flush cache, how to add a replica, etc.)
- [ ] Incident response plan (what if Redis is full? what if it's down?)
- [ ] Quarterly security review

---

## Final notes

**Your AI SaaS stack will use Redis for:**

1. **LLM response cache** — biggest cost saver
2. **Embedding cache** — same text → cached vector
3. **Session store** — fast, TTL-based
4. **Rate limiter** — protect Gemini free tier
5. **Background job queue** — Streams + worker
6. **Brute force protection** — failed login tracking
7. **Distributed locks** — prevent duplicate work
8. **Real-time pub/sub** — WebSockets for chat UI

**Pick the right tool for each:**
- Cache: `redis-py` directly
- Rate limit: `slowapi` (FastAPI)
- Job queue: raw Streams or Celery
- Distributed lock: `python-redis-lock`
- Session: `redis-py` + custom or `fastapi-users`
- Observability: `redis_exporter` + Prometheus + Grafana

**When NOT to use Redis:**
- Primary data storage (use Postgres/Mongo)
- Files > 1MB (use S3/Mongo GridFS)
- Long-term data without TTL
- High-write workloads > 100K ops/sec (consider Cluster)

---

**Library recommendations (all free, open source, industry standard):**

| Library | What | Why |
|---|---|---|
| `redis[hiredis]` | Python client | Official, fastest, async support |
| `slowapi` | Rate limiting | FastAPI standard, uses Redis backend |
| `fastapi-cache2` | Endpoint caching | Drop-in `@cache` decorator |
| `python-redis-lock` | Distributed locks | Handles edge cases for you |
| `celery[redis]` | Job queue | Industry standard for async tasks |
| `rq` | Lightweight job queue | Simpler than Celery |
| `redis_exporter` | Prometheus metrics | Standard, well-maintained |
| `redis/redisinsight` | GUI | Official, free |

---

**You now know enough to:**
1. Set up Redis in your AI SaaS
2. Cache LLM responses (save real money on Gemini free tier)
3. Build session/auth flows
4. Run background jobs (PDF ingestion, re-embedding)
5. Protect your API from abuse
6. Operate Redis in production safely

Welcome to senior backend engineering. 🎯
