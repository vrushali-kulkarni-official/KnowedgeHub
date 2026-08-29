#!/usr/bin/env python3
"""
Check that no two skills share the same name. Two skills with the same
name would shadow each other and the agent would have ambiguous behavior.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

# Reuse the loader from validate_skill_manifests.
sys.path.insert(0, str(Path(__file__).parent))
from validate_skill_manifests import find_manifests, load_manifest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skills", type=Path, nargs="+", required=True)
    args = parser.parse_args()

    manifests = find_manifests(args.skills)
    name_to_files: dict[str, list[Path]] = {}

    for path in manifests:
        try:
            data = load_manifest(path)
        except Exception as e:
            print(f"⚠️  {path}: load error: {e}", file=sys.stderr)
            continue
        name = data.get("name")
        if not name:
            print(f"⚠️  {path}: missing 'name' field", file=sys.stderr)
            continue
        name_to_files.setdefault(name, []).append(path)

    duplicates = {n: files for n, files in name_to_files.items() if len(files) > 1}
    if duplicates:
        print("❌ Duplicate skill names found:")
        for name, files in duplicates.items():
            print(f"   '{name}' declared in: {[str(f) for f in files]}")
        return 1

    print(f"✅ All {len(name_to_files)} skill names are unique.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
