"""EX08 - Hand-built supervisor with a real shared team state.

Run:  PYTHONPATH=examples .venv/bin/python examples/ex08_handbuilt_supervisor.py

The subagents pattern (EX06) gives you a supervisor that can only pass a
STRING.  Sometimes that is not enough:

  * the specialist must WRITE into a shared record (a score, a document id),
  * two specialists must contribute to the SAME artifact,
  * you need an audit trail of who did what,
  * a human must be able to inspect and override the team's intermediate work.

Then you hand-build the team on a `StateGraph` - but you still use
`create_agent` for each specialist, so you keep all of LangChain v1's agent
features (middleware, tools, structured output, limits).

This file builds such a team and focuses on HANDOFF MESSAGE DESIGN - the
single most-underrated part of multi-agent systems.

HANDOFF MESSAGE DESIGN
----------------------
A handoff is a PROMPT, not a packet.  Three rules:

  1. SELF-CONTAINED - the receiver cannot see your context.  Repeat what it
     needs.  ("Find 3 sources on X for a blog post about Y")
  2. EXPLICIT CONTRACT - say what shape the answer should be in.
  3. BOUNDED - say when to stop.  ("Answer in <=5 bullets")
"""

from __future__ import annotations

from typing import Annotated, Literal

from langchain.agents import AgentState, create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from _common import ai, once_then_final, scripted, text_of, user

LIMIT = {"recursion_limit": 20}


# ---------------------------------------------------------------------------
# The shared team state - module level (see EX07's gotcha)
# ---------------------------------------------------------------------------


class TeamState(AgentState):
    """Everything the team knows, in ONE place.

    Design rules used here:
      * `messages` holds the CONVERSATION (short).
      * structured facts live in their own typed fields (not in messages).
      * lists use an APPEND reducer so parallel writers do not clobber
        each other.
    """

    task: str
    brief: str
    """The task brief handed to the current specialist."""

    findings: Annotated[list[dict], lambda a, b: a + b]
    """Each specialist's contribution, appended."""

    draft: str
    final_answer: str
    status: Literal["routing", "working", "reviewing", "done"]
    next_agent: str
    """Who the supervisor decided should work next.  The graph dispatches on
    THIS field rather than re-deriving the decision - one source of truth."""

    trace: Annotated[list[str], lambda a, b: a + b]


class Assignment(BaseModel):
    """The supervisor's routing decision."""

    specialist: Literal["researcher", "writer", "reviewer"]
    brief: str = Field(description="A SELF-CONTAINED task brief for the specialist")
    done: bool = Field(default=False, description="True when no more work is needed")


# ---------------------------------------------------------------------------
# Specialists
# ---------------------------------------------------------------------------


@tool
def web_search(query: str) -> str:
    """Search the web."""
    return f"3 results for '{query}'"


@tool
def count_words(text: str) -> int:
    """Count words."""
    return len(text.split())


def build_specialists():
    researcher = create_agent(
        scripted(
            router=once_then_final(
                "web_search",
                {"query": "langgraph multi-agent"},
                final="Finding 1: supervisors. Finding 2: swarms. Finding 3: pipelines.",
                call_id="r1",
            )
        ),
        tools=[web_search],
        system_prompt="You research. Return exactly 3 numbered findings.",
        name="researcher",
    )
    writer = create_agent(
        scripted(
            router=once_then_final(
                "count_words",
                {"text": "draft body"},
                final="LangGraph lets you build multi-agent systems from three patterns.",
                call_id="w1",
            )
        ),
        tools=[count_words],
        system_prompt="You write the final section. <= 40 words.",
        name="writer",
    )
    reviewer = create_agent(
        scripted(responses=[ai("APPROVED")]),
        tools=[],
        system_prompt="You review. Reply with APPROVED or REQUEST CHANGES + why.",
        name="reviewer",
    )
    return {"researcher": researcher, "writer": writer, "reviewer": reviewer}


# ---------------------------------------------------------------------------
# The team graph
# ---------------------------------------------------------------------------


def build_team():
    specialists = build_specialists()

    def supervisor(state: TeamState):
        """Decide who works next, and write a self-contained brief."""

        def router(messages):
            # A real model would decide this from the conversation.
            # Note it returns a *structured* decision (EX07).
            done = state.get("status") == "done"
            if done:
                who, brief = "reviewer", "Review the draft. Reply APPROVED or REQUEST CHANGES."
            elif len(state["findings"]) == 0:
                who, brief = "researcher", (
                    "Find 3 numbered facts about LangGraph multi-agent patterns. "
                    "Return them as one line each, no preamble."
                )
            elif not state.get("draft"):
                who, brief = "writer", (
                    "Write one closing paragraph (<=40 words) about LangGraph "
                    "multi-agent patterns, using these findings: "
                    + "; ".join(f["summary"] for f in state["findings"])
                )
            else:
                who, brief = "reviewer", "Review the draft. Reply APPROVED or REQUEST CHANGES."
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "Assignment",
                        "args": {"specialist": who, "brief": brief, "done": done},
                        "id": "assign_1",
                        "type": "tool_call",
                    }
                ],
            )

        agent = create_agent(scripted(router=router), tools=[], response_format=Assignment, name="supervisor")
        result = agent.invoke({"messages": state["messages"]}, LIMIT)
        decision: Assignment = result["structured_response"]

        return {
            "status": "done" if decision.done else "working",
            "next_agent": decision.specialist,
            "brief": decision.brief,
            # !! With an APPEND reducer you must return ONLY the new items.
            #    Returning `state["trace"] + [...]` duplicates the whole list,
            #    because the reducer does `old + returned`.
            "trace": [f"supervisor -> {decision.specialist}"],
        }

    def make_worker(name: str):
        agent = specialists[name]

        def worker(state: TeamState):
            # THE HANDOFF: the specialist gets a fresh, self-contained
            # conversation.  It does NOT see the supervisor's transcript.
            result = agent.invoke(
                {"messages": [HumanMessage(content=state["brief"])]},
                LIMIT,
            )
            answer = text_of(result["messages"][-1])
            update = {
                "messages": [AIMessage(content=f"[{name}] {answer}")],
                # Only the NEW finding - the reducer appends it.
                "findings": [{"specialist": name, "summary": answer, "brief": state["brief"]}],
                "trace": [f"{name} delivered"],
            }
            if name == "writer":
                update["draft"] = answer
            if name == "reviewer":
                update["status"] = "done"
                update["final_answer"] = state.get("draft", answer)
            return update

        return worker

    def dispatch(state: TeamState):
        """Which worker runs next - straight from the supervisor's decision."""
        if state.get("status") == "done":
            return "finalise"
        return state.get("next_agent") or "researcher"

    def finalise(state: TeamState):
        answer = state.get("final_answer") or state.get("draft", "")
        return {
            "final_answer": answer,
            "status": "done",
            "trace": ["finalised"],
        }

    g = StateGraph(TeamState)
    g.add_node("supervisor", supervisor)
    g.add_node("researcher", make_worker("researcher"))
    g.add_node("writer", make_worker("writer"))
    g.add_node("reviewer", make_worker("reviewer"))
    g.add_node("finalise", finalise)
    g.add_edge(START, "supervisor")
    g.add_conditional_edges("supervisor", dispatch, ["researcher", "writer", "reviewer", "finalise"])
    g.add_edge("researcher", "supervisor")
    g.add_edge("writer", "supervisor")
    g.add_edge("reviewer", "supervisor")
    g.add_edge("finalise", END)
    return g.compile()


def main() -> None:
    print("=" * 74)
    print("EX08  Hand-built supervisor with a shared team state")
    print("=" * 74)

    app = build_team()
    out = app.invoke(
        {
            "messages": [user("Write a short post about LangGraph multi-agent patterns")],
            "task": "post",
            "brief": "",
            "findings": [],
            "draft": "",
            "final_answer": "",
            "status": "routing",
            "next_agent": "",
            "trace": [],
        },
        LIMIT,
    )

    print("\nTEAM TRACE")
    print("-" * 74)
    for step in out["trace"]:
        print(f"  {step}")

    print("\nSHARED STATE")
    print("-" * 74)
    print(f"  status        : {out['status']}")
    print(f"  findings      : {len(out['findings'])}")
    for f in out["findings"]:
        print(f"     - {f['specialist']}: {f['summary'][:60]}")
    print(f"  final_answer  : {out['final_answer'][:70]}")

    print("\nHANDOFF BRIEFS (what each specialist actually received)")
    print("-" * 74)
    for f in out["findings"]:
        print(f"  -> {f['specialist']}")
        print(f"     {f['brief'][:110]}")

    print()
    print("=" * 74)
    print("WHY A SHARED STATE BEATS STRING PASSING")
    print("=" * 74)
    print(
        """
  * The writer can read the researcher's findings from `findings` - it does
    NOT need the researcher's transcript, and it is not billed for it.
  * `trace` is an audit trail a human can read to see who did what.
  * `findings` uses an APPEND reducer, so when two specialists run in
    PARALLEL (L08) their writes merge instead of overwriting.
  * `status` lets a human-facing layer know what phase the team is in.

  The cost: the state schema grows, and every node sees a wider schema.
  Keep it narrow, and give each node a narrow `input_schema` (EX04).
"""
    )


if __name__ == "__main__":
    main()
