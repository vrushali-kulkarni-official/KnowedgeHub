"""L17 / M56 - Retries, crash recovery, and the absence of exactly-once.

Run:  python ex08_retry_idempotency.py

Three things this proves, all against a real PostgreSQL:

  1. `RetryPolicy` per node retries transient failures.
  2. A crash mid-run resumes from the last checkpoint - BUT the node runs
     again, so its external side effect happens TWICE. There is no
     exactly-once in LangGraph (or anywhere else).
  3. You can BUILD exactly-once for a specific effect with an idempotency
     key + a UNIQUE constraint in the same database as the effect.

Point 3 is the only real answer to "the user got double-charged".
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy
from psycopg import Connection

from _common import PG_URL_TEST, banner


class State(TypedDict, total=False):
    amount: int
    charged: bool
    log: list[str]


# --------------------------------------------------------------------------
# A "payment" table with a UNIQUE idempotency key
# --------------------------------------------------------------------------
DDL = """
CREATE TABLE IF NOT EXISTS payments (
    op_key      text PRIMARY KEY,
    amount      integer NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
"""


def charge(op_key: str, amount: int) -> bool:
    """Charge exactly once for `op_key`.

    Returns True if THIS call performed the charge, False if it was a
    duplicate (and therefore skipped).

    The UNIQUE constraint on op_key is what makes this exactly-once: the
    INSERT and the de-duplication check are the SAME statement, in the SAME
    transaction. If the process dies after the INSERT commits, the retry
    sees the row and skips.
    """
    with Connection.connect(PG_URL_TEST, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO payments (op_key, amount) VALUES (%s, %s) "
                "ON CONFLICT (op_key) DO NOTHING RETURNING op_key",
                (op_key, amount),
            )
            return cur.fetchone() is not None


def build_graph(effects: list[str], crash: bool, use_idempotency: bool):
    def risky(state: State) -> dict:
        """A node whose external effect must happen exactly once."""
        op_key = f"payment-{state.get('amount')}"
        if use_idempotency:
            performed = charge(op_key, state.get("amount", 0))
            effects.append(f"charge({op_key}) -> {'PERFORMED' if performed else 'SKIPPED (duplicate)'}")
        else:
            effects.append(f"charge({op_key}) -> PERFORMED")
        if crash:
            effects.append("*** process killed right after the effect ***")
            raise ValueError("simulated crash after side effect")
        return {"charged": True, "log": ["charged"]}

    g = StateGraph(State)
    g.add_node("risky", risky)
    g.add_edge(START, "risky")
    g.add_edge("risky", END)
    return g


def main() -> None:
    with Connection.connect(PG_URL_TEST, autocommit=True) as conn:
        conn.execute(DDL)
        conn.execute("TRUNCATE payments")

    with PostgresSaver.from_conn_string(PG_URL_TEST) as saver:
        saver.setup()

        # ------------------------------------------------------------------
        banner("1. RetryPolicy: transient failures are retried")
        attempts = {"n": 0}

        def flaky(state: State) -> dict:
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ConnectionError("upstream unavailable")
            return {"log": [f"succeeded on attempt {attempts['n']}"]}

        g = StateGraph(State)
        g.add_node(
            "flaky",
            flaky,
            retry_policy=RetryPolicy(
                initial_interval=0.01,
                backoff_factor=2.0,
                max_interval=0.05,
                max_attempts=5,
                jitter=False,
            ),
        )
        g.add_edge(START, "flaky")
        g.add_edge("flaky", END)
        graph = g.compile(checkpointer=saver)
        out = graph.invoke({"amount": 1}, {"configurable": {"thread_id": "retry-1"}})
        print("attempts:", attempts["n"], "result:", out["log"])
        print("-> RetryPolicy(max_attempts=5) rescued a flaky node.")
        print()
        print("RetryPolicy fields (langgraph.types.RetryPolicy):")
        print("  initial_interval=0.5  backoff_factor=2.0  max_interval=128.0")
        print("  max_attempts=3  jitter=True")
        print("  retry_on=<callable>   default: ConnectionError, HTTP 5xx,")
        print("                         and anything NOT in the 'definitely a")
        print("                         bug' list (ValueError, TypeError, ...)")

        # ------------------------------------------------------------------
        banner("2. Default retry_on does NOT retry programming errors")
        tries = {"n": 0}

        def buggy(state: State) -> dict:
            tries["n"] += 1
            raise ValueError("bug in my code")

        g2 = StateGraph(State)
        g2.add_node("buggy", buggy, retry_policy=RetryPolicy(max_attempts=5, initial_interval=0.01))
        g2.add_edge(START, "buggy")
        g2.add_edge("buggy", END)
        graph2 = g2.compile(checkpointer=saver)
        try:
            graph2.invoke({"amount": 2}, {"configurable": {"thread_id": "retry-2"}})
        except Exception as e:
            print(f"raised: {type(e).__name__}: {e}")
        print("attempts:", tries["n"])
        print("-> ValueError is treated as a bug, not a transient failure.")
        print("-> Retry it forever and you just burn CPU.")

        # ------------------------------------------------------------------
        banner("3. Crash mid-run: the node runs AGAIN on resume")
        effects: list[str] = []
        graph3 = build_graph(effects, crash=True, use_idempotency=False).compile(checkpointer=saver)
        cfg3 = {"configurable": {"thread_id": "crash-1"}}

        try:
            graph3.invoke({"amount": 100, "log": []}, cfg3)
        except Exception as e:
            print(f"run failed with: {type(e).__name__}: {e}")

        print("effects so far:", effects)
        print("state after crash:", graph3.get_state(cfg3).values)

        banner("4. Resume: the node re-runs -> DUPLICATE side effect")
        effects.clear()
        try:
            graph3.invoke(None, cfg3)
        except Exception as e:
            print(f"resume failed with: {type(e).__name__}: {e}")
        print("effects on resume:", effects)
        print("-> The charge happened TWICE. LangGraph gave you at-least-once.")
        print("-> Durability mode does not change this (see ex07).")

        # ------------------------------------------------------------------
        banner("5. FIX: idempotency key + UNIQUE constraint -> exactly once")
        effects2: list[str] = []
        graph4 = build_graph(effects2, crash=True, use_idempotency=True).compile(checkpointer=saver)
        cfg4 = {"configurable": {"thread_id": "crash-2"}}

        try:
            graph4.invoke({"amount": 100, "log": []}, cfg4)
        except Exception as e:
            print(f"run failed with: {type(e).__name__}: {e}")
        print("effects:", effects2)

        effects2.clear()
        try:
            graph4.invoke(None, cfg4)
        except Exception as e:
            print(f"resume failed with: {type(e).__name__}: {e}")
        print("effects on resume:", effects2)

        with Connection.connect(PG_URL_TEST, autocommit=True) as conn:
            rows = conn.execute("SELECT op_key, amount FROM payments").fetchall()
        print("rows in payments table:", rows)
        print("-> ONE row. The retry hit the UNIQUE constraint and skipped.")
        print("-> Exactly-once for THIS effect, guaranteed by the database.")

        banner("6. The rule to remember")
        print("  LangGraph gives you AT-LEAST-ONCE execution of a node.")
        print("  If a node's side effect must not repeat, the effect itself")
        print("  must be idempotent:")
        print("    - deterministic idempotency key (e.g. the business entity id)")
        print("    - a UNIQUE constraint that turns the 2nd attempt into a no-op")
        print("    - or a transactional outbox you drain separately")
        print("  Keep the key in graph state so it survives a crash.")


if __name__ == "__main__":
    main()
