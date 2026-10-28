"""
L02 - Your first StateGraph.

Demonstrates:
  1. The 5-step skeleton (StateGraph -> add_node -> add_edge -> compile -> invoke).
  2. add_conditional_edges with a path_map.
  3. add_sequence.
  4. Mermaid visualisation + reading it.
  5. Two classic beginner errors, reproduced on purpose.

Run:  uv run python examples/L02_first_graph.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from typing_extensions import TypedDict

from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph

from lgc.printing import section, show_state


class TriageState(TypedDict):
    ticket: str
    category: str
    doc_snippets: list[str]
    bug_id: str
    draft: str


# --------------------------------------------------------------------------
# Nodes
# --------------------------------------------------------------------------
def read_ticket(state: TriageState) -> dict:
    return {"ticket": state["ticket"].strip()}


def classify(state: TriageState) -> dict:
    # A real node would call the LLM here (see src/lgc/llm.py).
    text = state["ticket"].lower()
    if "crash" in text or "error" in text:
        category = "bug"
    elif "invoice" in text or "charged" in text:
        category = "billing"
    else:
        category = "question"
    return {"category": category}


def search_docs(state: TriageState) -> dict:
    return {"doc_snippets": ["Reset password: Settings > Security > Change Password"]}


def file_bug(state: TriageState) -> dict:
    return {"bug_id": "BUG-4242"}


def draft_reply(state: TriageState) -> dict:
    if state.get("doc_snippets"):
        body = "Based on our docs: " + state["doc_snippets"][0]
    else:
        body = "We filed a bug and will follow up."
    return {"draft": body}


# --------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------
def route(state: TriageState) -> str:
    """Return a *branch name*. The path_map turns it into a node name."""
    return state["category"]


def build_graph() -> StateGraph:
    builder = StateGraph(TriageState)
    builder.add_node("read_ticket", read_ticket)
    builder.add_node("classify", classify)
    builder.add_node("search_docs", search_docs)
    builder.add_node("file_bug", file_bug)
    builder.add_node("draft_reply", draft_reply)

    builder.add_edge(START, "read_ticket")
    builder.add_edge("read_ticket", "classify")
    builder.add_conditional_edges(
        "classify",
        route,
        {
            "question": "search_docs",
            "billing": "file_bug",  # stand-in for "escalate to a human"
            "bug": "file_bug",
        },
    )
    builder.add_edge("search_docs", "draft_reply")
    builder.add_edge("file_bug", "draft_reply")
    builder.add_edge("draft_reply", END)
    return builder


def main() -> None:
    section("1. BUILD, VISUALISE, RUN")
    graph = build_graph().compile()

    print("--- Mermaid source (paste into mermaid.live to see the picture) ---")
    print(graph.get_graph().draw_mermaid())

    for ticket in [
        "How do I reset my password?",
        "The export crashes every time I select PDF",
        "I was charged twice for my subscription",
    ]:
        section(f"ticket: {ticket!r}")
        result = graph.invoke({"ticket": ticket})
        show_state(result, "final state")

    section("2. add_sequence (linear fast path)")
    lin = (
        StateGraph(TriageState)
        .add_sequence([("read_ticket", read_ticket), ("classify", classify)])
        .add_edge(START, "read_ticket")
        .add_edge("classify", END)
        .compile()
    )
    print(lin.get_graph().draw_mermaid())

    section("3. CLASSIC ERROR A: a CYCLE with no exit -> GraphRecursionError")
    print("Note: forgetting add_edge(node, END) is NOT an error - the graph just")
    print("ends there. A recursion error means a LOOP with no way out.\n")
    cyclic = (
        StateGraph(TriageState)
        .add_node("read_ticket", read_ticket)
        .add_node("classify", classify)
        .add_edge(START, "read_ticket")
        .add_edge("read_ticket", "classify")
        .add_edge("classify", "read_ticket")  # oops: a cycle
        .compile()
    )
    try:
        cyclic.invoke({"ticket": "hello"}, {"recursion_limit": 4})
    except GraphRecursionError as exc:
        print(f"GraphRecursionError: {str(exc).splitlines()[0]}")
        print("Fix: route the loop to END, or use a termination condition")

    section("4. CLASSIC ERROR B: no edge from START -> compile-time ValueError")
    print("LangGraph validates this at compile() time, not invoke() time.\n")
    try:
        StateGraph(TriageState).add_node("read_ticket", read_ticket).add_edge(
            "read_ticket", END
        ).compile()
    except ValueError as exc:
        print(f"ValueError: {exc}")
        print("Fix: add_edge(START, <first node>)")


if __name__ == "__main__":
    main()
