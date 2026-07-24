If you want to understand **production-grade RAG retrieval systems**, then IVF, HNSW, PQ, LSH, DiskANN, and ScaNN are all part of a larger field called:

> **Approximate Nearest Neighbor Search (ANN)**

ANN is the technology that allows vector databases to search through millions or billions of embeddings quickly.

---

# Part 1: Why We Need ANN

Suppose you have:

```text
10 million documents
1536-dimensional embeddings
```

A user asks:

```text
"What are the symptoms of diabetes?"
```

You generate a query embedding:

```python
query_embedding = [0.12, 0.44, ...]
```

Now you need to find:

```text
Top 10 closest vectors
```

Naive approach:

```python
for every vector:
    compute cosine similarity
```

Complexity:

```text
10 million comparisons
```

Too slow.

This is called:

```text
Brute Force Search
Exact Search
Flat Index
```

Most vector databases therefore use:

```text
Approximate Nearest Neighbor (ANN)
```

which trades:

```text
99.9% accuracy
for
100x-1000x speed
```

---

# Evolution Timeline

| Year  | Algorithm            | Why                         |
| ----- | -------------------- | --------------------------- |
| 1998  | KD Tree              | First fast nearest neighbor |
| 1999  | LSH                  | High-dimensional search     |
| 2003  | Hierarchical K-Means | IVF precursor               |
| 2011  | Product Quantization | Memory reduction            |
| 2016  | HNSW                 | Graph search revolution     |
| 2019  | DiskANN              | Billion-scale on SSD        |
| 2020  | ScaNN                | Google's optimized ANN      |
| 2023+ | Hybrid ANN Systems   | Combination approaches      |

---

# 1. LSH (Locality Sensitive Hashing)

## Invented

1999

By:

```text
Piotr Indyk
Rajeev Motwani
```

---

## Problem

Before LSH:

```text
KD Trees worked only for low dimensions.
```

Example:

```text
2D
5D
10D
```

But embeddings are:

```text
768D
1024D
1536D
3072D
```

KD Trees fail.

This is called:

```text
Curse of Dimensionality
```

---

## Idea

Hash similar vectors into same bucket.

Example:

```text
A = [1,2]
B = [1.1,2.1]
C = [50,50]
```

LSH creates random hyperplanes.

```text
A -> bucket 10101
B -> bucket 10101

C -> bucket 00011
```

When querying:

```text
Search only bucket 10101
```

instead of all vectors.

---

## Advantages

Fast.

---

## Disadvantages

Poor recall.

Memory heavy.

Rarely used in modern RAG.

---

## Current Usage

Mostly:

```text
Deduplication
Similarity detection
Near duplicate search
```

Not common in modern vector DBs.

---

# 2. IVF (Inverted File Index)

## Invented

Early 2000s

Popularized by:

```text
Sivic & Zisserman (2003)
```

Later used in:

```text
FAISS
```

---

## Problem

Searching every vector is expensive.

---

## Idea

Cluster vectors.

Example:

```text
10 million vectors
```

Create:

```text
1000 clusters
```

using K-Means.

---

Instead of:

```text
Search 10 million
```

Do:

```text
Find nearest cluster
Search only cluster
```

Example:

```text
Cluster 421
contains 10,000 vectors
```

Search:

```text
10,000
instead of
10 million
```

Huge speedup.

---

## Why called Inverted File?

Borrowed from search engines.

Search engines:

```text
Word -> Documents
```

IVF:

```text
Cluster -> Vectors
```

---

## IVF Search

### Index Build

```text
1. Run K-Means
2. Create centroids
3. Assign vectors
```

---

### Query

```text
1. Find nearest centroid
2. Search inside cluster
```

---

Example:

```text
nlist = 1000
```

means:

```text
1000 clusters
```

---

```text
nprobe = 10
```

means:

```text
search 10 closest clusters
```

---

Tradeoff:

```text
Higher nprobe
=
better recall
=
slower
```

---

# 3. PQ (Product Quantization)

## Invented

2011

Paper:

```text
Product Quantization for Nearest Neighbor Search
```

By:

```text
Hervé Jégou
```

---

## Problem

Embeddings consume huge memory.

Example:

```text
1 billion vectors
1536 dimensions
float32
```

Memory:

```text
~6 TB
```

Impossible for RAM.

---

## Idea

Compress vectors.

---

Example

Vector:

```text
[1.2, 3.4, 5.6, 7.8]
```

Split into chunks:

```text
[1.2,3.4]
[5.6,7.8]
```

---

For each chunk create codebook.

Instead of storing:

```text
float values
```

Store:

```text
code ids
```

Example:

```text
[12,44]
```

---

Memory drops dramatically.

Often:

```text
16x
32x
64x
compression
```

---

## Used With IVF

Very common:

```text
IVF + PQ
```

FAISS:

```text
IndexIVFPQ
```

---

Meaning:

```text
1. Cluster vectors
2. Compress vectors
```

---

# 4. HNSW (Hierarchical Navigable Small World)

## Invented

2016

Paper:

```text
Efficient and Robust Approximate Nearest Neighbor Search
Using Hierarchical Navigable Small World Graphs
```

Author:

```text
Yury Malkov
```

---

This changed the ANN world.

Most vector databases today use HNSW.

---

## Idea

Create a graph.

Each vector connects to nearest neighbors.

Example:

```text
A <-> B
A <-> C
B <-> D
```

---

Search becomes:

```text
Graph Traversal
```

instead of:

```text
Scanning vectors
```

---

# Hierarchical Layers

Think of Google Maps.

Top layer:

```text
Countries
```

Middle:

```text
Cities
```

Bottom:

```text
Streets
```

---

HNSW uses multiple graph layers.

Top:

```text
Few nodes
```

Bottom:

```text
All vectors
```

---

Search:

```text
Start top
Jump down
Refine
```

---

Result:

```text
Very fast
Very accurate
```

---

## Parameters

### M

Connections per node.

Example:

```text
M=16
```

---

Higher:

```text
More RAM
Better recall
```

---

### efConstruction

Build quality.

---

### efSearch

Query quality.

---

Higher:

```text
Better recall
Slower
```

---

## Why HNSW Dominates

Recall often:

```text
99%+
```

while remaining extremely fast.

---

Used by:

```text
Pinecone
Qdrant
Weaviate
Milvus
OpenSearch
Elasticsearch
```

---

# 5. DiskANN

## Invented

2019

Microsoft Research

Paper:

```text
DiskANN
```

---

## Problem

HNSW is RAM hungry.

Example:

```text
1 billion vectors
```

May require:

```text
100s of GB RAM
```

or TBs.

---

## Idea

Store graph mostly on SSD.

Keep only important nodes in RAM.

---

Query flow:

```text
RAM → SSD → RAM → SSD
```

carefully optimized.

---

Result:

```text
Billion-scale search
Low RAM
High recall
```

---

## Why Important

Cloud costs.

Example:

```text
HNSW:
500 GB RAM
```

vs

```text
DiskANN:
64 GB RAM
```

Huge savings.

---

Used in:

```text
Microsoft Azure
```

and several modern vector systems.

---

# 6. ScaNN

## Invented

2020

Google Research

Paper:

```text
ScaNN:
Scalable Nearest Neighbor Search
```

---

## Problem

Need better TPU/CPU efficiency.

---

## Idea

Combines:

```text
Partitioning
+
Quantization
+
Re-ranking
```

---

Pipeline:

```text
1. Partition vectors
2. Candidate retrieval
3. Quantized scoring
4. Exact reranking
```

---

Think:

```text
IVF
+
PQ
+
Extra optimization
```

---

## Strength

Excellent for:

```text
TensorFlow
Vertex AI
Google systems
```

---

# Modern Production Vector Databases

Most use one of:

| Engine          | Main Algorithm     |
| --------------- | ------------------ |
| FAISS           | IVF, PQ, HNSW      |
| Pinecone        | HNSW variants      |
| Weaviate        | HNSW               |
| Qdrant          | HNSW               |
| Milvus          | HNSW, IVF, DiskANN |
| Elasticsearch   | HNSW               |
| OpenSearch      | HNSW               |
| Azure AI Search | HNSW, DiskANN      |
| Vertex AI       | ScaNN              |

---

# The Most Important Combinations

## Small Dataset

```text
< 100k vectors
```

Use:

```text
Flat Search
```

---

## Medium Dataset

```text
100k – 10M
```

Use:

```text
HNSW
```

---

## Huge Dataset

```text
10M – 1B
```

Use:

```text
IVF + PQ
```

or

```text
DiskANN
```

---

## Massive Dataset

```text
1B+
```

Use:

```text
DiskANN
```

or specialized distributed systems.

---

# Additional Algorithms You Should Know

These are often missed by beginners but appear in production:

### Flat Index

Exact search.

No approximation.

Used for evaluation.

---

### KD Tree

Ancestor of ANN systems.

Good for low dimensions.

---

### Ball Tree

Alternative to KD Tree.

---

### Annoy (Spotify)

2013

Forest of random projection trees.

Good for read-heavy workloads.

---

### NSG

Navigating Spreading-out Graph.

Predecessor/competitor to HNSW.

---

### Vamana

2022

Graph algorithm behind modern DiskANN improvements.

---

### IVF-Flat

Clustered but no compression.

---

### IVF-PQ

Clustered + compressed.

---

### OPQ (Optimized Product Quantization)

Improved PQ.

Rotates vectors before compression.

Often better recall.

---

# What Production RAG Engineers Usually Use in 2026

If you build a RAG system today, you'll most commonly encounter:

```text
1. HNSW
2. IVF
3. PQ
4. Hybrid Search (BM25 + Vectors)
5. Rerankers
6. Metadata Filtering
7. Query Expansion
8. Multi-vector Retrieval
9. Cross Encoder Reranking
10. DiskANN (very large deployments)
```

A practical learning order is:

```text
1. Cosine Similarity
2. Embeddings
3. Flat Search
4. ANN basics
5. IVF
6. PQ
7. HNSW
8. Hybrid Search
9. Reranking
10. Vector Databases
11. Distributed Retrieval
12. DiskANN / ScaNN
```

Once you deeply understand **Flat → IVF → PQ → HNSW → Hybrid Search → Reranking**, you'll understand about 90% of the retrieval infrastructure used in real-world production RAG systems.
