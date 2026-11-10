"""EX06 - The modern supervisor: agents-as-tools (the `langgraph-supervisor` replacement).

Run:  PYTHONPATH=examples .venv/bin/python examples/ex06_agents_as_tools.py

WHY THIS FILE EXISTS
--------------------
`langgraph-supervisor` (PyPI, last release 2025-11-19) was the old prebuilt
package for supervisor teams.  It has not been maintained since LangChain v1
landed, it pins the pre-v1 agent API, and it will not receive fixes.

The modern, maintained equivalent is the **subagents pattern**:

    worker  = create_agent(model, tools=[...], name="researcher")
    supervisor = create_agent(model, tools=[worker_as_tool, ...])

One `create_agent` per worker.  Each worker is exposed to the supervisor as an
ordinary tool.  Nothing else changes.

WHAT THIS EXAMPLE SHOWS
-----------------------
  1. How to wrap a `create_agent` as a tool (the "agent as tool" adapter).
  2. Why the adapter must return TEXT, not a state dict.
  3. How to keep the supervisor's own transcript small.
  4. When the subagents pattern is NOT enough - and what to reach for.
"""

from __future__ import annotations

from typing import Annotated

from langchain.agents import AgentState, create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph

from _common import ai, once_then_final, scripted, text_of, user

LIMIT = {"recursion_limit": 20}


# ---------------------------------------------------------------------------
# The specialist agents
# ---------------------------------------------------------------------------


@tool
def web_search(query: str) -> str:
    """Search the web."""
    return f"web: 3 articles about '{query}'"


@tool
def read_invoice(invoice_id: str) -> str:
    """Read an invoice."""
    return f"invoice {invoice_id}: 49.00 EUR, paid"


@tool
def open_ticket(title: str) -> str:
    """Open a support ticket."""
    return f"ticket opened: {title}"


def build_specialists():
    """Three specialists, each with its own tool, prompt and model."""
    research_model = scripted(
        router=once_then_final(
            "web_search",
            {"query": "langgraph supervisor"},
            final="LangGraph supervisor patterns: 3 approaches.",
            call_id="r1",
        )
    )
    billing_model = scripted(
        router=once_then_final(
            "read_invoice",
            {"invoice_id": "INV-77"},
            final="INV-77: 49.00 EUR, paid.",
            call_id="b1",
        )
    )
    support_model = scripted(
        router=once_then_final(
            "open_ticket",
            {"title": "cannot log in"},
            final="Ticket #412 opened for login issue.",
            call_id="s1",
        )
    )

    return {
        "researcher": create_agent(
            research_model,
            tools=[web_search],
            system_prompt="You are a research specialist. Cite sources. Be brief.",
            name="researcher",
        ),
        "billing": create_agent(
            billing_model,
            tools=[read_invoice],
            system_prompt="You handle invoices. Never speculate - look it up.",
            name="billing",
        ),
        "support": create_agent(
            support_model,
            tools=[open_ticket],
            system_prompt="You open tickets. One ticket per issue.",
            name="support",
        ),
    }


# ---------------------------------------------------------------------------
# THE ADAPTER: turn an agent into a tool
# ---------------------------------------------------------------------------


def agent_as_tool(name: str, description: str, agent):
    """Expose a `create_agent` to another agent as a callable tool.

    The contract is simple and important:

      * INPUT  - a plain string (the delegated task).
      * OUTPUT - a plain string (the specialist's final answer).

    Returning a state dict instead of a string is the most common mistake:
    the supervisor's model receives a JSON blob of internal state and has to
    guess which part is the answer.
    """

    @tool(f"ask_{name}", description=description)
    def ask(task: str) -> str:
        result = agent.invoke({"messages": [HumanMessage(content=task)]}, LIMIT)
        # The specialist's LAST message is its answer.
        return text_of(result["messages"][-1])

    return ask


def build_supervisor():
    specialists = build_specialists()

    researcher_tool = agent_as_tool(
        "researcher",
        "Delegate research / web lookups to the research specialist.",
        specialists["researcher"],
    )
    billing_tool = agent_as_tool(
        "billing",
        "Delegate invoice and payment questions to the billing specialist.",
        specialists["billing"],
    )
    support_tool = agent_as_tool(
        "support",
        "Delegate account / login / complaint issues to the support specialist.",
        specialists["support"],
    )

    supervisor_model = scripted(
        router=once_then_final(
            "ask_researcher",
            {"task": "Find articles about LangGraph supervisor patterns."},
            final="Here is what I found: LangGraph supervisor patterns.",
            call_id="s0",
        )
    )

    supervisor = create_agent(
        supervisor_model,
        tools=[researcher_tool, billing_tool, support_tool],
        system_prompt=(
            "You are a team supervisor. Pick exactly ONE specialist per step and "
            "delegate with a complete, self-contained task description."
        ),
        name="supervisor",
    )
    return supervisor, specialists


# ---------------------------------------------------------------------------
# Team state - what the team shares
# ---------------------------------------------------------------------------


class TeamState(AgentState):
    """The team's shared scratchpad.

    Note what is NOT here: the specialists' full transcripts.  Each specialist
    keeps its own conversation; the team only keeps the RESULTS.
    """

    findings: Annotated[list[str], lambda a, b: a + b]
    final_answer: str


def build_team_graph():
    """The supervisor runs as a NODE in a team graph."""

    def supervisor_node(state: TeamState):
        result = supervisor_node.agent.invoke({"messages": state["messages"]}, LIMIT)
        answer = text_of(result["messages"][-1])
        return {
            "messages": [result["messages"][-1]],
            "findings": [answer],
            "final_answer": answer,
        }

    supervisor, specialists = build_supervisor()
    supervisor_node.agent = supervisor  # type: ignore[attr-defined]

    g = StateGraph(TeamState)
    g.add_node("supervisor", supervisor_node)
    g.add_edge(START, "supervisor")
    g.add_edge("supervisor", END)
    return g.compile(), supervisor, specialists


def main() -> None:
    print("=" * 74)
    print("EX06  Agents-as-tools: the modern supervisor pattern")
    print("=" * 74)

    app, supervisor, specialists = build_team_graph()

    question = "What are the LangGraph supervisor patterns?"
    print(f"\nQuestion: {question}\n")

    out = app.invoke({"messages": [user(question)], "findings": [], "final_answer": ""}, LIMIT)

    print("TEAM STATE")
    print("-" * 74)
    print(f"  findings      : {out['findings']}")
    print(f"  final_answer  : {out['final_answer']}")
    print(f"  top-level messages: {len(out['messages'])}")
    for m in out["messages"]:
        print(f"     {m.type:<10} | {text_of(m)[:70]}")

    print()
    print("WHY THE SUPERVISOR'S TRANSCRIPT STAYS SMALL")
    print("-" * 74)
    print("  The researcher's own conversation (system prompt + tool call +")
    print("  tool result) lives INSIDE the researcher agent.  The supervisor")
    print("  only ever sees the researcher's final STRING.")
    print("  That is context isolation (L01, reason #1) in action.")

    print()
    print("=" * 74)
    print("WHEN IS THE SUBAGENTS PATTERN NOT ENOUGH?")
    print("=" * 74)
    print(
        """
  The subagents pattern gives you ONE thing: the supervisor picks a specialist
  and reads a string back.  Reach for something else when you need:

  * SHARED STATE between agents (the specialist must WRITE, not just answer)
      -> use a hand-built StateGraph (EX08) so the team has a real schema.

  * CONTROL FLOW handoffs (agent A hands the conversation to agent B and
    agent B continues talking to the user)
      -> use Command(graph=Command.PARENT, goto=...) (EX09).

  * PARALLEL specialists (do 5 things at once)
      -> use Send fan-out (EX13).

  * PER-AGENT budgets / different models per agent
      -> you already have that: each worker is its own create_agent, so it
         has its own model, its own middleware, its own limits.

  ESCAPE HATCH RULE: when the supervisor needs to pass more than a string
  back, stop stringifying.  Give the team a real shared state.
"""
    )

    print()
    print("=" * 74)
    print("REAL GEMINI SWAP")
    print("=" * 74)
    print(
        """
  from langchain.chat_models import init_chat_model
  model = init_chat_model("google_genai:gemini-3.8-flash")

  researcher = create_agent(model, tools=[web_search], name="researcher")
  ...the rest of the file is unchanged...
"""
    )


if __name__ == "__main__":
    main()
