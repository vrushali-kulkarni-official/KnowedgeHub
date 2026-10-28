"""
L07 - Runtime context.

Demonstrates:
  1. context_schema + context= + Runtime.
  2. Reading context in a node AND in a conditional edge.
  3. Context is read-only: a node cannot write to it.
  4. Context is NOT persisted - it never lands in a checkpoint.
  5. The four context types: context vs state vs store vs prompt.
  6. The store (cross-conversation memory).
  7. config_schema is deprecated - what the warning looks like.

Run:  uv run python examples/L07_runtime_context.py
"""

from __future__ import annotations

import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from typing_extensions import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.store.memory import InMemoryStore

from lgc.printing import section


@dataclass
class AppContext:
    user_id: str = "anonymous"
    tier: str = "standard"
    model: Any = None
    extras: dict[str, Any] = field(default_factory=dict)


class State(TypedDict):
    question: str
    answer: str
    route: str


def answer_node(state: State, runtime: Runtime[AppContext]) -> dict:
    user = runtime.context.user_id
    tier = runtime.context.tier
    print(f"  [node] user_id={user!r} tier={tier!r}")
    # NOTE: we deliberately do NOT copy user_id into the state - that is
    # exactly what context exists to avoid.
    return {"answer": f"Hello ({tier})"}


def route_node(state: State, runtime: Runtime[AppContext]) -> str:
    """A conditional edge can read the context too."""
    if runtime.context.tier == "enterprise":
        return "fast"
    return "standard"


def fast(state: State) -> dict:
    return {"answer": state["answer"] + " [fast track]"}


def standard(state: State) -> dict:
    return {"answer": state["answer"] + " [standard track]"}


def build():
    builder = StateGraph(State, context_schema=AppContext)
    builder.add_node("answer", answer_node)
    builder.add_node("fast", fast)
    builder.add_node("standard", standard)
    builder.add_edge(START, "answer")
    builder.add_conditional_edges("answer", route_node, {"fast": "fast", "standard": "standard"})
    builder.add_edge("fast", END)
    builder.add_edge("standard", END)
    return builder


def main() -> None:
    section("1. context_schema + context= + Runtime")
    graph = build().compile()
    print("  standard tier:")
    print("   ", graph.invoke({"question": "q", "answer": "", "route": ""},
                              context={"user_id": "u-1", "tier": "standard"}))
    print("  enterprise tier:")
    print("   ", graph.invoke({"question": "q", "answer": "", "route": ""},
                              context={"user_id": "u-2", "tier": "enterprise"}))

    section("2. THE OLD WAY (configurable) vs THE NEW WAY (context)")
    print("  OLD: graph.invoke(inp, {'configurable': {'user_id': 'u-1'}})")
    print("       -> runtime.context.user_id is EMPTY (it's not context)")
    print("  NEW: graph.invoke(inp, context={'user_id': 'u-1'})")
    print("       -> runtime.context.user_id == 'u-1'")

    section("3. CONTEXT IS NOT PERSISTED")
    saver = InMemorySaver()
    g2 = build().compile(checkpointer=saver)
    cfg = {"configurable": {"thread_id": "ctx-1"}}
    g2.invoke({"question": "q", "answer": "", "route": ""}, cfg,
              context={"user_id": "secret-user", "tier": "vip"})
    snap = g2.get_state(cfg)
    print("  checkpointed state:", snap.values)
    print("  -> no user_id in the checkpoint. Context stays in memory only.")

    section("4. THE STORE (cross-conversation memory)")
    store = InMemoryStore()
    g3 = build().compile(store=store)

    def remember(state, runtime: Runtime[AppContext]) -> dict:
        ns = (runtime.context.user_id, "memories")
        runtime.store.put(ns, "preferred_style", {"value": "concise"})
        got = runtime.store.get(ns, "preferred_style")
        print(f"  [node] stored + read back: {got}")
        return {"answer": "remembered"}

    g4 = StateGraph(State, context_schema=AppContext)
    g4.add_node("remember", remember)
    g4.add_edge(START, "remember")
    g4.add_edge("remember", END)
    g4c = g4.compile(store=store)

    g4c.invoke({"question": "q", "answer": "", "route": ""}, context={"user_id": "u-9"})
    # different thread, same store -> the memory is still there
    g4c.invoke({"question": "q", "answer": "", "route": ""}, context={"user_id": "u-9"})
    print("  -> the store outlives the thread; the checkpointer does not")

    section("5. config_schema IS DEPRECATED (warning text)")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            from langgraph.func import entrypoint

            @entrypoint(config_schema=AppContext)  # type: ignore[call-arg]
            def _old(x: int) -> int:
                return x
        except Exception as exc:
            print("  raised:", type(exc).__name__, exc)
        for w in caught:
            print(f"  {w.category.__name__}: {w.message}")


if __name__ == "__main__":
    main()
