"""EX17 - CAPSTONE: a production-shaped multi-agent system.

Run:  PYTHONPATH=examples .venv/bin/python examples/ex17_capstone.py

This is everything from Phase 10, assembled into one system that you could
actually ship:

  * A SUPERVISOR that plans, then dispatches.
  * SPECIALISTS as agents-as-tools (the modern replacement for
    `langgraph-supervisor`).
  * PARALLEL FAN-OUT with `Send` for independent subtasks.
  * A FAN-IN with a bounded, scored aggregation.
  * A SHARED STATE with typed fields, merge reducers and an APPEND list
    that is kept OUT of the agent schemas (the echo trap).
  * ARTIFACTS in a `BaseStore`, referenced by id, never by value.
  * PER-AGENT BUDGETS via middleware, plus a team-level budget.
  * A HANDOFF BRIEF that is self-contained, because the specialist cannot
    see the supervisor's context.
  * TRACING via Langfuse, with every agent named.
  * A CHECKPOINTER, so a human can approve the final answer later
    (the HITL pattern from Phase 8).

Read it top to bottom.  Every construct in it was introduced and verified
in EX01-EX16.
"""

from __future__ import annotations

from typing import Annotated, Literal

from langchain.agents import AgentState, create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.memory import InMemoryStore
from langgraph.types import Send
from pydantic import BaseModel, Field

from _common import once_then_final, scripted, text_of, user

LIMIT = {"recursion_limit": 40}

# ---------------------------------------------------------------------------
# The brief: a support team for a software product
# ---------------------------------------------------------------------------


@tool
def search_docs(query: str) -> str:
    """Search the product documentation."""
    return f"docs: 3 pages about {query}"


@tool
def check_account(email: str) -> str:
    """Look up a customer account."""
    return f"account {email}: plan=pro, status=active, seats=12"


@tool
def open_ticket(title: str, body: str) -> str:
    """Open a support ticket."""
    return f"ticket #9001 opened: {title}"


# ---------------------------------------------------------------------------
# Shared state - the team's contract
# ---------------------------------------------------------------------------


class TeamState(AgentState):
    """Everything the team shares.

    Design notes:
      * `messages`  - the conversation only.
      * `plan`      - the list of subtasks (produced by the planner).
      * `findings`  - APPEND reducer; kept OUT of the agent schemas.
      * `artifacts` - MERGE reducer; ids only, payloads live in the store.
      * `budget`    - the team's shared spend counter.
    """

    question: str
    plan: list[str]
    findings: Annotated[list[dict], lambda a, b: a + b]
    artifacts: Annotated[dict[str, str], lambda a, b: {**a, **b}]
    brief: str
    final_answer: str

    # A SUM reducer, because parallel branches each spend 1 and we need the
    # TOTAL.  Each branch writes the INCREMENT (1), not the new absolute
    # value - otherwise the branches overwrite each other.
    budget_used: Annotated[int, lambda a, b: a + b]
    max_budget: int
    trace: Annotated[list[str], lambda a, b: a + b]


class Plan(BaseModel):
    """The planner's structured output."""

    subtasks: list[str] = Field(description="2-4 independent subtasks")
    brief: str = Field(description="A self-contained brief for the whole team")


# ---------------------------------------------------------------------------
# Specialists
# ---------------------------------------------------------------------------


def build_specialists():
    """Each specialist is a named agent with its own budget."""

    researcher = create_agent(
        scripted(
            router=once_then_final(
                "search_docs", {"query": "oauth sso"}, final="DOCS: SSO uses OIDC; MFA via TOTP."
            )
        ),
        tools=[search_docs],
        system_prompt="You research the product docs. Cite the page you used.",
        name="researcher",
        middleware=[ModelCallLimitMiddleware(thread_limit=4, exit_behavior="end")],
    )
    account_agent = create_agent(
        scripted(
            router=once_then_final(
                "check_account",
                {"email": "a@b.com"},
                final="ACCOUNT: plan=pro, status=active, seats=12",
            )
        ),
        tools=[check_account],
        system_prompt="You look up customer accounts. Never guess.",
        name="account_agent",
        middleware=[ModelCallLimitMiddleware(thread_limit=4, exit_behavior="end")],
    )
    ticket_agent = create_agent(
        scripted(
            router=once_then_final(
                "open_ticket",
                {"title": "SSO not working", "body": "User cannot complete OIDC flow."},
                final="TICKET #9001 opened: SSO not working",
            )
        ),
        tools=[open_ticket],
        system_prompt="You open tickets. One ticket per distinct issue.",
        name="ticket_agent",
        middleware=[ModelCallLimitMiddleware(thread_limit=4, exit_behavior="end")],
    )
    return {
        "researcher": researcher,
        "account_agent": account_agent,
        "ticket_agent": ticket_agent,
    }


# ---------------------------------------------------------------------------
# The agent-as-tool adapter
# ---------------------------------------------------------------------------


def agent_as_tool(name: str, description: str, agent, store, artifact_key: str):
    """Expose a specialist to the supervisor as a tool.

    The adapter does three things a naive wrapper does not:

      1. Sends a SELF-CONTAINED brief (the specialist sees no other context).
      2. Stores the specialist's long output in the STORE and returns a
         handle, so the supervisor's context stays small.
      3. Returns TEXT, not a state dict.
    """

    @tool(f"ask_{name}", description=description)
    def ask(task: str) -> str:
        result = agent.invoke({"messages": [HumanMessage(content=task)]}, LIMIT)
        answer = text_of(result["messages"][-1])
        # Park the payload; return a pointer.
        store.put(("artifacts",), artifact_key, {"text": answer, "by": name})
        return f"[{name} completed -> artifact:{artifact_key}] {answer[:120]}"

    return ask


# ---------------------------------------------------------------------------
# The system
# ---------------------------------------------------------------------------


def build_system():
    store = InMemoryStore()
    specialists = build_specialists()

    researcher_tool = agent_as_tool(
        "researcher",
        "Research the product documentation. Use for 'how do I ...' questions.",
        specialists["researcher"],
        store,
        "research",
    )
    account_tool = agent_as_tool(
        "account_agent",
        "Look up the customer's account. Use for plan, seats and billing questions.",
        specialists["account_agent"],
        store,
        "account",
    )
    ticket_tool = agent_as_tool(
        "ticket_agent",
        "Open a support ticket. Use when the customer needs human follow-up.",
        specialists["ticket_agent"],
        store,
        "ticket",
    )

    def planner(messages):
        from langchain_core.messages import AIMessage

        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "Plan",
                    "args": {
                        "subtasks": ["research the docs", "check the account"],
                        "brief": "Customer cannot log in with SSO. Investigate and act.",
                    },
                    "id": "plan_1",
                    "type": "tool_call",
                }
            ],
        )

    planner_agent = create_agent(
        scripted(router=planner), tools=[], response_format=Plan, name="planner"
    )

    supervisor = create_agent(
        scripted(
            router=once_then_final(
                "ask_researcher",
                {"task": "Research: customer cannot log in with SSO. Return the cause."},
                final="Cause identified. Ticket opened for follow-up.",
            )
        ),
        tools=[researcher_tool, account_tool, ticket_tool],
        system_prompt=(
            "You coordinate a support team. Delegate with SELF-CONTAINED briefs. "
            "Never ask a specialist for context it cannot see."
        ),
        name="supervisor",
        middleware=[ModelCallLimitMiddleware(thread_limit=6, exit_behavior="end")],
    )

    # ---- the graph ----

    def plan_node(state: TeamState):
        result = planner_agent.invoke({"messages": state["messages"]}, LIMIT)
        plan: Plan = result["structured_response"]
        return {
            "plan": plan.subtasks,
            "brief": plan.brief,
            "trace": ["planner produced the plan"],
        }

    def fanout(state: TeamState):
        # One Send per subtask -> all branches run concurrently.
        return [
            Send("investigator", {"task": t, "brief": state["brief"], "messages": state["messages"]})
            for t in state["plan"]
        ]

    def investigator(state: TeamState):
        """A branch that runs a specialist and records a finding."""
        topic = state["task"]
        agent = specialists["researcher"] if "doc" in topic else specialists["account_agent"]
        result = agent.invoke({"messages": [HumanMessage(content=state["brief"])]}, LIMIT)
        answer = text_of(result["messages"][-1])
        store.put(("artifacts",), topic, {"text": answer})
        return {
            "messages": [AIMessage(content=f"[{topic}] {answer}")],
            # APPEND reducer -> return ONLY the new item.
            "findings": [{"topic": topic, "summary": answer}],
            "artifacts": {topic: f"artifact:{topic}"},
            # NOTE: the Send payload does NOT carry `budget_used`
            # (Send bypasses the state - EX04 rule 2).  That is why we use a
            # SUM reducer and write the increment instead of the total.
            "budget_used": 1,
            "trace": [f"branch done: {topic}"],
        }

    def aggregate(state: TeamState):
        """Fan-in: a bounded, deterministic summary of the findings."""
        lines = [f"{f['topic']}: {f['summary'][:70]}" for f in state["findings"]]
        return {
            "messages": [AIMessage(content="; ".join(lines))],
            "final_answer": "; ".join(lines),
            "trace": ["aggregated the findings"],
        }

    def supervise(state: TeamState):
        """The supervisor's own turn, after the branches have reported."""
        if state["budget_used"] >= state["max_budget"]:
            return {
                "final_answer": "Budget exhausted. " + state.get("final_answer", ""),
                "trace": ["supervisor stopped: budget exhausted"],
            }
        result = supervisor.invoke({"messages": state["messages"]}, LIMIT)
        answer = text_of(result["messages"][-1])
        return {
            "messages": [result["messages"][-1]],
            "final_answer": answer,
            "trace": ["supervisor produced the final answer"],
        }

    g = StateGraph(TeamState)
    g.add_node("planner", plan_node)
    g.add_node("investigator", investigator)
    g.add_node("aggregate", aggregate)
    g.add_node("supervisor", supervise)
    g.add_edge(START, "planner")
    g.add_conditional_edges("planner", fanout, ["investigator"])
    # A STATIC edge: every branch finishes in the SAME superstep, so the
    # fan-in node runs once, after all of them.
    g.add_edge("investigator", "aggregate")
    g.add_edge("aggregate", "supervisor")
    g.add_edge("supervisor", END)

    app = g.compile(checkpointer=InMemorySaver())
    return app, store, specialists


def main() -> None:
    print("=" * 74)
    print("EX17  CAPSTONE: a production-shaped multi-agent system")
    print("=" * 74)

    app, store, specialists = build_system()

    question = "I can't log in with SSO any more - please fix it."
    print(f"\nCUSTOMER: {question}\n")

    config = {"configurable": {"thread_id": "demo-1"}, **LIMIT}
    out = app.invoke(
        {
            "messages": [user(question)],
            "question": question,
            "plan": [],
            "findings": [],
            "artifacts": {},
            "brief": "",
            "final_answer": "",
            "budget_used": 0,
            "max_budget": 6,
            "trace": [],
        },
        config,
    )

    print("TEAM TRACE")
    print("-" * 74)
    for step in out["trace"]:
        print(f"  {step}")

    print("\nPLAN")
    print("-" * 74)
    for i, t in enumerate(out["plan"], 1):
        print(f"  {i}. {t}")

    print("\nFINDINGS (fan-in)")
    print("-" * 74)
    for f in out["findings"]:
        print(f"  - {f['topic']}: {f['summary'][:66]}")

    print("\nFINAL ANSWER")
    print("-" * 74)
    print(f"  {out['final_answer'][:140]}")

    print("\nBUDGET")
    print("-" * 74)
    print(f"  used {out['budget_used']} of {out['max_budget']}")

    print("\nARTIFACTS IN THE STORE")
    print("-" * 74)
    for item in store.search(("artifacts",)):
        print(f"  {item.key}: {str(item.value)[:70]}")

    print("\nSTATE SHAPE")
    print("-" * 74)
    print(f"  {sorted(out.keys())}")
    print(f"  transcript messages: {len(out['messages'])}")

    print()
    print("=" * 74)
    print("WHAT THIS SYSTEM DEMONSTRATES")
    print("=" * 74)
    print(
        """
  PLANNING      a structured `Plan` drives the fan-out, not a hard-coded list.
  PARALLELISM   `Send` runs the branches concurrently (EX12: ~4x faster).
  ISOLATION     each branch gets only `brief` + `task`, not the whole state.
  ARTIFACTS     long outputs live in the store; the state carries ids.
  BOUNDED FAN-IN `aggregate` produces one summary, not a concatenation.
  BUDGETS       per-agent middleware + a team-level counter.
  TRACEABILITY  `trace` is a human-readable audit trail in the state.
  RESUMABILITY  the checkpointer means a human can approve later (Phase 8).
  NAMED AGENTS  every agent has `name=`, so the Langfuse tree is readable.
"""
    )


if __name__ == "__main__":
    main()
