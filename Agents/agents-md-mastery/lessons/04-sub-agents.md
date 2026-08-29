# Lesson 04 — Sub-Agents and Orchestration

> 🟡 **Difficulty: Medium**
> 🎯 **Goal:** Split one agent into a team of specialists that work together.

---

## 4.1 The Problem With One Big Agent

Imagine you put *all* your personas in one `AGENTS.md`:

```markdown
# You are a backend engineer, a security auditor, a database expert,
# a DevOps engineer, a frontend dev, and a test engineer.
# Switch roles based on the prompt.
```

What actually happens:

1. The LLM tries to be all of them at once.
2. Output is muddled — backend code with security caveats wrapped in DevOps YAML.
3. Token budget explodes (every role's rules are in the context).
4. You can't tell who's "speaking" in the output.

This is called **persona bleed**. The fix is **sub-agents**.

---

## 4.2 What is a Sub-Agent?

A sub-agent is a **separate, focused agent** with:

- Its **own** `AGENTS.md` (or a section in a multi-agent file)
- Its **own** persona
- Its **own** skills/tools
- A **clear scope** (files, domains, or task types it owns)

The **parent** agent (usually the one in the root `AGENTS.md`) decides **when** to
invoke each sub-agent and passes them context.

Two main patterns exist in the wild:

### Pattern A — File-based sub-agents (most common)

```text
repo/
├── AGENTS.md                ← parent orchestrator
└── .github/
    └── agents/              ← (or sub-agents/, or agents.md is split)
        ├── backend-fastapi.md
        ├── data-postgres.md
        ├── ai-langchain.md
        ├── security-reviewer.md
        └── devops-deployer.md
```

Each sub-agent file is its own complete `AGENTS.md`. The parent *references* them.

### Pattern B — Inline sub-agents (single file, multiple sections)

Some tools (like `claude.md` or `agents.md` in some harnesses) support multiple
agents in one file using a header convention. Less common, harder to maintain.

We'll focus on **Pattern A** — it's the production standard.

---

## 4.3 The Parent Agent — Orchestrator Pattern

The root `AGENTS.md` should **not** do the work. Its job is to **delegate**.

```markdown
# 🤖 AGENTS.md — Root Orchestrator

## Identity
You are the **engineering lead** for this AI SaaS project. You do not write
production code yourself. You **delegate** to specialist sub-agents.

## Sub-Agent Roster
You have the following sub-agents available. **Always delegate** to the
appropriate one for the task at hand.

| Sub-agent            | Use when…                                                       |
|----------------------|-----------------------------------------------------------------|
| `backend-fastapi`    | Writing FastAPI routes, services, Pydantic models, middleware   |
| `data-postgres`      | Schema changes, migrations, query optimization, ORM models       |
| `vector-qdrant`      | Embedding pipelines, vector search tuning, collection design    |
| `ai-langchain`       | LangChain / LangGraph chains, agents, RAG pipelines             |
| `security-reviewer`  | Reviewing a PR for vulns, secrets, authz, injection             |
| `devops-deployer`    | Dockerfile, docker-compose, GitHub Actions, Ubuntu server setup |

## Delegation Rules
1. **Read** the relevant sub-agent's file before invoking it.
2. **Pass** the full user request + any extracted context to the sub-agent.
3. **Combine** outputs from multiple sub-agents if the task spans domains.
4. **Never** do a sub-agent's job yourself, even if the change is small.
5. **Refuse** tasks outside the roster (e.g. "build a React UI") with a polite
   note that the project is backend-only.

## Identity (default fallback)
If no sub-agent fits (small doc edit, simple README tweak), act as a
**general-purpose senior engineer** with the project's style rules.
```

**This is a powerful pattern.** The parent is a router. It never writes code.

---

## 4.4 Anatomy of a Sub-Agent File

A sub-agent file is **the same shape** as a root `AGENTS.md`, but:

- Scoped tighter (one domain only)
- Has a "trigger" header that the parent uses to know when to invoke it
- Inherits nothing — sub-agent must be **self-contained** (or explicitly say
  "inherit from root")

```markdown
<!--
=================================================================
  sub-agents/backend-fastapi.md
  Trigger: any task touching FastAPI routes, services, or middleware
=================================================================
-->

# Role: Backend FastAPI Specialist

## Identity
You are a senior FastAPI engineer. You ONLY work on:
- Route handlers (`@app.get`, `@app.post`, …)
- Service-layer modules
- Pydantic request/response models
- Middleware and dependencies
- Background tasks and WebSocket endpoints

You do **not** touch:
- Database migrations (delegate to `data-postgres`)
- LLM chains (delegate to `ai-langchain`)
- Docker / CI (delegate to `devops-deployer`)

## Skills
You may:
- Read and write any file under `backend/`
- Run `pytest` and `ruff`
- Run `uvicorn` for local smoke tests

You may **not**:
- Edit `migrations/`, `alembic/`, or any `*.sql` file
- Edit `Dockerfile`, `docker-compose.yml`, `.github/workflows/*`
- Push to remote, merge PRs, deploy

## Code Style (FastAPI specifics)
- Use `APIRouter` per domain, not one giant `app`.
- Group routes by feature, not by HTTP verb.
- Use `Depends()` for shared dependencies (DB session, current user).
- Every endpoint declares `response_model` and `status_code`.
- Pydantic models live in `models/`, one file per resource.
- Errors use `HTTPException` with the correct status code and a `detail` dict.

## Hand-off
When you finish, your output is a **diff** (or a list of changed files) that
the orchestrator will integrate. Do not commit. Do not push.
```

---

## 4.5 The Roster Pattern (Put This in Every Parent)

A clean roster table is the most important part of an orchestrator file. It's
what the parent "reads" to decide who to call.

```markdown
## Sub-Agent Roster

| Sub-agent         | Domain                                     | Triggers (keywords)              |
|-------------------|--------------------------------------------|----------------------------------|
| `backend-fastapi` | HTTP layer, services, middleware           | "route", "endpoint", "service"   |
| `data-postgres`   | Schema, migrations, queries                | "migration", "index", "query"    |
| `vector-qdrant`   | Vector search, embeddings                  | "embed", "search", "qdrant"     |
| `ai-langchain`    | LLM chains, RAG, agents                    | "chain", "rag", "langgraph"     |
| `security-reviewer` | Audits, secrets, authz                  | "audit", "review", "security"   |
| `devops-deployer` | Docker, CI, deploy                         | "docker", "deploy", "ci"         |
```

**Tip:** keep the trigger list tight. The parent will pattern-match on these
keywords (or you, the human, will read this and pick the right sub-agent).

---

## 4.6 The Two Communication Models

When the parent delegates to a sub-agent, how does context flow?

### Model 1 — Synchronous Delegation (one-shot)

```text
Parent reads user prompt
  → picks sub-agent A
  → reads sub-agent A's file
  → sends (user prompt + sub-agent A file) to LLM
  → gets back A's answer
  → picks sub-agent B if needed
  → sends (A's answer + sub-agent B file) to LLM
  → gets back B's answer
  → final response
```

Used in: Cursor Composer, Claude Code (sometimes), most IDE agents.

### Model 2 — Persistent Sub-Agents (long-running)

```text
Parent spawns sub-agents as separate "workers" with their own context windows.
Sub-agents can call tools, talk to each other, and report back.
Parent aggregates.
```

Used in: Hermes, OpenClaw, LangGraph multi-agent workflows.

**For your AI SaaS project**, you'll use **Model 1** with **LangGraph** as the
orchestrator. Yes — your *application*'s LLM orchestration will mirror this
pattern. Recursion is a feature, not a coincidence.

---

## 4.7 Inheritance — Sub-Agents Should Re-state, Not Inherit

**Bad pattern:**

```markdown
<!-- ❌ "inherit from parent" — fragile, agents forget -->
See root AGENTS.md for base rules.
```

**Good pattern:**

```markdown
<!-- ✅ Repeat the rules the sub-agent MUST follow, even if duplicated -->
- Python 3.11+, type hints everywhere
- SQLAlchemy 2.0 async
- Pydantic v2
- Tests in tests/, mirror source tree
```

Why? Because sub-agent context windows are sometimes **separate** from the parent.
If the parent file is missing or truncated, the sub-agent must still behave.

**Yes, there's duplication. Yes, it's worth it.** We'll solve this with a
shared `agents/_shared.md` snippet in Lesson 08.

---

## 4.8 Real Example — Three Sub-Agents Working Together

**Task:** *"Add an endpoint that lets a user upload a PDF, embeds it, and
stores the chunks in Qdrant."*

**Orchestrator's flow:**

```text
1. Parent reads task.
2. Recognizes three domains: HTTP (backend), Vector (qdrant), LLM (langchain).
3. Delegates:

   → backend-fastapi:
        "Create POST /documents/upload that accepts multipart PDF, validates
        user, and hands the file to a service called DocumentIngestService."

   → vector-qdrant:
       "Design the Qdrant collection 'tenant_documents' with payload fields
        tenant_id, document_id, chunk_index. Add a payload index on tenant_id."

   → ai-langchain:
       "Write the chunking + embedding function. Use Google text-embedding-004
        via LangChain. Return list of (text, vector, metadata) tuples."

4. Parent stitches the three outputs into a single plan.
5. Returns the plan to the user.
6. (User approves.) Parent invokes each sub-agent again, this time to **write code**.
7. Sub-agents produce diffs. Parent integrates.
```

That's a multi-agent workflow — and it lives entirely in `AGENTS.md` files.

---

## 4.9 Sub-Agent Naming Conventions

Stick to **lowercase-with-dashes** for sub-agent IDs. The filename **is** the ID.

```text
✅ backend-fastapi.md      → sub-agent id: backend-fastapi
✅ security-reviewer.md    → sub-agent id: security-reviewer
❌ BackendFastAPI.md       → avoid, case sensitivity bites you on Windows
❌ backend_fastapi.md      → works but the rest of the ecosystem uses dashes
```

---

## 4.10 Sub-Agent Count — Less is More

A good roster has **3 to 7** sub-agents. More than that, the parent's
delegation logic gets confused.

```text
3 sub-agents  → minimum viable team
5 sub-agents  → typical (your project)
7 sub-agents  → max recommended
10+           → split into multiple repos / monorepo sub-projects
```

For your project, we have **6** sub-agents. That's the upper edge of ideal.
You could merge `vector-qdrant` and `ai-langchain` into a single `ai-rag` agent
if you wanted 5.

---

## ✅ What's Next?

In **Lesson 05** we wire the most important part: **skills and tool grants**.
This is where you decide which sub-agent can do what, and — critically —
which can never do certain things. This is your **defense in depth**.

👉 [Open Lesson 05 →](./05-skills-and-tools.md)
