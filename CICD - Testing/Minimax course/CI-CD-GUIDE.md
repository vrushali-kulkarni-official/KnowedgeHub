# The Complete Beginner's Guide to CI/CD for Your AI SaaS

> You said "teach me like a beginner" — this guide assumes you've never set up
> CI/CD before. Read top to bottom, follow the steps in order, and you'll have
> a production-grade pipeline by the end.

---

## Table of Contents

1. [What is CI/CD anyway?](#1-what-is-cicd-anyway)
2. [The mental model: jobs, steps, runners, triggers](#2-the-mental-model)
3. [How GitHub Actions works (the absolute basics)](#3-how-github-actions-works)
4. [The 6 workflow files I built for you](#4-the-6-workflow-files-i-built-for-you)
5. [Step-by-step: how to put it all in your repo](#5-step-by-step-setup)
6. [Deep dive: every tool, what it does, why you need it](#6-deep-dive-every-tool)
7. [Deep dive: testing AI agents and skills specifically](#7-deep-dive-ai-agents-and-skills)
8. [Security: defense in depth explained](#8-security-defense-in-depth)
9. [How CI connects to your homelab (Watchtower flow)](#9-how-ci-connects-to-your-homelab)
10. [Cost & speed: keeping CI fast and cheap](#10-cost-speed)
11. [Maintenance: keeping the pipeline healthy](#11-maintenance)
12. [Troubleshooting common failures](#12-troubleshooting)
13. [Glossary](#13-glossary)

---

## 1. What is CI/CD anyway?

**CI = Continuous Integration.** Every time someone pushes code, you automatically
run a battery of tests and checks on it. Catch bugs before they merge.

**CD = Continuous Deployment / Continuous Delivery.** After tests pass, your
code is automatically deployed. In your case, a new Docker image is built,
signed, and pushed to a registry. Watchtower on your homelab sees the new
image and pulls + restarts.

The pipeline you have looks like this:

```
Developer pushes code
        │
        ▼
┌─────────────────────────────┐
│  GitHub Actions: CI         │  ← runs all the tests
│  - lint, types, unit, etc   │
└─────────────────────────────┘
        │  all pass?
        ▼
   Merge to main
        │
        ▼
┌─────────────────────────────┐
│  GitHub Actions: Release    │  ← builds image
│  - SBOM, sign, push         │
└─────────────────────────────┘
        │
        ▼
   GHCR / DockerHub
        │
        ▼ (Watchtower polls every 5 min)
┌─────────────────────────────┐
│  Homelab: pull + restart    │
└─────────────────────────────┘
```

---

## 2. The mental model

A GitHub Actions **workflow** is a YAML file in `.github/workflows/`. Each
file defines:

- **When** it runs (on push, on PR, on a schedule, manually).
- **What jobs** run (jobs = groups of steps that can run in parallel or sequence).
- **What each job does** (a sequence of steps, each step is either:
  - a `uses:` (somebody else's pre-made action, like `actions/checkout@v4`)
  - a `run:` (a shell command you write)

Workflows run on **runners** — GitHub gives you free virtual machines
(`ubuntu-latest`, `windows-latest`, `macos-latest`). They have CPUs, RAM, Docker,
and any language you install.

You can also self-host runners, but for now, the GitHub-hosted free ones are
plenty for a homelab SaaS.

---

## 3. How GitHub Actions works (the absolute basics)

Every workflow file looks like this skeleton:

```yaml
name: My Workflow           # shown in the Actions tab

on:                         # when to run
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:                 # least-privilege token
  contents: read

jobs:                       # list of jobs
  my-job:                   # a unique ID for this job
    name: My Job            # human-readable name
    runs-on: ubuntu-latest  # what OS to run on
    steps:                  # the actual work
      - uses: actions/checkout@v4            # step 1: get the code
      - run: echo "hello"                    # step 2: shell command
      - name: My step name                   # step 3: named step
        run: pip install mypackage           #   with description
```

Key concepts:

- **Concurrency**: I set `concurrency: cancel-in-progress: true` on most
  workflows. This means: if you push a new commit while the old one is still
  running, the old one is cancelled. Saves CI minutes.
- **Permissions**: Each workflow gets a `GITHUB_TOKEN` automatically. By default
  it has broad access. We restrict it per-job (`permissions: contents: read`
  means "can only read code, can't write anything"). Principle of least privilege.
- **Secrets**: API keys live in `Settings > Secrets and variables > Actions`.
  Reference as `${{ secrets.MY_API_KEY }}`. Never put secrets in the workflow file.
- **Environment variables**: Set with `env:` at workflow, job, or step level.
  Reference as `${{ env.MY_VAR }}` or just `$MY_VAR` in shell.

---

## 4. The 6 workflow files I built for you

Here's what each one does at a glance:

| File | Triggers | Purpose | Approx time |
|---|---|---|---|
| `ci.yml` | Every PR + main | Lint, type-check, unit tests, API contract, mutation | 5-10 min |
| `security.yml` | Every PR + main + nightly | SAST, secrets, deps, container, IaC, license | 10-15 min |
| `ai-evals.yml` | Every PR + main + nightly | LLM quality, RAG, prompt injection, PII, agent behavior | 10-20 min |
| `skill-validation.yml` | PRs touching skills/agents | Skill file lint, schema, contract, executability | 2-5 min |
| `load-test.yml` | Nightly + manual | k6 smoke/load, Locust distributed | 5-10 min |
| `release.yml` | Tag push (v1.0.0) + manual | Build, SBOM, sign, push, GitHub release | 10-15 min |

---

## 5. Step-by-step setup

### Step 1: Create the directory structure

In your repo, run:

```bash
mkdir -p .github/workflows
mkdir -p .github/ISSUE_TEMPLATE
mkdir -p docs
mkdir -p tests/{unit,integration,ai_evals,skills,security,property,load/k6}
mkdir -p tests/agents
mkdir -p scripts
mkdir -p schemas
mkdir -p skills
mkdir -p agents
mkdir -p .skills
```

I've already done this in `/workspace/`. Copy the files over.

### Step 2: Add the workflow files

Place these in `.github/workflows/`:

- `ci.yml` (lint, type, unit tests)
- `security.yml` (SAST, secrets, deps, container, IaC, license)
- `ai-evals.yml` (LLM/agent evals)
- `skill-validation.yml` (skill file validation)
- `load-test.yml` (performance)
- `release.yml` (build + push images)

### Step 3: Add the config files

- `pyproject.toml` — Python tool config (Ruff, Mypy, Pytest, etc.)
- `.pre-commit-config.yaml` — local pre-commit hooks
- `.yamllint` — YAML lint config
- `.github/renovate.json5` — automated dependency updates
- `.github/dependabot.yml` — backup dependency updater
- `.github/CODEOWNERS` — auto-assign reviewers

### Step 4: Add secrets to GitHub

Go to **Settings → Secrets and variables → Actions** and add:

| Secret | What it's for | Required? |
|---|---|---|
| `GITHUB_TOKEN` | Auto-provided by GitHub. Used to push to GHCR, etc. | ✅ Yes |
| `OPENAI_API_KEY` | OpenAI models for tests (GPT-4o, etc.) | ⚠️ Only if you use OpenAI |
| `GOOGLE_API_KEY` | Google Gemini for tests | ⚠️ Only if you use Gemini |
| `ANTHROPIC_API_KEY` | Claude for tests | ⚠️ Only if you use Claude |
| `LANGCHAIN_API_KEY` | LangSmith tracing (optional) | Optional |
| `DOCKERHUB_USERNAME` | Push to DockerHub | ⚠️ If you want DockerHub |
| `DOCKERHUB_TOKEN` | Push to DockerHub | ⚠️ If you want DockerHub |
| `WATCHTOWER_WEBHOOK` | Notify Watchtower (optional) | Optional |
| `CODECOV_TOKEN` | Upload coverage to codecov.io | Optional |

### Step 5: Install pre-commit locally

This catches 80% of issues BEFORE you push:

```bash
# Install pre-commit
uv tool install pre-commit
# or: pip install pre-commit

# Install the git hooks
pre-commit install
pre-commit install --hook-type commit-msg

# Now every 'git commit' runs the checks
git commit -m "feat: add weather skill"
```

### Step 6: Push and watch the magic

```bash
git add .
git commit -m "ci: set up production-grade CI/CD pipeline"
git push origin main
```

Go to your repo → **Actions** tab. You should see all 6 workflows running.

### Step 7: Fix things that break

Expect the FIRST run to fail. Why? Because:
- Code might not pass strict Mypy/Pyright yet (gradually tighten).
- Tests might not exist yet.
- Some tools might need extra config.

That's fine. Look at the failed logs, fix the issues, push again.

### Step 8: Add the badge to your README

Add this to your README.md so you can see CI status at a glance:

```markdown
![CI](https://github.com/YOUR-USERNAME/YOUR-REPO/actions/workflows/ci.yml/badge.svg)
![Security](https://github.com/YOUR-USERNAME/YOUR-REPO/actions/workflows/security.yml/badge.svg)
![AI Evals](https://github.com/YOUR-USERNAME/YOUR-REPO/actions/workflows/ai-evals.yml/badge.svg)
```

### Step 9: Protect your main branch

Go to **Settings → Branches → Add rule**:

- Branch name pattern: `main`
- ✅ Require a pull request before merging
- ✅ Require approvals: 1
- ✅ Require status checks to pass before merging
  - Search and add: `Lint (Ruff)`, `Type check (Mypy + Pyright)`, `Unit tests + coverage`, `SAST (CodeQL)`, `SAST (Bandit)`, `SAST (Semgrep)`, `Dependencies (pip-audit)`, `Secrets (Gitleaks)`, `Container scan (Trivy)`, `IaC (Checkov)`, `License compliance`, `Dockerfile lint (Hadolint)`, `Workflow lint (actionlint)`, `Prompt regression (Promptfoo)`, `LLM metrics (DeepEval)`, `RAG metrics (RAGAS)`, `PII leakage (Presidio)`, `Agent behavior`, `Lint skill files`, `Validate skill manifests`
- ✅ Require linear history
- ✅ Include administrators (even YOU can't push to main without review once it's set up)

### Step 10: Test the release flow

```bash
git tag v0.1.0
git push origin v0.1.0
```

This triggers `release.yml`. Check that:
- The image is built.
- SBOM is generated.
- The image is signed.
- It's pushed to GHCR (and DockerHub if you configured those secrets).

Then check that Watchtower on your homelab picks it up within 5 minutes.

---

## 6. Deep dive: every tool

### Code quality

#### Ruff
- **What:** Fast Python linter + formatter. Replaces flake8, isort, pyupgrade, Black, and bugbear.
- **Why:** Catches syntax errors, unused imports, code style issues, security patterns. Fast.
- **Configured in:** `pyproject.toml` under `[tool.ruff]`.
- **Replaces:** Black (use `ruff format` instead), isort (built in), flake8 (built in).

#### Mypy
- **What:** Static type checker for Python. Reads your type hints and verifies them.
- **Why:** Catches entire categories of bugs at write time, not runtime. "I expected an int but got None."
- **Configured in:** `pyproject.toml` under `[tool.mypy]`.
- **Note:** Slower than Pyright. Run both for best coverage.

#### Pyright
- **What:** Microsoft's type checker. Faster and stricter than Mypy.
- **Why:** Catches what Mypy misses, much faster.
- **Configured in:** `pyproject.toml` under `[tool.pyright]`.
- **Note:** Can disagree with Mypy. Use both; treat conflicts as "needs human review".

### Testing

#### Pytest
- **What:** The Python test runner. The de facto standard.
- **Why:** Powerful, pluggable, fast.
- **Configured in:** `pyproject.toml` under `[tool.pytest.ini_options]`.

#### pytest-cov
- **What:** Coverage plugin for pytest. Tells you what % of code is exercised by tests.
- **Why:** Shows you what you HAVEN'T tested.
- **Configured in:** `pyproject.toml` under `[tool.coverage.*]`.
- **Threshold:** I set `--cov-fail-under=80`. Tighten as you stabilize.

#### Hypothesis
- **What:** Property-based testing. You describe "the relationship that should hold" and Hypothesis generates hundreds of inputs to try to break it.
- **Why:** Finds edge cases humans never think of.
- **Example:** Test that `reverse(reverse(x)) == x` for any list.
- **Run:** Nightly (too slow for every PR).

#### mutmut
- **What:** Mutation testing. Modifies your code in-place to introduce bugs, then checks if your tests catch them.
- **Why:** Catches dead tests. If a test still passes after the code is broken, the test is useless.
- **Run:** Nightly (very slow).

#### httpx
- **What:** Async HTTP client.
- **Why:** Best way to test FastAPI endpoints in Python.
- **Example:** `async with httpx.AsyncClient(app=app) as ac: r = await ac.get("/health")`

#### Schemathesis
- **What:** Reads your OpenAPI schema and generates hundreds of random-but-valid test requests.
- **Why:** Catches edge cases in API contracts (missing null checks, wrong status codes, malformed responses).
- **Run:** On every PR.

### Security (SAST)

#### CodeQL
- **What:** GitHub's own semantic code analysis engine. The gold standard for SAST.
- **Why:** Catches SQL injection, XSS, path traversal, auth bypass. Free, integrated, and powerful.
- **Result location:** Security tab → Code scanning alerts.
- **Run:** On every PR.

#### Bandit
- **What:** Python-specific security linter. Catches common Python vulns (eval, exec, hardcoded passwords, weak crypto).
- **Why:** Lightweight, fast, free.
- **Run:** On every PR.

#### Semgrep
- **What:** Multi-language SAST. Community ruleset has 2000+ patterns. Has FastAPI, LangChain, Python rules.
- **Why:** Catches what Bandit misses. More general, more rules.
- **Run:** On every PR.

#### pip-audit
- **What:** Scans your Python dependencies for known CVEs. Uses PyPA's vuln DB.
- **Why:** Most breaches come from old deps with known vulns. Free.
- **Run:** On every PR.

#### OSV-Scanner
- **What:** Google's vulnerability scanner. Complements pip-audit (different data sources).
- **Why:** Two scanners are better than one. If one misses a vuln, the other might catch it.
- **Run:** On every PR.

#### Gitleaks
- **What:** Scans git history for accidentally committed secrets (API keys, tokens, passwords).
- **Why:** Fast, focused, free.
- **Run:** On every PR.

#### TruffleHog
- **What:** Deeper secret scanner. Verifies found secrets are actually valid by hitting their API.
- **Why:** Reduces false positives dramatically. Catches secrets Gitleaks might miss.
- **Run:** Nightly (slower).

#### OpenSSF Scorecard
- **What:** Audits your repo's security posture (branch protection, dependency update tool, SAST, etc.).
- **Why:** Catches meta-security issues ("you have no branch protection", "you pin actions by SHA, not tag").
- **Run:** Nightly.

#### pip-licenses
- **What:** Lists all your Python dependencies and their licenses.
- **Why:** Some licenses (GPL, AGPL) are toxic in proprietary SaaS. You need to know.
- **Run:** On every PR.

### Container & supply chain

#### Hadolint
- **What:** Dockerfile linter. Catches bad practices (using `latest`, running as root, bad layer caching).
- **Why:** Most Dockerfiles have security or perf issues.
- **Run:** On every PR.

#### Trivy
- **What:** All-in-one scanner. Scans filesystem, images, IaC, secrets. CVE database.
- **Why:** Industry standard for container security. Free.
- **Run:** On every PR.

#### Grype
- **What:** Anchore's CVE scanner. Complements Trivy (different vuln DB).
- **Why:** Two scanners are better than one. Defense in depth.
- **Run:** On every PR.

#### Checkov
- **What:** IaC scanner. Scans Dockerfiles, docker-compose, GitHub Actions, K8s manifests, Terraform.
- **Why:** Catches misconfigurations that lead to security holes.
- **Run:** On every PR.

#### Syft
- **What:** SBOM (Software Bill of Materials) generator. Lists every dep in your image.
- **Why:** Required by many regulations, useful for vuln response, mandatory for SLSA.
- **Run:** On release.

#### Cosign
- **What:** Signs your container images with Sigstore (keyless, OIDC-based).
- **Why:** Proves the image wasn't tampered with after you pushed it. Required for SLSA L3.
- **Run:** On release.

#### GitHub Artifact Attestations
- **What:** GitHub's built-in SLSA provenance generation. Proves where/when/how the image was built.
- **Why:** Required for SLSA L3. Free for public repos, included for private.
- **Run:** On release (built into docker/build-push-action).

### AI / LLM

#### DeepEval
- **What:** LLM eval framework. Metrics: Hallucination, Answer Relevancy, Faithfulness, Bias, Toxicity, G-Eval (custom criteria).
- **Why:** OSS, free, comprehensive. The closest thing to a "pytest for LLMs".
- **Run:** On every PR.

#### RAGAS
- **What:** RAG-specific metrics: Context Precision, Context Recall, Faithfulness, Answer Relevancy, Answer Similarity.
- **Why:** **CRITICAL for your stack** (Qdrant + LangChain = RAG). No other widely-used RAG eval lib.
- **Run:** On every PR.

#### Promptfoo
- **What:** Prompt regression testing + LLM red team.
- **Why:** Catches prompt regressions (small change → big output change) and runs hundreds of attack prompts.
- **Run:** On every PR.

#### Garak
- **What:** LLM vulnerability scanner from NVIDIA. Probes for prompt injection, jailbreaks, toxicity, PII leakage.
- **Why:** "Nmap for LLMs". Comprehensive attack coverage.
- **Run:** Nightly (slow).

#### Rebuff
- **What:** Prompt injection detection library. Hardened prompt templates. Canary tokens.
- **Why:** Adds a defense layer against prompt injection. Test that it works.
- **Run:** On every PR.

#### Presidio
- **What:** Microsoft's PII detection & redaction. Detects emails, SSNs, credit cards, names, etc.
- **Why:** **Mandatory** for any LLM that touches user data. Catches PII leakage in outputs.
- **Run:** On every PR.

### Performance

#### k6
- **What:** Scripted performance testing. JS-based. Great for "does the API hold up under X RPS".
- **Why:** Industry standard. Has Grafana integration.
- **Run:** Nightly.

#### Locust
- **What:** Realistic user load testing. Python-based. Define User classes and their behavior.
- **Why:** Simulates real users doing real flows. Locust's Python API fits naturally in a Python project.
- **Run:** Nightly.

### Maintenance

#### Renovate
- **What:** Automated dependency update tool. Creates PRs when new versions of your deps are released.
- **Why:** Better than Dependabot (more configurable, supports monorepos, better batching). Free for OSS.
- **Configured in:** `.github/renovate.json5`.
- **Note:** You need to install the Renovate GitHub App: https://github.com/marketplace/renovate

### Workflow quality

#### actionlint
- **What:** Linter for GitHub Actions workflow files.
- **Why:** Catches typos, missing fields, invalid action versions. Free.
- **Run:** On every PR.

#### shellcheck
- **What:** Linter for shell scripts. Catches common bash bugs.
- **Why:** Even small `run:` blocks in workflows can have shell bugs.
- **Run:** On every PR.

---

## 7. Deep dive: AI agents and skills

This is the section you specifically asked about. AI agents and skills are
genuinely harder to test than normal code because the "correct" output is
not deterministic.

### A. Why AI tests are different

Normal test:
```python
assert add(2, 2) == 4  # always true
```

AI test:
```python
response = call_llm("What is 2+2?")
# Could be "4", "four", "The answer is 4", "2+2=4", ...
# No single "correct" string
```

So we test **properties** of the output instead:
- Is it relevant to the question? (Answer Relevancy)
- Is it factually grounded? (Faithfulness, Hallucination)
- Is it free of PII? (Presidio)
- Is it free of toxic content? (Toxicity)
- Does it call the right tool? (Tool Selection Accuracy)
- Did it terminate? (Loop Prevention)
- Did it stay under budget? (Token Cost, Latency)

### B. Skill file testing (your specific question)

You said "agents, sub agents and skills." Skills are self-contained modules
the agent can invoke. In your stack, a skill is typically:
- A directory under `skills/`, `agents/`, or `.skills/`
- A `SKILL.md` file with YAML frontmatter (the manifest) + Markdown docs
- A Python `main.py` with a `run(inputs)` function
- Examples of inputs/outputs in the manifest

What we test:

1. **YAML syntax** (yamllint) — bad indentation breaks everything.
2. **Markdown style** (markdownlint) — consistent formatting.
3. **Manifest schema** (JSON Schema) — every skill declares its name, version,
   inputs, outputs, entry_point. We validate the manifest against a JSON schema.
4. **Unique names** — no two skills can have the same name.
5. **Version compatibility** — if a skill requires agent v1.2.0, you can't load
   it into agent v1.0.0.
6. **I/O contract** — every example's input must validate against the declared
   input schema, and running the skill must produce output matching the output schema.
7. **Idempotency** — same input → same output (for deterministic skills).
8. **Code examples are runnable** — extract ```python``` blocks from SKILL.md
   and execute them. If they break, the docs are lying.
9. **Agent can discover & use** — integration test where the agent is given
   a prompt and we verify it picks the right skill, calls it correctly, and
   produces a coherent answer.

### C. Agent behavior tests (your specific question)

These catch the silent failures that pure LLM evals miss:

- **Tool selection accuracy**: Given "what's the weather in Paris?", did the
  agent call `get_weather` and not `get_news` or `delete_database`?
- **Tool call schema**: Are the args valid? If `send_email` requires `to` and
  `body`, the agent must provide both.
- **Plan order**: For "look up Alice then email her", did the agent call
  `lookup_user` BEFORE `send_email`?
- **No infinite loops**: Agent must terminate within max_steps.
- **Token budget**: Stays under N tokens per scenario.
- **Latency SLO**: P95 < X seconds.
- **Permission boundary**: Agent with restricted tool list cannot call
  forbidden tools, even if user asks.
- **Idempotency**: Same prompt → same tool call sequence (with temperature=0).
- **Refusal correctness**: Agent refuses clearly harmful requests.
- **Sub-agent delegation**: Orchestrator agent correctly delegates to sub-agent.
- **State persistence**: Resume a conversation mid-way and verify state.

### D. Building a golden dataset

For RAGAS and DeepEval, you need a "golden dataset" — examples with
known-good answers. Build it like this:

1. Manually collect 50-100 real (question, ground_truth_answer) pairs from your domain.
2. For RAG tests, also include the relevant doc IDs.
3. Store in `tests/ai_evals/golden_dataset.json` or a CSV.
4. Version control it. When your LLM improves, you can rerun the same set
   and see if scores go up.

### E. The AI evals workflow

The flow in `ai-evals.yml`:

1. **On every PR** (fast subset):
   - Promptfoo regression (catches prompt changes)
   - DeepEval metrics (hallucination, relevancy, etc.)
   - RAGAS (RAG quality)
   - Rebuff (injection detection)
   - Presidio (PII)
   - Agent behavior (tool use, cost, latency)

2. **Nightly** (full):
   - All of the above, plus:
   - Garak (deep vuln scan, many probes)
   - Promptfoo red team (hundreds of attacks)
   - Heavy load tests

---

## 8. Security: defense in depth

You asked for "topmost security". The pattern is **defense in depth** —
multiple independent layers, each catching things the others miss.

| Layer | Tool | Catches |
|---|---|---|
| 1. Code style | Ruff, Black, markdownlint, yamllint | Bad patterns, security smells |
| 2. Type checking | Mypy, Pyright | Type confusion, NoneType errors |
| 3. Secret scanning | Gitleaks, TruffleHog | Committed API keys, passwords |
| 4. Dependency scanning | pip-audit, OSV-Scanner, Renovate | Vulns in 3rd-party code |
| 5. SAST (static) | CodeQL, Bandit, Semgrep | SQLi, XSS, path traversal, eval |
| 6. IaC scanning | Checkov, Trivy, Hadolint | Misconfigured Docker, compose, K8s |
| 7. Container scanning | Trivy, Grype | OS package vulns in image |
| 8. License compliance | pip-licenses | GPL/AGPL contamination |
| 9. SBOM | Syft, GH Attestations | Track what's in your image |
| 10. Image signing | Cosign | Tamper detection |
| 11. SLSA provenance | GH Attestations | Provenance (where/when built) |
| 12. Repo security | OpenSSF Scorecard | Branch protection, action pinning |
| 13. LLM-specific | DeepEval, RAGAS, Garak, Rebuff, Presidio | Hallucination, injection, PII |
| 14. Performance | k6, Locust | DoS, capacity issues |

Each layer is independent. If Gitleaks misses a secret, TruffleHog might catch
it. If Bandit misses an XSS, Semgrep or CodeQL will catch it.

---

## 9. How CI connects to your homelab

You have:
- **GitHub Actions** as CI
- **Watchtower** as CD (polls registries and auto-pulls new images)

The flow:

```
PR merged to main
   │
   ▼
release.yml triggers (on tag push OR manual)
   │
   ├─► Build image with `docker build`
   ├─► Generate SBOM with Syft
   ├─► Sign with Cosign
   ├─► Push to GHCR (and DockerHub)
   └─► (Optional) Webhook to Watchtower

Meanwhile, on your homelab, Watchtower runs:
   every 5 minutes:
     for each running container:
       check GHCR for newer image
       if newer:
         pull
         stop old
         start new
```

**Important caveats:**

1. **No staging environment.** Watchtower pulls whatever is in your registry.
   For real production, you'd want: dev → staging → prod, with manual approval
   between staging and prod. With Watchtower, you get one environment.

2. **Watchtower polls by default.** You can speed up the deploy with a webhook,
   but it's not required.

3. **Watchtower doesn't roll back automatically.** If the new image crashes,
   your service is down. Use a healthcheck to mitigate:
   ```yaml
   # in your docker-compose.yml
   services:
     app:
       image: ghcr.io/you/your-app:latest
       healthcheck:
         test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
         interval: 30s
         timeout: 5s
         retries: 3
       restart: unless-stopped
   ```
   With a healthcheck, Docker will mark the container unhealthy if `/health`
   fails, and Watchtower will pull the previous image.

4. **For real production**, consider:
   - **ArgoCD** or **Flux** for GitOps-based deploys.
   - **Portainer** as a UI on top of Docker.
   - **Drain/sleep before kill** for zero-downtime deploys.

---

## 10. Cost & speed: keeping CI fast and cheap

GitHub Actions free tier:
- 2,000 minutes/month for private repos
- Unlimited for public repos
- Each job runs on a fresh VM (no state between jobs)

Tips:

1. **Concurrency** — cancel in-progress runs when a new commit is pushed:
   ```yaml
   concurrency:
     group: ${{ github.workflow }}-${{ github.ref }}
     cancel-in-progress: true
   ```

2. **Caching** — cache pip, npm, Docker layers:
   ```yaml
   - uses: actions/setup-python@v5
     with:
       cache: pip
   - uses: actions/cache@v4
     with:
       path: ~/.cache/uv
       key: ${{ runner.os }}-uv-${{ hashFiles('uv.lock') }}
   ```

3. **Run heavy tests on schedule, not every PR**:
   - `mutmut`: nightly only
   - `k6/Locust`: nightly only
   - `Garak`: nightly only
   - `TruffleHog`: nightly only

4. **Fail fast** — use `needs:` to skip downstream jobs when an upstream fails:
   ```yaml
   jobs:
     test:
       needs: [lint, typecheck]  # only run if those pass
   ```

5. **Use matrix builds sparingly** — running tests on 5 OS versions takes
   5x the time. Stick to `ubuntu-latest` unless you really need to test other OSes.

6. **Self-hosted runners** — if CI costs become an issue, you can run
   `actions-runner` on your homelab. Free, no minute limits.

---

## 11. Maintenance: keeping the pipeline healthy

### Weekly
- Check the Renovate PR. Approve dependency updates.
- Look at any failed CI runs. Fix or ignore.

### Monthly
- Review Dependabot/Renovate config. Bump version constraints.
- Review the OpenSSF Scorecard. Look for new recommendations.
- Update the golden dataset for AI evals.

### Quarterly
- Bump tool versions in workflows (Ruff, Mypy, etc.).
- Review the AI evals thresholds. Tighten as quality improves.
- Audit `.github/CODEOWNERS`. Make sure the right people review the right things.

### When a CVE drops
1. Renovate auto-creates a PR for the affected dep.
2. CI runs all tests against the new version.
3. You review and merge.
4. The image is rebuilt and pushed.
5. Watchtower deploys the fix.

If Renovate is too slow:
1. Manually update the dep in `pyproject.toml`.
2. Push. CI runs.
3. If green, the release job builds and pushes the fixed image.

---

## 12. Troubleshooting

### "Mypy is too slow / fails on 3rd party libs"

Add to `pyproject.toml`:
```toml
[[tool.mypy.overrides]]
module = ["some_3rd_party_lib.*"]
ignore_missing_imports = true
```

Or run with `--ignore-missing-imports` as a flag.

### "Ruff complains about a rule I don't care about"

Add the rule to `ignore` in `pyproject.toml`:
```toml
[tool.ruff.lint]
ignore = ["E501", "B008"]
```

### "CodeQL finds a 'vulnerability' that's actually fine"

Mark it as a false positive in the Security tab. Add a comment explaining why.

### "GitHub Actions minutes ran out"

Solutions:
- Move heavy tests to nightly.
- Use self-hosted runners on your homelab.
- GitHub gives free minutes for public repos.

### "Trivy is slow"

Use `severity: HIGH,CRITICAL` to only scan high-severity issues. Or
`--skip-db-update` if you've already updated the DB.

### "An AI test is flaky (passes sometimes, fails other times)"

LLM outputs are non-deterministic. Solutions:
- Set `temperature=0` in tests.
- Run each test multiple times and check the median.
- Lower the metric threshold (0.7 instead of 0.9).
- Use larger models (GPT-4o > GPT-4o-mini for consistency).

### "Watchtower isn't pulling new images"

- Check Watchtower logs: `docker logs watchtower`.
- Verify the image was actually pushed: `docker pull ghcr.io/you/your-app:latest`.
- Watchtower needs the right labels. Add to your compose:
  ```yaml
  labels:
    - "com.centurylinklabs.watchtower.enable=true"
  ```
- Make sure Watchtower is monitoring the right registry.

---

## 13. Glossary

| Term | Meaning |
|---|---|
| **CI** | Continuous Integration. Auto-run tests on every push. |
| **CD** | Continuous Deployment. Auto-deploy after tests pass. |
| **Workflow** | A YAML file in `.github/workflows/`. |
| **Job** | A group of steps that run on the same VM. |
| **Step** | One action (use a pre-made action, or run a shell command). |
| **Runner** | The VM that runs your workflow. |
| **Action** | A reusable piece of code (like `actions/checkout@v4`). |
| **Secret** | Encrypted env var stored in repo settings. |
| **SARIF** | Standard format for security tool results. Uploaded to Security tab. |
| **SBOM** | Software Bill of Materials. List of every dep. |
| **SLSA** | Supply-chain Levels for Software Artifacts. A framework for build integrity. |
| **Cosign** | Tool for signing/verifying container images (Sigstore). |
| **SAST** | Static Application Security Testing. Scans source code for vulns. |
| **DAST** | Dynamic Application Security Testing. Attacks a running app. |
| **IaC** | Infrastructure as Code. YAML/Terraform files defining infra. |
| **CVE** | Common Vulnerabilities and Exposures. A public list of known vulns. |
| **RAG** | Retrieval-Augmented Generation. LLM that retrieves docs before answering. |
| **OIDC** | OpenID Connect. Lets GitHub Actions prove its identity to cloud providers without long-lived keys. |
| **GHCR** | GitHub Container Registry. |
| **Watchtower** | Tool that auto-pulls new Docker images and restarts containers. |
| **Dependabot/Renovate** | Tools that auto-create PRs to update deps. |
| **Property-based testing** | Test the *property* (relationship) instead of specific output. |
| **Mutation testing** | Introduce bugs, check if tests catch them. |
| **Property** | A behavior that should hold for all inputs. |
| **Hallucination** | When an LLM makes up facts not in its source material. |
| **Prompt injection** | When a user tricks an LLM into ignoring its instructions. |
| **PII** | Personally Identifiable Information. Names, emails, SSNs, etc. |
| **Canary token** | A unique secret planted in a prompt to detect leaks. |

---

## What's next?

Once you've got the basics running:

1. **Add branch protection** (Step 9 above) — non-negotiable.
2. **Build your golden dataset** — without it, your AI evals are meaningless.
3. **Set up monitoring** — Sentry for errors, Grafana for metrics, LangSmith for LLM traces.
4. **Add observability** — OpenTelemetry traces, structured logs.
5. **Add staging** — even a second Watchtower instance pointing at a `staging` tag.
6. **Add chaos engineering** — kill services randomly, verify recovery.

You've got this. 💪
