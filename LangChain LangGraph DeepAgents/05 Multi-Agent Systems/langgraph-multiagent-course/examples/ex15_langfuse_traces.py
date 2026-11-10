"""EX15 - Langfuse trace trees for multi-agent systems.

Run:  PYTHONPATH=examples .venv/bin/python examples/ex15_langfuse_traces.py

WHY YOU NEED THIS
-----------------
A multi-agent run produces a TREE of model calls, not a line.  When the
answer is wrong, you need to know:

  * which agent made the bad call?
  * what did the supervisor see when it chose that agent?
  * how many tokens did the whole tree burn?
  * did the specialist get a useful brief, or a useless one?

Langfuse (MIT licensed, self-hostable, free tier) draws that tree for you.

HOW IT WORKS
------------
Langfuse v5 is built on OpenTelemetry.  You attach a `CallbackHandler` to
the run and every LangChain / LangGraph step becomes a nested span:

    LangGraph
      supervisor
        researcher          <- create_agent(name="researcher")
          model
          tools
        writer
          model

NOTE THE AGENT NAMES: `create_agent(name="researcher")` is what makes the
span readable.  Without a name you get "LangGraph" over and over.

THIS FILE RUNS OFFLINE
----------------------
We point Langfuse at an in-memory OpenTelemetry exporter, so you can see the
exact tree your code produces without a server, an API key, or a network.
When you are ready for the real thing, see the SWAP block at the bottom.
"""

from __future__ import annotations

from typing import Annotated

from langchain.agents import AgentState, create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph

from _common import once_then_final, scripted, text_of, user

LIMIT = {"recursion_limit": 20}


# ---------------------------------------------------------------------------
# A tiny team to trace
# ---------------------------------------------------------------------------


@tool
def web_search(query: str) -> str:
    """Search the web."""
    return f"web: 2 results for {query}"


@tool
def read_invoice(invoice_id: str) -> str:
    """Read an invoice."""
    return f"invoice {invoice_id}: 49 EUR, paid"


def build_team():
    """A supervisor with two specialists - each a named agent."""

    def as_tool(name: str, description: str, agent):
        @tool(f"ask_{name}", description=description)
        def ask(task: str) -> str:
            r = agent.invoke({"messages": [HumanMessage(content=task)]}, LIMIT)
            return text_of(r["messages"][-1])

        return ask

    researcher = create_agent(
        scripted(router=once_then_final("web_search", {"query": "langgraph"}, final="3 findings")),
        tools=[web_search],
        name="researcher",
    )
    billing = create_agent(
        scripted(router=once_then_final("read_invoice", {"invoice_id": "INV-1"}, final="49 EUR, paid")),
        tools=[read_invoice],
        name="billing",
    )

    supervisor = create_agent(
        scripted(
            router=once_then_final(
                "ask_researcher",
                {"task": "find info about langgraph"},
                final="Here is the summary.",
            )
        ),
        tools=[
            as_tool("researcher", "Delegate research.", researcher),
            as_tool("billing", "Delegate billing.", billing),
        ],
        name="supervisor",
    )

    class TeamState(AgentState):
        results: Annotated[list[str], lambda a, b: a + b]

    def sup_node(state: TeamState):
        r = supervisor.invoke({"messages": state["messages"]}, LIMIT)
        return {"messages": [r["messages"][-1]], "results": [text_of(r["messages"][-1])]}

    g = StateGraph(TeamState)
    g.add_node("supervisor", sup_node)
    g.add_edge(START, "supervisor")
    g.add_edge("supervisor", END)
    return g.compile()


# ---------------------------------------------------------------------------
# The offline tracer
# ---------------------------------------------------------------------------


def make_offline_tracer():
    """Langfuse wired to an in-memory OpenTelemetry exporter.

    Returns (langfuse_client, callback_handler, exporter).
    """
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )
    from langfuse import Langfuse
    from langfuse.langchain import CallbackHandler

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    client = Langfuse(
        public_key="pk-lf-offline",
        secret_key="sk-lf-offline",
        base_url="http://localhost:9999",  # nothing is actually sent anywhere
        tracer_provider=provider,
        tracing_enabled=True,
    )
    return client, CallbackHandler(), exporter


def print_tree(exporter):
    """Print the captured span tree."""
    spans = exporter.get_finished_spans()
    rows = []
    for s in spans:
        ctx = s.get_span_context()
        parent = s.parent
        rows.append(
            {
                "name": s.name,
                "span_id": format(ctx.span_id, "016x"),
                "parent": format(parent.span_id, "016x") if parent else None,
            }
        )

    by_parent: dict[str | None, list[dict]] = {}
    for r in rows:
        by_parent.setdefault(r["parent"], []).append(r)

    def show(pid, depth):
        for r in sorted(by_parent.get(pid, []), key=lambda x: x["name"]):
            print("   " + "  " * depth + f"- {r['name']}")
            show(r["span_id"], depth + 1)

    for r in sorted(by_parent.get(None, []), key=lambda x: x["name"]):
        print(f"   - {r['name']}")
        show(r["span_id"], 1)

    return rows


def main() -> None:
    print("=" * 74)
    print("EX15  Langfuse trace trees for multi-agent systems")
    print("=" * 74)

    client, handler, exporter = make_offline_tracer()
    app = build_team()

    out = app.invoke({"messages": [user("Research LangGraph")], "results": []}, {**LIMIT, "callbacks": [handler]})

    print("\nRESULT")
    print("-" * 74)
    print(f"  {out['results']}")

    print("\nCAPTURED SPAN TREE")
    print("-" * 74)
    rows = print_tree(exporter)
    print(f"\n  ({len(rows)} spans)")

    print()
    print("=" * 74)
    print("HOW TO READ THIS TREE")
    print("=" * 74)
    print(
        """
  * `LangGraph` is the root - your whole graph.
  * `supervisor` is the node that ran the supervisor agent.
  * `researcher` is the SPECIALIST agent - it appears as its own span
    because you called `create_agent(name="researcher")`.
  * `model` / `tools` are the agent's internal steps.

  THE ONE THING TO DO: name every agent.

      create_agent(model, tools=[...], name="researcher")
                                              ^^^^^^^^^^^^

  Without a name every agent span is called "LangGraph" and the tree is
  useless.  `name=` also shows up in the AIMessage's `name` field, which
  is how you can tell WHICH agent produced which message.

  WHAT TO LOOK FOR IN A TRACE
    - a supervisor span with MANY child agent spans  -> the supervisor is
      looping (check your visit counter / limits)
    - a specialist span with a huge input            -> your handoff brief
      is too long (context isolation is failing)
    - a specialist span with a tiny input            -> your brief is too
      short and the specialist is guessing
    - many `tools` spans under one agent             -> a runaway tool loop
"""
    )

    print()
    print("=" * 74)
    print("SWAP IN THE REAL LANGFUSE")
    print("=" * 74)
    print(
        """
  # pip install langfuse
  from langfuse import Langfuse
  from langfuse.langchain import CallbackHandler

  lf = Langfuse(
      public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
      secret_key=os.environ["LANGFUSE_SECRET_KEY"],
      host="https://cloud.langfuse.com",      # or your self-hosted URL
  )
  handler = CallbackHandler()

  out = app.invoke(inputs, {"callbacks": [handler], "recursion_limit": 30})

  # Self-hosted Langfuse is MIT licensed and runs with Docker:
  #   docker compose up   (see https://github.com/langfuse/langfuse)

  # You can also add your own attributes to any span:
  with lf.start_as_current_observation(name="fanout", input={"topics": topics}) as obs:
      ...
      obs.update(output={"merged": merged})

  # And score the whole run:
  lf.score_current_trace(name="helpfulness", value=0.8)
"""
    )


if __name__ == "__main__":
    main()
