# The LangChain Open-Source Ecosystem: Zero → Production AI SaaS

A complete curriculum designed for your exact profile: Python/Pydantic/FastAPI/Postgres/Redis/Docker/CI-CD skills, FOSS-first, single Ubuntu host + Cloudflare Tunnel deployments.

**The ecosystem map (memorize this first):**

| Layer | Packages | Role |
|---|---|---|
| Core abstractions | `langchain-core` | Chat models, messages, tools, runnables, LCEL |
| Agent framework | `langchain` (v1.x) | `create_agent`, middleware system |
| Integrations | `langchain-openai`, `langchain-ollama`, `langchain-community`, etc. | Provider packages |
| Orchestration | `langgraph`, `langgraph-checkpoint-postgres` | Graphs, state, persistence, HITL |
| Prebuilt patterns | `langgraph-supervisor`, `langgraph-swarm`, `langmem` | Multi-agent + memory building blocks |
| Deep agents | `deepagents` | Planning, subagents, virtual filesystem, background tasks |
| MCP | `langchain-mcp-adapters`, `fastmcp` | Tool protocol interoperability |
| Observability/evals (OSS) | `langfuse` (self-hosted), `ragas`, `agentevals`, `promptfoo` | Replaces LangSmith/LangSmith Fleet |

**Through-line project:** you build one evolving app — a multi-tenant "Research Copilot SaaS" — growing it module by module until it's fully productionized in the capstone.

---

## Module 0 — Orientation, Setup & Mental Map *(4–6h)*
*Prereqs: your current skills · You build: dev environment + project skeleton*

**0.1 Ecosystem anatomy**
- `langchain-core` vs `langchain` vs partner packages vs `langchain-community` — what lives where and why the split exists
- What is OSS vs paid: LangSmith, LangSmith Fleet, LangGraph Platform/Deployment are closed → your FOSS substitutes (Langfuse for observability, custom FastAPI runtime for serving, Grafana for fleet-style monitoring)
- How LangGraph relates to LangChain v1's `create_agent` (agents *are* graphs under the hood)

**0.2 Version archaeology — avoiding the #1 beginner trap**
- Evolution: 0.1 → 0.2/0.3 → 1.x; mass deprecations (`LLMChain`, `initialize_agent`, legacy `create_react_agent`)
- Why 90% of tutorials/YouTube content online teaches dead APIs; how to detect outdated content
- Canonical sources: `docs.langchain.com`, the `langchain-ai/*` GitHub repos, Langfuse docs
- Pinning with `uv` lockfile; upgrading deliberately

**0.3 Dev environment with uv**
- `uv init` + project layout for an AI SaaS (`src/` layout, separate `lib/` for agent code vs API code)
- Secrets with `pydantic-settings` (you already know Pydantic) + `.env`
- Jupyter notebooks for experimentation vs Python files for real code

**0.4 Model access strategy for learning**
- Free/cheap API providers (Groq, Google AI Studio free tier, OpenRouter free models)
- Local models via Ollama (install, model pulls, when local is good enough)
- Cost hygiene from day one (spending caps, cheap models while learning)

**0.5 Your running project**
- Define the Research Copilot spec: tenants, document knowledge bases, web research agent, chat UI (API-only in this course)

---

## Module 1 — LLM Fundamentals & Mental Models *(6–8h)*
*Prereqs: Module 0 · You build: intuition layer (no code dependencies yet)*

**1.1 Mechanics**
- Tokens (tiktoken playground), context windows, why costs scale per token
- Sampling: temperature, top-p, max tokens, stop sequences; determinism and seeds

**1.2 The chat paradigm**
- System/user/assistant/tool roles; conversation as a list of messages
- Multimodal inputs (images); reasoning models vs standard models

**1.3 How tool calling really works**
- The protocol loop: model emits structured call → *you* execute → return result → model continues
- Parallel tool calls; why this is the foundation of all agents

**1.4 Structured output**
- Constrained decoding (JSON schema mode) vs prompt-and-pray parsing; why schemas + Pydantic matter

**1.5 Embeddings intuition**
- Vectors, cosine similarity, dimensions, why embeddings power search and memory

**1.6 Failure modes you'll engineer against forever**
- Hallucination, context rot, truncation, refusals, rate limits, non-determinism in tests

**1.7 Provider landscape**
- OpenAI/Anthropic/Google; open-weight families (Llama, Qwen, Mistral, DeepSeek); inference APIs (Groq, Together, Fireworks); local runtimes (Ollama, vLLM) and their trade-offs

---

## Module 2 — Chat Models in LangChain *(8–10h)*
*Prereqs: Module 1 · You build: model provider layer with streaming, retries, cost accounting, and tests*

**2.1 The standard chat model interface (`langchain-core`)**
- `BaseChatModel`: `invoke`/`stream`/`batch`, async everywhere (`ainvoke`/`astream`)
- Messages (`SystemMessage`, `HumanMessage`, `AIMessage`, `ToolMessage`), `usage_metadata`, standard params
- `.bind_tools()`, `.with_structured_output()`, `.with_retry()`, `.with_fallbacks()` — the chainable config pattern

**2.2 Instantiating models**
- `init_chat_model("provider:model")` — the provider-agnostic factory
- Partner packages; pointing `ChatOpenAI` at any OpenAI-compatible endpoint (Groq, OpenRouter, vLLM, LM Studio)
- Model-specific quirks that break tool calling (know which models do tools/structured output well)

**2.3 Ollama deep dive**
- Docker Compose service; model management, quantizations (Q4_K_M etc.), `keep_alive`, RAM math, embedding models (`nomic-embed-text`, `bge-m3`)
- Healthchecks, preloading models at startup

**2.4 LiteLLM gateway (optional but recommended)**
- Self-hosted proxy container: one endpoint for all providers, virtual keys, per-key budgets, fallbacks, spend tracking — your FOSS "model gateway"

**2.5 Streaming**
- Chunk anatomy; **accumulating streamed tool calls** (a classic gotcha); token counting during streams; stream options

**2.6 Resilience**
- Timeouts, retry-with-backoff, rate limit handling, fallback chains, circuit-breaking a provider

**2.7 Cost & token accounting**
- `usage_metadata` → your own usage ledger; feeding this to Langfuse later; per-request cost calculation

**2.8 Testing with fakes**
- `FakeChatModel`, `GenericFakeChatModel`, `FakeMessagesListChatModel`, fake tool calls; deterministic tests from day one

---

## Module 3 — Prompts & Structured Outputs *(6–8h)*
*Prereqs: Module 2 · You build: an extraction pipeline (messy input → validated Pydantic objects) with retries and tests*

**3.1 Prompt templates**
- `ChatPromptTemplate.from_messages`, `MessagesPlaceholder`, partials, few-shot examples
- Templates vs raw strings; why templates belong in files/version control

**3.2 Production prompt design**
- Role/constraints/format/examples structure; context budgeting; common anti-patterns (prompt stuffing)

**3.3 Structured outputs deep dive**
- `with_structured_output(Model)`: JSON-schema method vs tool-calling method; strict mode caveats
- Designing Pydantic models LLMs fill well: optionals, defaults, enums, nested models, descriptions as steering
- Validation failure → repair loop (re-prompt with error)

**3.4 Output parsers**
- `PydanticOutputParser`, `JsonOutputParser`, `OutputFixingParser`, parsing markdown-fenced JSON

**3.5 Prompt versioning & testing preview**
- The problem prompts-as-strings create in prod; local file convention now, Langfuse prompt management later; first taste of `promptfoo`

---

## Module 4 — Documents, Loaders & Chunking *(6–8h)*
*Prereqs: Module 3 · You build: an ingestion CLI pipeline (folders/PDFs/URLs → cleaned, de-duplicated chunks with stable IDs → JSONL)*

**4.1 The Document model**
- `page_content` + `metadata` everywhere; loaders overview (directory, web, GitHub)

**4.2 Parsing real-world files**
- PDF: `pypdf` vs `pymupdf4llm` vs `docling` vs `unstructured` vs `MarkItDown` — trade-offs, tables, OCR (tesseract)
- Choosing one stack and standardizing its output to Markdown

**4.3 Web content**
- `trafilatura` for main-content extraction; sitemap crawling; `crawlee-python` for serious crawling; robots.txt etiquette

**4.4 Text splitting**
- `RecursiveCharacterTextSplitter`, `MarkdownHeaderTextSplitter`, `HTMLHeaderTextSplitter`, token-based splitters (tiktoken)
- Chunk size/overlap tuning; structure-aware splitting (headers, tables) vs character splitting
- Experimental semantic chunking (awareness only)

**4.5 Chunk metadata & identity**
- Source, section, page, permissions, timestamps; **deterministic IDs for idempotent re-upserts** (stable UUIDs from source+hash)

**4.6 Incremental ingestion**
- Content hashing for change detection; store raw originals; reprocess only deltas

**4.7 Cleaning & dedup**
- Exact dedup (hashes), near-dup (embedding similarity), boilerplate stripping

---

## Module 5 — Embeddings & Vector Stores *(8–10h)*
*Prereqs: Module 4 · You build: a pgvector-backed index service with upsert API and search endpoints*

**5.1 Embeddings interface**
- `embed_documents`/`embed_query`, async, batching, cost; **never mix embedding models in one index**

**5.2 Choosing embeddings**
- Local: Ollama `nomic-embed-text`, `bge-m3`, `sentence-transformers` via `langchain-huggingface` vs API; MTEB benchmark; dimensions; multilingual needs

**5.3 pgvector deep dive (your unfair advantage — you know Postgres)**
- Extension setup, `vector` columns, HNSW vs IVFFlat, cosine vs inner-product (normalization!), tuning HNSW params
- `langchain-postgres` (`PGVector`): connection pooling, async support, metadata filtering
- **Multi-tenant isolation via Row-Level Security + metadata filters**
- Hybrid potential: `tsvector` full-text + vector in one query

**5.4 Qdrant (and when to prefer it)**
- Docker service, `langchain-qdrant`, payload filters, built-in hybrid sparse+dense, server-side rerank

**5.5 Chroma/FAISS quick tour**
- Prototyping vs production roles

**5.6 Search methods**
- Similarity vs MMR vs score thresholds; upserts vs re-add; delete-by-filter; `MultiVectorRetriever` (child chunks + parent pointers)

**5.7 Index lifecycle**
- Re-index strategy on embedding model change; backups (`pg_dump`); dimension migrations

**5.8 Connection management in services**
- Singleton clients, pool lifecycle in FastAPI lifespan, avoiding per-request init

---

## Module 6 — Retrieval-Augmented Generation *(10–12h)*
*Prereqs: Module 5 · You build: full production RAG service: hybrid retrieval + rerank + citations + graceful "I don't know" + query cache*

**6.1 Naive RAG**
- LCEL chain: retrieve → stuff → answer; source citation basics; score thresholds

**6.2 Query transformation**
- Multi-query, decomposition, step-back prompting, HyDE, query routing to different indexes

**6.3 Hybrid search**
- BM25 (`rank_bm25`) + dense; `EnsembleRetriever` with reciprocal rank fusion; pgvector full-text + vector fusion

**6.4 Reranking**
- Cross-encoders (`bge-reranker-v2-m3` via sentence-transformers/FlagEmbedding or Qdrant's server-side rerank); where rerankers run in your stack; latency budget

**6.5 Context engineering**
- Parent-document retriever; contextual compression (LLM extractors, embeddings filters); Anthropic-style "contextual retrieval" (chunk-context enrichment); sentence-window retrieval

**6.6 Metadata-driven retrieval**
- Self-querying retriever (natural language → structured filters); tenant/date filters

**6.7 Grounding & citations**
- Footnoted answers from retrieved chunks; quote-level attribution; refusing when context is insufficient

**6.8 Production retrieval design**
- Latency budgets per stage; Redis query-result caching; freshness/re-embedding schedules; fallback when search fails

**6.9 Advanced awareness**
- GraphRAG/LightRAG concept overview; late-interaction (ColBERT) awareness — enough to evaluate hype

---

## Module 7 — Tools & Function Calling *(8–10h)*
*Prereqs: Module 2 · You build: your app's toolkit — SearXNG web search, knowledge-base query, read-only DB tool — plus one FastMCP server*

**7.1 Defining tools**
- `@tool` decorator: Pydantic arg schemas, docstrings as the model's API docs, async tools, `StructuredTool`
- Tool artifacts (return rich data for the *app* while returning text for the *model*)

**7.2 Tool design principles**
- Narrow, single-purpose tools; errors as *return values* not exceptions; deterministic IDs; output size limits; idempotency

**7.3 Binding & executing**
- `bind_tools`, `tool_choice`, parallel calls, parsing streamed tool-call chunks; dispatching calls safely

**7.4 Tool security**
- Allowlists; input validation; **indirect prompt injection via tool output** (defenses: truncation, neutral formatting, trust labels); timeouts

**7.5 Real-world tool patterns**
- HTTP tools with httpx (timeouts, retries, SSRF protection, URL allowlists)
- DB tools: read-only role, describe-schema-first, query timeouts, SQL injection
- Self-hosted web search: **SearXNG** (FOSS, JSON API) — your search backbone
- Math/date/utility tools; why small utility tools matter

**7.6 Code execution tools**
- `PythonREPL` dangers; sandboxed execution design (dedicated container, no network, resource caps) — full treatment in the safety module

**7.7 Testing tools**
- Unit tests, httpx mocking, golden fixtures

**7.8 MCP (Model Context Protocol)**
- Concepts: servers, clients, tools/resources/prompts; stdio vs streamable-HTTP transports
- Building servers with **FastMCP**; consuming MCP tools via `langchain-mcp-adapters`
- Security model: trusting servers, validating tool args, network isolation
- When to use MCP vs plain LangChain tools (interoperability vs simplicity)

---

## Module 8 — Agents with LangChain `create_agent` + Middleware *(10–12h)*
*Prereqs: Modules 3, 6, 7 · You build: upgrade your RAG service into an agentic assistant with HITL approvals, summary memory, retries, and cost caps*

**8.1 Agent mental models**
- ReAct loop; the tool-calling loop as a while-loop; what `create_agent` (LangChain v1) actually is: a LangGraph graph you can inspect

**8.2 `create_agent` fundamentals**
- Model, tools, system prompt, `max_steps`, structured final answers (`response_format`), stopping conditions

**8.3 Streaming agents**
- `stream_mode` values/messages/tokens; streaming intermediate steps to an API; astream_events

**8.4 The middleware system (the killer feature of v1)**
- Middleware anatomy: `before_model`/`after_model`/`before_tool`/`after_tool`, `wrap_model_call`, `wrap_tool_call`, injecting dynamic system prompts
- Built-ins: `HumanInTheLoopMiddleware` (tool approvals, `ToolDeniedError`), `SummarizationMiddleware`, `TrimmingMiddleware`, `RetryMiddleware`, `LiteLLMModel`, `CheapestModel`, `ModelRouter`, `PlanAndExecute`, `AgentInterrupt` — plus the experimental ones (check current docs)
- Writing custom middleware: audit logging, budget enforcement, tenant context injection, guardrails

**8.5 Loop control**
- Runaway agents: step caps, token budget middleware, duplicate-call detection

**8.6 Agent memory**
- `create_agent` + checkpointer + store (it's a graph — pass them through); conversation persistence preview (full treatment in Module 11)

**8.7 Legacy recognition**
- `create_react_agent` (old prebuilt): recognizing it in the wild, migrating from it

---

## Module 9 — LangGraph Fundamentals *(10–12h)*
*Prereqs: Module 8 · You build: a deterministic multi-step workflow (ingest → retrieve → grade → rewrite loop → answer) with transition tests*

**9.1 Why graphs**
- Explicit control flow vs implicit agent loops; when an agent vs when a graph; StateGraph vs functional API

**9.2 State**
- TypedDict/Pydantic/dataclass state; **reducers** (`Annotated` + `operator.add`, `add_messages`, custom reducers — the #1 confusion point)
- Input/output schema separation (private keys)

**9.3 Building graphs**
- `add_node`, `add_edge`, `add_conditional_edges` (routers, path maps), START/END, `compile()`
- Visualizing with Mermaid (`get_graph().draw_mermaid()`); reading the state diagram

**9.4 Invocation & config**
- `thread_id`, `recursion_limit`, `configurable`, batch; `GraphRecursionError`

**9.5 Subgraphs**
- State mapping parent↔child; subgraph-as-node; when subgraph vs function

**9.6 Parallelism**
- Fan-out via multiple edges + reducer fan-in; **`Send` API for dynamic map-reduce**; ordering semantics

**9.7 The functional API**
- `@entrypoint` / `@task`; wrapping existing imperative code; mixing with StateGraph; when to prefer

**9.8 Async-first**
- Async nodes, `ainvoke`/`astream`; blocking-in-async pitfalls

**9.9 Dev tooling**
- `langgraph dev` local server + LangGraph Studio for visual inspection of state at every step (free dev tools)

---

## Module 10 — Persistence, Memory & Human-in-the-Loop *(10–12h)*
*Prereqs: Module 9 · You build: chat with persistent threads, approval flows, and long-term user memory — all in Postgres*

**10.1 Checkpointer architecture**
- What a checkpoint contains (values, next, versions); threads; per-superstep saves; why this gives you durability + time travel + HITL for free

**10.2 Postgres checkpointer**
- `langgraph-checkpoint-postgres` (`PostgresSaver`): setup, schema, psycopg connection pooling, connection lifecycle in services; the community Redis saver and when you'd want it

**10.3 State manipulation & time travel**
- `get_state`, `update_state`, checkpoint history, forking, replaying from a past checkpoint; debugging prod issues by replaying

**10.4 Durability & reliability**
- Durability modes (`durability=` sync/async/exit); per-node `RetryPolicy`; crash-recovery semantics; designing idempotent nodes

**10.5 Human-in-the-loop**
- Static breakpoints (`interrupt_before/after`), dynamic `NodeInterrupt`, `interrupt()` in functional API
- Resuming with `Command(resume=...)`; editing state before resume; approval timeout sweepers (a production pattern you'll reuse)

**10.6 Short-term memory**
- Thread-scoped message history; trimming; summarization of long conversations

**10.7 Long-term memory**
- `BaseStore`, namespaces, **`PostgresStore`** (with semantic search over memories), put/get/search/delete
- **`langmem`**: memory extraction tools, background memory formation, memory management
- Memory design: facts vs preferences vs procedures; what to store vs re-derive

**10.8 Multi-user/multi-tenant memory**
- `user_id`-scoped namespaces; isolating memories per tenant; RBAC on store access

**10.9 Data lifecycle**
- Thread/checkpoint TTL cleanup; GDPR-style deletion of a user's threads + memories + traces (Langfuse APIs)

---

## Module 11 — Advanced LangGraph & Production Patterns *(8–10h)*
*Prereqs: Module 10 · You build: a resumable, cancellable, testcontainers-tested workflow service*

**11.1 Streaming deep dive**
- All `stream_mode` values (values, updates, messages, custom, debug, subgraphs), combining modes, filtering; token streaming from nested nodes; designing your streaming event schema

**11.2 Control flow**
- `Command(goto=...)` navigation; dynamic routing; handoffs between nodes; loops with conditions

**11.3 Long-running agents in production**
- Graph execution in background workers; webhook/endpoint-triggered resume; run status tracking (Postgres/Redis); the "pending approval" state machine

**11.4 Testing graphs**
- Deterministic step assertions with fake models; state snapshots; testing interrupt/resume flows; **testcontainers-python** for real Postgres checkpointer tests in CI

**11.5 Performance**
- Minimizing supersteps; caching expensive nodes; parallel retrieval; connection pools; profiling

**11.6 Deployment models — the decision**
- Custom FastAPI runtime (your FOSS route: compiled graph + checkpointer behind your own API) vs LangGraph Platform/agent server (what it adds: run management, double-texting, studio-in-prod; licensing reality) — why custom runtime fits your stack

---

## Module 12 — Multi-Agent Systems *(8–10h)*
*Prereqs: Modules 8–11 · You build: a research team — supervisor + web researcher + doc analyst + writer — with HITL outline approval*

**12.1 When multi-agent**
- Cost/latency/complexity trade-offs; "single agent + good tools" as the default; topologies: supervisor, hierarchical, swarm/handoffs, pipeline

**12.2 Supervisor pattern**
- Hand-built supervisor in LangGraph (shared state, routing via tool calls or structured output); `langgraph-supervisor` prebuilt; task handoff message design

**12.3 Swarm/handoff pattern**
- Agents-as-tools vs `Command`-based handoffs; `langgraph-swarm` prebuilt; **state filters** (what transfers between agents)

**12.4 Hierarchical teams**
- Supervisor-of-supervisors; progress reporting patterns; failure escalation up the tree

**12.5 Shared state & communication design**
- Team state schemas; avoiding prompt-stuffing via shared filesystem/store/scratchpad; artifacts as the inter-agent medium (deep agents preview)

**12.6 Parallelism & aggregation**
- `Send` fan-out; merging; judge/vote aggregation of multiple agents' outputs

**12.7 Cross-cutting concerns**
- Persistence across agents; per-agent token budgets; tracing multi-agent runs in Langfuse; debugging with subgraph streaming

**12.8 Evaluating multi-agent behavior**
- Trajectory evaluation with `agentevals`; per-agent quality metrics (full treatment in Module 17)

---

## Module 13 — Deep Agents *(10–12h)*
*Prereqs: Modules 8–12 · You build: a deep research agent over your RAG + web — plan approval, parallel subagents, artifact export, resumable sessions*

**13.1 The deep agent system**
- The pattern (Anthropic's "deep agents" research): **planning (todos), subagents as tools, virtual filesystem for artifacts, intermediate thinking, persistence, background tasks**
- Deep agents vs plain agent vs multi-agent graph — when each wins

**13.2 `deepagents` quickstart**
- `create_deep_agent`, built-in tools (todo, filesystem, Task), default system prompt, backend/model selection (LiteLLM backend — any provider incl. Ollama)

**13.3 The virtual filesystem**
- State-backed FS vs real FS; customizing storage (persist artifacts to Postgres/MinIO); path safety; exporting artifacts to users

**13.4 Subagents via the Task tool**
- Each subagent = fresh context + own tools; custom subagents dict (name/prompt/tools); **parallel subagents**; per-subagent model routing; returning files as results

**13.5 Planning & todos**
- How the todo list steers long tasks; customizing planning prompts; HITL on the plan (interrupt before execution)

**13.6 Background tasks & notifications**
- Async task delegation, notification tool, polling progress; cost control for background work

**13.7 Integrations**
- `browser-use` (OSS browser control) for web research; SearXNG search; MCP tools inside deep agents; note on custom backends (e.g., Claude Agent SDK) and their licensing

**13.8 Customization & hardening**
- Rewriting the system prompt; adding middleware (HITL, summarization, retry, budget caps); checkpointers for resumable research sessions

**13.9 Production deep agent**
- Budget caps per run, timeouts, streaming progress events (plan/todo/tool events as SSE), per-subagent Langfuse tracing, cost-per-run measurement

---

## Module 14 — Langfuse: Self-Hosting & Fundamentals *(8–10h)*
*Prereqs: Docker Compose (yours) · You build: Langfuse v3 running in your Compose stack, behind Cloudflare Tunnel, with your app traced and prompts migrated into it*

**14.1 Why LLM observability**
- Langfuse vs LangSmith (what you gain/lose going OSS); traces → spans → generations; scores, datasets, sessions, users, prompt versions

**14.2 v3 architecture & deployment**
- Services (web + worker), **ClickHouse** (trace store), Postgres (app data), Redis (queue/cache), S3/MinIO (blobs); official docker-compose; required env vars (auth, encryption key, salt)
- Integrating into *your* compose: shared vs isolated Postgres, resource sizing (RAM is real), healthchecks, upgrade procedure

**14.3 Exposing & securing it**
- Cloudflare tunnel routing; Cloudflare Zero Trust Access in front of the Langfuse UI (free tier); API keys (service-level vs personal); OIDC SSO options

**14.4 Python SDK tracing**
- `@observe` decorator (nested spans/generations), context managers, low-level API, async
- Recording inputs/outputs, metadata, latency, usage; sessions & user IDs; trace ID propagation into your app logs
- Cost tracking: model pricing definitions (including your Ollama/self-hosted models — priced at 0 or estimated)

**14.5 Cost & privacy controls**
- Trace sampling rates; masking/redacting sensitive fields; ingestion queue tuning; what "free self-hosted" does/doesn't include (open-core boundaries)

**14.6 Prompt management**
- Creating/iterating prompts in UI, versioning, **labels (production/staging/draft)**, `get_prompt()` + `.compile()` in code, rolling back, migrating your Module 3 prompts in

**14.7 Datasets & annotation**
- Golden sets, annotation queues, ingesting user feedback as scores via API

**14.8 Langfuse ops**
- Backups (Postgres + ClickHouse + MinIO); retention/cleanup; monitoring queue depth; scaling workers

---

## Module 15 — Langfuse × LangChain/LangGraph Integration & Prompt Ops *(6–8h)*
*Prereqs: Modules 9, 14 · You build: end-to-end traced agent + user feedback endpoint + nightly LLM-as-judge eval job*

**15.1 The CallbackHandler**
- Attaching to `invoke`/`astream` config; tracing entire graphs *including subgraphs and every LLM/tool call*; per-run metadata (user, tenant, environment, thread)

**15.2 Correlation**
- Linking Langfuse traces to your request IDs/log lines; updating traces from your app; async ingestion & flush behavior; overhead measurement

**15.3 Custom spans & scores**
- Spanning business events (cache hit, approval wait, retrieval hit count); user feedback API → trace scores; building the feedback endpoint

**15.4 Evaluation pipelines**
- Datasets → run your graph → evaluators: LLM-as-judge (using open models via Ollama), custom Python evaluators, threshold-based pass/fail; experiment comparison views

**15.5 Prompt lifecycle ops**
- Dev → dataset eval → `staging` label → `production` label; diffs, rollback, A/B via labels; eliminating "prompt changed in code" incidents

**15.6 Alerting on quality drift**
- Scheduled evals (cron on your server) → thresholds → webhooks to **ntfy**/Telegram/email; dashboards for cost/latency/quality over time

---

## Module 16 — Evaluation & Testing Culture *(8–10h)*
*Prereqs: Modules 6, 8, 15 · You build: full CI quality pipeline — unit tests + RAGAS + trajectory evals + dataset regression gate in GitHub Actions*

**16.1 The LLM test pyramid**
- Unit (tools/parsers) → integration (graph steps) → e2e (agent trajectories) → offline evals → online monitoring; what CI can and can't catch

**16.2 pytest with test doubles**
- Fake chat models, fake embeddings, in-memory stores; monkeypatching models per test; deterministic trajectories

**16.3 RAGAS**
- Faithfulness, answer relevancy, context precision/recall; synthetic test-set generation; running against your RAG; interpreting and thresholding scores

**16.4 agentevals**
- Trajectory matching: exact vs LLM-as-judge subsets (tool-call sequences); authoring trajectory goldens; judging "did the agent take reasonable steps"

**16.5 promptfoo**
- Config-driven prompt/model/tool tests; assertion types (contains, llm-rubric, custom JS/Python); provider matrix (same prompt across models); **running as a GitHub Actions step**

**16.6 Langfuse datasets in CI**
- PR-triggered experiment runs vs main; posting score summaries; blocking regressions

**16.7 Performance & chaos testing**
- Locust load tests (p95 first-token latency, token throughput); killing a worker mid-run → verifying checkpoint recovery

---

## Module 17 — Safety, Guardrails & Privacy *(8–10h)*
*Prereqs: Modules 7, 8 · You build: security hardening pass — injection test suite, PII redaction middleware, sandboxed tool exec, audit trail*

**17.1 Threat model for agent SaaS**
- Direct & **indirect prompt injection** (via retrieved docs, tool outputs, web pages a subagent reads), jailbreaks, data exfil, tool abuse, memory poisoning; OWASP LLM Top 10 mapping

**17.2 Input guardrails**
- **Microsoft Presidio** for PII detection/anonymization before the LLM; **Llama Guard** via Ollama for moderation; custom validators; enforcing via `before_model` middleware

**17.3 Output guardrails**
- PII scanning outputs, secret detection, structured-output enforcement, citation requirements

**17.4 Tool hardening**
- Least-privilege DB roles, read-only SQL, URL allowlists + SSRF protection, per-user rate limits, argument schemas, trust-level labels on tool results

**17.5 Sandboxing execution**
- Docker-in-Docker sandbox: non-root, no network, seccomp, resource caps, ephemeral; awareness of gVisor/Firecracker-class isolation

**17.6 Retrieval poisoning defense**
- Provenance metadata, spotlighting/formatting data separately from instructions, trust levels per source

**17.7 Guardrail frameworks**
- NeMo Guardrails and Guardrails AI: what they solve, when custom middleware is simpler (usually, in your architecture)

**17.8 Human-in-the-loop as the final control**
- Approval requirements on risky tools; complete audit trail (Langfuse spans + DB records); kill switches; per-tenant emergency disable

---

## Module 18 — Serving Agents with FastAPI *(8–10h)*
*Prereqs: Modules 11, 13 (FastAPI itself you know — this is LLM-specific serving)*
*You build: production API layer around your deep agent — SSE streaming, approval endpoints, background jobs, quotas*

**18.1 SSE streaming**
- `StreamingResponse`/`sse-starlette`; bridging LangGraph `astream` to SSE; **backpressure and client-disconnect handling**; heartbeats; resume-from-last-event-ID (persisting event streams in Redis)

**18.2 WebSockets**
- When WS beats SSE (interruption, live updates); per-connection run management; propagating cancellation into a running graph (cancellation-token design)

**18.3 Long-running jobs**
- Offloading deep agent runs to **arq** workers (Redis-backed, simple, FOSS) vs Celery; job status endpoints; idempotency keys; **resume-from-checkpoint instead of blind retries**

**18.4 Multi-tenancy**
- JWT auth; tenant context propagation → graph config + Store namespaces + Langfuse metadata + metrics labels; Redis token-bucket rate limiting; per-tenant quotas/budgets

**18.5 App ↔ graph wiring**
- Dependency-injected graph/checkpointer singletons; lifespan-managed pools; request → thread mapping; conversation title generation; pagination of message history

**18.6 Observability wiring**
- structlog JSON logs with trace-ID correlation; GlitchTip (OSS, Sentry-API compatible) for errors; Prometheus metrics (`prometheus-fastapi-instrumentator`): tokens, cost, cache hits, run durations, queue depth

**18.7 The agent event protocol**
- Designing your SSE event schema (token / thought / tool_call / tool_result / artifact / approval_request / done) — the contract your future frontend will consume

---

## Module 19 — Deployment & Operations on Your Stack *(10–12h)*
*Prereqs: Module 18 · You build: the whole system live on Ubuntu behind Cloudflare Tunnel, with CI/CD, backups, monitoring, and a restore drill*

**19.1 Reference architecture (single host, Compose)**
- cloudflared (tunnel edge) → FastAPI app + arq worker → Postgres, Redis, Ollama → Langfuse stack (web, worker, ClickHouse, its Postgres, MinIO); network segmentation (frontend/backend zones); only the tunnel touches the internet

**19.2 Containerization with uv**
- Multi-stage Dockerfile (`uv sync --frozen`), slim images, non-root, healthchecks, compose base + prod/dev overrides, GHCR tagging strategy

**19.3 CI/CD (GitHub Actions → GHCR → server)**
- Build → test (testcontainers services) → push → deploy job (SSH, `compose pull && up -d`, migrations, smoke tests, rollback to previous tag); controlled deploys vs Watchtower trade-offs

**19.4 Cloudflare Tunnel specifics**
- cloudflared as a Compose service with tunnel token; DNS routing; Zero Trust Access guarding Langfuse/Grafana admin UIs; SSE/WebSocket support; WAF basics

**19.5 Data-layer ops**
- Postgres backups (`pg_dump` → restic → MinIO/S3); ClickHouse + MinIO backups; Redis persistence/eviction; **restore drills (an untested backup isn't a backup)**; connection pooling (pgbouncer) when workers multiply

**19.6 Monitoring & alerting (the FOSS "LangSmith Fleet")**
- Prometheus + node/cAdvisor/Postgres/Redis exporters; Grafana dashboards (tokens, cost, latency, error rate, queue depth, agent success rate); Alertmanager → ntfy/Telegram; Uptime Kuma external probes; optional Loki for logs

**19.7 Model serving ops**
- Ollama in Compose: model preloading, `keep_alive`, RAM budgeting, CPU-only reality check; when to move to vLLM (OpenAI-compatible, throughput); or API-only via LiteLLM gateway (keys, budgets, fallbacks) — the pragmatic split

**19.8 Host hardening**
- ufw, SSH keys only, unattended-upgrades, Docker Bench, non-root services, restart policies, capacity math (ClickHouse + Postgres + Ollama + app on one box)

**19.9 Runbooks**
- Runaway-agent playbook (detect via metrics → kill → disable tool → notify), cost-spike playbook, restore procedure, dependency-down playbook

---

## Module 20 — Cost, Performance & Scaling *(6–8h)*
*Prereqs: Module 19 · You build: tuning pass — caching, model routing, budgets — with before/after cost-per-request numbers*

**20.1 Cost anatomy**
- Token math for agent loops (context grows every step); tool-result bloat; measuring real cost via Langfuse

**20.2 Caching**
- LangChain LLM cache (`set_llm_cache` with Redis) — exact-match only; semantic cache caveats; provider prompt caching (Anthropic cache control, OpenAI automatic) and how to actually get hits (stable prompt prefixes)

**20.3 Context engineering (the modern skill)**
- Trim/summarize history; retrieve-into-context instead of dumping memory; tool-output truncation; **the filesystem/artifacts pattern as external context** (deep agents' trick) for very long tasks

**20.4 Model routing & cascades**
- Cheap-model-first (`CheapestModel`, `ModelRouter` middleware, LiteLLM router): easy queries → small, hard → large; batch APIs for bulk jobs; fallback chains

**20.5 Latency**
- First-token time; parallelize (tools, `Send` fan-out, async retrieval); Ollama `keep_alive` and quantization trade-offs

**20.6 Throughput & concurrency**
- Redis semaphores per provider; queue-depth control in arq; uvicorn workers vs worker replicas; when a second host (dedicated to model serving) makes sense

**20.7 Data-layer scaling**
- pgvector HNSW tuning (`ef_search`), table partitioning by tenant, pgbouncer, ClickHouse retention

**20.8 Unit economics**
- Cost per tenant, per run, per query; budget alerts; when features become unaffordable; re-evaluating the custom-runtime vs LangGraph Platform trade-off at scale

---

## Module 21 — Capstone: Production AI SaaS *(30–40h)*
*Prereqs: everything · You build: the complete Research Copilot SaaS, deployed*

**21.1 Spec & architecture** — multi-tenant, plan tiers, credit system; full system diagram
**21.2 Data model** — tenants, users, conversations/threads, runs, messages, documents, artifacts, approvals, usage ledger (Postgres + LangGraph + Langfuse)
**21.3 Agent core** — deepagents research agent (RAG + SearXNG + browser-use), middleware stack (authorization, HITL, summarization, retry, budget), PostgresSaver + PostgresStore + langmem, MCP for pluggable integrations
**21.4 Serving layer** — SSE + WS, arq deep-research jobs, approval/feedback/resume endpoints, quotas
**21.5 Observability & evals** — per-tenant tracing, prompt labels, nightly evals, dashboards, drift alerts
**21.6 Security** — injection test suite passing, PII redaction, sandboxed tools, retention/deletion jobs, audit trail
**21.7 Deployment** — full Compose + CI/CD + backups + monitoring from Module 19, plus restore drill and load test results
**21.8 Launch checklist** — ~50-item production readiness review (secrets, migrations, rollback, cost caps, ToS/privacy basics)
**21.9 Stretch** — MCP plugin surface for tenant integrations; Stripe metering design (not FOSS, but the standard); i18n

---

## Module 22 — Staying Current *(ongoing)*
**22.1** Following the ecosystem: release notes for `langchain`/`langgraph`/`deepagents`/`langfuse`; changelog-reading habits
**22.2** Migration discipline: pinned `uv` lockfile, upgrade cadence, your test suite as the safety net for API churn
**22.3** Watch list: MCP evolution, agent-to-agent protocols, memory standardization, local-model quality trajectory

---

# How to Use This Course with an AI Tutor

Paste the module text plus a prompt like:

> "Teach me Module N (pasted below) from my LangChain production course. I already know Python, Pydantic, FastAPI, Postgres, Redis, Docker, and Compose — skip those fundamentals. Teach submodule by submodule: (1) concept, (2) minimal runnable code using `uv` with current library versions — verify every API against current docs and explicitly warn me if something may have changed, (3) a common pitfall, (4) 2–3 exercises, then quiz me. Prefer FOSS integrations: Ollama, pgvector, Langfuse, SearXNG. My running project is [one-liner]; end the module by extending it."

**Three rules that will save you months:**
1. **Always pin and check versions.** This ecosystem deprecates APIs aggressively. Whenever the tutor gives code, ask: "does this use the current 1.x API or a deprecated 0.x pattern?"
2. **Trust tests over tutorials.** Most online LangChain content is one or two major versions behind. The official docs + running code are ground truth.
3. **Deploy Langfuse after Module 2** (pull Module 14.2–14.4 forward if you want) — tracing everything you build from early on makes every later module dramatically easier to debug.

**Suggested pacing:** Modules 0–3 (week 1–2), 4–6 (weeks 3–4), 7–8 (week 5), 9–11 (weeks 6–7), 12–13 (week 8), 14–16 (weeks 9–10), 17–19 (weeks 11–12), 20–21 (weeks 13+). Roughly 200–250 hours total to genuinely production-ready — faster if you lean on your existing backend strengths.

Want me to expand any single module into a full lesson right now to show you what the AI-tutor sessions will look like?
