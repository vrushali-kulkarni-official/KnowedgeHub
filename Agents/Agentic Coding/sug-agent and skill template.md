Both are plain Markdown files with a YAML frontmatter block up top and instructions in the body below it. Here's the breakdown of each.

## Subagent file (`.claude/agents/*.md`)

**Structure:** two blocks — YAML frontmatter between `---` fences, then a Markdown body that becomes the subagent's system prompt.

```markdown
---
name: code-reviewer
description: Reviews code for quality and best practices
tools: Read, Glob, Grep
model: sonnet
---

You are a code reviewer. When invoked, analyze the code and provide
specific, actionable feedback on quality, security, and best practices.
```

**Frontmatter fields** — only `name` and `description` are required; the rest are optional:

| Field | Purpose |
|---|---|
| `name` | Unique id (lowercase + hyphens), used to invoke it |
| `description` | Tells Claude when to delegate to this subagent |
| `tools` | Allowlist of tools it can use (omit = inherits all) |
| `disallowedTools` | Denylist, removed from inherited/specified tools |
| `model` | `sonnet`/`opus`/`haiku`/`fable`/full model ID/`inherit` |
| `permissionMode` | `default`, `acceptEdits`, `auto`, `dontAsk`, `bypassPermissions`, `plan`, `manual` |
| `maxTurns` | Cap on agentic turns |
| `skills` | Skills to preload fully into its context at startup |
| `mcpServers` | MCP servers scoped to just this subagent |
| `hooks` | Lifecycle hooks (`PreToolUse`, `PostToolUse`, `Stop`) scoped to it |
| `memory` | `user`/`project`/`local` — persistent memory directory |
| `background` | Keep it backgrounded even if Claude wants it foreground |
| `effort` | `low`/`medium`/`high`/`xhigh`/`max` |
| `isolation` | `worktree` — run in an isolated git worktree |
| `color` | Display color in transcript/task list |
| `initialPrompt` | Auto-submitted first turn when it's the main session agent |

**Body:** plain Markdown instructions — the subagent's system prompt verbatim, no templating.

**File locations** (by scope/priority): managed settings → `--agents` CLI flag → `.claude/agents/` (project) → `~/.claude/agents/` (user) → plugin `agents/` directory.

---

## Skill file (`SKILL.md`)

**Structure:** same two-part shape — YAML frontmatter, then Markdown instructions (plus optionally a folder of supporting files).

```markdown
---
name: my-skill
description: What this skill does
disable-model-invocation: true
allowed-tools: Read Grep
---

Your skill instructions here...
```

**Frontmatter fields** — all optional, though `description` is strongly recommended:

| Field | Purpose |
|---|---|
| `name` | Display name (defaults to directory name) |
| `description` | What it does / when to use it — drives auto-invocation |
| `when_to_use` | Extra trigger phrases, appended to description |
| `argument-hint` | Autocomplete hint, e.g. `[issue-number]` |
| `arguments` | Named positional args for `$name` substitution |
| `disable-model-invocation` | Only user can invoke (`/name`), not Claude |
| `user-invocable` | `false` = only Claude can invoke, hidden from `/` menu |
| `allowed-tools` | Tools pre-approved for the invoking turn |
| `disallowed-tools` | Tools removed while skill is active |
| `model` | Model override for that turn |
| `effort` | Effort level override |
| `context` | `fork` = run in a forked subagent |
| `agent` | Which subagent type to use with `context: fork` |
| `background` | With `context: fork`, background vs. wait for result |
| `hooks` | Hooks registered while the skill is active |
| `paths` | Glob patterns limiting auto-activation to matching files |
| `shell` | `bash` (default) or `powershell` for injected commands |
| `metadata` | Free-form YAML map for your own tooling |
| `license` | Agent Skills spec field (informational) |
| `compatibility` | Agent Skills spec field (informational) |

**Body:** Markdown instructions Claude follows when the skill runs — can include dynamic context injection (`` !`command` `` runs shell and inlines output) and string substitutions (`$ARGUMENTS`, `$0`/`$1`, `${CLAUDE_SESSION_ID}`, `${CLAUDE_SKILL_DIR}`, etc.).

**Optional supporting files** alongside `SKILL.md` in the same folder:
```
my-skill/
├── SKILL.md        (required)
├── reference.md    (loaded on demand)
├── examples.md     (loaded on demand)
└── scripts/
    └── helper.py   (executed, not loaded into context)
```

**File locations**: enterprise (managed settings) → personal `~/.claude/skills/<name>/SKILL.md` → project `.claude/skills/<name>/SKILL.md` → plugin `<plugin>/skills/<name>/SKILL.md`.

---

**Key difference in scope:** a *skill* is portable content that loads into your current conversation (per the Agent Skills open standard, works across tools); a *subagent* spawns an isolated Claude instance with its own fresh context window, tools, and permissions. `context: fork` in a skill and `skills:` in a subagent are two ways to bridge between them.
