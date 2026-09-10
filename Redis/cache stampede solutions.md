```markdown
# Cache Stampede: A Beginner-Friendly Guide with Interactive Strategies

## 1. The Problem We're Solving: What is a Cache Stampede?

First, a 10-second recap of caching:

- Your app is slow when it reads from the database every time.
- So you copy the answer into Redis with an expiry time (TTL), e.g. `SET product:42 "{...}" EX 300`. For 5 minutes, requests are served instantly from Redis.
- When the TTL runs out, Redis deletes the key. The next request must re-compute the answer (expensive DB query) and store it again.

Now imagine a popular product page. Its cache entry expires at exactly 17:00:00. At that same second, 500 users are browsing the page.

All 500 requests find the cache empty at the same time. All 500 decide "I must query the database!" at the same time.

**That is a cache stampede** (also called cache miss storm or thundering herd):

```plaintext
17:00:00  → cache expires
17:00:00  → request 1  misses cache → hits DB
17:00:00  → request 2  misses cache → hits DB
17:00:00  → request 3  misses cache → hits DB
   ...        ...
17:00:00  → request 500 misses cache → hits DB
```

Instead of 1 database query, your database suddenly gets 500 identical, heavy queries in the same second. Your database slows down or crashes, the rebuilds take longer, more caches expire in the meantime... a classic cascading failure.

💡 **The root cause is simple:** expiry is a "cliff". The data is 100% valid, then instantly 100% gone, and every request reacts to that at the same moment.

Every prevention strategy is essentially one of these ideas:

- Let only ONE request do the expensive rebuild (others wait or take a shortcut) → **Mutex / lock**
- Never let the data fully disappear — keep serving the old copy while refreshing → **Stale-While-Revalidate**
- Stop everyone from expiring at the same moment → **TTL jitter**
- Merge identical in-flight requests → **request coalescing**

---

## 2. Strategy 1: Mutex (distributed lock)

### The idea in plain words

Imagine a whiteboard in an office with yesterday's weather on it. The rule: "when the weather is outdated, erase it first, then go check outside and write the new one."

A stampede happens because 10 people walk in, see the board is empty, and all 10 run outside.

The mutex rule instead says: "Whoever erases the board takes a token. Only the person holding the token may go outside. Everyone else must wait by the board."

So: one request becomes the rebuilder, all the others wait (usually just a few milliseconds) until the fresh value is in Redis, then they read it from cache as normal.

### How it's done in Redis

Redis has a perfect command for this: `SET key value NX PX milliseconds`

- `NX` = only set if it does NOT exist (if someone already took the lock, this fails)
- `PX` = the lock auto-expires, so a crashed process can't hold the lock forever

```python
import redis, json, time, random

r = redis.Redis()

def get_product(product_id):
    key = f"product:{product_id}"
    cached = r.get(key)
    if cached:
        return json.loads(cached)          # ✅ cache hit, done

    lock_key = f"lock:{product_id}"
    # Try to become THE rebuilder. Only one request wins this.
    if r.set(lock_key, "1", nx=True, ex=10):   # SET NX PX
        try:
            # Double-check: maybe another worker just finished rebuilding
            cached = r.get(key)
            if cached:
                return json.loads(cached)

            data = fetch_from_database(product_id)   # 💸 expensive
            r.set(key, json.dumps(data), ex=300)
            return data
        finally:
            r.delete(lock_key)              # release the lock
    else:
        # Someone else is rebuilding right now → wait, then retry
        time.sleep(0.05 + random.random() * 0.1)   # small random wait!
        return get_product(product_id)
```

### Walk through what happens now

```plaintext
17:00:00  request 1  misses → wins lock → queries DB (takes 200ms)
17:00:00  request 2  misses → lock taken → sleeps 60ms
17:00:00  request 3  misses → lock taken → sleeps 80ms
17:00:00  request 4  misses → lock taken → sleeps 50ms
   ...
17:00:00.2  request 1 finishes → writes cache → releases lock
17:00:00.2  requests 2,3,4 wake up → CACHE HIT ✅
```

**Database queries: 1 instead of 500.**

### Important details beginners miss

- The lock must have an expiry (PX). If the rebuilder crashes mid-rebuild, without PX the lock lives forever and nobody can ever rebuild — worse than a stampede.
- Lock expiry must be longer than the worst-case rebuild time. If your query can take 3s but the lock expires in 1s, a second rebuilder can start while the first is still working → partial stampede. Common fix: extend/renew the lock, or set a generous expiry.
- The small random sleep (jitter) matters. If 499 waiting requests all wake up at exactly the same moment, they slam Redis with 499 simultaneous GETs (a mini-storm on the cache itself). Randomizing the sleep spreads them out.
- Use one lock per key (`lock:product:42`), never one global lock — otherwise a rebuild of product 42 would block unrelated products.
- What if rebuilding fails? The `finally` still releases the lock, so the next request can retry. Some systems return an error or stale data instead of retrying forever.
- "Wait" isn't your only option. If you have an old (stale) copy available, waiting requests can serve that instead of sleeping — which smoothly leads us to strategy 2.

---

## 3. Strategy 2: Stale-While-Revalidate (SWR)

### The idea in plain words

Back to the whiteboard. The mutex approach's flaw: everyone waits while one person runs outside. Users hate waiting.

The SWR rule: "Never erase the board. When the weather is outdated, serve the old weather immediately — and send one person outside to update it in the background."

So the data in your cache always exists, it just has two states:

| State | Meaning | What you serve |
|-------|---------|----------------|
| Fresh | now < expires_at | The value, instantly |
| Stale | expires_at < now < expires_at + stale_window | Still the value, instantly! — but trigger one background refresh |

The trick: expiry becomes "logical" — stored inside the value — instead of a hard Redis TTL delete.

### The structure of a cache entry

Instead of storing just the data:

```json
{ "data": { "name": "Wireless Mouse", "price": 19.99 }, "expires_at": 1757370000 }
```

Redis keeps the key alive (TTL = fresh time + stale window, or even no TTL at all), and your application code interprets whether the value is fresh or stale.

### The flow

```plaintext
17:00:00  expires_at passed → value is now "stale" (but still in Redis!)
17:00:00  request 1 arrives → serves STALE value instantly ✅ → wins refresh lock → rebuilds in background
17:00:00  request 2 arrives → serves STALE value instantly ✅
17:00:00  request 3 arrives → serves STALE value instantly ✅
   ...
17:00:00.2  rebuild finishes → fresh value stored, expires_at extended
17:00:00.2  request 501 arrives → serves FRESH value ✅
```

**Database queries: 1. Slow requests: 0. Users: always got an instant answer.**

### Code example

```python
import redis, json, time

r = redis.Redis()

FRESH_FOR   = 300   # fresh for 5 minutes
STALE_FOR   = 120   # may serve stale for 2 more minutes while refreshing

def get_product(product_id):
    key = f"product:{product_id}"
    raw = r.get(key)

    if raw:
        entry = json.loads(raw)                 # {"data": ..., "expires_at": ...}
        if entry["expires_at"] > time.time():
            return entry["data"]                # 🟢 fresh — perfect

        # 🟡 STALE — but still usable! Serve it NOW...
        if r.set(f"refresh_lock:{product_id}", "1", nx=True, ex=10):
            refresh_in_background(product_id, key)   # ...and refresh once
        return entry["data"]                    # user never waits ✅

    # 🔴 nothing in cache at all — must block (use the mutex pattern here)
    return rebuild_with_mutex(product_id, key)

def refresh_in_background(product_id, key):
    try:
        data = fetch_from_database(product_id)
        r.set(key, json.dumps({
            "data": data,
            "expires_at": time.time() + FRESH_FOR
        }), ex=FRESH_FOR + STALE_FOR)   # hard TTL = fresh + stale safety net
    finally:
        r.delete(f"refresh_lock:{product_id}")
```

Note that SWR combines beautifully with the mutex: the `SET NX` refresh lock ensures only one background refresh happens even if 500 requests hit the stale value at once. (In a real app, `refresh_in_background` runs in a thread/async task, not inline.)

### Where you may have already seen SWR

This is exactly what the HTTP header `Cache-Control: max-age=300, stale-while-revalidate=120` means — CDNs and browsers do the same thing. The concept is identical; here we're implementing it inside our own app with Redis.

### Bonus: Stale-If-Error

A tiny sibling of SWR: if the rebuild throws an error (database is down), don't fail the user — keep serving stale data a bit longer:

```python
try:
    data = fetch_from_database(product_id)
except DatabaseError:
    return entry["data"]        # stale is better than an error page
```

---

## 4. Strategy 3: TTL jitter (make expirations stop clustering)

Even with the strategies above, it's wasteful if 10,000 keys all expire at the top of the hour. Add randomness to every TTL:

```python
ttl = 300 + random.randint(0, 60)      # 300–360 seconds
r.set(key, json.dumps(data), ex=ttl)
```

Now keys expire spread out over a minute instead of all at once. Jitter doesn't prevent a stampede on a single hot key by itself, but it removes stampedes caused by synchronized expiry (very common with cron jobs or deploys that warm the cache at the same time). Always do this — it's one line.

---

## 5. Strategy 4: Request coalescing (singleflight)

If your app runs many server processes, per-process locks don't help — 50 processes = 50 simultaneous rebuilds. Singleflight means: while a request for key X is in flight, other requests for X attach to the same pending promise instead of starting new work.

In a single process this is a simple in-memory map; across machines you can use a Redis lock (as above) or a "per-key inflight registry". Go's `golang.org/x/sync/singleflight` is the famous implementation.

---

## Comparison table

| Strategy | DB load on expiry | User latency | Complexity | Best for |
|----------|-------------------|--------------|------------|----------|
| Nothing | 🔴 N queries | instant → slow | zero | nothing 🙂 |
| Mutex/lock | 🟢 1 query | 🟡 brief wait | low | Most cases; great default |
| Stale-While-Revalidate | 🟢 1 query | 🟢 always instant | medium | Read-heavy, hot keys, zero-latency requirements |
| TTL jitter | reduces clustering | unchanged | trivial | Always combine with others |
| Coalescing | 🟢 1 per key | 🟢 no duplicate work | medium | Multi-process/multi-server apps |

---

## Real-world combo (what most teams run)

**SWR + per-key refresh lock + TTL jitter + stale-if-error.**

You get **1 DB query**, **zero user-visible waits**, and **crash safety**.
```
