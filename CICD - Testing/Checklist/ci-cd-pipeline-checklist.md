# CI/CD Tooling Checklist — AI SaaS on GitHub Actions

Stack: Python · FastAPI · Postgres · MongoDB · Qdrant · LangChain/LangGraph/Deep Agents · Redis · Keycloak · Docker Compose · GHCR/Docker Hub · Watchtower CD · Cloudflare Tunnel · Ubuntu homelab

Guiding constraints applied: free/open-source first, popular & well-maintained over hand-rolled, security-first gates, self-hostable where it matches your homelab setup.

---

## 1. Code quality, style & static analysis

| Tool | Purpose |
|---|---|
| **Ruff** | Lint + format (drop Black/Flake8/isort — Ruff's formatter is Black-compatible) |
| **Mypy** *(primary)* | Type checking, best Pydantic/FastAPI plugin support |
| **Pyright/basedpyright** *(optional, editor-side)* | Use in VS Code for fast feedback; don't run both in CI, redundant and slows the pipeline |
| **pre-commit** | Run Ruff/Mypy/Hadolint/Gitleaks locally before push so CI is a safety net, not the first check |
| **actionlint** | Lints your own workflow YAML |
| **Hadolint** | Dockerfile linting |
| **sqlfluff** *(optional)* | If you write raw SQL against Postgres |

**Change:** Dropped Black (redundant with Ruff format) and dropped running Mypy+Pyright both in CI (pick one; Mypy has more mature Pydantic v2 support). Added pre-commit as the missing "shift left" layer.

---

## 2. Unit / property / mutation testing

- **Pytest** + **pytest-cov** (coverage threshold, e.g. `--cov-fail-under=80`)
- **Hypothesis** — property-based tests, especially for Pydantic model validators and any parsing/serialization logic
- **pytest-asyncio** — required for FastAPI async route/service tests (missing from original list, essential for your stack)
- **mutmut** — mutation testing on `main`/nightly only (too slow for PR gating)

---

## 3. API / contract / integration / fuzz testing

- **httpx** + Pytest — async-native API tests against FastAPI (preferred over `requests` since your app is async)
- **Schemathesis** — OpenAPI contract + property-based fuzzing of every FastAPI endpoint
- **Testcontainers (Python)** — spin up real Postgres, MongoDB, Redis, Qdrant, Keycloak per test run instead of mocks
- **testcontainers-keycloak** module specifically — test real OIDC/token flows, not stubs
- Pytest markers (`@pytest.mark.integration`) to separate fast unit runs from container-backed integration runs

---

## 4. Security — SAST / secrets / dependency scanning

| Tool | Purpose |
|---|---|
| **Bandit** | Python-specific SAST |
| **Semgrep** (`p/python`, `p/owasp-top-ten`, `p/fastapi`) | Broader SAST, custom rule support |
| **CodeQL** | Best-in-class taint analysis — **free only for public repos**; if your repo is private you need GitHub Advanced Security (paid). If you want to stay fully free with a private repo, rely on Semgrep + Bandit instead and treat CodeQL as optional |
| **pip-audit** | Dependency CVEs, official PyPA tool |
| **OSV-Scanner** *(primary)*, drop Safety | OSV-Scanner is free/unlimited; Safety's free tier is now limited/commercial-leaning |
| **Gitleaks** | Secrets in git history, fast, CI-friendly |
| **TruffleHog** | Secrets with live credential verification — complements Gitleaks, don't run only one |
| **actions/dependency-review-action** | GitHub-native, blocks PRs that introduce vulnerable/incompatible-license deps — free, add this, it was missing |

---

## 5. Container / IaC / image security

- **Trivy** — filesystem + image + Docker Compose config + secrets scan (your single all-in-one scanner)
- **Grype** + **Syft** *(optional pairing)* — only add if you want a second opinion on CVE matching; Trivy alone is usually sufficient, don't run 3 image scanners
- **Dockle** — CIS Docker Benchmark checks on the final built image
- Drop standalone **Checkov** — Trivy's misconfig scanner already covers Docker Compose; add Checkov only if you later adopt real IaC (Terraform/Ansible)

---

## 6. SBOM, signing & supply-chain provenance

- **Syft** — generate CycloneDX/SPDX SBOM for every image
- **Cosign** — keyless signing (Sigstore/Fulcio) of images pushed to GHCR and Docker Hub
- **GitHub Artifact Attestations** (`actions/attest-build-provenance`) — native SLSA provenance, simpler than standing up `slsa-github-generator` yourself
- **Renovate** *(primary)* over Dependabot — more configurable grouping/scheduling, handles Docker base images, GitHub Actions pins, and Python locks in one tool

---

## 7. AI / LLM / agent-specific evaluation & regression

| Tool | Purpose |
|---|---|
| **Langfuse** *(primary, self-hosted)* | Open-source, self-hostable LLM observability + eval/trace store — fits your homelab/FOSS constraints far better than LangSmith, which is a closed SaaS with a limited free tier |
| **DeepEval** | Offline evals, LLM-as-judge, regression test assertions inside Pytest |
| **Promptfoo** | Prompt regression testing + red-teaming (prompt injection, jailbreak attempts) |
| **Ragas** | RAG-specific eval (retrieval precision/recall, faithfulness, answer relevancy) — important addition since you're running Qdrant-backed retrieval and none of your original tools measured retrieval quality |
| **Garak** *(optional, scheduled not per-PR)* | Deeper adversarial/red-team scanning of LLM behavior |
| Custom Pytest fixtures | Deterministic unit tests for individual LangGraph nodes/edges and Deep Agents skills/tools, independent of live LLM calls (mock the model call) |

**Change:** Replaced LangSmith with Langfuse as the primary tool (FOSS + self-hostable, matches your stated preferences); added Ragas which your original list had no answer for (RAG quality was untested).

---

## 8. Performance & load testing

- **Locust** *(primary)* — Python-native, easiest for your team to extend, good for realistic multi-user + streaming-response scenarios (LLM endpoints often stream)
- **k6** *(optional)* — use instead if you want lighter-weight scripted checks wired directly into CI as a smoke/perf gate

---

## 9. DAST — testing the running app, not just the code

Missing from your original list entirely: everything above is static or unit-level. Add:

- **OWASP ZAP Baseline Scan** (`zaproxy/action-baseline`) — runs against your deployed **staging** environment post-deploy, catches runtime issues static tools can't (headers, auth bypass, live config)

---

## 10. Workflow / pipeline hardening (meta)

- **zizmor** — audits your own workflow files for injection risks, dangerous `pull_request_target` usage, unpinned actions
- **OpenSSF Scorecard** — overall repo security posture score, publish to Security tab
- Pin every third-party action to a full commit SHA
- Minimal `permissions:` block per job, `persist-credentials: false` on checkout
- OIDC/trusted publishing for GHCR/Docker Hub instead of long-lived tokens
- Never restore/save caches on `pull_request_target`-triggered workflows

---

## 11. Supporting / orchestration practices

- Multi-stage Docker builds, non-root user, read-only root filesystem where possible
- Integration tests run against the **same** Docker Compose service versions as production (pin image tags)
- Gates that actually fail the build: coverage threshold, zero critical/high CVEs, zero verified secrets, zero CodeQL/Semgrep "error"-severity findings
- Split jobs: `lint` → `unit` → `integration` (testcontainers) → `security` → `build+scan+sign` → `ai-eval` (Langfuse/DeepEval/Ragas, can run async/nightly for slower suites) → `deploy (staging)` → `dast` → `promote (production, manual or Watchtower poll)`
- Upload all SARIF (CodeQL, Semgrep, Trivy, Bandit-via-sarif) to the GitHub Security tab for a single pane of glass
- Attach SBOM + provenance + cosign signature to every image before Watchtower is allowed to pull it

---

## Summary — what changed and why

**Added (gaps in your original list):**
- `pytest-asyncio` — your FastAPI app is async; without it your async route tests either don't run correctly or silently pass/skip.
- `actions/dependency-review-action` — free, native GitHub PR-level dependency vuln/license gate; zero setup cost, no reason to skip it.
- `Ragas` — you had LangSmith/DeepEval/Promptfoo for agent behavior but nothing measuring Qdrant retrieval quality (precision, recall, faithfulness), which is a core correctness risk for a RAG-based product.
- `OWASP ZAP baseline scan` — your entire list was static/unit-level; nothing tested the actually-deployed staging app for runtime issues (auth bypass, headers, live misconfig).
- `pre-commit` — pushes your lint/format/secret checks to before commit, so CI failures become rare instead of routine.
- `testcontainers-keycloak` (named explicitly) — generic Testcontainers doesn't guarantee real OIDC flow coverage unless you use this module specifically.

**Replaced (better fit for your stated constraints):**
- `LangSmith → Langfuse` as primary — Langfuse is open-source and self-hostable, which matches your homelab + FOSS preference; LangSmith is a closed SaaS with a capped free tier.
- `Safety → OSV-Scanner` as primary — Safety's free tier has become restrictive/commercial; OSV-Scanner (Google/OSSF) is fully free and equally credible.

**Merged/trimmed (you had redundant tools doing the same job):**
- `Black` dropped — Ruff's formatter already covers this.
- Running both `Mypy` and `Pyright` in CI trimmed to Mypy only — pick one for CI (Mypy has the more mature Pydantic v2 plugin); keep Pyright in-editor if you like its speed, but don't double-run type checkers in the pipeline.
- `Checkov` folded into Trivy's misconfig scanner — you don't have separate IaC (Terraform/K8s) yet, so a dedicated tool is unnecessary overhead; revisit if you adopt Terraform/Ansible later.
- `Grype`/`Syft`-as-scanner made optional — Trivy alone covers image CVE scanning; Syft stays as your SBOM *generator* (different job), not a second vulnerability scanner.

**Flagged, not removed:**
- `CodeQL` — kept, but noted it's free only on public repos; on a private repo it requires paid GitHub Advanced Security. If that's a blocker, Semgrep + Bandit are your free SAST coverage instead.

**Kept as-is (correctly chosen the first time):**
Ruff, Bandit, Semgrep, pip-audit, Gitleaks, TruffleHog, Trivy, Dockle, Syft, Cosign, GitHub Attestations, Renovate, Promptfoo, DeepEval, Hypothesis, mutmut, Schemathesis, Testcontainers, zizmor, OpenSSF Scorecard, actionlint, Hadolint, Locust/k6.
