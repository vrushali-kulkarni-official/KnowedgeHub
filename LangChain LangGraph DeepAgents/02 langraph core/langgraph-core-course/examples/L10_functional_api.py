"""
L10 - The Functional API.

Demonstrates:
  1. @task returns a future; .result() (sync) / await (async).
  2. @entrypoint with ordinary Python control flow.
  3. `previous` is a PARAMETER, not an attribute.
  4. entrypoint.final(value=..., save=...) - return one thing, save another.
  5. Mixing the two APIs in both directions.
  6. The deprecated kwargs (config_schema, retry).

Run:  uv run python examples/L10_functional_api.py
"""

from __future__ import annotations

import asyncio
import sys
import warnings
from pathlib import Path
from typing_extensions import TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.func import entrypoint, task
from langgraph.graph import END, START, StateGraph

from lgc.printing import section


@task
def add(a: int, b: int) -> int:
    return a + b


@task
def shout(text: str) -> str:
    return text.upper()


@task
async def aadd(a: int, b: int) -> int:
    await asyncio.sleep(0.01)
    return a + b


@entrypoint()
def single_task(x: int) -> int:
    return add(x, 3).result()


@entrypoint()
def sync_workflow(x: int) -> dict:
    total = add(x, 10).result()
    loud = shout(f"total={total}").result()
    if total > 100:
        loud += " (big!)"
    return {"total": total, "message": loud}


@entrypoint()
async def async_workflow(x: int) -> dict:
    total = await aadd(x, 10)
    return {"total": total}


@entrypoint(checkpointer=InMemorySaver())
def counter(x: int, previous: int | None) -> int:
    print(f"  previous = {previous}")
    return (previous or 0) + x


@entrypoint(checkpointer=InMemorySaver())
def finisher(x: int, previous: int | None):
    entrypoint.final(value=x, save=100)
    return x


# --- mixing the two APIs ---------------------------------------------------
class State(TypedDict):
    data: dict
    result: str


@entrypoint()
def heavy_pipeline(data: dict) -> dict:
    cleaned = shout(str(sorted(data.keys()))).result()
    return {"cleaned": cleaned}


def graph_node(state: State) -> dict:
    """A StateGraph node that calls a Functional API workflow."""
    out = heavy_pipeline.invoke(state["data"])
    return {"result": out["cleaned"]}


def main() -> None:
    section("1. @task RETURNS A FUTURE")
    print("  A task only resolves INSIDE a run. Calling it outside raises:")
    try:
        add(2, 3)
    except RuntimeError as exc:
        print(f"    RuntimeError: {exc}")
    print("  Inside an entrypoint it becomes a real value:")
    print("   ", single_task.invoke(5))

    section("2. @entrypoint WITH ORDINARY PYTHON")
    print("  result:", sync_workflow.invoke(5))

    section("3. ASYNC ENTRYPOINT")
    print("  result:", asyncio.run(async_workflow.ainvoke(5)))

    section("4. `previous` IS A PARAMETER, NOT AN ATTRIBUTE")
    cfg = {"configurable": {"thread_id": "fn-1"}}
    print("  run 1:", counter.invoke(3, cfg))
    print("  run 2:", counter.invoke(4, cfg))
    print("  run 3:", counter.invoke(5, cfg))
    print("  -> the thread accumulates across invocations")
    try:
        counter.previous
    except AttributeError as exc:
        print(f"  counter.previous -> AttributeError: {exc}")

    section("5. entrypoint.final(value=..., save=...)")
    cfg2 = {"configurable": {"thread_id": "fn-final"}}
    print("  run 1 returned:", finisher.invoke(1, cfg2), "(and saved 100)")
    print("  run 2 returned:", finisher.invoke(2, cfg2), "(previous was 100)")
    try:
        entrypoint.final(saved_value=1)
    except TypeError as exc:
        print(f"  entrypoint.final(saved_value=1) -> TypeError: {exc}")

    section("6. MIXING THE TWO APIS")
    graph = (
        StateGraph(State)
        .add_node("run_pipeline", graph_node)
        .add_edge(START, "run_pipeline")
        .add_edge("run_pipeline", END)
        .compile()
    )
    print("  graph.invoke:", graph.invoke({"data": {"b": 2, "a": 1}, "result": ""}))

    section("7. DEPRECATED KWARGS")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")

        @entrypoint(config_schema=dict)  # type: ignore[call-arg]
        def _old(x: int) -> int:
            return x

        for w in caught:
            print(f"  {w.category.__name__}: {w.message}")


if __name__ == "__main__":
    main()
