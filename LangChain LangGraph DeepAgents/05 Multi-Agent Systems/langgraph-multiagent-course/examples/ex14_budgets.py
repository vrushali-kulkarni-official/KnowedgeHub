"""EX14 - Budgets, limits, and the failure modes that actually bite.

Run:  PYTHONPATH=examples .venv/bin/python examples/ex14_budgets.py

A multi-agent system can spend money in ways a single agent cannot:

  * N agents x M turns each, instead of 1 agent x M turns.
  * a swarm that hands off in a circle, forever.
  * a parallel fan-out where every branch is expensive.
  * a tool that retries internally, inside every branch.

You need THREE layers of defence:

  LAYER 1 - PER-AGENT LIMITS (the middleware)
      ModelCallLimitMiddleware / ToolCallLimitMiddleware.  These are attached
      to ONE agent, so they are the natural place for a per-agent budget.

  LAYER 2 - GRAPH LIMITS (the config)
      recursion_limit, plus node-level `retry_policy` and `timeout`.

  LAYER 3 - TEAM LIMITS (your own code)
      A shared token/cost counter in the team state, checked by the
      supervisor before it dispatches more work.

This file demonstrates all three, plus the five failure modes you will
actually meet.
"""

from __future__ import annotations

from typing import Annotated

from langchain.agents import AgentState, create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from _common import ai, once_then_final, scripted, text_of, tool_call, user

LIMIT = {"recursion_limit": 30}


# ---------------------------------------------------------------------------
# LAYER 1 - per-agent limits
# ---------------------------------------------------------------------------


@tool
def ping(x: str) -> str:
    """A cheap tool that always succeeds."""
    return "pong"


def model_call_limit():
    """Stop an agent after N model calls, whatever it is doing."""

    def router(msgs):
        # A model that ALWAYS asks for a tool -> an infinite ReAct loop.
        return tool_call("ping", {"x": "again"}, call_id="c1")

    model = scripted(router=router)
    agent = create_agent(
        model,
        tools=[ping],
        middleware=[ModelCallLimitMiddleware(thread_limit=3, exit_behavior="end")],
    )
    out = agent.invoke({"messages": [user("loop forever")]}, LIMIT)
    return out["messages"]


def tool_call_limit():
    """Stop an agent after N calls to one specific tool."""

    def router(msgs):
        return tool_call("ping", {"x": "again"}, call_id="c1")

    model = scripted(router=router)
    agent = create_agent(
        model,
        tools=[ping],
        middleware=[ToolCallLimitMiddleware(tool_name="ping", thread_limit=2, exit_behavior="end")],
    )
    out = agent.invoke({"messages": [user("loop forever")]}, LIMIT)
    return out["messages"]


# ---------------------------------------------------------------------------
# LAYER 2 - graph limits
# ---------------------------------------------------------------------------


def node_retry_policy():
    """Retry a flaky node at the GRAPH level."""
    attempts = {"n": 0}

    def flaky(state):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError(f"transient failure #{attempts['n']}")
        return {"answer": "succeeded on attempt 3"}

    class S(AgentState):
        answer: str

    g = StateGraph(S)
    g.add_node(
        "flaky",
        flaky,
        retry_policy=RetryPolicy(
            max_attempts=5,
            initial_interval=0.01,
            backoff_factor=2.0,
            retry_on=RuntimeError,
        ),
    )
    g.add_edge(START, "flaky")
    g.add_edge("flaky", END)
    app = g.compile()
    out = app.invoke({"messages": [user("go")]}, LIMIT)
    return out["answer"], attempts["n"]


# ---------------------------------------------------------------------------
# LAYER 3 - a team-level budget
# ---------------------------------------------------------------------------


class BudgetState(AgentState):
    """A team with a shared budget counter."""

    budget_used: int
    max_budget: int
    results: Annotated[list[str], lambda a, b: a + b]


def team_budget():
    """The supervisor refuses to dispatch once the budget is spent."""

    def supervisor(state: BudgetState):
        if state["budget_used"] >= state["max_budget"]:
            return {"results": ["BUDGET EXHAUSTED - stopping"], "budget_used": state["budget_used"]}
        # Spend one unit of budget per dispatch.
        return {"budget_used": state["budget_used"] + 1}

    def worker(state: BudgetState):
        return {"results": [f"work {state['budget_used']}"]}

    def route(state: BudgetState):
        return "worker" if state["budget_used"] < state["max_budget"] else "done"

    def done(state: BudgetState):
        return {}

    g = StateGraph(BudgetState)
    g.add_node("supervisor", supervisor)
    g.add_node("worker", worker)
    g.add_node("done", done)
    g.add_edge(START, "supervisor")
    g.add_conditional_edges("supervisor", route, ["worker", "done"])
    g.add_conditional_edges("worker", lambda s: "supervisor", ["supervisor"])
    g.add_edge("done", END)
    app = g.compile()
    return app.invoke(
        {"messages": [user("go")], "budget_used": 0, "max_budget": 2, "results": []}, LIMIT
    )


# ---------------------------------------------------------------------------
# THE FIVE FAILURE MODES
# ---------------------------------------------------------------------------


def failure_mode_1a_invocation_error():
    """A BAD ARGUMENT does NOT crash the graph.

    LangChain raises `ToolInvocationError` when the tool cannot even be
    called (wrong argument types, missing fields).  That error is turned
    into ToolMessage TEXT, so the model sees it and can correct itself.
    """

    @tool
    def needs_int(count: int) -> str:
        """Needs an integer."""
        return f"count={count}"

    model = scripted(router=once_then_final("needs_int", {"count": "not-a-number"}, final="gave up"))
    agent = create_agent(model, tools=[needs_int])
    out = agent.invoke({"messages": [user("go")]}, LIMIT)
    tool_msgs = [text_of(m) for m in out["messages"] if m.type == "tool"]
    return tool_msgs[0][:120] if tool_msgs else ""


def failure_mode_1b_runtime_error():
    """A tool that RAISES crashes the graph.

    Anything that is not a `ToolInvocationError` propagates out of the tool
    and fails the whole run.  If you want a tool failure to be recoverable,
    catch it inside the tool and return an error string.
    """

    @tool
    def flaky_tool(x: str) -> str:
        """Sometimes fails."""
        raise RuntimeError("upstream 503")

    model = scripted(router=once_then_final("flaky_tool", {"x": "a"}, final="gave up"))
    agent = create_agent(model, tools=[flaky_tool])
    try:
        agent.invoke({"messages": [user("go")]}, LIMIT)
        return "no exception (unexpected)"
    except Exception as exc:
        return f"{type(exc).__name__}: {str(exc)[:80]}"


def failure_mode_1c_caught_inside_tool():
    """The fix: catch inside the tool, return an error STRING."""

    @tool
    def safe_tool(x: str) -> str:
        """Never raises."""
        try:
            raise RuntimeError("upstream 503")
        except RuntimeError as exc:
            return f"ERROR: {exc}. Tell the user the service is down."

    model = scripted(router=once_then_final("safe_tool", {"x": "a"}, final="told the user"))
    agent = create_agent(model, tools=[safe_tool])
    out = agent.invoke({"messages": [user("go")]}, LIMIT)
    tool_msgs = [text_of(m) for m in out["messages"] if m.type == "tool"]
    return tool_msgs[0][:120] if tool_msgs else ""


def failure_mode_2_context_overflow():
    """A transcript that outgrows the model's window."""

    class S(AgentState):
        answer: str

    def flood(state: S):
        huge = "z" * 200_000
        return {"messages": [AIMessage(content=huge)], "answer": "wrote a lot"}

    g = StateGraph(S)
    g.add_node("flood", flood)
    g.add_edge(START, "flood")
    g.add_edge("flood", END)
    app = g.compile()
    out = app.invoke({"messages": [user("go")]}, LIMIT)
    return len(out["messages"][-1].content)


def failure_mode_3_no_termination():
    """The 9999 recursion limit."""

    from langchain.agents.factory import create_agent as _ca
    import inspect

    src = inspect.getsource(_ca)
    for line in src.splitlines():
        if "recursion_limit" in line:
            return line.strip()
    return "not found"


def failure_mode_4_lost_update():
    """Two nodes writing the same key in one step."""

    class S(AgentState):
        slot: str

    def a(state: S):
        return {"slot": "from-a"}

    def b(state: S):
        return {"slot": "from-b"}

    g = StateGraph(S)
    g.add_node("a", a)
    g.add_node("b", b)
    g.add_edge(START, "a")
    g.add_edge(START, "b")
    g.add_edge("a", END)
    g.add_edge("b", END)
    app = g.compile()
    try:
        app.invoke({"messages": [user("go")]}, LIMIT)
        return "no error"
    except Exception as exc:
        return f"{type(exc).__name__}: {str(exc).splitlines()[0]}"


def failure_mode_5_silent_state_drop():
    """A key that is not in the schema disappears without a trace."""

    class S(AgentState):
        known: str

    def writer(state: S):
        return {"known": "ok", "unknown": "gone"}

    g = StateGraph(S)
    g.add_node("w", writer)
    g.add_edge(START, "w")
    g.add_edge("w", END)
    app = g.compile()
    out = app.invoke({"messages": [user("go")]}, LIMIT)
    return f"unknown in result? {'unknown' in out}"


def main() -> None:
    print("=" * 74)
    print("EX14  Budgets, limits and failure modes")
    print("=" * 74)

    print("\nLAYER 1 - ModelCallLimitMiddleware")
    print("-" * 74)
    msgs = model_call_limit()
    print(f"  messages produced : {len(msgs)}")
    print(f"  final message     : {text_of(msgs[-1])[:70]}")

    print("\nLAYER 1 - ToolCallLimitMiddleware")
    print("-" * 74)
    msgs2 = tool_call_limit()
    print(f"  messages produced : {len(msgs2)}")
    print(f"  final message     : {text_of(msgs2[-1])[:70]}")

    print("\nLAYER 2 - node retry_policy")
    print("-" * 74)
    answer, attempts = node_retry_policy()
    print(f"  result     : {answer} (took {attempts} attempts)")

    print("\nLAYER 3 - a team-level budget")
    print("-" * 74)
    out = team_budget()
    print(f"  budget used : {out['budget_used']} of {out['max_budget']}")
    print(f"  results     : {out['results']}")

    print()
    print("=" * 74)
    print("THE FIVE FAILURE MODES")
    print("=" * 74)

    print("\n1a. TOOL INVOCATION ERROR (bad arguments) -> swallowed into a ToolMessage")
    print(f"   {failure_mode_1a_invocation_error()}")
    print()
    print("1b. TOOL RUNTIME ERROR -> crashes the graph")
    print(f"   {failure_mode_1b_runtime_error()}")
    print()
    print("1c. THE FIX: catch inside the tool")
    print(f"   {failure_mode_1c_caught_inside_tool()}")

    print("\n2. CONTEXT OVERFLOW")
    n = failure_mode_2_context_overflow()
    print(f"   a node wrote {n} chars into the transcript - legal,")
    print("   but the NEXT model call will fail on a real model.")

    print("\n3. NO TERMINATION")
    print(f"   {failure_mode_3_no_termination()}")

    print("\n4. LOST UPDATE")
    print(f"   {failure_mode_4_lost_update()}")

    print("\n5. SILENT STATE DROP")
    print(f"   {failure_mode_5_silent_state_drop()}")

    print()
    print("=" * 74)
    print("THE PRODUCTION BUDGET RECIPE")
    print("=" * 74)
    print(
        """
  # 1. Every agent gets a hard model-call cap.
  agent = create_agent(
      model, tools=tools,
      middleware=[
          ModelCallLimitMiddleware(thread_limit=8, exit_behavior="end"),
          ToolCallLimitMiddleware(thread_limit=20, exit_behavior="end"),
      ],
  )

  # 2. Every graph gets a recursion cap (create_agent's default is 9999!).
  app.invoke(inputs, {"recursion_limit": 30})

  # 3. Every node that calls a flaky service gets a retry policy.
  g.add_node("call_api", call_api,
             retry_policy=RetryPolicy(max_attempts=3, retry_on=(TimeoutError,)))

  # 4. The TEAM gets a shared budget counter in the state, and the
  #    supervisor checks it before dispatching more work.

  # 5. Swarms get a visit counter (EX09) AND a `RemainingSteps` check.
"""
    )


if __name__ == "__main__":
    main()
