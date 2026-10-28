"""
Verify that your environment matches the versions this course was written for.

Run:  uv run python scripts/verify_versions.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

EXPECTED = {
    "langgraph": "1.2.17",
    "langchain": "1.4.7",
    "langchain-core": "1.7.0",
    "langchain-google-genai": "4.4.2",
    "langfuse": "5.0.4",
}

OPTIONAL = {
    "langgraph-cli": "0.4.38",
    "langgraph-sdk": "0.4.9",
    "langgraph-prebuilt": "1.1.1",
    "langgraph-checkpoint": "4.3.0",
}


def main() -> int:
    import importlib.metadata as md

    print("=" * 72)
    print("  Phase 7 - LangGraph Core : version check")
    print("  (course written against these on 2026-10-26)")
    print("=" * 72)

    ok = True
    for pkg, want in {**EXPECTED, **OPTIONAL}.items():
        try:
            got = md.version(pkg)
        except md.PackageNotFoundError:
            tag = "optional" if pkg in OPTIONAL else "MISSING"
            print(f"  {pkg:<28} {tag}")
            if pkg not in OPTIONAL:
                ok = False
            continue
        match = got == want
        flag = "exact" if match else f"!= {want} (should still work)"
        print(f"  {pkg:<28} {got:<12} {flag}")

    print("-" * 72)
    print("  API surface checks:")

    checks = []

    def check(label: str, fn) -> None:
        try:
            fn()
            checks.append((label, True, ""))
        except Exception as exc:
            checks.append((label, False, f"{type(exc).__name__}: {exc}"))

    def _c1():
        from langgraph.graph.message import add_messages  # noqa: F401

    def _c2():
        from langgraph.types import Overwrite  # noqa: F401

    def _c3():
        from langgraph.runtime import Runtime  # noqa: F401

    def _c4():
        from langgraph.cache.memory import InMemoryCache  # noqa: F401

    def _c5():
        from langgraph.errors import NodeError  # noqa: F401

    def _c6():
        from langchain.agents import create_agent  # noqa: F401

    def _c7():
        from langgraph.managed import RemainingSteps  # noqa: F401

    for label, fn in [
        ("langgraph.graph.message.add_messages", _c1),
        ("langgraph.types.Overwrite", _c2),
        ("langgraph.runtime.Runtime", _c3),
        ("langgraph.cache.memory.InMemoryCache", _c4),
        ("langgraph.errors.NodeError", _c5),
        ("langchain.agents.create_agent", _c6),
        ("langgraph.managed.RemainingSteps", _c7),
    ]:
        check(label, fn)

    for label, good, err in checks:
        print(f"  {'OK  ' if good else 'FAIL'} {label}" + (f"  {err}" if err else ""))

    print("-" * 72)
    from lgc.llm import banner

    print(f"  {banner()}")
    print("=" * 72)

    if not ok:
        print("\nSome required packages are missing. Run:\n")
        print("  uv pip install -e '.[dev,sqlite]'\n")
        return 1

    failed = [c for c in checks if not c[1]]
    if failed:
        print(f"\n{len(failed)} API check(s) failed - you are probably on an older")
        print("langgraph. See CHEATSHEET.md section 1.\n")
        return 1

    print("\nEverything matches. Go and read lessons/L01-graph-thinking.md\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
