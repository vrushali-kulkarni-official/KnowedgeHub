"""
L09 - Async and streaming.

Demonstrates:
  1. Async nodes, and the hard rule that you must use ainvoke/astream.
  2. THE BLOCKING-IN-ASYNC TRAP, measured (0.51s vs 1.50s).
  3. All seven stream modes.
  4. Custom progress events with runtime.stream_writer.
  5. Async streaming.

Run:  uv run python examples/L09_async_and_streaming.py
"""

from __future__ import annotations

import asyncio
import operator
import sys
import time
from pathlib import Path
from typing import Annotated

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from typing_extensions import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from lgc.printing import section


class S(TypedDict):
    out: Annotated[list[str], operator.add]
    note: str


async def good_node(state: S) -> dict:
    await asyncio.sleep(0.5)
    return {"out": ["good"]}


async def bad_node(state: S) -> dict:
    time.sleep(0.5)  # BLOCKS THE EVENT LOOP
    return {"out": ["BAD-blocking"]}


def build(node):
    return (
        StateGraph(S)
        .add_node("a", node)
        .add_node("b", node)
        .add_node("c", node)
        .add_edge(START, "a")
        .add_edge(START, "b")
        .add_edge(START, "c")
        .add_edge("a", END)
        .add_edge("b", END)
        .add_edge("c", END)
        .compile()
    )


def main() -> None:
    section("1. THE HARD RULE: async nodes need the async API")
    g = build(good_node)
    try:
        g.invoke({"out": [], "note": ""})
    except TypeError as exc:
        print(f"TypeError: {exc}")
        print("-> use ainvoke() / astream() when any node is async.")

    section("2. THE BLOCKING-IN-ASYNC TRAP (measured)")
    print("3 nodes, each taking 0.5s, all in the same superstep.\n")

    async def measure():
        t0 = time.time()
        await build(good_node).ainvoke({"out": [], "note": ""})
        good = time.time() - t0

        t0 = time.time()
        await build(bad_node).ainvoke({"out": [], "note": ""})
        bad = time.time() - t0

        print(f"  await asyncio.sleep(0.5)  -> {good:.2f}s   (concurrent)")
        print(f"  time.sleep(0.5)           -> {bad:.2f}s   (SERIALISED)")
        print(f"  ratio: {bad / good:.1f}x slower, with no error message.")

    asyncio.run(measure())
    print("\n  Fix: await asyncio.sleep(...) | httpx.AsyncClient | asyncio.to_thread(...)")

    section("3. THE SEVEN STREAM MODES")
    graph = (
        StateGraph(S)
        .add_node("one", lambda s: {"out": ["1"], "note": "first"})
        .add_node("two", lambda s: {"out": ["2"], "note": "second"})
        .add_edge(START, "one")
        .add_edge("one", "two")
        .add_edge("two", END)
        .compile()
    )
    inp = {"out": [], "note": ""}
    for mode in ("values", "updates", "checkpoints", "tasks", "debug", "messages", "custom"):
        chunks = list(graph.stream(inp, stream_mode=mode))
        first = str(chunks[0])[:90] if chunks else "(none)"
        print(f"  {mode:<12} -> {len(chunks)} chunk(s); first: {first}")

    section("4. CUSTOM PROGRESS EVENTS")
    def progress_node(state: S, runtime: Runtime) -> dict:
        runtime.stream_writer({"progress": "50% done"})
        return {"out": ["worked"]}

    g2 = (
        StateGraph(S)
        .add_node("progress", progress_node)
        .add_edge(START, "progress")
        .add_edge("progress", END)
        .compile()
    )
    print("  custom events:", list(g2.stream(inp, stream_mode="custom")))

    section("5. MULTIPLE MODES AT ONCE + ASYNC STREAMING")
    for mode, chunk in graph.stream(inp, stream_mode=["updates", "values"]):
        print(f"  {mode:<8} {str(chunk)[:80]}")


if __name__ == "__main__":
    main()
