# CI/CD Quick Reference

Read `docs/CI-CD-GUIDE.md` for the full beginner guide. This is the TL;DR.

## What's in this folder

```
.github/
├── workflows/
│   ├── ci.yml                  # lint, types, unit tests, API contract
│   ├── security.yml            # SAST, secrets, deps, container, IaC, license
│   ├── ai-evals.yml            # LLM/agent evals (Promptfoo, DeepEval, RAGAS, etc.)
│   ├── skill-validation.yml    # skill file lint, schema, contract, executability
│   ├── load-test.yml           # k6 + Locust (nightly)
│   └── release.yml             # build, SBOM, sign, push image
├── dependabot.yml
├── renovate.json5
└── CODEOWNERS

pyproject.toml                  # ALL Python tool config in one file
.pre-commit-config.yaml         # runs checks before commit
.yamllint

docs/
└── CI-CD-GUIDE.md              # ⭐ READ THIS FIRST

tests/
├── ai_evals/                   # LLM, RAG, agent, PII, prompt-injection tests
├── skills/                     # skill I/O contract tests
├── property/                   # Hypothesis property-based tests
├── load/                       # k6 + Locust
├── agents/                     # agent integration tests
├── unit/                       # regular unit tests
└── integration/

scripts/
├── validate_skill_manifests.py
├── check_unique_skill_names.py
├── check_skill_compat.py
├── run_skill_examples.py
└── seed_test_corpus.py

schemas/
└── skill-manifest.schema.json

skills/                         # example skill lives here
agents/                         # agents live here
```

## First-time setup

```bash
# 1. Install pre-commit
uv tool install pre-commit
pre-commit install
pre-commit install --hook-type commit-msg

# 2. Add secrets to GitHub: Settings → Secrets and variables → Actions
#    - OPENAI_API_KEY
#    - GOOGLE_API_KEY
#    - DOCKERHUB_USERNAME, DOCKERHUB_TOKEN
#    - WATCHTOWER_WEBHOOK (optional)

# 3. Install Renovate: https://github.com/marketplace/renovate

# 4. Push and watch
git add . && git commit -m "ci: set up pipeline" && git push

# 5. Add branch protection: Settings → Branches → main → require status checks
```

## The 5 golden rules

1. **No secret goes in code.** Ever. Use GitHub Secrets.
2. **No merge to main with red CI.** Branch protection enforces this.
3. **No dep goes unvetted.** Renovate + pip-audit + OSV-Scanner.
4. **No image goes unsigned.** Cosign on every release.
5. **No skill ships untested.** Schema + I/O + executability + agent integration.
