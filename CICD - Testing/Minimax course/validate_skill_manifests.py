#!/usr/bin/env python3
"""
Validate every skill manifest against the JSON schema.

Usage:
    uv run python scripts/validate_skill_manifests.py \
        --schema schemas/skill-manifest.schema.json \
        --skills skills/ agents/ .skills/

Exit code 0 if all valid, 1 if any invalid.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    print("ERROR: jsonschema not installed. Run: uv add jsonschema", file=sys.stderr)
    sys.exit(2)

# Frontmatter delimiters in a markdown file.
FRONTMATTER_DELIM = "---"


def extract_frontmatter(md_path: Path) -> dict | None:
    """Extract YAML frontmatter from a markdown file."""
    try:
        import yaml
    except ImportError:
        print("ERROR: pyyaml not installed. Run: uv add pyyaml", file=sys.stderr)
        sys.exit(2)

    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIM:
        return None
    end_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == FRONTMATTER_DELIM:
            end_idx = i
            break
    if end_idx is None:
        return None
    fm_text = "\n".join(lines[1:end_idx])
    return yaml.safe_load(fm_text)


def find_manifests(roots: list[Path]) -> list[Path]:
    """Find every SKILL.md, manifest.yaml, manifest.json under the given roots."""
    manifests: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.name in {"SKILL.md", "skill.md"} and path.suffix == ".md":
                manifests.append(path)
            elif path.name in {"manifest.yaml", "manifest.yml", "manifest.json"}:
                manifests.append(path)
    return manifests


def load_manifest(path: Path) -> dict:
    """Load a manifest from either a YAML file or a markdown frontmatter."""
    if path.suffix in {".yaml", ".yml"}:
        import yaml
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if path.suffix == ".md":
        fm = extract_frontmatter(path)
        if fm is None:
            raise ValueError(f"No YAML frontmatter in {path}")
        return fm
    raise ValueError(f"Unknown manifest format: {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--skills", type=Path, nargs="+", required=True)
    args = parser.parse_args()

    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    validator = jsonschema.Draft7Validator(schema)

    manifests = find_manifests(args.skills)
    if not manifests:
        print("No skill manifests found.")
        return 0

    failed = 0
    for manifest_path in manifests:
        try:
            data = load_manifest(manifest_path)
        except Exception as e:
            print(f"❌ {manifest_path}: load error: {e}")
            failed += 1
            continue

        errors = list(validator.iter_errors(data))
        if errors:
            print(f"❌ {manifest_path}: {len(errors)} schema error(s)")
            for err in errors:
                path = "/".join(str(p) for p in err.absolute_path) or "<root>"
                print(f"   - {path}: {err.message}")
            failed += 1
        else:
            print(f"✅ {manifest_path}")

    if failed:
        print(f"\n{failed} manifest(s) failed validation.")
        return 1
    print(f"\nAll {len(manifests)} manifest(s) valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
