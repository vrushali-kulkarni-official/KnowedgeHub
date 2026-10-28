# L15 · Checkpointers & Threads

> **Phase 8 — Persistence, Memory & Human-in-the-Loop**
> Module M54 · *Checkpointers & PostgresSaver*
>
> Run: `python examples/ex01_checkpoint_anatomy.py`
> Run: `python examples/ex02_postgres_saver.py`
> Run: `python examples/ex03_agent_with_checkpointer.py`
> Run: `python examples/ex04_redis_checkpointer.py`

---

## 0. Why this lesson comes first

Everything else in this phase sits on top of one primitive: **the ability to
write a graph's state somewhere, and read it back later.**

Without it you cannot:

| You want to…                                | Needs a checkpointer |
|----------------------------------------------|----------------------|
| Remember what the user said 3 turns ago      | ✅ short-term memory |
| Pause a workflow for a human to approve it   | ✅ HITL              |
| Resume a workflow after your process crashed | ✅ crash recovery    |
| Re-run a production thread to debug it       | ✅ time travel       |
| Ask "what exactly happened in step 7?"       | ✅ observability     |

So let's build the mental model first, then the Postgres specifics.

---

## 1. The one-sentence model

> A **checkpoint** is a *versioned snapshot of the graph's state*, saved after
> every step, tagged with a **thread id** that says *which conversation it
> belongs to*.

Two words do all the work:

- **versioned** — you get the whole history, not just the latest.
- **thread id** — the namespace. Same graph, different thread = different state.

### Python bridge

Think of a checkpoint like a **save file in a game**, and the thread id like
the **save slot**.

```python
# Without persistence (what you had in Phase 7):
result = graph.invoke({"messages": [...]})   # state dies with the call

# With persistence:
graph.invoke({"messages": [...]}, {"configurable": {"thread_id": "user-42"}})
# ...state is saved. Later:
graph.invoke({"messages": [...]}, {"configurable": {"thread_id": "user-42"}})
# ...the graph CONTINUES where it left off.
```

Like `pickle.dump` vs `pickle.load`, but the "file" is a database row and the
"path" is the thread id.

---

## 2. What is actually inside a checkpoint?

This is where most tutorials hand-wave. Let's look at the real thing.
`ex01_checkpoint_anatomy.py` dumps it.

A saved checkpoint is a `CheckpointTuple` with four parts:

```python
tup = saver.get_tuple(config)
tup.checkpoint     # the raw snapshot bundle (a dict)
tup.metadata       # step, source, parents
tup.config         # the config that addresses THIS checkpoint
tup.parent_config  # the config of the previous checkpoint
tup.pending_writes # writes from tasks not yet committed
```

### 2.1 `tup.checkpoint` — the snapshot bundle

Real output from `ex01`:

```json
{
  "v": 4,
  "ts": "2026-10-28T15:16:35.612190+00:00",
  "id": "1f1d2e29-0a13-6632-8003-5de1790ac511",
  "channel_versions": {
    "__start__": "00000000000000000000000000000002.0.2189560551084001",
    "topic":      "00000000000000000000000000000002.0.2189560551084001",
    "notes":      "00000000000000000000000000000005.0.11547589925131219",
    "count":      "00000000000000000000000000000005.0.11547589925131219",
    "branch:to:plan":   "00000000000000000000000000000003.0.1455868447692935",
    "branch:to:work":   "00000000000000000000000000000004.0.5593263189746506",
    "branch:to:review": "00000000000000000000000000000005.0.11547589925131219"
  },
  "versions_seen": {
    "__input__": {},
    "__start__": { "__start__": "00000000000000000000000000000001.0.7973127125598728" },
    "plan":   { "branch:to:plan":   "00000000000000000000000000000002.0.2189560551084001" },
    "work":   { "branch:to:work":   "00000000000000000000000000000003.0.1455868447692935" },
    "review": { "branch:to:review": "00000000000000000000000000000004.0.5593263189746506" }
  },
  "updated_channels": ["count", "notes"],
  "channel_values": {
    "topic": "persistence",
    "notes": ["plan:persistence", "work:done", "review:ok"],
    "count": 3
  }
}
```

Let's decode every field, because these names show up in every error message
you will ever read.

**`channel_values`** — the actual state you care about. This is your
`StateGraph` state, plus LangGraph's internal channels.

**`channel_versions`** — a version counter for each channel. The format is
`"<version>.<nanos>"`. Why? Because LangGraph needs to know *whether a value
is newer than what a node has already seen*. That's how it does conflict
resolution across parallel branches.

**`versions_seen`** — for each node, the version of each channel it had
*already observed* when it last ran. This is the mechanism behind
`InvalidUpdateError` and behind "my reducer ran twice".

**`branch:to:<node>` channels** — these encode *which node runs next*. An
empty branch channel means "not scheduled". This is how a graph says
"after `plan`, go to `work`".

**`updated_channels`** — which channels actually changed in this step. Used
to compute deltas.

**`v: 4`** — the checkpoint *format version*. LangGraph migrates old
checkpoints forward automatically when you read them.

### 2.2 The "next node" question

A common confusion: `CheckpointTuple` has **no `.next` attribute**.

```python
s = saver.list(cfg)[0]
s.next        # ❌ AttributeError
```

`next` lives on **`StateSnapshot`**, which is what `graph.get_state()` returns
(see L16). Inside the raw checkpoint, the schedule is encoded as the
`branch:to:*` channels:

```python
next_nodes = [k.replace("branch:to:", "")
              for k in s.checkpoint["channel_values"]
              if k.startswith("branch:to:")]
```

### 2.3 `tup.metadata`

```json
{ "source": "loop", "step": 3, "parents": {} }
```

`source` tells you **how this checkpoint came to exist**. You will meet these
values in L16:

| `source`   | Meaning                                                  |
|------------|----------------------------------------------------------|
| `"input"`  | the very first checkpoint, created from your input        |
| `"loop"`   | a normal step of the graph                                 |
| `"update"` | created by `update_state()`                                |
| `"fork"`   | a branch created by re-running from an older checkpoint    |

`step` is the superstep counter. `parents` holds the parent ids (relevant for
subgraphs / parallel branches).

### 2.4 `pending_writes`

Writes that a task produced but that have **not yet been folded into
`channel_values`**. They exist so that a crash between "task finished" and
"checkpoint committed" does not lose the task's output.

---

## 3. Threads: a conversation is a thread

A **thread** is just a string you pass in the config. LangGraph does not
parse it, validate it, or give it meaning. It is *your* identifier.

```python
config = {"configurable": {"thread_id": "user-42"}}
```

Everything scoped by that string shares one state history.

### 3.1 The one rule that surprises everyone

**Re-invoking a thread continues it. It does not restart it.**

```python
graph.invoke({"topic": "persistence", "notes": [], "count": 0}, cfg)
graph.invoke({"topic": "persistence", "notes": ["--second-run--"]}, cfg)
```

With `notes: Annotated[list[str], operator.add]` the output is:

```python
{'topic': 'persistence',
 'notes': ['plan:persistence', 'work:done', 'review:ok',   # run 1
           '--second-run--', 'plan:persistence', 'work:done', 'review:ok'],  # run 2
 'count': 6}
```

The second call **appended** to run 1's history. That is the whole point of
persistence — and it is also why you must think about what you pass as input
on a continuing thread. If you pass the full state every time, you will
duplicate it.

### 3.2 Thread id design

| Purpose                     | Thread id                | Notes                                |
|-----------------------------|--------------------------|--------------------------------------|
| One chat per user           | `f"{tenant}:{user}"`     | one conversation per user             |
| Many chats per user         | `f"{tenant}:{user}:{conv}"` | one per conversation                |
| Workflow run                | `f"run:{uuid4()}"`       | one-shot, disposable                  |
| Per-tenant isolation        | `f"{tenant}:{user}"`     | see L22 — isolation is structural     |

> **Never** use a bare user id as a thread id if users can collide across
> tenants. Prefix it. L22 shows why.

---

## 4. The checkpointer interface

Every backend implements the same ABC (`langgraph.checkpoint.base.BaseCheckpointSaver`).
You only ever need four methods:

```python
saver.put(config, checkpoint, metadata, new_versions)   # write a checkpoint
saver.put_writes(config, writes, task_id, task_path)    # write task outputs
saver.get_tuple(config)                                 # read one checkpoint
saver.list(config)                                      # iterate a thread's history
```

Plus lifecycle helpers you will use in production:

```python
saver.delete_thread(thread_id)                          # GDPR
saver.prune([thread_ids], strategy="keep_latest")      # trim history
saver.setup()                                          # create the schema
```

**You almost never call these yourself.** LangGraph calls them for you when
you `compile(checkpointer=saver)`. You call `setup()` once at boot and the
rest when you are building admin tooling.

---

## 5. Choosing a backend

| Backend | Import | Survives restart | Semantic search | TTL | Best for |
|---|---|---|---|---|---|
| `InMemorySaver` | `langgraph.checkpoint.memory` | ❌ | ❌ | ❌ | tests, notebooks, throwaway |
| `PostgresSaver` | `langgraph.checkpoint.postgres` | ✅ | ❌ | ❌ (sweep it) | **production default** |
| `AsyncPostgresSaver` | `langgraph.checkpoint.postgres.aio` | ✅ | ❌ | ❌ | async services (FastAPI) |
| `SqliteSaver` | `langgraph.checkpoint.sqlite` | ✅ | ❌ | ❌ | local dev, single-node |
| `RedisSaver` (community) | `langgraph.checkpoint.redis` | ✅ | ❌ | ✅ native | high-throughput, ephemeral |

> ⚠️ **`langgraph.checkpoint` and `langgraph.store` have EMPTY top-level
> namespaces.** `from langgraph.checkpoint import PostgresSaver` **fails**.
> Always import from the full sub-path:
> `from langgraph.checkpoint.postgres import PostgresSaver`.

---

## 6. PostgresSaver in production

### 6.1 Setup

```python
from langgraph.checkpoint.postgres import PostgresSaver

with PostgresSaver.from_conn_string(DB_URL) as checkpointer:
    checkpointer.setup()                     # idempotent - safe every boot
    graph = builder.compile(checkpointer=checkpointer)
```

`setup()` runs the migrations: it creates `checkpoints`, `checkpoint_blobs`,
`checkpoint_writes`, `checkpoint_migrations`. It is **idempotent** — calling it
on every process start is the recommended pattern.

### 6.2 The schema (verified on `langgraph-checkpoint-postgres` 3.2.0)

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

**Key insight:** `checkpoint_blobs` is keyed by *(channel, version)*, not by
*key*. That is how the same value can be shared by many checkpoints without
being stored twice — a real database, not a JSON blob dump.

### 6.3 Lifecycle in a service — the part people get wrong

**❌ Don't create a pool per request.**

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

1. **Connection exhaustion.** `from_conn_string` opens a *pool*. One per
   request = N pools = your database's `max_connections` gone in seconds.
2. **Latency.** TLS + auth handshake on every request.
3. **Prepared statements.** `prepare_threshold=0` is set by LangGraph, so
   psycopg re-prepares statements; a warm pool avoids that churn.

**Rule of thumb:** one `PostgresSaver` per process, created at startup,
closed at shutdown. In Kubernetes, one per pod.

### 6.4 Async

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async with AsyncPostgresSaver.from_conn_string(DB_URL) as saver:
    await saver.setup()
    graph = builder.compile(checkpointer=saver)
    await graph.ainvoke(inputs, config)
    state = await graph.aget_state(config)
```

Use `ainvoke`/`astream`/`aget_state` when your service is async — the async
saver uses non-blocking psycopg3 calls.

### 6.5 Retention: `prune` vs `delete_thread`

```python
saver.prune(["user-42"], strategy="keep_latest")   # keep the thread, trim history
saver.delete_thread("user-42")                      # remove the thread entirely
```

Measured in `ex02`:

```
checkpoints before prune: 8
checkpoints after  prune: 1
checkpoints after delete_thread: 0
```

* `prune` → the conversation continues, but you lose the ability to time-travel
  back through it. **Run this on a schedule** (e.g. keep the last 20
  checkpoints per thread).
* `delete_thread` → GDPR "right to be forgotten". See L22.

---

## 7. The community Redis checkpointer

`langgraph-checkpoint-redis` (MIT, community-maintained by the langchain-ai
org, **not** part of the officially supported backend set).

```python
from langgraph.checkpoint.redis import RedisSaver

with RedisSaver.from_conn_string("redis://localhost:6379/0") as saver:
    saver.setup()
```

### 7.1 The requirement nobody mentions

> **RedisSaver requires Redis Stack** (RedisJSON + RediSearch modules),
> because it uses RedisVL for its indexes.

Verified on `langgraph-checkpoint-redis` 0.5.2 against a plain `redis-server`:

```
redisvl.exceptions.RedisVLError: Failed to load data: ...
unknown command 'JSON.SET'
```

Fix:

```bash
docker run -d -p 6379:6379 redis/redis-stack-server:latest
```

`ex04_redis_checkpointer.py` detects this and prints the fix instead of
crashing.

### 7.2 When would you want it?

| | Postgres | Redis Stack |
|---|---|---|
| Read latency | ~1ms+ | ~0.1ms |
| Built-in TTL | ❌ (you sweep) | ✅ `ttl={"default_ttl": 60}` |
| SQL / JOIN your tables | ✅ | ❌ |
| Straightforward backup | ✅ (`pg_dump`) | ⚠️ RDB/AOF |
| Durability guarantee | strong | depends on your persistence config |
| Extra infra | none | Redis Stack modules |

**The common production pattern:** Postgres for durable, long-lived,
queryable conversations; Redis for ephemeral, high-volume, short-lived ones.

**Practical default for most teams: just use Postgres.** It is one fewer
system, it is queryable, and you can JOIN your `users` table against
`checkpoints.thread_id`. Reach for Redis when you have measured a latency
problem.

---

## 8. Attaching a checkpointer to an AGENT

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

**Proof it works** (from `ex03`): the model prompt on turn 2 contains turn 1:

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

---

## 9. Common mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| Forgetting `thread_id` | `ValueError: checkpointer requires a thread_id` | always pass `configurable.thread_id` |
| New saver per request | connection exhaustion | create once at startup |
| Forgetting `setup()` | `relation "checkpoints" does not exist` | call `setup()` at boot |
| Passing full state on every turn | duplicated history | pass only the *delta* |
| Same thread id for two users | state leaks between users | scope the thread id |
| `import from langgraph.checkpoint` | `ImportError` | use the full sub-path |
| Using `InMemorySaver` in prod | state vanishes on deploy | `PostgresSaver` |

---

## 10. Checkpoint yourself

- [ ] I can name the four fields of a `CheckpointTuple` and what each is for.
- [ ] I can explain `channel_versions` and `versions_seen` in my own words.
- [ ] I know why `CheckpointTuple` has no `.next`.
- [ ] I know that re-invoking a thread *continues* it.
- [ ] I can write the `PostgresSaver` startup/shutdown code for a FastAPI app.
- [ ] I know that RedisSaver needs Redis Stack.

**Next → [L16: State inspection & time travel](./L16-state-inspection-and-time-travel.md)**
