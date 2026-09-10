# LangGraph + Deep Agents — Production Course

### From zero to shipping AI agents inside your FastAPI/Postgres/Redis/Docker SaaS

**How to use this course:** Copy one module at a time (just the module, not the whole file) into a fresh AI chat and say "teach me this module in depth, with working code, using LangGraph 1.x / deepagents 0.5.x, and quiz me at the end." Do them in order — later modules assume earlier ones. Each module lists **submodules** and, where needed, **sub-submodules**. A "✅ You should be able to" checkpoint closes every module so you can self-verify before moving on.

**Your stack context (feed this to the AI at the start of every module so answers stay relevant):**
`Python, FastAPI, PostgreSQL, Redis, Git/GitHub, GitHub Actions, GHCR, Docker/Docker Compose, deployed as containers on Ubuntu 26 with Cloudflare Tunnel. Prefer free/open-source, prefer popular battle-tested libraries over hand-rolled code.`

**Framework versions this course targets:** LangChain 1.x, LangGraph 1.x (GA since Oct 2025), `deepagents` 0.5.x, LangGraph checkpointers `langgraph-checkpoint-postgres` / `langgraph-checkpoint-redis`. Since this space moves fast, tell the AI to verify current package versions/APIs before writing code in each module.

---

## MODULE 0 — Orientation: What You're Actually Building

0.1 What LangGraph is (a low-level durable graph/state-machine runtime) vs what LangChain's `create_agent` is (a minimal agent loop built on LangGraph) vs what `deepagents` is (an opinionated, batteries-included agent harness built on top of `create_agent`) — the three-layer mental model
0.2 Where "AI agent" fits in your SaaS: agent as a backend service behind FastAPI, not a replacement for FastAPI
0.3 When you actually need a graph/agent vs. when a single LLM call or simple RAG pipeline is enough (avoiding overengineering)
0.4 Survey of the competing frameworks (CrewAI, AutoGen, OpenAI Agents SDK, Google ADK, pydantic AI) and why this course standardizes on LangGraph/Deep Agents for a self-hosted, Python/FastAPI shop
0.5 Setting up your learning repo: `uv` or `pip`, Python 3.11+, project skeleton, `.env` handling
0.6 How this course maps onto your final architecture (a diagram: Cloudflare Tunnel → FastAPI → LangGraph agent service → Postgres (checkpoints + app data) + Redis (cache/queue) → LLM provider(s))

✅ You should be able to: explain to a colleague, in 3 sentences, the difference between LangGraph, LangChain agents, and Deep Agents, and sketch where the agent sits in your existing stack.

---

## MODULE 1 — LLM & Agent Fundamentals (just enough theory)

1.1 What an "agent" actually is: LLM + tools + loop + state (de-mystifying the buzzword)
1.2 Tool calling / function calling mechanics: how the model requests a tool, how you execute it, how the result goes back in
1.3 Context windows, tokens, and why context management is the #1 production problem for agents
1.4 Prompting for agents: system prompts, tool descriptions, ReAct-style reasoning loops
1.5 Determinism vs. non-determinism: why agents need graphs (control), not just free-form loops
1.6 Model-agnosticism: LangChain's chat model interface, using `init_chat_model`, switching between Anthropic/OpenAI/local (Ollama/vLLM) with one line
1.7 Structured output basics (Pydantic schemas + `with_structured_output`)

✅ You should be able to: write a plain Python loop that calls an LLM, executes a tool, and feeds the result back — before ever touching LangGraph. This is what LangGraph automates for you.

---

## MODULE 2 — LangChain Core Primitives (the building blocks LangGraph sits on)

2.1 The modern LangChain package layout (`langchain-core`, `langchain`, provider packages like `langchain-anthropic`/`langchain-openai`, `langchain-classic` for legacy pieces) — know what's current vs. deprecated
2.2 Messages: `HumanMessage`, `AIMessage`, `SystemMessage`, `ToolMessage`, message history conventions
2.3 Tools
&nbsp;&nbsp;2.3.1 `@tool` decorator, sync vs async tools
&nbsp;&nbsp;2.3.2 Args schemas with Pydantic, input validation
&nbsp;&nbsp;2.3.3 Tool error handling conventions (returning errors vs raising)
&nbsp;&nbsp;2.3.4 Binding tools to a model (`model.bind_tools`)
2.4 Runnables & LCEL (LangChain Expression Language) basics — enough to read other people's code, not to over-invest in
2.5 `create_agent` — LangChain's prebuilt single-agent loop (the "middle layer" before Deep Agents)
2.6 Retrieval basics (vector stores, embeddings, retrievers) — only as much as needed for later RAG-tool modules
2.7 Free/open-source component choices: which vector DB (pgvector — reuses your existing Postgres!), which embedding models are open weight, avoiding paid-only pieces

✅ You should be able to: build a single LangChain agent with `create_agent`, give it 2 custom tools, and get it running end to end without LangGraph.

---

## MODULE 3 — LangGraph Fundamentals

3.1 Why a graph: nodes, edges, state — the core abstraction
3.2 The `StateGraph` API
&nbsp;&nbsp;3.2.1 Defining state with `TypedDict` / Pydantic models
&nbsp;&nbsp;3.2.2 Reducers (`Annotated[..., add_messages]` etc.) — how concurrent/sequential updates merge into state
&nbsp;&nbsp;3.2.3 Nodes as plain Python functions
&nbsp;&nbsp;3.2.4 Edges: normal edges vs conditional edges
&nbsp;&nbsp;3.2.5 `START` / `END`
3.3 Compiling and invoking a graph: `.compile()`, `.invoke()`, `.stream()`, `.ainvoke()`/`.astream()`
3.4 Building your first agent graph by hand (LLM node → tool node → conditional loop) — understanding what `create_agent`/`create_react_agent` does under the hood
3.5 Prebuilt `create_react_agent` from `langgraph.prebuilt` — when to use the prebuilt vs hand-roll
3.6 Visualizing graphs (Mermaid export, LangGraph Studio) for debugging
3.7 Sync vs async execution patterns — why you'll want async in a FastAPI service

✅ You should be able to: hand-build a ReAct-style agent graph from scratch (LLM node, tool-execution node, conditional routing edge) and explain every line.

---

## MODULE 4 — State, Memory & Persistence (the production-critical module)

4.1 Short-term memory: thread-scoped state and checkpointing
&nbsp;&nbsp;4.1.1 The `Checkpointer` interface and why every production agent needs one
&nbsp;&nbsp;4.1.2 `InMemorySaver` (dev only) vs durable checkpointers
&nbsp;&nbsp;4.1.3 **`PostgresSaver` (`langgraph-checkpoint-postgres`)** — setting it up against your existing Postgres instance, schema/migrations it creates, connection pooling considerations
&nbsp;&nbsp;4.1.4 Redis-backed checkpointer (`langgraph-checkpoint-redis`) — when to use Redis vs Postgres for checkpoints, trade-offs (durability vs speed)
&nbsp;&nbsp;4.1.5 Threads: what a `thread_id` represents, mapping threads to your app's users/conversations
4.2 Long-term memory: the `Store` interface
&nbsp;&nbsp;4.2.1 `InMemoryStore` vs `PostgresStore`
&nbsp;&nbsp;4.2.2 Cross-thread memory (facts about a user that persist across conversations)
&nbsp;&nbsp;4.2.3 Semantic search over stored memories (embeddings + pgvector)
4.3 Time travel & replay: inspecting/rewinding checkpoint history, forking from a past state (huge for debugging in production)
4.4 State schema design patterns: separating "public" input/output schema from "internal" working state, reducers for lists/dicts
4.5 Context management for long conversations
&nbsp;&nbsp;4.5.1 Trimming/summarizing message history
&nbsp;&nbsp;4.5.2 Why "just append forever" breaks agents in production (cost + quality degradation)
4.6 Designing your Postgres schema so LangGraph's tables coexist cleanly with your app's own tables (naming, migrations via Alembic, backups)

✅ You should be able to: run the same agent graph backed by `PostgresSaver`, kill the process mid-conversation, restart it, and resume the exact same thread from Postgres.

---

## MODULE 5 — Control Flow: Branching, Loops, Parallelism, Human-in-the-Loop

5.1 Conditional edges deep dive: routing functions, multiple destinations
5.2 Loops: building retry/self-correction loops (generate → validate → retry)
5.3 Parallel execution ("fan-out/fan-in"): running independent branches concurrently, merging results with reducers
5.4 `Send` API for dynamic parallel branching (map-reduce style, e.g. "research N subtopics in parallel")
5.5 Subgraphs: composing smaller graphs into larger ones, when to modularize
5.6 Human-in-the-loop (HITL)
&nbsp;&nbsp;5.6.1 `interrupt()` — pausing a graph mid-execution for approval
&nbsp;&nbsp;5.6.2 Resuming with `Command(resume=...)`
&nbsp;&nbsp;5.6.3 Patterns: approve/reject tool calls, edit agent output before it continues, "review queue" UX
&nbsp;&nbsp;5.6.4 How this maps to a real UI (FastAPI endpoint that surfaces a pending interrupt, user approves via your frontend, you resume the thread)
5.7 Error handling & retries at the node level, `RetryPolicy`
5.8 Caching node results (node-level caching to avoid redundant LLM calls)

✅ You should be able to: build a graph where a "risky" tool call pauses for human approval via `interrupt()`, and you can resume it later from a completely separate API request.

---

## MODULE 6 — Streaming (what makes agents feel responsive)

6.1 Why streaming matters for UX and for long-running agents
6.2 Stream modes: `values`, `updates`, `messages`, `custom`, `debug` — what each gives you
6.3 Token-level streaming from the underlying LLM through the graph
6.4 Streaming tool call progress / intermediate steps to the frontend
6.5 Wiring LangGraph streaming into FastAPI
&nbsp;&nbsp;6.5.1 Server-Sent Events (SSE) endpoint pattern (most popular, simplest with Cloudflare Tunnel/proxies)
&nbsp;&nbsp;6.5.2 WebSocket alternative and when you'd choose it instead
&nbsp;&nbsp;6.5.3 Handling client disconnects, backpressure, and cancellation
6.6 Streaming custom progress events from inside a node (`get_stream_writer` / custom events) — e.g. "searching the web…", "reading file…"

✅ You should be able to: expose a FastAPI SSE endpoint that streams a LangGraph agent's tokens and tool-progress events live to a browser `EventSource`.

---

## MODULE 7 — Multi-Agent Systems

7.1 Why multi-agent: task decomposition, specialization, isolating context windows
7.2 Architectures
&nbsp;&nbsp;7.2.1 Supervisor pattern (one orchestrator agent routes to specialist sub-agents)
&nbsp;&nbsp;7.2.2 Hierarchical/team pattern (supervisors of supervisors)
&nbsp;&nbsp;7.2.3 Network/swarm pattern (`langgraph-swarm`) — peer agents handing off to each other
&nbsp;&nbsp;7.2.4 Sequential pipeline pattern
7.3 Communication: shared state vs. explicit message-passing between agents (the "everyone reads/writes shared state" model vs. isolated sub-agent context)
7.4 Handoffs: implementing handoff tools, preserving/trimming context across handoffs
7.5 Isolating context windows per sub-agent (why this is critical for cost and quality at scale)
7.6 `langgraph-bigtool` — giving an agent access to hundreds/thousands of tools without blowing the context window (semantic tool retrieval)
7.7 When multi-agent is overkill: single well-designed agent with good tools often beats a multi-agent system — decision framework

✅ You should be able to: build a supervisor agent that routes a request to one of 3 specialist sub-agents and returns a merged result.

---

## MODULE 8 — Deep Agents Framework (the harness you'll actually build your product on)

8.1 What `deepagents` gives you out of the box that raw LangGraph doesn't: planning tool, filesystem, sub-agent spawning, context/auto-summarization, skills
8.2 Installing and first agent: `create_deep_agent()`, minimal example
8.3 Planning
&nbsp;&nbsp;8.3.1 The built-in `write_todos` tool — how explicit planning improves reliability on long tasks
&nbsp;&nbsp;8.3.2 Inspecting/streaming the plan to your UI (showing the user a live todo list)
8.4 Virtual filesystem
&nbsp;&nbsp;8.4.1 `read_file`/`write_file`/`edit_file`/`ls`/`glob`/`grep` — using files as the agent's working memory instead of stuffing everything into the context window
&nbsp;&nbsp;8.4.2 Pluggable backends: in-memory (dev) vs. real filesystem vs. cloud storage — choosing one that fits a stateless container deployment
8.5 Sub-agent delegation
&nbsp;&nbsp;8.5.1 The `task` tool — spawning isolated sub-agents with their own context window
&nbsp;&nbsp;8.5.2 Defining `SubAgent`s: custom tools/prompts per sub-agent, read-only vs. write sub-agents
&nbsp;&nbsp;8.5.3 When to delegate vs. handle inline
8.6 Shell/command execution tool and sandboxing options (why you never run this un-sandboxed in production — preview of Module 11's security section)
8.7 Skills: `SKILL.md`-style reusable behaviors the agent loads on demand — building your own domain-specific skills for your SaaS
8.8 Context management internals: auto-summarization triggers, large tool outputs auto-saved to files instead of flooding context
8.9 Customizing a Deep Agent: swapping models (any LangChain chat model, including local via Ollama/vLLM), custom system prompt, custom tool set, custom middleware
8.10 Deep Agents CLI — using the prebuilt coding-agent CLI as a reference implementation to study
8.11 Deep Agents' security model ("trust the LLM, enforce boundaries at the tool/sandbox layer, not by hoping the model self-polices") — why this dictates your Module 11 design

✅ You should be able to: build a custom Deep Agent for a real task (e.g., "research assistant" or "customer-support triager") with your own tools, a custom system prompt, and at least one delegated sub-agent.

---

## MODULE 9 — Tools, RAG & MCP Integration

9.1 Designing good tools for agents: naming, docstrings-as-prompts, narrow vs. broad tools, idempotency
9.2 Tool authentication patterns: injecting per-user credentials/API keys into tool calls safely (multi-tenant SaaS concern)
9.3 RAG as a tool
&nbsp;&nbsp;9.3.1 pgvector-backed retriever (reuse your existing Postgres — no new infra)
&nbsp;&nbsp;9.3.2 Open-source embedding models (self-hosted vs. free-tier API)
&nbsp;&nbsp;9.3.3 Chunking strategies, re-ranking basics
&nbsp;&nbsp;9.3.4 Wrapping retrieval as a LangChain tool the agent decides when to call (agentic RAG) vs. always-on RAG
9.4 Model Context Protocol (MCP)
&nbsp;&nbsp;9.4.1 What MCP is and why it's becoming the standard for tool interoperability
&nbsp;&nbsp;9.4.2 `langchain-mcp-adapters` — consuming existing MCP servers as LangChain tools
&nbsp;&nbsp;9.4.3 Writing your own MCP server for internal company tools/data
&nbsp;&nbsp;9.4.4 Transport options (stdio vs. streamable HTTP) and which to use for a self-hosted Dockerized setup
9.5 Web search / browsing tools using free/open options (self-hosted SearxNG vs. free-tier APIs)
9.6 Caching tool results in Redis to cut cost and latency on repeated calls

✅ You should be able to: give a Deep Agent a pgvector RAG tool over your own documents plus one MCP-sourced tool, and have it correctly choose between them.

---

## MODULE 10 — Observability, Evaluation & Testing

10.1 Why agents need different observability than normal APIs (non-determinism, multi-step, cost visibility)
10.2 LangSmith
&nbsp;&nbsp;10.2.1 Free tier and self-hosting options — deciding if you can stay fully open-source here or accept a hosted free tier
&nbsp;&nbsp;10.2.2 Tracing: enabling tracing (`LANGSMITH_TRACING`), reading a trace, spotting bottlenecks/cost hotspots
&nbsp;&nbsp;10.2.3 Open-source alternatives (e.g. Langfuse self-hosted via Docker Compose) if you want zero third-party dependency
10.3 Logging & metrics for production
&nbsp;&nbsp;10.3.1 Structured logging per node/run, correlating with your existing FastAPI request logs
&nbsp;&nbsp;10.3.2 Cost tracking per user/thread (token counts × pricing) stored in Postgres for billing/usage limits
&nbsp;&nbsp;10.3.3 Prometheus/Grafana basics for latency, error rate, tool-call failure rate (fits your "free/open-source" preference)
10.4 Testing agents
&nbsp;&nbsp;10.4.1 Unit-testing individual tools and nodes like normal Python functions
&nbsp;&nbsp;10.4.2 Testing graph routing logic deterministically (mocking the LLM)
&nbsp;&nbsp;10.4.3 Integration tests running the full graph against a real (cheap) model
10.5 Evaluation
&nbsp;&nbsp;10.5.1 Building an eval dataset from real user transcripts
&nbsp;&nbsp;10.5.2 LLM-as-judge evaluators, and their known failure modes
&nbsp;&nbsp;10.5.3 Regression testing prompts/graphs before you ship changes (preventing silent quality drops)
10.6 Handling and monitoring hallucinations / bad tool calls in production (guardrails, output validation)

✅ You should be able to: view a full trace of a multi-step agent run, identify which step cost the most tokens, and write one automated eval test that would catch a regression.

---

## MODULE 11 — Security & Sandboxing

11.1 Threat model for agents: prompt injection (from tool outputs, RAG documents, web content), excessive tool permissions, data exfiltration
11.2 Sandboxing code/shell execution
&nbsp;&nbsp;11.2.1 Why Deep Agents' shell tool must never touch your host directly
&nbsp;&nbsp;11.2.2 Docker-based sandboxing patterns (spinning up ephemeral containers per agent run) — fits your existing Docker expertise directly
&nbsp;&nbsp;11.2.3 Open-source sandbox runtimes to evaluate (e.g. gVisor, Firecracker-based options) vs. simplest viable approach for your scale
11.3 Least-privilege tool design: scoping what each tool can actually reach (DB read-only roles, restricted API keys, network egress rules)
11.4 Multi-tenant isolation: making sure User A's agent/thread/files can never leak into User B's — thread_id/store namespacing discipline
11.5 Secrets management: keeping LLM/API keys out of agent-visible context, out of git, using Docker secrets/env properly
11.6 Rate limiting & abuse prevention (Redis-backed rate limits per user/tenant on agent invocations)
11.7 Input/output guardrails: filtering user input and model output for your SaaS's specific risk surface
11.8 Human-in-the-loop as a security control, not just a UX feature (Module 5 callback)

✅ You should be able to: describe exactly how a malicious prompt injected via a tool's output could try to make your agent do something bad, and name the specific control in your system that stops it.

---

## MODULE 12 — Production Deployment (your exact stack)

12.1 Deployment topology options
&nbsp;&nbsp;12.1.1 Self-hosted "roll your own" (agent logic inside your FastAPI service) — the recommended path given your preferences
&nbsp;&nbsp;12.1.2 Self-hosted LangGraph Server / Agent Server (`langgraph up`, the open-source runtime) — what it adds (built-in APIs, persistence, streaming) vs. rolling your own, and licensing to check before adopting
&nbsp;&nbsp;12.1.3 Managed LangSmith deployment — noting it as the paid/non-self-hosted option you're likely to skip
12.2 Wrapping a LangGraph/Deep Agent inside FastAPI
&nbsp;&nbsp;12.2.1 App structure: separating agent definitions from API routes
&nbsp;&nbsp;12.2.2 Async endpoints calling `.ainvoke()`/`.astream()`
&nbsp;&nbsp;12.2.3 Background execution for long-running agent tasks (FastAPI `BackgroundTasks` vs. a proper task queue)
&nbsp;&nbsp;12.2.4 Using Redis as a job queue (e.g. Arq/Celery/RQ — pick the popular, well-maintained one) for long-running agent runs that shouldn't block a request
12.3 Dockerizing the agent service
&nbsp;&nbsp;12.3.1 Dockerfile best practices for a Python/LangGraph service (slim base image, layer caching, non-root user)
&nbsp;&nbsp;12.3.2 docker-compose.yml wiring: FastAPI+agent service, Postgres, Redis, and (optionally) self-hosted LangSmith-alternative
&nbsp;&nbsp;12.3.3 Environment/config management across dev/staging/prod
12.4 CI/CD fitting your existing pipeline
&nbsp;&nbsp;12.4.1 GitHub Actions: lint/test/build on PR, build+push image to GHCR on merge
&nbsp;&nbsp;12.4.2 Running agent eval tests (Module 10.5) as a CI gate before deploy
&nbsp;&nbsp;12.4.3 Pulling from GHCR and redeploying on your Ubuntu 26 server (compose pull + up -d, or a simple deploy script/webhook)
12.5 Exposing it via Cloudflare Tunnel
&nbsp;&nbsp;12.5.1 Tunnel config for a streaming (SSE/WebSocket) endpoint specifically — timeouts and buffering settings that commonly break streaming
&nbsp;&nbsp;12.5.2 TLS, custom domains, access policies via Cloudflare
12.6 Database migrations in production: managing both your app's Alembic migrations and LangGraph checkpointer's own schema setup safely
12.7 Zero/low-downtime deploys for a stateful agent service (in-flight thread considerations)

✅ You should be able to: draw the full docker-compose topology for your agent SaaS and explain what happens, step by step, from `git push` to a live update behind your Cloudflare Tunnel.

---

## MODULE 13 — Scaling & Cost Management

13.1 Horizontal scaling of a stateless agent-serving container (why checkpointing in Postgres/Redis, not in-memory, is what makes this possible)
13.2 Connection pooling for Postgres under concurrent agent runs (pgbouncer or equivalent)
13.3 Redis usage patterns: cache, checkpoints, rate limiting, job queue — keeping these logically separated (DB indexes/key prefixes) even on one Redis instance
13.4 Model routing for cost: cheap/fast model for simple steps, expensive model only where needed (LangGraph makes per-node model choice trivial)
13.5 Caching strategies: semantic caching of LLM responses, tool-result caching
13.6 Concurrency limits & backpressure: protecting your LLM provider spend and rate limits under load
13.7 Local/open-weight model options for cost-sensitive workloads (Ollama/vLLM self-hosted) and when the trade-off is worth it vs. hosted frontier APIs
13.8 Monitoring cost per tenant for usage-based billing tiers in your SaaS

✅ You should be able to: explain why your agent service can scale to N replicas behind a load balancer with zero code changes, given the persistence choices from Module 4.

---

## MODULE 14 — Capstone: Build Your Actual Product Feature

14.1 Scope a real feature from your SaaS idea as a Deep Agent (pick one: a research agent, a support agent, a data-analysis agent, a workflow-automation agent — something with real tools, not a toy)
14.2 Design pass: state schema, tools needed, sub-agents needed (if any), HITL points, guardrails
14.3 Build pass: implement using everything from Modules 3–9
14.4 Wrap pass: FastAPI endpoints (sync + streaming), Postgres/Redis wiring, Dockerfile, docker-compose
14.5 Harden pass: sandboxing, rate limits, multi-tenant isolation, secrets
14.6 Observe pass: tracing, logging, one eval test suite
14.7 Ship pass: GitHub Actions → GHCR → deploy to your Ubuntu 26 server → live behind Cloudflare Tunnel
14.8 Retro: what broke, what you'd change, what to read next (LangGraph release notes, `deepagents` changelog, LangChain forum)

✅ You should be able to: point a friend at a URL and have them use a real, persistent, streaming, sandboxed AI agent that you built and deployed entirely yourself.

---

## Suggested pace

- Modules 0–2: 1 sitting (you already know 90% of the prerequisite engineering, this is just framework vocabulary)
- Modules 3–6: the LangGraph core — take these slowly, they're the foundation for everything else
- Modules 7–9: where "agent" becomes "useful product"
- Modules 10–13: the part most tutorials skip and most production incidents come from — do not shortcut these
- Module 14: proves you actually learned it

## A note on staying current

LangGraph and Deep Agents are both under active, fast development. Before starting any module, ask the AI to check the current version of `langgraph` / `langchain` / `deepagents` and adjust API names if anything has changed since this course was written (September 2026).
