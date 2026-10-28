"""
L11 - Subgraphs.

Demonstrates:
  1. Pattern A: the subgraph as a node (shared state keys).
  2. Pattern B: calling the subgraph inside a node (different schemas).
  3. Namespace isolation + subgraphs=True in the stream.
  4. Persistence modes for subgraphs.

Run:  uv run python examples/L11_subgraphs.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from typing_extensions import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from lgc.printing import section


# --------------------------------------------------------------------------
# Pattern A: shared state keys
# --------------------------------------------------------------------------
class SharedState(TypedDict):
    foo: str
    bar: str


def sub1(state: SharedState) -> dict:
    return {"bar": "bar-from-sub"}


def sub2(state: SharedState) -> dict:
    return {"foo": state["foo"] + state["bar"]}


subgraph_shared = (
    StateGraph(SharedState)
    .add_node("sub1", sub1)
    .add_node("sub2", sub2)
    .add_edge(START, "sub1")
    .add_edge("sub1", "sub2")
    .add_edge("sub2", END)
    .compile()
)


# --------------------------------------------------------------------------
# Pattern B: different schemas
# --------------------------------------------------------------------------
class SubState(TypedDict):
    bar: str


class ParentState(TypedDict):
    a: str
    out: str


subgraph_diff = (
    StateGraph(SubState)
    .add_node("s1", lambda s: {"bar": "hi " + s["bar"]})
    .add_edge(START, "s1")
    .add_edge("s1", END)
    .compile()
)


def call_subgraph(state: ParentState) -> dict:
    result = subgraph_diff.invoke({"bar": state["a"]})
    return {"out": result["bar"]}


def main() -> None:
    section("1. PATTERN A - the subgraph AS A NODE (shared keys)")
    parent = (
        StateGraph(SharedState)
        .add_node("p1", lambda s: {"foo": "hi " + s["foo"]})
        .add_node("sub", subgraph_shared)
        .add_edge(START, "p1")
        .add_edge("p1", "sub")
        .add_edge("sub", END)
        .compile()
    )
    print(parent.get_graph().draw_mermaid())
    print("  result:", parent.invoke({"foo": "world", "bar": ""}))
    print("  -> the subgraph read the parent's 'foo' AND its sibling's 'bar'.")

    section("2. PATTERN B - calling the subgraph INSIDE a node")
    parent2 = (
        StateGraph(ParentState)
        .add_node("call", call_subgraph)
        .add_edge(START, "call")
        .add_edge("call", END)
        .compile()
    )
    print("  result:", parent2.invoke({"a": "world", "out": ""}))
    print("  -> you write the state mapping yourself.")

    section("3. NAMESPACE ISOLATION")
    print("  without subgraphs=True:")
    for chunk in parent.stream({"foo": "x", "bar": ""}, stream_mode="updates"):
        print("   ", chunk)
    print("  with subgraphs=True:")
    for ns, chunk in parent.stream(
        {"foo": "x", "bar": ""}, stream_mode="updates", subgraphs=True
    ):
        print(f"    ns={ns}  {chunk}")
    print("  -> the namespace tuple is the path to the subgraph.")

    section("4. SUBGRAPH PERSISTENCE MODES")
    print("  compile(checkpointer=...) on the SUBGRAPH decides whether it")
    print("  remembers things between calls:")
    print("    checkpointer=None  -> stateless (fresh every call)")
    print("    checkpointer=saver -> stateful (remembers per thread_id)")
    print("    checkpointer=False -> a fresh checkpointer per call")

    stateful_sub = (
        StateGraph(SharedState)
        .add_node("remember", lambda s: {"bar": s.get("bar", "") + "|x"})
        .add_edge(START, "remember")
        .add_edge("remember", END)
        .compile(checkpointer=InMemorySaver())
    )
    cfg = {"configurable": {"thread_id": "sub-1"}}
    stateful_sub.invoke({"foo": "", "bar": ""}, cfg)
    out = stateful_sub.invoke({"foo": "", "bar": ""}, cfg)
    print("  stateful subgraph, 2nd call ->", out)
    print("  -> it remembered the previous value.")


if __name__ == "__main__":
    main()
