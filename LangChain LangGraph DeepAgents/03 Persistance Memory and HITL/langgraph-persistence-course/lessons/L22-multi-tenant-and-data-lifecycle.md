# L22 · Multi-Tenant Memory & Data Lifecycle

> **Phase 8 — Persistence, Memory & Human-in-the-Loop**
> Module M61 · *Multi-tenant memory & data lifecycle*
>
> Run: `python examples/ex18_tenant_isolation.py`
> Run: `python examples/ex19_data_lifecycle.py`

---

## 0. Two hard problems

Up to now, memory has been about *what you remember*. This lesson is about the
two problems that show up the moment you have real customers:

1. **Isolation** — Alice's memories must never reach Bob.
2. **Lifecycle** — memories and conversations must be deletable, on demand, and
   on a schedule.

Both are boring. Both are where real systems leak.

---

## 1. The two scoping mechanisms

| | Checkpoint | Store |
|---|---|---|
| Scoped by | `thread_id` (a string) | `namespace` (a tuple of strings) |
| Where you put the tenant | in the thread id | in the namespace |
| Enforced by | convention (you build the string) | **structure** (the search prefix) |

The difference matters:

> A thread id that *contains* a user id is a **convention**. A namespace that
> *starts* with a tenant id is **structure** — `search()` physically cannot
> cross it.

---

## 2. Namespace design

```python
("tenant", "acme", "users", "alice", "memories")
  tenant  -> acme   -> users -> alice -> memories
```

Verified in `ex18`:

```
1. Write memories for TWO tenants
   tenant acme:
     tenant.acme.users.alice.memories / m1 = 'prefers metric units'
     tenant.acme.users.alice.memories / m2 = 'email alice@acme.com'
     tenant.acme.users.bob.memories   / m1 = 'prefers light mode'
   tenant globex:
     tenant.globex.users.alice.memories / m1 = 'email alice@globex.com'

2. ISOLATION: a scoped search cannot cross the tenant
   acme/alice   : ['prefers metric units', 'email alice@acme.com']
   globex/alice : ['email alice@globex.com']
   -> acme/alice CANNOT see globex/alice's memories. Verified.
```

Note the same user id (`alice`) exists in **both** tenants and they are
completely separate. That's why the tenant id must be in the namespace.

### 2.1 ⚠️ The order is the meaning

```python
("tenant", "acme", "users", "alice")   # acme + alice
("tenant", "users", "alice", "acme")   # a DIFFERENT thing
```

A search is a **prefix match**. If your search starts at
`("tenant", "acme")`, you get everything under acme. If it starts at
`("users", "alice")`, you get every tenant's alice.

**Rules:**

1. The **tenant id comes first** in every namespace.
2. **Every search starts at the tenant level.** Never at the user level.
3. **Never build a namespace with an f-string at the call site.**

### 2.2 The mistake that causes a leak

Verified in `ex18`:

```
4. THE MISTAKE: tenant id in the middle
   search(('tenant','acme')) now also returns:
      alice at acme - shared namespace bug
   -> The row was written OUTSIDE the tenant's namespace, so a
      tenant-scoped search picks it up. That is a data leak.
```

One call site that forgets the tenant prefix and you've leaked data across
tenants. **Never build a namespace with an f-string at the call site.**

### 2.3 The fix: a namespacing helper nobody can bypass

```python
# ONE place, in your codebase
def ns(tenant_id: str, user_id: str, *rest: str) -> tuple[str, ...]:
    return ("tenant", tenant_id, "users", user_id, *rest)
```

```python
store.put(ns("acme", "alice", "memories"), "m1", {...})
store.search(ns("acme", "alice", "memories"))
```

Now the only way to get it wrong is to call `ns()` with the wrong tenant —
which is visible in a diff.

### 2.4 The template approach (even better)

langmem's `NamespaceTemplate` resolves `{var}` from `config["configurable"]`:

```python
manager = create_memory_store_manager(
    model,
    namespace=("tenant", "{tenant_id}", "users", "{langgraph_user_id}"),
)

config = {"configurable": {
    "tenant_id": tenant_id,
    "langgraph_user_id": user_id,
    "thread_id": thread_id,
}}
```

The scope now comes from the **request context**, so it cannot be forgotten at
the call site.

### 2.5 The same rule for checkpoints

```python
def thread_id(tenant_id: str, conversation_id: str) -> str:
    return f"{tenant_id}:{conversation_id}"
```

→ `"acme:conv-42"`.

Verified:

```
6. Same rule for CHECKPOINTS
   acme:conv-1   -> {'log': ['x']}
   globex:conv-1 -> {'log': ['x']}
   -> different threads, different state.
```

The composite id makes the tenant boundary **visible in the database** —
`SELECT * FROM checkpoints WHERE thread_id LIKE 'acme:%'` is a one-liner.

---

## 3. Test your isolation

Isolation is a property that silently breaks during refactors. **Test it.**

```python
def test_tenant_isolation(store):
    store.put(("tenant", "a", "users", "u1", "memories"), "k",
              {"content": "A SECRET"})
    seen = [i.value for i in store.search(("tenant", "b"))]
    assert seen == []
```

Write this for **every** scope in your system. It costs 20 seconds and it
turns a silent leak into a CI failure.

---

## 4. TTL: making state expire on its own

### 4.1 The Store has TTL built in

```python
from langgraph.store.base import TTLConfig

ttl_config = TTLConfig(
    default_ttl=1440,               # MINUTES (24h)
    sweep_interval_minutes=5,
    refresh_on_read=False,          # absolute expiry
    omit_expired=True,              # hide expired items immediately
)

with PostgresStore.from_conn_string(DB_URL, index=index, ttl=ttl_config) as store:
    store.put(ns(t, u, "memories"), "k", {"content": "..."}, ttl=60)   # per item
```

### 4.2 ⚠️ Three unit/semantics traps (all verified)

**Trap 1 — the unit is MINUTES.**

```
   key=custom-ttl   ttl_minutes=10 expires_at=2026-10-28 15:40:00+00:00
   key=ephemeral    ttl_minutes=60 expires_at=2026-10-28 16:30:00+00:00
```

The column is literally named `ttl_minutes`. `ttl=60` means **60 minutes**.
(It is an `INT` column, so sub-minute TTLs round to 0.)

**Trap 2 — `refresh_on_read=True` (the default) means SLIDING expiration.**

Reading an item resets its expiry:

```sql
UPDATE store SET expires_at = NOW() + (s.ttl_minutes || ' minutes')::interval
```

So a memory that is read every hour with `default_ttl=60` **never expires**.
For "invalid after 24h" semantics you need `refresh_on_read=False`.

**Trap 3 — expired items are still returned until they are swept.**

With `omit_expired=False` (the default), `search()` keeps returning expired
items until `sweep_ttl()` deletes them. Set `omit_expired=True` to hide them
immediately.

### 4.3 The sweeper

```python
store.sweep_ttl()            # one pass; returns the number of rows deleted
store.start_ttl_sweeper()    # background thread, every sweep_interval_minutes
store.stop_ttl_sweeper()
```

Verified:

```
1c. sweep_ttl() removes expired items
   rows rewound: 2
   before sweep: []
   sweep_ttl() removed: 2
   after sweep : []
```

Run `start_ttl_sweeper()` in one place at startup (your API process, or a
dedicated worker). **Not** in every request handler — the sweeper is
idempotent, but you'd still be creating threads per request.

---

## 5. Checkpoint threads have no TTL — sweep them yourself

`PostgresSaver` has **no TTL**. You write the retention job.

```python
def purge_old_threads(saver, conn, days: int) -> int:
    cutoff = now() - timedelta(days=days)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT thread_id FROM checkpoints "
            "WHERE checkpoint->>'ts' < %s",
            (cutoff,),
        )
        stale = [r[0] for r in cur.fetchall()]
    for tid in stale:
        saver.delete_thread(tid)
    return len(stale)
```

Run it from cron / Celery beat / a K8s CronJob.

### 5.1 Or trim instead of delete

```python
saver.prune([thread_id], strategy="keep_latest")   # keep the conversation,
                                                   # drop the history
```

**A sensible default policy:**

| Data | Policy |
|---|---|
| Active conversation | keep the last N checkpoints (prune daily) |
| Inactive conversation (< 30 days) | keep everything |
| Inactive conversation (> 90 days) | `delete_thread` |
| Long-term memories | TTL 6–12 months, or until the user deletes them |

---

## 6. "Delete this user" — the GDPR delete

> A user is not one table. A user is **five things**:

```
   1. checkpoint threads   (their conversations)
   2. long-term memories  (the store)
   3. vector rows         (your RAG collection)
   4. traces              (Langfuse)
   5. your own app tables (users, billing, sessions, ...)
```

Delete 1–4 and leave 5, and you have not deleted the user.

### 6.1 Threads and memories (runnable)

```python
def delete_user(user_id: str) -> dict:
    counts = {}

    # 1. threads
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT thread_id FROM checkpoints WHERE thread_id LIKE %s",
            (f"{user_id}%",),
        )
        threads = [r[0] for r in cur.fetchall()]
    for t in threads:
        saver.delete_thread(t)
    counts["threads"] = len(threads)

    # 2. memories - every namespace under the user's prefix
    with PostgresStore.from_conn_string(url, index=index) as store:
        n = 0
        for ns in store.list_namespaces(prefix=("users", user_id)):
            for item in store.search(ns):
                store.delete(item.namespace, item.key)
                n += 1
        counts["memories"] = n
    ...
```

Note: you must iterate `list_namespaces(prefix=...)` — a single
`search(("users", user_id))` only covers one level. The store can hold
`("users", alice, "memories")` **and** `("users", alice, "projects")`.

Verified in `ex19`:

```
  1. threads found for user-to-delete: ['user-to-delete-thread-0', ...]
     -> deleted
  2. memories found: 2 -> deleted
```

### 6.2 Vector rows (your RAG collection)

```python
with PGVector.from_config(...) as vstore:
    ids = vstore.get(ids={"user_id": user_id})["ids"]
    vstore.delete(ids=ids)
```

The key is that **every vector row carries the user's id as metadata**.
If it doesn't, you can't delete it later. Design that in from day one:

```python
doc = {"id": str(uuid4()), "content": chunk, "metadata": {"user_id": user_id}}
```

### 6.3 Langfuse traces

Verified against **langfuse 5.0.4**:

```python
from langfuse import Langfuse

client = Langfuse(public_key=..., secret_key=..., base_url=...)

# 4a. find the trace ids for this user.
#     Langfuse v5 has NO api.trace.list() - you find observations
#     (which carry their trace_id) and filter there:
obs = client.api.observations.get_many(user_id=user_id, limit=100)
trace_ids = {o.trace_id for o in obs.data if o.trace_id}

# 4b. delete them. This cascades to observations, scores and events.
client.api.trace.delete_multiple(trace_ids=list(trace_ids))
client.flush()

# single trace:
client.api.trace.delete(trace_id="...")
```

**Tag every Langfuse trace with the user id** (as `user_id` or `session_id`)
so this lookup is exact.

### 6.4 Your own tables

```sql
DELETE FROM app_users WHERE id = %s;
DELETE FROM app_sessions WHERE user_id = %s;
DELETE FROM app_billing WHERE user_id = %s;
-- optionally keep an anonymised tombstone for audit:
INSERT INTO deleted_users (id, deleted_at) VALUES (%s, now());
```

### 6.5 Return counts and log them

```python
return counts   # {'threads': 3, 'memories': 12, 'vectors': 40, 'traces': 7, ...}
```

When the user asks *"did you actually delete everything?"*, you answer with
data, not a promise.

---

## 7. The complete lifecycle checklist

| # | Task | Mechanism | Cadence |
|---|---|---|---|
| 1 | Trim active thread history | `saver.prune(..., "keep_latest")` | daily |
| 2 | Delete inactive threads | `saver.delete_thread(...)` | daily |
| 3 | Expire short-lived memories | `store` TTL + `start_ttl_sweeper()` | continuous |
| 4 | Sweep expired store items | `store.sweep_ttl()` | continuous |
| 5 | Delete a user's data on request | the `delete_user()` function | on demand |
| 6 | Delete traces | Langfuse API | on demand |
| 7 | Delete vectors | your vector store | on demand |

---

## 8. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| User id in the middle of the namespace | cross-tenant leak | tenant id first, always |
| Building namespaces with f-strings at call sites | one omission = a leak | a `ns()` helper |
| Searching from the user level, not the tenant level | leak | search from the tenant |
| `ttl=60` meaning "60 seconds" | items expire 60× too fast | it's MINUTES |
| `refresh_on_read=True` for a "valid for 24h" rule | never expires | set `refresh_on_read=False` |
| Forgetting `omit_expired=True` | stale memories served | set it |
| `saver.prune()` in every request | DB churn | one scheduled job |
| Deleting only the store on a GDPR request | traces and vectors survive | the five-part checklist |
| Not tagging traces with the user id | can't find them to delete | set `user_id` on every trace |
| No isolation test | leaks appear in prod, not CI | assert isolation in tests |

---

## 9. Checkpoint yourself

- [ ] I can explain the difference between convention-based and structural
      isolation.
- [ ] I know the namespace ordering rule and the f-string mistake.
- [ ] I know the store TTL unit is minutes and can explain sliding expiry.
- [ ] I know that checkpoint threads have no TTL.
- [ ] I can list the five things a "delete user" must remove.
- [ ] I know the Langfuse v5 API for finding and deleting traces.

---

## 🎓 Phase 8 complete

You have now covered the full persistence surface:

| Lesson | Module | Core idea |
|---|---|---|
| [L15](./L15-checkpoints-and-threads.md) | M54 | checkpoints, threads, PostgresSaver |
| [L16](./L16-state-inspection-and-time-travel.md) | M55 | `get_state`, `update_state`, replay |
| [L17](./L17-durability-retries-and-crash-recovery.md) | M56 | durability, retries, idempotency |
| [L18](./L18-hitl-interrupts.md) | M57 | `interrupt()`, `Command(resume=…)` |
| [L19](./L19-hitl-production-approval-flows.md) | M58 | approval queues, sweeper, audit |
| [L20](./L20-short-term-memory.md) | M59 | trimming, context editing, summarization |
| [L21](./L21-long-term-memory-store-and-langmem.md) | M60 | the Store, pgvector, langmem |
| [L22](./L22-multi-tenant-and-data-lifecycle.md) | M61 | isolation, TTL, GDPR delete |

**Where to go next**

- **Phase 9 — deployment**: LangGraph Platform / `langgraph dev` / `langgraph.json`,
  streaming modes, and running the graph server behind FastAPI.
- **Phase 10 — evaluation & observability**: Langfuse tracing wired into
  LangGraph, datasets, online evals, and regression testing your checkpoints.
