"""L18 / M57 - interrupt() in the FUNCTIONAL API, and static breakpoints.

Run:  python ex10_functional_and_breakpoints.py

Part A: `interrupt()` works identically inside `@task` / `@entrypoint`
        (langgraph.func). The rules are the same: it pauses, and on resume the
        enclosing function restarts from the top.

Part B: STATIC breakpoints - `compile(interrupt_before=[...])` and
        `compile(interrupt_after=[...])`.

        These are for DEBUGGING. They break on EVERY run at a fixed node,
        without asking a question. They are NOT a HITL mechanism - you cannot
        answer them with a value; you just resume and the graph continues.

        `NodeInterrupt` (the old way to raise an interrupt by hand) is
        DEPRECATED since LangGraph 1.0 - use `interrupt()`.

        `interrupt_before` / `interrupt_after` are still supported and NOT
        deprecated, but they are a debugging tool, not a product feature.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.func import entrypoint, task
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from _common import banner


# ==========================================================================
# Part A - functional API
# ==========================================================================
def part_a() -> None:
    banner("A. interrupt() inside @task / @entrypoint (functional API)")

    calls = {"prep": 0, "entrypoint": 0}

    @task
    def prepare() -> str:
        calls["prep"] += 1
        return f"prepared#{calls['prep']}"

    @task
    def gate() -> str:
        answer = interrupt({"question": "ship it?", "options": ["yes", "no"]})
        return f"gate:{answer}"

    @entrypoint(checkpointer=InMemorySaver())
    def workflow(x: str) -> str:
        calls["entrypoint"] += 1
        prep = prepare().result()
        g = gate().result()
        return f"{x} | {prep} | {g}"

    cfg = {"configurable": {"thread_id": "func-1"}}

    out = workflow.invoke("run1", cfg, version="v2")
    print("paused  :", out.value, "| interrupts:", out.interrupts)
    print("body executions so far:", calls)

    out2 = workflow.invoke(Command(resume="yes"), cfg, version="v2")
    print("resumed :", out2.value)
    print("body executions now  :", calls)
    print()
    print(">>> IMPORTANT DIFFERENCE FROM GRAPH NODES:")
    print("  * the @entrypoint body re-ran  (entrypoint: 1 -> 2)")
    print("  * the completed @task did NOT re-run (prep stayed at 1)")
    print("    -> LangGraph replayed its result from the checkpoint.")
    print("  * So in the functional API, a task's side effect happens ONCE,")
    print("    while in a StateGraph a node's side effect can happen TWICE")
    print("    (once before the interrupt, once after the resume).")


# ==========================================================================
# Part B - static breakpoints
# ==========================================================================
class State(TypedDict, total=False):
    log: Annotated[list[str], operator.add]


def part_b() -> None:
    banner("B. Static breakpoints: interrupt_before / interrupt_after")

    def a(state: State) -> dict:
        return {"log": ["a"]}

    def b(state: State) -> dict:
        return {"log": ["b"]}

    def c(state: State) -> dict:
        return {"log": ["c"]}

    g = StateGraph(State)
    g.add_node("a", a)
    g.add_node("b", b)
    g.add_node("c", c)
    g.add_edge(START, "a")
    g.add_edge("a", "b")
    g.add_edge("b", "c")
    g.add_edge("c", END)

    saver = InMemorySaver()
    # Break BEFORE `b` runs: you can inspect state, then continue.
    graph = g.compile(checkpointer=saver, interrupt_before=["b"])
    cfg = {"configurable": {"thread_id": "break-1"}}

    out = graph.invoke({"log": []}, cfg, version="v2")
    print("paused before 'b':")
    print("  value     :", out.value)
    print("  interrupts:", out.interrupts)
    snap = graph.get_state(cfg)
    print("  next      :", snap.next, "  <- 'b' has not run yet")
    print("  interrupts on the snapshot:", snap.interrupts)
    print()
    print("-> A static breakpoint produces NO interrupt payload (nothing to")
    print("   answer) - it just stops the run so you can look at it.")

    banner("B2. Resuming from a static breakpoint")
    out2 = graph.invoke(None, cfg, version="v2")
    print("value     :", out2.value)
    print("interrupts:", out2.interrupts)
    print("-> the run continued and finished. No human answer was involved.")

    banner("B3. interrupt_after works the same way")
    graph2 = g.compile(checkpointer=saver, interrupt_after=["b"])
    cfg2 = {"configurable": {"thread_id": "break-2"}}
    out3 = graph2.invoke({"log": []}, cfg2, version="v2")
    print("paused after 'b':", out3.value)
    print("next:", graph2.get_state(cfg2).next)
    out4 = graph2.invoke(None, cfg2, version="v2")
    print("finished:", out4.value)

    banner("B4. WHY static breakpoints are a debugging tool, not HITL")
    print("  * They fire on EVERY run - you cannot show them to a user and")
    print("    wait for an answer.")
    print("  * There is no payload, so there is nothing for a reviewer to read.")
    print("  * They are declared at COMPILE time, not per-request.")
    print()
    print("  For human review use `interrupt()` (dynamic) - it carries a")
    print("  payload and is answered with Command(resume=...).")
    print()
    print("  Modern LangChain 1.x alternative for agent tool approval:")
    print("      from langchain.agents.middleware import HumanInTheLoopMiddleware")
    print("      create_agent(model, tools, middleware=[HumanInTheLoopMiddleware(")
    print("          interrupt_on={\"send_email\": True})])")


if __name__ == "__main__":
    part_a()
    part_b()
