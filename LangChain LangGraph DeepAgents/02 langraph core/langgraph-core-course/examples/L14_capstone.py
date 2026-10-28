"""
L14 - Capstone: the deep-research pipeline.

Runs the graph from graphs/research.py end to end and shows every Phase 7
concept working together:

  1. State with three reducer styles (append / overwrite / flag).
  2. Command-based routing with typed destinations.
  3. A parallel fan-out with the Send API.
  4. A subgraph (critique -> revise) with its own state.
  5. Runtime context (context_schema) carrying the model + user identity.
  6. A retry policy on the flaky research node.
  7. Persistence via a checkpointer, keyed by thread_id.
  8. Streaming, so you can watch the supersteps.

Run:  uv run python examples/L14_capstone.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from langgraph.checkpoint.memory import InMemorySaver

from graphs.research import DEFAULT_CORPUS, ResearchContext, builder, graph
from lgc.llm import get_llm, print_banner
from lgc.printing import section, show_state


def main() -> None:
    print_banner()

    # ---- the context: read-only, run-scoped, never persisted -------------
    ctx = ResearchContext(
        user_id="u-42",
        model=get_llm(),
        corpus=DEFAULT_CORPUS,
        max_questions=3,
    )

    # ---- persistence: a checkpointer keyed by thread_id ------------------
    compiled = builder.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "research-demo-1"}}

    section("1. RUN IT (streaming, so you can watch the supersteps)")
    for chunk in compiled.stream(
        {"topic": "LangGraph reducers"},
        config,
        context=ctx,
        stream_mode="updates",
    ):
        for node_name, update in chunk.items():
            preview = str(update)
            if len(preview) > 160:
                preview = preview[:160] + " ..."
            print(f"  [{node_name}] {preview}")

    section("2. FINAL STATE")
    state = compiled.get_state(config)
    show_state(state.values, "final state")
    print(f"\n  questions asked : {len(state.values.get('questions', []))}")
    print(f"  findings        : {len(state.values.get('findings', []))}")
    print(f"  revisions       : {state.values.get('revision')}")

    section("3. THE GRAPH (this is what Studio renders)")
    print(graph.get_graph().draw_mermaid())

    section("4. PERSISTENCE: same thread, new question -> same memory")
    compiled.invoke(
        {"topic": "LangGraph Send API"},
        config,
        context=ctx,
    )
    state2 = compiled.get_state(config)
    print(f"  questions asked so far: {len(state2.values.get('questions', []))}")
    print("  (the second run appended to the SAME thread's history)")

    section("5. A DIFFERENT THREAD STARTS FRESH")
    other = {"configurable": {"thread_id": "research-demo-2"}}
    compiled.invoke({"topic": "LangGraph checkpointers"}, other, context=ctx)
    other_state = compiled.get_state(other)
    print(f"  questions asked: {len(other_state.values.get('questions', []))}")
    print("  -> separate thread_id = separate memory")

    section("6. THE CHECKPOINT TIMELINE")
    for snap in compiled.get_state_history(config):
        print(f"  step={snap.metadata.get('step'):>3}  next={snap.next}")


if __name__ == "__main__":
    main()
