"""L16 / M55 - State inspection and time travel.

Run:  python ex05_state_inspection.py

The four tools you get once you have a checkpointer:

    graph.get_state(config)          -> StateSnapshot (current state)
    graph.get_state_history(config)  -> Iterator[StateSnapshot] (the whole past)
    graph.update_state(config, vals) -> write to state, creating a NEW checkpoint
    graph.invoke(None, old_config)   -> RE-RUN from an old checkpoint

Time travel = "take the config of an old checkpoint and run from there".
Forking    = "update_state() on an old checkpoint, then run from there",
              which creates a BRANCH and leaves the original history intact.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from _common import banner


class State(TypedDict, total=False):
    topic: str
    notes: Annotated[list[str], operator.add]
    count: int


def build_graph():
    def plan(state: State) -> dict:
        return {"notes": [f"plan:{state.get('topic')}"], "count": state.get("count", 0) + 1}

    def work(state: State) -> dict:
        return {"notes": ["work"], "count": state["count"] + 1}

    def review(state: State) -> dict:
        return {"notes": ["review"], "count": state["count"] + 1}

    g = StateGraph(State)
    g.add_node("plan", plan)
    g.add_node("work", work)
    g.add_node("review", review)
    g.add_edge(START, "plan")
    g.add_edge("plan", "work")
    g.add_edge("work", "review")
    g.add_edge("review", END)
    return g


def main() -> None:
    saver = InMemorySaver()
    graph = build_graph().compile(checkpointer=saver)
    cfg = {"configurable": {"thread_id": "tt"}}

    banner("0. Run the graph once")
    graph.invoke({"topic": "alpha", "notes": [], "count": 0}, cfg)
    print("final:", graph.get_state(cfg).values)

    banner("1. get_state(config) -> StateSnapshot")
    snap = graph.get_state(cfg)
    print("values      :", snap.values)
    print("next        :", snap.next, "  (nodes still to run)")
    print("config      :", snap.config)
    print("metadata    :", snap.metadata)
    print("created_at  :", snap.created_at)
    print("tasks       :", snap.tasks)
    print("interrupts  :", snap.interrupts)

    banner("2. get_state_history(config) -> the whole timeline")
    history = list(graph.get_state_history(cfg))
    print(f"{len(history)} snapshots, newest first:")
    for s in history:
        cid = s.config["configurable"]["checkpoint_id"]
        print(f"  step={s.metadata.get('step'):<3} source={str(s.metadata.get('source')):<6} "
              f"count={s.values.get('count')} notes={s.values.get('notes')} id={cid[:8]}")

    banner("3. Time travel: RE-RUN from an old checkpoint")
    # Pick the checkpoint right after 'plan' ran.
    mid = [s for s in history if s.values.get("notes") == ["plan:alpha"]][0]
    old_cfg = mid.config
    print("rewinding to:", mid.values, "step", mid.metadata.get("step"))

    # `invoke(None, old_config)` = "no new input, just re-run from here".
    replayed = graph.invoke(None, old_cfg)
    print("replay result:", replayed)
    print("-> the SAME nodes ran again, producing a NEW checkpoint.")
    print("-> your side effects (emails, DB writes) ran again too!")

    banner("4. History now has TWO branches")
    for s in graph.get_state_history(cfg):
        print(f"  step={s.metadata.get('step'):<3} source={str(s.metadata.get('source')):<6} "
              f"count={s.values.get('count')} notes={s.values.get('notes')}")

    banner("5. Forking: update_state on an OLD checkpoint -> new branch")
    # Start from the empty input checkpoint (step -1) and inject a different topic.
    root = [s for s in history if s.metadata.get("step") == -1][0]
    new_cfg = graph.update_state(root.config, {"topic": "beta", "notes": [], "count": 0})
    print("forked config:", new_cfg["configurable"]["checkpoint_id"][:8])
    forked = graph.invoke(None, new_cfg)
    print("forked result:", forked)

    banner("6. The fork did NOT destroy the original")
    for s in graph.get_state_history(cfg):
        print(f"  step={s.metadata.get('step'):<3} source={str(s.metadata.get('source')):<6} "
              f"topic={s.values.get('topic')} count={s.values.get('count')}")

    banner("7. update_state writes a checkpoint too (it is not a free mutation)")
    cur = graph.get_state(cfg)
    before = len(list(graph.get_state_history(cfg)))
    graph.update_state(cfg, {"count": 999})
    after = len(list(graph.get_state_history(cfg)))
    print(f"history length {before} -> {after}")
    print("new state:", graph.get_state(cfg).values)

    banner("8. as_node: pretend the write came from a specific node")
    graph.update_state(cfg, {"notes": ["<injected by review>"]}, as_node="review")
    print("state:", graph.get_state(cfg).values)


if __name__ == "__main__":
    main()
