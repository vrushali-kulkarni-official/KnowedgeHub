# Production RAG: Caching, Async, Batching, Streaming, Observability & Cost

You've already built the "intelligence" layer (chunking, embeddings, retrieval, re-ranking, eval).
This guide covers the "engineering" layer — the stuff that makes a RAG pipeline survive real
traffic, real latency budgets, and a real AWS bill. Every section = concept + why it matters in
production + actual heavily-commented code.

---

## 1. CACHING

### What it is
Storing the result of an expensive operation (embedding a string, calling an LLM, retrieving docs)
so you don't pay the latency/$ cost again for the same (or similar-enough) input.

### Why production systems need it
- LLM calls are the slowest + most expensive part of a RAG pipeline (500ms–5s, $0.001–$0.06/call).
- In real traffic, **the same or near-duplicate questions repeat constantly** ("what's your refund
  policy?" gets asked 500 times/day in a support bot).
- Embedding the same chunk twice (e.g. on re-deploy) wastes money for identical output.

### Layers of caching used in real systems

| Layer | What's cached | Tool |
|---|---|---|
| Exact-match LLM cache | prompt → response (exact string match) | LangChain `InMemoryCache`, Redis |
| Semantic cache | similar (not identical) query → response | GPTCache, Redis + embeddings |
| Embedding cache | text → vector (avoid re-embedding same chunk) | Redis, local disk, `CacheBackedEmbeddings` |
| Retrieval cache | query → retrieved doc IDs | Redis with TTL |
| HTTP/CDN cache | full API response | Cloudflare, nginx |

### Code: Embedding cache (avoid re-embedding identical chunks)

```python
"""
EMBEDDING CACHE
---------------
Problem: every time your ingestion pipeline runs (e.g. on a CI re-deploy, or because
you re-process a folder), it re-embeds chunks that haven't changed. Embedding calls
cost money and time. We cache by content hash so identical text is NEVER re-embedded.
"""

from langchain.embeddings import CacheBackedEmbeddings
from langchain.storage import LocalFileStore  # swap for RedisStore in prod
from langchain_openai import OpenAIEmbeddings

# 1. The "real" embedder that actually calls the API (expensive)
underlying_embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

# 2. A persistent key-value store. LocalFileStore is fine for a single machine /
#    dev. In production with multiple workers, use RedisStore so every worker
#    shares the same cache.
#    from langchain.storage import RedisStore
#    store = RedisStore(redis_url="redis://localhost:6379")
store = LocalFileStore("./.embedding_cache/")

# 3. Wrap the embedder. CacheBackedEmbeddings automatically:
#    - hashes the input text (namespace + content) to form a cache key
#    - checks the store before calling the underlying model
#    - writes the result to the store after a cache miss
cached_embedder = CacheBackedEmbeddings.from_bytes_store(
    underlying_embeddings,
    store,
    namespace="text-embedding-3-small",  # bump this if you change the model -
    # prevents stale vectors from a different
    # model silently mixing into your index
)

texts = [
    "LangChain makes LLM apps easier to build.",
    "LangChain makes LLM apps easier to build.",
]

# First call: 1 cache miss -> hits OpenAI API, 1 cache hit (duplicate in the same batch)
# Second run of this whole script: BOTH are cache hits -> zero API calls, near-zero latency
vectors = cached_embedder.embed_documents(texts)
print(f"Got {len(vectors)} vectors, dim={len(vectors[0])}")
```

### Code: Exact-match LLM response cache

```python
"""
EXACT-MATCH LLM CACHE
----------------------
Problem: if your app gets the literal same prompt twice (common with deterministic
system prompts + FAQ-style queries), you're paying for the same generation twice.
LangChain's global cache intercepts identical (prompt, model, params) tuples.
"""

import langchain
from langchain_community.cache import SQLiteCache
from langchain_openai import ChatOpenAI

# SQLiteCache persists across process restarts (good for a single-server app).
# In a multi-instance prod deployment, use RedisCache so all instances share hits:
#   from langchain_community.cache import RedisCache
#   langchain.llm_cache = RedisCache(redis_=redis_client)
langchain.llm_cache = SQLiteCache(database_path=".langchain_llm_cache.db")

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)  # temperature=0 is IMPORTANT:
# caching only makes sense for deterministic-ish calls. If temperature > 0, every
# call is "supposed" to be different, so caching gives you stale/wrong-feeling repeats.

import time

start = time.time()
r1 = llm.invoke("What is the capital of France?")
print(f"First call: {time.time() - start:.2f}s")  # real API call

start = time.time()
r2 = llm.invoke("What is the capital of France?")
print(f"Second call (cached): {time.time() - start:.2f}s")  # near-instant, $0 cost
```

### Code: Semantic cache (the real production pattern)

```python
"""
SEMANTIC CACHE
--------------
Exact-match caching fails on real user traffic because users phrase the same
question differently: "how do I reset my password" vs "password reset steps"
vs "I forgot my password help". A semantic cache embeds the incoming query and
checks if a SIMILAR query was answered recently (cosine similarity above a
threshold) — if so, it returns the cached answer instead of calling the LLM.

This is the single highest-leverage caching technique for customer-facing RAG bots.
"""

import hashlib
import time
from langchain_openai import OpenAIEmbeddings
import numpy as np


class SemanticCache:
    def __init__(
        self,
        embedder: OpenAIEmbeddings,
        similarity_threshold: float = 0.95,
        ttl_seconds: int = 3600,
    ):
        self.embedder = embedder
        self.threshold = similarity_threshold
        self.ttl = ttl_seconds
        # In prod, replace this list with a small vector DB (e.g. a dedicated
        # Redis/FAISS index just for cache entries) so lookups stay O(log n)
        # instead of O(n) as the cache grows.
        self.entries = []  # list of dicts: {vector, query, response, timestamp}

    def _cosine_sim(self, a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    def get(self, query: str):
        now = time.time()
        # Drop expired entries lazily (cheap; avoids a separate background job for a demo)
        self.entries = [e for e in self.entries if now - e["timestamp"] < self.ttl]

        query_vec = np.array(self.embedder.embed_query(query))
        best_score, best_entry = 0.0, None
        for e in self.entries:
            score = self._cosine_sim(query_vec, e["vector"])
            if score > best_score:
                best_score, best_entry = score, e

        if best_entry and best_score >= self.threshold:
            print(
                f"[semantic cache HIT] similarity={best_score:.3f} matched: '{best_entry['query']}'"
            )
            return best_entry["response"]
        print(f"[semantic cache MISS] best similarity was {best_score:.3f}")
        return None

    def set(self, query: str, response: str):
        vec = np.array(self.embedder.embed_query(query))
        self.entries.append({
            "vector": vec,
            "query": query,
            "response": response,
            "timestamp": time.time(),
        })


# --- usage inside a RAG pipeline ---
embedder = OpenAIEmbeddings(model="text-embedding-3-small")
cache = SemanticCache(embedder, similarity_threshold=0.93)


def answer_question(query: str, rag_chain) -> str:
    cached = cache.get(query)
    if cached:
        return cached  # skip retrieval AND generation entirely
    response = rag_chain.invoke(query)  # your real RAG chain (retrieval + LLM)
    cache.set(query, response)
    return response
```

**Production note on thresholds:** 0.95+ similarity is "safe" (near-duplicate phrasing only).
Going lower (0.85) catches more paraphrases but risks returning a *wrong* cached answer for a
question that's similar-but-not-the-same — tune this against your eval set, don't guess.

---

## 2. ASYNC PROCESSING

### What it is
Running I/O-bound operations (API calls, DB queries, network requests) concurrently instead of
sequentially, using `asyncio`, so your program isn't blocked waiting on one call before starting
the next.

### Why it matters for RAG
A single RAG request often does several *independent* I/O calls:
- embed the query
- retrieve from vector DB
- (maybe) call a re-ranker API
- call the LLM

And a **batch** job (e.g. evaluating 500 test questions) does the same request 500 times.
Doing these sequentially means total time = sum of all latencies. Async means total time ≈ the
slowest one (for concurrent independent calls) or massively reduced (for batches).

### Code: Async RAG chain (query embedding + retrieval + generation)

```python
"""
ASYNC RAG PIPELINE
-------------------
Every LangChain component (LLMs, retrievers, embeddings) has an async twin:
invoke -> ainvoke, embed_query -> aembed_query, get_relevant_documents -> aget_relevant_documents.

Using these lets FastAPI (or any async web server) serve MANY concurrent users
without spinning up a thread per request.
"""

import asyncio
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import FAISS

llm = ChatOpenAI(model="gpt-4o-mini")
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

# Assume `vectorstore` was already built during ingestion
# vectorstore = FAISS.load_local("my_index", embeddings)


async def async_rag_answer(query: str, vectorstore) -> str:
    # 1. Async retrieval — doesn't block the event loop while waiting on the vector DB
    docs = await vectorstore.asimilarity_search(query, k=4)
    context = "\n\n".join(d.page_content for d in docs)

    prompt = f"""Answer using only this context:\n{context}\n\nQuestion: {query}"""

    # 2. Async LLM call — this is the big one. While this request is waiting on
    #    OpenAI's servers, the event loop is free to handle OTHER users' requests.
    response = await llm.ainvoke(prompt)
    return response.content


async def handle_many_users(queries: list[str], vectorstore):
    """
    This is what actually happens under real traffic: many users hit your
    /chat endpoint at roughly the same time. asyncio.gather runs all of them
    CONCURRENTLY on a single process/thread instead of queueing them one by one.
    """
    tasks = [async_rag_answer(q, vectorstore) for q in queries]
    results = await asyncio.gather(*tasks)
    return results


# Example: 10 simultaneous users, each query taking ~2s if run alone.
# Sequential: ~20s total. Concurrent (async): ~2-3s total (bounded mainly by
# the LLM provider's own concurrency limits, not your code).
```

### Code: Async + concurrency limiting (don't blow your rate limit)

```python
"""
RATE-LIMITED ASYNC PROCESSING
-------------------------------
Naive asyncio.gather() on 1000 items will fire 1000 requests at once and get you
429 RATE LIMITED by your LLM/embedding provider. Real systems bound concurrency
with a Semaphore so you stay under the provider's limit while still going as
fast as the limit allows.
"""

import asyncio


async def bounded_embed(texts: list[str], embedder, max_concurrency: int = 10):
    semaphore = asyncio.Semaphore(max_concurrency)  # only N calls in flight at once

    async def embed_one(text: str):
        async with semaphore:  # blocks here if N calls are already running
            return await embedder.aembed_query(text)

    tasks = [embed_one(t) for t in texts]
    return await asyncio.gather(*tasks)


# This pattern — Semaphore + gather — is THE standard production pattern for
# "process N items concurrently, but not more than K at a time."
```

### FastAPI: serving RAG asynchronously (real deployment shape)

```python
"""
FASTAPI ASYNC ENDPOINT
------------------------
This is the actual shape of a production RAG API server. Note `async def` on
the route — this is what lets uvicorn/FastAPI handle many concurrent requests
on one process without threads.
"""

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class ChatRequest(BaseModel):
    query: str
    session_id: str


@app.post("/chat")
async def chat(req: ChatRequest):
    cached = cache.get(req.query)  # semantic cache from Section 1
    if cached:
        return {"answer": cached, "cached": True}

    answer = await async_rag_answer(req.query, vectorstore)
    cache.set(req.query, answer)
    return {"answer": answer, "cached": False}


# Run with: uvicorn app:app --workers 4
# --workers spins up multiple PROCESSES (for CPU parallelism / resilience);
# within each process, async handles many concurrent I/O-bound requests.
```

---

## 3. BATCHING

### What it is
Grouping multiple individual items into a single request to amortize fixed overhead (network
round-trip, model load, tokenization setup) across many items at once.

### Why it matters for RAG
- **Embedding 10,000 chunks one at a time** = 10,000 HTTP round trips. Batching them into groups
  of 100–2000 (provider-dependent limit) cuts wall-clock time by 10–50x.
- **LLM batch APIs** (OpenAI Batch API, Anthropic Batch API) cost ~50% less than synchronous calls
  in exchange for a 24h turnaround — perfect for offline eval runs, not for live chat.

### Code: Batched embedding during ingestion

```python
"""
BATCHED EMBEDDING INGESTION
------------------------------
Naive (slow, expensive in round trips):
    vectors = [embedder.embed_query(chunk) for chunk in all_chunks]   # DON'T

Batched (fast):
    embed_documents() internally chunks the list and sends fewer, larger requests.
"""

from langchain_openai import OpenAIEmbeddings

embedder = OpenAIEmbeddings(
    model="text-embedding-3-small",
    chunk_size=1000,  # max items per underlying API call — OpenAI's embeddings
    # endpoint accepts batches; LangChain auto-splits your
    # full list into chunk_size-sized batches and fires them.
)

all_chunks = [
    f"chunk number {i}" for i in range(5000)
]  # pretend this came from your chunker

# Internally this becomes 5 batched API calls (5000 / 1000), not 5000 individual calls.
vectors = embedder.embed_documents(all_chunks)
print(
    f"Embedded {len(vectors)} chunks via {len(all_chunks) // 1000 + 1} batched API calls"
)
```

### Code: Manual batching with a generator (control memory + progress)

```python
"""
MANUAL BATCH PROCESSING WITH PROGRESS TRACKING
-------------------------------------------------
For huge corpora (millions of chunks) you don't want everything in memory at
once, and you want to checkpoint progress so a crash doesn't mean starting over.
"""

from itertools import islice
from typing import Iterator


def batched(iterable, batch_size: int) -> Iterator[list]:
    """Splits any iterable into lists of size batch_size (last batch may be smaller)."""
    it = iter(iterable)
    while batch := list(islice(it, batch_size)):
        yield batch


def ingest_large_corpus(
    chunk_iterator,
    embedder,
    vectorstore,
    batch_size: int = 500,
    checkpoint_path: str = "ingest_progress.txt",
):
    # Resume support: if we crashed halfway, skip chunks already processed
    processed_count = 0
    try:
        with open(checkpoint_path) as f:
            processed_count = int(f.read().strip())
    except FileNotFoundError:
        pass

    for i, batch in enumerate(batched(chunk_iterator, batch_size)):
        batch_start_idx = i * batch_size
        if batch_start_idx < processed_count:
            continue  # already done, skip (resume logic)

        texts = [c.page_content for c in batch]
        vectors = embedder.embed_documents(
            texts
        )  # one batched call per `batch_size` chunks
        vectorstore.add_embeddings(zip(texts, vectors))

        # Checkpoint after every batch so a crash only costs you one batch of work
        with open(checkpoint_path, "w") as f:
            f.write(str(batch_start_idx + len(batch)))

        print(f"Ingested batch {i + 1}: {len(batch)} chunks")
```

### Code: LLM Batch API for offline evaluation (50% cheaper)

```python
"""
LLM BATCH API (OpenAI) — for offline / non-realtime workloads
-----------------------------------------------------------------
Use case: you're running RAGAS evaluation over 1000 Q&A pairs overnight, or
regenerating summaries for your whole corpus. You don't need the answer in
500ms — you need it cheaply. The Batch API trades latency (up to 24h) for ~50%
cost reduction. NEVER use this for live user-facing chat.
"""

import json
from openai import OpenAI

client = OpenAI()

# 1. Build a .jsonl file: one request per line, each with a unique custom_id
#    so you can match outputs back to inputs after the batch completes.
requests = [
    {
        "custom_id": f"eval-question-{i}",
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": question}],
        },
    }
    for i, question in enumerate(["What is RAG?", "Explain vector embeddings", "..."])
]

with open("batch_input.jsonl", "w") as f:
    for r in requests:
        f.write(json.dumps(r) + "\n")

# 2. Upload + submit the batch job
batch_file = client.files.create(file=open("batch_input.jsonl", "rb"), purpose="batch")
batch_job = client.batches.create(
    input_file_id=batch_file.id,
    endpoint="/v1/chat/completions",
    completion_window="24h",
)
print(f"Batch job submitted: {batch_job.id}, status: {batch_job.status}")

# 3. Later (poll or webhook), retrieve and parse results
# status = client.batches.retrieve(batch_job.id)
# if status.status == "completed":
#     result_file = client.files.content(status.output_file_id)
#     for line in result_file.text.splitlines():
#         parsed = json.loads(line)
#         print(parsed["custom_id"], parsed["response"]["body"]["choices"][0]["message"]["content"])
```

---

## 4. STREAMING RESPONSES

### What it is
Sending the LLM's output to the client **token-by-token as it's generated**, instead of waiting
for the full response and sending it all at once.

### Why it matters for RAG
- A RAG answer can take 3–8 seconds to fully generate. Without streaming, the user stares at a
  blank screen for the whole time. With streaming, they see the first words within ~300ms —
  this is the single biggest *perceived* latency win in any LLM product.
- It's also how ChatGPT/Claude.ai actually work under the hood.

### Code: Streaming from the LLM directly

```python
"""
BASIC TOKEN STREAMING
-----------------------
.stream() returns an iterator of chunks instead of one final AIMessage.
Each chunk has a `.content` fragment (sometimes empty, sometimes a few tokens).
"""

from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o-mini", streaming=True)

for chunk in llm.stream("Explain what a vector database is in 3 sentences."):
    print(chunk.content, end="", flush=True)  # prints as tokens arrive, no buffering
print()  # final newline
```

### Code: Streaming a full RAG chain (retrieval is NOT streamed, generation IS)

```python
"""
STREAMING A FULL RAG CHAIN
-----------------------------
Important nuance: retrieval (vector search) is fast and NOT meaningfully
streamable — it either returns docs or it doesn't. What you stream is the
GENERATION step, after retrieval is already done. So the real-world pattern is:

    1. Retrieve (blocking, but fast: ~50-200ms)
    2. Build prompt with retrieved context
    3. Stream the LLM's generation over that prompt
"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

prompt = ChatPromptTemplate.from_template(
    "Answer the question using only this context:\n{context}\n\nQuestion: {question}"
)
llm = ChatOpenAI(model="gpt-4o-mini", streaming=True)
chain = prompt | llm | StrOutputParser()


def stream_rag_answer(query: str, vectorstore):
    # Step 1: retrieval happens fully BEFORE we start streaming anything
    docs = vectorstore.similarity_search(query, k=4)
    context = "\n\n".join(d.page_content for d in docs)

    # Step 2 + 3: .stream() on the chain streams just the generation part
    for token in chain.stream({"context": context, "question": query}):
        yield token  # caller (e.g. FastAPI) forwards each token to the client immediately
```

### Code: Streaming over HTTP with FastAPI (Server-Sent Events)

```python
"""
STREAMING OVER HTTP (SSE)
----------------------------
This is how you actually deliver streaming to a browser/frontend. We use
StreamingResponse with a generator — FastAPI sends each yielded chunk to the
client as soon as it's produced, instead of buffering the whole response.
"""

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import json

app = FastAPI()


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    async def event_generator():
        # async equivalent: chain.astream(...) instead of chain.stream(...)
        docs = await vectorstore.asimilarity_search(req.query, k=4)
        context = "\n\n".join(d.page_content for d in docs)

        async for token in chain.astream({"context": context, "question": req.query}):
            # SSE format: each event is "data: <payload>\n\n"
            payload = json.dumps({"token": token})
            yield f"data: {payload}\n\n"

        yield "data: [DONE]\n\n"  # sentinel so the frontend knows the stream ended

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# Frontend (JS) consumes this with EventSource or a fetch() + ReadableStream reader.
```

---

## 5. OBSERVABILITY (LangSmith, LangFuse, etc.)

### What it is
Tracing, logging, and metrics for every step of a RAG pipeline (retrieval, prompt construction,
LLM call, re-ranking) so you can debug *why* an answer was wrong, measure latency/cost per step,
and catch regressions before users do.

### Why it matters
A RAG pipeline is a black box otherwise: a bad answer could be from bad retrieval, a bad prompt,
a bad chunk, or a hallucinating LLM — and without tracing you're guessing. In production, teams
treat this the same way they treat APM (Application Performance Monitoring) for normal software.

### Code: LangSmith (native LangChain integration — zero code changes for basic tracing)

```python
"""
LANGSMITH — automatic tracing
--------------------------------
LangSmith is built by the LangChain team and integrates by just setting
environment variables. Every chain/retriever/LLM call gets automatically traced
with inputs, outputs, latency, and token usage — no manual instrumentation needed.
"""

import os

os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_API_KEY"] = "ls__..."  # from smith.langchain.com
os.environ["LANGCHAIN_PROJECT"] = "production-rag-bot"  # groups traces in the UI

# That's it. Now ANY LangChain call below is automatically traced:
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o-mini")
llm.invoke("This call now shows up in the LangSmith dashboard with full trace detail.")
```

```python
"""
LANGSMITH — manual run tracking + feedback
----------------------------------------------
For things outside the auto-traced chain (e.g. your custom semantic cache logic,
or user thumbs-up/down feedback), you log manually using the @traceable decorator
and the feedback API.
"""

from langsmith import traceable, Client

client = Client()


@traceable(name="semantic_cache_lookup")  # shows as its own named step in traces
def cached_lookup(query: str):
    result = cache.get(query)
    return result  # automatically logged: input=query, output=result, latency


@traceable(name="full_rag_pipeline", run_type="chain")
def rag_pipeline(query: str):
    docs = retriever.invoke(query)  # nested trace: shows as a child span
    answer = llm.invoke(build_prompt(query, docs))  # another child span
    return answer


# Logging user feedback (thumbs up/down) back onto a specific trace — this is how
# teams build a feedback loop to find which RAG answers users didn't like.
def log_feedback(run_id: str, score: int, comment: str = ""):
    client.create_feedback(
        run_id=run_id, key="user_rating", score=score, comment=comment
    )
```

### Code: LangFuse (open-source alternative — self-hostable)

```python
"""
LANGFUSE — open-source observability (self-hostable, OTel-compatible)
--------------------------------------------------------------------------
Teams choose LangFuse over LangSmith when they need self-hosting (data residency
requirements) or want open-source. The decorator pattern is very similar.
"""

from langfuse.decorators import observe, langfuse_context


@observe(name="retrieval_step")
def retrieve(query: str, vectorstore):
    docs = vectorstore.similarity_search(query, k=4)
    # Attach custom metadata visible in the LangFuse dashboard — crucial for
    # debugging WHY a particular answer used the docs it used.
    langfuse_context.update_current_observation(
        metadata={
            "num_docs_retrieved": len(docs),
            "doc_ids": [d.metadata.get("id") for d in docs],
        }
    )
    return docs


@observe(name="generation_step")
def generate(query: str, docs, llm):
    context = "\n\n".join(d.page_content for d in docs)
    response = llm.invoke(f"Context: {context}\n\nQuestion: {query}")
    return response.content


@observe(name="rag_pipeline")  # parent span — retrieve + generate become its children
def full_pipeline(query: str, vectorstore, llm):
    docs = retrieve(query, vectorstore)
    answer = generate(query, docs, llm)
    return answer


# LangFuse also natively ingests RAGAS scores, so your retrieval-quality eval
# (faithfulness, context precision, etc. — which you already learned) shows up
# alongside latency/cost in the SAME dashboard, per-trace.
```

### Code: What good observability actually answers (the metrics that matter)

```python
"""
THE METRICS PRODUCTION TEAMS ACTUALLY WATCH
-----------------------------------------------
Tracing tools give you raw data; you decide what to alert on. These are the
ones real RAG teams track:
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class RAGTraceMetrics:
    query: str
    retrieval_latency_ms: float  # is retrieval the bottleneck or generation?
    generation_latency_ms: float
    num_docs_retrieved: int
    docs_used_in_answer: int  # were retrieved docs actually relevant/used?
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float
    cache_hit: bool  # cache hit rate is a key cost/latency KPI
    model_used: str  # which model handled this (if you route by complexity)
    user_feedback: int | None = None  # thumbs up/down, joined later


def compute_cost(prompt_tokens: int, completion_tokens: int, model: str) -> float:
    # Pricing per 1M tokens (illustrative — check current pricing pages, these change)
    PRICES = {
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "gpt-4o": {"input": 2.50, "output": 10.00},
    }
    p = PRICES.get(model, PRICES["gpt-4o-mini"])
    return (prompt_tokens / 1_000_000) * p["input"] + (
        completion_tokens / 1_000_000
    ) * p["output"]


# In a dashboard (Grafana, LangSmith, LangFuse), you'd alert on things like:
#   - p95 generation_latency_ms suddenly doubling -> model provider degradation
#   - cache_hit rate dropping -> semantic cache threshold or TTL misconfigured
#   - docs_used_in_answer consistently 0 -> retrieval is broken even though it "runs"
#   - estimated_cost_usd trending up faster than traffic -> someone shipped a prompt bloat
```

---

## 6. COST OPTIMIZATION

### Techniques real teams use, in order of typical impact

1. **Semantic + exact caching** (Section 1) — often the single biggest cost lever; FAQ-heavy
   traffic can see 30–60% of queries served from cache.
2. **Model routing** — use a cheap model (gpt-4o-mini, Haiku) for easy/short queries and an
   expensive model only when needed (complex reasoning, long context).
3. **Context/prompt compression** — don't stuff 20 retrieved chunks into the prompt if 4 are
   enough; every extra token in the prompt is billed input tokens, every call, forever.
4. **Batch API for offline work** (Section 3) — ~50% cheaper for anything that isn't live chat.
5. **Smaller/quantized embedding models** where retrieval quality allows (e.g. `text-embedding-3-small`
   instead of `-large` if your eval shows no meaningful quality drop).
6. **Truncate/trim chat history** sent to the LLM in conversational RAG — don't resend the entire
   conversation every turn once it gets long; summarize older turns instead.

### Code: Model routing by query complexity

```python
"""
MODEL ROUTING (cost-aware)
------------------------------
Not every query needs your best (most expensive) model. A simple classifier —
even a cheap LLM call itself — decides which model handles the real request.
The cost of the router call is tiny compared to what you save by not sending
every simple FAQ to a frontier model.
"""

from langchain_openai import ChatOpenAI

router_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)  # cheap classifier
cheap_llm = ChatOpenAI(model="gpt-4o-mini")
expensive_llm = ChatOpenAI(model="gpt-4o")


def classify_complexity(query: str) -> str:
    result = router_llm.invoke(
        f"""Classify this question's complexity as exactly one word, "simple" or "complex".
        "simple" = factual lookup, short answer, FAQ-style.
        "complex" = multi-step reasoning, comparison, synthesis across many sources, ambiguous.
        Question: {query}
        Answer with one word only."""
    )
    return result.content.strip().lower()


def route_and_answer(query: str, context: str):
    complexity = classify_complexity(query)
    model = expensive_llm if complexity == "complex" else cheap_llm
    print(f"Routed to: {model.model_name}")
    return model.invoke(f"Context: {context}\n\nQuestion: {query}")
```

### Code: Prompt/context compression before sending to the LLM

```python
"""
CONTEXT COMPRESSION
----------------------
Re-ranking (which you already learned) gives you the BEST k docs, but "best k"
can still be wasteful if k is too generous or chunks contain boilerplate. Two
real techniques:

1. Reduce k after re-ranking — trust the re-ranker's ordering, only keep top 2-3.
2. LLM-based or extractive compression — strip sentences from each chunk that
   aren't relevant to the specific query, before they ever hit the final prompt.
"""

from langchain.retrievers import ContextualCompressionRetriever
from langchain.retrievers.document_compressors import LLMChainExtractor
from langchain_openai import ChatOpenAI

compressor_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
compressor = LLMChainExtractor.from_llm(compressor_llm)
# This wraps your existing retriever: it gets docs as normal, then asks a cheap
# LLM to extract ONLY the sentences relevant to the query from each doc before
# passing them downstream — cutting prompt tokens fed into your main (expensive) LLM.
compression_retriever = ContextualCompressionRetriever(
    base_compressor=compressor,
    base_retriever=base_retriever,  # your existing similarity/MMR/hybrid retriever
)

compressed_docs = compression_retriever.invoke(
    "What's the cancellation policy for annual plans?"
)
# compressed_docs now contain only the relevant sentences, not full chunks —
# fewer tokens sent to your main generation model, every single request.
```

### Code: Token-aware cost tracking per request (tie it back to Section 5)

```python
"""
PER-REQUEST COST TRACKING
-----------------------------
Wrap every LLM call so cost is computed and logged in real time — this is what
feeds the dashboards in Section 5 and is the only way to catch a "someone shipped
a 10x prompt bloat" regression before the monthly bill does.
"""

from langchain_core.callbacks import BaseCallbackHandler


class CostTrackingCallback(BaseCallbackHandler):
    def __init__(self):
        self.total_cost_usd = 0.0

    def on_llm_end(self, response, **kwargs):
        usage = response.llm_output.get("token_usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        cost = compute_cost(
            prompt_tokens, completion_tokens, model="gpt-4o-mini"
        )  # from Section 5
        self.total_cost_usd += cost
        print(
            f"[cost] this call: ${cost:.6f} | running total: ${self.total_cost_usd:.4f}"
        )


tracker = CostTrackingCallback()
llm = ChatOpenAI(model="gpt-4o-mini", callbacks=[tracker])
llm.invoke("Summarize the benefits of RAG over fine-tuning.")
# tracker.total_cost_usd now reflects real, measured spend for this session/request.
```

---

## How these pieces fit together in one real request

```
User query arrives at FastAPI /chat/stream endpoint (async)
        │
        ▼
Check semantic cache (Section 1) ──── HIT ──► stream cached answer back, done
        │ MISS
        ▼
Async retrieval from vector DB (Section 2) ── traced by LangSmith/LangFuse (Section 5)
        │
        ▼
Re-rank + compress context (cost optimization, Section 6)
        │
        ▼
Route to cheap or expensive model based on complexity (Section 6)
        │
        ▼
Stream generation token-by-token over SSE (Section 4)
        │
        ▼
Write result to semantic cache for next time (Section 1)
        │
        ▼
Log full trace: latency per step, tokens, cost, cache hit/miss (Section 5)
```

This is genuinely the production shape — caching and observability wrap everything else, async
and batching are *how* each step executes efficiently, and streaming is how the result reaches
the user without them staring at a spinner.
