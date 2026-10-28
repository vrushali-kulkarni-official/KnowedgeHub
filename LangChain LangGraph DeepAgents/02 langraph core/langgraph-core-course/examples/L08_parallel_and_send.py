"""
L08 - Parallelism, fan-in and Send.

Demonstrates:
  1. Fan-out with multiple edges; fan-in with add_edge([...], node).
  2. The InvalidUpdateError you get without a reducer.
  3. Nondeterministic arrival order, and how to make the merge deterministic.
  4. The Send API for dynamic map-reduce.
  5. THE DIAGRAM GOTCHA: a Send-only target is missing from the static graph,
     and adding a "documentation-only" static edge causes an EXTRA execution.
  6. defer=True.

Run:  uv run python examples/L08_parallel_and_send.py
"""

from __future__ import annotations

import operator
import sys
import time
from pathlib import Path
from typing import Annotated

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from typing_extensions import TypedDict

from langgraph.errors import InvalidUpdateError
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send

from lgc.printing import section


class FanState(TypedDict):
    web: Annotated[list[str], operator.add]
    docs: Annotated[list[str], operator.add]
    combined: str


class NoReducerState(TypedDict):
    out: list[str]


class ItemState(TypedDict):
    items: list
    out: Annotated[list[str], operator.add]


class DocState(TypedDict):
    docs: list
    items: list
    out: Annotated[list[str], operator.add]


def main() -> None:
    section("1. FAN-OUT + FAN-IN")
    g = (
        StateGraph(FanState)
        .add_node("web", lambda s: {"web": ["w1"]})
        .add_node("docs", lambda s: {"docs": ["d1"]})
        .add_node("combine", lambda s: {"combined": s["web"] + s["docs"]})
        .add_edge(START, "web")
        .add_edge(START, "docs")
        .add_edge(["web", "docs"], "combine")   # the JOIN
        .add_edge("combine", END)
        .compile()
    )
    print(g.get_graph().draw_mermaid())
    print("result:", g.invoke({"web": [], "docs": [], "combined": ""}))
    print("-> web and docs ran in the SAME superstep (both fed by START).")

    section("2. WITHOUT A REDUCER -> InvalidUpdateError")
    bad = (
        StateGraph(NoReducerState)
        .add_node("a", lambda s: {"out": ["a"]})
        .add_node("b", lambda s: {"out": ["b"]})
        .add_edge(START, "a")
        .add_edge(START, "b")
        .add_edge("a", END)
        .add_edge("b", END)
        .compile()
    )
    try:
        bad.invoke({"out": []})
    except InvalidUpdateError as exc:
        print(f"InvalidUpdateError: {str(exc).splitlines()[0]}")

    section("3. ARRIVAL ORDER IS NOT GUARANTEED")
    print("Two parallel nodes appending to ONE list -> the order depends on")
    print("which one finishes first. Never rely on it. Use separate keys +")
    print("an explicit merge in the joining node (see `combined` above).")

    section("4. THE Send API - dynamic map-reduce")
    docs = [{"id": i, "text": f"doc {i}"} for i in range(3)]

    def split(state):
        return {"items": state["docs"]}

    def route_sends(state):
        return [Send("process", {"doc": d}) for d in state["items"]]

    def process(state):
        # state here is EXACTLY the Send payload
        return {"out": [f"processed:{state['doc']['id']}"]}

    g2 = (
        StateGraph(DocState)
        .add_node("split", split)
        .add_node("process", process)
        .add_edge(START, "split")
        .add_conditional_edges("split", route_sends, ["process"])
        .add_edge("process", END)
        .compile()
    )
    print(g2.get_graph().draw_mermaid())
    out = g2.invoke({"docs": docs, "items": [], "out": []})
    print("out:", out["out"], " <- 3 Sends -> 3 executions")

    section("5. THE DIAGRAM GOTCHA (measured)")
    print("Pattern A: add_conditional_edges(src, router_returning_sends, [target])")

    def build_a():
        def worker(state):
            counter["n"] += 1
            return {"out": ["w"]}

        b = StateGraph(ItemState)
        b.add_node("split", lambda s: {"items": ["a", "b", "c"]})
        b.add_node("worker", worker)
        b.add_node("after", lambda s: {"out": ["after"]})
        b.add_edge(START, "split")
        b.add_conditional_edges(
            "split", lambda s: [Send("worker", {"out": []}) for _ in s["items"]], ["worker"]
        )
        b.add_edge("worker", "after")
        b.add_edge("after", END)
        return b.compile()

    print("Pattern B: Command(goto=[Send(...)]) only")
    counter = {"n": 0}

    def build_b():
        def worker(state):
            counter["n"] += 1
            return {"out": ["w"]}

        b = StateGraph(ItemState)
        b.add_node("split", lambda s: {"items": ["a", "b", "c"]})
        b.add_node("dispatch", lambda s: Command(goto=[Send("worker", {"out": []}) for _ in s["items"]]))
        b.add_node("worker", worker)
        b.add_node("after", lambda s: {"out": ["after"]})
        b.add_edge(START, "split")
        b.add_edge("split", "dispatch")
        b.add_edge("worker", "after")
        b.add_edge("after", END)
        return b.compile()

    for name, build in (("A: conditional_edges + path_map", build_a), ("B: Command only", build_b)):
        counter["n"] = 0
        g = build()
        g.invoke({"items": [], "out": []})
        edges = [(e.source, e.target) for e in g.get_graph().edges]
        has_worker_edge = any(t == "worker" for _, t in edges)
        print(f"  {name}")
        print(f"     worker executed : {counter['n']}x (expected 3)")
        print(f"     'worker' edge drawn: {has_worker_edge}")
        print(f"     edges           : {edges}")

    print("\n  -> Pattern B OMITS 'worker' and everything downstream from the")
    print("     static diagram, even though the graph runs perfectly.")

    section("6. TRAP: a 'documentation-only' static edge causes an EXTRA run")
    counter2 = {"n": 0}

    def build_c(add_static):
        def worker(state):
            counter2["n"] += 1
            return {"out": ["w"]}

        b = StateGraph(ItemState)
        b.add_node("dispatch", lambda s: Command(goto=[Send("worker", {"out": []}) for _ in s["items"]]))
        b.add_node("worker", worker)
        b.add_node("after", lambda s: {"out": ["after"]})
        b.add_edge(START, "dispatch")
        if add_static:
            b.add_edge("dispatch", "worker")   # <-- "just for the diagram"
        b.add_edge("worker", "after")
        b.add_edge("after", END)
        return b.compile()

    for add_static in (False, True):
        counter2["n"] = 0
        g = build_c(add_static)
        g.invoke({"items": ["a", "b", "c"], "out": []})
        print(f"  add_edge(dispatch, worker) = {add_static}: worker ran {counter2['n']}x")
    print("  -> A static edge is a REAL edge. It schedules the node.")

    section("7. defer=True - run after the rest of the superstep")
    g3 = (
        StateGraph(FanState)
        .add_node("web", lambda s: {"web": ["w"]})
        .add_node("docs", lambda s: {"docs": ["d"]})
        .add_node("last", lambda s: {"combined": "deferred"}, defer=True)
        .add_edge(START, "web")
        .add_edge(START, "docs")
        .add_edge("web", "last")
        .add_edge("docs", "last")
        .add_edge("last", END)
        .compile()
    )
    print("result:", g3.invoke({"web": [], "docs": [], "combined": ""}))


if __name__ == "__main__":
    main()
