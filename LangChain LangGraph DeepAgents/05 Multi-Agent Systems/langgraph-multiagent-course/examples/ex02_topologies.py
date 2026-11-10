"""EX02 — The four multi-agent topologies, side by side.

Run:  PYTHONPATH=examples .venv/bin/python examples/ex02_topologies.py

Every topology below is a COMPLETE, RUNNABLE graph - not a diagram.  Run it,
then change one edge and watch the behaviour change.  That is how topologies
stop being abstract.

  1. SUPERVISOR   - a router owns the work, workers are leaf specialists.
  2. HIERARCHICAL - supervisors of supervisors (a tree).
  3. SWARM       - peers hand control to each other, no central boss.
  4. PIPELINE    - a fixed sequence; routing is static, not decided by an LLM.

Cost / latency / complexity, in the same units for all four:

  * LLM round trips per request  -> money + latency
  * number of LLM-routed edges   -> combinatorial explosion risk
  * max depth                    -> worst-case latency
  * shared mutable state         -> coupling risk
"""

from __future__ import annotations

from typing import Annotated, Literal, TypedDict

from langchain.agents import create_agent
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph

from _common import ai, once_then_final, scripted, user, text_of

LIMIT = {"recursion_limit": 20}


# ---------------------------------------------------------------------------
# Shared building blocks
# ---------------------------------------------------------------------------


@tool
def research(topic: str) -> str:
    """Research a topic."""
    return f"[research] {topic}: 3 key findings"


@tool
def write_draft(topic: str) -> str:
    """Write a draft."""
    return f"[draft] {topic}: first draft ready"


@tool
def review(draft: str) -> str:
    """Review a draft."""
    return f"[review] {draft[:40]}... : looks good"


class Team(TypedDict):
    """A deliberately tiny shared state."""

    task: str
    log: Annotated[list[str], lambda a, b: a + b]
    answer: str


def _agent(final: str, name: str):
    """A one-shot agent that returns `final` as its answer."""
    return create_agent(
        scripted(responses=[ai(final)]),
        tools=[],
        name=name,
    )


# ---------------------------------------------------------------------------
# 1. SUPERVISOR
# ---------------------------------------------------------------------------


def topology_supervisor():
    """A router node decides which worker runs next; workers report back."""

    class SupState(TypedDict):
        task: str
        log: Annotated[list[str], lambda a, b: a + b]
        answer: str

    def supervisor(state):
        # In production this is an LLM call with a structured routing schema.
        # Here it is deterministic so the shape of the graph is obvious.
        return {"log": ["supervisor: routed to research"]}

    def researcher(state):
        return {"log": ["researcher: produced findings"], "answer": "research findings"}

    def writer(state):
        return {"log": ["writer: produced draft"], "answer": "final draft"}

    def route(state):
        if len(state["log"]) == 1:
            return "researcher"
        return "writer"

    g = StateGraph(SupState)
    g.add_node("supervisor", supervisor)
    g.add_node("researcher", researcher)
    g.add_node("writer", writer)
    g.add_edge(START, "supervisor")
    g.add_conditional_edges("supervisor", route, ["researcher", "writer"])
    g.add_edge("researcher", "supervisor")
    g.add_edge("writer", END)
    return g.compile()


# ---------------------------------------------------------------------------
# 2. HIERARCHICAL
# ---------------------------------------------------------------------------


def topology_hierarchical():
    """Top supervisor -> mid supervisor -> leaf workers."""

    class HierState(TypedDict):
        task: str
        log: Annotated[list[str], lambda a, b: a + b]
        answer: str

    def top(state):
        return {"log": ["top: delegated to content team"]}

    def mid(state):
        return {"log": ["mid: delegated to writer"]}

    def writer(state):
        return {"log": ["writer: done"], "answer": "hierarchical answer"}

    g = StateGraph(HierState)
    g.add_node("top_supervisor", top)
    g.add_node("content_supervisor", mid)
    g.add_node("writer", writer)
    g.add_edge(START, "top_supervisor")
    g.add_edge("top_supervisor", "content_supervisor")
    g.add_edge("content_supervisor", "writer")
    g.add_edge("writer", END)
    return g.compile()


# ---------------------------------------------------------------------------
# 3. SWARM
# ---------------------------------------------------------------------------


def topology_swarm():
    """Peers hand control to each other; no one is in charge."""

    class SwarmState(TypedDict):
        task: str
        log: Annotated[list[str], lambda a, b: a + b]
        answer: str
        next: str

    def triage(state):
        return {"log": ["triage: routing to researcher"], "next": "researcher"}

    def researcher(state):
        return {"log": ["researcher: handing to writer"], "next": "writer"}

    def writer(state):
        return {"log": ["writer: final"], "answer": "swarm answer", "next": END}

    def route(state):
        return state["next"]

    g = StateGraph(SwarmState)
    g.add_node("triage", triage)
    g.add_node("researcher", researcher)
    g.add_node("writer", writer)
    g.add_edge(START, "triage")
    g.add_conditional_edges("triage", route, ["researcher", "writer", END])
    g.add_conditional_edges("researcher", route, ["researcher", "writer", END])
    g.add_conditional_edges("writer", route, ["researcher", "writer", END])
    return g.compile()


# ---------------------------------------------------------------------------
# 4. PIPELINE
# ---------------------------------------------------------------------------


def topology_pipeline():
    """Fixed sequence. No LLM decides anything about the routing."""

    class PipeState(TypedDict):
        task: str
        log: Annotated[list[str], lambda a, b: a + b]
        answer: str

    def step_research(state):
        return {"log": ["research: ok"]}

    def step_draft(state):
        return {"log": ["draft: ok"]}

    def step_review(state):
        return {"log": ["review: ok"], "answer": "pipeline answer"}

    g = StateGraph(PipeState)
    g.add_node("research", step_research)
    g.add_node("draft", step_draft)
    g.add_node("review", step_review)
    g.add_edge(START, "research")
    g.add_edge("research", "draft")
    g.add_edge("draft", "review")
    g.add_edge("review", END)
    return g.compile()


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def run_and_report(name, app, description, *, llm_routed_edges):
    out = app.invoke({"task": "write a post about LangGraph"}, LIMIT)
    print(f"\n{'-' * 70}")
    print(f"{name}")
    print(f"  {description}")
    print(f"  LLM-routed edges : {llm_routed_edges}")
    print(f"  path taken       : {' -> '.join(out['log'])}")
    print(f"  answer           : {out.get('answer')}")
    return out


def main() -> None:
    print("=" * 74)
    print("EX02  Four multi-agent topologies")
    print("=" * 74)

    run_and_report(
        "1. SUPERVISOR",
        topology_supervisor(),
        "One router owns the work; specialists are leaves. Most common.",
        llm_routed_edges=1,
    )
    run_and_report(
        "2. HIERARCHICAL",
        topology_hierarchical(),
        "Supervisors of supervisors. Scales to many specialists; deeper = slower.",
        llm_routed_edges=1,
    )
    run_and_report(
        "3. SWARM (handoffs)",
        topology_swarm(),
        "Peers hand off to each other. No bottleneck, but hard to predict.",
        llm_routed_edges=2,
    )
    run_and_report(
        "4. PIPELINE",
        topology_pipeline(),
        "Fixed sequence. Zero routing decisions = zero routing cost.",
        llm_routed_edges=0,
    )

    print()
    print("=" * 74)
    print("CHOOSING")
    print("=" * 74)
    print(
        """
  PIPELINE     use when the steps are known and fixed (extract -> summarise ->
               publish).  No LLM routing, so no routing cost, no routing
               mistakes.  Reach for this FIRST - it is the most under-used
               multi-agent pattern.

  SUPERVISOR   use when one coordinator must decide "who handles this?" and
               the specialists are genuinely different.  Easy to observe,
               easy to bound.

  HIERARCHICAL use when you have >~6 specialists: a flat supervisor's prompt
               and decision quality degrade as the option list grows.  Split
               into domains.

  SWARM       use when the experts genuinely need to talk to each other in a
               conversation that nobody should script.  Highest variance,
               hardest to debug, most prone to ping-pong loops.
"""
    )


if __name__ == "__main__":
    main()
