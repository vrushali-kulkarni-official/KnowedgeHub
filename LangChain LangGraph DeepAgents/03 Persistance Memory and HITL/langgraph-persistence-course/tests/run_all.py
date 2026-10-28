"""Run every example in the course and report pass/fail.

Usage:
    python tests/run_all.py            # run everything
    python tests/run_all.py --verbose  # show each example's output
    python tests/run_all.py ex05 ex07  # run only some

Each example is a standalone script that prints a report. This runner checks
that it (a) exits 0 and (b) produced the key markers we expect, so a silent
regression in a library upgrade is caught immediately.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"

# example -> (markers that MUST appear in the output)
EXPECTED: dict[str, tuple[str, ...]] = {
    "ex01_checkpoint_anatomy.py": (
        "channel_values",
        "channel_versions",
        "versions_seen",
        "Threads are isolated",
    ),
    "ex02_postgres_saver.py": (
        "checkpoint_blobs",
        "checkpoint_migrations",
        "checkpoint_writes",
        "checkpoints",
        "prune",
        "delete_thread",
        "AsyncPostgresSaver",
    ),
    "ex03_agent_with_checkpointer.py": (
        "The Paris question from turn 1 is in the prompt",
        "separate conversation",
    ),
    "ex04_redis_checkpointer.py": (
        "RedisJSON",
        "RedisSaver",
    ),
    "ex05_state_inspection.py": (
        "get_state_history",
        "update_state",
        "fork",
        "as_node",
    ),
    "ex06_replay_production_thread.py": (
        "Production is UNTOUCHED",
        "cloned",
        "replay with fixed code",
    ),
    "ex07_durability_modes.py": (
        "durability=sync",
        "durability=async",
        "durability=exit",
        "exactly-once",
    ),
    "ex08_retry_idempotency.py": (
        "RetryPolicy",
        "attempts:",
        "SKIPPED (duplicate)",
        "rows in payments table",
    ),
    "ex09_interrupt_basics.py": (
        "Command(resume=",
        "__interrupt__",
        "GraphOutput",
        "response_schema",
        "restarted from the top",
    ),
    "ex10_functional_and_breakpoints.py": (
        "entrypoint",
        "interrupt_before",
        "the completed @task did NOT re-run",
    ),
    "ex11_agent_hitl_middleware.py": (
        "HumanInTheLoopMiddleware",
        "approve",
        "reject",
        "edit",
        "respond",
    ),
    "ex12_approval_flow.py": (
        "forbidden",
        "timed_out",
        "sweep_timeouts",
        "approval_audit",
        "already_resolved",
    ),
    "ex13_short_term_memory.py": (
        "trim_messages",
        "ClearToolUsesEdit",
        "[cleared]",
    ),
    "ex14_summarization_middleware.py": (
        "SummarizationMiddleware",
        "summary",
        "profile",
    ),
    "ex15_store_basics.py": (
        "namespace",
        "get_store",
        "list_namespaces",
    ),
    "ex16_postgres_store.py": (
        "pgvector",
        "SEMANTIC search",
        "PostgresIndexConfig",
    ),
    "ex17_langmem.py": (
        "create_manage_memory_tool",
        "create_memory_store_manager",
        "KeyError",
        "namespace",
    ),
    "ex18_tenant_isolation.py": (
        "ISOLATION",
        "namespace",
        "tenant",
    ),
    "ex19_data_lifecycle.py": (
        "sweep_ttl",
        "ttl_minutes",
        "GDPR",
        "delete_multiple",
    ),
}


def main() -> int:
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    only = [a for a in sys.argv[1:] if not a.startswith("-")]

    files = sorted(EXAMPLES.glob("ex*.py"))
    if only:
        files = [f for f in files if any(o in f.name for o in only)]

    if not files:
        print("no examples matched")
        return 1

    env = dict(os.environ)
    env["PYTHONPATH"] = str(EXAMPLES) + os.pathsep + env.get("PYTHONPATH", "")

    results: list[tuple[str, bool, float, str]] = []
    for f in files:
        t0 = time.time()
        try:
            proc = subprocess.run(
                [sys.executable, str(f)],
                capture_output=True,
                text=True,
                timeout=180,
                cwd=str(EXAMPLES),
                env=env,
            )
            out = proc.stdout + proc.stderr
            ok = proc.returncode == 0
            detail = ""
            if not ok:
                detail = out.strip().splitlines()[-1] if out.strip() else "no output"
            else:
                missing = [m for m in EXPECTED.get(f.name, ()) if m not in out]
                if missing:
                    ok = False
                    detail = f"missing marker(s): {missing[:3]}"
            if verbose and ok:
                print(out)
        except subprocess.TimeoutExpired:
            ok, detail = False, "TIMEOUT (>180s)"
        dt = time.time() - t0
        results.append((f.name, ok, dt, detail))
        flag = "PASS" if ok else "FAIL"
        print(f"[{flag}] {f.name:<42} {dt:6.2f}s {detail}")

    passed = sum(1 for _, ok, _, _ in results if ok)
    print()
    print("=" * 70)
    print(f"{passed}/{len(results)} examples passed")
    print("=" * 70)
    if passed != len(results):
        print("\nFailures:")
        for name, ok, dt, detail in results:
            if not ok:
                print(f"  {name}: {detail}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
