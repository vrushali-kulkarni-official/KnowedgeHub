# Storage & DB Mechanisms in Production RAG

## Why one DB is never enough

A naive RAG (your FAISS-based one) treats retrieval as "embed query → cosine similarity → top-k." That works for a demo with 500 chunks. In production, you discover fast that:

- Vector search is *bad* at exact matches (product codes, names, error codes, acronyms — "RTX 4090" might semantically match "graphics card" but lose to a random GPU article).
- Vector search has *no* concept of relationships ("which docs cite this policy," "who reports to whom").
- You don't want to re-embed/re-chunk every time someone wants the *original* document.
- Re-running an LLM call or embedding call for every single query is slow and expensive.
- Vectors are useless for *filtering* ("only docs from Legal team, uploaded in 2024").
- You need to store the actual files (PDFs, images) *somewhere*, and it's not in a vector index.

So real systems split storage by **access pattern**, not by convenience. This is called **polyglot persistence** — use the right tool for the right job, and stitch them together in the pipeline. Below is each store, what it's for, and concrete examples.

---

## 1. Vector DB → semantic search

**What it stores:** embedding vectors + minimal metadata + (sometimes) a pointer/ID back to the real content.

**What it's good at:** "find me things that *mean* the same as this query" even if no words match.

**What it's bad at:** exact lookups, filtering on structured fields at scale (though most now support filtered search), explainability ("why did this match?").

**Examples:** FAISS (what you're using — local, no metadata filtering, no persistence layer by default), Qdrant, Weaviate, Milvus, Pinecone, pgvector (Postgres extension — vectors living *inside* your relational DB).

**Example query:**
```
User: "How do I get my money back for a defective product?"
Vector DB matches chunks about "refund policy", "returns process", "warranty claims"
— none of which contain the literal words "money back."
```

**Production note:** Vector DBs almost never store the *full text* of a chunk as the source of truth — they store an ID, and the real chunk lives in a **document store** (see #5). FAISS in your basic implementation actually breaks this rule (it keeps everything in-memory together), which is fine for learning but won't scale or persist properly.

---

## 2. Keyword / Sparse Search Engine → exact term search

**What it stores:** an **inverted index** — for every token/word, a list of which documents contain it, with frequency stats.

**What it's good at:** exact strings, IDs, codes, names, rare technical terms, boolean logic ("must contain X, must NOT contain Y"), and it's *explainable* (BM25 score tells you exactly why something ranked).

**What it's bad at:** synonyms, paraphrasing, conceptual similarity. If the user says "car" and the doc says "automobile," keyword search sees nothing in common.

**Examples:** Elasticsearch, OpenSearch, Apache Solr, or even SQLite's FTS5 / Postgres `tsvector` for smaller scale. The scoring algorithm underneath is almost always **BM25** (an improved TF-IDF).

**Example query:**
```
User: "What does error code E-4471 mean?"
Vector search: poor — "E-4471" has no semantic meaning, embeds almost randomly.
Keyword search: perfect — exact token match in the inverted index, instant.
```

This is *why* production RAG almost always does **hybrid search**: run both vector and keyword search in parallel, then merge results (commonly with **Reciprocal Rank Fusion**,` RRF). You get semantic recall + exact-match precision.

---

## 3. Relational DB (SQL) → structured data

**What it stores:** structured, tabular facts with strict schema — users, documents metadata, permissions, chunk-to-document mappings, ingestion job status, feedback/ratings, billing.

**What it's good at:** joins, transactions (ACID), filtering, aggregation, "who has access to what," anything you'd normally model as rows and foreign keys.

**What it's bad at:** unstructured text, similarity, schema-less data.

**Examples:** PostgreSQL, MySQL, SQLite.

**Example in your RAG pipeline:**
```sql
documents(id, filename, source_path, uploaded_by, upload_date, doc_type, status)
chunks(id, document_id, chunk_index, char_start, char_end, embedding_id, chunking_strategy)
users(id, name, department, access_level)
```
So when a chunk comes back from the vector DB with `embedding_id = 8841`, you JOIN against this table to find: which document it came from, who can see it (access control!), and where the original text actually lives.

This is also where **access control / row-level security** lives — critical and often skipped by beginners. Vector DBs generally don't enforce "user A can't see HR documents" — your SQL layer (or filtered vector search using metadata from this layer) does.

---

## 4. Graph DB → relationships and knowledge traversal

**What it stores:** nodes (entities) and edges (relationships) — "Person WORKS_AT Company," "Policy SUPERSEDES Policy," "Drug INTERACTS_WITH Drug."

**What it's good at:** multi-hop reasoning that vector/keyword search literally cannot do. "Find all documents that reference a policy that was later amended by Document X" is a *graph traversal*, not a similarity search.

**What it's bad at:** fuzzy/semantic queries, ranking by relevance the way embeddings do.

**Examples:** Neo4j, Amazon Neptune, ArangoDB. This is the backbone of **GraphRAG** (Microsoft's approach) and **Knowledge-Graph RAG**.

**Example query:**
```
User: "What changed in our refund policy since 2022, and which other policies reference it?"
Pure vector RAG: retrieves chunks that *mention* refund policy — but has no idea about version history or cross-references.
Graph RAG: traverses (RefundPolicy_v3)-[SUPERSEDES]->(RefundPolicy_v2)-[SUPERSEDES]->(RefundPolicy_v1)
           and (ShippingPolicy)-[REFERENCES]->(RefundPolicy_v3)
           — gives you a structured answer + correct citations.
```
In practice, an LLM is used during ingestion to extract entities/relationships from chunks ("entity extraction") and populate the graph — this is a much heavier pipeline than vector ingestion.

---

## 5. Document Store → original documents

**What it stores:** the actual source content — full original documents and/or the full, untruncated chunk text (not just vectors). Usually JSON/BSON or just blobs with metadata.

**What it's good at:** being the **source of truth**. Whatever the vector DB returns is just an *ID*; you go to the document store to get the real text to hand to the LLM, or to show the user "here's exactly where this came from, page 14, paragraph 3."

**What it's bad at:** search — it's typically not very searchable on its own (you fetch by ID, not by similarity).

**Examples:** MongoDB, Elasticsearch (it doubles as document store + search index), DynamoDB, or even just well-organized JSON files for smaller projects.

**Why this matters for you specifically:** In your current FAISS implementation, the chunk text is probably stored *inside* FAISS's docstore object (LangChain wraps this for you). That's exactly a tiny, in-memory version of a "document store" pattern — production systems just externalize it into something persistent, queryable by ID, and shared across multiple vector DB shards.

```json
{
  "doc_id": "policy_2024_refund.pdf",
  "chunk_id": "chunk_0042",
  "text": "Customers may request a full refund within 30 days of purchase...",
  "metadata": {"page": 14, "section": "Returns", "chunking_strategy": "semantic"}
}
```

---

## 6. Cache → speed

**What it stores:** recent or frequent results — query embeddings, retrieved chunks, even full LLM answers — keyed by a hash of the input.

**What it's good at:** killing latency and cost on repeated/similar queries. Embedding a query and calling an LLM are the two most expensive steps in the pipeline; caching avoids redoing them.

**What it's bad at:** novel queries (cache miss = no benefit), and it introduces staleness risk if underlying docs change.

**Examples:** Redis (overwhelmingly the standard), Memcached. Often used at multiple levels:
- **Embedding cache:** `hash(query_text) → embedding_vector` (skip the embedding model call)
- **Retrieval cache:** `hash(query_text) → [chunk_ids]` (skip the vector search)
- **Semantic cache:** cache by *similarity* not exact match — if a new query embeds within 0.95 cosine similarity of a cached query, reuse the cached answer (libraries: GPTCache)
- **Full response cache:** `hash(query+context) → final_LLM_answer`

**Example:**
```
10,000 employees ask some version of "what's our WFH policy" in the first week of a new policy rollout.
Without cache: 10,000 embedding calls + 10,000 vector searches + 10,000 LLM calls.
With semantic cache: maybe 50 unique underlying queries actually hit the expensive path.
```

---

## 7. Object Storage → raw files

**What it stores:** the actual binary files — PDFs, DOCX, images, audio, video — exactly as uploaded, untouched.

**What it's good at:** cheap, durable, massively scalable storage of large blobs. It is *not* a database — no querying inside the file.

**What it's bad at:** search, structure, anything beyond "store this blob, give me a key to fetch it later."

**Examples:** AWS S3, Google Cloud Storage, Azure Blob Storage, MinIO (self-hosted S3-compatible — great for local production-style learning).

**Why you need this even though you already have a "document store":** the document store (#5) holds *extracted, chunked text* — not the original PDF with its layout, images, tables. If a user wants to open the actual source PDF, or if you need to re-process a document with Docling later using a better chunking strategy, you need the *original file* preserved somewhere immutable. Object storage is that "cold," authoritative archive.

```
s3://company-rag-docs/raw/policy_2024_refund.pdf   ← original, untouched
                ↓ (Docling parses this)
MongoDB doc store: chunked text + metadata
                ↓ (embedding model)
Vector DB: embeddings + chunk_id pointer back to MongoDB
```

---

## Putting it together: the two data flows

### A. Ingestion flow (write path) — what happens when a document enters the system

```
1. RAW FILE ARRIVES
   → stored immediately, untouched, in Object Storage (S3/MinIO)
   → a row created in Relational DB: documents(id, filename, status='uploaded')

2. PARSING / LOADING
   → Docling pulls the file from Object Storage, extracts text/tables/structure
   → Relational DB status updated: 'parsed'

3. CHUNKING
   → your structural/semantic/recursive/token-guard chunking runs
   → each chunk gets an ID, stored as a full record in the Document Store (MongoDB)
     {chunk_id, document_id, text, page, chunking_strategy, ...}
   → Relational DB: chunks(id, document_id, chunk_index, doc store pointer)

4. EMBEDDING
   → each chunk's text → embedding model (your MiniLM) → vector
   → vector + chunk_id (NOT the full text) → inserted into Vector DB (FAISS/Qdrant)

5. KEYWORD INDEXING (parallel to step 4)
   → same chunk text → tokenized → inserted into inverted index (Elasticsearch/BM25)

6. ENTITY EXTRACTION (optional, if doing GraphRAG)
   → LLM extracts entities/relations from chunk → nodes/edges written to Graph DB

7. Relational DB status updated: 'indexed' — document is now queryable
```

Notice: **the same chunk's text physically lives in at least 3 places** (Document Store as source of truth, inside the Vector DB's index structure or alongside it, inside the keyword index) — this duplication is intentional and normal. Each store optimizes the data differently for its access pattern.

### B. Query flow (read path) — what happens when a user asks a question

```
1. USER QUERY ARRIVES: "How do I get a refund for a defective product?"

2. CACHE CHECK (Redis)
   → hash/embed the query, check semantic cache
   → CACHE MISS → proceed
   → (CACHE HIT → skip straight to step 7, return cached answer)

3. PARALLEL RETRIEVAL
   a) Embed query (MiniLM) → search Vector DB → top-k chunk_ids by similarity
   b) Tokenize query → search Keyword Index (BM25) → top-k chunk_ids by exact term match
   c) (optional) extract entities from query → traverse Graph DB → related chunk_ids

4. FUSION / RERANKING
   → merge results from (a)+(b)+(c), commonly via Reciprocal Rank Fusion
   → optionally pass merged candidates through a reranker model (e.g. cross-encoder)
     for a more accurate final ordering

5. ACCESS CONTROL FILTER (Relational DB)
   → JOIN chunk_ids against documents/users table
   → drop any chunks the requesting user isn't authorized to see

6. HYDRATE FULL TEXT
   → for the final top-k chunk_ids, fetch FULL chunk text from Document Store (MongoDB)
   → (the vector/keyword indexes only had IDs + scores, not necessarily full text)

7. BUILD CONTEXT → PROMPT → LLM
   → exactly like your chain: format_docs(retrieved_chunks) → prompt → llm → StrOutputParser()

8. CACHE THE RESULT (Redis)
   → store query→answer (and query→chunk_ids) for future reuse

9. RETURN ANSWER + CITATIONS
   → citations reference document_id/page from Relational DB / Document Store,
     so the user can be pointed to the original file in Object Storage if they want to open it
```

---

## Worked example, start to finish

Say you upload `refund_policy.pdf`.

| Step | Store | What gets written/read |
|---|---|---|
| Upload | **Object Storage** | `s3://docs/raw/refund_policy.pdf` saved |
| Metadata row | **Relational DB** | `documents` row: id=101, status=uploaded |
| Docling parses | — | text extracted in memory |
| Chunked (semantic) | **Document Store** | 40 chunk docs written, e.g. chunk_037: "Customers may request a refund within 30 days..." |
| Chunk metadata | **Relational DB** | `chunks` table: chunk_037 → document_id=101, page=14 |
| Embedded | **Vector DB** | vector for chunk_037 inserted, payload = `{chunk_id: "chunk_037"}` |
| Tokenized | **Keyword Index** | chunk_037's tokens added to inverted index |
| Entities extracted | **Graph DB** | `(RefundPolicy)-[DEFINED_IN]->(Doc:101)` edge created |

Now a user asks: *"Can I get money back on a broken item?"*

1. Redis: cache miss.
2. Vector search finds chunk_037 (semantic match: "refund" ≈ "money back", "defective" ≈ "broken").
3. Keyword search might *miss* this one (no literal word overlap) but could catch a different chunk mentioning "defective items" verbatim.
4. RRF fusion merges both lists — chunk_037 ranks high from vector signal, the literal chunk ranks high from BM25 signal — both make the final top-k.
5. SQL check: user's `access_level` permits viewing `documents.id=101` (public policy doc) → passes.
6. Document Store hydration: full text of chunk_037 and the other chunk are fetched.
7. Context built → sent to LLM → answer generated, citing "Refund Policy, page 14."
8. Answer + chunk_ids cached in Redis.
9. User sees the answer, and optionally a "view source" link resolving to the original PDF in S3.

---

## How this maps onto what you should build next

Given where you are (FAISS + HuggingFace embeddings + Docling + multiple chunking strategies), a natural next set of hands-on exercises, roughly in this order:

1. **Externalize your document store** — stop relying on FAISS's in-memory docstore; write chunks to MongoDB or even SQLite with full text, and have FAISS/Qdrant only store `chunk_id + vector`.
2. **Add a keyword index** (Elasticsearch or even `rank_bm25` Python lib for something lightweight) and implement hybrid search with RRF.
3. **Add Postgres** for document/chunk metadata + a basic `users`/`access_level` table, and implement filtered retrieval.
4. **Add Redis** for a simple exact-match query cache, then upgrade to semantic caching.
5. **Add MinIO** (local S3-compatible) so raw files are stored independent of your processing pipeline.
6. **Graph DB last** — it's the most involved (needs LLM-based entity/relation extraction) and is genuinely optional unless your data has heavy interconnection (legal, compliance, org-chart-like data).

This progression mirrors how actual companies grow a RAG system — they don't start with all seven; they add stores as specific failure modes show up (bad exact-match recall → add keyword search; users complain about latency/cost → add cache; compliance asks "who can see what" → add SQL-based ACL; multi-hop questions fail → add graph).
