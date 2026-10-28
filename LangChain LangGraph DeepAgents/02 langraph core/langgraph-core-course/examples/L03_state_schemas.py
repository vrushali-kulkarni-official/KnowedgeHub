"""
L03 - State & schema types.

Demonstrates:
  1. TypedDict vs Pydantic vs dataclass states.
  2. MessagesState and what it actually is.
  3. input_schema / output_schema separation.
  4. Private state via add_node(input_schema=...).
  5. NotRequired optional keys.

Run:  uv run python examples/L03_state_schemas.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import get_type_hints
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pydantic import BaseModel, Field
from typing_extensions import NotRequired, TypedDict

from langgraph.graph import END, START, MessagesState, StateGraph

from lgc.printing import section, show_state


# --------------------------------------------------------------------------
# 1. Three schema flavours
# --------------------------------------------------------------------------
class TDState(TypedDict):
    ticket: str
    category: str


class PydState(BaseModel):
    ticket: str
    category: str = "unknown"
    snippets: list[str] = Field(default_factory=list)


@dataclass
class DCState:
    ticket: str
    category: str = "unknown"
    snippets: list[str] = field(default_factory=list)


def pyd_node(state: PydState) -> dict:
    return {"category": "question", "snippets": ["doc-1"]}


def dc_node(state: DCState) -> dict:
    return {"category": "question", "snippets": ["doc-1"]}


# --------------------------------------------------------------------------
# 3. input / output schema separation
# --------------------------------------------------------------------------
class InputState(TypedDict):
    question: str


class OutputState(TypedDict):
    answer: str


class OverallState(InputState, OutputState):
    pass


def answer_node(state: InputState) -> OverallState:
    return {"answer": "bye", "question": state["question"]}


# --------------------------------------------------------------------------
# 4. Private state
# --------------------------------------------------------------------------
class PubState(TypedDict):
    a: str


class Node1Output(TypedDict):
    private_data: str


class Node2Input(TypedDict):
    private_data: str


def node_1(state: PubState) -> Node1Output:
    print("  node_1 sees :", state)
    return {"private_data": "set by node_1"}


def node_2(state: Node2Input) -> PubState:
    print("  node_2 sees :", state, "  <- private_data visible")
    return {"a": "set by node_2"}


def node_3(state: PubState) -> PubState:
    print("  node_3 sees :", state, "  <- private_data NOT visible")
    return {"a": "set by node_3"}


# --------------------------------------------------------------------------
# 5. Optional keys
# --------------------------------------------------------------------------
class OptionalState(TypedDict):
    required: str
    optional: NotRequired[list[str]]


def main() -> None:
    section("1. TypedDict state")
    g_td = (
        StateGraph(TDState)
        .add_node("n", lambda s: {"category": "question"})
        .add_edge(START, "n")
        .add_edge("n", END)
        .compile()
    )
    print("result:", g_td.invoke({"ticket": "hi", "category": "unknown"}))

    section("2. Pydantic state (input is VALIDATED at the boundary)")
    g_pyd = (
        StateGraph(PydState)
        .add_node("n", pyd_node)
        .add_edge(START, "n")
        .add_edge("n", END)
        .compile()
    )
    print("valid  :", g_pyd.invoke({"ticket": "hi"}))
    try:
        g_pyd.invoke({"ticket": 123})  # wrong type
    except Exception as exc:
        print(f"invalid: {type(exc).__name__} (caught at the graph boundary)")

    section("3. dataclass state")
    g_dc = (
        StateGraph(DCState)
        .add_node("n", dc_node)
        .add_edge(START, "n")
        .add_edge("n", END)
        .compile()
    )
    print("result:", g_dc.invoke({"ticket": "hi"}))

    section("4. MessagesState is just an Annotated list")
    print("raw annotations:", MessagesState.__annotations__)
    # Because `from __future__ import annotations` turns annotations into strings,
    # resolve them with get_type_hints(..., include_extras=True) to see the
    # Annotated metadata (i.e. the reducer).
    resolved = get_type_hints(MessagesState, include_extras=True)
    print("resolved       :", resolved)
    print("the reducer    :", resolved["messages"].__metadata__)

    section("5. input_schema / output_schema separation")
    g_io = (
        StateGraph(OverallState, input_schema=InputState, output_schema=OutputState)
        .add_node("answer_node", answer_node)
        .add_edge(START, "answer_node")
        .add_edge("answer_node", END)
        .compile()
    )
    out = g_io.invoke({"question": "hi"})
    print("output:", out)
    print("-> 'question' is filtered OUT by the output schema")

    section("6. Private state (add_node(input_schema=...))")
    # NOTE: add_sequence() takes callables, not names. When a node has a
    # custom input_schema you must add it with add_node(...) and wire it with
    # add_edge(...), otherwise the schema is lost.
    g_priv = (
        StateGraph(PubState)
        .add_node("node_1", node_1, input_schema=PubState)
        .add_node("node_2", node_2, input_schema=Node2Input)
        .add_node("node_3", node_3, input_schema=PubState)
        .add_edge(START, "node_1")
        .add_edge("node_1", "node_2")
        .add_edge("node_2", "node_3")
        .compile()
    )
    print("final output:", g_priv.invoke({"a": "set at start"}))
    print("-> private_data never appears in the public output")

    section("7. Optional keys with NotRequired")
    g_opt = (
        StateGraph(OptionalState)
        .add_node("n", lambda s: {"required": s["required"] + "!"})
        .add_edge(START, "n")
        .add_edge("n", END)
        .compile()
    )
    print("result:", g_opt.invoke({"required": "x"}))


if __name__ == "__main__":
    main()
