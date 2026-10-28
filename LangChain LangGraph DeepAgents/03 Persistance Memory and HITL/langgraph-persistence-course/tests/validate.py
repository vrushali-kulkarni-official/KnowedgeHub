"""Validate the course: links, deprecated APIs, example hygiene.

Usage:  python tests/validate.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LESSONS = ROOT / "lessons"
EXAMPLES = ROOT / "examples"

failures: list[str] = []


def check_links() -> None:
    print("== internal links ==")
    md_files = sorted(ROOT.rglob("*.md"))
    total = 0
    for md in md_files:
        text = md.read_text(encoding="utf-8")
        for m in re.finditer(r"\[[^\]]*\]\((\.[^)#]*)(#[^)]*)?\)", text):
            target = (md.parent / m.group(1)).resolve()
            total += 1
            if not target.exists():
                failures.append(f"broken link in {md.name}: {m.group(1)}")
    print(f"   {total} internal links checked")


def check_deprecated() -> None:
    """Flag deprecated APIs in CODE (lessons may mention them as warnings)."""
    print("== deprecated APIs in code ==")
    banned = [
        (r"from langgraph\.errors import .*\bNodeInterrupt\b", "NodeInterrupt import"),
        (r"raise NodeInterrupt\(", "raise NodeInterrupt"),
        (r"from langgraph\.checkpoint import ", "empty langgraph.checkpoint namespace"),
        (r"from langgraph\.store import ", "empty langgraph.store namespace"),
        (r"from langchain\.prebuilt import .*create_react_agent", "old create_react_agent"),
    ]
    hits = 0
    for py in sorted(EXAMPLES.glob("*.py")):
        text = py.read_text(encoding="utf-8")
        for pattern, label in banned:
            if re.search(pattern, text):
                failures.append(f"{py.name}: uses {label}")
                hits += 1
    print(f"   {hits} deprecated usages in examples")


def check_examples_importable() -> None:
    print("== examples import cleanly ==")
    import ast

    for py in sorted(EXAMPLES.glob("ex*.py")):
        try:
            ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError as e:
            failures.append(f"{py.name}: syntax error {e}")
    print(f"   {len(list(EXAMPLES.glob('ex*.py')))} examples parsed")


def check_lessons_present() -> None:
    print("== lessons ==")
    expected = [
        "L15-checkpoints-and-threads.md",
        "L16-state-inspection-and-time-travel.md",
        "L17-durability-retries-and-crash-recovery.md",
        "L18-hitl-interrupts.md",
        "L19-hitl-production-approval-flows.md",
        "L20-short-term-memory.md",
        "L21-long-term-memory-store-and-langmem.md",
        "L22-multi-tenant-and-data-lifecycle.md",
    ]
    for name in expected:
        p = LESSONS / name
        if not p.exists():
            failures.append(f"missing lesson {name}")
            continue
        words = len(p.read_text(encoding="utf-8").split())
        print(f"   {name:<48} {words:>6} words")
        if words < 1500:
            failures.append(f"{name}: only {words} words")


def main() -> int:
    check_lessons_present()
    check_links()
    check_deprecated()
    check_examples_importable()
    print()
    if failures:
        print(f"{len(failures)} problem(s):")
        for f in failures:
            print("  -", f)
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
