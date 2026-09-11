Everything is verified against the current docs (September 2026). Here's your complete lesson — from zero to advanced.

---

# Creating Tools in LangChain: The Complete Beginner→Advanced Guide

## 0. Setup & Mental Model

```bash
# With uv (since you already use it)
uv init my-tools-lesson && cd my-tools-lesson
uv add langchain langchain-core langchain-google-genai python-dotenv
```

Get a free API key from [Google AI Studio](https://aistudio.google.com) and put it in a `.env` file:

```
GOOGLE_API_KEY=your-key-here
```

**The mental model (read this first):** A "tool" in LangChain is just a **Pydantic model wrapping a function**. That's it. The Pydantic wrapper gives the function three things:

1. A **name** and **description** — plain text that gets sent to the LLM so it knows the tool exists and when to use it.
2. An **input schema** — auto-generated from your function's type hints, converted to JSON Schema, and sent to the LLM so it knows what arguments to pass.
3. A standardized **call interface** (`.invoke()`) — so agents, chains, and you can all call it the same way.

The LLM never runs your code. It only *decides* to call the tool and *proposes arguments*. Your Python code executes it.

---

## 1.1 Anatomy of a Tool

Every tool has exactly 5 parts:

| Part                  | What it is                            | Who consumes it                                   |
| --------------------- | ------------------------------------- | ------------------------------------------------- |
| `name`                | Unique identifier, e.g. `get_weather` | LLM + your code                                   |
| `description`         | When/why/how to use the tool          | **LLM** (this is prompt engineering!)             |
| `args_schema`         | Pydantic model describing arguments   | LLM (as JSON Schema) + validation of inputs       |
| The callable          | The actual Python function            | Your code (never the LLM directly)                |
| Return value contract | What the function returns             | Gets wrapped into a `ToolMessage` back to the LLM |

The **return value contract**: with the default `response_format="content"`, whatever you return becomes the `content` of a `ToolMessage` that goes back to the model. Strings are ideal. LangChain will serialize other types (dicts, lists, ints) for you, but **strings are the most token-efficient and the most reliable across providers**.

You can inspect all parts of any tool:

```python
from langchain_core.tools import tool

@tool
def get_weather(location: str, unit: str = "celsius") -> str:
    """Get the current weather for a location."""
    return f"Sunny, 22°{unit[0].upper()} in {location}"

# Anatomy inspection — do this constantly while learning:
print(get_weather.name)          # get_weather
print(get_weather.description)   # get_weather(location: str, unit: str = 'celsius') -> str - Get the current weather...
print(get_weather.args)          # {'location': {'title': 'Location', 'type': 'string'}, ...}
```

That `get_weather.args` dict is the **exact JSON Schema the LLM sees**. There is no magic — print it, and you'll know precisely what the model knows about your tool.

---

## 1.2 The `@tool` Decorator — Your Default Choice

```python
from langchain_core.tools import tool

@tool
def calculate_percentage(marks_obtained: int, marks_total: int) -> float:
    """Calculate the percentage from marks obtained and total marks."""
    return round((marks_obtained * 100.0) / marks_total, 2)

print(calculate_percentage.invoke({"marks_obtained": 670, "marks_total": 850}))
# 78.82
```

Three rules the decorator enforces/relies on:

1. **Type hints are required.** They define the input schema — no type hints, no schema, broken tool. Official docs state this explicitly. 
2. **The docstring becomes the description** the model sees. If there's no docstring, you'll get an error or a useless auto-generated description. Treat the docstring as a prompt you're writing *to the model*. 
3. **Use `snake_case` names.** Some providers (including Gemini) reject names with spaces or special characters. The official docs recommend snake_case for cross-provider compatibility. 

**Under the hood:** `@tool` actually builds a `StructuredTool` for you. You can verify: `type(calculate_percentage)` → `StructuredTool`. The decorator is just convenience sugar over section 1.5.

---

## 1.3 Customizing `@tool`

The full modern signature (current as of today):

```python
tool(
    name_or_callable=...,        # str or the function itself
    runnable=None,
    *,
    description=None,            # override the docstring-derived description
    return_direct=False,
    args_schema=None,            # your own Pydantic model
    infer_schema=True,
    response_format="content",   # or "content_and_artifact"
    parse_docstring=False,       # auto-extract arg descriptions from docstring
    error_on_invalid_docstring=True,
    extras=None,
)
```

### a) Overriding the name

```python
@tool("multiply_numbers")   # name differs from function name
def multiply(a: int, b: int) -> int:
    """Multiply two numbers together."""
    return a * b
```

### b) `parse_docstring=True` — free argument descriptions

Without it, your schema has titles but **no per-argument descriptions** — and argument descriptions genuinely improve the model's argument-filling accuracy. Instead of hand-writing a Pydantic model, use a **Google-style docstring**:

```python
@tool(parse_docstring=True)
def search_products(query: str, max_price: float | None = None, in_stock_only: bool = True) -> str:
    """Search the product catalog.

    Args:
        query: Keywords to search for, e.g. 'wireless headphones'.
        max_price: Optional maximum price filter in USD.
        in_stock_only: Whether to exclude out-of-stock items.
    """
    ...
```

Result: each argument gets its description injected into the JSON Schema automatically — verified by inspecting `search_products.args_schema.model_json_schema()`. 

⚠️ With `parse_docstring=True`, the docstring must be *valid* Google style — blank line before `Args:`, and every documented argument must exist in the signature. By default an invalid docstring raises `ValueError` (that's `error_on_invalid_docstring=True` working as a linter — a good thing, keep it on). 

**When `parse_docstring` isn't enough** → graduate to an explicit `args_schema` (next section).

### c) Explicit `args_schema` — maximum control

```python
from pydantic import BaseModel, Field

class WeatherInput(BaseModel):
    location: str = Field(description="City and country, e.g. 'Lisbon, PT'")
    unit: str = Field(default="celsius", description="'celsius' or 'fahrenheit'")

    @field_validator("unit")  # real validation, runs before your function
    @classmethod
    def check_unit(cls, v: str) -> str:
        if v not in ("celsius", "fahrenheit"):
            raise ValueError("unit must be 'celsius' or 'fahrenheit'")
        return v

@tool(args_schema=WeatherInput)
def get_weather(location: str, unit: str = "celsius") -> str:
    """Get the current weather for a location."""
    ...
```

Benefits over docstring parsing: validators, constraints (`Field(gt=0)`), nested models, and few-shot examples in descriptions. This is the pattern used in serious production code.

### d) `return_direct=True`

After this tool runs, **the agent loop stops** and the tool's output is returned to the user immediately, without the model seeing it again. Useful for a "final answer" tool. Default is `False`, and you should leave it `False` for 95% of tools.

### e) `response_format="content_and_artifact"` — a power feature

Return a **tuple**: `(content_for_model, artifact_for_code)`. The model sees only the string; the structured artifact is passed programmatically to downstream nodes (e.g., in LangGraph, retrieved via `Command(update=...)` or artifact fields):

```python
@tool(response_format="content_and_artifact")
def search_api(query: str) -> tuple[str, dict]:
    """Search the API and return a summary plus full results."""
    raw = raw_api_call(query)              # big dict
    summary = f"Found {len(raw['items'])} results."
    return summary, raw                    # (content, artifact)
```

---

## 1.4 Invoking Tools Manually vs. Letting a Model Call Them

This is the single most important debugging habit in all of tool engineering: **test tools in isolation before giving them to an agent.**

```python
# 1. Dict input — the same shape the LLM's tool_call produces
result = get_weather.invoke({"location": "Lisbon"})
print(result)   # ToolMessage(content="Sunny, 22°C in Lisbon", ...)

# 2. You can also invoke with a tool_call dict straight from a model response:
tc = ai_msg.tool_calls[0]        # {"name": ..., "args": {...}, "id": ..., "type": "tool_call"}
result = get_weather.invoke(tc)  # id is used to build the ToolMessage

# 3. Async version
result = await get_weather.ainvoke({"location": "Lisbon"})
```

**Modern vs. deprecated:** use `.invoke()` / `.ainvoke()` (the standard Runnable interface). `.run()` / `.arun()` still exist on `BaseTool` but are legacy — all new code should use `invoke`. 

A complete manual tool-calling loop with Gemini (you should type this out once to *feel* the mechanics):

```python
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

load_dotenv()

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
llm_with_tools = llm.bind_tools([get_weather])

messages = [HumanMessage("What's the weather in Lisbon?")]

# Step 1: model decides to call the tool
ai_msg = llm_with_tools.invoke(messages)
messages.append(ai_msg)
print(ai_msg.tool_calls)
# [{'name': 'get_weather', 'args': {'location': 'Lisbon'}, 'id': '...', 'type': 'tool_call'}]

# Step 2: YOU execute the tool
for tool_call in ai_msg.tool_calls:
    tool_message = get_weather.invoke(tool_call)
    messages.append(tool_message)

# Step 3: feed the result back for the final answer
final = llm_with_tools.invoke(messages)
print(final.content)
```

This exact pattern — bind → invoke → execute → feed back — is what the official Gemini integration docs teach, and it's what agent frameworks do for you automatically. 

⚠️ **Gemini quirk:** never name a function parameter literally `args` — a Pydantic internals bug injects a ghost `v__args` field into the schema that Gemini's API rejects. Rename the parameter or use an explicit `args_schema` if you must. 

**Why manual invocation matters:** when an agent misbehaves, 90% of the time the tool itself is the problem (bad description, bad schema, crash). `tool.invoke({...})` in a notebook cell isolates the bug in seconds — no LLM tokens, no agent noise.

---

## 1.5 `StructuredTool.from_function()` — The Programmatic Way

When you can't or don't want to decorate a function — most commonly **building tools dynamically in a loop** — use this. Current signature:

```python
StructuredTool.from_function(
    func=...,                    # sync function (or coroutine=... for async)    coroutine=None,
    name=None,
    description=None,
    return_direct=False,
    args_schema=None,
    infer_schema=True,
    response_format="content",
    parse_docstring=False,
    error_on_invalid_docstring=False,
)
```

```python
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

class MultiplyInput(BaseModel):
    a: int = Field(description="first number")
    b: int = Field(description="second number")

def multiply(a: int, b: int) -> int:
    """Multiply two numbers."""
    return a * b

calculator = StructuredTool.from_function(
    func=multiply,
    name="calculator",
    description="Multiply two numbers",   # explicit — no docstring reliance
    args_schema=MultiplyInput,
)
```

**The killer use case — dynamic tool generation:**

```python
def make_file_reader_tool(filepath: str) -> StructuredTool:
    def read_file() -> str:
        """Read the file's contents."""
        return open(filepath).read()

    return StructuredTool.from_function(
        func=read_file,
        name=f"read_{Path(filepath).stem}",
        description=f"Read the contents of {filepath}",
    )

tools = [make_file_reader_tool(p) for p in ["notes.md", "todo.md"]]
```

You can't parameterize a decorator like that — closures + `from_function` can. Note that `StructuredTool` is a `BaseTool` subclass and takes `func` plus an optional `coroutine` (the async twin). 

---

## 1.6 Subclassing `BaseTool` Directly — The Last Resort

`@tool` gives you *stateless function tools*. `BaseTool` subclassing gives you three things the decorator can't:

1. **Stateful tools** — instance attributes (counters, cached clients, rate limiters) created once in `__init__`.
2. **Full control over `run`/`arun` control flow** — custom pre/post-processing, streaming, custom error semantics.
3. **Custom lifecycle hooks** — `_run` (sync) and `_arun` (async) implemented independently.

```python
from typing import Type
from langchain_core.tools import BaseTool, ToolRuntime
from pydantic import BaseModel, Field

class GetHuggingFaceModelsInput(BaseModel):
    path: str = Field(default="", description="the api path")
    query_params: dict | None = Field(default=None, description="optional search params")

class GetHuggingFaceModelsTool(BaseTool):
    name: str = "get_huggingface_models"
    description: str = "Call GET on https://huggingface.co/api/models. Valid params: search, author, filter, sort."
    args_schema: Type[BaseModel] = GetHuggingFaceModelsInput

    # custom state lives here — plain Pydantic fields
    base_url: str = "https://huggingface.co/api/models"
    api_key: str = Field(default_factory=lambda: os.environ["HUGGINGFACE_API_KEY"])

    @property
    def _headers(self) -> dict:
        return {"authorization": f"Bearer {self.api_key}"}

    def _run(self, path: str = "", query_params: dict | None = None) -> dict:
        """Run the tool (sync)."""
        result = requests.get(self.base_url + path, params=query_params, headers=self._headers)
        return result.json()

    async def _arun(self, path: str = "", query_params: dict | None = None) -> dict:
        """Run the tool (async — real async, not thread-wrapped)."""
        async with aiohttp.ClientSession() as session:
            async with session.get(self.base_url + path, params=query_params, headers=self._headers) as resp:
                return await resp.json()

get_models_tool = GetHuggingFaceModelsTool()
```

Key mechanics to understand:

- **You implement `_run` (and optionally `_arun`).** The *public* `run`/`invoke` methods are owned by the framework — they do validation, callbacks, and tracing, then delegate to your `_run`. Never override `run`. 
- **If you only implement `_run`**, async calls get your sync code run in a thread — fine for quick tools. If your tool is I/O-bound and used in async agents, implement `_arun` properly.
- **Runtime injection (modern way):** if you need agent state, config, or the LangGraph store inside a tool, add a `runtime: ToolRuntime` parameter to `_run` — LangChain injects it automatically. Don't name parameters `config`, `run_manager`, or `callbacks`; those collide with framework-injected values and will break or be silently dropped. 

**Why last resort?** You now own: schema correctness, validation, sync/async parity, error handling, serialization for checkpoints. `@tool` + Pydantic gets all of that maintained by the framework. Reach for subclassing only when you've genuinely outgrown the function.

---

## 1.7 Error Handling (The Bit Everyone Skips)

Tools fail. APIs timeout, files are missing, models send garbage args. Two modern mechanisms:

```python
from langchain_core.tools import ToolException

@tool(handle_tool_error=True)     # catch ToolException → return message to model instead of crashing
def get_stock_price(ticker: str) -> str:
    """Get the latest stock price for a ticker symbol."""
    try:
        return fetch_price(ticker)
    except ConnectionError as e:
        raise ToolException(f"Price service unavailable: {e}")  # model sees this, agent continues
```

`handle_tool_error=True` converts a `ToolException` into a `ToolMessage` with the error text — the model can then retry or apologize instead of your agent dead-ending. (`handle_tool_error` also accepts a custom function.)

---

## 1.8 Wiring Tools Into an Agent (Modern Way)

As of **LangChain v1.0** (Oct 2025), the modern agent builder is:

```python
from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI

agent = create_agent(
    model=ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0),
    tools=[get_weather, calculator, *tools],
    system_prompt="You are a helpful assistant. Use tools when needed.",
)

result = agent.invoke({"messages": [("user", "What's the weather in Lisbon, and is 23% of 850 more than 200?")]})
for m in result["messages"]:
    m.pretty_print()
```

`create_agent` accepts `@tool`-decorated functions directly, plain typed functions with docstrings, or dicts for provider built-in tools.  Free Gemini API key via `GOOGLE_API_KEY`; the integration checks that first, with `GEMINI_API_KEY` as fallback.  (Also note: as of `langchain-google-genai` 4.x, the package uses the consolidated `google-genai` SDK.) 

---

## 📋 Deprecated / Legacy vs. Current — Cheat Sheet

| ❌ Old / deprecated                                               | ✅ Current (2026)                                                                                                               |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `from langchain.agents import initialize_agent, Tool, AgentType` | `from langchain.agents import create_agent`                                                                                    |
| `langgraph.prebuilt.create_react_agent`                          | `langchain.agents.create_agent` (v1)                                                                                           |
| `Tool(...)` dataclass (string-in/string-out only)                | `@tool` or `StructuredTool.from_function`                                                                                      |
| `tool.run(...)` / `tool.arun(...)`                               | `tool.invoke(...)` / `tool.ainvoke(...)`                                                                                       |
| `from langchain.tools import tool`                               | `from langchain_core.tools import tool` (the `langchain` import still works as a re-export, but `langchain_core` is canonical) |
| Passing `config`, `run_manager`, `callbacks` as tool args        | `runtime: ToolRuntime` parameter (auto-injected)                                                                               |
| Pydantic v1 patterns (`pydantic.v1`, `BaseSettings` with `env=`) | Pydantic v2: `Field(default_factory=...)`, `pydantic-settings`                                                                 |
| Everything removed in v1 (old chains, `Runnable.map`, etc.)      | Lives in `langchain-classic` package if you ever need it                                                                       |

---

## 🎯 Your Goal Checklist — Can You Now…?

- [ ] Write a `@tool` with type hints and a model-facing docstring
- [ ] Inspect `.name` / `.description` / `.args` and know exactly what the LLM sees
- [ ] Use `parse_docstring=True` and Google-style docstrings
- [ ] Write an explicit Pydantic `args_schema` with `Field` descriptions and validators
- [ ] Debug any tool with `.invoke({...})` — no LLM needed
- [ ] Build tools in a loop with `StructuredTool.from_function`
- [ ] Subclass `BaseTool` with state, custom `_run`/`_arun`, and `ToolRuntime`
- [ ] Handle failures with `ToolException` + `handle_tool_error=True`
- [ ] Bind tools to Gemini with `bind_tools` and run the manual call loop
- [ ] Register tools with `create_agent` and let the agent drive

## Suggested exercises

1. Build a `word_count_tool(text: str) -> int` — then print its `.args` and predict the JSON Schema before checking.
2. Build a file-reading tool factory (like §1.5) for every `.py` file in a directory.
3. Add a Pydantic validator that rejects negative numbers, and test it by invoking with bad input.
4. Take exercise 1's tool, bind it to Gemini, and run the full manual loop from §1.4.

Want the next lesson to be **tool runtime & state** (`ToolRuntime`, injected state, LangGraph stores), or **error handling & middleware** in depth? Both are the natural follow-ups.
