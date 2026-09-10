# LangChain Core Primitives — Complete Beginner → Advanced Lesson

Welcome to lesson 1! This is a long lesson, so grab a coffee. By the end you'll have a **fully working agent** running on your machine. Let's go step by step.

---

## Part 0: The Mental Model (Read This First)

Before touching code, understand this picture:

```
┌─────────────────────────────────────────────────┐
│                 YOUR AGENT                      │
│                                                 │
│  ┌──────────┐   ┌──────────┐   ┌─────────────┐  │
│  │ Messages │ → │  Model   │ → │    Tools    │  │
│  │ (memory) │   │ (brain)  │   │ (hands)     │  │
│  └──────────┘   └──────────┘   └─────────────┘  │
│        ↑                        │               │
│        └──────── tool results ──┘               │
│              (the "agent loop")                 │
└─────────────────────────────────────────────────┘
```

Everything in LangChain is one of these four things:

1. **Messages** — the conversation format (what gets sent back and forth)
2. **Models** — the LLM that reads messages and decides what to do
3. **Tools** — functions the model is allowed to call
4. **The agent loop** — "call model → if it wants a tool, run it, feed result back → repeat until the model gives a final answer"

LangGraph and Deep Agents are just *fancy versions of this loop*. If you understand this lesson, LangGraph will feel like a natural upgrade, not a new world.

---

## Part 1: The Modern Package Layout

### 1.1 Why is the package layout confusing?

LangChain has existed since 2022. It grew messy, so the team **split one big package into focused packages**. This is the #1 confusion for beginners, so let's nail it.

### 1.2 The package map

```
langchain-core        → The foundation. Messages, tools, runnables. ALWAYS needed. No models inside.
langchain             → The "agent layer". Has create_agent, prebuilt helpers. (v1.0+, Oct 2025)
langchain-anthropic   → ChatAnthropic model (Claude)
langchain-openai      → ChatOpenAI model (GPT)
langchain-community   → Third-party integrations (vector DBs, loaders...) maintained by community
langchain-classic     → OLD stuff: the old AgentExecutor, old chains like LLMChain, RetrievalQA. DEPRECATED.
```

### 1.3 What's current vs. deprecated

| ✅ Use this (modern) | ❌ Avoid this (legacy, in `langchain-classic`) |
|---|---|
| `create_agent` | `initialize_agent`, `AgentExecutor` |
| `@tool` decorator | `Tool.from_function`, old ` StructuredTool` boilerplate |
| `.invoke()` / `.stream()` everywhere | `.run()`, `.predict()` |
| LCEL (`prompt \| model`) | `LLMChain`, `RetrievalQA` chains |
| `model.bind_tools([...])` | `format_tool_descriptions` + manual JSON parsing |

### 1.4 Installation

```bash
pip install langchain langchain-core langchain-anthropic python-dotenv

# OR if you use OpenAI instead:
pip install langchain langchain-core langchain-openai python-dotenv
```

> **Rule of thumb:** you install `langchain` + `langchain-core` + **exactly one provider package** matching your model. Never `pip install langchain-community` unless you actually need a community integration — and treat those as second-class citizens.

### 1.5 Setup your API key

Create a `.env` file in your project folder:

```
ANTHROPIC_API_KEY=sk-ant-...
# or OPENAI_API_KEY=sk-...
```

```python
# At the top of every script:
from dotenv import load_dotenv
load_dotenv()  # reads .env into environment variables
```

---

## Part 2: Messages — The Currency of Everything

### 2.1 What is a message?

LLMs don't take "text". They take a **list of typed messages**. Each message has a **role** (who said it) and **content** (what they said).

### 2.2 The four message types you must know

```python
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

messages = [
    # 1. SystemMessage — instructions/persona. Written by YOU (the developer).
    #    The model treats it as background rules.
    SystemMessage(content="You are a helpful math tutor. Always show your work."),

    # 2. HumanMessage — the user's input.
    HumanMessage(content="What is 17 * 23?"),

    # 3. AIMessage — what the MODEL said previously.
    #    You'll mostly create these indirectly, but you can inspect them:
    #    - content: the model's text reply
    #    - tool_calls: list of tools the model wants to execute (advanced, Part 3.5)
    AIMessage(content="17 * 23 is 391."),

    # 4. ToolMessage — the RESULT of running a tool. Written by YOUR code.
    #    - content: what the tool returned
    #    - tool_call_id: which tool call this answers (links them together!)
    ToolMessage(content="391", tool_call_id="call_abc123"),
]
```

### 2.3 Message history conventions

An agent conversation is just **a Python list that keeps growing**. Each loop appends messages:

```python
# Round 1
messages = [
    SystemMessage("You are a helpful assistant."),
    HumanMessage("What's the weather in Paris?"),
]
response = model.invoke(messages)       # model asks to call a tool
messages.append(response)               # AIMessage with tool_calls

# Round 2 — you run the tool, append the result
tool_result = get_weather("Paris")
messages.append(ToolMessage(content=tool_result, tool_call_id=response.tool_calls[0].id))
response2 = model.invoke(messages)      # model now answers with final text
messages.append(response2)
```

Key conventions:
- **System message goes first.** Always. It's the rulebook.
- **Never reorder or delete** past messages — models assume chronological order.
- Every `ToolMessage` must have a `tool_call_id` matching the `AIMessage.tool_calls[].id` that requested it. Mismatched IDs cause silent weirdness.

### 2.4 The shorthand (know it, don't overuse it)

```python
# Strings get auto-converted to HumanMessage; tuples too:
model.invoke("hello")                      # equivalent to [HumanMessage("hello")]
model.invoke([("system", "be terse"), ("human", "hi")])  # same thing
```

Fine for quick tests. In real apps, use explicit message classes — clarity wins.

---

## Part 3: Tools — The Agent's Hands

### 3.1 The `@tool` decorator — your first tool

A **tool** = a Python function + a name + a description + a schema for its arguments. The description is what the model reads to decide *when* to use the tool.

```python
from langchain_core.tools import tool

@tool
def multiply(a: int, b: int) -> int:
    """Multiply two integers and return the product."""
    return a * b

# That's it. Inspect what LangChain built:
print(multiply.name)        # "multiply"
print(multiply.description) # "Multiply two integers and return the product."
print(multiply.args_schema) # auto-generated from type hints!
```

**Critical beginner detail:** the **docstring is not decoration — it's the tool's instruction manual for the model.** Write docstrings that say *what the tool does AND when to use it*:

```python
@tool
def get_stock_price(ticker: str) -> str:
    """Get the latest stock price for a ticker symbol like 'AAPL' or 'TSLA'.
    Use this whenever the user asks about current stock prices or market data."""
    ...
```

### 3.2 Sync vs. async tools

Python has two ways to run functions. Your tools can be either:

```python
# SYNC tool — normal def. Runs in a thread pool so it doesn't block.
@tool
def read_file(path: str) -> str:
    """Read a text file from disk."""
    with open(path) as f:
        return f.read()

# ASYNC tool — async def. Use when the tool itself does I/O
# (HTTP calls, DB queries, other LLM calls). Much more efficient.
import httpx

@tool
async def fetch_url(url: str) -> str:
    """Fetch the contents of a URL."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        return resp.text
```

**When to use which:**
- Tool does local CPU work (math, parsing) → sync `def` is fine.
- Tool makes network calls → async `def`, and your agent will run tools concurrently.
- `create_agent` handles both transparently. Start sync; go async when you need speed.

### 3.3 Args schemas with Pydantic — input validation

Type hints alone are weak ("trust me, this is an int"). Pydantic schemas **validate** inputs and give the model a precise JSON schema of what to send:

```python
from pydantic import BaseModel, Field

class WeatherInput(BaseModel):
    city: str = Field(description="City name, e.g. 'Tokyo'")
    unit: str = Field(default="celsius", description="'celsius' or 'fahrenheit'")

@tool(args_schema=WeatherInput)
def get_weather(city: str, unit: str = "celsius") -> str:
    """Get current weather for a city."""
    return f"Sunny, 22°{unit[0].upper()} in {city}"
```

**Why this matters:** without a schema, the model may call `get_weather(city="Tokyo", unit="banana")`. Pydantic catches that and returns a clean error the model can learn from. Rule: **any tool with more than one argument gets a Pydantic schema.**

### 3.4 Tool error handling — return vs raise

Two conventions:

```python
# ✅ CONVENTION A (preferred for most cases): RETURN the error as a string.
# The model SEES the error and can self-correct (retry with different args).
@tool
def divide(a: float, b: float) -> str:
    """Divide a by b."""
    if b == 0:
        return "Error: cannot divide by zero. Please provide a non-zero divisor."
    return str(a / b)

# ✅ CONVENTION B: RAISE a ToolException — for truly unexpected failures.
from langchain_core.tools import ToolException

@tool
def query_db(sql: str) -> str:
    """Run a SQL query."""
    try:
        return db.execute(sql)
    except Exception as e:
        raise ToolException(f"Database error: {e}")  # agent catches & reports
```

And in `create_agent`, you control what the model sees when tools raise:

```python
agent = create_agent(model, tools, handle_tool_errors=True)  # default: errors become tool messages
```

**Simple rule:** bad *user-input* (wrong args, missing file) → return a helpful error string. Bad *infrastructure* (DB down, API 500) → raise `ToolException`.

### 3.5 Binding tools to a model (`model.bind_tools`)

Normally a model only produces text. `bind_tools` tells it: *"here are functions you may request; respond with structured tool calls."*

```python
from langchain_anthropic import ChatAnthropic

model = ChatAnthropic(model="claude-sonnet-4-20250514")
model_with_tools = model.bind_tools([multiply, divide])

response = model_with_tools.invoke([HumanMessage("what is 6 / 0?")])
print(response.tool_calls)
# [ { 'name': 'divide', 'args': {'a': 6.0, 'b': 0.0}, 'id': 'toolu_01...', ... } ]
```

Notice: `response.content` may be empty while `response.tool_calls` is populated. **The model doesn't run the tool — it *requests* it. YOU (or the agent loop) run it and send back a `ToolMessage`.**

### 3.6 A handy trick: `tool.invoke()` for testing

You can call tools directly without any model — great for unit tests:

```python
multiply.invoke({"a": 3, "b": 4})   # → 12
```

---

## Part 4: Runnables & LCEL — Just Enough to Read Other People's Code

### 4.1 What is a Runnable?

A **Runnable** is any object with `.invoke(input)` → output (and `.stream()`, `.batch()`, async variants). Models are Runnables, tools are Runnables, prompts are Runnables.

### 4.2 The pipe operator `|`

LCEL lets you chain Runnables with `|`:

```python
from langchain_core.prompts import ChatPromptTemplate

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a {style} assistant."),
    ("human", "{question}"),
])
chain = prompt | model          # prompt output feeds into model
chain.invoke({"style": "pirate", "question": "why is the sky blue?"})
```

A `ChatPromptTemplate` with `{placeholders}` is a **template**; calling it produces a list of messages.

### 4.3 A few utilities you'll see in the wild

```python
from langchain_core.runnables import RunnableLambda, RunnablePassthrough

RunnableLambda(lambda x: x.upper())   # wrap any plain function into a Runnable
RunnablePassthrough()                  # pass input through unchanged (used with dicts)
```

### 4.4 Why "don't over-invest"?

Honest take: with `create_agent` (below), you rarely need to hand-build LCEL chains anymore. You need LCEL **literacy**, not mastery. If you can read `prompt | model | parser` and know it means "template fills → model answers → output parsed", you're done.

---

## Part 5: `create_agent` — The Prebuilt Agent Loop

### 5.1 What it is

`create_agent` (added in LangChain v1.0, lives in `langchain.agents`) gives you the whole loop from Part 0 — model call → tool execution → tool result back → repeat — in **one function**. This is the direct ancestor of Deep Agents.

```python
from langchain.agents import create_agent

agent = create_agent(model, tools)   # that's the whole loop, constructed
```

### 5.2 The full signature (important options)

```python
agent = create_agent(
    model,                              # a bound-tools-capable chat model
    tools,                              # list of @tool-decorated functions
    system_prompt="You are...",         # convenience for a SystemMessage
    state_schema=None,                  # (advanced) extend agent memory structure
    checkpointer=None,                  # (advanced) persistence across runs
    middleware=[],                      # (advanced) hooks — Deep Agents builds on this!
)
```

You don't need the advanced params today. Just know `create_agent` is **the middle layer**: above raw `bind_tools` plumbing, below LangGraph's full control.

---

## Part 6: End-to-End Project — "Notes & Math Agent" 🎯

This is the goal you asked for: **one agent, two custom tools, running end to end without LangGraph.**

### Tool 1: a calculator. Tool 2: a persistent notes tool (save/read notes).

```python
# agent.py
import json, os
from dotenv import load_dotenv
load_dotenv()

from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from langchain.agents import create_agent

# ---------- Tool 1: calculator (sync, simple) ----------
@tool
def calculate(expression: str) -> str:
    """Evaluate a math expression like '12 * (3 + 4)' or '2**10'.
    Use this for ANY arithmetic the user asks about."""
    try:
        # safe-ish eval: only numbers and operators
        allowed = set("0123456789+-*/().,% ")
        if not set(expression) <= allowed:
            return "Error: only numbers and + - * / ( ) . % are allowed."
        return str(eval(expression))   # fine for a learning project
    except Exception as e:
        return f"Error: could not evaluate ({e}). Check the expression."

# ---------- Tool 2: notes (async, Pydantic schema, persistence) ----------
NOTES_FILE = "notes.json"

class SaveNoteInput(BaseModel):
    title: str = Field(description="Short title of the note")
    content: str = Field(description="The note's content")

@tool(args_schema=SaveNoteInput)
async def save_note(title: str, content: str) -> str:
    """Save a note for later. Use when the user asks to remember, save, or jot down something."""
    notes = {}
    if os.path.exists(NOTES_FILE):
        notes = json.load(open(NOTES_FILE))
    notes[title] = content
    json.dump(notes, open(NOTES_FILE, "w"), indent=2)
    return f"Saved note '{title}'."

@tool
def read_note(title: str) -> str:
    """Read a previously saved note by its title."""
    if not os.path.exists(NOTES_FILE):
        return "No notes saved yet."
    notes = json.load(open(NOTES_FILE))
    if title not in notes:
        return f"No note titled '{title}'. Available: {list(notes)}"
    return notes[title]

# ---------- Assemble ----------
model = ChatAnthropic(model="claude-sonnet-4-20250514")

agent = create_agent(
    model,
    tools=[calculate, save_note, read_note],
    system_prompt="You are a helpful assistant with a calculator and a notebook.",
)

# ---------- Run it ----------
if __name__ == "__main__":
    result = agent.invoke(
        {"messages": [("human", "What's 144 / 12? Also, remember that my wifi password is 'hunter2'.")]}
    )
    # The agent likely called calculate AND save_note, then replied:
    print(result["messages"][-1].content)

    result2 = agent.invoke(
        {"messages": [("human", "What did I ask you to remember about wifi?")]},
        config={"configurable": {"thread_id": "demo"}},  # keeps memory within THIS process run
    )
    print(result2["messages"][-1].content)
```

Run it:

```bash
python agent.py
```

**What happens under the hood** (trace it — this is the agent loop):

1. Your human message goes in.
2. Model sees tools + request → emits `AIMessage` with 2 `tool_calls` (calculate, save_note).
3. `create_agent`'s loop executes both (async one runs async), wraps results in `ToolMessage`s.
4. Model sees results → final `AIMessage`: *"That's 12. I've saved your wifi note."*
5. `result["messages"]` contains the FULL history — inspect any message, including `tool_calls`.

> **Memory note:** without a `checkpointer`, each `agent.invoke` starts fresh — the second call above won't actually remember the note unless you pass back the previous message list or add a checkpointer. That's intentional: persistence is LangGraph/checkpointer territory (your next lessons!). For a stateful in-process demo, do `result = agent.invoke({"messages": result["messages"] + [("human", "...")]})`.

### 6.1 Streaming (you'll want this)

```python
for chunk in agent.stream(
    {"messages": [("human", "calculate 13*13 and tell me a fun fact about the result")]},
    stream_mode="values",
):
    chunk["messages"][-1].pretty_print()
```

---

## Part 7: Retrieval Basics (RAG Foundation)

Just enough for later. Retrieval answers: *"find me the most relevant chunks of my documents to stuff into the prompt."*

### 7.1 The three pieces

1. **Embeddings model** — turns text into a vector (list of numbers) such that similar texts get similar vectors.
2. **Vector store** — a database that stores vectors + the original text, and can search "nearest neighbors."
3. **Retriever** — the interface: `retriever.invoke("query")` → list of relevant documents.

```python
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_openai import OpenAIEmbeddings  # or an open one, see 8.2

store = InMemoryVectorStore.from_texts(
    ["LangGraph is a library for building agent workflows as graphs.",
     "pgvector adds vector search to PostgreSQL.",
     "Claude is an AI model made by Anthropic."],
    embedding=OpenAIEmbeddings(),
)
retriever = store.as_retriever(search_kwargs={"k": 2})
docs = retriever.invoke("how do I store vectors?")
# → returns the pgvector doc + likely the LangGraph doc
```

### 7.2 The tool connection

In agents, retrieval is usually exposed **as a tool**:

```python
@tool
def search_docs(query: str) -> str:
    """Search the company knowledge base. Use for any question about internal docs."""
    docs = retriever.invoke(query)
    return "\n\n".join(d.page_content for d in docs)
```

Now the agent decides *when* to retrieve instead of you hardcoding it — that's RAG-tool territory for your later modules.

---

## Part 8: Free / Open-Source Component Choices

### 8.1 Vector DB — **use pgvector**

| Option | Cost | Verdict |
|---|---|---|
| **pgvector** (PostgreSQL extension) | Free, reuses DB you may already have | ✅ Best default. One less system to run; vectors + relational data together |
| Chroma | Free, embedded, zero-config | ✅ Great for local dev/prototypes |
| Qdrant / Weaviate / Milvus | Free self-hosted | Fine, but another service to operate |
| Pinecone / Weaviate Cloud | Paid SaaS | ❌ Avoid for learning |

```bash
pip install langchain-postgres
# SQL: CREATE EXTENSION IF NOT EXISTS vector;
```

### 8.2 Embedding models — open weights

| Model | Where | Notes |
|---|---|---|
| **bge-m3** (BAAI) or **nomic-embed-text** | via Ollama (`ollama pull nomic-embed-text`) or HuggingFace | ✅ Fully free, local, good quality |
| `multilingual-e5-large` | HuggingFace `sentence-transformers` | ✅ Strong, open |
| OpenAI `text-embedding-3-small` | API | 💰 Paid, cheap, very good — acceptable exception |
| Anything that requires a paid API | — | ❌ avoid for learning |

```python
# Free + local:
from langchain_ollama import OllamaEmbeddings
emb = OllamaEmbeddings(model="nomic-embed-text")

# or HuggingFace:
from langchain_huggingface import HuggingFaceEmbeddings
emb = HuggingFaceEmbeddings(model_name="BAAI/bge-m3")
```

### 8.3 The LLM itself

For the model, use **Claude via `langchain-anthropic`** or GPT via `langchain-openai` for your learning — agent reliability matters and paid frontier models are the smoothest. Later, swap to local models with **Ollama** (`langchain-ollama`) when you want free inference; just know small local models follow tool-calling instructions less reliably.

---

## Part 9: Your Mastery Checklist ✅

You now know everything needed to hit your goal. Verify you can answer:

- [ ] Why are there separate `langchain-core` / `langchain` / provider packages, and what lives where?
- [ ] Which message type carries `tool_calls`, and which carries results back? How are they linked?
- [ ] Write a `@tool` with a Pydantic schema and a good docstring. Why does the docstring matter?
- [ ] Sync vs async — when would you pick each?
- [ ] Error handling: when do you `return "Error: ..."` vs `raise ToolException`?
- [ ] What does `model.bind_tools` actually do, and who executes the tools?
- [ ] Read `prompt | model` and explain each stage.
- [ ] Build the Part 6 agent and get it running end to end.
- [ ] Name your vector DB + embedding choices for a free stack.

---

## Where This Leads Next (preview of lesson 2+)

`create_agent` is the **single-agent, in-process loop**. Its limits: no durable memory across restarts, no multi-agent coordination, no human-in-the-loop pauses, no cycles with conditional branching. **LangGraph** gives you the loop as an explicit graph you control; **Deep Agents** layers on top: sub-agents, planning, filesystem-style memory, and long-horizon tasks. Everything you learned today — messages, tools, `bind_tools`, tool errors — transfers 1:1.

**Homework:** run the Part 6 agent, then modify it: add a 4th tool of your own (e.g., a web-search stub or a dice roller), break the Pydantic schema on purpose, and watch how the model recovers from the returned error string. That recovery behavior is the single most instructive thing you can observe at this stage.

Want me to build lesson 2 (LangGraph: state, nodes, edges, and re-implementing this exact agent as a graph) next?
