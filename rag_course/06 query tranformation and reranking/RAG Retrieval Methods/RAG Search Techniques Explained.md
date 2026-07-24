This is one of the most important topics in modern RAG.

If you understand:

* Dense Search
* Sparse Search
* BM25
* TF-IDF
* Hybrid Search
* Ensemble Retrievers
* RRF (Reciprocal Rank Fusion)

you'll understand how most production RAG systems retrieve documents.

---

# First: Why Retrieval Exists

Suppose your company has:

* 1 million PDFs
* 50 million chat messages
* 100,000 support tickets

A user asks:

> "How do I reset MFA for a suspended account?"

The LLM cannot read all documents.

Instead:

```text
User Question
      ↓
Retriever
      ↓
Top Relevant Documents
      ↓
LLM
      ↓
Answer
```

The retriever's job:

```text
Find the best documents
```

before the LLM sees anything.

---

# The Evolution of Search

Search technology evolved like this:

```text
TF-IDF
   ↓
BM25
   ↓
Dense Search (Embeddings)
   ↓
Hybrid Search
   ↓
Reranking
```

Most production RAG today uses:

```text
Hybrid Search
+
Reranker
```

because no single method is perfect.

---

# Part 1 — Sparse Search

Sparse search is the traditional search approach.

Example:

Document:

```text
Cats are wonderful pets.
```

Question:

```text
pets
```

Retriever checks:

```text
Does document contain word "pets"?
```

Yes.

Good score.

---

Question:

```text
animals
```

Document:

```text
Cats are wonderful pets.
```

Word "animals" doesn't exist.

Sparse search fails.

Even though:

```text
pet ≈ animal
```

The computer doesn't understand meaning.

It only understands words.

---

# Why It's Called Sparse

Vocabulary might contain:

```text
100,000 words
```

Document vector:

```text
[0,0,0,1,0,0,0,0,1,0,0...]
```

Most values are zero.

Hence:

```text
Sparse Vector
```

---

# Sparse Search Methods

Most common:

### TF-IDF

and

### BM25

---

# Part 2 — TF-IDF

TF-IDF means:

```text
Term Frequency
Inverse Document Frequency
```

---

## TF (Term Frequency)

How often a word appears.

Document:

```text
dog dog dog cat
```

Frequency:

```text
dog = 3
cat = 1
```

TF says:

```text
dog is important
```

because it appears often.

---

## Problem

Word:

```text
the
```

appears frequently everywhere.

TF alone gives it huge importance.

Bad.

---

## IDF

Inverse Document Frequency.

IDF asks:

```text
How rare is this word
across all documents?
```

Example:

Collection:

```text
Doc1: dog
Doc2: dog
Doc3: dog
Doc4: dog
```

Word:

```text
dog
```

appears everywhere.

Low IDF.

---

Collection:

```text
Doc1: quantum
Doc2: dog
Doc3: cat
Doc4: pet
```

Word:

```text
quantum
```

appears once.

High IDF.

---

Thus:

```text
Rare words
=
More informative
```

---

# TF-IDF Formula

Simplified:

```text
Score =
TF × IDF
```

High frequency

AND

Rare globally

↓

High score.

---

# Example

Query:

```text
quantum computing
```

Document A:

```text
quantum quantum quantum
```

Document B:

```text
dog cat pet
```

TF-IDF strongly favors:

```text
Document A
```

---

# Problems With TF-IDF

It doesn't understand meaning.

Example:

Query:

```text
car
```

Document:

```text
automobile
```

TF-IDF:

```text
No match
```

Even though they mean almost the same thing.

---

# Part 3 — BM25

BM25 is basically:

```text
TF-IDF 2.0
```

and is still one of the strongest search algorithms ever created.

Many search engines still use BM25.

---

BM25 improves:

### 1. Term Frequency Saturation

TF-IDF:

```text
car = 10 times
```

gets 10x more score.

But:

```text
car = 100 times
```

is not necessarily 10x more relevant.

BM25 caps the benefit.

---

Example:

Document:

```text
car car car car car
```

After a point:

```text
More cars
≠
More relevance
```

BM25 understands this.

---

### 2. Document Length Normalization

Document A:

```text
100 words
```

Document B:

```text
10,000 words
```

Long document naturally contains more keywords.

BM25 compensates for this.

---

Result:

```text
More accurate ranking
```

than TF-IDF.

---

# Production Reality

Many companies still use:

```text
BM25
```

because it is:

* Fast
* Cheap
* Explainable
* Excellent for exact keyword matches

---

# Part 4 — Dense Search

This changed everything.

Instead of matching words:

```text
Match meaning
```

---

Example

Query:

```text
How do I fix my vehicle?
```

Document:

```text
Car repair guide
```

No shared words.

BM25 struggles.

Dense search succeeds.

---

# Embeddings

An embedding model converts text into numbers.

Example:

```text
Car
```

↓

```text
[0.22, -0.91, 0.45, ...]
```

---

```text
Automobile
```

↓

```text
[0.21, -0.88, 0.47, ...]
```

Very similar vectors.

---

The embedding model learned:

```text
car ≈ automobile
```

---

# Dense Retrieval Flow

Documents:

```text
Doc1
Doc2
Doc3
...
```

Convert all docs:

```text
Document
    ↓
Embedding Model
    ↓
Vector
```

Store in vector database.

---

Question arrives:

```text
Question
   ↓
Embedding
   ↓
Vector Search
```

Find closest vectors.

---

Common similarity metrics:

### Cosine Similarity

Most popular.

```text
1.0 = identical
0.0 = unrelated
```

---

# Dense Search Advantages

Understands:

```text
car = automobile

doctor = physician

error = failure

login = sign in
```

without exact words.

Huge improvement.

---

# Dense Search Problems

It can miss exact keywords.

Example:

Query:

```text
Error code 0x80070005
```

Document contains:

```text
0x80070005
```

Dense search may ignore it.

BM25 finds it instantly.

---

This is why dense search alone is often insufficient.

---

# Part 5 — Hybrid Search

Hybrid Search combines:

```text
BM25
+
Dense Search
```

---

Example

Query:

```text
Error code 0x80070005
```

BM25:

```text
Excellent
```

because exact code exists.

Dense:

```text
Maybe
```

---

Query:

```text
How do I sign in?
```

Document:

```text
Login instructions
```

BM25:

```text
Weak
```

Dense:

```text
Strong
```

---

Together:

```text
Best of both worlds
```

---

Production systems today frequently use:

```text
Dense Search
+
BM25
+
Reranker
```

---

# Part 6 — Ensemble Retriever

An Ensemble Retriever combines multiple retrievers.

Example:

```text
BM25 Retriever
Dense Retriever
Knowledge Graph Retriever
```

Each returns results.

---

BM25:

```text
Doc1
Doc2
Doc5
```

Dense:

```text
Doc3
Doc1
Doc4
```

Now combine them.

This combination is:

```text
Ensemble Retrieval
```

---

LangChain example:

```python
ensemble = EnsembleRetriever(retrievers=[bm25, vector], weights=[0.4, 0.6])
```

---

Conceptually:

```text
Final Score
=
0.4 × BM25
+
0.6 × Dense
```

(implementation may vary)

---

# Part 7 — RRF

RRF means:

```text
Reciprocal Rank Fusion
```

A very popular ranking fusion algorithm.

---

Problem:

BM25 score:

```text
13.4
```

Dense score:

```text
0.88
```

Different scales.

Cannot combine directly.

---

Instead use rankings.

BM25:

```text
Rank1 DocA
Rank2 DocB
Rank3 DocC
```

Dense:

```text
Rank1 DocB
Rank2 DocA
Rank3 DocD
```

---

RRF Formula

```text
Score =
1/(k+rank)
```

where k is often:

```text
60
```

---

Example

DocA:

```text
BM25 rank = 1
Dense rank = 2
```

Score:

```text
1/(60+1)
+
1/(60+2)
```

---

DocB:

```text
BM25 rank = 2
Dense rank = 1
```

Score:

```text
1/(60+2)
+
1/(60+1)
```

Same score.

---

Why RRF Works

Because it rewards:

```text
Documents appearing
in multiple rankings
```

Those are often genuinely relevant.

---

# Production Retrieval Pipeline

A modern enterprise RAG often looks like:

```text
User Question
       ↓
Query Rewriting
       ↓
Hybrid Search
   (BM25 + Dense)
       ↓
RRF Fusion
       ↓
Top 100 Docs
       ↓
Cross Encoder Reranker
       ↓
Top 10 Docs
       ↓
Context Compression
       ↓
LLM
       ↓
Answer
```

---

# Example: Microsoft Documentation RAG

Question:

```text
How do I reset MFA for a disabled account?
```

BM25 finds:

```text
MFA
disabled account
reset
```

documents.

Dense finds:

```text
multi-factor authentication
locked users
authentication recovery
```

documents.

RRF combines.

Reranker reads:

```text
Question + Document
```

and picks the truly relevant ones.

LLM answers.

---

# What You Should Learn Next

For production-grade RAG, I would learn in this order:

1. Chunking
2. Embeddings
3. Vector Databases
4. TF-IDF
5. BM25
6. Dense Retrieval
7. Hybrid Search
8. Ensemble Retrieval
9. RRF
10. Cross-Encoder Rerankers
11. Query Expansion
12. Multi-Query Retrieval
13. Parent-Child Retrieval
14. Context Compression
15. Agentic RAG
16. Evaluation (Recall@K, MRR, nDCG)
17. Embedding Caching
18. Production RAG Architecture

A useful mental model is:

```text
BM25
   = keyword understanding

Dense Search
   = semantic understanding

Hybrid Search
   = both

RRF
   = combines rankings

Reranker
   = final judge
```

If you're aiming for production RAG engineering, the next topic after this should be **how vector databases actually perform similarity search internally (FAISS, HNSW, IVF, ANN, KNN, cosine similarity, indexing)** because that's the layer directly underneath dense retrieval.
