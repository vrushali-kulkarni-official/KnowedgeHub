"""EX11 - Shared state design, and how to stop prompt-stuffing.

Run:  PYTHONPATH=examples .venv/bin/python examples/ex11_shared_state_design.py

A multi-agent system's state schema is its most important design artefact.
Get it wrong and you get the two classic diseases:

  DISEASE 1 - PROMPT STUFFING
    Every agent gets the full `messages` transcript.  Every agent pays for
    every previous turn, on every model call, forever.  Cost and latency
    grow quadratically with team size.

  DISEASE 2 - THE GRAVEYARD SCHEMA
    Every agent needs one more field, so the schema grows forever.  Nobody
    knows which fields are still read.  Every node's `input_schema` becomes
    the whole schema, so context isolation quietly dies.

THE THREE PLACES DATA CAN LIVE
------------------------------
  1. `messages`      - the conversation.  Append-only.  Everyone sees it.
  2. shared state   - structured facts.  You control who sees what with
                       `input_schema`.
  3. the store      - big artifacts, addressed by ID.  Nobody sees the
                       payload unless they ask for it by ID.

This example measures all three, and shows the summarisation trick that
keeps `messages` from growing without bound.
"""

from __future__ import annotations

from typing import Annotated

from langchain.agents import AgentState, create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.store.memory import InMemoryStore

from _common import ai, once_then_final, scripted, text_of, user

LIMIT = {"recursion_limit": 20}

BIG_PAYLOAD = "x" * 4000  # 4000 characters of 'context'


# ---------------------------------------------------------------------------
# A BAD schema vs a GOOD schema
# ---------------------------------------------------------------------------


class BadState(AgentState):
    """Every agent's output dumped into one ever-growing bag."""

    research_output: str
    analysis_output: str
    writing_output: str
    review_output: str
    scratchpad: str
    debug_notes: str
    everything: str


class GoodState(AgentState):
    """Facts that later steps need, and nothing else."""

    facts: Annotated[list[str], lambda a, b: a + b]
    artifact_ids: Annotated[list[str], lambda a, b: a + b]
    final_answer: str


# ---------------------------------------------------------------------------
# Prompt stuffing: measure it
# ---------------------------------------------------------------------------


@tool
def measure_context(payload: str) -> str:
    """Report how much context the agent was given."""
    return f"{len(payload)} chars of payload"


def measure_prompt_stuffing():
    """How much context does each agent see as the conversation grows?"""

    rows = []
    for n_prior_turns in (0, 5, 20, 50):
        transcript = [user("start")]
        for i in range(n_prior_turns):
            transcript.append({"role": "assistant", "content": "previous answer " * 25})
            transcript.append({"role": "user", "content": "follow up " * 25})

        model = scripted(router=once_then_final("measure_context", {"payload": "p"}))
        agent = create_agent(model, tools=[measure_context])
        agent.invoke({"messages": transcript}, LIMIT)
        seen = model.last_seen()
        rows.append(
            {
                "turns": n_prior_turns,
                "messages": len(seen),
                "chars": sum(len(text_of(m)) for m in seen),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# The store: big payloads behind a handle
# ---------------------------------------------------------------------------


@tool
def fetch_artifact(artifact_id: str) -> str:
    """Fetch a stored artifact by id."""
    return f"[handle to {artifact_id}]"


def store_version():
    """Big payload in the store; the agent only carries the handle."""

    class StoreState(AgentState):
        artifact_ids: Annotated[list[str], lambda a, b: a + b]
        final_answer: str

    store = InMemoryStore()
    store.put(("artifacts",), "report-v1", {"text": BIG_PAYLOAD})

    def researcher(state: StoreState):
        # The researcher reads the payload (it NEEDS it) and stores a summary.
        item = store.get(("artifacts",), "report-v1")
        payload = item.value["text"] if item else ""
        return {
            "messages": [AIMessage(content=f"Analysed {len(payload)} chars")],
            "artifact_ids": ["report-v1"],
        }

    def writer(state: StoreState):
        # The writer only needs the SUMMARY - it never sees the 4000 chars.
        item = store.get(("artifacts",), "report-v1")
        summary = item.value.get("summary", "n/a") if item else "n/a"
        return {
            "messages": [AIMessage(content="Draft written from the summary")],
            "final_answer": f"Draft based on summary of {state['artifact_ids']}",
        }

    g = StateGraph(StoreState)
    g.add_node("researcher", researcher)
    g.add_node("writer", writer)
    g.add_edge(START, "researcher")
    g.add_edge("researcher", "writer")
    g.add_edge("writer", END)
    app = g.compile()
    return app.invoke({"messages": [user("analyse the report")], "artifact_ids": [], "final_answer": ""}, LIMIT), store


# ---------------------------------------------------------------------------
# Summarisation: keeping `messages` bounded
# ---------------------------------------------------------------------------


def summarisation_demo():
    """`SummarizationMiddleware` rewrites the transcript, `ContextEditingMiddleware`
    only trims the model request.

    Use this when a long-running agent's context must stay bounded.
    """
    from langchain.agents.middleware import SummarizationMiddleware

    class MidState(AgentState):
        facts: Annotated[list[str], lambda a, b: a + b]

    middleware = [
        SummarizationMiddleware(
            # NOTE: a FRACTIONAL trigger needs the model's token limit, which
            # comes from the model's `profile`.  A real Gemini model carries
            # this automatically; a custom model must declare it:
            #   profile={"max_input_tokens": 1_048_576}
            model=scripted(
                responses=[ai("SUMMARY: so far we learned ...")],
                profile={"max_input_tokens": 1_048_576},
            ),
            trigger={"fraction": 0.5},
        )
    ]

    model = scripted(router=once_then_final("remember", {"fact": "f1"}, final="ok"))

    @tool
    def remember(fact: str) -> str:
        """Remember a fact."""
        return "noted"

    agent = create_agent(model, tools=[remember], middleware=middleware)

    transcript = [user("start")]
    for i in range(8):
        transcript.append({"role": "assistant", "content": "chatter " * 30})
        transcript.append({"role": "user", "content": "more " * 30})

    out = agent.invoke({"messages": transcript}, LIMIT)
    return out


def main() -> None:
    print("=" * 74)
    print("EX11  Shared state design")
    print("=" * 74)

    print("\n1. PROMPT STUFFING - measured")
    print("-" * 74)
    print(f"  {'prior turns':>12}{'msgs seen':>12}{'chars seen':>13}")
    for r in measure_prompt_stuffing():
        print(f"  {r['turns']:>12}{r['messages']:>12}{r['chars']:>13}")
    print()
    print("  The agent's context grows linearly with the conversation, and")
    print("  EVERY agent pays it on EVERY call.  In a team of N agents this")
    print("  is the dominant cost.")

    print("\n2. THE STORE - big payload, small handle")
    print("-" * 74)
    out, store = store_version()
    for m in out["messages"]:
        print(f"     {m.type:<10} | {text_of(m)[:66]}")
    print(f"  final_answer  : {out['final_answer']}")
    print(f"  payload chars : {len(BIG_PAYLOAD)} (stored, never in the transcript)")
    print(f"  store items   : {len(list(store.search(('artifacts',))))}")

    print("\n3. SUMMARISATION - bounding the transcript")
    print("-" * 74)
    out2 = summarisation_demo()
    print(f"  final message : {text_of(out2['messages'][-1])[:60]}")
    print("  SummarizationMiddleware REWRITES the state transcript.")
    print("  ContextEditingMiddleware only trims the MODEL REQUEST - the")
    print("  checkpoint still holds the full history.")

    print()
    print("=" * 74)
    print("STATE DESIGN RULES")
    print("=" * 74)
    print(
        """
  1. `messages` holds the CONVERSATION and nothing else.  If a value is a
     fact, not a turn, put it in a typed field.

  2. Every fact gets a TYPE.  `facts: list[str]` is fine.  A field called
     `everything: str` is how teams rot.

  3. Give each node a NARROW `input_schema`.  This is the only mechanism
     that enforces context isolation.

  4. Anything BIG goes to the store; the state carries the ID.

  5. Use a MERGE reducer for dicts and an APPEND reducer for lists - but
     keep APPEND lists OUT of an agent's state schema (the echo trap, EX09).

  6. Summarise at every boundary.  A mid-tier supervisor should receive a
     SUMMARY of its leaves, not their raw transcripts.

  7. Give every shared field a default, so a partial state never explodes
     with KeyError at 3am.
"""
    )


if __name__ == "__main__":
    main()
