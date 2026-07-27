# The Complete Vibe Coding & Agentic AI Coding Guide

> **From "what is this" to "shipping a real AI SaaS"** — a beginner-to-pro course on how professional developers actually use AI to build software in 2026.

---

## How to Read This Course

This isn't a blog post you skim. This is a structured course. Read it in order, build each piece, and you'll end up with a real AI SaaS you actually shipped.

**The project we'll build together: DocuMind AI** — a multi-tenant SaaS where users upload PDFs and chat with them. It's small enough to finish, real enough to teach you everything that matters.

**Prerequisites:**
- You can write basic Python (functions, classes, if/else, loops)
- You've used a terminal a few times
- You have a GitHub account
- That's literally it

**What you'll have by the end:**
- A working AI SaaS running in Docker
- A GitHub repo with CI/CD
- Production-grade code patterns
- A repeatable vibe coding workflow you can apply to any project

**The structure:**

| Part | Topic | Difficulty |
|------|-------|------------|
| 0 | How to read this course | 🟢 Easy |
| 1 | What is vibe coding? What is agentic AI coding? | 🟢 Easy |
| 2 | The AI coding toolkit (tools, models, picks) | 🟢 Easy |
| 3 | The mental model — how AI coding actually works | 🟡 Medium |
| 4 | The art of the prompt | 🟡 Medium |
| 5 | Project architecture for an AI SaaS | 🟡 Medium |
| 6 | Hands-on: FastAPI + PostgreSQL | 🟠 Hard |
| 7 | Hands-on: LangChain fundamentals | 🟠 Hard |
| 8 | Hands-on: RAG — the AI pattern that matters | 🟠 Hard |
| 9 | Hands-on: Production concerns (auth, rate limits, logs) | 🔥 Pro |
| 10 | Hands-on: Docker + CI/CD with GitHub Actions | 🔥 Pro |
| 11 | The vibe coding workflow in real life | 🔥 Pro |
| 12 | Advanced patterns (multi-agent, streaming, memory) | 🔥 Pro |
| 13 | Capstone: ship DocuMind AI end-to-end | 🔥 Pro |

Let's go.

---

# Part 1: What is Vibe Coding? What is Agentic AI Coding?

## 1.1 The 30-Second Version

- **Vibe coding** = you describe what you want in natural language, an AI writes the code, you review and guide it. The "vibe" is your intent, not the syntax.
- **Agentic AI coding** = the AI doesn't just suggest — it plans, executes, tests, debugs, and iterates. You're more of a tech lead than a typist.

That's it. The rest of this guide is about doing both well.

## 1.2 The History (so you understand why this matters now)

**2017-2020: Tab-complete era**
GitHub Copilot launched in 2021 but the idea was older. AI would autocomplete the next line. Nice, but small.

**2021-2023: Chat-with-your-codebase**
ChatGPT, Claude, and Copilot Chat let you ask "how does this function work?" and get real answers. Huge shift — AI became a teacher, not just a typist.

**Feb 2025: Karpathy coins "vibe coding"**
Andrej Karpathy (one of the godfathers of modern AI) tweeted about a new way he was building side projects: just describe the vibe, don't even read the diffs, trust the LLM. It went viral because it was the first time a serious AI researcher admitted to *not* carefully reading code.

**2025-2026: Agentic coding goes mainstream**
Tools like Claude Code, Cursor Agent mode, Aider, Cline, and Devin can:
- Read your whole repo
- Plan multi-step changes
- Run commands
- Run tests
- Fix their own bugs
- Open PRs

**Where we are in 2026:** if you're writing every line yourself, you're leaving 5-10x productivity on the table. Top engineers use AI the way pilots use autopilot — it doesn't replace judgment, it handles the busywork.

## 1.3 The Two Modes (and when to use each)

### Mode A: Vibe Coding (you're driving, AI is the passenger)

You stay in the loop:
- You write specs / describe what you want
- AI generates code
- You review every change
- You run the code
- You tell AI what to fix

**Use when:** you're learning, the code is risky, the requirements are fuzzy.

### Mode B: Agentic AI Coding (AI is driving, you're the tech lead)

You give high-level goals:
- "Add a /chat endpoint that uses RAG over the user's documents"
- AI plans the steps, writes the code, runs the tests, fixes its own bugs
- You review the final result

**Use when:** the task is well-defined, the code paths are clear, you trust the AI to know the patterns.

**The pro move:** use both. Vibe for architecture decisions and risky bits, agentic for boilerplate, refactors, and tests.

## 1.4 What AI Coding is NOT

Be honest about the limits so you don't get burned:

| AI is great at | AI is bad at |
|----------------|--------------|
| Boilerplate | Knowing your business rules |
| Standard patterns | Architectural decisions |
| Translating intent to syntax | Telling you "no, this is a bad idea" |
| Writing tests for existing code | Designing the test strategy |
| Refactoring | Picking the right thing to build |
| Documentation | Knowing what's actually wrong with your vague prompt |
| Common bugs | Exotic edge cases in your specific domain |

The pro move is knowing which column each task is in.

## 1.5 The Mindset Shift

Traditional coding:
> I write a line → I run it → I see if it works → I write the next line

Vibe coding:
> I describe the whole feature → AI writes 200 lines → I run it → I review the behavior → I tell AI what to fix

Agentic coding:
> I describe the goal → AI plans, codes, tests, debugs → I review the result → I ship or refine

**The unlock:** stop thinking about code. Start thinking about *behavior*. "What should this thing do?" becomes the question, not "how do I write this loop?"

---

# Part 2: The AI Coding Toolkit (2026 Edition)

## 2.1 The Tools (what's what, what to pick)

I'll keep this brutally honest about what's free, open source, and beginner-friendly — matching your preferences.

### IDEs (where you write code)

| Tool | Price | Open source? | Vibe score | Pick if... |
|------|-------|--------------|------------|-----------|
| **VSCode** | Free | ✅ Yes (Microsoft) | Medium | You want the standard, huge extension ecosystem |
| **Cursor** | Freemium (Pro = $20/mo) | ❌ No (fork of VSCode) | 🏆 Highest | You want the best AI experience out of the box |
| **Windsurf** | Freemium | ❌ No | High | You want AI-flow like Cursor but different style |
| **Zed** | Free | ✅ Yes | Medium | You want speed, Rust-based |

**My pick for you: VSCode** (free, open source, the standard, plays nice with everything below). If you later want to upgrade to Cursor, the migration is trivial — both are VSCode forks.

### AI Coding Assistants (the AI that lives in your editor)

| Tool | Free tier? | Open source? | Runs where | Best for |
|------|-----------|--------------|------------|----------|
| **GitHub Copilot** | ✅ (free for students/OSS) | ❌ No | Cloud | Tab-complete + chat |
| **Continue.dev** | ✅ Fully free | ✅ Yes | Anywhere | BYO model, total control |
| **Cline** | ✅ Fully free | ✅ Yes | VSCode | Agent mode in your editor |
| **Aider** | ✅ Fully free | ✅ Yes | Terminal | Git-aware, great for big refactors |
| **Claude Code** | ✅ (limited) | ❌ No | Terminal | Most powerful agent right now |
| **Cursor Agent** | 💰 Pro tier | ❌ No | Cloud | Best in-IDE agent |

**My pick for you: Continue.dev with Cline as backup.** Both are free, open source, and you bring your own model. No lock-in. You can switch from Gemini to Claude to a local model in 5 minutes.

### Terminal Agents (AI that lives in your shell)

| Tool | Free? | Open source? | Best for |
|------|-------|--------------|----------|
| **Claude Code** | Limited free | ❌ No | Complex multi-file changes, the king of agentic |
| **Aider** | ✅ Free | ✅ Yes | Git-aware, great commit messages |
| **OpenHands** | ✅ Free | ✅ Yes | Long-running autonomous tasks |
| **Gemini CLI** | ✅ Free | ❌ No | Google ecosystem |

**My pick for you: Aider for open-source reliability, Claude Code for serious agentic work.** Aider is Git-native (it commits as it goes) which is great for learning.

### Models (the actual AI brains)

This is where the free + open source gets tricky. The best coding models are mostly closed-source but accessible via free tiers.

| Model | Free tier? | Hosted by | Best for |
|-------|-----------|-----------|----------|
| **Gemini 2.5 Flash** | ✅ Generous | Google | Fast, cheap, great for most tasks |
| **Gemini 2.5 Pro** | ✅ Limited | Google | Harder reasoning, planning |
| **Claude Sonnet 4.5** | 💰 Paid (or via proxies) | Anthropic | Best coding model, period |
| **GPT-4o** | 💰 Paid | OpenAI | Solid all-rounder |
| **DeepSeek V3** | ✅ Cheap/free | DeepSeek | Open weights, surprisingly good |
| **Qwen Coder** | ✅ Free | Alibaba | Open weights, great for code |
| **Llama 3.3 70B** | ✅ Local (heavy) | Meta | If you have GPU |

**My pick for you: Gemini 2.5 Flash (free) as the daily driver, DeepSeek V3 (cheap) for the harder problems.** Both work through OpenRouter which keeps you vendor-agnostic.

### Model Routers (so you don't get locked in)

| Tool | What it does | Why it matters |
|------|--------------|----------------|
| **OpenRouter** | One API, 100+ models | Switch models without changing code |
| **LiteLLM** | Same idea, open source, self-hosted | Run it inside your app |

**Use OpenRouter.** It's free for many models, you pay-as-you-go, and it future-proofs your code.

## 2.2 The Stack (the layers of your AI SaaS)

| Layer | Pick | Why |
|-------|------|-----|
| Language | Python 3.12 | The AI ecosystem standard |
| Web framework | FastAPI | Async, fast, auto-docs, the de-facto choice |
| Database | PostgreSQL 16 | Reliable, free, scales to billions of rows |
| ORM | SQLAlchemy 2.0 | The Python ORM, async support |
| Migrations | Alembic | Comes with SQLAlchemy |
| Validation | Pydantic v2 | Comes with FastAPI, used everywhere |
| LLM framework | LangChain | The abstraction layer (your "no lock-in" choice) |
| Vector DB | ChromaDB | Free, open source, runs locally, fine for most |
| Auth | python-jose + passlib | JWT-based, free |
| Tasks | ARQ (or Celery) | For background jobs |
| Caching | Redis | Optional, for production |
| API testing | httpx + pytest | Standard |
| Container | Docker + Docker Compose | The standard |
| CI/CD | GitHub Actions | Free for OSS, you already use GitHub |
| Observability | Langfuse (or LangSmith) | Free tier, traces LLM calls |
| Deployment | Fly.io / Render / Railway | Free tiers, Docker-friendly |

**The "why LangChain not OpenAI SDK directly" question:**

If you write `import openai` and call `openai.chat.completions.create(...)`, you're tied to OpenAI. The day you want to switch to Claude or Gemini or a local model, you rewrite everything.

If you use LangChain, you write:
```python
llm = ChatOpenAI(model="gpt-4o")
# or
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")
# or
llm = ChatAnthropic(model="claude-sonnet-4-5")
```
The rest of your code doesn't change. That's why we use LangChain.

## 2.3 The Setup Checklist (do this before Part 3)

```bash
# 1. Python
python --version  # should be 3.11+
# If not, install via pyenv or use python.org installer

# 2. Git
git --version  # you have this

# 3. Docker
docker --version
docker compose version  # note: v2 uses `docker compose` not `docker-compose`

# 4. VSCode
# Download from code.visualstudio.com (free)

# 5. Install these VSCode extensions:
#    - Python (Microsoft)
#    - Pylance (Microsoft)
#    - Continue (Continue.dev)
#    - Docker (Microsoft)
#    - GitLens (GitKraken)

# 6. Make a GitHub account if you don't have one

# 7. Sign up for free accounts:
#    - Google AI Studio (for Gemini free tier): aistudio.google.com
#    - OpenRouter (one API for many models): openrouter.ai
```

---

# Part 3: The Mental Model — How AI Coding Actually Works

## 3.1 The Loop

Every AI coding interaction follows the same loop, whether you're using autocomplete, a chat, or a full agent:

```
   ┌────────────────────────────────────────┐
   │                                        │
   ▼                                        │
 YOU: Write a spec / prompt                 │
   │                                        │
   ▼                                        │
 AI: Generates output (code, plan, etc)     │
   │                                        │
   ▼                                        │
 YOU: Review the output                     │
   │                                        │
   ▼                                        │
 YOU: Run it / test it / read it            │
   │                                        │
   ▼                                        │
   ├──── Good? ────► Ship it                │
   │                                        │
   └──── Bad?  ────► Tell AI what's wrong   │
                       │                   │
                       └───────────────────┘
                            (loop back)
```

The mistake beginners make: they skip the "review" step. They take whatever the AI gives, paste it in, move on. That's how you get a codebase full of subtle bugs and security holes.

The mistake pros make: they over-review. They read every diff line-by-line, defeating the purpose. They forget the "vibe" — the AI can move 100x faster than them on boilerplate.

**The sweet spot:** review the *behavior* and the *architecture*, skim the *syntax*. The first time you read a function the AI wrote, focus on: does it do what I asked? The second time, focus on: is it the right approach? Don't re-read the third time unless something's wrong.

## 3.2 The Three Levels of AI Coding

### Level 1: Tab-complete (you write, AI finishes)

You're typing a function. AI suggests the next 5 lines. You hit Tab if it's right, keep typing if it's wrong.

This is the "Copilot original" mode. It's fast for boilerplate. It's slow for novel stuff because the AI only sees what you've written so far.

### Level 2: Chat (you ask, AI answers)

You open a chat panel, paste a file, ask "what does this do?" or "add error handling here." AI replies, you copy the suggestion, paste it in.

This is the "ChatGPT in your IDE" mode. Good for explaining code, refactoring, generating tests. Slow because you have to copy-paste manually.

### Level 3: Agent (you describe, AI does)

You say: "Add a /chat endpoint that uses RAG over the user's documents. It should authenticate the user, fetch their last 10 documents, embed the query, retrieve the top 5 chunks, call the LLM, and stream the response. Use LangChain. Write the tests."

The AI:
1. Reads your codebase to understand the patterns
2. Plans the changes
3. Creates new files
4. Edits existing files
5. Runs the tests
6. Fixes what fails
7. Reports back

**This is where the productivity 10x lives.** But it requires good specs (Part 4) and good tools (Part 2).

## 3.3 When to Use Which Level

| Task | Use Level |
|------|-----------|
| Typing a new function from scratch | 1 (tab-complete) |
| "What does this regex do?" | 2 (chat) |
| "Write tests for this file" | 3 (agent) |
| "Add error handling to all endpoints" | 3 (agent) |
| "Refactor this 200-line file" | 3 (agent) |
| "Why is this import failing?" | 2 (chat) |
| "Add OAuth login" | 3 (agent) |
| "Document this function" | 2 (chat) |
| "Migrate from FastAPI 0.100 to 0.110" | 3 (agent) |
| "What naming convention should we use?" | 2 (chat) — this is a design decision |

**Rule of thumb:** if the task is well-defined and standard, use an agent. If it's a design decision, use chat (and don't trust the answer — go think). If you're typing novel logic, use tab-complete because context is fresh.

## 3.4 The "Spec First" Principle

This is the most important habit you'll build. Before you ask AI to write code, you write a spec.

Bad:
> "Add a chat feature"

Good:
> "Add a POST /api/v1/chat endpoint that:
> - Requires JWT auth (use the get_current_user dependency we already have)
> - Accepts { session_id: UUID, message: str }
> - Looks up the session, returns 404 if not found or not owned by user
> - Loads the session's documents from the vector store
> - Uses LangChain's ConversationalRetrievalChain with gpt-4o-mini
> - Streams the response as Server-Sent Events
> - Saves the user message and AI response to the messages table
> - Returns appropriate error codes (401, 403, 404, 422, 500)
> - Has tests covering: happy path, wrong user, missing session, no documents
> - Add this to the existing router in app/api/v1/chat.py"

That second prompt is what gets you production-quality output. The first prompt gets you a tutorial-quality demo.

**The rule:** the more you specify, the less the AI has to guess, the less you have to fix.

---

# Part 4: The Art of the Prompt

## 4.1 Anatomy of a Good Prompt

Every good prompt to an AI coding assistant has these parts:

```markdown
# Context
What is this code for? What's the bigger picture? What's the existing pattern?

# Goal
What specifically do you want done?

# Constraints
- Tech stack (use X, not Y)
- Patterns to follow (use our existing User model, not invent a new one)
- Files to touch (only modify app/api/, don't touch migrations/)
- What to avoid (don't add new dependencies, don't use async yet)

# Acceptance criteria
How will you know it worked?
- Tests pass
- Endpoint returns X
- No new linting errors

# Examples (optional but powerful)
"Like the /users endpoint but for /documents"
```

## 4.2 The 5 Prompt Anti-Patterns

### Anti-pattern 1: The Vague Ask
> "Make the API better"

What does "better" mean? Faster? More features? More secure? The AI will guess, and you won't like its guess.

### Anti-pattern 2: The Kitchen Sink
> "Add auth, payments, webhooks, email, and an admin panel all using Stripe and SendGrid and OAuth and..."

Too much at once. AI loses focus, output quality drops. Break it into chunks.

### Anti-pattern 3: The Magic Word
> "Write production-ready, scalable, secure, well-tested, documented code"

These words mean nothing to an AI. They're not instructions, they're vibes. Replace with specifics: "Use bcrypt for password hashing, rate limit to 10 req/sec, return 401 on missing JWT, log all auth failures to /var/log/auth.log."

### Anti-pattern 4: The Tutorial Trap
> "Explain to me how to build a SaaS in Python"

The AI will write a Medium article, not code. If you want code, ask for code. If you want an explanation, ask for an explanation. Don't mix.

### Anti-pattern 5: The Single-Shot
> *paste entire 500-line file*
> "Find the bug"

The AI can't see the runtime context. It will guess. Better:
- "In the `authenticate` function in `app/services/auth.py` line 42, when the JWT is expired, we get a 500 instead of 401. Here's the traceback:..."

## 4.3 Prompt Templates That Work

### Template: New Feature

```
# Context
I'm building DocuMind AI, a FastAPI + PostgreSQL SaaS for chatting with PDFs.
The existing code has: User model, JWT auth, /api/v1/users endpoints.
PostgreSQL via SQLAlchemy 2.0 async, Alembic for migrations.

# Goal
Add a /api/v1/documents endpoint that lets users upload PDFs.

# Constraints
- Use the existing User model and auth dependency
- Store files in /uploads/{user_id}/{doc_id}.pdf (we'll move to S3 later)
- Save metadata to a new Document model (id, user_id, filename, size, uploaded_at)
- Use python-multipart for file uploads
- Don't add new top-level dependencies without asking
- Follow the same patterns as the existing /users router

# Acceptance criteria
- POST /api/v1/documents accepts a PDF, returns 201 with the document
- GET /api/v1/documents returns the user's documents
- DELETE /api/v1/documents/{id} removes the file and the metadata
- Returns 401 for unauthenticated, 404 for wrong user
- pytest tests for the happy path and the auth failure
```

### Template: Bug Fix

```
# Context
DocuMind AI, FastAPI service, LangChain for the LLM chain.

# Bug
POST /api/v1/chat returns 500 with "RecursionError: maximum recursion depth exceeded"
when the user has more than 5 documents.

# What I tried
- Checked the chain, it works for 1 document
- Looks like the chain is calling itself somehow

# Please
Look at app/services/chat.py and find why it's recursing. Suggest a fix.
Don't change the public API.
```

### Template: Refactor

```
# Context
The function `process_message` in app/services/chat.py is 200 lines and does
5 things: validate, fetch, embed, retrieve, generate.

# Goal
Refactor it into 5 single-responsibility functions without changing behavior.

# Constraints
- Keep the public signature the same
- All existing tests must pass
- No new dependencies
- Add type hints
- Heavily comment the new structure
```

### Template: "I don't know what to do"

```
I'm building [X]. I've gotten to the point where I need to [Y]. 
I see three options:
1. [option A]
2. [option B]
3. [option C]

What are the tradeoffs? What would you pick for a beginner building a
small production app, and why? Don't write code yet — just help me decide.
```

## 4.4 The "I Don't Know What I Don't Know" Move

When you're a beginner, you don't know what to ask for. The fix:

> "I'm a beginner. I'm building [X]. I know [what I know]. I don't know [what I don't know]. Ask me 5 questions to figure out what to do next, then propose a plan."

This is the most powerful prompt in your toolkit. Use it often.

## 4.5 Reading AI Output (the critical skill)

When the AI gives you code, read it in this order:

1. **Does it do what I asked?** (the behavior check, 10 seconds)
2. **Is the approach reasonable?** (the architecture check, 30 seconds)
3. **Are there obvious bugs or security issues?** (the paranoid check, 30 seconds)
4. **Is the style consistent with my codebase?** (the cleanliness check, 10 seconds)
5. **Did it invent patterns that don't exist elsewhere?** (the consistency check, 10 seconds)

If 1-3 pass, ship it. If 4-5 fail, ask the AI to fix.

If you're reading every line of every diff, you're doing it wrong. If you're reading nothing, you're doing it wrong.

**The pro move:** skim 90% of AI output, deeply read 10%. The 10% is the parts that touch security, money, or data integrity.

---

# Part 5: Project Architecture for an AI SaaS

## 5.1 The Monolith-First Principle

**Don't start with microservices.** You don't need them. You won't need them for a long time. Every YC startup advice article telling you to start with microservices is wrong for 99% of cases.

Start with a monolith. One codebase. One process. One database. When it hurts (not when you think it might hurt someday), split.

For an AI SaaS, this looks like:

```
┌─────────────────────── ONE SERVER ───────────────────────┐
│                                                          │
│  FastAPI app                                             │
│  ├── /api/v1/users      (auth, profiles)                 │
│  ├── /api/v1/documents  (upload, list, delete)           │
│  ├── /api/v1/chat       (the AI endpoint)                │
│  └── /api/v1/billing    (Stripe webhooks)                │
│                                                          │
│  Background workers (ARQ)                                │
│  ├── Process uploaded PDFs                               │
│  └── Send emails                                         │
│                                                          │
│  PostgreSQL (one DB, maybe a separate vector store)      │
│  Redis (cache + broker)                                  │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

## 5.2 The Folder Structure That Scales

Here's the layout we'll use for DocuMind AI. It works for 100 users and for 100,000:

```
documind-ai/
├── .env.example              # Template for env vars (committed)
├── .env                      # Actual env vars (NOT committed)
├── .gitignore
├── .dockerignore
├── docker-compose.yml        # Local dev: app + postgres + redis
├── Dockerfile
├── alembic.ini
├── pyproject.toml            # or requirements.txt — modern way
├── README.md
│
├── app/                      # The application code
│   ├── __init__.py
│   ├── main.py               # FastAPI app entry point
│   ├── config.py             # Settings (Pydantic Settings)
│   │
│   ├── api/                  # HTTP layer — thin, just routing
│   │   ├── __init__.py
│   │   ├── deps.py           # Shared dependencies (auth, db session)
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py     # Aggregates all v1 routers
│   │       ├── users.py
│   │       ├── documents.py
│   │       ├── chat.py
│   │       └── auth.py
│   │
│   ├── core/                 # Cross-cutting concerns
│   │   ├── __init__.py
│   │   ├── security.py       # JWT, password hashing
│   │   ├── logging.py        # Structured logging
│   │   └── exceptions.py     # Custom exception classes
│   │
│   ├── db/                   # Database layer
│   │   ├── __init__.py
│   │   ├── base.py           # SQLAlchemy Base, engine
│   │   ├── session.py        # Session factory, get_db dependency
│   │   └── models/           # SQLAlchemy models (one file per table)
│   │       ├── __init__.py
│   │       ├── user.py
│   │       ├── document.py
│   │       ├── chat_session.py
│   │       └── message.py
│   │
│   ├── schemas/              # Pydantic schemas (request/response shapes)
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── document.py
│   │   ├── chat.py
│   │   └── token.py
│   │
│   ├── services/             # Business logic — the meat
│   │   ├── __init__.py
│   │   ├── user_service.py
│   │   ├── document_service.py
│   │   ├── chat_service.py
│   │   └── llm/              # LLM-specific logic
│   │       ├── __init__.py
│   │       ├── chains.py     # LangChain chain definitions
│   │       ├── prompts.py    # Prompt templates
│   │       └── vector_store.py  # Vector DB operations
│   │
│   └── workers/              # Background jobs (ARQ)
│       ├── __init__.py
│       └── pdf_processor.py
│
├── alembic/                  # Database migrations
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│
├── tests/                    # Tests mirror the app structure
│   ├── conftest.py           # Shared fixtures
│   ├── api/
│   │   └── v1/
│   │       ├── test_users.py
│   │       ├── test_documents.py
│   │       └── test_chat.py
│   └── services/
│       └── test_chat_service.py
│
└── scripts/                  # One-off scripts
    ├── seed.py
    └── create_admin.py
```

**Why this structure works:**

| Folder | Purpose | Rule of thumb |
|--------|---------|---------------|
| `api/` | HTTP layer | Thin. Validate input, call service, return output. No logic. |
| `services/` | Business logic | Where the "thinking" lives. Testable without HTTP. |
| `db/models/` | Data shape | What tables look like. |
| `schemas/` | API contract | What JSON comes in and out. |
| `core/` | Cross-cutting | Stuff every layer needs. |
| `workers/` | Async jobs | Things that take >1 second. |

**The flow of a request:**

```
HTTP request
    ↓
app/api/v1/users.py        # router, validation, auth
    ↓
app/services/user_service.py  # business logic
    ↓
app/db/models/user.py       # SQLAlchemy model
    ↓
PostgreSQL
```

If you ever need to add a new endpoint, you go top-down: router → service → maybe a new model.

## 5.3 The "Why Not Django" Question

Django is great for content sites, admin panels, traditional CRUD. FastAPI is great for:
- Async (real async, not faked with threads)
- AI workloads (lots of I/O, streaming)
- Auto-generated API docs (Swagger UI out of the box)
- Pydantic-validated request/response
- Modern Python type hints

For an AI SaaS where you'll be calling LLMs (slow I/O), FastAPI wins.

## 5.4 The "Why Not Flask" Question

Flask is the OG. It's still great. But it's synchronous by default, and the ecosystem around AI is FastAPI-first. LangChain's docs, LlamaIndex, etc., all show FastAPI examples. Going with FastAPI means more copy-paste-friendly tutorials.

## 5.5 The Database Choice (PostgreSQL, but)

PostgreSQL is the only database you should start with. Why:
- Free, open source
- Scales from 0 to billions of rows
- JSON support (for when you need it)
- Full-text search built in
- The most popular DB on earth (yes, more than MySQL now)
- Every cloud provider offers it

For the vector store, we have two options:
- **ChromaDB** (separate, free, local, perfect for getting started)
- **pgvector** (extension inside PostgreSQL, scales with your DB)

We'll start with ChromaDB for simplicity, then show pgvector as the upgrade.

---

# Part 6: Hands-On — FastAPI + PostgreSQL Foundation

This is where we start building. Every code block below is real, runnable, and heavily commented.

## 6.1 The Project Setup

```bash
# Create the project
mkdir documind-ai && cd documind-ai

# Create a virtual environment
python -m venv .venv

# Activate it
# On macOS/Linux:
source .venv/bin/activate
# On Windows:
.venv\Scripts\activate

# Install our core dependencies (we'll add more later)
pip install fastapi uvicorn[standard] sqlalchemy[asyncio] asyncpg alembic pydantic pydantic-settings python-jose[cryptography] passlib[bcrypt] python-multipart

# Save them
pip freeze > requirements.txt
```

**What each one does (this is the "explain every tool" part):**

| Package | What it is | Why we need it |
|---------|-----------|----------------|
| `fastapi` | The web framework | Our app is a FastAPI app |
| `uvicorn` | The ASGI server | Runs the FastAPI app |
| `sqlalchemy[asyncio]` | The ORM | Talk to PostgreSQL in Python |
| `asyncpg` | Async PostgreSQL driver | SQLAlchemy needs a driver |
| `alembic` | Migration tool | Version control for your DB schema |
| `pydantic` | Validation library | Validates request/response data |
| `pydantic-settings` | Settings from env vars | Loads `.env` files |
| `python-jose` | JWT library | For authentication tokens |
| `passlib` | Password hashing | We don't store plaintext passwords, ever |
| `python-multipart` | Form/file parsing | For file uploads |

**Why these and not the alternatives?**

| We picked | Alternative | Why we picked ours |
|-----------|-------------|--------------------|
| FastAPI | Flask, Django | Async, AI-friendly, auto-docs |
| SQLAlchemy | Tortoise ORM, raw psycopg | The standard, biggest ecosystem |
| asyncpg | psycopg2 | Native async, faster |
| Alembic | None, raw SQL | We want to version our schema |
| Pydantic v2 | Marshmallow, dataclasses | FastAPI's native, fastest |
| python-jose | PyJWT | More algorithms supported |
| passlib | bcrypt directly | Cleaner API, easy to switch algorithms |

## 6.2 The Settings (config.py)

This is the file that reads your `.env` and gives typed access to all config.

```python
# app/config.py
"""
Application configuration.

Why this file exists:
- Centralizes all config in one place
- Reads from environment variables (so the same code runs locally, in Docker, in prod)
- Type-checks everything via Pydantic (so you can't accidentally pass a string where an int is needed)
- Fails fast at startup if config is wrong (better than discovering it at request time)

Pydantic Settings reads from:
1. Environment variables (highest priority)
2. .env file (loaded automatically)
3. Default values in the class (lowest priority)
"""

from functools import lru_cache  # Caches the settings so we only read .env once
from typing import Literal  # For "this string must be one of these values"

from pydantic import Field, PostgresDsn  # Pydantic helpers
from pydantic_settings import BaseSettings, SettingsConfigDict  # The base class


class Settings(BaseSettings):
    """
    All app configuration in one place.

    Every field here is a config value you can set via .env or env var.
    Example: field `database_url` is read from env var `DATABASE_URL`.
    """

    # =========================================
    # APP
    # =========================================

    # App metadata — used in OpenAPI docs, logs, etc.
    app_name: str = "DocuMind AI"
    app_version: str = "0.1.0"
    # "debug" mode enables hot-reload, shows tracebacks, etc.
    # NEVER set this to True in production.
    debug: bool = False
    # Which environment we're in
    environment: Literal["local", "staging", "production"] = "local"

    # =========================================
    # API
    # =========================================

    # Where the API will be served. Used for CORS, OAuth callbacks, etc.
    api_v1_prefix: str = "/api/v1"
    # Comma-separated list of origins allowed to call our API
    # In dev, this is the frontend dev server (e.g. http://localhost:3000)
    cors_origins: str = "http://localhost:3000"

    # =========================================
    # DATABASE
    # =========================================

    # The async PostgreSQL connection string.
    # Format: postgresql+asyncpg://user:password@host:port/dbname
    # The "+asyncpg" tells SQLAlchemy to use the asyncpg driver.
    # We'll set this in .env, with a default for local dev.
    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://documind:documind@localhost:5432/documind"
    )

    # =========================================
    # SECURITY
    # =========================================

    # Secret key for signing JWTs. MUST be a long random string in production.
    # Generate one with: openssl rand -hex 32
    secret_key: str = "change-me-in-production-please-use-openssl-rand-hex-32"
    # JWT settings
    access_token_expire_minutes: int = 60 * 24  # 1 day
    refresh_token_expire_days: int = 30  # 30 days
    # Algorithm for JWT — HS256 is fine for our use case (symmetric)
    algorithm: str = "HS256"

    # =========================================
    # LLM
    # =========================================

    # Which LLM provider to use. We use LangChain so we can switch easily.
    llm_provider: Literal["openai", "google", "anthropic", "openrouter"] = "google"
    # Default model for chat
    llm_model: str = "gemini-2.5-flash"
    # Default model for embeddings
    embedding_model: str = "text-embedding-004"
    # API key (set in .env, never committed)
    llm_api_key: str = ""
    # Max tokens per response (cap cost + latency)
    llm_max_tokens: int = 1024
    # Temperature: 0 = deterministic, 1 = creative
    llm_temperature: float = 0.2

    # =========================================
    # VECTOR STORE
    # =========================================

    # Where to persist the vector DB on disk
    vector_store_path: str = "./chroma_data"
    # Name of the collection in ChromaDB
    vector_store_collection: str = "documents"

    # =========================================
    # FILE STORAGE
    # =========================================

    # Where uploaded PDFs go
    upload_dir: str = "./uploads"
    # Max upload size in bytes (10 MB default)
    max_upload_size: int = 10 * 1024 * 1024
    # Allowed file extensions
    allowed_extensions: list[str] = [".pdf"]

    # =========================================
    # Pydantic Settings config
    # =========================================

    # This is the magic that makes Pydantic read from .env
    model_config = SettingsConfigDict(
        env_file=".env",  # Path to the env file
        env_file_encoding="utf-8",
        case_sensitive=False,  # DATABASE_URL and database_url are the same
        extra="ignore",  # Ignore unknown env vars (we don't want crashes)
    )


@lru_cache
def get_settings() -> Settings:
    """
    Returns a cached Settings instance.

    Why lru_cache:
    - Settings should be read once per process
    - Re-reading .env on every call is wasteful
    - lru_cache gives us a singleton for free

    Usage in other files:
        from app.config import get_settings
        settings = get_settings()
        print(settings.database_url)
    """
    return Settings()


# Convenience: a ready-to-use settings instance
settings = get_settings()
```

**Your `.env` file (NEVER commit this):**

```bash
# .env
# Copy from .env.example, fill in real values, never commit

# Database
DATABASE_URL=postgresql+asyncpg://documind:documind@localhost:5432/documind

# Security (generate with: openssl rand -hex 32)
SECRET_KEY=your-super-secret-key-here-change-it

# LLM (pick one provider)
LLM_PROVIDER=google
LLM_MODEL=gemini-2.5-flash
GOOGLE_API_KEY=your-google-ai-studio-key-here
# Or for OpenAI:
# LLM_PROVIDER=openai
# LLM_MODEL=gpt-4o-mini
# OPENAI_API_KEY=your-key
```

**Your `.env.example` file (this one you commit):**

```bash
# .env.example
# Copy this to .env and fill in real values

APP_NAME="DocuMind AI"
DEBUG=true
ENVIRONMENT=local

DATABASE_URL=postgresql+asyncpg://documind:documind@localhost:5432/documind

SECRET_KEY=generate-with-openssl-rand-hex-32
ACCESS_TOKEN_EXPIRE_MINUTES=1440

LLM_PROVIDER=google
LLM_MODEL=gemini-2.5-flash
EMBEDDING_MODEL=text-embedding-004
GOOGLE_API_KEY=
```

**Your `.gitignore`:**

```gitignore
# .gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
.venv/
venv/
env/
.pytest_cache/
.mypy_cache/
.ruff_cache/

# Env
.env
.env.local
.env.*.local

# IDE
.vscode/
.idea/
*.swp
*.swo

# App
uploads/
chroma_data/
*.log
logs/

# OS
.DS_Store
Thumbs.db
```

## 6.3 The Database Layer

The `db/` folder is split into 3 parts: `base.py` (the engine), `session.py` (the sessionmaker), and `models/` (the tables).

### `app/db/base.py`

```python
# app/db/base.py
"""
SQLAlchemy declarative base.

Why a separate file:
- The Base is imported by every model
- If you put it in a model file, you get circular imports
- This is the SQLAlchemy convention
"""

from sqlalchemy.orm import DeclarativeBase  # The new 2.0 way to declare models


class Base(DeclarativeBase):
    """
    The base class for all SQLAlchemy models.

    Every model in your app inherits from this. It gives you:
    - The `Mapped` type annotation system (SQLAlchemy 2.0 style)
    - The `mapped_column` for declaring columns
    - The metadata container Alembic uses for migrations
    """
    pass
```

### `app/db/session.py`

```python
# app/db/session.py
"""
Database session management.

This file creates the async engine and the session factory,
plus a FastAPI dependency that gives each request its own session.

Why async:
- FastAPI is async, so we want non-blocking DB calls
- An async engine lets us handle many concurrent requests without threads
- asyncpg is the fastest async PostgreSQL driver
"""

from typing import AsyncGenerator  # Type hint for async generators

from sqlalchemy.ext.asyncio import (
    AsyncSession,  # The async version of a SQLAlchemy session
    async_sessionmaker,  # Factory that creates sessions
    create_async_engine,  # Creates the async engine
)

from app.config import settings  # Our typed config

# =========================================
# The Engine
# =========================================

# `create_async_engine` is the entry point to the DB.
# It manages a connection pool under the hood.
engine = create_async_engine(
    str(settings.database_url),  # Convert PostgresDsn to str
    # `echo=True` logs every SQL statement. Useful in dev, NEVER in prod.
    echo=settings.debug,
    # Pool size: how many connections to keep open
    pool_size=5,
    # Max overflow: how many extra connections to allow under load
    max_overflow=10,
)


# =========================================
# The Session Factory
# =========================================

# A session is a "unit of work" — you do queries in it, then commit.
# `expire_on_commit=False` means after commit, attributes don't get
# refreshed. Faster, but you need to be careful with stale data.
AsyncSessionLocal = async_sessionmaker(
    bind=engine,  # Which engine to use
    class_=AsyncSession,  # The type of session to create
    expire_on_commit=False,  # Don't refresh objects after commit
    autoflush=False,  # Don't auto-flush before queries (we'll be explicit)
)


# =========================================
# The FastAPI Dependency
# =========================================

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields a database session.

    Usage in a route:
        @router.get("/users")
        async def list_users(db: AsyncSession = Depends(get_db)):
            ...

    What it does:
    - Creates a new session for the request
    - Yields it to the route handler
    - Ensures the session is closed after the request (even on error)
    - Rolls back if an exception happened, so partial changes don't leak
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session  # Hand the session to the route
        except Exception:
            # If anything in the route raised, undo any uncommitted changes
            await session.rollback()
            raise  # Re-raise the exception so FastAPI can handle it
        finally:
            # `async with` will close the session, but we don't need an explicit close
            pass
```

### `app/db/models/user.py`

```python
# app/db/models/user.py
"""
The User model.

This defines the `users` table in PostgreSQL.

SQLAlchemy 2.0 style:
- We use `Mapped[type]` annotations
- We use `mapped_column()` instead of `Column()`
- The new style is fully type-safe and plays well with mypy
"""

import uuid  # For UUID generation
from datetime import datetime  # For timestamps

from sqlalchemy import Boolean, DateTime, String, func  # Column types
from sqlalchemy.dialects.postgresql import UUID  # PG-specific UUID type
from sqlalchemy.orm import Mapped, mapped_column  # 2.0-style annotations

from app.db.base import Base  # Our declarative base


class User(Base):
    """
    A user of the application.

    Table: users
    Columns: id, email, hashed_password, full_name, is_active, created_at, updated_at
    """

    # `__tablename__` is the actual table name in PostgreSQL.
    # By convention, use plural snake_case.
    __tablename__ = "users"

    # =========================================
    # Columns
    # =========================================

    # Primary key. UUIDs are great because:
    # - They're not enumerable (security)
    # - They work across distributed systems
    # - They don't leak business info (like user count)
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),  # The PG UUID type, treated as Python uuid.UUID
        primary_key=True,  # This is the primary key
        default=uuid.uuid4,  # Auto-generate a new UUID
    )

    # Email — unique, indexed (for fast lookups)
    email: Mapped[str] = mapped_column(
        String(255),  # Max 255 chars (standard for emails)
        unique=True,  # No two users can have the same email
        index=True,  # Creates an index for fast lookups by email
        nullable=False,  # NOT NULL constraint
    )

    # Hashed password. NEVER store plaintext passwords.
    # We use bcrypt via passlib.
    hashed_password: Mapped[str] = mapped_column(
        String(1024),  # Bcrypt hashes are ~60 chars, but 1024 leaves room
        nullable=False,
    )

    # Optional full name
    full_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,  # Can be NULL
    )

    # Is the user active? Inactive users can't log in.
    # We don't hard-delete users (for audit trails) — just deactivate them.
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Is the user a superuser? Admins, basically.
    is_superuser: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # =========================================
    # Timestamps
    # =========================================

    # When the user was created. Set automatically by the DB on INSERT.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),  # Always use timezone-aware datetimes
        server_default=func.now(),  # DB sets it, not Python
        nullable=False,
    )

    # When the user was last updated. Set automatically on every UPDATE.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),  # On insert
        onupdate=func.now(),  # On update
        nullable=False,
    )

    # =========================================
    # String representation (for debugging)
    # =========================================

    def __repr__(self) -> str:
        """What you see when you print a User object."""
        return f"<User id={self.id} email={self.email}>"
```

**Why these choices (the "explain every choice" thing):**

| Choice | Alternative | Why this |
|--------|-------------|----------|
| UUID primary key | Auto-incrementing int | Security (no enumeration), distributed-friendly |
| `String(255)` for email | `Text` | DB can still index, limits wasted space |
| `is_active` flag | Hard delete | Soft delete = audit trail, can undo |
| `server_default=func.now()` | Python default | DB time is the source of truth (works for all clients) |
| `timezone=True` | Naive datetime | NEVER use naive datetimes in 2026. They cause bugs. |
| Bcrypt-hashed password | MD5, SHA256 | Bcrypt is slow on purpose (defeats brute force) |

### `app/db/models/__init__.py`

```python
# app/db/models/__init__.py
"""
Import all models here so Alembic can discover them.

This is the SQLAlchemy + Alembic convention:
- You import every model class
- Alembic's autogenerate sees them via Base.metadata
- Now `alembic revision --autogenerate` works
"""

# Import the Base first so models can attach to it
from app.db.base import Base

# Then import every model
from app.db.models.user import User
from app.db.models.document import Document
from app.db.models.chat_session import ChatSession
from app.db.models.message import Message

# Export them so `from app.db.models import User` works
__all__ = ["Base", "User", "Document", "ChatSession", "Message"]
```

## 6.4 The Schemas Layer

Pydantic schemas define the shape of data coming in (requests) and going out (responses). They're separate from SQLAlchemy models because:

- API shape ≠ DB shape (you might expose `full_name` but DB has `first_name` + `last_name`)
- You don't want to leak password hashes in responses
- You want input validation that's separate from ORM concerns

### `app/schemas/user.py`

```python
# app/schemas/user.py
"""
Pydantic schemas for User-related API operations.

Three schemas here:
- UserCreate: what the client sends to create a user
- UserUpdate: what the client sends to update a user
- UserResponse: what we send back to the client
- UserInDB: the full user including hashed_password (internal use only)
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# =========================================
# Base — shared fields
# =========================================

class UserBase(BaseModel):
    """
    Fields shared by all user schemas.

    Why a base class:
    - DRY (don't repeat yourself)
    - Adding a field here adds it to all child schemas
    """
    email: EmailStr  # Validates it's a real email format
    full_name: str | None = None
    is_active: bool = True
    is_superuser: bool = False


# =========================================
# Create — what we accept to create a user
# =========================================

class UserCreate(UserBase):
    """
    Schema for POST /users (or /auth/register).

    The client sends: email, password, full_name
    We never accept hashed_password from the client.
    """
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="User password, 8-128 characters",
    )


# =========================================
# Update — what we accept to update a user
# =========================================

class UserUpdate(BaseModel):
    """
    Schema for PATCH /users/{id}.

    All fields optional — the client only sends what they want to change.
    """
    email: EmailStr | None = None
    full_name: str | None = None
    password: str | None = Field(None, min_length=8, max_length=128)


# =========================================
# Response — what we return to the client
# =========================================

class UserResponse(UserBase):
    """
    Schema for responses. NEVER includes the password.

    `model_config = ConfigDict(from_attributes=True)` lets us
    create this from a SQLAlchemy User object directly.
    """
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    # This is the magic that lets Pydantic read from ORM objects
    model_config = ConfigDict(from_attributes=True)


# =========================================
# Internal — full user including sensitive fields
# =========================================

class UserInDB(UserBase):
    """
    Internal representation, includes hashed_password.
    NEVER return this from an API endpoint.
    """
    id: uuid.UUID
    hashed_password: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
```

## 6.5 The Service Layer

The service layer is where business logic lives. The API layer is thin, the service layer is fat. Why?

- **Testable:** you can unit-test services without spinning up HTTP
- **Reusable:** multiple endpoints can call the same service
- **Clean separation:** the API doesn't know about the DB, the service doesn't know about HTTP

### `app/services/user_service.py`

```python
# app/services/user_service.py
"""
User-related business logic.

This is where you put things like:
- "create a user with a hashed password"
- "authenticate against the hashed password"
- "find a user by email"

The API layer just calls these functions.
"""

import uuid

from sqlalchemy import select  # For SELECT queries
from sqlalchemy.ext.asyncio import AsyncSession  # Async DB session

from app.core.security import get_password_hash, verify_password  # Password helpers
from app.db.models.user import User
from app.schemas.user import UserCreate, UserUpdate


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    """
    Get a user by ID. Returns None if not found.
    """
    # `select(User)` builds a SELECT * FROM users
    # `.where(User.id == user_id)` adds the WHERE clause
    result = await db.execute(select(User).where(User.id == user_id))
    # `.scalar_one_or_none()` returns the User or None
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    """Get a user by email. Returns None if not found."""
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, user_in: UserCreate) -> User:
    """
    Create a new user.

    Steps:
    1. Hash the password (NEVER store plaintext)
    2. Build a User ORM object
    3. Add to session
    4. Commit (writes to DB)
    5. Refresh (gets back the DB-generated values like created_at)
    6. Return
    """
    # 1. Hash the password
    hashed_password = get_password_hash(user_in.password)

    # 2. Build the User. Note: we use user_in.dict() to convert the Pydantic
    #    schema to a dict, then unpack it. We exclude `password` and add
    #    `hashed_password` instead.
    db_user = User(
        email=user_in.email,
        full_name=user_in.full_name,
        hashed_password=hashed_password,
        is_active=True,
        is_superuser=False,
    )

    # 3. Add to session (not yet written)
    db.add(db_user)

    # 4. Commit (writes to DB)
    await db.commit()

    # 5. Refresh (gets DB defaults like created_at, updated_at)
    await db.refresh(db_user)

    # 6. Return
    return db_user


async def authenticate(
    db: AsyncSession, email: str, password: str
) -> User | None:
    """
    Authenticate a user by email and password.

    Returns the User if credentials are valid, None otherwise.

    Why None for invalid creds (not an exception):
    - Exceptions are for unexpected errors
    - "Wrong password" is an expected outcome, not an error
    - The API layer will turn None into a 401
    """
    # 1. Look up the user
    user = await get_user_by_email(db, email)
    if not user:
        return None  # No user with that email

    # 2. Check password
    if not verify_password(password, user.hashed_password):
        return None  # Wrong password

    # 3. Check if user is active
    if not user.is_active:
        return None  # User is deactivated

    return user
```

### `app/core/security.py`

```python
# app/core/security.py
"""
Security helpers: password hashing, JWT tokens.

We use:
- passlib + bcrypt for password hashing (slow on purpose, defeats brute force)
- python-jose for JWT (JSON Web Tokens, the standard for stateless auth)
"""

from datetime import datetime, timedelta, timezone  # For token expiry

from jose import JWTError, jwt  # JWT encoding/decoding
from passlib.context import CryptContext  # Password hashing

from app.config import settings  # Our config (for SECRET_KEY, etc.)


# =========================================
# Password Hashing
# =========================================

# CryptContext manages the hashing algorithm.
# `deprecated="auto"` means if we change schemes, old hashes are auto-upgraded.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    """
    Hash a plaintext password.

    Use this when CREATING or UPDATING a user's password.
    NEVER store the plaintext.
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Check if a plaintext password matches a hashed one.

    Use this when the user logs in.
    Returns True if it matches, False otherwise.
    """
    return pwd_context.verify(plain_password, hashed_password)


# =========================================
# JWT Tokens
# =========================================

def create_access_token(subject: str | int, expires_delta: timedelta | None = None) -> str:
    """
    Create a JWT access token.

    Args:
        subject: who this token is for (usually the user ID)
        expires_delta: how long until it expires (default: from settings)

    Returns:
        The encoded JWT string

    The token looks like: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOi...
    It's three base64-encoded parts: header, payload, signature.
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.access_token_expire_minutes
        )

    # The "payload" is the data we encode in the token.
    # Keep it small — the token is sent with every request.
    to_encode = {"exp": expire, "sub": str(subject)}

    # Encode: header.payload.signature
    encoded_jwt = jwt.encode(
        to_encode,
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    return encoded_jwt


def decode_access_token(token: str) -> dict | None:
    """
    Decode a JWT and return the payload, or None if invalid.

    Use this to verify a token sent by a client.
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
        return payload
    except JWTError:
        # Token is invalid (bad signature, expired, malformed, etc.)
        return None
```

## 6.6 The API Layer

The API layer is thin. It validates input, calls the service, returns output.

### `app/api/deps.py`

```python
# app/api/deps.py
"""
Shared FastAPI dependencies.

Dependencies are functions that run before your route handler.
You use them for things like:
- Getting the DB session
- Authenticating the user
- Checking permissions

This is FastAPI's superpower — it makes these things clean and testable.
"""

import uuid

from fastapi import Depends, HTTPException, status  # FastAPI helpers
from fastapi.security import OAuth2PasswordBearer  # Bearer token auth
from sqlalchemy.ext.asyncio import AsyncSession  # Async DB session

from app.config import settings  # For the token URL
from app.core.security import decode_access_token  # JWT decoder
from app.db.models.user import User
from app.db.session import get_db
from app.services import user_service  # Our service layer


# This tells FastAPI:
# - We use OAuth2 with bearer tokens
# - The token is obtained at the /api/v1/auth/login endpoint
# - FastAPI will use this in the OpenAPI docs to show the auth flow
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.api_v1_prefix}/auth/login"
)


async def get_current_user(
    db: AsyncSession = Depends(get_db),  # Inject the DB session
    token: str = Depends(oauth2_scheme),  # Extract the bearer token
) -> User:
    """
    Get the currently authenticated user.

    Use as a dependency on any route that requires auth:
        @router.get("/me")
        async def read_me(user: User = Depends(get_current_user)):
            return user

    Raises 401 if the token is missing, invalid, or expired.
    Raises 401 if the user no longer exists or is inactive.
    """
    # Define a "credentials exception" we can reuse
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 1. Decode the JWT
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    # 2. Extract the user ID (we put it in "sub" when we created the token)
    user_id_str: str | None = payload.get("sub")
    if user_id_str is None:
        raise credentials_exception

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise credentials_exception

    # 3. Look up the user
    user = await user_service.get_user_by_id(db, user_id)
    if user is None:
        raise credentials_exception  # User was deleted

    # 4. Check if active
    if not user.is_active:
        raise credentials_exception  # User was deactivated

    return user


async def get_current_active_superuser(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Like get_current_user, but also requires is_superuser=True.
    Use for admin-only endpoints.
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough privileges",
        )
    return current_user
```

### `app/api/v1/auth.py`

```python
# app/api/v1/auth.py
"""
Authentication endpoints: register, login, refresh.

The /token endpoint is special: FastAPI's OAuth2PasswordBearer
points to it, so the OpenAPI docs link to it.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import create_access_token
from app.schemas.token import Token
from app.schemas.user import UserCreate, UserResponse
from app.services import user_service

# A router groups related endpoints. We'll mount this on the main app.
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """
    Register a new user.

    - If the email already exists, returns 400.
    - Otherwise creates the user and returns it (without the password).
    """
    # 1. Check if email is already taken
    existing_user = await user_service.get_user_by_email(db, user_in.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists",
        )

    # 2. Create the user (service handles password hashing)
    user = await user_service.create_user(db, user_in)

    # 3. Return the user (Pydantic will exclude hashed_password)
    return UserResponse.model_validate(user)


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Token:
    """
    Log in and get an access token.

    - Uses OAuth2PasswordRequestForm, which expects form data:
        username (we use email here)
        password
    - Returns a JWT access token.
    """
    # 1. Authenticate
    user = await user_service.authenticate(
        db, email=form_data.username, password=form_data.password
    )
    if not user:
        # Same error for "user not found" and "wrong password" — don't leak which
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. Create the access token
    access_token = create_access_token(subject=str(user.id))

    # 3. Return it
    return Token(access_token=access_token, token_type="bearer")
```

### `app/api/v1/users.py`

```python
# app/api/v1/users.py
"""
User endpoints: get me, update me, list users (admin), delete user (admin).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_superuser, get_current_user, get_db
from app.db.models.user import User
from app.schemas.user import UserResponse, UserUpdate
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def read_my_profile(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """
    Get the currently logged-in user.

    This is the easiest way to test auth — log in, then call /me.
    """
    return UserResponse.model_validate(current_user)


@router.patch("/me", response_model=UserResponse)
async def update_my_profile(
    user_in: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """
    Update the currently logged-in user's profile.

    Only the fields you send are updated (partial update).
    """
    # `user_in.model_dump(exclude_unset=True)` gives us only the fields
    # the client actually sent, ignoring defaults.
    update_data = user_in.model_dump(exclude_unset=True)

    # If they're updating the password, hash it
    if "password" in update_data:
        from app.core.security import get_password_hash
        update_data["hashed_password"] = get_password_hash(update_data.pop("password"))

    # Update the user object
    for field, value in update_data.items():
        setattr(current_user, field, value)

    # Commit
    await db.commit()
    await db.refresh(current_user)

    return UserResponse.model_validate(current_user)


@router.get("/", response_model=list[UserResponse])
async def list_users(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_db),
) -> list[UserResponse]:
    """
    List all users. Admin only.
    """
    users = await user_service.list_users(db, skip=skip, limit=limit)
    return [UserResponse.model_validate(u) for u in users]
```

### `app/main.py`

```python
# app/main.py
"""
The FastAPI application entry point.

This file:
- Creates the FastAPI app instance
- Configures middleware (CORS, logging, etc.)
- Mounts the API routers
- Defines a health check endpoint
- Sets up startup/shutdown events
"""

from contextlib import asynccontextmanager  # For the lifespan context manager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware  # For CORS

from app.api.v1.router import api_router
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs at startup and shutdown.

    Use this for:
    - Startup: connect to DB, warm caches, check dependencies
    - Shutdown: close connections gracefully
    """
    # Startup logic here
    print(f"🚀 {settings.app_name} v{settings.app_version} starting up")
    print(f"📝 Environment: {settings.environment}")
    print(f"🤖 LLM: {settings.llm_provider}/{settings.llm_model}")

    yield  # The app runs here

    # Shutdown logic here
    print(f"👋 {settings.app_name} shutting down")


# Create the FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,  # Use the lifespan context manager above
    # OpenAPI tags group endpoints in the docs
    openapi_tags=[
        {"name": "auth", "description": "Authentication operations"},
        {"name": "users", "description": "User operations"},
        {"name": "documents", "description": "Document operations"},
        {"name": "chat", "description": "Chat operations"},
    ],
)


# =========================================
# Middleware
# =========================================

# CORS — who can call our API from a browser
# In production, set this to your actual frontend domain
origins = settings.cors_origins.split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Which origins can call us
    allow_credentials=True,  # Allow cookies
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)


# =========================================
# Routes
# =========================================

@app.get("/health", tags=["health"])
async def health_check() -> dict:
    """
    Health check endpoint.

    Use this for:
    - Load balancers to check if the service is alive
    - Uptime monitoring services
    - Docker health checks
    """
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
    }


# Mount the v1 API router
app.include_router(api_router, prefix=settings.api_v1_prefix)
```

### `app/api/v1/router.py`

```python
# app/api/v1/router.py
"""
Aggregates all v1 routers.

This is the pattern: one file that imports all the v1 routers
and exposes them as a single router that main.py can mount.
"""

from fastapi import APIRouter

from app.api.v1 import auth, chat, documents, users

# Create the v1 router
api_router = APIRouter()

# Mount each module's router
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(documents.router)
api_router.include_router(chat.router)
```

## 6.7 Run It and See It Work

```bash
# 1. Start PostgreSQL with Docker
docker run -d --name documind-db \
  -e POSTGRES_USER=documind \
  -e POSTGRES_PASSWORD=documind \
  -e POSTGRES_DB=documind \
  -p 5432:5432 \
  -v documind-data:/var/lib/postgresql/data \
  postgres:16

# 2. Run the FastAPI app
uvicorn app.main:app --reload

# 3. Open your browser
# Swagger UI: http://localhost:8000/docs
# ReDoc:      http://localhost:8000/redoc
```

You should see a beautiful auto-generated API doc. Click around. Try `/health`. Then in another terminal:

```bash
# Register a user
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"[email protected]","password":"super-secret","full_name":"Test User"}'

# Log in (saves token)
TOKEN=$(curl -X POST http://localhost:8000/api/v1/auth/login \
  -d "username=[email protected]&password=super-secret" \
  | jq -r .access_token)

# Get my profile
curl http://localhost:8000/api/v1/users/me \
  -H "Authorization: Bearer $TOKEN"
```

If that works, congratulations — you have a working auth system.

---

(Continued in the next file due to size — this is already ~12K words. Let me continue in separate chapter files for the remaining parts.)
