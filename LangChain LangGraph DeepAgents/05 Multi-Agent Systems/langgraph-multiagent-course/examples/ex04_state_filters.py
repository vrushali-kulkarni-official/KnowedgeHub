"""EX04 — State filters: what actually crosses an agent boundary.

Run:  PYTHONPATH=examples .venv/bin/python examples/ex04_state_filters.py

"State filters" is the least glamorous and most important part of multi-agent
design.  When agent A hands work to agent B, exactly WHAT travels is decided
by LangGraph's schemas - not by you, at runtime, by accident.

This example proves three rules, all verified against langgraph 1.2.20:

  RULE 1  A node's `input_schema` filters the state it receives on a NORMAL
          edge.  Extra keys are dropped.

  RULE 2  A `Send(...)` payload BYPASSES the target node's `input_schema`.
          Whatever you put in the payload is delivered verbatim.
          => Never put secrets in a Send payload.

  RULE 3  A `Command(graph=Command.PARENT, update={...})` update IS filtered
          by the PARENT graph's state schema.  Unknown keys are dropped
          silently (no error, no warning).
"""

from __future__ import annotations

from typing import Annotated

from langchain.agents import AgentState, create_agent
from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send

from _common import make_scripted, once_then_final, scripted, text_of, user

LIMIT = {"recursion_limit": 20}


class FullState(AgentState):
    """The graph's full state - including a key we would rather not share."""

    public_note: str
    secret_note: str


class NarrowState(AgentState):
    """What a well-behaved node is allowed to see."""

    public_note: str


# ---------------------------------------------------------------------------
# RULE 1 - input_schema filters a normal edge
# ---------------------------------------------------------------------------


def rule_1_normal_edge_filters():
    seen: dict = {}

    def narrow_node(state):
        seen.update(state)
        return {}

    g = StateGraph(FullState)
    g.add_node("narrow", narrow_node, input_schema=NarrowState)
    g.add_edge(START, "narrow")
    g.add_edge("narrow", END)
    app = g.compile()
    app.invoke({"messages": [user("hi")], "public_note": "P", "secret_note": "S"}, LIMIT)
    return seen


# ---------------------------------------------------------------------------
# RULE 2 - Send payloads bypass input_schema
# ---------------------------------------------------------------------------


def rule_2_send_bypasses_filter():
    seen: dict = {}

    def narrow_node(state):
        seen.update(state)
        return {}

    def fanout(state):
        # The payload is delivered VERBATIM - the target's input_schema is
        # NOT applied to it.
        return [Send("narrow", {"public_note": "P", "secret_note": "LEAKED"})]

    g = StateGraph(FullState)
    g.add_node("start", lambda s: {})
    g.add_node("narrow", narrow_node, input_schema=NarrowState)
    g.add_edge(START, "start")
    g.add_conditional_edges("start", fanout, ["narrow"])
    g.add_edge("narrow", END)
    app = g.compile()
    app.invoke({"messages": [user("hi")], "public_note": "P", "secret_note": "S"}, LIMIT)
    return seen


# ---------------------------------------------------------------------------
# RULE 3 - Command.PARENT updates are filtered by the parent schema
# ---------------------------------------------------------------------------


def rule_3_command_parent_filters():
    seen: dict = {}

    @tool
    def handoff(tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
        """Hand off, carrying an extra key that the parent does not declare."""
        return Command(
            graph=Command.PARENT,
            goto="target",
            update={
                "messages": [
                    ToolMessage(content="handing over", tool_call_id=tool_call_id, name="handoff")
                ],
                "public_note": "note that IS declared",
                "undeclared_key": "dropped by the schema filter",
            },
        )

    def target(state):
        seen.update(state)
        return {}

    g = StateGraph(FullState)
    g.add_node(
        "router",
        create_agent(scripted(router=once_then_final("handoff", {})), tools=[handoff]),
    )
    g.add_node("target", target)
    g.add_edge(START, "router")
    g.add_edge("target", END)
    app = g.compile()
    app.invoke({"messages": [user("hi")], "public_note": "P", "secret_note": "S"}, LIMIT)
    return seen


# ---------------------------------------------------------------------------
# RULE 4 - an agent sees the whole `messages` transcript by default
# ---------------------------------------------------------------------------


def rule_4_agent_sees_all_messages():
    """`create_agent` always gets the full `messages` channel.

    There is no built-in "give this agent only the last 2 messages" knob on
    `create_agent`.  You get that by *not* putting the history in `messages` -
    you summarise it into a shared-state key and pass that instead (L07).
    """
    @tool
    def measure_context(prompt: str) -> str:
        """Echo the size of what the agent was given."""
        return f"{len(prompt)} chars"

    # Build a long transcript, then let the agent see all of it.
    transcript = [user("first question")]
    for i in range(5):
        transcript.append({"role": "assistant", "content": f"answer {i}" * 20})
    transcript.append(user("final question"))

    # The ScriptedChatModel records every invocation, so we can measure
    # exactly what the agent was asked to read.
    m = make_scripted(router=once_then_final("measure_context", {"prompt": "x"}, final="done"))
    agent = create_agent(m, tools=[measure_context])
    agent.invoke({"messages": transcript}, LIMIT)

    # `m.last_seen()` is the full message list the model received.
    seen = m.last_seen()
    return len(seen), sum(len(text_of(x)) for x in seen)


def main() -> None:
    print("=" * 74)
    print("EX04  State filters - what crosses an agent boundary")
    print("=" * 74)

    seen = rule_1_normal_edge_filters()
    print("\nRULE 1  input_schema filters a normal edge")
    print("-" * 74)
    print(f"  node received keys : {sorted(seen.keys())}")
    print(f"  'secret_note' here? {'secret_note' in seen}")
    print("  => filtered. The node never sees undeclared keys.")

    seen = rule_2_send_bypasses_filter()
    print("\nRULE 2  a Send payload BYPASSES input_schema")
    print("-" * 74)
    print(f"  node received keys : {sorted(seen.keys())}")
    print(f"  'secret_note' here? {'secret_note' in seen}  value={seen.get('secret_note')!r}")
    print("  => NOT filtered. Send delivers its payload verbatim.")

    seen = rule_3_command_parent_filters()
    print("\nRULE 3  Command.PARENT updates ARE filtered by the parent schema")
    print("-" * 74)
    print(f"  node received keys : {sorted(seen.keys())}")
    print(f"  'undeclared_key' here? {'undeclared_key' in seen}")
    print("  => filtered, and SILENTLY - no exception, no warning.")

    n_msgs, n_chars = rule_4_agent_sees_all_messages()
    print("\nRULE 4  an agent sees the entire `messages` transcript")
    print("-" * 74)
    print(f"  transcript messages : {n_msgs}")
    print(f"  chars the model saw : {n_chars}")
    print("  => there is no per-agent message window on `create_agent`.")
    print("     Control context by summarising into shared state (L07).")

    print()
    print("=" * 74)
    print("PRACTICAL CONSEQUENCES")
    print("=" * 74)
    print(
        """
  * Put only what a node NEEDS in the shared state, and declare a narrow
    `input_schema` for it.
  * Never build a `Send` payload out of "everything in the state" - copy the
    fields you want explicitly.
  * Do not rely on `Command(update=...)` to smuggle a new field into the
    parent: it will be dropped without any error, and you will spend an
    afternoon wondering where your data went.
"""
    )


if __name__ == "__main__":
    main()
