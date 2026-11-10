# CHEATSHEET — Phase 10 (Multi-Agent Systems)

Everything below was **verified by running it** against langgraph 1.2.20 /
langchain 1.4.9 on 2026-11-05.

---

## 1. Current vs deprecated

| ❌ old / deprecated | ✅ current | why |
|---|---|---|
| `langgraph.prebuilt.create_react_agent` | `langchain.agents.create_agent` | the prebuilt one is marked deprecated in its own docstring |
| `langgraph-supervisor` (0.0.31, 2025-11-19) | the **subagents pattern** (`create_agent` worker wrapped as a `@tool`) | the package is ~1 year stale and pinned to the pre-v1 API |
| `langgraph-swarm` (0.1.0, 2025-12-04) | build handoffs yourself with `Command(graph=Command.PARENT, goto=...)` | it targets the deprecated `create_react_agent` |
| `langgraph.types.Command` without `graph=` for cross-graph jumps | `Command(graph=Command.PARENT, ...)` | plain `goto` resolves inside the nested agent |
| `tool_call_id: InjectedToolCallId` (bare) | `tool_call_id: Annotated[str, InjectedToolCallId]` | the bare class is not recognised as an injection |
| passing state dicts between agents | shared state + `input_schema` / the store | dict passing defeats context isolation |
| `recursion_limit` as the only loop guard | `ModelCallLimitMiddleware` + visit counter + explicit `recursion_limit` | `create_agent` ships with 9999 |

### Still current, and worth using

| API | use |
|---|---|
| `langchain.agents.create_agent` | the agent factory — use this everywhere |
| `langgraph.types.Command` / `Send` | all routing |
| `langchain.agents.middleware.*` | limits, summarisation, HITL, PII, retries |
| `langgraph.prebuilt.InjectedState` / `InjectedStore` / `ToolRuntime` | giving tools access to state, the store and config |
| `langchain.agents.structured_output.ProviderStrategy` | native structured output (Gemini supports it) |
| `langfuse.langchain.CallbackHandler` | multi-agent trace trees |
| `langgraph.managed.RemainingSteps` | swarm loop guards |

### Gemini model line (verified 2026-11-05)

| model ID | stage | context | max out | $/1M in/out | use for |
|---|---|---|---|---|---|
| `gemini-4-argon` | Stable | 1,048,576 | 65,536 | $2 / $10 (intro) | hardest reasoning, the final answer |
| `gemini-3.8-flash` | Stable | 1,048,576 | 65,536 | $0.75 / $3.75 (intro) | specialist reasoning |
| `gemini-3.6-flash` | Stable | 1,048,576 | 65,536 | $0.75 / $3.75 | general |
| `gemini-3.5-flash-lite` | Stable | 1,048,576 | 65,536 | **$0.30 / $2.50** | routing, summarisation, subagents |

Retired / auto-routed — do not target:
`gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.5-flash-lite`,
`gemini-3.5-flash`, `gemini-3.7-flash`.

```python
from langchain.chat_models import init_chat_model

strong = init_chat_model("google_genai:gemini-3.8-flash")
cheap  = init_chat_model("google_genai:gemini-3.5-flash-lite")
best   = init_chat_model("google_genai:gemini-4-argon")
```

---

## 2. The imports you will actually use

```python
from langchain.agents import create_agent, AgentState
from langchain.agents.middleware import (
    ModelCallLimitMiddleware, ToolCallLimitMiddleware,
    SummarizationMiddleware, ContextEditingMiddleware,
    HumanInTheLoopMiddleware,
)
from langchain.agents.structured_output import ProviderStrategy

from langchain_core.tools import tool, InjectedToolCallId
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from langgraph.graph import StateGraph, START, END
from langgraph.types import Command, Send, RetryPolicy
from langgraph.prebuilt import InjectedState, InjectedStore, ToolRuntime
from langgraph.managed import RemainingSteps
from langgraph.store.memory import InMemoryStore
from langgraph.checkpoint.memory import InMemorySaver

from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
```

---

## 3. The agent-as-tool adapter

```python
from typing import Annotated
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.types import Command

def agent_as_tool(name: str, description: str, agent):
    """Expose a create_agent to another agent as a tool."""
    @tool(f"ask_{name}", description=description)
    def ask(task: str) -> str:
        result = agent.invoke({"messages": [HumanMessage(content=task)]})
        return result["messages"][-1].content      # STRING out
    return ask

def handoff_tool(target: str, description: str):
    """Hand CONTROL to another node (Command.PARENT)."""
    @tool(f"hand_off_to_{target}", description=description)
    def hand_off(
        task: str,
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        return Command(
            graph=Command.PARENT,                  # REQUIRED inside create_agent
            goto=target,
            update={"messages": [
                ToolMessage(content=task, tool_call_id=tool_call_id,
                            name=f"hand_off_to_{target}")
            ]},
        )
    return hand_off
```

---

## 4. The four verified gotchas

### 4.1 `Command(goto=)` inside `create_agent` does nothing

```
Task tools with path ('__pregel_push', 0, False) wrote to unknown channel
branch:to:billing, ignoring it.
```
→ add `graph=Command.PARENT`.

### 4.2 `Command(update=...)` from a tool needs a `ToolMessage`

```
ValueError: Expected to have a matching ToolMessage in Command.update for
tool 'write_note', got: [AIMessage(content='NOTE: hi', ...)].
```

### 4.3 `InjectedToolCallId` needs `Annotated`

```
Error invoking tool 'hand_off' with kwargs {} with error:
 tool_call_id: Field required
```

### 4.4 `create_agent` ships with `recursion_limit = 9999`

```python
# langchain/agents/factory.py
config: RunnableConfig = {"recursion_limit": 9_999}
```
→ always pass `{"recursion_limit": N}` and add `ModelCallLimitMiddleware`.

---

## 5. The four state-filter rules

| rule | behaviour |
|---|---|
| `input_schema` on a node | filters the state on a **normal edge** |
| a `Send` payload | **bypasses** `input_schema` — delivered verbatim |
| `Command(graph=Command.PARENT, update=...)` | filtered by the **parent** schema; unknown keys dropped **silently** |
| `create_agent` | always sees the **entire** `messages` transcript |

Plus the **echo trap**: a node that is a compiled agent writes its whole
state back to the parent — so append-reducer lists in the agent's
`state_schema` get duplicated. Keep them out; use merge reducers inside
agents.

---

## 6. Reducers

| want | reducer | gotcha |
|---|---|---|
| accumulate | `lambda a, b: a + b` | return **only the new items** |
| merge dicts | `lambda a, b: {**a, **b}` | safe inside agent schemas |
| sum counters | `lambda a, b: a + b` (ints) | each branch writes the **increment** |
| last write wins | *(no annotation)* | two writers in one step → `InvalidUpdateError` |

---

## 7. Structured output

```python
from pydantic import BaseModel, Field

class Route(BaseModel):
    """Which specialist handles this?"""
    specialist: Literal["researcher", "billing"]
    reason: str = Field(description="why")

agent = create_agent(model, tools=[], response_format=Route)
route = agent.invoke({"messages": [("user", q)]})["structured_response"]
```

* `ToolStrategy` (default): the synthetic tool is named after the **schema
  class** — `class Route` → the model must call a tool named `Route`.
* `ProviderStrategy`: the provider's native JSON mode (Gemini supports it).
* If the model returns prose instead of the tool call, the agent **silently
  retries until the recursion limit**. Validate it yourself.

---

## 8. Debugging commands

```python
# what changed, per node, including nested agents
app.stream(inputs, stream_mode=["updates"], subgraphs=True)
#   -> (namespace_tuple, mode, payload)

# the full state after each step
app.stream(inputs, stream_mode="values")

# what the model actually said
app.stream(inputs, stream_mode="messages", subgraphs=True)

# task-level input / result / error
app.stream(inputs, stream_mode=["tasks"], subgraphs=True)
```

---

## 9. Langfuse, offline

```python
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

exporter = InMemorySpanExporter()
provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(exporter))
lf = Langfuse(public_key="pk", secret_key="sk",
              base_url="http://localhost:9999", tracer_provider=provider)
handler = CallbackHandler()

app.invoke(inputs, {"callbacks": [handler]})
spans = exporter.get_finished_spans()      # assert on these in tests
```

Always `create_agent(..., name="researcher")` — otherwise every span is
called `LangGraph`.

---

## 10. Production defaults

```python
LIMIT = {"recursion_limit": 30}

create_agent(model, tools=tools, name="researcher", middleware=[
    ModelCallLimitMiddleware(thread_limit=8, exit_behavior="end"),
    ToolCallLimitMiddleware(thread_limit=20, exit_behavior="end"),
])

g.add_node("call_api", call_api,
           retry_policy=RetryPolicy(max_attempts=3, retry_on=(TimeoutError,)))
```

Tools should catch their own exceptions and return an error **string** —
a `ToolInvocationError` is recoverable, any other exception kills the graph.
