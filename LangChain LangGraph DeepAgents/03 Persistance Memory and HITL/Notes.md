# L15 · Checkpointers & Threads

A checkpoint is a **versioned snapshot of the graph's state,** saved after every step, tagged with a **thread id** that says which conversation it belongs to.

## Attaching a checkpointer to an AGENT

`create_agent` takes `checkpointer=` exactly like a `StateGraph`:

```python
from langchain.agents import create_agent

agent = create_agent(
    model=model,
    tools=[get_weather],
    system_prompt="You are a weather bot.",
    checkpointer=InMemorySaver(),
)

config = {"configurable": {"thread_id": "conv-1"}}
agent.invoke({"messages": [HumanMessage("What's the weather in Paris?")]}, config)
agent.invoke({"messages": [HumanMessage("And in Tokyo?")]}, config)
```

The agent's state is `AgentState`, whose `messages` channel uses the
`add_messages` reducer — so every turn appends.

Now because of checkout we will be able to see the entire conversation
```
prompt length: 6 messages
  SystemMessage 'You are a weather bot.'
  HumanMessage  "What's the weather in Paris?"
  AIMessage     ''
  ToolMessage   '18C and sunny in Paris'
  AIMessage     'It is 18C and sunny in Paris.'
  HumanMessage  'And in Tokyo?'
```

Without a checkpointer that prompt would contain only `'And in Tokyo?'`.



## Checkpoint Tuple
A saved checkpoint is a `CheckpointTuple`

```python
tup = saver.get_tuple(config)
tup.checkpoint     # the raw snapshot bundle (a dict)
tup.metadata       # step, source, parents
tup.config         # the config that addresses THIS checkpoint
tup.parent_config  # the config of the previous checkpoint
tup.pending_writes # writes from tasks not yet committed
```


### Checkpoint

- channel_values
- channel_versions
- versions_seen
- branch:to:<node>
- updated_channels
- v: 4


### Next node

Tuple of node names still to run

```
snap.next        # ()  -> nothing left to run
```

```python
next_nodes = [k.replace("branch:to:", "")
              for k in s.checkpoint["channel_values"]
              if k.startswith("branch:to:")]
```


### Metadata


```json
{ "source": "loop", "step": 3, "parents": {} }
```

source tells you **how this checkpoint came to exist**.

| `source`   | Meaning                                                 |
| ---------- | ------------------------------------------------------- |
| `"input"`  | the very first checkpoint, created from your input      |
| `"loop"`   | a normal step of the graph                              |
| `"update"` | created by `update_state()`                             |
| `"fork"`   | a branch created by re-running from an older checkpoint |

### Pending Writes
Writes that a task produced but that have **not yet been folded into `channel_values`**.



## Threads

A conversation is called a thread.
A **thread** is just a string you pass in the config. 
It acts as **your** identifier.

```python
config = {"configurable": {"thread_id": "user-42"}}
```

Re-invoking a thread continues it. It does not restart it.

```python
graph.invoke({"topic": "persistence", "notes": [], "count": 0}, cfg)
graph.invoke({"topic": "persistence", "notes": ["--second-run--"]}, cfg)
```

The second call **appended** to run 1's history. 
The whole point of thread is **persistence.**


## Checkpointer interface

The checkpoint interfaces with backend using these methods:

```python

# write a checkpoint
saver.put(config, checkpoint, metadata, new_versions)   

# write task outputs
saver.put_writes(config, writes, task_id, task_path)

# read one checkpoint    
saver.get_tuple(config)   

# iterate a thread's history                              
saver.list(config)                                      

# Delete
saver.delete_thread(thread_id)                         

# Trim history(Prune)
saver.prune([thread_ids], strategy="keep_latest")      

# create the schema
saver.setup()                                          

```

**You almost never call/setup these yourself.** 
LangGraph calls them for you when you `compile(checkpointer=saver)`. You call `setup()` and it builds everything.

- Backend DB: `PostgresSaver`
- Optional: `RedisSaver` (community) 


### PostgresSaver Setup in production

```python
from langgraph.checkpoint.postgres import PostgresSaver

with PostgresSaver.from_conn_string(DB_URL) as checkpointer:
    checkpointer.setup()                 # idempotent - safe every boot

    graph = builder.compile(checkpointer=checkpointer)
```

`setup()` runs the migrations and it creates:
1. `checkpoints`, 
2. `checkpoint_blobs`, 
3. `checkpoint_writes`, 
4. `checkpoint_migrations`. 

It is **idempotent** — calling it on every process start is the recommended pattern.

The Schema that setup() creates:
```sql
CREATE TABLE checkpoints (
    thread_id            text   NOT NULL,
    checkpoint_ns        text   NOT NULL DEFAULT '',
    checkpoint_id        text   NOT NULL,
    parent_checkpoint_id text,
    type                 text,
    checkpoint           jsonb  NOT NULL,   -- the snapshot bundle
    metadata             jsonb  NOT NULL DEFAULT '{}',
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

CREATE TABLE checkpoint_writes (
    thread_id text NOT NULL, checkpoint_ns text NOT NULL DEFAULT '',
    checkpoint_id text NOT NULL, task_id text NOT NULL,
    idx integer NOT NULL, channel text NOT NULL,
    type text, blob bytea NOT NULL, task_path text NOT NULL DEFAULT ''
);

CREATE TABLE checkpoint_blobs (
    thread_id text NOT NULL, checkpoint_ns text NOT NULL DEFAULT '',
    channel text NOT NULL, version text NOT NULL,
    type text NOT NULL, blob bytea,
    PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
);
```


## Database Connection Lifecycle:

❌ Don't create a pool per request.**

```python
# WRONG - a new connection pool on every request
@app.post("/chat")
def chat(body):
    with PostgresSaver.from_conn_string(DB_URL) as saver:   # 💀 pool per request
        graph = builder.compile(checkpointer=saver)
        return graph.invoke(...)
```

**✅ Create the saver once, at application startup.**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.saver = PostgresSaver.from_conn_string(DB_URL)
    with app.state.saver as saver:
        await saver.setup()
        app.state.graph = builder.compile(checkpointer=saver)
        yield
    # pool closed here

app = FastAPI(lifespan=lifespan)
```

Why it matters:

1. **Connection exhaustion.** `from_conn_string` opens a *pool*. 
One per request = N pools = your database's `max_connections` gone in seconds.

2. **Latency.** TLS + auth handshake on every request.

3. **Prepared statements.** `prepare_threshold=0` is set by LangGraph, so psycopg re-prepares statements; a warm pool avoids that churn.


Rule of thumb: one `PostgresSaver` per process, created at startup,
closed at shutdown. 



## Retention: prune vs delete_thread

`prune` trims the history but keeps the thread.
`delete_thread` remove the thread entirely

```python
saver.prune(["user-42"], strategy="keep_latest")   # keep the thread, trim history

saver.delete_thread("user-42")                      # remove the thread entirely
```


## The community Redis checkpointer

`langgraph-checkpoint-redis` is MIT licensed, community-maintained by the langchain-ai org and **not** part of the officially supported backend set.

```python
from langgraph.checkpoint.redis import RedisSaver

with RedisSaver.from_conn_string("redis://localhost:6379/0") as saver:
    saver.setup()
```

To Run Redis on docker:
```bash
docker run -d -p 6379:6379 redis/redis-stack-server:latest
```

#### When to use Redis:

|                        | Postgres      | Redis Stack                        |
| ---------------------- | ------------- | ---------------------------------- |
| Read latency           | ~1ms+         | ~0.1ms                             |
| Built-in TTL           | ❌ (you sweep) | ✅ `ttl={"default_ttl": 60}`        |
| SQL / JOIN your tables | ✅             | ❌                                  |
| Straightforward backup | ✅ (`pg_dump`) | ⚠️ RDB/AOF                          |
| Durability guarantee   | strong        | depends on your persistence config |
| Extra infra            | none          | Redis Stack modules                |



---


# L16 · State Inspection & Time Travel

Imagine a customer says *"the bot gave me a wrong answer yesterday"*. 

Now with a checkpointer you can:
1. **Look** at the past — `get_state`, `get_state_history`.
2. **Write** to the past — `update_state`.
3. **Re-run** the past — invoke with an old `checkpoint_id`.


## Inspection tools
```python
graph.get_state(config)                    # → StateSnapshot (current)
graph.get_state_history(config)            # → Iterator[StateSnapshot] (the past)
graph.update_state(config, values, as_node=None)   # → writes a new checkpoint
```



## Get_state

```python
snap = graph.get_state(cfg)
snap.values      # {'topic': 'alpha', 'notes': [...], 'count': 3}
snap.next        # ()  -> nothing left to run
snap.metadata    # {'source': 'loop', 'step': 3, 'parents': {}}
snap.created_at  # datetime
```

cfg is the config that you pass and it decides *which* checkpoint you read.


## Get_state_history

```python
history = list(graph.get_state_history(cfg))
```


Arguments that you can pass:
```python

# Get last 10 history
graph.get_state_history(cfg, limit=10)               

# Checkpoints before X
graph.get_state_history(cfg, before=older_config)    

# Only manual updates
graph.get_state_history(cfg, filter={"source": "update"})  
```


## Update_state

```python
new_config = graph.update_state(config, {"Some_State_Data": "New data" })
```

#### as_node

The `as_node` decides which node's write rules (reducer) apply.

```python
graph.update_state(cfg, {"notes": ["<injected>"]}, as_node="review")
```

If as_node is not present/defined, then LangGraph uses the last node that updated the state; if that's ambiguous it uses the write rules (reducer) of `__start__`.


#### one-head rule

Do not assume that updating a historical checkpoint automatically merges its new results into every later historical checkpoint.

The original execution history is not simply erased.

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


## Time travel: replaying an earlier checkpoint

Time travel lets you explore what happens if you resume from a historical checkpoint rather than the latest one.

two important capabilities:

- `Replay:` resume from an earlier checkpoint.
- `Fork:` create a new continuation from an earlier checkpoint with modified state.


### Replay versus fork

| Replay                                           | Fork                                                  |
| ------------------------------------------------ | ----------------------------------------------------- |
| Continues from an existing historical checkpoint | Creates a new checkpoint with modified state          |
| Re-executes subsequent nodes                     | Re-executes subsequent nodes using the modified state |
| Useful for reproducing execution                 | Useful for exploring alternative outcomes             |

#### ⚠️ Side effects do NOT undo

> Replaying re-runs your node code. If a node sends an email, charges a card,
> writes to your DB, or calls a third-party API — **it does it again.**


---

# L17 Durability - Retries and Crash Recovery


## Durability modes
- `sync`: checkpoint is written **before** the next step starts.

- `async`: checkpoint is written in the **background** while the next step runs

- `exit`: checkpoint is written once, when the run ends (success, error, or interrupt)


## RetryPolicy
- initial_interval: seconds before the first retry
- backoff_factor: each wait = previous * factor    
- max_interval: cap on the wait
- max_attempts: total attempts (1 = no retry)
- jitter: randomise to avoid thundering herds
- retry_on=default_retry_on: which exceptions are retryable

```python
from langgraph.types import RetryPolicy

builder.add_node(
    "flaky",
    flaky,
    retry_policy=RetryPolicy(
        initial_interval=0.5,     # seconds before the first retry
        backoff_factor=2.0,       # each wait = previous * factor
        max_interval=128.0,       # cap on the wait
        max_attempts=3,           # total attempts (1 = no retry)
        jitter=True,              # randomise to avoid thundering herds
        retry_on=default_retry_on, # which exceptions are retryable
    ),
)
```


### Re-execution Paths:

- `Crash / failure recovery`: re-execure the failed node from the top(start of the node function)
- `interrupt()`: re-execure the node containing interrupt() from the top
- replay / fork from an old checkpoint: re-execure every node after that point 

### Idempotency on retry:
use idempotency keys + UNIQUE constraint on Database



---


# L18 Human-in-the-Loop - Interrupts

Step 1: State function that has interrupt:

```python
from langgraph.types import interrupt, Command

def node(state):
   
# first call: raises, pauses the run, hands `answer` to the caller
 answer = interrupt({"question": "Approve this refund?",
                        "amount": state["amount"]})
    
    # after resume: `answer` IS the human's response
    return {"decision": answer}
```


Step 2: Calling before and after the interupt:

```python
config = {"configurable": {"thread_id": "t1"}}

# First call
out = graph.invoke({"amount": 250}, config, version="v2")

# Secord call
graph.invoke(Command(resume="approve"), config, version="v2")
```

#### `GraphOutput` can be checked using:

- `.value`: The graph state so far
- `.interrupts`: Tuple of pending `Interrupt` objects

for example:
```python
out = graph.invoke({"amount": 250}, config, version="v2")

type(out)            # <class 'langgraph.types.GraphOutput'>
out.value            # {'log': ['prepare:validated'], 'amount': 250}
out.interrupts       # (Interrupt(value={...}, id='...', response_schema=None),)
```



#### `Interrupt` Fields:

- `value`: the payload you passed to `interrupt()` — show this to the human
- `id`: a stable id for *this* interrupt; use it to answer precisely
- `response_schema`: JSON Schema of the expected answer (if you set one)


```python
Interrupt(value=..., id=..., response_schema=...)
```



## Resuming

Command(resume=...)

```python
from langgraph.types import Command

graph.invoke(Command(resume="approve"), config, version="v2")
```

**Note: The node restarts from the top, so keep everything above the `interrupt()` call idempotent.**

```python
# ❌ charges twice
def charge_node(state):
    charge_customer(state["customer_id"])          # runs again on resume!
    decision = interrupt("approve?")
    ...

# ✅ the effect is guarded by an idempotency key (L17)
def charge_node(state):
    if not already_charged(state["op_key"]):
        charge_customer(state["customer_id"])
    decision = interrupt("approve?")
    ...
```


## Structured answers: `response_schema`

The interrupt exposes the JSON Schema, so your frontend can render a form.

State function calling interrupt with `response_schema`:
```python
from pydantic import BaseModel

class Decision(BaseModel):
    approve: bool
    reason: str

def gate(state):
    d = interrupt({"question": "Approve?"}, response_schema=Decision)
    # d is a Decision instance
    return {"decision": str(d.approve)}
```

The data/structure of the `response_schema`:
```
interrupt: {'question': 'Approve?'}
response_schema: {'properties': {'approve': {...}, 'reason': {...}},
                  'required': ['approve', 'reason'], 'title': 'Decision',
                  'type': 'object'}
```


## Editing state before resuming

Sometimes the human wants to *change* something, not just answer a question.

```python
graph.update_state(cfg, {"amount": 10})     # lower the amount
graph.invoke(Command(resume="approve"), cfg, version="v2")
```

```
before  : {'log': ['prepare:validated'], 'amount': 500}
after   : {'log': ['prepare:validated'], 'amount': 10}
final   : {'log': ['prepare:validated', 'gate:approve', 'execute:approve'],
           'decision': 'approve', 'amount': 10}
```


##  Static breakpoints

you can add breakpoints using:
- interrupt_before
- interrupt_after

```python
graph = builder.compile(checkpointer=saver, interrupt_before=["b"])
```

same effect as:
```
paused before 'b':
  value     : {'log': ['a']}
  interrupts: ()      <- NO payload. There is nothing to answer.
  next      : ('b',)
```

These are **debugging breakpoints**, not a HITL mechanism


## HITL Middleware

using `interrupt()` in middleware instead of agent state call

```python
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware

agent = create_agent(
    model=model,
    tools=[send_email, delete_file],
    middleware=[
        HumanInTheLoopMiddleware(
            interrupt_on={"send_email": True, "delete_file": True},
            interrupt_mode="batched",     # or "per_call"
        )
    ],
    checkpointer=InMemorySaver(),
)
```

#### Two modes:
- `batched`: lists every gated call in the turn and expects one decision per call **in order**. 
Eg: all the code the AI edited is send to front end together as a batch and then the ui shown them one by one and then the human approves.

- `per_call`: one call per interrupt. 
Eg: sudden interpurtion for tool calls till the human approves or rejects

#### Four decision types:
- `approve`: run the tool as-is
- `reject`: don't run it; tell the model why
- `edit`: run it with different args
- `respond`: answer AS the tool; it never runs

#### Finding paused agents from your API

The `next` value tells you it is a *tool approval* pause (the middleware node) rather than a custom node pause.

```python
snap = agent.get_state(cfg)
snap.next        # ('HumanInTheLoopMiddleware.after_model',)
snap.interrupts  # the pending HITLRequest
```


---


# L19 · Human-in-the-Loop Part 2 — Production Approval Flows


#### Approval Status
- pending
- approved
- denied
- timed_out
- cancelled

The client should receive:
```json
{
    "status": "pending",
    "approval_id": "approval-1001",
    "thread_id": "thread-abc-123",
    "action": "refund_customer"
}
```



## Authorization rules

Before accepting the decision check for:
- Authentication
- Tenant isolation
- Reviewer authorization
- Separation of duties
- Request validity
- Payload integrity


## Audit trail
You should audit all activities (before and after approval)

An approval system should be able to answer:
- Who requested this operation?
- Who approved or rejected it?
- When was it approved?
- What exact operation was approved?
- What were its original parameters?
- Were the parameters modified?
- Why did the reviewer make the decision?
- Did the graph execute successfully?
- Was the action retried?
- Was the operation ultimately completed?

Example:
```json
{
    "approval_id": "approval-1001",
    "event": "APPROVAL_GRANTED",
    "actor": "manager-123",
    "timestamp": "2026-11-02T10:30:00Z"
}
```

Then separately:
```json
{
    "approval_id": "approval-1001",
    "event": "REFUND_EXECUTED",
    "actor": "refund-service",
    "timestamp": "2026-11-02T10:31:10Z"
}
```


---


# Short-Term Memory

## context-window

System prompt + Conversation messages + Tool definitions + 
Tool results + Retrieved documents + Memory + Other instructions


### If maximum context capacity is reached

#### Technique 1: trim_messages

```python
from langchain_core.messages import trim_messages

trimmed_messages = trim_messages(
    messages,
    max_tokens=2000,
    token_counter=model,
    strategy="last",
    include_system=True,
    allow_partial=False,
    start_on="human",
)
```


#### Technique 2: ContextEditingMiddleware

`ClearToolUsesEdit`: middleware can clear older tool results when the input context becomes too large.

```python
agent = create_agent(
    model=model,
    tools=tools,
    middleware=[
        ContextEditingMiddleware(
            edits=[
                ClearToolUsesEdit(
                    trigger=4000,
                    keep=3,
                    exclude_tools=["important_database_query"],
                )
            ],
            token_count_method="approximate",
        )
    ],
)
```

The context is counted using the following technique:
- `approximate`: Estimate token usage
- `model`: Use the model's token-counting capability when supported

`Exclude_tools` dont not clear the context of the imp tools


#### Technique 3: SummarizationMiddleware

summarization tries to preserve the important information in a much smaller representation

```python
from langchain.agents.middleware import (
    SummarizationMiddleware,
)

agent = create_agent(
    model=model,
    tools=tools,
    middleware=[
        SummarizationMiddleware(
            model=summarization_model,
            trigger=[("tokens", 8000),("messages", 30),],
            keep=("messages", 20),
        )
    ],
)
```


`trigger`: means summarization happens when the context reaches the configured threshold.

OR logic:
```python
trigger=[
    ("tokens", 8000),
    ("messages", 30),
]
```

AND logic:
```python
trigger={
    "tokens": 8000,
    "messages": 30,
}
```


---


# L21 — Long-Term Memory: Store and LangMem


A namespace is how you organize stored information.

```python
namespace = (
    "memories",
    "tenant-001",
    "user-123",
)
```


```
memories
   |
   +-- tenant-001
          |
          +-- user-123
```


## Store

LangGraph offers a generic storage interface.

```python
from langgraph.store.base import BaseStore
```

A store can be accessed using the Runtime object.
```python
runtime.store
```


#### Search
```python
store.search(
    ("memories", "tenant-001")
)
```

#### Put Items

An item is an individual record inside a namespace.

it has:
- `Namespace`: Where the item belongs
- `Key`: Unique item identifier within that namespace
- `Value`: Stored JSON-compatible mapping
- `created_at`
- `updated_at`

```python
store.put(
    namespace,
    "preference-001",
    {
        "category": "programming",
        "value": "Prefers Python",
    },
)
```


#### Retrieve(get) Items

```python
item = store.get(
    namespace,
    "preference-001",
)

print(item.value)
```


#### Delete

```python
store.delete(
    namespace,
    "preference-001",
)
```


#### normal search	vs semantic search

A normal key lookup retrieves an item by identifier.
```python
results = store.search(
    namespace,
)
```

A semantic search finds items related to a natural-language query.
```python
results = store.search(
    namespace,
    query="What programming language does the user prefer?",
)
```

### Metadata filtering

Semantic similarity alone is not enough.

Namespace isolation should be the primary boundary, with metadata filters providing additional selection.

### Store Durability 

`InMemoryStore`: Development
`PostgresStore`: Production

The PostgresStore manages its own persistence schema.

```python
await store.setup()
```


## LangMem — automatic memory

LangMem is a higher-level library that sits on top of LangGraph’s Store


#### When to use what:

- **Use only the Store when:**
    * You want full control over what gets written and how.
    * You are writing custom tools or nodes that just put/get/search.
    * Your memory needs are simple

- **Use LangMem (on top of a Store) when:**:
    * You want the agent to automatically extract useful facts, preferences, episodic summaries, etc.
    * You want the agent to be able to call manage_memory / search_memory tools itself **(“hot path”).**
    * You want procedural memory / prompt self-improvement.


### 2 ways to use LangMem:

1. **Tool-based / Hot-path :** 
	* `create_manage_memory_tool` + `create_search_memory_tool`
	* Agent can decide during the conversation to save/search memories.
	* **Pros:**
		* Immediate: the memory is available in the next turn of the same conversation.
		* Agent has full control
	* **Cons:**
	    * Adds latency to every response
	    * Higher token cost
	* **Best for:**
		* Explicit “remember this” / “forget this” moments
		* Critical facts that must be available immediately 
	
2. **Background / store managers:** 
	* `create_memory_store_manager` (or the lower-level `create_memory_manager`)
	* Automatically extract, update, consolidate memories after (or outside) the conversation.
	* **Pros:**
		* Zero extra latency for the user.
		* Agent stays simple — it just chats.
		* Better extraction quality
		* Cheaper in the long run
	* **Cons:**
		* Memories appear with a delay
		* Not ideal if the user says “Remember X” and expects it to work in the very next message.
	* **Best for:**
		* Most production usecases
		* High-traffic applications where latency and cost matter.


### Approach 1 — Tool-based (Hot-path)
The agent can use tools to:
- Create memories.
- Update memories.
- Delete memories.
- Search existing memories

example:
```python
from langmem import (
    create_manage_memory_tool,
    create_search_memory_tool,
)

model = init_chat_model(
    "google_genai:<supported-gemini-model>"
)

store = InMemoryStore()

tools = [
    create_manage_memory_tool(
        namespace=("memories", "{langgraph_user_id}"),
    ),
    create_search_memory_tool(
        namespace=("memories", "{langgraph_user_id}"),
    ),
]

agent = create_agent(
    model=model,
    tools=tools,
    store=store,
)
```

The user says: Remember that I prefer Python.
and the agent can call manage_memory.


### Approach B — Manager-based (automatic)

Instead of asking the active agent to manage memory through explicit tool calls, you can use a memory manager.

**create_memory_manager** 
- it is the core stateless memory extractor module
- it can be used with any AI agent memory 
- it can be used with Langgraph memory store or other tools like:
	- Mem0: Fact extraction + vector (+ optional graph)
	- Zep (Graphiti)
	- Letta (formerly MemGPT): OS-style tiered memory
	- Supermemory: Memory API + context engine
- it can be used with Vector Databases and do memory search yourself.

**create_memory_store_manager**
- A higher-level wrapper that uses create_memory_manager internally
- It is specifically designed to work smoothly with LangGraph’s Store
- It automatically:
	- searches the Store for existing memories,
	- calls the underlying create_memory_manager,
	- writes the results back to the Store
```python
from langmem import create_memory_store_manager

store_manager = create_memory_store_manager(
    "anthropic:claude-3-5-sonnet-latest",
    namespace=("memories", "{user_id}"),   # supports templates
    store=store,                          # optional if using graph context
    schemas=[YourSchema],
    instructions="...",
    enable_inserts=True,
    enable_deletes=False,
    query_limit=5,                        # how many existing memories to fetch
)

# Just pass the conversation — it does everything
store_manager.invoke(
    {"messages": conversation},
    config={"configurable": {"user_id": "user_123"}}
)
```

#### Create_memory_manager vs Create_memory_store_manager

```
create_memory_manager          ← pure extraction engine (stateless)
         ↑
         │ used by
         │
create_memory_store_manager    ← convenient wrapper that adds Store I/O
```


## Memory design

### Three kinds of memory
1. Semantic memory
    - Facts and knowledge.
    - Examples:
    	``` 
    	- User works with Python.
	    - User uses PostgreSQL.
	    ```
2. Episodic memory
    - Information about specific past events.
    - Examples:
        ```
        - On November 1, the user approved a deployment.
        - Last week, the user requested a database migration review.
        ```
3. Procedural memory
	- Information about how tasks should be performed.
	- Examples:
	```
		- Always produce Python examples.
		- Prefer open-source frameworks.
		- Follow the organization's coding standards.
	```
