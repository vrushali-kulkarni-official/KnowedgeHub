# Module 04 — Tool Calling & the ReAct Pattern

## Prerequisites

- Modules 02 and 03 (state, edges, the LLM-as-router idea)

## Why this module matters

Tools turn an LLM from a text generator into an **actor**. The ReAct loop is the canonical agent pattern: think → act → observe → repeat. Almost every useful agent you've ever heard of is a ReAct loop on top of something (memory, retrieval, code execution, browser control).

This module is where your graph becomes a real agent.

## Learning objectives

By the end of this module you can:

1. Define tools with the `@tool` decorator and the `BaseTool` class.
2. Bind tools to a model and inspect `tool_calls`.
3. Use `ToolNode` to execute tool calls.
4. Build the full ReAct loop in ~15 lines.
5. Handle tool errors gracefully (with `handle_tool_errors`).
6. Use parallel tool calls and `Send` for fan-out.
7. Design tool schemas that the model can call reliably.

---

## 4.1 Tool definitions

### 4.1.1 The `@tool` decorator

```python
from langchain_core.tools import tool

@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    # ...
    return f"Sunny, 22°C in {city}."
```

The decorator reads:
- Function name → tool name.
- Docstring → tool description (the model uses this to decide when to call).
- Type hints → argument schema.
- Return type → output schema.

**The docstring is the prompt.** Write it like you're telling another LLM when to use this tool.

### 4.1.2 The `BaseTool` class

For tools that need state, configs, or async:

```python
from langchain_core.tools import BaseTool
from pydantic import Field

class WeatherTool(BaseTool):
    name: str = "get_weather"
    description: str = "Get current weather for a city."
    api_key: str = Field(...)

    def _run(self, city: str) -> str:
        return call_weather_api(city, self.api_key)

    async def _arun(self, city: str) -> str:
        return await call_weather_api_async(city, self.api_key)
```

### 4.1.3 Structured input with Pydantic

When args are complex, define a schema:

```python
from pydantic import BaseModel, Field

class SearchQuery(BaseModel):
    query: str = Field(..., description="Search query string")
    top_k: int = Field(5, description="Number of results to return")

@tool(args_schema=SearchQuery)
def search_docs(query: str, top_k: int = 5) -> list[dict]:
    """Search the document store."""
    ...
```

### 4.1.4 Returning rich content

Tools can return strings, dicts, lists, or content blocks:

```python
from langchain_core.documents import Document

@tool
def search_docs(query: str) -> list[Document]:
    """Search the document store."""
    return [Document(page_content="...", metadata={"source": "..."})]
```

Returning `Document` objects (or structured content) is preferred over strings when you'll pipe the result into another step (e.g. RAG).

---

## 4.2 Binding tools to a model

```python
from app.llm import get_llm

llm = get_llm()
llm_with_tools = llm.bind_tools([get_weather, search_docs])

resp = llm_with_tools.invoke([HumanMessage(content="Weather in Tokyo?")])
resp.tool_calls
# [{'name': 'get_weather', 'args': {'city': 'Tokyo'}, 'id': 'call_abc'}]
```

Two key things on `AIMessage`:
- `tool_calls`: a list of dicts the model wants executed.
- `tool_call_id`: ties a tool result back to the call.

If the model doesn't need tools, `tool_calls` is empty and the response is in `content`.

---

## 4.3 `ToolNode`: the executor

```python
from langgraph.prebuilt import ToolNode

tool_node = ToolNode([get_weather, search_docs])
```

Internally, `ToolNode` reads the last `AIMessage.tool_calls`, runs each, and returns a list of `ToolMessage`s keyed by `tool_call_id`.

To wire it into a graph:

```python
builder.add_node("tools", tool_node)
```

That's the whole API.

---

## 4.4 The full ReAct loop

```python
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import ToolNode
from langchain_core.messages import HumanMessage
from app.llm import get_llm

tools = [get_weather, search_docs]
llm = get_llm().bind_tools(tools)

def agent(state: MessagesState):
    return {"messages": [llm.invoke(state["messages"])]}

def should_continue(state: MessagesState) -> str:
    last = state["messages"][-1]
    if last.tool_calls:
        return "tools"
    return END

g = (
    StateGraph(MessagesState)
    .add_node("agent", agent)
    .add_node("tools", ToolNode(tools))
    .add_edge(START, "agent")
    .add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    .add_edge("tools", "agent")
    .compile()
)

result = g.invoke({"messages": [HumanMessage(content="Weather in Tokyo and search for travel tips.")]})
for m in result["messages"]:
    m.pretty_print()
```

That's the agent. `agent → tools → agent → tools → ... → END`.

---

## 4.5 Error handling in tools

`ToolNode` can be configured to handle tool errors gracefully:

```python
ToolNode(tools, handle_tool_errors=True)
```

Now if a tool raises, the `ToolMessage` contains the error string and the model can retry or change strategy.

For more control, pass a function:

```python
def handle_error(e: Exception) -> str:
    return f"Tool failed: {e!r}. Try a different approach."

ToolNode(tools, handle_tool_errors=handle_error)
```

**Production tip:** Always handle tool errors. Tools fail — network, APIs, JSON parsing, you name it. Unhandled tool errors crash the graph.

---

## 4.6 Parallel tool calls

Modern models can request **multiple** tool calls in one response:

```python
resp.tool_calls   # len > 1
```

`ToolNode` runs them in parallel by default. Each becomes a `ToolMessage`. The model sees all results in the next turn.

**Watch out:** if your tool isn't thread-safe, parallel calls will break it. Mark stateful tools with care or wrap them with a lock.

---

## 4.7 Tool design for the model

The model's *only* signal for "should I call this tool?" is the name, description, and args schema. Optimize for that.

### 4.7.1 Naming

- ✅ `get_weather`, `search_docs`, `send_email`
- ❌ `tool1`, `do_stuff`, `handle`

### 4.7.2 Description

The description is the prompt. Include:
- **What** the tool does.
- **When** to use it.
- **What NOT** to use it for (if ambiguous with another tool).

```python
@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city.
    
    Use this when the user asks about weather conditions, temperature, or
    forecasts for a specific location. Do NOT use for historical climate data.
    """
```

### 4.7.3 Argument descriptions

```python
@tool
def search_docs(query: str, top_k: int = 5) -> list[Document]:
    """Search the internal document store.
    
    Args:
        query: The natural language search query. Be specific.
        top_k: Number of results to return. Max 20.
    """
```

### 4.7.4 Few-shot in the description

```python
@tool
def calculate(a: float, op: str, b: float) -> float:
    """Perform a basic arithmetic operation.
    
    Example: calculate(a=2, op='+', b=3) returns 5.
    Valid ops: '+', '-', '*', '/'.
    """
```

---

## 4.8 ToolNode as a router

You can also use `ToolNode` with `route_tool_call` to fork by tool name:

```python
from langgraph.prebuilt import tools_condition
```

`tools_condition` is the prebuilt router: returns `"tools"` if there are tool calls, else `END`. Equivalent to the `should_continue` in 4.4 but shorter.

---

## 4.9 Building a real ReAct agent with the LLM-as-router

Putting it all together with proper error handling, max iterations, and structured logging:

```python
class State(MessagesState):
    iterations: Annotated[int, operator.add] = 0

def agent(state: State) -> dict:
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response], "iterations": 1}

def route(state: State) -> str:
    if state["iterations"] > 15:
        return END
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    return END

g = (
    StateGraph(State)
    .add_node("agent", agent)
    .add_node("tools", ToolNode(tools, handle_tool_errors=True))
    .add_edge(START, "agent")
    .add_conditional_edges("agent", route, {"tools": "tools", END: END})
    .add_edge("tools", "agent")
    .compile()
)
```

Now you have a production-shaped ReAct agent.

---

## 4.10 Common tool pitfalls

| Pitfall | Fix |
|---|---|
| Tool description too vague | Treat description as the prompt |
| Tool returns unstructured string | Return documents / structured data |
| Tool raises uncaught exception | `handle_tool_errors=True` |
| State-mutating tool in parallel call | Wrap with lock, or design stateless |
| Tool with side effect (email, payment) without HITL | Use `interrupt` (Module 06) |
| Tool schema missing required arg | Test with the model: it should call it correctly |

---

## Hands-on project

**Goal:** Build a multi-tool research agent.

1. Define four tools: `search_web` (mock), `search_docs` (mock), `get_weather` (mock), `calculate` (real, safe).
2. Build the ReAct loop with `ToolNode`, `handle_tool_errors=True`, and a 10-step cap.
3. Test prompts:
   - "What's 2+2?" → no tool needed
   - "Weather in Paris?" → weather tool
   - "Search for X, then weather in Paris, then 5*5" → multiple tools, parallel
4. Add a `final_answer` extractor: after `END`, run a small "summary" LLM call to produce a clean response.

## Exercises

1. **Test what happens** when a tool raises (no `handle_tool_errors`). What does the model see? Now enable error handling. What's the difference?
2. **Make a tool that requires HITL** (e.g. `send_email`). Implement it without HITL first. See what happens. (We'll properly do HITL in Module 06.)
3. **Write 3 tool descriptions** that are bad. Then rewrite them. Compare model behavior.
4. **Parallel call challenge:** make a tool that's NOT thread-safe (e.g. increments a counter). Run a prompt that triggers 3 parallel calls. What's the bug? Fix it.
5. **Add streaming** to the agent (peek at Module 07 if you need a hint).

## Production checklist

- [ ] All tools have descriptive names and clear docstrings.
- [ ] All tools either return structured data or have explicit string contracts.
- [ ] `ToolNode` is created with `handle_tool_errors=True` (or a custom handler).
- [ ] Max iterations guard is in place.
- [ ] Side-effecting tools are flagged for HITL treatment (Module 06).
- [ ] No tools read from / write to global state without thinking about concurrency.

## Key takeaways

- Tools = `@tool` decorator + good docstrings + a real implementation.
- `ToolNode` is the executor. It pairs `tool_calls` with `tool_results` by id.
- The ReAct loop is `agent → tools → agent → ...` with a router reading `tool_calls`.
- Tool errors must be handled. Always.
- The model's only signal for tool use is the schema. Write it like a prompt.

## Resources

- LangChain tools: https://python.langchain.com/docs/how_to/custom_tools/
- `ToolNode` reference: https://langchain-ai.github.io/langgraph/reference/prebuilt/#langgraph.prebuilt.tool_node.ToolNode
- ReAct paper: https://arxiv.org/abs/2210.03629 (worth skimming)
