This is an important topic because **Runtime and ToolRuntime are the bridge between your agent's logic and the execution environment around it**.

Once you understand them properly, many things that otherwise feel “magical” in LangChain/LangGraph become straightforward:

* how a tool knows **which user** is calling it
* how a tool reads **current agent state**
* how a tool accesses **persistent memory/store**
* how execution metadata reaches a tool
* how a tool knows its **tool-call ID**
* how middleware and tools access the current run
* why you should not put things like `user_id`, DB connections, secrets, or internal services in LLM-generated tool arguments
* how `Runtime`, `ToolRuntime`, `context`, `state`, `config`, `store`, and `checkpointer` fit together

I checked the current LangChain/LangGraph references before explaining this. The current APIs are in the LangChain v1/LangGraph v1 generation; the current references list `langchain` 1.4.2, `langgraph` Runtime 1.2.12, and ToolRuntime 1.1.0. ([LangChain Reference][1])

---

# 1. First: forget LangChain for a moment

Before we talk about `Runtime`, understand the word **runtime** itself.

When people say:

> “At runtime…”

they generally mean:

> “While the program is actually executing.”

For example:

```python
def calculate(a: int, b: int):
    return a + b
```

When Python executes:

```python
calculate(10, 20)
```

the values `10` and `20` exist **at execution time**.

You can think of a program as having:

```text
Code
  ↓
Execution starts
  ↓
Current execution environment
  ↓
Function runs
```

That current execution environment often contains things such as:

```text
current user
current request
configuration
database connection
logging
execution ID
state
services
dependencies
```

A framework can bundle those things into an object.

That is essentially what LangGraph's `Runtime` does.

---

# 2. What is Runtime in LangGraph?

The modern LangGraph definition is roughly:

> `Runtime` is a convenience object that bundles run-scoped context and other runtime utilities.

It is injected into **graph nodes and middleware**. ([LangChain Reference][2])

The important words are:

### "run-scoped"

It belongs to the **current execution/run**.

### "bundles"

Instead of separately passing:

```python
context
store
stream_writer
execution_info
```

you can receive one object:

```python
runtime
```

and access:

```python
runtime.context
runtime.store
runtime.stream_writer
runtime.execution_info
```

---

# 3. A simple mental model

Imagine your agent is a worker entering a building.

The worker is given a backpack.

Inside the backpack are things needed while doing the current job:

```text
Runtime
│
├── context
├── store
├── stream_writer
├── execution_info
├── server_info
├── previous
├── heartbeat
└── control
```

The exact fields available depend on the runtime/API, but this is a useful mental model. The current `Runtime` reference exposes context, store, stream writer, previous result information, execution information, server information and run control. ([LangChain Reference][2])

So:

```python
runtime.context
```

means:

> "Give me the context for this run."

while:

```python
runtime.store
```

means:

> "Give me the store available to this run."

---

# 4. Runtime is NOT the Python runtime

This distinction is extremely important.

When you hear:

```python
from langgraph.runtime import Runtime
```

this does **not** mean:

> "Python's runtime."

It is a LangGraph class representing information and services associated with the current graph execution.

Think:

```text
Python runtime
    ↓
Python interpreter executing your program

LangGraph Runtime
    ↓
Execution context for a particular LangGraph run
```

Completely different concepts.

---

# 5. Where does Runtime appear?

Consider a LangGraph node:

```python
def my_node(state, runtime):
    ...
```

LangGraph can inject the runtime:

```python
from langgraph.runtime import Runtime

def my_node(state, runtime: Runtime):
    ...
```

Now the node can access information associated with the current graph execution.

For example:

```python
def my_node(state, runtime: Runtime):
    user_id = runtime.context.user_id

    print(user_id)

    return {"result": "done"}
```

---

# 6. Why do we need Runtime?

Without Runtime, you might be tempted to do this:

```python
def my_node(state, user_id, db, logger, config, store):
    ...
```

Then another node:

```python
def another_node(
    state,
    user_id,
    db,
    logger,
    config,
    store,
):
    ...
```

And eventually:

```text
state
user_id
db
logger
config
store
stream_writer
request
...
```

gets passed around everywhere.

That becomes messy.

Runtime gives you a standardized execution object:

```python
def my_node(state, runtime: Runtime[Context]):
    user_id = runtime.context.user_id
    db = runtime.context.db
    store = runtime.store
```

This is essentially **dependency injection for graph execution**.

---

# 7. Runtime and dependency injection

This is one of the most important concepts to understand.

Suppose your agent needs:

```text
user_id
database connection
tenant_id
feature flags
authenticated service client
```

Those are not things the LLM should invent.

For example, you don't want:

```python
@tool
def get_customer(
    user_id: str,
):
    ...
```

when `user_id` comes from your authenticated application.

Why?

Because then the model is being asked to provide something it should **not control**.

You might instead have:

```python
@tool
def get_customer(runtime: ToolRuntime):
    user_id = runtime.context.user_id
```

Now:

```text
Application
   │
   │ authenticated user
   ▼
context
   │
   ▼
Runtime
   │
   ▼
Tool
```

The LLM never decides the user ID.

This separation becomes extremely important in enterprise systems.

---

# 8. Now we get to ToolRuntime

Here is the key idea:

## `Runtime` is primarily for graph nodes/middleware.

## `ToolRuntime` is specifically for tools.

The current reference explicitly distinguishes them:

> `ToolRuntime` is designed specifically for tools and adds tool-specific information such as `config`, `state`, and `tool_call_id`. ([LangChain Reference][2])

This is the most important distinction in this lesson.

---

# 9. Runtime vs ToolRuntime

Think of it like this:

```text
                   LangGraph execution
                           │
             ┌─────────────┴─────────────┐
             │                           │
          Node                         Tool
             │                           │
             ▼                           ▼
         Runtime                   ToolRuntime
```

So:

```text
Runtime
  ↓
graph/node execution

ToolRuntime
  ↓
tool execution
```

`ToolRuntime` shares runtime facilities such as:

```text
context
store
stream_writer
```

but adds tool-specific information such as:

```text
state
config
tool_call_id
tools
```

and current references also expose execution/server metadata. ([LangChain Reference][3])

---

# 10. Your first ToolRuntime example

Start with the simplest possible tool:

```python
from langchain.tools import tool, ToolRuntime

@tool
def hello(runtime: ToolRuntime) -> str:
    """Say hello."""
    return "Hello!"
```

Notice something interesting.

The tool has:

```python
runtime: ToolRuntime
```

but the LLM does **not** need to supply `runtime`.

LangChain injects it automatically.

The current documentation explicitly says that when a tool has a parameter named `runtime` typed as `ToolRuntime`, the execution system automatically injects it, and no `Annotated` wrapper is required. ([LangChain Reference][3])

---

# 11. What does the LLM see?

This distinction is critical.

Suppose:

```python
@tool
def get_weather(
    city: str,
    runtime: ToolRuntime,
) -> str:
    """Get weather for a city."""
    ...
```

The LLM effectively sees a tool schema like:

```json
{
  "name": "get_weather",
  "parameters": {
    "city": {
      "type": "string"
    }
  }
}
```

It does **not** see:

```text
runtime
```

as something it needs to produce.

Current LangChain tool references describe injected arguments as being excluded from the model-facing tool schema. ([LangChain Reference][4])

This is a huge architectural feature.

---

# 12. Why hiding Runtime from the LLM matters

Imagine this tool:

```python
@tool
def read_employee_data(
    employee_id: str,
    tenant_id: str,
    db_password: str,
    runtime: ToolRuntime,
):
    ...
```

You do NOT want the LLM generating:

```text
tenant_id = "company-a"
db_password = "..."
```

The LLM should only generate the things that are actually part of the tool's intended user-facing input.

For example:

```python
employee_id
```

Everything sensitive or application-controlled should come from your runtime/dependency system.

So:

```text
LLM-controlled arguments
        ↓
    city
    query
    order_id

Application-controlled runtime
        ↓
    user_id
    tenant_id
    authenticated client
    database
    store
    run information
```

This separation is one of the major reasons to understand ToolRuntime properly.

---

# 13. ToolRuntime field #1 — `context`

This is one of the most important fields.

Example:

```python
from dataclasses import dataclass

@dataclass
class Context:
    user_id: str
```

Then:

```python
@tool
def get_profile(runtime: ToolRuntime) -> str:
    """Get the current user's profile."""

    user_id = runtime.context.user_id

    return f"Loading profile for {user_id}"
```

Suppose the application starts an agent run with:

```python
context=Context(user_id="user_123")
```

Then:

```python
runtime.context.user_id
```

returns:

```text
user_123
```

---

# 14. What exactly is Context?

Context is information that belongs to the **current run** and is normally supplied by the application rather than generated by the model.

Examples:

```text
user_id
tenant_id
authenticated_user
database client
API client
feature flags
request-scoped service
organization ID
permissions object
```

LangGraph describes runtime context as static context for a graph run and says it can be thought of as **run dependencies**. ([LangChain Reference][5])

This gives you a very useful mental model:

```text
Context = "What dependencies does this run have?"
```

---

# 15. Runtime context with `create_agent`

Modern `create_agent` supports:

```python
context_schema=...
```

The current `create_agent` API exposes:

```python
context_schema
```

specifically as the schema for runtime context. ([LangChain Reference][6])

Example:

```python
from dataclasses import dataclass

@dataclass
class Context:
    user_id: str
```

Then:

```python
agent = create_agent(
    model=model,
    tools=[get_profile],
    context_schema=Context,
)
```

And invoke:

```python
agent.invoke(
    {
        "messages": [
            {
                "role": "user",
                "content": "Show my profile",
            }
        ]
    },
    context=Context(user_id="user_123"),
)
```

The tool can then read:

```python
    runtime.context.user_id
```

---

# 16. This is extremely important for multi-user systems

Imagine your enterprise AI harness has:

```text
10,000 employees
```

Alice sends:

```text
"Show my Salesforce opportunities"
```

Bob sends:

```text
"Show my Salesforce opportunities"
```

The text may be identical.

But the execution contexts are different:

```text
Alice run
  context.user_id = alice

Bob run
  context.user_id = bob
```

Then:

```python
@tool
def get_salesforce_opportunities(
    runtime: ToolRuntime,
):
    user_id = runtime.context.user_id

    return salesforce.get_opportunities_for(user_id)
```

The LLM doesn't need to say:

```text
user_id="alice"
```

The application already knows who Alice is.

This is exactly the type of design you will want in an enterprise harness.

---

# 17. ToolRuntime field #2 — `state`

Now we reach another extremely important distinction.

`context` and `state` are **not the same thing**.

`state` represents the current graph/agent state.

For a normal agent, the state includes messages and can include additional application state. The current `AgentState` includes the `messages` field and may contain other agent-managed fields. ([LangChain Reference][7])-----------------------------------------------------

A tool can access it through:

```python
runtime.state
```

Example:

```python
@tool
def inspect_conversation(
    runtime: ToolRuntime,
) -> str:
    """Inspect the current conversation."""

    messages = runtime.state["messages"]

    return f"There are {len(messages)} messages."
```

The current LangChain documentation specifically shows reading short-term memory/state inside a tool through `runtime: ToolRuntime`. ([GitHub][8])

---

# 18. Context vs State

This difference is so important that memorize this:

### Context

Usually:

```text
"What is true for this run?"
```

Examples:

```text
user_id
tenant_id
DB connection
API client
permissions
```

### State

Usually:

```text
"What has happened / what data is currently held by this agent execution?"
```

Examples:

```text
messages
current workflow step
search results
draft answer
current order
approval status
temporary workflow data
```

A simplified picture:

```text
                 Agent run
                    │
        ┌───────────┴───────────┐
        │                       │
     Context                  State
        │                       │
        │                       │
   user_id                 messages
   tenant_id               search results
   db client               workflow data
   permissions             current status
```

---

# 19. Why should user_id usually be Context rather than State?

This is a subtle architectural question.

Consider:

```python
context.user_id
```

versus:

```python
state["user_id"]
```

Both can technically contain a user ID.

But they have different meanings.

`context` says:

> "This execution is being performed for this user."

`state` says:

> "The current agent state contains this value."

Context is usually a better fit for **run dependencies and caller identity**.

State is generally better for **evolving workflow data**.

---

# 20. ToolRuntime field #3 — `config`

ToolRuntime also contains:

```python
runtime.config
```

This is a `RunnableConfig`.

The current ToolRuntime reference explicitly exposes `config`, while regular `Runtime` does not include it by default. ([reference.langchain.com][2])

Example:

```python
@tool
def inspect_execution(
    runtime: ToolRuntime,
) -> str:
    """Inspect execution configuration."""

    return str(runtime.config)
```

You may encounter values such as:

```text
run_id
tags
metadata
callbacks
configurable values
etc.
```

depending on how the invocation was configured.

---

# 21. Context vs Config

This is another place beginners often get confused.

Think:

### Context

Application/runtime dependencies:

```text
user_id
tenant_id
db
API clients
authenticated services
```

### Config

Execution configuration:

```text
run_id
tags
metadata
callbacks
runtime execution options
```

So:

```python
runtime.context
```

answers:

> "What dependencies/context does this run have?"

while:

```python
runtime.config
```

answers more like:

> "How is this Runnable execution configured?"

---

# 22. Do NOT use Config as a dumping ground

A common older pattern was putting arbitrary application information into configurable config values.

For example, conceptually:

```python
config = {
    "configurable": {
        "user_id": "123",
        "tenant_id": "abc"
    }
}
```

Modern LangChain/LangGraph has moved toward explicit **runtime context** for run-scoped application dependencies.

The current `create_agent` API explicitly exposes `context_schema`, and current migration guidance recommends the runtime context approach for new v1 applications rather than relying on the older `config["configurable"]` pattern. ([LangChain Reference][6])

So, for modern code:

```text
OLD-ish pattern
config["configurable"]["user_id"]

Modern pattern
runtime.context.user_id
```

This is an important modernization point.

---

# 23. ToolRuntime field #4 — `store`

ToolRuntime can also provide:

```python
runtime.store
```

This is the LangGraph store.

Remember the distinction:

```text
State
    ↓
current agent/thread execution state

Checkpointer
    ↓
persist state/checkpoints for threads

Store
    ↓
persistent data shared across threads
```

The current `create_agent` docs describe `checkpointer` as persisting state for a single thread, while `store` persists data across multiple threads. ([LangChain Reference][6])

So:

```python
runtime.store
```

is useful for long-lived application data.

---

# 24. Example using Store from a tool

Imagine:

```text
User preferences
```

have been stored:

```text
user_123
    preferred_language = English
```

Then:

```python
@tool
def get_preferences(
    runtime: ToolRuntime,
) -> str:
    """Get the current user's preferences."""

    user_id = runtime.context.user_id

    result = runtime.store.get(
        ("users", user_id),
        "preferences",
    )

    if result is None:
        return "No preferences found."

    return str(result.value)
```

Now the architecture becomes:

```text
Current request
     │
     ▼
runtime.context.user_id
     │
     ▼
runtime.store
     │
     ▼
long-term data
```

---

# 25. Context vs Store

This distinction is also very important.

Suppose Alice is using your system.

### Context

```python
Context(
    user_id="alice"
)
```

is supplied for the current run.

### Store

Contains data such as:

```text
alice preferences
alice profile
alice organization settings
alice remembered facts
```

So:

```text
Context
    = runtime dependency

Store
    = persistent data repository
```

---

# 26. ToolRuntime field #5 — `tool_call_id`

This field is specific to tools:

```python
runtime.tool_call_id
```

Suppose the LLM says:

```json
{
  "name": "get_weather",
  "args": {
    "city": "Pune"
  },
  "id": "call_abc123"
}
```

The tool receives:

```python
runtime.tool_call_id == "call_abc123"
```

This lets you correlate:

```text
LLM tool request
      │
      ▼
tool_call_id
      │
      ▼
tool execution
      │
      ▼
ToolMessage
```

The current API exposes this directly on `ToolRuntime`. ([LangChain Reference][3])

---

# 27. Why is tool_call_id useful?

Suppose the agent makes two tool calls:

```text
call_001 → Salesforce
call_002 → ServiceNow
```

You can correlate them individually.

For example:

```python
@tool
def do_something(runtime: ToolRuntime):
    print(
        "Executing:",
        runtime.tool_call_id
    )
```

This becomes valuable for:

```text
logging
tracing
auditing
ToolMessage correlation
debugging
middleware
human approval workflows
```

---

# 28. ToolRuntime field #6 — `stream_writer`

Runtime also gives access to a stream writer.

This is useful when a long-running tool wants to report progress.

For example:

```text
Searching Salesforce...
Checking 120 records...
Applying filters...
Done.
```

rather than waiting until the tool completely finishes.

The current runtime API exposes `stream_writer` as part of Runtime, and ToolRuntime receives a tool-specific stream writer. ([LangChain Reference][2])

The current ToolRuntime API also exposes:

```python
runtime.emit_output_delta(...)
```

for tool output streaming. ([LangChain Reference][3])

Conceptually:

```python
@tool
def long_operation(runtime: ToolRuntime):
    runtime.emit_output_delta("Starting...")
    ...
```

The exact streaming setup depends on how you invoke the graph and which stream mode you request.

---

# 29. Why streaming matters for agents

Suppose your tool performs:

```text
1. Search 50 documents
2. Query database
3. Call ServiceNow
4. Call Salesforce
5. Combine results
```

Without streaming:

```text
User
  │
  │ wait...
  │ wait...
  │ wait...
  ▼
final answer
```

With progress/output streaming:

```text
User
  │
  ├── Searching...
  ├── Found 20 documents
  ├── Checking ServiceNow
  ├── Checking Salesforce
  └── Completed
```

That becomes important in production UX.

---

# 30. ToolRuntime field #7 — `tools`

Current ToolRuntime also exposes:

```python
runtime.tools
```

This is a list of the tools available to the current tool execution. ([LangChain Reference][9])

Conceptually:

```python
available = runtime.tools
```

You could inspect:

```python
for tool in runtime.tools:
    print(tool.name)
```

This is an advanced capability.

You generally don't need it for normal tools.

It becomes interesting for:

```text
meta-tools
dynamic tool selection
tool orchestration
sub-agent patterns
middleware
advanced agent architectures
```

But don't start building complicated self-referential tool systems until you actually need them.

---

# 31. ToolRuntime field #8 — `execution_info`

Current Runtime exposes:

```python
runtime.execution_info
```

This contains read-only execution metadata.

The current reference describes information such as:

```text
checkpoint_id
checkpoint namespace
task_id
thread_id
run_id
node attempt
```

through `ExecutionInfo`. ([LangChain Reference][10])

This becomes useful for:

```text
observability
debugging
audit logs
execution tracking
distributed workflows
```

For example:

```python
info = runtime.execution_info

if info:
    print(info.thread_id)
    print(info.run_id)
```

---

# 32. Runtime field — `previous`

Regular LangGraph `Runtime` also has:

```python
runtime.previous
```

This is associated with the functional API and previous return values when a checkpointer is provided. ([LangChain Reference][2])

This is more advanced and is not something you need for basic `create_agent` work.

Remember:

```text
Runtime
   ├── context
   ├── store
   ├── stream_writer
   ├── previous
   ├── execution_info
   ├── server_info
   └── control
```

while ToolRuntime is specialized around tool execution.

---

# 33. Runtime field — `server_info`

In LangGraph Server environments, runtime may also contain:

```python
runtime.server_info
```

The current documentation says this contains metadata injected by LangGraph Server and can be `None` when running open-source LangGraph without that server environment. ([LangChain Reference][2])

This is another example of Runtime adapting itself to the execution environment.

---

# 34. Runtime field — `heartbeat`

Current Runtime also exposes:

```python
runtime.heartbeat()
```

This is useful for long-running operations where there may otherwise be no activity for a while.

The current API documents `heartbeat` as a way to record progress for idle-timeout handling. ([LangChain Reference][2])

For example:

```python
def expensive_node(state, runtime: Runtime):
    for item in very_large_operation():
        process(item)

        runtime.heartbeat()
```

Conceptually:

> "I am still alive and working."

This becomes relevant in production workflows with timeouts.

---

# 35. The biggest difference: Runtime vs ToolRuntime

Here is the table I want you to remember.

| Feature          | `Runtime`                  | `ToolRuntime`  |
| ---------------- | -------------------------- | -------------- |
| Purpose          | Graph execution            | Tool execution |
| Injected into    | Nodes, middleware          | Tools          |
| `context`        | Yes                        | Yes            |
| `store`          | Yes                        | Yes            |
| `stream_writer`  | Yes                        | Yes            |
| `state`          | Not part of Runtime object | Yes            |
| `config`         | Not part of Runtime object | Yes            |
| `tool_call_id`   | No                         | Yes            |
| `tools`          | No                         | Yes            |
| `execution_info` | Yes                        | Yes            |
| `server_info`    | Yes                        | Yes            |
| Tool-specific    | No                         | Yes            |

This distinction comes directly from the current LangGraph API design. ([LangChain Reference][2])

---

# 36. Why doesn't regular Runtime have `state`?

This is a subtle design question.

In a graph node, you already receive state explicitly:

```python
def my_node(
    state,
    runtime: Runtime,
):
    ...
```

So the node already has:

```python
state
```

directly.

That is why Runtime doesn't need to bundle it the same way ToolRuntime does.

A tool, however, normally looks like:

```python
@tool
def search(query: str):
    ...
```

The tool isn't normally given:

```python
state
```

directly.

So ToolRuntime gives it:

```python
runtime.state
```

This is an important design difference.

---

# 37. Why doesn't Runtime have config?

The current Runtime reference explicitly notes:

> `Runtime` does not include `config`.

For graph nodes, the recommended way to access `RunnableConfig` is to inject it directly:

```python
from langchain_core.runnables import RunnableConfig

def my_node(
    state,
    config: RunnableConfig,
    runtime: Runtime,
):
    ...
```

or use `get_config()`. ([LangChain Reference][2])

So:

```text
Node

state
config
runtime
```

can all be independently injected.

ToolRuntime packages the tool-oriented pieces together for convenience.

---

# 38. How ToolRuntime injection actually works

This is where the "magic" becomes understandable.

Suppose you write:

```python
@tool
def get_user(
    query: str,
    runtime: ToolRuntime,
):
    ...
```

The LLM produces:

```json
{
  "name": "get_user",
  "args": {
    "query": "Bhargav"
  },
  "id": "call_123"
}
```

Then LangGraph's tool execution mechanism effectively does something conceptually like:

```python
runtime = ToolRuntime(
    state=current_state,
    context=current_context,
    config=current_config,
    tool_call_id="call_123",
    store=current_store,
    stream_writer=current_stream_writer,
    tools=available_tools,
    ...
)
```

Then:

```python
get_user(
    query="Bhargav",
    runtime=runtime,
)
```

The actual internal implementation constructs ToolRuntime instances for each tool call. The current `ToolNode` source shows this explicitly. ([GitHub][11])

---

# 39. This is dependency injection

So don't think:

> "LangChain magically knows what runtime is."

Think:

```text
Tool executor
     │
     ├── builds ToolRuntime
     │
     └── injects ToolRuntime
              │
              ▼
           your tool
```

This is dependency injection.

The framework owns the construction of the runtime object.

Your tool simply declares:

```python
runtime: ToolRuntime
```

---

# 40. A complete small example

Let's build one.

## Step 1 — define Context

```python
from dataclasses import dataclass

@dataclass
class Context:
    user_id: str
```

---

## Step 2 — define a tool

```python
from langchain.tools import tool, ToolRuntime

@tool
def get_current_user(runtime: ToolRuntime) -> str:
    """Return information about the current authenticated user."""

    user_id = runtime.context.user_id

    return f"Current user is {user_id}"
```

---

## Step 3 — create the agent

```python
from langchain.agents import create_agent

agent = create_agent(
    model=model,
    tools=[get_current_user],
    context_schema=Context,
)
```

---

## Step 4 — invoke

```python
result = agent.invoke(
    {
        "messages": [
            {
                "role": "user",
                "content": "Who am I?",
            }
        ]
    },
    context=Context(
        user_id="user_123"
    ),
)
```

The execution is conceptually:

```text
User request
     │
     ▼
create_agent
     │
     ▼
LLM
     │
     │ decides: call get_current_user
     ▼
Tool executor
     │
     │ creates ToolRuntime
     ▼
get_current_user(runtime)
     │
     │ runtime.context.user_id
     ▼
"user_123"
     │
     ▼
ToolMessage
     │
     ▼
LLM
     │
     ▼
Final response
```

That entire flow is what you need to visualize.

The modern `create_agent` execution loop is model → tool calls → tool execution → resulting `ToolMessage` → model again until no more tool calls are produced. ([LangChain Reference][6])

---

# 41. A Gemini version

Since you prefer Gemini, here's the same idea using the current Google GenAI LangChain integration.

The current `langchain-google-genai` integration exposes `ChatGoogleGenerativeAI`, and the current package uses Google's consolidated `google-genai` SDK. ([LangChain Reference][12])

For example:

```python
from dataclasses import dataclass

from langchain.agents import create_agent
from langchain.tools import tool, ToolRuntime
from langchain_google_genai import ChatGoogleGenerativeAI


@dataclass
class Context:
    user_id: str


@tool
def get_current_user(runtime: ToolRuntime) -> str:
    """Return the current authenticated user's ID."""
    return runtime.context.user_id


model = ChatGoogleGenerativeAI(
    model="gemini-3.1-pro-preview",
)

agent = create_agent(
    model=model,
    tools=[get_current_user],
    context_schema=Context,
)

result = agent.invoke(
    {
        "messages": [
            {
                "role": "user",
                "content": "Who am I?",
            }
        ]
    },
    context=Context(
        user_id="user_123"
    ),
)

print(result)
```

Current Google GenAI reference documentation lists `ChatGoogleGenerativeAI` as the primary Gemini chat integration. ([LangChain Reference][12])

---

# 42. Let's make the example more realistic

Suppose you have:

```text
AI Enterprise Harness
```

and a tool:

```python
@tool
def search_company_documents(
    query: str,
    runtime: ToolRuntime,
) -> str:
    """Search documents available to the current user."""
```

The model provides:

```text
query
```

The application provides:

```text
user_id
tenant_id
permissions
document store
```

So:

```python
@tool
def search_company_documents(
    query: str,
    runtime: ToolRuntime,
) -> str:

    user_id = runtime.context.user_id
    tenant_id = runtime.context.tenant_id

    results = search_documents(
        tenant_id=tenant_id,
        user_id=user_id,
        query=query,
    )

    return str(results)
```

This architecture is far better than:

```python
@tool
def search_company_documents(
    query: str,
    user_id: str,
    tenant_id: str,
):
    ...
```

because the model should not be responsible for supplying security-sensitive execution identity.

---

# 43. Context + State + Store + Config together

Now let's combine everything.

Suppose:

```text
user = Alice
tenant = Acme
thread = 123
```

The run might conceptually have:

```text
Runtime
│
├── context
│     ├── user_id = Alice
│     └── tenant_id = Acme
│
├── store
│     └── long-term company/user data
│
├── state
│     ├── messages
│     ├── current task
│     └── workflow information
│
├── config
│     ├── run_id
│     ├── tags
│     └── metadata
│
└── execution_info
      ├── thread_id = 123
      └── task information
```

This is the architecture you should picture.

---

# 44. Where does Checkpointer fit?

This is especially important because you are learning:

```text
State
Context
Config
Thread
Checkpointer
Store
```

The relationship is roughly:

```text
                   Agent Run
                       │
              ┌────────┴────────┐
              │                 │
           Runtime          State
              │                 │
              │                 ▼
              │            Checkpointer
              │                 │
              │                 ▼
              │             Thread data
              │
              ▼
         Context / Store
```

More precisely:

### State

Current working state.

### Checkpointer

Persists state/checkpoints associated with a thread.

### Context

Run dependencies supplied for the execution.

### Store

Persistent application data that can span threads.

### Config

Execution configuration.

### Runtime

Convenient access to several of these things during execution.

---

# 45. A very useful analogy

Imagine a restaurant.

## State

What's happening with the current order:

```text
table = 10
items = pizza + coke
status = preparing
```

## Context

Information about the current customer/session:

```text
customer_id
restaurant_id
authenticated_user
payment service
```

## Config

How this operation should run:

```text
request_id
logging options
tags
timeouts
```

## Store

The restaurant's persistent database:

```text
customer history
loyalty points
preferences
orders
```

## Checkpointer

A durable snapshot of the current workflow/order:

```text
Order #123
current step = payment
```

## Runtime

The waiter receives the relevant working environment:

```text
Runtime
 ├── context
 ├── store
 ├── execution information
 └── streaming/control facilities
```

## ToolRuntime

When the waiter invokes a particular tool:

```text
ToolRuntime
 ├── current state
 ├── context
 ├── config
 ├── store
 ├── current tool_call_id
 └── streaming/tool information
```

---

# 46. Can a tool modify state?

Yes.

Reading state is straightforward:

```python
runtime.state
```

For more advanced workflows, tools can return a `Command` to update graph state or influence graph control flow.

The current LangGraph `Command` API supports:

```python
Command(
    update=...
)
```

for applying updates to graph state. ([LangChain Reference][13])

Conceptually:

```python
@tool
def set_priority(
    priority: str,
    runtime: ToolRuntime,
):
    return Command(
        update={
            "priority": priority
        }
    )
```

This is an advanced pattern.

The important distinction is:

```text
runtime.state
     ↓
read current state

Command(update=...)
     ↓
request a state update
```

Don't think that simply modifying:

```python
runtime.state["priority"] = "high"
```

is equivalent to properly returning a graph state update.

State in LangGraph is managed by the graph execution model.

---

# 47. Runtime is not "memory"

This is another common misunderstanding.

Someone sees:

```python
runtime.store
runtime.state
```

and concludes:

> "Runtime is memory."

No.

Runtime is more like a **gateway to execution resources**.

It may give you access to:

```text
state
context
store
config
streaming
execution metadata
```

But Runtime itself isn't the persistence mechanism.

Think:

```text
Runtime
  = access mechanism / execution bundle

Store
  = persistence mechanism

Checkpointer
  = checkpoint persistence mechanism
```

---

# 48. ToolRuntime is not the tool itself

Another important distinction.

This:

```python
@tool
def search(query: str, runtime: ToolRuntime):
    ...
```

contains two different concepts.

### The tool

```python
search
```

defines an action the model can request.

### ToolRuntime

```python
runtime
```

provides the execution environment in which that action occurs.

So:

```text
Tool
   ↓
"What action can the agent request?"

ToolRuntime
   ↓
"What execution environment does that action have?"
```

---

# 49. ToolRuntime is hidden from the model

This deserves another emphasis.

Suppose:

```python
@tool
def search(
    query: str,
    runtime: ToolRuntime,
):
    ...
```

The model should effectively see:

```text
search(query)
```

not:

```text
search(query, runtime)
```

That is why this pattern is safe and convenient for internal application dependencies.

The current tool system explicitly identifies these as injected arguments that are excluded from the model-facing tool schema. ([LangChain Reference][4])

---

# 50. Compare this with an ordinary Python function

Ordinary Python:

```python
def search(
    query: str,
    user_id: str,
    db,
):
    ...
```

You have to manually provide:

```python
search(
    query="LangChain",
    user_id="user_123",
    db=db,
)
```

LangChain/LangGraph:

```python
@tool
def search(
    query: str,
    runtime: ToolRuntime,
):
    user_id = runtime.context.user_id
    db = runtime.context.db
```

The execution framework supplies runtime dependencies automatically.

That is the essence of dependency injection here.

---

# 51. Why not simply put everything in Context?

You might ask:

> "Why not just put state, config, store, everything inside Context?"

For example:

```python
@dataclass
class Context:
    user_id: str
    state: dict
    config: dict
    store: object
```

Technically you could design something like that.

But it's a bad architectural separation.

LangGraph already has distinct concepts:

```text
context
state
config
store
execution info
```

Keeping them distinct gives your system clearer semantics.

For example:

```text
Context
  = dependencies

State
  = evolving workflow state

Config
  = execution configuration

Store
  = persistent cross-thread data

Checkpointer
  = persistent thread state
```

This distinction becomes very valuable as your project grows.

---

# 52. Context should generally be stable during the run

Suppose:

```python
Context(
    user_id="alice",
    tenant_id="acme",
)
```

The whole run uses those values.

Contrast that with state:

```text
state:
  messages → changes
  search_results → changes
  current_step → changes
```

So an excellent mental model is:

```text
Context = relatively stable run dependencies

State = evolving working data
```

---

# 53. Runtime lifecycle

Let's walk through an agent run from start to finish.

Suppose you execute:

```python
agent.invoke(
    {"messages": [...]},
    context=Context(user_id="alice"),
)
```

Conceptually:

### Step 1

Application starts the run.

```text
user_id = alice
```

### Step 2

LangGraph creates the execution environment.

```text
Runtime
```

### Step 3

Runtime receives:

```text
context
store
streaming infrastructure
execution information
```

### Step 4

Agent invokes the model.

```text
LLM
```

### Step 5

Model says:

```text
Call search_documents
```

### Step 6

Tool executor sees:

```text
search_documents(...)
```

and constructs:

```text
ToolRuntime
```

for that tool call.

### Step 7

Tool receives:

```python
runtime: ToolRuntime
```

### Step 8

Tool accesses:

```python
runtime.context
runtime.state
runtime.store
runtime.config
runtime.tool_call_id
```

### Step 9

Tool returns a result.

### Step 10

Agent puts the result back into the graph state/messages.

### Step 11

Model sees the tool result.

### Step 12

The process repeats until the agent stops.

That is the machinery underneath modern `create_agent`. ([LangChain Reference][6])

---

# 54. One very important security rule

Never assume:

```text
"Because it came from the LLM, it is trustworthy."
```

For example:

```python
@tool
def delete_customer(
    customer_id: str,
    runtime: ToolRuntime,
):
    ...
```

The `customer_id` comes from the model.

So your application still needs authorization:

```python
user_id = runtime.context.user_id

authorize(
    user_id=user_id,
    customer_id=customer_id,
)
```

Runtime gives you the trustworthy application-controlled context.

The model gives you a requested operation.

Your tool combines them:

```text
LLM request
   +
trusted application context
   =
authorized action
```

This is particularly important in the enterprise harness you are building.

---

# 55. Runtime and middleware

Runtime isn't only about tools.

Current LangChain agents support middleware, and the current Runtime model is injected into LangGraph nodes and middleware. ([LangChain Reference][2])

So you can conceptually have:

```text
Agent
 │
 ├── middleware
 │      └── Runtime
 │
 ├── model
 │
 └── tools
        └── ToolRuntime
```

This becomes particularly powerful for:

```text
authorization
logging
rate limits
dynamic prompts
tool filtering
human approval
tenant isolation
observability
```

---

# 56. Runtime + middleware + ToolRuntime

Imagine:

```text
User
 │
 ▼
Middleware
 │
 │ Runtime
 │
 ├── verify tenant
 ├── check permissions
 └── add context
 │
 ▼
Model
 │
 ▼
Tool call
 │
 ▼
ToolRuntime
 │
 ├── state
 ├── context
 ├── config
 ├── store
 └── tool_call_id
 │
 ▼
Tool
```

This is a very powerful architecture.

---

# 57. What should go where?

Here is the practical rule set I recommend you memorize.

### Put in Context

Things like:

```text
user_id
tenant_id
authenticated principal
database connection/client
API clients
request-specific service dependencies
feature flags
permission information
```

### Put in State

Things like:

```text
messages
current workflow step
search results
temporary results
approval status
intermediate agent data
```

### Put in Config

Things like:

```text
run_id
tags
metadata
callbacks
execution configuration
```

### Put in Store

Things like:

```text
long-term user preferences
cross-thread memory
organization information
persistent application data
```

### Use Checkpointer

For:

```text
thread state
conversation continuity
durable agent execution
resume/replay workflows
```

---

# 58. Current vs old approaches

Since you specifically asked about deprecated/old/current styles, this is important.

## Older architecture

You will encounter code using APIs such as:

```python
initialize_agent(...)
```

older agent executors, older memory abstractions, and manually managed chains.

The current LangChain v1 direction is:

```python
create_agent(...)
```

The current `create_agent` API is the modern agent factory. ([LangChain Reference][6])

---

## Older context/config pattern

You may encounter:

```python
config["configurable"]
```

being used to pass application context such as:

```text
user_id
session_id
tenant_id
```

Modern LangChain/LangGraph favors explicit runtime context:

```python
context_schema=Context
```

and:

```python
agent.invoke(
    ...,
    context=Context(...)
)
```

The v1 migration direction explicitly favors runtime context for new applications. ([GitHub][14])

---

## Older injected-tool patterns

You may encounter:

```python
Annotated[
    dict,
    InjectedState,
]
```

or:

```python
Annotated[
    str,
    InjectedToolCallId,
]
```

These APIs still exist and are part of the current tool infrastructure. ([LangChain Reference][15])

But for a tool that needs **multiple runtime facilities**, modern `ToolRuntime` is usually cleaner:

```python
@tool
def my_tool(
    query: str,
    runtime: ToolRuntime,
):
    ...
```

Instead of separately injecting:

```text
state
store
tool_call_id
```

you have one runtime object.

---

# 59. Important: InjectedState is not "deprecated"

Don't misunderstand the previous point.

It is not:

```text
InjectedState = deprecated
```

The current LangGraph ToolNode reference still documents `InjectedState`, `InjectedStore`, and `ToolRuntime`. ([LangChain Reference][15])

Rather:

```text
InjectedState
    ↓
focused injection of one dependency

ToolRuntime
    ↓
complete execution environment for the tool
```

For simple tools, either can be appropriate.

For richer tools:

```python
runtime: ToolRuntime
```

is often much easier to reason about.

---

# 60. `Runtime` vs `ToolRuntime` vs `context`

Another common beginner confusion is treating these three as interchangeable.

They aren't.

```text
Context
    ↓
Data/dependencies for the current run

Runtime
    ↓
Object that gives graph nodes/middleware access to
context/store/streaming/execution facilities

ToolRuntime
    ↓
Tool-specific runtime object giving tools access to
context/state/config/store/tool-call information/etc.
```

So:

```text
Context ≠ Runtime
Runtime ≠ ToolRuntime
```

---

# 61. The cleanest mental model

I want you to remember this picture:

```text
                    CURRENT AGENT RUN
                           │
             ┌─────────────┴─────────────┐
             │                           │
          Context                     State
             │                           │
             │                           │
     user_id / tenant              messages / workflow
     dependencies                   intermediate data
             │                           │
             └─────────────┬─────────────┘
                           │
                        Runtime
                           │
                 graph nodes / middleware
                           │
                           ▼
                         Model
                           │
                      tool call
                           │
                           ▼
                     ToolRuntime
                           │
        ┌──────────┬───────┼────────┬──────────┐
        │          │       │        │          │
      state     context   config   store   tool_call_id
```

That is the architecture I want you to have in your head.

---

# 62. A realistic enterprise example

Imagine your enterprise AI harness has:

```text
Microsoft 365
Salesforce
ServiceNow
Slack
Google Drive
PostgreSQL
```

A user asks:

> "Find my open ServiceNow tickets and summarize anything related to Project Alpha."

The application creates:

```python
Context(
    user_id="user_123",
    tenant_id="acme",
    ...
)
```

The agent state contains:

```text
messages
current task
tool outputs
intermediate results
```

The model decides:

```text
call service_now_search
```

Tool gets:

```python
runtime: ToolRuntime
```

and does:

```python
user_id = runtime.context.user_id
tenant_id = runtime.context.tenant_id

tickets = service_now.search(
    tenant_id=tenant_id,
    user_id=user_id,
    query=query,
)
```

Then the tool can also log:

```python
runtime.tool_call_id
```

or retrieve persistent information:

```python
runtime.store
```

and access the current messages/state:

```python
runtime.state
```

This is exactly the kind of architecture Runtime/ToolRuntime enables.

---

# 63. The architectural principle underneath all of this

The deepest concept here is:

> **The model should decide what it wants to do; the application should control the environment in which that action executes.**

For example:

```text
LLM
 │
 │ "Search ServiceNow for Project Alpha"
 ▼
Tool call
 │
 ▼
Application execution environment
 │
 ├── Who is the user?
 ├── Which tenant?
 ├── What permissions?
 ├── Which DB?
 ├── Which credentials?
 ├── Which store?
 ├── Which thread?
 └── Which execution?
```

That separation is fundamental to robust agent engineering.

---

# 64. What you should memorize

Don't memorize the implementation first.

Memorize these five sentences:

### 1.

**Runtime is the execution environment bundle for a LangGraph run.**

### 2.

**Runtime is primarily injected into graph nodes and middleware.**

### 3.

**ToolRuntime is the specialized runtime object for tools.**

### 4.

**ToolRuntime lets a tool access things like state, context, config, store, and its tool-call ID without making the LLM provide those values.**

### 5.

**Context, State, Config, Store, and Checkpointer are different concepts; Runtime provides convenient access to several of them during execution.**

---

# 65. The modern API to learn

For the agent ecosystem you're studying, these are the APIs I would focus on now:

```python
from langchain.agents import create_agent
```

```python
from langchain.tools import tool, ToolRuntime
```

```python
from langgraph.runtime import Runtime
```

```python
agent = create_agent(
    model=model,
    tools=[...],
    context_schema=Context,
    checkpointer=...,
    store=...,
)
```

and:

```python
agent.invoke(
    input,
    context=Context(...),
)
```

rather than building new code around older agent APIs or using `configurable` as your main mechanism for application context. ([LangChain Reference][6])

---

# 66. One final comparison

Suppose you have this tool:

```python
@tool
def search_documents(
    query: str,
    runtime: ToolRuntime,
):
    ...
```

Then:

```text
query
```

comes from:

```text
LLM
```

while:

```text
runtime.context.user_id
runtime.context.tenant_id
runtime.state
runtime.store
runtime.config
runtime.tool_call_id
```

come from:

```text
application / LangGraph execution system
```

That single distinction explains a huge amount of modern agent architecture.

---

# 67. Your learning progression from here

Because you're currently learning `create_agent`, I'd learn the concepts in this order:

```text
1. Runtime
      ↓
2. Context
      ↓
3. ToolRuntime
      ↓
4. State
      ↓
5. Config
      ↓
6. Thread / thread_id
      ↓
7. Checkpointer
      ↓
8. Store
      ↓
9. Runtime + State + Context + Config together
      ↓
10. ToolRuntime + Command
      ↓
11. Middleware + Runtime
      ↓
12. Human-in-the-loop + ToolRuntime
      ↓
13. Multi-agent / subagents
      ↓
14. Production architecture
```

You're already studying several of these, and the important thing now is to **connect them rather than learn them as isolated APIs**.

The conceptual chain is:

```text
                 APPLICATION
                      │
                      ▼
                  Context
                      │
                      ▼
                 Agent Run
                      │
             ┌────────┴────────┐
             │                 │
           State            Runtime
             │                 │
             │         ┌───────┼────────┐
             │         │       │        │
             │       Store   Stream   Execution
             │
             ▼
         Checkpointer
             │
             ▼
           Thread
             │
             ▼
          Tool call
             │
             ▼
        ToolRuntime
             │
      ┌──────┼─────────┐
      │      │         │
    state  context   config
      │      │         │
      └──────┴─────────┘
             │
             ▼
           Tool
```

Once this diagram makes intuitive sense, `Runtime` and `ToolRuntime` stop being mysterious framework objects and become ordinary **dependency-injection/execution-context mechanisms**.

One especially important next step for your current syllabus is **`Runtime + Context + State + Config + Thread/Checkpointer + Store` as one unified execution model**; that is where most of the apparent complexity of LangChain/LangGraph agents starts to disappear.

[1]: https://reference.langchain.com/python/langchain/tools/ToolRuntime?utm_source=chatgpt.com "ToolRuntime | langchain | LangChain Reference"
[2]: https://reference.langchain.com/python/langgraph/runtime/Runtime?utm_source=chatgpt.com "Runtime | langgraph | LangChain Reference"
[3]: https://reference.langchain.com/python/langgraph.prebuilt/tool_node/ToolRuntime?utm_source=chatgpt.com "ToolRuntime | langgraph.prebuilt | LangChain Reference"
[4]: https://reference.langchain.com/python/langchain-core/tools?utm_source=chatgpt.com "tools | langchain_core | LangChain Reference"
[5]: https://reference.langchain.com/python/langgraph/runtime/Runtime/context?utm_source=chatgpt.com "context | langgraph | LangChain Reference"
[6]: https://reference.langchain.com/python/langchain/agents/factory/create_agent?utm_source=chatgpt.com "create_agent | langchain | LangChain Reference"
[7]: https://reference.langchain.com/python/langchain/agents/middleware/types/AgentState?utm_source=chatgpt.com "AgentState | langchain | LangChain Reference"
[8]: https://github.com/langchain-ai/docs/blob/main/src/oss/langchain/short-term-memory.mdx?utm_source=chatgpt.com "docs/src/oss/langchain/short-term-memory.mdx at main · langchain-ai/docs · GitHub"
[9]: https://reference.langchain.com/python/langgraph.prebuilt/tool_node/ToolRuntime/tools?utm_source=chatgpt.com "tools | langgraph.prebuilt | LangChain Reference"
[10]: https://reference.langchain.com/python/langgraph/runtime/ExecutionInfo?utm_source=chatgpt.com "ExecutionInfo | langgraph | LangChain Reference"
[11]: https://github.com/langchain-ai/langgraph/blob/main/libs/prebuilt/langgraph/prebuilt/tool_node.py?utm_source=chatgpt.com "langgraph/libs/prebuilt/langgraph/prebuilt/tool_node.py at main · langchain-ai/langgraph · GitHub"
[12]: https://reference.langchain.com/python/langchain-google-genai/langchain_google_genai?utm_source=chatgpt.com "langchain_google_genai | LangChain Reference"
[13]: https://reference.langchain.com/python/langgraph/types/Command?utm_source=chatgpt.com "Command | langgraph | LangChain Reference"
[14]: https://github.com/langchain-ai/langchain/issues/34363?utm_source=chatgpt.com "Runtime context is not supported now? · Issue #34363 · langchain-ai/langchain · GitHub"
[15]: https://reference.langchain.com/python/langgraph.prebuilt/tool_node?utm_source=chatgpt.com "tool_node | langgraph.prebuilt | LangChain Reference"
