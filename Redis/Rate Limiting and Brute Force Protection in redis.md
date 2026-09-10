# Redis for Rate Limiting & Brute Force Protection — Complete Beginner Guide

Great choice! Redis is the industry-standard tool for rate limiting because it's **in-memory** (super fast, ~sub-millisecond operations) and has atomic operations and TTLs built in. Let's build this up step by step, like a story — each approach solves a problem the previous one had.

---

## Part 0: The Core Ideas You Must Understand First

Before algorithms, understand these 4 Redis building blocks. Everything we build is a combination of these:

**1. `INCR` — atomic counter**

```
INCR login_attempts:user123    → 1
INCR login_attempts:user123    → 2
INCR login_attempts:user123    → 3
```

Each call increases a number by 1. "Atomic" means even if 100 requests hit at the exact same millisecond, Redis processes them one-by-one, so counts are never wrong. This is critical — if you did this in Python with `count += 1`, race conditions would let attackers slip past limits.

**2. `EXPIRE` — auto-delete after N seconds**

```
EXPIRE login_attempts:user123 300
```

The key deletes itself after 300 seconds. This is how we get "windows" (time periods) without any cleanup jobs.

**3. `SET key value EX seconds NX` — set only if not exists**

```
SET rate:ip:1.2.3.4 1 EX 60 NX
```

- `EX 60` → expires in 60 seconds
- `NX` → only sets if the key doesn't exist (returns None if it already exists)

This lets us detect "is this the FIRST request in the window?"

**4. Sorted Sets (`ZADD`, `ZREMRANGEBYSCORE`, `ZCARD`)** — a set where every member has a score (a number), and members are kept sorted by that score. We'll use timestamps as scores.

**Why Redis and not a Python variable or database?**



| Store                          | Why it fails                                                                                                                          |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------- |
| Python variable (e.g., a dict) | Works only on ONE process. Deploy 2 servers → each has its own count → attacker gets 2× the limit. Also resets on restart.            |
| PostgreSQL/MySQL               | Too slow under attack (disk I/O), and row-level locking under concurrent writes becomes a bottleneck — exactly when you need it most. |
| Redis                          | Shared by ALL servers, in-memory speed, atomic ops, auto-expiry.                                                                      |



---

## Part 1: Fixed Window Counter (The Simplest Approach)

### The idea

"Allow max N requests per minute. Count requests in the current minute."

### How it works

The key includes the **current timestamp bucket** (e.g., the minute number). Each request: increment the counter; if it's the first request, set expiry so the key dies when the window ends.

```python
import time
import redis

r = redis.Redis()

def fixed_window_rate_limit(user_id: str, limit: int = 10, window_sec: int = 60) -> bool:
    """
    Returns True if allowed, False if rate limited.
    """
    # Key = user + current time window. E.g. "rate:42:28376471"
    window = int(time.time()) // window_sec
    key = f"rate:{user_id}:{window}"

    count = r.incr(key)          # count = current request number
    if count == 1:
        # First request in this window → make key expire when window ends
        r.expire(key, window_sec)

    return count <= limit
```

**Example trace** (limit = 5/minute):

```
10:00:15 → key "rate:42:1685" becomes 1, expiry set ✅ allowed
10:00:20 → 2 ✅
10:00:45 → 3 ✅
10:00:59 → 4 ✅
10:00:59.9 → 5 ✅
10:01:01 → key "rate:42:1686" → 1 ✅ (NEW window, counter reset)
```

### ✅ Advantages

- Dead simple — ~10 lines of code
- Tiny memory usage (one key per user per window)
- Very fast (single `INCR`)

### ❌ The famous problem: the "burst at window edges"

Look what an attacker can do at the boundary:

```
10:00:55 → sends 5 requests  (window 10:00 counts: 5 ✅ allowed)
10:01:00 → NEW window starts → sends 5 more requests ✅ allowed
```

Result: **10 requests within 5 seconds**, even though the limit is "5 per minute."

That's the big disadvantage. Rule of thumb: **a fixed window allows up to 2× the limit in a burst at the boundary.**

### When to use it anyway

- Internal APIs where occasional 2× bursts are harmless
- Very cheap "rough" protection (e.g., limiting analytics calls)
- When simplicity matters more than precision

---

## Part 2: Sliding Window Log (The Perfect but Expensive Approach)

### The idea

"Store the timestamp of **every single request**. Allow a request only if fewer than N requests happened in the **last 60 seconds** — rolling."

This has **no boundary problem at all** — the window literally slides with every request.

### How it works (using a Sorted Set)

- Each request = one member in a sorted set, with its timestamp as the score.
- On each new request:
  
  1. Delete all entries older than 60 seconds (`ZREMRANGEBYSCORE`)
  
  2. Count what remains (`ZCARD`)
  
  3. If count < limit → add current timestamp (`ZADD`) and allow; else reject.

```python
def sliding_window_log(user_id: str, limit: int = 5, window_sec: int = 60) -> bool:
    key = f"ratelog:{user_id}"
    now = time.time()
    cutoff = now - window_sec

    pipe = r.pipeline()
    pipe.zremrangebyscore(key, 0, cutoff)   # 1. remove old entries
    pipe.zcard(key)                          # 2. count recent requests
    pipe.zadd(key, {f"{now}-{uuid4()}": now})  # 3. record THIS request
    pipe.expire(key, window_sec)             # keep memory in check
    _, count, _, _ = pipe.execute()

    return count < limit
```

(Note: `now-{uuid}` as the member name — members must be unique, and two requests could share the same millisecond.)

Wait — should we record the request before checking? Slight subtlety: if we record first and then check, the count includes the current request. The version above counts *prior* requests, then records — so `count < limit` means "fewer than limit before me." Fine either way, just be consistent.

### ✅ Advantages

- **Perfectly accurate** — true sliding window, no edge bursts
- The only approach where "5 per minute" literally means any 60-second span

### ❌ Disadvantages

- **Memory heavy**: you store one entry per request. A user making 1000 req/min → 1000 sorted-set entries per minute per user.
- **O(log N) per request** — more CPU on Redis than a simple counter.
- **Race condition risk** in the check-then-act sequence. Two concurrent requests could both pass the check before either records itself. (In practice people do the whole thing in a Lua script to make it atomic — more on this below.)

### When to use it

- Low-traffic, high-stakes endpoints (e.g., a password-reset endpoint, financial operations)
- Where exactness justifies the memory cost

---

## Part 3: Sliding Window Counter (The Practical Sweet Spot)

### The idea

"Estimate the sliding window by **combining the current fixed window and the previous one**, weighted by how much of the previous window is still 'alive'."

This gives you sliding-window-like smoothness with fixed-window-like cheapness. It's what most big companies (e.g., approaches inspired by Cloudflare's blog post) actually use.

### The formula

```
weight = (window_sec - time_elapsed_in_current_window) / window_sec
estimated_count = (previous_window_count * weight) + current_window_count

allow if estimated_count < limit
```

**Concrete example** (limit = 10/min):

```
Previous minute (10:00–10:01): 8 requests
Current minute (10:01–10:02), we're 20 seconds in: 3 requests so far

weight = (60 - 20) / 60 = 0.67
estimated = 8 × 0.67 + 3 = 8.36  →  over the limit? No (8.36 < 10) → allow

But 50 seconds in:
weight = (60 - 50) / 60 = 0.17
estimated = 8 × 0.17 + 3 = 4.36 → still fine
```

Compare with the fixed-window edge case: at 10:01:00 fixed window saw just 3 (the 8 "vanished" instantly), and near 10:01:59 it still saw ~3 — totally blind to the previous window. The sliding window counter keeps a fading memory of it. No more 2× burst exploit.

### Code

```python
def sliding_window_counter(user_id: str, limit: int = 10, window_sec: int = 60) -> bool:
    now = time.time()
    current_window = int(now // window_sec)
    prev_window = current_window - 1

    key_cur = f"swc:{user_id}:{current_window}"
    key_prev = f"swc:{user_id}:{prev_window}"

    # Read both counters (MGET = get multiple keys in one round trip)
    cur_count, prev_count = r.mget(key_cur, key_prev)
    cur_count = int(cur_count or 0)
    prev_count = int(prev_count or 0)

    # Ensure both keys expire (in case they're new)
    r.expire(key_cur, window_sec * 2)
    if prev_count > 0:
        r.expire(key_prev, window_sec * 2)

    # Weighted estimate
    elapsed = now % window_sec
    weight = (window_sec - elapsed) / window_sec
    estimated = (prev_count * weight) + cur_count

    if estimated >= limit:
        return False                      # rate limited

    r.incr(key_cur)                       # record this request
    return True
```

### ✅ Advantages

- Smooth (no burst exploit like fixed window)
- Cheap: only 2 integers per user (fixed memory), like fixed window
- Good enough accuracy for 99% of production use

### ❌ Disadvantages

- It's an **estimate** — not exact (e.g., it assumes the previous window's requests were spread evenly, but they might have all been at the end → we underestimate). In practice this is acceptable; it's usually *slightly stricter or looser*, never wildly wrong.
- Slightly more code than fixed window.

### When to use it

- **Public APIs** — this is the default "right answer" for most rate limiting.
- When you need fairness (no edge bursts) but high throughput.

### Quick comparison so far

| Approach        | Burst exploit?       | Memory per user     | Accuracy | Complexity |
| --------------- | -------------------- | ------------------- | -------- | ---------- |
| Fixed window    | ⚠️ Yes (2× at edges) | 1 counter           | Coarse   | ⭐          |
| Sliding log     | ✅ No                 | 1 entry per request | Exact    | ⭐⭐⭐        |
| Sliding counter | ✅ Mostly no          | 2 counters          | Estimate | ⭐⭐         |

---

## Part 4: Token Bucket (For Bursty Traffic + Smooth Throughput)

All the approaches above think in terms of "requests per window." Token bucket thinks in terms of **a bucket of tokens that refills over time**.

### The idea

- Imagine a bucket that holds, say, **10 tokens**.
- Every request needs to take **1 token** out of the bucket to proceed. No token → rejected.
- Tokens are **refilled continuously** — e.g., 1 token per second (or fractionally: refill rate = limit/window).

### Why it's great: it allows bursts AND enforces averages

- A user sitting idle accumulates tokens → when they come back, they can burst up to the bucket size (this is *allowed and fine*, unlike the fixed-window exploit which was unintended).
- Over the long run, throughput is capped at the refill rate.
- This is why token bucket is used for **API quotas** ("users may burst, but sustained rate is limited").

### The math (no need to store every token!)

Key insight: you only need to store **how many tokens exist right now** and **when the bucket was last updated**. Tokens refilled since then are computed on the fly:

```python
def token_bucket(user_id: str, capacity: int = 10, refill_per_sec: float = 1.0) -> bool:
    key = f"bucket:{user_id}"
    now = time.time()

    data = r.hgetall(key)
    if not data:
        tokens, last_refill = float(capacity), now    # first request: full bucket
    else:
        tokens = float(data[b"tokens"])
        last_refill = float(data[b"last_refill"])

    # Refill: tokens added = elapsed_time × refill_rate (capped at capacity)
    elapsed = now - last_refill
    tokens = min(capacity, tokens + elapsed * refill_per_sec)

    if tokens < 1:
        return False                      # not enough tokens → reject

    tokens -= 1                           # take one token
    r.hset(key, mapping={"tokens": tokens, "last_refill": now})
    r.expire(key, 3600)                   # cleanup idle users eventually
    return True
```

### ⚠️ Critical production issue: this code has a race condition

Two concurrent requests can both read `tokens=1`, both subtract, both pass → 2 requests consumed the last token. For production, do it **atomically in Lua** (Redis runs the whole script atomically, single-threaded):

```python
ALLOW_REQUEST = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local data = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(data[1]) or capacity
local last_refill = tonumber(data[2]) or now

tokens = math.min(capacity, tokens + (now - last_refill) * refill)

if tokens < 1 then
    return 0
end

redis.call('HMSET', key, 'tokens', tokens - 1, 'last_refill', now)
redis.call('EXPIRE', key, 3600)
return 1
"""

def token_bucket_safe(user_id, capacity=10, refill_per_sec=1.0):
    res = r.eval(ALLOW_REQUEST, 1, f"bucket:{user_id}",
                 capacity, refill_per_sec, time.time())
    return bool(res)
```

### ✅ Advantages

- Allows intentional bursts (up to bucket size)
- Enforces long-run average rate
- **Constant memory** (one small hash per user) regardless of traffic
- Refill is smooth/continuous, not window-based

### ❌ Disadvantages

- More complex to implement correctly (needs Lua for safety)
- The "burst" behavior must be what you *want* — not ideal for strict security limits (e.g., login attempts should NOT allow 10 rapid-fire attempts even after idle time)

### When to use what — decision guide

- **Fixed window** → simplest internal tooling, rough limits are fine
- **Sliding log** → low-traffic, must-be-exact endpoints (password reset, payment attempts)
- **Sliding window counter** → general public API rate limiting (the default choice)
- **Token bucket** → per-user API quotas where you *want* to permit bursts

---

## Part 5: Using SlowAPI for FastAPI ⭐ (Practical)

Rather than writing Redis logic yourself, the Python ecosystem has ready-made tools. The most popular for FastAPI is **slowapi**, which wraps the battle-tested `limits` library.

### Setup

```bash
pip install slowapi
```

### Basic usage

```python
from fastapi import FastAPI, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# get_remote_address = limit by client IP
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.get("/items")
@limiter.limit("5/minute")        # stricter limit on this endpoint
def read_items(request: Request):   # NOTE: request param is required
    return {"msg": "hello"}
```

### Limit by user instead of IP

```python
def get_user_id(request: Request) -> str:
    # adjust to your auth system (JWT decode, session, etc.)
    return request.headers.get("X-User-ID", get_remote_address(request))

limiter = Limiter(key_func=get_user_id)

@app.get("/premium-data")
@limiter.limit("30/minute")
def premium_data(request: Request):
    return {"data": "expensive stuff"}
```

### Dynamic limits (e.g., different tiers)

```python
@app.get("/api")
@limiter.limit(lambda request: "100/minute" if request.headers.get("X-Plan") == "pro" else "10/minute")
def api(request: Request):
    ...
```

### How it works under the hood

Slowapi's `limits` library uses a moving-window algorithm and stores counters in **memory by default** — which means the limits are per-process (same problem as a Python dict when you run multiple workers!). For production:

```python
from limits.storage import RedisStorage

storage_uri = "redis://localhost:6379/0"
limiter = Limiter(key_func=get_remote_address,
                  storage_uri=storage_uri,
                  default_limits=["100/minute"])
```

Now all your servers share the same counters via Redis.

### Practical gotchas with slowapi

1. **`request: Request` parameter is mandatory** in decorated functions — slowapi needs it.
2. Decorator order matters: put `@limiter.limit` directly above the function.
3. Background tasks and WebSockets need special handling.
4. For per-endpoint + global limits, combine `default_limits` with `@limiter.limit`.

---

## Part 6: Brute Force Protection for Login 🔐

This is rate limiting applied with a **different key and different rules**. Notice the key difference:

|              | Normal rate limiting | Brute force protection                 |
| ------------ | -------------------- | -------------------------------------- |
| Key          | IP or API key        | **username/account** (+ optionally IP) |
| Limit        | e.g., 100 req/min    | e.g., 5 failed logins / 15 min         |
| Counts       | All requests         | **Only FAILED attempts**               |
| After breach | Return 429           | **Lock account / require captcha**     |

### Level 1: Simple failed-attempt counter

```python
MAX_ATTEMPTS = 5
LOCK_SECONDS = 900   # 15 minutes

def check_login_allowed(username: str) -> bool:
    """Call BEFORE processing the password."""
    key = f"login_fail:{username.lower()}"
    fails = int(r.get(key) or 0)
    if fails >= MAX_ATTEMPTS:
        ttl = r.ttl(key)
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again in {ttl} seconds."
        )

def record_login_failure(username: str):
    key = f"login_fail:{username.lower()}"
    pipe = r.pipeline()
    pipe.incr(key)
    pipe.expire(key, LOCK_SECONDS, nx=True)  # only set TTL if not already set
    pipe.execute()

def record_login_success(username: str):
    # IMPORTANT: clear the counter on success, or a user who finally
    # remembers their password stays "one failure away" from lockout
    r.delete(f"login_fail:{username.lower()}")
```

**Login endpoint wiring:**

```python
@app.post("/login")
def login(credentials: LoginRequest, request: Request):
    check_login_allowed(credentials.username)

    user = authenticate(credentials.username, credentials.password)

    if not user:
        record_login_failure(credentials.username)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    record_login_success(credentials.username)
    return {"token": create_jwt(user)}
```

### Level 2: Why username-only is not enough — the attacker side and the DoS side

**Problem A — username-only lets an attacker LOCK OUT anyone.**
An attacker who knows your email can spam wrong passwords on purpose and lock *you* out. Classic denial-of-service on accounts.

**Problem B — IP-only lets attackers rotate around bans.**
Bots use botnets/proxies: thousands of IPs × 5 attempts each = still brute-forceable.

**The standard solution: combine both.**

```python
def check_login(request: Request, username: str):
    ip = get_remote_address(request)
    user_key = f"login_fail:u:{username.lower()}"
    ip_key = f"login_fail:ip:{ip}"

    for key, label in [(user_key, "this account"), (ip_key, "your IP")]:
        fails = int(r.get(key) or 0)
        if fails >= MAX_ATTEMPTS:
            ttl = r.ttl(key)
            raise HTTPException(429, f"Too many failed attempts for {label}. Retry in {ttl}s.")
```

Now:

- Account lockout protects against **password guessing on one account** (attacker must spread attempts across many accounts → dilutes their attack).
- IP lockout throttles a single noisy source.
- Attacker can't trivially DoS-lock a victim (they'd need the victim's *successful* login to fail... well, they can still lock you out — which is why many systems add step 3 below).

### Level 3: Progressive delays (better than hard lockout)

Hard lockouts cause support tickets and can be abused (DoS lockouts). A gentler, very effective pattern — **exponential backoff on failures**:

```python
def record_login_failure(username: str):
    key = f"login_fail:{username.lower()}"
    pipe = r.pipeline()
    fails = pipe.incr(key)
    pipe.expire(key, 3600, nx=True)
    pipe.execute()

def login(username, password):
    key = f"login_fail:{username.lower()}"
    fails = int(r.get(key) or 0)

    if fails >= 3:
        # force a delay: 2^fails seconds, capped at e.g. 300
        delay = min(2 ** fails, 300)
        last_try = float(r.get(f"{key}:last") or 0)
        if time.time() - last_try < delay:
            raise HTTPException(429, f"Wait {int(delay)}s before retrying.")
    ...
```

Failed 4 times → wait 16s. Failed 8 times → wait ~4.5 min. Bots get crippled (their throughput collapses), humans barely notice.

### Level 4: The modern best practice — fail "open" with monitoring, or require CAPTCHA after N failures

Many systems (Google, Cloudflare-style) avoid lockouts entirely:

- After ~3–5 failures: require a CAPTCHA
- After more: require email verification / 2FA
- Never hard-lock; just keep raising friction

This eliminates both the DoS-lockout abuse and the support burden.

### Extra brute-force protections that pair well with Redis limiting

1. **Constant-time password comparison** (`hmac.compare_digest`) — prevents timing attacks revealing valid usernames.
2. **Don't leak which field was wrong**: always return "invalid username or password" — otherwise attackers can enumerate valid accounts.
3. **Generic error on lockout**: don't say "account locked" — say "invalid credentials," otherwise you confirm the account exists.
4. **Monitor keys**: alert when `login_fail:*` keys spike — early warning of an attack campaign.

---

## Part 7: Cheat Sheet — Putting It All Together

```
┌─────────────────────────────────────────────────────────────┐
│  "I need to rate limit a public API endpoint"                │
│  → Sliding window counter (or slowapi with Redis storage)   │
├─────────────────────────────────────────────────────────────┤
│  "I have an internal endpoint where bursts are fine"         │
│  → Fixed window                                             │
├─────────────────────────────────────────────────────────────┤
│  "Low traffic endpoint where exactness matters (payments)"   │
│  → Sliding window log                                       │
├─────────────────────────────────────────────────────────────┤
│  "Per-user API quota where I WANT bursts (devs love this)"   │
│  → Token bucket (use the Lua script version!)               │
├─────────────────────────────────────────────────────────────┤
│  "Protecting /login"                                         │
│  → Separate counters: per-username (5 fails/15min)           │
│    + per-IP (20 fails/15min) + progressive delay +          │
│    CAPTCHA after N failures. Clear on success.              │
└─────────────────────────────────────────────────────────────┘
```

### Production checklist (applies to everything above)

- [ ] All check-and-increment logic is **atomic** (Lua script or Redis pipeline where safe). Race conditions = attackers get free passes.
- [ ] Keys always have **TTLs/EXPIRE** — otherwise Redis fills up forever.
- [ ] Rate limiter storage is **shared Redis**, not per-process memory (critical when running multiple uvicorn workers / containers!).
- [ ] Return proper **429 + `Retry-After`** header so well-behaved clients back off.
- [ ] Keep Redis **availability** in mind: if Redis is down, decide deliberately — fail open (no limiting) or fail closed (reject traffic). For auth endpoints, usually a short-lived local fallback is wise.

---

Want me to go deeper on any piece next? Good follow-ups: (1) a full working FastAPI project with slowapi + Redis + login brute-force protection wired together, (2) Lua scripts explained line by line, or (3) implementing a distributed token bucket that works across multiple app servers. Just say which one.
