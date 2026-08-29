#!/usr/bin/env python3
"""
Check that every skill's declared `requires.agent_version` is compatible
with the version in VERSION.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from validate_skill_manifests import find_manifests, load_manifest  # noqa: E402

SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def parse_semver(v: str) -> tuple[int, int, int]:
    m = SEMVER_RE.match(v.lstrip("^~="))
    if not m:
        raise ValueError(f"Not a semver: {v}")
    return tuple(int(g) for g in m.groups())  # type: ignore[return-value]


def is_compatible(required: str, actual: str) -> bool:
    """Support ^1.2.3 (caret) and ~1.2.3 (tilde) semver ranges."""
    req = required.strip()
    op = "="
    if req.startswith("^"):
        op = "^"
        req = req[1:]
    elif req.startswith("~"):
        op = "~"
        req = req[1:]
    elif req.startswith("="):
        req = req[1:]

    a = parse_semver(actual)
    r = parse_semver(req)

    if op == "^":
        # ^1.2.3 means >=1.2.3 and <2.0.0
        # ^0.2.3 means >=0.2.3 and <0.3.0 (different rules for 0.x)
        if r[0] == 0:
            return a == r or (a[0] == 0 and a[1] == r[1] and a[2] >= r[2])
        return a[0] == r[0] and (a > r)
    if op == "~":
        return a[0] == r[0] and a[1] == r[1] and a[2] >= r[2]
    return a == r


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skills", type=Path, nargs="+", required=True)
    parser.add_argument("--agent-version", required=True)
    args = parser.parse_args()

    manifests = find_manifests(args.skills)
    failed = 0
    for path in manifests:
        try:
            data = load_manifest(path)
        except Exception as e:
            print(f"⚠️  {path}: {e}", file=sys.stderr)
            continue
        requires = (data.get("requires") or {}).get("agent_version")
        if not requires:
            continue
        if not is_compatible(requires, args.agent_version):
            print(
                f"❌ {path}: skill requires agent {requires}, "
                f"but agent is {args.agent_version}"
            )
            failed += 1
        else:
            print(f"✅ {path}: {requires} compatible with {args.agent_version}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
