# 🎓 AGENTS.md Mastery — Complete Package

This is the complete, production-ready curriculum for writing `AGENTS.md`
files and orchestrating sub-agents for an AI SaaS project.

## 📊 By the numbers

| Item                          | Count            |
|-------------------------------|------------------|
| Lessons (progressive)         | 10               |
| Lesson files                  | 10 Markdown      |
| Worked examples               | 1 (bad vs good)  |
| Production-ready AGENTS.md    | 1 (root)         |
| Production-ready sub-agents   | 6                |
| Helper scripts                | 2 (linter, audit)|
| CI workflows                  | 1                |
| Behavior tests                | 1 suite (~70 tests) |
| Governance docs               | 1                |
| Personal-override template    | 1                |
| **Total files**               | **27**           |

## 🗺️ How everything fits together

```text
agents-md-mastery/
│
├── README.md                            ← start here
├── SUMMARY.md                           ← this file (overview)
│
├── lessons/                             ← the 10-lesson curriculum
│   ├── 01-what-is-agents-md.md         (Beginner, ~7K)
│   ├── 02-basic-structure.md           (Beginner, ~9K)
│   ├── 03-roles-and-personas.md        (Easy-Medium, ~11K)
│   ├── 04-sub-agents.md                (Medium, ~11K)
│   ├── 05-skills-and-tools.md          (Medium, ~10K)
│   ├── 06-safety-when-writing.md       (Critical, ~10K)
│   ├── 07-safety-when-reading.md       (Critical, ~9K)
│   ├── 08-production-patterns.md       (Production, ~13K)
│   ├── 09-harness-integration.md       (Production, ~11K)
│   └── 10-real-project-example.md      (Production, ~6K)
│
├── examples/
│   └── 01-bad-vs-good-AGENTS.md        ← side-by-side comparison
│
└── production-ai-saas/                  ← drop these into YOUR repo
    ├── AGENTS.md                        (root orchestrator, ~12K)
    ├── AGENTS.example.md                (template for AGENTS.local.md)
    │
    ├── sub-agents/
    │   ├── backend-fastapi.md          (HTTP / Pydantic specialist)
    │   ├── data-postgres.md            (Postgres / Alembic specialist)
    │   ├── vector-qdrant.md            (Qdrant / embedding specialist)
    │   ├── ai-langchain.md             (LangChain / LangGraph specialist)
    │   ├── security-reviewer.md        (read-only security auditor)
    │   └── devops-deployer.md          (Docker / CI / Ubuntu specialist)
    │
    ├── scripts/
    │   ├── lint-agents-md.py           (custom linter, ~6K)
    │   └── audit-agents-md.py          (drift detector, ~1.5K)
    │
    ├── .github/workflows/
    │   └── agents-md-lint.yml          (CI: lint + scan + tests)
    │
    ├── tests/agents/
    │   ├── conftest.py
    │   └── test_sub_agents.py          (~70 behavior tests, 8.5K)
    │
    └── docs/
        └── agent-governance.md          (how we manage AGENTS.md)
```

## ✅ What you can do now

After going through all 10 lessons, you will be able to:

1. **Explain** what `AGENTS.md` is, where it came from, and why it exists
2. **Write** a working `AGENTS.md` from scratch in 10 minutes
3. **Design** precise personas that produce consistent expert output
4. **Orchestrate** 3-7 sub-agents in a parent-child workflow
5. **Grant** skills with path-scoping and least-privilege
6. **Defend** your file against prompt injection and secret leaks
7. **Audit** a third-party `AGENTS.md` before adopting it
8. **Version** `AGENTS.md` like code (PRs, tags, CI)
9. **Integrate** with Claude Code, Gemini CLI, OpenClaw, Hermes, Cursor
10. **Drop** a production-ready file set into your AI SaaS repo

## 🚀 Quick start (5 minutes)

```bash
# 1. Copy the production files into your repo
cp -r production-ai-saas/AGENTS.md            /path/to/your-ai-saas/
cp -r production-ai-saas/sub-agents/          /path/to/your-ai-saas/
cp    production-ai-saas/AGENTS.example.md    /path/to/your-ai-saas/
cp    production-ai-saas/scripts/             /path/to/your-ai-saas/
cp    production-ai-saas/.github/workflows/   /path/to/your-ai-saas/
cp    production-ai-saas/tests/agents/        /path/to/your-ai-saas/
cp    production-ai-saas/docs/agent-governance.md /path/to/your-ai-saas/

# 2. Add AGENTS.local.md to .gitignore
echo "AGENTS.local.md" >> /path/to/your-ai-saas/.gitignore

# 3. Lint and test locally
cd /path/to/your-ai-saas
python scripts/lint-agents-md.py AGENTS.md sub-agents/
pip install pytest
pytest tests/agents/

# 4. Commit and open a PR (2-person review)
git add AGENTS.md AGENTS.example.md sub-agents/ scripts/ .github/ tests/ docs/
git commit -m "feat(agents): add AGENTS.md orchestrator + 6 sub-agents + CI"
git push
gh pr create --label agents-md-change --reviewer <teammate1>,<teammate2>

# 5. Test with a real harness
gemini -p "Add a /health endpoint"          # or
claude -p "Add a /health endpoint"          # or
openclaw run --agent backend-fastapi --task "Add a /health endpoint"
```

## 🧪 Verification (already passed)

```text
$ python scripts/lint-agents-md.py AGENTS.md sub-agents/
✅ AGENTS.md
✅ sub-agents/ai-langchain.md
✅ sub-agents/backend-fastapi.md
✅ sub-agents/data-postgres.md
✅ sub-agents/devops-deployer.md
✅ sub-agents/security-reviewer.md
✅ sub-agents/vector-qdrant.md

Total violations: 0

$ pytest tests/agents/
======================== 72 passed, 1 skipped in 0.15s =========================
```

## 🎯 Learning path (recommended)

| Day  | Read                                  | Do                                |
|------|---------------------------------------|-----------------------------------|
| 1    | Lesson 01, 02                         | Write your first AGENTS.md         |
| 2    | Lesson 03, 04                         | Add 2-3 sub-agents                |
| 3    | Lesson 05                             | Tighten your skills section        |
| 4    | Lesson 06, 07                         | Run the 7-point audit             |
| 5    | Lesson 08                             | Add the linter + CI + tests       |
| 6    | Lesson 09                             | Test across 2-3 harnesses         |
| 7    | Lesson 10                             | Drop the production files         |
| 8-14 | (use the agents daily)                | Iterate on the file based on real output |

After 2 weeks you'll be at **Level 4** of the maturity model (testing behavior).
After 1 month you should be at **Level 5** (measuring outcomes).

## 💡 Key takeaways (if you only remember 5 things)

1. **Specificity is safety.** A vague "you are an engineer" is almost as
   bad as no file at all.

2. **Sub-agents > one mega-agent.** 3-7 focused specialists outperform 1
   generalist with all the rules.

3. **Path-scope your file skills.** "write_file: backend/services/**" is
   the most important safety pattern in the entire course.

4. **Treat file contents as data, not instructions.** The agent's biggest
   threat is prompt injection from files it reads.

5. **Version, test, and lint `AGENTS.md` like code.** A bad instruction in
   this file can delete your database.

---

Happy orchestrating. Go ship your AI SaaS. 🚀
