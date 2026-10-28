# L17 · Durability, Retries & Crash Recovery

> **Phase 8 — Persistence, Memory & Human-in-the-Loop**
> Module M56 · *Durability, retries & crash recovery*
>
> Run: `python examples/ex07_durability_modes.py`
> Run: `python examples/ex08_retry_idempotency.py`

---

## 0. The three questions this lesson answers

1. **Durability**: when exactly is my state written to disk?
2. **Retries**: what happens when a node throws?
3. **Crash recovery**: my process died mid-run. What now?

And the punchline that ties them together:

> **There is no exactly-once.** LangGraph gives you *at-least-once* execution
> of a node. If a node's side effect must not repeat, **you** have to make the
> side effect idempotent.

---

## 1. Durability modes

`durability` is a **per-call** argument on `invoke` / `stream` / `ainvoke` /
`astream`. It is **not** a `compile()` argument.

```python
graph.invoke(inputs, config, durability="sync")
```

| Mode | When the checkpoint is written | Guarantees | Cost |
|---|---|---|---|
| `"sync"` | **before** the next step starts | every completed step is durable | extra latency per step |
| `"async"` | **in the background**, while the next step runs | every completed step is *usually* durable | ~free |
| `"exit"` | once, when the run ends (success, error, or interrupt) | only the final state | cheapest |

`"async"` is the default.

### 1.1 Measured, not guessed

`ex07_durability_modes.py` runs a 3-node graph under each mode and counts the
checkpoints left behind:

```
durability=sync   checkpoints=5
durability=async  checkpoints=5
durability=exit   checkpoints=1
```

Read that carefully:

- **`sync` and `async` both give you a checkpoint per superstep.** The
  difference is *when* the write lands, not *whether* it happens.
- **`exit` gives you exactly one checkpoint for the whole run.**

### 1.2 What each mode actually buys you

**`exit`** — you get the final answer and nothing else.
- ✅ Fastest. No per-step I/O.
- ❌ **You cannot time-travel mid-run.** No history to replay.
- ❌ **You cannot resume a crash.** If the process dies at step 2 of 5, the
  work is gone.
- ❌ Cannot pause for HITL mid-run (well — it *does* persist on interrupt exit,
  but you lose the intermediate checkpoints).
- Use for: long-running, cheap-to-repeat background jobs where only the final
  result matters.

**`async`** — the default.
- ✅ Full history, time travel, HITL.
- ⚠️ Small window: if the process is **hard-killed** while a checkpoint write
  is in flight, that write may be lost. The step before it is still there.
- Use for: most production graphs.

**`sync`** — the safest.
- ✅ Every step is committed before the next one starts. A hard kill loses at
  most the *currently executing* step.
- ❌ One extra round-trip to the DB per step.
- Use for: money movement, one-shot side effects, anything where a duplicated
  side effect costs more than the latency.

### 1.3 ⚠️ Durability does NOT give you exactly-once

Durability controls **when graph state is persisted**. It says nothing about
your node's external side effects.

> If a side effect commits but the node/task completion is not durably
> recorded, recovery may execute the node again. Use an operation-level
> idempotency key or a transactional deduplication record where possible.

This is not a LangGraph quirk — it is the nature of distributed systems. §4
shows how to actually solve it.

### 1.4 Choosing

| Situation | Mode |
|---|---|
| "the answer at the end is what matters" | `exit` |
| general-purpose production graph | `async` (default) |
| charging a card / sending an email | `sync` |
| you need to replay a production thread | `async` or `sync` (`exit` gives you nothing to replay) |

---

## 2. Retries: `RetryPolicy`

Attach a retry policy **per node**:

```python
from langgraph.types import RetryPolicy

builder.add_node(
    "flaky",
    flaky,
    retry_policy=RetryPolicy(
        initial_interval=0.5,     # seconds before the first retry
        backoff_factor=2.0,       # each wait = previous * factor
        max_interval=128.0,       # cap on the wait
        max_attempts=3,           # total attempts (1 = no retry)
        jitter=True,              # randomise to avoid thundering herds
        retry_on=default_retry_on, # which exceptions are retryable
    ),
)
```

### 2.1 What gets retried by default

`default_retry_on` (from `langgraph.types`) retries:

- `ConnectionError` (including `httpx.ConnectError`)
- `httpx.HTTPStatusError` with a **5xx** status
- `requests.HTTPError` with a **5xx** status
- **anything not in the "definitely a bug" list**

And does **NOT** retry:

`ValueError`, `TypeError`, `ArithmeticError`, `ImportError`, `LookupError`,
`NameError`, `SyntaxError`, `RuntimeError`, `ReferenceError`,
`StopIteration`, `StopAsyncIteration`, `OSError`.

That list is a heuristic: those exceptions usually mean *your code is wrong*,
so retrying just burns time and money.

Verified in `ex08`:

```
1. RetryPolicy: transient failures are retried
   attempts: 3 result: ['succeeded on attempt 3']

2. Default retry_on does NOT retry programming errors
   raised: ValueError: bug in my code
   attempts: 1
```

### 2.2 Custom `retry_on`

```python
def my_retry(exc: Exception) -> bool:
    return isinstance(exc, (TimeoutError, json.JSONDecodeError))

builder.add_node("x", x, retry_policy=RetryPolicy(max_attempts=5, retry_on=my_retry))
```

`retry_on` accepts an exception class, a tuple of classes, or a callable
taking the exception and returning a bool.

### 2.3 `error_handler` (newer)

`add_node` also accepts `error_handler=`:

```python
def handle(exc: Exception) -> dict:
    return {"result": f"failed gracefully: {exc}"}

builder.add_node("risky", risky, error_handler=handle)
```

Use it when a node fails in a way you want to *handle in the graph* (record
the error in state and route to a fallback node) rather than crash the run.

### 2.4 Retry storms

`jitter=True` (the default) randomises the wait. Without jitter, 100 workers
retrying the same flaky dependency at the same instant will hammer it again
at the same instant. **Leave jitter on.**

Also set `max_attempts` deliberately. The default is 3 — a reasonable default,
but your node might tolerate more (transient DB failover) or less (a paid
API call you don't want to repeat).

---

## 3. Crash recovery: what happens when the process dies?

Let's simulate it. `ex08` has a node that performs a side effect and *then*
raises:

```python
def risky(state):
    charge(op_key, amount)        # 💸 money moves
    raise ValueError("simulated crash after side effect")
```

```
3. Crash mid-run: the node runs AGAIN on resume
   run failed with: ValueError: simulated crash after side effect
   effects so far: ['charge(payment-100) -> PERFORMED', '*** killed ***']
   state after crash: {'amount': 100, 'log': []}

4. Resume: the node re-runs -> DUPLICATE side effect
   effects on resume: ['charge(payment-100) -> PERFORMED', '*** killed ***']
```

### 3.1 The resume mechanics

```python
graph.invoke(None, cfg)     # resume: no new input, continue from last checkpoint
```

- The last **successful** checkpoint is the resume point.
- The node that was executing when the crash happened **runs again from the
  top**.
- Its side effect happens again.

### 3.2 What "at-least-once" means here

```
attempt 1: node runs → side effect commits → 💥 process dies
attempt 2: node runs again → side effect commits again → 💸💸
```

The checkpoint system protects your **state**. It cannot protect your
**external world**.

### 3.3 The three re-execution paths (memorise these)

| Path | What re-runs |
|---|---|
| crash / failure recovery | the failed node, from the top |
| `interrupt()` resume | the node containing the interrupt, from the top (L18) |
| replay / fork from an old checkpoint | every node after that point (L16) |

In all three, **your code may run more than once**. Design for it.

---

## 4. The fix: idempotency keys + a UNIQUE constraint

This is the only real answer to *"the customer got double-charged"*.

### 4.1 The pattern

```python
def charge(op_key: str, amount: int) -> bool:
    """Charge exactly once for `op_key`."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO payments (op_key, amount) VALUES (%s, %s) "
            "ON CONFLICT (op_key) DO NOTHING RETURNING op_key",
            (op_key, amount),
        )
        return cur.fetchone() is not None
```

The magic is that the **de-duplication check and the effect are the same
statement, in the same transaction**. If the process dies after the INSERT
commits, the retry sees the row and skips.

### 4.2 Verified end-to-end

```
5. FIX: idempotency key + UNIQUE constraint -> exactly once
   run failed with: ValueError: simulated crash after side effect
   effects: ['charge(payment-100) -> PERFORMED', ...]

   resume failed with: ValueError: simulated crash after side effect
   effects on resume: ['charge(payment-100) -> SKIPPED (duplicate)', ...]

   rows in payments table: [('payment-100', 100)]
```

**One row.** The retry hit the UNIQUE constraint and skipped.

### 4.3 Designing the key

| ❌ Bad key | ✅ Good key |
|---|---|
| `uuid4()` generated inside the node | a deterministic id derived from the business entity |
| `f"charge-{time.time()}"` | `f"charge-{order_id}"` |
| `f"charge-{user_id}"` (one charge per user ever) | `f"charge-{order_id}-{attempt_kind}"` |

The key must be **stable across retries** and **unique per business
operation**. Store it in graph state so it survives a crash:

```python
class State(TypedDict):
    op_key: str      # generated ONCE, at the start, persisted in state
```

### 4.4 The other options

| Pattern | When |
|---|---|
| Idempotency key + UNIQUE constraint | ✅ default choice |
| Transactional outbox (write to an outbox table in the same tx; a worker delivers) | when the effect is on another service |
| Natural idempotency (`INSERT ... ON CONFLICT DO UPDATE` to the same row) | when "setting" a value rather than adding |
| Reconciliation (query the provider before retrying) | when the provider has no idempotency support |
| Exactly-once is impossible | for external APIs without a dedup mechanism — you get *at-least-once* + reconciliation |

> If the external service (Stripe, a bank) supports idempotency keys, **use
> theirs**. Pass your `op_key` as their idempotency key. That moves the
> guarantee to the party that actually holds the money.

---

## 5. A production checklist

- [ ] `durability="sync"` for anything that moves money or sends irreversible
      external effects; `"async"` elsewhere.
- [ ] A `RetryPolicy` on every node that talks to the network.
- [ ] `retry_on` narrowed to your actual transient failures.
- [ ] `max_attempts` chosen deliberately per node.
- [ ] Every side-effecting node has a deterministic idempotency key, stored in
      graph state.
- [ ] The idempotency key is enforced by a database constraint, not an
      application-level check.
- [ ] Your API is safe to call twice with the same request id.
- [ ] You have a way to find and repair "the effect committed but the
      checkpoint didn't" cases (a reconciliation job).

---

## 6. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| `durability="exit"` + you want time travel | no history to replay | use `async`/`sync` |
| Assuming `sync` prevents duplicate charges | it does not | idempotency keys |
| Retrying `ValueError` | infinite loop, no progress | narrow `retry_on` |
| Generating the idempotency key inside the node | new key on every retry | generate once, persist in state |
| `retry_on` catches everything | you retry your own bugs | narrow it |
| No `max_attempts` tuning | 3 retries on a slow endpoint | tune per node |

---

## 7. Checkpoint yourself

- [ ] I can state what `sync`, `async` and `exit` each write.
- [ ] I know `sync` and `async` both give one checkpoint per superstep.
- [ ] I know durability does **not** give exactly-once.
- [ ] I know which exceptions `default_retry_on` refuses to retry.
- [ ] I can explain the idempotency-key + UNIQUE-constraint pattern.
- [ ] I know the three re-execution paths.

**Next → [L18: HITL part 1 — interrupts](./L18-hitl-interrupts.md)**
