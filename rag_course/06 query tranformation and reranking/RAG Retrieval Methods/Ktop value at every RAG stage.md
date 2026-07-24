# Question:
for RAG retrieval system i want to do a dense + sparse search followed by RRF then MMR and then reranking


For a real-world large production system, what should be the value of K or Ktop that is the number of chunks that are retrieved or finalized at each step


# Answer: 
This is one of the most important tuning questions in production RAG, and unfortunately there is **no universal value**. Companies like Google, Microsoft, OpenAI, Anthropic, Cohere, and NVIDIA all use slightly different values depending on latency, corpus size, and LLM context window.

The pipeline you're proposing is:

```
User Query
      │
      ▼
Dense Search (top Kd)
      │
Sparse Search (top Ks)
      │
      ▼
RRF Fusion
      │
Top Kr
      │
      ▼
MMR Diversification
      │
Top Km
      │
      ▼
Cross Encoder Re-ranking
      │
Top Kfinal
      │
      ▼
LLM
```

Let's discuss what each stage should do.

---

# Stage 1 — Dense Retrieval

Suppose you have

```
100 million chunks
```

You obviously cannot rerank millions.

Instead the vector DB returns only the nearest neighbors.

Typical values:

| Corpus Size  | Dense Top-K |
| ------------ | ----------: |
| <100K chunks |       20-50 |
| 1M chunks    |      50-100 |
| 10M+ chunks  |     100-200 |

For enterprise RAG

```
Dense Top K = 100
```

is probably the most common.

Reason:

You want high recall.

---

# Stage 2 — Sparse Retrieval (BM25)

Do exactly the same.

```
BM25 Top K = 100
```

Some teams even use

```
150
```

because BM25 is inexpensive.

Typical:

```
Dense = 100
Sparse = 100
```

---

# Stage 3 — RRF Fusion

Now combine both lists.

Suppose

Dense

```
100 docs
```

Sparse

```
100 docs
```

After removing duplicates maybe

```
150 unique chunks
```

Sometimes

```
170
```

Sometimes

```
120
```

Now RRF scores them.

Do **not** keep all 150.

Usually keep around

```
Top 60–100
```

Typical:

```
RRF output = 80
```

---

# Why reduce after RRF?

Because MMR compares documents with one another.

MMR complexity is roughly

```
O(N²)
```

More candidates mean slower execution.

---

# Stage 4 — MMR

MMR removes redundancy.

Example

Suppose RRF returns

```
80 chunks
```

Many could be almost identical:

```
Chunk 1
Python supports classes.

Chunk 2
Python supports OOP.

Chunk 3
Python has inheritance.

Chunk 4
Python classes support inheritance.
```

Instead of passing all similar chunks, MMR keeps only diverse ones.

Typical output:

```
30–50 chunks
```

Very common:

```
MMR Top K = 40
```

---

# Stage 5 — Cross Encoder Reranking

This is the expensive step.

Every chunk is scored against the query.

If you rerank

```
100 chunks
```

you perform

```
100 transformer inferences
```

Expensive.

Most production systems rerank between

```
20–50 chunks
```

A common setup:

```
MMR output = 40

↓

Cross Encoder reranks all 40

↓

Keep Top 10
```

---

# Stage 6 — Final Context

The LLM doesn't need 40 chunks.

Usually

```
Top 5–10
```

is enough.

Examples:

GPT-4

```
6 chunks
```

Claude

```
8 chunks
```

Gemini

```
10 chunks
```

depending on chunk size and context window.

---

# A Production Example

Imagine

```
50 million chunks
```

Pipeline:

```
Dense Search
Top 100

Sparse Search
Top 100

↓

RRF

↓

80

↓

MMR

↓

40

↓

Cross Encoder

↓

10

↓

LLM
```

This is an extremely common architecture.

---

# Why not rerank 100?

Cross encoders are expensive.

Approximate comparison:

Vector search

```
100 docs

≈ 20 ms
```

BM25

```
100 docs

≈ 10 ms
```

Cross encoder

```
100 docs

≈ 300–800 ms
```

That's why we narrow the candidate set before reranking.

---

# Typical Values Used in Production

| Stage               | Typical Top-K |
| ------------------- | ------------: |
| Dense Search        |        50–150 |
| Sparse Search       |        50–150 |
| RRF Output          |        60–100 |
| MMR Output          |         20–50 |
| Cross-Encoder Final |          5–10 |
| Sent to LLM         |          4–10 |

---

# Recommended Starting Configuration

If you're building a production-grade RAG system, this is a strong baseline:

| Stage                       |       K |
| --------------------------- | ------: |
| Dense Retrieval             | **100** |
| Sparse Retrieval            | **100** |
| RRF Fusion Output           |  **80** |
| MMR Output                  |  **40** |
| Cross-Encoder Rerank Output |  **10** |
| Final Context to LLM        | **6–8** |

This configuration balances **high recall**, **diversity**, **latency**, and **LLM context efficiency** for many enterprise workloads.

### One more recommendation: tune by *recall*, not by fixed K

Rather than treating these values as constants, tune them using an evaluation set.

For example:

| Metric                     | Goal                                                             |
| -------------------------- | ---------------------------------------------------------------- |
| Recall@100 (Dense)         | >95% of relevant chunks appear in the candidate set              |
| Recall after RRF           | Should be at least as good as the better individual retriever    |
| Recall after MMR           | Lose very little recall (e.g., <2–3%) while increasing diversity |
| NDCG@10 after reranking    | Maximize ranking quality                                         |
| End-to-end answer accuracy | Primary optimization target                                      |

A common workflow is:

1. Start with a generous retrieval depth (e.g., Dense=100, Sparse=100).
2. Measure Recall@K on a labeled dataset.
3. Reduce the candidate sizes until latency improves without significantly hurting answer quality.
4. Tune MMR's diversity parameter (`lambda`) and the final number of chunks based on your LLM's context window and chunk size.

This data-driven approach is how large production RAG systems typically arrive at their final `K` values, rather than relying on fixed numbers alone.
   