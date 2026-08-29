#!/usr/bin/env python3
"""
audit-agents-md.py — report what changed in AGENTS.md files in the last N days.

Usage:
  python scripts/audit-agents-md.py [--days N]

Default: 7 days. Posts a human-readable summary to stdout.
Exit code 0 = always (this is informational, not a gate).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timedelta


def run_git_log(days: int) -> str:
    since = (datetime.now() - timedelta(days=days)).isoformat()
    cmd = [
        "git", "log",
        f"--since={since}",
        "--pretty=format:%h | %an | %ad | %s",
        "--date=short",
        "--",
        "AGENTS.md",
        "AGENTS.local.md",
        "AGENTS.example.md",
        "sub-agents/",
        ".github/agents/",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return f"(git log failed: {result.stderr.strip()})"
    return result.stdout.strip() or "(no changes)"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=7, help="Look back N days")
    args = p.parse_args()

    print(f"📋 AGENTS.md changes in the last {args.days} days:")
    print("-" * 78)
    print(run_git_log(args.days))
    print("-" * 78)
    print("\n💡 Tip: open each commit and review the diff before the next release.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
