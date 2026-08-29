#!/usr/bin/env python3
"""
Extract Python code blocks from skill markdown files and execute them.

Why: Your skill docs often have ```python``` examples meant to be runnable.
If they break silently, the docs are lying. This script runs them.

Usage:
    uv run python scripts/run_skill_examples.py \\
        --root skills/ agents/ .skills/ \\
        --timeout 30
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

CODE_BLOCK_RE = re.compile(r"```python\n(.*?)```", re.DOTALL)


def extract_code(md_path: Path) -> list[tuple[int, str]]:
    """Return [(line_number, code)] for each python code block in the file."""
    text = md_path.read_text(encoding="utf-8")
    out: list[tuple[int, str]] = []
    # Track line offsets so we can report line numbers.
    for match in CODE_BLOCK_RE.finditer(text):
        # Approximate line number from character offset.
        line_no = text.count("\n", 0, match.start()) + 1
        out.append((line_no, match.group(1)))
    return out


def run_code(code: str, timeout: int) -> tuple[bool, str]:
    """Run a code snippet in a subprocess. Return (success, output)."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        # Wrap the user's code with imports they almost certainly need.
        f.write("import asyncio, json, os, sys\n")
        f.write("from pathlib import Path\n")
        f.write(code)
        tmp = f.name
    try:
        result = subprocess.run(
            [sys.executable, tmp],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return True, result.stdout
        return False, result.stderr or result.stdout
    except subprocess.TimeoutExpired:
        return False, f"Timeout after {timeout}s"
    finally:
        Path(tmp).unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, nargs="+", required=True)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    md_files: list[Path] = []
    for root in args.root:
        if not root.exists():
            continue
        md_files.extend(root.rglob("*.md"))

    report: dict[str, list] = {"files": {}}
    total = 0
    failed = 0

    for md in md_files:
        blocks = extract_code(md)
        if not blocks:
            continue
        file_results = []
        for line_no, code in blocks:
            total += 1
            ok, output = run_code(code, args.timeout)
            entry = {
                "line": line_no,
                "success": ok,
                "output": output[:500],  # truncate for report
            }
            file_results.append(entry)
            if ok:
                print(f"✅ {md}:{line_no}")
            else:
                print(f"❌ {md}:{line_no}: {output[:200]}")
                failed += 1
        report["files"][str(md)] = file_results

    report["summary"] = {"total_blocks": total, "failed": failed, "passed": total - failed}

    if args.output:
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\n{total - failed}/{total} code blocks passed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
