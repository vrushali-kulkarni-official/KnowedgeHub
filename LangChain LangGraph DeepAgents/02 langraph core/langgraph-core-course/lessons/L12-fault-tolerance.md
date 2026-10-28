# L12 · Fault tolerance, timeouts and caching

> **Module M51 (part 3) · ~1.5h**
> Goal: make a graph survive the network being down — and stop wasting money
> calling the same expensive function twice.

---

## 1. The four levers

LangGraph 1.x gives you four per-node policies. All are passed to `add_node`:

```python
builder.add_node(
    "search_docs",
    search_docs,
    retry_policy=RetryPolicy(max_attempts=3, initial_interval=1.0),
    timeout=TimeoutPolicy(run_timeout=30.0, idle_timeout=10.0),
    cache_policy=CachePolicy(ttl=3600),
    error_handler=my_handler,
)
```

Or apply the same defaults to every node at once:

```python
builder.set_node_defaults(
    retry_policy=RetryPolicy(max_attempts=3),
    timeout=30.0,
)
```

Per-node values take precedence over the defaults.

---

## 2. `RetryPolicy`

```python
from langgraph.types import RetryPolicy

RetryPolicy(
    initial_interval=0.5,    # seconds before the first retry
    backoff_factor=2.0,      # multiply the interval each attempt
    max_interval=128.0,      # cap the interval
    max_attempts=3,          # total attempts (1 = no retry)
    jitter=True,             # randomise the interval (avoids thundering herds)
    retry_on=default_retry_on,   # which exceptions are retryable
)
```

**Verified:** a node that failed twice then succeeded, with
`max_attempts=5, initial_interval=0.05`, was called **3 times** and the
graph returned `{"x": "ok"}`.

With the **default** policy (`initial_interval=0.5`, `backoff_factor=2.0`),
three attempts take ≈ `0.5 + 1.0 = 1.5s` of waiting. **Verified: 1.47s.**
That is real wall-clock time your users will experience — set
`initial_interval` deliberately.

### What is retryable by default?

The default `retry_on` retries on a set of transient exceptions — connection
errors, timeouts, and similar. It does **not** retry on arbitrary
exceptions like `ValueError` or `KeyError`, because those are bugs, not
transient failures.

You can be explicit:

```python
RetryPolicy(retry_on=(ConnectionError, TimeoutError))
```

or use a predicate:

```python
def is_transient(exc: Exception) -> bool:
    return isinstance(exc, ConnectionError) or "429" in str(exc)

RetryPolicy(retry_on=is_transient)
```

### ⚠️ Never blindly retry an action node

If the node has a side effect (sending an email, charging a card, filing a
ticket), a retry can **duplicate** the side effect. Give it an idempotency
key, or do not retry it.

---

## 3. `TimeoutPolicy` and the simple `timeout=`

```python
from langgraph.types import TimeoutPolicy

TimeoutPolicy(
    run_timeout=30.0,     # hard wall-clock cap for the node
    idle_timeout=10.0,    # cap on time with NO progress
    refresh_on="auto",    # "auto" | "heartbeat"
)
```

Or the simple form:

```python
builder.add_node("slow", slow, timeout=30.0)             # seconds
builder.add_node("slow", slow, timeout=timedelta(minutes=2))
```

### `run_timeout` vs `idle_timeout`

| | Meaning |
|---|---|
| `run_timeout` | total wall-clock time for the node, whatever it is doing |
| `idle_timeout` | time since the last sign of progress |

`idle_timeout` is what you want for LLM calls: a long generation is fine as
long as tokens keep arriving, but a hung connection is not.

For `idle_timeout` to work, long-running work must **emit progress**. In an
async workflow you can call:

```python
runtime.heartbeat()     # "I'm still alive"
```

> **Note:** timeouts are supported only for **async** workflows. Sync
> workflows cannot be safely cancelled in-process, so the timeout is not
> enforced there.

When a timeout fires, LangGraph raises `NodeTimeoutError`. It deliberately
does **not** inherit from the builtin `TimeoutError` (an `OSError`
subclass), so the default `RetryPolicy` treats it as retryable.

---

## 4. `error_handler` — the compensation branch

When a node keeps failing even after retries, `error_handler` lets you route
to a recovery path.

```python
from langgraph.errors import NodeError
from langgraph.types import Command, RetryPolicy

def payment_error_handler(state: State, error: NodeError) -> Command:
    return Command(
        update={"status": f"compensated: {error.error}"},
        goto="finalize",
    )

builder.add_node(
    "charge_payment",
    charge_payment,
    retry_policy=RetryPolicy(max_attempts=3, retry_on=ConnectionError),
    error_handler=payment_error_handler,
)
```

### ⚠️ The `NodeError` is injected by TYPE ANNOTATION

This is the single most important detail, and it is easy to get wrong.

```python
# ✅ CORRECT - annotate the parameter
def handler(state: State, error: NodeError) -> Command: ...

# ❌ WRONG - no annotation, so it is never injected
def handler(state, error): ...      # TypeError: handler() missing 1
                                    # required positional argument: 'error'
```

**Verified:** the annotated handler received
`error.node == 'boom'` and `error.error` being the original `ValueError`,
and the graph routed to the recovery node and completed.

`NodeError` is a frozen dataclass with two fields:

| Field | Type | Meaning |
|---|---|---|
| `node` | `str` | the name of the node that failed |
| `error` | `BaseException` | the exception it raised |

> **Requires `langgraph >= 1.2`.** This is a recent addition, so older
> tutorials will not show it.

### The saga pattern

`error_handler` is what makes compensation (saga) workflows possible: if
step 3 fails, run the compensating action for step 2, then route to a
"failed" terminal state.

---

## 5. `CachePolicy` — don't pay twice

```python
from langgraph.types import CachePolicy

CachePolicy(
    key_func=default_cache_key,   # hashes the node's input with pickle
    ttl=3600,                     # seconds; None = never expires
)
```

### ⚠️ The cache backend must be supplied at `compile()`

This is the gotcha. `CachePolicy` on a node does nothing on its own:

```python
graph = builder.compile(cache=InMemoryCache())     # <- REQUIRED
```

```python
from langgraph.cache.memory import InMemoryCache
```

**Verified:** with `compile(cache=InMemoryCache())` and
`CachePolicy(ttl=120)`, three invocations with the same input called the
underlying function **once**. Changing the input caused a miss. Without
`compile(cache=...)`, the same three invocations called the function three
times — the policy was silently inert.

### What gets cached

The **node's input** determines the cache key (by default, a pickle hash of
the input). The node's *output* is what is stored. So:

- A pure function of its input → cache hits perfectly.
- A function that depends on external state (a database, the clock) → the
  cache will serve a stale answer. Use a custom `key_func` or do not cache.

### Custom key functions

```python
def key_by_question(state) -> str:
    return state["question"]

CachePolicy(key_func=key_by_question, ttl=600)
```

### What NOT to cache

- **Action nodes** (side effects). A cached "send email" means the email is
  never sent.
- Nodes whose output depends on time or external mutable state.
- Nodes with non-deterministic outputs you actually want fresh.

---

## 6. Choosing a strategy per node type

| Node type | Retry | Timeout | Cache | Error handler |
|---|---|---|---|---|
| LLM step | ✅ 3 attempts | ✅ run + idle | ✅ short TTL | route to a fallback answer |
| Data fetch (HTTP) | ✅ | ✅ idle | ✅ | return a degraded result |
| Vector search | ✅ | ✅ | ✅ | empty result set |
| Action (email, payment) | ⚠️ only with idempotency | ✅ | ❌ | compensation (saga) |
| Pure computation | ❌ pointless | ❌ | ✅ | let it bubble up |
| User input | n/a | n/a | ❌ | n/a |

> **The official guidance from the LangGraph docs** matches this table:
> transient errors → retry policy; LLM-recoverable errors → store the error in
> state and loop back; user-fixable errors → `interrupt()`; unexpected errors
> → let them bubble up so you can debug them.

---

## 7. The "let the LLM recover" pattern

Sometimes the best recovery is to let the model see the error and try again:

```python
def execute_tool(state: State) -> Command:
    try:
        result = run_tool(state["tool_call"])
        return Command(update={"tool_result": result}, goto="agent")
    except ToolError as e:
        # the model sees the error and can adjust
        return Command(update={"tool_result": f"Tool error: {e}"}, goto="agent")
```

This is a *different* mechanism from `error_handler`: here the graph keeps
going and the LLM adapts, rather than the framework routing to a fixed
recovery branch.

---

## 8. Checklist

- [ ] I know the four per-node policies and that `set_node_defaults` applies
      them graph-wide.
- [ ] I can configure a `RetryPolicy` and understand the backoff cost in
      wall-clock terms.
- [ ] I know `timeout=` works for async workflows only, and that
      `NodeTimeoutError` is retryable by default.
- [ ] I can write an `error_handler` with a **type-annotated** `NodeError`
      parameter.
- [ ] I know `compile(cache=...)` is required for `CachePolicy` to do
      anything.
- [ ] I never cache an action node and never blindly retry one.

---

**Next → [L13 · `langgraph dev` and LangSmith Studio](./L13-dev-and-studio.md)**
— the local Agent Server, the visual debugger, and replaying from any step.
