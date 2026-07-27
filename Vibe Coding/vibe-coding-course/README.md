# 🚀 The Complete Vibe Coding & Agentic AI Coding Guide

> **From "what is this" to "shipping a real AI SaaS"** — a beginner-to-pro course on how professional developers actually use AI to build software in 2026.

---

## 📚 What's in here

This is a complete, structured course that takes you from absolute beginner to professional AI-assisted developer. Every chapter builds on the previous one, and we build a real AI SaaS together along the way: **DocuMind AI** — a multi-tenant document chat SaaS.

## 🗺️ The Course Map

| # | File | Topic | Difficulty |
|---|------|-------|------------|
| 0 | [`00-THE-COMPLETE-GUIDE.md`](00-THE-COMPLETE-GUIDE.md) | Intro + Parts 1-6: Foundations, toolkit, mental model, prompts, architecture, FastAPI + PostgreSQL | 🟢 → 🟠 |
| 1 | [`01-LANGCHAIN-FUNDAMENTALS.md`](01-LANGCHAIN-FUNDAMENTALS.md) | Part 7: LangChain — LLMs, prompts, chains, tools, streaming | 🟠 |
| 2 | [`02-RAG-DEEP-DIVE.md`](02-RAG-DEEP-DIVE.md) | Part 8: RAG — the pattern that powers every AI SaaS | 🟠 |
| 3 | [`03-PRODUCTION-PATTERNS.md`](03-PRODUCTION-PATTERNS.md) | Part 9: Testing, logging, rate limiting, monitoring | 🔥 |
| 4 | [`04-DOCKER-CICD.md`](04-DOCKER-CICD.md) | Part 10: Docker, Compose, GitHub Actions, deployment | 🔥 |
| 5 | [`05-VIBE-CODING-WORKFLOW.md`](05-VIBE-CODING-WORKFLOW.md) | Part 11: How to actually use AI to code day-to-day | 🔥 |
| 6 | [`06-ADVANCED-PATTERNS.md`](06-ADVANCED-PATTERNS.md) | Part 12: Multi-agent, memory, streaming, caching, LangGraph | 🔥 |
| 7 | [`07-CAPSTONE-SHIP-IT.md`](07-CAPSTONE-SHIP-IT.md) | Part 13: Ship DocuMind AI end-to-end | 🔥 |

## 🛠️ The Stack You'll Learn

| Layer | What | Why |
|-------|------|-----|
| **Language** | Python 3.12 | The AI ecosystem standard |
| **Web** | FastAPI | Async, auto-docs, AI-friendly |
| **Database** | PostgreSQL 16 | Reliable, free, scales |
| **ORM** | SQLAlchemy 2.0 async | The Python ORM |
| **Migrations** | Alembic | Schema version control |
| **LLM Framework** | LangChain | Vendor abstraction, no lock-in |
| **LLM** | Google Gemini (configurable) | Free tier, easy to switch |
| **Vector DB** | ChromaDB | Free, open source, local |
| **Auth** | JWT + bcrypt | Industry standard |
| **Background Jobs** | ARQ + Redis | Async, simple, reliable |
| **Caching** | Redis | Industry standard |
| **Testing** | pytest + httpx | The standard |
| **Container** | Docker + Compose | Universal |
| **CI/CD** | GitHub Actions | Free for OSS |
| **Observability** | Langfuse + structlog | Free tier, traces LLMs |
| **Deployment** | Fly.io / Render | Free tier, Docker-friendly |

## 🎯 How to Read This Course

1. **Start with file 00** — it has the intro and Parts 1-6 (the foundations)
2. **Go in order** — each part assumes you read the previous
3. **Build as you go** — copy the code into a real project, run it, break it, fix it
4. **Use the spec templates** from Part 4 to ask your AI assistant to help you build the same things
5. **By file 07** you should be able to ship your own AI SaaS

## 💡 The Core Philosophy

```
+------------------------------------------+
|  You are the architect.                  |
|  The AI is your incredibly fast junior.  |
|  You set the spec. The AI does the typing.|
|  You review. The AI fixes what you catch.|
+------------------------------------------+
```

The pros don't write every line. They don't read every diff. They:
- Write clear specs
- Use AI for the busywork
- Review the behavior, not the syntax
- Catch what AI gets wrong
- Ship 5-10x faster than traditional coders

## 🆓 Everything in this course is free and open source

Every tool mentioned is either:
- **Free** (free tier / open source core)
- **Open source** (code you can read and modify)
- **Configurable** (use free tiers, upgrade later if needed)

No vendor lock-in. Switch LLM providers with one line of code. Move from one DB to another. Run locally forever.

## 📁 Project Structure

```
vibe-coding-course/
├── README.md                              # You are here
├── 00-THE-COMPLETE-GUIDE.md              # Intro + Parts 1-6
├── 01-LANGCHAIN-FUNDAMENTALS.md          # Part 7
├── 02-RAG-DEEP-DIVE.md                   # Part 8
├── 03-PRODUCTION-PATTERNS.md             # Part 9
├── 04-DOCKER-CICD.md                     # Part 10
├── 05-VIBE-CODING-WORKFLOW.md            # Part 11
├── 06-ADVANCED-PATTERNS.md               # Part 12
├── 07-CAPSTONE-SHIP-IT.md                # Part 13
├── code/                                  # (Sample code stubs — see each part)
│   ├── part-1-foundations/
│   ├── part-2-toolkit/
│   ├── part-3-architecture/
│   ├── part-4-fastapi-db/
│   ├── part-5-langchain/
│   ├── part-6-rag/
│   ├── part-7-production/
│   ├── part-8-docker-cicd/
│   ├── part-9-workflow/
│   ├── part-10-advanced/
│   └── capstone-documind/
└── diagrams/                              # Architecture diagrams
```

## 🎓 Who This Is For

- ✅ You can write basic Python
- ✅ You've used a terminal
- ✅ You have a GitHub account
- ✅ You want to ship a real AI SaaS
- ❌ No AI/ML background needed
- ❌ No prior LangChain / FastAPI experience needed

## 🗣️ What "Vibe Coding" and "Agentic AI Coding" Mean

- **Vibe coding** = you describe what you want in natural language, AI writes the code, you review and guide. Coined by Andrej Karpathy in Feb 2025.
- **Agentic AI coding** = the AI plans, executes, tests, and iterates. You're the tech lead, AI is the senior dev.

This course teaches you both.

## 📞 Get Help

- Each part ends with a "Quick Recap" so you can verify you got it
- Use the spec templates from Part 4 to ask AI for help
- Build the same project yourself with your own twist
- When stuck, re-read the relevant part — usually the answer is there

## 🚀 Ready?

**Start here:** [`00-THE-COMPLETE-GUIDE.md`](00-THE-COMPLETE-GUIDE.md)

Happy shipping. 🎉
