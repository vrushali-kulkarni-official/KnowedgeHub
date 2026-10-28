"""L17 / M56 - Durability modes: what do they ACTUALLY guarantee?

Run:  python ex07_durability_modes.py

LangGraph persists a checkpoint after every superstep. When? That depends on
the `durability` argument you pass to invoke/stream:

    durability="sync"   write the checkpoint BEFORE the next step starts.
                        Slowest, strongest guarantee.
    durability="async"  write the checkpoint IN THE BACKGROUND while the next
                        step executes.  (DEFAULT)
    durability="exit"   write ONE checkpoint when the run ends (success, error
                        or interrupt). Fastest, weakest guarantee.

`durability` is a PER-CALL argument on invoke/stream/ainvoke/astream.
It is NOT a compile() argument.

This example counts the checkpoints each mode leaves behind, and shows the
one thing durability does NOT give you: exactly-once side effects.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from _common import banner


class State(TypedDict, total=False):
    count: int


def build_graph(effect_log: list[str]):
    def a(state: State) -> dict:
        effect_log.append("side-effect-a")
        return {"count": state.get("count", 0) + 1}

    def b(state: State) -> dict:
        effect_log.append("side-effect-b")
        return {"count": state["count"] + 1}

    def c(state: State) -> dict:
        effect_log.append("side-effect-c")
        return {"count": state["count"] + 1}

    g = StateGraph(State)
    g.add_node("a", a)
    g.add_node("b", b)
    g.add_node("c", c)
    g.add_edge(START, "a")
    g.add_edge("a", "b")
    g.add_edge("b", "c")
    g.add_edge("c", END)
    return g


def main() -> None:
    banner("How many checkpoints does each durability mode leave behind?")
    print("3-node graph => 3 supersteps after the input.")
    print()

    results = {}
    for mode in ("sync", "async", "exit"):
        saver = InMemorySaver()
        log: list[str] = []
        graph = build_graph(log).compile(checkpointer=saver)
        cfg = {"configurable": {"thread_id": f"dur-{mode}"}}

        graph.invoke({"count": 0}, cfg, durability=mode)

        history = list(saver.list(cfg))
        n = len(history)
        results[mode] = n
        print(f"  durability={mode:<6} checkpoints={n}")
        for s in history:
            print(f"      step={s.metadata.get('step'):<3} source={s.metadata.get('source'):<6} "
                  f"count={s.checkpoint.get('channel_values', {}).get('count')}")

    banner("Interpretation")
    print(f"  sync  -> {results['sync']} checkpoints: every step is durable")
    print(f"  async -> {results['async']} checkpoints: every step is durable")
    print(f"  exit  -> {results['exit']} checkpoint(s): ONLY the final state")
    print()
    print("'sync' and 'async' both give you a checkpoint PER SUPERSTEP.")
    print("The difference is only WHEN the write happens:")
    print("   sync  - the next step waits for the write to land (safe, slower)")
    print("   async - the next step runs while the write is in flight (fast,")
    print("           but a hard crash in that window can lose the write)")
    print("   exit  - nothing is written until the run ends. You cannot")
    print("           time-travel mid-run and you cannot resume a crash.")

    banner("What durability does NOT give you: exactly-once")
    print("Durability controls WHEN graph state is persisted.")
    print("It says NOTHING about your node's external side effects.")
    print()
    print("Scenario: node 'a' charges a credit card, then the process is")
    print("killed before the checkpoint is written. On resume, node 'a'")
    print("runs AGAIN -> the customer is charged twice.")
    print()
    print("=> Use an idempotency key (see ex08_idempotency.py).")

    banner("Which mode should you use?")
    print("  exit  - long-running, cheap-to-repeat background jobs where you")
    print("          only care about the final answer.")
    print("  async - the DEFAULT. Good balance for most production graphs.")
    print("  sync  - money movement, one-shot side effects, or anything where")
    print("          losing a step would be unacceptable. Use it when a")
    print("          duplicated side effect costs more than the extra latency.")


if __name__ == "__main__":
    main()
