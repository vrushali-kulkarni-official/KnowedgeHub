# Distributed Locks with Redis — A Complete Beginner's Guide

Let's build this up step by step, the same way the technology itself evolved: each new approach was invented to fix the weaknesses of the previous one.

---

## Part 0: What Problem Are We Even Solving?

Imagine two servers (Server A and Server B) both trying to update the same bank account balance at the same time:

```
Server A: read balance = 100 → add 50 → write 150
Server B: read balance = 100 → subtract 20 → write 80   💥 A's +50 is lost!
```

A **lock** makes sure only **one** server can do the critical operation at a time. On a single machine, you'd use a normal in-process lock (like Python's `threading.Lock`). But your servers run on different machines — so you need a lock stored in a place **all** servers can see: a shared external store. That's where **Redis** comes in.

> **Key insight:** A distributed lock is just a key in Redis that only one client is allowed to "hold" at a time. Everyone else must wait or fail.

---

## Part 1: The Simple Lock (`SET key value NX PX`)

### The naive version (and why it's broken)

You might think: "Just check if the key exists, and if not, create it."

```python
# ❌ WRONG — do not do this
if not redis.exists("my_lock"):
    redis.set("my_lock", "1")
    # ... do critical work ...
    redis.delete("my_lock")
```

**Why this fails:** Between `exists()` and `set()`, another server could do the exact same check and also think the lock is free. This is a **race condition**. Checking and acquiring must be a single, atomic operation.

### The correct primitive: `SET NX PX`

Redis gives us a command that does it atomically:

```bash
SET my_lock <unique_value> NX PX 10000
```

Breaking down each piece:

| Part             | Meaning                                                                                      |
| ---------------- | -------------------------------------------------------------------------------------------- |
| `SET my_lock`    | Create this key                                                                              |
| `<unique_value>` | A random token — usually a UUID. **Critical. Remember this for later.**                      |
| `NX`             | **Only set if key does NOT exist** (NX = "Not eXists"). This makes the check-and-set atomic. |
| `PX 10000`       | Expire the key after 10,000 ms (10 seconds). **Auto-release safety net.**                    |

### Why the expiry (PX) matters

What if a server crashes while holding the lock? Without expiry, the lock stays forever and **nobody can ever work again** (a "deadlock"). The TTL (time-to-live) guarantees the lock eventually frees itself, even if the holder dies.

### Full Python example

```python
import uuid, time
import redis

r = redis.Redis()

def do_critical_work():
    token = str(uuid.uuid4())          # unique token identifies ME as the owner
    acquired = r.set("payment_lock", token, nx=True, ex=10)  # atomic, 10s TTL

    if not acquired:
        print("Lock held by someone else — give up or retry")
        return

    try:
        # ... your critical section here ...
        process_payment()
    finally:
        # release ONLY if it's still OUR lock (compare token before delete)
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        r.eval(script, 1, "payment_lock", token)
```

### The delete-script is important — here's why

If you naively `DELETE my_lock`, you can delete **someone else's** lock:

```
10:00:00  Server A acquires lock (TTL 10s)
10:00:05  Server A freezes for 8 seconds (GC pause, network blip...)
10:00:10  Lock expires → Server B acquires it
10:00:13  Server A wakes up and runs DELETE → deletes B's lock! 💥
10:00:14  Server C acquires a "free" lock → now B AND C both hold it
```

This is why every lock holder must store a **unique token**, and deletion must be a Lua script that atomically checks `token == mine` before deleting. `GET` and `DEL` can't be two separate commands (that would be another race condition), so we use a Lua script to make check-and-delete atomic.

### Limitations of the Simple Lock — this is what motivated everything else

1. **Single point of failure.** If your one Redis server crashes, your whole locking system dies with it. No locks = possible double-execution.
2. **Client pauses can break correctness.** As shown above — a client that stalls longer than its TTL can lose the lock *without knowing it*, and keep operating on stale assumptions. ("Am I still the owner?" — Redis can't tell you.)
3. **No fencing.** If Client A loses the lock and Client B takes over, there's nothing stopping delayed writes from A from clobbering B's work. (More on fencing later.)
4. **You must implement renewal yourself.** If your job takes longer than the TTL, you need a background thread extending the lock — easy to get wrong.

> ⚠️ Honest note: for **many real-world cases**, this simple lock is honestly good enough — if the lock is only a "best-effort" optimization to avoid duplicate work (e.g., preventing two cron jobs from running the same report twice), the simple lock with a token + Lua-script release is perfectly fine. The fancier algorithms matter when **correctness is critical** (money, inventory) or **Redis itself can fail**.

---

## Part 2: Redlock — The "Serious Business" Algorithm

### The problem it solves

The simple lock trusts **one** Redis node. What if that node dies at the wrong moment? Redlock (designed by Antirez, Redis's creator, [2015 blog post](https://redis.io/docs/latest/develop/clients/patterns/distributed-locks/)) spreads the lock across **multiple independent Redis masters** so the system survives node failures.

### The algorithm (acquiring)

You run, say, **5 independent Redis masters** (not replicas — separate instances, no replication between them).

```
To acquire the lock:
1. Generate a unique token (UUID) and pick a total TTL, e.g. 10 seconds.
2. Try to acquire the lock on ALL 5 nodes, sequentially, with a short
   per-node timeout (e.g. 50ms). If one node is slow/down, skip it fast.
3. Count successes: you need at least N/2 + 1 = 3 successes to win.
4. Also measure total elapsed time. You must have gotten the majority
   WITHIN the TTL. If 8 seconds elapsed for 3 successes, the lock is
   effectively already expired — treat as failure.
5. If you failed → send UNLOCK commands to all 5 nodes (the ones that
   did succeed) and try again later with a random delay (to avoid
   thundering herd).
```

**Why majority (3 of 5)?** Because at most one client can ever reach a majority, even if nodes disagree. If Client A got 3 nodes and Client B got 3 nodes, that means they share a node that gave the lock to two people — impossible with NX semantics. Majority quorums mathematically guarantee mutual exclusion (as long as no node hands out the lock twice).

**Why 5 nodes and not 2?** With 2 nodes you need 2/2 = 100% — any single node failure breaks everything. With 3 nodes, quorum = 2, so you survive 1 failure. With 5, quorum = 3, survive 2 failures. More nodes = more tolerance, but slower and more expensive. **Odd numbers** are preferred because they tolerate the same failures with fewer nodes (3 and 4 both tolerate 1 failure).

### Releasing

Send the token-checked `DEL` Lua script to **all** nodes (not just the majority). This cleans up any stragglers.

### Renewal (extension)

If work exceeds the TTL, extend the lock on all nodes similarly: extend on a majority, within a fresh time budget.

### Why is this better than the simple lock?

| Failure scenario                         | Simple lock (1 node)           | Redlock (5 nodes)                         |
| ---------------------------------------- | ------------------------------ | ----------------------------------------- |
| Redis node crashes                       | Locking unavailable or unsafe  | Still works with 3+ alive                 |
| Node forgets everything (no persistence) | Data/lock state lost           | Majority still holds the truth            |
| Network partition splits clients         | Whole system blocked or unsafe | Only the majority partition can win locks |

### Limitations / criticisms of Redlock

Important for you to know — Redlock is **controversial**. Martin Kleppmann (author of *Designing Data-Intensive Applications*) wrote a famous critique ([2016 blog post](https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html)):

1. **Clock jumps & GC pauses break it.** If your client freezes for longer than the TTL mid-acquisition, or the server's clock jumps, the safety guarantees can silently break. Real networks and JVMs (big GC pauses) do this.
2. **It relies on timing assumptions** — distributed systems theory (FLP result) says algorithms that depend on bounded time can fail in weird edge cases.
3. **It's complex to implement correctly.** Most "Redlock" libraries have subtle bugs. (redis-py used to ship one, deprecated it for years, and removed it — a lesson in how hard this is.)
4. **Cost/complexity:** you must operate 5+ Redis instances.

**Kleppmann's recommendation:** if you need *strong* correctness, don't rely purely on time-based locks at all. Instead, add a **fencing token**: a monotonically increasing number issued with the lock. Every write to the shared resource includes the token, and the storage layer rejects writes with older tokens. Even if two clients briefly both think they hold the lock, the database enforces that only the newest token's writes survive.

### When to use Redlock

- Correctness matters (payments, inventory, leader election)
- You can afford to run 5 Redis nodes
- You accept operational complexity and the timing caveats above
- Combine with **fencing tokens** for real-world safety

For "efficiency locks" (avoid duplicate emails/reports), Redlock is overkill.

---

## Part 3: python-redis-lock — The "Just Make It Easy" Library

### What it is

[`python-redis-lock`](https://github.com/jazzband/python-redis-lock) is a battle-tested PyPI library that wraps the simple-lock pattern and adds everything people kept re-implementing (badly) by hand:

```bash
pip install python-redis-lock
```

```python
import redis, redis_lock

conn = redis.Redis()

# Context manager — auto-acquires and auto-releases
with redis_lock.Lock(conn, "my-resource"):
    print("I have the lock")
    do_critical_work()   # if this raises, lock is still released properly

# Or manual control with timeout and blocking:
lock = redis_lock.Lock(conn, "my-resource", expire=30, auto_renewal=True)
if lock.acquire(blocking_timeout=10):
    try:
        do_critical_work()
    finally:
        lock.release()
```

### What it gives you over raw SET NX PX

1. **Automatic renewal (`auto_renewal=True`)**: a background thread extends the TTL while you still hold the lock. This solves the "job took 15s but TTL was 10s" problem — your lock won't silently expire mid-work.
2. **Blocking with timeout**: `acquire(blocking_timeout=10)` waits up to 10s instead of failing instantly. Raw Redis has no wait — you'd have to write a retry loop with sleep + jitter yourself.
3. **Safe release**: it stores a unique token per lock instance and uses a Lua script to delete only if it's yours — the exact race we discussed is handled for you.
4. **Signal-based wait (with `Lock(..., expire=...)` + multiple waiters)**: waiters subscribe to a pub/sub channel; when the lock is released, the next waiter is **signaled instantly** instead of polling. Polling wastes requests and adds latency.
5. **Crash safety**: same TTL safety net as the manual version — a dead process's lock expires on its own.

### How it works internally (simplified)

```
acquire():
    1. SET lock_key <token> NX PX expire
    2. if success → start auto-renewal thread (optional)
    3. if fail and blocking=True → subscribe to lock_key's pub/sub channel,
       wait until released (with timeout), then retry from step 1

release():
    1. stop renewal thread
    2. Lua script: DEL only if stored token == my token
    3. PUBLISH to the channel → wake up one waiting client
```

### Limitations of python-redis-lock

1. **Still a single Redis node.** It doesn't do Redlock. If Redis dies, locks die. (It optionally supports *sentinel*, but not true multi-master quorum.)
2. **Still timing-based.** A client paused beyond the TTL has the same theoretical risk as the simple lock — auto-renewal *reduces* this risk a lot (renewals happen frequently, so a stalled client can't hold a "valid-looking" lock for long), but can't eliminate pauses.
3. **Still no fencing tokens.**
4. Adds a dependency and a background thread (renewal) per held lock — fine for a few locks, worth being aware of at high concurrency.

---

## Part 4: The Big Comparison — When to Use What

| Scenario                                                                                                           | Recommended approach                                                                                 | Why                                                                                                 |
| ------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Preventing duplicate cron jobs / reports / emails                                                                  | **python-redis-lock** (or even simple SET NX PX)                                                     | Failure = minor duplicate work, not corruption. Don't over-engineer.                                |
| Rate limiting, leader election for background tasks                                                                | **python-redis-lock**                                                                                | Nice API, auto-renewal, safe release, no ops burden                                                 |
| Money movement, inventory, booking the last seat                                                                   | **Redlock + fencing tokens** (or reconsider: use a DB transaction/consensus like Raft/Paxos instead) | Timing-based locks have edge cases; fencing tokens put correctness enforcement in the storage layer |
| Your Redis is already highly available (e.g., AWS ElastiCache with failover) and lock correctness is "best effort" | **python-redis-lock**                                                                                | The 5-node Redlock ops cost isn't justified                                                         |
| You need strict correctness but can't add fencing                                                                  | Don't use Redis locks — use **Postgres advisory locks**, ZooKeeper/etcd, or a DB transaction         | Eliminates the whole class of timing problems                                                       |

### A useful mental model for "when to use what"

Ask two questions:

1. **If the lock fails (two clients get in at once), what's the damage?**
   
   - Minor/inconvenience → simple lock or python-redis-lock is fine.
   
   - Financial/correctness damage → you need fencing tokens or a different mechanism entirely.
2. **Can Redis be a single point of failure for this?**
   
   - Yes → python-redis-lock on one node is fine.
   
   - No → Redlock, or an external consensus system.

---

## Part 5: Quick Recap of the Evolution

```
1. Simple lock (SET NX PX + token + Lua release)
   → Fixed: race condition in check-then-set, deadlock on crash
   → Remaining: single Redis point of failure, TTL expiry races

2. Redlock (majority quorum across 5+ masters)
   → Fixed: Redis node failures, single-point-of-failure
   → Remaining: timing assumptions (GC pauses, clock jumps),
     complexity, no fencing — hence controversy

3. python-redis-lock (library over single node)
   → Fixed: renewal hell, polling waits, unsafe deletes, boilerplate
   → Remaining: still single-node, still timing-based, no fencing
   → Note: it's an ergonomic improvement, NOT a new locking algorithm
```

## Key takeaways

1. **`SET NX PX` with a unique token + Lua-scripted release** is the atomic foundation of everything here.
2. **TTLs prevent deadlocks but introduce "expired while working" races** — auto-renewal and fencing tokens are the two main mitigations.
3. **Redlock trades simplicity for fault tolerance** via majority quorums, but depends on timing assumptions — know the debate.
4. **python-redis-lock is the pragmatic daily driver**: use it when "one good Redis" + safety conveniences is enough; reach for Redlock/fencing only when correctness demands it.

Want me to follow up with hands-on code — e.g., a runnable demo showing the exact race conditions (naive delete bug, TTL expiry race) so you can see them break in practice? Or a deeper dive into the fencing token pattern?
