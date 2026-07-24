In real-world production RAG, **all of these techniques exist**, but they are **not used equally**.

The biggest mistake beginners make is assuming that every query goes through HyDE, Multi-Query, Step-Back, etc. In production, every extra LLM call increases:

* Latency
* Cost
* Complexity
* Failure points

So production systems usually use a **query transformation pipeline**, where different techniques are triggered only when needed.

---

# Production Usage Ranking

If I had to rank them by actual production usage:

| Technique       | Production Usage  |
| --------------- | ----------------- |
| Query Rewriting | ⭐⭐⭐⭐⭐ Very Common |
| Multi-Query     | ⭐⭐⭐⭐ Common       |
| Decomposition   | ⭐⭐⭐ Common        |
| Step-Back       | ⭐⭐ Limited        |
| HyDE            | ⭐ Rare            |

---

# 1. Query Rewriting (Most Common)

Almost every serious RAG system does some form of query rewriting.

User queries are messy.

Examples:

User:

> money back for broken item

Document contains:

> damaged product refund policy

Retriever may miss it.

System rewrites:

> refund policy for damaged product

Now retrieval becomes much easier.

---

## Real Example

User:

> My package came smashed. Can I get my money back?

Rewrite:

> refund policy for damaged product

Then retrieve.

---

## Why It's Popular

Benefits:

* Cheap
* Fast
* Improves retrieval significantly
* Single LLM call

This is probably the most widely deployed query transformation technique.

---

# 2. Multi-Query (Very Common)

Instead of one search query, generate several.

User:

> How do I optimize PostgreSQL for vector search?

Generate:

Query 1:

> PostgreSQL vector search optimization

Query 2:

> pgvector performance tuning

Query 3:

> HNSW index optimization in PostgreSQL

Query 4:

> ANN search performance PostgreSQL

Retrieve for all.

Merge results.

---

## Why Companies Use It

One query embedding captures only one semantic direction.

Multiple queries explore multiple directions.

Recall improves dramatically.

---

## Production Usage

Common in:

* Enterprise search
* Documentation search
* Customer support bots
* Internal knowledge bases

Usually limited to:

* 3–5 queries

not

* 20 queries

because cost increases.

---

# 3. Query Decomposition (Common)

Used when query contains multiple sub-questions.

Example:

> Compare IVF and HNSW and explain which one is better for a billion-vector RAG system.

This contains:

Subquery 1:

> What is IVF?

Subquery 2:

> What is HNSW?

Subquery 3:

> IVF vs HNSW

Subquery 4:

> Billion-scale vector search

Retrieve separately.

---

## Where Used

Very common in:

* Research assistants
* Agentic RAG
* Enterprise analytics
* Financial assistants

---

## Example

Microsoft, Google, OpenAI-style assistants often decompose internally before retrieval because a single retrieval pass may miss some aspects.

---

# 4. Step-Back Prompting (Less Common)

Paper idea:

Instead of searching directly:

User:

> Why does HNSW outperform IVF?

Generate a broader question:

> What are the characteristics of graph-based ANN algorithms?

Retrieve.

Then answer.

---

## Problem

Works great academically.

But in production:

* Additional LLM call
* Can become too abstract
* Sometimes retrieves irrelevant information

---

## Where Used

Mostly:

* Research assistants
* Deep reasoning systems
* Agentic workflows

Not commonly used in customer support RAG.

---

# 5. HyDE (Rare in Production)

HyDE = Hypothetical Document Embeddings

---

User:

> What is the warranty policy?

LLM generates:

> The warranty policy allows customers to return defective products within 2 years...

Then embedding is created from that generated document.

Then search happens.

---

## Why It Works

Generated text often resembles actual documents.

Embedding quality improves.

---

## Why It's Rare

Problems:

### Cost

Two embedding operations:

1. Generate hypothetical document
2. Embed it

---

### Latency

Additional LLM call.

---

### Hallucination Risk

Generated document may drift away from reality.

Example:

User:

> Tesla refund policy

HyDE might generate:

> Tesla provides 60-day refunds...

which may not exist.

Retriever may be guided incorrectly.

---

# What Big Production Systems Actually Do

A common production pipeline looks like:

```text
User Query
    │
    ▼
Query Analysis
    │
    ├── Intent Detection
    ├── Entity Extraction
    ├── Keyword Extraction
    ├── Metadata Filters
    │
    ▼
Query Rewriting
    │
    ▼
Multi-Query Generation
    │
    ▼
Hybrid Retrieval
(Dense + BM25)
    │
    ▼
RRF Fusion
    │
    ▼
MMR Reranking
    │
    ▼
LLM Answer
```

---

# What Companies Typically Use

### Customer Support RAG

Most common:

```text
Rewrite
+
Hybrid Search
```

Maybe Multi-Query.

Nothing more.

---

### Enterprise Search

Most common:

```text
Rewrite
+
Multi Query
+
Hybrid Search
+
Reranker
```

---

### Research Assistant

Most common:

```text
Rewrite
+
Decomposition
+
Multi Query
+
Hybrid Search
+
Reranker
```

---

### Agentic RAG

Most common:

```text
Rewrite
+
Decomposition
+
Multi Query
+
Step Back
```

depending on complexity.

---

# If You Are Building a Production-Grade RAG Today

I would learn and implement in this order:

```text
1. Query Rewriting       ← Mandatory
2. Multi Query           ← Very useful
3. Query Decomposition   ← Important
4. RRF Fusion
5. Reranking
6. Step Back
7. HyDE
```

The first three deliver most of the practical gains you'll see in production systems. Step-Back and HyDE are valuable techniques to understand, but they are far less commonly deployed as the default path for every query.
