# The Complete Guide to Agentic Coding CLIs: Claude Code, OpenCode & Antigravity CLI

## Part 0: The Mental Model — What Even *Is* an Agentic Coding CLI?

Before we touch any tool, you need to understand the fundamental idea, because everything else is a variation on it.

### 0.1 Autocomplete vs. Chat vs. Agent

There are three generations of AI coding help:

1. **Autocomplete** (GitHub Copilot circa 2021): You type, it suggests the next few lines. It's a very smart keyboard.
2. **Chat** (ChatGPT in a browser): You copy-paste code, get advice, copy-paste it back. The AI has no eyes and no hands.
3. **Agent** (Claude Code, OpenCode, Antigravity CLI): You give the AI a *goal* in plain English, and it **reads your files, runs your terminal commands, edits your code, runs your tests, sees the failures, and fixes them** — in a loop, until the goal is done.

An agentic CLI is not a chatbot. It is a **loop**:

```
┌─────────────────────────────────────────────┐
│  1. You state a GOAL in natural language    │
│  2. The model REASONS about what to do      │
│  3. It picks a TOOL (read file, run bash,   │
│     edit file, search web...)               │
│  4. The tool EXECUTES and returns output    │
│  5. Output goes back into the model's       │
│     CONTEXT; it decides the next step       │
│  6. Repeat until the model decides it's     │
│     done → then it reports back to you      │
└─────────────────────────────────────────────┘
```

This loop is called the **agentic loop**. Every tool you'll learn (Claude Code, OpenCode, Antigravity CLI) implements this loop with different models, tools, and guardrails. That's why learning one transfers ~80% to the others.

### 0.2 The five universal concepts

Every agentic CLI has these five systems. Learn them once, apply them everywhere:

| Concept                          | What it is                                                                     | Analogy                                     |
| -------------------------------- | ------------------------------------------------------------------------------ | ------------------------------------------- |
| **Context / Instructions file**  | Markdown files the agent reads every session (CLAUDE.md, AGENTS.md)            | A senior engineer's onboarding doc          |
| **Permissions**                  | Rules for which tools need your approval                                       | A junior dev's access badge                 |
| **Hooks**                        | Your scripts that fire on lifecycle events (before/after edits, on stop)       | CI checks welded into the agent             |
| **MCP (Model Context Protocol)** | A standard plug-in protocol to connect external tools (databases, Jira, Slack) | USB-C for AI tools                          |
| **Subagents**                    | Spawning fresh, isolated agent instances for sub-tasks                         | Hiring a specialist contractor for one task |

Everything in this guide is a deeper dive into these five concepts inside each specific tool.

### 0.3 Why this matters for *your* project

You're building an enterprise AI harness with **Python, uv, FastAPI, Pydantic, LangChain**. These CLIs will be your "developers." The most important skill is not prompting — it's **describing your project conventions well** (in CLAUDE.md/AGENTS.md) and **gating the agent** (permissions + hooks running `ruff`, `mypy`, `pytest`). We'll build exactly this setup in Part 5.

---

# PART 1: CLAUDE CODE

Claude Code is Anthropic's terminal agent, widely considered the strongest for long multi-file work . As of late 2026, its default model is Claude Opus 5.5 .

## 1.1 Installation (beginner)

You need **one** of these. The native installer is recommended (no Node.js needed); the npm path needs Node 22+ .

```bash
# Option A: native installer (recommended)
curl -sL claude.ai/install.sh | sh

# Option B: npm
npm install -g @anthropic-ai/claude-code

# Option C: macOS Homebrew
brew install anthropic/claude/claude
```

Then, in **your project directory**:

```bash
cd ~/your-project
claude          # launches the interactive session
/login          # authenticates via browser (first run does this automatically)
```

Now type your first prompt:

```
> What does this repo do? Read the key files and summarize.
```

Watch carefully what happens. Claude will call tools — `Read`, `Glob`, `Grep` — and you'll see each tool call before it runs. This is the agentic loop, live.

**Slash commands you'll use daily:**

- `/help` — all commands
- `/clear` — wipe context (huge context = degraded quality + higher cost)
- `/compact` — summarize old context to free space
- `/model` — switch model (opus = deep reasoning, sonnet = daily driver, haiku = cheap/fast)
- `/init` — generate a starter CLAUDE.md from your repo
- `/cost` — see session spend
- `!` prefix — run a bash command directly without the model
- `#` prefix — quick memory: `# never use print, always use logger` → saved to CLAUDE.md

## 1.2 Permission modes (safety, beginner-critical)

Claude asks before doing risky things by default. You choose the level:

- **default** — asks before each edit/bash command (annoying but safe while learning)
- **acceptEdits** — auto-accept file edits, still asks for bash
- **plan mode** (`shift+tab` to toggle) — Claude *researches* and proposes a plan but cannot change anything until you approve. **Use this for anything architectural.**
- **bypassPermissions** — no asking at all. Never use this outside a disposable container.

## 1.3 CLAUDE.md — your project's brain (beginner → intermediate)

This is the single highest-leverage file in your setup. Claude reads it at session start. Put it at your repo root; put smaller ones in subdirectories (they load as Claude works in them) .

`CLAUDE.md` is **additive** — user-level (`~/.claude/CLAUDE.md`), project-level, and subdirectory files all contribute at once .

```markdown
# CLAUDE.md — my enterprise-ai-harness

## Commands
- Install: `uv sync`
- Run: `uv run uvicorn app.main:app --reload`
- Lint: `uv run ruff check --fix .`
- Types: `uv run mypy app/`
- Test: `uv run pytest -x -q`

## Project structure
- `app/main.py` — FastAPI factory
- `app/agents/` — LangChain agent definitions
- `app/schemas/` — all Pydantic models
- `app/api/v1/` — route handlers, thin, no business logic

## Hard rules (NEVER violate)
- All public API inputs/outputs MUST be Pydantic models in app/schemas/
- Never `print()`; use `structlog` via `from app.logging import get_logger`
- Every endpoint returns a typed response model
- After editing Python, run ruff + mypy. Do not stop until both pass.
- uv only. Never pip/poetry/conda.
- Tests: pytest with anyio for async, factories via polyfactory

## Architecture decisions
- Agent runtime = LangChain `create_agent`, NOT raw loops
- All LLM calls go through `app/llm/gateway.py` for cost tracking
```

**Why this works:** every session starts with your conventions already in context, so you never re-explain, and the agent self-corrects before violating your rules.

## 1.4 Settings hierarchy (intermediate)

Behavior is controlled by `settings.json` at three levels (later wins): enterprise managed → user `~/.claude/settings.json` → project `.claude/settings.json` → `.claude/settings.local.json` (gitignored).

```json
{
  "permissions": {
    "allow": ["Bash(uv run pytest *)", "Bash(uv run ruff *)", "Bash(uv run mypy *)"],
    "deny":  ["Bash(rm -rf *)", "Bash(git push --force*)", "Bash(curl * | sh)"],
    "ask":   ["Bash(git commit*)", "Bash(uv add *)"]
  },
  "env": { "CLAUDE_CODE_SUBAGENT_MODEL": "sonnet" }
}
```

The `allow`/`deny`/`ask` syntax uses **tool + shell-glob patterns**. Allowing the exact commands from CLAUDE.md ("run the test suite") while denying destructive ones removes 90% of permission prompts — safely.

## 1.5 Hooks — deterministic automation (intermediate → advanced)

**Key principle: prompts request; hooks guarantee.** If something must run every time (format, typecheck, security scan), put it in a hook, because the model might skip a prompt but cannot skip a hook .

Hooks are commands in `settings.json` (or scripts in `.claude/hooks/`) that fire on lifecycle events:

| Event                | When                   | Can block?                 |
| -------------------- | ---------------------- | -------------------------- |
| `PreToolUse`         | before a tool runs     | yes — validate/block       |
| `PostToolUse`        | after a tool completes | no — format/lint           |
| `UserPromptSubmit`   | you hit enter          | yes — inject context       |
| `Stop`               | Claude says "done"     | yes — force it to continue |
| `SubagentStart/Stop` | subagent lifecycle     | yes (stop)                 |

The hook receives JSON on stdin, e.g. `{"tool_name":"Bash","tool_input":{"command":"npm test"}}` .

A Python-optimized hook config:

```json
{
  "hooks": {
    "PostToolUse": [
      { "matcher": "Edit|Write",
        "hooks": [{ "type": "command",
          "command": "uv run ruff check --fix \"$CLAUDE_FILE_PATHS\" && uv run mypy \"$CLAUDE_FILE_PATHS\"",
          "timeout": 60000 }] }
    ],
    "Stop": [
      { "hooks": [{ "type": "agent",
        "prompt": "Run `uv run pytest -x -q`. If anything fails, fix it. $ARGUMENTS",
        "timeout": 300 }] }
    ]
  }
}
```

- `type: "command"` runs a shell script.
- `type: "agent"` spawns a subagent with tools to verify real state (added in 2026) .
- `async: true` runs it in the background for notifications/logging .
- The `Stop`-hook pattern = **"don't stop until tests pass"**: the gate for unattended/overnight sessions .

## 1.6 MCP — Model Context Protocol (intermediate)

MCP connects Claude to external systems: Postgres, GitHub, Sentry, Slack, your internal services — 3,000+ integrations exist .

```bash
claude mcp add postgres -- npx -y @modelcontextprotocol/server-postgres "postgresql://localhost/mydb"
claude mcp add github    -- npx -y @modelcontextprotocol/server-github
claude mcp list
```

Scope matters: `local` (just you) < `project` (team, committed to repo) < `user` (all your projects). Enterprise note: managed settings can force-allow/deny MCP servers.

For **your harness**, the killer combo is: an MCP server exposing your harness's own tools (e.g., list deployed agents, inspect traces) + a skill documenting how to use them well .

## 1.7 Subagents — the delegation layer (advanced)

Your main conversation has one finite context window (200K standard, 1M with extended models) . Everything the agent reads eats it. The fix: **subagents** — fresh context windows that do focused work and return only a summary .

Three built-ins: **Explore** (read-only search), **Plan** (research + propose plan), **General-purpose**. Define custom ones in `.claude/agents/code-reviewer.md`:

```markdown
---
name: code-reviewer
description: Reviews diffs for API contract safety, Pydantic correctness, async bugs
tools: Read, Grep, Glob, Bash
model: sonnet
---

You are a reviewer for a FastAPI + LangChain codebase. Check:
1. Every new/modified route has a response_model and error handlers
2. No blocking I/O in async functions (no requests/time.sleep in async paths)
3. Pydantic models use Field constraints, not validators that raise bare ValueError
4. No secrets in code — all config via pydantic-settings
Return findings as a numbered list, severity first.
```

The parent agent invokes it via the Task tool; only the final summary returns. Use `CLAUDE_CODE_SUBAGENT_MODEL=sonnet` (or a cheaper tier) for exploration, reserving Opus for architecture — **model tiering** is a major cost lever .

## 1.8 Skills & plugins (advanced)

A **Skill** is a folder with `SKILL.md` (frontmatter + instructions, optional helper scripts) in `.claude/skills/` or `~/.claude/skills/`. You invoke it as `/add-endpoint`; Claude can also auto-load it when its description matches the task . Custom slash commands merged into Skills in 2026. **Plugins** package skills + hooks + agents + MCP for distribution via marketplaces.

The decision rule :

- **Skill** = expertise the agent should apply (how we add endpoints here)
- **Hook** = something that must happen no matter what (ruff after every edit)
- **Subagent** = work to hand off to a fresh context

## 1.9 Headless mode, CI & SDK (advanced)

```bash
# One-shot, non-interactive
claude -p "summarize the changes in this PR"

# Structured output for CI (JSON events stream)
claude -p --json "run the test suite, report failures"

# GitHub Actions — the agent becomes a CI step
```

There's also the **Claude Agent SDK** (Python + TypeScript) to embed the same agent loop in your own apps — very relevant since you're building an agent harness. For enterprise: Anthropic offers managed deployment, SSO, audit logs, and bedrock/vertex routing.

## 1.10 Cost & governance

Pay per token (API) or flat subscription (Pro/Max). Cost drivers: model tier, context size, subagent sprawl. Controls: `/cost` to observe, subagent model tiering, keeping CLAUDE.md tight, `/clear` between unrelated tasks. Claude Code authored ~4% of all public GitHub commits by early 2026 — roughly 135K commits/day  — so governance (permissions, hooks, audit) is a solved, documented problem.

---

# PART 2: OPENCODE

OpenCode is the open-source (MIT) terminal agent from Anomaly (formerly SST), with ~200K+ GitHub stars, 75+ model providers, and no lock-in . Kilo Code and several other agents are rebuilt on it.

## 2.1 Installation & first run

```bash
curl -fsSL https://opencode.ai/install | bash
# or: npm i -g opencode-ai   /   brew install opencode

cd your-project
opencode        # launches the TUI
```

Inside the TUI:

- `/connect` — add a provider (Anthropic key, OpenAI, OpenRouter, **OpenCode Zen** = their managed/free routing, Azure, Ollama...) 
- `/init` — generates `AGENTS.md` (OpenCode's equivalent of CLAUDE.md) and commits it to git 
- `/models` — pick your model; `Tab` toggles between **Build** (can edit everything) and **Plan** (read-only analysis) modes 
- `@` to reference files, `/undo`, `/redo`, `/share`, `/compact`, `/stats`

## 2.2 The two built-in agents: Build vs Plan

This is OpenCode's signature simplicity. Two modes:

- **Build** — full tool access (read/write/bash). For doing the work.
- **Plan** — read-only (analysis, architecture proposals). For thinking before touching.

You toggle with `Tab`. Everything else (custom agents, permissions) is an elaboration of these two. You can also assign *different models* to each — e.g., cheap model for Plan, strong model for Build.

## 2.3 Configuration files (beginner → intermediate)

OpenCode uses `opencode.json` (project) and `~/.config/opencode/opencode.json` (global), with **project overriding global** . It supports `{env:VAR}` and `{file:path}` substitution, so API keys can live in env vars or separate files .

```json
{
  "$schema": "https://opencode.ai/config.json",
  "model": "anthropic/claude-sonnet-4-5",
  "small_model": "anthropic/claude-haiku-4-5",
  "instructions": ["AGENTS.md", "./docs/architecture.md"],
  "permission": {
    "edit": "allow",
    "bash": { "*": "ask", "uv run *": "allow", "git status": "allow" },
    "webfetch": "ask"
  },
  "mcp": {
    "postgres": {
      "type": "local",
      "command": ["npx", "-y", "@modelcontextprotocol/server-postgres", "postgresql://localhost/devdb"]
    }
  }
}
```

- `model` = main model; `small_model` = cheap route for background tasks (titles, summaries, compaction) .
- Precedence of model selection: `--model` flag → config → last used .
- `enabled_providers` / `disabled_providers` restrict which providers can load .
- Organizations can publish defaults via a `.well-known/opencode` endpoint — loaded first, overridable locally (nice enterprise feature) .

## 2.4 Permissions system (intermediate)

OpenCode's permission keys are richer than Claude Code's, with **per-key, per-pattern** control:

| Key                                        | Gates                                                   |
| ------------------------------------------ | ------------------------------------------------------- |
| `read` / `edit` / `glob` / `grep` / `list` | the matching tools                                      |
| `bash`                                     | shell commands (accepts glob patterns → allow/ask/deny) |
| `external_directory`                       | anything touching files outside the worktree            |
| `webfetch` / `websearch` / `lsp` / `skill` | those capabilities                                      |
| `task`                                     | spawning subagents                                      |

Each value is `"allow" | "ask" | "deny"`, or an object of pattern → action .

```json
"permission": {
  "edit": { "app/**": "allow", "**/*.lock": "deny" },
  "bash": { "*": "ask", "uv run *": "allow", "rm *": "deny" },
  "external_directory": "deny"
}
```

Per-agent overrides let you give your "reviewer" agent `edit: deny` while "builder" gets `edit: allow` — least privilege by design.

## 2.5 Extension points: commands, skills, plugins, MCP (intermediate → advanced)

OpenCode has five extension points; choosing is a flow of *"how does it trigger?"* :

| Extension          | Lives in                            | Triggered by                        |
| ------------------ | ----------------------------------- | ----------------------------------- |
| **Custom Command** | `.opencode/commands/NAME.md`        | you type `/name`                    |
| **Custom Agent**   | `.opencode/agents/NAME.md`          | you type `/name` or model delegates |
| **Agent Skill**    | `.opencode/skills/NAME/SKILL.md`    | auto-matched by description         |
| **Plugin**         | `.opencode/plugins/NAME.js` (JS/TS) | events in OpenCode itself           |
| **MCP server**     | `opencode.json → mcp`               | model calling the tool              |

`A custom agent (compare with Claude Code's):

```markdown
---
description: Use this agent when implementing or modifying FastAPI endpoints
mode: primary
model: anthropic/claude-sonnet-4-5
temperature: 0.1
permission:
  edit: allow
  bash: { "uv run *": "allow", "*": "ask" }
---
You are a FastAPI specialist in this repo. Rules:
- Response models from app/schemas only
- structlog, never print
- After edits run `uv run ruff check --fix` and `uv run mypy app/`
- Write/update a pytest for every endpoint you touch
```

MCP config mirrors Claude Code's (local command or remote URL, `enabled` flags), and plugins (JS hooks into lifecycle events) are OpenCode's unique power: e.g., auto-format with `ruff format` after every file write, because it's code you control, not shell.

## 2.6 Providers & local models (intermediate)

The killer feature: **any provider**. Built-ins via `/connect` (Anthropic, OpenAI, Google, Azure with Entra ID, OpenRouter, Vercel AI Gateway, Cloudflare AI Gateway, Zen, Copilot OAuth...) plus custom OpenAI-compatible providers and locals:

```json
"provider": {
  "ollama": {
    "npm": "@ai-sdk/openai-compatible",
    "name": "Ollama (local)",
    "options": { "baseURL": "http://localhost:11434/v1" },
    "models": { "qwen3.5:4b": { "name": "Qwen3.5 4B" } }
  }
}
```

Same shape works for LM Studio, vLLM, LiteLLM, and corporate gateways . Model IDs are `provider_id/model_id`; per-model options like `reasoningEffort` and `thinking.budgetTokens` can be set globally and overridden per agent . `blacklist`/`whitelist` prune the `/models` picker .

## 2.7 Headless & CI (advanced)

```bash
opencode run "explain the auth flow"          # non-interactive
opencode run -m anthropic/claude-sonnet-4-5 "fix the failing tests"
opencode run --format json "..."              # structured output
opencode stats                                # token/session stats
```

There's also an OpenCode SDK (server + client libraries) for embedding the harness programmatically. `AGENTS.md` conventions + `opencode.json` + headless mode make OpenCode very CI-friendly: same config governs human and bot sessions.

---

# PART 3: ANTIGRAVITY CLI (`agy`)

Newest and most unusual of the three.

## 3.1 What it is and where it came from

Google launched Antigravity in November 2025 as its agent-first platform (an IDE with an "Editor View" and a "Manager Surface" where you dispatch agents that verify their own work with artifacts — screenshots, browser verification) . On **June 18, 2026**, Google retired Gemini CLI and pointed everyone at the **Antigravity CLI** — a single Go binary named `agy`, the only way to use Gemini models agentically from a consumer terminal account .

Key facts to know before adopting:

- **Closed source** (Gemini CLI was Apache-2.0 — that's why Qwen Code etc. were forked from it) .
- **Quota**: weekly compute-based cap (free tier / AI Pro / Ultra), replacing the old 1,000-requests/day model; heavy users report hitting the cap mid-week .
- **Model**: Gemini 3 Pro from the terminal, with multi-agent support — coordinate several agents from one session .
- Gemini Code Assist **Standard/Enterprise license orgs** were unaffected by the Gemini CLI shutdown — so enterprise Google customers kept their path .

## 3.2 Installation & everyday use

```bash
# install the single Go binary (no runtime needed)
# from Google's Antigravity download page / package manager, then:
agy          # start a session
agy --help   # inspect flags
```

Day-to-day it feels like the other two (natural-language goals, tool calls, approvals), with Google-flavored differentiators:

1. **Artifacts**: agents return screenshots, screen recordings, and task lists instead of raw logs — you *verify what the agent did* rather than reading transcripts. This is the Manager Surface philosophy in the terminal.
2. **Browser control**: agents can drive a real browser to verify what they built — uniquely valuable for your FastAPI app: "implement the endpoint, then start uvicorn and hit it with a browser/HTTP client and show me the response."
3. **Plugins**: the Gemini CLI features you may know — Agent Skills, Hooks, Subagents, Extensions — carried over, now implemented as **Antigravity plugins** . So the five universal concepts map cleanly.
4. **Multi-agent**: fan out several coordinated agents in one session, sharing a knowledge base that persists useful context between tasks .

## 3.3 When to choose it

- You're on Google AI Pro/Ultra and want frontier Gemini access free-ish in the terminal.
- You value artifact-based verification and browser-driven self-checking.
- Caveats for an enterprise: closed source, weekly quota caps, and org licensing is tied to Google Cloud Code Assist tiers — evaluate against your procurement rules.

---

# PART 4: SIDE-BY-SIDE & DECISION FRAMEWORK

| Dimension                    | Claude Code                                    | OpenCode                                                       | Antigravity CLI                                          |
| ---------------------------- | ---------------------------------------------- | -------------------------------------------------------------- | -------------------------------------------------------- |
| **Maker / License**          | Anthropic, proprietary                         | Anomaly, MIT open source                                       | Google, closed source                                    |
| **Default model**            | Opus 5.5                                       | You choose (any of 75+ providers)                              | Gemini 3 Pro                                             |
| **Provider freedom**         | Anthropic (or Bedrock/Vertex/Gateway)          | Total (BYOK, Zen, local Ollama/vLLM, gateways)                 | Google only                                              |
| **Instructions file**        | CLAUDE.md (+ nested)                           | AGENTS.md (+ global rules)                                     | Knowledge base + project context                         |
| **Safety model**             | Permissions + plan mode + hooks                | Rich per-tool/per-pattern permissions                          | Approvals + artifacts verification                       |
| **Deterministic automation** | Hooks (command/agent/async)                    | Plugins (JS) + permissions                                     | Hooks (as plugins)                                       |
| **Subagents**                | First-class (built-ins + custom, model-tiered) | Custom agents + task tool                                      | Multi-agent orchestration                                |
| **Extensibility**            | MCP, skills, plugins, Agent SDK                | MCP, skills, commands, plugins, SDK                            | Plugins (skills/hooks/subagents/extensions)              |
| **Headless/CI**              | `claude -p [--json]`, GitHub Actions           | `opencode run [--format json]`, server                         | Scriptable via binary; pairs with Jules (async PR agent) |
| **Cost**                     | Subscription or API tokens                     | Bring your own keys; free local models possible; Zen free tier | Free with weekly compute cap                             |
| **Best at**                  | Long multi-file refactors, deepest ecosystem   | Model independence, self-hosting, cost control                 | Browser-verified tasks, Gemini quality, artifacts        |

**The pragmatic enterprise answer: run two.** Claude Code (or the Agent SDK) as the primary high-quality loop, and OpenCode as the provider-flexible/self-hosted fallback and CI runner. Add Antigravity CLI where Gemini's browser verification and free tier fit. All three share the same mental model, so skills transfer.

---

# PART 5: YOUR CONCRETE SETUP — "agentic development" for the Python/uv/FastAPI/Pydantic/LangChain harness

Here's the end-to-end workflow I'd build for your project, using the concepts above.

**Step 1 — Repo hygiene first (the agent is only as good as the repo).**

```bash
uv init --lib --name enterprise-ai-harness   # or your existing layout
git init && git add -A && git commit -m "init"
```

Commit early and often — every CLI has `/undo` and diff review, and git is your safety net. Never run agents in a dirty repo.

**Step 2 — Write CLAUDE.md *and* AGENTS.md** (keep both; Claude Code reads the first, OpenCode the second — you can symlink). Include: uv commands, ruff/mypy/pytest invocation, project structure, hard rules (Pydantic everywhere, structlog, LangChain `create_agent` only, LLM calls via gateway), and architecture decisions. This one file is 50% of your agent quality.

**Step 3 — Wire the safety net.**

Claude Code (`settings.json`):

- `allow`: `Bash(uv run pytest *)`, `Bash(uv run ruff *)`, `Bash(uv run mypy *)`
- `deny`: `rm -rf`, `curl|sh`, writes outside repo, `git push --force`
- PostToolUse hook: `ruff check --fix + mypy` on Edit/Write
- Stop hook: agent-type hook running pytest until green

OpenCode (`opencode.json`):

- `bash`: `{ "*": "ask", "uv run *": "allow", "git push*": "deny" }`
- `edit`: `{ "app/**": "allow", "migrations/**": "ask" }`
- Plugin: after write, run `ruff format`

**Step 4 — Define specialist agents.** A `plan` agent (read-only, strong model, proposes design before code), a `builder` agent (edits + runs checks), a `reviewer` agent (read-only: Pydantic correctness, async discipline, no blocking I/O, LangChain usage per your gateway rule). Route reviewer to a cheaper model.

**Step 5 — Add MCP.** Postgres MCP for inspecting your harness's stores; GitHub MCP for PR flows; later, expose *your own harness's tools* as an MCP server so the coding agent can inspect your agent runtime's traces — a nice recursive touch.

**Step 6 — The daily loop.**

1. Start in **plan mode**: "Design the new endpoint for X; read app/schemas and app/agents first; propose the plan." Review, adjust, approve.
2. Switch to build. Agent implements, hooks run ruff/mypy, tests run.
3. `/compact` between unrelated tasks. `/cost` to watch spend.
4. Commit with conventional commits; the Stop hook or a `/commit` skill drafts the message.
5. Long tasks → delegate to subagents; over-night tasks → "don't stop until tests pass" Stop gate.

**Step 7 — CI integration.** Add `claude -p --json` or `opencode run --format json` steps: PR review bots, migration checks, "update the changelog" jobs — same configs, headless flags.

**Step 8 — Enterprise governance checklist:** SSO/managed settings (Claude Code), `.well-known/opencode` org defaults + `enabled_providers` allowlist (OpenCode), secrets only via `{env:}`/`{file:}` substitution never in config, per-project sandboxes/containers, pinned plugin/skill versions from tags, and an audit log of sessions (transcripts) for compliance.

---

## Your learning path (beginner → advanced)

1. **Week 1:** Claude Code only. Default permissions. `/init` a CLAUDE.md. Do 20 small tasks. Learn `/clear`, plan mode, and reading tool calls.
2. **Week 2:** Add permissions `allow` lists, then one PostToolUse hook (ruff). Write your first custom subagent. Install one MCP server (GitHub).
3. **Week 3:** Install OpenCode. Connect via API key, then try a local Ollama model. Port your conventions to AGENTS.md. Try `opencode run` headless.
4. **Week 4:** Try Antigravity CLI (`agy`) for a browser-verifiable task on your FastAPI app. Compare the three on the same task.
5. **Ongoing (advanced):** plugins, skills marketplace, Agent SDK embedding, CI bots, model tiering/cost optimization, multi-agent orchestration, and — since you're building a harness — study these three as reference architectures for your own agent loop (tool permissioning, compaction, subagent isolation are all directly portable to your LangChain design).

Want me to go deeper on any single topic next — e.g., a fully-worked Claude Code hooks + subagents setup for your exact repo layout, or a line-by-line walkthrough of OpenCode's plugin API
