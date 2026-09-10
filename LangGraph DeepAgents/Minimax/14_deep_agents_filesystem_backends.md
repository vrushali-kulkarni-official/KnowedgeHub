# Module 14 — Deep Agents: File System & Backends

## Prerequisites

- Module 13 (you have a subagent-using Deep Agent)

## Why this module matters

The virtual file system is Deep Agents' answer to "where do I put all this data?" Stuffing large artifacts into messages blows up your context. Files don't — they're referenced by path and loaded on demand.

For a SaaS, the backend choice also defines **where your users' data lives**.

## Learning objectives

By the end of this module you can:

1. Explain why a virtual file system is the right abstraction.
2. Use the built-in `ls`, `read_file`, `write_file`, `edit_file` tools.
3. Choose the right backend: `StateBackend`, `FilesystemBackend`, `StoreBackend`, `CompositeBackend`.
4. Implement a custom backend (S3, MinIO, your own).
5. Implement per-user/per-thread isolation.
6. Handle large files and binary data.

---

## 14.1 The file system primitives

A Deep Agent has four file system tools by default:

- `ls(path)` — list files in a directory.
- `read_file(path, offset, limit)` — read a file (with optional paging).
- `write_file(path, content)` — write/overwrite a file.
- `edit_file(path, old_string, new_string)` — string replace in a file.

The model uses these like a developer uses a shell. It can:

- Write notes to `/notes/findings.md`.
- Read them back later.
- Edit them as it learns more.
- Save final outputs to `/output/`.

The state has a `files: dict[str, str]` channel that holds the current file tree.

---

## 14.2 Why a virtual file system?

Three reasons:

1. **Context budget:** loading a 5000-line file into messages eats your context window. The model can read it on demand, in chunks.
2. **Persistence:** files are part of the checkpointed state. They survive across turns, across resumes, across server restarts.
3. **Collaboration:** parent + subagents share the same file system. Artifacts are first-class shared state.

It's not just a convenience — it's a structural scaling tool.

---

## 14.3 The four built-in backends

### 14.3.1 `StateBackend` (in-state, default)

Files live in the agent's state (`files` channel). Persisted via the checkpointer.

```python
from deepagents.backends import StateBackend

agent = create_deep_agent(
    model=...,
    backend=StateBackend(),
)
```

**Use when:** dev, tests, small files.
**Don't use when:** production with multi-GB data.

### 14.3.2 `FilesystemBackend` (real disk)

Files live in a directory on disk.

```python
from deepagents.backends import FilesystemBackend

agent = create_deep_agent(
    model=...,
    backend=FilesystemBackend(root_dir="/var/lib/ai-saas/agent-files"),
)
```

**Use when:** local single-server deployment, large files.
**Don't use when:** multi-replica (each replica has its own disk).

### 14.3.3 `StoreBackend` (cross-thread store)

Uses LangGraph's `BaseStore` (from Module 05) — typically Postgres-backed.

```python
from deepagents.backends import StoreBackend
from langgraph.store.postgres import PostgresStore

store = PostgresStore.from_conn_string(DB_URI)
agent = create_deep_agent(
    model=...,
    backend=StoreBackend(store=store),
    checkpointer=...,
)
```

**Use when:** production, multi-replica, want cross-thread persistence.
**This is the right choice for your SaaS.**

### 14.3.4 `CompositeBackend` (mix)

Different paths → different backends. E.g.:

- `/scratch/` → StateBackend (in-memory, ephemeral).
- `/artifacts/` → StoreBackend (persistent, cross-thread).
- `/uploads/` → FilesystemBackend (or S3).

```python
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend

agent = create_deep_agent(
    model=...,
    backend=CompositeBackend(
        default=StoreBackend(store=store),
        routes={
            "/scratch/": StateBackend(),
            "/artifacts/": StoreBackend(store=store),
        },
    ),
)
```

Powerful for the "ephemeral working memory vs persistent user artifacts" pattern.

---

## 14.4 Custom backends

A backend is an object with methods:

```python
class Backend(Protocol):
    def ls(self, path: str) -> list[str]: ...
    def read(self, path: str, offset: int = 0, limit: int = 2000) -> str: ...
    def write(self, path: str, content: str) -> str: ...
    def edit(self, path: str, old: str, new: str) -> str: ...
    def exists(self, path: str) -> bool: ...
```

Implement your own. Common cases:

- **S3 / MinIO backend:** for blob storage.
- **Database backend:** for files stored in Postgres as `BYTEA` or in a separate table.
- **Git backend:** for versioned agent artifacts.

```python
# app/backends/s3.py
import boto3
from deepagents.backends.protocol import Backend

class S3Backend(Backend):
    def __init__(self, bucket: str, prefix: str, s3_client=None):
        self.bucket = bucket
        self.prefix = prefix
        self.s3 = s3_client or boto3.client("s3")

    def _key(self, path):
        return f"{self.prefix}{path}"

    def read(self, path, offset=0, limit=2000):
        obj = self.s3.get_object(Bucket=self.bucket, Key=self._key(path))
        content = obj["Body"].read().decode()
        return "\n".join(content.splitlines()[offset:offset+limit])

    def write(self, path, content):
        self.s3.put_object(Bucket=self.bucket, Key=self._key(path), Body=content.encode())
        return f"Wrote {len(content)} bytes to {path}"

    def ls(self, path):
        # list keys with prefix
        ...
```

For MinIO (S3-compatible, FOSS), just point `boto3` at your MinIO endpoint.

---

## 14.5 Per-user / per-thread isolation

**Critical for SaaS:** user A must not see user B's files.

Two approaches:

### 14.5.1 Namespace the paths

The backend prefixes all paths with the user/thread ID.

```python
class NamespacedBackend(Backend):
    def __init__(self, inner: Backend, user_id: str, thread_id: str):
        self.inner = inner
        self.prefix = f"/{user_id}/{thread_id}"

    def read(self, path, **kwargs):
        return self.inner.read(self.prefix + path, **kwargs)
    # etc.
```

Pass it via the agent's `config`:

```python
def get_backend(config):
    user_id = config["configurable"]["user_id"]
    thread_id = config["configurable"]["thread_id"]
    return NamespacedBackend(StoreBackend(store=store), user_id, thread_id)
```

### 14.5.2 Use the Store's native namespacing

`PostgresStore` already supports tuples as namespaces. Encode user/thread:

```python
namespace = ("files", user_id, thread_id)
store.put(namespace, "/notes/x.md", {"content": "..."})
```

Cleaner if your backend supports it.

---

## 14.6 Large files and binary data

The file tools work with strings. For binary:

- **Option A:** Base64-encode binary into the string. Painful for large files.
- **Option B:** Store references (URLs, S3 keys) in the file system; the actual blob lives elsewhere.
- **Option C:** Use a dedicated file upload tool that bypasses the model and writes to S3 directly.

For most SaaS agents, option B is the right answer:

```python
@tool
def upload_file(file_path: str) -> str:
    """Upload a local file to blob storage; return its URL."""
    url = s3.upload(file_path)
    return f"Uploaded to {url}. Reference: file://{url}"
```

The agent gets back a URL, not the file content.

---

## 14.7 Paging and reading strategy

`read_file(path, offset, limit)` lets the model read in chunks. This is critical for long files.

Prompt the model to use it:

```
For files over 1000 lines, ALWAYS read in chunks of 500 lines at a time.
Start with offset=0, limit=500. Then continue with offset=500, limit=500.
Don't try to read the whole file at once.
```

In your backend, implement paging properly:

```python
def read(self, path, offset=0, limit=2000):
    content = self._read_full(path)
    lines = content.splitlines()
    return "\n".join(lines[offset:offset+limit])
```

---

## 14.8 File system patterns

### 14.8.1 Pattern: scratch + output

```
/scratch/    # working memory, may be deleted
/output/     # final artifacts, persisted
```

Use `CompositeBackend` to route differently.

### 14.8.2 Pattern: shared whiteboard

Subagents write to `/shared/`. The parent reads it.

```python
# In researcher subagent:
write_file("/shared/research.md", "...")

# In parent:
read_file("/shared/research.md")
```

### 14.8.3 Pattern: versioned artifacts

Save outputs with timestamps:

```python
ts = datetime.now().isoformat()
write_file(f"/output/report-{ts}.md", content)
```

Allows audit and rollback.

---

## 14.9 The file system in production

For your SaaS:

| Path | Backend | Lifetime |
|---|---|---|
| `/scratch/` | StateBackend | Per thread, ephemeral |
| `/user/{user_id}/uploads/` | S3/MinIO | Persistent, per user |
| `/user/{user_id}/artifacts/` | StoreBackend | Persistent, per user |
| `/shared/{thread_id}/` | StoreBackend (namespaced) | Per thread |

Each backend has a clear ownership and lifetime.

---

## 14.10 The `files` channel in state

`state["files"]` is a dict: `path -> content`. Persisted by the checkpointer. Inspectable in the UI.

```python
result = agent.invoke({"messages": [...]})
for path, content in result["files"].items():
    print(f"--- {path} ---")
    print(content[:500])
```

Stream it:

```python
async for event in agent.astream(..., stream_mode="values"):
    if "files" in event:
        render_file_tree(event["files"])
```

You can build a "file tree" sidebar in the UI that updates as the agent works.

---

## 14.11 Common file system pitfalls

| Pitfall | Fix |
|---|---|
| Agent reads huge file in one go | Prompt: read in chunks |
| Files not isolated per user | Namespacing |
| Files lost on restart | Use a persistent backend (Store/S3) |
| State blowing up with file content | StateBackend for small files, external for large |
| Agent edits same file concurrently | Lock or sequence (rare in practice) |
| Binary data in files | Use references, not content |

---

## Hands-on project

**Goal:** Build a Deep Agent with production-grade file isolation.

1. Set up a `PostgresStore` for files.
2. Implement a `CompositeBackend`: `/scratch/` → StateBackend, `/artifacts/` → StoreBackend.
3. Implement a per-user/per-thread namespace.
4. Define a `S3Backend` for `/uploads/` (use MinIO via Docker).
5. Build an agent that:
   - Reads a user-provided PDF (reference from `/uploads/`).
   - Writes analysis to `/artifacts/analysis.md`.
   - Uses `/scratch/` for working notes.
6. Test: two users, two threads — verify isolation.

## Exercises

1. **Backend swap:** run the same agent with `StateBackend` and `StoreBackend`. Compare persistence behavior.
2. **Large file test:** write a 10,000-line file. Have the agent read it. Verify it uses paging.
3. **MinIO backend:** implement a `MinIOBackend` using `boto3`. Run an agent that uploads/downloads a file.
4. **Cross-thread memory:** in thread A, save to `/artifacts/`. In thread B, read it. Verify it works.
5. **File tree UI:** stream `files` and build a simple file-tree visualization.

## Production checklist

- [ ] Backend chosen: `StoreBackend` (Postgres) or `S3Backend` (MinIO/S3).
- [ ] Per-user/per-thread isolation enforced.
- [ ] Large file strategy (chunked reads, references for binaries).
- [ ] File TTL / cleanup for `/scratch/`.
- [ ] File tree visible in UI.
- [ ] Audit: which files were created/modified, by which user, when.

## Key takeaways

- Virtual file system = context-budget-safe persistent scratchpad.
- Four backends: `State`, `Filesystem`, `Store`, `Composite`. Use `Store` or S3 in production.
- Custom backends (S3/MinIO) are easy to write.
- Namespace paths by user/thread. Non-negotiable for SaaS.
- For large files, prompt chunked reads; for binaries, use references.

## Resources

- Deep Agents backends: see the library's `backends/` directory.
- LangChain `BaseStore`: https://langchain-ai.github.io/langgraph/reference/store/
- MinIO: https://min.io/ (FOSS S3 alternative, perfect for your Docker stack).
