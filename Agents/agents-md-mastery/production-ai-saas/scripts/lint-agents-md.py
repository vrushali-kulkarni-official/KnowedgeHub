#!/usr/bin/env python3
"""
lint-agents-md.py — fail CI if AGENTS.md violates our rules.

Rules enforced:
  1. No secrets (regex match for common patterns).
  2. No destructive blanket permissions.
  3. No prompt-injection red flags.
  4. Required sections exist (Identity, Layout, Skills).
  5. File size under token cap.

Usage:
  python scripts/lint-agents-md.py [PATHS...]

Default paths: AGENTS.md and sub-agents/*.md
Exit code 0 = clean, 1 = violations found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Rule definitions
# ---------------------------------------------------------------------------

# Rule 1: secret patterns
SECRET_PATTERNS: list[str] = [
    r"sk-[a-zA-Z0-9]{20,}",                  # OpenAI / OpenRouter style
    r"sk-proj-[a-zA-Z0-9_-]{20,}",           # OpenAI project keys
    r"AKIA[0-9A-Z]{16}",                     # AWS access key
    r"ghp_[a-zA-Z0-9]{36}",                  # GitHub PAT
    r"github_pat_[a-zA-Z0-9_]{22,}",         # GitHub fine-grained PAT
    r"xox[baprs]-[0-9a-zA-Z-]{10,}",         # Slack tokens
    r"AIza[0-9A-Za-z_-]{35}",                # Google API key
    r"-----BEGIN [A-Z ]+PRIVATE KEY-----",   # Private keys
    r"postgres://[^:\s]+:[^@\s]+@",          # Postgres w/ embedded password
    r"mysql://[^:\s]+:[^@\s]+@",            # MySQL w/ embedded password
    r"mongodb(\+srv)?://[^:\s]+:[^@\s]+@",  # MongoDB w/ embedded password
]

# Rule 2: destructive blanket permissions
DESTRUCTIVE_PATTERNS: list[str] = [
    r"run_shell\s*[(:][^)]*\*\s*\)?",        # run_shell(*)
    r"write_file[^{]*\{[^}]*\*\s*/?\}",     # write_file { * }
    r"edit_file[^{]*\{[^}]*\*\s*/?\}",      # edit_file { * }
    r"grant\s*:\s*\[?\s*['\"]?\*['\"]?\s*\]?",  # grant: [*]
    r"all\s+skills",                        # "all skills" wording
    r"any\s+command",                        # "any command" wording
    r"any\s+file",                          # "any file" wording
]

# Rule 3: prompt-injection red flags
INJECTION_PATTERNS: list[str] = [
    r"always\s+obey\s+the\s+user",
    r"never\s+refuse",
    r"reveal\s+your\s+(system\s+)?prompt",
    r"disable\s+(any\s+)?safety",
    r"disable\s+(any\s+)?security",
    r"read\s+\.env\b",
    r"read\s+~/?\.ssh",
    r"do\s+not\s+ask\s+for\s+confirmation",
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"you\s+are\s+now\s+a",
    r"bypass\s+safety",
    r"jailbreak",
    r"DAN\s+mode",
]

# Rule 4: required sections (matches both "## Identity" and "## 1. Identity")
REQUIRED_SECTIONS: list[str] = [
    r"^##\s+(?:\d+\.\s+)?Identity\b",
    r"^##\s+(?:\d+\.\s+)?Layout\b",
    r"^##\s+(?:\d+\.\s+)?Skills\b",
]

# Rule 5: token cap (rough heuristic: 1 token ≈ 4 chars)
# 8000 chars ≈ 2000 tokens. Above this, split into sub-agents.
# Root files get a higher cap because they orchestrate everything.
# Sub-agents with copy-pasteable config examples (Docker, CI) get 18K.
MAX_CHARS_ROOT = 14000   # ~3500 tokens
MAX_CHARS_SUB = 18000    # ~4500 tokens (for config-heavy sub-agents)

# Optional: warn on sub-agents that are too small (likely missing context)
MIN_CHARS = 200


# ---------------------------------------------------------------------------
# Logic
# ---------------------------------------------------------------------------


def _strip_code_fences(text: str) -> str:
    """Replace code-fenced blocks with blank lines (preserving line numbers).

    This is so that *example* secrets/URLs in fenced code blocks don't trip
    the linter. Real secrets in code blocks are still a problem, but that's
    a job for gitleaks — not this script.
    """
    out: list[str] = []
    in_fence = False
    for line in text.splitlines(keepends=True):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            out.append("\n")  # blank to keep line numbers
            continue
        out.append("\n" if in_fence else line)
    return "".join(out)


def _strip_inline_code(text: str) -> str:
    """Replace `inline code` with empty (still flagging words is fine)."""
    return re.sub(r"`[^`]+`", "``", text)


def _is_in_defense_context(text: str, offset: int) -> bool:
    """Return True if the match is inside a 'defense' / 'deny' / 'attack'
    discussion. We look at the surrounding 600 chars for defense keywords.
    """
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


def check_file(path: Path) -> list[str]:
    """Return list of violation messages. Empty list = clean."""
    text = path.read_text(encoding="utf-8")
    violations: list[str] = []

    # Strip code fences and inline code so examples don't trip the linter.
    # Real secrets in code blocks are caught by gitleaks in CI.
    scan_text = _strip_inline_code(_strip_code_fences(text))

    # Rule 1: secrets
    for pat in SECRET_PATTERNS:
        for m in re.finditer(pat, scan_text):
            violations.append(
                f"[SECRET] matched pattern '{pat}': "
                f"'{m.group(0)[:30]}…' (offset {m.start()})"
            )

    # Rule 2: destructive blanket permissions
    for pat in DESTRUCTIVE_PATTERNS:
        for m in re.finditer(pat, scan_text, re.IGNORECASE):
            if _is_in_defense_context(scan_text, m.start()):
                continue
            violations.append(f"[DESTRUCTIVE] matched pattern '{pat}'")

    # Rule 3: prompt injection
    for pat in INJECTION_PATTERNS:
        for m in re.finditer(pat, scan_text, re.IGNORECASE):
            if _is_in_defense_context(scan_text, m.start()):
                continue
            violations.append(f"[INJECTION] matched pattern '{pat}'")

    # Rule 4: required sections
    for section in REQUIRED_SECTIONS:
        if not re.search(section, text, re.MULTILINE):
            violations.append(f"[MISSING-SECTION] required: {section}")

    # Rule 5: size
    n = len(text)
    # Heuristic: root AGENTS.md lives at the repo root, sub-agents are in
    # sub-agents/*.md (or .github/agents/*.md).
    is_root = path.name == "AGENTS.md" and path.parent == Path(".")
    cap = MAX_CHARS_ROOT if is_root else MAX_CHARS_SUB
    if n > cap:
        violations.append(
            f"[TOO-LONG] {n} chars (cap {cap}). "
            f"{'Trim the root file.' if is_root else 'Split into sub-agents.'}"
        )
    elif n < MIN_CHARS:
        violations.append(
            f"[TOO-SHORT] {n} chars (min {MIN_CHARS}). "
            "Did you forget the body of the file?"
        )

    return violations


def discover_files(args: list[str]) -> list[Path]:
    """Resolve CLI args to a list of Markdown files."""
    if not args:
        # Default: AGENTS.md + sub-agents/*.md
        paths = [Path("AGENTS.md")]
        sub = Path("sub-agents")
        if sub.is_dir():
            paths.extend(sorted(sub.glob("*.md")))
        return paths

    out: list[Path] = []
    for a in args:
        p = Path(a)
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            out.extend(sorted(p.rglob("AGENTS*.md")))
            out.extend(sorted(p.rglob("sub-agents/*.md")))
            out.extend(sorted(p.rglob(".github/agents/*.md")))
        else:
            # treat as glob
            out.extend(sorted(Path(".").glob(a)))
    # dedupe while preserving order
    seen: set[Path] = set()
    return [p for p in out if not (p in seen or seen.add(p))]


def main(argv: list[str]) -> int:
    files = discover_files(argv[1:])
    if not files:
        print("No AGENTS.md files found.", file=sys.stderr)
        return 1

    total = 0
    for f in files:
        violations = check_file(f)
        if violations:
            print(f"\n❌ {f}")
            for v in violations:
                print(f"   - {v}")
            total += len(violations)
        else:
            print(f"✅ {f}")

    print(f"\nTotal violations: {total}")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
