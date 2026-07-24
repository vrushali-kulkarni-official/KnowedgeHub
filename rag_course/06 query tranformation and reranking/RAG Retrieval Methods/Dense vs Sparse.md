When people say **"RAG retrieval"**, they are usually talking about **how chunks are searched and ranked** before being sent to the LLM.

There are several retrieval methods, each with different strengths.

# 1. Keyword Search (Lexical Search)

## BM25

The most famous keyword search algorithm.

Example:

Document:

> "SQLAlchemy is a Python ORM."

Query:

> "Python ORM"

BM25 finds documents containing the exact words **Python** and **ORM**.

### Advantages

* Fast
* Explainable
* Great for exact terms
* Good for product names, error codes, IDs, API names

### Disadvantages

* Doesn't understand meaning
* Misses synonyms

Example:

Query:

> "database mapper"

BM25 may not find:

> "SQLAlchemy is a Python ORM"

because none of the words match.

Libraries:

* Elasticsearch
* OpenSearch
* Whoosh
* Lucene

---

# 2. Dense Vector Search

Uses embeddings.

Example:

Query:

> "database mapper"

Embedding model understands:

database mapper ≈ ORM

So it can retrieve:

> "SQLAlchemy is a Python ORM"

even though words don't match.

### Advantages

* Semantic understanding
* Handles synonyms
* Best for natural language

### Disadvantages

* More expensive
* Can miss exact keywords

Vector databases:

* FAISS
* pgvector
* Pinecone
* Weaviate
* Qdrant
* Milvus

---

# 3. Sparse Vector Search

Modern version of keyword search.

Examples:

* SPLADE
* uniCOIL

Instead of storing words directly, it creates sparse vectors.

Advantages:

* Keeps keyword matching
* Better semantic understanding than BM25

Often used in enterprise search.

---

# 4. Hybrid Search

Combines:

```
BM25 + Vector Search
```

This is what most production RAG systems use.

Example:

Query:

> "How do I configure SQLAlchemy Session?"

BM25:

* finds exact "SQLAlchemy Session"

Vector:

* finds semantically related chunks

Final ranking combines both.

### Advantages

* Best overall accuracy
* Handles exact terms + semantic meaning

Used by:

* OpenAI Assistants
* Azure AI Search
* Elastic Search AI
* Most enterprise RAG systems

---

# 5. Metadata Filtering

Search only within filtered documents.

Example:

```python
{"department": "HR", "year": 2025}
```

Query:

> Leave policy

Search only HR documents from 2025.

Not a retrieval algorithm itself, but usually combined with vector search.

---

# 6. Parent-Child Retrieval

Store small chunks.

Retrieve parent document later.

Example:

```
PDF
 ├─ Chunk 1
 ├─ Chunk 2
 ├─ Chunk 3
```

Search retrieves Chunk 2.

System returns:

```
Entire Section containing Chunk 2
```

Benefits:

* Better context
* Less hallucination

LangChain:

* ParentDocumentRetriever

---

# 7. Multi-Query Retrieval

LLM generates multiple search queries.

Example:

User asks:

> How do SQLAlchemy sessions work?

Generated queries:

```
SQLAlchemy Session
SQLAlchemy transaction
SQLAlchemy ORM session
Database session lifecycle
```

Search all of them.

Merge results.

Benefits:

* Better recall

---

# 8. Query Expansion

Similar to Multi-Query but simpler.

Example:

```
car
automobile
vehicle
```

Search all synonyms.

---

# 9. Self-Query Retrieval

LLM extracts filters automatically.

User:

> HR policies from 2024 about remote work

LLM converts:

```python
query = "remote work"

filters = {"department": "HR", "year": 2024}
```

Then vector search uses filters.

Very useful for enterprise RAG.

---

# 10. Reranking

After retrieval, a second model re-sorts results.

Pipeline:

```
Query
 ↓
Vector Search (Top 50)
 ↓
Reranker
 ↓
Top 5
 ↓
LLM
```

Examples:

* Cohere Rerank
* BGE Reranker
* Jina Reranker
* Cross Encoder

This often improves RAG more than changing embeddings.

---

# 11. Graph RAG

Documents stored as relationships.

Example:

```
LangChain
   ├── uses → OpenAI
   ├── supports → FAISS
   └── supports → Qdrant
```

Useful for:

* Company knowledge bases
* Research papers
* Legal documents

Tools:

* Neo4j
* Memgraph

---

# 12. Agentic Retrieval

Agent decides:

1. What to search
2. Which tool to use
3. Whether another search is needed

Flow:

```
Question
 ↓
Agent
 ↓
Search
 ↓
Evaluate
 ↓
Search Again
 ↓
Answer
```

Used in advanced AI assistants.

---

# Retrieval Evolution

```text
BM25
  ↓
Vector Search
  ↓
Hybrid Search
  ↓
Hybrid + Reranker
  ↓
Agentic RAG
  ↓
Graph + Agentic RAG
```

For most real-world projects, **Hybrid Search + Metadata Filters + Reranker** gives the best accuracy/cost tradeoff.

---

# What is RAGAS?

RAGAS = **Retrieval Augmented Generation Assessment**

It is a framework used to **evaluate a RAG pipeline automatically**.

Official project: [RAGAS](https://docs.ragas.io/?utm_source=chatgpt.com)

Instead of manually reading answers, RAGAS scores:

1. Retrieval quality
2. Answer quality
3. Grounding quality

---

## Common RAGAS Metrics

### Context Precision

Were the retrieved chunks actually relevant?

```
Retrieved: 10 chunks
Relevant: 8 chunks

Precision = 0.8
```

---

### Context Recall

Did retrieval find all important information?

```
Needed chunks = 10
Retrieved relevant = 7

Recall = 0.7
```

---

### Faithfulness

Did the answer stay grounded in the retrieved context?

High score:

> Uses only retrieved facts.

Low score:

> Hallucinates information.

---

### Answer Relevancy

Did the answer actually answer the user's question?

---

### Context Relevancy

Measures how useful retrieved chunks were for the query.

---

# Typical Production RAG Stack (2026)

For a company knowledge-base chatbot:

```text
Docling
    ↓
Semantic Chunking
    ↓
BGE / OpenAI Embeddings
    ↓
pgvector
    ↓
Hybrid Search (BM25 + Vector)
    ↓
Reranker (BGE/Jina/Cohere)
    ↓
LLM
    ↓
RAGAS Evaluation
```

For an OpenClaw-style AI assistant:

```text
Semantic Chunking
    ↓
Hybrid Search
    ↓
Multi-Query Retrieval
    ↓
Reranker
    ↓
Agentic Retrieval
    ↓
LLM
    ↓
RAGAS
```

If you're currently learning RAG, focus first on mastering:

1. BM25
2. Dense Vector Search
3. Hybrid Search
4. Metadata Filtering
5. Reranking
6. RAGAS evaluation

Those six concepts cover about 80–90% of what you'll encounter in production RAG systems.
