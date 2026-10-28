"""L15 / M54 - PostgresSaver: the production checkpointer.

Run:  python ex02_postgres_saver.py

Requires a reachable PostgreSQL. Default URL:
    postgresql://langgraph:langgraph@127.0.0.1:5432/langgraph
Override with LANGGRAPH_PG_URL.

What this example proves:
  1. `PostgresSaver.setup()` creates the schema (and is safe to re-run).
  2. `from_conn_string(...)` is a context manager that owns a connection POOL.
  3. State survives a brand-new saver object -> the data is really in Postgres.
  4. Threads are rows; `prune()` and `delete_thread()` manage their lifetime.
  5. The async variant works the same way (AsyncPostgresSaver).
"""

from __future__ import annotations

import asyncio
from typing import TypedDict

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from psycopg import Connection
from psycopg.rows import dict_row

from _common import PG_URL, PG_URL_TEST, banner


class State(TypedDict, total=False):
    messages: list[str]


def build_graph():
    def step_a(state: State) -> dict:
        return {"messages": state.get("messages", []) + ["a"]}

    def step_b(state: State) -> dict:
        return {"messages": state["messages"] + ["b"]}

    g = StateGraph(State)
    g.add_node("step_a", step_a)
    g.add_node("step_b", step_b)
    g.add_edge(START, "step_a")
    g.add_edge("step_a", "step_b")
    g.add_edge("step_b", END)
    return g


def main() -> None:
    banner("1. setup() creates the schema (idempotent)")
    with PostgresSaver.from_conn_string(PG_URL_TEST) as saver:
        saver.setup()
        saver.setup()  # safe to call again
        print("setup() ran twice without error.")

        banner("2. What tables did LangGraph create?")
        with Connection.connect(PG_URL_TEST, autocommit=True, row_factory=dict_row) as conn:
            rows = conn.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' ORDER BY table_name
                """
            ).fetchall()
            for r in rows:
                print("  -", r["table_name"])

            banner("3. The checkpoints table is a per-thread log")
            print("(no threads have run yet - counted again in section 6)")

        banner("4. Run a graph, then reopen the saver from scratch")
        builder = build_graph()
        graph = builder.compile(checkpointer=saver)
        cfg = {"configurable": {"thread_id": "user-42"}}
        graph.invoke({"messages": []}, cfg)
        print("run inside saver #1:", graph.get_state(cfg).values)

        # Simulate a process restart: brand new pool, brand new saver.
        with PostgresSaver.from_conn_string(PG_URL_TEST) as saver2:
            graph2 = builder.compile(checkpointer=saver2)
            print("run inside saver #2 (fresh connection):", graph2.get_state(cfg).values)
            print("-> identical, because the state lives in Postgres, not in RAM.")

            banner("5. A conversation IS a thread")
            graph2.invoke({"messages": ["hello"]}, cfg)
            print("after 2nd turn:", graph2.get_state(cfg).values)
            other = {"configurable": {"thread_id": "user-43"}}
            graph2.invoke({"messages": ["different user"]}, other)
            print("user-42:", graph2.get_state(cfg).values)
            print("user-43:", graph2.get_state(other).values)

            banner("6. Inspect the thread's history")
            with Connection.connect(PG_URL_TEST, autocommit=True, row_factory=dict_row) as conn:
                rows = conn.execute(
                    """
                    SELECT thread_id, checkpoint_ns, count(*) AS n
                    FROM checkpoints GROUP BY 1,2 ORDER BY 1
                    """
                ).fetchall()
                for r in rows:
                    print(f"  thread_id={r['thread_id']} ns='{r['checkpoint_ns']}' rows={r['n']}")
                print()
            for s in saver2.list(cfg):
                print(f"  step={s.metadata.get('step')} "
                      f"source={s.metadata.get('source')} "
                      f"messages={s.checkpoint.get('channel_values', {}).get('messages')}")

        banner("7. Retention: delete_thread() vs prune()")
        with PostgresSaver.from_conn_string(PG_URL_TEST) as saver3:
            saver3.setup()
            n_before = len(list(saver3.list(cfg)))
            print("checkpoints before prune:", n_before)
            saver3.prune([cfg["configurable"]["thread_id"]], strategy="keep_latest")
            n_after = len(list(saver3.list(cfg)))
            print("checkpoints after  prune:", n_after)

            saver3.delete_thread(cfg["configurable"]["thread_id"])
            print("checkpoints after delete_thread:", len(list(saver3.list(cfg))))
            print("-> prune() keeps the thread but trims its history.")
            print("-> delete_thread() removes the thread entirely (GDPR!).")


async def async_demo() -> None:
    banner("8. Async: AsyncPostgresSaver")
    async with AsyncPostgresSaver.from_conn_string(PG_URL_TEST) as saver:
        await saver.setup()
        builder = build_graph()
        graph = builder.compile(checkpointer=saver)
        cfg = {"configurable": {"thread_id": "async-thread"}}
        out = await graph.ainvoke({"messages": []}, cfg)
        print("ainvoke result:", out)
        snap = await graph.aget_state(cfg)
        print("aget_state:", snap.values)
        print("-> use ainvoke/ainvoke when your service is async (FastAPI).")


if __name__ == "__main__":
    main()
    asyncio.run(async_demo())
