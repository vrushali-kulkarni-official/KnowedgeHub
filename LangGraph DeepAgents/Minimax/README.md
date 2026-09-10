# LangGraph + Deep Agents — Production-Grade Course

> **Audience:** You already know Python, FastAPI, Postgres, Redis, Git, GitHub, GitHub Actions, GHCR, Docker, Docker Compose, and you deploy on Ubuntu with Cloudflare Tunnel. You're building toward an AI SaaS.
>
> **Goal:** By the end of Module 16, you can design, build, test, deploy, and operate a production AI agent system using LangGraph and the Deep Agents library — integrated with your existing stack.

---

## How to use this course

1. **Work through modules in order.** Each one builds on the previous. Skipping ahead will hurt.
2. **Feed one module at a time to an AI tutor** (me or any other). Say: *"Teach me this module step by step, ask me to write the code, and grade my answers to the exercises."*
3. **Do the hands-on project in every module.** Reading ≠ learning. Type the code. Run it. Break it. Fix it.
4. **Do the exercises before looking at hints.** Struggle is the point.
5. **Treat the Capstone as the real deliverable.** Modules 0–15 are scaffolding for Module 16.

Each module file follows the same structure so you (and your AI tutor) always know where you are:

```
# Module NN — Title
## Prerequisites          ← which modules you must have done
## Why this module matters
## Learning objectives
## Sub-modules (with sub-sub-modules)
## Hands-on project
## Exercises
## Production checklist
## Key takeaways
## Resources
```

---

## The roadmap at a glance

| # | Module | Focus | Output you build |
|---|--------|-------|------------------|
| 00 | [Prerequisites & Setup](./modules/00_prerequisites_and_setup.md) | LangChain basics, env, project layout | Working dev env + first "Hello LangGraph" |
| 01 | [LangGraph Mental Model](./modules/01_langgraph_mental_model.md) | Why graphs, when to use them | Decision framework |
| 02 | [State — the heart of LangGraph](./modules/02_state_the_heart_of_langgraph.md) | StateGraph, schema, reducers | A graph with rich state |
| 03 | [Nodes, Edges & Topology](./modules/03_nodes_edges_topology.md) | Graph shapes, routing, parallelism | A branching/looping graph |
| 04 | [Tool Calling & ReAct](./modules/04_tool_calling_and_react.md) | ToolNode, agent loop, errors | A tool-using agent |
| 05 | [Memory & Persistence](./modules/05_memory_and_persistence.md) | Checkpointers, threads, time travel | A persistent multi-turn agent |
| 06 | [Human-in-the-Loop](./modules/06_human_in_the_loop.md) | interrupt, Command, approval flows | A human-approved agent |
| 07 | [Streaming](./modules/07_streaming.md) | Token/event streaming, FastAPI SSE | A real-time chat endpoint |
| 08 | [Subgraphs & Multi-Agent](./modules/08_subgraphs_and_multi_agent.md) | Supervisor, handoffs, network | A multi-agent system |
| 09 | [LangGraph Platform & Deployment](./modules/09_langgraph_platform_deployment.md) | Studio, langgraph-cli, self-hosting | A deployable graph server |
| 10 | [Observability, Eval & Production](./modules/10_observability_evaluation_production.md) | LangSmith, retries, rate limits, testing | Production hardening pass |
| 11 | [Deep Agents: The Big Picture](./modules/11_deep_agents_big_picture.md) | The 4 pillars, when to use vs raw LangGraph | First deep agent |
| 12 | [Deep Agents: Planning & Todos](./modules/12_deep_agents_planning.md) | write_todos, plan visibility | A planning deep agent |
| 13 | [Deep Agents: Subagents](./modules/13_deep_agents_subagents.md) | The task tool, context isolation | A deep agent with workers |
| 14 | [Deep Agents: File System & Backends](./modules/14_deep_agents_filesystem_backends.md) | Virtual FS, backends, MinIO/S3 | A deep agent that handles files |
| 15 | [Deep Agents: Production Patterns](./modules/15_deep_agents_production_patterns.md) | Custom instructions, evals, cost | Production-ready deep agent |
| 16 | [Capstone: AI SaaS Agent](./modules/16_capstone_ai_saas_agent.md) | Full stack: FastAPI + LangGraph + Postgres + Redis + Docker + Cloudflare | Your SaaS MVP |

---

## Recommended pacing

- **Beginner phase (00–04):** 1 module per 2–3 days. Lots of typing, lots of "why" questions.
- **Intermediate phase (05–10):** 1 module per 3–5 days. Start thinking about your SaaS architecture.
- **Advanced phase (11–15):** 1 module per 3–5 days. You're building production muscle.
- **Capstone (16):** 1–2 weeks. This is where it all comes together.

Total: roughly **3 months** of focused, hands-on learning.

---

## Tooling rules (matching your preferences)

- **Free + open source only.** Every dependency in `requirements.txt` is FOSS.
- **Popular libraries, not bespoke code.** If the LangChain / LangGraph ecosystem ships it, we use it.
- **Abstraction layer over vendor SDKs.** LangChain stays the seam — never import `openai` or `google.generativeai` directly from app code. (Exception: thin LangChain-compatible wrappers when needed.)
- **Docker first.** Every service runs in a container. No "run `pip install` on the host."
- **Model-agnostic.** Default examples use OpenAI-compatible APIs (works with Gemini via OpenAI-compatible endpoint, Ollama, OpenRouter, etc.). You'll be able to swap models without rewriting.

---

## What this course is *not*

- Not a LangChain beginner course. Module 00 is the *minimum* LangChain you need, not a deep dive.
- Not a Python course. We assume you can write Python.
- Not a "build a chatbot in 5 minutes" tutorial. We go deep on production concerns.
- Not vendor-locked. Every choice is replaceable.

---

## Ready?

Start with **[Module 00 — Prerequisites & Setup](./modules/00_prerequisites_and_setup.md)**.
