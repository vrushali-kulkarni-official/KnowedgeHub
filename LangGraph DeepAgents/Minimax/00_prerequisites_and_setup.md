# Module 00 — Prerequisites & Setup

## Prerequisites

- Python 3.11+
- Comfortable on the command line
- A model API key (we'll default to OpenAI-compatible; you can use Gemini, OpenRouter, Ollama, etc.)
- ~30 minutes

## Why this module matters

LangGraph doesn't exist in a vacuum — it sits on top of **LangChain**. You don't need to be a LangChain expert, but you do need to understand the *minimum* mental model so the LangGraph docs and examples make sense. This module gets you from zero to a runnable LangGraph program and a project layout that will carry you through Module 16.

## Learning objectives

By the end of this module you can:

1. Explain what LangChain and LangGraph are, how they relate, and why they exist.
2. Set up a Python project with `uv` (or `pip` + `venv`) for LangGraph development.
3. Configure environment variables for any major LLM provider **without** coupling your app to a vendor SDK.
4. Use the three LangChain primitives you actually need: **ChatModels**, **Messages**, and **Tools**.
5. Build and run your first LangGraph program.

---

## 0.1 The LangChain / LangGraph mental model

### 0.1.1 What is LangChain?

LangChain is a framework for building applications with LLMs. It provides:

- **ChatModels** — a unified interface to every LLM provider (OpenAI, Anthropic, Google, local, etc.).
- **Messages** — a typed message protocol (`HumanMessage`, `AIMessage`, `SystemMessage`, `ToolMessage`).
- **Tools** — a standard way to give an LLM "actions" it can call.
- **Prompt templates**, **output parsers**, **retrievers**, **embeddings** — all the boring plumbing.

The key idea: **abstraction over vendor**. Your app code talks to LangChain, LangChain talks to whoever.

### 0.1.2 What is LangGraph?

LangGraph is a library (built by the same team) for building **stateful, multi-actor** LLM applications as **graphs**.

- **Graph** = nodes (functions) + edges (routing).
- **Stateful** = the graph has a typed, persistent state that flows through it.
- **Multi-actor** = multiple "actors" (LLMs, tools, humans) can collaborate, with explicit control flow.

Think of LangGraph as a *state machine + workflow engine* purpose-built for LLM apps. Most things you build with raw LangChain chains quickly become spaghetti; LangGraph keeps them structured.

### 0.1.3 When to use what

| Use case | Use |
|---|---|
| One-shot LLM call | LangChain `ChatModel` directly |
| Simple prompt → LLM → parse | LangChain `Chain` (LCEL) |
| Multi-step with branching, loops, memory, or human input | **LangGraph** |
| Multi-agent orchestration | **LangGraph** |
| "I want Claude Code / Devin-style agent" | **Deep Agents** (which uses LangGraph) |

---

## 0.2 Project setup

### 0.2.1 Project layout

Create this skeleton. You'll grow into it across the course.

```
ai-saas/
├── pyproject.toml
├── .env.example
├── .gitignore
├── docker-compose.yml          # added in later modules
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app (added in Module 07)
│   ├── config.py               # Pydantic settings
│   ├── llm.py                  # Model factory — the ONLY place that knows about providers
│   ├── graph/
│   │   ├── __init__.py
│   │   ├── state.py            # State schemas
│   │   ├── nodes.py            # Node functions
│   │   └── graph.py            # Graph assembly
│   └── tools/
│       └── __init__.py
└── tests/
    └── __init__.py
```

### 0.2.2 Dependency management (uv recommended)

We use `uv` because it's the modern, fast, FOSS Python package manager. Fall back to `pip` + `venv` if you must.

```bash
# Install uv (FOSS, Rust-based)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create project
mkdir ai-saas && cd ai-saas
uv init --python 3.11
uv add langgraph langchain langchain-core langchain-openai \
       pydantic pydantic-settings python-dotenv httpx
uv add --dev pytest pytest-asyncio ruff mypy
```

If you're not using OpenAI, swap `langchain-openai` for the package that matches your provider — all of them follow the same `langchain-<provider>` naming convention. We will wrap them all behind one factory in `app/llm.py` (next sub-module).

### 0.2.3 The "one place that knows about providers" pattern

**Never** import a vendor SDK from your graph / node / tool code. Create a single module that returns a configured `BaseChatModel`:

```python
# app/llm.py
from functools import lru_cache
from langchain.chat_models import init_chat_model
from app.config import settings

@lru_cache
def get_llm():
    return init_chat_model(
        model=settings.MODEL_NAME,
        model_provider=settings.MODEL_PROVIDER,
        temperature=settings.TEMPERATURE,
        api_key=settings.API_KEY,    # read once, never logged
    )
```

```python
# app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    MODEL_PROVIDER: str = "openai"
    MODEL_NAME: str = "gpt-4o-mini"
    TEMPERATURE: float = 0.0
    API_KEY: str = "sk-..."

settings = Settings()
```

```env
# .env.example (commit this; do NOT commit your real .env)
MODEL_PROVIDER=openai
MODEL_NAME=gpt-4o-mini
TEMPERATURE=0
API_KEY=replace-me
```

This pattern is the **abstraction layer** you wanted. To switch from OpenAI to Gemini to a local Ollama model, you change `MODEL_PROVIDER` and `MODEL_NAME` — nothing else.

---

## 0.3 The three LangChain primitives you must know

### 0.3.1 ChatModel

```python
from app.llm import get_llm
from langchain_core.messages import HumanMessage

llm = get_llm()
response = llm.invoke([HumanMessage(content="Hello, who are you?")])
print(response.content)        # string answer
print(response.response_metadata)  # tokens, model version, etc.
```

`init_chat_model` is the modern factory that returns the right class based on `model_provider`. You don't need to know which class it returns.

### 0.3.2 Messages

There are four message types you'll use constantly:

| Class | Role | Use |
|---|---|---|
| `SystemMessage` | system | Sets behavior, persona, constraints |
| `HumanMessage` | user | The user's input |
| `AIMessage` | assistant | The LLM's reply; can contain `tool_calls` |
| `ToolMessage` | tool | Result of a tool execution |

```python
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

messages = [
    SystemMessage(content="You are a helpful assistant."),
    HumanMessage(content="What's the capital of France?"),
    AIMessage(content="Paris."),
    HumanMessage(content="And its population?"),
]
```

**`tool_calls` on `AIMessage`**: when the model wants to use a tool, the `AIMessage` has a `tool_calls` attribute (a list of dicts with `id`, `name`, `args`). The tool result comes back as a `ToolMessage` keyed by that same `id`. This is how the ReAct loop works (Module 04).

### 0.3.3 Tools

A tool is just a Python function with a schema. The `@tool` decorator does the schema for you:

```python
from langchain_core.tools import tool

@tool
def get_weather(city: str) -> str:
    """Get the current weather for a given city."""
    # pretend we call a real API
    return f"It's 22°C and sunny in {city}."

print(get_weather.name)            # "get_weather"
print(get_weather.description)     # "Get the current weather..."
print(get_weather.args_schema.schema())
```

Bind tools to an LLM:

```python
llm_with_tools = llm.bind_tools([get_weather])
msg = llm_with_tools.invoke([HumanMessage(content="Weather in Tokyo?")])
msg.tool_calls
# [{'name': 'get_weather', 'args': {'city': 'Tokyo'}, 'id': 'call_...'}]
```

You will use tools *all the time* in LangGraph via `ToolNode` (Module 04).

---

## 0.4 Your first LangGraph program

This is the smallest possible LangGraph app. We will dissect every line in Module 01.

```python
# app/graph/graph.py
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage
from app.llm import get_llm

class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

def chat_node(state: State):
    llm = get_llm()
    return {"messages": [llm.invoke(state["messages"])]}

graph = (
    StateGraph(State)
    .add_node("chat", chat_node)
    .add_edge(START, "chat")
    .add_edge("chat", END)
    .compile()
)

if __name__ == "__main__":
    result = graph.invoke({"messages": [{"role": "user", "content": "Hi!"}]})
    print(result["messages"][-1].content)
```

Run it:

```bash
uv run python -m app.graph.graph
```

You should see the model reply. If you do — you're set up. If you don't, debug your `.env` and API key first.

---

## Hands-on project

**Goal:** Get a clean dev environment, run your first graph, and verify the abstraction layer works.

1. Create the `ai-saas/` project above.
2. Configure `.env` with a real model provider key.
3. Run the "first LangGraph program" snippet. Confirm a reply comes back.
4. **Swap providers** by changing `.env` only (e.g. OpenAI → Gemini → Ollama). Confirm it still works.
5. Add a second tool, `add(a: int, b: int) -> int`, bind it, and manually inspect `tool_calls`.

## Exercises

1. **What happens if you remove `Annotated[list[BaseMessage], add_messages]`** and just use `messages: list[BaseMessage]`? Try it. (Don't write the answer here — find out.)
2. **Add a third tool** that returns today's date. Bind all three. Send a message that should trigger two tool calls. What does the `AIMessage` look like?
3. **Add a second node** to the graph that just appends " — verified" to the LLM's response. Chain it after `chat`. (Hint: the second node receives the full state, including the LLM's `AIMessage`.)
4. **Why is `lru_cache` used on `get_llm()`?** Remove it and re-invoke the graph 5 times. What changes?

## Production checklist

- [ ] `app/llm.py` is the **only** file that touches vendor SDKs.
- [ ] `.env` is in `.gitignore`; `.env.example` is committed.
- [ ] All model calls go through `get_llm()` (so caching, retries, evals can be added in one place later).
- [ ] `pyproject.toml` pins major versions (`langgraph>=0.2,<1.0` style).
- [ ] `ruff` and `mypy` are set up (Module 10 will add CI for them).

## Key takeaways

- LangChain = LLM plumbing. LangGraph = stateful workflows for LLM apps. Deep Agents = opinionated agent library on top of LangGraph.
- Keep vendor SDKs behind **one factory function**. Switch providers by changing `.env`.
- You only need 3 LangChain primitives to start: `ChatModel`, `Messages`, `Tools`.

## Resources

- LangChain docs: https://python.langchain.com/docs/introduction/
- LangGraph quickstart: https://langchain-ai.github.io/langgraph/concepts/why-langgraph/
- `init_chat_model` reference: https://python.langchain.com/docs/how_to/chat_models_universal_init/
- `uv` docs: https://docs.astral.sh/uv/
