# L16 · State Inspection & Time Travel

> **Phase 8 — Persistence, Memory & Human-in-the-Loop**
> Module M55 · *State inspection & time travel*
>
> Run: `python examples/ex05_state_inspection.py`
> Run: `python examples/ex06_replay_production_thread.py`

---

## 0. The payoff

In L15 you learned that a checkpoint is a **versioned** snapshot. This lesson
is about what you can *do* with versions:

1. **Look** at the past — `get_state`, `get_state_history`.
2. **Write** to the past — `update_state`.
3. **Re-run** the past — invoke with an old `checkpoint_id`.

That third one is a superpower. Imagine a customer says *"the bot gave me a
wrong answer yesterday"*. With a checkpointer you can:

- find the exact step where the wrong answer was produced,
- look at the exact state the graph saw at that moment,
- re-run it with a fix,
- and compare — **without reproducing the bug by hand and without touching
  the customer's live conversation**.

`ex06_replay_production_thread.py` does exactly that against real Postgres.

---

## 1. The three inspection tools

All three live on the **compiled graph** (the `CompiledStateGraph` / `Pregel`
object), not on the saver:

```python
graph.get_state(config)                    # → StateSnapshot (current)
graph.get_state_history(config)            # → Iterator[StateSnapshot] (the past)
graph.update_state(config, values, as_node=None)   # → writes a new checkpoint
```

Plus the async twins: `aget_state`, `aget_state_history`, `aupdate_state`.

### 1.1 `StateSnapshot` — the fields

```python
StateSnapshot._fields
# ('values', 'next', 'config', 'metadata', 'created_at', 'parent_config',
#  'tasks', 'interrupts')
```

| Field | What it means |
|---|---|
| `values` | the state values at that point |
| `next` | **tuple of node names still to run** |
| `config` | the config that addresses this checkpoint |
| `metadata` | `step`, `source`, `parents` |
| `created_at` | timestamp |
| `parent_config` | config of the previous checkpoint |
| `tasks` | the pending tasks in this step (with their interrupts) |
| `interrupts` | pending interrupts waiting for an answer |

`next` is the field you'll use most in a HITL API:

```python
snap = graph.get_state(config)
if snap.next:
    print("this thread is waiting on node", snap.next[0])
```

---

## 2. `get_state` — what is the state right now?

```python
snap = graph.get_state(cfg)
snap.values      # {'topic': 'alpha', 'notes': [...], 'count': 3}
snap.next        # ()  -> nothing left to run
snap.metadata    # {'source': 'loop', 'step': 3, 'parents': {}}
snap.created_at  # datetime
```

The config you pass decides *which* checkpoint you read:

```python
graph.get_state({"configurable": {"thread_id": "t"}})                       # newest
graph.get_state({"configurable": {"thread_id": "t", "checkpoint_id": "..."}}) # that one
```

---

## 3. `get_state_history` — the whole timeline

```python
history = list(graph.get_state_history(cfg))
```

Newest first:

```
step=3   source=loop    count=3 notes=['plan:alpha', 'work', 'review']
step=2   source=loop    count=2 notes=['plan:alpha', 'work']
step=1   source=loop    count=1 notes=['plan:alpha']
step=0   source=loop    count=0 notes=[]
step=-1  source=input   count=None notes=[]
```

Useful arguments:

```python
graph.get_state_history(cfg, limit=10)                 # last 10
graph.get_state_history(cfg, before=older_config)      # checkpoints before X
graph.get_state_history(cfg, filter={"source": "update"})  # only manual updates
```

### 3.1 Reading `metadata["source"]`

This is the field that tells you *how* a checkpoint came to be. It is your
best debugging tool:

| `source` | Meaning | Typical cause |
|---|---|---|
| `"input"` | created from your input | the start of a run |
| `"loop"` | a normal graph step | the graph advanced |
| `"update"` | created by `update_state()` | someone edited state |
| `"fork"` | a branch from a replay | you time-travelled |

---

## 4. `update_state` — writing to state

```python
new_config = graph.update_state(config, {"count": 999})
```

### 4.1 It is NOT a free mutation

`update_state` **writes a new checkpoint**. The thread grows.

```python
before = len(list(graph.get_state_history(cfg)))
graph.update_state(cfg, {"count": 999})
after = len(list(graph.get_state_history(cfg)))
# before=12 -> after=13
```

### 4.2 `as_node` — who "wrote" this?

```python
graph.update_state(cfg, {"notes": ["<injected>"]}, as_node="review")
```

`as_node` decides which node's write rules (reducer) apply. If you omit it,
LangGraph uses the last node that updated the state; if that's ambiguous it
uses `__start__`.

**Practical rule:** if you're injecting a value that a reducer would normally
own, pass `as_node` explicitly so you know which reducer runs.

### 4.3 The one-head rule (important!)

> A thread has **exactly one head**. `update_state()` on an *older*
> checkpoint creates a new checkpoint that becomes the thread's newest.
> After that, `graph.get_state(thread_id)` returns **your edit**, not the
> customer's original state.

Verified in `ex05`:

```
5. Forking: update_state on an OLD checkpoint -> new branch
   forked result: {'topic': 'beta', ...}

6. The fork did NOT destroy the original
   step=3   source=loop   topic=beta   <- the fork is now the HEAD
   ...
   step=3   source=loop   topic=alpha  <- the original is still on disk
```

So forking does not "leave the original alone" in the sense of *which state
the thread reports*. The original history is preserved, but the thread's
current state is your new branch.

**⇒ For experiments, use a different thread id.** That is what
`ex06` does: it clones the thread (see §7) and works in the clone.

---

## 5. Time travel: re-running from an old checkpoint

```python
graph.invoke(None, old_config)
```

`None` means *"no new input — just run from here"*. LangGraph loads that
checkpoint and continues executing from the node that was scheduled next.

```python
mid = [s for s in history if s.values.get("notes") == ["plan:alpha"]][0]
replayed = graph.invoke(None, mid.config)
# {'topic': 'alpha', 'notes': ['plan:alpha', 'work', 'review'], 'count': 3}
```

The same nodes ran again and produced **new** checkpoints. The history now
contains two branches:

```
step=4   source=loop   count=3 notes=[...]      <- the replay
step=3   source=loop   count=2 notes=[...]
step=2   source=fork   count=1 notes=[...]      <- the fork point
step=3   source=loop   count=3 notes=[...]      <- the original run
```

### 5.1 ⚠️ Side effects do NOT undo

This is the caveat that matters most:

> Replaying re-runs your node code. If a node sends an email, charges a card,
> writes to your DB, or calls a third-party API — **it does it again.**

Time travel rewinds *LangGraph's state*, not the world.

| Replay path | What re-runs | Practical meaning |
|---|---|---|
| `invoke(None, old_cfg)` | every node from that point | all their side effects repeat |
| `update_state(old_cfg, ...)` then run | nodes after the edit point | same |
| code *above* `interrupt()` in a node | that code | runs again on resume (L18) |

Mitigations:
- Use idempotent nodes (L17 has the full pattern).
- Replay against a **sandbox thread** with stubbed side effects.
- Never replay a thread that charges money without an idempotency key.

### 5.2 What time travel is genuinely good for

- **Debugging**: reproduce the exact state that caused a bug.
- **Testing a fix against real data**: replay production input with new code.
- **Exploration**: "what would have happened if the router chose differently?"
- **Auditing**: reconstruct exactly what the agent saw.

---

## 6. The four `metadata["source"]` values, in practice

From `ex05`:

| Situation | `source` |
|---|---|
| first checkpoint of a run | `input` |
| normal advance | `loop` |
| you called `update_state` | `update` |
| you replayed / forked | `fork` |

When you look at a production thread and see `source: fork`, someone (or a
script) ran a time-travel experiment on that thread. That is worth knowing.

---

## 7. Cloning a thread (safe debugging)

The safest debugging workflow:

```
1. copy_thread(prod_thread, scratch_thread)   <- clone
2. replay / fork inside the scratch thread
3. once you know the fix, apply it to production deliberately
```

### 7.1 ⚠️ `copy_thread` exists in the API but is NOT implemented

`BaseCheckpointSaver.copy_thread(source_thread_id, target_thread_id)` is
declared in `langgraph.checkpoint.base` — but on **langgraph-checkpoint 4.3.1**
it raises `NotImplementedError` in every shipped saver:

| Saver | Implements `copy_thread`? |
|---|---|
| `PostgresSaver` | ❌ |
| `AsyncPostgresSaver` | ❌ |
| `InMemorySaver` | ❌ |
| `RedisSaver` | ❌ |

So you do it yourself. `ex06` shows the SQL, which doubles as a lesson in the
schema:

```python
def clone_thread(saver, source: str, target: str) -> None:
    columns = {
        "checkpoints":
            "thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, "
            "type, checkpoint, metadata",
        "checkpoint_writes":
            "thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, "
            "type, blob, task_path",
        "checkpoint_blobs":
            "thread_id, checkpoint_ns, channel, version, type, blob",
    }
    with saver.lock, saver.conn.cursor() as cur:
        for table, cols in columns.items():
            select_cols = cols.replace("thread_id", "%s", 1)
            cur.execute(
                f"INSERT INTO {table} ({cols}) "
                f"SELECT {select_cols} FROM {table} WHERE thread_id = %s "
                f"ON CONFLICT DO NOTHING",
                (target, source),
            )
    saver.conn.commit()
```

> **Note the column order.** `INSERT INTO t (cols) SELECT cols FROM t` — you
> cannot write `SELECT %s, *`, because the target column count would not
> match.

---

## 8. The full debugging workflow (verified end-to-end in `ex06`)

The scenario: a support bot mis-routes a VIP ticket, because the routing node
reads `vip` while the upstream system sends `is_vip`.

```
1. The 'production' run
   route: standard-desk        <- BUG reproduced

2. Read the production thread's history
   step=3 source=loop route=standard-desk
   step=2 source=loop route=standard-desk
   step=1 source=loop route=None
   step=0 source=loop route=None
   step=-1 source=input route=None

3. Bisect: which node broke it?
   step=3  is_vip=True vip=False route=standard-desk
   step=1  is_vip=True vip=False route=None        <- input was correct!

4. Clone the thread
   cloned 5 checkpoints from prod-ticket-7781 to scratch-ticket-7781

5. Replay in the scratch thread with the data patched
   replay result: vip-desk

6. Production is UNTOUCHED
   prod route : standard-desk
   scratch    : vip-desk

7. Change the CODE, replay the scratch thread again
   replay with fixed code -> vip-desk

8. Apply the fix to production deliberately
   production replay -> vip-desk
```

Step 3 is the real skill: you can see the input was right (`is_vip=True`) at
step 1, and the output was wrong at step 2. The bug is *between* them —
i.e. in the `route` node. You did not need to reproduce anything.

---

## 9. Debugging a production thread in practice

```python
from langgraph.checkpoint.postgres import PostgresSaver

with PostgresSaver.from_conn_string(DB_URL) as saver:
    graph = builder.compile(checkpointer=saver)
    cfg = {"configurable": {"thread_id": "complaint-1234"}}

    # 1. what does the user see now?
    print(graph.get_state(cfg).values)

    # 2. what happened, step by step?
    for s in graph.get_state_history(cfg):
        print(s.metadata.get("step"), s.metadata.get("source"), s.values)

    # 3. find the step right before the bad one
    history = list(graph.get_state_history(cfg))
    anchor = [s for s in history if s.values.get("route") is None][0]

    # 4. re-run it with a fix, IN A SANDBOX
    clone_thread(saver, "complaint-1234", "scratch-1234")
    scratch = {"configurable": {"thread_id": "scratch-1234"}}
    print(graph.invoke(None, anchor.config))
```

**Tip:** build a small internal tool around this. "Replay thread X" is a
button you want in your admin panel, not a script you rewrite every time.

---

## 10. Common mistakes

| Mistake | What happens | Fix |
|---|---|---|
| Expecting `update_state` to be a free edit | it writes a checkpoint | that's fine — just know |
| Forking on the live thread | the head moves to your branch | clone to a scratch thread first |
| Replaying a thread with real side effects | duplicate emails/charges | idempotent nodes (L17) |
| `s.next` on a `CheckpointTuple` | `AttributeError` | use `graph.get_state()` |
| Assuming history is unlimited | DB grows forever | `prune(strategy="keep_latest")` |
| Assuming `copy_thread` works | `NotImplementedError` | do the SQL copy yourself |

---

## 11. Checkpoint yourself

- [ ] I can name all eight `StateSnapshot` fields.
- [ ] I know what `metadata["source"]` values exist and what each means.
- [ ] I understand that `update_state` creates a checkpoint.
- [ ] I know that a thread has one head, and that forking moves it.
- [ ] I know side effects do not undo on replay.
- [ ] I know `copy_thread` raises `NotImplementedError` and can write the SQL.

**Next → [L17: Durability, retries & crash recovery](./L17-durability-retries-and-crash-recovery.md)**
