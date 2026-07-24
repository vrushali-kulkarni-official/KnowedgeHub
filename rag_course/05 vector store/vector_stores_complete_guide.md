# Vector Stores & Vector Databases — Complete Production RAG Guide

> **Learning Path Context:** You've built Basic RAG → Docling Loader → Chunking Strategies →
> Tokenization & Embeddings → **You are here: Vector Stores & Vector DBs**

---

## TABLE OF CONTENTS

1. [What Are Vector Stores / Vector DBs?](#1-what-are-vector-stores--vector-dbs)
2. [Similarity Metrics — Cosine, Euclidean, Dot Product](#2-similarity-metrics)
3. [Indexes — How Search is Made Fast](#3-indexes)
4. [ANN vs kNN](#4-ann-vs-knn)
5. [FAISS — Prototyping](#5-faiss--prototyping)
6. [Chroma — Persistence](#6-chroma--persistence)
7. [Pgvector — Production](#7-pgvector--production)
8. [Other Vector DBs at a Glance](#8-other-vector-dbs-at-a-glance)
9. [Choosing the Right Vector DB](#9-choosing-the-right-vector-db)

---

## 1. What Are Vector Stores / Vector DBs?

### The Core Problem

Traditional databases store and search **exact** or **keyword** data.
If you search for "What causes heart disease?", a SQL `LIKE '%heart disease%'`
query will fail to return "cardiovascular risk factors" — even though it's semantically
the same topic.

Vector stores solve this. They store **numerical representations (embeddings)** of text,
images, or any data, and let you find items by **semantic meaning**, not exact keywords.

```
Your Text Chunk           Embedding Model            Vector (384 dims)
─────────────────         ───────────────            ──────────────────
"The sky is blue"  ──▶   MiniLM-L6-v2      ──▶    [0.12, -0.45, 0.88, ...]
"Clouds are white" ──▶   MiniLM-L6-v2      ──▶    [0.10, -0.42, 0.85, ...]
"Stock market fell"──▶   MiniLM-L6-v2      ──▶    [0.91,  0.33, -0.21, ...]
```

The first two vectors are *close together* in high-dimensional space.
The third is *far away*. Similarity search exploits this geometry.

### Vector Store vs Vector DB

| Feature               | Vector Store (e.g., FAISS) | Vector DB (e.g., Qdrant, Pinecone) |
|-----------------------|----------------------------|------------------------------------|
| Persistence           | Manual (save/load files)   | Built-in, automatic                |
| Metadata Filtering    | Not built-in               | First-class support                |
| CRUD Operations       | Limited                    | Full (insert, update, delete)      |
| Scalability           | Single machine             | Distributed clusters               |
| Access Control        | None                       | Built-in auth/API keys             |
| Use Case              | Prototyping, research      | Production systems                 |

### Where Vector Stores Fit in RAG

```
                         ┌─────────────────────────────────────────┐
INDEXING PIPELINE        │                                         │
(runs once, offline)     │  Documents                              │
                         │      │                                  │
                         │      ▼                                  │
                         │  Chunker  (you already built this!)     │
                         │      │                                  │
                         │      ▼                                  │
                         │  Embedding Model  (MiniLM, etc.)        │
                         │      │                                  │
                         │      ▼                                  │
                         │  ┌─────────────┐                        │
                         │  │ VECTOR STORE│  ◀── You are here      │
                         │  └─────────────┘                        │
                         └─────────────────────────────────────────┘

                         ┌─────────────────────────────────────────┐
RETRIEVAL PIPELINE       │                                         │
(runs on every query)    │  User Query                             │
                         │      │                                  │
                         │      ▼                                  │
                         │  Embedding Model  (same model!)         │
                         │      │                                  │
                         │      ▼                                  │
                         │  Similarity Search in Vector Store      │
                         │      │                                  │
                         │      ▼                                  │
                         │  Top-k Relevant Chunks                  │
                         │      │                                  │
                         │      ▼                                  │
                         │  LLM + Prompt → Answer                  │
                         └─────────────────────────────────────────┘
```

---

## 2. Similarity Metrics

When you search a vector store, it computes a **distance or similarity score**
between your query vector and every stored vector, then returns the closest ones.

### 2.1 Cosine Similarity

Measures the **angle** between two vectors. Ignores magnitude (length).
Best for text embeddings because word/sentence frequency differences shouldn't
matter — only direction (meaning) matters.

```
Formula:  cos(θ) = (A · B) / (||A|| × ||B||)

Range:    -1    →  +1
           ↑        ↑
        opposite  identical
```

```python
import numpy as np


def cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    """
    Compute cosine similarity between two vectors.

    Why cosine for text?
    - "The dog runs fast" and "A dog runs very fast" differ in length
      but mean the same thing.
    - Cosine ignores that "very fast" adds more tokens (magnitude)
      and focuses on the directional similarity (meaning).
    """
    # Dot product of the two vectors
    dot_product = np.dot(vec_a, vec_b)

    # L2 norm (magnitude/length) of each vector
    norm_a = np.linalg.norm(vec_a)  # sqrt(sum of squares)
    norm_b = np.linalg.norm(vec_b)

    # Avoid division by zero for zero vectors
    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


# ── Example ───────────────────────────────────────────────────────────────────
# Simulate what an embedding model would produce for these sentences
# (In reality, these would be 384-dim vectors from MiniLM)
sky_vec = np.array([0.9, 0.1, 0.05, 0.02])  # "The sky is blue"
weather_vec = np.array([0.85, 0.15, 0.08, 0.03])  # "It's a clear blue day"  ← similar
finance_vec = np.array([0.02, 0.95, 0.8, 0.6])  # "Stock market crashed"   ← different

print(f"Sky vs Weather : {cosine_similarity(sky_vec, weather_vec):.4f}")  # High ~0.99
print(f"Sky vs Finance : {cosine_similarity(sky_vec, finance_vec):.4f}")  # Low  ~0.15

# IMPORTANT NOTE:
# Most vector DBs store "cosine distance" = 1 - cosine_similarity
# So distance=0 means identical, distance=2 means opposite
# Always check the DB docs: higher score = better OR lower score = better?
```

### 2.2 Euclidean Distance (L2)

Measures the **straight-line distance** between two points in space.
Good when the magnitude of vectors matters (e.g., image embeddings).

```python
def euclidean_distance(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    """
    Compute L2 (Euclidean) distance between two vectors.

    Formula: sqrt( sum( (a_i - b_i)^2 ) )

    Range: 0 → infinity
           ↑              ↑
        identical       very different

    Lower score = more similar (opposite of cosine similarity!)

    When to use:
    - Image embeddings (CLIP, ResNet) where magnitude is meaningful
    - When vectors are already normalized (then L2 ≈ cosine distance)
    - FAISS default for many index types
    """
    # NumPy's built-in norm of the difference vector
    return float(np.linalg.norm(vec_a - vec_b))


# ── Example ───────────────────────────────────────────────────────────────────
print(f"Sky vs Weather (L2) : {euclidean_distance(sky_vec, weather_vec):.4f}")  # Small
print(f"Sky vs Finance (L2) : {euclidean_distance(sky_vec, finance_vec):.4f}")  # Large


# NORMALIZATION TIP:
# If you L2-normalize your vectors first (unit length = 1),
# then: L2_distance^2 = 2 - 2*cosine_similarity
# So normalized L2 ≈ cosine. Many systems normalize by default.
def normalize(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec
```

### 2.3 Dot Product (Inner Product)

Measures both **angle AND magnitude**. Fastest to compute. Used in production
when you want frequently-occurring or highly confident items to rank higher.

```python
def dot_product_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    """
    Compute dot product (inner product) similarity.

    Formula: sum(a_i * b_i)  ← just element-wise multiply and sum

    Range: -infinity → +infinity
    Higher = more similar

    Key insight:
    - dot_product = cosine_similarity * ||a|| * ||b||
    - If vectors are unit-normalized: dot_product == cosine_similarity
    - If NOT normalized: longer vectors score higher regardless of angle

    When to use:
    - Your embeddings are already normalized (then it's free cosine)
    - You WANT magnitude to matter (e.g., Matryoshka embeddings)
    - Pure speed — no sqrt() needed
    - Pinecone default, OpenAI Ada embeddings are normalized (dot = cosine)
    """
    return float(np.dot(vec_a, vec_b))


# ── Summary Comparison ────────────────────────────────────────────────────────
print("\n=== Metric Comparison ===")
print(f"{'Metric':<20} {'Sky vs Weather':>15} {'Sky vs Finance':>15}")
print("-" * 52)
print(
    f"{'Cosine Sim':<20} {cosine_similarity(sky_vec, weather_vec):>15.4f} "
    f"{cosine_similarity(sky_vec, finance_vec):>15.4f}"
)
print(
    f"{'Euclidean Dist':<20} {euclidean_distance(sky_vec, weather_vec):>15.4f} "
    f"{euclidean_distance(sky_vec, finance_vec):>15.4f}"
)
print(
    f"{'Dot Product':<20} {dot_product_similarity(sky_vec, weather_vec):>15.4f} "
    f"{dot_product_similarity(sky_vec, finance_vec):>15.4f}"
)
```

### 2.4 Metric Selection Cheat Sheet

```
Your Embeddings                         Recommended Metric
───────────────────────────────────────────────────────────
Sentence transformers (MiniLM, etc.)  → Cosine
OpenAI text-embedding-3-*             → Cosine or Dot Product (pre-normalized)
Image embeddings (CLIP, ResNet)       → Euclidean (L2)
Already L2-normalized                 → Dot Product (fastest, equals cosine)
Sparse vectors (BM25 hybrid)          → Dot Product
```

---

## 3. Indexes

A **vector index** is a data structure that makes similarity search fast.
Without an index, you'd compare your query against every single vector —
that's fine for 1,000 docs, catastrophic for 10 million.

### 3.1 Flat Index (Brute Force / Exact Search)

```
Query Vector ──▶ Compare with ALL vectors ──▶ Return top-k

Pros: 100% accurate (exact nearest neighbours)
Cons: O(n) per query — too slow for large datasets
Use:  < 100k vectors, highest accuracy needed, testing
```

### 3.2 IVF — Inverted File Index

```
Build time: Cluster vectors into Voronoi cells (like K-means)
Query time: Only search vectors in the nearest nprobe cells

     ┌───────────────────────────────────────────────────┐
     │  ●                                                │
     │      ●  ●  Cell 1     │   Cell 2  ●  ●           │
     │    ●  [centroid1]     │        [centroid2]  ●    │
     │                       │                          │
     │  ─────────────────────┼──────────────────────    │
     │                       │                          │
     │    ●  ●  Cell 3       │  Cell 4   ●              │
     │       [centroid3]  ●  │        [centroid4] ●  ●  │
     └───────────────────────────────────────────────────┘
     
Query → find nearest centroids → search only those cells

nlist = number of cells (higher = more precise partitioning)
nprobe = cells to search at query time (higher = more accurate, slower)
```

### 3.3 HNSW — Hierarchical Navigable Small World (★ Most Popular)

```
A layered graph structure. Like a highway system:
- Top layer: long-distance connections (skip list / highway)
- Bottom layer: local connections (neighbourhood streets)

Layer 2:  A ─────────────────── E
Layer 1:  A ──── B ──── C ────  E
Layer 0:  A ─ B ─ C ─ D ─ E ─ F

Query starts at top layer (fast), drills down to exact neighbourhood

Parameters:
  M       = number of connections per node (higher = better recall, more RAM)
  ef_construction = search width during build (higher = better index, slower build)
  ef      = search width during query (tune recall vs speed at query time)

Pros: Excellent recall/speed tradeoff, dynamic insert support
Cons: High memory usage (~50 bytes * M per vector)
Use:  Production systems — Chroma, Qdrant, Weaviate all use HNSW by default
```

### 3.4 PQ — Product Quantization

```
Compresses vectors to save RAM. Splits each vector into subvectors,
then replaces each subvector with a codebook ID.

384-dim float32 vector = 1,536 bytes
384-dim PQ vector      = ~48 bytes   (32x compression!)

Pros: Massive memory savings, enables billion-scale on commodity hardware
Cons: Lossy compression → slight accuracy drop
Use:  Combined with IVF as "IVF_PQ" for large-scale datasets
```

### 3.5 Index Type Cheat Sheet

```
Index Type     Accuracy  Speed    Memory    Best For
─────────────────────────────────────────────────────────────
Flat           ★★★★★     ★☆☆☆☆   ★★★☆☆    < 100k vectors, testing
IVF_Flat       ★★★★☆     ★★★☆☆   ★★★☆☆    100k – 1M vectors
HNSW           ★★★★☆     ★★★★★   ★★☆☆☆    Most production use cases
IVF_PQ         ★★★☆☆     ★★★★☆   ★★★★★    > 10M vectors, RAM constrained
HNSW + PQ      ★★★☆☆     ★★★★★   ★★★★★    Billion-scale
```

---

## 4. ANN vs kNN

```python
"""
kNN — k Nearest Neighbours (Exact Search)
──────────────────────────────────────────
- Compare query against EVERY vector in the database
- Guaranteed to return the TRUE top-k most similar vectors
- Time complexity: O(n × d) where n=vectors, d=dimensions
- Perfectly accurate, but painfully slow at scale

ANN — Approximate Nearest Neighbours (Indexed Search)
──────────────────────────────────────────────────────
- Use an index (HNSW, IVF, etc.) to SKIP most comparisons
- Returns vectors that are VERY LIKELY the top-k (but not guaranteed)
- Time complexity: O(log n × d) — orders of magnitude faster
- Slightly less accurate, but 99%+ recall is achievable in practice

The RAG Reality:
- For RAG, ANN is almost always the right choice
- Missing the #1 most similar chunk and returning #2 instead is fine
- What matters is: are the returned chunks relevant? Yes, with 99% recall.
- Facebook's HNSW benchmarks: 1M vectors, 1ms query, 99.9% recall

Recall = (# true neighbours returned) / k
"""

# Concrete numbers from ANN benchmarks (ann-benchmarks.com)
benchmarks = {
    "Dataset": "GloVe-100 (1.2M vectors, 100 dims)",
    "Methods": {
        "Brute Force (kNN)": {
            "Recall@10": 1.0,
            "Queries/sec": 14,  # Very slow
        },
        "HNSW (ANN)": {
            "Recall@10": 0.999,  # 99.9% — virtually identical
            "Queries/sec": 15_000,  # 1000x faster
        },
        "IVF_PQ (ANN)": {
            "Recall@10": 0.95,  # 95% recall
            "Queries/sec": 45_000,  # 3000x faster, uses 30x less RAM
        },
    },
}

# CONCLUSION for RAG:
# Use ANN (HNSW) — you get 1000x speed with negligible accuracy loss
```

---

## 5. FAISS — Prototyping

FAISS (Facebook AI Similarity Search) is the grandfather of vector search.
It's a library, not a database — no server, no persistence, runs in Python process memory.

**When to use:** Research, prototyping, experimenting with chunking strategies,
offline batch processing, when you control the entire pipeline.

### 5.1 Installation

```bash
# CPU version (sufficient for most RAG prototyping)
pip install faiss-cpu langchain-community sentence-transformers

# GPU version (for large-scale, speeds up index build 10-100x)
# pip install faiss-gpu
```

### 5.2 Raw FAISS — No LangChain (Understanding the Internals)

```python
"""
Start here to understand what LangChain is doing under the hood.
Every LangChain vector store is a thin wrapper around primitives like these.
"""

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

# ── 1. Setup ──────────────────────────────────────────────────────────────────

# Load embedding model — same one you used in your RAG chain
# This is the model that converts text → 384-dim vectors
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

EMBEDDING_DIM = 384  # MiniLM produces 384-dimensional vectors
# This MUST match your index dimension

# ── 2. Create Documents ───────────────────────────────────────────────────────

# Simulating chunks you'd get from your chunking pipeline
documents = [
    "Python is a high-level programming language known for its simplicity.",
    "Machine learning is a subset of artificial intelligence.",
    "FAISS is a library for efficient similarity search developed by Facebook.",
    "RAG stands for Retrieval Augmented Generation.",
    "Vector databases store embeddings for semantic search.",
    "The Transformer architecture revolutionized NLP in 2017.",
    "Cosine similarity measures the angle between two vectors.",
    "Large language models are trained on massive text corpora.",
    "Chunking splits documents into smaller pieces for embedding.",
    "Embeddings are dense numerical representations of text.",
]

# ── 3. Generate Embeddings ────────────────────────────────────────────────────

print("Generating embeddings...")
# Returns numpy array of shape (n_documents, 384)
embeddings = model.encode(documents, show_progress_bar=True)

# CRITICAL: FAISS requires float32
embeddings = embeddings.astype(np.float32)

print(f"Embeddings shape: {embeddings.shape}")  # (10, 384)

# ── 4. Build FAISS Index ──────────────────────────────────────────────────────

# IndexFlatL2 = Flat (brute force) index with L2 (Euclidean) distance
# This is the simplest, most accurate index type
# Great for prototyping because there's no configuration needed
index = faiss.IndexFlatL2(EMBEDDING_DIM)

# For cosine similarity, use IndexFlatIP (Inner Product)
# BUT you must normalize vectors first!
# index = faiss.IndexFlatIP(EMBEDDING_DIM)
# faiss.normalize_L2(embeddings)  # ← normalize in-place

print(f"Index is trained: {index.is_trained}")  # Flat index is always "trained"
print(f"Vectors in index: {index.ntotal}")  # 0 — nothing added yet

# Add vectors to the index
# FAISS assigns sequential integer IDs: 0, 1, 2, ...
index.add(embeddings)
print(f"Vectors in index: {index.ntotal}")  # 10 after adding

# ── 5. Search ─────────────────────────────────────────────────────────────────

query = "What is retrieval augmented generation?"

# Embed the query using the SAME model
query_embedding = model.encode([query]).astype(np.float32)
# Shape: (1, 384) — FAISS expects a 2D array even for single queries

k = 3  # Number of neighbours to retrieve

# search() returns:
#   distances: (1, k) array of L2 distances — lower = more similar
#   indices:   (1, k) array of document indices — maps back to your docs list
distances, indices = index.search(query_embedding, k)

print("\n=== Search Results ===")
for rank, (dist, idx) in enumerate(zip(distances[0], indices[0])):
    print(f"Rank {rank + 1}: [{dist:.4f}] {documents[idx]}")

# ── 6. Advanced: IVF Index for Scale ─────────────────────────────────────────

"""
For > 100k vectors, switch from Flat to IVF:
- Build time: cluster vectors into cells (like K-means)
- Query time: only search nprobe cells instead of all vectors
"""

# Rule of thumb: nlist ≈ sqrt(n_vectors)
# For 10k vectors → nlist=100, for 1M → nlist=1000
nlist = 5  # Low because we only have 10 docs (normally sqrt(n))

# IVF_Flat = IVF clustering + flat (exact) search within each cell
quantizer = faiss.IndexFlatL2(EMBEDDING_DIM)  # Used to assign vectors to cells
ivf_index = faiss.IndexIVFFlat(quantizer, EMBEDDING_DIM, nlist)

# IVF indexes MUST be trained before adding vectors
# Training finds the cluster centroids
ivf_index.train(embeddings)  # Needs representative sample of your data
ivf_index.add(embeddings)

# nprobe = how many cells to search (accuracy vs speed tradeoff)
# Higher nprobe → more accurate but slower
# Start with nprobe=1, increase until recall is acceptable
ivf_index.nprobe = 2  # Search 2 out of 5 cells

distances_ivf, indices_ivf = ivf_index.search(query_embedding, k)
print("\n=== IVF Index Results ===")
for rank, (dist, idx) in enumerate(zip(distances_ivf[0], indices_ivf[0])):
    print(f"Rank {rank + 1}: [{dist:.4f}] {documents[idx]}")

# ── 7. Save and Load (Manual Persistence) ────────────────────────────────────

"""
FAISS has NO automatic persistence.
You manually serialize the index to a file.
This is one of FAISS's major limitations vs a proper vector DB.
"""

import pickle
import os

# Save FAISS index binary
faiss.write_index(index, "my_faiss_index.bin")

# Save document store separately (FAISS only stores vectors, not text!)
# You need to maintain the mapping: vector_id → original_text
doc_store = {i: doc for i, doc in enumerate(documents)}
with open("my_doc_store.pkl", "wb") as f:
    pickle.dump(doc_store, f)

# Load back
loaded_index = faiss.read_index("my_faiss_index.bin")
with open("my_doc_store.pkl", "rb") as f:
    loaded_doc_store = pickle.load(f)

print(f"\nLoaded index has {loaded_index.ntotal} vectors")

# Clean up
os.remove("my_faiss_index.bin")
os.remove("my_doc_store.pkl")
```

### 5.3 FAISS with LangChain (Production Prototyping Pattern)

```python
"""
LangChain's FAISS wrapper handles:
  - The doc_store mapping (text ↔ vector ID)
  - Metadata storage
  - save_local / load_local convenience methods
  - Integration with retrievers, chains
"""

from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.schema import Document

# ── 1. Setup Embeddings ───────────────────────────────────────────────────────

embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    model_kwargs={"device": "cpu"},  # "cuda" if GPU available
    encode_kwargs={
        "normalize_embeddings": True,  # L2-normalize → dot product ≈ cosine
        "batch_size": 32,  # Process 32 chunks at a time
    },
)

# ── 2. Create Documents with Metadata ────────────────────────────────────────

"""
In production, metadata is how you do filtering.
Always store: source, page, section, chunk_id, creation_date
"""

documents = [
    Document(
        page_content="Python is a high-level programming language.",
        metadata={"source": "python_docs.pdf", "page": 1, "section": "intro"},
    ),
    Document(
        page_content="Machine learning uses algorithms to learn from data.",
        metadata={"source": "ml_textbook.pdf", "page": 5, "section": "basics"},
    ),
    Document(
        page_content="FAISS enables billion-scale similarity search.",
        metadata={"source": "faiss_paper.pdf", "page": 2, "section": "overview"},
    ),
    Document(
        page_content="RAG combines retrieval with language model generation.",
        metadata={"source": "rag_paper.pdf", "page": 1, "section": "abstract"},
    ),
    Document(
        page_content="Vector embeddings represent semantic meaning numerically.",
        metadata={"source": "embeddings_guide.pdf", "page": 3, "section": "intro"},
    ),
]

# ── 3. Create FAISS Index from Documents ─────────────────────────────────────

print("Building FAISS index...")
vectorstore = FAISS.from_documents(
    documents=documents,
    embedding=embeddings,
    # distance_strategy="COSINE"  # or "EUCLIDEAN_DISTANCE", "MAX_INNER_PRODUCT"
)

# ── 4. Search Methods ─────────────────────────────────────────────────────────

query = "How does retrieval augmented generation work?"

# Method 1: similarity_search — returns Document objects
print("\n=== similarity_search ===")
results = vectorstore.similarity_search(query, k=3)
for doc in results:
    print(f"  Source: {doc.metadata['source']}")
    print(f"  Content: {doc.page_content[:80]}")
    print()

# Method 2: similarity_search_with_score — returns (Document, score) pairs
print("=== similarity_search_with_score ===")
results_scored = vectorstore.similarity_search_with_score(query, k=3)
for doc, score in results_scored:
    # With normalized embeddings: lower L2 score = more similar
    print(f"  Score: {score:.4f} | {doc.page_content[:60]}")

# Method 3: similarity_search_with_relevance_scores — normalized 0-1
print("\n=== similarity_search_with_relevance_scores ===")
results_rel = vectorstore.similarity_search_with_relevance_scores(query, k=3)
for doc, score in results_rel:
    # 1.0 = most relevant, 0.0 = least relevant
    print(f"  Relevance: {score:.4f} | {doc.page_content[:60]}")

# Method 4: Metadata filtering
print("\n=== Metadata Filtering ===")
results_filtered = vectorstore.similarity_search(
    query,
    k=3,
    filter={"source": "rag_paper.pdf"},  # Only search RAG paper chunks
)
for doc in results_filtered:
    print(f"  {doc.metadata['source']}: {doc.page_content[:60]}")

# ── 5. As a LangChain Retriever ───────────────────────────────────────────────

# This is what plugs into your existing RAG chain!
retriever = vectorstore.as_retriever(
    search_type="similarity",  # or "mmr" or "similarity_score_threshold"
    search_kwargs={
        "k": 4,  # Return top 4 chunks
        # "score_threshold": 0.7,      # Only return if relevance > 0.7
        # "filter": {"source": "..."}  # Optional metadata filter
    },
)

# search_type="mmr" = Maximum Marginal Relevance
# Balances relevance + diversity: avoids returning 4 near-identical chunks
retriever_mmr = vectorstore.as_retriever(
    search_type="mmr",
    search_kwargs={
        "k": 4,
        "fetch_k": 20,  # Fetch 20, then pick 4 diverse ones
        "lambda_mult": 0.5,  # 0=max diversity, 1=max relevance
    },
)

# ── 6. Persistence (Save/Load) ────────────────────────────────────────────────

import os

# Save index and docstore to a local folder
FAISS_PATH = "./faiss_index"
vectorstore.save_local(FAISS_PATH)
print(f"\nSaved FAISS index to {FAISS_PATH}/")
# Creates: faiss_index/index.faiss (binary index)
#          faiss_index/index.pkl   (docstore with texts + metadata)

# Load back (e.g., in a new process / server restart)
loaded_vectorstore = FAISS.load_local(
    FAISS_PATH,
    embeddings=embeddings,  # Must use same embedding model!
    allow_dangerous_deserialization=True,  # Required flag for pickle loading
)
print(f"Loaded vectorstore with {loaded_vectorstore.index.ntotal} vectors")

# ── 7. Adding Documents Incrementally ────────────────────────────────────────

"""
FAISS supports adding more documents after initial creation.
Useful when new documents arrive in batches.
"""

new_docs = [
    Document(
        page_content="Transformers use attention mechanisms for NLP tasks.",
        metadata={"source": "attention_paper.pdf", "page": 1},
    )
]

# Add new documents to existing index
vectorstore.add_documents(new_docs)
print(f"\nAfter adding: {vectorstore.index.ntotal} vectors")

# Save again to persist the additions
vectorstore.save_local(FAISS_PATH)

# ── 8. Merge Multiple FAISS Indexes ──────────────────────────────────────────

"""
Useful for: processing large document sets in parallel, then merging
"""

docs_batch_2 = [
    Document(
        page_content="PyTorch is a deep learning framework.",
        metadata={"source": "pytorch.pdf"},
    )
]

# Create a second index
index2 = FAISS.from_documents(docs_batch_2, embeddings)

# Merge into the first
vectorstore.merge_from(index2)
print(f"After merge: {vectorstore.index.ntotal} vectors")

# ── 9. Full RAG Chain with FAISS ──────────────────────────────────────────────

from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate


# This is the same chain pattern you already built!
def format_docs(docs):
    """Join retrieved chunks into a single context string."""
    return "\n\n".join(
        f"[Source: {doc.metadata.get('source', 'unknown')}]\n{doc.page_content}"
        for doc in docs
    )


prompt = ChatPromptTemplate.from_template("""
Answer the question based only on the following context:

{context}

Question: {question}

Answer:""")

# Plug FAISS retriever into your existing chain pattern
rag_chain = (
    RunnablePassthrough.assign(
        context=(lambda x: x["question"]) | retriever | format_docs
    )
    | prompt
    # | llm           ← plug in your existing LLM here
    # | StrOutputParser()
)

# Test retrieval (without LLM for now)
chain_input = {"question": "What is RAG?"}
context_result = (lambda x: x["question"]) | retriever | format_docs
retrieved_context = context_result.invoke(chain_input["question"])
print(f"\nRetrieved context preview:\n{retrieved_context[:300]}...")
```

### 5.4 FAISS Limitations (Why You Need a Real DB for Production)

```python
"""
FAISS Limitations Summary:

1. NO SERVER: runs inside your Python process
   → Can't share index across multiple API workers/containers
   → Each worker would load its own copy = RAM × n_workers

2. NO PERSISTENCE BY DEFAULT: save/load is manual
   → If process crashes without saving, all data lost
   → No WAL (write-ahead log), no crash recovery

3. NO METADATA FILTERING (fast):
   → Filtering = post-query filter → you over-fetch then discard
   → Inefficient compared to Qdrant/Weaviate which filter DURING search

4. NO UPDATES/DELETES:
   → Can't update an existing vector in-place
   → Can't delete a specific vector (must rebuild index)
   → This is a serious problem when documents change

5. NO CONCURRENT WRITES:
   → Not thread-safe for concurrent index modification
   → Read-only is fine, but writes need external locking

CONCLUSION: Use FAISS for prototyping, experiments, offline pipelines.
Switch to Chroma (simple persistence) or Pgvector (full production)
before going to production.
"""
```

---

## 6. Chroma — Persistence

Chroma is the "next step up" from FAISS. It adds a proper embedded database
engine with automatic persistence, metadata filtering, and a client-server mode.

**When to use:** Small-to-medium production (< 1M vectors), single-server 
deployments, when you want a "just works" solution with persistence.

### 6.1 Installation & Setup

```bash
pip install chromadb langchain-chroma sentence-transformers

# For client-server mode (production):
# pip install chromadb-client
# docker run -p 8000:8000 chromadb/chroma
```

### 6.2 Chroma Internals

```
Chroma Architecture:
┌─────────────────────────────────────────────────────────────┐
│  ChromaDB                                                   │
│                                                             │
│  ┌─────────────────┐    ┌─────────────────────────────┐     │
│  │   Collections   │    │   Storage Backend           │     │
│  │   (namespaces)  │    │                             │     │
│  │                 │    │  SQLite    ← metadata       │     │
│  │  "my_docs"      │    │  + documents + IDs          │     │
│  │  "code_chunks"  │    │                             │     │
│  │  "qa_pairs"     │    │  HNSW Index ← vectors       │     │
│  └─────────────────┘    │  (via hnswlib)              │     │
│                         │                             │     │
│                         └─────────────────────────────┘     │
│                                                             │
│  Modes:                                                     │
│  1. In-memory (testing, ephemeral)                          │
│  2. Persistent (local disk, SQLite + HNSW files)            │
│  3. Client-server (separate Chroma server process)          │
└─────────────────────────────────────────────────────────────┘
```

### 6.3 Raw Chroma Client (Understanding Internals)

```python
import chromadb
from chromadb.utils import embedding_functions

# ── 1. Client Modes ───────────────────────────────────────────────────────────

# MODE 1: In-memory (for tests, no persistence)
client_memory = chromadb.EphemeralClient()

# MODE 2: Persistent (local disk, SQLite + HNSW)
# Data survives process restarts
client = chromadb.PersistentClient(path="./chroma_db")
# Creates: ./chroma_db/chroma.sqlite3  (metadata, docs)
#          ./chroma_db/<uuid>/          (HNSW index files)

# MODE 3: HTTP Client (connect to Chroma server)
# client = chromadb.HttpClient(host="localhost", port=8000)

# ── 2. Collections ───────────────────────────────────────────────────────────

"""
Collections are like tables in SQL or indexes in Elasticsearch.
Each collection has its own HNSW index and metadata store.
Use separate collections for different document types/use cases.
"""

# Create or get (idempotent — safe to call multiple times)
collection = client.get_or_create_collection(
    name="rag_documents",
    # Chroma's built-in embedding function
    # Or we'll use our own embeddings below
    embedding_function=embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    ),
    # Distance metric for HNSW
    metadata={"hnsw:space": "cosine"},
    # Options: "cosine" (default), "l2", "ip" (inner product)
)

print(f"Collection: {collection.name}")
print(f"Count: {collection.count()}")  # 0

# ── 3. Adding Documents ───────────────────────────────────────────────────────

"""
Chroma requires you to provide IDs manually.
Choose meaningful IDs: hash of content, or doc_name + chunk_index
"""

import hashlib


def make_id(text: str) -> str:
    """Create deterministic ID from text content (deduplication benefit)."""
    return hashlib.md5(text.encode()).hexdigest()[:16]


documents = [
    "Python is a high-level programming language known for its simplicity.",
    "Machine learning uses statistical algorithms to learn from data.",
    "FAISS is a library for efficient similarity search by Facebook Research.",
    "RAG combines retrieval with generation for knowledge-grounded LLMs.",
    "ChromaDB is an open-source embedding database with persistence.",
]

metadatas = [
    {"source": "python_docs.pdf", "page": 1, "category": "programming"},
    {"source": "ml_book.pdf", "page": 5, "category": "ai"},
    {"source": "faiss_paper.pdf", "page": 1, "category": "vectordb"},
    {"source": "rag_paper.pdf", "page": 1, "category": "ai"},
    {"source": "chroma_docs.pdf", "page": 1, "category": "vectordb"},
]

ids = [make_id(doc) for doc in documents]

# Add documents (Chroma will embed them automatically using the collection's
# embedding function if you don't provide pre-computed embeddings)
collection.add(
    documents=documents,  # Chroma will embed these
    metadatas=metadatas,
    ids=ids,
)

print(f"Count after add: {collection.count()}")  # 5

# ── 4. Query ──────────────────────────────────────────────────────────────────

# Basic semantic search
results = collection.query(
    query_texts=["What is retrieval augmented generation?"],
    n_results=3,
    # include what to return in results
    include=["documents", "distances", "metadatas"],
)

print("\n=== Chroma Query Results ===")
for i, (doc, dist, meta) in enumerate(
    zip(results["documents"][0], results["distances"][0], results["metadatas"][0])
):
    print(f"Rank {i + 1}: distance={dist:.4f}")
    print(f"  Source: {meta['source']}")
    print(f"  Text: {doc[:80]}")

# ── 5. Metadata Filtering (WHERE clause) ─────────────────────────────────────

"""
Chroma's `where` clause filters BEFORE similarity search.
This is more efficient than FAISS post-filtering.
"""

# Filter by exact value
results_filtered = collection.query(
    query_texts=["vector similarity search"],
    n_results=2,
    where={"category": "vectordb"},  # Only search vectordb docs
)

# Filter with operators
results_complex = collection.query(
    query_texts=["machine learning"],
    n_results=3,
    where={
        "$or": [
            {"category": {"$eq": "ai"}},
            {"page": {"$gte": 3}},  # page >= 3
        ]
    },
    # Operators: $eq, $ne, $gt, $gte, $lt, $lte, $in, $nin, $and, $or
)

# Filter on document content (not just metadata)
results_content = collection.query(
    query_texts=["programming"],
    n_results=3,
    where_document={"$contains": "Python"},  # Document text contains "Python"
)

# ── 6. CRUD Operations ────────────────────────────────────────────────────────

# UPDATE: Modify existing document
collection.update(
    ids=[ids[0]],
    documents=["Python is a versatile, high-level language used in AI and web."],
    metadatas=[
        {
            "source": "python_docs.pdf",
            "page": 1,
            "category": "programming",
            "updated": True,
        }
    ],
)

# UPSERT: Add if not exists, update if exists
collection.upsert(
    ids=["new_doc_001"],
    documents=["LangChain is a framework for building LLM applications."],
    metadatas=[{"source": "langchain_docs.pdf", "category": "ai"}],
)

# DELETE by ID
collection.delete(ids=["new_doc_001"])
print(f"After delete: {collection.count()}")  # Back to 5

# DELETE by filter (dangerous — deletes all matching!)
# collection.delete(where={"category": "old"})

# ── 7. Pre-computed Embeddings ────────────────────────────────────────────────

"""
If you want to use your own embedding model (not Chroma's built-in):
1. Compute embeddings yourself
2. Pass them directly to collection.add() via `embeddings` parameter
"""

from sentence_transformers import SentenceTransformer
import numpy as np

model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

new_texts = ["Attention is all you need was the transformer paper."]
new_embeddings = model.encode(new_texts).tolist()  # Must be list of lists

# Create collection WITHOUT embedding function (you manage embeddings)
raw_collection = client.get_or_create_collection(
    name="manual_embeddings",
    metadata={"hnsw:space": "cosine"},
    # No embedding_function — we'll provide vectors ourselves
)

raw_collection.add(
    embeddings=new_embeddings,  # Pre-computed
    documents=new_texts,
    ids=["attn_001"],
)

# Query also needs pre-computed embedding
query_embedding = model.encode(["transformer attention mechanism"]).tolist()
results = raw_collection.query(
    query_embeddings=query_embedding,  # Pre-computed query vector
    n_results=1,
)
print(f"\nManual embedding query: {results['documents'][0][0][:60]}")
```

### 6.4 Chroma with LangChain (Full RAG Integration)

```python
from langchain_chroma import (
    Chroma,
)  # or: from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.schema import Document
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

# ── 1. Embeddings ─────────────────────────────────────────────────────────────

embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True},
)

CHROMA_PATH = "./chroma_langchain_db"

# ── 2. Build Vectorstore (First Run) ─────────────────────────────────────────

documents = [
    Document(
        page_content="The mitochondria is the powerhouse of the cell.",
        metadata={"source": "biology.pdf", "chapter": 3, "topic": "cell_biology"},
    ),
    Document(
        page_content="Neurons transmit electrical signals via synapses.",
        metadata={"source": "neuroscience.pdf", "chapter": 1, "topic": "brain"},
    ),
    Document(
        page_content="DNA carries genetic information in a double helix structure.",
        metadata={"source": "genetics.pdf", "chapter": 2, "topic": "genetics"},
    ),
    Document(
        page_content="The immune system defends against pathogens using antibodies.",
        metadata={"source": "immunology.pdf", "chapter": 5, "topic": "immunity"},
    ),
    Document(
        page_content="Photosynthesis converts sunlight into chemical energy in plants.",
        metadata={"source": "botany.pdf", "chapter": 4, "topic": "plants"},
    ),
]

# Create vectorstore with persistence
# The `persist_directory` parameter enables automatic disk persistence
vectorstore = Chroma.from_documents(
    documents=documents,
    embedding=embeddings,
    persist_directory=CHROMA_PATH,
    collection_name="biology_rag",
    collection_metadata={"hnsw:space": "cosine"},  # Distance metric
)

print(f"Vectorstore created with {vectorstore._collection.count()} vectors")

# ── 3. Reload Existing Vectorstore (Subsequent Runs) ─────────────────────────

"""
This is the KEY difference from FAISS:
Chroma automatically persists to disk and reloads on next run.
No manual save/load needed!
"""


def get_or_create_vectorstore(
    documents: list, embeddings, path: str, collection_name: str
) -> Chroma:
    """
    Production pattern: load existing vectorstore if it exists,
    otherwise create it from documents.
    This avoids re-embedding on every server restart!
    """
    import os

    if os.path.exists(path) and os.listdir(path):
        # Load existing — this is instant, no re-embedding needed
        print(f"Loading existing vectorstore from {path}...")
        return Chroma(
            persist_directory=path,
            embedding_function=embeddings,
            collection_name=collection_name,
        )
    else:
        # Create new — this embeds all documents (expensive!)
        print(f"Creating new vectorstore at {path}...")
        return Chroma.from_documents(
            documents=documents,
            embedding=embeddings,
            persist_directory=path,
            collection_name=collection_name,
        )


vectorstore = get_or_create_vectorstore(
    documents, embeddings, CHROMA_PATH, "biology_rag"
)

# ── 4. Adding New Documents (Incremental Update) ─────────────────────────────

new_documents = [
    Document(
        page_content="CRISPR-Cas9 allows precise gene editing in living organisms.",
        metadata={
            "source": "crispr.pdf",
            "chapter": 1,
            "topic": "genetics",
            "added_at": "2024-01-15",
        },
    )
]

# Add to existing collection — no need to rebuild from scratch!
vectorstore.add_documents(new_documents)
print(f"After adding: {vectorstore._collection.count()} vectors")

# ── 5. Retriever with Advanced Configuration ──────────────────────────────────

# Standard retriever
retriever_basic = vectorstore.as_retriever(
    search_type="similarity", search_kwargs={"k": 3}
)

# Retriever with metadata filtering
retriever_filtered = vectorstore.as_retriever(
    search_type="similarity",
    search_kwargs={
        "k": 3,
        "filter": {"topic": "genetics"},  # Chroma uses "filter" not "where"
    },
)

# MMR retriever (diversity + relevance)
retriever_mmr = vectorstore.as_retriever(
    search_type="mmr",
    search_kwargs={
        "k": 3,
        "fetch_k": 10,
        "lambda_mult": 0.7,  # 70% relevance, 30% diversity
    },
)

# Score threshold retriever (only return if relevant enough)
retriever_threshold = vectorstore.as_retriever(
    search_type="similarity_score_threshold",
    search_kwargs={
        "score_threshold": 0.5,  # 0-1 range; adjust based on your similarity metric
        "k": 5,
    },
)

# ── 6. Complete RAG Chain ─────────────────────────────────────────────────────


def format_docs_with_metadata(docs: list[Document]) -> str:
    """Format retrieved docs with source citations for the LLM."""
    formatted = []
    for i, doc in enumerate(docs):
        source = doc.metadata.get("source", "unknown")
        chapter = doc.metadata.get("chapter", "?")
        formatted.append(
            f"[{i + 1}] Source: {source}, Chapter {chapter}\n{doc.page_content}"
        )
    return "\n\n".join(formatted)


prompt = ChatPromptTemplate.from_template("""
You are a biology tutor. Answer the student's question using only the provided context.
Always cite your sources using the [N] format.

Context:
{context}

Student Question: {question}

Answer:""")

# The RAG chain — same pattern as your FAISS chain
rag_chain = (
    RunnablePassthrough.assign(
        context=(lambda x: x["question"]) | retriever_basic | format_docs_with_metadata
    )
    | prompt
    # | llm | StrOutputParser()   ← add your LLM here
)

# ── 7. Production Pattern: Separate Index & Query Services ────────────────────


class ChromaVectorStore:
    """
    Production-ready wrapper around Chroma.
    Separates indexing (write) from querying (read) concerns.
    """

    def __init__(self, persist_dir: str, collection_name: str, embeddings):
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self.embeddings = embeddings
        self._store = None

    def _get_store(self) -> Chroma:
        """Lazy load the store (don't connect until needed)."""
        if self._store is None:
            self._store = Chroma(
                persist_directory=self.persist_dir,
                embedding_function=self.embeddings,
                collection_name=self.collection_name,
            )
        return self._store

    def index_documents(self, documents: list[Document], batch_size: int = 100):
        """
        Index documents in batches to avoid memory issues with large datasets.
        Each batch is committed to disk before the next batch starts.
        """
        store = self._get_store()
        total = len(documents)

        for i in range(0, total, batch_size):
            batch = documents[i : i + batch_size]
            store.add_documents(batch)
            print(f"Indexed {min(i + batch_size, total)}/{total} documents")

        print(f"Indexing complete. Total: {store._collection.count()} vectors")

    def similarity_search(
        self, query: str, k: int = 4, filter_dict: dict = None
    ) -> list[Document]:
        """Semantic search with optional metadata filtering."""
        store = self._get_store()
        kwargs = {"k": k}
        if filter_dict:
            kwargs["filter"] = filter_dict
        return store.similarity_search(query, **kwargs)

    def delete_by_source(self, source: str):
        """
        Delete all chunks from a specific document.
        Use when a source document is updated or removed.
        """
        store = self._get_store()
        # Get IDs for chunks from this source
        results = store._collection.get(
            where={"source": source},
            include=[],  # Only need IDs, not content
        )

        if results["ids"]:
            store._collection.delete(ids=results["ids"])
            print(f"Deleted {len(results['ids'])} chunks from '{source}'")

    def get_retriever(self, k: int = 4, search_type: str = "mmr"):
        """Get a configured LangChain retriever for use in chains."""
        return self._get_store().as_retriever(
            search_type=search_type, search_kwargs={"k": k}
        )


# Usage
chroma_store = ChromaVectorStore(CHROMA_PATH, "biology_rag", embeddings)
results = chroma_store.similarity_search("What is gene editing?", k=2)
for doc in results:
    print(f"  {doc.metadata['source']}: {doc.page_content[:80]}")
```

---

## 7. Pgvector — Production

**pgvector** is a PostgreSQL extension that adds vector similarity search to 
the world's most battle-tested relational database. This is the gold standard
for production RAG when you need:

- SQL joins (combine vector search with business data)
- ACID transactions  
- Existing PostgreSQL infrastructure
- Hybrid search (full-text + vector in one query)

### 7.1 Setup

```bash
# Install Python packages
pip install pgvector psycopg2-binary langchain-postgres sqlalchemy

# Docker: PostgreSQL with pgvector
docker run -d \
  --name pgvector-db \
  -e POSTGRES_USER=rag_user \
  -e POSTGRES_PASSWORD=rag_password \
  -e POSTGRES_DB=rag_db \
  -p 5432:5432 \
  pgvector/pgvector:pg16   # Official pgvector image

# Or add to existing Postgres
# psql -c "CREATE EXTENSION vector;"
```

### 7.2 Raw pgvector SQL (Understanding the Foundation)

```sql
-- Enable the pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create a table with a vector column
-- 384 = MiniLM embedding dimension
CREATE TABLE documents (
    id          SERIAL PRIMARY KEY,
    content     TEXT NOT NULL,
    embedding   vector(384),        -- ← pgvector column type
    source      TEXT,
    page_num    INTEGER,
    category    TEXT,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- Create HNSW index for fast ANN search
-- This is the recommended index for most production use cases
CREATE INDEX ON documents 
USING hnsw (embedding vector_cosine_ops)  -- cosine similarity
WITH (
    m = 16,                -- Number of connections per layer (more = better recall, more RAM)
    ef_construction = 64   -- Build quality (higher = better index, slower build)
);

-- Alternative: IVFFlat index (less RAM, good recall)
-- CREATE INDEX ON documents 
-- USING ivfflat (embedding vector_cosine_ops)
-- WITH (lists = 100);  -- sqrt(n_rows) is a good starting point

-- Example: Insert a document with its embedding
-- (In practice, Python generates the embedding array)
INSERT INTO documents (content, embedding, source, category)
VALUES (
    'RAG combines retrieval with generation.',
    '[0.1, 0.2, -0.3, ...]'::vector,  -- 384 floats
    'rag_paper.pdf',
    'ai'
);

-- Similarity search: find top 5 most similar to a query vector
-- <=> is cosine distance operator (lower = more similar)
-- <->  is L2 distance
-- <#>  is negative inner product (for dot product similarity)
SELECT 
    content,
    source,
    1 - (embedding <=> '[0.1, 0.2, -0.3, ...]'::vector) AS cosine_similarity
FROM documents
ORDER BY embedding <=> '[0.1, 0.2, -0.3, ...]'::vector  -- ORDER BY distance
LIMIT 5;

-- HYBRID SEARCH: combine full-text search with vector search
-- This is a major advantage of pgvector over standalone vector DBs
SELECT 
    content,
    source,
    -- Combine BM25 text score with cosine similarity
    ts_rank(to_tsvector('english', content), query) AS text_score,
    1 - (embedding <=> '[0.1, ...]'::vector) AS vector_score
FROM documents, 
     to_tsquery('english', 'retrieval & augmented') query
WHERE to_tsvector('english', content) @@ query   -- Full-text filter first
ORDER BY (
    0.3 * ts_rank(to_tsvector('english', content), query) +
    0.7 * (1 - (embedding <=> '[0.1, ...]'::vector))  -- Weighted combination
) DESC
LIMIT 10;

-- Metadata filtering + vector search (efficient)
SELECT content, source, category
FROM documents
WHERE category = 'ai'               -- Filter applied BEFORE vector search
  AND source != 'deprecated.pdf'
ORDER BY embedding <=> '[0.1, ...]'::vector
LIMIT 5;
```

### 7.3 Python: Direct pgvector (Full Control)

```python
"""
Using psycopg2 + pgvector directly.
Gives you full SQL control — important for production systems.
"""

import psycopg2
import numpy as np
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer

# ── 1. Connection ─────────────────────────────────────────────────────────────

# Production: use environment variables, not hardcoded credentials
import os

DB_CONFIG = {
    "host": os.getenv("PGHOST", "localhost"),
    "port": os.getenv("PGPORT", "5432"),
    "dbname": os.getenv("PGDATABASE", "rag_db"),
    "user": os.getenv("PGUSER", "rag_user"),
    "password": os.getenv("PGPASSWORD", "rag_password"),
}

conn = psycopg2.connect(**DB_CONFIG)
register_vector(conn)  # Teach psycopg2 how to handle vector type

# ── 2. Schema Setup ───────────────────────────────────────────────────────────

with conn.cursor() as cur:
    # Enable extension (idempotent — safe to run multiple times)
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # Create documents table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rag_documents (
            id          SERIAL PRIMARY KEY,
            doc_id      TEXT UNIQUE,           -- External ID (hash, filename+chunk)
            content     TEXT NOT NULL,
            embedding   vector(384),
            source      TEXT,
            page_num    INTEGER,
            category    TEXT,
            chunk_index INTEGER,               -- Position within source document
            created_at  TIMESTAMP DEFAULT NOW(),
            updated_at  TIMESTAMP DEFAULT NOW()
        );
    """)

    # HNSW index — best for production (fast query, good recall)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS rag_docs_embedding_hnsw_idx 
        ON rag_documents 
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
    """)

    # Regular indexes on metadata columns for fast filtering
    cur.execute("CREATE INDEX IF NOT EXISTS idx_category ON rag_documents(category);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_source ON rag_documents(source);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_doc_id ON rag_documents(doc_id);")

    # Full-text search index for hybrid search
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_fts 
        ON rag_documents 
        USING gin(to_tsvector('english', content));
    """)

    conn.commit()

print("Schema created successfully")

# ── 3. Embedding Model ────────────────────────────────────────────────────────

model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

# ── 4. Indexing Documents ─────────────────────────────────────────────────────


def index_documents(conn, documents: list[dict], model):
    """
    Batch-insert documents with their embeddings.

    documents: list of dicts with keys: content, source, page_num,
                                         category, chunk_index
    """
    import hashlib

    # Generate all embeddings in one batch (GPU-friendly)
    texts = [doc["content"] for doc in documents]
    embeddings = model.encode(texts, show_progress_bar=True)

    # Batch insert
    with conn.cursor() as cur:
        for doc, embedding in zip(documents, embeddings):
            # Deterministic ID: if same content is re-indexed, it updates
            doc_id = hashlib.md5(
                f"{doc['source']}_chunk{doc['chunk_index']}".encode()
            ).hexdigest()

            cur.execute(
                """
                INSERT INTO rag_documents 
                    (doc_id, content, embedding, source, page_num, category, chunk_index)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (doc_id) DO UPDATE SET
                    content    = EXCLUDED.content,
                    embedding  = EXCLUDED.embedding,
                    updated_at = NOW();
            """,
                (
                    doc_id,
                    doc["content"],
                    embedding.tolist(),  # numpy array → Python list
                    doc.get("source"),
                    doc.get("page_num"),
                    doc.get("category"),
                    doc.get("chunk_index", 0),
                ),
            )

    conn.commit()
    print(f"Indexed {len(documents)} documents")


# Sample documents (in practice, these come from your chunking pipeline)
sample_docs = [
    {
        "content": "Python is a high-level language.",
        "source": "python.pdf",
        "page_num": 1,
        "category": "programming",
        "chunk_index": 0,
    },
    {
        "content": "Machine learning learns from data.",
        "source": "ml.pdf",
        "page_num": 5,
        "category": "ai",
        "chunk_index": 0,
    },
    {
        "content": "RAG uses retrieval for grounded generation.",
        "source": "rag.pdf",
        "page_num": 1,
        "category": "ai",
        "chunk_index": 0,
    },
    {
        "content": "pgvector adds vector search to PostgreSQL.",
        "source": "pgvector.pdf",
        "page_num": 1,
        "category": "vectordb",
        "chunk_index": 0,
    },
    {
        "content": "Transformers revolutionised natural language processing.",
        "source": "attn.pdf",
        "page_num": 1,
        "category": "ai",
        "chunk_index": 0,
    },
]

index_documents(conn, sample_docs, model)

# ── 5. Similarity Search ──────────────────────────────────────────────────────


def vector_search(
    conn,
    query: str,
    model,
    k: int = 5,
    category_filter: str = None,
    source_filter: str = None,
    min_similarity: float = 0.0,
) -> list[dict]:
    """
    Full-featured vector search with optional filters.

    Returns: list of dicts with content, source, similarity_score
    """
    # Embed the query
    query_embedding = model.encode([query])[0].tolist()

    # Build dynamic WHERE clause based on filters
    conditions = ["1=1"]  # Always true base condition
    params = [query_embedding]

    if category_filter:
        conditions.append("category = %s")
        params.append(category_filter)

    if source_filter:
        conditions.append("source = %s")
        params.append(source_filter)

    if min_similarity > 0:
        # cosine distance = 1 - cosine_similarity
        max_distance = 1 - min_similarity
        conditions.append("(embedding <=> %s::vector) < %s")
        params.extend([query_embedding, max_distance])

    where_clause = " AND ".join(conditions)
    params.append(k)

    sql = f"""
        SELECT 
            content,
            source,
            page_num,
            category,
            chunk_index,
            1 - (embedding <=> %s::vector) AS similarity_score
        FROM rag_documents
        WHERE {where_clause}
        ORDER BY embedding <=> %s::vector   -- Order by distance (ascending)
        LIMIT %s;
    """

    # Insert query_embedding twice: once for SELECT, once for ORDER BY
    all_params = [query_embedding] + params[1:] + [query_embedding, k]

    with conn.cursor() as cur:
        cur.execute(sql, [query_embedding] + params[0:-1] + [query_embedding, k])
        rows = cur.fetchall()

    return [
        {
            "content": row[0],
            "source": row[1],
            "page_num": row[2],
            "category": row[3],
            "chunk_index": row[4],
            "similarity": float(row[5]),
        }
        for row in rows
    ]


# Search examples
print("\n=== Vector Search ===")
results = vector_search(conn, "What is retrieval augmented generation?", model, k=3)
for r in results:
    print(f"  [{r['similarity']:.4f}] {r['source']}: {r['content'][:60]}")

print("\n=== Filtered Vector Search (AI only) ===")
results_filtered = vector_search(
    conn, "deep learning systems", model, k=3, category_filter="ai"
)
for r in results_filtered:
    print(f"  [{r['similarity']:.4f}] {r['source']}: {r['content'][:60]}")

# ── 6. Hybrid Search: Vector + Full-Text (Production Power Feature) ───────────


def hybrid_search(
    conn,
    query: str,
    model,
    k: int = 5,
    vector_weight: float = 0.7,  # 70% semantic, 30% keyword
    text_weight: float = 0.3,
) -> list[dict]:
    """
    Hybrid search combining pgvector similarity with PostgreSQL full-text search.

    This is more powerful than pure vector search:
    - Vector search: finds semantically similar text (handles synonyms, paraphrases)
    - Full-text search: exact keyword matching (handles proper nouns, IDs, codes)

    Reciprocal Rank Fusion (RRF) or weighted scoring combines the two.
    """
    query_embedding = model.encode([query])[0].tolist()

    # Convert query to tsquery (handle special chars)
    # For production: use plainto_tsquery or websearch_to_tsquery
    ts_query = " & ".join(query.split())  # Simple: "what is rag" → "what & is & rag"

    sql = """
        WITH 
        -- Vector search results with ranking
        vector_ranked AS (
            SELECT 
                id,
                content,
                source,
                category,
                1 - (embedding <=> %s::vector) AS vec_score,
                ROW_NUMBER() OVER (ORDER BY embedding <=> %s::vector) AS vec_rank
            FROM rag_documents
        ),
        -- Full-text search results with ranking  
        text_ranked AS (
            SELECT 
                id,
                content,
                source,
                category,
                ts_rank(to_tsvector('english', content), 
                        plainto_tsquery('english', %s)) AS text_score,
                ROW_NUMBER() OVER (
                    ORDER BY ts_rank(to_tsvector('english', content),
                                     plainto_tsquery('english', %s)) DESC
                ) AS text_rank
            FROM rag_documents
            WHERE to_tsvector('english', content) @@ plainto_tsquery('english', %s)
        )
        -- Combine with weighted scoring (RRF-inspired)
        SELECT 
            v.content,
            v.source,
            v.category,
            v.vec_score,
            COALESCE(t.text_score, 0) AS text_score,
            -- Weighted final score
            (%s * v.vec_score + %s * COALESCE(t.text_score, 0)) AS final_score
        FROM vector_ranked v
        LEFT JOIN text_ranked t ON v.id = t.id
        ORDER BY final_score DESC
        LIMIT %s;
    """

    with conn.cursor() as cur:
        cur.execute(
            sql,
            [
                query_embedding,
                query_embedding,  # vector_ranked CTEzz
                query,
                query,
                query,  # text_ranked CTE (3x for ts_rank, row_number, where)
                vector_weight,
                text_weight,  # weights
                k,
            ],
        )
        rows = cur.fetchall()

    return [
        {
            "content": row[0],
            "source": row[1],
            "category": row[2],
            "vec_score": float(row[3]),
            "text_score": float(row[4]),
            "final_score": float(row[5]),
        }
        for row in rows
    ]


print("\n=== Hybrid Search ===")
hybrid_results = hybrid_search(conn, "machine learning retrieval", model, k=3)
for r in hybrid_results:
    print(
        f"  [final={r['final_score']:.4f} | vec={r['vec_score']:.4f} "
        f"| text={r['text_score']:.4f}] {r['content'][:60]}"
    )

conn.close()
```

### 7.4 Pgvector with LangChain (Clean Production Integration)

```python
"""
LangChain's PGVector integration handles the schema, embeddings, and retriever.
Use this for clean integration in production FastAPI/Django apps.
"""

from langchain_postgres.vectorstores import PGVector  # New: langchain_postgres

# from langchain_community.vectorstores import PGVector  # Old: langchain_community
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.schema import Document
import os

# ── Connection String ─────────────────────────────────────────────────────────

# Format: postgresql+psycopg://user:password@host:port/dbname
CONNECTION_STRING = (
    f"postgresql+psycopg://{os.getenv('PGUSER', 'rag_user')}:"
    f"{os.getenv('PGPASSWORD', 'rag_password')}@"
    f"{os.getenv('PGHOST', 'localhost')}:"
    f"{os.getenv('PGPORT', '5432')}/"
    f"{os.getenv('PGDATABASE', 'rag_db')}"
)

# ── Embeddings ────────────────────────────────────────────────────────────────

embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True},
)

# ── Documents ─────────────────────────────────────────────────────────────────

documents = [
    Document(
        page_content="The heart pumps blood throughout the body.",
        metadata={"source": "anatomy.pdf", "category": "biology", "page": 12},
    ),
    Document(
        page_content="The liver metabolizes toxins and produces bile.",
        metadata={"source": "anatomy.pdf", "category": "biology", "page": 45},
    ),
    Document(
        page_content="Neurons communicate through electrical and chemical signals.",
        metadata={"source": "neuroscience.pdf", "category": "biology", "page": 3},
    ),
    Document(
        page_content="PostgreSQL is a powerful open-source relational database.",
        metadata={"source": "postgres_docs.pdf", "category": "database", "page": 1},
    ),
    Document(
        page_content="Indexes speed up database queries significantly.",
        metadata={"source": "postgres_docs.pdf", "category": "database", "page": 22},
    ),
]

# ── Create/Load PGVector Vectorstore ─────────────────────────────────────────

"""
PGVector creates a table: langchain_pg_embedding
with columns: uuid, collection_id, embedding, document, cmetadata
"""

vectorstore = PGVector.from_documents(
    documents=documents,
    embedding=embeddings,
    connection=CONNECTION_STRING,
    collection_name="production_rag",  # Logical namespace (like Chroma collection)
    pre_delete_collection=False,  # True = wipe before inserting (use carefully!)
    use_jsonb=True,  # Store metadata as JSONB for better filtering
)

print("PGVector store created")

# Load existing store (no re-embedding)
vectorstore_existing = PGVector(
    embeddings=embeddings,
    collection_name="production_rag",
    connection=CONNECTION_STRING,
    use_jsonb=True,
)

# ── Search ────────────────────────────────────────────────────────────────────

# Basic similarity search
results = vectorstore.similarity_search("blood circulation", k=2)
for doc in results:
    print(f"  {doc.metadata['source']} p.{doc.metadata['page']}: {doc.page_content}")

# With metadata filter (uses JSONB @> operator in SQL)
results_filtered = vectorstore.similarity_search(
    "how databases work", k=3, filter={"category": "database"}
)
for doc in results_filtered:
    print(f"  [{doc.metadata['source']}]: {doc.page_content}")

# ── Retriever for RAG Chain ───────────────────────────────────────────────────

retriever = vectorstore.as_retriever(
    search_type="similarity",
    search_kwargs={
        "k": 4,
        "filter": {"category": "biology"},  # Optional metadata filter
    },
)

# ── Production Pattern: Document Updates ──────────────────────────────────────

"""
When a source document changes:
1. Delete all chunks from that source
2. Re-embed and re-insert the updated chunks

This is clean and transactional with PostgreSQL.
"""


def update_document_source(
    vectorstore: PGVector, old_source: str, new_docs: list[Document]
):
    """Replace all chunks from a source document with new content."""
    # Step 1: Delete old chunks
    # Note: PGVector's delete API varies by version
    # Direct SQL is more reliable for production
    # vectorstore.delete(filter={"source": old_source})

    # Step 2: Add new chunks
    vectorstore.add_documents(new_docs)
    print(f"Updated {len(new_docs)} chunks from '{old_source}'")


# ── Complete Production Service Class ────────────────────────────────────────

from typing import Optional
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate


class ProductionRAGService:
    """
    Production-ready RAG service using PGVector.

    Features:
    - Connection pooling via SQLAlchemy
    - Metadata filtering
    - Hybrid search (vector + SQL filtering)
    - Document CRUD
    - Health check
    """

    def __init__(self, connection_string: str, collection_name: str, embeddings):
        self.connection_string = connection_string
        self.collection_name = collection_name
        self.embeddings = embeddings
        self._vectorstore = None

    @property
    def vectorstore(self) -> PGVector:
        """Lazy initialization with connection reuse."""
        if self._vectorstore is None:
            self._vectorstore = PGVector(
                embeddings=self.embeddings,
                collection_name=self.collection_name,
                connection=self.connection_string,
                use_jsonb=True,
            )
        return self._vectorstore

    def index(self, documents: list[Document]) -> int:
        """Add documents to the vector store. Returns count of indexed docs."""
        ids = self.vectorstore.add_documents(documents)
        return len(ids)

    def search(
        self, query: str, k: int = 4, filter: Optional[dict] = None
    ) -> list[tuple[Document, float]]:
        """Search and return (document, score) tuples."""
        kwargs = {"k": k}
        if filter:
            kwargs["filter"] = filter
        return self.vectorstore.similarity_search_with_score(query, **kwargs)

    def get_retriever(self, k: int = 4, filter: Optional[dict] = None):
        """Get a retriever for use in LangChain chains."""
        search_kwargs = {"k": k}
        if filter:
            search_kwargs["filter"] = filter
        return self.vectorstore.as_retriever(
            search_type="mmr", search_kwargs=search_kwargs
        )

    def health_check(self) -> bool:
        """Verify database connection is healthy."""
        try:
            self.vectorstore.similarity_search("health check", k=1)
            return True
        except Exception as e:
            print(f"Health check failed: {e}")
            return False

    def build_rag_chain(self, llm, k: int = 4):
        """Build a complete RAG chain with this vector store as retriever."""
        retriever = self.get_retriever(k=k)

        def format_docs(docs):
            return "\n\n".join(
                f"Source: {d.metadata.get('source', 'N/A')}\n{d.page_content}"
                for d in docs
            )

        prompt = ChatPromptTemplate.from_template("""
Use the context below to answer the question. Cite sources.

Context:
{context}

Question: {question}

Answer:""")

        return (
            RunnablePassthrough.assign(
                context=(lambda x: x["question"]) | retriever | format_docs
            )
            | prompt
            | llm
            | StrOutputParser()
        )


# Usage
service = ProductionRAGService(CONNECTION_STRING, "production_rag", embeddings)
print(f"Service healthy: {service.health_check()}")

results = service.search("organ functions", k=2, filter={"category": "biology"})
for doc, score in results:
    print(f"  [{score:.4f}] {doc.page_content[:60]}")
```

---

## 8. Other Vector DBs at a Glance

### 8.1 Qdrant — Best Open-Source Production DB

```python
"""
Qdrant: Rust-powered, cloud-native, excellent filtering, REST + gRPC APIs
Killer feature: Named vectors (multiple vector types per document)
                payload (metadata) filtering is first-class and fast

Use when: You want a dedicated vector DB with production features,
          open-source (self-host), no PostgreSQL dependency
"""

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)
from langchain_qdrant import Qdrant  # pip install langchain-qdrant

# ── Setup ─────────────────────────────────────────────────────────────────────

# In-memory (testing)
client = QdrantClient(":memory:")

# Persistent local (single-node production)
# client = QdrantClient(path="./qdrant_data")

# Qdrant server (docker run -p 6333:6333 qdrant/qdrant)
# client = QdrantClient(host="localhost", port=6333)

# Qdrant Cloud
# client = QdrantClient(url="https://xyz.qdrant.io", api_key="...")

# ── Create Collection ─────────────────────────────────────────────────────────

COLLECTION_NAME = "rag_docs"

client.recreate_collection(
    collection_name=COLLECTION_NAME,
    vectors_config=VectorParams(
        size=384,  # Embedding dimension
        distance=Distance.COSINE,  # Or EUCLIDEAN, DOT
        # HNSW config (optional tuning):
        # hnsw_config=HnswConfigDiff(m=16, ef_construct=100)
    ),
    # Enable payload (metadata) indexing for fast filtering
    # payload_schema={"category": PayloadSchemaType.KEYWORD}
)

# ── Index Documents ───────────────────────────────────────────────────────────

from sentence_transformers import SentenceTransformer

model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

texts = [
    "RAG improves LLM accuracy with retrieved context.",
    "Qdrant is a production-ready vector database.",
    "Machine learning models learn from data.",
]
embeddings = model.encode(texts).tolist()

# PointStruct = one document = vector + payload (metadata) + id
points = [
    PointStruct(
        id=i,  # Integer or UUID
        vector=embeddings[i],
        payload={  # Metadata = "payload" in Qdrant
            "text": texts[i],
            "source": f"doc_{i}.pdf",
            "category": ["ai", "rag"][i % 2],
        },
    )
    for i in range(len(texts))
]

client.upsert(collection_name=COLLECTION_NAME, points=points)

# ── Search with Filtering ─────────────────────────────────────────────────────

query_embedding = model.encode(["retrieval augmented generation"]).tolist()[0]

results = client.search(
    collection_name=COLLECTION_NAME,
    query_vector=query_embedding,
    limit=3,
    # Qdrant filtering is evaluated DURING vector search (not post-filter)
    query_filter=Filter(
        must=[FieldCondition(key="category", match=MatchValue(value="ai"))]
    ),
    with_payload=True,  # Include metadata in results
)

for result in results:
    print(f"Score: {result.score:.4f} | {result.payload['text'][:60]}")

# ── LangChain Integration ─────────────────────────────────────────────────────

from langchain_community.embeddings import HuggingFaceEmbeddings

lc_embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

qdrant_lc = Qdrant(
    client=client,
    collection_name=COLLECTION_NAME,
    embeddings=lc_embeddings,
)

# Works exactly like Chroma/FAISS retrievers
retriever = qdrant_lc.as_retriever(search_kwargs={"k": 3})
```

### 8.2 Weaviate — Best for Hybrid Search Out-of-the-Box

```python
"""
Weaviate: Combines vector search + BM25 keyword search natively.
GraphQL-like query interface, excellent schema management.

Killer feature: "Hybrid search" mode that combines vector + BM25 in one query
                without you having to write custom SQL.

Use when: You want hybrid search without managing PostgreSQL,
          GraphQL-style data modeling, knowledge graphs
"""

import weaviate
from langchain_weaviate import WeaviateVectorStore  # pip install langchain-weaviate

# ── Setup ─────────────────────────────────────────────────────────────────────

# Docker: docker run -p 8080:8080 semitechnologies/weaviate:latest
client = weaviate.connect_to_local(host="localhost", port=8080)

# Weaviate Cloud
# client = weaviate.connect_to_wcs(
#     cluster_url="https://your-cluster.weaviate.network",
#     auth_credentials=weaviate.auth.AuthApiKey(api_key="...")
# )

# ── Schema (Collections in Weaviate v4) ──────────────────────────────────────

from weaviate.classes.config import Configure, Property, DataType

# Create collection with HNSW + BM25 hybrid search
if not client.collections.exists("RagDocument"):
    client.collections.create(
        name="RagDocument",
        vectorizer_config=Configure.Vectorizer.none(),  # We provide our own vectors
        vector_index_config=Configure.VectorIndex.hnsw(  # HNSW index
            ef_construction=128, max_connections=64, distance_metric="cosine"
        ),
        properties=[
            Property(name="content", data_type=DataType.TEXT),
            Property(name="source", data_type=DataType.TEXT),
            Property(name="category", data_type=DataType.TEXT),
            Property(name="page_num", data_type=DataType.INT),
        ],
    )

# ── LangChain Integration ─────────────────────────────────────────────────────

from langchain_community.embeddings import HuggingFaceEmbeddings

lc_embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

weaviate_store = WeaviateVectorStore(
    client=client,
    index_name="RagDocument",
    text_key="content",
    embedding=lc_embeddings,
    attributes=["source", "category", "page_num"],
)

from langchain.schema import Document

docs = [
    Document(
        page_content="Weaviate supports hybrid vector and keyword search.",
        metadata={"source": "weaviate.pdf", "category": "vectordb", "page_num": 1},
    ),
]
weaviate_store.add_documents(docs)

# Hybrid search (vector + BM25 combined, alpha controls the blend)
results = weaviate_store.similarity_search(
    "vector keyword hybrid",
    k=3,
    # alpha=0.75  # 0=pure BM25, 1=pure vector, 0.75=mostly vector
)
for doc in results:
    print(f"  {doc.metadata['source']}: {doc.page_content[:60]}")

client.close()
```

### 8.3 Milvus — Best for Billion-Scale

```python
"""
Milvus: Cloud-native, distributed, handles billions of vectors.
Built for enterprise scale. Has a free lightweight version (Milvus Lite).

Killer feature: Distributed architecture, multiple index types (HNSW, IVF, DISKANN),
                GPU acceleration, very mature ecosystem

Use when: 100M+ vectors, enterprise scale, need GPU-accelerated search
"""

from pymilvus import MilvusClient, DataType
from langchain_milvus import Milvus  # pip install langchain-milvus

# ── Setup (Milvus Lite — no server needed for dev) ────────────────────────────

# Milvus Lite: file-based, for development
client = MilvusClient("./milvus_demo.db")

# Full server (docker-compose):
# client = MilvusClient(uri="http://localhost:19530")

# Zilliz Cloud (managed Milvus):
# client = MilvusClient(uri="https://...", token="...")

# ── Create Collection ─────────────────────────────────────────────────────────

COLLECTION_NAME = "rag_collection"

if client.has_collection(COLLECTION_NAME):
    client.drop_collection(COLLECTION_NAME)

client.create_collection(
    collection_name=COLLECTION_NAME,
    dimension=384,  # Embedding dimension
    metric_type="COSINE",  # IP, L2, or COSINE
    index_type="HNSW",  # IVF_FLAT, IVF_SQ8, IVF_PQ, HNSW, DISKANN
    index_params={"M": 16, "efConstruction": 256},
)

# ── LangChain Integration ─────────────────────────────────────────────────────

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.schema import Document

lc_embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

docs = [
    Document(
        page_content="Milvus handles billions of vectors for enterprise search.",
        metadata={"source": "milvus.pdf", "category": "vectordb"},
    ),
]

milvus_store = Milvus.from_documents(
    documents=docs,
    embedding=lc_embeddings,
    connection_args={"uri": "./milvus_demo.db"},
    collection_name=COLLECTION_NAME,
)

results = milvus_store.similarity_search("enterprise vector database", k=2)
for doc in results:
    print(f"  {doc.page_content[:60]}")
```

### 8.4 Pinecone — Best Fully-Managed Cloud Service

```python
"""
Pinecone: Fully managed, serverless vector DB. Zero infrastructure.

Killer feature: "Serverless" mode — pay per query, scales to zero.
                No index tuning required, automatic scaling.

Use when: You don't want to manage any infrastructure,
          rapid prototyping of production apps, startups

Cons: Vendor lock-in, cost at scale, data leaves your infrastructure
"""

from pinecone import Pinecone, ServerlessSpec
from langchain_pinecone import PineconeVectorStore  # pip install langchain-pinecone

import os

# ── Setup ─────────────────────────────────────────────────────────────────────

pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])

INDEX_NAME = "rag-index"

# Create index (one-time setup)
if INDEX_NAME not in pc.list_indexes().names():
    pc.create_index(
        name=INDEX_NAME,
        dimension=384,
        metric="cosine",
        spec=ServerlessSpec(
            cloud="aws",  # or "gcp", "azure"
            region="us-east-1",
        ),
    )
    # Wait for index to be ready
    import time

    while not pc.describe_index(INDEX_NAME).status["ready"]:
        time.sleep(1)

# ── LangChain Integration ─────────────────────────────────────────────────────

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.schema import Document

lc_embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

docs = [
    Document(
        page_content="Pinecone is a managed vector database service.",
        metadata={"source": "pinecone.pdf", "category": "vectordb"},
    ),
]

# PineconeVectorStore handles upsert, index management automatically
pinecone_store = PineconeVectorStore.from_documents(
    documents=docs,
    embedding=lc_embeddings,
    index_name=INDEX_NAME,
    namespace="production",  # Namespaces for multi-tenant isolation
)

retriever = pinecone_store.as_retriever(search_kwargs={"k": 3})
```

### 8.5 LanceDB — Best for Embedded/Offline Use Cases

```python
"""
LanceDB: Serverless vector DB built on the Lance columnar format.
No server needed, like FAISS but with persistence + SQL-like queries.

Killer feature: Zero-copy reads, amazing for ML pipelines.
                Native Python + Pandas + Arrow integration.
                Handles both vectors AND structured data natively.

Use when: ML pipelines, data science workflows, offline processing,
          when you want FAISS-like simplicity with persistence
"""

import lancedb
from langchain_community.vectorstores import (
    LanceDB,
)  # pip install lancedb langchain-community

import os

# ── Setup ─────────────────────────────────────────────────────────────────────

# Local persistent storage
db = lancedb.connect("./lancedb_data")

# LanceDB Cloud
# db = lancedb.connect("db://your-project", api_key="...")

# ── LangChain Integration ─────────────────────────────────────────────────────

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.schema import Document

lc_embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

docs = [
    Document(
        page_content="LanceDB is built on the Lance columnar format.",
        metadata={"source": "lancedb.pdf", "category": "vectordb"},
    ),
    Document(
        page_content="Lance format enables zero-copy data access.",
        metadata={"source": "lancedb.pdf", "category": "vectordb"},
    ),
]

# Create table (LanceDB concept, equivalent to collection)
lancedb_store = LanceDB.from_documents(
    documents=docs, embedding=lc_embeddings, connection=db, table_name="rag_table"
)

# SQL-like filtering (LanceDB supports SQL WHERE clauses)
results = lancedb_store.similarity_search(
    "columnar storage format",
    k=2,
    filter="category = 'vectordb'",  # SQL WHERE syntax
)
for doc in results:
    print(f"  {doc.page_content[:60]}")
```

---

## 9. Choosing the Right Vector DB

### 9.1 Decision Matrix

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCENARIO                          RECOMMENDED        REASON
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Prototyping / experiments          FAISS              No server, fast to setup
Learning / tutorials               FAISS / Chroma     Simple APIs
Single-developer, < 100k vectors   Chroma             Persistence out of box
Small team, < 1M vectors           Chroma / Qdrant    Simple ops, good APIs
Already use PostgreSQL             pgvector           SQL joins, ACID, familiar
Need hybrid search (text+vector)   pgvector / Weaviate SQL power / Weaviate native
Production, dedicated vector DB    Qdrant             Best OSS production DB
Enterprise, 100M+ vectors          Milvus             Distributed, GPU-ready
Zero infra management              Pinecone           Fully managed, serverless
ML pipelines, offline processing   LanceDB            Lance format, Pandas native
Multi-tenant SaaS                  Qdrant / Pinecone  Namespace/collection isolation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 9.2 Feature Comparison

```
Feature              FAISS  Chroma  pgvector  Qdrant  Weaviate  Milvus  Pinecone
────────────────────────────────────────────────────────────────────────────────
Persistence          ❌     ✅      ✅        ✅      ✅        ✅      ✅
Metadata Filter      ❌     ✅      ✅        ✅      ✅        ✅      ✅
Hybrid Search        ❌     ❌      ✅        ✅      ✅        ✅      ✅
CRUD (update/delete) ❌     ✅      ✅        ✅      ✅        ✅      ✅
Distributed          ❌     ❌      ❌        ✅      ✅        ✅      ✅
ACID Transactions    ❌     ❌      ✅        ❌      ❌        ❌      ❌
SQL Joins            ❌     ❌      ✅        ❌      ❌        ❌      ❌
GPU Acceleration     ✅     ❌      ❌        ❌      ❌        ✅      ❌
Self-Hosted          ✅     ✅      ✅        ✅      ✅        ✅      ❌
Fully Managed        ❌     ❌      ❌        ✅*     ✅*       ✅*     ✅
────────────────────────────────────────────────────────────────────────────────
* = Cloud offering available, self-host also available
```

### 9.3 The Progression Path (Your Learning Roadmap)

```
  ┌─────────────────────────────────────────────────────────────────────┐
  │                  Vector DB Learning Progression                     │
  │                                                                     │
  │  Stage 1: Prototype                                                 │
  │  ┌─────────────┐                                                    │
  │  │    FAISS    │ → Understand raw vectors, indexes, similarity      │
  │  └─────────────┘                                                    │
  │         │                                                           │
  │         ▼                                                           │
  │  Stage 2: Persistence                                               │
  │  ┌─────────────┐                                                    │
  │  │   Chroma    │ → Add persistence, metadata filtering, CRUD       │
  │  └─────────────┘                                                    │
  │         │                                                           │
  │         ▼                                                           │
  │  Stage 3: Production (choose one)                                   │
  │  ┌────────────────────────────────────────────────────┐            │
  │  │  pgvector   │  Qdrant   │  Weaviate  │  Pinecone  │            │
  │  │  (SQL+vec)  │  (OSS)    │  (hybrid)  │  (managed) │            │
  │  └────────────────────────────────────────────────────┘            │
  │         │                                                           │
  │         ▼                                                           │
  │  Stage 4: Scale (if needed)                                         │
  │  ┌─────────────┐                                                    │
  │  │   Milvus    │ → Billions of vectors, GPU acceleration            │
  │  └─────────────┘                                                    │
  └─────────────────────────────────────────────────────────────────────┘
```

### 9.4 Your Recommended Stack (Given Your RAG Journey)

```python
"""
Given your current stack:
  - HuggingFaceEmbeddings (MiniLM)
  - LangChain chains
  - Docling loader
  - Multiple chunking strategies

RECOMMENDATION:

For learning now:
  → FAISS (you already have this working ✓)
  → Chroma (add persistence, easy migration from FAISS)

For production:
  → pgvector if you're in a web app with PostgreSQL
  → Qdrant if you want a dedicated vector DB

The migration is easy — LangChain abstracts the vector store:
"""

# SWAP FAISS → CHROMA → PGVECTOR with minimal code change:

# FAISS (prototype)
from langchain_community.vectorstores import FAISS

vs = FAISS.from_documents(docs, embeddings)

# CHROMA (persistence) — same API!
from langchain_chroma import Chroma

vs = Chroma.from_documents(docs, embeddings, persist_directory="./chroma")

# PGVECTOR (production) — same API!
from langchain_postgres.vectorstores import PGVector

vs = PGVector.from_documents(docs, embeddings, connection=CONNECTION_STRING)

# QDRANT (production, dedicated DB) — same API!
from langchain_qdrant import Qdrant

vs = Qdrant.from_documents(docs, embeddings, url="http://localhost:6333")

# The retriever call is IDENTICAL for all:
retriever = vs.as_retriever(search_kwargs={"k": 4})
# → Plug into your existing RunnablePassthrough chain — nothing else changes!
```

---

## APPENDIX: Quick Reference

### Install Commands

```bash
# FAISS (prototyping)
pip install faiss-cpu langchain-community

# Chroma (persistence)  
pip install chromadb langchain-chroma

# pgvector (production, PostgreSQL)
pip install pgvector psycopg2-binary langchain-postgres sqlalchemy
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=pass pgvector/pgvector:pg16

# Qdrant (production, dedicated)
pip install qdrant-client langchain-qdrant
docker run -p 6333:6333 qdrant/qdrant

# Weaviate (hybrid search)
pip install weaviate-client langchain-weaviate
docker run -p 8080:8080 semitechnologies/weaviate:latest

# Milvus (enterprise scale)
pip install pymilvus langchain-milvus

# Pinecone (managed cloud)
pip install pinecone-client langchain-pinecone

# LanceDB (ML pipelines)
pip install lancedb langchain-community
```

### Similarity Metric Quick Reference

```python
# Cosine: for text embeddings (angle between vectors)
# Use when: semantic search, sentence transformers
score_cosine = np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))  # 1.0 = identical

# Euclidean (L2): for image embeddings (distance in space)
# Use when: image search, when magnitude matters
score_l2 = np.linalg.norm(a - b)  # 0.0 = identical

# Dot Product: for normalized vectors (fastest)
# Use when: vectors are pre-normalized, OpenAI embeddings
score_dot = np.dot(a, b)  # Higher = more similar
```

### Index Selection Quick Reference

```
Vectors     Accuracy Priority    Speed Priority    Choose
────────────────────────────────────────────────────────
< 100k      Max                  Don't care        IndexFlatL2 / Flat
< 1M        High                 Medium            HNSW (m=16, ef=64)
1M - 100M   Medium               High              IVF_HNSW
100M+       Medium               Max               IVF_PQ or DISKANN
```

---

*Next in your learning path: Advanced RAG techniques — 
Reranking (Cohere, BGE), Query Rewriting, Hypothetical Document Embeddings (HyDE),
Multi-vector retrieval, RAG evaluation (RAGAS)*
