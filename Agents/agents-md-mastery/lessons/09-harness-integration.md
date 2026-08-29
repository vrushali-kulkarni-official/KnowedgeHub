# Lesson 09 — Agent Harness Integration (Claude Code, Gemini CLI, OpenClaw, Hermes, Cursor)

> 🟠 **Difficulty: Production**
> 🎯 **Goal:** Make your `AGENTS.md` work across **every** harness you use,
> not just one.

---

## 9.1 What is an Agent Harness?

The **harness** is the program that:
1. Reads your `AGENTS.md`
2. Sends it + your prompt to an LLM
3. Receives the LLM's tool-call requests
4. **Enforces** which tools/skills are actually allowed
5. Returns the result to you

```text
┌─────────────────────────────────────────────────────┐
│  You (in the terminal / IDE)                        │
│      ↓                                              │
│  Harness (Claude Code / Gemini CLI / OpenClaw…)     │
│      ↓                                              │
│  ┌────────────────────┐  ┌────────────────────┐    │
│  │ AGENTS.md loader   │  │ Skill enforcer     │    │
│  └────────────────────┘  └────────────────────┘    │
│      ↓                          ↓                   │
│  LLM (Anthropic / Google / OpenAI / local)         │
│      ↓                                              │
│  Tool execution (file system, shell, git, etc.)    │
└─────────────────────────────────────────────────────┘
```

The harness is the **security boundary**. Your `AGENTS.md` is the **policy**.

Different harnesses have slightly different syntax. Let's map them.

---

## 9.2 The Big Four Harnesses — How They Read `AGENTS.md`

| Harness       | Reads from             | Skill syntax            | Sub-agents |
|---------------|------------------------|-------------------------|------------|
| **Claude Code** | `AGENTS.md` (root), `CLAUDE.md` (alt) | `## Skills` + path scoping | Yes (Task tool) |
| **Gemini CLI**  | `AGENTS.md` (root)  | `## Tools` section      | Yes (delegate) |
| **OpenClaw**    | `AGENTS.md` + `agents/*.md` | YAML frontmatter + body | Native multi-agent |
| **Hermes**      | `AGENTS.md` + per-folder overrides | `## capabilities`      | Native multi-agent |
| **Cursor**      | `.cursorrules` (legacy) + `AGENTS.md` (newer) | `## rules` section | Project-level |
| **Aider**       | `AGENTS.md` (convention), `CONVENTIONS.md` (alt) | `## commands` | No |
| **Continue.dev** | `AGENTS.md` (system prompt) | `## tools` block | VSCode only |

**Bottom line:** there is **no single spec**. The Markdown sections we've
written (`## Identity`, `## Layout`, `## Skills`, `## Conflict Resolution`)
work everywhere because every harness falls back to "treat as system prompt"
when it doesn't recognize a section.

---

## 9.3 The Common Subsets — What Every Harness Understands

These sections are **universal** — every harness will read them and behave
better when they're present.

```markdown
# 🤖 AGENTS.md

## Identity
[Persona description — read as system prompt]

## Project Context
[Elevator pitch — read as system prompt]

## Layout
[File tree — read as system prompt]

## Style & Rules
[Code style — read as system prompt]

## Skills
[Skill list — most harnesses parse this; some ignore it and require
 their own config]

## Conflict Resolution
[What to do when user prompt conflicts — read as system prompt]
```

If you only write these six sections, you're **80% compatible** with every
harness on the market.

---

## 9.4 Claude Code — Specifics

Claude Code (by Anthropic) reads `AGENTS.md` and additionally supports:

- `CLAUDE.md` as an alias (older projects use this)
- A `.claude/` folder for project-specific config
- A `permissions.json` file for **enforced** skill grants
- A `settings.json` for harness settings

### `CLAUDE.md` vs `AGENTS.md`

```text
CLAUDE.md   →  Claude Code looks for this FIRST
AGENTS.md   →  Claude Code looks for this if CLAUDE.md is absent
```

For multi-harness compatibility, **prefer `AGENTS.md`**.

### Claude Code Permissions (enforced, not just instructed)

`AGENTS.md` is **instructions**. `permissions.json` is **enforcement**. For
production safety, use both.

```json
// .claude/permissions.json
{
  "allow": [
    "Read",
    "Write(backend/services/**)",
    "Edit(backend/services/**)",
    "Bash(pytest*)",
    "Bash(ruff*)"
  ],
  "deny": [
    "Bash(rm*)",
    "Bash(git push*)",
    "Bash(docker push*)",
    "Write(.env*)",
    "Write(**/secrets*)"
  ]
}
```

The `deny` list is **absolute** — the LLM cannot talk its way past it.

---

## 9.5 Gemini CLI — Specifics

Gemini CLI reads `AGENTS.md` and:

- Uses Google's Gemini models (free tier supported)
- Has a `.gemini/` folder for settings
- Supports a `GEMINI.md` as an alias (older projects)
- Skills are declared in a `## Tools` section (or a `gemini-config.json`)

### Gemini's Tool Format

```markdown
## Tools
- `read_file` (any path)
- `write_file` (paths: backend/**, tests/**)
- `run_shell` (commands: pytest, ruff)
- `google_web_search`
- `code_execution` (sandbox: docker)
```

Or, equivalently, in `gemini-config.json`:

```json
{
  "tools": {
    "read_file": { "enabled": true },
    "write_file": { "enabled": true, "path_allowlist": ["backend/**", "tests/**"] },
    "run_shell": {
      "enabled": true,
      "command_allowlist": ["pytest", "ruff", "mypy"]
    }
  }
}
```

### Gemini Free-Tier Tip

The free tier has stricter rate limits. To get the most out of it:

1. **Keep `AGENTS.md` under 1500 tokens** — saves context budget.
2. **Pre-cache the file structure** in the Identity section so the model
   doesn't waste tokens re-deriving it.
3. **Use deterministic instructions** ("Always use SQLAlchemy 2.0 async")
   not exploratory ones ("You might want to use…").

---

## 9.6 OpenClaw — Specifics

OpenClaw (open-source) is **multi-agent native**. It expects:

- A `agents/` folder at the repo root
- One Markdown file per agent
- YAML frontmatter for metadata

### `agents/backend-fastapi.md` (OpenClaw format)

```markdown
---
name: backend-fastapi
version: 1.2.0
skills:
  granted:
    - read_file
    - write_file
  granted_scoped:
    write_file:
      paths: ["backend/**", "tests/**"]
  denied:
    - git_push
    - docker_push
model: claude-sonnet-4.5
temperature: 0.2
---

# Role: Backend FastAPI Specialist

## Identity
You are a senior FastAPI engineer…
[rest of the file, same as before]
```

The **frontmatter** is enforced by OpenClaw's YAML parser. Anything in
`skills.denied` is **hard-blocked**, not just instructed.

---

## 9.7 Hermes — Specifics

Hermes is also multi-agent native, similar to OpenClaw, but uses a slightly
different convention:

```markdown
<!-- agents/backend-fastapi.md (Hermes format) -->

# Agent: backend-fastapi

## capabilities
- read_file (any)
- write_file (backend/**, tests/**)
- edit_file (backend/**, tests/**)
- run_shell (pytest, ruff, mypy)

## restrictions
- git_push: denied
- docker_push: denied
- backend/migrations/**: denied
- .env*: denied

## persona
You are a senior FastAPI engineer…

## prompt_template
You are a senior FastAPI engineer working on {project_name}.
The current task is: {user_prompt}.
You have access to: {capabilities}.
You may NOT: {restrictions}.
```

Hermes' `prompt_template` is interesting — it lets you parameterize the
agent's prompt with runtime values.

---

## 9.8 Cursor — Specifics

Cursor has historically used `.cursorrules` but now also reads `AGENTS.md`.

- `.cursorrules` is **Cursor-only** — don't write a project around it.
- `AGENTS.md` is **multi-harness** — write the project around this.

For Cursor, also add `.cursorignore` (analogous to `.gitignore`):

```text
# .cursorignore
.env
.env.*
**/secrets.*
**/*.pem
```

---

## 9.9 Cross-Harness Compatibility — A Recipe

To write **one** `AGENTS.md` that works everywhere:

1. **Use the universal six sections** (Identity, Project Context, Layout,
   Style, Skills, Conflict Resolution).
2. **Put skill grants in a `## Skills` section** as a Markdown list.
   Harnesses that parse it will parse it. Harnesses that don't will ignore
   it gracefully.
3. **For path scoping**, use a **comment-annotated** style:
   ```markdown
   - `write_file`   # paths: backend/**, tests/**
   ```
   Some harnesses read the inline comment. Others read only the bare skill.
4. **Avoid YAML frontmatter** unless you're committed to OpenClaw.
5. **Avoid JSON config blocks** unless you're committed to Claude Code.
6. **Keep it Markdown-first.** All harnesses understand plain Markdown.

---

## 9.10 The "Harness Test" — Run Your File Through Each Tool

```bash
# Test 1: Claude Code
claude --load-AGENTS.md -p "Add a /health endpoint"

# Test 2: Gemini CLI
gemini -p "Add a /health endpoint"  # auto-loads AGENTS.md

# Test 3: OpenClaw
openclaw run --agent backend-fastapi --task "Add a /health endpoint"

# Test 4: Hermes
hermes invoke backend-fastapi --task "Add a /health endpoint"
```

If the output is consistent across all four, your `AGENTS.md` is
cross-harness compatible.

---

## 9.11 The "Local LLM" Case (Ollama, LM Studio)

If you run a local LLM, `AGENTS.md` is even more important because the
smaller model has weaker priors. Things to add:

```markdown
## Local-LLM Specific Hints
- Be explicit about imports. Local models sometimes invent libraries.
- Always include the file path in your diff comments.
- Prefer `from x import y` over `import x` then `x.y()`.
- Add type hints to every function you write. Local models skip them otherwise.
```

---

## 9.12 The Final Cross-Harness Cheat Sheet

| You want…                                    | Use this section           |
|----------------------------------------------|----------------------------|
| Persona                                      | `## Identity`              |
| Project context                              | `## Project Context`       |
| File layout                                  | `## Layout`                |
| Code style                                   | `## Style & Rules`         |
| Skill grants (human-readable, multi-harness)| `## Skills` (Markdown list)|
| Skill grants (enforced in Claude Code)       | `.claude/permissions.json` |
| Skill grants (enforced in OpenClaw)         | YAML frontmatter           |
| Skill grants (enforced in Hermes)           | `## capabilities` + `## restrictions` |
| Sub-agent roster                             | `## Sub-Agent Roster` (table) |
| Conflict resolution                          | `## Conflict Resolution`   |
| Personal overrides                           | `AGENTS.local.md` (gitignored) |
| Secrets policy                               | `## Secrets` section       |
| Prompt-injection defense                     | `## Prompt Injection Defense` |

---

## ✅ What's Next?

Final lesson. **Lesson 10** is the payoff: I'll give you the **complete,
production-ready `AGENTS.md` set** for your specific AI SaaS project
(FastAPI + Postgres + Qdrant + LangChain + LangGraph + Docker + GitHub
Actions + Ubuntu). Drop these into your repo and you're production-ready.

👉 [Open Lesson 10 →](./10-real-project-example.md)
