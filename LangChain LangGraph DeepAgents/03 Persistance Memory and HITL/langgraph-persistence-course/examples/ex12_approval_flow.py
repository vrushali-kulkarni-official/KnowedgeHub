"""L19 / M58 - A production approval flow: state machine, sweeper, auth, audit.

Run:  python ex12_approval_flow.py

This is the "real service" version of HITL. Four pieces:

  1. PENDING APPROVAL STATE MACHINE
        pending -> approved | denied | timed_out | cancelled
     Stored in your own Postgres table, NOT in the graph. The graph holds the
     workflow; your table holds the queue of things a human must act on.

  2. TIMEOUT SWEEPER
     A background job that scans pending rows older than the deadline and
     resolves them as `timed_out` (and resumes the graph with a timeout
     decision, if you want the workflow to continue).

  3. RESUMING FROM YOUR API
     POST /approvals/{id}/decide  ->  graph.invoke(Command(resume=...), cfg)
     with AUTHORIZATION: only the reviewer who is allowed to decide may.

  4. AUDIT RECORD
     Every decision (who, what, when, from where, with what comment) is
     written to an append-only audit table. Never mutate it.

Everything is plain SQL + plain FastAPI-style handlers - no framework magic.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from psycopg import Connection
from psycopg.rows import dict_row

from _common import PG_URL_TEST, banner

# --------------------------------------------------------------------------
# Schema for the approval queue + audit trail
# --------------------------------------------------------------------------
DDL = """
CREATE TABLE IF NOT EXISTS approvals (
    id           uuid PRIMARY KEY,
    thread_id    text        NOT NULL,
    requester    text        NOT NULL,
    reviewer     text        NOT NULL,
    payload      jsonb       NOT NULL,
    status       text        NOT NULL DEFAULT 'pending',
    deadline     timestamptz NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    resolved_at  timestamptz,
    resolved_by  text
);

CREATE TABLE IF NOT EXISTS approval_audit (
    id          bigserial PRIMARY KEY,
    approval_id uuid        NOT NULL,
    thread_id   text        NOT NULL,
    action      text        NOT NULL,
    actor       text        NOT NULL,
    detail      jsonb       NOT NULL DEFAULT '{}'::jsonb,
    at          timestamptz NOT NULL DEFAULT now()
);
"""

ApprovalStatus = Literal["pending", "approved", "denied", "timed_out", "cancelled"]


def now() -> datetime:
    return datetime.now(timezone.utc)


def audit(conn: Connection, approval_id: str, thread_id: str, action: str,
          actor: str, detail: dict[str, Any] | None = None) -> None:
    """Append-only. One row per decision. Never UPDATE or DELETE these."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO approval_audit (approval_id, thread_id, action, actor, detail) "
            "VALUES (%s, %s, %s, %s, %s)",
            (approval_id, thread_id, action, actor, json.dumps(detail or {})),
        )


# --------------------------------------------------------------------------
# The graph
# --------------------------------------------------------------------------
@dataclass
class ApprovalState:
    request: str = ""
    amount: int = 0
    result: str = ""


def build_graph(saver: PostgresSaver):
    from typing import TypedDict

    class S(TypedDict, total=False):
        request: str
        amount: int
        result: str

    def prepare(state: S) -> dict:
        return {"result": "prepared"}

    def ask_human(state: S) -> dict:
        decision = interrupt(
            {
                "kind": "approval_request",
                "request": state.get("request"),
                "amount": state.get("amount"),
                "options": ["approve", "deny"],
            }
        )
        return {"result": f"decision:{decision}"}

    def finish(state: S) -> dict:
        return {"result": state.get("result", "") + "|finished"}

    g = StateGraph(S)
    g.add_node("prepare", prepare)
    g.add_node("ask_human", ask_human)
    g.add_node("finish", finish)
    g.add_edge(START, "prepare")
    g.add_edge("prepare", "ask_human")
    g.add_edge("ask_human", "finish")
    g.add_edge("finish", END)
    return g.compile(checkpointer=saver)


# --------------------------------------------------------------------------
# The service layer
# --------------------------------------------------------------------------
class ApprovalService:
    """Everything your API needs, with no framework in the way."""

    def __init__(self, saver: PostgresSaver, graph, conn: Connection):
        self.saver = saver
        self.graph = graph
        self.conn = conn

    # -- 1. start a request ------------------------------------------------
    def submit(self, *, thread_id: str, requester: str, reviewer: str,
               request: str, amount: int, timeout_s: int = 300) -> dict:
        """Kick off the graph; it will pause at the approval node."""
        cfg = {"configurable": {"thread_id": thread_id}}
        out = self.graph.invoke(
            {"request": request, "amount": amount}, cfg, version="v2"
        )
        if not out.interrupts:
            return {"status": "completed", "result": out.value}

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
        approval_id = str(row["id"])
        audit(self.conn, approval_id, thread_id, "submitted", requester,
              {"payload": payload})
        self.conn.commit()
        return {
            "status": "pending",
            "approval_id": approval_id,
            "deadline": row["deadline"],
            "payload": payload,
        }

    # -- 2. list the queue -------------------------------------------------
    def list_pending(self) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT id, thread_id, requester, reviewer, payload, deadline "
                "FROM approvals WHERE status = 'pending' ORDER BY created_at"
            )
            return [dict(r) for r in cur.fetchall()]

    def get(self, approval_id: str) -> dict | None:
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM approvals WHERE id = %s", (approval_id,))
            row = cur.fetchone()
        return dict(row) if row else None

    # -- 3. decide (this is what your POST endpoint calls) -----------------
    def decide(self, approval_id: str, *, actor: str, decision: str,
               comment: str = "", role: str = "reviewer") -> dict:
        """AUTHORIZATION lives here.

        Rule: only the assigned reviewer (or someone with the `approver-admin`
        role) may decide. A requester may NOT approve their own request.
        """
        approval = self.get(approval_id)
        if approval is None:
            return {"error": "not_found"}
        if approval["status"] != "pending":
            return {"error": "already_resolved", "status": approval["status"]}

        is_admin = role == "approver-admin"
        is_reviewer = actor == approval["reviewer"]
        if not (is_admin or is_reviewer):
            audit(self.conn, approval_id, approval["thread_id"], "denied_attempt",
                  actor, {"reason": "not_authorized", "role": role})
            self.conn.commit()
            return {"error": "forbidden"}

        if decision not in ("approve", "deny"):
            return {"error": "bad_decision"}

        status: ApprovalStatus = "approved" if decision == "approve" else "denied"
        resume_value = "approve" if decision == "approve" else "deny"

        # 3a. mark the row (guarded: only if still pending)
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE approvals SET status = %s, resolved_at = %s, resolved_by = %s "
                "WHERE id = %s AND status = 'pending' RETURNING id",
                (status, now(), actor, approval_id),
            )
            updated = cur.fetchone()
        self.conn.commit()
        if updated is None:
            # Lost a race with the sweeper.
            return {"error": "already_resolved"}

        # 3b. audit FIRST, then resume the graph.
        audit(self.conn, approval_id, approval["thread_id"], status, actor,
              {"comment": comment})
        self.conn.commit()

        # 3c. resume the paused graph
        cfg = {"configurable": {"thread_id": approval["thread_id"]}}
        out = self.graph.invoke(Command(resume=resume_value), cfg, version="v2")
        return {"status": status, "result": out.value}

    # -- 4. the timeout sweeper -------------------------------------------
    def sweep_timeouts(self) -> list[dict]:
        """Background job. Find pending approvals past their deadline and
        resolve them as `timed_out`.

        Returns the list of timed-out approvals.
        """
        timed_out: list[dict] = []
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
            # Resume the graph so the workflow is not stuck forever.
            cfg = {"configurable": {"thread_id": r["thread_id"]}}
            try:
                self.graph.invoke(Command(resume="timeout"), cfg, version="v2")
            except Exception as e:  # pragma: no cover
                print("   resume failed:", e)
            timed_out.append({"approval_id": approval_id, "thread_id": r["thread_id"]})
        return timed_out

    # -- 5. audit trail ----------------------------------------------------
    def audit_trail(self, approval_id: str) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT action, actor, detail, at FROM approval_audit "
                "WHERE approval_id = %s ORDER BY at, id",
                (approval_id,),
            )
            return [dict(r) for r in cur.fetchall()]


def main() -> None:
    with Connection.connect(PG_URL_TEST, autocommit=True, row_factory=dict_row) as conn:
        conn.execute(DDL)
        conn.execute("TRUNCATE approvals, approval_audit")

        with PostgresSaver.from_conn_string(PG_URL_TEST) as saver:
            saver.setup()
            graph = build_graph(saver)
            svc = ApprovalService(saver, graph, conn)

            banner("1. Submit a request -> it pauses at the approval node")
            res = svc.submit(
                thread_id="thread-approve-1",
                requester="alice",
                reviewer="bob",
                request="Refund order #55",
                amount=1200,
                timeout_s=300,
            )
            print(res)
            approval_id = res["approval_id"]

            banner("2. The pending queue")
            print("queue table : approvals")
            print("audit table : approval_audit  (append-only)")
            for row in svc.list_pending():
                print(f"  {row['id']} | {row['requester']} -> {row['reviewer']} | "
                      f"deadline={row['deadline']} | {row['payload']}")

            banner("3. AUTHORIZATION: the wrong person tries to approve")
            print(svc.decide(approval_id, actor="mallory", decision="approve"))
            print("-> refused, and the attempt itself is audited.")

            banner("4. The requester tries to approve their own request")
            print(svc.decide(approval_id, actor="alice", decision="approve"))
            print("-> refused (only the assigned reviewer or an admin may decide).")

            banner("5. The right reviewer approves")
            print(svc.decide(approval_id, actor="bob", decision="approve",
                              comment="looks legit"))
            print("-> the graph resumed and finished.")

            banner("6. The audit trail for that approval")
            for row in svc.audit_trail(approval_id):
                print(f"  {row['at']} {row['action']:<16} by {row['actor']:<16} {row['detail']}")

            banner("7. Double-decide is rejected")
            print(svc.decide(approval_id, actor="bob", decision="deny"))

            banner("8. A DENY path")
            r2 = svc.submit(thread_id="thread-approve-2", requester="carol",
                            reviewer="bob", request="Refund order #56", amount=99)
            aid2 = r2["approval_id"]
            print(svc.decide(aid2, actor="bob", decision="deny", comment="no receipt"))
            for row in svc.audit_trail(aid2):
                print(f"  {row['action']:<16} by {row['actor']:<16} {row['detail']}")

            banner("9. TIMEOUT: a request nobody answers")
            r3 = svc.submit(thread_id="thread-approve-3", requester="dave",
                            reviewer="bob", request="Refund order #57", amount=42,
                            timeout_s=-1)  # already expired
            aid3 = r3["approval_id"]
            print("submitted, deadline is in the past")
            print("pending before sweep:", len(svc.list_pending()))
            timed = svc.sweep_timeouts()
            print("sweeper resolved:", timed)
            print("pending after sweep :", len(svc.list_pending()))
            print("status now:", svc.get(aid3)["status"])
            for row in svc.audit_trail(aid3):
                print(f"  {row['action']:<16} by {row['actor']:<16} {row['detail']}")

            banner("10. The sweeper is idempotent - running it twice is safe")
            print("second sweep:", svc.sweep_timeouts())

            banner("11. Where the sweeper runs in production")
            print("  Option A - a separate worker process (best):")
            print("      while True:")
            print("          svc.sweep_timeouts()")
            print("          time.sleep(30)")
            print("  Option B - a periodic task in your existing scheduler")
            print("      (Celery beat, APScheduler, cron, K8s CronJob).")
            print("  Option C - lazily, inside the read path of list_pending().")
            print("      Cheapest, but only sweeps when someone looks.")
            print("  The sweeper MUST be safe to run concurrently with itself:")
            print("  the UPDATE ... WHERE status='pending' RETURNING guard means")
            print("  only one worker can win each row.")


if __name__ == "__main__":
    main()
