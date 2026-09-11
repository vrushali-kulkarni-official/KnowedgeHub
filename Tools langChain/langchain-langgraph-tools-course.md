# LangChain / LangGraph Tools — Zero to Production Course

**How to use this document:** Each module below is self-contained. Copy one module's content into a fresh conversation with an AI tutor and ask it to teach you that module in depth, with runnable code. Go in order — later modules assume earlier ones. Modules 0–4 are foundational (beginner), 5–11 are intermediate (building real tools), 12–15 are advanced/internals, 16–18 are production/capstone.

Your existing stack (Python, uv, Pydantic, FastAPI, Postgres, Redis, Docker/Compose, GitHub Actions, GHCR, Cloudflare Tunnel) is assumed throughout — every module ties back to it, and the course ends by wiring everything into that exact deployment pattern.

---

## Module 0 — Foundations & Mental Model

*Goal: understand why tools exist and how they fit into the agent loop before writing any code.*

- **0.1** What a "tool" actually is — a function + a JSON schema the model can request by name, and why LLMs can't just "call Python functions" directly
- **0.2** The tool-calling loop end to end: prompt → model emits a tool call → your code executes it → result goes back to the model → model responds or calls another tool
- **0.3** LangChain vs LangGraph vs raw provider SDKs (OpenAI/Anthropic native tool calling) — what each layer actually buys you, and when you don't need LangChain at all
- **0.4** Where "tools" sit relative to "agents", "chains", and "graphs" — vocabulary you'll need for the rest of the course
- **0.5** Environment setup with `uv`: `langchain-core`, `langchain`, `langgraph`, a model provider package, version pinning strategy, and why `langchain-core` is the only hard dependency for tool-writing

---

## Module 1 — Creating Tools: The Basics

*Goal: be able to write, register, and invoke a simple tool.*

- **1.1** Anatomy of a tool: `name`, `description`, `args` (schema), the callable itself, and the return value contract
- **1.2** The `@tool` decorator — minimal example, how the docstring becomes the tool description shown to the model
- **1.3** `@tool` customization — overriding the name, `return_direct`, `parse_docstring=True` for auto-extracting arg descriptions
- **1.4** Manually invoking a tool with `.invoke()` vs letting a model call it — debugging tools in isolation before wiring them into an agent
- **1.5** `StructuredTool.from_function()` — the non-decorator way to build the same thing, and when it's more ergonomic (e.g., building tools dynamically in a loop)
- **1.6** Subclassing `BaseTool` directly — what you get that `@tool` doesn't (stateful tools, custom `run`/`arun` control flow), and why it should be your last resort, not your default

---

## Module 2 — Sync vs Async Tools

*Goal: know which to write and why it matters once you're behind FastAPI.*

- **2.1** Defining a sync tool (`def`) vs an async tool (`async def`) — LangChain auto-detects and exposes both `.invoke()`/`.ainvoke()`
- **2.2** Why this matters in production: a sync, blocking tool (e.g., `requests.get`) inside an async FastAPI event loop stalls every concurrent user
- **2.3** What happens if you only define a sync tool but call `.ainvoke()` — the executor thread-pool fallback, and its hidden costs (thread pool exhaustion under load)
- **2.4** Writing a tool with both `func=` and `coroutine=` for dual sync/async support
- **2.5** Timeouts and cancellation for tools (`asyncio.wait_for`, provider-level timeouts) — never let a hung external API hang your whole agent

---

## Module 3 — Structured Inputs with Pydantic (`args_schema`)

*Goal: give the model precise, validated, self-documenting inputs — this is the module that most directly reuses your existing Pydantic skill.*

- **3.1** Why `args_schema` beats letting LangChain infer from type hints once tools get non-trivial
- **3.2** Building an `args_schema` as a `BaseModel`: `Field(..., description=...)` — remember the model reads these descriptions, they are prompt engineering
- **3.3** Optional fields, defaults, `Literal`/enum fields, nested Pydantic models as arguments
- **3.4** Validators (`field_validator`) as a second line of defense against malformed model output — pairs directly with Module 4 (error handling)
- **3.5** Multi-argument tools vs single-string tools — why almost everything in production should be multi-argument structured tools
- **3.6** `InjectedToolArg` — hiding arguments the model should *never* see or set (a `user_id`, a DB session, a request context) so they're supplied by your code, not the LLM — critical for multi-tenant safety, previewed here and used heavily in Modules 6 and 13
- **3.7** Returning richer outputs with `response_format="content_and_artifact"` — separating what the model reads (a summary string) from what your app uses (a dataframe, an image, raw rows)

---

## Module 4 — Tool Error Handling

*Goal: tools fail constantly in production (bad API responses, timeouts, validation errors) — the model needs to see failures as recoverable, not crash your app.*

- **4.1** `ToolException` — the built-in way to signal a tool-level failure without killing the run
- **4.2** `handle_tool_error` — turning an exception into a message the *model* sees, so it can retry with different arguments or apologize to the user, instead of your process crashing
- **4.3** Writing error messages for the model, not for a human log — specific, actionable, telling it exactly what to change ("`limit` must be between 1 and 100, you passed 500")
- **4.4** Separating what the model sees from what you log — full stack traces go to your observability stack (Module 16), never to the model
- **4.5** Retry strategies for transient failures (network blips) vs permanent ones (bad input) — using `tenacity` for the former, `ToolException` for the latter
- **4.6** Testing failure paths deliberately — unit tests that force a tool into its error branch and assert the model-facing message is sane

---

## Module 5 — Tools That Call External APIs

*Goal: the most common real-world tool — wrapping a third-party REST API.*

- **5.1** Basic pattern: `httpx.AsyncClient` inside an async tool, structured `args_schema` for the endpoint's parameters
- **5.2** Secrets and auth — API keys via environment variables/Docker secrets, never hardcoded, never passed through the model
- **5.3** Rate limiting and backoff against the external API using `tenacity`, and surfacing a graceful `ToolException` when you're throttled
- **5.4** Caching API responses in Redis (you already know this) to cut cost/latency — cache key design for tool calls, TTL strategy
- **5.5** A generic "make an HTTP request" tool — why this pattern is popular but dangerous (SSRF, hitting internal services, arbitrary outbound calls) and how to constrain it (domain allowlist) if you build one at all

---

## Module 6 — Tools That Hit Your Own Postgres / Redis

*Goal: connect agents to your own application's data safely — the backbone of most real SaaS agent features.*

- **6.1** The DB-backed tool pattern with async SQLAlchemy or `psycopg` — passing a connection/session into the tool without exposing it to the model
- **6.2** Connection pooling in a tool context — reusing your app's existing pool vs a per-call connection, and why creating a new pool per tool call will destroy your DB under load
- **6.3** Redis-backed tools — read/write cache tools, session/short-term-memory tools, rate-limit tools, pub/sub-triggered tools
- **6.4** Multi-tenant safety: using `InjectedToolArg` (Module 3.6) to force `user_id`/`tenant_id` scoping into every query — the model must never be able to supply or override this value
- **6.5** Idempotency and side effects — write tools (create/update/delete) need extra guardrails vs read tools; previewing human-in-the-loop confirmation (Module 13.5) for anything destructive

---

## Module 7 — SQL Tools & Text-to-SQL

*Goal: let an agent query your Postgres database in natural language, safely.*

- **7.1** The `SQLDatabase` utility and `SQLDatabaseToolkit` from `langchain-community` — what's included (list tables, get schema, query, query-checker)
- **7.2** Building a safe text-to-SQL tool: read-only DB role, mandatory `LIMIT`, query validation before execution, blocking DDL/DML
- **7.3** Why letting an LLM generate raw SQL against a writable connection is a security incident waiting to happen — defense in depth (role permissions + query allowlist regex + result-row caps)
- **7.4** When to skip text-to-SQL entirely and instead expose a small set of purpose-built, parameterized query tools (usually the better production choice for a SaaS app with known query patterns)

---

## Module 8 — Search Tools & Web Access

*Goal: give agents current, real-world information.*

- **8.1** Free/open-source-friendly search options: DuckDuckGo search tool, SearxNG (self-hosted, fully open source, fits your "prefer FOSS" constraint), vs paid options (Tavily, SerpAPI) and the trade-offs
- **8.2** Building a custom search tool wrapping any search API behind your standard `args_schema` + error-handling pattern from Modules 3–4
- **8.3** Web fetch/content-extraction tools — fetching a URL and stripping it to readable text (`httpx` + `trafilatura`/`readability-lxml`) so the model isn't drowning in raw HTML
- **8.4** The "search then fetch" pattern — search tool returns snippets + URLs, a second fetch tool pulls full content only for the page the model picks, keeping token usage sane
- **8.5** Grounding and citations — designing tool outputs so the model can (and is instructed to) cite sources, and where prompt-level instruction has to do the rest

---

## Module 9 — Code Execution Tools

*Goal: the highest-value, highest-risk tool category — treat it accordingly.*

- **9.1** Why a code-execution tool is powerful (math, data analysis, dynamic logic) and why it is the single riskiest tool you can give a model
- **9.2** Sandboxing approaches, cheapest to most robust: a restricted subprocess with resource limits (your baseline given you already run Docker), a dedicated short-lived Docker container per execution, open-source sandbox runtimes (e.g., gVisor-hardened containers), vs managed sandboxes (E2B, Modal) if you ever relax the "FOSS only" constraint
- **9.3** Building a Docker-based Python execution tool: no network access, CPU/memory/time limits, read-only filesystem except a scratch dir, non-root user — this reuses your Docker/Compose skills directly
- **9.4** What to log and cap: stdout/stderr size limits, execution timeouts, never returning raw filesystem paths to the model

---

## Module 10 — Built-in & Community Tools

*Goal: know the ecosystem well enough to stop reinventing things — matches your stated preference for popular, pre-made components.*

- **10.1** The shape of the `langchain-community` tools ecosystem — how it's organized, and how to find what exists before writing your own
- **10.2** Notable tools worth knowing by name: `requests` toolkit, file-management toolkit, `SQLDatabaseToolkit`, shell tool, `arxiv`/`wikipedia` tools, GitHub tool, Slack tool — what each is actually good for
- **10.3** "Toolkits" as a concept — a pre-bundled, related group of tools (e.g., all SQL tools together) vs standalone tools
- **10.4** Decision framework: use a built-in/community tool when it's actively maintained, matches your exact use case, and its abstraction doesn't fight you; write your own when you need tenant scoping, custom error semantics, or the community version has stale dependencies/security issues
- **10.5** Vetting a community tool before you ship it: last commit date, open security issues, what it actually sends over the network, license compatibility

---

## Module 11 — `@tool` vs MCP (Model Context Protocol)

*Goal: understand the two competing patterns for giving models capabilities, and when to use which.*

- **11.1** What MCP is at a protocol level — a standard for exposing tools/resources/prompts from a server that *any* MCP-compatible client can consume, vs a LangChain tool which is Python-object-local to your process
- **11.2** Architectural comparison: in-process `@tool` (fast, simple, tightly coupled to your codebase) vs an MCP server (network-addressable, language-agnostic, reusable across multiple agents/clients)
- **11.3** `langchain-mcp-adapters` — consuming tools from an existing MCP server as if they were native LangChain tools inside a LangGraph agent
- **11.4** Building your own MCP server vs a plain LangChain tool — decision framework: reach for MCP when multiple different agents/apps (or third parties) need the same capability; stay with `@tool` when it's one agent, one codebase, one deployment
- **11.5** Where MCP earns its complexity in a production SaaS: e.g., a shared "billing tools" MCP server used by both your support agent and an internal ops agent, vs just importing a Python module twice

---

## Module 12 — Tool-Calling Internals

*Goal: stop treating tool calling as magic — understand exactly what's happening between your code and the model API.*

- **12.1** What `bind_tools()` actually does — converts each `BaseTool`'s `args_schema` into the JSON-schema format the provider's API expects, attaches it to the outgoing request
- **12.2** Provider differences — how OpenAI's function-calling format and Anthropic's tool-use format differ under the hood, and why LangChain's abstraction exists to hide this from you (and where it leaks)
- **12.3** Parallel tool calls — how a model can request multiple tools in a single turn, how to enable/disable this per-provider, and how your executor must handle concurrent execution safely
- **12.4** Forcing a specific tool call with `tool_choice` — "must call this exact tool," "must call some tool," "auto" — and real use cases for each (e.g., forcing a structured-output tool call)
- **12.5** The message shapes involved: `AIMessage.tool_calls` (the model's request), `ToolMessage` (your result, keyed by `tool_call_id`) — reading and constructing these by hand at least once so the abstraction stops feeling opaque
- **12.6** Building a bare-metal tool loop yourself (bind → invoke → execute → append `ToolMessage` → invoke again) before relying on prebuilt agents, so you know exactly what they're doing for you

---

## Module 13 — Tools Inside LangGraph

*Goal: move from "tools in isolation" to "tools as part of a real agent graph" — this is where production agents actually live.*

- **13.1** `ToolNode` — the prebuilt LangGraph node that executes whatever tool calls are on the latest `AIMessage`, including parallel execution and error routing
- **13.2** `create_react_agent` — the prebuilt agent loop (model ↔ `ToolNode`) and what it gives you for free vs a hand-built `StateGraph`
- **13.3** When to drop the prebuilt agent and write a custom graph: conditional routing based on *which* tool was called, multi-agent handoff, approval steps between tool call and execution
- **13.4** `InjectedState` / `InjectedStore` — pulling graph state or a persistent store into a tool's execution without the model needing to (or being able to) supply it — the LangGraph-native version of the `InjectedToolArg` pattern from Module 3.6
- **13.5** Human-in-the-loop before executing a sensitive tool — using `interrupt()` to pause the graph, show the pending tool call to a user/admin, resume only on approval — essential for any write/delete tool from Module 6.5
- **13.6** Streaming tool call events to a frontend — surfacing "the agent is calling `search_orders`..." in real time via LangGraph's streaming modes, which you'll wire into FastAPI in Module 17

---

## Module 14 — Designing Good Tool Interfaces

*Goal: the model only ever sees your tool's name, description, and schema — treat that surface as prompt engineering, because it is.*

- **14.1** Naming conventions: verbs that match intent (`get_order_status` not `orders`), consistent naming across a toolset so the model can pattern-match
- **14.2** Writing descriptions that actually work: what the tool does, when to use it, when *not* to use it, and one concrete example inline in the docstring
- **14.3** Schema minimalism — every extra parameter is a chance for the model to get it wrong; default aggressively, require only what's truly required
- **14.4** Tool granularity — one broad tool with a `mode` parameter vs several small single-purpose tools; why more, narrower tools usually route better than one Swiss-army tool
- **14.5** Avoiding overlapping tools that confuse tool selection (two tools that both "sort of" search) — auditing your toolset for ambiguity
- **14.6** Measuring tool-selection accuracy directly: build a small eval set of (prompt → expected tool + args) pairs and check the model picks correctly before you ever ship — first taste of the eval discipline covered fully in Module 16

---

## Module 15 — Security & Production Hardening

*Goal: tools are the attack surface of an agentic system — this module is non-negotiable before shipping.*

- **15.1** Least-privilege credentials per tool — a DB tool gets a role that can only touch what it needs, an API tool's key is scoped as narrowly as the provider allows
- **15.2** Sandboxing every risky tool (code execution, shell, filesystem) per Module 9 — never run these with the same privileges as your main app process
- **15.3** Prompt injection via tool *output* — a web page or API response a tool fetches can contain text instructing the model to do something else; treating all tool output as untrusted data, not instructions
- **15.4** Guardrails: allowlisting which tools are available per user/context, validating tool outputs before they reach the model, mandatory human approval gates for destructive actions (ties to 13.5)
- **15.5** Auditing — logging every tool call (who, what args, what result, what the model did next) so you can reconstruct any incident after the fact

---

## Module 16 — Observability, Testing & Evaluation

*Goal: know your tools are working, in production, over time — not just in your notebook.*

- **16.1** Tracing tool calls with open-source-friendly options: OpenTelemetry instrumentation, self-hosted Langfuse — capturing latency, inputs, outputs, and errors per tool call
- **16.2** Unit testing tools in isolation — mocking the external API/DB, asserting both the happy path and the `ToolException` path from Module 4.6
- **16.3** Integration testing the full agent+tools graph — does the right tool get called for a given prompt, does the graph terminate, does a forced tool error actually get handled gracefully
- **16.4** Evaluation datasets for tool selection and correctness — expanding the small eval set from 14.6 into a real regression suite you run in CI (ties to your GitHub Actions pipeline)
- **16.5** Cost and latency monitoring per tool — knowing which tool is your slowest/most expensive so you know where to optimize (cache it? make it async? drop it?)

---

## Module 17 — Deployment on Your Stack

*Goal: wire everything above into the exact stack you already use — this is the "make it real" module.*

- **17.1** Structuring a FastAPI app that exposes your LangGraph agent (streaming and non-streaming endpoints), keeping tool definitions in their own module separate from route handlers
- **17.2** Running async tools correctly inside FastAPI's event loop — avoiding the sync-tool-blocks-everyone trap from Module 2.2 for real this time
- **17.3** Dockerizing the agent service, adding Postgres and Redis to your existing `docker-compose.yml`, environment-based config for API keys and DB roles from Module 15.1
- **17.4** CI/CD: running the Module 16.4 eval suite and unit tests in GitHub Actions, building and pushing the image to GHCR on merge
- **17.5** Exposing the service through Cloudflare Tunnel exactly as you do for your other apps — no changes needed to your existing pattern, just pointing it at the new container
- **17.6** Secrets management in production — Docker secrets/env files, keeping API keys and DB credentials out of the image and out of git
- **17.7** Scaling considerations — when a slow tool (code execution, a slow external API) needs to move off the request/response path entirely into a queue (Redis-backed job queue you already have the pieces for) with the agent polling or resuming via `interrupt`/checkpointing

---

## Module 18 — Capstone Project

*Goal: build one real agent that exercises every module.*

- **18.1** Spec: an AI SaaS "ops assistant" agent with — a Postgres-backed tool (scoped by `InjectedToolArg` tenant id), a Redis cache tool, a self-hosted search tool (SearxNG), a sandboxed Docker code-execution tool, one tool consumed from an external MCP server, full error handling, human-in-the-loop approval on any write tool, tracing via Langfuse/OpenTelemetry, an eval suite in CI, and deployment via Docker Compose + GitHub Actions + GHCR + Cloudflare Tunnel
- **18.2** Build order: tools first (Modules 1–11) → graph wiring (Module 13) → interface polish (Module 14) → security pass (Module 15) → observability (Module 16) → ship (Module 17)
- **18.3** Post-mortem checklist: run through Module 15's security checklist and Module 16's observability checklist against your own capstone before calling it production-ready

---

### Suggested pacing
Modules 0–4: fundamentals, do these fully before anything else. Modules 5–11: pick the ones matching your actual product first (you likely need 6, 7, and 8 before 9). Modules 12–14: do these once you're comfortable, they make everything before them click. Modules 15–18: mandatory before real users touch the thing.
