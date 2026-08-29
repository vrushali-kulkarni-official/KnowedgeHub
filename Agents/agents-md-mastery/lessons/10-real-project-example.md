# Lesson 10 — The Complete `AGENTS.md` Set for Your AI SaaS Project

> 🔴 **Production-ready**
> 🎯 **Goal:** Drop the files in `/workspace/agents-md-mastery/production-ai-saas/`
> directly into your repo and start shipping.

---

## 10.1 The Files You're Getting

```text
production-ai-saas/
├── AGENTS.md                    ← root orchestrator (~1800 tokens)
├── AGENTS.example.md            ← template for contributors
└── sub-agents/
    ├── backend-fastapi.md       ← FastAPI / Pydantic / services
    ├── data-postgres.md         ← Postgres / SQLAlchemy / Alembic
    ├── vector-qdrant.md         ← Qdrant / embeddings
    ├── ai-langchain.md          ← LangChain / LangGraph / RAG
    ├── security-reviewer.md     ← Security auditor (read-only)
    └── devops-deployer.md       ← Docker / GH Actions / Ubuntu
```

These six files **are the system**. They cover the six domains of your
project, and they enforce the safety rules from Lessons 06 and 07.

---

## 10.2 How to Use These Files

```bash
# 1. Copy them into your real repo
cp production-ai-saas/AGENTS.md            /path/to/your-ai-saas/
cp -r production-ai-saas/sub-agents/       /path/to/your-ai-saas/
cp production-ai-saas/AGENTS.example.md    /path/to/your-ai-saas/

# 2. Add AGENTS.local.md to .gitignore (for personal overrides)
echo "AGENTS.local.md" >> /path/to/your-ai-saas/.gitignore

# 3. Commit
cd /path/to/your-ai-saas
git add AGENTS.md AGENTS.example.md sub-agents/
git commit -m "Add AGENTS.md orchestrator + 6 sub-agents"

# 4. Test with a harness
cd /path/to/your-ai-saas
gemini -p "Add a /health endpoint"
# or
claude -p "Add a /health endpoint"
# or
openclaw run --agent backend-fastapi --task "Add a /health endpoint"
```

That's it. Your AI agents now have a clear, scoped, safe set of instructions.

---

## 10.3 File-by-File Walkthrough

I've annotated each file inline (with `<!--` comments) so you can read it
like a tutorial. The comments explain *why* each line is there.

### Root: `AGENTS.md`

This is the **orchestrator**. It doesn't write code — it routes work to
the right sub-agent. Read it top-to-bottom and you'll see:
- Who you are
- What the project is
- Where things live
- Which sub-agent does what
- Safety rules
- Conflict resolution

### `sub-agents/backend-fastapi.md`

FastAPI specialist. Owns the HTTP layer. Cannot touch migrations, cannot
push to deploy. Knows Pydantic v2, async patterns, dependency injection,
and how to write a clean OpenAPI spec.

### `sub-agents/data-postgres.md`

Postgres specialist. Owns schema, migrations (Alembic), and query
optimization. Cannot deploy the app. Asks before running destructive
migrations.

### `sub-agents/vector-qdrant.md`

Qdrant specialist. Owns collections, payload indexes, and embedding
pipelines. Cannot edit the LLM chain that calls it.

### `sub-agents/ai-langchain.md`

LangChain + LangGraph specialist. Owns chains, agents, RAG pipelines,
state machines. Cannot deploy.

### `sub-agents/security-reviewer.md`

**Read-only** security auditor. Runs `bandit`, `gitleaks`, `pip-audit`,
`trivy`. Refuses to write code. Flags CVEs, secrets, and prompt-injection
attempts.

### `sub-agents/devops-deployer.md`

Docker, GitHub Actions, and Ubuntu deployment. Owns `Dockerfile`,
`docker-compose.yml`, `.github/workflows/`, and the production server
setup. Cannot write application code.

---

## 10.4 A Worked Example — Multi-Agent Task

**Your prompt:**
> "Add an endpoint that lets users upload PDFs and ask questions about them."

**What happens (in order):**

```text
1. You: send the prompt to the harness.
2. Harness: reads AGENTS.md (root).
3. Root: "This spans HTTP, vector, and LLM. Delegate."
4. Root → backend-fastapi: "Design POST /documents/upload."
5. backend-fastapi returns: route stub + Pydantic models.
6. Root → vector-qdrant: "Design the 'tenant_documents' collection."
7. vector-qdrant returns: collection schema + index plan.
8. Root → ai-langchain: "Design the chunking + embedding + QA chain."
9. ai-langchain returns: LangGraph state machine spec.
10. Root: stitches the three outputs into a plan.
11. Root → you: "Here's the plan. Approve to proceed?"
12. You: "yes"
13. Root → backend-fastapi: "Write the code now."
14. ...etc.
```

Notice: **at no point does the root agent write code itself.** It orchestrates.
That's the multi-agent pattern, and it lives entirely in `AGENTS.md`.

---

## 10.5 The Maintenance Loop

Once a month, do this:

```text
1. Read the root AGENTS.md out loud. Is it still true?
2. Read each sub-agent. Has the sub-team added new constraints?
3. Run scripts/lint-agents-md.py (Lesson 08).
4. Run scripts/audit-agents-md.py to see what drifted.
5. Open a PR with the month's edits.
6. Tag the release.
```

This 30-minute monthly ritual will keep your `AGENTS.md` from rotting.

---

## 10.6 What To Do When an Agent Misbehaves

```text
1. Save the bad output (don't delete it).
2. Find the agent's AGENTS.md version (git tag).
3. Diff against the previous version.
4. Was it a rule that was missing? Add it.
5. Was it a rule that was too soft? Tighten it.
6. Was the agent given a skill it shouldn't have? Revoke it.
7. Was the LLM just wrong? Add an example to the persona showing
   the right answer.
8. File a post-mortem. Update the linter to catch the failure mode.
9. Roll forward, not back. Don't delete the file; improve it.
```

---

## 10.7 Going Beyond — The Next Level

Once you're comfortable with the basics:

- **Lesson 11 (self-study):** Add a `agents/skills/` folder with **named
  skill packs** that any sub-agent can `use_skill("postgres_query")` to
  load. This is the LangChain-of-AGENTS.md pattern.
- **Lesson 12 (self-study):** Add a **memory** layer where the orchestrator
  records what each sub-agent has done, so it can be re-invoked
  intelligently. (This is what LangGraph does for your *application*.)
- **Lesson 13 (self-study):** Add a **prompt-injection firewall** that
  inspects every file the agent reads, looking for instructions
  embedded in the file content. (A research area; not standardized yet.)

---

## ✅ You're Done

You now have:
- ✅ A mental model of `AGENTS.md` (Lesson 01)
- ✅ A working first file (Lesson 02)
- ✅ Persona design (Lesson 03)
- ✅ Multi-agent orchestration (Lesson 04)
- ✅ Skill grants (Lesson 05)
- ✅ Writing safety (Lesson 06)
- ✅ Reading safety (Lesson 07)
- ✅ Production patterns + CI (Lesson 08)
- ✅ Cross-harness compatibility (Lesson 09)
- ✅ A complete drop-in file set for your project (Lesson 10)

Go ship it. 🚀

👉 [Back to README →](../README.md)
