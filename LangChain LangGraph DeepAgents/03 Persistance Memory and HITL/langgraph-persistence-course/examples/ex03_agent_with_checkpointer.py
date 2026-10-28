"""L15 / M54 - Attaching a checkpointer to an AGENT (create_agent).

Run:  python ex03_agent_with_checkpointer.py

`create_agent` accepts `checkpointer=` exactly like a StateGraph does. The
agent's state is `AgentState`, whose `messages` channel uses the
`add_messages` reducer, so every turn appends to a persistent history.

This example proves the agent remembers turn 1 when you ask about turn 2 -
by inspecting the actual prompt the model received on the second turn.
"""

from __future__ import annotations

from typing import TypedDict

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from _common import ScriptedChatModel, banner


class GetWeather(TypedDict):
    """Get the current weather for a city."""

    city: str


def get_weather(city: str) -> str:
    """Look up the weather for a city (fake data, real tool signature)."""
    return f"18C and sunny in {city}"


def build_agent():
    model = ScriptedChatModel(
        responses=[
            # turn 1: model asks for the tool
            AIMessage(
                content="",
                tool_calls=[{"name": "get_weather", "args": {"city": "Paris"}, "id": "c1"}],
            ),
            # turn 1: model answers using the tool result
            AIMessage(content="It is 18C and sunny in Paris."),
            # turn 2: model asks for the tool again
            AIMessage(
                content="",
                tool_calls=[{"name": "get_weather", "args": {"city": "Tokyo"}, "id": "c2"}],
            ),
            # turn 2: model answers
            AIMessage(content="It is 18C and sunny in Tokyo."),
        ]
    )
    agent = create_agent(
        model=model,
        tools=[get_weather],
        system_prompt="You are a weather bot.",
        checkpointer=InMemorySaver(),
    )
    return agent, model


def main() -> None:
    agent, model = build_agent()
    cfg = {"configurable": {"thread_id": "conv-1"}}

    banner("1. Turn 1")
    out = agent.invoke({"messages": [HumanMessage("What's the weather in Paris?")]}, cfg)
    print("final:", out["messages"][-1].content)
    print("messages stored:", len(out["messages"]))

    banner("2. What the checkpointer holds right now")
    state = agent.get_state(cfg)
    print("state keys:", list(state.values.keys()))
    for m in state.values["messages"]:
        print(f"  {type(m).__name__:<12} {str(m.content)[:60]!r} "
              f"tool_calls={getattr(m, 'tool_calls', None)}")

    banner("3. Turn 2 - the agent should REMEMBER turn 1")
    out2 = agent.invoke({"messages": [HumanMessage("And in Tokyo?")]}, cfg)
    print("final:", out2["messages"][-1].content)
    print("total messages now:", len(out2["messages"]))

    banner("4. PROOF: what the model actually saw on turn 2")
    # calls[2] is the first model call of turn 2.
    turn2_prompt = model.calls[2].messages
    print(f"prompt length: {len(turn2_prompt)} messages")
    for m in turn2_prompt:
        print(f"  {type(m).__name__:<12} {str(m.content)[:70]!r}")
    print()
    print("-> The Paris question from turn 1 is in the prompt.")
    print("-> Without a checkpointer this prompt would contain ONLY turn 2.")

    banner("5. A second thread is a separate conversation")
    cfg2 = {"configurable": {"thread_id": "conv-2"}}
    agent.invoke({"messages": [HumanMessage("hello, fresh thread")]}, cfg2)
    s2 = agent.get_state(cfg2)
    print("conv-2 messages:", len(s2.values["messages"]))
    print("conv-1 messages:", len(agent.get_state(cfg).values["messages"]))

    banner("6. inspect: full message roles for conv-1")
    for m in agent.get_state(cfg).values["messages"]:
        print(f"  {m.type:<10} {str(m.content)[:60]!r}")


if __name__ == "__main__":
    main()
