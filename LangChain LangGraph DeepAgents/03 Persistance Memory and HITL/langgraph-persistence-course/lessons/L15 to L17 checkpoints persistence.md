# LangGraph Learning Course: L15–L17

## Persistence, debugging, durability, retries, and crash recovery

These three lessons form one of the most important parts of learning LangGraph at a production engineering level. They explain how to build agents that can continue conversations, survive failures, resume interrupted work, and avoid repeating dangerous operations.

I'll teach them as one connected course, using a shared example throughout rather than three disconnected collections of definitions.

## 1. The learning order

Your proposed order is already fundamentally sound. I'll refine it slightly by introducing the mental model first, then following the lifecycle of a real graph.

L15 — Checkpointers & Threads

Understand what gets saved, where it gets saved, how threads identify conversations, and how to configure persistent storage.

L16 — State Inspection & Time Travel

Inspect snapshots, read execution history, edit state safely, replay earlier execution, and debug a particular conversation.

L17 — Durability, Retries & Crash Recovery

Understand what survives a crash, what gets retried, why duplicate side effects happen, and how idempotency protects production systems.

## 2. Current implementation baseline

As of October 29, 2026, the official LangGraph documentation includes the newer LangGraph 1.2-era fault-tolerance APIs. The PostgreSQL checkpointer repository reports `langgraph-checkpoint-postgres` version 3.2.0. I'll use these current APIs as the reference point.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

Docs by LangChain+1

A few important distinctions will be maintained throughout the lessons:

- Current: `InMemorySaver`, `PostgresSaver`, `AsyncPostgresSaver`, `RetryPolicy`, `get_state()`, `get_state_history()`, and `update_state()`.
- Use with caution: Community-maintained checkpointers, backend-specific pruning or copying operations, and newer beta features.
- Not a guarantee: A saved checkpoint does not automatically make an external action exactly-once. We will prove why in L17.

I'll use deterministic Python nodes for most examples so that you can understand LangGraph without paying for LLM calls or being distracted by model behavior. When we reach the agent integration example, I'll use Gemini through the LangChain ecosystem, as you prefer.

# L15 — Checkpointers & Threads

## 0. Why this lesson comes first

Imagine you build an enterprise AI assistant that can read documents, search internal systems, and perform tasks.

A user asks:

> Find the latest invoice, verify its amount, prepare an approval request, and wait for my permission before sending it.

Your LangGraph workflow might look like this:

1\. Find the invoice

2\. Verify the invoice

3\. Prepare approval request

4\. Wait for human approval

5\. Send after approval

Now consider four situations.

Situation A: The user sends another message. The agent should know which invoice they were discussing.

Situation B: The application restarts. The graph should be able to recover its previous execution state rather than necessarily starting over.

Situation C: The workflow fails at step 4. You need to understand where it stopped and resume safely.

Situation D: The user disputes a decision. You need to inspect the previous state, understand what happened, and potentially replay the workflow from an earlier point.

Without persistence, these requirements become much harder.

LangGraph's persistence layer addresses them with checkpoints and threads. The official documentation distinguishes these from stores, which are intended for application-defined information shared across threads, such as long-term user preferences.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

Docs by LangChain

## 1. The one-sentence model

A checkpointer saves snapshots of a LangGraph thread's execution state so the graph can continue from previously saved work instead of always starting from scratch.

Let's understand every part of this sentence.

### 1.1 What is a graph's state?

Suppose we define a graph with this state:

```
from typing_extensions import TypedDictclass InvoiceState(TypedDict, total=False):    invoice_id: str    amount: float    verified: bool    approval_status: str
```

This is the information the graph needs to perform its workflow.

At different stages, the state could look like this:

INITIAL STATE

```
{    "invoice_id": "INV-100",}
```

AFTER VERIFICATION

```
{    "invoice_id": "INV-100",    "amount": 2500.0,    "verified": True,}
```

AFTER APPROVAL

```
{    "invoice_id": "INV-100",    "amount": 2500.0,    "verified": True,    "approval_status": "approved",}
```

The graph moves from one state to another as nodes execute.

A state object is not inherently persistent. Without a checkpointer, a local Python dictionary does not magically survive a process restart.

### 1.2 What is a checkpoint?

A checkpoint is a saved representation of the graph's state and execution information at a particular point.

Think of a video game.

When you save a game, you save more than just the character's name. You need information such as the character's position, inventory, completed quests, and where to resume.

Similarly, a LangGraph checkpoint needs to preserve enough internal information to restore the workflow correctly.

It contains state values, channel-version information, and execution-related information. The checkpointing system also tracks execution metadata and intermediate task writes.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

Docs by LangChain+1

### 1.3 What is a thread?

A thread is the durable identity under which LangGraph accumulates checkpoints for an ongoing interaction or workflow.

For a chatbot:

- Thread A might represent a conversation with a customer about an invoice.
- Thread B might represent a different conversation with that customer.
- Thread C might represent a separate conversation with another customer.

A thread can contain many checkpoints and span many graph invocations.

### 1.4 What is a checkpointer?

A checkpointer is the component responsible for saving and retrieving these checkpoints.

For example:

```
from langgraph.checkpoint.memory import InMemorySavercheckpointer = InMemorySaver()
```

This creates a checkpointer that stores its data in memory.

For production:

```
from langgraph.checkpoint.postgres import PostgresSaver
```

`PostgresSaver` implements checkpoint persistence using PostgreSQL.

The graph does not need to know the storage mechanics. It interacts with the checkpointer interface, while the implementation handles reading and writing the saved execution information.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

Docs by LangChain

## 2. The most important distinction: runs, threads, and checkpoints

These three concepts must never be confused.

| Concept    | Meaning                                   | Example                          |
| ---------- | ----------------------------------------- | -------------------------------- |
| Run        | One invocation or execution of the graph  | The user asks a new question     |
| Thread     | The continuing identity of an interaction | One conversation                 |
| Checkpoint | A saved execution snapshot                | State after a node or super-step |

Imagine one conversation:

```
Thread: customer-123-conversation-abc

    Run 1: "Find my invoice"
        Checkpoint 1
        Checkpoint 2
        Checkpoint 3

    Run 2: "What is the amount?"
        Checkpoint 4
        Checkpoint 5
        Checkpoint 6

    Run 3: "Please prepare an approval request"
        Checkpoint 7
        Checkpoint 8
```

All three runs use the same thread ID.

The thread accumulates checkpoints from those executions, allowing the graph to access previous state when the application invokes it again with the same thread ID.

The key idea: one thread can contain multiple runs, and one run can produce multiple checkpoints.

This is the foundation for every subsequent lesson. The official persistence guide describes a thread as a collection of checkpointed graph-state history.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

Docs by LangChain

## 3. Build a small graph before using a checkpointer

We'll use a simple, deterministic workflow throughout these lessons. This lets you observe LangGraph itself without introducing an LLM's nondeterministic output.

Our graph has two nodes:

```
START → draft → review → END
```

First, define the graph:

```
from typing_extensions import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

class State(TypedDict, total=False):    
    topic: str    
    draft: str    
    review: str
    

 def draft(state: State) -> dict:    
     topic = state["topic"]    
     
     return {        
         "draft": f"This document explains {topic}."    
     }
     
     def review(state: State) -> dict:
         draft_text = state["draft"]    
         
         return {
                 "review": f"Reviewed document: {draft_text}"    
         }
     builder = StateGraph(State)
     
     builder.add_node("draft", draft)
     builder.add_node("review", review)
     
     builder.add_edge(START, "draft")
     builder.add_edge("draft", "review")
     builder.add_edge("review", END)
     
     checkpointer = InMemorySaver()
     
     graph = builder.compile(checkpointer=checkpointer)
```

Let's understand the code.

`StateGraph(State)` tells LangGraph what structure the graph's state should follow.

Each node receives the current state and returns a partial update. The `draft` node returns a value for `draft`; it doesn't need to return the entire state dictionary.

The builder describes the nodes and execution paths. Calling `.compile(checkpointer=checkpointer)` turns the builder into an executable graph and configures persistence.

Notice the difference between these two operations:

```
builder.add_node("draft", draft)
```

This registers a node.

```
graph = builder.compile(checkpointer=checkpointer)
```

This creates the executable graph with the checkpointer attached.

Next, run it:

```
config = {        
    "configurable": {        
        "thread_id": "invoice-conversation-001"    
        }
     }
     result = graph.invoke(    
         {"topic": "LangGraph checkpoints"},    config,)
          
     print(result)
```

The result will contain the topic, draft, and review.

The important configuration is:

```
{"configurable": {"thread_id": "invoice-conversation-001"}}
```

This tells LangGraph which thread's checkpoint history to use and update.

A checkpointer-enabled graph generally needs a `thread_id` for invocation. Without a stable, correctly scoped thread ID, LangGraph cannot know which conversation or workflow history should be resumed.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

Docs by LangChain

## 4. What is actually inside a checkpoint?

This is where we move from beginner-level understanding to the internal mechanics.

When you inspect a checkpointer directly, you may encounter an object called a `CheckpointTuple`, usually represented as `tup` in examples.

Conceptually, it contains:

```
CheckpointTuple
├── config
├── checkpoint
├── metadata
├── parent_config
└── pending_writes
```

The exact serialized representation depends on the checkpointer version and implementation. The official checkpointer contract describes these pieces as the checkpoint's stored configuration, snapshot, metadata, parent link, and pending writes.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

Docs by LangChain

### 4.1 `tup.checkpoint` — the snapshot bundle

The checkpoint itself contains the information required to represent the graph's saved execution state.

A simplified conceptual example looks like this:

```
checkpoint = {    
"v": 4,    
"id": "checkpoint-abc",    
"ts": "2026-10-29T10:00:00+00:00",    
"channel_values": { 
         "topic": "LangGraph checkpoints",        
         "draft": "This document explains LangGraph checkpoints.",    
         },    
 
 "channel_versions": {
         "topic": 1,
         "draft": 2,
                     },
                         
 "versions_seen": {
         "draft": {"topic": 1},    
         },
 }
```

This is illustrative, not a checkpoint you should construct manually.

Let's break down its fields.

`v` — checkpoint format version

LangGraph uses an internal format version so the serialization and execution infrastructure can understand the checkpoint representation.

It is not your application's version number.

`id` — checkpoint identifier

This identifies a particular checkpoint. A thread can have many checkpoint IDs.

The checkpoint ID is useful for history inspection, selecting a historical snapshot, and time travel.

`ts` — timestamp

This indicates when the checkpoint was created.

It is useful for inspecting and diagnosing execution history. Do not rely on timestamps alone as unique identifiers.

`channel_values` — state values

This is the part most beginners care about.

It contains the values associated with the graph's state channels. A channel corresponds to a piece of state managed by LangGraph.

For example:

```
{    
"topic": "LangGraph checkpoints",    
"draft": "This document explains LangGraph checkpoints.",
}
```

These are application-level values.

However, the checkpoint can also contain internal channels. It is not necessarily just your public `TypedDict` fields.

`channel_versions` — version of each channel

LangGraph tracks changes to channels over time.

When a channel changes, its version information helps the runtime understand which state updates occurred.

`versions_seen` — versions observed by nodes

This records version information relevant to execution decisions.

It helps the runtime determine whether nodes have seen particular versions of state and whether changed inputs mean further execution is needed.

These fields are important to LangGraph's scheduler. They are not meant to be edited manually by application developers. The official PostgreSQL implementation shows these fields in its current checkpoint representation.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub

### Why do we need channel versions?

Imagine you have two nodes:

```
                  ┌── node_a
START → dispatch ─┤
                  └── node_b
```

Suppose both nodes read the same input state and update different channels.

LangGraph needs to coordinate their execution and their writes. It cannot simply treat the workflow as a sequence of arbitrary Python function calls.

Channel-version information contributes to maintaining correct execution semantics as state changes.

The lesson is that a checkpoint is both application data and runtime bookkeeping.

Do not manually edit `channel_versions` or `versions_seen` to try to control execution. Use graph state APIs and supported graph edges instead.

### 4.2 The "next node" question

A common misunderstanding is that the checkpoint is just a dictionary and must explicitly contain a field such as:

```
{"next_node": "review"}
```

That is not a reliable way to think about LangGraph's internal representation.

When you inspect the public state snapshot, you see:

```
snapshot.next
```

For example:

```
StateSnapshot(    
values={        
    "topic": "LangGraph checkpoints",        
    "draft": "This document explains LangGraph checkpoints.",    
    }, 
       
    next=("review",),    
    ...)
```

This indicates that `review` is scheduled to execute next when the graph continues from that saved state.

If:

```
snapshot.next == ()
```

the graph has no node scheduled to run next at that snapshot; it has completed that execution path.

The public `StateSnapshot` is the appropriate interface for this sort of inspection. The runtime determines continuation from its checkpoint and execution bookkeeping; don't design code around an assumed `next_node` key inside the raw checkpoint dictionary.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

Docs by LangChain

### 4.3 `tup.metadata` — why was this checkpoint created?

Checkpoint metadata gives you context about the checkpoint.

For example, a state snapshot may display:

```
metadata = {    
    "source": "loop",    
    "writes": {        
        "draft": {            
            "draft": "This document explains LangGraph checkpoints."
         }    
     },    
    "step": 1,
}
```

The fields are useful for different purposes.

- `source` indicates the origin category of the checkpoint.
- `writes` records node updates associated with it.
- `step` indicates the graph's super-step counter.

The value of `writes` is not necessarily the entire current state. A node often returns only the fields it updates, while the accumulated state includes values from earlier nodes.

For example, the draft node may return:

```
{"draft": "A document about checkpoints"}
```

The checkpointed state can still contain the original `topic` alongside that new draft.

That is why `metadata["writes"]` and `channel_values` are not interchangeable.

### 4.4 `pending_writes` — the recovery mechanism that many people miss

This is one of the most important internal concepts in the entire course.

Remember that LangGraph can execute multiple nodes in the same super-step, including parallel branches.

Imagine this graph:

```
                 ┌── fetch_invoice ──┐
START → parallel ┤                   ├ → combine
                 └── fetch_customer ─┘
```

Both branches run during the same super-step.

Suppose:

- `fetch_invoice` succeeds.
- `fetch_customer` fails.
- The graph cannot yet complete the super-step.

What happens to the successful invoice result?

Without intermediate write tracking, LangGraph could be forced to rerun work that had already completed.

Pending writes allow the checkpointer to preserve successful task outputs associated with the unfinished super-step. When execution resumes, LangGraph can reuse those successful writes instead of rerunning the corresponding successful nodes.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

Docs by LangChain

Think of the difference this way:

| Data                | Purpose                                                                  |
| ------------------- | ------------------------------------------------------------------------ |
| Checkpoint snapshot | Represents saved graph state at a checkpoint boundary                    |
| Pending writes      | Tracks node outputs associated with a checkpoint's in-progress execution |
| State snapshot      | Public, convenient view for inspecting graph state and next steps        |

Pending writes are not the same as the final merged state.

A node may have completed successfully, but its output may not yet have become part of the fully committed next super-step state.

This feature helps avoid redundant computation after a partial failure. It does not promise that arbitrary external side effects have happened exactly once. We will return to that distinction in L17.

## 5. Threads: a conversation is a thread

Now let's connect those internal concepts to an actual application.

### 5.1 The one rule that surprises everyone

The thread ID is the link between successive invocations.

Let's run the graph twice.

First invocation:

```
config = {    
    "configurable": {        
        "thread_id": "conversation-001",    
     }
}

graph.invoke(    
    {"topic": "LangGraph persistence"},    
    config,
)
```

Second invocation:

```
graph.invoke(    
    {"topic": "LangGraph time travel"},    
    config,
)
```

Both invocations use the same thread ID.

LangGraph can load the existing state associated with this thread when handling the subsequent invocation. The input is processed in the context of the existing graph state according to the state channels and reducers you've defined.

However, notice an important distinction: passing a value in a later invocation does not automatically mean that it replaces every previous state field. The graph's state-update semantics determine what happens.

For a conversational agent, the `messages` state channel typically uses a reducer that adds messages to the accumulated conversation, rather than replacing the entire message history on every turn.

A repeated `thread_id` is therefore what lets a chat agent maintain continuity, but correct state behavior still depends on the graph and its reducers.

### 5.2 Thread ID design

In an enterprise service, a thread ID should identify the conversation or workflow instance, not act as an authorization mechanism.

A practical design could be:

```
tenant-42:conversation-uuid
```

Or simply a UUID stored in your application's database and mapped to a tenant and user.

For example:

```
Application database
    conversation_id
    tenant_id
    owner_id
    created_at
    status
```

The application can look up which thread belongs to the authenticated user before allowing the graph to access it.

Three rules are especially important:

1. Do not let the client choose arbitrary thread IDs without authorization checks. Otherwise, users might try to access another user's saved conversation.

2. Use a stable identifier for the lifetime of one conversation. Generating a fresh thread ID on every request prevents the graph from finding the intended history.

3. Keep IDs within backend limits. The current LangGraph PostgreSQL documentation specifically warns that `thread_id` values exceeding the column limit can cause database errors and recommends keeping them under 255 characters.&#x20;

   [image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

   Docs by LangChain

The `thread_id` does not need to be a secret. Security comes from authentication, authorization, tenant isolation, and careful access to persisted state.

### 5.3 Thread versus long-term memory

This distinction becomes important when you eventually build enterprise agents.

Suppose an employee tells the assistant:

> I prefer all reports in CSV format.

There are two separate questions.

Question A: What happened in this conversation?

The checkpointer is responsible for the thread's graph-state history.

Question B: What should the assistant remember across different conversations?

That is an application-level memory problem. LangGraph stores provide a mechanism for storing application-defined information across threads.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

Docs by LangChain

For example:

```
Checkpointer:
    Thread A → current state + execution history
    Thread B → current state + execution history

Store:
    User 42 → preferred_report_format = "CSV"
```

A checkpointer is not automatically a global user-profile database, and a store is not a substitute for the execution checkpoint history needed to resume a workflow.

## 6. The checkpointer interface

A checkpointer is more than a save operation.

The checkpointer interface supports saving checkpoints, recording intermediate task writes, retrieving checkpoint tuples, listing historical checkpoints, and deleting a thread. It also provides asynchronous counterparts for appropriate operations.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

Docs by LangChain

Here's a conceptual mapping of its main operations.

| Operation                          | What it does                               |
| ---------------------------------- | ------------------------------------------ |
| `put` / `aput`                     | Save a checkpoint                          |
| `put_writes` / `aput_writes`       | Save intermediate writes produced by tasks |
| `get_tuple` / `aget_tuple`         | Load a checkpoint tuple                    |
| `list` / `alist`                   | List checkpoints, usually newest first     |
| `delete_thread` / `adelete_thread` | Delete a thread's checkpoint data          |

You will generally use public graph-level methods such as `get_state()` and `get_state_history()` in application code.

Directly interacting with the checkpointer interface becomes useful when developing custom storage integrations, debugging persistence behavior, building administrative tools, or investigating database-level details.

### Why does `put_writes` exist separately from `put`?

Because successful work can exist before the graph's next fully merged checkpoint is committed.

For example:

```
Super-step begins
    │
    ├── node A completes → persist its writes
    │
    └── node B fails
             │
             ▼
      Resume the super-step
             │
             ├── Reuse node A's saved writes
             └── Retry the unfinished work
```

The exact execution behavior depends on the graph's checkpoint state and successful task writes, but the purpose is to recover without blindly redoing everything.

## 7. Choosing a backend

A checkpointer is an interface; a backend determines where the data lives and what operational guarantees are available.

In-memory — `InMemorySaver`

Use for tutorials, unit tests, and short-lived experiments. Its state lives in process memory and is lost when that process loses its memory.

SQLite

Useful for local development and small, single-machine workflows. It stores data on disk rather than relying exclusively on process memory.

PostgreSQL — `PostgresSaver`

A strong default for production applications that already use PostgreSQL and need durable persistence with a mature relational database.

Redis — community integration

An alternative if Redis is already a core part of the infrastructure and its data retention, persistence, and module requirements fit your workload.

The official LangGraph documentation lists the in-memory, SQLite, PostgreSQL, and MongoDB integrations, among others. Redis has a separately maintained community integration.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

Docs by LangChain+1

For your enterprise AI backend, I would start by learning `InMemorySaver`, then use PostgreSQL for production-style persistence. PostgreSQL is a particularly natural fit when your application already uses it for tenant records, conversations, jobs, and application metadata.

### 7.1 The community Redis checkpointer

The Redis implementation from `redis-developer/langgraph-redis` requires more than a completely bare Redis server.

Its documentation specifies RedisJSON and RediSearch requirements. Redis 8 and newer include these modules in the core distribution; older installations may need Redis Stack or separately installed modules. The integration also has its own TTL configuration and persistence considerations.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub

Install the integration:

```
uv add langgraph-checkpoint-redis
```

A basic synchronous setup resembles:

```
from langgraph.checkpoint.redis import RedisSaver

with RedisSaver.from_conn_string(    "redis://localhost:6379") as checkpointer:    checkpointer.setup()    
graph = builder.compile(checkpointer=checkpointer)
```

The first `.setup()` initializes the required structures and indexes.

For a production deployment, do not choose Redis merely because it appears faster than a relational database. Evaluate its persistence settings, eviction policy, TTL behavior, replication, backups, and recovery requirements. A checkpoint that disappears because Redis evicted it cannot be used to resume the corresponding execution.

## 8. PostgreSQL checkpointers in production

Let's now look at the backend I recommend understanding deeply.

### 8.1 Setup

The current installation command is:

```
uv add langgraph-checkpoint-postgres
```

The package provides the PostgreSQL saver implementation using Psycopg 3. The default package dependencies include Psycopg; choose an appropriate Psycopg installation for your deployment.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub

A basic script can use:

```
from langgraph.checkpoint.postgres import PostgresSaverDATABASE_URL = (    "postgresql://user:password@localhost:5432/appdb")with PostgresSaver.from_conn_string(    DATABASE_URL) as checkpointer:    checkpointer.setup()    graph = builder.compile(        checkpointer=checkpointer    )    config = {        "configurable": {            "thread_id": "demo-thread",        }    }    result = graph.invoke(        {"topic": "PostgreSQL checkpoints"},        config,    )
```

The context manager closes the connection when the block ends.

This pattern is useful in a script or tutorial. It is not a good way to open and close an entire checkpointer connection context for every incoming web request.

The checkpointer must remain available throughout the graph's execution.

Also, call `setup()` when the checkpoint database is initialized for the first time. It creates the required tables and applies database migrations. In a deployed service, consider a controlled initialization or migration step rather than having every application replica independently modify the schema.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub

### 8.2 The PostgreSQL schema

For `langgraph-checkpoint-postgres` 3.2.0, understand the purpose of these internal tables rather than memorizing a schema that might change across releases.

| Table                   | Purpose                                                                                        |
| ----------------------- | ---------------------------------------------------------------------------------------------- |
| `checkpoint_migrations` | Tracks database migration versions                                                             |
| `checkpoints`           | Stores checkpoint records and associated metadata                                              |
| `checkpoint_blobs`      | Stores serialized channel values that are persisted separately from the main checkpoint record |
| `checkpoint_writes`     | Stores intermediate writes produced by graph tasks                                             |

The official implementation uses checkpoint IDs, parent-checkpoint relationships, namespaces, serialized state, and metadata to reconstruct execution history. Some fields are stored separately from the main checkpoint record.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub+2

Understand the relationship like this:

```
Thread + namespace
        │
        ▼
   checkpoints
        │
        ├── checkpoint ID
        ├── parent checkpoint ID
        └── state and metadata
                 │
                 ├── checkpoint_blobs
                 │       └── Serialized channel values
                 │
                 └── checkpoint_writes
                         └── Intermediate node writes
```

The schema is an implementation detail, not a substitute for the LangGraph API.

Best practice: let `.setup()` perform initialization and migrations. Do not build your own manually managed version of these tables unless you are intentionally implementing a custom checkpointer against the documented contract.

### 8.3 The lifecycle mistake: creating a checkpointer per request

Imagine this FastAPI endpoint:

```
@app.post("/chat")def chat(request: ChatRequest):    with PostgresSaver.from_conn_string(        DATABASE_URL    ) as checkpointer:        graph = builder.compile(            checkpointer=checkpointer        )        return graph.invoke(...)
```

This example is useful for seeing the API in a small script, but it is not the pattern I would use for a production service.

It creates a connection context for each request and also reconstructs the compiled graph repeatedly.

A more appropriate lifecycle is:

```
Application starts
      │
      ▼
Open database connection pool
      │
      ▼
Initialize checkpointer
      │
      ▼
Compile or initialize graph
      │
      ▼
Handle multiple requests
      │
      ▼
Application shuts down
      │
      ▼
Close connection pool
```

The graph and checkpointer should be managed through the application's lifecycle. They should not be unnecessarily reconstructed for every message.

For a concurrent service, use an appropriately managed connection pool. The PostgreSQL implementation supports connection pools, and the official documentation explains the connection settings needed when creating connections manually: `autocommit=True` and `row_factory=dict_row`.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub

An asynchronous service can use the asynchronous saver and connection-pool APIs:

```
from psycopg.rows import dict_rowfrom psycopg_pool import AsyncConnectionPoolfrom langgraph.checkpoint.postgres.aio import (    AsyncPostgresSaver,)async def initialize_checkpointer(    database_url: str,) -> tuple[AsyncConnectionPool, AsyncPostgresSaver]:    pool = AsyncConnectionPool(        conninfo=database_url,        kwargs={            "autocommit": True,            "row_factory": dict_row,        },        min_size=2,        max_size=10,        open=False,    )    await pool.open()    checkpointer = AsyncPostgresSaver(pool)    await checkpointer.setup()    return pool, checkpointer
```

This illustrates the asynchronous initialization pattern. In a real FastAPI application, call it from the application's lifespan handler and close the pool during shutdown. Adapt connection ownership and initialization to the way your deployment manages migrations and application instances.

Use asynchronous graph methods such as `await graph.ainvoke(...)` when working within the asynchronous execution path.

### 8.4 Retention: `prune` versus `delete_thread`

Saving every checkpoint forever has consequences.

A long-running conversation may accumulate many snapshots. A workflow service handling thousands of conversations can accumulate a substantial volume of persisted state, intermediate writes, and serialized data.

You need a retention policy.

There are two different goals.

Delete a thread: remove its persisted checkpoint history when the conversation or workflow is no longer retained.

```
checkpointer.delete_thread(thread_id)
```

For an asynchronous saver, the corresponding operation is generally:

```
await checkpointer.adelete_thread(thread_id)
```

Prune old checkpoints: retain a smaller amount of checkpoint history while removing older data.

The current PostgreSQL implementation provides a `prune()` API with strategies including `"keep_latest"` and `"delete"`. The exact behavior and support depend on the installed backend version.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub

Conceptually:

```
Before pruning:

Checkpoint 1 → Checkpoint 2 → Checkpoint 3 → Checkpoint 4
                                                ▲
                                          Latest state

After pruning:

Checkpoint 4
     ▲
 Latest state
```

This diagram is illustrative; the exact retained records depend on the backend's pruning strategy.

Pruning can reduce the ability to replay older history. It also needs special care with incremental or delta-based state representations, because a current checkpoint may depend on earlier writes.

For example, the current LangGraph checkpoint guide warns that `DeltaChannel` data may depend on an ancestor chain and that pruning must preserve the necessary writes or create an appropriate snapshot first.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

Docs by LangChain

Do not implement retention as a generic SQL statement that deletes arbitrary old rows. Use the backend's supported retention mechanisms and verify the consequences for recovery and time travel.

Also, checkpoint deletion is different from deleting the application's conversation record, removing user-profile data, or meeting a legal data-deletion requirement. Your application needs a policy covering all relevant stores.

## 9. Attaching a checkpointer to an agent

The same principle applies to agents created with the modern `create_agent` API.

Here is a Gemini-backed example:

```
from langchain.agents import create_agentfrom langchain_google_genai import ChatGoogleGenerativeAIfrom langgraph.checkpoint.memory import InMemorySavermodel = ChatGoogleGenerativeAI(    model="gemini-2.5-flash")checkpointer = InMemorySaver()agent = create_agent(    model=model,    tools=[],    checkpointer=checkpointer,)
```

The model identifier is an example; use a model supported by your Google account and installed integration.

Invoke the agent for the first message:

```
config = {    "configurable": {        "thread_id": "employee-chat-001"    }}response = agent.invoke(    {        "messages": [            {                "role": "user",                "content": "My preferred report format is CSV.",            }        ]    },    config,)
```

Then continue with the same thread:

```
response = agent.invoke(    {        "messages": [            {                "role": "user",                "content": "What report format do I prefer?",            }        ]    },    config,)
```

With the same checkpointer and thread ID, the agent can use its accumulated message history. Whether the agent correctly answers the question is still a matter of the model and its instructions, but the persistence mechanism gives it the previous conversational state.

This illustrates thread-scoped conversation continuity, not automatically permanent cross-thread user memory.

For agent applications, use the current `langchain.agents.create_agent` API. Older LangGraph examples using `langgraph.prebuilt.create_react_agent` are part of an earlier agent-construction pattern; don't carry that older construction API into new code without checking its current status and migration guidance.

# L16 — State Inspection & Time Travel

L15 taught you how state gets saved. L16 teaches you how to examine, modify, and replay that saved state.

This is crucial in production.

For example, a user reports:

> The assistant told me that the invoice was verified, but the amount was wrong.

You need to determine:

- What state did the graph have?
- Which node executed?
- What did the node write?
- Which node was scheduled next?
- What was the prior state?
- Can you reproduce the behavior without restarting the entire workflow?

LangGraph offers three main public tools for this: `get_state()`, `get_state_history()`, and `update_state()`.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

Docs by LangChain

## 1. `StateSnapshot` — the fields

When you call `get_state()`, LangGraph returns a `StateSnapshot`.

Conceptually, it looks like this:

```
snapshot = graph.get_state(config)
```

The current documentation describes the snapshot with these fields.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

Docs by LangChain

| Field           | Meaning                                                                    |
| --------------- | -------------------------------------------------------------------------- |
| `values`        | State channel values at this checkpoint                                    |
| `next`          | Nodes scheduled to execute next                                            |
| `config`        | Configuration identifying the thread, checkpoint namespace, and checkpoint |
| `metadata`      | Information about the checkpoint's source, writes, and step                |
| `created_at`    | Checkpoint creation timestamp                                              |
| `parent_config` | Configuration identifying the parent checkpoint, when available            |
| `tasks`         | Information about tasks scheduled or involved in the saved execution       |

Let's understand each field.

### `values`

This is the current state represented by the snapshot.

```
snapshot.values
```

For our example, you might see:

```
{    "topic": "LangGraph persistence",    "draft": "This document explains LangGraph persistence.",}
```

### `next`

```
snapshot.next
```

Suppose the saved graph is between `draft` and `review`.

It might return:

```
("review",)
```

This tells you what the graph is ready to execute next.

### `config`

```
snapshot.config
```

This identifies the particular checkpoint snapshot.

It contains the configuration used to locate that state, including the `thread_id` and `checkpoint_id`.

This is important because a thread can have multiple snapshots.

### `metadata`

```
snapshot.metadata
```

This tells you how the checkpoint was created and what updates were recorded.

### `created_at`

```
snapshot.created_at
```

This helps establish the order and timing of saved states.

### `parent_config`

```
snapshot.parent_config
```

This identifies the parent checkpoint where applicable. It is particularly useful when examining checkpoint history or investigating a branch created through state updates.

### `tasks`

```
snapshot.tasks
```

Tasks can include useful diagnostic information such as task names, IDs, errors, and interrupts.

This is especially helpful when debugging an interrupted workflow or a failed node.

## 2. `get_state()` — what is the state right now?

Let's inspect our graph after running it.

```
config = {    "configurable": {        "thread_id": "invoice-conversation-001"    }}graph.invoke(    {"topic": "LangGraph persistence"},    config,)snapshot = graph.get_state(config)print(snapshot.values)print(snapshot.next)print(snapshot.metadata)
```

The important point is that `get_state()` does not return only your application's dictionary.

It returns a snapshot containing the values plus information about the graph's execution.

### Can I inspect a historical checkpoint?

Yes.

Instead of asking for the latest state, provide a configuration containing a specific checkpoint ID:

```
history = list(graph.get_state_history(config))oldest_example = history[-1]historical_snapshot = graph.get_state(    oldest_example.config)
```

This works because each snapshot's `config` identifies the checkpoint represented by that snapshot. The official documentation supports retrieving state for a specific checkpoint using its `checkpoint_id`.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

Docs by LangChain

Notice that the example above does not assume that every historical checkpoint is a suitable place to resume execution. It simply demonstrates how to inspect one.

## 3. `get_state_history()` — the execution timeline

A snapshot shows one point in time. History gives you a series of saved points.

Use:

```
history = list(graph.get_state_history(config))
```

The history is returned with the most recent checkpoint first. This is an important detail because many developers naturally expect an oldest-first timeline.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

Docs by LangChain

To inspect the history:

```
for snapshot in history:    print("Checkpoint:", snapshot.config["configurable"]["checkpoint_id"])    print("Values:", snapshot.values)    print("Next:", snapshot.next)    print("Metadata:", snapshot.metadata)    print("---")
```

You can use this information to reconstruct what the workflow state looked like at successive checkpoints.

### 3.1 Finding a checkpoint before a specific node

Suppose you want to inspect the state before `review` executes.

You can find a snapshot whose `next` value identifies that node:

```
before_review = next(    snapshot    for snapshot in history    if snapshot.next == ("review",))
```

This works for the simple graph we have been using.

However, in a looping graph, the same node can be scheduled multiple times. In that case, also consider the checkpoint ID, metadata step, creation time, or task information to identify the intended checkpoint precisely.

### 3.2 Reading `metadata["source"]`

This is a useful debugging field.

The current official documentation identifies three standard checkpoint source categories:

| `source`   | Meaning                                             |
| ---------- | --------------------------------------------------- |
| `"input"`  | Checkpoint associated with the supplied graph input |
| `"loop"`   | Checkpoint generated during graph execution         |
| `"update"` | Checkpoint created by an explicit state update      |

These are the standard categories documented for checkpoint state snapshots. A state update used to create a fork is still categorized as `"update"`; `"fork"` is not a separate standard source value in this documented list.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

Docs by LangChain

So, despite the heading in your original outline referring to four source values, the current standard documented set contains three. If a custom backend or particular release exposes another source, investigate it as an implementation-specific addition rather than assuming it is a universal value.

## 4. `update_state()` — writing to state

This API is particularly powerful because it lets you create a modified checkpoint and continue execution from it.

Let's say our graph produced this state:

```
{    "topic": "LangGraph persistence",    "draft": "This document explains LangGraph persistence.",}
```

But, for debugging, you want to change the topic to `"LangGraph time travel"`.

You can use:

```
fork_config = graph.update_state(    before_review.config,    values={        "topic": "LangGraph time travel"    },)
```

The result is a new checkpoint configuration.

The original checkpoint remains intact. `update_state()` does not modify the old snapshot in place or erase the old history. It creates a new checkpoint based on the supplied point and values.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

Docs by LangChain

### 4.1 It is NOT a free mutation

There is an important detail here: state updates follow LangGraph's normal channel-update semantics.

Suppose your state uses a reducer.

A reducer specifies how an incoming value is combined with the existing channel value.

For example, an append-style state channel might combine lists instead of replacing the previous list. If you update such a channel with a full historical value, you may append data you did not intend to append.

This means `update_state()` is not equivalent to:

```
state["topic"] = "LangGraph time travel"
```

It is an operation through LangGraph's state machinery.

For a channel without a reducer, a supplied value typically replaces its previous value. For a channel with a reducer, the reducer determines the result.

### 4.2 `as_node` — who "wrote" this?

When using `update_state()`, LangGraph needs to determine the execution position associated with the update.

Consider:

```
START → draft → review → END
```

If the state update should be treated as though `draft` had produced it, specify:

```
fork_config = graph.update_state(    before_review.config,    values={        "topic": "LangGraph time travel"    },    as_node="draft",)
```

Conceptually, this means the graph should continue from the successor of `draft`, which is `review`.

Why does it matter?

Because the update isn't only changing data. It can also affect what the graph executes next.

Current documentation recommends explicitly specifying `as_node` in situations such as ambiguous parallel-branch history, fresh threads without execution history, or when intentionally skipping nodes.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

Docs by LangChain

Do not set `as_node` arbitrarily. It must align with the graph topology and the intended point of resumption.

### 4.3 The one-head rule

When you update a state from a historical checkpoint, you are creating a new continuation from that point.

Think of a graph's history as a branching structure:

```
Checkpoint A
     │
     ▼
Checkpoint B
     │
     ▼
Checkpoint C ─────► Checkpoint D (new branch)
     │
     ▼
Checkpoint E (old history)
```

The diagram is conceptual: the exact checkpoint-parent relationships depend on the operations you perform.

The key point is that the original execution history is not simply erased.

After creating a branch, use the configuration returned by `update_state()` when you want to continue execution from that newly created state.

Do not assume that updating a historical checkpoint automatically merges its new results into every later historical checkpoint.

## 5. Time travel: replaying an earlier checkpoint

Time travel lets you explore what happens if you resume from a historical checkpoint rather than the latest one.

Suppose your graph executed like this:

```
Checkpoint 1: input received
       │
       ▼
Checkpoint 2: draft created
       │
       ▼
Checkpoint 3: review completed
```

Imagine you want to replay the graph from the checkpoint after the draft was created.

First, find the checkpoint:

```
history = list(graph.get_state_history(config))before_review = next(    snapshot    for snapshot in history    if snapshot.next == ("review",))
```

Then resume from that checkpoint:

```
replay_result = graph.invoke(    None,    before_review.config,)
```

Passing `None` tells LangGraph to continue from the saved execution state rather than supplying a new initial input.

Because the selected checkpoint has `review` scheduled next, the `review` node executes again.

The graph does not simply return a cached final result.

LangGraph's time-travel guide describes two important capabilities:

- Replay: resume from an earlier checkpoint.
- Fork: create a new continuation from an earlier checkpoint with modified state.

Nodes before the selected checkpoint are skipped, while nodes after it execute again.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

Docs by LangChain

### 5.1 Replay versus fork

| Replay                                           | Fork                                                  |
| ------------------------------------------------ | ----------------------------------------------------- |
| Continues from an existing historical checkpoint | Creates a new checkpoint with modified state          |
| Re-executes subsequent nodes                     | Re-executes subsequent nodes using the modified state |
| Useful for reproducing execution                 | Useful for exploring alternative outcomes             |

If you need a different result, use a fork with a controlled state change.

### 5.2 Side effects do NOT undo

This is the single most important time-travel warning.

Suppose a node sends an email:

```
def send_email(state: State) -> dict:    email_service.send(        to="approver@example.com",        subject="Invoice approval",        body="Please approve invoice INV-100.",    )    return {        "approval_status": "sent"    }
```

The first execution sends the email.

Then you replay the graph from a checkpoint before that node.

The email may be sent again.

LangGraph cannot automatically retract an email, undo a bank transfer, cancel an external API operation, or reverse an action in an unrelated system just because you selected an older checkpoint.

Its time-travel documentation explicitly warns that nodes after the selected checkpoint re-execute, including API requests and other external calls.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

Docs by LangChain

Practical rule: never replay a production workflow containing irreversible operations unless you have deliberately designed those operations to tolerate replay.

### 5.3 What time travel is genuinely good for

Time travel is especially valuable for:

- Reproducing an agent's behavior from an earlier state.
- Testing a modified prompt or state.
- Investigating faulty routing decisions.
- Understanding why a particular node was scheduled.
- Exploring alternate paths without deleting the previous execution history.
- Debugging a human-in-the-loop workflow.

It is not a substitute for database backups, transaction rollback, or an external system's compensation mechanism.

## 6. Cloning a thread safely

Your outline notes that `copy_thread` may exist at an API or integration level but should not be assumed to be implemented universally.

That caution is appropriate.

The current checkpointer documentation discusses copying threads as a capability that checkpointer implementations need to handle carefully, especially when state is stored incrementally. The current PostgreSQL saver source does not expose a generic public `copy_thread()` method that I would rely on as a portable API.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

Docs by LangChain+1

### Why is cloning difficult?

A thread isn't necessarily just one independent state dictionary.

It may include:

- A chain of checkpoints.
- Parent-checkpoint relationships.
- Intermediate writes.
- Subgraph namespaces.
- Interrupt state.
- Channel history necessary to reconstruct the current state.

For a normal, self-contained snapshot, copying only the latest state values may be sufficient for a purpose-built debugging workflow. But copying only those values does not reproduce the entire original execution history.

Delta channels make this even more important because a current value may depend on information in earlier checkpoints. The official documentation warns that copying a thread containing delta-channel state requires preserving the appropriate ancestor chain and writes.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

Docs by LangChain

Recommended debugging approach:

1. Inspect the original thread and identify the relevant checkpoint.
2. Use `update_state()` to create a branch when that is sufficient and supported by your workflow.
3. For an independent debug thread, use a deliberately implemented and tested cloning procedure for your specific backend, or reconstruct a new run from known input.
4. Ensure that external side effects are disabled, mocked, or protected by idempotency mechanisms during replay.

Never copy database rows blindly and assume you've cloned a valid LangGraph execution.

## 7. The full debugging workflow

Let's combine the inspection methods.

```
config = {    "configurable": {        "thread_id": "invoice-conversation-001"    }}# 1. Inspect the latest state.latest = graph.get_state(config)print("Current values:", latest.values)print("Next nodes:", latest.next)# 2. Inspect the history.history = list(graph.get_state_history(config))# 3. Find the checkpoint before the review node.before_review = next(    snapshot    for snapshot in history    if snapshot.next == ("review",))print("Earlier state:", before_review.values)print("Earlier metadata:", before_review.metadata)# 4. Make a controlled change to the state.fork_config = graph.update_state(
```

The essential difference between each operation is:

- `get_state()` reads a snapshot.
- `get_state_history()` discovers earlier snapshots.
- `update_state()` creates a modified continuation.
- `invoke(None, checkpoint_config)` resumes from the selected continuation.

These operations are the foundation for practical time-travel debugging in LangGraph.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

Docs by LangChain

### Production debugging checklist

When debugging an actual enterprise thread, begin with the snapshot rather than dumping raw database rows.

Check the state values, next nodes, metadata, tasks, and checkpoint ID. Compare the relevant historical snapshots and correlate them with application logs and trace information.

Be mindful of sensitive customer messages, internal documents, access tokens, tool outputs, and other data that may be stored in checkpoints. Only authorized operators should be able to inspect them.

Most importantly, investigation is not the same as replay. Reading history is usually safe; replaying an earlier node can cause real-world operations to execute again.

# L17 — Durability, Retries & Crash Recovery

L15 taught us how LangGraph persists state.

L16 taught us how to inspect and revisit that state.

L17 asks the questions that determine whether a real service is reliable:

1. How much saved state might we lose if a process crashes?
2. What happens when a node fails?
3. If we resume, could a node execute more than once?
4. How do we keep retries from causing duplicate payments, emails, or other side effects?

The key principle is this:

Persistence improves recovery, but persistence alone does not guarantee exactly-once execution of external operations.

Let's understand why.

## 1. Durability modes

LangGraph supports three durability modes that determine when checkpoint changes are persisted relative to graph execution:

- `"exit"`
- `"async"`
- `"sync"`

They trade off performance and how much intermediate execution state is guaranteed to have been saved before a failure.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

Docs by LangChain

### 1.1 `durability="exit"`

With this mode, LangGraph persists changes when graph execution exits, whether successfully, with an error, or because of a human-in-the-loop interruption.

The benefit is that checkpoint writes can be deferred, reducing overhead during long-running graph execution.

The trade-off is significant: intermediate state may not be saved if the process crashes while the graph is executing.

Suppose:

```
Node A → Node B → Node C → END
```

If the process crashes during Node C before the execution reaches a checkpoint-save boundary, the latest durable checkpoint may be earlier than the work already performed.

This mode is therefore inappropriate when mid-execution recovery from process crashes is a core requirement.

### 1.2 `durability="async"`

With asynchronous durability, LangGraph persists checkpoint changes asynchronously while execution continues.

This can offer a useful balance between performance and durability.

However, a process crash can occur before an asynchronous write finishes. You therefore cannot treat it as a guarantee that every preceding step has already been durably written before the next step starts.

### 1.3 `durability="sync"`

With synchronous durability, LangGraph persists the checkpoint before proceeding to the next step.

This reduces the window in which a process crash can leave the graph without the latest saved checkpoint.

The trade-off is additional persistence overhead, potentially increasing execution latency.

### 1.4 Comparison

| Mode    | When persistence occurs                  | Main trade-off                                                                                    |
| ------- | ---------------------------------------- | ------------------------------------------------------------------------------------------------- |
| `exit`  | At graph execution exit                  | Best execution performance in appropriate workloads, but no intermediate crash-recovery guarantee |
| `async` | Asynchronously while execution continues | Balances performance with durability, with a window where writes may not finish                   |
| `sync`  | Before the next step begins              | Stronger checkpoint durability at the cost of extra overhead                                      |

These are checkpoint durability semantics, not guarantees about external systems.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

Docs by LangChain

### 1.5 Choosing a mode

For a conversational agent that mainly generates text, you might prefer `"async"` if your measured performance and recovery requirements support it.

For workflows involving expensive, long-running, or important business operations, `"sync"` is a strong starting point for evaluation.

For a long computation that only needs a final result and can tolerate restarting from the beginning after a crash, `"exit"` may be acceptable.

Don't choose based on intuition alone. Measure it.

```
import timestart = time.perf_counter()result = graph.invoke(    {"topic": "Durability testing"},    config,    durability="sync",)elapsed = time.perf_counter() - startprint(f"Elapsed time: {elapsed:.3f}s")
```

Repeat the test with representative graph workloads and the other modes.

A meaningful benchmark should include storage latency, the number of state updates, graph duration, concurrency, and the size of your saved state. Avoid drawing conclusions from a tiny local test alone.

## 2. Retries: `RetryPolicy`

Checkpoint durability and retry behavior solve different problems.

Durability controls when graph state is saved.

A retry policy controls what happens when node execution fails.

Consider a node calling an external API:

```
def fetch_invoice(state: State) -> dict:    # Imagine that this makes an HTTP request.    ...
```

The API might return a temporary failure, experience a connection timeout, or be temporarily unavailable.

Instead of abandoning the graph immediately, you can configure a retry policy.

```
from langgraph.types import RetryPolicybuilder.add_node(    "fetch_invoice",    fetch_invoice,    retry_policy=RetryPolicy(        max_attempts=3,    ),)
```

The current fault-tolerance API accepts a `RetryPolicy` on a node. `max_attempts=3` means at most three attempts, including the original attempt.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

Docs by LangChain

### 2.1 What does a retry actually do?

Suppose the first attempt fails with a retryable exception.

The conceptual execution is:

```
Attempt 1
    │
    ├── Failure
    ▼
Wait before retry
    │
    ▼
Attempt 2
    │
    ├── Failure
    ▼
Wait before retry
    │
    ▼
Attempt 3
    │
    ├── Success → continue
    │
    └── Failure → propagate or invoke error handler
```

The actual behavior depends on the exception, retry policy, and any configured error handler.

Retries are not synonymous with rerunning the entire graph from scratch. They are node-level fault-tolerance behavior.

### 2.2 Backoff and jitter

The current `RetryPolicy` exposes parameters including:

| Parameter          | Default            | Meaning                                           |
| ------------------ | ------------------ | ------------------------------------------------- |
| `max_attempts`     | 3                  | Total number of attempts                          |
| `initial_interval` | 0.5 seconds        | Initial retry delay                               |
| `backoff_factor`   | 2.0                | Multiplier applied to the delay                   |
| `max_interval`     | 128 seconds        | Maximum delay                                     |
| `jitter`           | `True`             | Adds random variation to retry timing             |
| `retry_on`         | `default_retry_on` | Determines whether an exception should be retried |

These defaults are documented in LangGraph's fault-tolerance guide.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

Docs by LangChain

Backoff prevents an application from immediately hammering an already struggling service.

Jitter helps prevent many workers from retrying simultaneously at the same intervals.

For example, if a hundred workers hit an API failure at the same instant and all retry at exactly 1 second, they may overwhelm the recovering API. Randomized delays spread the load.

### 2.3 Custom `retry_on`

Do not assume every exception should be retried.

The current documented default retry predicate excludes several exception classes, including `ValueError`, `TypeError`, `RuntimeError`, and `OSError`. For common HTTP clients, retry behavior also considers HTTP status codes; server errors in the 5xx range are handled differently from ordinary client errors. `NodeTimeoutError` is retryable by default.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

Docs by LangChain

This means that error classification matters.

A network timeout may be transient.

A `ValueError` caused by invalid business data is unlikely to be fixed by waiting half a second.

You can specify a more deliberate retry predicate:

```
from langgraph.types import RetryPolicy, default_retry_ondef should_retry(exc: BaseException) -> bool:    # Do not retry a known business-rule failure.    if isinstance(exc, InvalidInvoiceError):        return False    # Preserve the framework's default classification    # for the remaining exception types.    return default_retry_on(exc)builder.add_node(    "fetch_invoice",    fetch_invoice,    retry_policy=RetryPolicy(        max_attempts=3,        retry_on=should_retry,    ),)
```

Here, `InvalidInvoiceError` represents an application-defined exception.

The point is not to blindly copy this exact exception taxonomy into every application. It is to make failure classification a deliberate part of your design.

### 2.4 `error_handler` — the newer fault-tolerance capability

Current LangGraph 1.2 documentation also describes node-level error handlers. These run after a node fails and its retries have been exhausted. Node-level error handlers and node-level timeouts require `langgraph>=1.2`.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

Docs by LangChain

An error handler receives the state and a `NodeError` describing the failure.

For example:

```
from langgraph.errors import NodeErrordef invoice_error_handler(    state: State,    error: NodeError,) -> dict:    return {        "approval_status": (            f"verification_failed: {error.error}"        )    }
```

You can register it on the node:

```
builder.add_node(    "fetch_invoice",    fetch_invoice,    retry_policy=RetryPolicy(max_attempts=3),    error_handler=invoice_error_handler,)
```

The handler can return a partial state update or a `Command` to update the state and route to another node.

This makes it possible to implement controlled recovery rather than treating every failure as a terminal graph error.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.langchain.com\&sz=32)

Docs by LangChain

A good example is a workflow that tries to retrieve a document three times and then marks its status as `verification_failed`, allowing the rest of the workflow to produce a user-facing explanation.

But do not use an error handler to hide serious failures or incorrectly mark an operation successful.

## 3. Crash recovery: what happens when the process dies?

Imagine your LangGraph service is running on a server.

The graph has already completed two nodes and is about to run a third.

Then the operating system kills the process.

What happens when the application restarts?

The checkpointer allows LangGraph to load saved state. Given an appropriate thread ID and a resumable execution, LangGraph can continue based on the latest available checkpoint and saved task writes.

The exact recovery position depends on the state that was successfully persisted, whether there are pending writes, and the type of failure.

### 3.1 The basic recovery sequence

```
Graph execution
      │
      ▼
Checkpoint saved
      │
      ▼
Next node executes
      │
      ▼
Process crashes
      │
      ▼
Application restarts
      │
      ▼
Load checkpoint for thread
      │
      ▼
Resume recoverable work
```

This is not a promise to resume at an arbitrary Python instruction.

LangGraph persists graph execution state, not a complete snapshot of the Python interpreter, open file descriptors, local variables, network sockets, or arbitrary external processes.

A node that has not produced recoverable writes may need to execute again.

A node that completed and had its intermediate writes saved can, in appropriate recovery scenarios, avoid being run again.

That is precisely why the checkpoint-plus-pending-writes model matters.

### 3.2 What "at-least-once" means here

The term at-least-once describes a situation in which the same logical operation may be attempted more than once.

Suppose a node:

1. Calls an external service.
2. The external service successfully performs an action.
3. The node fails before the corresponding graph result is safely recorded.

LangGraph may have to execute the node again.

The external action may happen a second time.

This can occur even if you choose `durability="sync"`. Synchronous checkpoint persistence does not turn a PostgreSQL transaction and an unrelated external API operation into one atomic transaction.

### 3.3 The three important re-execution paths

Memorize these distinctions:

Path 1: Node-level retry

A node raises a retryable exception. Its retry policy permits another attempt.

Path 2: Failure or crash recovery

Execution resumes from saved graph state. Work without recoverable saved results may need to run again.

Path 3: Time-travel replay

You deliberately resume from an older checkpoint. Subsequent nodes execute again, including external calls made by those nodes.

A fourth operational situation is worth remembering too: the client may resubmit an HTTP request after losing the response to an earlier successful request. That can initiate another logical execution unless your application deduplicates requests.

The framework's checkpoint and retry mechanisms are useful, but they do not remove the need to design external operations for repeated attempts.

## 4. The fix: idempotency keys and a `UNIQUE` constraint

This is where reliable workflow engineering becomes especially important.

Consider this node:

```
def charge_payment(state: State) -> dict:    payment_gateway.charge(        amount=state["amount"]    )    return {        "payment_status": "charged"    }
```

What happens if the gateway charges the customer successfully, but the process crashes before the node's successful result is persisted?

A retry may charge the same customer again.

The dangerous part is the gap between completing an external operation and saving the corresponding local result.

Checkpoint durability alone does not close that gap.

### 4.1 What is idempotency?

An operation is idempotent if performing the same logical operation repeatedly has the same intended effect as performing it once.

For example, setting a record's status to `"approved"` is naturally idempotent in many designs:

```
record.status = "approved"
```

Setting it to the same value repeatedly does not create another approval record by itself.

Charging a payment is different. Two calls can create two charges.

To make such an operation safer, you need a stable identifier for the logical action.

### 4.2 Design an idempotency key

A useful key for a payment might encode:

```
tenant ID
+ order ID
+ operation type
+ operation version
```

For example:

```
idempotency_key = (    f"tenant:{tenant_id}:"    f"order:{order_id}:"    f"charge:v1")
```

This key should be the same across retries of the same logical charge.

Do not generate a new random ID for every attempt. Doing so would make each retry look like a new operation.

Also, do not use the checkpoint ID as the business idempotency key. Replaying from another checkpoint may produce a different checkpoint identifier for the same intended payment.

### 4.3 Add a database uniqueness constraint

Your application can maintain a table of logical operations.

```
CREATE TABLE payment_actions (
    tenant_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    status TEXT NOT NULL,
    provider_reference TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (tenant_id, idempotency_key)
);
```

This primary key prevents the database from creating two rows for the same idempotency key within the same tenant.

The uniqueness constraint is important because a Python check like this is not sufficient:

```
if not repository.action_exists(idempotency_key):    repository.create_action(idempotency_key)
```

Two concurrent workers could both check that the key doesn't exist before either creates it.

The database uniqueness constraint is the final protection against duplicate records.

### 4.4 The essential distinction: database deduplication versus provider deduplication

Here is a robust pattern when the payment provider supports idempotency keys:

```
def charge_payment(    tenant_id: str,    order_id: str,    amount: float,) -> dict:    idempotency_key = (        f"tenant:{tenant_id}:"        f"order:{order_id}:charge:v1"    )    existing = repository.get_action(        tenant_id,        idempotency_key,    )    if existing is not None and existing.status == "succeeded":        return {            "payment_status": "charged",            "provider_reference": existing.provider_reference,        }    repository.create_pending_if_absent(        tenant_id=tenant_id,        idempotency_key=idempotency_key,    )    # The same key must be reused for every retry.    result = payment_gateway.charge(
```

This is a conceptual example; the repository operations need to be implemented with correct transaction handling and concurrency controls.

The example combines two protections:

- The local database ensures that the application has one logical record per operation key.
- The payment provider's idempotency mechanism, if supported and used correctly, deduplicates repeated requests for the same charge.

That second protection matters enormously.

Suppose the provider charges the customer successfully, then the process crashes before `mark_succeeded()`.

The next attempt sees a pending local action. It can call the provider again using the same key. If the provider correctly honors that idempotency key, the application can retrieve or recover the result without creating a second charge.

Without provider-side idempotency, a local uniqueness constraint alone cannot guarantee this behavior. The external charge and the local database update are two separate operations.

### 4.5 What if the external API does not support idempotency?

You need a different design, and the correct choice depends on the business operation.

For example, an outbox-based design can record an intended operation transactionally in the application's database, then dispatch it to the external system. You can track delivery attempts and reconcile uncertain outcomes.

However, an outbox alone does not magically guarantee exactly-once execution in a remote system. If the external API does not support deduplication, a dispatcher can still face uncertainty after a timeout or crash.

For high-value operations, you may need reconciliation against the external provider, a unique external reference, a query-before-retry strategy where appropriate, or an explicit compensation process.

The production principle is to make repeated attempts safe, not to assume repeated attempts will never happen.

## 5. Common mistakes across L15–L17

Here are the most important mistakes to avoid as you build production agents.

| Mistake                                            | Why it matters                                                    | Better approach                                        |
| -------------------------------------------------- | ----------------------------------------------------------------- | ------------------------------------------------------ |
| Using a new thread ID for every message            | The graph cannot find the intended conversation history           | Persist and reuse the correct thread ID                |
| Using `InMemorySaver` for durable production state | Process restarts lose in-memory persistence                       | Choose a persistent backend                            |
| Treating a checkpoint as just application state    | Internal execution metadata and version tracking also matter      | Use the public state APIs                              |
| Assuming `get_state_history()` is oldest first     | The newest snapshot is first                                      | Account for reverse chronological ordering             |
| Treating `update_state()` as an in-place mutation  | It creates a new checkpoint and follows reducer semantics         | Inspect the returned configuration and resulting state |
| Replaying a node with irreversible side effects    | External operations may execute again                             | Use idempotency mechanisms and control replay          |
| Retrying every exception                           | Permanent data errors can trigger pointless retries               | Classify exceptions deliberately                       |
| Assuming `"sync"` means exactly-once execution     | Checkpoint writes and external side effects are separate concerns | Use stable business idempotency keys                   |
| Copying checkpoint rows manually                   | Historical state may depend on writes and parent checkpoints      | Use supported APIs and tested backend-specific tools   |
| Deleting arbitrary checkpoint rows for retention   | Recovery and state reconstruction may break                       | Use backend-supported pruning and retention policies   |

## 6. A production checklist

For a production agent service, I would validate the following before considering checkpoint recovery complete.

### Persistence and thread management

- The graph has a persistent checkpointer.
- Each conversation or workflow uses a stable, authorized thread ID.
- Application replicas share the appropriate persistence backend.
- Connection pools and saver lifecycles are managed through application startup and shutdown.
- Database initialization and migrations are handled deliberately.
- Checkpoint data and credentials are protected by appropriate access controls.

### Recovery and debugging

- The team understands the chosen durability mode.
- The application has a safe way to inspect state and historical checkpoints.
- Interrupted workflows can be investigated and resumed as intended.
- Retention and deletion policies are tested.
- Replay procedures account for external side effects.

### Retries and external operations

- Retry policies distinguish transient errors from permanent ones.
- Backoff and jitter are appropriate for external-service limits.
- Timeouts are configured for relevant node operations.
- Error handlers record failures accurately and don't mask them as successes.
- Business operations use stable idempotency keys when necessary.
- Database uniqueness constraints protect against duplicate logical operations.
- External API operations use the provider's idempotency mechanisms where available.
- Crash and duplicate-request scenarios are tested, including failure between an external action and saving its result.

## 7. Checkpoint yourself

Use these questions to test whether you understand the mechanisms rather than just recognize the terminology.

1\. A user sends a second message. Which value connects it to the existing conversation history?

checkpoint_id

thread_id

channel_versions

2\. What does get_state_history() return first?

The oldest checkpoint

The newest checkpoint

Only failed checkpoints

3\. One parallel node succeeds and another fails. What can pending writes help LangGraph do?

Undo the successful node's external actions

Reuse successfully saved task outputs during recovery

Guarantee the failed node cannot execute again

4\. What does update_state() do?

Edits an old checkpoint in place

Creates a new checkpoint based on a state update

Deletes the remainder of the thread

5\. Which durability mode persists checkpoint changes before the next step starts?

exit

async

sync

6\. A payment succeeded remotely, but the node crashed before saving success. What is the key protection?

A new random ID per attempt

A stable business idempotency key with provider deduplication where supported

A bigger max_attempts value

0 of 6 answered

Reset quiz

## 8. Final mental model

Before moving on to the next LangGraph topic, make sure you can explain these five statements in your own words.

1\. Checkpoints preserve graph execution state. They are more than application dictionaries: they also contain internal bookkeeping needed to recover execution.

2\. Threads connect successive runs. A stable, properly authorized `thread_id` lets the graph locate the right interaction history.

3\. Inspection and time travel are different operations. `get_state()` and `get_state_history()` inspect saved state; `update_state()` creates a modified continuation; invoking from an earlier checkpoint re-executes subsequent nodes.

4\. Retries and durability solve different problems. Durability controls checkpoint persistence; retry policies control repeated node attempts. Neither automatically reverses an external operation.

5\. Exactly-once business effects require an explicit design. Stable idempotency keys, database uniqueness constraints, external provider deduplication, and reconciliation help make recovery safe.

Once these concepts are clear, you will have a solid foundation for the next advanced layer: interrupt/resume workflows, human-in-the-loop approval, persistent subgraphs, production agent deployment, and integrating tracing and observability through Langfuse.
