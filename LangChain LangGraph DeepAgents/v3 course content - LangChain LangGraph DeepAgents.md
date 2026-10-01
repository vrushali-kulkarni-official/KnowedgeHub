# LangChain · LangGraph · Deep Agents · Langfuse — Updated Course

> **Legend:** 🔄 = item replaced or updated because the original was outdated, deprecated, renamed, or non-existent. Everything without 🔄 is unchanged.
> **Checked against docs on 29 Sep 2026:** `langchain` 1.3.x, `langgraph` ≥ 1.1, `deepagents` ≥ 0.6, Langfuse Python SDK v4 / self-hosted server v4.

---

## PHASE 0 — Orientation & LLM Mental Models

**M1 · The ecosystem map & the version problem** — 1.5h
- Package split: `langchain-core` vs `langchain` v1 vs `langchain-classic` vs partner packages vs `langchain-community` — what lives where, why the split exists
- 🔄 What's OSS vs closed: LangSmith, **LangSmith Fleet** (no-code agent builder, formerly Agent Builder), **LangSmith Deployment / Agent Server** (formerly LangGraph Platform, renamed Oct 2025) → your substitutes (Langfuse, custom FastAPI runtime, Prometheus/Grafana)
- 🔄 Version history 0.1 → 0.2/0.3 → 1.x: what died (`LLMChain`, `initialize_agent`, `AgentExecutor`, `langgraph.prebuilt.create_react_agent` with `prompt=` / `pre_model_hook` / `post_model_hook`) and what replaced each
- **⚠️ The #1 beginner trap:** 90% of tutorials teach dead APIs — 🔄 the tell-tale imports to recognize (`langchain.chains`, `agent=` params, `ConversationalRetrievalChain`, `langchain.retrievers`, `from langgraph.prebuilt import create_react_agent`, `from langfuse.decorators import observe`, `from langfuse.callback import CallbackHandler`)
- Canonical sources only: `docs.langchain.com`, `langchain-ai/*` GitHub, changelogs

**M2 · Project setup with uv** — 1.5h
- `uv init`, src-layout, separate `app/` (FastAPI) and `agent/` (LangChain) packages; Jupyter via `uv run` for experiments
- `pydantic-settings` Settings class, `.env`, secrets hygiene
- Lockfile discipline: `uv lock`, why pinning matters in a fast-deprecating ecosystem; deliberate upgrades
- *Build:* Research Copilot repo skeleton with run/test/lint tasks

**M3 · LLM mechanics** — 2h
- Tokens (tiktoken), context windows, per-token in/out pricing
- Sampling: temperature, top_p, max_tokens, stop, seeds & non-determinism
- Multimodal inputs; reasoning models vs standard models (when each)
- Failure-mode catalogue you'll engineer against forever: hallucination, context rot, truncation, refusals, rate limits
- Provider landscape: OpenAI/Anthropic/Google; open weights (Llama, Qwen, Mistral, DeepSeek); free/cheap inference (Groq, Google AI Studio, OpenRouter free tier); local runtimes (Ollama, vLLM)

**M4 · Messages & the tool-calling protocol** — 2h
- The message list as universal state: system/user/assistant/tool roles; conversation = list of messages
- The protocol loop: model emits structured tool call → *your app* executes → `ToolMessage` result → model continues; parallel calls
- Mental model you'll keep forever: an agent = a while-loop around this protocol (this is literally what `create_agent` is)
- Trace a full multi-turn tool conversation by hand, on paper, before writing any code

**M5 · Structured output & embeddings intuition** — 1.5h
- Constrained decoding (JSON schema mode) vs prompt-and-parse; Pydantic schema as the contract
- Embeddings: vectors, cosine similarity, dimensions; what they enable (search, memory, dedup)
- Choosing structured output vs tool calls for extraction
- **⚠️ Foreshadow:** never mix embedding models in one index

**M6 · Research Copilot spec** — 1h
- Full spec: multi-tenant SaaS, per-tenant document KBs, web research agent, chat API, plan tiers, credit system
- Draw the target architecture — you'll build toward it for 120 modules
- Map each future module to a feature increment

---

## PHASE 1 — Models, Prompts & the Config Layer

**M7 · First chat model calls** — 2.5h
- `init_chat_model("provider:model")` factory; partner packages; pointing `ChatOpenAI` at any OpenAI-compatible `base_url` (Groq, OpenRouter, LM Studio, vLLM)
- `invoke`/`stream`/`batch` + async twins; `AIMessage` anatomy: `content`, `tool_calls`, `usage_metadata`, `id`, `response_metadata`
- Standard params; build a token/cost ledger from `usage_metadata`
- *Build:* `models.py` provider layer + cost ledger + CLI chat script

**M8 · The config layer** — 2.5h
- `.bind_tools()` + `tool_choice`; `.with_structured_output(Model, method="json_schema" | "function_calling")`
- `.with_retry()`, `.with_fallbacks()`, timeouts, rate-limit-aware backoff
- `RunnableConfig`: `tags`, `metadata`, `run_name`, `configurable`, `recursion_limit` (preview of LangGraph)
- **⚠️** Which models do tools/strict JSON poorly (incl. quantized local models) — pick per task

**M9 · Streaming deep dive** — 2.5h
- `AIMessageChunk` anatomy; content chunks vs `tool_call_chunks`
- **⚠️ The classic gotcha:** accumulating streamed tool-call chunks into complete calls
- Token counting from the final chunk (`stream_usage`/`include_usage` per provider)
- *Build:* streaming CLI that prints tokens live and reconstructs tool calls correctly

**M10 · Ollama for development** — 2.5h
- Compose service; model pulls; quantization tags (`q4_K_M` etc.) and RAM math; `keep_alive`
- `ChatOllama`, `OllamaEmbeddings`; OpenAI-compatible mode; healthchecks + model preloading at startup
- When local is good enough: dev, tests, eval judges, privacy
- **⚠️** Quantized open models are weaker at tool calling — choose dev models accordingly

**M11 · LiteLLM gateway** *(optional but recommended)* — 2h
- Self-hosted proxy container: one OpenAI-compatible endpoint for all providers
- Virtual keys, per-key budgets, spend tracking, fallbacks, routing rules
- Why this becomes your production model gateway (keys never touch your app)
- *Build:* compose service + config; app now talks only to LiteLLM

**M12 · Fake models & model-layer testing** — 1.5h
- `FakeChatModel`, `GenericFakeChatModel`, `FakeMessagesListChatModel`, fake tools; canned tool-call sequences
- Deterministic unit tests for anything that calls a model; golden fixtures
- Pytest markers: `unit` (no network) / `integration` (real API) / `local` (Ollama)
- *Build:* conftest with fakes; first CI run

**M13 · Prompt templates & production prompt design** — 3h
- `ChatPromptTemplate.from_messages`, `MessagesPlaceholder`, partials, few-shot examples
- Templates as files in the repo vs strings in code; reviewable prompt diffs
- Structure: role → task → constraints → format spec → examples; context budgeting; anti-patterns (prompt stuffing, contradictory instructions)
- Foreshadow Langfuse prompt management (M84)

**M14 · Structured outputs deep dive** — 3h
- Schema design LLMs fill well: optionals, defaults, enums, nested models, **field descriptions as steering**
- Method trade-offs; strict mode; token cost of schemas
- Validation failure → repair loop: re-prompt with the Pydantic error; max-retry policy
- *Build:* extraction pipeline (messy markdown → validated Pydantic objects) with repair loop + fake-model tests

**M15 · Output parsers** — 1.5h
- `PydanticOutputParser`, `JsonOutputParser`, `get_format_instructions`
- 🔄 `OutputFixingParser` (now lives in `langchain-classic`; prefer your M14 repair loop); parsing fenced JSON from chatty models
- Why parsers still matter: local/non-tool-calling models, agent intermediate output

**M16 · LCEL & Runnables** — 2.5h
- Pipe syntax, `RunnableLambda`, `RunnablePassthrough`, `.assign()`, the classic RAG LCEL pattern
- `batch`/async/stream on any chain; `RunnableConfig` propagation
- LCEL's role in 1.x: chains *inside* graph nodes — not the whole app
- *Build:* extraction chain as pure LCEL

**M17 · Bootstrap Langfuse now (minimum viable observability)** — 2h
- Why tracing from day one makes every later module debuggable — do this before RAG
- 🔄 Deploy the official Langfuse compose stack with defaults (server **v4** is GA for self-hosting; components unchanged: web, worker, ClickHouse ≥ 25.12, Postgres, Redis, MinIO — no tuning yet; full treatment in Phase 12)
- 🔄 SDK basics: `from langfuse import observe, get_client` (not `langfuse.decorators`); recording input/output/metadata
- *Build:* your CLI scripts and chains traced; first traces in the UI

---

## PHASE 2 — Ingestion

**M18 · The Document model & core loaders** — 1.5h
- `Document` = `page_content` + `metadata` — the universal currency of the ecosystem
- `DirectoryLoader`, `TextLoader`, `WebBaseLoader`, GitHub ingestion (clone + DirectoryLoader)
- The pipeline shape: load → split → embed → store
- *Build:* ingest CLI skeleton (typer) emitting JSONL of Documents

**M19 · Parsing PDFs & office docs** — 2.5h
- `pypdf` vs `pymupdf4llm` vs Microsoft's `MarkItDown` vs `docling` vs `unstructured` — trade-offs
- Tables, scanned PDFs, OCR (tesseract), page-level metadata; standardizing all output to Markdown
- Per-filetype routing with fallbacks
- *Build:* PDF → Markdown pipeline + a fixtures folder of nasty PDFs

**M20 · Web content: extraction & crawling** — 2h
- `trafilatura` main-content extraction; robots.txt etiquette, rate limits, UA
- Sitemap crawling; `crawlee-python` (Playwright) for JS-heavy sites
- URL dedup; HTML structure as splitting signal
- *Build:* URL/sitemap → Documents CLI

**M21 · Text splitting** — 2.5h
- `RecursiveCharacterTextSplitter` mechanics (separator hierarchy); token-based splitting with tiktoken
- Chunk size/overlap: why structure-awareness beats magic numbers
- `MarkdownHeaderTextSplitter`, `HTMLHeaderTextSplitter`, code splitters
- Semantic chunking — awareness only (cost/benefit)

**M22 · Chunk metadata, IDs, dedup & incremental ingestion** — 2.5h
- Metadata design: source, section, page, tenant, permissions, timestamps, content hash
- **Deterministic UUIDs from (source, chunk-hash) → idempotent upserts** — the single most important ingest trick
- Exact dedup (hashes) + near-dup (embedding similarity threshold)
- Incremental ingestion: store raw originals, reprocess deltas only, change detection triggers
- *Build:* complete ingest pipeline v1 (folders/PDFs/URLs → cleaned chunks → JSONL with stable IDs)

---

## PHASE 3 — Embeddings & Vector Stores

**M23 · Embeddings in LangChain** — 2h
- `Embeddings` interface: `embed_documents`/`embed_query`, async, batching, cost
- Choosing models: `nomic-embed-text`/`bge-m3` via Ollama, `sentence-transformers` via `langchain-huggingface`, vs APIs; MTEB; dimensions; multilingual needs
- **⚠️** One index = one embedding model, forever (until full re-index); normalization & cosine vs inner-product

**M24 · pgvector fundamentals** — 2.5h
- Extension, `vector` columns, inserts, KNN queries — **in raw SQL first** (leverage your Postgres strength)
- HNSW vs IVFFlat: `m`/`ef_construction`/`ef_search`, `lists`/`probes`; cosine vs IP with normalized vectors
- `EXPLAIN ANALYZE` on vector queries; index build times
- *Build:* SQL playground schema + query benchmarks

**M25 · PGVector store via langchain-postgres** — 2h
- `PGVectorStore` (the legacy `PGVector` class is deprecated): `add_documents` (with your stable IDs), `similarity_search`, `as_retriever`, metadata filters, delete-by-filter
- Score vs distance semantics; async support
- **⚠️** 🔄 `PGEngine` / connection-pool lifecycle: create once (app lifespan), close on shutdown — never per-request
- *Build:* the Copilot's index service module

**M26 · pgvector in production** — 2.5h
- Multi-tenant isolation: metadata filters + **Postgres Row-Level Security**
- Hybrid search in one SQL query: `tsvector` GIN + vector, RRF fusion
- `ef_search` tuning per query; partitioning by tenant; re-index strategy on embedding model change; backup implications
- *Build:* tenant-scoped search functions + hybrid SQL query

**M27 · The store landscape: Qdrant, Chroma, FAISS** *(optional)* — 1.5h
- Qdrant: compose service, payload filters, native hybrid (sparse+dense), server-side rerank
- Chroma/FAISS: prototyping roles vs server stores for prod
- Decision framework: when to leave pgvector (scale, features, ops burden)

**M28 · Retrievers & search methods** — 2h
- `as_retriever`; similarity vs **MMR** vs score thresholds; `k`/`fetch_k` tuning
- 🔄 `MultiVectorRetriever` (now `langchain_classic.retrievers.multi_vector`, not `langchain.retrievers`): child chunks → parent docs; summary vectors
- The retriever interface → composable in LCEL chains
- *Build:* retriever configs for the Copilot with measured recall on a hand-labeled set

---

## PHASE 4 — RAG

**M29 · Naive RAG** — 2.5h
- Retrieve → format context → answer, as an LCEL chain; source metadata in output
- Score thresholds; "I don't know" when context is insufficient; context budgeting
- *Build:* `/ask` over your index (CLI or minimal FastAPI route)

**M30 · Citations & grounding** — 2h
- Inline `[1][2]` citations mapped to chunk IDs; quote-level attribution
- Prompting for grounded answers; verification pass (heuristic + LLM check)
- *Build:* cited-answer endpoint returning structured citations with each response

**M31 · Query transformation** — 2.5h
- Multi-query, decomposition, step-back prompting, HyDE — mechanics + cost/latency of each
- Conversational query rewriting (condense question with history)
- Query routing across indexes/tenants
- *Build:* router + multi-query in your chain, with measured deltas

**M32 · Hybrid search & reranking** — 3h
- 🔄 BM25 (`rank_bm25`) + `EnsembleRetriever` (now `langchain_classic.retrievers`) with RRF weights; the pgvector SQL hybrid from M26
- Cross-encoder reranking: `bge-reranker-v2-m3` via sentence-transformers/FlagEmbedding; Qdrant server-side rerank
- Where rerank sits in the pipeline; latency budgets; caching reranked results
- *Build:* hybrid + rerank pipeline; recall@k before/after on your labeled set

**M33 · Advanced context engineering** — 3h
- 🔄 `ParentDocumentRetriever` (from `langchain_classic.retrievers`); sentence-window retrieval
- 🔄 `ContextualCompressionRetriever`: LLM extractors, `EmbeddingsFilter` (both from `langchain_classic.retrievers`)
- Anthropic-style "contextual retrieval": enrich each chunk with document context at ingest — cost vs quality
- *Build:* parent-document retrieval + one compression technique into the service

**M34 · Metadata-driven retrieval & self-query** — 2h
- 🔄 `SelfQueryRetriever` (from `langchain_classic.retrievers.self_query`): natural language → structured filters (field descriptions matter)
- Hard tenant/date/permission filters vs model-generated filters
- *Build:* "documents from last month about X" query path

**M35 · RAG in production** — 2.5h
- Redis query-result caching; semantic-cache caveats (when it's dangerously wrong)
- Freshness: re-embedding schedules, ingest webhooks; fallback when the store is down
- Latency budget per stage; per-tenant index vs shared-index+filters decision
- *Build:* cached, tenant-aware `/ask` with p50/p95 logging to Langfuse

---

## PHASE 5 — Tools & MCP

**M36 · Tool fundamentals & design** — 2.5h
- `@tool` decorator (from `langchain.tools`): signature → Pydantic args schema; docstring = the model's API docs; `args_schema`, artifacts (rich data for the app, text for the model)
- Async tools; `StructuredTool.from_function`; naming/description discipline
- 🔄 Design principles: narrow scope, **errors as return values (not exceptions)** — or let `ToolErrorMiddleware` convert exceptions into `ToolMessage(status="error")` — output size caps, idempotency
- **⚠️** Giant JSON tool outputs silently destroying your context budget

**M37 · Building the Copilot toolkit** — 3h
- httpx-based HTTP tools: timeouts, retries, URL allowlists
- DB tool: read-only role, schema description in the docstring, query timeout
- **SearXNG**: self-hosted metasearch — compose service, JSON API, result shaping/truncation
- *Build:* toolkit v1 (search, KB query, DB read) with mocked-httpx unit tests

**M38 · Tool security** — 2.5h
- Indirect prompt injection via tool output: truncation, neutral formatting, trust labels
- Allowlists, input validation, secrets never in args/logs, per-user rate limits
- Dangerous actions → approval requirement (foreshadows HITL)
- *Build:* hardened tools + an injection test-case folder

**M39 · The agent loop by hand** — 2.5h
- Implement the while-loop manually: `bind_tools` → parse `tool_calls` → dispatch (incl. parallel) → `ToolMessage` → repeat until no calls
- Max iterations, duplicate-call detection, token budget inside the loop
- *Build:* ~50-line mini-agent on your toolkit — you'll rebuild it on `create_agent` in M42 and know exactly what the framework does for you

**M40 · MCP part 1: building servers with FastMCP** — 2.5h
- MCP concepts: servers, tools/resources/prompts; stdio vs streamable-HTTP transports
- FastMCP: `@mcp.tool`, context, lifespan; running as a container service
- When MCP vs plain LangChain tools: interoperability and third-party servers vs simplicity
- *Build:* a knowledge-base MCP server exposing your search

**M41 · MCP part 2: consuming in LangChain** — 2h
- `langchain-mcp-adapters`: `load_mcp_tools`, `MultiServerMCPClient`
- stdio subprocess vs HTTP transport inside your compose network
- Trusting third-party servers: argument validation, isolation, network policy
- *Build:* tool registry mixing native + MCP tools, ready for agents

---

## PHASE 6 — Agents with `create_agent`

**M42 · create_agent fundamentals & deep dive** — 3.5h
- 🔄 `create_agent(model, tools, system_prompt=..., middleware=[...], response_format=..., checkpointer=..., store=..., context_schema=...)`: there is no `max_steps` — cap loops with `recursion_limit` in the run config or `ModelCallLimitMiddleware`; `response_format` (schema, `ToolStrategy`, or `ProviderStrategy`) for structured final answers; stopping conditions
- It's a LangGraph graph: `get_graph().draw_mermaid()`; passing `checkpointer`/`store` through
- The agent as a Runnable: invoke/stream/config like any chain
- *Build:* Copilot assistant v1 — your M39 mini-agent rebuilt on the framework, same toolkit

**M43 · Agent streaming** — 2h
- 🔄 `stream_mode="values" / "updates" / "messages"` with `version="v2"` (typed `StreamPart` chunks: `type` / `ns` / `data`); token streaming via messages mode
- 🔄 Event streaming: `stream_events(version="v3")` (beta; typed projections such as `run.messages`, `run.values`) replaces hand-parsing `astream_events` v1/v2 — filtering and mapping events to your own schema
- *Build:* streaming CLI that visually separates tokens, thoughts, and tool calls

**M44 · Middleware anatomy** — 2.5h
- 🔄 The full lifecycle: `before_agent`, `before_model`, `wrap_model_call`, `after_model`, `wrap_tool_call`, `after_agent` (class-based `AgentMiddleware` or decorators like `@before_model`, `@wrap_model_call`, `@dynamic_prompt`) — there is no `before_tool`/`after_tool`/`modify_model_request`
- 🔄 Injecting state/context (`state_schema`, `context_schema`, `runtime.context`); halting early with `jump_to: "end"`; denying a tool call by returning an error `ToolMessage` from `wrap_tool_call`
- Execution order when composing multiple middlewares
- *Build:* a logging middleware recording every model/tool call

**M45 · Built-in middleware tour** — 3h
- 🔄 `HumanInTheLoopMiddleware` (`interrupt_on`; decisions `approve` / `edit` / `reject`; requires a checkpointer), `SummarizationMiddleware` (`trigger=` / `keep=`), `ContextEditingMiddleware` (clears old tool outputs), `ModelRetryMiddleware` / `ToolRetryMiddleware`, `ToolErrorMiddleware`, `PIIMiddleware`, `ModelCallLimitMiddleware` / `ToolCallLimitMiddleware`, `LLMToolSelectorMiddleware`
- 🔄 Model routing: `ModelFallbackMiddleware` plus a custom `wrap_model_call` that swaps the model per request (cheap-first, escalate); LiteLLM works through your M11 gateway via `ChatOpenAI(base_url=...)`
- 🔄 Planning & delegation to check in current docs: `TodoListMiddleware` (`write_todos`), `SubAgentMiddleware` (subagents behind a `task` tool, from `deepagents`)
- Which to enable by default in production
- *Build:* assistant v2 with HITL + summarization + retry wired in

**M46 · Custom middleware** — 3h
- 🔄 Tenant/system-prompt injection from request context (`context_schema` + `@dynamic_prompt`)
- Budget-enforcement middleware: token & cost caps per run
- Guardrail hooks (pre/post model); audit middleware
- Testing custom middleware with fakes
- *Build:* `BudgetMiddleware` + `TenantContextMiddleware` + tests

**M47 · Loop control & legacy recognition** — 1.5h
- 🔄 Runaway agents: `recursion_limit`, `ModelCallLimitMiddleware` / `ToolCallLimitMiddleware`, budget middleware, duplicate-call detection, wall-clock timeouts
- 🔄 Recognizing legacy code in the wild: `langgraph.prebuilt.create_react_agent` (`prompt=`, `pre_model_hook`, `post_model_hook`), `AgentExecutor` → migration mapping to `create_agent` (`system_prompt=`, middleware)
- When *not* to use an agent at all — deterministic chains win more often than you think

---

## PHASE 7 — LangGraph Core

**M48 · Graph thinking & your first graph** — 3h
- Explicit graphs vs agent loops — the decision; StateGraph vs functional API overview
- `add_node`, `add_edge`, `add_conditional_edges` (routers, path maps), `START`/`END`, `compile()`
- Mermaid visualization via `get_graph().draw_mermaid()`; reading state diagrams
- `Command(goto=...)` navigation basics
- *Build:* ingest → retrieve → grade → rewrite-loop → answer workflow graph

**M49 · State & reducers** — 3h
- TypedDict/Pydantic/dataclass state; **`Annotated[list, add_messages]`, `operator.add`, custom reducers — the #1 confusion point in all of LangGraph**
- Input/output schema separation; private keys
- State design principles: minimal, append-only where possible
- **⚠️** Reducer mistakes = silently lost messages, not errors

**M50 · Config, invocation & subgraphs** — 2.5h
- 🔄 `RunnableConfig`: `thread_id`, `recursion_limit`; `GraphRecursionError`; run-scoped static settings via `context_schema` + `context=` (read with `Runtime`) instead of stuffing `configurable`
- Subgraphs: as-node, parent↔child state mapping, namespace isolation
- 🔄 *Build:* context-driven retrieval params on the workflow graph

**M51 · Parallelism, Send & async** — 2.5h
- Fan-out via multiple edges + reducer fan-in; nondeterministic arrival order
- **`Send` API for dynamic map-reduce** (e.g., per-document processing)
- Async nodes; blocking-in-async pitfalls; parallel retrieval
- *Build:* parallel multi-query retrieval with Send fan-out

**M52 · Functional API** — 2h
- `@entrypoint` / `@task`; wrapping existing imperative code; mixing with StateGraph
- When to prefer: linear pipelines, wrapping libraries
- *Build:* rewrite one linear chain as an entrypoint; compare ergonomics

**M53 · langgraph dev & Studio** — 1h
- 🔄 `langgraph dev` local server; Studio (now part of LangSmith; formerly "LangGraph Studio") visual debugger — check current docs for account requirements
- Step-through state inspection at every superstep; replay
- Habit: keep Studio open while building every later module

---

## PHASE 8 — Persistence, Memory & Human-in-the-Loop

**M54 · Checkpointers & PostgresSaver** — 3h
- What a checkpoint contains (values, `next`, versions, pending writes); threads; per-superstep saves
- `langgraph-checkpoint-postgres` (`PostgresSaver`): setup, pooling, lifecycle in services; the community Redis checkpointer and when you'd want it
- A conversation = a thread; attaching to graphs *and* agents
- *Build:* chat with persistent threads in Postgres

**M55 · State inspection & time travel** — 2.5h
- `get_state`, `get_state_history`, `update_state`; forking and replaying from old checkpoints
- **Debugging production issues by replaying a real thread** — a superpower
- Caveats: side effects don't undo; time travel semantics
- *Build:* admin script to inspect/replay/fork threads

**M56 · Durability, retries & crash recovery** — 2.5h
- Durability modes (`sync`/`async`/`exit`) and what each actually guarantees
- `RetryPolicy` per node; idempotent node design for external side effects
- Crash mid-run → resume semantics; there is no exactly-once
- *Build:* chaos test — kill the process mid-graph, verify recovery

**M57 · HITL part 1: interrupts** — 2.5h
- 🔄 `interrupt()` inside nodes (and in the functional API) is the primary mechanism; static breakpoints (`interrupt_before`/`interrupt_after`) are for debugging; `NodeInterrupt` is deprecated
- What a paused run looks like in state (`__interrupt__` / `GraphOutput.interrupts` with `version="v2"`); resuming with `Command(resume=...)` on the same `thread_id`; ⚠️ the node restarts from its top on resume, so keep pre-interrupt code idempotent
- Editing state before resuming (`update_state` → resume)
- *Build:* approval gate on the web-search tool

**M58 · HITL part 2: production approval flows** — 3h
- The pending-approval state machine: paused → notify → approve/deny/**timeout**
- Timeout sweeper (background job scanning paused threads)
- Resuming from your API: endpoint design, authorization on *who* may approve
- An audit record for every approval decision
- *Build:* `/approvals` endpoints + timeout sweeper

**M59 · Short-term memory** — 2h
- 🔄 Thread-scoped history via the checkpointer; trimming (`trim_messages`, `ContextEditingMiddleware`)
- 🔄 Summarization of long conversations (`SummarizationMiddleware`)
- Context-window budgeting across turns
- *Build:* long-conversation handling in Copilot chat

**M60 · Long-term memory: Store & langmem** — 3h
- `BaseStore`: namespaces, put/get/search/delete; **`PostgresStore` with semantic search over memories**
- `langmem` (still pre-1.0): memory tools, background memory formation (hot path vs reflection)
- Memory design: facts vs preferences vs procedures; what to store vs re-derive; conflicting memories
- *Build:* user-preference memory in the Copilot (extract + recall)

**M61 · Multi-tenant memory & data lifecycle** — 2h
- `user_id`/`tenant_id`-scoped namespaces; isolation patterns
- Thread/checkpoint/memory TTL cleanup jobs
- **GDPR-style "delete a user"**: threads + memories + traces (Langfuse API) + vector rows
- *Build:* retention & deletion jobs

---

## PHASE 9 — Production LangGraph

**M62 · Streaming deep dive** — 2.5h
- 🔄 All `stream_mode` values: `values`, `updates`, `messages`, `custom`, `checkpoints`, `tasks`, `debug`; `version="v2"` unified `StreamPart` output; combining modes; `subgraphs=True`; event streaming (`stream_events(version="v3")`, beta)
- Custom events via `get_stream_writer()` from deep inside the graph
- **Designing your SSE event schema** (token / thought / tool_call / tool_result / artifact / approval_request / done) — the contract your frontend will consume
- *Build:* unified event stream from the workflow graph

**M63 · Long-running graphs** — 3h
- Graphs in background workers; a `runs` status table (pending/running/paused/done/failed/cancelled)
- Endpoint/webhook-triggered resume; idempotency; cancellation propagated into a running graph
- The pattern: checkpoint = durability = resumable deep tasks
- *Build:* `/runs` endpoints with status + resume + cancel

**M64 · Testing graphs** — 3h
- Step assertions with fake models (which node ran, state after N steps); state snapshot tests
- Testing interrupt/resume flows; testing reducers
- **testcontainers-python** for real PostgresSaver tests in CI
- *Build:* CI test suite for the workflow graph

**M65 · The deployment decision** — 1.5h
- 🔄 Custom FastAPI runtime (your FOSS route: compiled graph + checkpointer behind your own API) vs LangSmith Deployment / Agent Server (formerly LangGraph Platform)
- 🔄 What the platform actually adds (run management, double-texting, Studio in prod) and its licensing reality (even the standalone server needs a LangSmith license)
- Write the decision memo for the Copilot

---

## PHASE 10 — Multi-Agent Systems

**M66 · Multi-agent decision framework** — 1.5h
- When multi-agent: context isolation, parallelism, specialization — vs "single agent + good tools" (the default)
- Topologies: supervisor, hierarchical, swarm/handoffs, pipeline; cost/latency/complexity math
- Communication media: shared state vs messages vs artifacts

**M67 · Supervisor: by hand + subagents-as-tools** — 3h
- Hand-built: shared team state, supervisor node routing via structured output, handoff message design
- 🔄 The `langgraph-supervisor` prebuilt is no longer actively maintained → use the subagents pattern: a `create_agent` supervisor with each worker wrapped as a `@tool`; when that's enough, how to escape its limits
- *Build:* research team v1 — supervisor + web researcher + doc analyst

**M68 · Swarm & handoffs** — 2.5h
- 🔄 Agents-as-tools vs `Command`-based handoffs (tools that return `Command(goto=..., update=...)`); the `langgraph-swarm` package still targets the legacy `create_react_agent`, so build handoffs yourself
- **State filters** — what actually transfers between agents
- *Build:* triage swarm; compare feel vs supervisor

**M69 · Hierarchical teams & shared state design** — 2.5h
- 🔄 Supervisor-of-supervisors (a mid-tier `create_agent` wrapped as a tool on the top-level agent); progress reporting; failure escalation up the tree
- Shared state schema design; avoiding prompt-stuffing via store/artifacts
- *Build:* add a writer + reviewer under a team lead

**M70 · Parallel agents, aggregation & debugging** — 2.5h
- `Send` fan-out of subagents; merging results; judge/vote aggregation
- Per-agent token budgets; Langfuse trace trees for multi-agent; subgraph streaming for debugging
- *Build:* parallel researchers + judge; inspect the full trace

---

## PHASE 11 — Deep Agents

**M71 · The deep agent pattern** — 1.5h
- The recipe (from Anthropic's deep agents work): **planning todos, subagents for context isolation, virtual filesystem for state offload, intermediate thinking, persistence, background tasks**
- Deep agents vs plain agent vs multi-agent graph — selection guide
- Why externalizing state to files beats context stuffing for long tasks

**M72 · deepagents quickstart** — 2.5h
- 🔄 `create_deep_agent(model, tools, system_prompt=..., subagents=..., middleware=..., skills=..., memory=...)` (the old `instructions=` parameter is gone); built-ins: `write_todos`, `ls`/`read_file`/`write_file`/`edit_file`/`glob`/`grep`, `task` (plus `execute` when the backend is a sandbox)
- Dissect the default system prompt — what it's telling the model and why (your `system_prompt` is prepended to the built-in base prompt)
- 🔄 Model selection: any `"provider:model"` string or chat-model instance (including `ollama:...`, or your LiteLLM gateway via `ChatOpenAI(base_url=...)`) — no LiteLLM "backend" needed; "backend" now means the filesystem backend
- *Build:* first deep research run over your toolkit

**M73 · The virtual filesystem** — 2.5h
- 🔄 Backends: `StateBackend` (default, per-thread), `StoreBackend`, `CompositeBackend` (e.g., route `/memories/` to a persistent store); large tool results auto-offload to files; artifact lifecycle: scratch vs deliverables
- Customizing storage: persist artifacts to Postgres (via `PostgresStore`) / MinIO (custom backend); path safety; exporting artifacts to users
- *Build:* artifacts persisted to Postgres + export endpoint

**M74 · Subagents & the task tool** — 3h
- 🔄 `task` tool semantics: fresh context + own tools + returns a concise result; a built-in `general-purpose` subagent always exists
- 🔄 Custom subagents list of dicts (`name` / `description` / `system_prompt` / `tools` / optional `model`, `middleware`) or `CompiledSubAgent` for your own graph; **parallel `task` calls**
- Per-subagent model routing: cheap researchers, strong writer
- *Build:* parallel web-research subagents + doc analyst

**M75 · Planning, todos & HITL on the plan** — 2.5h
- How the `write_todos` list steers long tasks; customizing planning prompts
- 🔄 Interrupt before execution via `interrupt_on` (HITL middleware) → user approves/edits the plan → resume; mid-run replanning
- *Build:* plan-approval flow on the research agent

**M76 · Background tasks & notifications** — 2h
- 🔄 Async subagents (`AsyncSubAgent` pointing at an Agent Protocol / Agent Server graph): launch non-blocking, poll status; requires Agent Server (LangSmith Deployment), so compare with your own arq/Taskiq worker pattern
- Cost control and timeouts for background work
- *Build:* "notify me when done" long-research mode

**M77 · Customization, hardening & the production deep agent** — 3h
- 🔄 Rewriting system prompts (`system_prompt`, harness profiles); adding middleware (HITL, summarization, retry, budget caps); checkpointers for resumable sessions
- `browser-use` (OSS) for real web research; MCP tools inside deep agents
- Per-run budget caps, timeouts, cost-per-run measurement, progress as SSE events
- *Build:* the production deep research agent — RAG + SearXNG + browser + artifacts

---

## PHASE 12 — Langfuse in Production

**M78 · Observability concepts & v4 architecture** — 1.5h
- 🔄 Traces → observations (spans, generations); scores, sessions, users, datasets, experiments, prompt versions; v4's observations-first data model (attributes propagate to every observation)
- 🔄 Architecture: web + worker, **ClickHouse** (trace store; v4 needs ≥ 25.12), Postgres (app data), Redis (queue), S3/MinIO (blobs) — unchanged from v3; why Langfuse moved to ClickHouse
- Open-core boundaries: what free self-hosted includes vs paid

**M79 · Production deployment** — 2.5h
- Official compose; required env (auth, `ENCRYPTION_KEY`, salt); ClickHouse & MinIO config
- Integrating into *your* stack: shared vs isolated Postgres, **RAM sizing (ClickHouse is real)**, healthchecks, 🔄 upgrade procedure (v3 → v4 is a three-step migration with `legacy`/`dual` write modes; v3 gets security patches until Jan 2027)
- *Build:* Langfuse running properly in your compose

**M80 · Securing & operating Langfuse** — 2h
- Cloudflare tunnel routing + **Zero Trust Access** (free ≤50 users) in front of the UI
- API keys: service vs personal; OIDC SSO options
- Backups (Postgres + ClickHouse + MinIO), retention/cleanup, queue-depth monitoring, worker scaling

**M81 · Python SDK tracing deep dive** — 2.5h
- 🔄 `@observe` nesting; `get_client()` and `start_as_current_observation(as_type="span" | "generation")`; async semantics
- 🔄 Metadata, sessions, user IDs via `propagate_attributes(user_id=, session_id=, tags=, metadata=, trace_name=)` (replaces `update_current_trace`); usage & cost recording (define pricing for self-hosted models = 0)
- Trace-ID propagation into your app logs; async ingestion & flush behavior; overhead measurement
- *Build:* the app's proper tracing module (replacing the M17 bootstrap)

**M82 · LangChain/LangGraph integration** — 2h
- 🔄 `from langfuse.langchain import CallbackHandler` via config (not the old `langfuse.callback`): whole graphs traced **including subgraphs and every LLM/tool call**
- 🔄 Per-run metadata (user, tenant, env, thread) via an enclosing `propagate_attributes()` block or `langfuse_user_id` / `langfuse_session_id` / `langfuse_tags` metadata keys; correlation with request IDs; sampling

**M83 · Scores & feedback loops** — 2h
- User feedback endpoint → trace scores via API; 👍/👎 capture design
- Custom spans for business events (cache hit, approval wait, retrieval hit count)
- Dashboards: cost/latency/quality by tenant and feature (v4 also adds Alerts)
- *Build:* feedback endpoints wired to traces

**M84 · Prompt management** — 2.5h
- Prompts in the UI: create, iterate, version; **labels: `production` / `staging` / `draft`**
- `get_prompt()` + `.compile()` in code; migrating your M13 file-prompt library in
- A/B via labels; diffs & rollback; the rule: no prompt change without a dataset eval
- *Build:* all Copilot prompts managed in Langfuse

**M85 · Datasets & experiment pipelines** — 2.5h
- Datasets built from real traces (ingest production examples); annotation queues
- 🔄 Experiments: run your graph over a dataset with the SDK's experiment runner (`langfuse.run_experiment(...)`, task + evaluators); evaluators = LLM-as-judge (Ollama) + custom Python; comparing runs
- Nightly eval job; drift detection
- *Build:* nightly eval cron + report

---

## PHASE 13 — Evaluation & Testing Culture

**M86 · Testing culture & pytest with fakes** — 2.5h
- The LLM test pyramid: unit → integration → e2e trajectory → offline eval → online monitoring; what CI can and cannot catch
- Fakes everywhere: chat models, embeddings, stores, tools; deterministic golden fixtures
- Marker structure: fast unit (every commit) / integration (PR) / e2e (nightly)

**M87 · RAGAS** — 2.5h
- What each metric actually measures: faithfulness, answer relevancy, context precision/recall
- Running against your RAG with local judge models (Ollama); synthetic test-set generation
- Interpreting scores, thresholding, judge-model bias pitfalls
- *Build:* RAG eval suite + baseline numbers recorded

**M88 · agentevals** — 2h
- Trajectory matching: exact vs subset (order-insensitive) vs LLM-as-judge
- Authoring goldens from real traces; partial credit
- *Build:* trajectory evals for the research team agent

**M89 · promptfoo** — 2.5h
- `promptfooconfig.yaml`; provider matrix — same prompt across models including Ollama
- Assertion types: contains, llm-rubric, contains-json, custom Python
- CLI + CI mode; side-by-side model/prompt comparison
- *Build:* matrix tests for extraction + RAG prompts

**M90 · CI quality gates** — 2.5h
- GitHub Actions: unit + testcontainers integration → promptfoo step → nightly RAGAS/agentevals (Ollama service container as judge)
- Langfuse dataset experiments triggered from CI; score summaries posted to PRs; **thresholds block merges**
- *Build:* the full quality pipeline in CI

**M91 · Load & chaos testing** — 2h
- Locust: p50/p95 first-token and total latency, tokens/sec, concurrent streams
- Kill a worker mid-run → verify checkpoint recovery; provider-outage drills (fallbacks fire?)
- *Build:* load suite + capacity findings report

---

## PHASE 14 — Safety, Guardrails & Privacy

**M92 · Threat modeling your agent SaaS** — 2h
- Assets: tenant data, system prompts, tool credentials, API spend
- OWASP LLM Top 10 mapped to your stack; direct vs **indirect prompt injection**; data exfiltration; memory poisoning; tool abuse; multi-tenant leakage paths

**M93 · Prompt injection & defenses** — 2.5h
- Direct jailbreaks; indirect injection via retrieved docs, web pages, tool outputs — *the realistic attack for your app*
- Defenses: spotlighting/delimiters, instruction-data separation, trust labels, output filtering for exfil patterns (URLs, secrets)
- *Build:* a curated injection test suite; red-team your own agent and record results

**M94 · PII & content guardrails** — 2.5h
- 🔄 Built-in `PIIMiddleware` (email, credit card, IP, etc., with `redact`/`mask`/`hash`/`block` strategies and custom detectors) for the basics; **Presidio** analyzer/anonymizer for deeper detect & mask pre-LLM; re-scan outputs
- Llama Guard via Ollama for moderation; custom validators
- Enforcement via `before_model`/`after_model` middleware; latency cost measurement

**M95 · Tool & retrieval hardening** — 2.5h
- Least-privilege DB roles; read-only SQL; URL allowlists + SSRF (private-IP blocking); per-user rate limits
- Retrieval poisoning defense: provenance metadata, source trust levels, quarantine for untrusted docs
- Secrets handling in tool args and logs

**M96 · Sandboxed code execution** — 2.5h
- Why agents + arbitrary code need real isolation; Docker sandbox: non-root, no network, seccomp/cap drops, CPU/mem limits, ephemeral, hard timeout
- API design: submit code → sandbox container → result
- Awareness: gVisor/Firecracker-class isolation for higher stakes

**M97 · Guardrail frameworks, audit & kill switches** — 2h
- NeMo Guardrails & Guardrails AI: what they solve; when custom middleware is simpler (usually, for your architecture)
- Complete audit trail design (Langfuse spans + DB records)
- Kill switches: per-tool, per-tenant, global; emergency disable; HITL as the final control

---

## PHASE 15 — Serving Agents with FastAPI

**M98 · SSE streaming & the event protocol** — 3h
- 🔄 FastAPI's native SSE (`from fastapi.sse import EventSourceResponse, ServerSentEvent`, FastAPI ≥ 0.135; `sse-starlette` remains an option); bridging `astream` → SSE; your event schema from M62 as the wire format
- **Backpressure & client-disconnect handling** (`request.is_disconnected`), heartbeats, Last-Event-ID resume (persist events in Redis)
- **⚠️** Proxy buffering; Cloudflare SSE behavior

**M99 · WebSockets & cancellation** — 2.5h
- When WS beats SSE (interruption, bidirectional); per-connection run management
- Propagating cancel into a running graph; reconnect semantics
- *Build:* WS endpoint with a working stop button

**M100 · Background jobs with Taskiq** — 2.5h
- 🔄 **Taskiq** (async-native, Redis broker, FastAPI-friendly; SAQ is a lighter alternative) vs Celery — `arq` is now maintenance-only, so don't start new work on it; task functions, retries, schedules/cron
- Offloading deep-research runs; job status endpoints; idempotency keys
- **Resume-from-checkpoint instead of blind retry**
- 🔄 *Build:* deep-research job queue + workers (Taskiq)

**M101 · Multi-tenancy end-to-end** — 3h
- JWT auth → tenant context middleware → propagation *everywhere*: graph config, store namespaces, Langfuse metadata, metrics labels, log fields
- Redis token-bucket rate limiting; per-tenant quotas and spend caps
- Per-tenant feature flags/config

**M102 · App ↔ graph wiring** — 2.5h
- DI of compiled graph + checkpointer + store singletons; lifespan-managed pools
- Request → thread mapping; conversation list + paginated history endpoints; auto title generation
- Error taxonomy → HTTP responses (no stack traces to clients)

**M103 · Logs, errors & metrics** — 2.5h
- structlog JSON logs with trace-ID correlation; **GlitchTip** (OSS, Sentry-compatible) + sentry-sdk
- `prometheus-fastapi-instrumentator` + custom metrics: tokens, cost, cache hits, run duration, queue depth, approvals
- Request-ID middleware tying logs + traces + metrics together

---

## PHASE 16 — Deployment & Operations

**M104 · Reference architecture** — 1.5h
- The full topology: cloudflared → app + Taskiq workers → Postgres/Redis/Ollama → Langfuse stack (web, worker, ClickHouse, its Postgres, MinIO); frontend/backend networks; only the tunnel is exposed
- **Capacity math for one host** — the RAM budget across ClickHouse + Postgres + Ollama + app
- What moves to a second host first, when needed

**M105 · Containers & compose** — 2.5h
- Multi-stage Dockerfile with uv (`uv sync --frozen`); slim images; non-root; healthchecks
- Compose base + prod/dev overrides; GHCR tags = git SHA; `depends_on` conditions; build-cache optimization

**M106 · CI/CD** — 2.5h
- Actions pipeline: build → test (testcontainers + Ollama judge service) → promptfoo → push GHCR → deploy over SSH (`compose pull && up -d`) → migrations → smoke test → **rollback to previous tag**
- Secrets management; environments

**M107 · Cloudflare Tunnel & Zero Trust** — 2h
- `cloudflared` as a compose service with tunnel token; DNS routing; multiple hostnames (app, langfuse, grafana)
- Zero Trust Access policies guarding admin UIs; WAF basics; SSE/WS through the tunnel

**M108 · Backups & data ops** — 2.5h
- `pg_dump`/pgBackRest → **restic** → MinIO/S3; ClickHouse + MinIO backups for Langfuse; Redis persistence/eviction
- pgbouncer when workers multiply; **restore drills — an untested backup isn't a backup**; migration discipline (alembic)

**M109 · Monitoring & alerting (your FOSS replacement for LangSmith's monitoring/Deployment dashboards)** — 3h
- Prometheus + node/cAdvisor/postgres/redis exporters; Grafana dashboards: tokens, cost, latency, error rate, queue depth, agent success rate, eval scores
- Alertmanager → **ntfy**/Telegram; Uptime Kuma external probes; optional Loki for logs (Langfuse v4 Alerts can cover LLM-metric alerts)
- *Build:* dashboards + alert rules that actually fire

**M110 · Model serving ops** — 2.5h
- Ollama in prod: preloading, `keep_alive`, RAM budgeting, the CPU-only reality check, model update procedure
- When to graduate to vLLM (GPU, throughput, OpenAI-compatible) — or stay API-only via the LiteLLM gateway (keys, budgets, fallbacks); the pragmatic split
- Local vs API per workload: the decision table

**M111 · Host hardening & runbooks** — 2h
- ufw, SSH keys only, unattended-upgrades, Docker Bench, restart policies
- Runbooks: runaway agent (detect via metrics → kill → disable tool → notify), cost spike, restore, dependency-down
- Solo-founder on-call basics

---

## PHASE 17 — Cost, Performance & Scale

**M112 · Cost anatomy & measurement** — 2h
- Where tokens actually go: agent loops grow context every step; tool-output bloat; multi-agent multiplication
- Measuring real cost via `usage_metadata` + Langfuse; cost per feature / tenant / run

**M113 · Caching** — 2.5h
- LangChain LLM cache with Redis — **exact-match only**; semantic cache and when it's dangerously wrong
- 🔄 Provider prompt caching: Anthropic `cache_control` (or `AnthropicPromptCachingMiddleware` in `langchain-anthropic`), OpenAI automatic — the **stable-prompt-prefix discipline** that makes hits actually happen
- Cache-hit measurement

**M114 · Context engineering for cost & latency** — 2.5h
- 🔄 Aggressive trim/summarize (`SummarizationMiddleware`, `ContextEditingMiddleware`); retrieve-into-context instead of memory dumps; tool-output truncation
- The filesystem/artifacts pattern as external context (deep agents' trick) for very long tasks
- First-token latency: parallelism, streaming, `keep_alive`

**M115 · Model routing & cascades** — 2h
- 🔄 Cheap-first routing (custom `wrap_model_call` model-selection middleware, `ModelFallbackMiddleware`, LiteLLM router); escalation patterns
- Batch APIs for bulk jobs; fallback chains; per-feature model selection

**M116 · Unit economics & scaling decisions** — 2h
- Cost per tenant/run/query; budget alerts; knowing when a feature is unaffordable
- 🔄 Scaling path: second host for models, pgbouncer, partitioning, ClickHouse retention; revisiting custom-runtime vs LangSmith Deployment

---

## PHASE 18 — Capstone: The Complete SaaS

**M117 · Spec & architecture** — 3h
- Final Research Copilot spec: tiers, credits, quotas; full system + data-flow diagram; scope decisions and cut lines

**M118 · Data model & agent core** — 10h
- Postgres schema: tenants, users, conversations/threads, runs, messages, documents, artifacts, approvals, usage ledger
- deepagents core: RAG + SearXNG + browser-use; middleware stack (tenant, budget, HITL, summarization, retry); `PostgresSaver` + `PostgresStore` + langmem; MCP plugin surface

**M119 · Serving & observability** — 8h
- 🔄 SSE + WS endpoints; Taskiq deep-research jobs; approvals/feedback/resume; quotas & rate limits
- Per-tenant tracing, prompt labels, nightly evals, dashboards, drift alerts

**M120 · Security & deployment** — 6h
- Injection suite passing; PII redaction; sandboxed tools; retention/deletion jobs; audit trail
- Full compose + CI/CD + backups + monitoring; a restore drill; load-test results documented

**M121 · Launch checklist & stretch** — 4h
- ~50-item production readiness review: secrets, migrations, rollback, cost caps, privacy/ToS basics
- Stretch: Stripe metering design, MCP tenant integrations, i18n, self-serve onboarding

**M122 · Staying current** — ongoing
- Release-notes habit for langchain / langgraph / deepagents / langfuse; changelog-reading skills
- Upgrade cadence: lockfile + your test suite as the safety net for API churn
- Watch list: MCP evolution, agent-to-agent protocols, memory standardization, local-model quality trajectory
