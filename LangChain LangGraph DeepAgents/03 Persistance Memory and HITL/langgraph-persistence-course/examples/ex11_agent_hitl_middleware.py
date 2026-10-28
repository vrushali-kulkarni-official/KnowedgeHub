"""L18 / M57 - HumanInTheLoopMiddleware: HITL for AGENTS (modern style).

Run:  python ex11_agent_hitl_middleware.py

In LangChain 1.x you do not have to hand-roll `interrupt()` inside an agent.
`HumanInTheLoopMiddleware` gates TOOL CALLS and uses the same interrupt
mechanism under the hood.

    from langchain.agents import create_agent
    from langchain.agents.middleware import HumanInTheLoopMiddleware

    agent = create_agent(
        model,
        tools=[send_email, delete_file],
        middleware=[HumanInTheLoopMiddleware(
            interrupt_on={"send_email": True, "delete_file": True}
        )],
        checkpointer=InMemorySaver(),
    )

Two interrupt modes:

    interrupt_mode="batched"   (DEFAULT) one interrupt per model turn. The
                                value is a HITLRequest listing every gated
                                call; answer with a HITLResponse
                                {"decisions": [...]} - one per call, in order.

    interrupt_mode="per_call"  one interrupt per gated tool call, as the call
                                starts. Answer with a single Decision keyed by
                                the interrupt id. ("per_call" is planned to
                                become the default in the next major release.)

Four decision types:
    {"type": "approve"}                          run the tool as-is
    {"type": "reject", "message": "..."}         do not run it; tell the model
    {"type": "edit", "edited_action": {...}}     run it with different args
    {"type": "respond", "message": "..."}        answer AS the tool (skip it)
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from _common import ScriptedChatModel, banner

SENT = []


def send_email(to: str, subject: str) -> str:
    """Send an email to a person."""
    SENT.append(f"email to {to}: {subject}")
    return f"sent to {to}"


def delete_file(path: str) -> str:
    """Delete a file from disk."""
    SENT.append(f"deleted {path}")
    return f"deleted {path}"


def build_agent(mode: str):
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "send_email", "args": {"to": "alice@example.com",
                                                    "subject": "Report"}, "id": "c1"},
                    {"name": "delete_file", "args": {"path": "/tmp/report.pdf"}, "id": "c2"},
                ],
            ),
            AIMessage(content="Done - I emailed Alice and deleted the report."),
        ]
    )
    agent = create_agent(
        model=model,
        tools=[send_email, delete_file],
        middleware=[
            HumanInTheLoopMiddleware(
                interrupt_on={"send_email": True, "delete_file": True},
                interrupt_mode=mode,
            )
        ],
        checkpointer=InMemorySaver(),
    )
    return agent


def main() -> None:
    banner("1. BATCHED mode (default): one interrupt per model turn")
    agent = build_agent("batched")
    cfg = {"configurable": {"thread_id": "hitl-agent-1"}}

    out = agent.invoke(
        {"messages": [HumanMessage("Email Alice, then delete the report.")]},
        cfg,
        version="v2",
    )
    print("interrupts:", len(out.interrupts))
    payload = out.interrupts[0].value
    print("payload type:", payload.get("type", "HITLRequest"))
    for req in payload["action_requests"]:
        print("   action:", req["name"], req["args"])
    print("review_configs:", payload["review_configs"])
    print("tools run so far:", SENT)

    banner("2. Answer with a HITLResponse: approve one, reject the other")
    out2 = agent.invoke(
        Command(
            resume={
                "decisions": [
                    {"type": "approve"},
                    {"type": "reject", "message": "Keep the report, we might need it."},
                ]
            }
        ),
        cfg,
        version="v2",
    )
    print("tools run now:", SENT)
    print("final message:", out2.value["messages"][-1].content)
    print()
    print("-> The email ran, the delete did NOT.")
    print("-> The model was told about the rejection, so it can react.")

    banner("3. EDIT a tool call before it runs")
    agent2 = build_agent("batched")
    cfg2 = {"configurable": {"thread_id": "hitl-agent-2"}}
    agent2.invoke(
        {"messages": [HumanMessage("Email Alice, then delete the report.")]}, cfg2, version="v2"
    )
    SENT.clear()
    out3 = agent2.invoke(
        Command(
            resume={
                "decisions": [
                    {"type": "approve"},
                    {
                        "type": "edit",
                        "edited_action": {
                            "name": "delete_file",
                            "args": {"path": "/tmp/report-ARCHIVED.pdf"},
                        },
                    },
                ]
            }
        ),
        cfg2,
        version="v2",
    )
    print("tools run:", SENT)
    print("-> the reviewer redirected the deletion to a different path.")

    banner("4. PER_CALL mode: one interrupt per gated tool call")
    agent3 = build_agent("per_call")
    cfg3 = {"configurable": {"thread_id": "hitl-agent-3"}}
    p1 = agent3.invoke(
        {"messages": [HumanMessage("Email Alice, then delete the report.")]}, cfg3, version="v2"
    )
    print("interrupts exposed:", len(p1.interrupts))
    for i in p1.interrupts:
        print("   id:", i.id[:8], "| value:", i.value)
        print("   response_schema:", i.response_schema)

    banner("5. Answer the first one, the second appears next")
    SENT.clear()
    first_id = p1.interrupts[0].id
    p2 = agent3.invoke(Command(resume={first_id: {"type": "approve"}}), cfg3, version="v2")
    print("interrupts now:", len(p2.interrupts))
    for i in p2.interrupts:
        print("   id:", i.id[:8], "| value:", i.value)
    print("tools run after approving the FIRST call:", SENT)
    print("   -> in per_call mode an approval executes that tool IMMEDIATELY,")
    print("      while the next gated call is still waiting for a decision.")
    second_id = p2.interrupts[0].id
    p3 = agent3.invoke(Command(resume={second_id: {"type": "reject", "message": "no"}}),
                       cfg3, version="v2")
    print("tools run in total:", SENT)
    print("final:", p3.value["messages"][-1].content)
    print("message trail:")
    for m in p3.value["messages"]:
        print(f"   {m.type:<6} tool={getattr(m, 'name', None)!s:<12} {str(m.content)[:50]!r}")

    banner("6. RESPOND: answer as the tool, without running it")
    agent4 = build_agent("per_call")
    cfg4 = {"configurable": {"thread_id": "hitl-agent-4"}}
    p4 = agent4.invoke(
        {"messages": [HumanMessage("Email Alice, then delete the report.")]}, cfg4, version="v2"
    )
    id1 = p4.interrupts[0].id
    SENT.clear()
    agent4.invoke(
        Command(resume={id1: {"type": "respond", "message": "Alice said yes!"}}),
        cfg4,
        version="v2",
    )
    print("tools run:", SENT, "(empty - the tool never ran)")
    print("-> 'respond' injects a synthetic ToolMessage instead of executing.")

    banner("7. How to see a paused agent from your API")
    agent5 = build_agent("batched")
    cfg5 = {"configurable": {"thread_id": "hitl-agent-5"}}
    agent5.invoke({"messages": [HumanMessage("delete it")]}, cfg5, version="v2")
    snap = agent5.get_state(cfg5)
    print("next       :", snap.next)
    print("interrupts :", snap.interrupts)
    print("-> your API can poll get_state(thread) to find pending approvals.")


if __name__ == "__main__":
    main()
