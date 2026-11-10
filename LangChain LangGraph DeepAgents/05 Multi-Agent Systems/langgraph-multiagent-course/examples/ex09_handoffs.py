"""EX09 - Handoffs and swarms, built the modern way.

Run:  PYTHONPATH=examples .venv/bin/python examples/ex09_handoffs.py

A HANDOFF is different from agents-as-tools (EX06):

  agents-as-tools : the supervisor CALLS a specialist and gets a string back.
                    The specialist is a subroutine.  Control stays with the
                    supervisor.

  handoff         : agent A gives control to agent B.  B continues the
                    conversation.  Control MOVES.  A is done.

Why you might want a handoff instead:
  * the specialist needs to TALK TO THE USER (clarify, confirm, collect data)
  * the specialist must own the rest of the conversation
  * you want a conversation between two peers, not a boss-and-helper

THE MODERN PRIMITIVE
--------------------
`Command(graph=Command.PARENT, goto="<target>", update={...})` returned from a
TOOL inside a `create_agent`.

Why `graph=Command.PARENT`?  Because `create_agent` compiles to a NESTED
graph.  A plain `goto` is resolved inside that nested graph, where your
target node does not exist - it is silently ignored (see EX05, trap 1).

WHY NOT `langgraph-swarm`?
--------------------------
`langgraph-swarm` (PyPI 0.1.0, last release 2025-12-04) is built on the
legacy `langgraph.prebuilt.create_react_agent`, which is DEPRECATED in
LangChain v1 in favour of `langchain.agents.create_agent`.  The package is
therefore pinned to an API that no longer receives updates.  Building the
handoff yourself is about 40 lines - this file is those 40 lines.

THIS FILE ALSO SHOWS
--------------------
  * which state actually crosses a handoff (the state filters),
  * how to stop a handoff PING-PONG (A->B->A->B...).
"""

from __future__ import annotations

from typing import Annotated

from langchain.agents import AgentState, create_agent
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from _common import once_per_turn, once_then_final, scripted, text_of, user

LIMIT = {"recursion_limit": 20}


# ---------------------------------------------------------------------------
# The team state
# ---------------------------------------------------------------------------


class TeamState(AgentState):
    """The PARENT's state.

    `handoff_log` records who took over.  `visits` counts how many times
    each agent was handed to - the guard against ping-pong loops.
    """

    # MERGE reducer (last-write-wins per key).  A merge reducer is safe to
    # put in an agent's state schema - see PeerAgentState below.
    visits: Annotated[dict[str, int], lambda a, b: {**a, **b}]

    # APPEND reducer.  This one must NOT be in the agent's state schema -
    # see the "echo" trap in PeerAgentState.
    handoff_log: Annotated[list[str], lambda a, b: a + b]

    answer: str
    current_agent: str


class PeerAgentState(AgentState):
    """The AGENT's state - deliberately SMALLER than the parent's.

    THE ECHO TRAP
    -------------
    When you add a compiled agent to a graph as a node, the agent writes its
    ENTIRE state back to the parent when it finishes.  If that state
    contains an APPEND-reducer list, the parent's list gets the agent's
    STALE copy appended too - so every list entry appears TWICE.

      parent handoff_log = ["a->b"]
      agent   handoff_log = ["a->b"]   (its stale input)
      parent  += agent's copy            -> ["a->b", "a->b"]

    Fix: give the agent a state schema with ONLY what it needs.  Merge
    reducers (dicts) are immune, because merging a dict with itself is a
    no-op.  Append reducers (lists) are not.
    """

    visits: Annotated[dict[str, int], lambda a, b: {**a, **b}]


# ---------------------------------------------------------------------------
# 1. The basic handoff
# ---------------------------------------------------------------------------


def build_handoff_team():
    """Two peers.  `triage` hands off to `billing`; `billing` answers."""

    @tool
    def hand_off_to_billing(
        question: str,
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """Give control to the billing specialist. Use for invoices/payments."""
        return Command(
            graph=Command.PARENT,
            goto="billing",
            update={
                "messages": [
                    ToolMessage(
                        content=f"Handing over: {question}",
                        tool_call_id=tool_call_id,
                        name="hand_off_to_billing",
                    )
                ],
                "handoff_log": ["triage -> billing"],
                "current_agent": "billing",
            },
        )

    @tool
    def hand_off_to_support(
        question: str,
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """Give control to the support specialist. Use for access/login/bugs."""
        return Command(
            graph=Command.PARENT,
            goto="support",
            update={
                "messages": [
                    ToolMessage(
                        content=f"Handing over: {question}",
                        tool_call_id=tool_call_id,
                        name="hand_off_to_support",
                    )
                ],
                "handoff_log": ["triage -> support"],
                "current_agent": "support",
            },
        )

    triage = create_agent(
        scripted(router=once_then_final("hand_off_to_billing", {"question": "invoice?"})),
        tools=[hand_off_to_billing, hand_off_to_support],
        system_prompt="Route the customer to the right specialist.",
        name="triage",
    )

    billing = create_agent(
        scripted(responses=[AIMessage(content="Invoice INV-9 is 12 EUR, paid on the 3rd.")]),
        tools=[],
        system_prompt="You are the billing specialist.",
        name="billing",
    )

    support = create_agent(
        scripted(responses=[AIMessage(content="I can help - please confirm your email.")]),
        tools=[],
        system_prompt="You are the support specialist.",
        name="support",
    )

    g = StateGraph(TeamState)
    g.add_node("triage", triage)
    g.add_node("billing", billing)
    g.add_node("support", support)
    g.add_edge(START, "triage")
    g.add_edge("billing", END)
    g.add_edge("support", END)
    return g.compile()


# ---------------------------------------------------------------------------
# 2. A hand-built swarm with ping-pong protection
# ---------------------------------------------------------------------------


def build_swarm():
    """Three peers that hand off to each other - with a loop guard.

    FOUR design rules, all learned the hard way:

    RULE A  A node that returns `Command(goto=...)` must NOT also have a
            conditional edge.  Both would fire, the target node would run
            TWICE in parallel, and two writes to a last-value channel raise
            `InvalidUpdateError: Can receive only one value per step`.

    RULE B  The loop guard lives INSIDE the handoff tool, not in the graph.
            The tool reads the visit counter with `InjectedState` and
            refuses to hand off when the target has been visited too often.

    RULE C  To inject state into a tool, the agent must be created with a
            `state_schema=` that declares the key.  The default schema
            (`AgentState`) has no `visits`, so the injection fails with
            `KeyError: 'visits'`.

    RULE D  The agent's state schema must be SMALLER than the parent's, and
            must not contain APPEND-reducer lists (the "echo" trap).
    """

    MAX_VISITS = 2
    PEERS = ["triage", "researcher", "writer"]

    def make_peer(name: str):
        """A peer that can hand off to any other peer, with a visit guard."""

        @tool(f"hand_off_from_{name}", description="Give control to another specialist.")
        def hand_off(
            target: str,
            note: str,
            tool_call_id: Annotated[str, InjectedToolCallId],
            state: Annotated[PeerAgentState, InjectedState],
        ) -> Command:
            visits = dict((state or {}).get("visits", {}) or {})
            seen = visits.get(target, 0)

            if seen >= MAX_VISITS:
                # Guard hit: stop the swarm instead of looping forever.
                return Command(
                    graph=Command.PARENT,
                    goto=END,
                    update={
                        "messages": [
                            ToolMessage(
                                content=f"{name} stopped: {target} already visited {seen}x",
                                tool_call_id=tool_call_id,
                                name=f"hand_off_from_{name}",
                            )
                        ],
                        "handoff_log": [f"{name} -> STOP (visit limit for {target})"],
                        "current_agent": name,
                    },
                )

            visits[target] = seen + 1
            return Command(
                graph=Command.PARENT,
                goto=target,
                update={
                    "messages": [
                        ToolMessage(
                            content=f"{name} -> {target}: {note}",
                            tool_call_id=tool_call_id,
                            name=f"hand_off_from_{name}",
                        )
                    ],
                    "handoff_log": [f"{name} -> {target}"],
                    "current_agent": target,
                    "visits": visits,
                },
            )

        # Each peer hands off to the NEXT peer in a fixed rotation; a real
        # swarm lets the model pick `target` freely.
        nxt = PEERS[(PEERS.index(name) + 1) % len(PEERS)]
        model = scripted(
            router=once_per_turn(
                f"hand_off_from_{name}",
                {"target": nxt, "note": "over to you"},
            )
        )
        # state_schema= is REQUIRED for InjectedState to find `visits`,
        # and it must stay NARROW (RULE D).
        return create_agent(model, tools=[hand_off], name=name, state_schema=PeerAgentState)

    agents = {p: make_peer(p) for p in PEERS}

    g = StateGraph(TeamState)
    for p in PEERS:
        # RULE A: no conditional edges from these nodes.  The Command's
        # `goto` is the only thing that moves control.
        g.add_node(p, agents[p])
    g.add_edge(START, "triage")
    return g.compile(), MAX_VISITS


def main() -> None:
    print("=" * 74)
    print("EX09  Handoffs and swarms")
    print("=" * 74)

    print("\n1. The basic handoff")
    print("-" * 74)
    app = build_handoff_team()
    out = app.invoke(
        {
            "messages": [user("Why was I charged 12 EUR?")],
            "handoff_log": [],
            "visits": {},
            "answer": "",
            "current_agent": "",
        },
        LIMIT,
    )
    print(f"  handoff_log   : {out['handoff_log']}")
    print(f"  current_agent : {out['current_agent']}")
    print("  transcript:")
    for m in out["messages"]:
        print(f"     {m.type:<10} | {text_of(m)[:66]}")

    print("\n  THE PRIMITIVE THAT MADE IT WORK")
    print("  ---------------------------")
    print("      Command(graph=Command.PARENT, goto='billing', update={...})")
    print("  graph=Command.PARENT is REQUIRED: create_agent is a nested graph,")
    print("  so a plain goto would look for 'billing' inside the agent's own")
    print("  internal graph, not find it, and silently drop the instruction.")
    print()
    print("  STATE THAT CROSSED THE HANDOFF")
    print("  ---------------------------")
    print("  messages    - the WHOLE transcript, including the handoff ToolMessage")
    print("  handoff_log - appended by the reducer")
    print("  visits      - merged by the reducer")
    print("  answer      - NOT set by the handoff (the specialist sets it later)")
    print("  Anything not in TeamState is silently dropped (EX04, rule 3).")

    print("\n2. A hand-built swarm with a loop guard")
    print("-" * 74)
    swarm, max_visits = build_swarm()
    out2 = swarm.invoke(
        {
            "messages": [user("Write about LangGraph")],
            "handoff_log": [],
            "visits": {},
            "answer": "",
            "current_agent": "",
        },
        LIMIT,
    )
    print(f"  handoff path : {out2['handoff_log']}")
    print(f"  visits       : {out2['visits']}")
    print("  (each entry appears ONCE - the echo trap is avoided because")
    print("   handoff_log is not in the agent's state schema)")
    print(f"  max visits   : {max_visits} per agent")
    print()
    print("  The guard fired and stopped the swarm instead of looping.")
    print("  Try raising MAX_VISITS to 5 and watch the path get longer.")

    print()
    print("=" * 74)
    print("PING-PONG: THE #1 SWARM BUG")
    print("=" * 74)
    print(
        """
  Two agents that keep handing back to each other will burn your entire
  budget.  Three defences, use all three:

  1. A VISITS COUNTER (above).  Cheap, explicit, and it shows up in your
     traces so you can see the loop after the fact.

  2. `RemainingSteps` from `langgraph.managed` - LangGraph's built-in
     "how many steps have I got left" primitive.  Inject it into a tool and
     refuse to hand off when it is low:

         from langgraph.managed import RemainingSteps

         @tool
         def hand_off(target: str, remaining: RemainingSteps) -> Command: ...

  3. `ModelCallLimitMiddleware` / `ToolCallLimitMiddleware` (L09) - a hard
     backstop at the model layer, whatever the graph does.

  NEVER rely on `recursion_limit` alone: create_agent ships with 9999.
"""
    )


if __name__ == "__main__":
    main()
