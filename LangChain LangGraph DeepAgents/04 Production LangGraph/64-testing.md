# M64 — Testing graphs

**Time: 3 hours.** The goal: be able to change a prompt on a Friday afternoon
and *know* — before deploying — that the agent still works.

---

## 1. Why agent testing is different

A normal function is deterministic: same input, same output. So you assert on
outputs.

An agent is not. It calls a model, which is non-deterministic. So:

> **A test that depends on model output is not testing your code. It is
> testing the model's mood.**

The entire strategy of this module follows from that one rule: **inject a
deterministic fake model, and assert on everything else** — which nodes ran,
what state resulted, what events were emitted.

The second rule: **test the graph, not the prompt.** A prompt is a business
decision you will change often. If your test asserts on the exact wording of
the model's answer, every prompt tweak breaks CI, and the team learns to
ignore red builds. Assert on *structure* instead.

---

## 2. The fake model

Everything starts here. `src/p9/models.py`:

```python
class ScriptedChatModel(BaseChatModel):
    turns: list[dict[str, Any]] = []
    tokenize: bool = True
    _call_counter: int = 0

    def bind_tools(self, tools, **kwargs):
        """Accept (and ignore) tool bindings - the script already knows."""
        return self

    def _pick_turn(self) -> dict[str, Any]:
        if not self.turns:
            return {"content": ""}
        idx = min(self._call_counter, len(self.turns) - 1)
        self._call_counter += 1
        return self.turns[idx]
```

`turns` is a **script**: each element describes one model call.

```python
scripted_model("Hello.")                                  # always this
ScriptedChatModel(turns=[
    {"content": "", "tool_calls": [{"name": "task", "args": {...}}]},
    {"content": "The ingest queue backs up when the partitioner stalls."},
])
```

The index is clamped to the last turn, so you never have to count calls.

### 2.1 Two implementation traps

**Trap 1: `_stream` must yield `ChatGenerationChunk`, not `AIMessageChunk`.**

```python
# WRONG - explodes deep inside langchain_core with a baffling message:
#   AttributeError: 'AIMessageChunk' object has no attribute 'generation_info'
def _stream(self, messages, stop=None, run_manager=None, **kwargs):
    yield AIMessageChunk(content="hello")

# RIGHT
def _stream(self, messages, stop=None, run_manager=None, **kwargs):
    yield ChatGenerationChunk(message=AIMessageChunk(content="hello"))
```

**Trap 2: agents call `bind_tools`.** If your fake does not implement it,
every agent test dies with a bare `NotImplementedError` from
`BaseChatModel.bind_tools`. Returning `self` is enough when the script is
fixed.

### 2.2 Tool calls in the fake

```python
yield ChatGenerationChunk(
    message=AIMessageChunk(
        content="",
        tool_call_chunks=[{
            "name": call["name"],
            "args": json.dumps(call["args"]),
            "id": call["id"],
            "index": 0,
        }],
    )
)
```

`tool_call_chunks` (not `tool_calls`) is what the streaming path expects, and
it is what makes tool calls appear in the `messages` stream mode.

Verified — this fake drives a real Deep Agents graph:

```
  [human] Why is the ingest backlog growing?
  [ai]    | tool_calls: [{'name': 'task', 'args': {'description': 'Research the ingest backlog problem', ...}}]
  [tool]  The ingest queue backs up when the partitioner stalls.
  [ai]    The ingest queue backs up when the partitioner stalls.
```

---

## 3. Three styles of graph test

### 3.1 Step assertions — "which node ran?"

The `updates` stream tells you which node produced which delta.

```python
async def test_step_assertions(support_graph, thread_config):
    steps: list[str] = []
    async for part in support_graph.astream(
        {"topic": "ingest backlog"},
        config=thread_config,
        stream_mode="updates",
        version="v2",
    ):
        steps.extend(part["data"].keys())

    assert "route" in steps
    assert "tools" in steps
    assert "__interrupt__" in steps      # <- note: not "approval"
    assert steps.index("route") < steps.index("tools") < steps.index("__interrupt__")
```

> **The pause shows up as `__interrupt__`, not as the node's name.** LangGraph
> uses a magic key. If you assert `"approval" in steps` you will be surprised.

### 3.2 State snapshots — "what does the state look like?"

```python
async def test_state_snapshot_after_pause(support_graph, thread_config):
    async for _ in support_graph.astream({"topic": "ingest backlog"}, config=thread_config):
        pass

    snapshot = support_graph.get_state(thread_config)
    assert snapshot.next == ("approval",)         # paused AT this node
    assert snapshot.values["answer"]
    assert snapshot.values["artifacts"] == []
    assert snapshot.interrupts[0].value["question"].startswith("Publish the answer")
```

Useful members of a `StateSnapshot`:

| Member | What it tells you |
|---|---|
| `.values` | The current state |
| `.next` | The node(s) that will run next — **non-empty means paused** |
| `.interrupts` | The pending interrupt payloads |
| `.config` | The config, including `checkpoint_id` |
| `.metadata` | Step number, source, writes |

And `get_state_history(config)` gives you the full checkpoint history — time
travel for free.

### 3.3 Reducer tests — "does the state merge correctly?"

Reducers are pure functions, so they are the easiest thing in LangGraph to
test exhaustively.

```python
def test_add_messages_reducer_appends_and_dedupes():
    from langgraph.graph.message import add_messages as reducer

    a = AIMessage(content="first", id="m1")
    b = AIMessage(content="second", id="m2")
    assert reducer([a], [b]) == [a, b]

    # Same id -> replaced in place.
    a_updated = AIMessage(content="first (edited)", id="m1")
    result = reducer([a, b], [a_updated])
    assert len(result) == 2
    assert result[0].content == "first (edited)"
```

### 3.4 The reducer bug you must know about

Two parallel branches writing to the same channel:

```python
class State(TypedDict, total=False):
    items: Annotated[list[str], operator.add]   # <- reducer
```

→ both survive. ✅

```python
class State(TypedDict, total=False):
    items: list[str]                              # <- no reducer
```

→ **LangGraph raises**, it does not silently drop data:

```
langgraph.errors.InvalidUpdateError:
  At key 'items': Can receive only one value per step.
  Use an Annotated key to handle multiple values.
```

This is good news: the failure is loud, at runtime, with a message that tells
you the fix. Your test should assert on it:

```python
with pytest.raises(InvalidUpdateError, match="only one value per step"):
    graph.invoke({"items": []})
```

If you are migrating an older codebase that *was* silently losing data, this
test is your canary.

---

## 4. Testing interrupt / resume

This is the trickiest flow, because it spans **two** graph invocations.

```python
async def test_resume_with_command_completes_the_graph(support_graph, thread_config):
    await support_graph.ainvoke({"topic": "ingest backlog"}, config=thread_config)

    # 1. The graph is paused.
    snapshot = support_graph.get_state(thread_config)
    assert snapshot.next == ("approval",)

    # 2. Resume with the SAME thread_id.
    resumed = await support_graph.ainvoke(Command(resume="approve"), config=thread_config)

    # 3. Assert the answer was applied.
    assert resumed["approved"] is True
    assert resumed["artifacts"]
    assert support_graph.get_state(thread_config).next == ()
```

### 4.1 The failure mode worth testing explicitly

What happens if you resume on a *different* thread?

```python
async def test_resume_requires_the_same_thread_id(support_graph, thread_config):
    await support_graph.ainvoke({"topic": "ingest backlog"}, config=thread_config)

    other = {"configurable": {"thread_id": "a-different-thread"}}
    resumed = await support_graph.ainvoke(Command(resume="approve"), config=other)

    # It did NOT resume; it started fresh and paused again.
    assert "__interrupt__" in resumed
    assert "approved" not in resumed
```

Documenting the failure mode in a test is worth it: when it breaks in
production, you will know exactly why.

### 4.2 Testing that state survives a restart

```python
async def test_checkpoint_survives_a_rebuild(support_graph, thread_config):
    await support_graph.ainvoke({"topic": "ingest backlog"}, config=thread_config)

    # Simulate a restart: brand-new graph object, same checkpointer.
    rebuilt = build_support_graph(
        model=scripted_model("fresh process, same state"),
        checkpointer=support_graph.checkpointer,
    )
    snapshot = rebuilt.get_state(thread_config)
    assert snapshot.next == ("approval",)
    assert snapshot.values["answer"]
```

---

## 5. Async vs sync: pick one and be consistent

If any node in your graph is `async def`, the graph **must** be driven with
the async API:

```python
await graph.ainvoke(payload, config)
async for part in graph.astream(payload, config): ...
```

Calling the sync API on a graph with an async node gives:

```
TypeError: No synchronous function provided to "route".
Either initialize with a synchronous function or invoke via the async API
(ainvoke, astream, etc.)
```

This is a good habit: **write async nodes, test async.** Your production
runtime (FastAPI + workers) is async end to end, so nothing has to be
translated.

In pytest:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
```

`asyncio_mode = "auto"` means you write `async def test_...` and pytest-asyncio
handles the loop.

---

## 6. The in-memory checkpointer lies to you

`InMemorySaver` is perfect for testing graph *logic*. But it cannot tell you
whether your persistence actually works:

* it never serialises to a real database → **a non-JSON-serialisable state
  value passes in tests and explodes in production**;
* it has no transactions → the Postgres checkpointer's locking semantics are
  never exercised;
* durability modes behave differently;
* concurrent writes from parallel tasks are not really tested.

> **The rule: logic tests in memory, persistence tests in a real database.**

---

## 7. Real Postgres with testcontainers

`testcontainers-python` starts a throwaway Postgres for the test session and
tears it down afterwards.

```python
import pytest

def _docker_available() -> bool:
    try:
        import docker
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False

pytestmark = pytest.mark.docker

@pytest.fixture(scope="module")
def postgres_uri():
    if not _docker_available():
        pytest.skip("Docker is not available - skipping the Postgres checkpointer tests")

    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="psycopg") as pg:
        yield pg.get_connection_url()
```

> ### ⚠️ `testcontainers.postgres` is deprecated
>
> On testcontainers 4.15.0 you get:
>
> ```
> DeprecationWarning: testcontainers.postgres is deprecated,
> use testcontainers.community.postgres instead
> ```
>
> Use `testcontainers.community.postgres`. Verified on 4.15.0.

The `driver="psycopg"` argument matters: the LangGraph Postgres checkpointer
uses **psycopg 3**, so the URL must be `postgresql+psycopg://`, not
`postgresql://` (which defaults to psycopg2).

### 7.1 The async saver lives in `.aio`

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async with AsyncPostgresSaver.from_conn_string(uri) as saver:
    await saver.setup()
```

> ### ⚠️ `AsyncPostgresSaver` moved
>
> `langgraph.checkpoint.postgres` exports only the **synchronous**
> `PostgresSaver`. The async one lives in
> **`langgraph.checkpoint.postgres.aio`**. Importing it from the top-level
> module raises `ImportError`.

And it must be created **inside a running event loop**, because
`from_conn_string` is an async context manager.

### 7.2 What to test against real Postgres

```python
async def test_postgres_saver_persists_across_graph_instances(postgres_saver):
    thread_id = f"pg-{uuid.uuid4()}"
    config = {"configurable": {"thread_id": thread_id}}

    graph_a = build_support_graph(model=scripted_model("first process"), checkpointer=postgres_saver)
    async for _ in graph_a.astream({"topic": "x"}, config=config):
        pass

    # A completely new compiled graph, same saver.
    graph_b = build_support_graph(model=scripted_model("second process"), checkpointer=postgres_saver)
    snapshot = graph_b.get_state(config)
    assert snapshot.next == ("approval",)
    assert snapshot.values["answer"] == "first process"
```

Plus: resume-after-restart, durability modes, and `aget_tuple` auditing.

### 7.3 In CI

```yaml
# .github/workflows/tests.yml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e ".[dev]"
      # GitHub Actions runners have Docker pre-installed, so testcontainers
      # just works. Mark the Postgres tests as required.
      - run: pytest tests/ -v --cov=src/p9 --cov-report=term-missing
```

GitHub-hosted runners have Docker, so the `docker` marker tests run there.
Locally without Docker they skip. To make them *required* in CI, add:

```toml
# pyproject.toml
[tool.pytest.ini_options]
addopts = "-m 'not docker'"
```

…in a local override, and remove it in CI. Or simply keep them running
everywhere and let the skip happen.

---

## 8. Testing the HTTP layer

FastAPI's `TestClient` runs the ASGI app in a background thread with its own
event loop — so the lifespan (and therefore the worker) really does run.

```python
@pytest.fixture
def client(run_store, fake_model):
    graph = build_support_graph(model=fake_model, checkpointer=InMemorySaver())
    app = create_app(store=run_store, graphs={"support": graph}, start_worker=True)
    with TestClient(app) as c:
        yield c
```

The `with` block is essential: it triggers the lifespan startup/shutdown.

```python
def test_idempotency_key_replays_the_same_run(client):
    headers = {"Idempotency-Key": "abc-123"}
    first = client.post("/runs", json={"topic": "hello"}, headers=headers)
    second = client.post("/runs", json={"topic": "hello"}, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 200
    assert second.headers.get("Idempotent-Replay") == "true"
    assert first.json()["id"] == second.json()["id"]
```

### 8.1 Waiting for a background run

A background run is asynchronous, so tests must wait for it:

```python
def wait_for(client, run_id, statuses, timeout=20.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = client.get(f"/runs/{run_id}").json()
        if last["status"] in statuses:
            return last
        time.sleep(0.1)
    raise TimeoutError(f"run stuck in {last and last['status']!r}")
```

Always give it a timeout. A test that hangs forever in CI is much worse than
a test that fails.

---

## 9. The test pyramid for agents

```
        ╱╲
       ╱  ╲          E2E / online eval     (few, slow, real model, non-deterministic)
      ╱    ╲         - "does the product work?"
     ╱──────╲
    ╱        ╲      Integration            (real checkpointer, fake model)
   ╱          ╲     - "does it persist? resume? cancel?"
  ╱────────────╲
 ╱              ╲   Unit                   (pure functions, reducers, schema)
╱                ╲  - "is the logic right?"
```

| Layer | Model | Checkpointer | Speed | What it protects |
|---|---|---|---|---|
| Unit | fake | none | ms | reducers, state schemas, pure helpers |
| Graph | fake | in-memory | ms | node order, state, interrupts, events |
| Persistence | fake | **real Postgres** | s | serialisation, durability, resume-after-restart |
| API | fake | in-memory | ~s | HTTP contract, idempotency, status codes |
| Online eval | **real Gemini** | real | min | product quality (not correctness) |

Note the split: the last layer is *evaluation*, not *testing*. Evaluation asks
"is this answer good?" — which needs a real model and a human-preference
signal. Testing asks "does this code do what it says?" — which does not.

### 9.1 The line between them

| | Test | Eval |
|---|---|---|
| Deterministic? | Yes | No |
| Blocks a deploy? | Yes | Usually not |
| Uses a real model? | No | Yes |
| Asserts on | structure, state, events | quality, accuracy, tone |
| Lives in | CI, every commit | scheduled, or on release candidates |

Keep them separate. Mixing them gives you a flaky red build that nobody
trusts.

---

## 10. What to assert on

A practical checklist for "what should this test assert?"

| Concern | Assert on |
|---|---|
| Control flow | the **order** of node names in the `updates` stream |
| State | `snapshot.values` / `snapshot.next` |
| HITL | `snapshot.interrupts`, and the state after `Command(resume=...)` |
| Streaming | the **event sequence** from your contract (`test_sse_contract.py`) |
| Contracts | `validate_event()` on every emitted event |
| Persistence | state readable from a *new* graph object |
| HTTP | status codes, headers, idempotency behaviour |
| Errors | the *exception type*, not the message text |

And a few things **not** to assert on:

* The exact wording of the model's answer → assert on structure instead.
* The exact number of tokens → the fake's chunking is an implementation detail.
* Internal node names you plan to refactor → assert on behaviour.

---

## 11. Running the suite

```bash
python -m pytest tests/ -v                     # everything
python -m pytest tests/ -v -m docker           # only the Postgres tests
python -m pytest tests/ -v -k "interrupt"      # by keyword
python -m pytest tests/ --cov=src/p9 --cov-report=term-missing
```

Current state of this course's suite:

```
52 passed, 5 skipped
```

(The 5 skipped are the testcontainers tests — no Docker in the authoring
environment.)

---

## 12. Traps

| Trap | Symptom | Fix |
|---|---|---|
| Fake yields `AIMessageChunk` | `'AIMessageChunk' object has no attribute 'generation_info'` | Yield `ChatGenerationChunk` |
| Fake has no `bind_tools` | `NotImplementedError` in every agent test | Implement `bind_tools` |
| Asserting on the model's wording | Every prompt change breaks CI | Assert on structure |
| Sync `invoke` on an async graph | `No synchronous function provided to "x"` | Use `ainvoke`/`astream` |
| Asserting `"approval" in steps` | Fails — the key is `__interrupt__` | Use `__interrupt__` |
| Only in-memory checkpointer | Non-serialisable state ships to prod | testcontainers for persistence |
| Test has no timeout | CI hangs forever | Always set a deadline |
| `TestClient` not used as a context manager | Lifespan never runs, no worker | `with TestClient(app) as c:` |
| `AsyncPostgresSaver` imported from the top-level module | `ImportError` | `langgraph.checkpoint.postgres.aio` |
| `testcontainers.postgres` | `DeprecationWarning` | `testcontainers.community.postgres` |
| Waiting for a background run with `sleep(5)` | Flaky | Poll with a deadline |

---

## 13. Exercise

1. **Break the fake on purpose.** Change `_stream` to yield `AIMessageChunk`
   and read the error. Then write a test that asserts the fake streams
   `ChatGenerationChunk` — so nobody can regress it.

2. **Add a test for the reducer of your own state.** Then delete the reducer
   and watch `InvalidUpdateError` fire. That test is your canary for a whole
   class of production data-loss bugs.

3. **Write the eval layer.** Take the same fake-model test and swap in a
   real Gemini model. Assert on something fuzzy ("the answer mentions the
   partitioner"). Run it on a schedule, not on every commit. This is the
   boundary between testing and evaluation.

4. **Measure the persistence gap.** Add a state value that is not JSON
   serialisable (a `datetime`, an open file handle). Run the suite with the
   in-memory saver (passes) and with Postgres (fails). That is the bug the
   in-memory saver was hiding.

---

**Next: [M65 — The deployment decision](65-deployment.md) →**
