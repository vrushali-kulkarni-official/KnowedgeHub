"""L15 / M54 - What is actually inside a checkpoint?

Run:  python ex01_checkpoint_anatomy.py

This example builds a tiny 3-node graph, runs it with an InMemorySaver, then
dumps the raw checkpoint tuples so you can see every field LangGraph persists.

Key idea: a checkpoint is NOT "the state". A checkpoint is a *versioned
snapshot bundle* containing:

    checkpoint["channel_values"]   the state values at that moment
    checkpoint["channel_versions"] version counter per channel (last-write-wins)
    checkpoint["versions_seen"]    the version each node last observed
    checkpoint["id"]               the checkpoint uuid
    checkpoint["ts"]               ISO timestamp

...plus, on the surrounding CheckpointTuple:

    .config         the config that addresses THIS checkpoint
    .metadata       step, source, parents
    .parent_config  the config of the previous checkpoint
    .pending_writes writes from tasks that have not been committed yet
"""

from __future__ import annotations

import json
import operator
from typing import Annotated, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from _common import banner


class State(TypedDict, total=False):
    topic: str
    # `add` reducer: each write APPENDS instead of replacing.
    # This is what makes "the next run continues the thread" visible.
    notes: Annotated[list[str], operator.add]
    count: int


def build_graph():
    def plan(state: State) -> dict:
        return {"notes": [f"plan:{state.get('topic')}"], "count": state.get("count", 0) + 1}

    def work(state: State) -> dict:
        return {"notes": ["work:done"], "count": state["count"] + 1}

    def review(state: State) -> dict:
        return {"notes": ["review:ok"], "count": state["count"] + 1}

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
    banner("1. Build the graph WITHOUT a checkpointer")
    builder = build_graph()
    plain = builder.compile()
    result = plain.invoke({"topic": "persistence", "notes": [], "count": 0})
    print("result:", result)
    print("-> no checkpointer means no history, no resume, no time travel.")

    banner("2. Same graph WITH an InMemorySaver")
    saver = InMemorySaver()
    graph = builder.compile(checkpointer=saver)

    cfg = {"configurable": {"thread_id": "thread-A"}}
    graph.invoke({"topic": "persistence", "notes": [], "count": 0}, cfg)
    print("run 1 done")

    banner("3. The raw checkpoint tuple")
    tup = saver.get_tuple(cfg)
    print("type:", type(tup).__name__)
    print("\n-- .checkpoint (the raw snapshot bundle) --")
    print(json.dumps(tup.checkpoint, indent=2, default=str))
    print("\n-- .metadata --")
    print(json.dumps(tup.metadata, indent=2, default=str))
    print("\n-- .config --")
    print(json.dumps(tup.config, indent=2, default=str))
    print("\n-- .parent_config --")
    print(json.dumps(tup.parent_config, indent=2, default=str))
    print("\n-- .pending_writes --")
    print(json.dumps(tup.pending_writes, indent=2, default=str))

    banner("4. Every checkpoint written for this thread")
    print("NOTE: a raw CheckpointTuple has NO .next field. `next` lives on")
    print("      StateSnapshot (what graph.get_state() returns).")
    print("      Inside the raw checkpoint, the schedule is encoded as")
    print("      'branch:to:<node>' channels in channel_values.")
    print()
    print(f"{'ts':<28} {'step':<6} {'source':<10} scheduled-next (branch channels)")
    print("-" * 78)
    for s in saver.list(cfg):
        ts = s.checkpoint.get("ts")
        branches = [k for k in s.checkpoint.get("channel_values", {}) if k.startswith("branch:to:")]
        next_nodes = [b.replace("branch:to:", "") for b in branches]
        print(f"{str(ts):<28} {s.metadata.get('step'):<6} "
              f"{str(s.metadata.get('source')):<10} {next_nodes or '(finished)'}")

    print()
    print("The live view (StateSnapshot) does have .next:")
    snap = graph.get_state(cfg)
    print("  state.next       =", snap.next)
    print("  state.created_at =", snap.created_at)
    print("  state.tasks      =", [(t.name, t.state) for t in snap.tasks])

    banner("5. Threads are isolated namespaces")
    cfg_b = {"configurable": {"thread_id": "thread-B"}}
    graph.invoke({"topic": "isolation", "notes": [], "count": 0}, cfg_b)

    print("thread-A:", graph.get_state(cfg).values)
    print("thread-B:", graph.get_state(cfg_b).values)
    print("-> same graph, same node code, completely separate state.")

    banner("6. Re-running a thread CONTINUES it (this is the whole point)")
    graph.invoke({"topic": "persistence", "notes": ["--second-run--"]}, cfg)
    print("thread-A after 2nd run:", graph.get_state(cfg).values)
    print("-> 'notes' used the `add` reducer, so the second run APPENDED to")
    print("   the first run's history instead of replacing it.")
    print("-> 'count' is last-write-wins per write, but each node READS the")
    print("   carried-over value and adds 1, so the counter kept climbing.")

    banner("7. A NEW checkpoint = a NEW VERSION of the same thread")
    hist = list(saver.list(cfg))
    print(f"checkpoints in thread-A: {len(hist)}")
    for s in hist:
        cv = s.checkpoint.get("channel_values", {})
        print(f"  step={s.metadata.get('step')} "
              f"source={s.metadata.get('source')} "
              f"count={cv.get('count')} notes={cv.get('notes')}")


if __name__ == "__main__":
    main()
