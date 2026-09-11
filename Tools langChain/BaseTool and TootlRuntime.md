**BaseTool** and **ToolRuntime** are two important ideas in LangChain (and LangGraph) tools.

I will explain them in very simple, step-by-step language for a complete beginner.

---

### Step 1: What is a “Tool” in LangChain?

A **tool** is just a normal Python function that an AI agent can call.

Example of a simple tool:

```python
from langchain.tools import tool

@tool
def add(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b
```

When the AI decides “I need to add numbers”, it calls this tool.

---

### Step 2: What is `BaseTool`?

`BaseTool` is the **parent class** (the blueprint) of every tool in LangChain.

Think of it like this:

- Every tool you create (whether with `@tool` or by writing a class) is actually a child of `BaseTool`.
- `BaseTool` forces every tool to have some required things:
  - A **name**
  - A **description** (so the AI knows when to use it)
  - An **input schema** (what arguments it accepts)
  - A way to **run** the tool (`_run` or the function itself)

#### Two common ways to create a tool:

**Way 1 (Recommended for beginners) – Use the `@tool` decorator**

```python
from langchain.tools import tool

@tool
def multiply(a: int, b: int) -> int:
    """Multiply two numbers."""
    return a * b
```

Behind the scenes, LangChain turns this function into a `BaseTool`.

**Way 2 – Manually create a class that inherits from `BaseTool`**

```python
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

class MultiplyInput(BaseModel):
    a: int = Field(description="First number")
    b: int = Field(description="Second number")

class MultiplyTool(BaseTool):
    name = "multiply"
    description = "Multiply two numbers"
    args_schema = MultiplyInput

    def _run(self, a: int, b: int) -> int:
        return a * b
```

Both ways give you something that is a `BaseTool`.

**Simple summary of BaseTool:**  
`BaseTool` = the standard “shape” that every tool must follow so the AI agent can understand and use it.

---

### Step 3: What is `ToolRuntime`?

Sometimes your tool needs extra information that the AI (LLM) should **not** see or provide.

Examples of extra information:
- Current conversation history (state)
- Who the current user is
- A database connection
- Long-term memory (store)
- Tool call ID
- Ability to stream progress updates

This extra information is given to the tool through a special object called **`ToolRuntime`**.

#### How to use it:

Just add `runtime: ToolRuntime` as a parameter in your tool function.  
LangChain will automatically inject it (you don’t have to pass it yourself).

```python
from langchain.tools import tool, ToolRuntime

@tool
def summarize_conversation(runtime: ToolRuntime) -> str:
    """Summarize the conversation so far."""
    
    # Access the current messages
    messages = runtime.state["messages"]
    
    human_count = sum(1 for m in messages if m.type == "human")
    ai_count = sum(1 for m in messages if m.type == "ai")
    
    return f"Conversation has {human_count} human messages and {ai_count} AI messages."
```

**Important points:**
- The parameter name should be `runtime`
- The type should be `ToolRuntime`
- This parameter is **hidden** from the AI model (the AI never sees it or fills it)
- It is injected automatically when the tool runs inside a proper agent / ToolNode

#### What can you access inside `ToolRuntime`?

| Attribute            | What it gives you                          |
|----------------------|--------------------------------------------|
| `runtime.state`       | Current graph/agent state (e.g. messages) |
| `runtime.context`    | Custom context you passed (user_id, etc.) |
| `runtime.store`      | Long-term memory store                     |
| `runtime.config`     | RunnableConfig                             |
| `runtime.tool_call_id` | ID of the current tool call             |
| `runtime.stream_writer` | To stream custom updates                |

---

### Step 4: Simple Analogy

Imagine a restaurant:

- **BaseTool** = The official menu format. Every dish must have a name, description, and ingredients list. The waiter (AI) can only order from this standard format.
- **ToolRuntime** = The kitchen’s internal information (who the customer is, special requests, table number, etc.). The waiter never sees this, but the chef (your tool function) can use it to cook better.

---

### Step 5: Complete Beginner Example

```python
from langchain.tools import tool, ToolRuntime
from typing import Annotated

@tool
def greet_user(name: str, runtime: ToolRuntime) -> str:
    """Greet the user by name and show conversation length."""
    
    # Normal argument from the AI
    greeting = f"Hello {name}!"
    
    # Extra info from ToolRuntime
    message_count = len(runtime.state.get("messages", []))
    
    return f"{greeting} This conversation has {message_count} messages so far."
```

When the AI calls this tool, it only needs to provide `name`.  
`runtime` is automatically filled by LangChain/LangGraph.

---

### Quick Recap

| Concept       | Simple Meaning                                      | When to use it                          |
|---------------|-----------------------------------------------------|-----------------------------------------|
| **BaseTool**  | The standard base class / blueprint for all tools  | Always (every tool is a BaseTool)      |
| **ToolRuntime** | Special object that gives your tool extra context | When your tool needs state, user info, memory, etc. |

---

Would you like me to also show:
1. How to create a custom tool by inheriting from `BaseTool`, or  
2. A full working example with an agent that uses `ToolRuntime`?

Just tell me!
