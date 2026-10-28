# CHEATSHEET — Phase 8

Everything on one page. Verified against the versions in `README.md`.

---

## 1. Imports that actually work

```python
# ❌ these top-level namespaces are EMPTY
from langgraph.checkpoint import PostgresSaver        # ImportError
from langgraph.store import PostgresStore             # ImportError

# ✅ always use the full sub-path
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.redis import RedisSaver
from langgraph.checkpoint.base import BaseCheckpointSaver

from langgraph.store.postgres import PostgresStore
from langgraph.store.postgres.aio import AsyncPostgresStore
from langgraph.store.memory import InMemoryStore
from langgraph.store.base import BaseStore, Item, SearchItem, TTLConfig, IndexConfig
from langgraph.store.base import GetOp, PutOp, SearchOp, ListNamespacesOp

from langgraph.types import interrupt, Command, RetryPolicy, Durability
from langgraph.types import GraphOutput, Interrupt, StateSnapshot, Send
from langgraph.config import get_store, get_config
from langgraph.runtime import get_runtime
from langgraph.func import entrypoint, task
from langgraph.errors import GraphInterrupt, GraphBubbleUp

from langchain.agents import create_agent
from langchain.agents.middleware import (
    ContextEditingMiddleware, SummarizationMiddleware, HumanInTheLoopMiddleware,
    ModelRetryMiddleware, ToolRetryMiddleware, ModelCallLimitMiddleware,
    PIIMiddleware, TodoListMiddleware,
)
from langchain.agents.middleware.context_editing import ClearToolUsesEdit
```

---

## 2. Current vs. deprecated

| ❌ Old / deprecated | ✅ Current | Since |
|---|---|---|
| `raise NodeInterrupt(value)` | `interrupt(value)` | **1.0** (`LangGraphDeprecatedSinceV10`) |
| `out["__interrupt__"]` | `out.interrupts` with `version="v2"` | legacy shape, still works |
| `interrupt_before`/`interrupt_after` for HITL | `interrupt()` | static ones = debugging only |
| `from langgraph.checkpoint import X` | `from langgraph.checkpoint.postgres import X` | namespaces are empty |
| `from langgraph.store import X` | `from langgraph.store.postgres import X` | namespaces are empty |
| `saver.copy_thread(a, b)` | copy the rows yourself | **still `NotImplementedError`** |
| `from langchain.prebuilt import create_react_agent` | `from langchain.agents import create_agent` | 1.0 |
| `langgraph.prebuilt.chat_agent_executor` | `langchain.agents.create_agent` | 1.0 |
| `langgraph.memory` | `langgraph.checkpoint.*` / `langgraph.store.*` | 1.0 |
| `text-embedding-004` (Gemini API) | `gemini-embedding-001` | deprecated Jan 2026 |
| `gemini-2.5-flash` for new projects | `gemini-3.8-flash` / `gemini-3.5-flash-lite` | Google recommends the newer ones |
| `langmem` unpinned | `langmem==0.0.30` | still pre-1.0 |

Not deprecated, but often misunderstood:

| Thing | Reality |
|---|---|
| `interrupt_before` / `interrupt_after` | **supported**, not deprecated — but they are *debugging* breakpoints, not HITL |
| `create_memory_store_manager` | current; langmem is just pre-1.0 |
| `durability="async"` | the current default |

---

## 3. The compiled-graph API

```python
graph.get_state(config)                      # -> StateSnapshot
graph.aget_state(config)
graph.get_state_history(config, limit=None, before=None, filter=None)
graph.update_state(config, values, as_node=None, task_id=None)   # -> new config
graph.aupdate_state(...)

graph.invoke(input, config, durability="async", version="v2")
graph.stream(input, config, stream_mode="values", durability="async")
graph.ainvoke(input, config)
```

### `StateSnapshot` fields

```
values  next  config  metadata  created_at  parent_config  tasks  interrupts
```

### `metadata["source"]`

```
"input" | "loop" | "update" | "fork"
```

### `GraphOutput` (version="v2")

```python
out.value        # the state
out.interrupts   # tuple[Interrupt]
```

`Interrupt(value=..., id=..., response_schema=...)`

---

## 4. Checkpointers

| Class | Import | Async | TTL | Notes |
|---|---|---|---|---|
| `InMemorySaver` | `langgraph.checkpoint.memory` | ❌ | ❌ | tests |
| `PostgresSaver` | `langgraph.checkpoint.postgres` | ✅ (`.aio`) | ❌ | production |
| `SqliteSaver` | `langgraph.checkpoint.sqlite` | ✅ | ❌ | local |
| `RedisSaver` | `langgraph.checkpoint.redis` | ✅ | ✅ | **community**; needs Redis Stack |

```python
with PostgresSaver.from_conn_string(DB_URL) as saver:
    saver.setup()                       # idempotent
    graph = builder.compile(checkpointer=saver)

saver.prune([thread_ids], strategy="keep_latest")
saver.delete_thread(thread_id)
```

Tables: `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`,
`checkpoint_migrations`.

---

## 5. Durability modes

| Mode | Writes | Use for |
|---|---|---|
| `"sync"` | every step, **before** the next starts | money, one-shot effects |
| `"async"` | every step, in the background (**default**) | most production graphs |
| `"exit"` | once, at the end | long cheap jobs, no time travel |

Per-call argument. **Not** a `compile()` argument.
Controls *checkpoint timing* — **not** exactly-once side effects.

---

## 6. Retries

```python
from langgraph.types import RetryPolicy

RetryPolicy(
    initial_interval=0.5,
    backoff_factor=2.0,
    max_interval=128.0,
    max_attempts=3,
    jitter=True,
    retry_on=default_retry_on,   # or an exception class / tuple / callable
)

builder.add_node("x", x, retry_policy=RetryPolicy(max_attempts=5))
builder.add_node("x", x, retry_policy=RetryPolicy(retry_on=my_fn))
builder.add_node("x", x, error_handler=handle_exception)
```

`default_retry_on` retries `ConnectionError`, HTTP 5xx, and anything not in
`{ValueError, TypeError, ArithmeticError, ImportError, LookupError, NameError,
SyntaxError, RuntimeError, ReferenceError, StopIteration, StopAsyncIteration,
OSError}`.

---

## 7. HITL

```python
from langgraph.types import interrupt, Command

def node(state):
    answer = interrupt({"question": "...", "options": ["yes", "no"]})
    return {"decision": answer}

# pause
out = graph.invoke(inp, cfg, version="v2")
out.interrupts            # tuple[Interrupt]

# resume
graph.invoke(Command(resume="yes"), cfg, version="v2")
graph.invoke(Command(resume={interrupt_id: "yes"}), cfg, version="v2")

# structured answers
from pydantic import BaseModel
class Decision(BaseModel):
    approve: bool
    reason: str
interrupt({"question": "?"}, response_schema=Decision)

# edit before resuming
graph.update_state(cfg, {"amount": 10})
```

### Paused-thread detection

```python
snap = graph.get_state(cfg)
if snap.next and snap.interrupts:
    ...  # waiting on a human
```

### Functional API

```python
from langgraph.func import entrypoint, task

@task
def prepare() -> str: ...

@task
def gate() -> str:
    return interrupt({"question": "?"})

@entrypoint(checkpointer=saver)
def workflow(x): ...
```

⚠️ The `@entrypoint` body re-runs on resume; completed `@task`s do **not**.

### Agent tool approval

```python
from langchain.agents.middleware import HumanInTheLoopMiddleware

HumanInTheLoopMiddleware(
    interrupt_on={"send_email": True, "delete_file": True},
    interrupt_mode="batched",     # default; "per_call" planned as next default
)

# batched answer
Command(resume={"decisions": [{"type": "approve"},
                              {"type": "reject", "message": "no"}]})
# per_call answer
Command(resume={interrupt_id: {"type": "approve"}})
```

Decision types: `approve` · `reject` · `edit` · `respond`.

---

## 8. The Store

```python
store.put(namespace, key, value, index=None, ttl=None)
store.get(namespace, key)
store.search(prefix, query=None, filter=None, limit=10, offset=0)
store.delete(namespace, key)
store.batch([PutOp(...), GetOp(...), SearchOp(...), ListNamespacesOp(...)])
store.list_namespaces(prefix=None)
```

### PostgresStore + semantic search

```python
from langgraph.store.postgres import PostgresStore
from langgraph.store.postgres.base import PostgresIndexConfig
from langchain_google_genai import GoogleGenerativeAIEmbeddings

embed = GoogleGenerativeAIEmbeddings(model="gemini-embedding-001", ...)
index = PostgresIndexConfig(dims=3072, embed=embed, fields=["content"])

with PostgresStore.from_conn_string(DB_URL, index=index) as store:
    store.setup()
```

Needs **pgvector**. `dims` must match the model's output size.

### Inside a node

```python
from langgraph.config import get_store
store = get_store()
```

### TTL

```python
from langgraph.store.base import TTLConfig

TTLConfig(default_ttl=1440,      # MINUTES
          sweep_interval_minutes=5,
          refresh_on_read=False,  # False = absolute expiry (default True = sliding)
          omit_expired=True)      # hide expired rows immediately

store.sweep_ttl()                # one pass
store.start_ttl_sweeper()        # background thread
store.stop_ttl_sweeper()
```

---

## 9. langmem

```python
from langmem import (create_manage_memory_tool, create_search_memory_tool,
                     create_memory_store_manager, create_memory_manager,
                     create_thread_extractor)

manage = create_manage_memory_tool(
    namespace=("memories", "{langgraph_user_id}"),
    store=store, actions_permitted=("create", "update", "delete"))
search = create_search_memory_tool(namespace=("memories", "{langgraph_user_id}"),
                                   store=store)

manager = create_memory_store_manager(
    model, store=store, namespace=("memories", "{langgraph_user_id}"))
await manager.ainvoke({"messages": messages}, config=config)
```

⚠️ **Value-shape gotcha:** the tool writes `{"content": ...}`; the manager
expects `{"kind": ..., "content": ...}` and raises `KeyError: 'kind'` on
mismatch. Standardise the shape.

⚠️ **Tool names** the manager uses: `Memory`, `PatchDoc`,
`PatchFunctionErrors`.

---

## 10. Short-term memory

```python
from langchain_core.messages import trim_messages
trim_messages(messages, max_tokens=60, token_counter="approximate",
              strategy="last", include_system=True, start_on="human")

from langchain.agents.middleware import ContextEditingMiddleware
from langchain.agents.middleware.context_editing import ClearToolUsesEdit
ContextEditingMiddleware(edits=[ClearToolUsesEdit(trigger=100_000, keep=3,
                                                  clear_at_least=0,
                                                  exclude_tools=(),
                                                  placeholder="<cleared>")],
                         token_count_method="approximate")   # or "model"

from langchain.agents.middleware import SummarizationMiddleware
SummarizationMiddleware(model=cheap_model,
                        trigger=("messages", 30),   # or ("tokens", N) or ("fraction", f)
                        keep=("messages", 20),
                        trim_tokens_to_summarize=4000,
                        summary_prompt="...")
```

`("fraction", f)` needs `ChatModel(..., profile={"max_input_tokens": N})`.

| | Context editing | Summarization |
|---|---|---|
| Edits | the **request** | the **state** |
| Checkpoint keeps the full transcript | ✅ | ❌ |
| Loses | tool payloads | message content |

---

## 11. Multi-tenancy & lifecycle

```python
def ns(tenant_id, user_id, *rest):
    return ("tenant", tenant_id, "users", user_id, *rest)

def thread_id(tenant_id, conversation_id):
    return f"{tenant_id}:{conversation_id}"
```

Rules:
1. Tenant id **first** in every namespace.
2. Every search starts at the **tenant** level.
3. Never f-string a namespace at the call site.
4. Test isolation in CI.

### Retention

```python
saver.prune([thread_id], strategy="keep_latest")   # trim history
saver.delete_thread(thread_id)                     # remove the thread
store.sweep_ttl()                                  # remove expired memories
```

### GDPR delete — five places

```python
# 1. threads
saver.delete_thread(tid)
# 2. memories
for n in store.list_namespaces(prefix=("users", uid)):
    for item in store.search(n):
        store.delete(item.namespace, item.key)
# 3. vector rows
vstore.delete(ids=vstore.get(ids={"user_id": uid})["ids"])
# 4. Langfuse traces
obs = client.api.observations.get_many(user_id=uid, limit=100)
client.api.trace.delete_multiple(trace_ids=list({o.trace_id for o in obs.data}))
# 5. your own tables
```

---

## 12. Gemini reference (verified Oct 2026)

| Model | Context / output | Use |
|---|---|---|
| `gemini-3.8-flash` | 1,048,576 / 65,536 | main agent (GA) |
| `gemini-3.6-flash` | 1M / 64k | general Flash (GA) |
| `gemini-3.5-flash-lite` | 1M | summarization, extraction (GA) |
| `gemini-3.1-flash-lite` | 1M | cost-optimised (GA) |
| `gemini-3.1-pro-preview` | — | hardest reasoning (preview) |
| `gemini-embedding-001` | 128–3072 dims | embeddings (current) |
| `text-embedding-004` | 768 | ⚠️ deprecated for Gemini API |

```python
from langchain.chat_models import init_chat_model
model = init_chat_model("google_genai:gemini-3.8-flash")

from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

model = ChatGoogleGenerativeAI(
    model="gemini-3.8-flash",
    google_api_key=os.environ["GOOGLE_API_KEY"],
    profile={"max_input_tokens": 1_048_576},   # needed for ("fraction", f) triggers
)
```

---

## 13. The nine traps

1. `langgraph.checkpoint` / `langgraph.store` top-level namespaces are empty.
2. `durability="exit"` leaves you with **one** checkpoint — no time travel.
3. A node **restarts from the top** on interrupt-resume.
4. A thread has **one head**; forking moves it.
5. `copy_thread()` raises `NotImplementedError`.
6. The store's TTL is in **minutes**, and it **slides** by default.
7. langmem's tool and manager use **different value shapes**.
8. The Redis checkpointer needs **Redis Stack** (RedisJSON + RediSearch).
9. `("fraction", f)` triggers need a **model profile**.
