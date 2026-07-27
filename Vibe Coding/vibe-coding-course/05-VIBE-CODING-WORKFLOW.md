# Part 11: The Vibe Coding Workflow in Real Life

> **Continue from:** `04-DOCKER-CICD.md`
>
> **In this part:** the meta-skill — how to actually use AI to ship code, day-to-day. This is what separates the pros from the people who tried Copilot for a week and quit.

---

## 11.1 The Setup (do this once)

### Your Editor (VSCode)

**Essential extensions:**

| Extension | Why |
|-----------|-----|
| Python (Microsoft) | Python language support |
| Pylance (Microsoft) | Type checking, autocomplete |
| Continue (Continue.dev) | Free open-source AI assistant |
| Cline | Free open-source agent mode |
| GitLens | Git superpowers |
| Docker | Manage containers from VSCode |
| Even Better TOML | pyproject.toml support |
| Error Lens | Inline error display |
| Indent Rainbow | Visual indent guides |

### The AI Assistant (Continue)

```json
// .continue/config.json
{
  "models": [
    {
      "title": "Gemini Flash",
      "provider": "gemini",
      "model": "gemini-2.5-flash",
      "apiKey": "${env:GOOGLE_API_KEY}"
    },
    {
      "title": "DeepSeek V3",
      "provider": "openai",
      "model": "deepseek/deepseek-chat",
      "apiKey": "${env:OPENROUTER_API_KEY}",
      "apiBase": "https://openrouter.ai/api/v1"
    }
  ],
  "tabAutocompleteModel": {
    "title": "Gemini Flash",
    "provider": "gemini",
    "model": "gemini-2.5-flash"
  },
  "systemPrompts": [
    {
      "title": "DocuMind AI Project Context",
      "content": "We're building DocuMind AI, a FastAPI + PostgreSQL + LangChain SaaS. Python 3.12, async everywhere, SQLAlchemy 2.0, Pydantic v2, ChromaDB for vectors. We use the service layer pattern: API layer is thin, business logic in services/. Always suggest production-ready code with type hints, docstrings, and error handling. When suggesting code, follow the existing patterns in the codebase."
    }
  ]
}
```

The `systemPrompts` is the killer feature — it primes the AI with your project's context. The AI now knows your stack, your patterns, your style.

### Your Shell Setup

```bash
# Add to your ~/.bashrc or ~/.zshrc
alias py="python"
alias pip="python -m pip"
alias dc="docker compose"
alias lint="ruff check . && ruff format --check ."
alias fmt="ruff check . --fix && ruff format ."
alias test="pytest -v"
alias cov="pytest --cov=app --cov-report=term-missing"

# Git aliases
alias gs="git status"
alias gp="git push"
alias gpl="git pull"
alias gc="git commit"
alias gaa="git add -A"
alias gb="git branch"
alias gco="git checkout"
```

## 11.2 The Daily Workflow (how a pro uses AI)

### The 5-Step Loop

```
1. UNDERSTAND     — Read the issue / think about the task
       ↓
2. SPEC          — Write down what you want, in detail
       ↓
3. GENERATE      — Ask AI to write it
       ↓
4. REVIEW        — Skim, run, test
       ↓
5. ITERATE       — Fix what AI got wrong
       ↓
   (commit, push, repeat)
```

Let's walk through each.

### Step 1: UNDERSTAND

Before you touch anything, answer these in your head (or in writing):

- What behavior do I want to add/change?
- What does "done" look like?
- What are the edge cases?
- What could go wrong?
- How will I test it?

**Time budget: 2-5 minutes.** Most devs skip this and waste hours later.

### Step 2: SPEC

Write the spec before asking AI. Use the templates from Part 4. The more specific, the better.

**The 30-second spec (for small changes):**

> "In app/api/v1/chat.py, add a max_tokens query param to the chat endpoint. Default to settings.llm_max_tokens. Validate it's between 1 and 4096. Update the service to pass it to the LLM."

**The 5-minute spec (for new features):**

```markdown
# Feature: Streaming chat responses

## Why
Right now, users wait 5-10 seconds for the whole response. We want
them to see tokens appear in real-time, like ChatGPT.

## What
- Add a new endpoint: POST /api/v1/chat/stream
- Same auth as /chat (requires JWT)
- Same request body
- Returns Server-Sent Events with the chunks
- Each event is "data: {token}\n\n"
- Final event is "data: [DONE]\n\n"
- Saves the full message to the DB after streaming completes

## Acceptance criteria
- [ ] Endpoint returns 200 with text/event-stream content type
- [ ] Tokens appear in <500ms from request
- [ ] Full message is saved to the messages table
- [ ] Errors are returned as SSE events with type "error"
- [ ] Has tests for: happy path, no documents, LLM error
- [ ] Doesn't break the existing /chat endpoint

## Out of scope
- Cancel button in the UI
- Multiple parallel streams
```

### Step 3: GENERATE

Pick the right tool for the job (Part 3):

| Spec complexity | Tool | Prompt |
|----------------|------|--------|
| Tiny (1-2 lines) | Tab-complete | Just start typing |
| Small (function, file) | Chat | Paste spec into chat |
| Medium (feature, refactor) | Agent | "Implement the spec above" |
| Large (architectural) | Multiple sessions | Break into smaller specs |

**Example agent prompt:**

```
Read the spec in docs/features/streaming-chat.md and implement it.

Constraints:
- Follow the existing patterns in app/api/v1/chat.py
- Use LangChain's astream() for streaming
- Add tests in tests/api/v1/test_chat.py
- Don't break the existing /chat endpoint
- Update the OpenAPI description to mention streaming

Report back with:
- Files changed
- Any decisions you made
- Any specs that were unclear
```

### Step 4: REVIEW (the 90/10 rule)

When the AI finishes, review like this:

**Skim 90% (fast):**
- Read the diff. Does it do what you asked?
- Does the file structure make sense?
- Are the tests covering the right cases?
- Does it match existing patterns in the codebase?

**Deep-read 10% (slow):**
- Any new function that touches auth, security, or money
- Any SQL query (does it use indexes? is it safe from injection?)
- Any error handling (does it fail gracefully?)
- Any new dependency (do you really need it?)

**Run the code:**
```bash
# Lint
ruff check . && ruff format --check .

# Type check
mypy app

# Tests
pytest -v

# Manual smoke test
docker compose up -d
curl http://localhost:8000/health
```

If something is wrong, go to step 5. If everything is right, commit and push.

### Step 5: ITERATE

Tell the AI what's wrong. Be specific.

**Vague feedback (bad):**
> "This doesn't work, fix it"

**Specific feedback (good):**
> "The endpoint returns 200 but the SSE format is wrong. I'm seeing 'data: token' instead of 'data: token\n\n'. Look at the FastAPI docs for StreamingResponse and fix the format. Also, the connection closes after the first chunk — looks like the generator isn't yielding properly."

**When to take over manually:**

If the AI is going in circles on the same bug, take over. After 3 failed attempts, you have enough context to fix it yourself. Commit your fix with a comment explaining what was wrong.

## 11.3 The Commit Workflow (AI-generated commit messages)

```bash
# Stage your changes
git add -A

# AI-generate the commit message
# Option 1: Use a CLI tool
aider --commit  # if you use aider

# Option 2: Use a pre-commit hook
# .git/hooks/prepare-commit-msg
#!/bin/sh
# Calls an LLM to generate a commit message from the diff
```

Or just use Continue's chat in VSCode:
> "Look at my staged diff. Write a commit message in the conventional commits format."

**Conventional commit format:**

```
feat: add streaming chat endpoint
fix: handle expired tokens in chat service
docs: update README with deployment instructions
refactor: extract prompt templates to separate file
test: add coverage for document upload edge cases
chore: bump langchain to 0.3.0
```

## 11.4 Working with an Agent (the right expectations)

When you give an agent a task, here's the realistic flow:

**What the agent is good at:**
- Multi-file refactors
- Writing tests for existing code
- Migrating from one library version to another
- Adding CRUD endpoints
- Writing boilerplate

**What the agent is bad at:**
- Designing the API (decide this first)
- Picking the right approach (decide this first)
- Knowing your business rules (write them in the spec)
- Debugging weird runtime issues (give it the full error)

**How to make the agent more effective:**

1. **Give it access to your code** (it reads files, you don't paste them)
2. **Tell it where the relevant files are** ("look at app/api/v1/users.py for the pattern")
3. **Tell it where to write new code** ("add to app/api/v1/chat.py, don't create a new file")
4. **Tell it what NOT to do** ("don't add new dependencies", "don't modify the schema")
5. **Run it in a clean git state** (so you can `git diff` what it did)

**The most important rule:** review every change the agent makes. Don't trust, verify. It's a brilliant junior dev, not a senior who knows your codebase.

## 11.5 The Daily Routine (a real workday)

Here's what a real "AI-first" engineer's day looks like:

```
9:00  — Standup (or planning). Look at the issue tracker. Pick 2-3 things.
9:30  — Spec out the first task. 10-15 minutes. Use a doc.
9:45  — Open the AI agent, paste the spec. Go get coffee. (10-15 min)
10:00 — Review the agent's work. Run tests. Skim the diff.
10:15 — Send feedback. Iterate. (10-15 min)
10:30 — Commit, push, open PR. Move to next task.
10:45 — Repeat.

12:00 — Lunch.

13:00 — PR review. Look at others' code. (Yes, even in AI-first world, you review humans)
14:00 — Spec out the harder task. The one that needs thought.
14:30 — Use the AI to research. "What are the tradeoffs of X vs Y?" "Find me the docs for Z."
15:00 — Build the hard part. Sometimes you write the code yourself. Sometimes you pair-program with AI.
16:00 — Tests. Documentation. Cleanup.
17:00 — Wrap up. Plan tomorrow.

The key: AI does the busywork, you do the thinking.
```

## 11.6 The "I'm Stuck" Toolkit

When you're stuck, here's the AI-first rescue plan:

### Problem: I don't know what to build
> "I have a Python FastAPI app. I want to add a feature that [helps users do X]. What are 5 ways I could implement this? What are the tradeoffs? What would you recommend for a beginner?"

### Problem: I have a vague error
> "I'm getting this error: [paste full error]. Here's the relevant code: [paste]. The app should do [X] but instead does [Y]. What could be wrong?"

### Problem: My code is too complex
> "Refactor this function. It's 200 lines and does 5 things. Split it into single-responsibility functions. Keep the public signature the same. All existing tests must pass."

### Problem: I want to learn a concept
> "I'm a beginner. Explain [concept] to me. Use a real-world analogy. Then show me a code example in Python. Then give me a small exercise to try."

### Problem: My tests are flaky
> "These tests are flaky: [paste]. They pass sometimes, fail sometimes. Look at the test setup. What's likely to be the cause? Suggest fixes."

### Problem: I want to know if this is a good idea
> "I'm thinking of [doing X]. Pros: [list]. Cons: [list]. Is this a good idea for a small production SaaS? What am I missing?"

## 11.7 The "I Don't Trust the AI" Patterns

Sometimes the AI is confidently wrong. Watch for these:

| Pattern | What it looks like | What to do |
|---------|--------------------|-----------| 
| **Hallucinated APIs** | "Use `db.fetch_all(sql)`" — function doesn't exist | Check the actual library docs |
| **Outdated info** | Code for FastAPI 0.95 when you're on 0.110 | Check the version, update if needed |
| **Over-engineered** | 500 lines for a 50-line problem | Ask "what's the simplest version?" |
| **Made-up package** | `pip install fast-ai-saas` — doesn't exist | Always verify packages exist |
| **Security holes** | No auth check, SQL injection, etc. | Have a security checklist |
| **Silent assumptions** | "Assuming the user is admin..." — weren't told that | Read every comment in the code |

**The rule:** if you can't tell whether the AI is right, you don't know enough to use the code. Go learn the concept first, then come back.

## 11.8 The Collaboration Playbook (when you have teammates)

When working with humans + AI:

1. **Specs are shared.** Write the spec in a doc, share it in the PR.
2. **PRs include the prompt.** "I asked the AI to..." in the description.
3. **AI is a tool, not a teammate.** Don't blame the AI; you wrote the spec, you own the code.
4. **Code review still matters.** Reviewers should ask "would I have written it this way?" not "did you write it?"
5. **Pair on hard stuff.** Two humans + one AI > one human + one AI.

## 11.9 The Time-Saving Habits (the small stuff)

1. **Use snippets/templates for prompts.** Don't rewrite the same spec structure every time.
2. **Have a personal "patterns" file.** The things you find yourself re-explaining to the AI.
3. **Set up a good `.gitignore` once.** Then never commit junk again.
4. **Use a Makefile for common commands.** See below.
5. **Tag your Docker images.** `myapp:dev`, `myapp:v1.2.3`, `myapp:sha-abc123`. Helps debugging.

```makefile
# Makefile
.PHONY: help install test lint fmt run up down logs migrate

help:
	@echo "Available commands:"
	@echo "  install    Install dependencies"
	@echo "  test       Run tests"
	@echo "  lint       Run linters"
	@echo "  fmt        Auto-format code"
	@echo "  run        Run the app locally"
	@echo "  up         Start Docker Compose"
	@echo "  down       Stop Docker Compose"
	@echo "  logs       Show Docker logs"
	@echo "  migrate    Run DB migrations"

install:
	pip install -r requirements.txt

test:
	pytest -v --cov=app --cov-report=term-missing

lint:
	ruff check . && ruff format --check . && mypy app

fmt:
	ruff check . --fix && ruff format .

run:
	uvicorn app.main:app --reload

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

migrate:
	docker compose exec app alembic upgrade head

migrate-new:
	docker compose exec app alembic revision --autogenerate -m "$(name)"
```

## 11.10 The "I'm a Pro Now" Checklist

You know you've made it when:

- [ ] You write specs before asking the AI to code
- [ ] You can tell at a glance whether AI output is good or bad
- [ ] You have a personal config that makes the AI feel like a junior dev who knows your codebase
- [ ] You can ship a feature in 30 minutes that would've taken 2 days before
- [ ] You use AI for the busywork, but think for the architecture
- [ ] You review every change the AI makes, but you don't read every line
- [ ] You can recover from a bad AI output in 5 minutes
- [ ] Your PRs have specs, AI transcripts, and tests
- [ ] You have a Makefile, good .gitignore, and CI that catches your mistakes
- [ ] You feel like the AI is your co-pilot, not your boss

## 11.11 Quick Recap

In this part you learned:
- The 5-step loop (understand → spec → generate → review → iterate)
- How to set up your editor for AI-first development
- The realistic daily workflow
- How to use an agent effectively
- How to rescue yourself when stuck
- The patterns to watch out for (AI confidently wrong)

In Part 12 we cover advanced patterns — multi-agent systems, memory, streaming, and the things that make AI apps feel like magic.

---
