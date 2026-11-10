"""Validate the course's content: links, syntax, and deprecated-API hygiene.

Usage:
    python tests/validate.py
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LESSONS = ROOT / "lessons"
EXAMPLES = ROOT / "examples"

errors: list[str] = []
warnings: list[str] = []


def check_links() -> None:
    """Every relative markdown link must resolve."""
    pattern = re.compile(r"\[[^\]]*\]\(([^)#]+?)(?:#[^)]*)?\)")
    for md in sorted(ROOT.rglob("*.md")):
        if ".venv" in md.parts:
            continue
        text = md.read_text(encoding="utf-8")
        for target in pattern.findall(text):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (md.parent / target).resolve()
            if not resolved.exists():
                errors.append(f"{md.relative_to(ROOT)}: broken link -> {target}")


def check_python_syntax() -> None:
    """Every example must parse."""
    for py in sorted(EXAMPLES.glob("*.py")):
        try:
            ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        except SyntaxError as exc:
            errors.append(f"{py.name}: syntax error: {exc}")


def check_examples_are_runnable() -> None:
    """Every example must have a main guard and a docstring."""
    for py in sorted(EXAMPLES.glob("ex*.py")):
        text = py.read_text(encoding="utf-8")
        if 'if __name__ == "__main__":' not in text:
            errors.append(f"{py.name}: missing __main__ guard")
        if not text.lstrip().startswith('"""'):
            errors.append(f"{py.name}: missing module docstring")


def check_deprecated_usage() -> None:
    """Examples must not *use* deprecated APIs.

    Names inside docstrings and comments are fine - several examples
    deliberately name a deprecated API to explain that it is deprecated.
    So we strip strings and comments before searching.
    """
    banned = {
        "create_react_agent": "deprecated - use langchain.agents.create_agent",
        "langgraph_supervisor": "stale package - use the subagents pattern",
        "langgraph_swarm": "stale package - build handoffs yourself",
        "langgraph.prebuilt import create_react_agent": "deprecated",
    }
    for py in sorted(EXAMPLES.glob("*.py")):
        source = py.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        # Collect every identifier / attribute / import actually used in code.
        used: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used.add(node.id)
            elif isinstance(node, ast.Attribute):
                used.add(node.attr)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    used.add(alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    used.add(alias.name.split(".")[-1])
                    used.add(alias.name)

        for name, why in banned.items():
            leaf = name.split()[-1]
            if leaf in used:
                errors.append(f"{py.name}: uses {leaf} ({why})")


def check_no_hardcoded_secrets() -> None:
    """No example should contain a real-looking API key."""
    key_pattern = re.compile(r"(?:sk|pk)-[A-Za-z0-9_\-]{20,}")
    for py in sorted(EXAMPLES.glob("*.py")):
        for m in key_pattern.finditer(py.read_text(encoding="utf-8")):
            errors.append(f"{py.name}: possible hardcoded key {m.group()[:12]}...")


def check_lesson_files() -> None:
    """The twelve lessons must exist and be substantial."""
    expected = [
        "L01_decision_framework.md",
        "L02_communication_substrate.md",
        "L03_routing_primitives.md",
        "L04_agents_as_tools.md",
        "L05_handbuilt_supervisor.md",
        "L06_handoffs_and_swarms.md",
        "L07_hierarchical_teams.md",
        "L08_shared_state_design.md",
        "L09_parallel_and_aggregation.md",
        "L10_budgets_and_failure_modes.md",
        "L11_observability.md",
        "L12_capstone_and_checklist.md",
    ]
    for name in expected:
        path = LESSONS / name
        if not path.exists():
            errors.append(f"lessons/{name}: missing")
            continue
        size = len(path.read_text(encoding="utf-8"))
        if size < 3000:
            errors.append(f"lessons/{name}: suspiciously short ({size} chars)")
        if size > 60000:
            warnings.append(f"lessons/{name}: very long ({size} chars)")


def check_docs_exist() -> None:
    for name in ("README.md", "ROADMAP.md", "CHEATSHEET.md", "requirements.txt"):
        if not (ROOT / name).exists():
            errors.append(f"{name}: missing")


def main() -> None:
    print("=" * 74)
    print("PHASE 10  content validation")
    print("=" * 74)

    check_links()
    check_python_syntax()
    check_examples_are_runnable()
    check_deprecated_usage()
    check_no_hardcoded_secrets()
    check_lesson_files()
    check_docs_exist()

    for w in warnings:
        print(f"  WARN  {w}")

    if errors:
        print(f"\nFAILED: {len(errors)} problem(s)")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    n_lessons = len(list(LESSONS.glob("L*.md")))
    n_examples = len(list(EXAMPLES.glob("ex*.py")))
    print(f"  {n_lessons} lessons, {n_examples} examples, all links resolve, "
          f"no deprecated APIs in examples.")
    print("OK")
    sys.exit(0)


if __name__ == "__main__":
    main()
