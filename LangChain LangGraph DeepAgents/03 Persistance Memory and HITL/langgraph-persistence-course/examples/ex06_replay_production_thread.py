"""L16 / M55 - Debugging production by replaying a real thread.

Run:  python ex06_replay_production_thread.py

This is the "superpower" lesson: a production thread lives in Postgres with
every step recorded. You can load it, read its history, find the exact step
that produced the bad outcome, and re-run from there with a fix.

THE SAFE WORKFLOW (this is the important part):

    1. copy_thread(prod_thread, scratch_thread)   <- clone, don't touch prod
    2. replay / fork inside the scratch thread
    3. once you know the fix, apply it to production deliberately

Why not just replay in the production thread? Because a thread has ONE head.
`update_state()` on an old checkpoint creates a new checkpoint that becomes
the thread's newest -> `get_state(thread_id)` now returns YOUR experiment,
not the customer's real state. Cloning first keeps production pristine.

The scenario: a support bot mis-routed a ticket because the triage node read
a stale field name. We reproduce, diagnose and fix it against real data.
"""

from __future__ import annotations

import operator
from typing import Annotated, Callable, TypedDict

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph

from _common import PG_URL_TEST, banner


class State(TypedDict, total=False):
    ticket_id: str
    subject: str
    # The BUG: the router reads `vip`, but the upstream system sends `is_vip`.
    vip: bool
    is_vip: bool
    route: str
    log: Annotated[list[str], operator.add]


def buggy_route(state: State) -> dict:
    # BUG (deliberate): should read `is_vip`, reads `vip`.
    is_vip = state.get("vip", False)
    route_name = "vip-desk" if is_vip else "standard-desk"
    return {"route": route_name, "log": [f"routed:{route_name}"]}


def fixed_route(state: State) -> dict:
    is_vip = state.get("is_vip", False)
    route_name = "vip-desk" if is_vip else "standard-desk"
    return {"route": route_name, "log": [f"routed:{route_name}"]}


def build_graph(route: Callable[[State], dict] = buggy_route):
    def load_ticket(state: State) -> dict:
        return {"log": [f"loaded:{state.get('ticket_id')}"]}

    def answer(state: State) -> dict:
        return {"log": [f"answered via {state.get('route')}"]}

    g = StateGraph(State)
    g.add_node("load_ticket", load_ticket)
    g.add_node("route", route)
    g.add_node("answer", answer)
    g.add_edge(START, "load_ticket")
    g.add_edge("load_ticket", "route")
    g.add_edge("route", "answer")
    g.add_edge("answer", END)
    return g



def clone_thread(saver: PostgresSaver, source: str, target: str) -> None:
    """Copy every row of a thread to a new thread_id.

    NOTE: `BaseCheckpointSaver.copy_thread(src, dst)` exists in the API but
    raises NotImplementedError in every shipped saver (checked on
    langgraph-checkpoint 4.3.1: PostgresSaver, AsyncPostgresSaver,
    InMemorySaver, RedisSaver). So we do the copy ourselves in SQL.

    This is also a great excuse to look at the real schema:

        checkpoints       one row per checkpoint  (thread_id, checkpoint_ns,
                          checkpoint_id, parent_checkpoint_id, checkpoint jsonb,
                          metadata jsonb)
        checkpoint_writes one row per pending write per task
        checkpoint_blobs  the binary/serde payloads, keyed by
                          (thread_id, checkpoint_ns, channel, version)
    """
    columns = {
        "checkpoints": (
            "thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, "
            "type, checkpoint, metadata"
        ),
        "checkpoint_writes": (
            "thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, "
            "type, blob, task_path"
        ),
        "checkpoint_blobs": (
            "thread_id, checkpoint_ns, channel, version, type, blob"
        ),
    }
    with saver.lock, saver.conn.cursor() as cur:
        for table, cols in columns.items():
            col_list, _, rest = cols.partition(",")
            target_cols = cols
            select_cols = cols.replace("thread_id", "%s", 1)
            cur.execute(
                f"INSERT INTO {table} ({target_cols}) "
                f"SELECT {select_cols} FROM {table} WHERE thread_id = %s "
                f"ON CONFLICT DO NOTHING",
                (target, source),
            )
    saver.conn.commit()
    print(f"cloned {len(list(saver.list({'configurable': {'thread_id': source}})))} "
          f"checkpoints from {source} to {target}")


def main() -> None:
    with PostgresSaver.from_conn_string(PG_URL_TEST) as saver:
        saver.setup()

        thread_id = "prod-ticket-7781"
        scratch_id = "scratch-ticket-7781"
        cfg = {"configurable": {"thread_id": thread_id}}

        # start clean so the example is re-runnable
        saver.delete_thread(thread_id)
        saver.delete_thread(scratch_id)

        banner("1. The 'production' run (the customer sent this ticket)")
        graph = build_graph().compile(checkpointer=saver)
        graph.invoke(
            {
                "ticket_id": thread_id,
                "subject": "My premium order is late",
                "is_vip": True,   # upstream sends is_vip
                "vip": False,     # the field the buggy code looks at
                "log": [],
            },
            cfg,
        )
        state = graph.get_state(cfg)
        print("route:", state.values["route"])
        print("log  :", state.values["log"])
        print("-> BUG reproduced: a VIP ticket went to the standard desk.")

        banner("2. Read the production thread's history")
        history = list(graph.get_state_history(cfg))
        for s in history:
            cid = s.config["configurable"]["checkpoint_id"]
            print(f"  step={s.metadata.get('step'):<3} source={str(s.metadata.get('source')):<6} "
                  f"route={str(s.values.get('route')):<16} id={cid[:8]}")

        banner("3. Bisect: which node broke it?")
        for s in history:
            v = s.values
            print(f"  step={s.metadata.get('step'):<3} "
                  f"is_vip={v.get('is_vip')} vip={v.get('vip')} route={v.get('route')}")

        banner("4. SAFE DEBUGGING: clone the thread, then experiment")
        clone_thread(saver, thread_id, scratch_id)
        scratch_cfg = {"configurable": {"thread_id": scratch_id}}
        print(f"copied {thread_id} -> {scratch_id}")
        print("scratch state:", graph.get_state(scratch_cfg).values["route"])

        banner("5. Replay inside the scratch thread")
        # Anchor = the checkpoint right BEFORE the route node ran.
        hist2 = list(graph.get_state_history(scratch_cfg))
        anchor = [
            s for s in hist2
            if s.values.get("route") is None and s.values.get("is_vip") is not None
        ][0]
        print("anchor values:", {k: anchor.values.get(k) for k in ("ticket_id", "is_vip", "vip")})

        # 5a. Simulate the DATA fix (upstream starts sending `vip` too).
        fork_cfg = graph.update_state(anchor.config, {"vip": True, "log": ["patched:vip=True"]})
        fixed = graph.invoke(None, fork_cfg)
        print("replay result:", fixed["route"], fixed["log"])

        banner("6. Production is UNTOUCHED")
        print("prod route :", graph.get_state(cfg).values["route"])
        print("prod log   :", graph.get_state(cfg).values["log"])
        print("scratch    :", graph.get_state(scratch_cfg).values["route"])

        banner("7. Now the real fix: change the CODE, replay the scratch thread")
        graph_fixed = build_graph(fixed_route).compile(checkpointer=saver)
        hist3 = list(graph_fixed.get_state_history(scratch_cfg))
        anchor2 = [
            s for s in hist3
            if s.values.get("route") is None and s.values.get("is_vip") is not None
        ][0]
        replay = graph_fixed.invoke(None, anchor2.config)
        print("replay with fixed code ->", replay["route"])
        print("-> the ORIGINAL production data now produces the CORRECT route.")
        print("-> this is how you validate a fix against real production input,")
        print("   with zero risk to the live conversation.")

        banner("8. Apply the fix to production (deliberately, not by accident)")
        # Now that we KNOW the fix, replay the real thread with fixed code.
        prod_anchor = [
            s for s in history
            if s.values.get("route") is None and s.values.get("is_vip") is not None
        ][0]
        applied = graph_fixed.invoke(None, prod_anchor.config)
        print("production replay ->", applied["route"])
        print("prod state now   :", graph.get_state(cfg).values["route"])
        print("-> the customer gets the right answer, and the whole history")
        print("   (including the bug) is still on disk for auditing.")

        banner("9. Clean up")
        saver.delete_thread(thread_id)
        saver.delete_thread(scratch_id)
        print("threads deleted. remaining:",
              len(list(saver.list(cfg))), len(list(saver.list(scratch_cfg))))


if __name__ == "__main__":
    main()
