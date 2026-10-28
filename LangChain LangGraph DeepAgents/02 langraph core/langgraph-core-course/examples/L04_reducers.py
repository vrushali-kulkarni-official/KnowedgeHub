"""
L04 - Reducers. THE most important lesson in Phase 7.

Demonstrates:
  1. State-as-channels: every key is an independent channel with a reducer.
  2. The default is OVERWRITE -> silently lost messages (the classic bug).
  3. operator.add as an append reducer (and why parallel order is undefined).
  4. add_messages: IDs, replace-by-ID, RemoveMessage, coercion.
  5. Custom reducers and the rules they must follow.
  6. Overwrite to bypass a reducer.
  7. The 'errors: []' merge trap.
  8. Debugging: reading a graph's channel configuration.

Run:  uv run python examples/L04_reducers.py
"""

from __future__ import annotations

import operator
import sys
from pathlib import Path
from typing import Annotated, Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage
from typing_extensions import TypedDict

from langgraph.errors import InvalidUpdateError
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Overwrite

from lgc.printing import section, show_state


# --------------------------------------------------------------------------
# 2. NO reducer -> overwrite -> silent message loss
# --------------------------------------------------------------------------
class NoReducerState(TypedDict):
    messages: list


def n_a(state: NoReducerState) -> dict:
    return {"messages": [AIMessage("A")]}


def n_b(state: NoReducerState) -> dict:
    return {"messages": [AIMessage("B")]}


# --------------------------------------------------------------------------
# 3. operator.add
# --------------------------------------------------------------------------
class AppendState(TypedDict):
    snippets: Annotated[list[str], operator.add]


# --------------------------------------------------------------------------
# 4. add_messages
# --------------------------------------------------------------------------
class MsgState(TypedDict):
    messages: Annotated[list[Any], add_messages]


# --------------------------------------------------------------------------
# 5. Custom reducers
# --------------------------------------------------------------------------
def merge_dicts(left: dict, right: dict) -> dict:
    """Merge two dict updates. Must not mutate `left`."""
    return {**left, **right}


def dedupe_append(left: list[str], right: list[str]) -> list[str]:
    """Append while preserving order and dropping duplicates."""
    out = list(left)
    for item in right or []:
        if item not in out:
            out.append(item)
    return out


def last_wins_errors(left: list[str], right: list[str]) -> list[str]:
    """Semantics: 'sticky errors' - an empty right-hand list means
    'no NEW errors' and keeps whatever was already there."""
    return right or left


def latest_verdict_errors(left: list[str], right: list[str]) -> list[str]:
    """Semantics: 'latest verdict wins' - an empty right-hand list CLEARS
    the channel, because the last node is authoritative."""
    return list(right)


class CustomState(TypedDict):
    meta: Annotated[dict, merge_dicts]
    tags: Annotated[list[str], dedupe_append]
    errors: Annotated[list[str], operator.add]   # the classic trap


class VerdictState(TypedDict):
    errors: Annotated[list[str], latest_verdict_errors]


# --------------------------------------------------------------------------
# 6. Overwrite
# --------------------------------------------------------------------------
class OverwriteState(TypedDict):
    events: Annotated[list[str], operator.add]


def main() -> None:
    section("1. STATE IS A SET OF CHANNELS")
    print("Every key is an independent channel. Each has its own merge rule.")
    print("A node writing {'draft': 'x'} asks the 'draft' channel's reducer")
    print("how to combine that write with what is already there.\n")

    section("2. THE DEFAULT IS OVERWRITE -> SILENT MESSAGE LOSS")
    g_no = (
        StateGraph(NoReducerState)
        .add_node("A", n_a)
        .add_node("B", n_b)
        .add_edge(START, "A")
        .add_edge("A", "B")
        .add_edge("B", END)
        .compile()
    )
    res = g_no.invoke({"messages": []})
    print("messages after A then B:", [m.content for m in res["messages"]])
    print("!! 'A' is GONE. No error, no warning. This is the #1 LangGraph bug.\n")

    g_par = (
        StateGraph(NoReducerState)
        .add_node("A", n_a)
        .add_node("B", n_b)
        .add_edge(START, "A")
        .add_edge("A", "B")
        .add_edge("B", END)
        .compile()
    )
    print("Now make A and B parallel (both fed by START):")
    g_par2 = (
        StateGraph(NoReducerState)
        .add_node("A", n_a)
        .add_node("B", n_b)
        .add_edge(START, "A")
        .add_edge(START, "B")
        .add_edge("A", END)
        .add_edge("B", END)
        .compile()
    )
    try:
        g_par2.invoke({"messages": []})
    except InvalidUpdateError as exc:
        print(f"InvalidUpdateError: {str(exc).splitlines()[0]}")
        print("-> LangGraph refuses to guess. A reducer makes it well-defined.\n")

    section("3. operator.add AS AN APPEND REDUCER")
    g_app = (
        StateGraph(AppendState)
        .add_node("A", lambda s: {"snippets": ["a"]})
        .add_node("B", lambda s: {"snippets": ["b"]})
        .add_edge(START, "A")
        .add_edge("A", "B")
        .add_edge("B", END)
        .compile()
    )
    print("sequential:", g_app.invoke({"snippets": []})["snippets"])

    g_app_par = (
        StateGraph(AppendState)
        .add_node("A", lambda s: {"snippets": ["a"]})
        .add_node("B", lambda s: {"snippets": ["b"]})
        .add_edge(START, "A")
        .add_edge(START, "B")
        .add_edge("A", END)
        .add_edge("B", END)
        .compile()
    )
    print("parallel  :", g_app_par.invoke({"snippets": []})["snippets"], " <- order undefined")
    print()

    section("4. add_messages - MORE THAN APPENDING")
    g_msg = (
        StateGraph(MsgState)
        .add_node("add_human", lambda s: {"messages": [HumanMessage("hi")]})
        .add_node("add_ai", lambda s: {"messages": [AIMessage("hello")]})
        .add_edge(START, "add_human")
        .add_edge("add_human", "add_ai")
        .add_edge("add_ai", END)
        .compile()
    )
    out = g_msg.invoke({"messages": []})
    print("messages:", [(m.type, m.content, m.id[:8]) for m in out["messages"]])

    print("\n(a) shorthand coercion: {'role': 'user', 'content': 'hey'}")
    g_short = (
        StateGraph(MsgState)
        .add_node("n", lambda s: {"messages": [{"role": "user", "content": "hey"}]})
        .add_edge(START, "n")
        .add_edge("n", END)
        .compile()
    )
    out2 = g_short.invoke({"messages": []})
    print("    ->", type(out2["messages"][0]).__name__, out2["messages"][0].content)

    print("\n(b) replace-by-ID: writing the same id UPDATES instead of appending")
    g_repl = (
        StateGraph(MsgState)
        .add_node("add", lambda s: {"messages": [AIMessage("first", id="m1")]})
        .add_node("edit", lambda s: {"messages": [AIMessage("edited", id="m1")]})
        .add_edge(START, "add")
        .add_edge("add", "edit")
        .add_edge("edit", END)
        .compile()
    )
    out3 = g_repl.invoke({"messages": []})
    print("    ->", len(out3["messages"]), "message:", out3["messages"][0].content)

    print("\n(c) RemoveMessage deletes a message")
    g_rm = (
        StateGraph(MsgState)
        .add_node(
            "add",
            lambda s: {"messages": [HumanMessage("keep", id="h1"), HumanMessage("drop", id="h2")]},
        )
        .add_node(
            "rm",
            lambda s: {"messages": [RemoveMessage(id="h2")]},
        )
        .add_edge(START, "add")
        .add_edge("add", "rm")
        .add_edge("rm", END)
        .compile()
    )
    out4 = g_rm.invoke({"messages": []})
    print("    ->", [m.content for m in out4["messages"]])

    section("5. CUSTOM REDUCERS")
    g_cust = (
        StateGraph(CustomState)
        .add_node("A", lambda s: {"meta": {"a": 1}, "tags": ["x"], "errors": ["bad sql"]})
        .add_node("B", lambda s: {"meta": {"b": 2}, "tags": ["x", "y"], "errors": []})
        .add_edge(START, "A")
        .add_edge("A", "B")
        .add_edge("B", END)
        .compile()
    )
    out5 = g_cust.invoke({"meta": {}, "tags": [], "errors": []})
    show_state(out5, "merged state")
    print(
        "meta  -> dicts merged        : {'a': 1, 'b': 2}\n"
        "tags  -> deduped on append   : ['x', 'y']  (the second 'x' dropped)\n"
        "errors-> operator.add TRAP   : ['bad sql'] - node B wrote [] meaning\n"
        "        'no errors', but CONCATENATION kept the old error alive."
    )

    print("\nThe same thing with a 'latest verdict wins' reducer:")
    g_verdict = (
        StateGraph(VerdictState)
        .add_node("A", lambda s: {"errors": ["bad sql"]})
        .add_node("B", lambda s: {"errors": []})
        .add_edge(START, "A")
        .add_edge("A", "B")
        .add_edge("B", END)
        .compile()
    )
    print("  errors:", g_verdict.invoke({"errors": []})["errors"], " <- cleared")
    print(
        "\n-> A reducer is a MERGE RULE. If two nodes mean different things by\n"
        "   the same write, pick the semantics on purpose."
    )

    section("6. Overwrite - BYPASS THE REDUCER")
    g_ow = (
        StateGraph(OverwriteState)
        .add_node("add", lambda s: {"events": ["e1", "e2"]})
        .add_node("reset", lambda s: {"events": Overwrite([])})
        .add_node("json_form", lambda s: {"events": {"__overwrite__": ["only-me"]}})
        .add_edge(START, "add")
        .add_edge("add", "reset")
        .add_edge("reset", "json_form")
        .add_edge("json_form", END)
        .compile()
    )
    print("events:", g_ow.invoke({"events": []})["events"])

    section("7. DEBUGGING: READ THE GRAPH'S CHANNEL CONFIG")
    g_dbg = (
        StateGraph(MsgState)
        .add_node("n", lambda s: {"messages": [AIMessage("x")]})
        .add_edge(START, "n")
        .add_edge("n", END)
        .compile()
    )
    for name, ch in g_dbg.channels.items():
        print(f"  channel {name!r}: {type(ch).__name__}")
    print("\n-> inspect `graph.channels` when data 'disappears'.")
    print("   (note: it is on the COMPILED graph, not on get_graph())")


if __name__ == "__main__":
    main()
