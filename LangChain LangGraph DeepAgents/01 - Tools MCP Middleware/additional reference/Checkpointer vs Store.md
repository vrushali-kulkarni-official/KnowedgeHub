You are learning the right set of concepts at the right time. These ideas are the foundation underneath **LangChain agents, LangGraph persistence, memory, human-in-the-loop, multi-user agents, and production deployment**.

The most useful way to learn them is not as isolated definitions, but as parts of one execution model.

# 1. The big picture first

A modern LangChain/LangGraph agent execution can be thought of like this:

```text
                 YOUR APPLICATION
                       │
                       │
                 authenticated user
                       │
                       ▼
              ┌─────────────────┐
              │     RUN         │
              │ "do this task"  │
              └─────────────────┘
                 │     │     │
        ┌────────┘     │     └───────────┐
        ▼               ▼                 ▼
     CONFIG          CONTEXT            STATE
        │               │                 │
        │               │                 │
        │          "who/what is           │
        │           available             │
        │           for this run"         │
        │                                 │
        │                         "what the graph
        │                          currently knows/
        │                          has produced"
        │
        └── execution behavior
            + thread_id
            + tracing
            + limits
            + configurable values

                       │
                       ▼
                 AGENT / GRAPH
                       │
              ┌────────┴────────┐
              ▼                 ▼
         CHECKPOINTER          STORE
              │                 │
              │                 │
       thread-scoped       cross-thread
       persisted state     application data
              │                 │
              ▼                 ▼
        "conversation       "user preferences,
         history /          long-term memories,
         workflow state"    facts, knowledge"
```

The current LangGraph persistence model explicitly separates **checkpointers** and **stores**: checkpointers persist graph state for a single thread, while stores persist application-defined data across threads. ([GitHub][1])

And modern `create_agent()` exposes these concepts directly through `context_schema`, `checkpointer`, and `store`. ([LangChain Reference][2])

---

# 2. The five concepts you should keep in your head

Here is the mental model I want you to remember:

| Concept          | Think of it as            | Main question                                              |
| ---------------- | ------------------------- | ---------------------------------------------------------- |
| **Config**       | Execution envelope        | "How should this run execute?"                             |
| **Context**      | Run-scoped dependencies   | "What information/resources does this run have access to?" |
| **State**        | Workflow whiteboard       | "What does the agent currently know/hold/do?"              |
| **Checkpointer** | Snapshot/history system   | "How do I preserve state for this thread?"                 |
| **Store**        | Persistent filing cabinet | "What data should live beyond this thread?"                |

And:

| Concept             | Think of it as                                       |
| ------------------- | ---------------------------------------------------- |
| **Thread**          | One logical conversation/workflow                    |
| **thread_id**       | Identifier of that thread                            |
| **conversation_id** | Usually your application's name for the same concept |
| **run_id**          | One execution/turn inside a thread                   |
| **checkpoint_id**   | One particular saved state snapshot                  |

That last distinction is extremely important.

---

# 3. First: what is a "run"?

Before understanding config, context, and state, understand a **run**.

Suppose your user says:

> "Find my Q3 sales report and summarize it."

Your application might execute:

```text
HTTP request
    ↓
authenticate user
    ↓
create agent run
    ↓
agent receives input
    ↓
agent decides to search
    ↓
tool searches files
    ↓
agent reads result
    ↓
agent summarizes
    ↓
state updated
    ↓
checkpoint saved
    ↓
response returned
```

That entire execution is a **run**.

Now suppose the user says:

> "Now compare it with Q2."

That's another run.

But both runs may belong to the same **thread**:

```text
Thread: abc123

Run 1:
    "Find my Q3 sales report"

Run 2:
    "Now compare it with Q2"

Run 3:
    "What caused the difference?"
```

The thread ties these executions together.

LangGraph's checkpointer uses `thread_id` as the primary identifier for storing/retrieving checkpoint history. Reusing a `thread_id` is what gives conversational continuity. ([LangChain Reference][3])

---

# 4. What is Config?

Let's start with the simplest idea.

## Config is execution configuration

Modern LangChain uses `RunnableConfig`.

The current `RunnableConfig` contains fields such as:

```python
{
    "tags": [...],
    "metadata": {...},
    "callbacks": [...],
    "run_name": "...",
    "max_concurrency": ...,
    "recursion_limit": ...,
    "configurable": {...},
    "run_id": ...,
}
```

These are the current supported configuration concepts in LangChain's Runnable system. ([LangChain Reference][4])

For example:

```python
config = {
    "recursion_limit": 30,
    "tags": ["production", "sales-agent"],
    "metadata": {
        "tenant": "acme"
    },
}
```

You then do:

```python
result = graph.invoke(
    input_data,
    config=config,
)
```

---

# 5. What does Config actually control?

There are several categories.

## 5.1 Execution limits

For example:

```python
config = {
    "recursion_limit": 30
}
```

This controls execution behavior.

It is not application memory.

It does not mean:

> "Remember that the user likes Python."

It means:

> "Limit how deeply this execution can recurse."

Similarly:

```python
{
    "max_concurrency": 5
}
```

controls concurrency behavior. ([LangChain Reference][4])

---

# 6. Config and tracing

Config can also carry tracing-related information.

For example:

```python
config = {
    "tags": ["customer-support"],
    "metadata": {
        "tenant_id": "tenant-123",
        "environment": "production"
    },
    "run_name": "support-agent"
}
```

Tags and metadata propagate to child Runnable executions, which is particularly useful with tracing/observability systems. ([LangChain Reference][4])

For your stack, that can become useful with Langfuse/LangSmith-style observability.

For example:

```text
agent
 ├── model call
 ├── tool call
 ├── database call
 └── another model call
```

The parent configuration can propagate through the execution tree.

---

# 7. The important part: `configurable`

You will frequently see:

```python
config = {
    "configurable": {
        "thread_id": "abc123"
    }
}
```

This is very important.

`configurable` is where runtime values for configurable Runnable behavior are supplied. LangGraph also uses it for persistence-related configuration such as `thread_id`. ([LangChain Reference][4])

The most important example is:

```python
config = {
    "configurable": {
        "thread_id": "thread-001"
    }
}
```

---

# 8. Why is `thread_id` inside Config?

Because the checkpointer needs to know:

> "Which sequence of persisted checkpoints does this run belong to?"

Think about a database.

You might have:

```text
thread_id         checkpoint
--------------------------------
thread-001        checkpoint A
thread-001        checkpoint B
thread-001        checkpoint C

thread-002        checkpoint A
thread-002        checkpoint B
```

When you execute:

```python
config = {
    "configurable": {
        "thread_id": "thread-001"
    }
}
```

the checkpointer knows:

> Load the state associated with thread-001, execute the next step, and save the new state back into that thread.

That's why `thread_id` belongs in the configuration passed to the run. ([LangChain Reference][5])

---

# 9. Config is NOT State

This distinction is fundamental.

Consider:

```python
config = {
    "configurable": {
        "thread_id": "abc"
    }
}
```

This does not mean:

```python
state["thread_id"]
```

The thread ID is not automatically an application-state field.

It identifies the persistence context.

By contrast:

```python
state = {
    "messages": [...],
    "current_task": "search",
    "documents": [...],
}
```

is actual graph state.

---

# 10. Config is NOT Context

This distinction is even more important in modern LangGraph.

Old designs often put various runtime values into config.

Modern LangGraph provides **runtime context** specifically for run-scoped dependencies/data.

Current `StateGraph` has:

```python
StateGraph(
    state_schema=...,
    context_schema=...
)
```

and `context_schema` is the current mechanism for exposing run-scoped context such as `user_id`, database connections, or similar dependencies. ([LangChain Reference][6])

---

# 11. What is Context?

Think:

> **Context = information/dependencies provided to this particular run.**

Examples:

```text
user_id
tenant_id
authenticated principal
database connection
request-scoped service
feature flags
current locale
organization ID
request metadata
dependency objects
```

For example:

```python
from dataclasses import dataclass

@dataclass
class Context:
    user_id: str
    tenant_id: str
```

Then:

```python
context = Context(
    user_id="user-123",
    tenant_id="company-456",
)
```

and:

```python
graph.invoke(
    input_data,
    context=context,
)
```

The runtime exposes this context to graph nodes through `Runtime`. ([LangChain Reference][7])

---

# 12. Why does Context exist?

Because not everything an agent needs should become State.

Suppose the user ID is:

```text
user-123
```

You could theoretically put it inside State:

```python
{
    "messages": [...],
    "user_id": "user-123"
}
```

But conceptually this is wrong in many cases.

Why?

Because `user_id` is usually not something the agent's workflow is "discovering and changing."

It is an input/dependency of the run.

Think:

```text
STATE

"What is happening?"

messages
search_results
current_plan
tool_results
draft_answer
approval_required
```

versus:

```text
CONTEXT

"Who is executing this?"

user_id
tenant_id
database
permissions
service clients
request dependencies
```

Current LangGraph documentation describes runtime context as static/run-scoped context and dependencies such as `user_id` or `db_conn`. ([LangChain Reference][7])

---

# 13. Context is intended to be run-scoped

Suppose:

```python
@dataclass
class Context:
    user_id: str
    tenant_id: str
```

User A executes:

```python
Context(
    user_id="alice",
    tenant_id="company-a",
)
```

User B executes:

```python
Context(
    user_id="bob",
    tenant_id="company-b",
)
```

The same compiled graph can serve both users.

The graph doesn't need to be rebuilt.

Conceptually:

```text
                     SAME AGENT
                         │
              ┌──────────┴──────────┐
              │                     │
          Run A                  Run B
              │                     │
        Context Alice          Context Bob
              │                     │
          State A               State B
              │                     │
       Thread A              Thread B
```

This is extremely important for your enterprise harness.

---

# 14. Runtime

Modern LangGraph provides a `Runtime` object to graph nodes.

Example:

```python
from langgraph.runtime import Runtime

def my_node(state, runtime: Runtime[Context]):
    user_id = runtime.context.user_id
```

The current Runtime object provides access to:

```text
context
store
stream_writer
previous
execution_info
...
```

and deliberately does **not** contain `config`. For config, the current API recommends injecting `RunnableConfig` directly into the node if needed. ([LangChain Reference][7])

So:

```python
def my_node(
    state: State,
    runtime: Runtime[Context],
):
    user_id = runtime.context.user_id
```

versus:

```python
def my_node(
    state: State,
    config: RunnableConfig,
):
    thread_id = config["configurable"]["thread_id"]
```

These are deliberately different things.

---

# 15. Context in tools

Modern agents also have `ToolRuntime`.

This is extremely useful.

A tool can receive:

```python
from langchain.tools import ToolRuntime

@tool
def my_tool(
    value: str,
    runtime: ToolRuntime,
) -> str:
    ...
```

`ToolRuntime` gives the tool access to:

```text
runtime.state
runtime.context
runtime.config
runtime.store
runtime.tool_call_id
runtime.stream_writer
```

The current API automatically injects this runtime into tools; these runtime details are not exposed as normal model-generated tool arguments. ([LangChain Reference][8])

That is a very important modern pattern.

For example:

```python
@tool
def get_customer_data(
    customer_id: str,
    runtime: ToolRuntime,
) -> dict:
    user_id = runtime.context.user_id
```

The LLM only needs to provide:

```text
customer_id
```

It does **not** need to provide:

```text
user_id
tenant_id
database
thread_id
```

Your application/runtime already knows those things.

That's safer and cleaner.

---

# 16. Very important security principle

Never trust the LLM to tell you:

```text
user_id = "some user"
tenant_id = "some tenant"
```

Those are application-level identity/security values.

Instead:

```text
HTTP authentication
       ↓
your backend determines user_id
       ↓
Context(user_id=...)
       ↓
agent
       ↓
ToolRuntime.context.user_id
```

The model should not control identity.

This is especially important for your enterprise AI harness.

---

# 17. What is State?

Now we reach one of LangGraph's most important concepts.

**State is the data the graph evolves as it executes.**

Current `StateGraph` is explicitly defined as a graph whose nodes communicate by reading and writing shared state. A node conceptually has the signature:

```text
State → Partial[State]
```

State fields can also have reducers that determine how updates are combined. ([LangChain Reference][6])

---

# 18. Simple State example

Imagine:

```python
from typing import TypedDict

class State(TypedDict):
    count: int
```

A node may receive:

```python
{
    "count": 5
}
```

and return:

```python
{
    "count": 6
}
```

The graph's state evolves:

```text
Before node:

count = 5

      ↓

node executes

      ↓

After node:

count = 6
```

---

# 19. Agent State is much more interesting

A real agent might have:

```python
class State(TypedDict):
    messages: list
    current_task: str
    search_results: list
    selected_document: str | None
    approval_required: bool
```

During execution:

```text
START

messages = [...]
current_task = None
search_results = []
selected_document = None
approval_required = False
```

Then:

```text
LLM node

current_task = "search documents"
```

Then:

```text
search tool

search_results = [...]
```

Then:

```text
LLM node

selected_document = "Q3-report.pdf"
```

Then:

```text
approval node

approval_required = True
```

That's state.

---

# 20. State changes over time

This is one of the key differences between Context and State.

### Context

```text
user_id = alice
tenant_id = acme
```

typically remains the same throughout that run.

### State

```text
task = search
      ↓
task = read
      ↓
task = summarize
      ↓
task = completed
```

changes as the graph executes.

---

# 21. State and reducers

Suppose your state contains:

```python
class State(TypedDict):
    messages: list
```

You may want every new message to be appended rather than replacing the whole list.

LangGraph supports reducers for this.

Conceptually:

```text
old state:
messages = [A, B]

new update:
messages = [C]

reducer:

[A, B] + [C]

=

[A, B, C]
```

The `StateGraph` API supports reducer functions for state keys, and LangGraph's `add_messages` helper provides message-specific merging semantics. ([LangChain Reference][6])

---

# 22. State is not necessarily persistent

This is a critical misconception.

State exists regardless of whether you use persistence.

For example:

```python
graph = builder.compile()
```

The graph can have state.

But if you don't configure a checkpointer:

```text
Run
  ↓
State created
  ↓
nodes execute
  ↓
final result
  ↓
process ends
```

That state is not automatically available as durable conversational memory on the next invocation.

---

# 23. Checkpointer changes everything

Now:

```python
checkpointer = InMemorySaver()

graph = builder.compile(
    checkpointer=checkpointer
)
```

and:

```python
config = {
    "configurable": {
        "thread_id": "chat-123"
    }
}
```

Now LangGraph can persist the graph's state for that thread. ([GitHub][9])

So:

```text
Run 1
   ↓
State A
   ↓
checkpoint

Run 2 with same thread_id
   ↓
load State A
   ↓
continue
   ↓
State B
   ↓
checkpoint
```

---

# 24. The most important distinction: State vs Checkpoint

People often confuse these.

### State

The logical current data:

```python
{
    "messages": [...],
    "search_results": [...],
    "task": "summarize"
}
```

### Checkpoint

A persisted snapshot of state at a particular point in graph execution.

Think:

```text
State
   ↓
snapshot
   ↓
Checkpoint
```

A checkpointer is the mechanism that saves/retrieves those snapshots.

---

# 25. What is a Thread?

A LangGraph **thread is not an operating-system thread**.

It is a logical sequence of graph executions that share persisted thread state.

For a chatbot:

```text
Thread 123

Run 1:
User: Hi

Run 2:
User: My name is Bhargav

Run 3:
User: What did I tell you my name was?

Run 4:
User: Help me build an agent
```

All four runs can share the same checkpointed state.

LangGraph's checkpointer documentation describes `thread_id` as the identifier used to store/retrieve checkpoints and recommends reusing it for conversational memory. ([LangChain Reference][5])

---

# 26. Thread vs Run

This is worth memorizing.

```text
THREAD
│
├── RUN 1
├── RUN 2
├── RUN 3
└── RUN 4
```

A **thread** is the long-lived logical workflow/conversation.

A **run** is one execution.

So:

```text
thread_id = "thread-123"
```

does not mean:

```text
run_id = "thread-123"
```

They represent different concepts.

`RunnableConfig` also has a separate `run_id`, which identifies an individual LangChain run. ([LangChain Reference][4])

---

# 27. What is `thread_id`?

`thread_id` answers:

> "Which persisted conversation/workflow does this execution belong to?"

Example:

```python
config = {
    "configurable": {
        "thread_id": "9a7c..."
    }
}
```

The checkpointer uses this to locate the thread's checkpoints. ([LangChain Reference][5])

---

# 28. Should `thread_id` equal the user's ID?

Usually **no**.

This is a very important design choice.

Bad design:

```text
user_id = alice
thread_id = alice
```

Then Alice can only naturally have one conversation.

But a real ChatGPT-like application might have:

```text
Alice
 ├── thread-001 "AI project"
 ├── thread-002 "Travel"
 ├── thread-003 "Work"
 └── thread-004 "Research"
```

Therefore:

```text
user_id
    │
    ├── thread-001
    ├── thread-002
    └── thread-003
```

---

# 29. What is Conversation ID?

Here's a subtle but important point.

`conversation_id` is **not the central LangGraph persistence primitive** in the same way `thread_id` is.

In many applications, developers call their concept:

```text
conversation_id
```

while LangGraph calls it:

```text
thread_id
```

You can map them 1:1:

```text
your database:
conversation_id = abc123

LangGraph:
thread_id = abc123
```

That's perfectly reasonable.

But conceptually, **thread_id is the LangGraph concept**.

The official LangGraph APIs and SDK use `thread_id` for the thread resource and checkpoint identity. ([LangChain Reference][10])

---

# 30. So should you use both?

Usually you don't need both.

For your enterprise harness:

```text
Conversation
    id = UUID
```

could simply become:

```text
LangGraph thread_id = same UUID
```

Your relational DB might additionally have:

```text
conversation
------------
id
user_id
tenant_id
title
created_at
```

Then:

```text
conversation.id
      ↓
LangGraph thread_id
```

That's a clean architecture.

---

# 31. Multiple users and `thread_id`

Imagine:

```text
User A
    thread-A1
    thread-A2

User B
    thread-B1
    thread-B2
```

Your application might maintain:

```text
conversation table

id         user_id       tenant_id
-------------------------------------
A1         user-A        tenant-X
A2         user-A        tenant-X
B1         user-B        tenant-Y
B2         user-B        tenant-Y
```

Then:

```text
thread_id = conversation.id
```

The application authenticates:

```text
request.user_id = user-A
```

and verifies:

```text
conversation A1 belongs to user-A
```

Only then does it call:

```python
config = {
    "configurable": {
        "thread_id": "A1"
    }
}
```

---

# 32. Why authorization must happen before LangGraph

Suppose an attacker somehow sends:

```text
thread_id = B1
```

while authenticated as User A.

If your backend blindly calls:

```python
graph.invoke(
    input,
    {
        "configurable": {
            "thread_id": "B1"
        }
    }
)
```

you have potentially exposed User B's conversation.

The checkpointer sees:

> thread B1

It does not inherently know that the HTTP caller is User A.

Therefore:

```text
Authentication
      ↓
Authorization
      ↓
verify thread ownership
      ↓
LangGraph invoke
```

not:

```text
client sends thread_id
      ↓
LangGraph blindly loads it
```

This distinction is crucial for your multi-tenant enterprise design.

---

# 33. A better enterprise identity model

I would mentally model your system as:

```text
Tenant
  │
  ├── User
  │    │
  │    ├── Thread
  │    │    ├── Run
  │    │    ├── Run
  │    │    └── Run
  │    │
  │    └── Thread
  │
  └── User
       └── Thread
```

Then:

```text
Context
{
    tenant_id,
    user_id,
    permissions,
    ...
}
```

and:

```text
Config
{
    configurable: {
        thread_id
    }
}
```

and:

```text
Store namespace
(
    "tenant",
    tenant_id,
    "user",
    user_id
)
```

This gives you a clean separation.

---

# 34. What is a Checkpointer?

Now we can properly define it.

A **checkpointer persists the state of a graph across execution steps and runs, keyed by thread**.

Current LangGraph documentation specifically describes checkpointers as the mechanism for thread-scoped short-term memory, conversational continuity, human-in-the-loop, time travel, and fault tolerance. ([GitHub][1])

---

# 35. Why is it called "checkpoint"?

Think about a video game.

You reach:

```text
Level 5
```

and the game saves.

If the application crashes, you don't restart from Level 1.

You resume from:

```text
Checkpoint = Level 5
```

LangGraph does something conceptually similar.

```text
Graph execution

Step 1
  ↓
checkpoint

Step 2
  ↓
checkpoint

Step 3
  ↓
checkpoint

Step 4
  ↓
checkpoint
```

LangGraph persists graph state at graph execution boundaries/super-steps. ([GitHub][11])

---

# 36. What does a checkpoint contain?

Conceptually it can contain things such as:

```text
messages
tool results
state channels
graph progress
metadata
checkpoint ID
parent checkpoint
execution information
```

The internal representation is more sophisticated than simply:

```python
json.dumps(state)
```

The checkpointer has a serialization layer and maintains checkpoint/channel information needed for graph execution and recovery. ([LangChain Reference][3])

---

# 37. Why do we need checkpoints?

They enable things such as:

### Conversational continuity

```text
Run 1 → save
Run 2 → load previous state
```

### Human-in-the-loop

```text
agent
  ↓
approval required
  ↓
pause
  ↓
checkpoint
  ↓
human approves
  ↓
resume
```

### Failure recovery

```text
run
 ↓
failure
 ↓
resume from persisted state
```

### Time travel

You can inspect/retrieve previous checkpoints and branch from them.

The current checkpointer API exposes operations for getting/listing checkpoints, deleting threads, copying threads, pruning, and related history operations. ([LangChain Reference][5])

---

# 38. InMemorySaver / InMemorySaver

For learning and testing:

```python
from langgraph.checkpoint.memory import InMemorySaver

checkpointer = InMemorySaver()
```

Then:

```python
graph = builder.compile(
    checkpointer=checkpointer
)
```

The current documentation recommends in-memory checkpointing for testing/debugging rather than production persistence. ([LangChain Reference][12])

---

# 39. Why is InMemorySaver not production persistence?

Because:

```text
Python process
    ↓
RAM
```

If the process dies:

```text
RAM disappears
    ↓
checkpoints disappear
```

The current LangGraph persistence documentation explicitly warns that `InMemorySaver`/memory checkpointing loses data on process restart. ([GitHub][1])

Therefore:

```text
development/testing:
InMemorySaver

production:
PostgresSaver / AsyncPostgresSaver
```

---

# 40. PostgresSaver

For PostgreSQL-backed checkpoint persistence:

```python
from langgraph.checkpoint.postgres import PostgresSaver
```

The package is currently distributed as:

```text
langgraph-checkpoint-postgres
```

and the current API provides `PostgresSaver` and `AsyncPostgresSaver`. ([LangChain Reference][13])

For a synchronous application:

```python
with PostgresSaver.from_conn_string(DB_URI) as checkpointer:
    checkpointer.setup()

    graph = builder.compile(
        checkpointer=checkpointer
    )
```

For an async application such as your FastAPI backend:

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async with AsyncPostgresSaver.from_conn_string(DB_URI) as checkpointer:
    await checkpointer.setup()
```

The official async implementation provides async `get`, `put`, `list`, deletion, and other operations. ([LangChain Reference][14])

---

# 41. Important: `setup()` is not "save my graph"

This:

```python
checkpointer.setup()
```

means:

> Create/update the database schema required by the checkpointer.

It performs the necessary migrations/tables setup. It is something you do when provisioning/upgrading the persistence infrastructure, not something you conceptually need before every individual graph request. ([LangChain Reference][15])

In your FastAPI application, this generally belongs in application startup/deployment initialization rather than inside:

```text
POST /chat
```

for every request.

---

# 42. PostgresSaver preserves checkpoint history

Current `PostgresSaver` stores full checkpoint history.

That enables:

```text
checkpoint A
checkpoint B
checkpoint C
checkpoint D
```

and supports history/time-travel style workflows. ([LangChain Reference][12])

There is also:

```text
ShallowPostgresSaver
AsyncShallowPostgresSaver
```

which retain only the most recent checkpoint and therefore do not provide full time-travel history. ([LangChain Reference][16])

For learning, use the normal `PostgresSaver`.

---

# 43. What is a Store?

Now comes the other half of persistence.

A **Store** is not primarily for the graph's current execution state.

It is for **application-defined persistent data that can live across threads**.

Current LangGraph documentation describes stores as long-term, cross-thread memory, such as user preferences, facts, and shared knowledge. ([GitHub][1])

---

# 44. Example: why Checkpointer alone isn't enough

Suppose Alice has:

```text
Thread 1:
"Help me with Python"

Thread 2:
"Help me with my deployment"

Thread 3:
"Explain databases"
```

Suppose your agent learns:

```text
Alice prefers:
- concise answers
- Python examples
- PostgreSQL
```

Should that information belong only to Thread 1?

No.

It's a **user-level memory**.

You want:

```text
Alice
  │
  ├── Thread 1
  ├── Thread 2
  └── Thread 3
       ▲
       │
       │
  USER MEMORY
```

That's what the Store is for.

---

# 45. Checkpointer vs Store

The core distinction:

```text
              CHECKPOINTER
                   │
                   ▼
            one thread
                   │
          conversation state
```

versus:

```text
                 STORE
                   │
          ┌────────┼────────┐
          ▼        ▼        ▼
       thread 1 thread 2 thread 3
          \        |        /
             shared memory
```

The official LangGraph persistence table summarizes it as:

|                | Checkpointer          | Store                    |
| -------------- | --------------------- | ------------------------ |
| Persists       | graph state snapshots | application-defined data |
| Scope          | one thread            | across threads           |
| Typical memory | short-term            | long-term                |
| Example        | conversation history  | preferences/facts        |
| Access         | `thread_id`           | namespace + key          |

([GitHub][1])

---

# 46. Store uses namespace + key

This is important.

For example:

```python
store.put(
    ("users", "alice"),
    "preferences",
    {
        "tone": "concise",
        "language": "python",
    }
)
```

Conceptually:

```text
namespace:
("users", "alice")

key:
"preferences"

value:
{
    "tone": "concise",
    "language": "python"
}
```

Then:

```python
item = store.get(
    ("users", "alice"),
    "preferences",
)
```

The Store API uses namespaces and keys as its fundamental organization model. ([LangChain Reference][17])

---

# 47. Namespace design

For your enterprise system I would think in terms of:

```text
(
    "tenant",
    tenant_id,
    "user",
    user_id,
    "memories"
)
```

or something simpler such as:

```text
(
    "users",
    user_id,
    "memories"
)
```

For example:

```python
namespace = (
    "tenant",
    "acme",
    "user",
    "alice",
    "memories",
)
```

Then:

```python
store.put(
    namespace,
    "preferences",
    {
        "response_style": "concise",
        "favorite_language": "Python",
    },
)
```

This is how you can maintain long-term memory independent of any particular conversation.

---

# 48. InMemoryStore

The simplest store is:

```python
from langgraph.store.memory import InMemoryStore

store = InMemoryStore()
```

Current documentation describes it as an in-memory dictionary-backed store, optionally supporting vector search. ([LangChain Reference][17])

Example:

```python
store.put(
    ("users", "alice"),
    "preferences",
    {"theme": "dark"},
)

item = store.get(
    ("users", "alice"),
    "preferences",
)

print(item.value)
```

---

# 49. InMemoryStore can do semantic search

This is a particularly interesting feature.

A store can optionally be configured with an index:

```python
store = InMemoryStore(
    index={
        "dims": ...,
        "embed": ...,
        "fields": ["text"],
    }
)
```

Then:

```python
store.put(
    ("memories",),
    "memory-1",
    {"text": "I prefer Python over JavaScript"}
)
```

and you can perform similarity search.

Current `InMemoryStore` supports optional vector search; semantic indexing is disabled unless configured. ([LangChain Reference][17])

This is useful for long-term agent memory.

---

# 50. Store is not the same as vector database

Important.

A Store is a persistence abstraction.

It may support:

```text
key-value retrieval
+
namespace organization
+
filtering
+
optional semantic search
+
optional TTL
```

It isn't simply:

```text
"LangGraph's vector database"
```

You can use it as a normal key-value store without embeddings.

Semantic search is an optional capability. ([LangChain Reference][18])

---

# 51. PostgresStore

Now for production:

```python
from langgraph.store.postgres import PostgresStore
```

Current LangGraph provides a Postgres-backed store with optional `pgvector` semantic search. ([LangChain Reference][19])

Example:

```python
with PostgresStore.from_conn_string(DB_URI) as store:
    store.setup()

    store.put(
        ("users", "alice"),
        "preferences",
        {
            "theme": "dark",
            "language": "python",
        },
    )

    item = store.get(
        ("users", "alice"),
        "preferences",
    )
```

---

# 52. PostgresStore vs PostgresSaver

This is one of the most important things for you to understand.

They both use PostgreSQL.

They do **different jobs**.

## PostgresSaver

```text
LangGraph graph
      ↓
current graph state
      ↓
PostgresSaver
      ↓
checkpoints
```

## PostgresStore

```text
Agent/application
      ↓
long-term application data
      ↓
PostgresStore
      ↓
memory/preferences/facts/etc.
```

They aren't interchangeable.

---

# 53. Think of your PostgreSQL database containing two conceptual worlds

You might have:

```text
PostgreSQL
│
├── application tables
│   ├── users
│   ├── tenants
│   ├── conversations
│   ├── permissions
│   └── ...
│
├── LangGraph checkpoint data
│   ├── checkpoints
│   ├── checkpoint_blobs
│   └── checkpoint_writes
│
└── LangGraph Store data
    └── store / memory data
```

Current Postgres checkpointer migrations create tables such as `checkpoints`, `checkpoint_blobs`, and `checkpoint_writes`. ([LangChain Reference][20])

PostgresStore has its own persistence layer.

So one PostgreSQL server/database can host both.

---

# 54. `AsyncPostgresStore`

Because your backend is FastAPI and you're building an asynchronous enterprise backend, pay attention to this version:

```python
from langgraph.store.postgres import AsyncPostgresStore
```

The current Postgres store implementation includes an async counterpart and supports connection pooling. ([LangChain Reference][21])

For example:

```python
async with AsyncPostgresStore.from_conn_string(
    DB_URI,
) as store:
    await store.setup()
```

For higher concurrency, the current implementation supports pool configuration. ([GitHub][22])

---

# 55. One database, two abstractions

This is a perfectly reasonable production architecture:

```text
                    PostgreSQL
                         │
            ┌────────────┴────────────┐
            │                         │
      PostgresSaver              PostgresStore
            │                         │
            ▼                         ▼
   thread/checkpoints       cross-thread memory
```

And your application database can coexist around those.

---

# 56. Config vs Context vs State

Let's now make the distinction extremely clear.

## Config

Answers:

> How should this execution behave or be identified?

Examples:

```text
thread_id
run_id
recursion_limit
max_concurrency
tags
metadata
callbacks
configurable values
```

---

## Context

Answers:

> What run-scoped identity/dependencies/resources are available?

Examples:

```text
user_id
tenant_id
permissions
database connection
service clients
feature flags
request-scoped objects
```

---

## State

Answers:

> What is the workflow currently carrying and evolving?

Examples:

```text
messages
tool results
plan
search results
approval status
current task
generated draft
workflow variables
```

---

# 57. A concrete example

Suppose Alice sends:

> "Find the Q3 finance report."

### Config

```python
config = {
    "configurable": {
        "thread_id": "thread-9f31"
    },
    "tags": ["finance"],
}
```

---

### Context

```python
context = Context(
    user_id="alice",
    tenant_id="acme",
)
```

---

### State

At the beginning:

```python
{
    "messages": [
        "Find the Q3 finance report"
    ],
    "search_results": [],
    "selected_document": None
}
```

After search:

```python
{
    "messages": [
        "Find the Q3 finance report"
    ],
    "search_results": [
        "Q3-finance.pdf",
        "Q3-finance-final.pdf"
    ],
    "selected_document": None
}
```

After choosing:

```python
{
    "messages": [...],
    "search_results": [...],
    "selected_document": "Q3-finance-final.pdf"
}
```

The checkpointer persists the thread's evolving state.

The Store might contain:

```python
(
    "tenant", "acme",
    "user", "alice",
    "memories"
)

"preferences"
{
    "response_style": "concise"
}
```

---

# 58. One very useful analogy

Imagine an employee working on a case.

### Config = instructions on the work order

```text
Case ID: 123
Maximum steps: 30
Tags: finance
```

### Context = employee badge + equipment

```text
Employee: Alice
Company: ACME
Permissions: finance-read
Database connection: ...
```

### State = whiteboard

```text
Task: Find Q3 report
Search results: ...
Chosen file: ...
Need approval: yes
```

### Checkpointer = photographs of the whiteboard

```text
Snapshot 1
Snapshot 2
Snapshot 3
Snapshot 4
```

### Store = company filing cabinet

```text
Alice's preferences
Company policies
Long-term knowledge
Shared facts
```

### Thread = the case folder

```text
Case 123
  Run 1
  Run 2
  Run 3
```

This analogy is surprisingly useful when designing agents.

---

# 59. Modern LangGraph agent architecture

Current `create_agent()` directly exposes:

```python
create_agent(
    model=...,
    tools=[...],
    context_schema=...,
    checkpointer=...,
    store=...,
)
```

The current API describes `checkpointer` as persisting state for a single thread and `store` as persistent storage across multiple threads. ([LangChain Reference][2])

Conceptually:

```python
agent = create_agent(
    model=model,
    tools=tools,
    context_schema=Context,
    checkpointer=checkpointer,
    store=store,
)
```

then:

```python
result = agent.invoke(
    {
        "messages": [
            {
                "role": "user",
                "content": "Find my report",
            }
        ]
    },
    config={
        "configurable": {
            "thread_id": "thread-123"
        }
    },
    context=Context(
        user_id="alice",
        tenant_id="acme",
    ),
)
```

That single call illustrates all three:

```text
input
  ↓
State input

config
  ↓
thread/execution configuration

context
  ↓
run-scoped dependencies
```

---

# 60. How a tool sees all of this

A modern tool can use `ToolRuntime`.

Conceptually:

```python
from langchain.tools import ToolRuntime

@tool
def get_my_preferences(
    runtime: ToolRuntime,
) -> str:
    user_id = runtime.context.user_id

    item = runtime.store.get(
        ("users", user_id),
        "preferences",
    )

    return str(item.value if item else {})
```

Inside the tool:

```text
runtime.context
        ↓
      user_id

runtime.config
        ↓
     thread_id

runtime.state
        ↓
 current graph state

runtime.store
        ↓
 long-term memory
```

This is one of the cleanest modern ways to understand the runtime model. ([LangChain Reference][8])

---

# 61. A complete lifecycle

Let's trace a real request.

Alice sends:

```text
"Compare my Q3 and Q2 reports."
```

## Step 1 — authentication

Your FastAPI backend determines:

```python
user_id = "alice"
tenant_id = "acme"
```

---

## Step 2 — conversation lookup

Application database:

```text
conversation_id = "c-123"
owner = alice
tenant = acme
```

---

## Step 3 — authorization

Your backend verifies:

```text
Alice owns c-123
```

---

## Step 4 — create config

```python
config = {
    "configurable": {
        "thread_id": "c-123"
    }
}
```

---

## Step 5 — create context

```python
context = Context(
    user_id="alice",
    tenant_id="acme",
)
```

---

## Step 6 — checkpointer loads thread

```text
thread c-123
      ↓
latest checkpoint
      ↓
previous state
```

---

## Step 7 — agent executes

Agent sees the state.

Tools can access:

```text
user_id
tenant_id
store
state
config
```

through runtime mechanisms.

---

## Step 8 — agent updates state

For example:

```text
messages += new messages
reports = [...]
comparison = ...
```

---

## Step 9 — checkpoint

The new graph state is persisted.

---

## Step 10 — store lookup

The agent may retrieve:

```text
Alice's preferred response style
```

from `PostgresStore`.

---

## Step 11 — response

The final answer is returned to Alice.

---

# 62. Checkpointer vs Store: the practical rule

Ask yourself:

## "Does this belong to this conversation/workflow?"

Use:

**Checkpointer / State**

Examples:

```text
current messages
tool results
current plan
pending approval
current workflow step
intermediate results
```

---

## "Should this survive across conversations?"

Use:

**Store**

Examples:

```text
user preferences
user profile memory
long-term facts
organization-level memory
shared knowledge
learned preferences
```

---

# 63. Another example

Alice tells agent:

> "Remember that I prefer concise responses."

You generally don't want this permanently stuffed into:

```text
Thread A's state
```

because Alice may later start:

```text
Thread B
```

You probably want:

```text
Store
namespace = user Alice
key = preferences

{
    "response_style": "concise"
}
```

Then Thread A, B, C, D can all access it.

---

# 64. But don't put everything into Store either

Suppose the current conversation has:

```text
search result
temporary tool output
current plan
pending approval
temporary API response
```

Do not automatically put all of that into long-term memory.

That belongs more naturally in:

```text
State → Checkpointer
```

The Store should contain information intentionally promoted into durable application memory.

That distinction becomes extremely important for cost, privacy, retention, and correctness.

---

# 65. Short-term vs long-term memory

A useful language is:

```text
Short-term memory
      =
thread state
      =
checkpointer
```

and:

```text
Long-term memory
      =
cross-thread data
      =
store
```

This is also the terminology used by current LangGraph documentation. ([GitHub][1])

---

# 66. Modern vs old/deprecated APIs

Because you specifically asked for current vs deprecated, this part is important.

## Current

Use:

```python
from langchain.agents import create_agent
```

The current `create_agent()` is the modern agent factory. ([LangChain Reference][2])

---

## Deprecated: `create_react_agent`

Older LangGraph tutorials frequently show:

```python
from langgraph.prebuilt import create_react_agent
```

The current reference explicitly marks `create_react_agent` as deprecated and says to use:

```python
from langchain.agents import create_agent
```

instead. ([LangChain Reference][23])

So when you find old tutorials:

```text
create_react_agent
```

translate that mentally to:

```text
create_agent
```

unless you are specifically studying legacy code.

---

# 67. Deprecated: `config_schema`

Older examples may show:

```python
StateGraph(
    state_schema=State,
    config_schema=Config,
)
```

Current LangGraph explicitly marks `config_schema` as deprecated since v0.6 and says to use:

```python
context_schema=Context
```

for run-scoped context. ([LangChain Reference][6])

This is one of the most important migration points.

### Old

```python
config_schema=...
```

### Current

```python
context_schema=...
```

---

# 68. Deprecated: MessageGraph

Older LangGraph tutorials may show:

```python
MessageGraph
```

The current reference marks `MessageGraph` as deprecated. Modern graph design uses `StateGraph`, with message state represented through state schemas/helpers such as `MessagesState` and `add_messages`. ([LangChain Reference][24])

---

# 69. Old tutorials are particularly confusing around config

You'll often find code such as:

```python
config = {
    "configurable": {
        "user_id": "123",
        "thread_id": "456"
    }
}
```

You may still encounter configurations like this in existing applications, and `configurable` is a valid mechanism for actual configurable Runnable fields.

But for **new LangGraph designs**, don't automatically treat `configurable` as your general-purpose context dictionary.

Modern LangGraph gives you:

```python
context_schema=Context
```

for explicit runtime context.

Use:

```python
context=Context(...)
```

for things like:

```text
user_id
tenant_id
services
dependencies
request-scoped data
```

while retaining:

```python
config["configurable"]["thread_id"]
```

for thread identification/persistence.

This separation makes your architecture much clearer. ([LangChain Reference][4])

---

# 70. InMemorySaver vs InMemoryStore

Another common beginner confusion:

```text
InMemorySaver
```

and:

```text
InMemoryStore
```

are not two names for the same thing.

They are different systems.

### InMemorySaver

```text
short-term/thread memory
```

for checkpoints.

### InMemoryStore

```text
long-term/cross-thread memory
```

for application-defined data.

Current references clearly distinguish the two. ([LangChain Reference][12])

---

# 71. Production architecture for your FastAPI project

For the enterprise harness you're building, a sensible modern architecture is:

```text
                         FastAPI
                            │
                    Authentication
                            │
                    Authorization
                            │
                ┌───────────┴───────────┐
                │                       │
             Config                  Context
                │                       │
           thread_id            user_id / tenant_id
                │                       │
                └───────────┬───────────┘
                            │
                       create_agent
                            │
               ┌────────────┴────────────┐
               │                         │
          PostgresSaver             PostgresStore
               │                         │
       thread checkpoints        cross-thread memory
               │                         │
               └────────────┬────────────┘
                            │
                       PostgreSQL
```

Then your normal application tables can sit alongside them:

```text
PostgreSQL
│
├── users
├── tenants
├── conversations
├── permissions
├── integrations
│
├── LangGraph checkpoints
│
└── LangGraph store
```

---

# 72. Why PostgreSQL is a particularly natural fit for your stack

You're already working with PostgreSQL.

That means you can potentially use:

```text
PostgreSQL
+
PostgresSaver
+
PostgresStore
+
pgvector
+
your application tables
```

instead of introducing several separate persistence systems immediately.

Current `PostgresStore` supports optional vector search through `pgvector`, while `PostgresSaver` handles checkpoint persistence. ([LangChain Reference][19])

---

# 73. Async FastAPI example

For your FastAPI backend, I'd teach the production pattern using the asynchronous implementations.

Conceptually:

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres import AsyncPostgresStore
```

Then application startup creates the persistence infrastructure:

```python
async with AsyncPostgresSaver.from_conn_string(DB_URI) as checkpointer:
    await checkpointer.setup()

    async with AsyncPostgresStore.from_conn_string(DB_URI) as store:
        await store.setup()

        agent = create_agent(
            model=model,
            tools=tools,
            context_schema=Context,
            checkpointer=checkpointer,
            store=store,
        )
```

The current libraries provide these async PostgreSQL implementations and require initial `setup()` to create/migrate the required database structures. ([LangChain Reference][14])

In a real FastAPI application, you would manage their lifecycle with your application's lifespan rather than constructing them for every request.

---

# 74. Important production detail: don't create a DB persistence object per request

Conceptually avoid:

```text
HTTP request
    ↓
create PostgresSaver
    ↓
connect
    ↓
invoke
    ↓
disconnect
```

for every request.

Prefer:

```text
Application startup
    ↓
create persistence resources/pools
    ↓
application serves requests
    ↓
many requests reuse them
    ↓
application shutdown
    ↓
cleanup
```

The async Postgres store supports connection pooling, which is especially relevant for a concurrent FastAPI service. ([GitHub][22])

---

# 75. The security side of Postgres checkpoints

There's another advanced point worth knowing.

LangGraph's checkpoint serialization uses a serialization mechanism that can handle LangChain/LangGraph types. Current documentation also warns about deserialization security when an attacker can directly manipulate checkpoint data.

The current Postgres checkpointer documentation recommends strict MessagePack settings or an explicit allowed-module list to restrict deserialization. ([LangChain Reference][13])

So production persistence is not simply:

```text
"put random Python objects into Postgres"
```

and forget about it.

Serialization and trust boundaries matter.

---

# 76. One more important concept: `checkpoint_id`

You will eventually encounter:

```text
thread_id
checkpoint_ns
checkpoint_id
```

Don't confuse them.

Think:

```text
Thread
  │
  ├── checkpoint 1
  ├── checkpoint 2
  ├── checkpoint 3
  └── checkpoint 4
```

`thread_id` identifies:

```text
the thread
```

`checkpoint_id` identifies:

```text
a specific checkpoint in that thread
```

The current checkpointer API can retrieve/list checkpoints and supports operations against particular checkpoints. ([LangChain Reference][5])

This becomes useful for:

```text
time travel
branching
resume from a particular checkpoint
debugging
human approval workflows
```

---

# 77. What is `checkpoint_ns`?

This is more advanced.

LangGraph may use checkpoint namespaces to distinguish persistence contexts, particularly around subgraphs.

You will see things such as:

```python
{
    "configurable": {
        "thread_id": "...",
        "checkpoint_ns": "..."
    }
}
```

You don't need to manually manipulate this during your beginner stage.

For now:

```text
thread_id
```

is the important concept.

Later, when you learn subgraphs and multi-agent workflows, `checkpoint_ns` becomes relevant.

---

# 78. A complete mental model

Here's the model I want you to internalize.

```text
                         USER
                          │
                          ▼
                    HTTP REQUEST
                          │
                          ▼
                 Authentication
                          │
                          ▼
                  Authorization
                          │
              ┌───────────┴───────────┐
              │                       │
              ▼                       ▼
           CONTEXT                  THREAD
              │                       │
       user_id, tenant_id         thread_id
       permissions                conversation
       dependencies                     │
              │                         │
              │                         ▼
              │                    CHECKPOINTER
              │                         │
              │                  previous STATE
              │                         │
              └─────────────┬───────────┘
                            │
                            ▼
                         AGENT
                            │
                   ┌────────┴────────┐
                   │                 │
                   ▼                 ▼
                STATE             STORE
                   │                 │
            current workflow     long-term data
                   │                 │
                   └────────┬────────┘
                            │
                            ▼
                       next STATE
                            │
                            ▼
                       CHECKPOINT
                            │
                            ▼
                          RESULT
```

---

# 79. The golden rules

I recommend memorizing these.

### Rule 1

**State = evolving workflow data.**

```text
What the graph is currently doing/holding.
```

---

### Rule 2

**Context = run-scoped identity/dependencies.**

```text
Who is running?
What resources/dependencies are available?
```

---

### Rule 3

**Config = execution configuration and identifiers.**

```text
How should the run execute?
Which thread does this belong to?
How should it be traced/limited?
```

---

### Rule 4

**Thread = logical conversation/workflow.**

```text
thread_id identifies it.
```

---

### Rule 5

**Checkpointer = persistence for thread state.**

```text
State → checkpoint → resume later
```

---

### Rule 6

**Store = persistent application memory across threads.**

```text
User preferences
Facts
Long-term memories
Shared knowledge
```

---

### Rule 7

**`thread_id` is not `user_id`.**

One user can own many threads.

```text
user
 ├── thread A
 ├── thread B
 └── thread C
```

---

### Rule 8

**`thread_id` is not authorization.**

Your application must verify ownership before invoking the graph.

---

### Rule 9

**Don't put everything into State.**

Especially identity and infrastructure dependencies.

---

### Rule 10

**Don't put everything into Store.**

Not every temporary intermediate value deserves long-term memory.

---

# 80. The most important table to remember

| Question                                    | Use             |
| ------------------------------------------- | --------------- |
| "Which conversation is this?"               | `thread_id`     |
| "How should this execution behave?"         | `config`        |
| "Who is executing this?"                    | `context`       |
| "What has the workflow discovered so far?"  | `state`         |
| "How do I resume this conversation later?"  | `checkpointer`  |
| "What should survive across conversations?" | `store`         |
| "Which exact execution happened?"           | `run_id`        |
| "Which exact saved state?"                  | `checkpoint_id` |

---

# 81. Your modern API map

For your learning roadmap, I would keep this map in your notes:

```text
LangChain
│
└── create_agent()
        │
        ├── model
        ├── tools
        ├── middleware
        ├── context_schema
        ├── checkpointer
        └── store
                │
                ▼
             LangGraph
                │
        ┌───────┼────────┐
        │       │        │
      State   Context   Runtime
        │       │        │
        │       │        ├── Runtime
        │       │        └── ToolRuntime
        │
        ▼
   Checkpointer
        │
        ├── InMemorySaver
        ├── PostgresSaver
        └── AsyncPostgresSaver

Store
 │
 ├── InMemoryStore
 ├── PostgresStore
 └── AsyncPostgresStore
```

`create_agent()` is the current LangChain agent API, and LangChain agents are built on LangGraph infrastructure for persistence, durable execution, streaming, and human-in-the-loop capabilities. ([LangChain Reference][2])

---

# 82. Current vs deprecated cheat sheet

| Older/legacy material                       | Modern approach                        |
| ------------------------------------------- | -------------------------------------- |
| `create_react_agent`                        | `langchain.agents.create_agent`        |
| `config_schema`                             | `context_schema`                       |
| general runtime data stuffed into config    | explicit `context_schema` + `context=` |
| `MessageGraph`                              | `StateGraph`                           |
| ad-hoc long-term memory in checkpoint state | `Store`                                |
| in-memory persistence for production        | PostgreSQL-backed persistence          |
| `InMemorySaver` for production              | `PostgresSaver` / `AsyncPostgresSaver` |

The deprecations for `create_react_agent`, `config_schema`, and `MessageGraph` are explicitly reflected in the current references. ([LangChain Reference][23])

---

# 83. One final example tying everything together

Suppose your enterprise AI harness has:

```text
Tenant: ACME
User: Bhargav
Conversation: Finance Q3
```

You might have:

### Application identity

```python
tenant_id = "acme"
user_id = "bhargav"
thread_id = "8e2b..."
```

### Context

```python
Context(
    tenant_id="acme",
    user_id="bhargav",
)
```

### Config

```python
{
    "configurable": {
        "thread_id": "8e2b..."
    },
    "tags": ["finance"],
}
```

### State

```python
{
    "messages": [...],
    "search_results": [...],
    "selected_report": "q3.pdf",
    "comparison": None,
}
```

### Checkpointer

```text
thread 8e2b...
    ↓
checkpoint 1
checkpoint 2
checkpoint 3
checkpoint 4
```

### Store

```text
namespace:
("tenant", "acme", "user", "bhargav", "memories")

key:
"preferences"

value:
{
    "response_style": "concise"
}
```

Now you have a clean separation:

```text
             CONFIG
                │
          thread identity
                │
                ▼
              THREAD
                │
                ▼
           CHECKPOINTER
                │
                ▼
              STATE
                ▲
                │
             AGENT
                │
          ┌─────┴─────┐
          │           │
       CONTEXT       STORE
          │           │
       identity     long-term
       deps         memory
```

That is the architecture you should have in your head before moving into advanced LangGraph topics.

---

# 84. What I recommend you learn next

Given your current LangChain/LangGraph/Deep Agents learning path, the natural next layer is:

**`State → reducers → Runtime → ToolRuntime → checkpointer → thread lifecycle → interrupts → time travel → Store namespaces → long-term memory → subgraph persistence → multi-agent threads`.**

The most important hands-on exercise is to build one tiny agent with **all five concepts at once**:

```text
create_agent
+
Context
+
State
+
InMemorySaver
+
InMemoryStore
+
thread_id
```

Then replace only:

```text
InMemorySaver → AsyncPostgresSaver
InMemoryStore → AsyncPostgresStore
```

and you'll see exactly what changes and what does not.

That exercise is much more valuable than memorizing definitions.

[1]: https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/persistence.mdx?utm_source=chatgpt.com "docs/src/oss/langgraph/persistence.mdx at main · langchain-ai/docs · GitHub"
[2]: https://reference.langchain.com/python/langchain/agents/factory/create_agent?utm_source=chatgpt.com "create_agent | langchain | LangChain Reference"
[3]: https://reference.langchain.com/python/langgraph.checkpoint/base?utm_source=chatgpt.com "base | langgraph.checkpoint | LangChain Reference"
[4]: https://reference.langchain.com/python/langchain-core/runnables/config/RunnableConfig?utm_source=chatgpt.com "RunnableConfig | langchain_core | LangChain Reference"
[5]: https://reference.langchain.com/python/langgraph.checkpoint/base/BaseCheckpointSaver?utm_source=chatgpt.com "BaseCheckpointSaver | langgraph.checkpoint | LangChain Reference"
[6]: https://reference.langchain.com/python/langgraph/graph/state/StateGraph?utm_source=chatgpt.com "StateGraph | langgraph | LangChain Reference"
[7]: https://reference.langchain.com/python/langgraph/runtime/Runtime?utm_source=chatgpt.com "Runtime | langgraph | LangChain Reference"
[8]: https://reference.langchain.com/python/langgraph.prebuilt/tool_node/ToolRuntime?utm_source=chatgpt.com "ToolRuntime | langgraph.prebuilt | LangChain Reference"
[9]: https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/add-memory.mdx?utm_source=chatgpt.com "docs/src/oss/langgraph/add-memory.mdx at main · langchain-ai/docs · GitHub"
[10]: https://reference.langchain.com/python/langgraph-sdk?utm_source=chatgpt.com "langgraph_sdk | LangChain Reference"
[11]: https://github.com/langchain-ai/langchain-skills/blob/main/config/skills/langgraph-persistence/SKILL.md?utm_source=chatgpt.com "langchain-skills/config/skills/langgraph-persistence/SKILL.md at main · langchain-ai/langchain-skills · GitHub"
[12]: https://reference.langchain.com/python/langgraph/checkpoints?utm_source=chatgpt.com "checkpoints | langgraph | LangChain Reference"
[13]: https://reference.langchain.com/python/langgraph.checkpoint.postgres?utm_source=chatgpt.com "langgraph.checkpoint.postgres | LangChain Reference"
[14]: https://reference.langchain.com/python/langgraph.checkpoint.postgres/aio/AsyncPostgresSaver?utm_source=chatgpt.com "AsyncPostgresSaver | langgraph.checkpoint.postgres | LangChain Reference"
[15]: https://reference.langchain.com/python/langgraph.checkpoint.postgres/PostgresSaver/setup?utm_source=chatgpt.com "setup | langgraph.checkpoint.postgres | LangChain Reference"
[16]: https://reference.langchain.com/python/langgraph.checkpoint.postgres/aio?utm_source=chatgpt.com "aio | langgraph.checkpoint.postgres | LangChain Reference"
[17]: https://reference.langchain.com/python/langgraph.store/memory/InMemoryStore?utm_source=chatgpt.com "InMemoryStore | langgraph.store | LangChain Reference"
[18]: https://reference.langchain.com/python/langgraph.store/base/BaseStore?utm_source=chatgpt.com "BaseStore | langgraph.store | LangChain Reference"
[19]: https://reference.langchain.com/python/langgraph.store.postgres/base/PostgresStore?utm_source=chatgpt.com "PostgresStore | langgraph.store.postgres | LangChain Reference"
[20]: https://reference.langchain.com/python/langgraph.checkpoint.postgres/base/MIGRATIONS?utm_source=chatgpt.com "MIGRATIONS | langgraph.checkpoint.postgres | LangChain Reference"
[21]: https://reference.langchain.com/python/langgraph.store.postgres?utm_source=chatgpt.com "langgraph.store.postgres | LangChain Reference"
[22]: https://github.com/langchain-ai/langgraph/blob/main/libs/checkpoint-postgres/langgraph/store/postgres/aio.py?utm_source=chatgpt.com "langgraph/libs/checkpoint-postgres/langgraph/store/postgres/aio.py at main · langchain-ai/langgraph · GitHub"
[23]: https://reference.langchain.com/python/langgraph.prebuilt/chat_agent_executor/create_react_agent?utm_source=chatgpt.com "create_react_agent | langgraph.prebuilt | LangChain Reference"
[24]: https://reference.langchain.com/python/langgraph/graph?utm_source=chatgpt.com "graph | langgraph | LangChain Reference"
