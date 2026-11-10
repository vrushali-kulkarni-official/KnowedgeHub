"""EX05 - The routing primitives: Command, Send, and the four traps.

Run:  PYTHONPATH=examples .venv/bin/python examples/ex05_command_and_send.py

Two objects do ALL the routing in LangGraph:

  Command(update=..., goto=..., graph=...)
      "change the state AND/OR jump to another node"
      - update  : a dict of state writes
      - goto    : the name of the next node (or a Send)
      - graph   : None (this graph) or Command.PARENT (the graph above me)

  Send(node, arg)
      "run `node` with `arg` as its input, in parallel with my siblings"

Everything else (conditional edges, `Command.PARENT`, handoffs, fan-out) is
built from these two.

This file also reproduces the FOUR TRAPS that cost beginners the most time.
Every trap is reproduced here, with the exact error message, so you can
recognise it in the wild.
"""

from __future__ import annotations

from typing import Annotated

from langchain.agents import AgentState, create_agent
from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send

from _common import once_then_final, scripted, text_of, user

LIMIT = {"recursion_limit": 12}


class TeamState(AgentState):
    note: str


# ---------------------------------------------------------------------------
# Command - the three forms
# ---------------------------------------------------------------------------


def command_update_only():
    """Command(update=...) writes state and continues on the normal edge."""

    def writer(state):
        return {"note": state.get("note", "") + "!"}

    g = StateGraph(TeamState)
    g.add_node("writer", writer)
    g.add_edge(START, "writer")
    g.add_edge("writer", END)
    app = g.compile()
    out = app.invoke({"messages": [user("go")], "note": "hi"}, LIMIT)
    return out["note"]


def command_goto_same_graph():
    """Command(goto=...) jumps to a sibling node in the SAME graph."""

    def a(state):
        return Command(goto="b", update={"note": "a ran"})

    def b(state):
        return {"note": state.get("note", "") + "|b ran"}

    g = StateGraph(TeamState)
    g.add_node("a", a)
    g.add_node("b", b)
    g.add_edge(START, "a")
    g.add_edge("b", END)
    app = g.compile()
    out = app.invoke({"messages": [user("go")]}, LIMIT)
    return out["note"]


def command_parent_goto():
    """Command(graph=Command.PARENT, goto=...) jumps to the graph ABOVE.

    This is the modern handoff primitive (L05).  The tool lives inside a
    `create_agent` subgraph, so a plain `goto` would try to find the target
    inside the agent's own internal graph - and silently fail.
    """

    @tool
    def hand_off(tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
        """Hand the conversation to the billing specialist."""
        return Command(
            graph=Command.PARENT,
            goto="billing",
            update={
                "messages": [
                    ToolMessage(content="handing off", tool_call_id=tool_call_id, name="hand_off")
                ],
                "note": "handed off",
            },
        )

    def billing(state):
        return {"note": state.get("note", "") + "|billing handled it"}

    g = StateGraph(TeamState)
    g.add_node(
        "router",
        create_agent(scripted(router=once_then_final("hand_off", {})), tools=[hand_off]),
    )
    g.add_node("billing", billing)
    g.add_edge(START, "router")
    g.add_edge("billing", END)
    app = g.compile()
    out = app.invoke({"messages": [user("go")]}, LIMIT)
    return out["note"]


# ---------------------------------------------------------------------------
# Send - fan-out
# ---------------------------------------------------------------------------


def send_fanout():
    """Send(node, arg) runs `node` once per Send, all in parallel."""

    class FanState(TeamState):
        results: Annotated[list[str], lambda a, b: a + b]

    def worker(state):
        return {"results": [f"worker saw {state.get('topic')}"]}

    def fanout(state):
        return [
            Send("worker", {"topic": t, "messages": state["messages"]})
            for t in ("alpha", "beta", "gamma")
        ]

    g = StateGraph(FanState)
    g.add_node("start", lambda s: {})
    g.add_node("worker", worker)
    g.add_edge(START, "start")
    g.add_conditional_edges("start", fanout, ["worker"])
    g.add_edge("worker", END)
    app = g.compile()
    out = app.invoke({"messages": [user("go")], "results": []}, LIMIT)
    return out["results"]


# ---------------------------------------------------------------------------
# TRAP 1 - a plain goto from inside create_agent silently does nothing
# ---------------------------------------------------------------------------


def trap_1_plain_goto_inside_agent():
    @tool
    def hand_off(tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
        """Hand off WITHOUT graph=Command.PARENT."""
        return Command(
            goto="billing",
            update={
                "messages": [
                    ToolMessage(content="x", tool_call_id=tool_call_id, name="hand_off")
                ]
            },
        )

    def billing(state):
        return {"note": "billing ran"}

    g = StateGraph(TeamState)
    g.add_node(
        "router",
        create_agent(scripted(router=once_then_final("hand_off", {})), tools=[hand_off]),
    )
    g.add_node("billing", billing)
    g.add_edge(START, "router")
    g.add_edge("billing", END)
    app = g.compile()
    try:
        out = app.invoke({"messages": [user("go")]}, LIMIT)
        return "no exception", out.get("note")
    except Exception as exc:  # GraphRecursionError: the loop never terminates
        return type(exc).__name__, str(exc).splitlines()[0]


# ---------------------------------------------------------------------------
# TRAP 2 - Command(update=) must carry a matching ToolMessage
# ---------------------------------------------------------------------------


def trap_2_missing_tool_message():
    @tool
    def write_note(note: str) -> Command:
        """Write a note but return a bare message instead of a ToolMessage."""
        return Command(update={"messages": [{"role": "assistant", "content": note}]})

    g = StateGraph(AgentState)
    g.add_node(
        "a", create_agent(scripted(router=once_then_final("write_note", {"note": "x"})), tools=[write_note])
    )
    g.add_edge(START, "a")
    g.add_edge("a", END)
    app = g.compile()
    try:
        app.invoke({"messages": [user("go")]}, LIMIT)
        return "no exception", ""
    except Exception as exc:
        return type(exc).__name__, str(exc)[:200]


# ---------------------------------------------------------------------------
# TRAP 3 - InjectedToolCallId must be Annotated
# ---------------------------------------------------------------------------


def trap_3_wrong_injection_annotation():
    @tool
    def hand_off(tool_call_id: InjectedToolCallId) -> Command:
        """Uses the BARE annotation instead of Annotated[str, InjectedToolCallId]."""
        return Command(
            graph=Command.PARENT,
            goto="billing",
            update={
                "messages": [
                    ToolMessage(content="x", tool_call_id=tool_call_id, name="hand_off")
                ]
            },
        )

    def billing(state):
        return {"note": "billing ran"}

    g = StateGraph(TeamState)
    g.add_node(
        "router",
        create_agent(scripted(router=once_then_final("hand_off", {})), tools=[hand_off]),
    )
    g.add_node("billing", billing)
    g.add_edge(START, "router")
    g.add_edge("billing", END)
    app = g.compile()
    out = app.invoke({"messages": [user("go")]}, LIMIT)
    # The tool error is swallowed into a ToolMessage - no exception!
    errors = [text_of(m) for m in out["messages"] if m.type == "tool"]
    return "no exception (error swallowed into ToolMessage)", errors[0][:140] if errors else ""


# ---------------------------------------------------------------------------
# TRAP 4 - create_agent defaults to recursion_limit 9999
# ---------------------------------------------------------------------------


def trap_4_recursion_limit_default():
    """`create_agent` compiles with `{"recursion_limit": 9_999}`.

    A runaway loop therefore makes ~9999 LLM calls before anything stops it.
    Always pass an explicit recursion_limit.
    """
    from langchain.agents.factory import create_agent as _ca
    import inspect

    src = inspect.getsource(_ca)
    line = next((ln.strip() for ln in src.splitlines() if "recursion_limit" in ln), "not found")
    return line


def main() -> None:
    print("=" * 74)
    print("EX05  Command, Send, and the four traps")
    print("=" * 74)

    print("\nCOMMAND - three forms")
    print("-" * 74)
    print(f"  update only        -> {command_update_only()!r}")
    print(f"  goto (same graph)  -> {command_goto_same_graph()!r}")
    print(f"  goto (PARENT)      -> {command_parent_goto()!r}")

    print("\nSEND - parallel fan-out")
    print("-" * 74)
    results = send_fanout()
    print(f"  results ({len(results)} branches): {results}")

    print("\n" + "=" * 74)
    print("THE FOUR TRAPS")
    print("=" * 74)

    kind, detail = trap_1_plain_goto_inside_agent()
    print("\nTRAP 1  plain Command(goto=...) from inside a create_agent tool")
    print("-" * 74)
    print("  a create_agent is a NESTED graph.  A goto inside it looks for the")
    print("  target in the AGENT'S OWN internal graph, does not find it, and")
    print("  logs: 'wrote to unknown channel branch:to:billing, ignoring it'.")
    print(f"  observed: {kind}: {detail}")
    print("  FIX: add graph=Command.PARENT")

    kind, detail = trap_2_missing_tool_message()
    print("\nTRAP 2  Command(update=...) without a matching ToolMessage")
    print("-" * 74)
    print(f"  observed: {kind}")
    print(f"  {detail}")
    print("  FIX: put a ToolMessage(tool_call_id=<the call id>) in the update.")

    kind, detail = trap_3_wrong_injection_annotation()
    print("\nTRAP 3  InjectedToolCallId without Annotated")
    print("-" * 74)
    print(f"  observed: {kind}")
    print(f"  {detail}")
    print("  FIX: tool_call_id: Annotated[str, InjectedToolCallId]")

    line = trap_4_recursion_limit_default()
    print("\nTRAP 4  the 9999 recursion limit")
    print("-" * 74)
    print(f"  create_agent source: {line}")
    print("  FIX: always pass {'recursion_limit': N} in the invoke config.")


if __name__ == "__main__":
    main()
