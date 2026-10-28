"""Graphs for `langgraph dev` (the LangGraph local server).

`langgraph.json` points here. The server handles persistence for you, so
these graphs are compiled WITHOUT a checkpointer - the server injects one.

Run locally:
    langgraph dev --config langgraph.json
"""

from __future__ import annotations

import os
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from langgraph.store.postgres import PostgresStore
from langgraph.store.postgres.base import PostgresIndexConfig

DB_URL = os.getenv(
    "LANGGRAPH_PG_URL",
    "postgresql://langgraph:langgraph@127.0.0.1:5432/langgraph",
)


class SupportState(TypedDict, total=False):
    ticket_id: str
    request: str
    amount: int
    decision: str
    log: Annotated[list[str], lambda a, b: a + b]


def _store():
    """A PostgresStore with semantic search (needs pgvector)."""
    try:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        embed = GoogleGenerativeAIEmbeddings(
            model="gemini-embedding-001",
            google_api_key=os.environ["GOOGLE_API_KEY"],
        )
        index = PostgresIndexConfig(dims=3072, embed=embed, fields=["content"])
    except Exception:
        # No API key: run without semantic search.
        index = None
    return PostgresStore.from_conn_string(DB_URL, index=index)


def build_graph():
    """A tiny approval workflow - the L19 pattern, in graph form."""

    def prepare(state: SupportState) -> dict:
        return {"log": [f"prepared:{state.get('ticket_id')}"]}

    def ask_human(state: SupportState) -> dict:
        decision = interrupt(
            {
                "kind": "approval_request",
                "request": state.get("request"),
                "amount": state.get("amount"),
                "options": ["approve", "deny"],
            }
        )
        return {"decision": decision, "log": [f"decision:{decision}"]}

    def finish(state: SupportState) -> dict:
        return {"log": [f"finished:{state.get('decision')}"]}

    g = StateGraph(SupportState)
    g.add_node("prepare", prepare)
    g.add_node("ask_human", ask_human)
    g.add_node("finish", finish)
    g.add_edge(START, "prepare")
    g.add_edge("prepare", "ask_human")
    g.add_edge("ask_human", "finish")
    g.add_edge("finish", END)
    # NOTE: no checkpointer here - `langgraph dev` provides persistence.
    return g.compile()


# The name in langgraph.json must match a module-level variable.
approval_flow = build_graph()
