# L19 · Human-in-the-Loop Part 2 — Production Approval Flows

> **Phase 8 — Persistence, Memory & Human-in-the-Loop**
> Module M58 · *HITL part 2: production approval flows*
>
> Run: `python examples/ex12_approval_flow.py`

---

## 0. From "a graph pauses" to "a company approves refunds"

L18 gave you the mechanism. This lesson is the **service design** around it.

A production approval flow has four moving parts:

```
   ┌──────────────┐        ┌──────────────────┐        ┌──────────────┐
   │  your API    │───────▶│  the graph       │───────▶│  your DB     │
   │  (submit)    │        │  (paused at the  │        │  approvals   │
   └──────────────┘        │   approval node) │        │  audit       │
          ▲                └──────────────────┘        └──────────────┘
          │                          ▲                        │
          │                          │                        │
          │        ┌─────────────────┴────────────────┐       │
          └────────│  reviewer approves / denies      │◀──────┘
                   │  (API + authorization + audit)    │
                   └──────────────────────────────────┘
```

1. **A pending-approval state machine** — where does "waiting for a human"
   live? (Answer: *your* tables, not the graph.)
2. **A timeout sweeper** — what if nobody answers?
3. **Resuming from your API** — endpoints + authorization.
4. **An audit record** — who decided what, when.

`ex12_approval_flow.py` implements all four against real PostgreSQL.

---

## 1. Where does the "pending" state live?

**In your own database — not in the graph.**

The graph knows *that* it is paused (that's `snap.next` and `snap.interrupts`).
But the graph is not a queue. It cannot answer:

- Who is allowed to approve this?
- When does it expire?
- Has anyone already approved it?
- Show me everything Alice approved last month.

That is a **relational** question. Keep it relational.

### 1.1 The schema

```sql
CREATE TABLE approvals (
    id           uuid PRIMARY KEY,
    thread_id    text        NOT NULL,
    requester    text        NOT NULL,
    reviewer     text        NOT NULL,
    payload      jsonb       NOT NULL,   -- the interrupt value, for the UI
    status       text        NOT NULL DEFAULT 'pending',
    deadline     timestamptz NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    resolved_at  timestamptz,
    resolved_by  text
);

CREATE TABLE approval_audit (
    id          bigserial PRIMARY KEY,
    approval_id uuid        NOT NULL,
    thread_id   text        NOT NULL,
    action      text        NOT NULL,   -- submitted | approved | denied | ...
    actor       text        NOT NULL,
    detail      jsonb       NOT NULL DEFAULT '{}'::jsonb,
    at          timestamptz NOT NULL DEFAULT now()
);
```

Note `payload jsonb` — you store the interrupt value so the UI can render the
request later without replaying the graph.

---

## 2. The state machine

```
                      ┌──────────────┐
        submit ──────▶│   pending    │
                      └──┬───┬───┬───┘
             approve ─────┘   │   └───── timeout  → timed_out
                   │           │
            ┌──────▼───┐  ┌────▼─────┐
            │ approved │  │  denied  │
            └──────────┘  └──────────┘
                   │
            (any state) ──▶ cancelled
```

| Status | Meaning | Graph |
|---|---|---|
| `pending` | waiting for a human | paused at the interrupt |
| `approved` | a human said yes | resumed with the approval |
| `denied` | a human said no | resumed with the denial |
| `timed_out` | nobody answered in time | resumed with a timeout (or left paused) |
| `cancelled` | the requester withdrew it | resumed with a cancellation, or left paused |

**Store the status in your table. Do not try to derive it from the graph.**
The graph only knows "paused" vs "running".

---

## 3. Submitting a request

```python
def submit(self, *, thread_id, requester, reviewer, request, amount, timeout_s=300):
    cfg = {"configurable": {"thread_id": thread_id}}
    out = self.graph.invoke({"request": request, "amount": amount}, cfg, version="v2")

    if not out.interrupts:
        return {"status": "completed", "result": out.value}   # no approval needed

    payload = out.interrupts[0].value
    with self.conn.cursor() as cur:
        cur.execute(
            "INSERT INTO approvals (id, thread_id, requester, reviewer, payload, "
            "status, deadline) VALUES (gen_random_uuid(), %s, %s, %s, %s, "
            "'pending', %s) RETURNING id, deadline",
            (thread_id, requester, reviewer, json.dumps(payload),
             now() + timedelta(seconds=timeout_s)),
        )
        row = cur.fetchone()
    self.conn.commit()

    audit(self.conn, row["id"], thread_id, "submitted", requester, {"payload": payload})
    self.conn.commit()
    return {"status": "pending", "approval_id": str(row["id"]), "deadline": row["deadline"]}
```

Two things to notice:

1. **If the graph did not pause, don't create an approval row.** The approval
   may be conditional (e.g. only above $500). Handle the "no approval needed"
   path explicitly.
2. **Audit the submission too.** "Who asked for what, when" is half the
   compliance story.

---

## 4. Deciding — with authorization

This is the endpoint that actually matters.

```python
def decide(self, approval_id, *, actor, decision, comment="", role="reviewer"):
    approval = self.get(approval_id)
    if approval is None:
        return {"error": "not_found"}
    if approval["status"] != "pending":
        return {"error": "already_resolved", "status": approval["status"]}

    # ---- AUTHORIZATION ----
    is_admin = role == "approver-admin"
    is_reviewer = actor == approval["reviewer"]
    if not (is_admin or is_reviewer):
        audit(self.conn, approval_id, approval["thread_id"], "denied_attempt",
              actor, {"reason": "not_authorized", "role": role})
        self.conn.commit()
        return {"error": "forbidden"}

    if decision not in ("approve", "deny"):
        return {"error": "bad_decision"}

    status = "approved" if decision == "approve" else "denied"
    resume_value = "approve" if decision == "approve" else "deny"

    # ---- claim the row atomically ----
    with self.conn.cursor() as cur:
        cur.execute(
            "UPDATE approvals SET status = %s, resolved_at = %s, resolved_by = %s "
            "WHERE id = %s AND status = 'pending' RETURNING id",
            (status, now(), actor, approval_id),
        )
        updated = cur.fetchone()
    self.conn.commit()
    if updated is None:
        return {"error": "already_resolved"}     # lost a race

    # ---- audit, THEN resume ----
    audit(self.conn, approval_id, approval["thread_id"], status, actor,
          {"comment": comment})
    self.conn.commit()

    cfg = {"configurable": {"thread_id": approval["thread_id"]}}
    out = self.graph.invoke(Command(resume=resume_value), cfg, version="v2")
    return {"status": status, "result": out.value}
```

### 4.1 The authorization rules

| Rule | Why |
|---|---|
| Only the **assigned reviewer** may decide | the requester picked them |
| An **admin role** may override | escalation path |
| The **requester may not approve their own request** | separation of duties |
| Failed attempts are **audited** | detect privilege-escalation probing |

### 4.2 ⚠️ The atomic claim

```sql
UPDATE approvals SET status = 'approved', ...
WHERE id = %s AND status = 'pending' RETURNING id
```

This is the whole concurrency story in one line. Two reviewers click Approve
at the same instant; exactly one gets a row back, the other gets `None` and
returns `already_resolved`. **No double-approval, no lost update.**

Do **not** do this:

```python
if approval["status"] == "pending":      # ❌ read-then-write race
    approval["status"] = "approved"
```

### 4.3 Audit BEFORE resuming

If the resume crashes, you still have the audit record saying the decision
was made. If you audit after, a crash leaves an approved request with no
audit trail. **Audit first, then act.**

### 4.4 Verified output (`ex12`)

```
3. AUTHORIZATION: the wrong person tries to approve
   {'error': 'forbidden'}
   -> refused, and the attempt itself is audited.

4. The requester tries to approve their own request
   {'error': 'forbidden'}

5. The right reviewer approves
   {'status': 'approved', 'result': {...'result': 'decision:approve|finished'}}

6. The audit trail for that approval
   2026-10-28 15:23:47 submitted      by alice   {'payload': {...}}
   2026-10-28 15:23:47 denied_attempt by mallory {'role': 'reviewer', 'reason': 'not_authorized'}
   2026-10-28 15:23:47 denied_attempt by alice   {'role': 'reviewer', 'reason': 'not_authorized'}
   2026-10-28 15:23:47 approved       by bob     {'comment': 'looks legit'}

7. Double-decide is rejected
   {'error': 'already_resolved', 'status': 'approved'}
```

---

## 5. The timeout sweeper

Some approvals must not wait forever. A periodic job finds expired pending
rows and resolves them.

```python
def sweep_timeouts(self):
    timed_out = []
    with self.conn.cursor() as cur:
        cur.execute(
            "UPDATE approvals SET status = 'timed_out', resolved_at = %s, "
            "resolved_by = 'system:sweeper' "
            "WHERE status = 'pending' AND deadline < %s RETURNING id, thread_id",
            (now(), now()),
        )
        rows = cur.fetchall()
    self.conn.commit()

    for r in rows:
        approval_id = str(r["id"])
        audit(self.conn, approval_id, r["thread_id"], "timed_out",
              "system:sweeper", {"reason": "deadline_exceeded"})
        self.conn.commit()
        cfg = {"configurable": {"thread_id": r["thread_id"]}}
        try:
            self.graph.invoke(Command(resume="timeout"), cfg, version="v2")
        except Exception as e:
            print("resume failed:", e)
        timed_out.append({"approval_id": approval_id, "thread_id": r["thread_id"]})
    return timed_out
```

Verified:

```
9. TIMEOUT: a request nobody answers
   sweeper resolved: [{'approval_id': 'ddaf8035-...', 'thread_id': 'thread-approve-3'}]
   pending before sweep: 1
   pending after sweep : 0
   status now: timed_out

10. The sweeper is idempotent - running it twice is safe
    second sweep: []
```

### 5.1 The sweeper must be safe to run concurrently

The `UPDATE ... WHERE status='pending' RETURNING` guard means only **one**
worker can win each row. If you run three sweeper replicas, each row is still
resolved exactly once. That's why the sweeper uses the same atomic-claim
pattern as `decide()`.

### 5.2 Where the sweeper runs

| Option | How | Trade-off |
|---|---|---|
| **A. Separate worker process** | `while True: sweep(); sleep(30)` | best isolation; one more deployment |
| **B. Existing scheduler** | Celery beat / APScheduler / cron / K8s CronJob | reuses infra you already have |
| **C. Lazily in the read path** | call `sweep()` inside `list_pending()` | zero infra; only sweeps when someone looks |

Start with **C** if you have no scheduler, then move to **B**.

### 5.3 Should a timeout resume the graph?

Two designs:

| Design | Behaviour | Use when |
|---|---|---|
| Resume with `"timeout"` | the workflow continues with a timeout branch | the graph has an explicit timeout path |
| Don't resume | the thread stays paused | you want a human to look at it later |

Both are valid. Make it explicit in your `interrupt()` payload:

```python
decision = interrupt({
    "kind": "approval_request",
    "options": ["approve", "deny"],
    "timeout_options": ["approve", "deny"],   # what the sweeper may send
})
```

Then the sweeper resumes with `Command(resume="deny")` — the same value a
human would send — and your node logic stays simple.

---

## 6. API surface

A complete, minimal approval API:

```python
# POST /approvals                      -> submit a request
# GET  /approvals                      -> list pending (for the reviewer's queue)
# GET  /approvals/{id}                 -> detail (payload, status, audit)
# POST /approvals/{id}/decide          -> approve / deny
# POST /approvals/{id}/cancel          -> requester withdraws
```

```python
@app.post("/approvals/{approval_id}/decide")
def decide(approval_id: str, body: DecideRequest, user=Depends(current_user)):
    # 1. who is this? -> user.id, user.role
    # 2. service does auth + atomic claim + audit + resume
    result = service.decide(
        approval_id,
        actor=user.id,
        decision=body.decision,
        comment=body.comment,
        role=user.role,
    )
    if "error" in result:
        status = {"not_found": 404, "forbidden": 403,
                  "already_resolved": 409, "bad_decision": 400}[result["error"]]
        raise HTTPException(status, result)
    return result
```

| Situation | HTTP |
|---|---|
| approval doesn't exist | 404 |
| not authorized | 403 |
| already decided | 409 (Conflict) |
| decided successfully | 200 |

Use **409** for "already resolved" — it is a conflict with the current state,
not a client error.

### 6.1 The reviewer's queue query

```sql
SELECT id, requester, reviewer, payload, deadline, created_at
FROM approvals
WHERE status = 'pending' AND reviewer = :me
ORDER BY deadline
LIMIT 50;
```

This is exactly the kind of query PostgresSaver cannot do for you — another
reason the approval queue lives in your database, not in the graph.

---

## 7. The audit trail

**Append only.** Never `UPDATE` or `DELETE` an audit row.

```
submitted      by alice           {'payload': {...}}
denied_attempt by mallory         {'role': 'reviewer', 'reason': 'not_authorized'}
approved       by bob             {'comment': 'looks legit'}
```

What to record:

| Field | Why |
|---|---|
| `action` | what happened (submitted / approved / denied / timed_out / denied_attempt) |
| `actor` | who did it (including `system:sweeper`) |
| `detail` | free-form JSON: the comment, the reason, the payload |
| `at` | when (server time, never client time) |

Also record **failed** attempts. If someone probes your approval endpoint
looking for weaknesses, that log is your only evidence.

---

## 8. The full lifecycle, end to end

```
1. alice submits a $1200 refund
        ↓
2. graph runs → pauses at the approval node
        ↓
3. approvals row: status='pending', reviewer='bob', deadline=now+5min
        ↓
4. audit: 'submitted' by alice
        ↓
5. mallory tries to approve → 403, audited as 'denied_attempt'
        ↓
6. bob approves → atomic claim → audit 'approved' → graph resumes
        ↓
7. graph finishes; refund executed
```

And if bob never clicks:

```
5'. 5 minutes pass
        ↓
6'. sweeper: atomic claim → status='timed_out', audit 'timed_out'
        ↓
7'. graph resumed with the timeout decision
```

---

## 9. Production checklist

- [ ] The approval queue is a table in **your** database, not the graph.
- [ ] `payload jsonb` stores the interrupt value for the UI.
- [ ] Only the assigned reviewer (or an admin) can decide.
- [ ] The requester cannot approve their own request.
- [ ] The status transition is a single atomic `UPDATE ... WHERE status='pending'`.
- [ ] The audit row is written **before** the graph is resumed.
- [ ] Failed authorization attempts are audited.
- [ ] A sweeper exists and is safe to run concurrently.
- [ ] `409` is returned for "already resolved".
- [ ] The resume value the sweeper sends is one the node understands.

---

## 10. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Keeping the queue only in the graph | no queries, no authz, no audit | use a table |
| `if status == 'pending'` then update | double approval under concurrency | atomic `UPDATE ... RETURNING` |
| Auditing after the resume | crash leaves no audit trail | audit first |
| No timeout | threads hang forever | sweeper |
| Resuming with a value the node doesn't expect | node crashes on resume | define the timeout value up front |
| Let the requester approve | fraud | enforce separation of duties |
| Trusting client-supplied status | trivially bypassable | status is server-owned |

---

## 11. Checkpoint yourself

- [ ] I can design the `approvals` + `approval_audit` tables.
- [ ] I can explain why the atomic `UPDATE ... RETURNING` claim matters.
- [ ] I know why you audit before resuming.
- [ ] I can write a concurrency-safe sweeper.
- [ ] I know the 403 vs 409 distinction.

**Next → [L20: Short-term memory](./L20-short-term-memory.md)**
