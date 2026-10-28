"""
L06 - Config, threads, persistence and time travel.

Demonstrates:
  1. RunnableConfig, thread_id, recursion_limit.
  2. A checkpointer and a multi-turn conversation.
  3. get_state / get_state_history / update_state.
  4. Time travel: rewind to a checkpoint and re-run.
  5. GraphRecursionError and the proactive RemainingSteps alternative.
  6. Durability modes.
  7. interrupt_before as a debugging knob.

Run:  uv run python examples/L06_config_threads_persistence.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from typing_extensions import TypedDict

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from langgraph.managed import RemainingSteps

from lgc.printing import section, show_state


class ChatState(TypedDict):
    messages: list


def model_node(state: ChatState) -> dict:
    last = state["messages"][-1].content
    return {"messages": [AIMessage(f"echo: {last}")]}


def build_chat():
    return (
        StateGraph(ChatState)
        .add_node("model", model_node)
        .add_edge(START, "model")
        .add_edge("model", END)
        .compile(checkpointer=InMemorySaver())
    )


class LoopState(TypedDict):
    x: str
    steps: RemainingSteps


def loop_node(state: LoopState) -> dict:
    return {"x": state["x"] + "!"}


def main() -> None:
    section("1. MULTI-TURN CONVERSATION (the checkpointer pays off)")
    graph = build_chat()
    config = {"configurable": {"thread_id": "chat-1"}}

    graph.invoke({"messages": [HumanMessage("My name is Ada")]}, config)
    result = graph.invoke({"messages": [HumanMessage("What did I say?")]}, config)
    print("message count:", len(result["messages"]))
    for m in result["messages"]:
        print(f"  {m.type}: {m.content}")

    section("2. A NEW thread_id = A NEW MEMORY")
    other = {"configurable": {"thread_id": "chat-2"}}
    r2 = graph.invoke({"messages": [HumanMessage("hello")]}, other)
    print("message count on thread-2:", len(r2["messages"]))
    print("-> same graph, different thread, different history")

    section("3. get_state - what is the current state?")
    snap = graph.get_state(config)
    print("  values  :", snap.values)
    print("  next    :", snap.next)
    print("  metadata:", {k: snap.metadata.get(k) for k in ("step", "source")})
    print("  NOTE: the state dict is on .values, NOT .state")

    section("4. get_state_history - the checkpoint timeline")
    for s in graph.get_state_history(config):
        print(f"  step={s.metadata.get('step'):>3}  next={s.next}")

    section("5. update_state - write to a thread")
    graph.update_state(config, {"messages": [AIMessage("EDITED BY update_state")]})
    snap2 = graph.get_state(config)
    print("  last message now:", snap2.values["messages"][-1].content)

    section("6. TIME TRAVEL - rewind and re-run")
    history = list(graph.get_state_history(config))
    target = history[-1]  # the earliest checkpoint
    print(f"  rewinding to step {target.metadata.get('step')}")
    graph.invoke(
        {"messages": [HumanMessage("REPLAYED with a different question")]},
        config=target.config,
    )
    snap3 = graph.get_state(config)
    print("  messages now:", [m.content for m in snap3.values["messages"]])

    section("7. recursion_limit + GraphRecursionError")
    loop = (
        StateGraph(LoopState)
        .add_node("loop", loop_node)
        .add_edge(START, "loop")
        .add_edge("loop", "loop")  # infinite cycle
        .compile()
    )
    try:
        loop.invoke({"x": "a", "steps": 0}, {"recursion_limit": 4})
    except GraphRecursionError as exc:
        print(f"  GraphRecursionError: {str(exc).splitlines()[0]}")

    section("8. THE PROACTIVE ALTERNATIVE: RemainingSteps")
    print("  RemainingSteps tells the node how many supersteps are LEFT,")
    print("  so the graph can stop GRACEFULLY instead of blowing the limit.")
    print("  VERIFIED RULE: stop when steps <= 2, NOT steps <= 1.")
    print("  With a margin of 1 the stop decision lands on the very last tick")
    print("  and the run STILL raises GraphRecursionError - even though the")
    print("  final state is correct. Leave >= 2 supersteps of headroom.\n")

    def bounded_node(state: LoopState) -> dict:
        left = state.get("steps", 0)
        print(f"    [node] steps remaining = {left}")
        return {"x": state["x"] + "!"}

    def stop_when_low(state: LoopState) -> str:
        return "stop" if state.get("steps", 0) <= 2 else "keep"

    bounded = (
        StateGraph(LoopState)
        .add_node("loop", bounded_node)
        .add_node("done", lambda s: {"x": s["x"] + "<stopped>"})
        .add_edge(START, "loop")
        .add_conditional_edges("loop", stop_when_low, {"stop": "done", "keep": "loop"})
        .add_edge("done", END)
        .compile()
    )
    out = bounded.invoke({"x": "a", "steps": 0}, {"recursion_limit": 20})
    print("  final x:", out["x"])
    print("  -> no GraphRecursionError; the graph ended on purpose.")

    section("9. DURABILITY MODES")
    for mode in ("sync", "async", "exit"):
        g = build_chat()
        c = {"configurable": {"thread_id": f"dur-{mode}"}}
        g.invoke({"messages": [HumanMessage("hi")]}, c, durability=mode)
        print(f"  durability={mode:<6} -> ok, {len(g.get_state(c).values['messages'])} message(s)")

    section("10. interrupt_before - pause before a node (debugging knob)")
    dbg = (
        StateGraph(ChatState)
        .add_node("model", model_node)
        .add_node("second", lambda s: {"messages": [AIMessage("second")]})
        .add_edge(START, "model")
        .add_edge("model", "second")
        .add_edge("second", END)
        .compile(checkpointer=InMemorySaver(), interrupt_before=["second"])
    )
    c2 = {"configurable": {"thread_id": "dbg-1"}}
    out2 = dbg.invoke({"messages": [HumanMessage("hello")]}, c2)
    print("  stopped before 'second'. state:", out2)
    print("  next node to run:", dbg.get_state(c2).next)


if __name__ == "__main__":
    main()
