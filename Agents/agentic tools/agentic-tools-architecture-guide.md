# The Anatomy of Agentic Coding Tools

## A complete guide to the files, folders, and architecture shared by every harness, CLI, and IDE

You already spotted the two most important primitives — **skills** and **agents**. Those sit inside a bigger, surprisingly consistent skeleton. Nearly every agentic coding tool (Claude Code, Gemini CLI, Cursor, Antigravity, Codex, Windsurf, Cline, and the harnesses built on top of raw LLM APIs) is assembled from the same ~8 building blocks. Vendors give them different filenames, but the *concepts* are identical because they're all solving the same problem: **how do you give a stateless LLM persistent memory, tools, boundaries, and delegation — using nothing but files on disk?**

This guide walks through every category in detail, then shows you the runtime flow that ties them together, then gives you a cross-tool naming map so you can transfer knowledge instantly between tools.

---

## Part 1 — The Big Picture

An LLM by itself has **no memory, no hands, and no judgment about what it's allowed to touch**. Every agentic tool bolts three things onto the raw model:

1. **Memory** — text files injected into context so the agent "remembers" your project, your preferences, and how to do recurring tasks.
2. **Hands** — tools (file read/write, shell/bash, browser, MCP servers) the model can call, plus a loop that lets it call them repeatedly.
3. **Governance** — permission/settings files, hooks, and sandboxing that constrain what those hands are allowed to do without asking you.

Every file/folder below is an implementation of one of those three things. Once you see it this way, a brand-new tool stops being a mystery — you just ask "where does *this* tool put its memory files, its tool-permission file, and its delegation folder?"

---

## Part 2 — The Core File/Folder Categories

### 1. Instruction / Memory files — "the README written for an agent, not a human"

**What they are:** A single Markdown file (or small set of them) that the agent loads into context automatically, every session, without you asking. This is the most important file in the whole system because it's the only one that's *always* present.

**The universal one — `AGENTS.md`:** This has become an actual open standard, not just a convention. It started as a joint effort from OpenAI, Google, Cursor, Sourcegraph, and Factory, and by late 2025 it was donated to the Linux Foundation's Agentic AI Foundation. As of mid-2026 it's <cite index="7-1">natively read by more than twenty tools and used in over 60,000 repositories</cite>. You put it at your repo root, and it typically contains build commands, test commands, directory layout, and code-style conventions — think of it as <cite index="1-1">a README written for agents rather than humans</cite>.

Key behavior worth knowing: <cite index="9-1">precedence runs from a special AGENTS.override.md file, down to the closest AGENTS.md to the file being edited, then parent directories, then a global user-level file</cite> — so you can nest more specific `AGENTS.md` files inside subfolders of a monorepo and the closest one wins. <cite index="2-1">OpenAI's own Codex monorepo, for example, ships 88 nested AGENTS.md files, one per package</cite>.

**Tool-specific variants (same idea, different filename):**

- **`CLAUDE.md`** — Claude Code's own memory file. <cite index="5-1">Claude Code doesn't read AGENTS.md natively — it uses CLAUDE.md instead</cite>, though people commonly symlink the two so both tools see the same content.
- **`GEMINI.md`** — Gemini CLI's equivalent.
- **`.cursorrules`** (legacy, single flat file) or **`.cursor/rules/*.mdc`** (current) — Cursor's version, discussed in detail below.
- **`.github/copilot-instructions.md`** — GitHub Copilot's version. Interestingly, Copilot reads *both* this file and a root `AGENTS.md` and merges them, giving Copilot-specific instructions priority on conflicts.
- **`.clinerules`** — Cline's version.

**Why so many names for one idea:** the ecosystem is converging on `AGENTS.md` as the neutral format precisely because this fragmentation was painful. A widely-used trick is to write one canonical file and symlink the rest:

```bash
mv CLAUDE.md AGENTS.md && ln -s AGENTS.md CLAUDE.md
mv .cursorrules AGENTS.md && ln -s AGENTS.md .cursorrules
```

**Cursor's system deserves its own note**, because it's the most granular of the bunch. It has evolved through three formats:

1. `.cursorrules` — legacy, one flat file, always loaded in full for every request (a "token tax"), and as of recent Cursor versions it's **silently ignored in Agent mode**.
2. `.cursor/rules/*.mdc` — the current standard. Each `.mdc` file is Markdown with YAML frontmatter (`description`, `globs`, `alwaysApply`) and has <cite index="34-1">four activation modes</cite> — always-on, auto-attached to matching file globs, agent-requested by description, or fully manual. This means a rule about React components doesn't load its tokens into context when you're editing a SQL migration.
3. Global **User Rules** in Cursor's settings apply across every project regardless of repo.

Precedence when multiple rule sources conflict: <cite index="32-1">Team Rules (highest) > Project Rules (.cursor/rules/) > User Rules (Cursor Settings)</cite>, and when several rules match simultaneously, all of them get included in context together.

**What to put in these files, and what not to:** commands (build/test/lint), directory structure, naming conventions, architectural decisions, "don't touch this folder" warnings. What *not* to do: auto-generate them with a script and let them balloon — bloated, kitchen-sink instruction files are one of the most common performance killers in every tool that uses them, because <cite index="4-1">the effectiveness of an agent depends not just on the base model but on how precisely guidelines are defined, stored, and retrieved</cite>.

---

### 2. Skills — "a procedure the agent can pull into context on demand"

You already know the concept, but here's the precise mental model: a Skill is **not** always-loaded like `AGENTS.md`. It's a folder containing a `SKILL.md` file (plus optional helper scripts/assets) that sits dormant until the agent's current task matches its description — <cite index="15-1">Claude Code reads the folder name and description on every session, and only pulls in the full body when the current task matches</cite>. This is a critical distinction: `AGENTS.md` is a *tax on every request*; skills are a *library the agent browses and checks out one book from*.

Why this matters architecturally: it lets you accumulate dozens of specialized procedures ("how we do database migrations," "how we write a new API endpoint," "how we generate a PDF report") without bloating every single conversation with all of them. Only the matching one gets pulled in.

This is exactly the pattern you're reading right now — the `SKILL.md` files listed in my own `<available_skills>` are Claude's version of this, applied to document generation, PDF handling, spreadsheets, etc.

---

### 3. Subagents — "delegating to a fresh, isolated agent"

**What they are:** Markdown files (usually in `.claude/agents/` for Claude Code, or an equivalent folder in other tools) with YAML frontmatter defining a *separate* assistant — its own system prompt, its own restricted tool list, sometimes even its own model tier.

**Why they exist — the core insight:** context is a shared, finite, and expensive resource. If your main agent does a deep exploratory search through 40 files to find one bug, all 40 files' worth of noise stays in the *main* conversation forever, crowding out the actual work. A subagent runs that exploration in a **clean, separate context window** and returns only a summary. <cite index="16-1">The delegation layer spawns subagents with clean contexts, does focused work, and returns summaries — the exploration results don't bloat the main conversation, only the conclusions return</cite>. You can even route subagents to a cheaper/faster model for grunt work while reserving your best model for the main thread.

**Skill vs. subagent — the actual decision rule:** <cite index="11-1">use a subagent when a side task like deep search, a log analysis pass, or a dependency audit would clutter your main conversation with intermediate results you won't reference again; use a skill when you want the procedure to play out inside the main thread so you can see and steer each step</cite>. Skill = visible and steerable. Subagent = isolated and delegated.

**Scope:** subagents can live at the project level (`.claude/agents/`, shared with your team via git) or the user level (`~/.claude/agents/`, applies to everything you personally work on).

---

### 4. Hooks — "guaranteed side effects, not model behavior"

**What they are:** Deterministic scripts or HTTP calls wired to fire on specific lifecycle events — before a tool runs, after a file edit, when the session starts, when the agent is about to stop. Unlike everything above (which is *advice* the model reads and may or may not follow), hooks are **code that runs no matter what the model decides**.

<cite index="11-1">There are several types of hooks — command, HTTP, mcp_tool, prompt, and agent — and all of them are deterministically triggered.</cite> Typical real-world examples: <cite index="15-1">PreToolUse blocking writes outside the repo, PostToolUse running prettier after every file edit, an on-Stop hook running the full test suite, or a redact-secrets check on every shell command</cite>.

**The mental model that makes this click:** rules/`AGENTS.md`/skills are *persuasion* — you're hoping the model reads and follows them. Hooks are *enforcement* — the side effect happens whether the model "wants to" or not. If something absolutely must happen every time (formatting, secret-scanning, blocking a dangerous `rm -rf`), that belongs in a hook, not a markdown instruction.

---

### 5. MCP server configuration — "giving the agent new hands"

**What MCP is:** Model Context Protocol, an open standard (originally from Anthropic, now widely adopted) for connecting an agent to *external* tools and data — databases, GitHub, Slack, browsers, your company's internal APIs — over a standard JSON-RPC interface, instead of every tool vendor writing bespoke one-off integrations.

**The file:** almost universally a JSON file with a top-level `mcpServers` object, where each entry is either:

- a **stdio server** — a local process the tool launches itself, defined by `command` / `args` / `env` (e.g., `npx some-mcp-server`), or
- a **remote/HTTP server** — just a `url` and optional `headers` for auth.

<cite index="20-1">The JSON format is identical across Claude Desktop, Claude Code, and Cursor</cite> — <cite index="27-1">Cursor and Claude Code speak the same protocol, so server packages are interchangeable</cite> and you can usually copy-paste the same config block between tools. What differs between tools is only **where the file lives** and **the exact root key name**:

| Tool                     | Typical config location                                                                                                                                                                                                                                                  |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Claude Desktop           | `claude_desktop_config.json`                                                                                                                                                                                                                                             |
| Claude Code              | `.mcp.json` (project-scoped) and `~/.claude/settings.json` / `~/.claude.json` (personal, global)                                                                                                                                                                         |
| Cursor                   | `.cursor/mcp.json` (project) or `~/.cursor/mcp.json` (global)                                                                                                                                                                                                            |
| Gemini CLI / Antigravity | `~/.gemini/settings.json`, and for Antigravity specifically a separate <cite index="24-1">shared config at ~/.gemini/config/mcp_config.json</cite> — note the docs flag these as related but *not* the same file, so always double check the exact path for your version |

A useful architectural split many teams use in Claude Code: <cite index="26-1">put personal, cross-project tools like Gmail/Slack/Calendar in the global `~/.claude/settings.json`, and put project-specific dev tools like a database client or Sentry connector in the repo-local `.mcp.json`</cite>.

**Why this matters for your learning:** MCP is the layer that turns "a chatbot that talks about code" into "an agent that can actually query your Postgres database, open a GitHub PR, or click through a real webpage." Skills and `AGENTS.md` shape *how* the agent thinks; MCP determines *what it can literally touch*.

---

### 6. Settings & permissions — "the governance layer"

**What it is:** usually `settings.json` (Claude Code) or an equivalent, and it's the single most safety-relevant file in the whole stack because it defines exactly which tools/commands the agent may run **without asking you**, which it must always ask about, and which are outright forbidden.

<cite index="13-1">The settings.json file controls what the agent is and isn't allowed to do — tool permissions, hook configurations, project-level settings</cite>. The evaluation order is important and consistent across tools that implement this pattern: <cite index="13-1">deny rules are checked first, then ask, then allow — a deny rule always wins even if a matching allow rule also exists</cite>, and <cite index="13-1">if a command isn't explicitly listed in either allow or deny, the agent asks before proceeding — a deliberate middle ground so you don't have to anticipate every possible command upfront</cite>.

This file also typically holds a **deny-list for file visibility** — <cite index="18-1">a permissions.deny setting that makes files matching certain patterns (API keys, secrets, .env files) completely invisible to the agent, preventing any accidental exposure</cite>. This is different from a hook that *blocks an action* — this makes the file not even readable in the first place.

There's usually a **local override file** too (e.g. `settings.local.json`) meant to be gitignored — personal permission tweaks that shouldn't be forced on your whole team.

---

### 7. Slash commands — "saved prompts with a shortcut"

A folder of small Markdown files (e.g. `.claude/commands/`) where each file becomes a typed shortcut — `commands/review.md` becomes `/review`. The body of the file is literally the prompt that gets sent when you type the command. This is the simplest primitive in the whole system: no frontmatter logic, no isolation, no enforcement — just "save me from retyping this long prompt every time."

---

### 8. Plugins — "bundling all of the above for distribution"

A plugin packages skills, subagents, hooks, commands, and settings together so a whole team (or the open-source community) can install one thing and get a complete, opinionated setup rather than assembling seven files by hand. In Claude Code these are managed by a plugin manifest and installed via `/plugin install`; you generally don't hand-edit these files.

---

### 9. Session/state files — "the agent's short-term memory across a run"

Things like Claude Code's `~/.claude.json`, transcript/history files, and checkpoint state. These aren't instructions you write — they're the tool's own bookkeeping of what happened in past sessions (auth tokens, recent conversation state, installed-plugin registry). <cite index="12-1">You shouldn't delete the core ones (like `~/.claude.json`, `~/.claude/settings.json`, or the plugins folder) since they hold your auth, preferences, and installed plugins</cite> — but auxiliary per-session history is generally safe to wipe if you want a clean slate; the tool rebuilds it.

---

### 10. Secrets / environment files

`.env`, credential stores, and similar — not agent-specific, just the ordinary mechanism by which any program (agentic or not) gets API keys and tokens without hardcoding them. The reason this belongs in this list at all is #6 above: every serious harness treats `.env` as something that should be on the **deny list** by default, since an agent that can read your environment file can potentially leak a credential into a chat log or a committed file.

---

## Part 3 — The Runtime Flow: how it all fires, in order

This is the part that actually explains "architecture." Here's what happens, roughly, from the moment you launch a session to the moment the agent finishes a task — this sequence is consistent across Claude Code, Gemini CLI, Cursor Agent mode, and custom harnesses:

```
1. STARTUP
   ├─ Tool locates its config directory (.claude/, .cursor/, ~/.gemini/, etc.)
   ├─ Loads always-on memory: AGENTS.md / CLAUDE.md / always-apply rules
   ├─ Loads settings.json → builds the permission table (allow/ask/deny)
   ├─ Registers MCP servers listed in mcp.json → discovers their tools
   ├─ Indexes available Skills (names + descriptions only, not full bodies)
   ├─ Indexes available Subagents and Slash Commands
   └─ Fires any SessionStart hooks

2. YOU SEND A PROMPT
   └─ Prompt + always-on memory + tool list all become the model's context

3. THE AGENTIC LOOP (repeats until the task is done)
   ├─ Model reasons about what to do next
   ├─ Model may pull a Skill into context if the task matches one
   ├─ Model requests a tool call (file edit, bash command, MCP tool, or
   │  "delegate this to a Subagent")
   ├─ PreToolUse hooks fire → can block/modify the call deterministically
   ├─ Permission check against settings.json → allow silently / ask you /
   │  deny outright
   ├─ Tool executes (locally, or via MCP to an external server)
   ├─ PostToolUse hooks fire (e.g. auto-format the file just written)
   ├─ Result is appended to context
   └─ Loop continues — model decides whether it's done or needs another step

4. SUBAGENT DELEGATION (a nested version of step 3)
   └─ Spawns with its own clean context, its own restricted tool list,
      possibly a cheaper model. Runs its own loop internally. Returns
      only a final summary to the parent, not its full transcript.

5. STOP
   └─ Stop hooks may fire (e.g., "run the test suite before finishing")
```

The single most important thing to internalize: **almost every file in Parts 1–2 exists to answer one of three questions the raw model can't answer on its own** — *"What do I already know about this project?" (memory files, skills), "What am I physically able to do?" (MCP, tools), and "What am I allowed to do without asking?" (settings, hooks).* Once you can categorize a new file into one of those three buckets, you understand it, regardless of which vendor invented it.

---

## Part 4 — Cross-tool naming map

| Concept                   | Claude Code                                        | Cursor                                           | Gemini CLI / Antigravity                                      | Open standard                                 |
| ------------------------- | -------------------------------------------------- | ------------------------------------------------ | ------------------------------------------------------------- | --------------------------------------------- |
| Always-on memory          | `CLAUDE.md`                                        | `.cursor/rules/*.mdc` (or legacy `.cursorrules`) | `GEMINI.md`                                                   | `AGENTS.md`                                   |
| On-demand procedures      | `.claude/skills/*/SKILL.md`                        | — (less formalized)                              | —                                                             | `SKILL.md` pattern spreading via plugins      |
| Delegated isolated agent  | `.claude/agents/*.md`                              | —                                                | —                                                             | "subagent" pattern, name varies               |
| Deterministic automation  | `settings.json` → `hooks` key, or `.claude/hooks/` | —                                                | —                                                             | "hooks" concept, name varies                  |
| External tool connections | `.mcp.json`, `~/.claude/settings.json`             | `.cursor/mcp.json`                               | `~/.gemini/settings.json`, `~/.gemini/config/mcp_config.json` | MCP (`mcpServers` JSON) — genuinely universal |
| Permission/governance     | `settings.json` (+ `settings.local.json`)          | Settings UI                                      | `settings.json`                                               | varies                                        |
| Saved prompt shortcuts    | `.claude/commands/*.md`                            | —                                                | —                                                             | varies                                        |

The row that matters most if you're jumping between tools: **MCP really is universal** — <cite index="25-1">you install one server and just register it in each client's config file; the server binary itself is identical, only the registration location changes</cite>. Everything else above it (memory, skills, subagents, hooks) is converging toward shared standards but isn't fully there yet — which is exactly why tools like `AGENTS.md` and community projects like `ruler` (which compiles one canonical rules file out to every tool's proprietary format) exist.

---

## Part 5 — How to actually use this to learn *any* new tool

When you open a brand-new agent harness you've never used, ask these five questions in order:

1. **Where's its memory file?** (Look for `AGENTS.md` support first — most modern tools read it.)
2. **Where does it look for MCP servers?** This is your fastest path to giving it real capabilities.
3. **Does it have a permissions/settings file, and what's the default (ask-first, or allow-by-default)?** Know this before you let it run `rm` or `git push`.
4. **Does it support delegation (subagents) or is everything one flat conversation?** This tells you whether long tasks will blow out your context window.
5. **Does it support hooks, or is everything just "hope the model follows the instructions"?** This tells you how much you can actually *enforce* versus merely *suggest*.

Answer those five for OpenClaw, Hermes, Antigravity, or anything else you pick up next, and you'll have 90% of what you need to be productive in it within an hour.
