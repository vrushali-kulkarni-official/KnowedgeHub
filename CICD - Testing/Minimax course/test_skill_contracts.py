"""
Skill contract tests — every skill declares input/output schemas.
These tests verify the skill actually accepts and produces those shapes.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft7Validator


SKILL_ROOTS = [Path("skills"), Path("agents"), Path(".skills")]


def discover_skills() -> list[Path]:
    """Find every skill directory containing a manifest."""
    out: list[Path] = []
    for root in SKILL_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("manifest.yaml"):
            out.append(path.parent)
        for path in root.rglob("SKILL.md"):
            out.append(path.parent)
    return out


SKILLS = discover_skills()
SKILL_IDS = [str(p) for p in SKILLS]


def load_manifest(skill_dir: Path) -> dict:
    """Load the manifest from a skill directory."""
    for name in ("manifest.yaml", "manifest.yml", "SKILL.md"):
        p = skill_dir / name
        if p.exists():
            if p.suffix in {".yaml", ".yml"}:
                return yaml.safe_load(p.read_text(encoding="utf-8"))
            # Markdown frontmatter
            text = p.read_text(encoding="utf-8")
            lines = text.splitlines()
            if lines[0].strip() == "---":
                end = next(
                    (i for i, l in enumerate(lines[1:], start=1) if l.strip() == "---"),
                    None,
                )
                if end is not None:
                    return yaml.safe_load("\n".join(lines[1:end]))
    raise FileNotFoundError(f"No manifest in {skill_dir}")


def load_skill_module(entry_point: str, skill_dir: Path):
    """Import the skill's Python module."""
    # entry_point is relative to the skill dir, e.g. "main.py"
    module_name = f"{skill_dir.name}_{entry_point.replace('/', '_').replace('.py', '')}"
    spec_path = (skill_dir / entry_point).resolve()
    spec = importlib.util.spec_from_file_location(module_name, spec_path)  # noqa: F821
    mod = importlib.util.module_from_spec(spec)  # noqa: F821
    spec.loader.exec_module(mod)  # noqa: F821
    return mod


# ---------------------------------------------------------------------------
# Test 1: Manifest schema is itself valid
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("skill_dir", SKILLS, ids=SKILL_IDS)
def test_skill_manifest_is_valid(skill_dir: Path):
    """Each skill manifest must be valid YAML and have required fields."""
    manifest = load_manifest(skill_dir)
    for required in ("name", "version", "description", "inputs", "outputs", "entry_point"):
        assert required in manifest, f"{skill_dir} missing required field: {required}"
    assert manifest["entry_point"].endswith(".py")
    assert (skill_dir / manifest["entry_point"]).exists(), (
        f"Entry point {manifest['entry_point']} not found in {skill_dir}"
    )


# ---------------------------------------------------------------------------
# Test 2: Skill's declared input schema matches examples
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("skill_dir", SKILLS, ids=SKILL_IDS)
def test_skill_examples_match_input_schema(skill_dir: Path):
    """Every example's input must validate against the declared input schema."""
    manifest = load_manifest(skill_dir)
    inputs_schema = manifest.get("inputs", {})
    examples = manifest.get("examples", [])
    if not examples:
        pytest.skip(f"{skill_dir}: no examples declared")
    validator = Draft7Validator(inputs_schema)
    for i, example in enumerate(examples):
        errors = list(validator.iter_errors(example.get("input", {})))
        assert not errors, f"{skill_dir} example {i} input invalid: {errors}"


# ---------------------------------------------------------------------------
# Test 3: Skill produces output matching its declared schema
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("skill_dir", SKILLS, ids=SKILL_IDS)
def test_skill_output_matches_schema(skill_dir: Path):
    """Run each example and verify output matches declared schema."""
    manifest = load_manifest(skill_dir)
    outputs_schema = manifest.get("outputs", {})
    examples = manifest.get("examples", [])
    if not examples:
        pytest.skip(f"{skill_dir}: no examples declared")
    try:
        mod = load_skill_module(manifest["entry_point"], skill_dir)
    except Exception as e:
        pytest.fail(f"{skill_dir}: failed to import: {e}")
    if not hasattr(mod, "run"):
        pytest.skip(f"{skill_dir}: no run() function")

    validator = Draft7Validator(outputs_schema)
    for i, example in enumerate(examples):
        try:
            actual = mod.run(example["input"])
        except Exception as e:
            pytest.fail(f"{skill_dir} example {i} raised: {e}")
        errors = list(validator.iter_errors(actual))
        assert not errors, f"{skill_dir} example {i} output invalid: {errors}"


# ---------------------------------------------------------------------------
# Test 4: Idempotency — same input, same output
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("skill_dir", SKILLS, ids=SKILL_IDS)
def test_skill_idempotent(skill_dir: Path):
    """Skills should be deterministic for the same input."""
    manifest = load_manifest(skill_dir)
    examples = manifest.get("examples", [])
    if not examples or not hasattr(load_skill_module(manifest["entry_point"], skill_dir), "run"):
        pytest.skip(f"{skill_dir}: no runnable examples")
    mod = load_skill_module(manifest["entry_point"], skill_dir)
    for i, example in enumerate(examples):
        out1 = mod.run(example["input"])
        out2 = mod.run(example["input"])
        # JSON compare handles dict ordering and stringification.
        assert json.dumps(out1, sort_keys=True) == json.dumps(out2, sort_keys=True), (
            f"{skill_dir} example {i} not idempotent"
        )
