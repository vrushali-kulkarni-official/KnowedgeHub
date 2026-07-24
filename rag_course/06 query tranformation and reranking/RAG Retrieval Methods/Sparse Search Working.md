**BM25 (Sparse Search)** is still one of the strongest retrieval methods even in 2026. Almost every enterprise-grade RAG system combines:

> Dense Search + Sparse Search + Fusion + Reranker

Let's go step by step.

---

# Part 1 — What is Sparse Search?

Sparse search is the traditional keyword search.

Instead of understanding meaning, it looks for **important words**.

Example

Query

> "How do I reset my password?"

Document A

> To reset your password click Forgot Password.

Document B

> User authentication uses OAuth2.

A sparse search engine immediately sees

```
reset
password
forgot
```

and returns Document A.

---

Dense search instead converts everything into embeddings.

```
Query
↓
Embedding
↓

0.21
-0.53
0.98
...
```

Sparse search never creates embeddings.

It stores words.

---

# Part 2 — Why is it called Sparse?

Imagine every unique word is a dimension.

Vocabulary

```
apple
banana
computer
car
python
password
reset
...
```

Suppose there are

```
10 million words
```

Every document becomes

```
[0,0,1,0,0,0,3,0,0,1...]
```

Almost every value is zero.

Hence

**Sparse Vector**

```
0
0
0
0
5
0
0
0
1
0
...
```

Only a few words exist.

---

Dense embeddings

```
0.34
-0.55
0.11
0.91
...
```

Every value exists.

Hence

Dense Vector.

---

# Part 3 — What does BM25 actually store?

Suppose our chunk is

```
The customer can reset the password using the Forgot Password link.
```

Tokenizer produces

```
the
customer
can
reset
the
password
using
forgot
password
link
```

Stop words removed

```
customer
reset
password
forgot
password
link
```

Stemmer may convert

```
reset
resetting
resets

↓

reset
```

Now BM25 stores something like

| Word     | Frequency |
| -------- | --------- |
| customer | 1         |
| reset    | 1         |
| password | 2         |
| forgot   | 1         |
| link     | 1         |

No embeddings.

Only words.

---

# Part 4 — Index Creation

Imagine 3 chunks.

Chunk 1

```
Reset your password.
```

Chunk 2

```
Install Python.
```

Chunk 3

```
Reset account PIN.
```

The search engine builds an **Inverted Index**.

Instead of

```
Document
↓

Words
```

It stores

```
Word
↓

Documents
```

Like this

```
password

↓

Doc1
```

```
python

↓

Doc2
```

```
reset

↓

Doc1
Doc3
```

This is called an

**Inverted Index**

Every search engine uses this.

ElasticSearch

OpenSearch

Lucene

Solr

etc.

---

# Part 5 — Input to BM25

This is the most commonly misunderstood part.

Suppose user asks

```
How do I reset my password?
```

Input is

**Only plain text**

```
"How do I reset my password?"
```

NOT

Embedding

NOT Vector

NOT Chunk ID

Only raw text.

---

BM25 tokenizes it

```
reset
password
```

Then searches inverted index.

---

# Part 6 — How BM25 Scores

BM25 computes a score.

Simplified

```
Score =
TF
×
IDF
×
Length Normalization
```

Let's understand every part.

---

## 1. TF (Term Frequency)

Suppose document

```
password password password reset
```

Password appears

```
3 times
```

Higher TF

↓

Higher score.

---

## 2. IDF (Inverse Document Frequency)

Very common words

```
the

is

and
```

appear everywhere.

They are useless.

Rare words

```
OAuth

Kubernetes

Redis

JWT
```

are much more informative.

IDF gives higher importance to rare words.

Formula

```
IDF

=

log(
N / df
)
```

Where

```
N

=

Number of documents
```

```
df

=

Number of documents containing the word
```

Example

```
password

appears

10,000 docs
```

Low IDF.

---

```
OAuth2

appears

50 docs
```

Huge IDF.

---

# 3. Length Normalization

Imagine

Doc A

```
20 words
```

Doc B

```
5000 words
```

Without normalization

Doc B always wins.

BM25 penalizes huge documents.

---

# BM25 Formula

Real formula

[
\text{Score}(D,Q)
=================

\sum IDF(q_i)
\cdot
\frac{
TF(q_i)(k_1+1)
}{
TF(q_i)+k_1
\left(
1-b+b\frac{|D|}{avgDL}
\right)
}
]

Looks scary.

In practice it simply means

Higher TF

Higher IDF

Smaller documents

↓

Higher score.

---

# Part 7 — Example Calculation

Query

```
reset password
```

Doc A

```
reset password password
```

Doc B

```
reset account settings
```

Scores

Doc A

```
TF(password)=2

TF(reset)=1

↓

Higher
```

Doc B

```
password missing

↓

Lower
```

BM25 ranks

```
Doc A
Doc B
```

---

# Part 8 — Why BM25 is still amazing

Suppose user searches

```
HTTP 502 Gateway Timeout
```

Dense embeddings may think

```
Server error
```

BM25 matches

```
HTTP

502

Gateway

Timeout
```

exactly.

Therefore

Error codes

Product IDs

Invoice numbers

API names

Function names

Variable names

Legal document numbers

Medical codes

are much better with BM25.

---

# Part 9 — Production RAG Pipeline

Typical enterprise pipeline

```
User Query
      │
      ▼
Dense Embedding
      │
      ▼
Vector Search
      │
      ▼
Top 100
```

Parallel

```
User Query
      │
      ▼
BM25
      │
      ▼
Top 100
```

Then

```
RRF
```

Then

```
MMR
```

Then

```
Cross Encoder
```

Then

```
Top 10
```

LLM.

This architecture is now the de facto standard.

---

# Part 10 — What are the inputs at each stage?

| Stage           | Input              | Output                  |
| --------------- | ------------------ | ----------------------- |
| Chunking        | Raw documents      | Chunks                  |
| Dense Embedding | Chunk text         | Dense vectors           |
| Sparse Index    | Chunk text         | Inverted index (BM25)   |
| User Query      | Plain text         | Query text              |
| Dense Search    | Query embedding    | Top-K dense chunks      |
| Sparse Search   | Query text         | Top-K BM25 chunks       |
| RRF             | Two ranked lists   | Combined ranking        |
| MMR             | Ranked list        | Diversified ranked list |
| Reranker        | Query + chunk text | Final ranking           |

Notice that **the sparse side never uses embeddings**; it only needs the raw query text.

---

# Part 11 — ElasticSearch vs OpenSearch vs Qdrant Sparse Search

This is where enterprise architecture decisions matter.

## Option 1 — ElasticSearch (Most Mature)

Pros:

* Best-in-class BM25 implementation (built on Apache Lucene)
* Extremely fast inverted indexes
* Rich query language, filters, aggregations, synonyms, analyzers
* Mature scaling, monitoring, and security
* Hybrid search support with dense vectors

Cons:

* More operational complexity
* Commercial licensing considerations for some advanced features

Typical users: large enterprises, finance, healthcare, e-commerce.

---

## Option 2 — OpenSearch

Pros:

* Open-source fork of Elasticsearch
* Lucene-based BM25
* Similar APIs and performance characteristics
* Good hybrid search support

Cons:

* Ecosystem and documentation are somewhat smaller than Elasticsearch

Typical users: organizations preferring a fully open-source stack or using AWS OpenSearch Service.

---

## Option 3 — Qdrant Sparse Search

Qdrant started as a vector database but now supports sparse vectors and hybrid retrieval.

Pros:

* One system for dense and sparse retrieval
* Simpler architecture (no separate search engine)
* Excellent vector search performance
* Built-in hybrid search and fusion capabilities

Cons:

* Sparse search features are newer and not as feature-rich as Lucene-based engines
* Fewer advanced text-analysis capabilities (complex analyzers, linguistic processing, etc.) compared with Elasticsearch/OpenSearch

Typical users: AI-native applications where vector search is the primary workload.

---

# What do large production RAG systems use?

There isn't a single answer, but common patterns are:

| Organization Type                 | Common Choice                               |
| --------------------------------- | ------------------------------------------- |
| Traditional enterprise search     | Elasticsearch + vector search               |
| AWS-centric enterprise            | OpenSearch                                  |
| AI-native startup                 | Qdrant, Weaviate, or Milvus                 |
| Existing Elasticsearch deployment | Elasticsearch hybrid search                 |
| New greenfield AI platform        | Qdrant hybrid search is increasingly common |

Many mature enterprises already have Elasticsearch or OpenSearch for search workloads, so extending them for hybrid RAG is often the lowest-risk path. AI-first companies that primarily need semantic retrieval frequently choose a vector database like Qdrant and use its hybrid capabilities to keep the architecture simpler.

---

# A practical recommendation for a production RAG architecture

For a new enterprise RAG system with millions of chunks:

```
Documents
      │
      ▼
Chunking
      │
      ├──────────────► BM25 Index
      │                    │
      ▼                    ▼
Embedding Model      Elasticsearch/OpenSearch
      │                    │
      ▼                    │
Qdrant Dense Index ◄────────┘ (or use a single hybrid engine if appropriate)

               User Query
                    │
      ┌─────────────┴─────────────┐
      ▼                           ▼
Dense Search                 Sparse (BM25)
      │                           │
      └─────────────┬─────────────┘
                    ▼
              Reciprocal Rank Fusion (RRF)
                    ▼
               Maximal Marginal Relevance (MMR)
                    ▼
              Cross-Encoder Reranker
                    ▼
                Final Top-N Chunks
                    ▼
                     LLM
```

For organizations that value operational simplicity over maximum text-search flexibility, a single hybrid-capable engine such as Qdrant can be an excellent choice. For organizations with sophisticated keyword search requirements (complex analyzers, multilingual stemming, synonym management, advanced filtering), Elasticsearch or OpenSearch remain the strongest options.
