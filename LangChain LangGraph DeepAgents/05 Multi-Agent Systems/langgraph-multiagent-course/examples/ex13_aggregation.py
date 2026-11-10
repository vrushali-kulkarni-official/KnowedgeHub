"""EX13 - Aggregating parallel results: vote, judge, and hybrid.

Run:  PYTHONPATH=examples .venv/bin/python examples/ex13_aggregation.py

When N agents answer the same question, you now have a NEW problem: which
answer do you believe?  Three standard strategies, in increasing cost:

  VOTE    count normalised answers, take the most common.  Free (no extra
          model call).  Best when the answers are objective and the agents
          are similar.  Fails when the agents are biased the same way.

  JUDGE   show a model all N answers and ask it to pick the best.  Costs one
          extra model call with N answers in the prompt.  Best when quality
          varies and "best" is not a simple majority.

  HYBRID  vote first; if there is a clear winner, stop.  Only call the judge
          when the vote is tied.  This is what you should ship.

The most common mistake: running the judge unconditionally.  You pay a model
call per request for a decision the vote could have made for free.
"""

from __future__ import annotations

from collections import Counter
from typing import Annotated

from langchain.agents import AgentState, create_agent
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph

from _common import ai, once_then_final, scripted, text_of, user

LIMIT = {"recursion_limit": 25}


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class VoteState(AgentState):
    """Shared state for the aggregation demo."""

    candidates: Annotated[list[str], lambda a, b: a + b]
    answer: str
    method: str
    votes: dict


# ---------------------------------------------------------------------------
# Three agents that answer the same question, differently
# ---------------------------------------------------------------------------


@tool
def look_it_up(topic: str) -> str:
    """Look something up."""
    return "lookup"


def build_answerers(answers: list[str]):
    """One agent per candidate answer."""
    agents = []
    for i, ans in enumerate(answers):
        model = scripted(
            router=once_then_final("look_it_up", {"topic": "q"}, final=ans, call_id=f"c{i}")
        )
        agents.append(create_agent(model, tools=[look_it_up], name=f"agent_{i}"))
    return agents


# ---------------------------------------------------------------------------
# Strategy 1: VOTE
# ---------------------------------------------------------------------------


def normalise(text: str) -> str:
    """Make answers comparable: lowercase, strip punctuation and whitespace."""
    return " ".join(text.lower().strip().rstrip(".").split())


def vote(candidates: list[str]) -> tuple[str, dict]:
    """Majority vote over normalised answers.

    Returns (winner, vote_counts).
    """
    normalised = [normalise(c) for c in candidates]
    counts = Counter(normalised)
    if not counts:
        return "", {}
    top = counts.most_common(1)[0]
    # Tie -> first-seen wins (deterministic).
    winner_norm = top[0]
    for c, n in zip(candidates, normalised):
        if n == winner_norm:
            return c, counts
    return candidates[0], counts


# ---------------------------------------------------------------------------
# Strategy 2: JUDGE
# ---------------------------------------------------------------------------


class VerdictSchema(BaseModel):
    """Which candidate is best?

    NOTE: with the default `ToolStrategy`, this class name IS the synthetic
    tool name the model must call.  Rename the class and you must rename
    the tool call too.
    """

    index: int = Field(description="0-based index of the best candidate")
    reason: str = Field(description="why it is best")


def judge(candidates: list[str]) -> VerdictSchema:
    """A model picks the best candidate."""
    from langchain_core.messages import AIMessage as AI

    def router(messages):
        # Emit the structured tool call once, then answer.  A router that
        # ALWAYS emits the tool call makes the agent retry forever
        # (the silent-retry trap, EX07).
        from _common import once_then_final

        return once_then_final(
            "VerdictSchema",
            {"index": 1, "reason": "most specific and well-evidenced"},
            final="verdict recorded",
        )(messages)

    model = scripted(router=router)
    agent = create_agent(model, tools=[], response_format=VerdictSchema)
    listing = "\n".join(f"{i}. {c}" for i, c in enumerate(candidates))
    out = agent.invoke({"messages": [user(f"Which is best?\n{listing}")]}, LIMIT)
    sr = out["structured_response"]
    return sr


# ---------------------------------------------------------------------------
# Strategy 3: HYBRID
# ---------------------------------------------------------------------------


def hybrid(candidates: list[str], margin: int = 2) -> tuple[str, str, dict]:
    """Vote first; only escalate to the judge when the vote is close.

    Returns (answer, method_used, vote_counts).
    """
    winner, counts = vote(candidates)
    if not counts:
        return "", "none", counts
    ranked = counts.most_common()
    if len(ranked) == 1:
        return winner, "vote (unanimous)", counts
    top_count = ranked[0][1]
    second_count = ranked[1][1] if len(ranked) > 1 else 0
    if top_count - second_count >= margin:
        return winner, f"vote ({top_count} vs {second_count})", counts
    verdict = judge(candidates)
    return (
        candidates[verdict.index],
        f"judge (vote was {top_count} vs {second_count})",
        counts,
    )


# ---------------------------------------------------------------------------
# The graph
# ---------------------------------------------------------------------------


def build_graph(answers: list[str]):
    agents = build_answerers(answers)

    # GOTCHA (again): the branch function's type hints must resolve at
    # MODULE scope, or you get NameError: name 'GraphState' is not defined.
    def planner(state: VoteState):
        return {}

    def branch(state: VoteState):
        idx = state["idx"]
        result = agents[idx].invoke({"messages": [HumanMessage(content="q")]}, LIMIT)
        return {"candidates": [text_of(result["messages"][-1])]}

    def fanout(state: VoteState):
        from langgraph.types import Send

        return [
            Send("branch", {"idx": i, "messages": state["messages"]}) for i in range(len(agents))
        ]

    def aggregator(state: VoteState):
        answer, method, counts = hybrid(state["candidates"])
        # Store a plain dict: a Counter is a dict subclass, but the state
        # should stay trivially serialisable for checkpointing.
        return {"answer": answer, "method": method, "votes": dict(counts)}

    g = StateGraph(VoteState)
    g.add_node("planner", planner)
    g.add_node("branch", branch)
    g.add_node("aggregator", aggregator)
    g.add_edge(START, "planner")
    g.add_conditional_edges("planner", fanout, ["branch"])
    g.add_edge("branch", "aggregator")
    g.add_edge("aggregator", END)
    return g.compile()


def main() -> None:
    print("=" * 74)
    print("EX13  Aggregating parallel results")
    print("=" * 74)

    scenarios = [
        (
            "CLEAR MAJORITY",
            ["LangGraph is a graph framework.", "LangGraph is a graph framework.", "It is a DB."],
        ),
        (
            "SPLIT VOTE -> JUDGE DECIDES",
            ["LangGraph is a graph framework.", "LangGraph is a workflow engine.", "It is a database."],
        ),
    ]

    for title, answers in scenarios:
        print(f"\n{title}")
        print("-" * 74)
        app = build_graph(answers)
        out = app.invoke({"messages": [user("What is LangGraph?")], "candidates": [], "answer": "", "method": "", "votes": {}}, LIMIT)
        print(f"  candidates : {out['candidates']}")
        print(f"  votes      : {out['votes']}")
        print(f"  method     : {out['method']}")
        print(f"  answer     : {out['answer']}")

    print()
    print("=" * 74)
    print("PICKING A STRATEGY")
    print("=" * 74)
    print(
        """
  VOTE   when answers are objective (a number, a yes/no, a classification)
         and the agents are of comparable quality.  Zero extra cost.

  JUDGE  when quality VARIES between agents and "best" is subjective.
         Costs one model call with N answers in the prompt - so N is
         bounded by your context budget.

  HYBRID what to actually ship: vote, and only judge when the margin is
         small.  You pay for the judge only on the hard cases.

  NEVER  run the judge on every request if a vote would do.  You are
         multiplying your cost by N for a decision you could make with
         arithmetic.

  NORMALISE before voting - "Yes." / "yes" / "YES" must count as the same
  answer, or your vote is split for no reason.
"""
    )


if __name__ == "__main__":
    main()
