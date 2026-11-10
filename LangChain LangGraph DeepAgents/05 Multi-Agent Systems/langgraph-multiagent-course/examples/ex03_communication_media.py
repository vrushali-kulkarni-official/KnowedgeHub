"""EX03 — The three communication media: shared state, messages, artifacts.

Run:  PYTHONPATH=examples .venv/bin/python examples/ex03_communication_media.py

A multi-agent system has exactly THREE ways to move information between
agents.  Choosing badly is the single most common cause of a multi-agent
system that "works but feels dumb".

  1. SHARED STATE  - a typed dict every node can read and write.  Reducers
                     decide how concurrent writes merge.
  2. MESSAGES      - the `messages` channel.  A conversation transcript.
                     Every agent that sees `messages` sees the WHOLE thing.
  3. ARTIFACTS     - big payloads parked in the `store`, referenced by ID.
                     The agent gets a pointer, not the payload.

This example builds one small pipeline three times, once per medium, and
shows exactly what each agent can see.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langchain.agents import create_agent, AgentState
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.store.memory import InMemoryStore

from _common import ai, scripted, user, text_of

LIMIT = {"recursion_limit": 20}


# ---------------------------------------------------------------------------
# MEDIUM 1 - SHARED STATE
# ---------------------------------------------------------------------------


def shared_state_version():
    """Nodes coordinate through a typed dict, not by talking."""

    class PipelineState(TypedDict):
        topic: str
        research_notes: str
        draft: str
        audit_trail: Annotated[list[str], lambda a, b: a + b]

    def research(state: PipelineState):
        return {
            "research_notes": "LangGraph models agents as state machines.",
            "audit_trail": ["researcher wrote notes"],
        }

    def write(state: PipelineState):
        # The writer reads the researcher's output out of SHARED STATE.
        return {
            "draft": f"Draft based on: {state['research_notes']}",
            "audit_trail": ["writer read shared state and drafted"],
        }

    def publish(state: PipelineState):
        return {"audit_trail": [f"publisher got {state['draft'][:30]}..."]}

    g = StateGraph(PipelineState)
    g.add_node("researcher", research)
    g.add_node("writer", write)
    g.add_node("publisher", publish)
    g.add_edge(START, "researcher")
    g.add_edge("researcher", "writer")
    g.add_edge("writer", "publisher")
    g.add_edge("publisher", END)

    app = g.compile()
    out = app.invoke({"topic": "LangGraph", "audit_trail": []}, LIMIT)
    return out


# ---------------------------------------------------------------------------
# MEDIUM 2 - MESSAGES
# ---------------------------------------------------------------------------


def messages_version():
    """Agents coordinate by reading the transcript."""

    class PipelineState(AgentState):
        audit_trail: Annotated[list[str], lambda a, b: a + b]

    researcher = create_agent(
        scripted(responses=[ai("LangGraph models agents as state machines.")]),
        tools=[],
        name="researcher",
    )

    def writer(state: PipelineState):
        # The writer sees the researcher's message in `state["messages"]`.
        facts = text_of(state["messages"][-1])
        return {
            "messages": [AIMessage(content=f"Draft based on: {facts}")],
            "audit_trail": ["writer read the transcript"],
        }

    def publisher(state: PipelineState):
        return {"audit_trail": ["publisher read the transcript"]}

    g = StateGraph(PipelineState)
    g.add_node("researcher", researcher)
    g.add_node("writer", writer)
    g.add_node("publisher", publisher)
    g.add_edge(START, "researcher")
    g.add_edge("researcher", "writer")
    g.add_edge("writer", "publisher")
    g.add_edge("publisher", END)

    app = g.compile()
    out = app.invoke({"messages": [user("Tell me about LangGraph")], "audit_trail": []}, LIMIT)
    return out


# ---------------------------------------------------------------------------
# MEDIUM 3 - ARTIFACTS (store + pointer)
# ---------------------------------------------------------------------------

BIG_DOCUMENT = "word " * 400  # ~2000 characters of 'payload'


@tool
def fetch_document(doc_id: str) -> str:
    """Fetch a document. The real payload is large."""
    return f"[small handle for {doc_id}]"


def artifacts_version():
    """Big payloads live in the store; agents only see a handle."""

    class PipelineState(AgentState):
        doc_id: str
        audit_trail: Annotated[list[str], lambda a, b: a + b]

    store = InMemoryStore()
    store.put(("docs",), "langgraph-intro", {"text": BIG_DOCUMENT})

    researcher = create_agent(
        scripted(responses=[ai("I stored the summary under doc_id=langgraph-intro")]),
        tools=[fetch_document],
        name="researcher",
    )

    def writer(state: PipelineState):
        # The writer pulls the FULL payload out of the store, not from the
        # prompt.  The prompt only ever held a handle.
        item = store.get(("docs",), state.get("doc_id", "langgraph-intro"))
        payload = item.value["text"] if item else ""
        return {
            "messages": [
                AIMessage(content=f"Draft from {len(payload)} chars pulled from the store")
            ],
            "audit_trail": [f"writer pulled {len(payload)} chars from store"],
        }

    g = StateGraph(PipelineState)
    g.add_node("researcher", researcher)
    g.add_node("writer", writer)
    g.add_edge(START, "researcher")
    g.add_edge("researcher", "writer")
    g.add_edge("writer", END)

    app = g.compile()
    out = app.invoke(
        {"messages": [user("Summarise the doc")], "doc_id": "langgraph-intro", "audit_trail": []},
        LIMIT,
    )
    return out, store


def main() -> None:
    print("=" * 74)
    print("EX03  Three communication media")
    print("=" * 74)

    print("\nMEDIUM 1 - SHARED STATE")
    print("-" * 74)
    out = shared_state_version()
    print(f"  research_notes : {out['research_notes']}")
    print(f"  draft          : {out['draft']}")
    print(f"  audit_trail    : {out['audit_trail']}")

    print("\nMEDIUM 2 - MESSAGES")
    print("-" * 74)
    out = messages_version()
    print(f"  transcript     : {len(out['messages'])} messages")
    for m in out["messages"]:
        print(f"     {m.type:<10} | {text_of(m)[:64]}")
    print(f"  audit_trail    : {out['audit_trail']}")

    print("\nMEDIUM 3 - ARTIFACTS (store + handle)")
    print("-" * 74)
    out, store = artifacts_version()
    for m in out["messages"]:
        print(f"     {m.type:<10} | {text_of(m)[:64]}")
    print(f"  audit_trail    : {out['audit_trail']}")
    print(f"  store holds    : {len(list(store.search(('docs',))))} document(s)")
    print(f"  payload chars  : {len(BIG_DOCUMENT)}  (never entered the prompt)")

    print()
    print("=" * 74)
    print("RULES OF THUMB")
    print("=" * 74)
    print(
        """
  SHARED STATE  use for structured facts that later steps need as DATA
               (a score, a filename, a verdict).  Reducers make concurrent
               writes safe.  Downside: every node's schema grows forever.

  MESSAGES      use for the conversation itself.  It is append-only and
               fully replayable.  Downside: it is UNBOUNDED - every agent
               that gets `messages` pays for the whole history on every call.

  ARTIFACTS     use for anything big: documents, code, raw tool output.
               Park it in the store, pass a handle.  This is how you stop
               prompt-stuffing (see L07).
"""
    )


if __name__ == "__main__":
    main()
