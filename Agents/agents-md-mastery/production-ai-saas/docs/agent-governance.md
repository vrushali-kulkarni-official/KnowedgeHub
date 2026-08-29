# Agent Governance — How We Manage `AGENTS.md`

> Owner: platform team
> Last updated: 2026-08-03

This document is the **process layer** for our `AGENTS.md` files. The
`AGENTS.md` files themselves are the **content layer**. Keep this doc
short — it's the constitution, not the code.

---

## 1. Ownership

| File / folder                  | Owner team       | Review required    |
|--------------------------------|------------------|--------------------|
| `AGENTS.md` (root)             | Platform team    | 2 reviewers        |
| `AGENTS.example.md`            | Platform team    | 1 reviewer         |
| `sub-agents/backend-fastapi.md`| Backend team     | 1 reviewer         |
| `sub-agents/data-postgres.md`  | Data team        | 1 reviewer         |
| `sub-agents/vector-qdrant.md`  | AI infra team    | 1 reviewer         |
| `sub-agents/ai-langchain.md`   | AI team          | 1 reviewer         |
| `sub-agents/security-reviewer.md` | Security team | 2 reviewers, must include a security lead |
| `sub-agents/devops-deployer.md`| Platform team    | 2 reviewers (deploy is high-blast-radius) |
| `docs/agent-governance.md`     | Platform team    | 2 reviewers        |
| `scripts/lint-agents-md.py`    | Platform team    | 1 reviewer         |
| `tests/agents/`                | Platform team    | 1 reviewer         |

---

## 2. Change process

Every change to an `AGENTS.md` file **must**:

1. Be on a branch (not `main` directly).
2. Open a PR.
3. Get the required number of reviewers (see table above).
4. Pass CI: `python scripts/lint-agents-md.py` and `pytest tests/agents/`.
5. Be tagged in the commit message with the `agents-md` scope:
   ```text
   agents-md(scope): summary
   ```
   Examples:
   - `agents-md(root): clarify delegation rules`
   - `agents-md(security): add prompt-injection audit checklist`
   - `agents-md(devops): add Qdrant health check to compose`

---

## 3. Release process

`AGENTS.md` files are versioned with the rest of the repo. At each release:

1. Tag with `v<YYYY.MM.PATCH>-agents` (e.g. `v2026.08.0-agents`).
2. The tag is **immutable** once pushed. Old tags are retained for 12
   months minimum.
3. The current version is in the file header (in the frontmatter comment).

When triaging an agent incident, the on-call should:
1. Find the version of `AGENTS.md` the agent was running (git tag).
2. `git diff v<previous>-agents v<current>-agents AGENTS.md sub-agents/`
3. Identify which rule change (or absence) caused the issue.

---

## 4. Incident response

If an agent misbehaves:

1. **Save the bad output** (don't delete it; we need it for the post-mortem).
2. Find the `AGENTS.md` version (git tag).
3. Diff against the previous version.
4. Classify the failure:
   - Was a rule missing? → add it.
   - Was a rule too soft? → tighten it.
   - Was a skill granted that shouldn't be? → revoke it.
   - Was the LLM just wrong (not the file's fault)? → add a worked
     example to the persona showing the right answer.
5. File a post-mortem (template below).
6. Update the linter to catch the failure mode if possible.
7. Roll **forward** with the fix; don't roll back the file.

### Post-mortem template

```markdown
# Post-mortem: <one-line summary>

**Date:** YYYY-MM-DD
**AGENTS.md version:** vYYYY.MM.PATCH-agents
**Agent:** <which sub-agent or "root">
**Severity:** 🔴 Critical / 🟠 High / 🟡 Medium / 🟢 Low

## What happened
<1-2 paragraphs>

## Impact
<data exposure, downtime, cost, etc.>

## Root cause
<why did the agent do the wrong thing? was the rule missing, vague, or did the LLM just hallucinate?>

## Fix
<PR link + summary of the change>

## Prevention
<new linter rule, new test, new sub-agent, etc.>
```

---

## 5. Audit

- **Weekly** (automated, posted to Slack):
  `python scripts/audit-agents-md.py --days 7`
- **Monthly** (in a team meeting): full read-through of the root
  `AGENTS.md` and one randomly-chosen sub-agent.
- **Quarterly**: full review of all sub-agents + the linter rule set.

---

## 6. Onboarding

New engineers:
1. Read this document in week 1.
2. Read the root `AGENTS.md` in week 1.
3. Read the sub-agent relevant to their team in week 2.
4. Run the linter locally and fix any violations (in a branch).
5. Get added to the `OWNERS` of their sub-agent file.

---

## 7. Promotions and demotions

A sub-agent can be:
- **Promoted** (its file is split into two because it grew too big) — old
  file is archived, new files are created.
- **Demoted** (its file is merged with another because they overlap) —
  this is rare and requires a written rationale in the PR.
- **Retired** (the sub-agent is no longer needed) — file is moved to
  `sub-agents/_retired/`.

Retired files are kept for 6 months then deleted.

---

## 8. Exceptions and overrides

In an emergency (e.g. a CVE requires an immediate change), the platform
team on-call can:
1. Push a fix directly to `main` (bypassing the PR review).
2. Tag the commit `agents-md-emergency`.
3. File a post-mortem within 24 hours.

This is the only exception to the PR rule. Use sparingly.

---

## 9. Anti-patterns

We **do not** do any of the following:

- ❌ Put secrets, keys, or passwords in `AGENTS.md`.
- ❌ Grant blanket `*` permissions to any sub-agent.
- ❌ Edit `AGENTS.md` on `main` directly.
- ❌ Skip the linter ("just this once").
- ❌ Copy a third-party `AGENTS.md` without a 7-point audit
  (see `lessons/07-safety-when-reading.md` in the internal training).
- ❌ Use `AGENTS.md` to override a security rule from elsewhere in the
  repo. `AGENTS.md` is a **supplement** to our security posture, not
  a replacement for it.

---

## 10. References

- Training: `agents-md-mastery/lessons/` (this repo)
- Linter: `scripts/lint-agents-md.py`
- Tests: `tests/agents/`
- CI: `.github/workflows/agents-md-lint.yml`
- Root: `AGENTS.md`
- Sub-agents: `sub-agents/*.md`
