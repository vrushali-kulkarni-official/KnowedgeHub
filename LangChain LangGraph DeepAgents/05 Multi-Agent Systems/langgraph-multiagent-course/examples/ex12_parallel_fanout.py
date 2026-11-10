"""EX12 - Parallel agents: fan-out with `Send`, and fan-in.

Run:  PYTHONPATH=examples .venv/bin/python examples/ex12_parallel_fanout.py

PARALLELISM is the one multi-agent benefit that a single agent CANNOT get.
If three subtasks are independent, running them concurrently is roughly a
3x latency win for the same token spend.

This is also the reason to reach for multi-agent LATE: you only find out that
subtasks are independent after you have done the work of splitting them.

THE MECHANISM
-------------
`Send("node", payload)` from a conditional edge fans out.  All the Sends
produced by one node run in the SAME superstep, concurrently.

    def fanout(state):
        return [Send("worker", {"task": t}) for t in tasks]

    g.add_conditional_edges("planner", fanout, ["worker"])

THE MERGE (fan-in)
------------------
Every branch writes to the same state channel, so the channel needs a
reducer that MERGES rather than OVERWRITES:

    results: Annotated[list[str], lambda a, b: a + b]      # append

THE TWO TRAPS
-------------
  TRAP 1  A `Send` payload BYPASSES the target node's `input_schema`
          (verified in EX04).  Build payloads from explicit fields.

  TRAP 2  A `Send` payload is NOT filtered, so a secret in the graph state
          can leak into every branch.  Copy fields explicitly.
"""

from __future__ import annotations

import time
from typing import Annotated

from langchain.agents import AgentState, create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from _common import ai, once_then_final, scripted, text_of, user

LIMIT = {"recursion_limit": 25}


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class FanState(AgentState):
    """The shared state for a fan-out / fan-in team."""

    question: str
    topics: list[str]
    """The plan: what each branch will investigate."""

    results: Annotated[list[dict], lambda a, b: a + b]
    """Branch outputs, merged by APPENDING."""

    answer: str


# ---------------------------------------------------------------------------
# The branches
# ---------------------------------------------------------------------------


@tool
def fetch(topic: str) -> str:
    """Fetch information about a topic."""
    return f"raw data for {topic}"


def make_branch_agent(tag: str):
    """One agent per branch.  IMPORTANT: one agent INSTANCE per branch.

    If you share one agent instance across branches, they share the model's
    cursor and the outputs get mixed up (you will see 'scripted model
    exhausted' or duplicated answers).
    """
    model = scripted(
        router=once_then_final(
            "fetch",
            {"topic": tag},
            final=f"{tag}: 3 findings about {tag}",
        )
    )
    return create_agent(model, tools=[fetch], name=f"branch_{tag}")


def build_parallel_team(topics: list[str]):
    agents = {t: make_branch_agent(t) for t in topics}

    def planner(state: FanState):
        return {"topics": topics}

    def worker(state: FanState):
        """The branch body.  `state["task"]` came from the Send payload."""
        topic = state["task"]
        result = agents[topic].invoke({"messages": [HumanMessage(content=topic)]}, LIMIT)
        answer = text_of(result["messages"][-1])
        return {
            "results": [{"topic": topic, "answer": answer}],
            "messages": [AIMessage(content=f"[{topic}] {answer}")],
        }

    def fanout(state: FanState):
        # One Send per branch -> all branches run in the SAME superstep.
        return [
            Send("worker", {"task": t, "question": state["question"], "messages": state["messages"]})
            for t in topics
        ]

    def joiner(state: FanState):
        return {"answer": " | ".join(r["answer"] for r in state["results"])}

    g = StateGraph(FanState)
    g.add_node("planner", planner)
    g.add_node("worker", worker)
    g.add_node("joiner", joiner)
    g.add_edge(START, "planner")
    g.add_conditional_edges("planner", fanout, ["worker"])
    g.add_edge("worker", "joiner")
    g.add_edge("joiner", END)
    return g.compile()


# ---------------------------------------------------------------------------
# Serial vs parallel
# ---------------------------------------------------------------------------


def build_serial_team(topics: list[str]):
    """The same work, but one branch at a time."""
    agents = {t: make_branch_agent(t) for t in topics}

    def planner(state: FanState):
        return {"topics": topics}

    def worker(state: FanState):
        topic = state["task"]
        result = agents[topic].invoke({"messages": [HumanMessage(content=topic)]}, LIMIT)
        answer = text_of(result["messages"][-1])
        return {
            "results": [{"topic": topic, "answer": answer}],
            "messages": [AIMessage(content=f"[{topic}] {answer}")],
        }

    def route_next(state: FanState):
        done = {r["topic"] for r in state["results"]}
        remaining = [t for t in topics if t not in done]
        if remaining:
            return Send("worker", {"task": remaining[0], "messages": state["messages"]})
        return "joiner"

    def joiner(state: FanState):
        return {"answer": " | ".join(r["answer"] for r in state["results"])}

    g = StateGraph(FanState)
    g.add_node("planner", planner)
    g.add_node("worker", worker)
    g.add_node("joiner", joiner)
    g.add_edge(START, "planner")
    g.add_conditional_edges("planner", route_next, ["worker", "joiner"])
    g.add_conditional_edges("worker", route_next, ["worker", "joiner"])
    g.add_edge("joiner", END)
    return g.compile()


# ---------------------------------------------------------------------------
# A slow tool, to make the timing difference visible
# ---------------------------------------------------------------------------


def build_slow_parallel(n: int = 4):
    """Parallel branches with a genuinely slow tool."""

    @tool
    def slow_fetch(topic: str) -> str:
        """Fetch information (slowly)."""
        time.sleep(0.35)
        return f"data for {topic}"

    def make(tag):
        model = scripted(router=once_then_final("slow_fetch", {"topic": tag}, final=f"{tag} done"))
        return create_agent(model, tools=[slow_fetch], name=f"slow_{tag}")

    agents = {f"t{i}": make(f"t{i}") for i in range(n)}

    def worker(state: FanState):
        topic = state["task"]
        r = agents[topic].invoke({"messages": [HumanMessage(content=topic)]}, LIMIT)
        return {"results": [{"topic": topic, "answer": text_of(r["messages"][-1])}]}

    def fanout(state: FanState):
        return [Send("worker", {"task": t, "messages": state["messages"]}) for t in agents]

    g = StateGraph(FanState)
    g.add_node("planner", lambda s: {})
    g.add_node("worker", worker)
    g.add_edge(START, "planner")
    g.add_conditional_edges("planner", fanout, ["worker"])
    g.add_edge("worker", END)
    return g.compile(), n


def main() -> None:
    print("=" * 74)
    print("EX12  Parallel agents: fan-out and fan-in")
    print("=" * 74)

    topics = ["pricing", "security", "performance"]
    par = build_parallel_team(topics)
    out = par.invoke({"messages": [user("Analyse LangGraph")], "question": "Analyse LangGraph"}, LIMIT)
    print("\nPARALLEL TEAM")
    print("-" * 74)
    print(f"  branches : {len(topics)}")
    for r in out["results"]:
        print(f"     - {r['topic']:<12} {r['answer']}")
    print(f"  answer   : {out['answer'][:80]}")

    ser = build_serial_team(topics)
    out2 = ser.invoke({"messages": [user("Analyse LangGraph")], "question": "Analyse LangGraph"}, LIMIT)
    print("\nSERIAL TEAM (same work, one at a time)")
    print("-" * 74)
    for r in out2["results"]:
        print(f"     - {r['topic']:<12} {r['answer']}")

    print("\n" + "=" * 74)
    print("THE TIMING DIFFERENCE (4 branches, 0.35s tool each)")
    print("=" * 74)
    par_app, n = build_slow_parallel(4)

    t0 = time.perf_counter()
    par_app.invoke({"messages": [user("go")], "results": []}, LIMIT)
    par_ms = (time.perf_counter() - t0) * 1000

    ser_app = build_slow_parallel(4)
    # force serial by chaining: build a serial variant
    def build_serial_slow(n=4):
        @tool
        def slow_fetch(topic: str) -> str:
            """Fetch information (slowly)."""
            time.sleep(0.35)
            return f"data for {topic}"

        def make(tag):
            model = scripted(router=once_then_final("slow_fetch", {"topic": tag}, final=f"{tag} done"))
            return create_agent(model, tools=[slow_fetch], name=f"slow_{tag}")

        agents = {f"t{i}": make(f"t{i}") for i in range(n)}

        def worker(state: FanState):
            topic = state["task"]
            r = agents[topic].invoke({"messages": [HumanMessage(content=topic)]}, LIMIT)
            return {"results": [{"topic": topic, "answer": text_of(r["messages"][-1])}]}

        def route(state: FanState):
            done = {r["topic"] for r in state["results"]}
            remaining = [t for t in agents if t not in done]
            if remaining:
                return Send("worker", {"task": remaining[0], "messages": state["messages"]})
            return END

        g = StateGraph(FanState)
        g.add_node("planner", lambda s: {})
        g.add_node("worker", worker)
        g.add_edge(START, "planner")
        g.add_conditional_edges("planner", route, ["worker", END])
        g.add_conditional_edges("worker", route, ["worker", END])
        return g.compile()

    ser_app = build_serial_slow(4)
    t0 = time.perf_counter()
    ser_app.invoke({"messages": [user("go")], "results": []}, LIMIT)
    ser_ms = (time.perf_counter() - t0) * 1000

    print(f"  parallel : {par_ms:8.1f} ms   (4 x 0.35s tool)")
    print(f"  serial   : {ser_ms:8.1f} ms")
    print(f"  speed-up : {ser_ms / par_ms:.2f}x")
    print()
    print("  Same tokens, same agents - only the SCHEDULE changed.")
    print("  This is benefit #2 of multi-agent (L01), and the only one a")
    print("  single agent cannot get.")

    print()
    print("=" * 74)
    print("FAN-IN: MERGING THE RESULTS")
    print("=" * 74)
    print(
        """
  The branch results land in ONE channel, so the channel needs a MERGING
  reducer:

      results: Annotated[list[dict], lambda a, b: a + b]

  With a plain (last-write-wins) channel, the branches would overwrite each
  other and you would lose all but the last one.

  FAN-IN SHAPES
    concat   - keep everything, in order.        (default)
    dedupe   - drop exact duplicates.
    rank     - keep the top N by some score.
    vote     - keep only the most common answer.  (see EX13)
    judge    - let a model pick the best one.    (see EX13)

  Always cap the fan-in.  Merging 50 branch outputs into one prompt is
  prompt-stuffing with extra steps.
"""
    )


if __name__ == "__main__":
    main()
