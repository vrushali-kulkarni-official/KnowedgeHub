# RAG Embeddings — Complete Production Guide

> **Your RAG Journey So Far:**
> Basic RAG → Docling Loader → Chunking (Structural / TokenGuard / Semantic / Recursive)
> **Now: Embeddings** — the bridge between text and vector search.

---

## TABLE OF CONTENTS
1. [What Are Embeddings?](#1-what-are-embeddings)
2. [How Embedding Models Work Internally](#2-how-embedding-models-work-internally)
3. [Embedding Dimensions — Why They Matter](#3-embedding-dimensions)
4. [Sentence Transformers (Local, Free, Powerful)](#4-sentence-transformers)
5. [HuggingFace Embeddings (via LangChain)](#5-huggingface-embeddings-via-langchain)
6. [Gemini Embeddings (Google's API)](#6-gemini-embeddings)
7. [OpenAI Embeddings (Industry Baseline)](#7-openai-embeddings)
8. [Ollama Embeddings (Fully Local)](#8-ollama-embeddings)
9. [Choosing the Right Embedding Model](#9-choosing-the-right-model)
10. [Tradeoffs: Quality vs Cost vs Speed](#10-tradeoffs)
11. [Symmetric vs Asymmetric Embeddings](#11-symmetric-vs-asymmetric)
12. [Bi-Encoder vs Cross-Encoder (Reranking)](#12-bi-encoder-vs-cross-encoder)
13. [Production Embedding Pipeline](#13-production-embedding-pipeline)
    - Batching
    - Async embedding
    - Caching
    - Rate limiting
14. [Evaluating Your Embeddings (MTEB + Custom)](#14-evaluating-embeddings)
15. [Advanced: Hybrid Search (Dense + Sparse BM25)](#15-hybrid-search)
16. [Advanced: Matryoshka Embeddings](#16-matryoshka-embeddings)
17. [Advanced: Binary & Int8 Quantization of Embeddings](#17-quantization)
18. [The Full Production Embedding Strategy Diagram](#18-production-strategy)

---

## 1. What Are Embeddings?

An **embedding** is a list of floating point numbers (a vector) that represents the
*semantic meaning* of a piece of text — not its exact words, but what it *means*.

```
"The cat sat on the mat"  →  [0.21, -0.44, 0.08, 0.91, ...]   (768 numbers)
"A kitten rested on a rug" →  [0.20, -0.42, 0.09, 0.89, ...]   (768 numbers)
"Stock market crashed today" → [0.85,  0.67, -0.3, 0.02, ...]   (768 numbers)
```

The first two sentences are semantically similar → their vectors are close together.
The third sentence is unrelated → its vector is far away.

### Why RAG needs embeddings

In RAG:
1. At **index time**: you embed all your document chunks → store in a vector DB (FAISS, Chroma, etc.)
2. At **query time**: you embed the user's question → find the closest document vectors
3. **Retrieve** those close documents → pass to LLM as context

The quality of your embeddings directly determines the quality of retrieval.
Bad embeddings = wrong context = wrong answers.

```python
# ============================================================
# CONCEPTUAL DEMO: What is "closeness" between embeddings?
# ============================================================

import numpy as np


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """
    Cosine similarity measures the ANGLE between two vectors.
    Range: -1 (opposite) to 0 (unrelated) to 1 (identical meaning)

    This is the most common metric for text embeddings because
    it's length-independent — a long doc and short doc about the
    same topic should be equally similar.
    """
    a = np.array(vec_a)
    b = np.array(vec_b)

    # dot product divided by the product of their magnitudes
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


# Hypothetical embedding output (in reality these are 384-3072 dims)
cat_sentence = [0.21, -0.44, 0.08, 0.91]  # "The cat sat on the mat"
kitten_sentence = [0.20, -0.42, 0.09, 0.89]  # "A kitten rested on a rug"
stock_sentence = [0.85, 0.67, -0.30, 0.02]  # "Stock market crashed today"

print(cosine_similarity(cat_sentence, kitten_sentence))  # → ~0.99 (very similar)
print(cosine_similarity(cat_sentence, stock_sentence))  # → ~0.22 (unrelated)
```

---

## 2. How Embedding Models Work Internally

```
Input Text → Tokenizer → Transformer Layers → [CLS] Token / Mean Pooling → L2 Normalize → Vector

          "The cat sat"
                ↓
    ["The", "cat", "sat"] + position info
                ↓
    12 transformer layers (attention + feed-forward)
                ↓
    Each token has a 768-dim representation
                ↓
    MEAN POOLING: average all token vectors → one 768-dim vector
                ↓
    L2 NORMALIZE: scale to unit length (makes cosine sim = dot product)
                ↓
    [0.21, -0.44, 0.08, ...]   ← your embedding
```

### What is Mean Pooling?

```python
# ============================================================
# MEAN POOLING — how raw token embeddings become one vector
# ============================================================
import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModel


def mean_pooling(model_output, attention_mask):
    """
    The model produces one vector per TOKEN (e.g., 12 tokens → 12 vectors).
    We need ONE vector for the whole sentence.

    Mean pooling = weighted average of all token vectors,
    where padding tokens (attention_mask=0) are ignored.
    """
    # model_output[0] shape: [batch_size, seq_len, hidden_dim]
    # e.g.,                  [1, 12, 768]
    token_embeddings = model_output[0]

    # attention_mask shape: [batch_size, seq_len] — 1=real token, 0=padding
    # We expand it to match the embedding dimensions
    input_mask_expanded = (
        attention_mask
        .unsqueeze(-1)  # [batch, seq] → [batch, seq, 1]
        .expand(token_embeddings.size())  # → [batch, seq, hidden_dim]
        .float()
    )

    # Sum only the real (non-padding) token embeddings
    sum_embeddings = torch.sum(token_embeddings * input_mask_expanded, 1)

    # Divide by count of real tokens to get the mean
    sum_mask = torch.clamp(input_mask_expanded.sum(1), min=1e-9)

    return sum_embeddings / sum_mask


# --- FULL MANUAL EMBEDDING (so you understand what's happening under the hood) ---
tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")
model = AutoModel.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")

sentences = ["The cat sat on the mat", "Stock market crashed today"]

# Tokenize: convert text → token IDs + attention mask
encoded = tokenizer(
    sentences,
    padding=True,  # pad shorter sequences with 0s
    truncation=True,  # cut sequences longer than max_length
    max_length=256,
    return_tensors="pt",  # return PyTorch tensors
)

# Forward pass through transformer — no gradient needed at inference
with torch.no_grad():
    model_output = model(**encoded)

# Pool the token embeddings into sentence embeddings
sentence_embeddings = mean_pooling(model_output, encoded["attention_mask"])

# Normalize to unit length (required for cosine similarity = dot product)
sentence_embeddings = F.normalize(sentence_embeddings, p=2, dim=1)

print(sentence_embeddings.shape)  # torch.Size([2, 384])
# These 2 embeddings are now ready for storage / similarity search
```

---

## 3. Embedding Dimensions

The **dimension** of an embedding is how many numbers are in the vector.
Higher dimensions generally = more information = better quality (up to a point).

| Model | Dim | Notes |
|---|---|---|
| all-MiniLM-L6-v2 | 384 | Fast, small, surprisingly good |
| all-mpnet-base-v2 | 768 | Good balance |
| BAAI/bge-large-en-v1.5 | 1024 | Best open-source for English RAG |
| text-embedding-3-small (OpenAI) | 1536 | Cheap, good |
| text-embedding-3-large (OpenAI) | 3072 | Best quality from OpenAI |
| models/text-embedding-004 (Gemini) | 768 | Google's latest, very competitive |
| nomic-embed-text (Ollama) | 768 | Good local option |

### Why dimensions matter in production

```python
# ============================================================
# STORAGE & MEMORY COST OF EMBEDDING DIMENSIONS
# ============================================================


def calculate_vector_storage(
    num_documents: int,
    dimension: int,
    bytes_per_float: int = 4,  # float32 = 4 bytes
) -> dict:
    """
    In production you may embed millions of chunks.
    Understanding storage costs is critical for infrastructure planning.
    """
    total_bytes = num_documents * dimension * bytes_per_float
    total_mb = total_bytes / (1024**2)
    total_gb = total_bytes / (1024**3)

    return {
        "documents": num_documents,
        "dimension": dimension,
        "storage_mb": round(total_mb, 2),
        "storage_gb": round(total_gb, 4),
        # Higher dim also means slower similarity search
        "relative_search_cost": f"{dimension / 384:.1f}x vs MiniLM-384",
    }


# Compare storage for 1 million document chunks
for model, dim in [
    ("MiniLM-L6-v2", 384),
    ("mpnet-base-v2", 768),
    ("bge-large-en", 1024),
    ("text-embedding-3-large", 3072),
]:
    stats = calculate_vector_storage(1_000_000, dim)
    print(f"{model}: {stats['storage_mb']} MB  ({stats['relative_search_cost']})")

# Output:
# MiniLM-L6-v2:            1464.84 MB  (1.0x vs MiniLM-384)
# mpnet-base-v2:           2929.69 MB  (2.0x vs MiniLM-384)
# bge-large-en:            3906.25 MB  (2.7x vs MiniLM-384)
# text-embedding-3-large: 11718.75 MB  (8.0x vs MiniLM-384)
```

---

## 4. Sentence Transformers

The `sentence-transformers` library is the **standard** for local embedding models.
Built on top of HuggingFace Transformers, optimized specifically for producing
sentence/paragraph-level embeddings.

```python
# ============================================================
# SENTENCE TRANSFORMERS — The full picture
# ============================================================
# pip install sentence-transformers

from sentence_transformers import SentenceTransformer
import numpy as np

# ---- LOADING MODELS ----
# Models are downloaded once and cached at ~/.cache/huggingface/
# Subsequent runs are instant (loaded from disk)

# Option 1: Fast & small (good for development / resource-constrained)
model_small = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
# 80MB on disk, 384-dim, ~14k sentences/sec on CPU

# Option 2: Best quality open-source for English RAG (recommended for production)
model_bge = SentenceTransformer("BAAI/bge-large-en-v1.5")
# 1.3GB on disk, 1024-dim, ~2k sentences/sec on CPU

# Option 3: Multilingual (if your docs are not just English)
model_multi = SentenceTransformer(
    "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
)
# Supports 50+ languages, 768-dim

# ---- BASIC ENCODING ----
sentences = [
    "What are the eligibility requirements for a home loan?",
    "To qualify for a mortgage, you need a credit score above 620.",
    "The Federal Reserve raised interest rates by 25 basis points.",
    "Loan eligibility depends on income, credit history, and debt-to-income ratio.",
]

# encode() handles batching, tokenization, pooling, normalization internally
embeddings = model_small.encode(
    sentences,
    batch_size=32,  # process 32 sentences at once (adjust to your GPU/CPU RAM)
    show_progress_bar=True,  # useful when embedding thousands of chunks
    convert_to_numpy=True,  # return np.array instead of torch.Tensor
    normalize_embeddings=True,  # L2 normalize → cosine sim = dot product (faster search)
)

print(f"Shape: {embeddings.shape}")  # (4, 384)

# ---- SIMILARITY SEARCH ----
query = "What income is needed for a home loan?"
query_embedding = model_small.encode(query, normalize_embeddings=True)

# Dot product works for cosine similarity when embeddings are normalized
similarities = np.dot(embeddings, query_embedding)

for i, (sentence, score) in enumerate(zip(sentences, similarities)):
    print(f"[{score:.4f}] {sentence}")

# Output (sorted by relevance to query):
# [0.8234] To qualify for a mortgage, you need a credit score above 620.
# [0.7891] Loan eligibility depends on income, credit history, and debt-to-income ratio.
# [0.6123] What are the eligibility requirements for a home loan?
# [0.2341] The Federal Reserve raised interest rates by 25 basis points.
```

### Sentence Transformers with LangChain (your existing pipeline)

```python
# ============================================================
# SENTENCE TRANSFORMERS → LANGCHAIN INTEGRATION
# ============================================================
from langchain_huggingface import HuggingFaceEmbeddings
# NOTE: use langchain_huggingface, NOT langchain_community for new code
# pip install langchain-huggingface

# ---- CONFIGURATION ----
embedding_model = HuggingFaceEmbeddings(
    model_name="BAAI/bge-large-en-v1.5",
    # Where to run the model
    model_kwargs={
        "device": "cuda",  # "cuda" if GPU available, else "cpu"
        # "trust_remote_code": True,  # needed for some newer models
    },
    # How to encode
    encode_kwargs={
        "normalize_embeddings": True,  # ALWAYS True for cosine similarity search
        "batch_size": 64,  # larger = faster but more RAM
    },
    # Cache embeddings to disk to avoid recomputing on restart
    # (LangChain will skip computing embeddings for text it's seen before)
    cache_folder="./embedding_cache",
    # Show progress for large batches
    show_progress=True,
)

# ---- BGE MODELS NEED A SPECIAL QUERY PREFIX ----
# BGE (BAAI/bge-*) models were trained with a special instruction prefix
# for QUERIES (not for documents).
# This significantly improves retrieval quality.


class BGEEmbeddings(HuggingFaceEmbeddings):
    """
    BGE models need "Represent this sentence: " prepended to QUERIES only.
    Documents are embedded as-is.
    This asymmetric setup is intentional — BGE was fine-tuned this way.
    """

    # This prefix is added to queries during retrieval
    query_instruction = "Represent this sentence for searching relevant passages: "

    def embed_query(self, text: str) -> list[float]:
        """Called when embedding the USER'S QUESTION."""
        # Add the BGE query prefix to improve retrieval
        return super().embed_query(self.query_instruction + text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Called when embedding DOCUMENT CHUNKS. No prefix needed."""
        return super().embed_documents(texts)


# Use this instead of plain HuggingFaceEmbeddings for BGE models
bge_embedder = BGEEmbeddings(
    model_name="BAAI/bge-large-en-v1.5",
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True},
)

# Now use in your FAISS pipeline exactly as before
from langchain_community.vectorstores import FAISS

vectorstore = FAISS.from_documents(
    documents=your_chunks,  # your chunked documents from previous step
    embedding=bge_embedder,
)
```

---

## 5. HuggingFace Embeddings (via LangChain)

```python
# ============================================================
# ALL HUGGINGFACE EMBEDDING OPTIONS IN LANGCHAIN
# ============================================================

# ---- OPTION A: HuggingFaceEmbeddings (local model, runs on your machine) ----
from langchain_huggingface import HuggingFaceEmbeddings

local_embedder = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-mpnet-base-v2",
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True},
)

# ---- OPTION B: HuggingFaceInferenceAPIEmbeddings (remote API, no local GPU needed) ----
# Uses HuggingFace's Inference API — free tier available, paid for production
from langchain_community.embeddings import HuggingFaceInferenceAPIEmbeddings

api_embedder = HuggingFaceInferenceAPIEmbeddings(
    api_key="hf_your_token_here",
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    # Useful when: you don't have GPU locally but want to use a larger model
    # Downside: API latency (~200-500ms per call), rate limits, cost at scale
)

# ---- OPTION C: HuggingFaceEndpointEmbeddings (your own deployed endpoint) ----
# Deploy a model on HuggingFace Inference Endpoints (dedicated hardware)
# Better for production than free Inference API (no rate limits, guaranteed latency)
from langchain_huggingface import HuggingFaceEndpointEmbeddings

endpoint_embedder = HuggingFaceEndpointEmbeddings(
    model="https://your-endpoint.huggingface.cloud",
    huggingfacehub_api_token="hf_your_token_here",
)

# ---- OPTION D: TEI (Text Embeddings Inference) — Production-grade serving ----
# HuggingFace's high-performance embedding server (Docker)
# docker run -p 8080:80 ghcr.io/huggingface/text-embeddings-inference:cpu-1.5 \
#   --model-id BAAI/bge-large-en-v1.5
from langchain_huggingface import HuggingFaceEndpointEmbeddings

tei_embedder = HuggingFaceEndpointEmbeddings(
    model="http://localhost:8080",  # your TEI server
    # TEI gives you:
    # - Dynamic batching (handles bursts efficiently)
    # - Continuous batching
    # - ONNX/TensorRT optimization
    # - 10-50x faster than plain transformers serving
    # - Prometheus metrics
)
```

### Comparing HuggingFace local vs API vs endpoint

```python
# ============================================================
# WHEN TO USE WHICH HF OPTION
# ============================================================

"""
SCENARIO → RECOMMENDED OPTION

Development / prototyping
    → HuggingFaceEmbeddings (local, free, instant, no API keys)

Production, small-medium scale (< 10k docs, < 100 queries/day)
    → HuggingFaceEmbeddings (local) or Inference API

Production, large scale (> 100k docs, high QPS)
    → TEI (Text Embeddings Inference) on your own server
      OR HuggingFace Inference Endpoints (managed)

No GPU available, need large model
    → HuggingFace Inference API (free tier for testing)

Cost-sensitive with high volume
    → Local model with CPU batching or TEI on a CPU server
      (once you pay for the server, embedding is free forever)

Need SLA guarantees
    → HuggingFace Inference Endpoints (paid) or self-hosted TEI
"""
```

---

## 6. Gemini Embeddings

Google's embedding models are competitive with OpenAI and often outperform
open-source models on many benchmarks, especially for multilingual content.

```python
# ============================================================
# GEMINI EMBEDDINGS — Full Setup
# ============================================================
# pip install langchain-google-genai google-generativeai

import os
from langchain_google_genai import GoogleGenerativeAIEmbeddings

# ---- AVAILABLE MODELS ----
# models/text-embedding-004      → current best, 768-dim, FREE (as of 2024)
# models/embedding-001           → older, still good, 768-dim
# Both have 2048 token input limit (longer = truncated)

os.environ["GOOGLE_API_KEY"] = "your_gemini_api_key"

gemini_embedder = GoogleGenerativeAIEmbeddings(
    model="models/text-embedding-004",
    # TASK TYPE — THIS IS GEMINI'S SUPERPOWER
    # Gemini lets you specify what the embedding will be used for,
    # and it optimizes the vector accordingly.
    # For document chunks (index time):
    task_type="retrieval_document",
    # For user queries (query time):
    # task_type="retrieval_query",
    # Other task types available:
    # "semantic_similarity"  → for comparing two texts
    # "classification"       → for categorizing text
    # "clustering"           → for grouping similar texts
    # "question_answering"   → QA pairs
    # "fact_verification"    → for checking claims
)


# ---- THE KEY INSIGHT: TASK-SPECIFIC EMBEDDINGS ----
class GeminiRAGEmbeddings:
    """
    Gemini requires DIFFERENT task types for documents vs queries.
    This wrapper handles the switching automatically.
    """

    def __init__(self, api_key: str):
        os.environ["GOOGLE_API_KEY"] = api_key

        # Embedder for document chunks (used at index time)
        self.doc_embedder = GoogleGenerativeAIEmbeddings(
            model="models/text-embedding-004",
            task_type="retrieval_document",
        )

        # Embedder for user queries (used at retrieval time)
        self.query_embedder = GoogleGenerativeAIEmbeddings(
            model="models/text-embedding-004",
            task_type="retrieval_query",
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Called by LangChain when indexing document chunks."""
        return self.doc_embedder.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        """Called by LangChain when embedding user's question."""
        return self.query_embedder.embed_query(text)


# ---- RATE LIMITS & BATCHING FOR GEMINI ----
import time
from typing import Generator


def batch_embed_with_gemini(
    texts: list[str],
    embedder: GoogleGenerativeAIEmbeddings,
    batch_size: int = 100,  # Gemini limit: 100 texts per batch
    requests_per_minute: int = 1500,  # Free tier: 1500 RPM
) -> list[list[float]]:
    """
    Gemini has rate limits. This batches your documents safely.

    Free tier limits (as of 2024):
    - text-embedding-004: 1,500 RPM, 100 texts/request
    - Roughly: 150,000 text embeds per minute maximum
    """
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]

        try:
            batch_embeddings = embedder.embed_documents(batch)
            all_embeddings.extend(batch_embeddings)

            # Throttle to stay within rate limits
            # 1500 RPM = 1 request per 0.04 seconds, but be conservative
            time.sleep(0.1)

            print(f"Embedded {min(i + batch_size, len(texts))}/{len(texts)} texts")

        except Exception as e:
            if "RATE_LIMIT" in str(e) or "429" in str(e):
                # Exponential backoff on rate limit
                print(f"Rate limited. Waiting 60 seconds...")
                time.sleep(60)
                # Retry the same batch
                batch_embeddings = embedder.embed_documents(batch)
                all_embeddings.extend(batch_embeddings)
            else:
                raise e

    return all_embeddings


# ---- USING GEMINI WITH FAISS ----
from langchain_community.vectorstores import FAISS

gemini_rag = GeminiRAGEmbeddings(api_key="your_key")

# IMPORTANT: You must use the wrapper as the embedding object
# so that FAISS uses doc embeddings for indexing and query embeddings for search
vectorstore = FAISS.from_documents(
    documents=your_chunks,
    embedding=gemini_rag,  # uses embed_documents internally
)

# At query time, FAISS calls embedding.embed_query() automatically
retriever = vectorstore.as_retriever(search_kwargs={"k": 5})
```

---

## 7. OpenAI Embeddings

```python
# ============================================================
# OPENAI EMBEDDINGS — The industry baseline
# ============================================================
# pip install langchain-openai

import os
from langchain_openai import OpenAIEmbeddings

os.environ["OPENAI_API_KEY"] = "your_openai_api_key"

# ---- MODELS ----
# text-embedding-3-small  → 1536-dim, $0.020/1M tokens, great quality/cost ratio
# text-embedding-3-large  → 3072-dim, $0.130/1M tokens, best OpenAI quality
# text-embedding-ada-002  → 1536-dim, $0.100/1M tokens, older, still works well

openai_embedder = OpenAIEmbeddings(
    model="text-embedding-3-small",
    # MATRYOSHKA SUPPORT: OpenAI's new models support dimension reduction
    # You can reduce 1536 dims down to as low as 256 with minimal quality loss
    # (More on this in the Matryoshka section)
    # dimensions=512,  # Optional: reduce dimensions to save storage/cost
    # Chunk size for batching (OpenAI allows 2048 texts per batch)
    chunk_size=1000,
    # Automatically retry on rate limit errors
    max_retries=3,
    # Request timeout
    timeout=60,
)


# ---- COST CALCULATOR ----
def estimate_openai_embedding_cost(
    texts: list[str],
    model: str = "text-embedding-3-small",
    avg_tokens_per_text: int = None,
) -> dict:
    """
    Before embedding your production corpus, estimate the cost.
    This prevents surprise bills.
    """
    pricing = {
        "text-embedding-3-small": 0.020 / 1_000_000,  # $ per token
        "text-embedding-3-large": 0.130 / 1_000_000,
        "text-embedding-ada-002": 0.100 / 1_000_000,
    }

    # Rough estimate: ~4 characters per token
    if avg_tokens_per_text is None:
        avg_chars = sum(len(t) for t in texts) / len(texts)
        avg_tokens_per_text = avg_chars / 4

    total_tokens = len(texts) * avg_tokens_per_text
    cost_usd = total_tokens * pricing[model]

    return {
        "num_texts": len(texts),
        "estimated_tokens": int(total_tokens),
        "model": model,
        "estimated_cost_usd": round(cost_usd, 4),
        "note": "Actual tokens may vary. Use tiktoken for exact count.",
    }


# Check cost before a large embedding job
cost = estimate_openai_embedding_cost(your_text_chunks, model="text-embedding-3-small")
print(cost)
# {'num_texts': 5000, 'estimated_tokens': 750000, 'estimated_cost_usd': 0.015}
# $0.015 for 5000 chunks — very cheap!
```

---

## 8. Ollama Embeddings (Fully Local, Zero Cost)

```python
# ============================================================
# OLLAMA EMBEDDINGS — 100% local, no API key, no cost
# ============================================================
# 1. Install Ollama: https://ollama.ai
# 2. Pull a model: ollama pull nomic-embed-text
# 3. Start server:  ollama serve  (or it auto-starts)

from langchain_ollama import OllamaEmbeddings

# ---- AVAILABLE EMBEDDING MODELS IN OLLAMA ----
# nomic-embed-text          → 768-dim, 137MB, very good quality, recommended
# mxbai-embed-large         → 1024-dim, 670MB, best quality in Ollama
# all-minilm                → 384-dim, 45MB, fastest option

ollama_embedder = OllamaEmbeddings(
    model="nomic-embed-text",
    base_url="http://localhost:11434",  # default Ollama server URL
    # Ollama specific settings
    # num_ctx=8192,       # context window size (default varies by model)
    # num_thread=8,       # CPU threads to use
)

# ---- TEST IT ----
test_embedding = ollama_embedder.embed_query("test sentence")
print(f"Dimension: {len(test_embedding)}")  # 768

# ---- WHEN TO USE OLLAMA IN PRODUCTION ----
"""
GREAT FOR:
✓ Air-gapped environments (no internet access allowed)
✓ Sensitive data that can't leave your infrastructure
✓ Development — zero API cost, instant feedback
✓ On-premise deployment with good hardware
✓ High volume where API costs become significant

NOT IDEAL FOR:
✗ Serverless deployments (Ollama needs a persistent server)
✗ Very resource-constrained environments
✗ When you need highest quality (closed API models still edge it out)
"""
```

---

## 9. Choosing the Right Model

```python
# ============================================================
# THE MODEL SELECTION FRAMEWORK
# ============================================================

"""
STEP 1: Know your constraints
─────────────────────────────
Q: Can data leave your infrastructure?
  YES → All options available
  NO  → Local only: sentence-transformers, Ollama

Q: Do you have GPU?
  YES → Large models (bge-large, mpnet) are viable
  NO  → Small-medium models or API-based

Q: What's your budget?
  Free: sentence-transformers / Ollama
  Pay-per-use: Gemini (cheapest), OpenAI
  Fixed: self-hosted TEI

Q: What language(s) is your corpus in?
  English only: BGE, OpenAI, Gemini
  Multilingual: multilingual-mpnet, Gemini (very strong multi-lang)


STEP 2: Know your use case
──────────────────────────
Technical docs / code → bge-large, text-embedding-3-large
Legal / financial / medical      → text-embedding-3-large (highest accuracy)
Customer support                 → bge-base, text-embedding-3-small
General knowledge base           → nomic-embed-text (local) or text-embedding-3-small
Real-time chat                   → MiniLM (fastest) or text-embedding-3-small
Multi-language                   → Gemini text-embedding-004 or multilingual-mpnet


STEP 3: Benchmark on YOUR data (always)
────────────────────────────────────────
Generic benchmarks (MTEB) are helpful but not definitive.
Your domain may be different. Always test on a sample of your real data.
"""


# ---- PRACTICAL SELECTION MATRIX ----
def select_embedding_model(
    data_privacy: str,  # "public" | "private"
    has_gpu: bool,
    budget: str,  # "zero" | "low" | "medium" | "high"
    language: str,  # "english" | "multilingual"
    priority: str,  # "speed" | "quality" | "cost"
) -> dict:
    """
    A simple decision tree for model selection.
    Adjust weights based on your specific requirements.
    """

    recommendations = []

    if data_privacy == "private":
        # Data cannot leave your infrastructure
        if has_gpu:
            recommendations.append({
                "model": "BAAI/bge-large-en-v1.5",
                "lib": "sentence-transformers",
                "why": "Best open-source quality, GPU makes it fast enough",
            })
        else:
            recommendations.append({
                "model": "nomic-embed-text",
                "lib": "ollama",
                "why": "Good quality, simple setup, CPU-friendly",
            })
    else:
        # Data can go to API
        if budget == "zero":
            recommendations.append({
                "model": "sentence-transformers/all-MiniLM-L6-v2",
                "lib": "sentence-transformers",
                "why": "Free forever, surprisingly good, 384-dim",
            })
        elif budget in ("low", "medium"):
            recommendations.append({
                "model": "models/text-embedding-004",
                "lib": "google-genai",
                "why": "Free tier generous, task-type optimization, 768-dim",
            })
        elif budget == "high":
            recommendations.append({
                "model": "text-embedding-3-large",
                "lib": "openai",
                "why": "Best-in-class quality, 3072-dim, industry standard",
            })

    return recommendations[0] if recommendations else {"error": "No match found"}
```

---

## 10. Tradeoffs

```
QUALITY vs COST vs SPEED — The Triangle

         QUALITY
            ▲
            │  text-embedding-3-large
            │  bge-large-en-v1.5
            │      text-embedding-3-small
            │      bge-base-en-v1.5
            │           nomic-embed-text
            │           all-mpnet-base-v2
            │                all-MiniLM-L6-v2
            │
            └─────────────────────────────────▶ SPEED
            
COST:     $$$$           $$$           $$        $         FREE
         (3-large)    (ada-002)     (3-small) (Gemini)  (local)
```

```python
# ============================================================
# BENCHMARKING YOUR OPTIONS — do this before committing
# ============================================================
import time
from typing import Callable

def benchmark_embedder(
    embedder,
    texts: list[str],
    name: str,
) -> dict:
    """
    Measure real-world performance of an embedding model
    on YOUR data before committing to it.
    """
    
    # Warmup (first call is slow due to model loading / connection setup)
    _ = embedder.embed_documents(texts[:2])
    
    # Benchmark
    start = time.perf_counter()
    embeddings = embedder.embed_documents(texts)
    elapsed = time.perf_counter() - start
    
    dimension = len(embeddings[0])
    texts_per_second = len(texts) / elapsed
    
    # Storage cost for 1M documents
    storage_mb = (1_000_000 * dimension * 4) / (1024 ** 2)
    
    return {
        "name": name,
        "dimension": dimension,
        "texts_embedded": len(texts),
        "elapsed_seconds": round(elapsed, 2),
        "texts_per_second": round(texts_per_second, 1),
        "storage_per_1M_docs_mb": round(storage_mb, 0),
    }


# Run benchmark on your actual chunks
benchmark_texts = your_chunks_text[:100]  # sample of real data

results = [
    benchmark_embedder(
        HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2", ...),
        benchmark_texts, "MiniLM-L6-v2"
    ),
    benchmark_embedder(
        HuggingFaceEmbeddings(model_name="BAAI/bge-large-en-v1.5", ...),
        benchmark_texts, "BGE-Large"
    ),
    benchmark_embedder(
        GoogleGenerativeAIEmbeddings(model="models/text-embedding-004"),
        benchmark_texts, "Gemini-004"
    ),
]

for r in results:
    print(f"{r['name']:25} | dim={r['dimension']} | "
          f"{r['texts_per_second']:.0f} txt/s | "
          f"{r['storage_per_1M_docs_mb']:.0f} MB/1M docs")
```

---

## 11. Symmetric vs Asymmetric Embeddings

This is a **critical concept** most RAG tutorials skip.

```python
# ============================================================
# SYMMETRIC vs ASYMMETRIC EMBEDDINGS
# ============================================================

"""
SYMMETRIC: Query and document are embedded in the SAME way.
  - "What is Paris?" ←→ "Paris is the capital of France"
  - Used when both sides are similar in structure
  - Example: duplicate detection, semantic similarity
  - Models: all-MiniLM, all-mpnet (these are symmetric)

ASYMMETRIC: Query and document are embedded DIFFERENTLY.
  - Short question ←→ Long document passage
  - The query asks; the document answers
  - Models: BGE (needs prefix), E5 (needs prefix), Gemini (task_type parameter)
  - This is what you want for RAG!
"""

# The E5 family needs explicit prefixes (similar to BGE but different prefix)
from langchain_huggingface import HuggingFaceEmbeddings


class E5Embeddings(HuggingFaceEmbeddings):
    """
    E5 models (intfloat/e5-*) require different prefixes for queries vs docs.

    Fine-tuning detail: E5 was trained on (query, passage) pairs where:
    - query: "query: <text>"
    - passage: "passage: <text>"

    Using the wrong prefix (or no prefix) degrades retrieval by 10-20%.
    """

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        # Prepend "passage: " to all document chunks
        prefixed = ["passage: " + t for t in texts]
        return super().embed_documents(prefixed)

    def embed_query(self, text: str) -> list[float]:
        # Prepend "query: " to user questions
        return super().embed_query("query: " + text)


# Usage
e5_embedder = E5Embeddings(
    model_name="intfloat/e5-large-v2",
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True},
)

# ---- VISUAL INTUITION ----
"""
Without asymmetric handling:
  query:    "What is the capital of France?"   → vector_A
  document: "Paris is the capital of France."  → vector_B
  similarity(vector_A, vector_B) = 0.71  ← decent but not optimal

With asymmetric handling (E5 prefixes):
  query:    "query: What is the capital of France?"    → vector_A'
  document: "passage: Paris is the capital of France." → vector_B'
  similarity(vector_A', vector_B') = 0.94  ← much better!

This is because the model was TRAINED on prefixed text, so its internal
representations align better when you use them at inference too.
"""
```

---

## 12. Bi-Encoder vs Cross-Encoder (Reranking)

```python
# ============================================================
# BI-ENCODER vs CROSS-ENCODER — The two-stage retrieval pattern
# ============================================================

"""
STAGE 1 — BI-ENCODER (what we've been doing):
  - Embed query → vector
  - Embed documents → vectors
  - Find top-K by cosine similarity
  - FAST: O(1) per query (vector lookup), scales to millions of docs
  - LESS ACCURATE: query and doc are embedded independently (no interaction)

STAGE 2 — CROSS-ENCODER (reranking):
  - Takes top-K results from stage 1
  - Passes (query, document) TOGETHER through the model
  - SLOW: O(K) model forward passes per query
  - MORE ACCURATE: query and doc attend to each other → deeper understanding
  - Typically K = 20-50 (retrieve many, then rerank to top 5)
"""

from sentence_transformers import CrossEncoder
from langchain_community.vectorstores import FAISS


class TwoStageRetriever:
    """
    Production retrieval:
    1. Bi-encoder retrieves top-20 candidates quickly
    2. Cross-encoder reranks to find the truly best top-5

    This gives you speed (bi-encoder) AND accuracy (cross-encoder).
    """

    def __init__(self, vectorstore: FAISS, first_stage_k: int = 20, final_k: int = 5):
        # Stage 1: fast bi-encoder retriever
        self.retriever = vectorstore.as_retriever(
            search_kwargs={"k": first_stage_k}  # retrieve more than needed
        )

        # Stage 2: accurate cross-encoder reranker
        # ms-marco models are trained specifically for passage reranking
        self.reranker = CrossEncoder(
            "cross-encoder/ms-marco-MiniLM-L-6-v2",
            # Other reranker options:
            # "cross-encoder/ms-marco-MiniLM-L-12-v2"  → better quality, slower
            # "BAAI/bge-reranker-large"                 → best reranker
            # "mixedbread-ai/mxbai-rerank-base-v1"      → good balance
        )

        self.final_k = final_k

    def retrieve(self, query: str) -> list:
        # Stage 1: get top-20 by embedding similarity
        candidates = self.retriever.invoke(query)

        if not candidates:
            return []

        # Stage 2: score (query, document) pairs with cross-encoder
        # cross_inputs: list of (query, document_text) tuples
        cross_inputs = [[query, doc.page_content] for doc in candidates]

        # Scores are raw logits (not normalized), higher = more relevant
        scores = self.reranker.predict(cross_inputs)

        # Sort candidates by cross-encoder score (descending)
        scored = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)

        # Return only the top-K after reranking
        top_k_docs = [doc for doc, score in scored[: self.final_k]]

        # Add reranking scores to metadata for debugging
        for (doc, score), reranked_doc in zip(scored[: self.final_k], top_k_docs):
            reranked_doc.metadata["rerank_score"] = float(score)

        return top_k_docs


# ---- INTEGRATE WITH YOUR RAG CHAIN ----
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_core.output_parsers import StrOutputParser

two_stage = TwoStageRetriever(vectorstore, first_stage_k=20, final_k=5)


def format_docs(docs: list) -> str:
    return "\n\n".join(d.page_content for d in docs)


# The two-stage retriever replaces the simple retriever in your chain
rag_chain = (
    RunnablePassthrough.assign(
        context=(lambda x: x["question"])
        | RunnableLambda(two_stage.retrieve)  # two-stage instead of plain retriever
        | format_docs
    )
    | prompt
    | llm
    | StrOutputParser()
)
```

---

## 13. Production Embedding Pipeline

### Batching

```python
# ============================================================
# PRODUCTION PATTERN: EFFICIENT DOCUMENT INGESTION
# ============================================================

from langchain_core.documents import Document
from typing import Iterator
import asyncio


class ProductionEmbeddingPipeline:
    """
    A production-grade pipeline for embedding large document corpora.

    Features:
    - Dynamic batching (adapts to model limits)
    - Progress tracking
    - Error recovery (failed batches don't stop the whole job)
    - Checkpointing (resume interrupted jobs)
    - Memory-efficient streaming
    """

    def __init__(
        self,
        embedder,
        vectorstore_class,
        batch_size: int = 64,
        checkpoint_path: str = "./checkpoint.json",
    ):
        self.embedder = embedder
        self.vectorstore_class = vectorstore_class
        self.batch_size = batch_size
        self.checkpoint_path = checkpoint_path
        self.failed_batches = []

    def _load_checkpoint(self) -> set[str]:
        """Load previously processed document IDs to resume interrupted jobs."""
        import json

        try:
            with open(self.checkpoint_path) as f:
                return set(json.load(f)["processed_ids"])
        except FileNotFoundError:
            return set()

    def _save_checkpoint(self, processed_ids: set[str]):
        """Save progress so we can resume if interrupted."""
        import json

        with open(self.checkpoint_path, "w") as f:
            json.dump({"processed_ids": list(processed_ids)}, f)

    def _batch_documents(self, documents: list[Document]) -> Iterator[list[Document]]:
        """Split documents into batches."""
        for i in range(0, len(documents), self.batch_size):
            yield documents[i : i + self.batch_size]

    def ingest(
        self,
        documents: list[Document],
        resume: bool = True,
    ) -> "FAISS":
        """
        Embed and index documents with fault tolerance.
        If resume=True, skips already-processed documents.
        """
        from langchain_community.vectorstores import FAISS

        processed_ids = self._load_checkpoint() if resume else set()

        # Filter out already-processed documents
        remaining = [
            doc for doc in documents if doc.metadata.get("doc_id") not in processed_ids
        ]

        print(
            f"Total: {len(documents)} | Already done: {len(processed_ids)} | Remaining: {len(remaining)}"
        )

        vectorstore = None

        for batch_num, batch in enumerate(self._batch_documents(remaining)):
            try:
                if vectorstore is None:
                    # First batch: create the vectorstore
                    vectorstore = FAISS.from_documents(batch, self.embedder)
                else:
                    # Subsequent batches: add to existing vectorstore
                    vectorstore.add_documents(batch)

                # Update checkpoint
                batch_ids = {
                    doc.metadata.get("doc_id", str(i)) for i, doc in enumerate(batch)
                }
                processed_ids.update(batch_ids)
                self._save_checkpoint(processed_ids)

                print(f"Batch {batch_num + 1}: embedded {len(batch)} docs ✓")

            except Exception as e:
                print(f"Batch {batch_num + 1} FAILED: {e}")
                self.failed_batches.append(batch)
                # Continue with next batch instead of crashing
                continue

        if self.failed_batches:
            print(
                f"WARNING: {len(self.failed_batches)} batches failed. Check self.failed_batches"
            )

        return vectorstore
```

### Async Embedding

```python
# ============================================================
# ASYNC EMBEDDING — For high-throughput API-based models
# ============================================================
import asyncio
import aiohttp
from langchain_openai import OpenAIEmbeddings


class AsyncEmbeddingPipeline:
    """
    Async embedding is critical for API-based models (OpenAI, Gemini).

    Why async?
    - API calls have ~100-500ms latency
    - Sequential: 1000 texts × 200ms = 200 seconds
    - Async (10 concurrent): 1000 texts × 200ms / 10 = 20 seconds = 10x faster

    But: don't exceed rate limits!
    """

    def __init__(
        self,
        embedder: OpenAIEmbeddings,
        max_concurrent: int = 10,  # max simultaneous API calls
        requests_per_minute: int = 3000,  # stay under rate limit
    ):
        self.embedder = embedder
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.rpm_delay = 60.0 / requests_per_minute  # seconds between requests

    async def embed_one_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a single batch with rate limiting."""
        async with self.semaphore:
            # Use LangChain's async embed method
            result = await self.embedder.aembed_documents(texts)
            await asyncio.sleep(self.rpm_delay)  # rate limit
            return result

    async def embed_all(
        self, texts: list[str], batch_size: int = 100
    ) -> list[list[float]]:
        """Embed all texts concurrently in batches."""
        # Split into batches
        batches = [texts[i : i + batch_size] for i in range(0, len(texts), batch_size)]

        # Create async tasks for all batches
        tasks = [self.embed_one_batch(batch) for batch in batches]

        # Run all tasks concurrently (limited by semaphore)
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Flatten results and handle errors
        all_embeddings = []
        for i, result in enumerate(batch_results):
            if isinstance(result, Exception):
                print(f"Batch {i} failed: {result}")
                # Use zero vectors as fallback (or implement retry logic)
                all_embeddings.extend([[0.0] * 1536] * len(batches[i]))
            else:
                all_embeddings.extend(result)

        return all_embeddings

    def embed_sync(self, texts: list[str]) -> list[list[float]]:
        """Synchronous wrapper for use in non-async contexts."""
        return asyncio.run(self.embed_all(texts))
```

### Embedding Cache

```python
# ============================================================
# EMBEDDING CACHE — Never recompute the same text twice
# ============================================================
import hashlib
import pickle
from pathlib import Path


class CachedEmbeddings:
    """
    Wraps any embedder with a disk cache.

    In production, your document corpus changes slowly.
    Re-embedding unchanged documents wastes money and time.

    Cache key = SHA256(text) so identical text always hits the cache.
    """

    def __init__(self, embedder, cache_dir: str = "./.embedding_cache"):
        self.embedder = embedder
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.hits = 0
        self.misses = 0

    def _get_cache_key(self, text: str) -> str:
        """Hash the text to create a unique cache key."""
        return hashlib.sha256(text.encode()).hexdigest()

    def _cache_path(self, key: str) -> Path:
        # Use subdirectories to avoid having too many files in one directory
        return self.cache_dir / key[:2] / f"{key}.pkl"

    def _load_from_cache(self, key: str) -> list[float] | None:
        path = self._cache_path(key)
        if path.exists():
            with open(path, "rb") as f:
                return pickle.load(f)
        return None

    def _save_to_cache(self, key: str, embedding: list[float]):
        path = self._cache_path(key)
        path.parent.mkdir(exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(embedding, f)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed documents, using cache for texts we've seen before."""
        keys = [self._get_cache_key(t) for t in texts]

        # Separate cached from uncached
        to_embed_indices = []
        to_embed_texts = []
        cached_embeddings = {}

        for i, (text, key) in enumerate(zip(texts, keys)):
            cached = self._load_from_cache(key)
            if cached is not None:
                cached_embeddings[i] = cached
                self.hits += 1
            else:
                to_embed_indices.append(i)
                to_embed_texts.append(text)
                self.misses += 1

        # Only call the actual embedder for uncached texts
        if to_embed_texts:
            new_embeddings = self.embedder.embed_documents(to_embed_texts)
            for idx, emb, text in zip(to_embed_indices, new_embeddings, to_embed_texts):
                key = self._get_cache_key(text)
                self._save_to_cache(key, emb)
                cached_embeddings[idx] = emb

        # Return in original order
        return [cached_embeddings[i] for i in range(len(texts))]

    def embed_query(self, text: str) -> list[float]:
        """Queries are usually unique, but cache them anyway."""
        key = self._get_cache_key(text)
        cached = self._load_from_cache(key)

        if cached is not None:
            return cached

        embedding = self.embedder.embed_query(text)
        self._save_to_cache(key, embedding)
        return embedding

    @property
    def cache_stats(self) -> dict:
        total = self.hits + self.misses
        hit_rate = self.hits / total if total > 0 else 0
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": f"{hit_rate:.1%}",
            "cost_saved": f"~{self.hits} API calls avoided",
        }


# Use it by wrapping any existing embedder
raw_embedder = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004")
cached_embedder = CachedEmbeddings(raw_embedder, cache_dir="./.gemini_cache")

# Drop-in replacement — use it exactly like the original
vectorstore = FAISS.from_documents(documents=chunks, embedding=cached_embedder)
print(cached_embedder.cache_stats)  # {'hits': 4320, 'misses': 680, 'hit_rate': '86.4%'}
```

---

## 14. Evaluating Embeddings

```python
# ============================================================
# EVALUATING RETRIEVAL QUALITY — Don't just guess, measure
# ============================================================

"""
The MTEB Benchmark (Massive Text Embedding Benchmark)
  → https://huggingface.co/spaces/mteb/leaderboard
  → 56 datasets, 8 task types, standardized evaluation
  → Use MTEB scores as a starting point, but ALWAYS verify on YOUR data.

Key metrics for RAG:
  - MRR@K  (Mean Reciprocal Rank)   → rank of the first correct doc
  - NDCG@K (Normalized Discounted Cumulative Gain) → quality of top-K ranking
  - Recall@K → % of relevant docs in top-K results
  - Precision@K → % of top-K results that are relevant
"""


class RAGEvaluator:
    """
    Evaluate embedding quality on YOUR domain data.

    You need a test set of (question, correct_document_id) pairs.
    Even 50-100 questions gives you meaningful signal.
    """

    def __init__(self, vectorstore, k_values: list[int] = [1, 3, 5, 10]):
        self.vectorstore = vectorstore
        self.k_values = k_values

    def evaluate(
        self,
        test_pairs: list[dict],
        # test_pairs format:
        # [
        #   {"question": "What is...", "relevant_doc_ids": ["doc_123", "doc_456"]},
        #   ...
        # ]
    ) -> dict:

        metrics = {f"recall@{k}": 0 for k in self.k_values}
        metrics.update({f"precision@{k}": 0 for k in self.k_values})
        mrr_sum = 0

        max_k = max(self.k_values)

        for pair in test_pairs:
            query = pair["question"]
            relevant_ids = set(pair["relevant_doc_ids"])

            # Retrieve top-max_k documents
            results = self.vectorstore.similarity_search(query, k=max_k)
            retrieved_ids = [r.metadata.get("doc_id") for r in results]

            # Calculate MRR (rank of first relevant document)
            for rank, doc_id in enumerate(retrieved_ids, start=1):
                if doc_id in relevant_ids:
                    mrr_sum += 1.0 / rank
                    break

            # Calculate Recall@K and Precision@K
            for k in self.k_values:
                top_k_ids = set(retrieved_ids[:k])

                # Recall: how many relevant docs did we find in top-k?
                found_relevant = len(top_k_ids & relevant_ids)
                metrics[f"recall@{k}"] += found_relevant / len(relevant_ids)

                # Precision: of the top-k we returned, how many were relevant?
                metrics[f"precision@{k}"] += found_relevant / k

        n = len(test_pairs)
        results = {k: round(v / n, 4) for k, v in metrics.items()}
        results["mrr"] = round(mrr_sum / n, 4)

        return results


# ---- HOW TO BUILD A TEST SET CHEAPLY ----
def generate_test_questions_with_llm(
    documents: list[Document],
    n_questions: int = 100,
    llm=None,  # pass your LLM
) -> list[dict]:
    """
    Auto-generate test questions using your LLM.

    This is called "synthetic evaluation data generation."
    It's not perfect, but much better than no evaluation.
    """
    test_pairs = []
    sample_docs = documents[:n_questions]  # use first N docs

    for doc in sample_docs:
        # Ask LLM to generate a question this document can answer
        prompt = f"""Generate one specific question that this document passage answers.
        The question should be what a real user might ask.
        Return ONLY the question, nothing else.

        Document: {doc.page_content[:500]}

        Question:"""

        question = llm.invoke(prompt).content.strip()

        test_pairs.append({
            "question": question,
            "relevant_doc_ids": [
                doc.metadata.get("doc_id", doc.metadata.get("source"))
            ],
        })

    return test_pairs


# ---- COMPARE TWO EMBEDDING MODELS HEAD-TO-HEAD ----
def compare_models(model_a, model_b, documents, test_pairs):
    from langchain_community.vectorstores import FAISS

    # Build vectorstore with model A
    vs_a = FAISS.from_documents(documents, model_a)
    evaluator_a = RAGEvaluator(vs_a)
    metrics_a = evaluator_a.evaluate(test_pairs)

    # Build vectorstore with model B
    vs_b = FAISS.from_documents(documents, model_b)
    evaluator_b = RAGEvaluator(vs_b)
    metrics_b = evaluator_b.evaluate(test_pairs)

    print("\nModel Comparison:")
    print(f"{'Metric':20} {'Model A':15} {'Model B':15} {'Winner':10}")
    print("-" * 60)
    for metric in ["recall@1", "recall@5", "mrr"]:
        a, b = metrics_a[metric], metrics_b[metric]
        winner = "A" if a > b else ("B" if b > a else "tie")
        print(f"{metric:20} {a:<15.4f} {b:<15.4f} {winner:10}")
```

---

## 15. Hybrid Search (Dense + Sparse)

```python
# ============================================================
# HYBRID SEARCH — Combine embedding similarity with BM25
# ============================================================

"""
Dense search (embeddings):   Great for semantic similarity ("car" ↔ "automobile")
Sparse search (BM25/TF-IDF): Great for exact keyword matching ("API v2.3.1")

Hybrid = best of both worlds.
Critical for technical docs, code, product catalogs with model numbers, etc.
"""

from langchain_community.retrievers import BM25Retriever
from langchain.retrievers import EnsembleRetriever
from langchain_community.vectorstores import FAISS


def create_hybrid_retriever(
    documents: list[Document],
    embedding_model,
    dense_weight: float = 0.5,  # weight for embedding similarity
    sparse_weight: float = 0.5,  # weight for BM25
    k: int = 5,
) -> EnsembleRetriever:
    """
    EnsembleRetriever combines results from multiple retrievers
    using Reciprocal Rank Fusion (RRF).

    RRF score: 1 / (rank + 60) for each result, then sum across retrievers.
    This handles different score scales without needing normalization.

    dense_weight + sparse_weight should sum to 1.0
    """

    # Dense retriever: embedding similarity
    vectorstore = FAISS.from_documents(documents, embedding_model)
    dense_retriever = vectorstore.as_retriever(
        search_kwargs={"k": k * 2}  # retrieve more before fusion
    )

    # Sparse retriever: BM25 (keyword matching)
    # BM25 works on raw text — no embeddings needed
    bm25_retriever = BM25Retriever.from_documents(documents)
    bm25_retriever.k = k * 2  # same k for fair comparison

    # Hybrid retriever: weighted ensemble
    hybrid_retriever = EnsembleRetriever(
        retrievers=[dense_retriever, bm25_retriever],
        weights=[dense_weight, sparse_weight],
        # c=60 is the RRF constant (standard value)
    )

    return hybrid_retriever


# ---- WHEN TO ADJUST WEIGHTS ----
"""
High dense_weight (0.7-0.9):
  → User queries use natural language ("what's the process for...")
  → Document content is prose / narrative
  → Semantic understanding is more important than exact words

High sparse_weight (0.7-0.9):
  → Queries contain specific identifiers (product codes, version numbers)
  → Technical documentation with precise terminology
  → Users often search for exact phrases

Balanced (0.5 / 0.5):
  → Mixed content and query types
  → Good default for general-purpose RAG
"""

# Example: technical docs with model numbers → favor sparse
tech_retriever = create_hybrid_retriever(
    documents=tech_docs,
    embedding_model=bge_embedder,
    dense_weight=0.3,  # semantic understanding
    sparse_weight=0.7,  # exact keyword matching for model numbers
)

# Example: support FAQ → favor dense
faq_retriever = create_hybrid_retriever(
    documents=faq_docs,
    embedding_model=bge_embedder,
    dense_weight=0.7,  # "how do I cancel?" ≈ "subscription cancellation"
    sparse_weight=0.3,
)
```

---

## 16. Matryoshka Embeddings

```python
# ============================================================
# MATRYOSHKA EMBEDDINGS — Variable-dimension embeddings
# ============================================================

"""
Matryoshka Representation Learning (MRL) trains a single model so that
the FIRST N dimensions are always a useful embedding, regardless of N.

Think of Russian nesting dolls: the model packs the most important
information into the first few dimensions.

Benefits:
  Full 1536-dim → highest quality
  Truncate to 512-dim → 3x storage savings, ~same quality
  Truncate to 256-dim → 6x storage savings, slight quality drop

OpenAI's text-embedding-3 models support this.
Some sentence-transformer models too (e.g., nomic-embed-text-v1.5).
"""

from langchain_openai import OpenAIEmbeddings

# Standard full-dimension embeddings
full_embedder = OpenAIEmbeddings(
    model="text-embedding-3-small",
    dimensions=1536,  # default
)

# Truncated to 512 dims — 3x less storage, minimal quality loss
efficient_embedder = OpenAIEmbeddings(
    model="text-embedding-3-small",
    dimensions=512,  # ← matryoshka truncation
)

# Ultra-compact for high-volume, cost-sensitive use cases
compact_embedder = OpenAIEmbeddings(
    model="text-embedding-3-small",
    dimensions=256,  # ← more aggressive truncation
)


# For local models, you can manually truncate (if trained with MRL)
def truncate_embedding(embedding: list[float], target_dim: int) -> list[float]:
    """
    Manually truncate embeddings from an MRL-trained model.

    After truncation, you MUST re-normalize the vector.
    Without re-normalization, cosine similarity breaks.
    """
    import numpy as np

    truncated = np.array(embedding[:target_dim])
    # Re-normalize to unit length
    normalized = truncated / np.linalg.norm(truncated)
    return normalized.tolist()


# nomic-embed-text-v1.5 supports MRL
from langchain_community.embeddings import OllamaEmbeddings


class MatryoshkaOllamaEmbeddings:
    """
    Nomic Embed Text v1.5 with Matryoshka dimension reduction.
    Great for high-volume local deployments.
    """

    def __init__(self, target_dim: int = 256):
        self.base_embedder = OllamaEmbeddings(model="nomic-embed-text")
        self.target_dim = target_dim  # full=768, practical range: 64-768

    def embed_documents(self, texts):
        embeddings = self.base_embedder.embed_documents(texts)
        return [truncate_embedding(e, self.target_dim) for e in embeddings]

    def embed_query(self, text):
        embedding = self.base_embedder.embed_query(text)
        return truncate_embedding(embedding, self.target_dim)
```

---

## 17. Binary & Int8 Quantization of Embeddings

```python
# ============================================================
# QUANTIZATION — Compress embeddings for production scale
# ============================================================

"""
Float32 embedding: [-0.234, 0.891, -0.012, ...]  → 4 bytes per number

QUANTIZATION reduces precision to save memory and speed up search:

Int8 quantization:   map float to range [-128, 127] → 1 byte (4x smaller)
Binary quantization: map each float to 0 or 1        → 1 bit (32x smaller!)

Quality tradeoff:
  Float32 → baseline quality
  Int8    → ~99% of float32 quality, 4x smaller storage, 4x faster search
  Binary  → ~96% of float32 quality, 32x smaller storage, 32x faster search

Use case: you have millions of documents, storage is a constraint.
"""

import numpy as np
from langchain_community.vectorstores import FAISS
import faiss


def quantize_embeddings_int8(embeddings: np.ndarray) -> np.ndarray:
    """
    Convert float32 embeddings to int8.
    This is a simple linear quantization.
    """
    # Scale to [-128, 127] range
    # Each embedding is already normalized to unit length (values roughly -1 to 1)
    # So multiply by 127 to use the full int8 range
    int8_embeddings = np.clip((embeddings * 127).astype(np.int8), -128, 127)
    return int8_embeddings


def create_faiss_index_with_quantization(
    embeddings: np.ndarray,
    use_ivf: bool = True,  # Inverted File Index for fast approximate search
    use_pq: bool = True,  # Product Quantization for compression
    n_clusters: int = 256,  # IVF: number of Voronoi cells
    n_subvectors: int = 16,  # PQ: number of sub-vectors
) -> faiss.Index:
    """
    Build a compressed FAISS index for production-scale search.

    IVF (Inverted File Index):
      - Divides vector space into clusters
      - At search time, only checks nearby clusters
      - Makes search O(sqrt(N)) instead of O(N)
      - Great for > 100k vectors

    PQ (Product Quantization):
      - Compresses each vector from 768 floats to 16 bytes
      - ~192x compression! (768 × 4 bytes → 16 bytes)
      - Slight quality loss (~2-5% recall)

    Combined (IVFPQ): used by major vector DBs (Pinecone, Weaviate, etc.)
    """
    dimension = embeddings.shape[1]
    n_vectors = embeddings.shape[0]

    if use_ivf and use_pq:
        # IVFPQ: fast search + compressed storage
        # n_clusters: typically sqrt(n_vectors)
        # n_subvectors: dimension must be divisible by this
        index = faiss.IndexIVFPQ(
            faiss.IndexFlatL2(dimension),  # coarse quantizer
            dimension,
            n_clusters,  # number of clusters
            n_subvectors,  # bytes per compressed vector
            8,  # bits per subvector component (usually 8)
        )
    elif use_ivf:
        # IVF only: fast search, full precision
        index = faiss.IndexIVFFlat(
            faiss.IndexFlatL2(dimension),
            dimension,
            n_clusters,
            faiss.METRIC_INNER_PRODUCT,  # for cosine similarity (normalized vecs)
        )
    else:
        # Flat exact search (no compression, no approximation)
        # Only practical for < 100k vectors
        index = faiss.IndexFlatIP(dimension)  # IP = Inner Product

    # IVFPQ requires training before adding vectors
    if hasattr(index, "train"):
        print(f"Training FAISS index on {n_vectors} vectors...")
        index.train(embeddings.astype(np.float32))

    # Add vectors to index
    index.add(embeddings.astype(np.float32))

    # For IVF: how many clusters to check at search time
    # Higher nprobe = better recall but slower search
    # Rule of thumb: nprobe = sqrt(n_clusters)
    if hasattr(index, "nprobe"):
        index.nprobe = min(32, int(np.sqrt(n_clusters)))

    print(f"Index size: {index.ntotal} vectors")
    return index
```

---

## 18. Production Strategy Diagram

```
YOUR RAG EMBEDDING ARCHITECTURE — PRODUCTION FLOW
═══════════════════════════════════════════════════════════════════════

  DOCUMENTS
  (PDFs, Word, HTML, etc.)
        │
        ▼ [Docling Loader]
  Raw Text + Metadata
        │
        ▼ [Chunking Pipeline]
  Structural → TokenGuard → Semantic → Recursive
        │
        ▼
  Document Chunks (with source, page, section metadata)
        │
        ├──────────────────────────────────────┐
        ▼                                      ▼
  [Dense Embedding]                     [Sparse BM25]
  ┌─────────────────────┐               ┌────────────┐
  │ Model Selection:    │               │ Keyword    │
  │ Dev: MiniLM (free)  │               │ Matching   │
  │ Prod: BGE-large or  │               │ No vectors │
  │ text-embedding-3-sm │               │ needed     │
  │                     │               └────────────┘
  │ Optimizations:      │                     │
  │ - CachedEmbeddings  │                     │
  │ - Async batching    │                     │
  │ - BGE prefix        │                     │
  └─────────────────────┘                     │
        │                                      │
        ▼                                      │
  Vector Store (FAISS / Chroma / Pinecone)     │
  [With IVF+PQ for scale]                      │
        │                                      │
        └──────────────┬───────────────────────┘
                       ▼
              [EnsembleRetriever]
              Hybrid: dense(0.5) + sparse(0.5)
              top-20 candidates
                       │
                       ▼
             [CrossEncoder Reranker]
             BAAI/bge-reranker-large
             top-20 → top-5
                       │
                       ▼
             [LLM + StrOutputParser]
             Final answer

═══════════════════════════════════════════════════════════════════════

  QUICK DECISION GUIDE:
  ─────────────────────────────────────────────────────────────────────
  Budget?         Free → sentence-transformers BGE
                  Low  → Gemini text-embedding-004 (free tier)
                  Any  → text-embedding-3-small (cheap, great quality)

  Privacy?        Strict → Ollama (nomic-embed-text) or local BGE
                  Normal → Any API model

  Scale?          < 100k docs → FAISS flat index + no quantization
                  > 100k docs → FAISS IVFPQ or Pinecone/Qdrant
                  > 10M docs  → Managed vector DB (Pinecone, Weaviate)

  Quality max?    Bi-encoder (BGE/3-large) + Cross-encoder reranker
  Speed max?      MiniLM + No reranker
  Balance?        nomic-embed or text-embedding-3-small + optional rerank

  Always evaluate on your own domain before committing to a model.
═══════════════════════════════════════════════════════════════════════
```

---

## SUMMARY CHEATSHEET

```python
# ════════════════════════════════════════════════════════════
# ONE-FILE REFERENCE: All embedding options for LangChain RAG
# ════════════════════════════════════════════════════════════

# 1. Local free — best for dev or private data
from langchain_huggingface import HuggingFaceEmbeddings

embedder = HuggingFaceEmbeddings(
    model_name="BAAI/bge-large-en-v1.5",
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True},
)

# 2. Ollama — local, zero-config
from langchain_ollama import OllamaEmbeddings

embedder = OllamaEmbeddings(model="nomic-embed-text")

# 3. Gemini — cheapest API, task-type optimization
from langchain_google_genai import GoogleGenerativeAIEmbeddings

embedder = GoogleGenerativeAIEmbeddings(
    model="models/text-embedding-004",
    task_type="retrieval_document",  # or "retrieval_query" for queries
)

# 4. OpenAI — industry standard, matryoshka support
from langchain_openai import OpenAIEmbeddings

embedder = OpenAIEmbeddings(model="text-embedding-3-small")

# Add caching to ANY embedder (wrap it):
embedder = CachedEmbeddings(embedder)

# Build vectorstore — same for all:
from langchain_community.vectorstores import FAISS

vectorstore = FAISS.from_documents(chunks, embedder)

# Hybrid search — always better than pure dense:
from langchain.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever

hybrid = EnsembleRetriever(
    retrievers=[
        vectorstore.as_retriever(search_kwargs={"k": 20}),
        BM25Retriever.from_documents(chunks),
    ],
    weights=[0.5, 0.5],
)

# Reranking — use after hybrid for best quality:
from sentence_transformers import CrossEncoder

reranker = CrossEncoder("BAAI/bge-reranker-large")
```

---

*Next steps to continue your RAG journey:*
- **Advanced Retrieval**: Parent-child chunking, HyDE (Hypothetical Document Embeddings), Step-back prompting
- **Vector Databases**: Moving from FAISS to Qdrant / Chroma / Pinecone for production
- **Observability**: LangSmith tracing, retrieval metrics dashboards
- **Fine-tuning embeddings**: Domain-specific fine-tuning for specialized corpora
