# 🎓 AGENTS.md Mastery — From Zero to Production-Ready

Welcome! This is a **progressive tutorial** for writing `AGENTS.md` files and orchestrating
sub-agents for your AI SaaS application.

## 🎯 What you'll be able to do after this course

By the end of these 10 lessons you will be able to:

1. ✅ Explain what `AGENTS.md` is, where it came from, and why it matters
2. ✅ Write a basic `AGENTS.md` from scratch
3. ✅ Assign precise **roles** to agents and sub-agents
4. ✅ Create **sub-agent** files that collaborate on a shared goal
5. ✅ Grant and scope **skills** (tool access) safely
6. ✅ Write `AGENTS.md` files without leaking secrets or creating prompt-injection risks
7. ✅ Audit and safely use `AGENTS.md` files written by **other people / tools**
8. ✅ Version-control `AGENTS.md` like production code
9. ✅ Integrate with **agent harnesses** (Claude Code, Gemini CLI, OpenClaw, Hermes)
10. ✅ Drop a production-ready `AGENTS.md` set into your **FastAPI + Postgres + Qdrant + LangChain + LangGraph** project

## 📚 Lesson Map (go in order — each builds on the last)

| #  | File                                    | Concept                                        | Difficulty |
|----|-----------------------------------------|------------------------------------------------|------------|
| 1  | `lessons/01-what-is-agents-md.md`       | What `AGENTS.md` is, history, why it exists    | 🟢 Beginner |
| 2  | `lessons/02-basic-structure.md`         | File locations, sections, first working file   | 🟢 Beginner |
| 3  | `lessons/03-roles-and-personas.md`      | Role assignment, persona design                | 🟡 Easy-Medium |
| 4  | `lessons/04-sub-agents.md`              | Sub-agents, delegation, parent-child workflows | 🟡 Medium |
| 5  | `lessons/05-skills-and-tools.md`        | Granting skills/tools safely, least-privilege  | 🟠 Medium |
| 6  | `lessons/06-safety-when-writing.md`     | Don't leak secrets, avoid prompt injection     | 🔴 Important |
| 7  | `lessons/07-safety-when-reading.md`     | Auditing other people's `AGENTS.md` files      | 🔴 Important |
| 8  | `lessons/08-production-patterns.md`     | Versioning, CI/CD, team workflows              | 🟠 Production |
| 9  | `lessons/09-harness-integration.md`     | Claude Code, Gemini CLI, OpenClaw, Hermes      | 🟠 Production |
| 10 | `lessons/10-real-project-example.md`    | The full `AGENTS.md` set for YOUR project      | 🔴 Production |

## 🛠️ Companion Files (use these in your actual project)

```
production-ai-saas/
├── AGENTS.md                 ← The main file (drop into your repo root)
└── sub-agents/
    ├── backend-fastapi.md        ← FastAPI/Python specialist
    ├── data-postgres.md          ← PostgreSQL + SQLAlchemy specialist
    ├── vector-qdrant.md          ← Qdrant vector DB specialist
    ├── ai-langchain.md           ← LangChain + LangGraph specialist
    ├── security-reviewer.md      ← Security + secrets auditor
    └── devops-deployer.md        ← Docker / GitHub Actions / Ubuntu deploy
```

## 📖 How to study this

- **Read in order.** Each lesson assumes you know the previous one.
- **Type out the examples** by hand. Don't just read — write.
- **Drop the production files into a sandbox repo** and test with a real agent harness.
- **Break things on purpose** at the end to learn the safety boundaries.

## ⚠️ The Golden Rule of AGENTS.md

> An `AGENTS.md` is **executable documentation**. Every line is an instruction
> to an AI agent that can run code, push commits, and deploy servers. Treat it
> with the same seriousness as a `Dockerfile`, an `nginx.conf`, or an IAM policy.

Let's go. 🚀
