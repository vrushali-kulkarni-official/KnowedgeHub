# Lesson 01 — What is `AGENTS.md` and Why Does It Exist?

> 🟢 **Difficulty: Beginner**
> 🎯 **Goal:** Understand the *what*, *where it came from*, and *why* before you write a single line.

---

## 1.1 The 30-Second Explanation

`AGENTS.md` is a **Markdown file at the root of a repository** that gives AI coding
agents (Claude Code, Gemini CLI, Cursor, OpenClaw, Hermes, etc.) persistent,
project-specific instructions.

Think of it as a **README.md, but the reader is an AI agent that can run code.**

```text
README.md     → tells HUMANS about your project
AGENTS.md     → tells AI AGENTS how to work on your project
```

That's the whole idea. Now let's go deeper.

---

## 1.2 Where Did It Come From?

### The problem it solves

Before `AGENTS.md`, every time you opened a new chat with an AI coding agent, you had to:

1. Re-explain your stack ("I use FastAPI, Postgres, Qdrant, LangChain…")
2. Re-state your code style ("I prefer type hints everywhere, snake_case files…")
3. Re-list your project layout ("The backend is in `/brain`, services in `/services`…")
4. Re-warn about constraints ("Never commit secrets, always use SQLAlchemy 2.0…")

That's **prompt boilerplate** — and it breaks the moment you forget a detail.

### The fix

`AGENTS.md` standardizes the place where the agent looks *first* for context. It was
popularized around 2024-2025 by:

| Tool                      | Role                             |
| ------------------------- | -------------------------------- |
| Claude Code               | CLI agent by Anthropic           |
| Gemini CLI                | CLI agent by Google              |
| Cursor                    | IDE with built-in agent          |
| Aider / OpenClaw / Hermes | Open-source agent harnesses      |
| Continue.dev              | VSCode extension with agent mode |

All of them adopted a similar convention: **look for `AGENTS.md` in the repo root, read it, and treat its contents as project-wide instructions.**

---

## 1.3 What It Is NOT

Let me clear up some common confusions before we go further.

| ❌ It's not                                | ✅ What it actually is                                  |
| ----------------------------------------- | ------------------------------------------------------ |
| A replacement for `README.md`             | A separate file, often used **alongside** README.md    |
| A magic prompt that "activates" an AI     | A plain Markdown file the agent reads at session start |
| A way to control which LLM the agent uses | A neutral, tool-agnostic spec                          |
| A locked-down security boundary           | A **trust boundary** (we cover this in lesson 7)       |
| Something only the agent ever sees        | Humans can (and should) read it too — it lives in git  |

---

## 1.4 What Problem Does It Solve FOR YOU?

For your AI SaaS project specifically, an `AGENTS.md` will:

- **Stop the agent from inventing project structure** ("I'll just create a `utils.py` at the root!") because you already told it your layout.
- **Keep the agent on your chosen libraries** ("Use LangChain, don't reach for LlamaIndex").
- **Enforce your style** ("SQLAlchemy 2.0 async, no raw SQL, snake_case modules").
- **Reduce hallucination on the free-tier LLM** (Gemini free tier has weaker memory — this file is its long-term memory).
- **Make handoffs between agents and humans consistent** (sub-agents inherit the same root instructions).

---

## 1.5 The Mental Model

Here's the picture you should hold in your head:

```text
┌─────────────────────────────────────────────────────────────┐
│  Your Repository                                            │
│                                                             │
│  ├── README.md          ← humans read this                  │
│  ├── AGENTS.md          ← AI agents read this               │
│  │   ├── (root rules)                                       │
│  │   ├── (project layout)                                   │
│  │   ├── (style guide)                                      │
│  │   └── (skills the agent is allowed to use)               │
│  │                                                          │
│  ├── .github/                                               │
│  │   └── sub-agents/    ← (some teams put sub-agents here)  │
│  │       ├── backend-fastapi.md                             │
│  │       ├── data-postgres.md                               │
│  │       └── security-reviewer.md                           │
│  │                                                          │
│  ├── brain/             ← your real code                    │
│  ├── services/                                              │
│  └── docker-compose.yml                                     │
└─────────────────────────────────────────────────────────────┘
```

The agent's mental flow when you start a session:

```text
1. Open repo
2. Read AGENTS.md (always)
3. Read sub-agent files IF delegated to a sub-agent
4. Combine with current user prompt
5. Act
```

---

## 1.6 The Three Big Principles

Keep these in mind through every lesson:

### Principle 1 — Explicit > Implicit

If the agent has to guess, it will guess wrong. **Spell things out.**

### Principle 2 — Least Privilege

Only grant the skills a role actually needs. A security reviewer doesn't need
deployment tools. A backend dev doesn't need to push to production.

### Principle 3 — Treat It as Code

`AGENTS.md` goes in git, gets reviewed, gets versioned, gets CI-checked.
A bad instruction in this file can delete your database. Treat it like an
`nginx.conf` or a `terraform.tf`.

---

## 1.7 Quick Self-Check

Before moving on, answer these (in your head is fine):

1. What's the difference between `README.md` and `AGENTS.md`?
2. Name two agent harnesses that read `AGENTS.md`.
3. True or false: `AGENTS.md` replaces `README.md`.
4. Why does the free-tier Gemini LLM benefit more from an `AGENTS.md` than a paid model?

<details>
<summary>Answers</summary>

1. `README.md` is for humans; `AGENTS.md` is for AI agents.
2. Claude Code, Gemini CLI, Cursor, OpenClaw, Hermes, Aider, Continue.dev — any of two.
3. **False.** They coexist.
4. Because free-tier models have weaker session memory and benefit from a persistent context file. A paid model "remembers more" between sessions, but a clear `AGENTS.md` still helps both.

</details>

---

## ✅ What's Next?

In **Lesson 02**, you'll write your **first `AGENTS.md`** — a minimal but valid one
for a real FastAPI project. We'll cover file placement, required sections, and the
exact wording that makes agents behave correctly.

👉 [Open Lesson 02 →](./02-basic-structure.md)
