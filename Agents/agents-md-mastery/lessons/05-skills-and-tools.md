# Lesson 05 — Skills and Tool Grants (The Heart of Agent Safety)

> 🟠 **Difficulty: Medium**
> 🎯 **Goal:** Learn to grant the *minimum* skills each agent needs, and nothing more.

---

## 5.1 What is a "Skill" in the Agent World?

In the context of agent harnesses (Claude Code, Gemini CLI, OpenClaw, Hermes,
Cursor, Aider, Continue), a **skill** is a **named capability** the agent can
invoke. It maps to a real action.

| Skill name      | What it actually does              | Real-world risk |
| --------------- | ---------------------------------- | --------------- |
| `read_file`     | Read a file from disk              | 🟢 low          |
| `write_file`    | Write a file to disk               | 🟡 medium       |
| `edit_file`     | Patch a file (find/replace)        | 🟡 medium       |
| `run_shell`     | Execute an arbitrary shell command | 🔴 high         |
| `web_search`    | Hit a search engine                | 🟡 medium       |
| `web_fetch`     | Fetch a URL and parse              | 🟡 medium       |
| `git_commit`    | `git commit`                       | 🟠 high         |
| `git_push`      | `git push`                         | 🔴 critical     |
| `docker_run`    | `docker run`                       | 🔴 critical     |
| `kubectl_apply` | `kubectl apply`                    | 🔴 critical     |
| `db_query`      | Run a SQL query                    | 🟠 high         |
| `db_migrate`    | Run a migration                    | 🔴 critical     |

**Skills are not the same as LLM functions.** Skills are **granted by the
harness** to the agent. The LLM can *ask* to use a skill, but the harness
**decides** whether to allow it.

```text
LLM:   "I want to run: rm -rf /tmp/cache"
Tool:  ❌ DENIED — `run_shell` is granted, but `rm -rf` is on the deny-list.
```

This is your **first line of defense**.

---

## 5.2 The Skills Section in `AGENTS.md`

There is no universal syntax for declaring skills — each harness is slightly
different. But the **de facto** convention (used by Claude Code, OpenClaw,
Hermes, and most modern harnesses) is a `## Skills` section like this:

```markdown
## Skills

### Granted (allow-list)
- `read_file`
- `write_file`      (paths: `backend/**`, `tests/**`, `docs/**`)
- `edit_file`       (paths: `backend/**`, `tests/**`)
- `run_shell`       (commands: `pytest`, `ruff`, `mypy`, `uv`, `docker compose`)

### Denied (deny-list — these are NEVER allowed, even if user asks)
- `git_push`        (no pushing; user reviews all PRs manually)
- `docker_push`     (no pushing images; CI does that)
- `db_drop`         (no DROP TABLE, DROP DATABASE, TRUNCATE)
- `kubectl_delete`  (no resource deletion in any cluster)
- `*secrets*`       (any skill matching "secret" is denied)

### Conditional (require human approval)
- `git_commit`      (allowed, but show diff and wait for "yes")
- `db_migrate`      (allowed, but show SQL first and wait for "yes")
- `docker_run`      (allowed only for `docker compose up`, never for raw `docker run`)
```

That's a **complete skills block**. Three lists: granted, denied, conditional.

---

## 5.3 Path-Scoped Skills — Your Secret Weapon

Most modern harnesses support **path scoping** on file skills. This is gold.

```markdown
### Granted with path scoping
- `read_file`         (any path)
- `write_file`        (paths: `backend/services/chatservices/**`)
- `edit_file`         (paths: `backend/models/**`, `backend/services/**`)
- `run_shell`         (commands: `pytest tests/chatservices/`)
```

Now the `backend-fastapi` sub-agent can:

- ✅ Read any file
- ✅ Write only inside `services/chatservices/`
- ❌ Edit anything else, even if the user asks

**This is the most important safety pattern in the entire course.** If you
remember only one thing, remember path-scoped skills.

---

## 5.4 The Least-Privilege Principle

Every skill you grant is a **liability**. Ask three questions:

```text
1. Does the role actually NEED this skill to do its job?
2. Can I scope it tighter (path, command, argument)?
3. If this skill is abused, what's the worst case?
```

Worked example for your project:

### `backend-fastapi` sub-agent

```markdown
Granted:
  - read_file (any)
  - write_file (paths: backend/**, tests/**)
  - edit_file (paths: backend/**, tests/**)
  - run_shell (commands: pytest, ruff, mypy, uvicorn --reload)
Denied:
  - git_push, docker_push, kubectl_*
  - any file matching backend/migrations/**  ← delegate to data-postgres
```

### `data-postgres` sub-agent

```markdown
Granted:
  - read_file (any)
  - write_file (paths: backend/models/**, backend/migrations/**, alembic/**)
  - edit_file (same paths)
  - run_shell (commands: alembic, psql --dry-run)
Conditional:
  - db_migrate (show SQL, wait for approval)
Denied:
  - git_push, docker_push
  - backend/services/**  ← delegate to backend-fastapi
```

### `security-reviewer` sub-agent

```markdown
Granted:
  - read_file (any)
  - run_shell (commands: bandit, gitleaks detect, pip-audit, trivy fs)
  - web_search (for CVE lookups)
Denied:
  - write_file          ← reviewers don't write code
  - edit_file           ← reviewers don't patch code
  - run_shell (commands: anything destructive)
  - git_push, git_commit
```

Notice: **the security reviewer is read-only.** That's a deliberate constraint.
A reviewer that can also write is just a dev with a fancy title.

---

## 5.5 Skills Across Your Roster

Here's the full skills matrix for your AI SaaS project:

| Skill                | backend-fastapi | data-postgres  | vector-qdrant  | ai-langchain   | security-reviewer | devops-deployer |
| -------------------- |:---------------:|:--------------:|:--------------:|:--------------:|:-----------------:|:---------------:|
| `read_file`          | ✅               | ✅              | ✅              | ✅              | ✅                 | ✅               |
| `write_file`         | ✅ (scoped)      | ✅ (scoped)     | ✅ (scoped)     | ✅ (scoped)     | ❌                 | ✅ (scoped)      |
| `edit_file`          | ✅ (scoped)      | ✅ (scoped)     | ✅ (scoped)     | ✅ (scoped)     | ❌                 | ✅ (scoped)      |
| `run_shell` (safe)   | ✅ (pytest…)     | ✅ (alembic…)   | ✅ (qdrant…)    | ✅ (pytest…)    | ✅ (bandit…)       | ✅ (docker…)     |
| `run_shell` (unsafe) | ❌               | ❌              | ❌              | ❌              | ❌                 | ❌               |
| `git_commit`         | ⚠️ conditional  | ⚠️ conditional | ⚠️ conditional | ⚠️ conditional | ❌                 | ⚠️ conditional  |
| `git_push`           | ❌               | ❌              | ❌              | ❌              | ❌                 | ❌               |
| `db_query` (read)    | ✅               | ✅              | ⚠️ via API     | ⚠️ via API     | ✅ (anonymized)    | ❌               |
| `db_migrate`         | ❌               | ⚠️ conditional | ❌              | ❌              | ❌                 | ❌               |
| `web_search`         | ✅               | ✅              | ✅              | ✅              | ✅                 | ✅               |
| `web_fetch`          | ✅               | ✅              | ✅              | ✅              | ✅                 | ✅               |
| `docker_run`         | ⚠️ compose only | ❌              | ❌              | ❌              | ❌                 | ✅ (compose)     |
| `docker_push`        | ❌               | ❌              | ❌              | ❌              | ❌                 | ❌               |
| `kubectl_*`          | ❌               | ❌              | ❌              | ❌              | ❌                 | ⚠️ apply only   |

Legend: ✅ allowed · ❌ denied · ⚠️ needs human approval

---

## 5.6 The "Human-in-the-Loop" Pattern

For the **conditional** skills, the agent must:

1. Show what it's about to do (diff, command, SQL)
2. Stop and wait
3. Only proceed after the human says "yes" or types a confirm keyword

A common pattern in `AGENTS.md`:

```markdown
## Human-in-the-Loop

The following actions require explicit human confirmation in the chat:
- `git commit`         → show `git diff --staged`, then ask "Commit? (yes/no)"
- `db_migrate`         → show SQL, then ask "Apply? (yes/no)"
- `docker compose up`  → show the compose file diff, then ask "Up? (yes/no)"
- deleting any file    → show path, then ask "Delete? (yes/no)"

If the user says "yes", proceed. If "no" or silence > 60s, abort.
```

Most harnesses support a "stop and ask" hook. This is the standard.

---

## 5.7 Pre-Action Hooks (Advanced)

Some harnesses let you define **hooks** that run *before* a skill is invoked.
This is the gold standard.

```markdown
## Hooks

### pre_run_shell
Before running ANY shell command, log it to `.agent-audit.log` with:
- timestamp
- agent id
- full command
- working directory
```

This creates an **audit trail**. If something goes wrong, you can trace which
agent ran what. (We expand on this in Lesson 08.)

---

## 5.8 Anti-Patterns in Skills

| Anti-pattern                                       | Why it's bad                                           |
| -------------------------------------------------- | ------------------------------------------------------ |
| Granting `run_shell` to all agents with no scoping | Anyone can `rm -rf`                                    |
| Granting `*` (all skills) to a "do-anything" agent | Defeats least-privilege, single point of failure       |
| Granting `git_push` to anyone                      | Pushes bypass code review                              |
| Granting `db_drop` "just in case"                  | One typo, data gone                                    |
| Letting the agent decide its own skills            | Self-grant is the most dangerous pattern               |
| No deny-list, only allow-list                      | New skills added later are auto-granted  — bad default |

---

## ✅ What's Next?

Now that you can grant skills safely, we need to talk about the **biggest
real-world risk**: **what you accidentally put in `AGENTS.md` itself**. Lesson 06
covers secrets, prompt injection, and the mistakes that get agents fired (and
companies breached).

👉 [Open Lesson 06 →](./06-safety-when-writing.md)
