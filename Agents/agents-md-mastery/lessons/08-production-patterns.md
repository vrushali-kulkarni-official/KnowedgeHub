# Lesson 08 — Production Patterns (Versioning, CI/CD, Team Workflows)

> 🟠 **Difficulty: Production**
> 🎯 **Goal:** Make `AGENTS.md` a **first-class artifact** in your engineering org.

---

## 8.1 The Maturity Model

Most teams treat `AGENTS.md` as a one-time write-and-forget. That fails.
Treat it like code. Here's the maturity ladder.

```text
Level 0 — "We have an AGENTS.md"
  → A file at the root. No review. No CI. Drifts.

Level 1 — "We review changes"
  → PRs required for changes. No automated checks.

Level 2 — "We lint it"
  → CI runs gitleaks, secret scans, schema validation.

Level 3 — "We version it"
  → Changes are tagged in commits. Old versions are archived.

Level 4 — "We test it"
  → Unit tests assert that the agent behaves per the file.

Level 5 — "We measure it"
  → Track how often agents refuse tasks, how often humans override.
```

You should aim for **Level 4** in the first month, **Level 5** by month 3.

---

## 8.2 File Layout for Production

```text
your-ai-saas/
├── AGENTS.md                       ← root orchestrator (≤ 2000 tokens)
├── AGENTS.local.md                 ← personal overrides (gitignored)
├── AGENTS.example.md               ← template for new contributors
├── .github/
│   ├── agents/                     ← (alt location, some teams use this)
│   │   ├── backend-fastapi.md
│   │   ├── data-postgres.md
│   │   ├── vector-qdrant.md
│   │   ├── ai-langchain.md
│   │   ├── security-reviewer.md
│   │   └── devops-deployer.md
│   └── workflows/
│       ├── agents-md-lint.yml      ← CI: lint, secret scan
│       ├── agents-md-test.yml      ← CI: behavior tests
│       └── agents-md-audit.yml     ← weekly: review drift
├── scripts/
│   ├── lint-agents-md.py           ← custom linter
│   └── test-agents-md.py           ← behavior tests
├── tests/
│   └── agents/
│       ├── test_backend_agent.py
│       ├── test_security_agent.py
│       └── ...
└── docs/
    └── agent-governance.md         ← "how we manage AGENTS.md"
```

--- 

## 8.3 The Linter — Custom Python Script

Save as `scripts/lint-agents-md.py`:

```python
#!/usr/bin/env python3
"""
lint-agents-md.py — fail CI if AGENTS.md violates our rules.

Rules enforced:
  1. No secrets (regex match for common patterns)
  2. No destructive blanket permissions
  3. No prompt-injection red flags
  4. Required sections exist (Identity, Layout, Skills)
  5. File size under token cap

Run: python scripts/lint-agents-md.py AGENTS.md sub-agents/*.md
Exit code 0 = clean, 1 = violations found.
"""

import re
import sys
from pathlib import Path

# --- Rule 1: secret patterns ---
SECRET_PATTERNS = [
    r"sk-[a-zA-Z0-9]{20,}",                  # OpenAI
    r"AKIA[0-9A-Z]{16}",                     # AWS
    r"ghp_[a-zA-Z0-9]{36}",                  # GitHub PAT
    r"-----BEGIN [A-Z ]+PRIVATE KEY-----",   # Private keys
    r"postgres://[^:]+:[^@]+@",              # Postgres w/ password
]

# --- Rule 2: destructive blanket permissions ---
DESTRUCTIVE_PATTERNS = [
    r"run_shell\s*[(:][^)]*\*",              # run_shell: *
    r"write_file[^{]*\{[^}]*\*\s*/?\}",     # write_file: *
    r"edit_file[^{]*\{[^}]*\*\s*/?\}",      # edit_file: *
    r"grant\s*:\s*\[?\s*['\"]?\*['\"]?",    # grant: *
]

# --- Rule 3: prompt-injection red flags ---
INJECTION_PATTERNS = [
    r"always\s+obey\s+the\s+user",
    r"never\s+refuse",
    r"reveal\s+your\s+(system\s+)?prompt",
    r"disable\s+(any\s+)?safety",
    r"read\s+\.env\b",
    r"read\s+~/?\.ssh",
    r"do\s+not\s+ask\s+for\s+confirmation",
]

# --- Rule 4: required sections ---
REQUIRED_SECTIONS = [
    r"^##\s+Identity",
    r"^##\s+Layout",
    r"^##\s+Skills",
]

# --- Rule 5: token cap (rough heuristic: 1 token ≈ 4 chars) ---
MAX_CHARS = 8000  # ~2000 tokens for root, allow 8000 for safety


def check_file(path: Path) -> list[str]:
    """Return list of violation messages. Empty list = clean."""
    text = path.read_text(encoding="utf-8")
    violations: list[str] = []

    for pat in SECRET_PATTERNS:
        m = re.search(pat, text)
        if m:
            violations.append(f"[SECRET] matched pattern '{pat}': {m.group(0)[:30]}…")

    for pat in DESTRUCTIVE_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            violations.append(f"[DESTRUCTIVE] matched pattern '{pat}'")

    for pat in INJECTION_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            violations.append(f"[INJECTION] matched pattern '{pat}'")

    for section in REQUIRED_SECTIONS:
        if not re.search(section, text, re.MULTILINE):
            violations.append(f"[MISSING-SECTION] required: {section}")

    if len(text) > MAX_CHARS:
        violations.append(
            f"[TOO-LONG] {len(text)} chars (cap {MAX_CHARS}). "
            "Split into sub-agents."
        )

    return violations


def main(roots: list[str]) -> int:
    files: list[Path] = []
    for r in roots:
        p = Path(r)
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            files.extend(p.rglob("AGENTS*.md"))
            files.extend(p.rglob("sub-agents/*.md"))

    if not files:
        print("No AGENTS.md files found.")
        return 1

    total = 0
    for f in sorted(set(files)):
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
    sys.exit(main(sys.argv[1:] or ["AGENTS.md", "sub-agents"]))
```

Save it. Make it executable. Add to `requirements-dev.txt`:

```text
# (no extra deps — stdlib only)
```

---

## 8.4 The CI Workflow — GitHub Actions

Save as `.github/workflows/agents-md-lint.yml`:

```yaml
name: AGENTS.md Lint
# Runs on every PR that touches AGENTS.md or any sub-agent file.

on:
  pull_request:
    paths:
      - "AGENTS.md"
      - "AGENTS.local.md"
      - "AGENTS.example.md"
      - "sub-agents/**"
      - ".github/agents/**"
  push:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run AGENTS.md linter
        run: python scripts/lint-agents-md.py AGENTS.md sub-agents/

      - name: Scan for secrets with gitleaks
        uses: gitleaks/gitleaks-action@v2
        with:
          args: detect --source . --no-banner

      - name: Check file sizes
        run: |
          # Block any single AGENTS file over 8KB
          find . -name "AGENTS*.md" -size +8k \
            -path "./sub-agents/*" -o -name "AGENTS.md" -size +8k \
            | while read f; do
              echo "❌ $f exceeds 8KB. Split into sub-agents."
              exit 1
            done
```

**Result:** if any PR breaks these rules, the PR is blocked.

---

## 8.5 The Behavior Test — Does the Agent Follow the File?

Save as `tests/agents/test_backend_agent.py`:

```python
"""
Behavior tests for the backend-fastapi sub-agent.

These tests use a mock harness to verify the sub-agent's AGENTS.md
file actually constrains the LLM as intended. We don't call a real
LLM in CI (too slow, too flaky) — we instead inspect the file and
the harness config.

For real end-to-end behavior tests, see tests/agents/e2e/ (run manually).
"""

import re
from pathlib import Path

import pytest

AGENT_FILE = Path(__file__).parents[2] / "sub-agents" / "backend-fastapi.md"


@pytest.fixture(scope="module")
def agent_text() -> str:
    return AGENT_FILE.read_text(encoding="utf-8")


def test_has_identity_section(agent_text: str) -> None:
    assert re.search(r"^##\s+Identity", agent_text, re.MULTILINE), \
        "backend-fastapi.md must have an Identity section"


def test_grants_run_shell_with_command_list(agent_text: str) -> None:
    # run_shell must have a command list, not '*'
    m = re.search(r"run_shell[^{]*\{([^}]*)\}", agent_text)
    if m:
        body = m.group(1)
        assert "*" not in body, "run_shell cannot grant '*'"


def test_does_not_grant_destructive_skills(agent_text: str) -> None:
    forbidden = ["git_push", "docker_push", "kubectl_delete", "db_drop"]
    for skill in forbidden:
        # The skill should appear ONLY in a "denied" or "you may not" list
        for match in re.finditer(rf"\b{re.escape(skill)}\b", agent_text):
            # Look at the line and the 3 preceding lines for "denied" / "not"
            start = max(0, match.start() - 200)
            ctx = agent_text[start:match.end()].lower()
            assert any(
                word in ctx for word in ["deny", "denied", "may not", "forbidden", "❌"]
            ), f"'{skill}' must be in a deny-list context"


def test_has_clear_scope(agent_text: str) -> None:
    # The file must say what the agent does NOT do
    assert re.search(r"do\s+not|you are not|never\s+touch", agent_text, re.IGNORECASE), \
        "Sub-agent must declare its negative scope"


def test_file_size_under_cap() -> None:
    # 8000 chars ≈ 2000 tokens
    assert len(AGENT_FILE.read_text(encoding="utf-8")) < 8000, \
        "Sub-agent file too large; consider splitting"
```

Run with `pytest tests/agents/`.

---

## 8.6 Versioning — The Tag Pattern

When `AGENTS.md` changes meaningfully, tag it.

```bash
# In your normal release flow
git tag -a v2026.08.0-agents -m "agents: split data-postgres from backend-fastapi"
git push origin v2026.08.0-agents
```

In your `AGENTS.md`, add a header:

```markdown
<!--
  AGENTS.md
  Version : v2026.08.0-agents  (matches git tag)
  Owner   : platform-team
  Updated : 2026-08-03
  Review  : 2-person rule (see docs/agent-governance.md)
-->
```

Why version? Because when an agent misbehaves, you want to know **which
version of its instructions** it was running.

---

## 8.7 The Governance Doc

Save as `docs/agent-governance.md`:

```markdown
# Agent Governance — How We Manage AGENTS.md

## Ownership
- The **platform team** owns `AGENTS.md` and the sub-agent roster.
- Sub-agent files are owned by the relevant sub-team
  (data team owns `data-postgres.md`, etc.).

## Change Process
1. Open a PR.
2. Add the label `agents-md-change`.
3. Get **two reviewers** (two-person rule).
4. CI must pass: lint, secret scan, behavior tests.
5. Merge to main.

## Release Process
- Tagged per release: `v<YYYY.MM.PATCH>-agents`.
- Old tags retained for 12 months minimum.

## Incident Response
If an agent misbehaves:
1. Find the AGENTS.md version it was running (git tag).
2. Diff against the previous version.
3. Roll back the AGENTS.md tag if needed.
4. File a post-mortem and update the linter to catch the new failure mode.

## Audit
- Weekly: `scripts/audit-agents-md.py` summarizes changes.
- Monthly: review the full file in a team meeting.

## Onboarding
- New engineers read `docs/agent-governance.md` and the current
  `AGENTS.md` in their first week.
- They get a sandbox harness and run the behavior tests.
```

---

## 8.8 The Drift Detector

`AGENTS.md` will drift. Detect it weekly.

```python
#!/usr/bin/env python3
"""
audit-agents-md.py — report what changed in AGENTS.md files in the last N days.
"""
import subprocess
import sys
from datetime import datetime, timedelta

N_DAYS = 7


def main() -> int:
    since = (datetime.now() - timedelta(days=N_DAYS)).isoformat()
    cmd = [
        "git", "log", f"--since={since}",
        "--pretty=format:%h %an %ad %s",
        "--date=short",
        "--", "AGENTS.md", "AGENTS.local.md", "AGENTS.example.md",
        "sub-agents/", ".github/agents/",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return 1
    print(f"AGENTS.md changes in the last {N_DAYS} days:")
    print(result.stdout or "(no changes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Run weekly in CI and post to Slack. Drift becomes visible.

---

## 8.9 The "Frozen" Sub-Agent Pattern

For sub-agents that **must not change often** (e.g. `security-reviewer`),
use a code-freeze pattern:

```markdown
<!--
  SECURITY-REVIEWER SUB-AGENT — FROZEN
  Any change requires:
    1. Security-team approval (2 reviewers)
    2. PR labeled "security-sensitive"
    3. Manual post-deploy verification
-->
```

The harness can be configured to **refuse** to load this file if its hash
doesn't match a known-good value:

```yaml
# In OpenClaw config
sub_agents:
  security-reviewer:
    file: sub-agents/security-reviewer.md
    expected_sha256: 9f2e8c...
    on_hash_mismatch: refuse_to_load
```

This is overkill for most projects but **exactly right** for security-critical
roles.

---

## ✅ What's Next?

Lesson 09 zooms into the **agent harness layer** — Claude Code, Gemini CLI,
OpenClaw, Hermes. You'll learn the small but important differences in how
each one loads, parses, and enforces `AGENTS.md` so your files work across
the ecosystem.

👉 [Open Lesson 09 →](./09-harness-integration.md)
