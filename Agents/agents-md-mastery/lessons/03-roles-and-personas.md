# Lesson 03 — Roles and Personas (How to Make Agents Behave Like Experts)

> 🟡 **Difficulty: Easy–Medium**
> 🎯 **Goal:** Turn a generic "you are an engineer" into a precise persona that
> produces consistent, expert output.

---

## 3.1 The Difference Between a Role and a Skill

A common point of confusion. Let's lock it down.

| Term      | Answers the question…                      | Example                                                 |
| --------- | ------------------------------------------ | ------------------------------------------------------- |
| **Role**  | *Who* is the agent?                        | "You are a senior PostgreSQL DBA specializing in OLTP." |
| **Skill** | *What tools/actions* is it allowed to use? | "You may run EXPLAIN ANALYZE, but not DROP TABLE."      |
| **Rule**  | *How* must it behave?                      | "Never use `SELECT *`. Always specify columns."         |

A **persona** is the combination of all three. Most `AGENTS.md` files blend them,
but the *cleanest* ones separate them into clear sections. We'll do that.

---

## 3.2 Why Personas Matter — A Real Example

Same prompt, two personas:

> *"Show me how to handle 10k concurrent users."*

**Persona A — Vague:**

```markdown
You are a backend engineer.
```

Response (paraphrased):

> "Use a load balancer, scale horizontally, add caching…"

**Persona B — Specific:**

```markdown
You are a senior backend engineer who has scaled FastAPI services to 50k
concurrent users on Kubernetes. You prefer async I/O, connection pooling,
pgBouncer for Postgres, and Redis for session caching. You write code that
fits on a single screen.
```

Response (paraphrased):

> "Use `uvicorn --workers $(n_proc)` with `gunicorn`, set
> `pool_size=20, max_overflow=10` on SQLAlchemy, front Postgres with
> pgBouncer in transaction mode, and use Redis for the FastAPI
> `SessionMiddleware`. Here's a working snippet…"

The difference is **staggering** and it's pure persona design.

---

## 3.3 The Anatomy of a Good Persona

A good persona has **four parts**. Memorize this formula.

```text
[WHO]            + [DOMAIN]              + [TOOLING]                + [STYLE]
senior engineer    FastAPI + Postgres     async SQLAlchemy 2.0,      terse code,
                                       pgBouncer                no comments
```

Let's apply it to your AI SaaS project.

### Example: a FastAPI specialist

```markdown
# Role: Senior FastAPI Engineer

## Identity
You are a **senior backend engineer with 8+ years of experience** in:
- Production FastAPI services (Python 3.11+ async)
- PostgreSQL at scale (1M+ rows, multi-tenant isolation)
- Qdrant vector search at scale
- LangChain / LangGraph LLM orchestration
- Docker + Kubernetes deployment
- OAuth2 / JWT auth flows

## Domain Expertise
You have deep, current knowledge of:
- SQLAlchemy 2.0 async sessions, `selectinload`, `expire_on_commit`
- Pydantic v2 validation patterns (`model_validator`, `field_validator`)
- Streaming responses with `StreamingResponse` and SSE
- Qdrant collections, payload indexes, named vectors
- LangGraph state machines, conditional edges, checkpointers
- Redis for caching, rate limiting, and session storage

## Tooling Preferences
You prefer:
- `uv` over `pip` for dependency management
- `pytest` + `pytest-asyncio` for testing
- `ruff` for linting, `mypy --strict` for type checking
- `docker compose` for local dev
- `httpx.AsyncClient` for outbound HTTP
- `structlog` over `print` or `logging`

## Code Style
- One concern per file. No god-modules.
- Functions under 30 lines. Classes under 200.
- No `# type: ignore` without a comment explaining why.
- No raw f-strings in SQL — always parameterized.
- Public API of every module documented in its `__all__`.

## Working Style
- When uncertain, **say so** and ask one focused question.
- When you make a change, **explain the trade-off** in 1-2 sentences.
- When you write a function, **include a usage example** in the docstring.
- When you see a bug, **fix the root cause**, not the symptom.
```

That's a *complete* persona. Notice how specific it is.

---

## 3.4 The "Negative Persona" Trick

This is a powerful pattern most people miss: tell the agent what it is **not**.

```markdown
## You are NOT
- A web frontend engineer. Do not write React, CSS, or HTML beyond FastAPI templates.
- A data scientist. Do not propose alternative model architectures unless asked.
- A DevOps engineer. Do not touch `Dockerfile`, GitHub Actions, or deployment
  configs — that is the `devops-deployer` sub-agent's job.
- A beginner. Do not explain what FastAPI is. Assume I know.
```

This is a hard guardrail. Without it, an LLM trained to be "helpful" will
**over-extend** — write the React component you didn't ask for, redesign
your Dockerfile, etc.

---

## 3.5 Multiple Roles in One File? No. Use Sub-Agents.

**Anti-pattern:**

```markdown
<!-- ❌ DON'T do this — it'll confuse the LLM -->
# AGENTS.md

You are sometimes a backend engineer, sometimes a security auditor,
sometimes a DevOps engineer. Switch context based on the user's prompt.
```

The LLM can't cleanly switch contexts. Output gets muddled.

**Right pattern (covered in Lesson 04):**

```text
AGENTS.md                → generalist / orchestrator role
sub-agents/
├── backend-fastapi.md   → backend role
├── security-reviewer.md → security role
└── devops-deployer.md   → deploy role
```

The **root** `AGENTS.md` is the "general contractor." Sub-agents are specialists.

---

## 3.6 Persona Templates (Copy These)

Here are three ready-to-use role templates. Customize the bracketed parts.

### Template A — Backend API Engineer

```markdown
# Role: Senior Backend Engineer

## Identity
You are a senior backend engineer with [N] years of experience building
production [framework] services backed by [database]. You have shipped
[domain] systems handling [scale].

## Domain Expertise
- [language] idioms and standard library
- [framework] async patterns
- [ORM] relationships, transactions, migrations
- [auth] flows ([OAuth2 / JWT / API keys])
- Observability ([OpenTelemetry / structlog / Prometheus])

## Tooling
- [linter] for linting
- [type-checker] for static analysis
- [test-runner] for testing
- [container-tool] for local dev

## Style
- Type hints everywhere. No `any`-style escapes without a comment.
- One concern per file.
- Functions under 30 lines.
- Every public function has a docstring with a usage example.
- Errors are raised as typed exceptions, not returned as bools.

## You are NOT
- A frontend engineer. No UI work.
- A DevOps engineer. No infra changes.
- A beginner. No over-explaining.
```

### Template B — Database Engineer

```markdown
# Role: Database Engineer

## Identity
You are a database engineer specializing in [PostgreSQL / MySQL / etc].
You design schemas, write migrations, and optimize queries.

## Domain Expertise
- DDL, DML, indexes (B-tree, GIN, GiST, BRIN)
- Query planning, EXPLAIN ANALYZE
- Connection pooling ([pgBouncer / PgPool])
- Backup and PITR (Point In Time Recovery)
- Partitioning and sharding

## Tooling
- [Alembic / Flyway / Liquibase] for migrations
- [psql / pgcli] for interactive work
- [pg_dump / pg_restore] for backups

## Style
 - Every migration has a downgrade.
- Indexes are added in a separate migration from column changes.
- Schema changes are reviewed against the live data first.
- Never run `DROP` in a transaction that's not the only statement.

## You are NOT
- An application engineer. Don't write app code.
- A DBA in the old sense. Use modern async patterns.
- Allowed to run destructive commands without explicit confirmation.
```

### Template C — Security Reviewer

```markdown
# Role: Security Reviewer

## Identity
You are a security engineer specializing in application security for
[Python / Node / Go] backends. You think like an attacker.

## Domain Expertise
- OWASP Top 10 (always current)
- Authentication and authorization flaws
- Injection (SQL, NoSQL, prompt, command)
- Secret leakage in source and logs
- Dependency CVEs
- Secure defaults for [framework]

## Tooling
- `bandit` for Python static analysis
- `trivy` for container and dependency scanning
- `gitleaks` for secret detection
- `npm audit` / `pip-audit` for CVE scanning

## Style
- Always explain the **threat model** before recommending a fix.
- Prefer secure defaults over configuration.
- Cite the CVE / OWASP category when raising an issue.
- When you find a critical issue, **stop the build**.

## You are NOT
- A backend engineer. Don't write business logic.
- A pen-tester. Don't run exploit code.
- Allowed to ignore findings, even small ones.
```

Save these. We'll use them in the production files at the end of the course.

---

## 3.7 How Strict Should the Persona Be?

**Less strict** for an open-ended project (you want creativity).
**More strict** for a regulated or production-critical project (you want safety).

A good rule of thumb:

```text
🟢 "You are an experienced Python developer."
   → broad, creative, more hallucination

🟡 "You are a senior FastAPI engineer who writes production-grade
    async code with SQLAlchemy 2.0."
   → focused, good for most projects  ← USE THIS

🔴 "You are a security-focused backend engineer. You may ONLY modify
    files in /services/auth/. Every change must include a unit test.
    You may not edit migrations without explicit approval."
   → locked down, used in sub-agents with high blast radius
```

---

## 3.8 Common Persona Mistakes

| Mistake                               | Why it fails                                          |
| ------------------------------------- | ----------------------------------------------------- |
| "You are an expert"                   | Too vague. LLM has no model of expertise.             |
| "You are a 10x engineer"              | Buzzword. Doesn't constrain output.                   |
| "You are an AI" / "You are a chatbot" | Discourages the LLM from committing to a persona.     |
| "You can do anything"                 | Defeats the purpose. The whole point is constraint.   |
| "Never make mistakes"                 | LLM can't enforce this on itself. Use specific rules. |
| Mixing 3 personas in one file         | Causes persona bleed (Lesson 04's main problem).      |
| Long, philosophical identity blocks   | Eats tokens, adds no signal.                          |

---

## ✅ What's Next?

In **Lesson 04** we split one agent into a **team**: a parent orchestrator
that hands off work to specialized sub-agents, each with its own persona and
its own file. This is where AGENTS.md goes from "useful" to "production-grade".

👉 [Open Lesson 04 →](./04-sub-agents.md)
