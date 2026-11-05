# L15 · Checkpointers & Threads

A checkpoint is a **versioned snapshot of the graph's state,** saved after every step, tagged with a **thread id** that says *which conversation it belongs to.

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










