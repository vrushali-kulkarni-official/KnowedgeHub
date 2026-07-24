`LLMChainExtractor` is one of the most useful but often misunderstood components in LangChain retrieval pipelines.

Most developers think retrieval is:

```
User Query
    ↓
Retriever
    ↓
Top K Documents
    ↓
LLM
```

But in production, retrieved documents often contain a lot of irrelevant text.

Example:

Query:

> What is the refund policy for damaged products?

Retrieved chunk:

```text
Returns Policy

Our company was founded in 2015.
We operate in 20 countries.
Customer satisfaction is important.

If a product arrives damaged, customers may request a refund within 30 days.

We also offer gift wrapping.
Shipping costs vary by region.
```

Only one sentence is relevant.

Sending the whole chunk:

* wastes tokens
* increases latency
* increases cost
* increases hallucination risk

This is where `LLMChainExtractor` comes in.

---

# What is LLMChainExtractor?

It is a document compression component.

Instead of sending entire retrieved documents to the final QA chain, it asks an LLM:

> Extract only the parts of this document relevant to the query.

So:

```text
Large Retrieved Document
          ↓
LLMChainExtractor
          ↓
Relevant Snippet
          ↓
Final LLM
```

---

# Why it exists

Suppose your chunk size is:

```python
chunk_size = 1000
```

Retriever returns:

```python
k = 5
```

Total context:

```text
5000+ tokens
```

But maybe only:

```text
200 tokens
```

are actually relevant.

LLMChainExtractor removes the useless text.

---

# Internal Idea

Imagine:

```python
query = "How long is the refund period?"
```

Retrieved document:

```text
Section 1: Company Overview

Our company was founded in 2015.

Section 2: Refund Policy

Customers may return damaged items
within 30 days for a full refund.

Section 3: Shipping

Shipping takes 5-7 days.
```

LLMChainExtractor sends something like:

```text
Query:
How long is the refund period?

Document:
[entire document]

Extract only information relevant to answering the query.
```

LLM responds:

```text
Customers may return damaged items
within 30 days for a full refund.
```

Compressed document becomes:

```text
Customers may return damaged items
within 30 days for a full refund.
```

---

# Architecture

Without compression:

```text
Question
   ↓
Retriever
   ↓
Doc1
Doc2
Doc3
   ↓
Final LLM
```

With compression:

```text
Question
   ↓
Retriever
   ↓
Doc1
Doc2
Doc3
   ↓
LLMChainExtractor
   ↓
Compressed Doc1
Compressed Doc2
Compressed Doc3
   ↓
Final LLM
```

---

# Basic Example

```python
from langchain.retrievers.document_compressors import LLMChainExtractor
from langchain_openai import ChatOpenAI

llm = ChatOpenAI()

compressor = LLMChainExtractor.from_llm(llm)
```

Creates an extractor that uses an LLM to compress documents.

---

# Example Input

Document:

```text
Apple Inc.

Apple designs consumer electronics.

The iPhone 15 was released in September 2023.

Apple also sells MacBooks and iPads.
```

Question:

```text
When was iPhone 15 released?
```

Extractor output:

```text
The iPhone 15 was released in September 2023.
```

---

# How Compression Actually Works

Internally:

For every retrieved document:

```python
for doc in docs:
    compressed_doc = llm.extract(query, doc)
```

Conceptually:

```python
compressed_docs = []

for doc in retrieved_docs:
    result = extractor(doc, query)

    compressed_docs.append(result)
```

---

# Example with Multiple Documents

Question:

```text
What is Amazon Bedrock?
```

Retrieved docs:

### Doc1

```text
Amazon was founded by Jeff Bezos in 1994.
Amazon Bedrock provides access to foundation models.
AWS has data centers worldwide.
```

### Doc2

```text
Bedrock supports Claude, Llama, Titan,
and many other models.
```

### Doc3

```text
AWS revenue grew significantly in 2024.
```

Compressed output:

### Compressed Doc1

```text
Amazon Bedrock provides access to foundation models.
```

### Compressed Doc2

```text
Bedrock supports Claude, Llama, Titan,
and many other models.
```

### Compressed Doc3

```text
(empty)
```

---

# Where It Is Usually Used

Typically with:

```python
ContextualCompressionRetriever
```

This is the most common production setup.

```python
Retriever
      ↓
Top K Docs
      ↓
LLMChainExtractor
      ↓
Compressed Docs
      ↓
Return
```

Example:

```python
from langchain.retrievers import ContextualCompressionRetriever

compression_retriever = ContextualCompressionRetriever(
    base_compressor=compressor, base_retriever=retriever
)
```

Now:

```python
compression_retriever.invoke(query)
```

will:

### Step 1

Retrieve documents.

```python
docs = retriever.invoke(query)
```

### Step 2

Compress them.

```python
compressed_docs = compressor.compress_documents(docs, query)
```

### Step 3

Return compressed docs.

---

# Real Production Example

Imagine:

Customer Support RAG.

Knowledge base:

```text
1000 page handbook
```

Retriever finds:

```text
10 chunks
```

Each chunk:

```text
1000 tokens
```

Total:

```text
10000 tokens
```

Final LLM context window gets crowded.

With LLMChainExtractor:

```text
10000 tokens
        ↓
Relevant sentences only
        ↓
1200 tokens
```

Huge reduction.

---

# What Happens Internally

Let's look deeper.

Suppose:

```python
docs = [doc1, doc2, doc3]
query = "What is ACID consistency?"
```

Internally:

```python
compress_documents(docs, query)
```

Loops through documents:

```python
for doc in docs:
```

Build prompt:

```text
Question:
What is ACID consistency?

Document:
[document text]

Extract only relevant portions.
```

Call LLM.

Receive:

```text
Relevant extracted text
```

Create new document:

```python
Document(page_content=extracted_text, metadata=original_metadata)
```

Return list.

---

# Difference Between Filtering and Extraction

Many people confuse these.

## Filtering

Keeps or removes entire documents.

```text
Doc1 → Keep
Doc2 → Remove
Doc3 → Keep
```

No modification.

---

## Extraction

Keeps only relevant text inside document.

```text
Original:

Line A
Line B
Line C
Line D

Question needs only Line C

Output:

Line C
```

This is what LLMChainExtractor does.

---

# LLMChainExtractor vs Embeddings

Embeddings answer:

```text
Which documents are relevant?
```

LLMChainExtractor answers:

```text
Which parts of the document are relevant?
```

Together:

```text
Embedding Retriever
        ↓
Relevant Docs
        ↓
LLMChainExtractor
        ↓
Relevant Passages
```

Very powerful combination.

---

# LLMChainExtractor vs LLMChainFilter

These are commonly confused.

## LLMChainFilter

Output:

```text
Keep Doc?
Yes / No
```

Example:

```text
Doc1 → Keep
Doc2 → Remove
Doc3 → Keep
```

Document unchanged.

---

## LLMChainExtractor

Output:

```text
Extract relevant text
```

Example:

Original:

```text
Apple sells iPhones.
Apple sells MacBooks.
Apple sells Watches.
```

Question:

```text
What products does Apple sell?
```

Output:

```text
Apple sells iPhones.
Apple sells MacBooks.
Apple sells Watches.
```

Question:

```text
Does Apple sell watches?
```

Output:

```text
Apple sells Watches.
```

---

# Production Tradeoffs

## Benefits

### Smaller Context

```text
Less tokens
```

### Lower Cost

```text
Less input tokens
```

### Better Accuracy

Less irrelevant information.

### Better Long-Document Handling

Useful for:

* PDFs
* Contracts
* Manuals
* Knowledge bases

---

## Drawbacks

### Extra LLM Calls

Without extractor:

```text
Retriever → Final LLM
```

1 LLM call.

With extractor:

```text
Retriever
   ↓
Extractor LLM
   ↓
Final LLM
```

Many additional calls.

---

Example:

```python
k = 10
```

Retrieved docs:

```text
10 documents
```

Extractor runs:

```text
10 LLM calls
```

Then:

```text
1 final LLM call
```

Total:

```text
11 LLM calls
```

Latency increases significantly.

---

# When Real Production Systems Use It

Good for:

✅ Large documents

✅ Enterprise search

✅ Legal documents

✅ Financial reports

✅ Insurance policies

✅ Medical guidelines

✅ Long PDFs

Not usually needed for:

❌ Small chunks (200-300 tokens)

❌ Highly optimized retrieval

❌ Fast chatbot applications requiring sub-second response

---

# Complete Production Flow

```text
User Question
      ↓
History Aware Retriever
      ↓
Vector Search
      ↓
Top 20 Chunks
      ↓
LLMChainFilter
      ↓
Top 8 Chunks
      ↓
LLMChainExtractor
      ↓
Relevant Sentences Only
      ↓
StuffDocumentsChain
      ↓
Final Answer
```

This is close to what many enterprise-grade RAG systems do when they need high precision over large, noisy documents.

The key idea is:

> Retrieval finds the right documents. `LLMChainExtractor` finds the right sentences inside those documents.

That's why it is called a **contextual document compressor** rather than a retriever—it doesn't search for information; it **shrinks retrieved documents down to only the query-relevant content before the final answering step**.



# Quesiton: is compressor done, after cross encoder reranking or before ? also give me the complete flow including - components like dense and sparse search, mmr, rrf, crossencoder


In a production-grade RAG system, **LLMChainExtractor is almost always applied after retrieval and reranking**, not before.

The reason is simple:

* Cross-encoder reranking is much cheaper than LLM extraction.
* You don't want to run an LLM on 50-100 retrieved chunks.
* First reduce the candidate set aggressively.
* Then use the extractor on only the top few chunks.

---

# Typical Modern RAG Pipeline

A common enterprise flow looks like:

```text
User Query
    ↓
Query Processing
    ↓
Hybrid Retrieval
    ↓
Fusion
    ↓
MMR
    ↓
Cross Encoder Reranking
    ↓
LLM Extraction / Compression
    ↓
Context Assembly
    ↓
Answer Generation
```

Let's examine every stage.

---

# Stage 1: Query Processing

User asks:

```text
What is the refund policy for damaged products?
```

Before retrieval you may perform:

## Query Rewriting

History-aware retriever:

```text
User: What about refunds?
```

becomes:

```text
What is the refund policy for damaged products?
```

---

## Multi Query Generation

Generate variants:

```text
refund policy damaged products
return damaged item
money back for defective item
```

Improves recall.

---

## HyDE

Generate hypothetical answer:

```text
Customers may receive a refund for damaged items within 30 days.
```

Embed this generated answer.

Often improves dense retrieval.

---

# Stage 2: Hybrid Retrieval

Most production systems use both:

## Dense Search

Vector DB

```text
Query Embedding
      ↓
Cosine Similarity
      ↓
Top K Dense Results
```

Example:

```text
Query:
broken product refund
```

Document:

```text
damaged item return policy
```

Dense retrieval understands:

```text
broken ≈ damaged
refund ≈ return
```

Semantic match.

---

## Sparse Search

BM25

```text
Query:
broken product refund
```

Looks for:

```text
broken
product
refund
```

keyword matches.

---

Why both?

Dense can miss exact keywords.

Sparse can miss semantic matches.

Together:

```text
Dense Top 20
Sparse Top 20
```

---

# Stage 3: Fusion (RRF)

Now you have:

Dense results:

```text
Doc A rank 1
Doc B rank 2
Doc C rank 3
```

Sparse results:

```text
Doc C rank 1
Doc D rank 2
Doc A rank 3
```

Need to combine.

---

## Reciprocal Rank Fusion (RRF)

Formula:

```text
1/(k+rank)
```

Conceptually:

```text
Dense score
+
Sparse score
```

Results:

```text
Doc A
Doc C
Doc B
Doc D
```

Documents appearing in both lists rise to the top.

---

Pipeline:

```text
Dense Retrieval
       ↓
Sparse Retrieval
       ↓
RRF Fusion
       ↓
Combined Ranking
```

---

# Stage 4: MMR

After fusion:

```text
Top 20 chunks
```

Problem:

```text
Chunk 1: Refund policy
Chunk 2: Refund policy
Chunk 3: Refund policy
Chunk 4: Refund policy
```

Near duplicates.

---

## Maximum Marginal Relevance (MMR)

MMR optimizes:

```text
Relevance
+
Diversity
```

Instead of:

```text
Refund policy
Refund policy
Refund policy
Refund policy
```

you get:

```text
Refund policy
Return process
Damaged goods policy
Customer support process
```

More coverage.

---

Example:

Without MMR:

```text
Top 10 chunks
=
same PDF page repeated
```

With MMR:

```text
Top 10 chunks
=
different sections
```

Much better context.

---

# Stage 5: Cross Encoder Reranking

This is where ranking quality jumps significantly.

---

## Retriever Scores

Dense retrieval:

```text
Query embedding
vs
Document embedding
```

Fast but approximate.

---

## Cross Encoder

Instead of comparing embeddings separately:

Input:

```text
[QUERY]
What is refund policy?

[DOCUMENT]
Customers may return damaged items...
```

Both go into the same transformer.

Cross encoder directly predicts:

```text
relevance = 0.97
```

---

Example:

Dense retrieval:

```text
Doc A = 0.81
Doc B = 0.79
Doc C = 0.78
```

Hard to distinguish.

Cross encoder:

```text
Doc A = 0.97
Doc C = 0.82
Doc B = 0.55
```

Much more precise.

---

Pipeline:

```text
Top 20 Chunks
       ↓
Cross Encoder
       ↓
Top 5 Chunks
```

---

Common models:

* BGE Reranker
* Cohere Rerank
* Jina Reranker
* MS MARCO Cross Encoders

---

# Stage 6: LLMChainExtractor

Now we finally compress.

We only have:

```text
Top 5 Chunks
```

instead of:

```text
Top 50 Chunks
```

---

Chunk:

```text
Company Overview

Founded in 2015.

Refund Policy

Damaged items may be returned
within 30 days.

Shipping Information

...
```

Question:

```text
What is the refund policy?
```

Extractor returns:

```text
Damaged items may be returned
within 30 days.
```

---

Pipeline:

```text
Top 5 Chunks
      ↓
LLMChainExtractor
      ↓
Relevant Sentences
```

---

# Stage 7: Context Assembly

Now combine extracted snippets:

```text
Snippet 1
Snippet 2
Snippet 3
```

Total:

```text
700 tokens
```

instead of:

```text
7000 tokens
```

---

# Stage 8: Final Answer Generation

StuffDocumentsChain:

```text
Question
+
Compressed Context
      ↓
LLM
      ↓
Answer
```

---

# Full Enterprise RAG Flow

A realistic enterprise setup:

```text
User Question
      ↓
History-Aware Query Rewriting
      ↓
Multi Query Expansion
      ↓
Hybrid Retrieval
      ├─ Dense Search (Vector DB)
      └─ Sparse Search (BM25)
      ↓
RRF Fusion
      ↓
Top 50 Chunks
      ↓
MMR Diversity Selection
      ↓
Top 20 Chunks
      ↓
Cross Encoder Reranker
      ↓
Top 5 Chunks
      ↓
LLMChainExtractor
      ↓
Relevant Sentences
      ↓
Context Packing
      ↓
StuffDocumentsChain
      ↓
LLM Answer
```

---

# What Most Production Systems Actually Do

For latency reasons, many production systems stop here:

```text
Query
   ↓
Hybrid Retrieval
   ↓
RRF
   ↓
Cross Encoder
   ↓
Top 5 Chunks
   ↓
LLM
```

No extractor.

Reason:

```text
Cross Encoder = ~20-100 ms
LLM Extraction = several hundred ms to seconds
```

---

# High-Accuracy Enterprise Systems

For legal, finance, compliance, insurance, healthcare:

```text
Hybrid Retrieval
      ↓
RRF
      ↓
Cross Encoder
      ↓
LLMChainExtractor
      ↓
Answer LLM
```

because accuracy matters more than latency.

---

A useful rule of thumb:

```text
Dense + Sparse
        ↓
RRF
        ↓
MMR
        ↓
Cross Encoder
        ↓
LLMChainExtractor
        ↓
Answer LLM
```

**Cross-encoder decides which chunks deserve attention.**
**LLMChainExtractor decides which sentences inside those chunks deserve attention.**

So in almost all production architectures, **cross-encoder reranking comes before LLMChainExtractor**.
