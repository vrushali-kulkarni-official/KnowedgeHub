"""
L01 - Graph thinking.

Demonstrates:
  1. A linear graph and a fan-out graph, with supersteps made visible.
  2. How many supersteps a graph takes (the thing recursion_limit counts).
  3. WHY parallel nodes writing the same key need a reducer (the first
     taste of L04).

Run:  uv run python examples/L01_graph_thinking.py
"""

from __future__ import annotations

import operator
import sys
from pathlib import Path
from typing import Annotated

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from langgraph.errors import InvalidUpdateError
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from lgc.printing import section


class S(TypedDict):
    # NOTE: the reducer is the whole reason two parallel nodes can both write
    # to `order` in the same superstep. L04 explains this properly.
    order: Annotated[list[str], operator.add]
    label: str


class SNoReducer(TypedDict):
    """The same state WITHOUT a reducer - used to show the failure mode."""

    order: list[str]
    label: str


def make(order: list[str]) -> S:
    return {"order": order, "label": "x"}


def a(state: S) -> dict:
    return {"order": ["A"]}


def b(state: S) -> dict:
    return {"order": ["B"]}


def c(state: S) -> dict:
    return {"order": ["C"]}


def linear_graph():
    """START -> A -> B -> END.  Two node supersteps."""
    return (
        StateGraph(S)
        .add_node("A", a)
        .add_node("B", b)
        .add_edge(START, "A")
        .add_edge("A", "B")
        .add_edge("B", END)
        .compile()
    )


def fanout_graph():
    """START -> A -> {B, C} -> END.  B and C run in the SAME superstep."""
    return (
        StateGraph(S)
        .add_node("A", a)
        .add_node("B", b)
        .add_node("C", c)
        .add_edge(START, "A")
        .add_edge("A", "B")
        .add_edge("A", "C")
        .add_edge("B", END)
        .add_edge("C", END)
        .compile()
    )


def count_supersteps(graph, input_state: dict) -> int:
    """Count SUPERSTEPS (not nodes).

    `stream_mode="updates"` yields one chunk PER NODE, which is *not* the same
    thing. `stream_mode="debug"` carries a `step` number that IS the
    superstep index, so the number of distinct steps is the superstep count.
    """
    steps = set()
    for event in graph.stream(input_state, stream_mode="debug"):
        if event["type"] == "task":
            steps.add(event["step"])
    return len(steps)


def main() -> None:
    section("1. LINEAR GRAPH  START -> A -> B -> END")
    g1 = linear_graph()
    print(g1.get_graph().draw_mermaid())
    out = g1.invoke(make([]))
    print("\nresult order:", out["order"])
    print("supersteps  :", count_supersteps(g1, make([])))

    section("2. FAN-OUT GRAPH  START -> A -> {B, C} -> END")
    g2 = fanout_graph()
    print(g2.get_graph().draw_mermaid())
    out2 = g2.invoke(make([]))
    print("\nresult order:", out2["order"], "  <- order of B vs C is NOT guaranteed")
    print("supersteps  :", count_supersteps(g2, make([])))
    print(
        "\nNOTE: B and C ran in the SAME superstep, so the order they appended\n"
        "      to the list is NOT guaranteed. Never rely on it."
    )

    section("3. THE SAME FAN-OUT WITHOUT A REDUCER -> InvalidUpdateError")
    print("Two nodes wrote the same key ('order') in one superstep.")
    print("Without a reducer LangGraph refuses to guess. This is L04's whole topic.\n")
    bad = (
        StateGraph(SNoReducer)
        .add_node("B", lambda s: {"order": ["B"]})
        .add_node("C", lambda s: {"order": ["C"]})
        .add_edge(START, "B")
        .add_edge(START, "C")
        .add_edge("B", END)
        .add_edge("C", END)
        .compile()
    )
    try:
        bad.invoke({"order": [], "label": "x"})
    except InvalidUpdateError as exc:
        print("InvalidUpdateError:", exc)
        print("\nFix: Annotated[list[str], operator.add]  (see L04)")

    section("4. WHAT recursion_limit ACTUALLY COUNTS")
    print("recursion_limit counts SUPERSTEPS, not nodes.")
    print("  linear graph : 2 supersteps (A, then B)")
    print("  fan-out graph: 2 supersteps (A, then B+C together)")

    section("5. THE DECISION HELPER")
    print(
        """
Agent loop (create_agent)  -> the LLM's choice picks the CODE PATH
Explicit graph (StateGraph) -> the LLM's choice is just DATA in a fixed frame

Ask: "if the LLM made a different choice, would I change code?"
  no  -> explicit graph
  yes -> agent loop
"""
    )


if __name__ == "__main__":
    main()
