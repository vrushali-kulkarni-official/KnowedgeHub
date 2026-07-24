When working with RAG, embeddings, LLMs, and semantic chunking, it helps to think of the pipeline as:

```text
Raw Text
   ↓
Tokenizer
   ↓
Token IDs
   ↓
Embedding Model
   ↓
Dense Vectors
   ↓
Vector DB / Retrieval
```

A tokenizer and an embedding model are related, but they are separate components. Each embedding model generally expects the tokenizer it was trained with.

---

# 1. OpenAI Ecosystem

| Tokenizer   | Library  | Embedding Model              | Library    |
| ----------- | -------- | ---------------------------- | ---------- |
| cl100k_base | tiktoken | text-embedding-3-small       | OpenAI SDK |
| cl100k_base | tiktoken | text-embedding-3-large       | OpenAI SDK |
| o200k_base  | tiktoken | GPT-4o embeddings (internal) | OpenAI SDK |

Example:

```python
import tiktoken

enc = tiktoken.get_encoding("cl100k_base")
tokens = enc.encode(text)
```

Embedding:

```python
from openai import OpenAI

client = OpenAI()

emb = client.embeddings.create(model="text-embedding-3-small", input=text)
```

Common in production:

* OpenAI Assistants
* OpenAI RAG
* Enterprise search systems

---

# 2. BERT Family

| Tokenizer | Library               | Embedding Model    | Library               |
| --------- | --------------------- | ------------------ | --------------------- |
| WordPiece | transformers          | bert-base-uncased  | transformers          |
| WordPiece | transformers          | bert-large-uncased | transformers          |
| WordPiece | sentence-transformers | all-MiniLM-L6-v2   | sentence-transformers |

Example:

```python
from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")
```

Production usage:

* Search systems
* Classification
* Entity extraction

---

# 3. Sentence Transformers

Most popular embedding family for RAG.

| Tokenizer | Library      | Embedding Model            | Library               |
| --------- | ------------ | -------------------------- | --------------------- |
| WordPiece | transformers | all-MiniLM-L6-v2           | sentence-transformers |
| WordPiece | transformers | all-MiniLM-L12-v2          | sentence-transformers |
| WordPiece | transformers | multi-qa-MiniLM-L6-cos-v1  | sentence-transformers |
| WordPiece | transformers | msmarco-distilbert-base-v4 | sentence-transformers |

Example:

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
```

Most common local embedding model in tutorials and many production systems.

---

# 4. RoBERTa Family

| Tokenizer      | Library      | Embedding Model | Library      |
| -------------- | ------------ | --------------- | ------------ |
| Byte-Level BPE | transformers | roberta-base    | transformers |
| Byte-Level BPE | transformers | roberta-large   | transformers |

Tokenizer:

```python
from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("roberta-base")
```

Used in:

* NLP pipelines
* Research systems

---

# 5. MPNet Family

Very popular for retrieval.

| Tokenizer           | Library      | Embedding Model   | Library               |
| ------------------- | ------------ | ----------------- | --------------------- |
| SentencePiece + BPE | transformers | all-mpnet-base-v2 | sentence-transformers |

Example:

```python
model = SentenceTransformer("all-mpnet-base-v2")
```

Often outperforms MiniLM.

Production RAG systems frequently use:

```text
MiniLM  -> fast
MPNet   -> better quality
```

---

# 6. E5 Family (Microsoft)

One of the strongest open-source retrieval models.

| Tokenizer       | Library      | Embedding Model | Library      |
| --------------- | ------------ | --------------- | ------------ |
| XLM-R tokenizer | transformers | e5-small-v2     | transformers |
| XLM-R tokenizer | transformers | e5-base-v2      | transformers |
| XLM-R tokenizer | transformers | e5-large-v2     | transformers |

Example:

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("intfloat/e5-base-v2")
```

Used heavily in:

* Enterprise RAG
* Search engines
* Knowledge bases

---

# 7. BGE Family (BAAI)

Currently one of the most popular production embedding families.

| Tokenizer       | Library      | Embedding Model   | Library       |
| --------------- | ------------ | ----------------- | ------------- |
| XLM-R tokenizer | transformers | bge-small-en-v1.5 | FlagEmbedding |
| XLM-R tokenizer | transformers | bge-base-en-v1.5  | FlagEmbedding |
| XLM-R tokenizer | transformers | bge-large-en-v1.5 | FlagEmbedding |

Example:

```python
from FlagEmbedding import FlagModel

model = FlagModel("BAAI/bge-large-en-v1.5")
```

Used by many:

* RAG startups
* Search products
* Internal enterprise assistants

---

# 8. Cohere Embeddings

| Tokenizer             | Library    | Embedding Model    | Library    |
| --------------------- | ---------- | ------------------ | ---------- |
| Proprietary tokenizer | Cohere SDK | embed-v4.0         | Cohere SDK |
| Proprietary tokenizer | Cohere SDK | embed-english-v3.0 | Cohere SDK |

Used for:

* Enterprise search
* RAG

---

# 9. Voyage AI

Among the strongest commercial embedding providers.

| Tokenizer             | Library    | Embedding Model | Library    |
| --------------------- | ---------- | --------------- | ---------- |
| Proprietary tokenizer | Voyage SDK | voyage-3-large  | Voyage SDK |
| Proprietary tokenizer | Voyage SDK | voyage-3        | Voyage SDK |

Used in:

* High-end production RAG
* Enterprise retrieval

---

# 10. Jina AI Embeddings

| Tokenizer     | Library      | Embedding Model    | Library      |
| ------------- | ------------ | ------------------ | ------------ |
| SentencePiece | transformers | jina-embeddings-v3 | transformers |

Example:

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("jinaai/jina-embeddings-v3")
```

Popular for:

* Long-context retrieval
* Multilingual search

---

# 11. Llama Family

| Tokenizer     | Library      | Embedding Model                        | Library      |
| ------------- | ------------ | -------------------------------------- | ------------ |
| SentencePiece | transformers | Llama 3 embeddings (custom extraction) | transformers |
| SentencePiece | transformers | LlamaIndex embedding adapters          | llama-index  |

Tokenizer:

```python
from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("meta-llama/Llama-3-8B")
```

---

# 12. Mistral Family

| Tokenizer     | Library      | Embedding Model   | Library      |
| ------------- | ------------ | ----------------- | ------------ |
| SentencePiece | transformers | mistral-embed     | Mistral SDK  |
| SentencePiece | transformers | e5-based variants | transformers |

---

# Most Important Tokenization Algorithms

| Algorithm                | Used By                |
| ------------------------ | ---------------------- |
| WordPiece                | BERT, MiniLM           |
| BPE (Byte Pair Encoding) | GPT-2, RoBERTa         |
| Byte-Level BPE           | GPT-2, RoBERTa         |
| SentencePiece BPE        | Llama, T5              |
| SentencePiece Unigram    | T5, ALBERT             |
| tiktoken BPE             | GPT-3.5, GPT-4, GPT-4o |
| XLM-R Tokenizer          | E5, BGE                |
| Character Tokenization   | Rare today             |
| Whitespace Tokenization  | Traditional NLP        |

---

# What top companies typically use today (2025–2026)

For semantic splitting and RAG:

| Company Type                 | Common Embeddings      |
| ---------------------------- | ---------------------- |
| OpenAI-based products        | text-embedding-3-large |
| Microsoft enterprise search  | E5 family              |
| Startups                     | BGE-large              |
| Cost-sensitive production    | MiniLM                 |
| High-quality retrieval       | MPNet                  |
| State-of-the-art open source | BGE, E5, Jina          |
| Large-scale enterprise RAG   | OpenAI, Voyage, Cohere |

A practical ranking for modern RAG systems would be:

```text
Commercial:
1. OpenAI text-embedding-3-large
2. Voyage-3-large
3. Cohere embed-v4

Open Source:
1. BGE-large-en-v1.5
2. E5-large-v2
3. Jina-embeddings-v3
4. all-mpnet-base-v2
5. all-MiniLM-L6-v2
```

For semantic chunking specifically, most production systems do **not** use a special tokenizer. They usually:

1. Split text into sentences (spaCy, NLTK, blingfire, syntok).
2. Generate embeddings using BGE/E5/OpenAI/Voyage.
3. Measure cosine similarity between adjacent sentence embeddings.
4. Create chunk boundaries where similarity drops significantly.

So the embedding model (BGE, E5, OpenAI, Voyage) is usually far more important than the tokenizer when implementing semantic splitting.
