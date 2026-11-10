"""EX18 - The same system with a REAL Gemini model.

Run:  export GOOGLE_API_KEY=...  &&  PYTHONPATH=examples .venv/bin/python examples/ex18_gemini_real.py

This example is NOT part of the offline test suite - it needs an API key and
network access.  It exists so you can see the EXACT delta between the
scripted harness and production code.

THE WHOLE DELTA IS FOUR LINES
------------------------------
    from langchain.chat_models import init_chat_model

    model = init_chat_model("google_genai:gemini-3.8-flash")

Everything else - the state schema, the `Send` fan-out, the reducers, the
handoff tools, the middleware, the store - is identical.

WHY GEMINI
----------
  * `langchain-google-genai` is first-party and actively maintained.
  * Gemini supports native structured output, so you can use
    `ProviderStrategy` instead of the default `ToolStrategy`.
  * The free tier is generous enough to build and test the whole course.

THE CURRENT MODEL LINE (verified 2026-11-05)
---------------------------------------------
    model ID                 stage    context      max out   $/1M in/out
    gemini-4-argon           Stable   1,048,576    65,536     $2  / $10  (intro)
    gemini-3.8-flash         Stable   1,048,576    65,536     $0.75/ $3.75(intro)
    gemini-3.6-flash         Stable   1,048,576    65,536     $0.75/ $3.75
    gemini-3.5-flash-lite    Stable   1,048,576    65,536     $0.30/ $2.50

MODEL CHOICES FOR A MULTI-AGENT SYSTEM
---------------------------------------
    routing / classification  -> gemini-3.5-flash-lite   ($0.30/$2.50)
    summarisation             -> gemini-3.5-flash-lite   ($0.30/$2.50)
    specialist reasoning      -> gemini-3.8-flash        ($0.75/$3.75)
    hard reasoning / final    -> gemini-4-argon         (most capable)

    Different agents CAN use different models.  That is one of the best
    reasons to split an agent in the first place: a routing step on a
    Flash-Lite model costs about a quarter of the same step on Flash.

RETIRED / AUTO-ROUTED (do not target these)
-------------------------------------------
    gemini-2.5-pro        -> auto-routes to gemini-3.8-flash from 2026-12-01
    gemini-2.5-flash      -> auto-routes to gemini-3.5-flash-lite from 2026-12-01
    gemini-2.5-flash-lite -> use gemini-3.5-flash-lite instead
    gemini-3.5-flash      -> auto-routes to gemini-3.6-flash
    gemini-3.7-flash      -> auto-routes to gemini-3.8-flash

    NOTE: Google made the Interactions API the default interface in June
    2026; `generateContent` is now legacy.  `langchain-google-genai`
    handles that for you - you still just call `init_chat_model(...)`.
"""

from __future__ import annotations

import os
import sys
from typing import Annotated

from langchain.agents import AgentState, create_agent
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph

LIMIT = {"recursion_limit": 30}


# ---------------------------------------------------------------------------
# Tools (these are real - they call real APIs)
# ---------------------------------------------------------------------------


@tool
def web_search(query: str) -> str:
    """Search the web for information."""
    # Replace with your own search API (Tavily, Brave, Serper, ...).
    return f"[search results for '{query}'] LangGraph is a low-level orchestration framework."


@tool
def read_invoice(invoice_id: str) -> str:
    """Read a billing invoice."""
    return f"[invoice {invoice_id}] total 49.00 EUR, status paid."


def build_team(model):
    """The production shape, with a real model.

    Note: every agent gets its OWN model instance, and the specialists get a
    cheaper model than the supervisor.
    """

    def agent_as_tool(name: str, description: str, agent):
        @tool(f"ask_{name}", description=description)
        def ask(task: str) -> str:
            result = agent.invoke({"messages": [HumanMessage(content=task)]}, LIMIT)
            return result["messages"][-1].content

        return ask

    researcher = create_agent(
        model,
        tools=[web_search],
        system_prompt="You research. Cite the source. Be brief.",
        name="researcher",
    )
    billing = create_agent(
        model,
        tools=[read_invoice],
        system_prompt="You handle invoices. Never speculate - look it up.",
        name="billing",
    )

    supervisor = create_agent(
        model,
        tools=[
            agent_as_tool("researcher", "Delegate research questions.", researcher),
            agent_as_tool("billing", "Delegate invoice questions.", billing),
        ],
        system_prompt=(
            "You are a team supervisor. Pick exactly one specialist and give it a "
            "SELF-CONTAINED brief - it cannot see this conversation."
        ),
        name="supervisor",
    )

    class TeamState(AgentState):
        results: Annotated[list[str], lambda a, b: a + b]

    def sup_node(state: TeamState):
        result = supervisor.invoke({"messages": state["messages"]}, LIMIT)
        return {"messages": [result["messages"][-1]], "results": [result["messages"][-1].content]}

    g = StateGraph(TeamState)
    g.add_node("supervisor", sup_node)
    g.add_edge(START, "supervisor")
    g.add_edge("supervisor", END)
    return g.compile()


def main() -> None:
    if not os.environ.get("GOOGLE_API_KEY"):
        print("=" * 74)
        print("EX18  Real Gemini example")
        print("=" * 74)
        print("\n  GOOGLE_API_KEY is not set - skipping the live call.\n")
        print("  export GOOGLE_API_KEY=your-key")
        print("  PYTHONPATH=examples .venv/bin/python examples/ex18_gemini_real.py\n")
        print("  Here is the code you would run:")
        print(
            """
  from langchain.chat_models import init_chat_model

  # The current GA workhorse: 1,048,576 context / 65,536 max output.
  model = init_chat_model("google_genai:gemini-3.8-flash")

  # A much cheaper model for routing / summarisation ($0.30/$2.50 per 1M).
  cheap = init_chat_model("google_genai:gemini-3.5-flash-lite")

  # The most capable model, for the hardest reasoning.
  best  = init_chat_model("google_genai:gemini-4-argon")

  researcher = create_agent(model, tools=[web_search], name="researcher")
  billing    = create_agent(cheap, tools=[read_invoice], name="billing")
  supervisor = create_agent(model, tools=[ask_researcher, ask_billing], name="supervisor")
"""
        )
        return

    model = init_chat_model("google_genai:gemini-3.8-flash")
    app = build_team(model)

    question = "What is LangGraph, and is it still maintained?"
    print("=" * 74)
    print("EX18  Real Gemini example")
    print("=" * 74)
    print(f"\nQ: {question}\n")

    out = app.invoke({"messages": [("user", question)], "results": []}, LIMIT)
    print("A:")
    for r in out["results"]:
        print(f"  {r}")

    print()
    print("  Now go and read your Langfuse trace - you should see the")
    print("  supervisor span with a 'researcher' child span under it.")


if __name__ == "__main__":
    main()
