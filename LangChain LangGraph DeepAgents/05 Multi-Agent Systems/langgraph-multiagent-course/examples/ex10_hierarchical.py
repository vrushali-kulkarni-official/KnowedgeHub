"""EX10 - Hierarchical teams: supervisors of supervisors.

Run:  PYTHONPATH=examples .venv/bin/python examples/ex10_hierarchical.py

A FLAT supervisor has one problem that gets worse as you add specialists:
the supervisor's prompt grows, its tool list grows, and its routing accuracy
drops.  Around half a dozen specialists, you should split the domain.

  TOP SUPERVISOR
     |
     +-- CONTENT SUPERVISOR  (mid tier)
     |      +-- writer agent
     |      +-- reviewer agent
     |
     +-- RESEARCH SUPERVISOR (mid tier)
            +-- researcher agent
            +-- fact-checker agent

THE MODERN IMPLEMENTATION
-------------------------
The mid tier is itself a `create_agent`.  You wrap it in a tool exactly like
you wrap a leaf worker (EX06), and the top supervisor calls it like any
other tool.

    mid   = create_agent(model, tools=[writer_tool, reviewer_tool], name="content_supervisor")
    top   = create_agent(model, tools=[mid_tool, research_tool], name="top_supervisor")

That is the whole trick - and it is why the hierarchical topology is cheap to
build on top of the subagents pattern.

PROGRESS REPORTING AND FAILURE ESCALATION are also here, because they are
the two things a hierarchy makes HARDER:
  * progress reporting: how does the top tier know the mid tier is 2/3 done?
  * failure escalation: what happens when a leaf fails and the mid tier
    cannot fix it?
"""

from __future__ import annotations

from typing import Annotated, Literal

from langchain.agents import AgentState, create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph

from _common import ai, once_then_final, once_per_turn, scripted, text_of, user

LIMIT = {"recursion_limit": 25}


# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------


class TeamState(AgentState):
    """State shared by the whole hierarchy.

    `progress` is written by the LEAVES so the whole tree can see it - this
    is how progress reporting works without any extra machinery.
    """

    brief: str
    progress: Annotated[list[str], lambda a, b: a + b]
    artifacts: Annotated[dict[str, str], lambda a, b: {**a, **b}]
    final_answer: str
    status: Literal["running", "done", "escalated"]
    escalation: str


# ---------------------------------------------------------------------------
# Leaf specialists
# ---------------------------------------------------------------------------


@tool
def web_search(query: str) -> str:
    """Search the web."""
    return f"web: 2 results for '{query}'"


def build_leaves():
    researcher = create_agent(
        scripted(router=once_then_final("web_search", {"query": "langgraph"}, final="FACTS: 1,2,3")),
        tools=[web_search],
        system_prompt="You research. Reply with FACTS: ...",
        name="researcher",
    )
    fact_checker = create_agent(
        scripted(responses=[ai("ALL FACTS VERIFIED")]),
        tools=[],
        system_prompt="You verify facts. Reply ALL FACTS VERIFIED or a correction.",
        name="fact_checker",
    )
    writer = create_agent(
        scripted(responses=[ai("Draft: LangGraph multi-agent systems in three patterns.")]),
        tools=[],
        system_prompt="You write. One paragraph.",
        name="writer",
    )
    reviewer = create_agent(
        scripted(responses=[ai("APPROVED")]),
        tools=[],
        system_prompt="You review. Reply APPROVED or REQUEST CHANGES.",
        name="reviewer",
    )
    return {
        "researcher": researcher,
        "fact_checker": fact_checker,
        "writer": writer,
        "reviewer": reviewer,
    }


def agent_as_tool(name: str, description: str, agent):
    """The agent-as-tool adapter (see EX06)."""

    @tool(f"ask_{name}", description=description)
    def ask(task: str) -> str:
        result = agent.invoke({"messages": [HumanMessage(content=task)]}, LIMIT)
        return text_of(result["messages"][-1])

    return ask


# ---------------------------------------------------------------------------
# Mid tier: a supervisor that is ITSELF a create_agent
# ---------------------------------------------------------------------------


def build_content_supervisor(leaves):
    """A mid-tier supervisor, wrapped so the top tier can call it as a tool."""

    writer_tool = agent_as_tool("writer", "Delegate writing to the writer.", leaves["writer"])
    reviewer_tool = agent_as_tool("reviewer", "Delegate review to the reviewer.", leaves["reviewer"])

    mid_model = scripted(
        router=once_then_final(
            "ask_writer",
            {"task": "Write one paragraph about LangGraph multi-agent patterns."},
            final="Draft written and reviewed.",
        )
    )

    mid = create_agent(
        mid_model,
        tools=[writer_tool, reviewer_tool],
        system_prompt="You supervise the content team. Delegate, then summarise.",
        name="content_supervisor",
    )
    return mid, mid_model


def build_research_supervisor(leaves):
    """A second mid tier, in a different domain."""

    researcher_tool = agent_as_tool(
        "researcher", "Delegate research to the researcher.", leaves["researcher"]
    )
    checker_tool = agent_as_tool(
        "fact_checker", "Delegate fact-checking to the fact checker.", leaves["fact_checker"]
    )

    mid_model = scripted(
        router=once_then_final(
            "ask_researcher",
            {"task": "Find 3 facts about LangGraph multi-agent patterns."},
            final="FACTS: 1,2,3 - ALL FACTS VERIFIED",
        )
    )

    mid = create_agent(
        mid_model,
        tools=[researcher_tool, checker_tool],
        system_prompt="You supervise the research team.",
        name="research_supervisor",
    )
    return mid, mid_model


# ---------------------------------------------------------------------------
# Progress reporting
# ---------------------------------------------------------------------------


def build_progress_recorder():
    """A leaf that reports progress into the shared state.

    In a real system the leaf's tool writes to the parent's state via
    `Command(graph=Command.PARENT, update={...})`.  Here we do it in the
    wrapper node so the example stays short.
    """

def build_leaf_node(leaves, name: str, artifact_key: str):
    """Wrap a leaf agent so it records progress + its artifact."""

    def node(state: TeamState):
        brief = state.get("brief") or "Continue the task."
        result = leaves[name].invoke({"messages": [HumanMessage(content=brief)]}, LIMIT)
        answer = text_of(result["messages"][-1])
        return {
            "messages": [AIMessage(content=f"[{name}] {answer}")],
            "progress": [f"{name} done"],
            "artifacts": {artifact_key: answer},
        }

    return node


# ---------------------------------------------------------------------------
# Failure escalation
# ---------------------------------------------------------------------------


def build_escalation_demo():
    """What happens when a leaf fails?

    The rule: a mid tier that cannot complete its domain does NOT retry
    forever.  It returns an ESCALATION marker, and the top tier decides
    whether to (a) try another domain, (b) ask a human, or (c) answer with
    partial results.
    """

    @tool
    def always_fails(query: str) -> str:
        """A tool that always fails."""
        raise RuntimeError("upstream API is down")

    failing = create_agent(
        scripted(router=once_then_final("always_fails", {"query": "x"}, final="never")),
        tools=[always_fails],
        name="failing_agent",
    )

    def mid_tier(state: TeamState):
        try:
            result = failing.invoke({"messages": [HumanMessage(content="do it")]}, LIMIT)
            answer = text_of(result["messages"][-1])
            return {"artifacts": {"failure": answer}, "status": "running"}
        except Exception as exc:
            # ESCALATION: report upward instead of looping.
            return {
                "escalation": f"research tier failed: {type(exc).__name__}",
                "status": "escalated",
                "progress": ["research tier escalated"],
            }

    def top_tier(state: TeamState):
        if state.get("status") == "escalated":
            # The top tier decides what to do with the escalation.
            return {
                "final_answer": f"Partial answer. Escalation: {state['escalation']}",
                "status": "escalated",
                "progress": ["top tier handled escalation"],
            }
        return {"final_answer": "ok", "status": "done"}

    g = StateGraph(TeamState)
    g.add_node("mid", mid_tier)
    g.add_node("top", top_tier)
    g.add_edge(START, "mid")
    g.add_conditional_edges("mid", lambda s: "top", ["top"])
    g.add_edge("top", END)
    return g.compile()


# ---------------------------------------------------------------------------
# The full hierarchy
# ---------------------------------------------------------------------------


def build_hierarchy():
    leaves = build_leaves()
    content_mid, content_model = build_content_supervisor(leaves)
    research_mid, research_model = build_research_supervisor(leaves)

    content_tool = agent_as_tool(
        "content_supervisor",
        "Delegate ALL writing and reviewing to the content team.",
        content_mid,
    )
    research_tool = agent_as_tool(
        "research_supervisor",
        "Delegate ALL research and fact-checking to the research team.",
        research_mid,
    )

    top_model = scripted(
        router=once_then_final(
            "ask_content_supervisor",
            {"task": "Write one paragraph about LangGraph multi-agent patterns."},
            final="Here is your paragraph.",
        )
    )

    top = create_agent(
        top_model,
        tools=[content_tool, research_tool],
        system_prompt="You are the top supervisor. Pick the right department.",
        name="top_supervisor",
    )

    def top_node(state: TeamState):
        result = top.invoke({"messages": state["messages"]}, LIMIT)
        answer = text_of(result["messages"][-1])
        return {
            "messages": [result["messages"][-1]],
            "final_answer": answer,
            "status": "done",
            "progress": ["top supervisor finished"],
        }

    g = StateGraph(TeamState)
    g.add_node("top", top_node)
    g.add_edge(START, "top")
    g.add_edge("top", END)
    app = g.compile()
    models = [content_model, research_model, top_model]
    return app, models, leaves


def main() -> None:
    print("=" * 74)
    print("EX10  Hierarchical teams")
    print("=" * 74)

    app, models, leaves = build_hierarchy()
    out = app.invoke(
        {
            "messages": [user("Write about LangGraph multi-agent patterns")],
            "brief": "",
            "progress": [],
            "artifacts": {},
            "final_answer": "",
            "status": "running",
            "escalation": "",
        },
        LIMIT,
    )
    print("\nHIERARCHY RESULT")
    print("-" * 74)
    print(f"  final_answer : {out['final_answer']}")
    print(f"  status       : {out['status']}")
    print(f"  LLM calls    : {sum(m.n_calls for m in models)} across {len(models)} supervisors")
    print()
    print("  The tree:")
    print("    top_supervisor")
    print("      +-- content_supervisor  -> ask_writer / ask_reviewer")
    print("      +-- research_supervisor -> ask_researcher / ask_fact_checker")
    print()
    print("  Each tier is an ordinary `create_agent`.  The mid tier is just")
    print("  a tool that happens to contain other agents.")

    print("\n" + "=" * 74)
    print("FAILURE ESCALATION")
    print("=" * 74)
    esc = build_escalation_demo()
    out2 = esc.invoke(
        {
            "messages": [user("go")],
            "brief": "",
            "progress": [],
            "artifacts": {},
            "final_answer": "",
            "status": "running",
            "escalation": "",
        },
        LIMIT,
    )
    print(f"  status      : {out2['status']}")
    print(f"  escalation  : {out2['escalation']}")
    print(f"  final_answer: {out2['final_answer']}")
    print()
    print("  Note the direction of travel: a FAILURE moves UP the tree,")
    print("  never down.  A leaf must never decide to escalate itself.")

    print()
    print("=" * 74)
    print("PROGRESS REPORTING")
    print("=" * 74)
    print(
        """
  Three levels need three different amounts of progress:

  LEAF     writes to shared state as it goes:
           Command(graph=Command.PARENT, update={"progress": ["researcher done"]})

  MID TIER summarises its leaves' progress into one line for the top tier.
           Do NOT let the top tier read the raw leaf progress list - it is
           noise, and it grows without bound.

  TOP TIER shows the user: "Researched (2/2), drafting (1/2)...".
           Derive this from the MID TIER summaries, not from raw leaves.

  RULE: progress flows UP as summaries, DOWN as tasks.  Never pass raw
  progress lists upward - summarise at each boundary.
"""
    )


if __name__ == "__main__":
    main()
