"""EX07 - Structured-output routing: how a supervisor decides WHO handles what.

Run:  PYTHONPATH=examples .venv/bin/python examples/ex07_structured_routing.py

A supervisor has to answer one question: "which specialist?"  There are two
ways to do it:

  A) FREE-FORM  - the model calls a tool per specialist (`ask_researcher`,
     `ask_billing`, ...).  The tool IS the routing decision.

  B) STRUCTURED - the model returns a SCHEMA.  You read the schema, and YOU
     decide what to do with it.

(B) is better when you want to:
  * validate the routing decision before spending money on it,
  * log/measure routing accuracy,
  * route to something that is NOT an agent (a Python function, a queue),
  * apply business rules ("if amount > 100, escalate to a human").

In LangChain v1, `response_format=` gives you structured output.  There are
two strategies and the difference matters:

  ToolStrategy      (the default) - the schema is exposed to the model as a
                    synthetic TOOL.  Works with EVERY model, including
                    Gemini, OpenAI, Anthropic, and local models.

  ProviderStrategy  - uses the provider's native structured-output feature.
                    Cleaner (no fake tool call in the transcript), but only
                    works on providers that support it.

This file also reproduces the SILENT RETRY TRAP: if the model returns plain
text when a schema was requested, the agent does not fail - it silently
re-asks, over and over, until the recursion limit.
"""

from __future__ import annotations

from typing import Annotated, Literal

from langchain.agents import AgentState, create_agent
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from _common import ai, once_then_final, scripted, text_of, user

LIMIT = {"recursion_limit": 12}


# ---------------------------------------------------------------------------
# The routing schema
# ---------------------------------------------------------------------------


class Route(BaseModel):
    """Which specialist should handle this request, and why."""

    specialist: Literal["researcher", "billing", "support", "human"]
    reason: str = Field(description="One sentence explaining the routing")
    urgency: Literal["low", "normal", "high"] = Field(default="normal")


# ---------------------------------------------------------------------------
# 1. ToolStrategy - the default, works everywhere
# ---------------------------------------------------------------------------


def tool_strategy_router():
    """The model must emit a tool call NAMED AFTER THE SCHEMA CLASS."""

    def router(messages):
        # `Route` is the schema class name -> that is the synthetic tool name.
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "Route",
                    "args": {
                        "specialist": "billing",
                        "reason": "The user asks about an invoice.",
                        "urgency": "normal",
                    },
                    "id": "route_1",
                    "type": "tool_call",
                }
            ],
        )

    model = scripted(router=router)
    agent = create_agent(model, tools=[], response_format=Route)
    out = agent.invoke({"messages": [user("Why was I charged 49 EUR?")]}, LIMIT)

    sr = out.get("structured_response")
    print(f"  structured_response type : {type(sr).__name__}")
    print(f"  specialist               : {sr.specialist}")
    print(f"  reason                   : {sr.reason}")
    print(f"  urgency                  : {sr.urgency}")
    print("  transcript:")
    for m in out["messages"]:
        print(f"     {m.type:<10} | {text_of(m)[:64]}")
    return sr


# ---------------------------------------------------------------------------
# 2. The silent-retry trap
# ---------------------------------------------------------------------------


def silent_retry_trap():
    """Model returns plain text when a schema was requested -> infinite retry."""

    model = scripted(responses=[ai("I think billing should handle it.")])
    agent = create_agent(model, tools=[], response_format=Route)
    try:
        agent.invoke({"messages": [user("invoice?")]}, LIMIT)
        return "no exception"
    except Exception as exc:
        return f"{type(exc).__name__}: {str(exc).splitlines()[0]}"


# ---------------------------------------------------------------------------
# 3. ProviderStrategy - native structured output
# ---------------------------------------------------------------------------


def provider_strategy_note():
    """ProviderStrategy needs a provider that supports native JSON output."""
    from langchain.agents.structured_output import ProviderStrategy

    try:
        ProviderStrategy(Route)
        return "constructible - but the MODEL must support native structured output"
    except Exception as exc:
        return f"not usable here: {exc}"


# ---------------------------------------------------------------------------
# 4. Routing to real specialists
# ---------------------------------------------------------------------------


# GOTCHA: `add_conditional_edges` inspects the type hints of the dispatch
# function to infer the branch's input schema.  If the state class is
# defined INSIDE a function, the forward reference cannot be resolved and
# you get: NameError: name 'TeamState' is not defined.
# => Define team state schemas at MODULE level.
class TeamState(AgentState):
    """The team's shared state."""

    route: str
    reason: str
    result: str


@tool
def web_search(query: str) -> str:
    """Search the web."""
    return f"web hits for {query}"


def build_specialist(name, tool_obj, final):
    model = scripted(router=once_then_final(tool_obj.name, {"query": "x", "invoice_id": "I-1"}, final=final))
    return create_agent(model, tools=[tool_obj], name=name)


def build_routed_team():
    """A router agent produces a Route; the graph dispatches on it."""

    def router(messages):
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "Route",
                    "args": {"specialist": "researcher", "reason": "needs facts", "urgency": "low"},
                    "id": "route_1",
                    "type": "tool_call",
                }
            ],
        )

    router_agent = create_agent(scripted(router=router), tools=[], response_format=Route, name="router")

    researcher = create_agent(
        scripted(router=once_then_final("web_search", {"query": "langgraph"}, final="3 key findings")),
        tools=[web_search],
        name="researcher",
    )

    def routing_node(state: TeamState):
        result = router_agent.invoke({"messages": state["messages"]}, LIMIT)
        sr = result["structured_response"]
        return {"route": sr.specialist, "reason": sr.reason}

    def research_node(state: TeamState):
        r = researcher.invoke({"messages": state["messages"]}, LIMIT)
        return {"result": text_of(r["messages"][-1])}

    def escalate(state: TeamState):
        return {"result": "Escalated to a human agent."}

    def dispatch(state: TeamState):
        return "research_node" if state.get("route") == "researcher" else "escalate"

    g = StateGraph(TeamState)
    g.add_node("router", routing_node)
    g.add_node("research_node", research_node)
    g.add_node("escalate", escalate)
    g.add_edge(START, "router")
    g.add_conditional_edges("router", dispatch, ["research_node", "escalate"])
    g.add_edge("research_node", END)
    g.add_edge("escalate", END)
    return g.compile()


def main() -> None:
    print("=" * 74)
    print("EX07  Structured-output routing")
    print("=" * 74)

    print("\n1. ToolStrategy (default)")
    print("-" * 74)
    tool_strategy_router()

    print("\n2. The silent-retry trap")
    print("-" * 74)
    print(f"  observed: {silent_retry_trap()}")
    print("  The model returned prose instead of the `Route` tool call.")
    print("  The agent did not raise - it kept re-asking until the limit.")
    print("  FIX (production): validate the structured_response yourself, or")
    print("       use a cheaper/faster model for routing, or cap retries.")

    print("\n3. ProviderStrategy")
    print("-" * 74)
    print(f"  {provider_strategy_note()}")
    print("  With Gemini, ProviderStrategy uses the native JSON-schema mode.")
    print("  With a model that lacks it, use ToolStrategy (default).")

    print("\n4. Routing to real specialists")
    print("-" * 74)
    app = build_routed_team()
    out = app.invoke({"messages": [user("Tell me about LangGraph")]}, LIMIT)
    print(f"  route   : {out['route']}")
    print(f"  reason  : {out['reason']}")
    print(f"  result  : {out['result']}")

    print()
    print("=" * 74)
    print("A / B - WHICH ROUTING STYLE?")
    print("=" * 74)
    print(
        """
  FREE-FORM (one tool per specialist)
    + the specialist IS the action; no dispatch code at all
    + the model can call two specialists in one turn (parallel fan-out)
    - the routing decision is buried in tool-call arguments
    - harder to validate, log or override

  STRUCTURED (a schema)
    + you hold a typed object: `route.specialist == "billing"`
    + trivial to validate, log, threshold, or route to a human
    + you can route to non-agent destinations (a queue, a REST call)
    - you must write the dispatch code yourself
    - ToolStrategy adds a synthetic tool call to the transcript

  PICK: free-form when the routing IS the work.  Structured when you need to
  make a DECISION about the routing.
"""
    )


if __name__ == "__main__":
    main()
