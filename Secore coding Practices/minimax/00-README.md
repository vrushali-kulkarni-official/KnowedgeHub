# The Complete Secure Coding Guide
### A beginner-friendly, exhaustive course for Python + FastAPI + PostgreSQL developers

> Read the files in order. Each one builds on the previous. By the end, you'll be able to read a FastAPI codebase, spot vulnerabilities, write exploit code to *prove* the vulnerability exists, fix it, and prevent it from coming back with the right tools.

---

## 📚 How to read this course

| File | What it covers | Read when |
|------|----------------|-----------|
| `00-README.md` | This file — the syllabus | First |
| `01-foundations.md` | CIA triad, threat modeling, core security principles | Before any code |
| `02-owasp-2021.md` | The current OWASP Top 10 (2021), each with attack + fix + tool | After foundations |
| `03-owasp-history.md` | OWASP Top 10 from 2003, 2004, 2007, 2010, 2013, 2017 — what changed and why it matters | After 02 |
| `04-beyond-owasp.md` | Vulnerabilities that don't fit neatly in the Top 10 (race conditions, IDOR, CSRF, deserialization, etc.) | After 03 |
| `05-fastapi-progression.md` | The same Todo app, rewritten 7 times — each version more secure than the last | After 04 |
| `06-postgres-security.md` | Postgres-specific attacks: SQLi patterns, RLS, roles, pg_hba, leaks | After 05 |
| `07-ai-vibe-coding.md` | How to use AI coding assistants safely, prompt-injection in your own code, AI supply chain | After 06 |
| `08-tools-and-checklist.md` | Bandit, Semgrep, pip-audit, Trivy, Snyk, OWASP ZAP + a final pre-deploy checklist | Last |

---

## 🧭 The learning promise

For every vulnerability, this course will answer five questions in the same order:

1. **What is it?** — Plain-English explanation with a real-world analogy.
2. **Why does it happen?** — The root cause in code or architecture.
3. **How is it attacked?** — A working exploit, often in `curl` or Python, that you can run against a vulnerable app.
4. **How do you fix it?** — The patched code with a Pydantic/FastAPI/Postgres idiom.
5. **What stops it automatically?** — The linter, library, or runtime guard that would have caught it.

---

## 🛠️ Tech stack assumed

- **Language:** Python 3.11+
- **Framework:** FastAPI 0.110+
- **DB:** PostgreSQL 15+
- **ORM:** SQLAlchemy 2.x (async) — used selectively; raw SQL shown for teaching
- **Validation:** Pydantic v2
- **Auth:** python-jose, passlib[argon2]
- **Container:** Docker (for the lab exercises)
- **OS:** Linux/macOS (the `curl` examples are POSIX; Windows users: use WSL2)

If you don't have these installed, that's fine for the theory parts. For the practical parts, the easiest path is:

```bash
python -m venv .venv && source .venv/bin/activate
pip install fastapi uvicorn[standard] sqlalchemy[asyncio] asyncpg pydantic[email] 'passlib[argon2]' python-jose[cryptography] python-multipart
```

---

## 🧪 The "attacker's mindset"

A quick note before we start. To defend a system, you have to be able to *break* it. Every exploit in this guide is one you can run locally against a vulnerable app you wrote yourself. **Never** run these exploits against systems you don't own — that's illegal in essentially every jurisdiction. We'll set up a deliberately-vulnerable app called `vulntodo` and attack only that.

> "To know your enemy, you must become your enemy." — Sun Tzu (paraphrased)

Ready? Open `01-foundations.md`.
