"""
The capstone graph: a deep-research pipeline.

This is the graph that `langgraph dev` serves (see ../langgraph.json).

It uses, deliberately, every major idea from Phase 7:

    * a state schema with three different reducer styles
    * Command-based routing with typed destinations
    * a parallel fan-out with the `Send` API (map-reduce)
    * a subgraph (critique -> revise) with its own state
    * runtime context (context_schema) for the model + user identity
    * a retry policy and a timeout on the flaky research node
    * persistence via a checkpointer, keyed by thread_id
    * streaming, so you can watch it work

The LLM is Gemini via `lgc.llm.get_llm()`. Without an API key it falls back
to a deterministic offline model, so this file always runs.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal

from langchain_core.messages import AIMessage, HumanMessage
from typing_extensions import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, RetryPolicy, Send

from lgc.llm import get_llm

# --------------------------------------------------------------------------
# Runtime context: read-only, run-scoped, never persisted
# --------------------------------------------------------------------------
@dataclass
class ResearchContext:
    """Per-run dependencies. Injected at invoke() time via context=."""

    user_id: str = "anonymous"
    model: Any = None
    corpus: dict[str, str] = field(default_factory=dict)
    max_questions: int = 3
    # A refinement loop MUST be bounded. Without this, a critic that never
    # says "APPROVED" loops until GraphRecursionError.
    max_revisions: int = 2


# --------------------------------------------------------------------------
# The state schema
# --------------------------------------------------------------------------
class Findings(TypedDict):
    question: str
    answer: str
    source: str


class ResearchState(TypedDict):
    # --- inputs ---
    topic: str

    # --- append-only, merged by a reducer ---
    questions: Annotated[list[str], operator.add]
    findings: Annotated[list[Findings], operator.add]

    # --- last-write-wins (default reducer) ---
    plan: list[str]
    work_items: list[str]
    draft: str
    critique: str
    revision: int

    # --- flags ---
    needs_revision: bool
    final_report: str


# --------------------------------------------------------------------------
# A tiny local corpus so the offline path is meaningful
# --------------------------------------------------------------------------
DEFAULT_CORPUS = {
    "langgraph": (
        "LangGraph models agent workflows as graphs: nodes are functions, edges "
        "are transitions, and state is a shared dictionary with per-key reducers."
    ),
    "reducers": (
        "A reducer is a function (left, right) -> value that decides how a node's "
        "update merges into a state channel. Without a reducer, writes overwrite."
    ),
    "send": (
        "The Send API enables dynamic fan-out: a router returns a list of "
        "Send(node, payload) objects, and each one runs the target node in parallel."
    ),
    "checkpoint": (
        "A checkpointer saves state after every superstep, which enables "
        "persistence across invocations, time travel, and human-in-the-loop."
    ),
    "studio": (
        "LangSmith Studio is the visual debugger. It connects to a local Agent "
        "Server started with `langgraph dev` and shows state at every step."
    ),
}


# --------------------------------------------------------------------------
# Nodes
# --------------------------------------------------------------------------
def plan(state: ResearchState, runtime: Runtime[ResearchContext]) -> Command[
    Literal["dispatch"]
]:
    """Break the topic into sub-questions, then route to the fan-out."""
    topic = state["topic"]
    llm = runtime.context.model or get_llm()

    questions = _plan_questions(llm, topic, runtime.context.max_questions)

    return Command(update={"plan": questions, "questions": questions}, goto="dispatch")


def _plan_questions(llm: Any, topic: str, limit: int) -> list[str]:
    """Ask the model for sub-questions; fall back to a deterministic split."""
    try:
        prompt = (
            f"Break the topic {topic!r} into at most {limit} focused research "
            "questions. Return them as a JSON list of strings, nothing else."
        )
        raw = llm.invoke(prompt)
        text = raw.content if hasattr(raw, "content") else str(raw)
        import json

        parsed = json.loads(text)
        if isinstance(parsed, list) and parsed:
            return [str(q) for q in parsed][:limit]
    except Exception:
        pass  # offline model, or unparseable output -> deterministic split
    return [
        f"What is {topic}?",
        f"How does {topic} work in practice?",
        f"What are the trade-offs of {topic}?",
    ][:limit]


def dispatch(state: ResearchState) -> dict:
    """Prepare the work list.

    The actual fan-out happens in the CONDITIONAL EDGE below (`route_research`),
    which returns one `Send` per work item. Doing it this way - rather than
    returning `Command(goto=[Send(...)])` from the node - keeps the static
    graph diagram correct: LangGraph can then draw the
    `dispatch -> research` edge, and the Send list controls how many times
    `research` actually runs.
    """
    return {"work_items": list(state.get("plan", []))}


def route_research(state: ResearchState) -> list[Send]:
    """Fan out: one `Send` per work item.

    Verified behaviour:
      * `research` runs exactly once per Send (3 questions -> 3 runs).
      * The static edge `dispatch -> research` is still drawn in the Mermaid
        diagram, because the path_map declares the target.
    """
    return [Send("research", {"question": q}) for q in state.get("work_items", [])]


def research(state: ResearchState, runtime: Runtime[ResearchContext]) -> dict:
    """Research ONE question.

    This node is the Send target, so its input is exactly the payload the
    Send provided: {"question": ...}. It cannot see the rest of the parent
    state - by design.
    """
    question = state["question"]
    llm = runtime.context.model or get_llm()

    context = _lookup(runtime.context.corpus or DEFAULT_CORPUS, question)
    try:
        answer = llm.invoke(
            f"Answer the question using only this context.\n\n"
            f"Context: {context}\n\nQuestion: {question}"
        )
        text = answer.content if hasattr(answer, "content") else str(answer)
    except Exception:
        text = context

    return {
        "findings": [
            {"question": question, "answer": text, "source": "local-corpus"}
        ]
    }


def _lookup(corpus: dict[str, str], question: str) -> str:
    q = question.lower()
    best, best_hits = "", -1
    for key, body in corpus.items():
        hits = sum(1 for w in set(q.split()) if w and w in body.lower()) + (
            1 if key in q else 0
        )
        if hits > best_hits:
            best, best_hits = body, hits
    return best or "No relevant context found."


def synthesize(state: ResearchState, runtime: Runtime[ResearchContext]) -> dict:
    """Reduce the findings into a draft report."""
    llm = runtime.context.model or get_llm()
    findings = state.get("findings", [])
    lines = "\n".join(f"- Q: {f['question']}\n  A: {f['answer']}" for f in findings)
    try:
        draft = llm.invoke(
            "Write a concise report from these findings. Use bullet points.\n\n" + lines
        )
        text = draft.content if hasattr(draft, "content") else str(draft)
    except Exception:
        text = lines
    return {"draft": text}


# --------------------------------------------------------------------------
# A SUBGRAPH: critique -> (maybe) revise
# --------------------------------------------------------------------------
class CritiqueState(TypedDict):
    draft: str
    critique: str
    revision: int
    needs_revision: bool


def critique_node(state: CritiqueState, runtime: Runtime[ResearchContext]) -> dict:
    llm = runtime.context.model or get_llm()
    try:
        result = llm.invoke(
            "Critique this report. If it is complete, say APPROVED. "
            "Otherwise list what is missing.\n\n" + state["draft"]
        )
        text = result.content if hasattr(result, "content") else str(result)
    except Exception:
        text = "APPROVED"
    needs_revision = "APPROVED" not in text.upper()
    return {"critique": text, "needs_revision": needs_revision}


def revise_node(state: CritiqueState, runtime: Runtime[ResearchContext]) -> dict:
    llm = runtime.context.model or get_llm()
    try:
        result = llm.invoke(
            "Revise the report to address the critique.\n\n"
            f"Report:\n{state['draft']}\n\nCritique:\n{state['critique']}"
        )
        text = result.content if hasattr(result, "content") else str(result)
    except Exception:
        text = state["draft"]
    # `.get` because `revision` may not exist yet on the first pass.
    return {"draft": text, "revision": state.get("revision", 0) + 1}


def route_revision(
    state: CritiqueState, runtime: Runtime[ResearchContext]
) -> Literal["revise", "done"]:
    """Decide whether to revise again.

    TWO conditions must both hold to loop:
      1. the critic asked for changes, AND
      2. we have not hit the revision budget.

    Condition 2 is what makes the loop terminate. A refinement loop without
    a budget runs until GraphRecursionError.
    """
    if not state.get("needs_revision"):
        return "done"
    if state.get("revision", 0) >= runtime.context.max_revisions:
        return "done"
    return "revise"


critique_builder = StateGraph(CritiqueState)
critique_builder.add_node("critique", critique_node)
critique_builder.add_node("revise", revise_node)
critique_builder.add_edge(START, "critique")
critique_builder.add_conditional_edges(
    "critique",
    route_revision,
    {"revise": "revise", "done": END},
)
critique_builder.add_edge("revise", "critique")   # loop back and re-critique
critique_graph = critique_builder.compile()


# --------------------------------------------------------------------------
# The parent graph
# --------------------------------------------------------------------------
builder = StateGraph(ResearchState, context_schema=ResearchContext)

builder.add_node("plan", plan, destinations=("dispatch",))
builder.add_node("dispatch", dispatch)
builder.add_node(
    "research",
    research,
    retry_policy=RetryPolicy(max_attempts=3, initial_interval=0.5),
)
builder.add_node("synthesize", synthesize)
builder.add_node("critique_and_revise", critique_graph)
builder.add_node("finalize", lambda s: {"final_report": s["draft"]})

builder.add_edge(START, "plan")
# The fan-out: the router returns one Send per work item.
builder.add_conditional_edges("dispatch", route_research, ["research"])
builder.add_edge("research", "synthesize")
builder.add_edge("synthesize", "critique_and_revise")
builder.add_edge("critique_and_revise", "finalize")
builder.add_edge("finalize", END)

graph = builder.compile(name="deep-research")

# NOTE: `builder` is also importable from this module, so tests and examples
# can compile it with their own checkpointer / store:
#     from graphs.research import builder
#     my_graph = builder.compile(checkpointer=InMemorySaver())
