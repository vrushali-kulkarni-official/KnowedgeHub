# M63 — Long-running graphs

**Time: 3 hours.** This module turns "a function that returns an answer" into
"a **run** that has a lifecycle, survives a restart, and can be stopped".

---

## 1. The shape of the problem

A production agent run has four properties a notebook does not:

```
 pending ──▶ running ──▶ paused ──▶ running ──▶ done
                │           │                       ▲
                │           └───────────────────────┘
                ▼
         failed / cancelled
```

1. **It outlives the request.** The HTTP client may be gone long before the
   run finishes.
2. **It can wait for a human.** For hours, maybe.
3. **It must be stoppable.** "Stop" must mean *now*, not "after the current
   node finishes a 10-minute job".
4. **It must survive a restart.** A deploy should not lose runs.

None of these are LangGraph features. They are *your* features. That is the
central lesson of this module.

---

## 2. The `runs` table — your admission log

### 2.1 Why the checkpointer is not enough

The checkpointer answers "what is the state of thread T?". It does **not**
answer:

- Is this run queued, running, paused, or finished?
- Have I already accepted this request?
- Has the user asked me to stop?
- What did the client already receive?

And the LangGraph docs are explicit about why the first gap cannot be closed
by the checkpointer:

> If you need to distinguish "never accepted" from "accepted but lost", record
> admission outside the checkpointer, for example by committing an outbox row
> to your own store before you call `invoke`.

Before the first checkpoint becomes durable, a thread that was *accepted* and a
thread that was *never invoked* look identical — `get_tuple()` returns `None`
for both. Only a table you own can tell them apart.

### 2.2 The schema

```python
class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_runs_idempotency_key"),
        Index("ix_runs_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=...)
    thread_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    graph_name: Mapped[str] = mapped_column(String(128), nullable=False, default="support")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")

    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    input: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    cancel_requested: Mapped[bool] = mapped_column(default=False, nullable=False)
    cancel_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    interrupt_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    interrupt_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    resume_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    run_metadata: Mapped[str] = mapped_column("metadata", Text, nullable=False, default="{}")

    created_at / updated_at / started_at / finished_at / heartbeat_at
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
```

Four decisions worth defending:

**`idempotency_key` is UNIQUE.** Not indexed — *unique*. The database, not
your application code, guarantees that a retry maps to the same run. A
`SELECT`-then-`INSERT` check has a race; a unique constraint does not.

**`cancel_requested` is separate from `status`.** Cancellation is a
*request*; only the worker knows when it is safe to stop. Conflating them
means either cancelling a run that is not running, or ignoring a cancel
because the run is in a transient state.

**`resume_value` carries the human's answer.** The answer is data in your
table, not a parameter on a function call that might be lost.

**`run_metadata` is named `run_metadata` in Python but `metadata` in SQL.**
`metadata` is reserved by SQLAlchemy's declarative base (`Base.metadata` is
the `MetaData` object). Using it as an attribute name raises a `SAWarning`
and can shadow framework internals. The column keeps its natural name; the
attribute does not.

### 2.3 Status transitions are a state machine

```python
ALLOWED_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.PENDING: {RunStatus.RUNNING, RunStatus.CANCELLED, RunStatus.FAILED},
    RunStatus.RUNNING: {RunStatus.PAUSED, RunStatus.DONE, RunStatus.FAILED, RunStatus.CANCELLED},
    RunStatus.PAUSED:  {RunStatus.RUNNING, RunStatus.CANCELLED, RunStatus.FAILED},
    RunStatus.DONE:    set(),
    RunStatus.FAILED:  set(),
    RunStatus.CANCELLED: set(),
}
```

And every transition is a **compare-and-set**:

```python
def _transition(self, run_id, target, *, expected, updates=None) -> bool:
    run = session.get(Run, run_id)
    if run is None: return False
    current = RunStatus(run.status)
    if current not in expected: return False
    if target not in ALLOWED_TRANSITIONS.get(current, set()): return False
    run.status = target.value
    ...
    session.commit()
    return True
```

If two workers race, one gets `True` and the other `False`. No locks held
across the (minutes-long) graph execution.

### 2.4 Claiming a run

```python
def claim_next_pending(self) -> RunView | None:
    dialect = self.engine.dialect.name
    if dialect == "postgresql":
        stmt = (select(Run)
                .where(Run.status == RunStatus.PENDING.value)
                .order_by(Run.created_at)
                .with_for_update(skip_locked=True)
                .limit(1))
        run = session.execute(stmt).scalar_one_or_none()
        ...
    else:
        # portable path (SQLite): UPDATE ... WHERE status = 'pending'
```

`FOR UPDATE SKIP LOCKED` is the PostgreSQL idiom for "give me a row nobody
else is working on, without blocking". Two workers never see the same run
and never wait for each other. SQLite has no `SKIP LOCKED`, so the portable
path uses a conditional `UPDATE` — which is safe for the single-process dev
worker it is meant for.

---

## 3. The worker

The worker is small. The hard parts are what it *manages*.

```python
async def run_forever(self) -> None:
    while not self._stop.is_set():
        run = await self.store.claim_next_pending()
        if run is None:
            await asyncio.wait_for(self._stop.wait(), timeout=self.config.poll_interval)
            continue
        async with self._semaphore:
            task = asyncio.create_task(self._execute(run))
            self._tasks[run.id] = task
            try:
                await task
            except asyncio.CancelledError:
                ...
```

### 3.1 Executing one run

```python
payload = json.loads(run.input or "{}")
config = {"configurable": {"thread_id": run.thread_id}}
control = RunControl()
translator = StreamTranslator(run_id=run.id, thread_id=run.thread_id)

graph_input = payload
if run.resume_value is not None:
    graph_input = Command(resume=json.loads(run.resume_value))

cancel_watcher = asyncio.create_task(self._watch_for_cancel(run.id, control))
try:
    async for part in graph.astream(
        graph_input, config=config,
        stream_mode=["messages", "updates", "custom", "values"],
        version="v2", subgraphs=True, control=control,
    ):
        # `values` is captured but NOT forwarded: it is the whole state,
        # every step. The client gets `updates`.
        if part.get("type") == "values":
            final_state = part["data"]
            continue

        for event in translator.translate_part(part):
            await self.store.append_event(run.id, event["seq"], event["event"], json.dumps(event["data"]))

        if part.get("type") == "updates" and "__interrupt__" in (part.get("data") or {}):
            await self.store.mark_paused(run.id, interrupt.id, json.dumps(interrupt.value))
            await self.store.append_event(run.id, translator.next_seq(), "done", json.dumps({"status": "paused"}))
            return

    await self.store.mark_done(run.id, json.dumps(final_state, default=str))
except GraphDrained as exc:
    await self.store.mark_cancelled(run.id, f"drained: {exc}")
```

Four things to notice:

1. **The worker never runs the graph in the HTTP request.** The API writes a
   row and returns. Graph execution belongs in the worker, so a slow graph
   cannot exhaust your web tier.
2. **`values` is captured but filtered out** of the event stream.
3. **A pause is not a completion.** The run goes to `paused` and the event log
   gets a `done` event with status `paused` — so the client's stream closes
   cleanly and it knows to wait for a human.
4. **The resume uses the same `thread_id`**, so the checkpointer replays the
   graph up to the interrupt and continues.

### 3.2 The event log is durable

```python
class RunEvent(Base):
    __tablename__ = "run_events"
    __table_args__ = (Index("ix_run_events_run_seq", "run_id", "seq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event: Mapped[str] = mapped_column(String(32), nullable=False)
    data: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
```

Why persist events instead of keeping them in memory?

* A client that connects late (or reconnects) can **replay** from the last
  sequence number it saw.
* A crashed worker's output is **not lost**.
* You can inspect what the user actually received.

At scale you add Redis pub/sub *on top* of this table for live fan-out —
that is exactly what the Agent Server does. The table stays the source of
truth.

---

## 4. Cancellation — two flavours, and the difference matters

This is the part people get wrong. There are two ways to stop a run.

### 4.1 `drain` — cooperative, resumable (**use this**)

```python
from langgraph.runtime import RunControl
from langgraph.errors import GraphDrained

control = RunControl()
# from any thread:
control.request_drain("user pressed stop")

try:
    result = graph.invoke(inputs, config, control=control)
except GraphDrained as e:
    print(f"Drained: {e.reason}")
    # a resumable checkpoint exists
```

Requires **LangGraph ≥ 1.2**. The semantics, from the docs:

| Scenario | Behaviour |
|---|---|
| Node mid-execution | Runs to completion. Drain takes effect on the next superstep. |
| Node retrying | The retry loop runs to exhaustion or success. Drain takes effect after. |
| Graph finishes naturally on the same tick as the drain | Returns normally. Check `control.drain_requested`. |
| More supersteps remain | Raises `GraphDrained(reason)`. Checkpoint is saved and resumable. |
| Subgraph requests drain | `GraphDrained` bubbles up and stops the parent at its next boundary. |

Resume a drained run:

```python
result = graph.invoke(None, config)   # same thread_id
```

**The key property: the work already done is not thrown away.**

### 4.2 `abort` — hard kill

Cancel the asyncio task outright. The node is interrupted mid-flight. Faster,
but the last checkpoint may be unusable and the run is not cleanly resumable.

### 4.3 The decision

> Always prefer `drain` unless you have a specific reason not to.
> Draining preserves work; aborting destroys it.

Our worker supports both:

```python
@dataclass
class WorkerConfig:
    cancel_mode: str = "drain"   # or "abort"
```

### 4.4 Watching for the request

```python
async def _watch_for_cancel(self, run_id: str, control: RunControl) -> None:
    while True:
        try:
            await asyncio.sleep(self.config.cancel_poll_interval)
            run = await self.store.get_run(run_id)
            if run is None:
                return
            if not run.cancel_requested:
                continue
            if self.config.cancel_mode == "abort":
                self.request_abort(run_id)
            else:
                control.request_drain(run.cancel_reason or "cancel requested")
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("cancel watcher failed for run %s", run_id)
```

> ### 🐛 The bug that cost us an afternoon
>
> Look at that `except Exception` clause. It is not decoration — it is the
> fix for a bug that shipped in the first version of this worker:
>
> ```python
> # THE BUG
> run = await self.store.get_run(run_id)
> if run.cancel_requested:
>     control.request_drain(run.cancel_reason or "cancel requested")
> ```
>
> `RunView` had no `cancel_reason` attribute. So the moment the watcher found
> a cancel request, it raised `AttributeError` **and died**.
>
> And a background asyncio task that raises is **silently swallowed**. The
> exception is only reported when the task object is garbage-collected, which
> can be minutes later, in a place nobody is looking.
>
> The symptom was beautifully confusing:
>
> * The API returned `200` for `POST /runs/{id}/cancel`.
> * The database showed `cancel_requested = true`.
> * The run **kept going** and finished normally.
> * Nothing was logged.
>
> *Why it is so hard to find:* the failure happened **only on the code path
> that mattered**. Every other poll succeeded. The watcher worked perfectly
> until the exact moment it had something to do — and then it died.
>
> Two lessons, both now enforced in the code:
>
> 1. **A background task must never die quietly.** Catch everything, log it,
>    keep going.
> 2. **Test the unhappy path of your watcher.** A test that only checks
>    "cancel when nothing is happening" would have passed.

### 4.5 The second bug: the event loop starvation

We hit a second, sneakier one immediately afterwards. The cancellation still
did not work.

The cause: **`RunStore` was synchronous**, and the worker called it directly
from `async def`:

```python
# BEFORE - blocks the event loop
run = self.store.get_run(run_id)
```

A synchronous database call inside `async def` blocks the **entire event
loop** for the duration of the query. In a worker that also runs graphs, that
means:

* the cancellation watcher cannot poll → cancels are ignored,
* other runs on the same worker stall,
* if the loop is shared with FastAPI → **the whole HTTP server** stalls.

On SQLite it is worse: a write-lock wait (the driver waits up to 5 s by
default) freezes the whole process.

**The fix** is an async facade that hands every synchronous call to a worker
thread:

```python
class AsyncRunStore:
    async def get_run(self, run_id: str) -> RunView | None:
        return await asyncio.to_thread(self._store.get_run, run_id)
```

At scale you would instead use SQLAlchemy's async engine:

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
engine = create_async_engine("postgresql+psycopg://...")
```

with `asyncpg` / `psycopg` (async) / `aiosqlite`. That is the better answer at
scale: no thread-pool hop, real connection pooling, native cancellation.

The lesson generalises far beyond this course:

> **In an async application, the database call is the thing most likely to
> block you. Audit every `session.execute()` reachable from an `async def`.**

---

## 5. Idempotency

A client retries `POST /runs` because the network timed out. Or a webhook is
delivered twice. Or a user double-clicks.

Without idempotency you get two runs, two LLM bills, and two answers in the
UI.

```python
def create_run(self, *, thread_id, graph_name, payload, idempotency_key, metadata):
    with self._sessionmaker() as session:
        if idempotency_key:
            existing = session.execute(
                select(Run).where(Run.idempotency_key == idempotency_key)
            ).scalar_one_or_none()
            if existing is not None:
                return RunView.of(existing), False

        run = Run(...)
        session.add(run)
        try:
            session.commit()
        except Exception:
            session.rollback()
            if idempotency_key:
                # Lost the race: another request inserted the same key.
                existing = session.execute(
                    select(Run).where(Run.idempotency_key == idempotency_key)
                ).scalar_one_or_none()
                if existing is not None:
                    return RunView.of(existing), False
            raise
        return RunView.of(run), True
```

Note the `except` branch: the **unique constraint** is the arbiter. The
`SELECT` is only an optimisation. Two concurrent requests both `SELECT` (both
find nothing), both `INSERT`, and the database lets exactly one win.

At the HTTP layer:

```python
@app.post("/runs", response_model=RunResponse, status_code=202)
async def create_run(body, response: Response, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    run, created = await store.create_run(..., idempotency_key=idempotency_key)
    response.status_code = 202 if created else 200
    response.headers["Location"] = f"/runs/{run.id}"
    if not created:
        response.headers["Idempotent-Replay"] = "true"
    return RunResponse.of(run)
```

`202 Accepted` for a new run, `200 OK` for a replay, plus an
`Idempotent-Replay: true` header so the client can tell.

---

## 6. Resuming — endpoint, webhook, or both

### 6.1 The resume endpoint

```python
@app.post("/runs/{run_id}/resume", response_model=RunResponse)
async def resume_run(run_id: str, body: ResumeRequest) -> RunResponse:
    run = await store.get_run(run_id)
    if run.status != RunStatus.PAUSED:
        raise HTTPException(status_code=409, detail=f"run is {run.status.value}, not paused")
    if not await store.prepare_resume(run_id, body.value):
        raise HTTPException(status_code=409, detail="could not queue the resume")
    return RunResponse.of(await store.get_run(run_id))
```

`prepare_resume` sets the answer and moves the run back to `pending`:

```python
def prepare_resume(self, run_id: str, value: Any) -> bool:
    run = session.get(Run, run_id)
    if RunStatus(run.status) != RunStatus.PAUSED:
        return False
    run.resume_value = json.dumps(value, default=str)
    run.status = RunStatus.PENDING.value
    session.commit()
    return True
```

**The resume goes back on the queue.** The HTTP request must return
immediately — a graph that takes 4 minutes to resume must not hold an HTTP
connection for 4 minutes. The worker picks it up and resumes it from its
checkpoint.

### 6.2 Webhook-triggered resume

The classic HITL flow: the agent needs approval, the approval happens in
Slack.

```python
@app.post("/webhooks/{kind}", response_model=RunResponse)
async def webhook(kind: str, body: WebhookRequest) -> RunResponse:
    run = await store.get_run(body.run_id)
    if body.interrupt_id and run.interrupt_id and body.interrupt_id != run.interrupt_id:
        raise HTTPException(status_code=409, detail="interrupt_id does not match")
    if run.status != RunStatus.PAUSED:
        raise HTTPException(status_code=409, detail=f"run is {run.status.value}, not paused")
    value = body.value if body.value is not None else (body.text or "approve")
    if not await store.prepare_resume(body.run_id, value):
        raise HTTPException(status_code=409, detail="could not queue the resume")
    return RunResponse.of(await store.get_run(body.run_id))
```

Two design points:

* **The webhook only re-queues.** It never runs the graph inline. A slow
  resume must not block the webhook caller (Slack times out in 3 seconds).
* **The `interrupt_id` is checked.** Without it, a stale Slack button could
  approve a *different*, newer interrupt on the same run.

And the webhook handler must itself be **idempotent** — Slack retries. Use the
`Idempotency-Key` header on the webhook too, or make `prepare_resume`
idempotent by requiring the run to be `paused` (which it will not be after the
first resume).

---

## 7. Durability modes

LangGraph lets you choose *when* checkpoints are written:

| Mode | When it writes | Performance | Durability |
|---|---|---|---|
| `exit` | Only when the run ends (success, error, or interrupt) | Best | Worst — a crash loses everything |
| `async` | In the background while the next step runs (**default**) | Good | Good — small risk on a hard crash |
| `sync` | Before the next step starts | Worst | Best — every checkpoint is committed |

```python
graph.stream(inputs, durability="sync")
```

The subtlety for a **new thread**:

> In every mode, a crash before the first checkpoint becomes durable leaves the
> thread indistinguishable from a thread that was never invoked: `get_tuple()`
> returns `None` in both cases, and `invoke(None, config)` raises
> `EmptyInputError`.

Which is the admission-log argument from §2.1, restated.

### Choosing

* Interactive chat → `async` (the default). Nobody notices a lost checkpoint
  in a 3-turn conversation.
* Long-running / expensive runs → `sync`. You cannot afford to redo 30
  minutes of LLM calls.
* Batch jobs you can re-run → `exit`.

There is also `DeltaChannel` (LangGraph ≥ 1.2, still **beta**) which stores
only the *incremental* delta of a channel instead of the full accumulated
value — a big win for append-heavy channels like `messages`, at the cost of
extra latency. It is not stable yet, so this course does not use it.

---

## 8. The HTTP surface

```
POST   /runs                    enqueue a run (idempotent via Idempotency-Key)
GET    /runs/{id}               status
GET    /runs                    list runs (filter by status)
GET    /runs/{id}/events        SSE stream (replayable via ?after_seq=N)
POST   /runs/{id}/cancel        request cancellation
POST   /runs/{id}/resume        answer a pending interrupt
POST   /webhooks/{kind}         external system triggers a resume
GET    /healthz                 liveness
```

### The SSE endpoint

```python
settled = {RunStatus.DONE, RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.PAUSED}

async def generator():
    seq = after_seq
    while True:
        events = await store.read_events(run_id, after_seq=seq)
        for event in events:
            seq = event.seq
            yield {"event": event.event, "id": str(event.seq), "data": json.dumps({...})}

        current = await store.get_run(run_id)
        if current is None:
            break
        if current.status in settled:
            # drain anything written after the status flip
            ...
            break
        await asyncio.sleep(EVENT_POLL_INTERVAL)
```

**A paused run ends the stream too, on purpose.** The run is waiting for a
human; the client has nothing to receive until the answer arrives. The
client reconnects with `?after_seq=` and gets the rest of the story.

> This was a real bug in our first version: the endpoint only closed on
> terminal statuses, so a paused run's SSE connection **hung forever**. The
> test suite caught it as a hang rather than a failure — which is exactly the
> kind of bug you want a test for.

---

## 9. Crash recovery

What happens when the worker dies mid-run?

| Situation | What you find | What you do |
|---|---|---|
| Killed between steps | Run still `running`, `heartbeat_at` stale | A reaper marks it `failed` (or re-queues it) |
| Killed during a step | Same | Same |
| Container restarted | Same | Same |

The `heartbeat_at` column exists for exactly this. A run whose heartbeat is
older than N minutes and whose status is `running` belongs to a dead worker.
A small **reaper** job finds those:

```sql
UPDATE runs
SET status = 'pending', started_at = NULL
WHERE status = 'running'
  AND heartbeat_at < now() - interval '10 minutes'
  AND attempt < 3;
```

(re-queue, with an attempt counter to stop infinite crash loops).

The checkpoint makes this safe: the resumed run replays from the last
checkpoint, not from the beginning.

---

## 10. The lab

```bash
python scripts/demo_m63.py
```

Real output:

```
1. Admit a run (idempotency key: demo-key-1)
   status_code: 202
2. Idempotent retry returns the SAME run
   status_code: 200 (200 = replay, 202 = newly created)
   same run id: True
   Idempotent-Replay header: true

3. Worker claims it; the graph pauses on the interrupt
   status: paused
   interrupt_id: 4516c1cac8badbc3e568537976427485
   interrupt_payload: {"question": "Publish the answer about ingest backlog?", ...}

4. Durable event log (what the client received)
   seq=1   status           {"phase": "thinking"}
   seq=6   token            {"text": "Restart ", "node": "route", "complete": false}
   seq=27  tool_result      {"tool_name": "lookup_docs", ...}
   seq=30  approval_request {"interrupt_id": "4516c1...", "question": "Publish..."}

6. Webhook-triggered resume (like a Slack 'Approve' button)
   webhook status: 200
   status after webhook: pending
   final status: done

7. Cancellation of a running graph (cooperative drain)
   cancel status_code: 200
   cancel_requested: True
   status after cancel: cancelled
   error/cancel_reason: drained: Graph drained: cancelled via API

8. Thread state survived (checkpoint = durability)
   next nodes: ()
   approved: True
   artifacts: [{'name': 'answer-ingest backlog.md', ...}]
```

---

## 11. Production checklist

- [ ] A `runs` table with a **unique** idempotency key
- [ ] Status transitions enforced (compare-and-set, not read-then-write)
- [ ] `cancel_requested` is a **request**, separate from `status`
- [ ] Graph execution happens in a **worker**, never in the request
- [ ] `thread_id` is stable across the pause/resume boundary
- [ ] Events are **persisted** so clients can replay
- [ ] Every stream segment ends with a `done` event
- [ ] SSE endpoint closes on `paused`, not only on terminal states
- [ ] Webhooks are idempotent and re-queue (never execute inline)
- [ ] `heartbeat_at` is written, and a reaper exists
- [ ] **No synchronous DB calls from `async def`** (use the async facade)
- [ ] Background tasks never die silently (catch-all + log)
- [ ] `durability` chosen deliberately per workflow
- [ ] Graceful shutdown: drain in-flight runs on SIGTERM

---

## 12. Traps

| Trap | Symptom | Fix |
|---|---|---|
| Sync DB call in `async def` | Cancels ignored, server stalls | `AsyncRunStore` / async engine |
| Background task raises | Silent failure, hours later | Catch-all + log + test the unhappy path |
| Run executes in the request | HTTP timeouts, web tier exhausted | Worker + queue |
| Resume with a new `thread_id` | Graph restarts from scratch | Same `thread_id` |
| Resume executes inline | Webhook times out (Slack: 3s) | Re-queue |
| No idempotency key | Duplicate runs, duplicate bills | `UNIQUE` constraint |
| `values` forwarded to clients | Enormous payloads | Filter to `updates` |
| SSE only closes on terminal states | Connection hangs on a paused run | Include `paused` |
| Cancel aborts instead of drains | Work lost | `RunControl` |
| No heartbeat | Orphaned `running` runs forever | Heartbeat + reaper |

---

## 13. Exercise

1. **Add a reaper.** A background task that finds `running` runs with a stale
   heartbeat and re-queues them (up to `attempt < 3`). Write a test that
   simulates a dead worker.

2. **Make the webhook idempotent.** Add an `Idempotency-Key` header and a
   unique constraint. Then verify that a double-clicked Slack button does not
   queue two resumes.

3. **Break the drain.** Set `cancel_mode="abort"` and observe the difference:
   the run is cancelled but the checkpoint may be mid-node. What does the
   client see? What state is the thread in?

4. **Add a heartbeat.** Write `heartbeat_at` from the worker on every step,
   and build a tiny dashboard query: "runs that have been `running` for more
   than 10 minutes".

---

**Next: [M64 — Testing graphs](64-testing.md) →**
