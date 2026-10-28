"""
L12 - Fault tolerance, timeouts and caching.

Demonstrates:
  1. RetryPolicy - retries, backoff, and the real wall-clock cost.
  2. error_handler with a TYPE-ANNOTATED NodeError parameter (the gotcha).
  3. CachePolicy - AND the fact that compile(cache=...) is REQUIRED.
  4. set_node_defaults for graph-wide policies.
  5. Timeouts (async only).

Run:  uv run python examples/L12_fault_tolerance.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from typing_extensions import TypedDict

from langgraph.cache.memory import InMemoryCache
from langgraph.errors import NodeError
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, RetryPolicy, TimeoutPolicy

from lgc.printing import section


class S(TypedDict):
    x: str


def main() -> None:
    section("1. RetryPolicy - the node is retried until it succeeds")
    attempts = {"n": 0}

    def flaky(state: S) -> dict:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ConnectionError("transient")
        return {"x": "ok"}

    g = (
        StateGraph(S)
        .add_node(
            "flaky",
            flaky,
            retry_policy=RetryPolicy(max_attempts=5, initial_interval=0.05),
        )
        .add_edge(START, "flaky")
        .add_edge("flaky", END)
        .compile()
    )
    t0 = time.time()
    print("  result:", g.invoke({"x": ""}), f"attempts={attempts['n']} in {time.time()-t0:.2f}s")

    print("\n  the DEFAULT policy's real cost:")
    print("    RetryPolicy() = max_attempts=3, initial_interval=0.5,")
    print("                     backoff_factor=2.0")
    print("    -> 3 attempts wait ~0.5s + ~1.0s = ~1.5s of real time.")
    print("    Verified below with a failing node.")
    attempts2 = {"n": 0}

    def always_fail(state: S) -> dict:
        attempts2["n"] += 1
        raise ConnectionError("nope")

    g2 = (
        StateGraph(S)
        .add_node("fail", always_fail, retry_policy=RetryPolicy())
        .add_edge(START, "fail")
        .add_edge("fail", END)
        .compile()
    )
    t0 = time.time()
    try:
        g2.invoke({"x": ""})
    except Exception as exc:
        print(f"    attempts={attempts2['n']} in {time.time()-t0:.2f}s  -> {type(exc).__name__}")

    section("2. error_handler - the NodeError is injected by TYPE ANNOTATION")
    print("  ✅ def handler(state: S, error: NodeError) -> Command")
    print("  ❌ def handler(state, error)   -> TypeError: missing 1 argument\n")

    def always_boom(state: S) -> dict:
        raise ValueError("nope")

    def handler(state: S, error: NodeError) -> Command:
        print(f"  handler: node={error.node!r} error={type(error.error).__name__}: {error.error}")
        return Command(update={"x": f"recovered from {error.node}"}, goto="recover")

    g3 = (
        StateGraph(S)
        .add_node(
            "boom",
            always_boom,
            retry_policy=RetryPolicy(max_attempts=2, initial_interval=0.01),
            error_handler=handler,
        )
        .add_node("recover", lambda s: {"x": s["x"] + "!"})
        .add_edge(START, "boom")
        .add_edge("recover", END)
        .compile()
    )
    print("  result:", g3.invoke({"x": ""}))

    print("\n  and WITHOUT the annotation:")
    try:
        g4 = (
            StateGraph(S)
            .add_node("boom", always_boom, error_handler=lambda state, error: None)
            .add_edge(START, "boom")
            .compile()
        )
        g4.invoke({"x": ""})
    except TypeError as exc:
        print(f"  TypeError: {exc}")

    section("3. CachePolicy - AND compile(cache=...) IS REQUIRED")
    calls = {"n": 0}

    def expensive(state: S) -> dict:
        calls["n"] += 1
        return {"x": f"computed-{calls['n']}"}

    def build(cache):
        b = StateGraph(S).add_node("exp", expensive, cache_policy=RetryPolicy and None)
        b = StateGraph(S).add_node("exp", expensive)
        b.add_edge(START, "exp")
        b.add_edge("exp", END)
        return b.compile(cache=cache) if cache is not None else b.compile()

    from langgraph.types import CachePolicy

    def build2(with_cache: bool):
        b = StateGraph(S)
        b.add_node("exp", expensive, cache_policy=CachePolicy(ttl=120))
        b.add_edge(START, "exp")
        b.add_edge("exp", END)
        return b.compile(cache=InMemoryCache()) if with_cache else b.compile()

    print("  WITHOUT compile(cache=...) - the policy is silently inert:")
    calls["n"] = 0
    g5 = build2(False)
    for _ in range(3):
        g5.invoke({"x": "same"})
    print(f"    underlying function called {calls['n']}x (expected 3)")

    print("\n  WITH compile(cache=InMemoryCache()):")
    calls["n"] = 0
    g6 = build2(True)
    for _ in range(3):
        g6.invoke({"x": "same"})
    print(f"    underlying function called {calls['n']}x (expected 1)")
    g6.invoke({"x": "different"})
    print(f"    after a different input: {calls['n']}x (a cache miss)")

    section("4. set_node_defaults - graph-wide policies")
    calls2 = {"n": 0}

    def maybe_fail(state: S) -> dict:
        calls2["n"] += 1
        if calls2["n"] < 2:
            raise ConnectionError("transient")
        return {"x": "ok"}

    g7 = (
        StateGraph(S)
        .set_node_defaults(retry_policy=RetryPolicy(max_attempts=4, initial_interval=0.01))
        .add_node("n1", maybe_fail)
        .add_node("n2", maybe_fail)
        .add_edge(START, "n1")
        .add_edge("n1", "n2")
        .add_edge("n2", END)
        .compile()
    )
    print("  result:", g7.invoke({"x": ""}), f"total attempts={calls2['n']}")

    section("5. TIMEOUTS (async workflows only)")
    print("  TimeoutPolicy(run_timeout=..., idle_timeout=..., refresh_on=...)")
    print("  TimeoutError -> NodeTimeoutError (retryable by default)")

    async def slow(state: S) -> dict:
        await asyncio.sleep(5)
        return {"x": "never"}

    g8 = (
        StateGraph(S)
        .add_node("slow", slow, timeout=TimeoutPolicy(run_timeout=0.2))
        .add_edge(START, "slow")
        .add_edge("slow", END)
        .compile()
    )

    async def run():
        t0 = time.time()
        try:
            await g8.ainvoke({"x": ""})
        except Exception as exc:
            print(f"  after {time.time()-t0:.2f}s -> {type(exc).__name__}: {str(exc).splitlines()[0]}")

    asyncio.run(run())


if __name__ == "__main__":
    main()
