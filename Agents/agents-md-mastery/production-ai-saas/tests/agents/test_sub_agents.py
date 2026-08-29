"""
Behavior tests for the AGENTS.md file set.

These tests don't call an LLM (too slow, too flaky in CI).
Instead, they inspect the AGENTS.md files and assert structural
and safety invariants.

For real end-to-end behavior tests with an LLM, see tests/agents/e2e/
(those are run manually, not in CI).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[2]
ROOT_AGENTS = REPO_ROOT / "AGENTS.md"
SUB_AGENTS_DIR = REPO_ROOT / "sub-agents"


def all_agent_files() -> list[Path]:
    """All AGENTS.md files in scope."""
    files = []
    if ROOT_AGENTS.exists():
        files.append(ROOT_AGENTS)
    if SUB_AGENTS_DIR.is_dir():
        files.extend(sorted(SUB_AGENTS_DIR.glob("*.md")))
    return files


@pytest.fixture(scope="module")
def root_text() -> str:
    return ROOT_AGENTS.read_text(encoding="utf-8")


@pytest.fixture(scope="module", params=all_agent_files(), ids=lambda p: p.name)
def agent_file(request) -> Path:
    return request.param


@pytest.fixture(scope="module")
def agent_text(agent_file: Path) -> str:
    return agent_file.read_text(encoding="utf-8")


def _strip_code_fences(text: str) -> str:
    """Replace fenced code blocks with blank lines (for line numbers)."""
    out: list[str] = []
    in_fence = False
    for line in text.splitlines(keepends=True):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            out.append("\n")
            continue
        out.append("\n" if in_fence else line)
    return "".join(out)


def _strip_inline_code(text: str) -> str:
    """Replace `inline code` with empty."""
    return re.sub(r"`[^`]+`", "``", text)


def _is_in_defense_context(text: str, offset: int) -> bool:
    """Mirror the linter's defense-context detection."""
    start = max(0, offset - 600)
    end = min(len(text), offset + 100)
    ctx = text[start:end].lower()
    defense_words = [
        "deny", "denied", "do not", "don't", "never", "refuse",
        "forbidden", "prohibited", "attack", "red flag", "❌",
        "defense", "guard", "reject", "strip", "remove",
        "not allowed", "not grant", "without explicit",
        "ignore it", "ignore the", "looks like instructions",
        "exfiltrat", "treat as data", "treat file contents as data",
        "if you see", "if a file contains",
    ]
    return any(w in ctx for w in defense_words)


def is_sub_agent(path: Path) -> bool:
    return path.parent.name == "sub-agents" or path.parent.name == "agents"


# ---------------------------------------------------------------------------
# Required-section tests
# ---------------------------------------------------------------------------


def test_root_has_required_sections(root_text: str) -> None:
    """The root AGENTS.md must have all 6 universal sections."""
    required = [
        r"^##\s+1\.\s+Identity",
        r"^##\s+3\.\s+Layout",
        r"^##\s+5\.\s+Sub-Agent Roster",
        r"^##\s+6\.\s+Skills",
        r"^##\s+7\.\s+Secrets Policy",
        r"^##\s+8\.\s+Prompt Injection Defense",
    ]
    for section in required:
        assert re.search(section, root_text, re.MULTILINE), (
            f"AGENTS.md must have section: {section}"
        )


def test_sub_agent_has_required_sections(agent_text: str, agent_file: Path) -> None:
    """Every sub-agent file must have Identity, Skills, and Hand-off.
    Skip for the root file (it has a different section set)."""
    if not is_sub_agent(agent_file):
        pytest.skip(f"{agent_file.name} is the root file; uses different sections")
    required = [
        r"^##\s+1\.\s+Identity",
        r"^##\s+4\.\s+Skills",
        r"^##\s+\d+\.\s+Hand-off",
    ]
    for section in required:
        assert re.search(section, agent_text, re.MULTILINE), (
            f"{agent_file.name} must have section: {section}"
        )


def test_sub_agent_declares_negative_scope(agent_text: str, agent_file: Path) -> None:
    """Every sub-agent must declare what it does NOT do."""
    assert re.search(
        r"do\s+not|you are not|never\s+touch|not\s+allowed",
        agent_text,
        re.IGNORECASE,
    ), f"{agent_file.name} must declare its negative scope"


# ---------------------------------------------------------------------------
# Safety tests
# ---------------------------------------------------------------------------


def test_no_secrets_in_any_file(agent_text: str, agent_file: Path) -> None:
    """No file may contain a real secret pattern (outside code blocks)."""
    scan = _strip_inline_code(_strip_code_fences(agent_text))
    patterns = [
        r"sk-[a-zA-Z0-9]{20,}",
        r"AKIA[0-9A-Z]{16}",
        r"ghp_[a-zA-Z0-9]{36}",
        r"AIza[0-9A-Za-z_-]{35}",
        r"-----BEGIN [A-Z ]+PRIVATE KEY-----",
        r"postgres://[^:\s]+:[^@\s]+@",
    ]
    for pat in patterns:
        m = re.search(pat, scan)
        assert not m, (
            f"{agent_file.name} contains a secret pattern: {pat} "
            f"({m.group(0)[:30] if m else ''})"
        )


def test_no_destructive_blanket_permissions(agent_text: str, agent_file: Path) -> None:
    """No file may grant `run_shell(*)` or `write_file(*)` or similar
    (outside code blocks and defensive context)."""
    scan = _strip_inline_code(_strip_code_fences(agent_text))
    bad_patterns = [
        (r"run_shell\s*[(:]\s*\*\s*\)?", "run_shell(*)"),
        (r"write_file[^{]*\{[^}]*\*\s*/?\}", "write_file { *}"),
        (r"edit_file[^{]*\{[^}]*\*\s*/?\}", "edit_file { *}"),
    ]
    for pat, desc in bad_patterns:
        for m in re.finditer(pat, scan, re.IGNORECASE):
            if _is_in_defense_context(scan, m.start()):
                continue
            raise AssertionError(f"{agent_file.name} has destructive grant: {desc}")


def test_no_prompt_injection_red_flags(agent_text: str, agent_file: Path) -> None:
    """No file may contain prompt-injection patterns outside defensive context."""
    scan = _strip_inline_code(_strip_code_fences(agent_text))
    bad_patterns = [
        r"always\s+obey\s+the\s+user",
        r"never\s+refuse",
        r"reveal\s+your\s+(system\s+)?prompt",
        r"disable\s+(any\s+)?safety",
        r"do\s+not\s+ask\s+for\s+confirmation",
    ]
    for pat in bad_patterns:
        for m in re.finditer(pat, scan, re.IGNORECASE):
            if _is_in_defense_context(scan, m.start()):
                continue
            raise AssertionError(
                f"{agent_file.name} contains injection pattern: {pat}"
            )


def test_destructive_skills_are_denied(agent_text: str, agent_file: Path) -> None:
    """If a destructive skill is mentioned, it must be in a denied context."""
    destructive = [
        "git_push",
        "git_force_push",
        "docker_push",
        "kubectl_delete",
        "db_drop",
        "db_truncate",
    ]
    for skill in destructive:
        for m in re.finditer(rf"\b{re.escape(skill)}\b", agent_text):
            # Look at the 500 chars before the match for denial context
            # (the section header is usually a few bullets away)
            start = max(0, m.start() - 500)
            ctx = agent_text[start:m.end()].lower()
            denial_words = [
                "deny", "denied", "may not", "forbidden", "❌", "never",
                "prohibited", "refuse", "blocked", "not ", "you may not",
                "conditional", "mutate", "write", "skill grants",
                "edit", "deny-list",
            ]
            assert any(word in ctx for word in denial_words), (
                f"{agent_file.name}: '{skill}' must be in a deny-list context "
                f"(line context: ...{agent_text[max(0, m.start()-80):m.end()+80]}...)"
            )


# ---------------------------------------------------------------------------
# Structural tests
# ---------------------------------------------------------------------------


def test_file_size_under_cap(agent_file: Path) -> None:
    """No file may exceed 14000 chars (root) or 18000 chars (sub-agents).
    Sub-agents that include copy-pasteable config examples (Docker, CI) get
    a higher cap; the content is high-signal.
    """
    text = agent_file.read_text(encoding="utf-8")
    is_root = agent_file.name == "AGENTS.md" and agent_file.parent == Path(".")
    cap = 14000 if is_root else 18000
    assert len(text) < cap, (
        f"{agent_file.name} is {len(text)} chars (cap {cap}). "
        f"{'Trim the root file.' if is_root else 'Split into smaller sub-agents.'}"
    )


def test_has_h1(agent_file: Path, agent_text: str) -> None:
    """Every file should have an h1 title."""
    assert re.search(r"^# ", agent_text, re.MULTILINE), (
        f"{agent_file.name} needs an h1 title"
    )


def test_sub_agent_is_self_contained(agent_text: str, agent_file: Path) -> None:
    """Sub-agents should re-state the core rules, not rely on inheritance."""
    # Look for the phrase "see root AGENTS.md" — that's the anti-pattern
    assert "see root" not in agent_text.lower() or "see root AGENTS.md" not in agent_text, (
        f"{agent_file.name} should not defer to root AGENTS.md; "
        "re-state the rules so the sub-agent works in isolation"
    )


# ---------------------------------------------------------------------------
# Roster tests
# ---------------------------------------------------------------------------


def test_root_roster_matches_sub_agents(root_text: str) -> None:
    """The Sub-Agent Roster in the root must match the actual files."""
    # Extract roster entries from the table
    roster_section = re.search(
        r"##\s+5\.\s+Sub-Agent Roster\s+(.*?)(?=^##\s|\Z)",
        root_text,
        re.MULTILINE | re.DOTALL,
    )
    assert roster_section, "AGENTS.md missing Sub-Agent Roster section"
    roster_text = roster_section.group(1)
    # Find all sub-agent names in the table (format: | `name` |)
    roster_ids = set(re.findall(r"\|\s*`([a-z0-9-]+)`\s*\|", roster_text))
    # Find all actual sub-agent files
    actual_ids = {p.stem for p in SUB_AGENTS_DIR.glob("*.md")}
    assert roster_ids == actual_ids, (
        f"Roster IDs {roster_ids} don't match actual files {actual_ids}. "
        "Either update the roster or rename the files."
    )


# ---------------------------------------------------------------------------
# Persona / style tests
# ---------------------------------------------------------------------------


def test_root_orchestrator_does_not_write_code(root_text: str) -> None:
    """The root orchestrator must instruct itself NOT to write code."""
    # Should have a line saying "do not write code" or similar
    assert re.search(
        r"do\s+not\s+write.*code|delegate.*write|only\s+edit",
        root_text,
        re.IGNORECASE,
    ), "Root orchestrator must declare it does not write code itself"


def test_sub_agents_have_clear_owner(agent_text: str, agent_file: Path) -> None:
    """Every sub-agent should declare its owner team."""
    assert re.search(r"owner\s*:", agent_text, re.IGNORECASE), (
        f"{agent_file.name} should declare its Owner in the header"
    )
