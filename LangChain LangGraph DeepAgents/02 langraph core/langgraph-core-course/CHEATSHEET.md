# Cheat sheet — Phase 7 LangGraph Core

> Verified against `langgraph 1.2.17`, `langchain 1.4.7`, `langchain-core 1.7.0`
> on 2026-10-26.

---

## 1. Deprecated → current

| Old (deprecated / gone) | Current | Notes |
|---|---|---|
| `config_schema=` on `StateGraph` / `@entrypoint` | `context_schema=` | Deprecated in v0.6, **removal in v2.0**. Warning class `LangGraphDeprecatedSinceV10`. |
| `config["configurable"]["user_id"]` | `runtime.context.user_id` | `configurable` is for *framework* config (`thread_id`) only. |
| `langgraph.checkpoint.memory.MemorySaver` | `InMemorySaver` | `MemorySaver` still works as an alias. |
| `from langchain_core.messages import add_messages` | `from langgraph.graph.message import add_messages` | The core export **no longer exists** in langchain-core 1.7. |
| `from langgraph.prebuilt import create_agent` | `from langchain.agents import create_agent` | `langgraph.prebuilt` now exposes `create_react_agent`, `ToolNode`, `tools_condition`, `InjectedState`, `InjectedStore`, `ToolRuntime`, `ValidationNode`. |
| `retry=` on `@entrypoint` | `retry_policy=` | `LangGraphDeprecatedSinceV05`. |
| "LangGraph Studio" | **LangSmith Studio** | Renamed late 2025. |
| "LangGraph Platform" | **LangSmith Deployment** | Renamed late 2025. |
| "the LangGraph API server" | **Agent Server** | Renamed late 2025. |
| `langfuse.callback` | `langfuse.langchain` (CallbackHandler) | v2-era import is gone. |
| `graph.get_graph().channels` | `graph.channels` | It is on the **compiled** graph, not on `get_graph()`. |
| `snapshot.state` | `snapshot.values` | `StateSnapshot` exposes `values`, not `state`. |
| `add_sequence(["a", "b"])` | `add_sequence([node_a, node_b])` | Bare **name strings** raise `TypeError`. |

### Gemini model names (as of Oct 2026)

| Model | Status |
|---|---|
| `gemini-3.8-flash` | ✅ **GA — the default recommendation** |
| `gemini-3.6-flash` | ✅ stable |
| `gemini-3.5-flash-lite` | ✅ stable, cheapest |
| `gemini-3.1-flash-lite` | ✅ stable |
| `gemini-3.1-pro-preview` | ✅ the Pro tier (still preview) |
| `gemini-3.7-flash` | ⛔ **deprecated 2026-10-08** → auto-routed to 3.8-flash |
| `gemini-3.5-flash` | ⛔ deprecated → auto-routed to 3.6-flash |
| `gemini-3-pro-preview` | ⛔ shut down → use `gemini-3.1-pro-preview` |

---

## 2. Imports you will actually use

```python
# graph
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.graph.message import add_messages

# types
from langgraph.types import Command, Send, Interrupt, RetryPolicy, CachePolicy, TimeoutPolicy
from langgraph.types import interrupt, Overwrite
from langgraph.runtime import Runtime

# errors
from langgraph.errors import GraphRecursionError, NodeError, NodeTimeoutError, InvalidUpdateError

# persistence & memory
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.cache.memory import InMemoryCache
from langgraph.managed import RemainingSteps

# functional API
from langgraph.func import entrypoint, task

# config helpers
from langgraph.config import get_config, get_store, get_stream_writer

# messages
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.messages import RemoveMessage

# langchain 1.x
from langchain.agents import create_agent
```

---

## 3. The five-line skeleton

```python
from langgraph.graph import StateGraph, START, END

builder = StateGraph(State)
builder.add_node("a", node_a)
builder.add_edge(START, "a")
builder.add_edge("a", END)
graph = builder.compile()
graph.invoke(input)
```

---

## 4. `StateGraph` API (v1.2)

```python
StateGraph(
    state_schema,
    context_schema=None,
    *,
    input_schema=None,
    output_schema=None,
)
```

| Method | Signature (key parts) |
|---|---|
| `add_node` | `(name, action, *, defer=False, metadata=None, input_schema=None, retry_policy=None, cache_policy=None, error_handler=None, destinations=None, timeout=None)` |
| `add_edge` | `(start_key: str \| list[str], end_key: str)` |
| `add_conditional_edges` | `(source, path, path_map=None)` |
| `add_sequence` | `(nodes: Sequence[callable \| (name, callable)])` |
| `set_entry_point` / `set_finish_point` | `(key)` |
| `set_node_defaults` | `(*, retry_policy=None, cache_policy=None, error_handler=None, timeout=None)` |
| `compile` | `(checkpointer=None, *, cache=None, store=None, interrupt_before=None, interrupt_after=None, debug=False, name=None, transformers=None)` |

---

## 5. State & reducers

```python
from typing import Annotated, NotRequired
from typing_extensions import TypedDict
import operator

class State(TypedDict):
    messages: Annotated[list, add_messages]      # chat history
    events:   Annotated[list[str], operator.add]  # append-only
    draft:    str                                  # overwrite (default)
    count:    int                                  # overwrite (default)
    maybe:    NotRequired[list[str]]               # optional
```

| Want | Write |
|---|---|
| Append | `Annotated[list[str], operator.add]` |
| Chat messages | `Annotated[list, add_messages]` |
| Merge dicts | `Annotated[dict, my_merge]` |
| Replace regardless of reducer | `Overwrite(value)` |
| JSON-friendly replace | `{"__overwrite__": value}` |

**Custom reducer contract:** `(left, right) -> value`; deterministic; handle
`left` empty and `right` None; do not mutate `left`; order-tolerant if used
in parallel branches.

---

## 6. Routing

```python
# conditional edges
builder.add_conditional_edges("src", router, {"label": "node_name"})

# Command
from typing import Literal
def node(state) -> Command[Literal["a", "b"]]:
    return Command(update={"k": v}, goto="a")

# dynamic fan-out
def router(state) -> list[Send]:
    return [Send("worker", {"item": i}) for i in state["items"]]
builder.add_conditional_edges("split", router, ["worker"])
```

> **The `Send` diagram gotcha:** a node reachable *only* via `Send` is
> omitted from the static Mermaid graph, along with all its downstream edges.
> Adding a "documentation-only" static edge causes an **extra execution**.
> Use the path_map form above to keep the diagram honest.

---

## 7. Configuration & runtime context

| Concern | Where |
|---|---|
| Conversation id | `config["configurable"]["thread_id"]` |
| Max supersteps | `config["recursion_limit"]` |
| Tracing | `config["tags"]`, `config["metadata"]`, `config["callbacks"]` |
| Your app's values | **`context=`** → `runtime.context` |
| Per-run mutable data | **state** |
| Cross-conversation memory | **store** → `runtime.store` |
| Text for the model | the prompt (build it in the node) |

```python
@dataclass
class Ctx:
    user_id: str
    model: Any = None

builder = StateGraph(State, context_schema=Ctx)
graph.invoke(inp, config, context={"user_id": "u-1"})
```

---

## 8. Persistence

```python
from langgraph.checkpoint.memory import InMemorySaver          # tests
from langgraph.checkpoint.sqlite import SqliteSaver            # local dev
from langgraph.checkpoint.postgres import PostgresSaver        # production

graph = builder.compile(checkpointer=InMemorySaver())
config = {"configurable": {"thread_id": "t1"}}
```

| Call | Purpose |
|---|---|
| `graph.get_state(config)` | current state (`snapshot.values`, `.next`, `.metadata`) |
| `graph.get_state_history(config)` | the checkpoint timeline |
| `graph.update_state(config, values)` | write to a thread |
| `graph.invoke(inp, target.config)` | time travel: re-run from a checkpoint |

Durability: `"sync"` (default-safe) · `"async"` · `"exit"`.

---

## 9. Streaming modes

`Literal['values', 'updates', 'checkpoints', 'tasks', 'debug', 'messages', 'custom']`

```python
for chunk in graph.stream(inp, stream_mode="updates"): ...
for mode, chunk in graph.stream(inp, stream_mode=["updates", "messages"]): ...
for ns, chunk in graph.stream(inp, stream_mode="updates", subgraphs=True): ...
```

Custom events: `runtime.stream_writer({...})` → `stream_mode="custom"`.

---

## 10. Fault tolerance

```python
from langgraph.types import RetryPolicy, CachePolicy, TimeoutPolicy
from langgraph.errors import NodeError

RetryPolicy(initial_interval=0.5, backoff_factor=2.0, max_interval=128.0,
            max_attempts=3, jitter=True, retry_on=default_retry_on)
TimeoutPolicy(run_timeout=None, idle_timeout=None, refresh_on="auto")
CachePolicy(key_func=default_cache_key, ttl=None)

def handler(state: State, error: NodeError) -> Command:   # NOTE the annotation
    return Command(update={"status": "recovered"}, goto="fallback")
```

⚠️ `compile(cache=InMemoryCache())` is **required** for `CachePolicy` to do
anything.

---

## 11. Error → cause table

| Error | Usual cause |
|---|---|
| `ValueError: Graph must have an entrypoint...` | no `add_edge(START, ...)` (raised at **compile** time) |
| `GraphRecursionError` | a cycle with no exit (not a missing `END`) |
| `InvalidUpdateError: Can receive only one value per step` | two nodes in one superstep wrote the same key with no reducer |
| `TypeError: No synchronous function provided to "x"` | `invoke()` on a graph containing an async node |
| `ValueError: Checkpointer requires ... thread_id` | a checkpointer is present but no `thread_id` |
| `RuntimeError: Called get_config outside of a runnable context` | calling a `@task` outside a workflow |
| `TypeError: handler() missing 1 required positional argument: 'error'` | `error_handler` without a `NodeError` annotation |
| `TypeError: Expected a Runnable, callable or dict` | `add_sequence(["a", "b"])` with bare strings |

---

## 12. Numbers worth remembering (all verified)

| Fact | Value |
|---|---|
| Default `recursion_limit` | 10000 |
| Supersteps a simple cycle gets | exactly `recursion_limit` node executions |
| `RemainingSteps` initial value | `recursion_limit - 1` |
| `RemainingSteps` safe stop threshold | `<= 2` (a margin of 1 still raises) |
| Default retry wall-clock (3 attempts) | ~1.5–2.6s (jitter on) |
| Two 0.5s parallel nodes | 0.51s (truly concurrent) |
| Three 0.5s nodes, blocking inside async | 1.50s (serialised, 3× slower) |
| `add_messages` import | `langgraph.graph.message` |

---

## 13. The three questions to ask about any state key

1. Does it need to survive across steps? → **state**
2. Does it need to survive across conversations? → **store**
3. Is it fixed for the run and read-only? → **context**
4. Is it text for the model? → **the prompt**, built in the node

And one rule for reducers:

> A reducer is a **merge rule**. If two nodes mean different things by the
> same write, decide the semantics on purpose — do not let an accidental
> `operator.add` decide for you.
