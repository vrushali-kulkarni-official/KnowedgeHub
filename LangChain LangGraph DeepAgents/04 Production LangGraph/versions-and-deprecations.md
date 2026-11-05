# 90 — Versions and deprecations reference

**Verified on 2026-11-04** against PyPI and against the *installed* packages
(introspection, not memory). Everything here was checked.

---

## 1. The versions this course is built on

| Package | Version | Why this version |
|---|---|---|
| `langgraph` | **1.2.19** | Latest stable. 1.2 introduced the v3 event protocol and `DeltaChannel`. |
| `langgraph-checkpoint` | **4.3.1** | Pulled in by `langgraph`. |
| `langgraph-checkpoint-postgres` | **3.2.0** | The production checkpointer. |
| `langgraph-checkpoint-sqlite` | **3.1.3** | Zero-dependency local runs. |
| `langgraph-checkpoint-mongodb` | **0.5.1** | Alternative (Mongo). |
| `langgraph-sdk` | **0.4.12** | Client for the Agent Server. |
| `langchain` | **1.4.8** | v1 line: `create_agent`, middleware. |
| `langchain-core` | **1.7.4** | The shared runtime. |
| `langchain-community` | **0.4.2** | Community integrations. |
| `langchain-google-genai` | **4.4.2** | Gemini via LangChain (no vendor SDK in app code). |
| `langsmith` | **0.14.17** | Required by `langchain`. |
| `langfuse` | **5.1.0** | FOSS observability. **Requires Python ≥ 3.11.** |
| `deepagents` | **0.7.32** | The multi-agent layer. |
| `testcontainers` | **4.15.0** | Real Postgres in CI. |
| `sse-starlette` | **3.6.0** | SSE responses for FastAPI. |
| `psycopg` / `psycopg-pool` | **3.3.8** / **3.3.3** | Postgres driver (psycopg 3). |
| `sqlalchemy` | **2.1.8** | The runs table. |
| `fastapi` | **0.162.0** | The HTTP layer. |
| `pydantic` | **2.14.2** | Models. |
| `httpx` | **0.28.1** | HTTP client (and `TestClient`'s engine). |
| Python | **3.11+** | Required by `langfuse` 5.x and by `Deep Agents`. |

Re-check everything with:

```bash
uv pip list | grep -E "langgraph|langchain|langfuse|deepagents|testcontainers"
```

---

## 2. The master table: old vs modern

### 2.1 LangGraph streaming

| Old / legacy | Status | Modern replacement |
|---|---|---|
| `graph.stream(..., stream_mode="updates")` returning raw data | **Legacy shape** (still the default) | `graph.stream(..., stream_mode="updates", version="v2")` → `StreamPart` |
| `graph.stream(..., stream_mode=["a","b"])` returning `(mode, data)` tuples | **Legacy shape** | `version="v2"` → every chunk is `{"type","ns","data"}` |
| `subgraphs=True` returning `(namespace, data)` tuples | **Legacy shape** | `version="v2"` → namespace lives in `chunk["ns"]` |
| `astream_events(version="v1")` | **Deprecated** | `version="v2"` (default) or `version="v3"` |
| — | **New (beta)** | `astream_events(version="v3")` — typed projections |
| `stream_mode="messages"` payload `(chunk, metadata)` | **Current** | unchanged in v2 |

`version="v2"` requires **LangGraph ≥ 1.1**.
`version="v3"` requires **LangGraph ≥ 1.2** and emits
`LangChainBetaWarning: The v3 streaming protocol on Pregel is experimental.`

Verified by introspection:

```python
>>> inspect.signature(Pregel.stream)
(input, config=None, *, context=None, stream_mode=None, print_mode=(),
 output_keys=None, interrupt_before=None, interrupt_after=None,
 durability=None, control=None, subgraphs=False, debug=None,
 version: Literal['v1','v2'] = 'v1', **kwargs)

>>> inspect.signature(Pregel.stream_events)
(input, config=None, *, version: Literal['v1','v2','v3'] = 'v2',
 transformers=None, **kwargs)
```

### 2.2 LangGraph agents

| Old | Status | Modern replacement |
|---|---|---|
| `from langgraph.prebuilt import create_react_agent` | **Deprecated** (LangGraph V1.0) | `from langchain.agents import create_agent` |
| `from langgraph.prebuilt import AgentStatePydantic` | **Deprecated** | `from langchain.agents import AgentState` |
| `AgentStateWithStructuredResponsePydantic` | **Deprecated** | `AgentState` in `langchain.agents` |

Exact warning emitted by `langgraph.prebuilt.create_react_agent`:

```
LangGraphDeprecatedSinceV10: create_react_agent has been moved to
`langchain.agents`. Please update your import to
`from langchain.agents import create_agent`.
Deprecated in LangGraph V1.0 to be removed in V2.0.
```

### 2.3 Checkpointers

| Old | Status | Modern replacement |
|---|---|---|
| `from langgraph.checkpoint.postgres import AsyncPostgresSaver` | **ImportError** — moved | `from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver` |
| `from langgraph.checkpoint.postgres import PostgresSaver` | **Current** | unchanged |
| `Interrupt.interrupt_id` | **Deprecated** (V1.0 → V2.0) | `Interrupt.id` |
| — | **New (beta)** | `DeltaChannel` (LangGraph ≥ 1.2) — incremental channel storage |

Exact warning:

```
LangGraphDeprecatedSinceV10: `interrupt_id` is deprecated. Use `id` instead.
Deprecated in LangGraph V1.0 to be removed in V2.0.
```

> The `AsyncPostgresSaver` move is a real trap: the top-level module still
> *looks* like it should have it, and the error is a bare `ImportError` with
> no hint.

### 2.4 LangChain core

| Old | Status | Modern replacement |
|---|---|---|
| `chat_model.dict()` | **Deprecated** (1.4.2 → 2.0.0) | `asdict()` (pydantic v2) |
| `llm.dict()` | **Deprecated** (1.4.2) | `asdict()` |
| `output_parser.dict()` | **Deprecated** (1.4.2) | `asdict()` |
| `prompt.dict()` | **Deprecated** (1.4.2) | `asdict()` |
| `prompt.save(path)` | **Deprecated** (since 1.2.21) | `dumpd`/`dumps` from `langchain_core.load`, `load`/`loads` to read back |

### 2.5 Gemini model IDs

Google deprecates model names aggressively. Verified against the official
models page on 2026-11-04:

| Model | Status | Use instead |
|---|---|---|
| `gemini-2.5-pro` | **Deprecated** — no longer selectable in AI Studio; API auto-routes from **2026-12-01** | `gemini-4-argon` (flagship) or `gemini-3.8-flash` |
| `gemini-2.5-flash` | **Deprecated** — same | `gemini-3.8-flash` (default) |
| `gemini-2.0-flash`, `gemini-2.0-pro`, `gemini-1.5-*` | **Retired** | — |
| `gemini-2.5-flash-lite` | **Not deprecated** | still served, but `gemini-3.5-flash-lite` is newer |
| **`gemini-3.8-flash`** | **Current — recommended default.** "Our most intelligent Flash model, engineered for long-horizon software engineering, autonomous agents, and complex enterprise workflows." | — |
| `gemini-3.6-flash` | Current — previous-generation Flash | — |
| `gemini-3.5-flash-lite` | Current — fastest, cheapest 3.5 | — |
| `gemini-3.1-flash-lite` | Current | — |
| `gemini-4-argon` | Current — Gemini 4 flagship reasoning, 1M context | — |
| `gemini-3-flash-preview` | Preview | — |
| `gemini-*-latest` aliases | Current, but hot-swapped | **Prefer a specific stable model** in production |

The course defaults to `gemini-3.8-flash` and *refuses* the deprecated IDs at
runtime:

```python
if model_id in DEPRECATED_GEMINI_MODELS:
    raise ValueError(f"{model_id!r} is deprecated by Google. ...")
```

### 2.6 Tooling

| Old | Status | Modern replacement |
|---|---|---|
| `from testcontainers.postgres import PostgresContainer` | **Deprecated** | `from testcontainers.community.postgres import PostgresContainer` |
| `PostgresContainer(driver="psycopg2")` (the default) | Wrong driver for LangGraph | `PostgresContainer(..., driver="psycopg")` → `postgresql+psycopg://` |

Exact warning:

```
DeprecationWarning: testcontainers.postgres is deprecated,
use testcontainers.community.postgres instead
```

### 2.7 LangGraph Platform / Agent Server

| Old belief | Status | Reality (2026-11-04) |
|---|---|---|
| "The standalone server runs in restricted *lite mode* without a licence key" | **Outdated** | The "lite mode" warning was **removed**. Servers validating with a LangSmith API key **already have every feature**. |
| "LangGraph Platform" | **Renamed** | **Agent Server** (the runtime) / **LangSmith Deployment** (the managed platform) |
| "LangGraph Server" | Renamed | Agent Server |
| "Self-hosting needs Enterprise" | **Partly true** | The *server* works with a free-tier LangSmith API key. **Self-hosting LangSmith itself** (the observability control plane) is an Enterprise add-on. |
| "You can run it on serverless" | **Warned against** | "Do not run standalone servers in serverless environments. Scale-to-zero may cause task loss." |
| "Docker Compose is the production path" | Warned against | Kubernetes + the maintained LangSmith Helm chart is the tested production path. |

---

## 3. API surface you should know (verified by introspection)

```python
from langgraph.types import (
    StreamPart, ValuesStreamPart, UpdatesStreamPart, MessagesStreamPart,
    CustomStreamPart, CheckpointStreamPart, TasksStreamPart, DebugStreamPart,
    Command, Interrupt, Durability,   # Durability = Literal['sync','async','exit']
)
from langgraph.stream import (
    ProtocolEvent, StreamChannel, StreamTransformer,
    GraphRunStream, AsyncGraphRunStream, SubgraphRunStream,
)
from langgraph.prebuilt import ToolCallTransformer
from langgraph.config import get_stream_writer
from langgraph.runtime import RunControl, Runtime
from langgraph.errors import GraphDrained, GraphInterrupt, InvalidUpdateError
```

### 3.1 The `StreamPart` union

```python
from langgraph.types import StreamPart
# A disjoint union discriminated on part["type"], so type checkers can narrow.
```

### 3.2 `RunControl` — cooperative draining (LangGraph ≥ 1.2)

```python
from langgraph.runtime import RunControl
from langgraph.errors import GraphDrained

control = RunControl()
control.request_drain("sigterm")
# ... later, from any thread:
if control.drain_requested:
    print(control.drain_reason)
```

Resume a drained run with `graph.invoke(None, config)` — same `thread_id`.

### 3.3 `Durability`

```python
from langgraph.types import Durability
# Literal['sync', 'async', 'exit']
```

### 3.4 The v3 run-stream object

```python
stream = graph.stream_events(input, version="v3")
# stream.messages  stream.values  stream.output  stream.subgraphs
# stream.interrupts  stream.interrupted  stream.extensions  stream.lifecycle
# stream.interleave("values", "messages", "subgraphs")
```

### 3.5 `langgraph_sdk` (client for the Agent Server)

```python
from langgraph_sdk import get_client
client = get_client(url="http://localhost:8123", api_key=None)
client.assistants  client.threads  client.runs  client.crons  client.store
```

`RunsClient` methods: `create`, `stream`, `join`, `join_stream`, `wait`,
`cancel`, `cancel_many`, `list`, `get`, `delete`, `create_batch`.

Notable `create()` parameters: `after_seconds` (background run),
`if_not_exists` (idempotency), `multitask_strategy`, `on_completion`,
`durability`, `webhook`, `checkpoint_during`, `stream_subgraphs`,
`stream_resumable`.

### 3.6 Langfuse v5

```python
from langfuse import get_client, observe, propagate_attributes
from langfuse.langchain import CallbackHandler

client = get_client()          # reads LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY
handler = CallbackHandler()
client.start_as_current_observation(name=..., type="agent", ...)
client.update_current_span(...)
client.score_current_trace(name=..., value=...)
client.create_score(trace_id=..., name=..., value=...)
client.get_trace_url(trace_id=...)
client.flush(); client.shutdown()
```

**Langfuse v5 requires `langchain-core>=1`** and Python ≥ 3.11.

### 3.7 Deep Agents

```python
from deepagents import create_deep_agent, SubAgent, CompiledSubAgent

agent = create_deep_agent(
    model=..., tools=[...], system_prompt=..., subagents=[...],
    skills=[...], memory=[...], backend=..., interrupt_on={...},
    response_format=..., checkpointer=..., store=..., name=...,
)
```

Subagents are **isolated by default** (they receive only the delegated task).
`mode="fork"` continues the parent's conversation but is **experimental**.

---

## 4. How to check for deprecations in your own code

```bash
# 1. Turn deprecation warnings into errors in CI - you find out on day one.
pytest -W error::DeprecationWarning

# 2. Or just look at the warnings:
pytest -W default

# 3. Find deprecated imports statically:
grep -rn "create_react_agent\|AgentStatePydantic\|interrupt_id" src/

# 4. Find deprecated LangGraph APIs:
grep -rn "langgraph.prebuilt import\|langgraph.checkpoint.postgres import" src/
```

The deprecation classes are:

```python
from langgraph.errors import LangGraphDeprecatedSinceV10   # LangGraph V1.0 deprecations
from langchain_core._api.deprecation import LangChainDeprecationWarning
from langchain_core._api.beta_decorator import LangChainBetaWarning
```

---

## 5. A "modern style" checklist

```python
# ✅ Modern LangGraph
from langchain.agents import create_agent              # not langgraph.prebuilt.create_react_agent
from langchain.agents import AgentState                # not AgentStatePydantic
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver   # not the top-level module
from langgraph.checkpoint.postgres import PostgresSaver            # sync is fine here
from langgraph.runtime import RunControl               # cooperative drain
from langgraph.config import get_stream_writer
from langgraph.types import Command, Interrupt, StreamPart
from langgraph.errors import GraphDrained, GraphInterrupt

graph.stream(payload, stream_mode=[...], version="v2")   # unified StreamPart
graph.stream_events(payload, version="v3")               # beta; know what you are doing

# ✅ Modern model access
model.model_dump()      # not .dict()
prompt.model_dump_json() # not .dict()

# ✅ Modern Gemini
init_chat_model("google_genai:gemini-3.8-flash")

# ✅ Modern testcontainers
from testcontainers.community.postgres import PostgresContainer
PostgresContainer("postgres:16-alpine", driver="psycopg")
```

---

## 6. How to stay current

The LangChain ecosystem moves fast. Three habits:

1. **Pin, then review monthly.** `uv pip compile` / a lockfile gives you
   reproducibility; review it monthly so you are not three majors behind.
2. **Read the changelog when you upgrade a minor version.** LangGraph's
   changelog lists breaking changes prominently (this is where the "lite mode
   removal" and the `FF_RESUME_DRAINED_RUNS` flag were announced).
3. **Watch the deprecation warnings in CI.** Turn them into errors and the
   upgrade notes write themselves.

```bash
# Upgrade safely in this project
uv pip install --upgrade langgraph langchain langfuse deepagents
python -m pytest tests/ -v -W error::DeprecationWarning
```
