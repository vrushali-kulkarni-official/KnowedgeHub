"""Run every example and assert on its output.

This is the course's regression suite.  It exists because a multi-agent
course that only works when a real LLM picks the right tool is a course you
cannot trust.

Usage:
    PYTHONPATH=examples python tests/run_all.py
    PYTHONPATH=examples python tests/run_all.py ex05 ex12      # a subset
"""

from __future__ import annotations

import io
import os
import re
import subprocess
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
PY = sys.executable


def run_example(path: Path) -> tuple[int, str, str]:
    """Run one example as a subprocess.  Returns (returncode, stdout, stderr)."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(EXAMPLES) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [PY, "-u", str(path)],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(ROOT),
        env=env,
    )
    return proc.returncode, proc.stdout, proc.stderr


# name -> (required substrings, forbidden substrings)
ASSERTIONS: dict[str, tuple[list[str], list[str]]] = {
    "ex01_decision_matrix.py": (
        ["single agent", "supervisor team", "model_calls", "CONTEXT ISOLATION"],
        ["Traceback"],
    ),
    "ex02_topologies.py": (
        ["SUPERVISOR", "HIERARCHICAL", "SWARM", "PIPELINE", "LLM-routed edges"],
        ["Traceback"],
    ),
    "ex03_communication_media.py": (
        ["SHARED STATE", "MESSAGES", "ARTIFACTS", "audit_trail", "never entered the prompt"],
        ["Traceback"],
    ),
    "ex04_state_filters.py": (
        ["RULE 1", "RULE 2", "RULE 3", "RULE 4", "BYPASSES", "filtered"],
        ["Traceback"],
    ),
    "ex05_command_and_send.py": (
        [
            "TRAP 1",
            "TRAP 2",
            "TRAP 3",
            "TRAP 4",
            "unknown channel",
            "Expected to have a matching ToolMessage",
            "Field required",
            "9_999",
        ],
        ["Traceback"],
    ),
    "ex06_agents_as_tools.py": (
        ["name=\"researcher\"", "final_answer", "ESCAPE HATCH RULE", "context isolation"],
        ["Traceback"],
    ),
    "ex07_structured_routing.py": (
        ["structured_response", "specialist", "ToolStrategy", "ProviderStrategy", "GraphRecursionError"],
        ["Traceback"],
    ),
    "ex08_handbuilt_supervisor.py": (
        ["supervisor -> researcher", "supervisor -> writer", "supervisor -> reviewer", "finalised"],
        ["Traceback"],
    ),
    "ex09_handoffs.py": (
        ["triage -> billing", "STOP (visit limit", "PING-PONG", "graph=Command.PARENT"],
        ["Traceback"],
    ),
    "ex10_hierarchical.py": (
        ["content_supervisor", "research_supervisor", "escalated", "PROGRESS REPORTING"],
        ["Traceback"],
    ),
    "ex11_shared_state_design.py": (
        ["PROMPT STUFFING", "msgs seen", "SUMMARY", "STATE DESIGN RULES"],
        ["Traceback"],
    ),
    "ex12_parallel_fanout.py": (
        ["parallel", "serial", "speed-up", "results"],
        ["Traceback"],
    ),
    "ex13_aggregation.py": (
        ["votes", "method", "judge", "vote"],
        ["Traceback"],
    ),
    "ex14_budgets.py": (
        [
            "ModelCallLimitMiddleware",
            "ToolCallLimitMiddleware",
            "retry_policy",
            "BUDGET",
            "LOST UPDATE",
            "SILENT STATE DROP",
            "9_999",
        ],
        ["Traceback"],
    ),
    "ex15_langfuse_traces.py": (
        ["CAPTURED SPAN TREE", "researcher", "supervisor", "spans"],
        ["Traceback"],
    ),
    "ex16_debugging_streaming.py": (
        ["stream_mode='updates'", "stream_mode='tasks'", "stream_mode='values'", "DEBUGGING PLAYBOOK"],
        ["Traceback"],
    ),
    "ex17_capstone.py": (
        ["TEAM TRACE", "FINDINGS", "BUDGET", "ARTIFACTS IN THE STORE", "PLAN"],
        ["Traceback"],
    ),
    "ex18_gemini_real.py": (
        ["EX18", "init_chat_model", "gemini-3.8-flash"],
        ["Traceback"],
    ),
}


def main() -> None:
    wanted = set(sys.argv[1:])
    files = sorted(EXAMPLES.glob("ex*.py"))
    if wanted:
        files = [f for f in files if f.stem in wanted or f.name in wanted]

    if not files:
        print("No examples matched.")
        sys.exit(1)

    print("=" * 74)
    print(f"PHASE 10  running {len(files)} examples")
    print("=" * 74)

    failures: list[tuple[str, str]] = []
    total = 0.0

    for path in files:
        name = path.name
        start = time.perf_counter()
        try:
            code, out, err = run_example(path)
        except subprocess.TimeoutExpired:
            failures.append((name, "TIMEOUT (>300s)"))
            print(f"  TIMEOUT  {name}")
            continue
        elapsed = time.perf_counter() - start
        total += elapsed

        if code != 0:
            tail = (err or out).strip().splitlines()[-6:]
            failures.append((name, "\n".join(tail)))
            print(f"  FAIL     {name}  ({elapsed:.1f}s, exit {code})")
            continue

        required, forbidden = ASSERTIONS.get(name, ([], ["Traceback"]))
        missing = [s for s in required if s not in out]
        present = [s for s in forbidden if s in out]

        if missing or present:
            detail = []
            if missing:
                detail.append(f"missing markers: {missing}")
            if present:
                detail.append(f"forbidden markers present: {present}")
            failures.append((name, "\n".join(detail)))
            print(f"  FAIL     {name}  ({elapsed:.1f}s)")
            for d in detail:
                print(f"             {d}")
            continue

        print(f"  ok       {name}  ({elapsed:.1f}s)")

    print()
    print("=" * 74)
    if failures:
        print(f"FAILED: {len(failures)} of {len(files)}")
        for name, detail in failures:
            print(f"\n--- {name} ---")
            print(detail)
        sys.exit(1)

    print(f"ALL {len(files)} EXAMPLES PASSED  ({total:.1f}s total)")
    sys.exit(0)


if __name__ == "__main__":
    main()
