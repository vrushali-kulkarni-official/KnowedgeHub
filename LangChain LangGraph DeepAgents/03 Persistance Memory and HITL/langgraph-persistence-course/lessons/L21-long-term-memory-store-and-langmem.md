# L21 · Long-Term Memory — the Store & langmem

> **Phase 8 — Persistence, Memory & Human-in-the-Loop**
> Module M60 · *Long-term memory: Store & langmem*
>
> Run: `python examples/ex15_store_basics.py`
> Run: `python examples/ex16_postgres_store.py`
> Run: `python examples/ex17_langmem.py`

---

## 0. Two persistence systems, two questions

| | **Checkpointer** | **Store** |
|---|---|---|
| Question it answers | "what is the graph's state *right now*, for *this* thread?" | "what does the app know, *across* threads?" |
| Scope | one thread | application-defined namespaces |
| Keyed by | `thread_id` | `(namespace, key)` |
| Contains | graph state (messages, counters, flags) | facts, preferences, procedures |
| Dies with | the thread | never (until you delete it) |
| LangGraph import | `langgraph.checkpoint.postgres` | `langgraph.store.postgres` |

A concrete example:

> "The user prefers metric units."
>
> - **Short-term** (checkpoint): "in *this* conversation, the user said 'always use Celsius'."
> - **Long-term** (store): "this user, in *every* conversation, wants metric units."

You can use either, both, or neither.

---

## 1. The Store API

```python
from langgraph.store.memory import InMemoryStore          # dev
from langgraph.store.postgres import PostgresStore        # production

store.put(namespace, key, value, index=None, ttl=None)
store.get(namespace, key, refresh_ttl=None)
store.search(namespace_prefix, query=None, filter=None, limit=10, offset=0)
store.delete(namespace, key)
store.batch([...])
store.list_namespaces(prefix=None)
```

### 1.1 Namespaces are tuples of strings

A namespace is a **path**, read right to left as a hierarchy:

```python
("users", "alice", "memories")
  users   -> alice   -> memories
```

`search()` takes a **prefix** and returns everything under it:

```python
store.search(("users",))                     # every user's everything
store.search(("users", "alice"))             # alice's everything
store.search(("users", "alice", "memories")) # exactly that level
```

Verified in `ex15`:

```
store.search(('users',))
   ('users', 'alice', 'memories') / pref-1
   ('users', 'alice', 'memories') / fact-1
   ('users', 'bob', 'memories') / pref-1
   ('users', 'alice', 'projects') / proj-1

store.search(('users', 'alice', 'memories'))
   ('users', 'alice', 'memories') / pref-1
   ('users', 'alice', 'memories') / fact-1
```

> **The namespace is the unit of isolation.** L22 is entirely about getting
> this right.

### 1.2 Items

```python
item = store.get(("users", "alice", "memories"), "pref-1")
item.value        # {'content': 'prefers dark mode', 'kind': 'preference'}
item.namespace    # ('users', 'alice', 'memories')
item.key          # 'pref-1'
item.created_at   # datetime
item.updated_at   # datetime
```

`value` is a plain dict — you decide the schema.

### 1.3 Using the store from inside a node

```python
from langgraph.config import get_store

def remember(state):
    st = get_store()
    st.put(("users", "dave", "memories"), "m1", {"content": "asked about invoices"})
    ...
```

`get_store()` works in any node or `@task`, as long as the graph was compiled
with `store=`. You never thread the store through state.

```python
graph = builder.compile(checkpointer=saver, store=store)
```

### 1.4 `batch()`

```python
from langgraph.store.base import GetOp, PutOp, SearchOp, ListNamespacesOp

results = store.batch([
    PutOp(("users", "carol", "memories"), "m1", {"content": "likes tea"}),
    PutOp(("users", "carol", "memories"), "m2", {"content": "lives in Oslo"}),
    GetOp(("users", "carol", "memories"), "m1"),
])
```

`Op` is a **type alias** (a union), not a class you instantiate with a
string action:

```python
Op = GetOp | SearchOp | PutOp | ListNamespacesOp
```

Use the concrete NamedTuples.

---

## 2. PostgresStore — production

```python
from langgraph.store.postgres import PostgresStore
from langgraph.store.postgres.base import PostgresIndexConfig

index = PostgresIndexConfig(
    dims=768,
    embed=embeddings,      # a LangChain `Embeddings` object
    fields=["content"],    # which field of the value to embed
)

with PostgresStore.from_conn_string(DB_URL, index=index) as store:
    store.setup()
    ...
```

### 2.1 Requirements

| Requirement | Detail |
|---|---|
| PostgreSQL 15+ | verified on 15.19 |
| **pgvector** extension | `CREATE EXTENSION vector;` — the store's schema uses `vector` columns |
| An embedding model | only if you want semantic search |

```bash
apt-get install postgresql-15-pgvector
psql -c "CREATE EXTENSION vector;"
```

Verified in `ex16`:

```
0. Requirements check
   pgvector extension: 0.8.7
```

### 2.2 The tables

`store` and `store_vectors`:

```sql
CREATE TABLE store (
    prefix text NOT NULL,      -- dot-joined namespace: 'users.alice.memories'
    key    text NOT NULL,
    value  jsonb NOT NULL,
    created_at timestamptz, updated_at timestamptz,
    expires_at timestamptz, ttl_minutes int
);
CREATE TABLE store_vectors (
    prefix text, key text, field_name text, embedding vector(dims), ...
);
```

Note the prefix is stored **dot-joined** (`users.alice.memories`). That's why
namespace ordering matters so much (L22).

### 2.3 Semantic search

```python
results = store.search(("users", "alice", "memories"),
                        query="measurement units preference", limit=3)
for r in results:
    print(r.score, r.key, r.value)
```

Verified:

```
4. SEMANTIC search - 'what units does alice like?'
   score=0.2582  m3: 'always reply in metric units'
   score=0.0     m1: 'prefers dark mode in the dashboard'
   score=0.0     m2: 'works at Acme Corp as a data engineer'
```

`search(query=...)` embeds the query, compares it to the stored vectors with
pgvector, **and still applies the namespace filter**. That combination —
semantic *and* scoped — is the whole point.

### 2.4 Metadata filtering

```python
store.search(("users", "alice", "memories"),
             filter={"kind": "preference", "source": "mobile"})
```

Filters are ANDed. Verified:

```
6. Metadata filtering
   filter kind=preference AND source=mobile ->
     m4: prefers dark mode in the mobile app
```

### 2.5 The production embedding model

```python
from langchain_google_genai import GoogleGenerativeAIEmbeddings

embed = GoogleGenerativeAIEmbeddings(
    model="gemini-embedding-001",
    google_api_key=os.environ["GOOGLE_API_KEY"],
)
index = PostgresIndexConfig(dims=3072, embed=embed, fields=["content"])
```

| Model | Status | Notes |
|---|---|---|
| `gemini-embedding-001` | ✅ current | 128–3072 dims; 768/1536/3072 recommended |
| `text-embedding-004` | ⚠️ deprecated for the Gemini API (Jan 2026) | 768 dims, English only |
| `text-embedding-005` | ✅ | 768 dims, English + code |

> ⚠️ **Changing the embedding model or `dims` invalidates every stored
> vector.** You must re-index: delete and re-`put` every item. Plan the
> embedding model before you have production data, and version your namespaces
> if you might change it:
> `("memories", "v2", "alice")`.

---

## 3. langmem — automatic memory

`langmem` is **MIT-licensed but still PRE-1.0** (verified: `0.0.30`).
**Pin it exactly** and read the changelog before upgrading:

```bash
uv add "langmem==0.0.30"
```

It offers two approaches.

### 3.1 Approach A — tool-based (explicit)

The **agent** decides what is worth remembering, and calls a tool.

```python
from langmem import create_manage_memory_tool, create_search_memory_tool

manage_tool = create_manage_memory_tool(
    namespace=("memories", "{langgraph_user_id}"),
    store=store,
    actions_permitted=("create", "update", "delete"),
)
search_tool = create_search_memory_tool(
    namespace=("memories", "{langgraph_user_id}"),
    store=store,
)

agent = create_agent(model, tools=[manage_tool, search_tool], checkpointer=..., store=...)
```

Verified (`ex17`):

```
A2. The agent calls manage_memory
   result: created memory 9760708b-2195-41a4-83b1-7d42260f376f

   what is in the store now:
     9760708b-...: {'content': 'prefers metric units'}
     c7581f4b-...: {'content': 'works at Acme Corp as a data engineer'}

A4. Namespace isolation
   alice sees: ['prefers metric units', 'works at Acme Corp as a data engineer']
   bob sees  : ['prefers light mode']
```

**Pros:** total control, no LLM surprise, predictable cost, auditable.
**Cons:** the agent must remember to call the tool.

### 3.2 Approach B — manager-based (automatic)

A manager reads the conversation, extracts memories, writes them to the Store.

```python
from langmem import create_memory_store_manager

manager = create_memory_store_manager(
    model,                                   # any tool-calling chat model
    store=store,
    namespace=("memories", "{langgraph_user_id}"),
)

await manager.ainvoke({"messages": messages}, config=config)
```

**The `{langgraph_user_id}` template** is resolved from
`config["configurable"]["langgraph_user_id"]` — so the scope comes from the
request, not from a string you concatenate by hand.

Verified:

```
B2. FIX: write memories in the manager-compatible shape
   manager output: [{'namespace': ('memories', 'alice'),
                     'key': 'c6d3ad80-...',
                     'value': {'kind': 'Memory', 'content': {'content': 'alice prefers metric units'}}}]
```

### 3.3 ⚠️ The two APIs use DIFFERENT value shapes

This is a real, verified gotcha:

```
>>> FIRST: run the manager over memories written by the TOOL.
    -> KeyError: 'kind'
    -> GOTCHA: the two langmem APIs use DIFFERENT value shapes:
         manage_memory tool writes : {'content': '...'}
         the manager expects         : {'kind': ..., 'content': ...}
       If you mix them in one namespace, the manager crashes.
       Pick ONE shape and use it everywhere.
```

**Rule:** standardise your memory value shape yourself. Recommended:

```python
{"kind": "fact" | "preference" | "procedure", "content": "..."}
```

Then either write it yourself with `store.put(...)`, or use the manager
consistently.

### 3.4 The manager's tool contract

The manager uses `trustcall` (strict structured calling). The tool names are:

| Tool | Purpose |
|---|---|
| `Memory` | create a new memory |
| `PatchDoc` | update / delete an existing memory |
| `PatchFunctionErrors` | fix a malformed call |

With a real model it handles this for you. If you ever see:

```
Unrecognized function call memories
```

…your model called the wrong tool name. The valid names are the three above.

### 3.5 Hot path vs background

| | Hot path (inline) | Background |
|---|---|---|
| Where it runs | inside the request handler | a task / worker / queue |
| Latency | +LLM call on every request | ~0 |
| Freshness | immediate | eventual |
| Failure handling | the request fails | retry in the worker |
| Complexity | simple | needs a queue |

**Hot path:**

```python
await manager.ainvoke({"messages": messages}, config=config)
```

**Background:**

```python
asyncio.create_task(manager.ainvoke({"messages": messages}, config=config))
# or, properly: a Celery / arq / K8s job, with retries and a dead-letter queue
```

**Practical default:** run extraction in the **background**; let the agent
**read** memories at the start of the next turn. Users don't notice a memory
that arrives 2 seconds late, but they *do* notice a 2-second latency on every
message.

---

## 4. Memory design

### 4.1 Three kinds of memory

| Kind | Example | Changes? | Scope |
|---|---|---|---|
| **Fact** | "works at Acme Corp", "email is a@b.com" | rarely | personal |
| **Preference** | "prefers metric units", "dark mode" | rarely | personal |
| **Procedure** | "always check the CRM before quoting a price" | rarely | **global** (not user-specific) |

**Give every memory a `kind` field.** It lets you:

- filter recall by kind,
- resolve conflicts by kind (a new *fact* supersedes an old fact; a new
  *preference* **replaces** the old preference),
- expire procedures separately from facts,
- keep procedures in a **shared** namespace and facts in a **user** namespace.

### 4.2 What to store vs what to re-derive

| ✅ Store | ❌ Don't store |
|---|---|
| preferences | the conversation transcript (→ checkpoint) |
| stable facts about the user | document contents (→ your vector store) |
| procedures / policies | anything recomputable from the current request |
| decisions the user asked you to remember | temporary scratch data |
| corrections the user made | tool outputs (→ context editing) |

> **Rule of thumb:** if re-deriving it costs one extra tool call, re-derive
> it. Storage is not free — it costs tokens to recall, money to write, and
> correctness risk when it's stale.

### 4.3 Conflicting memories

"Actually, use imperial units now" must **replace** "prefers metric units",
not sit next to it.

The manager handles this: it searches the store first, sees the existing
memory, and emits a `PatchDoc` instead of a duplicate. Verified:

```
E. Conflicting memories
   alice's memories now:
     mem-pref: {'kind': 'preference', 'content': 'prefers metric units'}
     ...
   -> With a real model the manager SEEES the existing memories
      (it searches the store first) and emits a PATCH instead of a
      duplicate, so you get one row per fact, not a pile of rows.
```

If you build your own extraction, you must implement this yourself:
**search before insert, update when the new value supersedes the old.**

### 4.4 Memory hygiene

| Practice | Why |
|---|---|
| Store a `source` (which thread/turn it came from) | you can trace and correct it |
| Store a `confidence` for inferred memories | the agent can hedge |
| Include a timestamp | "what did we know on day 1?" |
| Cap the number of memories per user | unbounded memory = unbounded tokens |
| Provide a way to forget | L22 |

---

## 5. Do you even need langmem?

The Store API alone is enough for many systems:

```python
store.put(("users", user_id, "memories"), "pref-1", {"content": "..."})
```

langmem adds the **LLM-driven extraction** on top. If you want:

| You want | Use |
|---|---|
| The agent to decide what to remember (explicit, auditable) | `create_manage_memory_tool` |
| Automatic extraction from conversations | `create_memory_store_manager` |
| Full control, no LLM in the loop | the raw Store API |
| Zero extra dependencies | the raw Store API |

Since langmem is pre-1.0, **a good default is: raw Store API now, langmem
behind a thin interface you can swap later.**

---

## 6. Common mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| `from langgraph.store import PostgresStore` | `ImportError` | `from langgraph.store.postgres import PostgresStore` |
| Forgetting `store.setup()` | missing tables | call it at boot |
| No pgvector | semantic search fails | install the extension |
| `dims` ≠ model output size | dimension mismatch at query time | match them |
| Changing the embedding model later | garbage search results | re-index, or version your namespace |
| Mixing langmem value shapes | `KeyError: 'kind'` | standardise the shape |
| Storing everything | token blowup, stale facts | curate |
| No `kind` field | can't resolve conflicts | add it |

---

## 7. Checkpoint yourself

- [ ] I can state the difference between a checkpointer and a store in one
      sentence each.
- [ ] I know namespaces are prefixes and the order matters.
- [ ] I can call `get_store()` from inside a node.
- [ ] I know the pgvector requirement and the `dims` rule.
- [ ] I can explain the two langmem value shapes and the `KeyError: 'kind'`.
- [ ] I can name the three memory kinds and where procedures belong.

**Next → [L22: Multi-tenant memory & data lifecycle](./L22-multi-tenant-and-data-lifecycle.md)**
