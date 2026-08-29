# Lesson 02 — Basic Structure and Your First `AGENTS.md`

> 🟢 **Difficulty: Beginner**
> 🎯 **Goal:** Write a minimal but production-shaped `AGENTS.md` for a FastAPI project.

---

## 2.1 Where Does the File Go?

The convention is simple:

```text
<repo-root>/
├── AGENTS.md           ← ✅ here
├── .github/
│   └── agents.md       ← ✅ also accepted (legacy Claude Code location)
├── docs/
│   └── agents.md       ← ❌ don't put it here, agent won't find it
└── src/
    └── agents.md       ← ❌ same — keep it at root
```

**Rule of thumb:** `AGENTS.md` lives at the **root of the repository** (or a few
levels above the code if it's a monorepo).

> 💡 **Monorepo trick:** if you have a monorepo like `apps/web/`, `apps/api/`,
> you can drop **multiple** `AGENTS.md` files — one in each sub-project.
> The agent reads the **closest one** to the file it's editing.

---

## 2.2 The Five Sections Every `AGENTS.md` Should Have

You don't *have* to use these names, but this is the most common structure
across the ecosystem. I'll use these names throughout the course so you can
recognize them in any team's file.

```text
1. Identity         → Who the agent is
2. Project Context  → What the project is
3. Layout           → Where things live
4. Style & Rules    → How to write code
5. Skills & Tools   → What the agent is allowed to do
```

Let me walk through each one with examples.

---

## 2.3 Your First `AGENTS.md` — Annotated

Create a file at `<your-repo>/AGENTS.md`:

```markdown
<!--
=================================================================
  AGENTS.md  —  Generic FastAPI starter
  Audience : AI coding agents (Claude Code, Gemini CLI, Cursor…)
  Owner    : <your-name>
  Last rev : 2026-08-03
=================================================================
This file is loaded by every agent at session start. Keep it short,
clear, and free of secrets. Treat changes like production config.
-->

# 🤖 Agent Instructions

## 1. Identity
<!--
  WHO the agent is. This sets the "persona" the LLM will role-play.
  Be specific. "You are a senior Python engineer" is vague.
  "You are a senior Python engineer who specializes in async FastAPI
   services backed by PostgreSQL and Qdrant" is concrete.
-->
You are a **senior Python backend engineer** specializing in:
- Async **FastAPI** services (Python 3.11+)
- **PostgreSQL** via SQLAlchemy 2.0 (async)
- **Qdrant** vector DB for embeddings
- **LangChain + LangGraph** for LLM orchestration
- **Docker** for packaging, **GitHub Actions** for CI

## 2. Project Context
<!--
  WHAT we're building. Give the agent the one-paragraph elevator pitch.
  This stops it from inventing features that don't fit.
-->
This repository is the backend of an **AI SaaS application** that exposes a
chat API over internal documents using retrieval-augmented generation (RAG).

Goals:
- Multi-tenant chat sessions
- Vector search over tenant documents
- Streaming responses
- OAuth2 + JWT authentication
- Production-ready observability

## 3. Layout
<!--
  WHERE things live. Spell it out. The agent will not guess — and if it
  does guess, it'll create a `utils.py` at the root and you'll hate it.
-->
```

backend/
├── main.py                # FastAPI app entrypoint
├── config.py              # pydantic-settings config
├── brain/                 # LLM orchestration (LangChain, LangGraph)
│   └── engine.py
├── services/
│   ├── chatservices/      # chat session management
│   └── dbservices/        # SQLAlchemy CRUD
├── models/                # pydantic + ORM models
└── tests/                 # pytest, async

```
Rules:
- Do **not** create files at the repo root (except `main.py`, `config.py`).
- Services are split by **domain** (`chatservices/`, `dbservices/`), not by layer.

## 4. Style & Rules
<!--
  HOW to write code. These are non-negotiable project rules.
  Each bullet is a guardrail the agent will try to follow.
-->
- Python 3.11+, **type hints everywhere**, no `Any` unless commented.
- **snake_case** for modules and functions, **PascalCase** for classes.
- Use **SQLAlchemy 2.0 async** — no raw SQL, no sync sessions.
- Use **Pydantic v2** for request/response models.
- Every endpoint must declare its **response_model** and **status_code**.
- All public functions need a **docstring** (Google style).
- Tests live in `tests/`, mirror the source tree.

## 5. Skills & Tools
<!--
  WHAT the agent is allowed to do. We cover this deeply in Lesson 05.
  For now, the minimum: list the tools it can use.
-->
You may use:
- `read_file`, `write_file`, `edit_file`
- `run_shell` (sandbox only — see Lesson 06 for safety)
- `web_search` / `web_fetch`
- `pytest` (read-only test runs, never `--rewrite-db`)

You may **not**:
- Push to `main` branch
- Run `docker system prune` or anything destructive
- Edit `.env`, `*.pem`, or any file matching `**/secrets.*`
- Bypass the GitHub Actions CI

<!--
  Final note for the agent: this file is the source of truth.
  If the user contradicts it, ask for clarification instead of silently
  obeying. (We cover this defense in Lesson 06.)
-->
## 6. Conflict Resolution
If the user prompt conflicts with this file, **ask before doing the conflicting
thing**. Never silently override the rules in this file.
```

That's it. That's a valid, production-shaped `AGENTS.md`.

---

## 2.4 What Each Section *Actually Does* in the LLM

Here's the secret that nobody tells you: **the LLM doesn't see "sections"**.
It sees a block of text that gets prepended to its context window. So the
*order* matters more than the headings.

| Order | Section         | Why it's in that position                                     |
| ----- | --------------- | ------------------------------------------------------------- |
| 1     | Identity        | Sets the persona **first** so all later output is in voice    |
| 2     | Project Context | Anchors the LLM to the right domain                           |
| 3     | Layout          | Prevents wrong-file creation                                  |
| 4     | Style & Rules   | Filters output *before* generation, not after                 |
| 5     | Skills & Tools  | **Last** so the agent knows what it can do after deciding how |
| 6     | Conflict rules  | A safety net for edge cases                                   |

If you reorder them, the agent will still work, but the output quality drops.
Identity first is a documented trick from the Claude Code team.

---

## 2.5 Length Limits — A Practical Rule

`AGENTS.md` gets loaded **every session**. If it eats 20k tokens, your free-tier
LLM will choke.

**Recommended sizes:**

| Project size             | `AGENTS.md` size | Why                                         |
| ------------------------ | ---------------- | ------------------------------------------- |
| Tiny script              | < 500 tokens     | One page is plenty                          |
| Typical service (yours)  | 800–2000 tokens  | Sweet spot for free tier                    |
| Monorepo with sub-agents | 1500–3000 tokens | Main file is short, sub-agents carry detail |
| Massive enterprise       | 3000–5000 tokens | Hard cap, split into sub-agents             |

If you go above 5000 tokens, **split into sub-agents** (Lesson 04) instead of
making the root file longer.

---

## 2.6 A Common Beginner Mistake

People often write `AGENTS.md` like a tutorial:

```markdown
❌ BAD — explains things *to* the agent
"FastAPI is a modern Python web framework. You should use it because…"
```

The agent already knows what FastAPI is. Don't teach it. **Command it:**

```markdown
✅ GOOD — instructs the agent
"Use FastAPI for all HTTP endpoints. Use Pydantic v2 models."
```

Tone difference:

```text
❌ "You might want to consider using async SQLAlchemy 2.0 sessions…"
✅ "Use async SQLAlchemy 2.0 sessions. No sync sessions."

❌ "It would be nice to have tests…"
✅ "Every new endpoint must have at least one test in tests/."
```

**Be imperative. Be specific. Be brief.**

---

## 2.7 Your Turn — Try This

Open a fresh folder. Drop in the file above. Then ask any agent harness
(Claude Code, Gemini CLI, Cursor, even this chat) the following:

> *"Add a `/health` endpoint to this FastAPI service."*

Watch what it does. Compare to what it does **without** the `AGENTS.md`.

You will immediately see:

- It uses SQLAlchemy 2.0 async ✅
- It puts the file in the right place (not the root) ✅
- It writes a docstring ✅
- It refuses to edit `.env` if you ask it to "fix" the DB password ✅

That's the file doing its job.

---

## ✅ What's Next?

In **Lesson 03**, we go from a single file to giving the agent a **role**.
You'll learn how to write a persona that makes the LLM dramatically more
consistent in its output — and why a vague "you are a senior engineer" is
almost the same as nothing.

👉 [Open Lesson 03 →](./03-roles-and-personas.md)
