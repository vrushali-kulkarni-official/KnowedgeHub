# popular tokenization models and embedding model combination

When building a **production RAG (Retrieval-Augmented Generation)** system, there are two separate but related components that people often confuse:

1. **Tokenizer** – Converts text into tokens that an LLM understands.
2. **Embedding Model** – Converts text into dense vectors for semantic search.

> **Important:** The tokenizer used by your LLM **does not have to match** the embedding model's tokenizer. In production, they are usually completely separate.

For example:

* User Question → **BGE-M3 embedding model** → Vector Database
* Retrieved Documents → **GPT-4.1 tokenizer (tiktoken)** → LLM

This is perfectly normal.

---

# 1. OpenAI

| LLM     | Tokenizer | Embedding Model        | Creator | Open Source? |
| ------- | --------- | ---------------------- | ------- | ------------ |
| GPT-4   | tiktoken  | text-embedding-3-small | OpenAI  | ❌            |
| GPT-4o  | tiktoken  | text-embedding-3-large | OpenAI  | ❌            |
| GPT-4.1 | tiktoken  | text-embedding-3-large | OpenAI  | ❌            |
| GPT-3.5 | tiktoken  | text-embedding-3-small | OpenAI  | ❌            |

Tokenizer

* **tiktoken**
* Very fast BPE tokenizer
* Closed-source model family, tokenizer library is open source

Embedding Models

* text-embedding-3-small
* text-embedding-3-large

Both are proprietary.

---

# 2. Anthropic Claude

| LLM           | Tokenizer        | Embedding                |
| ------------- | ---------------- | ------------------------ |
| Claude 3 Opus | Claude Tokenizer | Voyage AI / BGE / OpenAI |
| Claude Sonnet | Claude Tokenizer | Voyage AI / BGE          |
| Claude Haiku  | Claude Tokenizer | Voyage AI                |

Creator

Anthropic

Open Source?

❌ No

Anthropic does **not provide embedding models**.

Most Claude RAG systems use

* Voyage AI
* BGE
* OpenAI embeddings

---

# 3. Google Gemini

| LLM        | Tokenizer     | Embedding         |
| ---------- | ------------- | ----------------- |
| Gemini 2.5 | SentencePiece | Gemini Embeddings |

Creator

Google

Open Source?

❌ No

---

# 4. Meta Llama

| Model     | Tokenizer                | Embedding |
| --------- | ------------------------ | --------- |
| Llama 2   | SentencePiece            | BGE       |
| Llama 3   | TikToken-style tokenizer | BGE       |
| Llama 3.1 | TikToken-style tokenizer | BGE       |
| Llama 4   | TikToken-style tokenizer | BGE       |

Creator

Meta

Open Source?

* Model weights: ✅ Open-weight (license restrictions apply)
* Tokenizer: ✅

Popular embeddings

* BGE
* E5
* Nomic

---

# 5. Alibaba Qwen

| Model   | Tokenizer      | Embedding |
| ------- | -------------- | --------- |
| Qwen2   | Qwen Tokenizer | GTE-Qwen  |
| Qwen2.5 | Qwen Tokenizer | GTE-Qwen2 |
| Qwen3   | Qwen Tokenizer | GTE-Qwen3 |

Creator

Alibaba

Open Source?

✅ Yes

Tokenizer

Based on HuggingFace tokenizer.

Embedding

GTE-Qwen family

Excellent multilingual support.

---

# 6. DeepSeek

| Model       | Tokenizer     | Embedding |
| ----------- | ------------- | --------- |
| DeepSeek-V3 | SentencePiece | BGE       |
| DeepSeek-R1 | SentencePiece | BGE       |

Creator

DeepSeek AI

Open Source?

✅ Yes

DeepSeek currently does **not** ship official embedding models.

---

# 7. Mistral AI

| Model      | Tokenizer     | Embedding     |
| ---------- | ------------- | ------------- |
| Mistral 7B | SentencePiece | Mistral Embed |
| Mixtral    | SentencePiece | Mistral Embed |
| Magistral  | SentencePiece | Mistral Embed |

Creator

Mistral AI

Open Source?

| Component | Open Source |
| --------- | ----------- |
| Tokenizer | ✅           |
| LLM       | Mostly Open |
| Embedding | ❌ API       |

---

# 8. Microsoft Phi

| Model | Tokenizer     | Embedding |
| ----- | ------------- | --------- |
| Phi-3 | SentencePiece | E5        |
| Phi-4 | SentencePiece | E5        |

Creator

Microsoft

Open Source?

✅ Yes

---

# 9. Cohere

| Model      | Tokenizer        | Embedding |
| ---------- | ---------------- | --------- |
| Command R  | Cohere tokenizer | embed-v4  |
| Command R+ | Cohere tokenizer | embed-v4  |

Creator

Cohere

Open Source?

❌ No

Very popular in enterprise RAG.

---

# 10. Jina AI

| Model              | Tokenizer     | Embedding |
| ------------------ | ------------- | --------- |
| jina-embeddings-v2 | SentencePiece | jina-v2   |

Creator

Jina AI

Open Source?

Mostly ✅

Excellent for multilingual RAG.

---

# 11. BAAI (Beijing Academy of Artificial Intelligence)

No LLM

Only embeddings.

| Embedding |
| --------- |
| BGE-small |
| BGE-base  |
| BGE-large |
| BGE-M3    |

Tokenizer

SentencePiece

Creator

BAAI

Open Source?

✅ Yes

One of the most popular embedding families.

---

# 12. Nomic AI

| Embedding        |
| ---------------- |
| Nomic Embed Text |

Tokenizer

SentencePiece

Creator

Nomic AI

Open Source?

✅ Yes

Great for long-context retrieval.

---

# 13. Voyage AI

| Embedding      |
| -------------- |
| voyage-3       |
| voyage-large-2 |
| voyage-code    |

Tokenizer

Proprietary

Creator

Voyage AI

Open Source?

❌ No

One of the highest-performing commercial embedding providers.

---

# 14. Snowflake Arctic

| Embedding    |
| ------------ |
| Arctic Embed |

Tokenizer

SentencePiece

Creator

Snowflake

Open Source?

✅ Yes

Very strong enterprise embedding model.

---

# 15. Naver HyperCLOVA

| Embedding        |
| ---------------- |
| HyperCLOVA Embed |

Creator

Naver

Open Source?

Mostly ❌

Popular in Korea.

---

# 16. IBM Granite

| Model   | Tokenizer     | Embedding          |
| ------- | ------------- | ------------------ |
| Granite | SentencePiece | Granite Embeddings |

Creator

IBM

Open Source?

✅ Yes

---

# 17. Tencent Hunyuan

| Model   | Tokenizer     | Embedding     |
| ------- | ------------- | ------------- |
| Hunyuan | SentencePiece | Hunyuan Embed |

Creator

Tencent

Open Source?

Partially

---

# 18. ByteDance Doubao

| Model  | Tokenizer     | Embedding        |
| ------ | ------------- | ---------------- |
| Doubao | SentencePiece | Doubao Embedding |

Creator

ByteDance

Open Source?

❌ Mostly API

---

# 19. Open Source Embedding Models (Model Zoo)

These embedding models are commonly paired with many different LLMs:

| Embedding Model              | Creator    | Open Source | Typical Tokenizer | Notes                                                      |
| ---------------------------- | ---------- | ----------- | ----------------- | ---------------------------------------------------------- |
| BGE-small/base/large         | BAAI       | ✅           | SentencePiece     | Strong general-purpose retrieval                           |
| BGE-M3                       | BAAI       | ✅           | SentencePiece     | Multilingual, multi-function (dense, sparse, multi-vector) |
| E5-small/base/large          | Microsoft  | ✅           | SentencePiece     | Excellent retrieval quality                                |
| multilingual-E5              | Microsoft  | ✅           | SentencePiece     | Multilingual RAG                                           |
| GTE-large                    | Alibaba    | ✅           | SentencePiece     | High-quality multilingual embeddings                       |
| GTE-Qwen                     | Alibaba    | ✅           | Qwen tokenizer    | Optimized for Qwen ecosystem                               |
| Nomic Embed Text             | Nomic AI   | ✅           | SentencePiece     | Long-context retrieval                                     |
| Jina Embeddings v2           | Jina AI    | ✅           | SentencePiece     | Multilingual and long-context                              |
| Arctic Embed                 | Snowflake  | ✅           | SentencePiece     | Enterprise retrieval                                       |
| Stella                       | NovaSearch | ✅           | SentencePiece     | Strong open-source benchmark performance                   |
| UAE-Large-V1                 | WhereIsAI  | ✅           | SentencePiece     | General-purpose semantic search                            |
| NV-Embed                     | NVIDIA     | ✅           | SentencePiece     | Optimized for retrieval tasks                              |
| Mistral Embed                | Mistral AI | ❌ (API)     | SentencePiece     | Commercial embedding service                               |
| embed-v4                     | Cohere     | ❌           | Proprietary       | Enterprise-focused                                         |
| Voyage-3 / Voyage-large      | Voyage AI  | ❌           | Proprietary       | State-of-the-art commercial retrieval                      |
| text-embedding-3-small/large | OpenAI     | ❌           | tiktoken          | High-quality proprietary embeddings                        |

# Production Recommendations (2026)

These are common combinations used in production:

| LLM                  | Tokenizer        | Embedding              | Open Source Stack?                   |
| -------------------- | ---------------- | ---------------------- | ------------------------------------ |
| GPT-4.1 / GPT-4o     | tiktoken         | text-embedding-3-large | ❌                                    |
| GPT-4.1 / GPT-4o     | tiktoken         | BGE-M3                 | Partial (embedding only)             |
| Claude 4             | Claude tokenizer | Voyage-3               | ❌                                    |
| Claude 4             | Claude tokenizer | BGE-M3                 | Partial                              |
| Gemini 2.5           | SentencePiece    | Gemini Embeddings      | ❌                                    |
| Llama 3.1 / Llama 4  | Llama tokenizer  | BGE-M3                 | ✅ (open-weight LLM + open embedding) |
| Llama 3.1 / Llama 4  | Llama tokenizer  | E5-large               | ✅                                    |
| Qwen 3               | Qwen tokenizer   | GTE-Qwen3              | ✅                                    |
| DeepSeek R1          | SentencePiece    | BGE-M3                 | ✅                                    |
| Mistral 7B / Mixtral | SentencePiece    | BGE-M3                 | Mostly ✅                             |
| Phi-4                | SentencePiece    | E5-large               | ✅                                    |

## Practical guidance

For most production RAG systems today, a few embedding models dominate:

* **Open-source:** BGE-M3, multilingual-E5, GTE-Qwen, NV-Embed, Jina Embeddings v2.
* **Commercial:** OpenAI `text-embedding-3-large`, Voyage `voyage-3`, Cohere `embed-v4`.

The choice of tokenizer is usually dictated by the **generation model (LLM)**, while the choice of embedding model is dictated by your **retrieval quality, latency, language support, licensing, and deployment requirements**. It's common to mix vendors—for example, using Llama 3.1 for generation with BGE-M3 for retrieval, or Claude with Voyage embeddings.
