"""
L05 - Routing: conditional edges and Command.

Demonstrates:
  1. add_conditional_edges with and without a path_map.
  2. Reading the branch label back out of the Mermaid diagram.
  3. Command(update=..., goto=...) - the modern style.
  4. Command[Literal[...]] typed destinations + destinations= on add_node.
  5. A ReAct-style loop expressed as a cycle with a conditional exit.
  6. Command(update=...) still going through reducers.

Run:  uv run python examples/L05_routing_and_command.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from typing_extensions import TypedDict

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from lgc.printing import section, show_state


class SupportState(TypedDict):
    ticket: str
    category: str
    draft: str
    escalated: bool


# --------------------------------------------------------------------------
# Style 1: add_conditional_edges
# --------------------------------------------------------------------------
def classify_old(state: SupportState) -> dict:
    category = "billing" if "charged" in state["ticket"].lower() else "question"
    return {"category": category}


def route_old(state: SupportState) -> str:
    """A pure router - easy to unit test on its own."""
    return "billing" if state["category"] == "billing" else "question"


def build_conditional_graph():
    builder = StateGraph(SupportState)
    builder.add_node("classify", classify_old)
    builder.add_node("search_docs", lambda s: {"draft": "docs answer"})
    builder.add_node("escalate", lambda s: {"draft": "human will handle", "escalated": True})
    builder.add_edge(START, "classify")
    builder.add_conditional_edges(
        "classify",
        route_old,
        {
            # business label -> node name
            "question": "search_docs",
            "billing": "escalate",
        },
    )
    builder.add_edge("search_docs", END)
    builder.add_edge("escalate", END)
    return builder.compile()


# --------------------------------------------------------------------------
# Style 2: Command
# --------------------------------------------------------------------------
def classify_cmd(state: SupportState) -> Command[Literal["search_docs", "escalate"]]:
    category = "billing" if "charged" in state["ticket"].lower() else "question"
    goto = "escalate" if category == "billing" else "search_docs"
    return Command(update={"category": category}, goto=goto)


def build_command_graph():
    builder = StateGraph(SupportState)
    builder.add_node(
        "classify",
        classify_cmd,
        destinations=("search_docs", "escalate"),
    )
    builder.add_node("search_docs", lambda s: {"draft": "docs answer"})
    builder.add_node("escalate", lambda s: {"draft": "human will handle", "escalated": True})
    builder.add_edge(START, "classify")
    builder.add_edge("search_docs", END)
    builder.add_edge("escalate", END)
    # NOTE: no add_conditional_edges - the Command's goto= does the routing.
    return builder.compile()


# --------------------------------------------------------------------------
# A ReAct-style loop as a cycle
# --------------------------------------------------------------------------
class LoopState(TypedDict):
    question: str
    steps: int
    answer: str


def think(state: LoopState) -> dict:
    return {"steps": state["steps"] + 1}


def should_continue(state: LoopState) -> str:
    return "done" if state["steps"] >= 3 else "think_again"


def build_loop_graph():
    builder = StateGraph(LoopState)
    builder.add_node("think", think)
    builder.add_node("finish", lambda s: {"answer": f"done after {s['steps']} steps"})
    builder.add_edge(START, "think")
    builder.add_conditional_edges(
        "think", should_continue, {"done": "finish", "think_again": "think"}
    )
    builder.add_edge("finish", END)
    return builder.compile()


# --------------------------------------------------------------------------
# Command(update=...) goes through reducers
# --------------------------------------------------------------------------
from typing import Annotated  # noqa: E402

from langgraph.graph.message import add_messages  # noqa: E402


class MsgState(TypedDict):
    messages: Annotated[list, add_messages]


def build_command_reducer_graph():
    builder = StateGraph(MsgState)
    builder.add_node(
        "say",
        lambda s: Command(update={"messages": [AIMessage("hello")]}, goto="done"),
    )
    builder.add_node("done", lambda s: {"messages": [AIMessage("bye")]})
    builder.add_edge(START, "say")
    builder.add_edge("done", END)
    return builder.compile()


def main() -> None:
    section("1. STYLE 1 - add_conditional_edges + path_map")
    g1 = build_conditional_graph()
    print(g1.get_graph().draw_mermaid())
    print("\nrouter is a pure function - test it alone:")
    print("  route_old({'category': 'billing'}) ->", route_old({"category": "billing"}))
    show_state(g1.invoke({"ticket": "I was charged twice", "category": "", "draft": "", "escalated": False}))

    section("2. STYLE 2 - Command(update=..., goto=...)")
    g2 = build_command_graph()
    print(g2.get_graph().draw_mermaid())
    show_state(g2.invoke({"ticket": "I was charged twice", "category": "", "draft": "", "escalated": False}))
    print("-> the branch label in the diagram IS the goto= value")

    section("3. A REACT LOOP IS JUST A CYCLE")
    g3 = build_loop_graph()
    print(g3.get_graph().draw_mermaid())
    print("result:", g3.invoke({"question": "q", "steps": 0, "answer": ""}))

    section("4. Command(update=...) STILL GOES THROUGH REDUCERS")
    g4 = build_command_reducer_graph()
    out = g4.invoke({"messages": []})
    print("messages:", [m.content for m in out["messages"]])
    print("-> 'hello' was APPENDED, not replaced: the reducer still applies.")


if __name__ == "__main__":
    main()
