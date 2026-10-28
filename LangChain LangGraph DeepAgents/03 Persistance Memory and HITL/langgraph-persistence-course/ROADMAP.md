# ROADMAP — Phase 8

## Where you are

```
Phase 0  Orientation & LLM mental models            ✅
Phase 1  Models & prompts                          ✅
Phase 2  Ingestion                                 ✅
Phase 3  Embeddings & vector stores                ✅
Phase 4  RAG                                       ✅
Phase 5  Tools & MCP                               ✅
Phase 6  Agents with create_agent                  ✅
Phase 7  LangGraph Core                            ✅
Phase 8  Persistence, Memory & HITL        ◀── YOU ARE HERE
```

---

## Phase 8 progress

| Lesson | Module | Status | Example |
|---|---|---|---|
| [L15](./lessons/L15-checkpoints-and-threads.md) | M54 — checkpointers & PostgresSaver | ✅ | `ex01`–`ex04` |
| [L16](./lessons/L16-state-inspection-and-time-travel.md) | M55 — state inspection & time travel | ✅ | `ex05`, `ex06` |
| [L17](./lessons/L17-durability-retries-and-crash-recovery.md) | M56 — durability, retries, crash recovery | ✅ | `ex07`, `ex08` |
| [L18](./lessons/L18-hitl-interrupts.md) | M57 — HITL part 1: interrupts | ✅ | `ex09`–`ex11` |
| [L19](./lessons/L19-hitl-production-approval-flows.md) | M58 — HITL part 2: approval flows | ✅ | `ex12` |
| [L20](./lessons/L20-short-term-memory.md) | M59 — short-term memory | ✅ | `ex13`, `ex14` |
| [L21](./lessons/L21-long-term-memory-store-and-langmem.md) | M60 — Store & langmem | ✅ | `ex15`–`ex17` |
| [L22](./lessons/L22-multi-tenant-and-data-lifecycle.md) | M61 — multi-tenancy & lifecycle | ✅ | `ex18`, `ex19` |

**8 lessons · 8 modules · 19 runnable examples · 0 unverified claims.**

---

## The skill checklist

Tick these off as you go. If you can't do them without looking, re-read the
lesson.

### L15 — checkpoints

- [ ] Explain what a checkpoint contains (`channel_values`, `channel_versions`,
      `versions_seen`, `branch:to:*`).
- [ ] Say why `CheckpointTuple` has no `.next`.
- [ ] Explain why re-invoking a thread continues it.
- [ ] Write the `PostgresSaver` startup/shutdown for a FastAPI app.
- [ ] Name the four tables PostgresSaver creates.
- [ ] Explain `prune` vs `delete_thread`.
- [ ] Say what RedisSaver requires (Redis Stack) and when you'd use it.

### L16 — time travel

- [ ] List the eight `StateSnapshot` fields.
- [ ] Read `metadata["source"]` and say what each value means.
- [ ] Explain that `update_state` writes a checkpoint.
- [ ] Explain the "one head" rule and when it bites.
- [ ] Replay a thread with `invoke(None, old_cfg)`.
- [ ] Explain why side effects don't undo.
- [ ] Write the SQL to clone a thread (because `copy_thread` doesn't work).

### L17 — reliability

- [ ] State what `sync` / `async` / `exit` each write.
- [ ] Say why `sync` and `async` both give one checkpoint per superstep.
- [ ] Explain why durability ≠ exactly-once.
- [ ] Write a `RetryPolicy` and narrow `retry_on`.
- [ ] Implement an idempotency key with a UNIQUE constraint.
- [ ] Name the three re-execution paths.

### L18 — interrupts

- [ ] Write the `interrupt()` / `Command(resume=...)` pair from memory.
- [ ] Use `version="v2"` and read `out.interrupts`.
- [ ] Explain why the node restarts from the top.
- [ ] Answer multiple interrupts by id.
- [ ] Use `response_schema` for a typed answer.
- [ ] Edit state with `update_state` before resuming.
- [ ] Say what is deprecated (`NodeInterrupt`) and what static breakpoints
      are really for.

### L19 — approval flows

- [ ] Design the `approvals` + `approval_audit` tables.
- [ ] Explain the atomic `UPDATE ... WHERE status='pending' RETURNING` claim.
- [ ] Say why you audit before resuming.
- [ ] Write a concurrency-safe sweeper.
- [ ] Choose 403 vs 409 correctly.

### L20 — short-term memory

- [ ] Say where short-term memory physically lives.
- [ ] Choose between trimming, context editing and summarization.
- [ ] Explain the difference between context editing and summarization with
      respect to the stored state.
- [ ] Configure a `("fraction", …)` trigger with a model profile.

### L21 — long-term memory

- [ ] Distinguish a checkpointer from a store.
- [ ] Design a namespace scheme and explain why order matters.
- [ ] Call `get_store()` from inside a node.
- [ ] Set up PostgresStore with pgvector and a real embedding model.
- [ ] Explain the two langmem value shapes.
- [ ] Name the three memory kinds and where procedures belong.

### L22 — multi-tenancy & lifecycle

- [ ] Explain convention-based vs structural isolation.
- [ ] Write a `ns()` helper and a composite `thread_id()`.
- [ ] Configure absolute (non-sliding) TTL.
- [ ] Write the retention job for checkpoint threads.
- [ ] List the five things a "delete user" must remove.
- [ ] Use the Langfuse v5 API to find and delete traces.

---

## What you can now build

- [ ] A multi-tenant agent with persistent conversations in Postgres.
- [ ] An approval workflow (refunds, publishing, deletions) with a reviewer
      queue, timeouts, authorization and an audit trail.
- [ ] A debug tool that replays any production thread.
- [ ] An agent with a context budget that survives a thousand-turn
      conversation.
- [ ] A long-term memory system with semantic recall and a GDPR delete.

---

## Suggested next: Phase 9 — Deployment

Once persistence is solid, the next questions are operational:

1. **`langgraph.json` + `langgraph dev`** — run the graph as a server with
   persistence handled for you.
2. **Streaming modes** — `values` / `updates` / `messages` / `debug` /
   `custom`, and how they interact with checkpoints.
3. **Running behind FastAPI** — SSE, cancellation, and long-running runs.
4. **Deployment topology** — one process vs many, shared Postgres, and how
   HITL pauses survive a restart.
5. **Background jobs** — running memory extraction and sweeper jobs as
   separate workers.

## Then: Phase 10 — Evaluation & Observability

- **Langfuse** wired into LangGraph: `@observe`, trace/span hierarchy,
  session and user tagging (which L22's GDPR delete depends on).
- **Datasets + experiments**: replaying your checkpoint history as an
  evaluation set.
- **Online evals**: scoring traces as they happen.
- **Regression testing**: snapshot a thread, change the code, re-run, diff.

---

## How to keep this course useful

1. **Re-run the examples after every upgrade.** LangGraph moves fast; the
   `source` values, the `__interrupt__` shape and the middleware internals
   are the things most likely to change.
2. **Pin your versions.** `langmem` is pre-1.0. `langgraph` is 1.x and
   follows semver-ish rules, but the middleware APIs are still moving.
3. **Keep a `docs/decisions.md`** in your project recording *why* you chose
   Postgres over Redis, `sync` over `async`, summarization over trimming.
   Six months later, that file is worth more than the code.
