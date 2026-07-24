# Enterprise RAG Observability: LangSmith + Langfuse (Zero to Production)

You already know loaders, chunking, embeddings, Qdrant, hybrid search, RRF, MMR, reranking,
metadata filtering, and evaluation. This guide assumes all of that and focuses **only** on
the layer that sits on top of your pipeline: **observability** — seeing, measuring, and
improving what your RAG system does once it's running.

---

## Part 1 — Theory: What is "Observability" for RAG, and why enterprises obsess over it

### 1.1 The core problem

A RAG pipeline is not one function call — it's a **chain of decisions**:

```
query → (maybe rewrite) → (decide: retrieve or not?) → (decide: which source?)
      → hybrid search → RRF fuse → MMR diversify → rerank → (grade docs: relevant?)
      → (maybe re-retrieve) → build prompt → LLM generate → (maybe grade answer)
      → return
```

When this breaks in production, you get one of these symptoms:
- "The answer was wrong" — but *which* step caused it? Bad retrieval? Bad rerank? Bad prompt? Hallucination despite good context?
- "It's slow" — is it the embedding call, Qdrant, the reranker, or the LLM?
- "It's expensive" — which node/user/tenant is burning tokens?
- "It worked yesterday" — did someone change a prompt? Did the LLM provider silently change model behavior?

**Observability = the tooling that answers these questions without you having to guess.**
It has three enterprise-grade pillars, borrowed from classic software observability (logs/metrics/traces) but adapted for LLM systems:

| Pillar | Classic software | LLM/RAG equivalent |
|---|---|---|
| **Traces** | Distributed request tracing (Jaeger/Zipkin) | Full run tree: every retriever call, every LLM call, every tool call, nested, with inputs/outputs |
| **Metrics** | Latency, error rate, throughput | Token usage, cost, latency per node, retrieval hit-rate, groundedness score |
| **Evaluation** | Unit tests / integration tests | LLM-as-judge scores, human feedback (👍/👎), regression testing on golden datasets |

**LangSmith** and **Langfuse** are the two dominant tools that give you all three, specifically
built for LLM/agent/RAG applications (not generic APM tools like Datadog, though those can be
used alongside them).

### 1.2 LangSmith vs Langfuse — when to use which

| | **LangSmith** | **Langfuse** |
|---|---|---|
| Made by | LangChain team | Independent (Langfuse GmbH) |
| Best with | LangChain / LangGraph (native, zero-config) | Framework-agnostic (LangChain, LlamaIndex, raw OpenAI SDK, anything) |
| Hosting | Managed cloud only (LangSmith SaaS) | Managed cloud **or self-hosted** (Docker/Kubernetes) — important for enterprises with data residency rules |
| Open source | Client SDK is OSS, backend is closed | Fully OSS (MIT), including backend |
| Evaluation | Very deep native `evaluate()` framework, datasets, experiments | Also has evaluation, scoring API, LLM-as-judge, slightly less "batteries included" but very flexible |
| Prompt management | LangSmith Hub | Langfuse Prompt Management (versioned, with rollback) |
| Pricing model | Per-trace, enterprise tiers | Per-observation, generous self-host free tier |

**In practice, most serious teams pick one as primary**, but this guide teaches both because:
1. Interviewers ask about both.
2. Many companies use LangSmith during LangChain/LangGraph development and Langfuse in production because they can self-host it (compliance) or because they're multi-framework.
3. You *can* run both simultaneously (I'll show you how) — this is actually a common pattern during a migration period.

### 1.3 Key vocabulary (used identically in both tools)

- **Trace** — one end-to-end run (e.g., one user question → one final answer). Has a unique ID.
- **Span / Observation** — one step inside a trace (a retriever call, an LLM call, a tool call). Spans nest inside each other, forming a tree.
- **Generation** — a special type of span specifically for LLM calls (captures prompt, completion, token counts, model name, cost).
- **Run** — LangSmith's word for "a trace or a span" (used interchangeably).
- **Session / Thread** — groups multiple traces that belong to the same conversation (multi-turn chat).
- **Dataset** — a curated set of (input, expected output) examples used for offline evaluation.
- **Experiment** — running your pipeline against a dataset and scoring the results, so you can compare prompt-version-A vs prompt-version-B.
- **Feedback / Score** — a numeric or categorical judgment attached to a trace — either from a human (👍/👎 in your UI) or from an automated evaluator (LLM-as-judge, exact match, etc.)

---

## Part 2 — Setup (do this once)

```bash
# Core RAG libs (you already have these, listed for completeness)
pip install langchain langchain-openai langchain-qdrant langgraph qdrant-client

# Observability libs
pip install langsmith langfuse
```

Get your keys:
- LangSmith: https://smith.langchain.com → Settings → API Keys
- Langfuse: https://cloud.langfuse.com (or your self-hosted URL) → Project Settings → API Keys (you get a **public** key and a **secret** key)

```bash
# .env file — never hardcode these in code
# --- LangSmith ---
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=enterprise-rag-prod      # groups traces, like a "folder"

# --- Langfuse ---
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com   # or your self-hosted URL

# --- Your LLM provider ---
OPENAI_API_KEY=sk-...
```

**Important enterprise note:** `LANGSMITH_TRACING=true` set as an env var means **every**
LangChain/LangGraph call in your process gets traced automatically — no code changes needed.
This is LangSmith's biggest selling point: it hooks into LangChain's internal callback system
globally. Langfuse achieves the same effect via an explicit `CallbackHandler` you attach, or
via `langfuse.langchain.CallbackHandler` — one extra line, not zero lines, but still no
per-call rewriting.

---

## Part 3 — Step 1: The absolute minimum trace (no RAG yet, just to see the mechanism)

### 3.1 LangSmith — tracing a plain Python function

```python
import os
from dotenv import load_dotenv

load_dotenv()  # loads LANGSMITH_API_KEY etc. from .env

# The @traceable decorator is LangSmith's core primitive.
# It works on ANY python function, not just LangChain objects.
# This is what you'd use to trace your own custom retrieval logic,
# your own reranker wrapper, your own routing function, etc.
from langsmith import traceable


@traceable(
    name="say_hello",  # human-readable name shown in the LangSmith UI
    run_type="chain",  # categorizes the span: "chain", "llm", "retriever", "tool", "parser"
)
def say_hello(name: str) -> str:
    # Whatever this function returns is captured as the "output" of the span.
    # Whatever args it receives are captured as the "input" of the span.
    return f"Hello, {name}!"


result = say_hello("Enterprise RAG learner")
print(result)

# --> Go to https://smith.langchain.com, open your project
#     "enterprise-rag-prod", and you will see ONE trace named "say_hello"
#     with input {"name": "..."} and output "Hello, ...!"
#     No manual logging code was written — the decorator did everything.
```

### 3.2 Langfuse — tracing the same function

```python
import os
from dotenv import load_dotenv

load_dotenv()

# Langfuse's equivalent decorator is @observe.
# Since Langfuse SDK v2/v3, this is the recommended way to trace arbitrary code.
from langfuse import observe


@observe(name="say_hello", as_type="span")  # as_type can be "span" or "generation"
def say_hello(name: str) -> str:
    return f"Hello, {name}!"


result = say_hello("Enterprise RAG learner")
print(result)

# --> Go to https://cloud.langfuse.com, open your project.
#     You'll see a trace "say_hello" with the same input/output captured.
# NOTE: Langfuse batches and flushes traces asynchronously in the background.
# In short scripts, call langfuse_client.flush() before the process exits,
# otherwise the last few traces might not be sent yet.
from langfuse import get_client

get_client().flush()
```

**What you just learned:** both tools give you a decorator that wraps a function and
auto-captures input/output/timing/errors. This is the foundation. Everything else
(nesting, metadata, RAG-specific fields) builds on this.

---

## Part 4 — Step 2: Tracing a real (but simple) RAG chain automatically

This is where LangSmith's "zero-config" advantage becomes obvious — because your retriever
and LLM are LangChain objects, tracing is **automatic** once the env var is set.

```python
import os
from dotenv import load_dotenv

load_dotenv()
# Just having LANGSMITH_TRACING=true in .env is enough. No decorator needed below.

from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

# --- Your existing Qdrant setup (you already know this part) ---
client = QdrantClient(url="http://localhost:6333")
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
vectorstore = QdrantVectorStore(
    client=client,
    collection_name="enterprise_docs",
    embedding=embeddings,
)
retriever = vectorstore.as_retriever(search_kwargs={"k": 5})

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

prompt = ChatPromptTemplate.from_template(
    "Answer the question using ONLY the context below.\n\n"
    "Context:\n{context}\n\nQuestion: {question}\nAnswer:"
)


def format_docs(docs):
    # Simple joiner — in your enterprise pipeline this is where you already
    # add citations/metadata, but keeping it simple here since the focus is tracing.
    return "\n\n".join(d.page_content for d in docs)


# LCEL (LangChain Expression Language) chain — this whole "|" pipeline
# is a Runnable, and every Runnable step automatically becomes its own
# nested span inside the trace, IN ORDER, with zero extra code.
rag_chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt
    | llm
    | StrOutputParser()
)

answer = rag_chain.invoke("What is our company's refund policy?")
print(answer)

# --> In LangSmith you will now see ONE trace named "RunnableSequence" containing
#     nested child spans in this exact order:
#       1. RunnableParallel (context + question)
#          -> retriever span (run_type="retriever") showing the k=5 docs it fetched,
#             their scores, and their content
#          -> format_docs span
#       2. ChatPromptTemplate span (shows the final filled-in prompt)
#       3. ChatOpenAI span (run_type="llm") showing exact prompt sent, completion
#          received, token counts (prompt_tokens, completion_tokens), latency, and COST
#       4. StrOutputParser span
#     This tree view is exactly what lets you debug "was it retrieval or generation
#     that went wrong" in one click.
```

### 4.1 The same chain, now also sent to Langfuse (running BOTH simultaneously)

```python
from langfuse.langchain import CallbackHandler

# This handler is LangChain's generic "callback" mechanism — the same mechanism
# LangSmith hooks into globally, except Langfuse asks you to pass it explicitly
# per-invocation (or bind it once to the chain). This is the ONLY code difference
# needed to ALSO get full Langfuse tracing on the exact same chain.
langfuse_handler = CallbackHandler()

answer = rag_chain.invoke(
    "What is our company's refund policy?",
    config={"callbacks": [langfuse_handler]},  # <-- the only addition
)
print(answer)

# --> Now BOTH LangSmith (via env var) AND Langfuse (via callback) recorded
#     the exact same trace tree, independently. Many companies do this
#     temporarily while migrating, or permanently if different teams
#     (ML team vs platform team) prefer different dashboards.
```

---

## Part 5 — Step 3: Enterprise metadata — tags, users, sessions, tenants

Raw traces are useless at scale unless you can **filter and group** them. Enterprises always
tag every trace with: who the user was, what tenant/customer they belong to, what environment
(dev/staging/prod), what app version, and what conversation/session it's part of.

```python
import uuid

user_id = "user_8231"
tenant_id = "acme_corp"  # multi-tenant SaaS: crucial for per-customer cost tracking
session_id = str(uuid.uuid4())  # groups multi-turn conversation traces together
app_version = "rag-pipeline-v2.3.1"

# ---------- LangSmith metadata/tags ----------
# LangSmith accepts "metadata" (a free-form dict, filterable in the UI)
# and "tags" (a list of strings, quick filters) via the `config` argument.
answer = rag_chain.invoke(
    "What is our refund policy?",
    config={
        "metadata": {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "session_id": session_id,
            "app_version": app_version,
        },
        "tags": ["prod", "refund-flow", tenant_id],
        # run_name overrides the default "RunnableSequence" trace name in the UI
        "run_name": "refund-policy-question",
    },
)

# ---------- Langfuse metadata/session/user ----------
# Langfuse has FIRST-CLASS fields for user_id and session_id (not just generic
# metadata) which unlocks built-in UI features: "show me this user's full history",
# "show me this conversation thread". This is one of Langfuse's strongest features.
langfuse_handler = CallbackHandler(
    # In Langfuse SDK v3, you set these via update_current_trace or pass in metadata;
    # shown here is the metadata-passthrough style compatible with LangChain configs:
)
answer = rag_chain.invoke(
    "What is our refund policy?",
    config={
        "callbacks": [langfuse_handler],
        "metadata": {
            "langfuse_user_id": user_id,  # special key Langfuse recognizes
            "langfuse_session_id": session_id,  # special key Langfuse recognizes
            "langfuse_tags": ["prod", "refund-flow", tenant_id],
            "tenant_id": tenant_id,
            "app_version": app_version,
        },
    },
)

# --> Enterprise payoff:
#     - In LangSmith: filter traces by metadata.tenant_id = "acme_corp" to see
#       exactly how much this customer is costing you, or filter by
#       tags contains "prod" AND "refund-flow" to see just that feature's traces.
#     - In Langfuse: click on "Users" tab -> user_8231 -> see EVERY trace,
#       total cost, total tokens, this user has ever generated. Click "Sessions"
#       -> see the full multi-turn conversation replayed in order.
```

---

## Part 6 — Step 4: Deciding WHEN to retrieve (adaptive/agentic RAG), fully traced

Enterprise RAG rarely retrieves blindly for every query. A "hi" or "thanks" doesn't need a
vector search. This decision itself is something you must **observe**, because a bad routing
decision (retrieving when unnecessary = wasted cost/latency; NOT retrieving when needed =
hallucination) is one of the most common production failure modes.

We use **LangGraph** for this because its explicit graph structure maps 1:1 onto trace spans —
every node you define becomes its own visible span automatically.

```python
from typing import TypedDict, Literal
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langsmith import traceable

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


# The shared state that flows between every node in the graph.
class RAGState(TypedDict):
    question: str
    needs_retrieval: bool
    context: str
    answer: str


# ---- Node 1: the "router" that decides whether retrieval is needed at all ----
# We wrap it with @traceable so it shows up as its own named span, separate
# from the generic node name LangGraph would otherwise assign.
@traceable(name="decide_retrieval", run_type="chain")
def decide_retrieval(state: RAGState) -> RAGState:
    # In production this is usually a small, fast, cheap LLM call (or even a
    # fine-tuned classifier) — NOT the same expensive model used for generation.
    router_prompt = (
        "Does answering this question require looking up company documents? "
        "Reply with ONLY 'yes' or 'no'.\n\n"
        f"Question: {state['question']}"
    )
    decision = llm.invoke(router_prompt).content.strip().lower()
    state["needs_retrieval"] = decision.startswith("y")
    return state


# ---- Conditional edge function: LangGraph calls this to pick the next node ----
# This function itself is traced too (as part of the graph's own instrumentation)
# and its return value is what determines the branch — this is the part you
# WANT to see clearly in your trace tree when debugging "why didn't it retrieve?"
def route_decision(state: RAGState) -> Literal["retrieve", "generate_direct"]:
    return "retrieve" if state["needs_retrieval"] else "generate_direct"


@traceable(name="retrieve_node", run_type="retriever")
def retrieve_node(state: RAGState) -> RAGState:
    docs = retriever.invoke(state["question"])
    state["context"] = "\n\n".join(d.page_content for d in docs)
    return state


@traceable(name="generate_with_context", run_type="chain")
def generate_with_context(state: RAGState) -> RAGState:
    answer = llm.invoke(
        f"Context:\n{state['context']}\n\nQuestion: {state['question']}"
    ).content
    state["answer"] = answer
    return state


@traceable(name="generate_direct_no_retrieval", run_type="chain")
def generate_direct(state: RAGState) -> RAGState:
    # No context needed — e.g. "hello", "thank you", general knowledge questions
    state["answer"] = llm.invoke(state["question"]).content
    return state


# ---- Assemble the graph ----
graph = StateGraph(RAGState)
graph.add_node("decide_retrieval", decide_retrieval)
graph.add_node("retrieve", retrieve_node)
graph.add_node("generate_with_context", generate_with_context)
graph.add_node("generate_direct", generate_direct)

graph.set_entry_point("decide_retrieval")
graph.add_conditional_edges(
    "decide_retrieval",
    route_decision,
    {"retrieve": "retrieve", "generate_direct": "generate_direct"},
)
graph.add_edge("retrieve", "generate_with_context")
graph.add_edge("generate_with_context", END)
graph.add_edge("generate_direct", END)

app = graph.compile()

# Run it — LANGSMITH_TRACING=true env var means the ENTIRE graph execution,
# every node, every conditional branch taken, is automatically traced as one tree.
result = app.invoke(
    {"question": "Hey, how are you?"},
    config={"run_name": "adaptive-rag-run", "tags": ["adaptive-routing"]},
)
print(result["answer"])

# --> In the LangSmith trace tree you will SEE:
#     decide_retrieval (output: needs_retrieval=False)
#       -> generate_direct_no_retrieval (skipped retrieve/generate_with_context entirely)
#     This is exactly the audit trail you need to prove/debug routing behavior,
#     e.g. "why did we spend money retrieving for a greeting?" never happens,
#     and conversely you can catch "why didn't it retrieve for this factual question?"
```

---

## Part 7 — Step 5: Multi-source routing (vector DB vs SQL vs web search vs cache), fully traced

Enterprises rarely have ONE knowledge source. A real system routes between: your Qdrant
vector store (unstructured docs), a SQL database (structured data — "how many orders did
customer X place"), a live web search (for very recent info), and a semantic cache (to skip
computation entirely for repeated questions — which you already know).

```python
from typing import Literal
from langchain_core.tools import tool

# Assume these already exist from your "hybrid search / caching" learning:
# - qdrant_hybrid_search(query) -> List[Document]
# - semantic_cache_lookup(query) -> Optional[str]
# - run_sql_query(sql: str) -> str


class MultiSourceState(TypedDict):
    question: str
    source: str
    context: str
    answer: str
    cache_hit: bool


@traceable(name="check_semantic_cache", run_type="retriever")
def check_cache(state: MultiSourceState) -> MultiSourceState:
    cached = semantic_cache_lookup(state["question"])  # your existing cache function
    state["cache_hit"] = cached is not None
    if cached:
        state["answer"] = cached
    return state


def route_after_cache(state: MultiSourceState) -> Literal["done", "route_source"]:
    return "done" if state["cache_hit"] else "route_source"


# The router itself: classifies which BACKEND should handle this query.
# This classification is a critical thing to trace, because misrouting
# ("sent a structured aggregation question to vector search") is a
# very common silent failure in enterprise systems — the pipeline runs fine,
# returns AN answer, just the WRONG kind of answer, and without tracing
# you'd never know the router picked wrong.
@traceable(name="route_to_source", run_type="chain")
def route_to_source(state: MultiSourceState) -> MultiSourceState:
    routing_prompt = (
        "Classify this question into exactly one category: "
        "'vector_docs' (policy/how-to/unstructured document questions), "
        "'sql' (numeric aggregation over structured order/customer data), "
        "or 'web' (requires current/real-time information).\n"
        f"Question: {state['question']}\nCategory:"
    )
    category = llm.invoke(routing_prompt).content.strip().lower()
    state["source"] = category
    return state


def pick_source_branch(state: MultiSourceState) -> Literal["vector_docs", "sql", "web"]:
    if "sql" in state["source"]:
        return "sql"
    if "web" in state["source"]:
        return "web"
    return "vector_docs"


@traceable(name="vector_retrieval", run_type="retriever")
def vector_branch(state: MultiSourceState) -> MultiSourceState:
    docs = retriever.invoke(state["question"])  # your existing hybrid+rerank retriever
    state["context"] = "\n\n".join(d.page_content for d in docs)
    return state


@traceable(name="sql_retrieval", run_type="retriever")
def sql_branch(state: MultiSourceState) -> MultiSourceState:
    # In production, an LLM first converts NL -> SQL, then you execute it.
    # We mark this whole thing as run_type="retriever" because conceptually
    # it plays the same role as a vector retriever: fetching grounding context.
    sql = llm.invoke(f"Write a SQL query for: {state['question']}").content
    state["context"] = run_sql_query(sql)  # your existing SQL executor
    return state


@traceable(name="web_retrieval", run_type="retriever")
def web_branch(state: MultiSourceState) -> MultiSourceState:
    from langchain_community.tools import DuckDuckGoSearchRun

    search = DuckDuckGoSearchRun()
    state["context"] = search.invoke(state["question"])
    return state


@traceable(name="final_generate", run_type="chain")
def final_generate(state: MultiSourceState) -> MultiSourceState:
    state["answer"] = llm.invoke(
        f"Context ({state['source']}):\n{state['context']}\n\n"
        f"Question: {state['question']}"
    ).content
    return state


graph = StateGraph(MultiSourceState)
graph.add_node("check_cache", check_cache)
graph.add_node("route_to_source", route_to_source)
graph.add_node("vector_docs", vector_branch)
graph.add_node("sql", sql_branch)
graph.add_node("web", web_branch)
graph.add_node("final_generate", final_generate)

graph.set_entry_point("check_cache")
graph.add_conditional_edges(
    "check_cache", route_after_cache, {"done": END, "route_source": "route_to_source"}
)
graph.add_conditional_edges(
    "route_to_source",
    pick_source_branch,
    {"vector_docs": "vector_docs", "sql": "sql", "web": "web"},
)
graph.add_edge("vector_docs", "final_generate")
graph.add_edge("sql", "final_generate")
graph.add_edge("web", "final_generate")
graph.add_edge("final_generate", END)

app = graph.compile()

result = app.invoke(
    {"question": "How many orders did we ship last week?"},
    config={
        "run_name": "multi-source-rag",
        "tags": ["multi-source", "sql-branch-expected"],
        "metadata": {"tenant_id": "acme_corp"},
    },
)
print(result.get("answer"))

# --> The trace tree now shows, for THIS specific question, exactly:
#     check_cache (cache_hit=False) -> route_to_source (source="sql")
#     -> sql (the exact SQL generated and its raw result) -> final_generate
#     If a customer complains "the number was wrong", you open this ONE trace
#     and immediately see the generated SQL — no guessing whether it was a
#     retrieval problem or a generation problem.
```

---

## Part 8 — Step 6: Full production-grade agentic RAG graph (Self-RAG style: grade + rewrite loop)

This combines everything: hybrid retrieval, reranking, self-grading of retrieved docs
(discard irrelevant ones), a rewrite-and-retry loop if grading fails, and generation —
all as one fully observable graph. This is close to what you'd actually deploy.

```python
from typing import List


class AgenticRAGState(TypedDict):
    question: str
    original_question: str
    documents: List[str]
    answer: str
    retry_count: int
    grade: str  # "relevant" | "not_relevant"


MAX_RETRIES = 2


@traceable(name="hybrid_retrieve_and_rerank", run_type="retriever")
def retrieve_node(state: AgenticRAGState) -> AgenticRAGState:
    # This is where YOUR existing hybrid search + RRF + MMR + cross-encoder
    # reranking pipeline plugs in. Since it's one @traceable-wrapped function,
    # it appears as ONE span, but you can go deeper by wrapping the internal
    # steps (hybrid_search, rrf_fuse, mmr, rerank) with their OWN @traceable
    # decorators too — nesting is unlimited, which is exactly how you'd debug
    # "was it the fusion step or the reranker that dropped the right doc?"
    docs = your_existing_hybrid_rerank_pipeline(state["question"])  # your function
    state["documents"] = [d.page_content for d in docs]
    return state


@traceable(name="grade_documents", run_type="chain")
def grade_documents(state: AgenticRAGState) -> AgenticRAGState:
    # LLM-as-judge grading EACH retrieved chunk for relevance — this is a
    # "self-RAG" pattern. We log the grade as part of the trace so you can
    # later analyze: "what % of retrievals are graded irrelevant?" as a
    # retrieval-quality metric over time.
    joined = "\n---\n".join(state["documents"])
    verdict = (
        llm
        .invoke(
            f"Question: {state['question']}\n\nRetrieved context:\n{joined}\n\n"
            "Is this context sufficient and relevant to answer the question? "
            "Reply ONLY 'relevant' or 'not_relevant'."
        )
        .content.strip()
        .lower()
    )
    state["grade"] = "relevant" if "not" not in verdict else "not_relevant"
    return state


def decide_after_grading(
    state: AgenticRAGState,
) -> Literal["generate", "rewrite", "give_up"]:
    if state["grade"] == "relevant":
        return "generate"
    if state["retry_count"] >= MAX_RETRIES:
        return "give_up"
    return "rewrite"


@traceable(name="rewrite_query", run_type="chain")
def rewrite_query(state: AgenticRAGState) -> AgenticRAGState:
    new_q = llm.invoke(
        f"The search query '{state['question']}' did not retrieve good results. "
        "Rewrite it to be clearer and more specific for a document search engine."
    ).content
    state["question"] = new_q
    state["retry_count"] += 1
    return state


@traceable(name="generate_final_answer", run_type="chain")
def generate(state: AgenticRAGState) -> AgenticRAGState:
    context = "\n\n".join(state["documents"])
    state["answer"] = llm.invoke(
        f"Answer using this context ONLY:\n{context}\n\nQuestion: {state['original_question']}"
    ).content
    return state


@traceable(name="give_up_gracefully", run_type="chain")
def give_up(state: AgenticRAGState) -> AgenticRAGState:
    # Enterprise best practice: NEVER let the bot silently hallucinate when it
    # can't find good info — degrade gracefully and say so, and make sure this
    # path is heavily tagged/tracked, because "give_up rate" is a key production
    # health metric (if it spikes, your retrieval or knowledge base has a gap).
    state["answer"] = (
        "I couldn't find reliable information to answer this confidently. "
        "Please rephrase or contact support."
    )
    return state


graph = StateGraph(AgenticRAGState)
graph.add_node("retrieve", retrieve_node)
graph.add_node("grade_documents", grade_documents)
graph.add_node("rewrite", rewrite_query)
graph.add_node("generate", generate)
graph.add_node("give_up", give_up)

graph.set_entry_point("retrieve")
graph.add_edge("retrieve", "grade_documents")
graph.add_conditional_edges(
    "grade_documents",
    decide_after_grading,
    {"generate": "generate", "rewrite": "rewrite", "give_up": "give_up"},
)
graph.add_edge("rewrite", "retrieve")  # loop back to retry retrieval
graph.add_edge("generate", END)
graph.add_edge("give_up", END)

app = graph.compile()

result = app.invoke(
    {
        "question": "refund window",
        "original_question": "refund window",
        "documents": [],
        "answer": "",
        "retry_count": 0,
        "grade": "",
    },
    config={
        "run_name": "self-rag-agentic",
        "tags": ["self-rag", "prod"],
        "metadata": {"tenant_id": "acme_corp", "pipeline_version": "v3"},
    },
)
print(result["answer"])

# --> If this looped (rewrite -> retrieve -> grade -> rewrite -> retrieve -> generate),
#     the trace tree shows the ENTIRE loop, every rewritten query, every re-grading,
#     which is invaluable for tuning MAX_RETRIES and your grading prompt.
```

---

## Part 9 — Step 7: Offline Evaluation — LangSmith `evaluate()` and Langfuse Datasets

Tracing tells you what happened for ONE request. **Evaluation** tells you, systematically,
whether your PIPELINE (as a whole, or after a prompt change) is getting better or worse,
using a curated dataset of known-good question/answer pairs (a "golden set").

### 9.1 LangSmith: create a dataset, run an experiment, auto-score with an LLM judge

```python
from langsmith import Client

ls_client = Client()

# --- 1. Create (or reuse) a dataset of golden examples ---
dataset_name = "refund-policy-golden-set"
dataset = ls_client.create_dataset(dataset_name=dataset_name)

golden_examples = [
    {"question": "What is the refund window?", "expected": "30 days from purchase"},
    {
        "question": "Can I get a refund on sale items?",
        "expected": "No, sale items are final",
    },
]
for ex in golden_examples:
    ls_client.create_example(
        inputs={"question": ex["question"]},
        outputs={"answer": ex["expected"]},
        dataset_id=dataset.id,
    )


# --- 2. Define the pipeline you want to evaluate (wraps your RAG chain) ---
def target(inputs: dict) -> dict:
    return {"answer": rag_chain.invoke(inputs["question"])}


# --- 3. Define an evaluator — here, an LLM-as-judge for correctness ---
from langsmith.evaluation import evaluate, LangChainStringEvaluator

correctness_evaluator = LangChainStringEvaluator(
    "labeled_criteria",
    config={
        "criteria": {
            "correctness": "Does the submitted answer match the reference answer in meaning?"
        },
        "llm": llm,  # the judge model — can be a different, more capable model than the pipeline itself
    },
)

# --- 4. Run the experiment ---
results = evaluate(
    target,
    data=dataset_name,
    evaluators=[correctness_evaluator],
    experiment_prefix="rag-v3-hybrid-rerank",  # lets you compare experiments over time
    metadata={"pipeline_version": "v3", "retriever": "hybrid+rrf+mmr+rerank"},
)

# --> Open LangSmith -> Datasets -> "refund-policy-golden-set" -> Experiments tab.
#     You now see a TABLE: each row = one golden question, columns = your answer,
#     the reference answer, the correctness score, and latency/cost per row.
#     Run this again after changing your prompt or reranker and LangSmith
#     shows a SIDE-BY-SIDE diff of experiment "v3" vs "v4" — this is how
#     enterprises prevent prompt-change regressions before shipping.
```

### 9.2 Langfuse: dataset + experiment run + scoring

```python
from langfuse import get_client

langfuse = get_client()

# --- 1. Create a dataset ---
langfuse.create_dataset(name="refund-policy-golden-set")
for ex in golden_examples:
    langfuse.create_dataset_item(
        dataset_name="refund-policy-golden-set",
        input={"question": ex["question"]},
        expected_output={"answer": ex["expected"]},
    )

# --- 2. Fetch dataset and run your pipeline against every item ---
dataset = langfuse.get_dataset("refund-policy-golden-set")

for item in dataset.items:
    # `item.observe()` links this specific run back to the dataset item,
    # so Langfuse can show pass/fail per golden example, same as LangSmith.
    with item.observe(run_name="rag-v3-hybrid-rerank") as trace_id:
        answer = rag_chain.invoke(item.input["question"])

        # --- 3. Score it (here: simple automated LLM-judge scoring) ---
        judge_verdict = (
            llm
            .invoke(
                f"Reference: {item.expected_output['answer']}\n"
                f"Submitted: {answer}\nDoes the submitted answer match? yes/no"
            )
            .content.strip()
            .lower()
        )
        score = 1.0 if "yes" in judge_verdict else 0.0

        langfuse.create_score(
            trace_id=trace_id,
            name="correctness",
            value=score,
            comment=f"Judge said: {judge_verdict}",
        )

langfuse.flush()
# --> In Langfuse -> Datasets -> "refund-policy-golden-set" -> Runs, you get the
#     same side-by-side comparison table across experiment runs.
```

### 9.3 Online evaluation + human feedback (production, not offline)

```python
# ---------- LangSmith: attach human feedback to a LIVE trace ----------
from langsmith import Client

ls_client = Client()

# In your app's UI, when a user clicks 👍 or 👎 on a chatbot answer, you already
# have the run_id (LangSmith returns it when you invoke with return_run_id / callbacks).
ls_client.create_feedback(
    run_id="the-run-id-of-that-specific-answer",
    key="user_thumbs",
    score=1,  # 1 = thumbs up, 0 = thumbs down
    comment="Correct and fast!",
)

# ---------- Langfuse: same idea ----------
langfuse.create_score(
    trace_id="the-trace-id-of-that-answer",
    name="user_thumbs",
    value=1,
    data_type="BOOLEAN",
)

# --> Enterprise pattern: dashboard showing "thumbs-up rate over time, sliced
#     by tenant / prompt-version / retriever config" — this is your #1
#     production health signal, better than any offline benchmark, because
#     it reflects REAL user judgment on REAL traffic.
```

---

## Part 10 — Enterprise-grade production concerns

### 10.1 Cost & token tracking (multi-tenant billing)

Both tools auto-capture `prompt_tokens`, `completion_tokens`, and estimated `$cost` per LLM
generation span, because they know the model name and current pricing tables. The enterprise
work is **aggregating** this by tenant/user:

```python
# LangSmith: query traces filtered by metadata, sum costs, in Python (or use the UI's
# built-in "Usage" / cost dashboards, which already group by project automatically).
from langsmith import Client

client = Client()

runs = client.list_runs(
    project_name="enterprise-rag-prod",
    filter='and(eq(metadata_key, "tenant_id"), eq(metadata_value, "acme_corp"))',
)
total_cost = sum(r.total_cost or 0 for r in runs)
print(f"acme_corp spent: ${total_cost:.4f} this period")

# Langfuse: has a native Usage/Cost dashboard sliced by any metadata field,
# and an API for it too:
from langfuse import get_client

langfuse = get_client()
# Langfuse Cloud UI: Dashboards -> Usage, filterable by tags/user/session out of the box.
```

### 10.2 Prompt versioning (never hardcode prompts in production code)

```python
# ---------- LangSmith Hub: pull a versioned, centrally-managed prompt ----------
from langsmith import Client

client = Client()

# Prompts are pushed once (e.g. from a notebook or CI job) and pulled at runtime.
# This means a prompt-engineer can update the prompt WITHOUT a code deploy,
# and every version is tracked with a commit hash for rollback.
prompt_template = client.pull_prompt("my-org/refund-rag-prompt:production")

# ---------- Langfuse Prompt Management: same idea ----------
from langfuse import get_client

langfuse = get_client()

lf_prompt = langfuse.get_prompt("refund-rag-prompt", label="production")
compiled = lf_prompt.compile(context="...", question="...")
# Langfuse links every trace back to the EXACT prompt version used,
# so "we changed the prompt and quality dropped" is instantly diagnosable.
```

### 10.3 Sampling (don't trace 100% of traffic at massive scale — control cost)

```python
# LangSmith supports sampling via an env var — trace only a % of runs in high-volume prod:
import os

os.environ["LANGSMITH_TRACING_SAMPLING_RATE"] = "0.1"  # trace ~10% of requests

# Langfuse: implement sampling yourself around the callback handler,
# or use their `sample_rate` param on some SDK versions:
import random


def maybe_get_callbacks():
    if random.random() < 0.1:
        return [CallbackHandler()]
    return []
```

### 10.4 PII redaction before data leaves your infra

```python
# Both LangSmith and Langfuse let you register a "masking function" that runs
# BEFORE data is sent over the network — critical for GDPR/HIPAA compliance.

# Langfuse example:
from langfuse import Langfuse
import re


def mask_pii(data):
    if isinstance(data, str):
        # crude example: redact emails before they ever leave your servers
        return re.sub(r"[\w\.-]+@[\w\.-]+", "[REDACTED_EMAIL]", data)
    return data


langfuse = Langfuse(mask=mask_pii)

# LangSmith equivalent: use `hide_inputs` / `hide_outputs` processing functions
# configured on the Client, or a custom RunTree processor, to strip/replace
# sensitive fields before they're transmitted.
```

### 10.5 Self-hosting Langfuse (common enterprise requirement)

```bash
# Langfuse is fully open-source; enterprises with data-residency requirements
# self-host it via Docker Compose (or Helm chart for Kubernetes):
git clone https://github.com/langfuse/langfuse.git
cd langfuse
docker compose up -d
# Then point LANGFUSE_HOST at your internal URL, e.g. http://langfuse.internal:3000
```

### 10.6 Alerting (know about failures before your users complain)

Neither tool has generic "PagerDuty-style" alerting built in as a first-class citizen — the
enterprise pattern is: **export metrics via their APIs on a schedule, or use their webhook /
Slack integrations**, feeding into your existing monitoring stack (Datadog, Grafana, PagerDuty).

```python
# Simplified scheduled job (e.g. a cron / Airflow task) checking error rate & give_up rate:
from langsmith import Client

client = Client()

recent_runs = client.list_runs(project_name="enterprise-rag-prod", limit=1000)
error_rate = sum(1 for r in recent_runs if r.error) / len(recent_runs)

if error_rate > 0.05:
    # send_slack_alert(...) / trigger_pagerduty(...) - your existing infra
    print("ALERT: RAG error rate above 5% in the last 1000 requests")
```

---

## Part 11 — Beginner Mistakes (avoid these)

1. **Not setting a `run_name` / trace name** — everything shows up as "RunnableSequence", and after a week of traces you can't tell them apart. Always set meaningful `run_name`s and `tags`.
2. **Forgetting `langfuse.flush()`** in short scripts (or serverless functions like AWS Lambda) — the SDK batches sends in the background thread, and the process exits before the batch is sent, silently losing traces.
3. **Tracing only the top-level chain, not the internal steps** — wrapping your hybrid-search/RRF/MMR/rerank pipeline as ONE opaque function means you lose the ability to tell which sub-step is slow or wrong. Wrap each meaningful sub-step with its own `@traceable`/`@observe`.
4. **Never attaching `user_id`/`session_id`/`tenant_id`** — you'll have thousands of anonymous traces and no way to debug "customer X's" specific complaint or measure per-tenant cost.
5. **Confusing "evaluation" with "tracing"** — tracing shows you what happened; it does NOT tell you if the answer was *correct*. You still need a golden dataset and evaluators, run regularly (ideally in CI, on every prompt/retriever change).
6. **Hardcoding prompts in source code** instead of using prompt versioning (LangSmith Hub / Langfuse Prompt Management) — makes it impossible to A/B test or roll back a bad prompt without a full code deploy.
7. **Tracing 100% of production traffic with zero sampling** at huge scale, and being surprised by the observability bill — plan sampling rates deliberately.
8. **Sending PII/secrets into traces unmasked** — inputs/outputs are captured verbatim by default; without a masking function, customer emails, SSNs, etc. end up sitting in a third-party SaaS dashboard.
9. **Only using LLM-as-judge for evaluation, never human feedback** — LLM judges have their own biases/blind spots; production `thumbs_up`/`thumbs_down` from real users is your ground truth and should always be collected too.
10. **Not comparing experiments** — running an eval once after building the pipeline and never again. The value of a golden dataset is in *repeated* runs after every meaningful change, diffed against previous experiments.
11. **Ignoring the "give_up"/fallback path** — not tracking how often your agent bails out ungracefully or gives a low-confidence answer is a huge blind spot; this rate is often the earliest signal of a knowledge-base gap or embedding drift.
12. **Forgetting to grade retrieval separately from generation** — a "good" final answer can hide a bad retrieval that got lucky, and a "bad" final answer can hide great retrieval ruined by a bad prompt. Always track retrieval-quality metrics (precision@k, grading pass-rate) *independently* of end-to-end answer quality.

---

## Part 12 — Interview Questions & Answers (Intermediate → Advanced)

**Q1. What's the difference between a "trace" and a "span"?**
A trace is the root-level record of one complete end-to-end execution (e.g., one user query
through your whole RAG pipeline) and has one unique trace ID. A span (LangSmith calls it a
"run") is any single step *within* that trace — a retriever call, an LLM call, a tool call.
Spans nest to form a tree; the trace is the root of that tree.

**Q2. Why would an enterprise choose Langfuse over LangSmith even though LangSmith has deeper native LangChain integration?**
Primarily **self-hosting** for data residency/compliance (Langfuse is fully open-source and
can run entirely inside your VPC), and **framework independence** — if part of your stack uses
LlamaIndex, raw OpenAI SDK calls, or a custom agent framework alongside LangChain/LangGraph,
Langfuse's `@observe` decorator and manual span API work identically everywhere, whereas
LangSmith's zero-config tracing is strongest specifically within the LangChain ecosystem.

**Q3. How does LangSmith automatically trace a LangChain/LangGraph pipeline with zero code changes?**
LangChain has an internal callback-manager system that every `Runnable` (chains, retrievers,
LLMs, parsers, LangGraph nodes) invokes at each lifecycle event (`on_chain_start`,
`on_llm_end`, etc.). When `LANGSMITH_TRACING=true` is set, LangSmith registers a global
callback handler that listens to these events and streams them to the LangSmith backend,
building the nested trace tree automatically — no explicit instrumentation per call needed.

**Q4. In an agentic/self-RAG loop with a rewrite-and-retry mechanism, what specific observability signal would you monitor to catch an infinite-loop or excessive-retry problem in production before it drains your budget?**
Track (a) the distribution of `retry_count` per trace (a spike toward `MAX_RETRIES` across many
traces signals a systemic retrieval/knowledge-base problem, not a one-off), and (b) total
tokens/cost *per trace* (not per LLM call) — a single trace's cost quietly ballooning due to
repeated rewrite+retrieve+grade cycles is the clearest early warning, best caught via an
automated alert on a "cost per trace" percentile (e.g., p99) rather than an average.

**Q5. What's the difference between offline evaluation and online evaluation, and why do you need both?**
Offline evaluation runs your pipeline against a fixed, curated "golden" dataset with known
expected outputs, before shipping a change — it answers "did this prompt/retriever change
improve or regress accuracy on cases we already understand?" Online evaluation scores *live*
production traffic (via LLM-as-judge run continuously on real traces, and/or real user
feedback like thumbs up/down) — it answers "how is the system actually performing on the
messy, unpredictable distribution of real user queries, including ones not in our golden set?"
Offline catches regressions pre-deploy; online catches distribution drift and unknown-unknowns
post-deploy. Enterprises need both — offline as a CI gate, online as continuous monitoring.

**Q6. How would you debug a production complaint "the chatbot gave a wrong answer" using LangSmith or Langfuse, step by step?**
1. Find the specific trace (via `session_id`/`user_id` metadata filter, or the run_id the
   frontend logged).
2. Open the trace tree and inspect the **retriever span** first — did it retrieve the right
   documents at all? Check the doc content and similarity/rerank scores.
3. If retrieval was fine, inspect the **grading span** (if using self-RAG) — was a relevant doc
   incorrectly graded as irrelevant, causing a bad rewrite loop?
4. If both are fine, inspect the **prompt** actually sent to the LLM (the exact rendered
   template, not just the raw template) — often the bug is in how context was formatted/truncated.
5. Check the **LLM generation span** for the raw completion and finish_reason (did it get
   cut off by max_tokens?).
6. Attach a negative feedback score to the trace and, if it reveals a systemic gap, add it as
   a new golden example to your evaluation dataset so future prompt/retriever changes are
   tested against this exact failure case going forward.

**Q7. Explain how you'd design cost attribution in a multi-tenant enterprise RAG SaaS product.**
Tag every trace at invocation time with `tenant_id` (and ideally `user_id`, `feature_name`,
`app_version`) via the `metadata`/`tags` config on every chain/graph invocation. Both tools
capture token counts and computed `$cost` per LLM generation span automatically. Periodically
(batch job) query/export runs filtered by `metadata.tenant_id`, sum `total_cost` per tenant,
and feed that into your billing/usage system. For real-time dashboards, Langfuse's built-in
Usage dashboard can be filtered live by these metadata fields without custom code; for
LangSmith, you'd typically build this via their API + your own BI layer.

**Q8. Why is it important to trace the routing/decision logic (e.g., "retrieve or not," "which source") as its own explicit span rather than letting it happen inside a single opaque LLM call?**
Because routing decisions are a distinct failure mode from retrieval or generation failures —
if you don't isolate the routing span, "the SQL branch got the wrong data" and "the router
picked SQL when it should have picked vector search" look identical from the outside (both
produce a wrong final answer). An explicit, named, traced routing span lets you directly see
the classification decision and its input, letting you distinguish a routing bug from a
downstream retrieval/generation bug in one glance at the trace tree, and lets you compute a
routing-accuracy metric independently in evaluation.

**Q9. What are the tradeoffs of tracing 100% of production traffic versus sampling?**
100% tracing gives complete auditability (essential for regulated industries and for catching
rare-but-critical failures) but costs more (both in observability platform fees and in
network/latency overhead of shipping every trace) and can generate more data than is
practically reviewable. Sampling (e.g., 10%) reduces cost and noise but risks missing rare
edge-case failures entirely unless combined with **always-trace-on-error** logic (trace 100%
of runs that error or receive negative feedback, sample the rest) — which is the pattern most
mature teams land on: full sampling for anomalies, statistical sampling for the "healthy" baseline.

**Q10. How would you set up a CI/CD gate that prevents a prompt or retriever change from being deployed if it regresses quality?**
Maintain a versioned golden dataset (LangSmith Dataset or Langfuse Dataset) representative of
real production query patterns and known edge cases. In your CI pipeline, on every PR that
touches prompts/retrieval logic, run `evaluate()` (LangSmith) or the dataset-runner pattern
(Langfuse) against the new code, scoring with both automated evaluators (LLM-as-judge for
correctness/groundedness) and any exact-match/regex checks that apply. Compare the aggregate
score against the last known-good experiment's baseline (stored/tagged, e.g., via
`experiment_prefix` naming or Langfuse dataset run names); fail the build if the score drops
beyond an agreed threshold (e.g., more than 2 percentage points), and require manual review/
override for intentional tradeoffs.

**Q11. What is "groundedness" as an evaluation metric, and how is it typically computed with LLM-as-judge?**
Groundedness measures whether the generated answer is actually supported by the retrieved
context (as opposed to being fluent but hallucinated). It's typically computed by giving a
judge LLM both the retrieved context and the generated answer and asking it to verify each
claim in the answer against the context, scoring the fraction of claims that are supported (or
a simple relevant/not-relevant-style binary/categorical judgment for simpler setups). This is
distinct from "correctness" (does it match a reference answer) — an answer can be grounded but
still wrong if the retrieved context itself was incorrect/outdated, which is why enterprises
track groundedness and correctness as *separate* scores.

**Q12. In a LangGraph-based agentic RAG system, why does using `@traceable` (or manual instrumentation) on internal helper functions inside a node matter, even though LangGraph nodes are already auto-traced as spans?**
LangGraph auto-traces at the **node** granularity — one span per node in your graph. If a
single node internally calls hybrid search, then RRF fusion, then MMR diversification, then
cross-encoder reranking, all four of those happen *inside* one opaque node-level span unless
you explicitly wrap each sub-step with its own `@traceable`. Without that finer-grained
instrumentation, you can see the node's overall input/output/latency but not which internal
step consumed the most time or which step is responsible for a quality drop (e.g., did MMR
diversification remove the one document that actually had the answer, or did the reranker
demote it?). Enterprises instrument at the granularity they need to debug at.
