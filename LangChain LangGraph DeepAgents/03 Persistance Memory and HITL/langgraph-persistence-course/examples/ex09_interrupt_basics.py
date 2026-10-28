"""L18 / M57 - interrupt(): pausing a graph for a human.

Run:  python ex09_interrupt_basics.py

THE core HITL mechanism:

    from langgraph.types import interrupt, Command

    decision = interrupt({"question": "...", "options": [...]})   # pauses
    ...                                                          # resumes here

Rules you MUST know:

  * `interrupt()` raises. On the FIRST call it pauses the run and hands the
    value to the caller. On RESUME it *returns* the value you supplied via
    `Command(resume=...)`.
  * The node RESTARTS FROM THE TOP on resume. Every line above the
    `interrupt()` call runs AGAIN. Keep that code idempotent.
  * You need a checkpointer. Without one there is nowhere to pause.
  * Modern shape: `graph.invoke(..., version="v2")` returns a `GraphOutput`
    with `.value` and `.interrupts`. The legacy `__interrupt__` key still
    works but is the old shape.

What is DEPRECATED / what to use instead:

    NodeInterrupt                    -> use `interrupt()` (deprecated since 1.0)
    interrupt_before / interrupt_after
      in compile()                   -> still supported, but they are DEBUGGING
                                       breakpoints, not a HITL mechanism
    GraphInterrupt / GraphBubbleUp   -> internal, never raise these yourself
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from _common import banner


class State(TypedDict, total=False):
    log: Annotated[list[str], operator.add]
    decision: str
    amount: int


def build_graph():
    def prepare(state: State) -> dict:
        # NOTE: this runs AGAIN on resume. It must be idempotent.
        return {"log": ["prepare:validated"]}

    def gate(state: State) -> dict:
        # The value is shown to the human. On resume this call RETURNS their answer.
        decision = interrupt(
            {
                "question": "Approve this refund?",
                "amount": state.get("amount"),
                "options": ["approve", "reject"],
            }
        )
        return {"log": [f"gate:{decision}"], "decision": decision}

    def execute(state: State) -> dict:
        return {"log": [f"execute:{state.get('decision')}"]}

    g = StateGraph(State)
    g.add_node("prepare", prepare)
    g.add_node("gate", gate)
    g.add_node("execute", execute)
    g.add_edge(START, "prepare")
    g.add_edge("prepare", "gate")
    g.add_edge("gate", "execute")
    g.add_edge("execute", END)
    return g


def main() -> None:
    saver = InMemorySaver()
    graph = build_graph().compile(checkpointer=saver)
    cfg = {"configurable": {"thread_id": "hitl-1"}}

    banner("1. Run until the interrupt")
    out = graph.invoke({"log": [], "amount": 250}, cfg, version="v2")
    print("type      :", type(out).__name__)
    print(".value    :", out.value)
    print(".interrupts:", out.interrupts)
    for i in out.interrupts:
        print("   interrupt.id    :", i.id)
        print("   interrupt.value :", i.value)
    print()
    print("-> The run is PAUSED. The process could end here; the pause is")
    print("   durable because the checkpoint is in the store.")

    banner("1b. The LEGACY shape: out['__interrupt__']")
    print("Without version='v2', invoke() returns a plain dict with a magic key.")
    cfg_legacy = {"configurable": {"thread_id": "hitl-legacy"}}
    legacy = graph.invoke({"log": [], "amount": 1}, cfg_legacy)
    print("keys       :", list(legacy.keys()))
    print("__interrupt__:", legacy["__interrupt__"])
    print()
    print("-> Same information, older shape. New code should use")
    print("   invoke(..., version='v2') and read out.interrupts.")
    print("-> The legacy key still works; it is not hard-deprecated.")

    banner("2. What does the paused thread look like?")
    snap = graph.get_state(cfg)
    print("values    :", snap.values)
    print("next      :", snap.next, "   <- the node that is waiting")
    print("interrupts:", snap.interrupts)
    print("tasks     :", [(t.name, t.state) for t in snap.tasks])
    print()
    print("-> next == ('gate',) tells your API 'this thread is waiting on gate'.")

    banner("3. Resume with Command(resume=...)")
    out2 = graph.invoke(Command(resume="approve"), cfg, version="v2")
    print(".value    :", out2.value)
    print(".interrupts:", out2.interrupts)
    print()
    print("-> 'prepare:validated' appears TWICE: the node restarted from the top.")
    print("   THIS is the single most important HITL gotcha.")

    banner("4. A second thread that gets REJECTED")
    cfg2 = {"configurable": {"thread_id": "hitl-2"}}
    graph.invoke({"log": [], "amount": 99}, cfg2, version="v2")
    out3 = graph.invoke(Command(resume="reject"), cfg2, version="v2")
    print(".value:", out3.value)

    banner("5. Multiple interrupts in ONE node: they pause ONE AT A TIME")

    def two_gates(state: State) -> dict:
        a = interrupt({"question": "first?"})
        b = interrupt({"question": "second?"})
        return {"log": [f"got:{a},{b}"], "decision": f"{a}/{b}"}

    g2 = StateGraph(State)
    g2.add_node("two_gates", two_gates)
    g2.add_edge(START, "two_gates")
    g2.add_edge("two_gates", END)
    graph2 = g2.compile(checkpointer=saver)
    cfg3 = {"configurable": {"thread_id": "hitl-3"}}

    p1 = graph2.invoke({"log": []}, cfg3, version="v2")
    print("pause #1 interrupts:", [(i.id[:8], i.value) for i in p1.interrupts])
    print("-> Only ONE interrupt is exposed. The second one has not been")
    print("   reached yet, so there is nothing to answer.")

    banner("6. Answering by interrupt ID")
    ids = [i.id for i in p1.interrupts]
    p2 = graph2.invoke(Command(resume={ids[0]: "A"}), cfg3, version="v2")
    print("pause #2 interrupts:", [(i.id[:8], i.value) for i in p2.interrupts])
    ids2 = [i.id for i in p2.interrupts]
    p3 = graph2.invoke(Command(resume={ids2[0]: "B"}), cfg3, version="v2")
    print("final:", p3.value)
    print()
    print("-> resume values are matched BY ID when you pass a dict,")
    print("   or BY ORDER when you pass a bare value.")
    print("   The resume list is scoped to the task that raised the interrupt,")
    print("   so two parallel tasks never steal each other's answers.")

    banner("7. update_state() BEFORE resuming: edit the paused state")
    cfg5 = {"configurable": {"thread_id": "hitl-5"}}
    graph.invoke({"log": [], "amount": 500}, cfg5, version="v2")
    print("before  :", graph.get_state(cfg5).values)
    graph.update_state(cfg5, {"amount": 10})   # a human lowers the amount
    print("after   :", graph.get_state(cfg5).values)
    out6 = graph.invoke(Command(resume="approve"), cfg5, version="v2")
    print("final   :", out6.value)
    print("-> The interrupt VALUE was built from the OLD amount (500), because")
    print("   the question was already rendered before the edit.")
    print("   If you want the edited value, read state after update_state.")

    banner("8. Structured answers with response_schema")
    from pydantic import BaseModel

    class Decision(BaseModel):
        approve: bool
        reason: str

    def typed_gate(state: State) -> dict:
        d = interrupt(
            {"question": "Approve?"},
            response_schema=Decision,
        )
        return {"log": [f"typed:{d.approve}:{d.reason}"], "decision": str(d.approve)}

    g3 = StateGraph(State)
    g3.add_node("typed_gate", typed_gate)
    g3.add_edge(START, "typed_gate")
    g3.add_edge("typed_gate", END)
    graph3 = g3.compile(checkpointer=saver)
    cfg6 = {"configurable": {"thread_id": "hitl-6"}}
    p = graph3.invoke({"log": []}, cfg6, version="v2")
    print("interrupt:", p.interrupts[0].value)
    print("response_schema:", p.interrupts[0].response_schema)
    p = graph3.invoke(Command(resume={"approve": True, "reason": "looks fine"}), cfg6, version="v2")
    print("final:", p.value)


if __name__ == "__main__":
    main()
