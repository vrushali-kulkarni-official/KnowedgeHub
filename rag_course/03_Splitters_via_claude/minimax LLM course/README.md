# 📚 Production RAG — Chunking Strategies: Complete Theory Guide

## Why Chunking Matters More Than You Think

Your RAG pipeline is only as good as its chunks.

Here's the brutal truth: you can have the best LLM, the best vector database, and
the most carefully crafted prompts — but if your chunks are bad, retrieval fails,
and the LLM hallucinates. Chunking is **the most impactful lever** you haven't
fully tuned yet.

```
Document → [CHUNK] → Embed → Store in Vector DB
                                     ↓
Query → Embed → Similarity Search → Retrieve Chunks → LLM → Answer
```

The chunks retrieved must:
1. Be **semantically complete** (not cut mid-thought)
2. Be **the right size** (not too big, not too small)
3. Have **enough context** (the LLM needs surrounding info)
4. **Match query granularity** (fine-grained query → fine-grained chunks)

---

## The Size Tradeoff

This is the central tension in chunking:

| Chunk Size | Retrieval Quality | Context Quality | Cost |
|-----------|------------------|-----------------|------|
| Very Small (100 tokens) | ✅ Precise match | ❌ Missing context | ✅ Cheap |
| Medium (300-500 tokens) | ✅ Good balance | ✅ Good context | ✅ Moderate |
| Very Large (2000+ tokens) | ❌ Noisy match | ✅ Full context | ❌ Expensive |

**Rule of thumb**: chunk size should roughly match the granularity of expected queries.
If users ask about one specific fact → small chunks. If users ask for summaries → larger.

---

## Strategy 1: Fixed-Size Chunking (The Naive Baseline)

### How it works
Split text every `N` characters. Period. No awareness of words, sentences, or meaning.

```
Text:  "The quick brown fox jumps over the lazy dog sitting near the river."
N=20:  ["The quick brown fox ", "jumps over the lazy ", "dog sitting near th", "e river."]
```

With **overlap** (e.g., 5 chars): last 5 chars of chunk[i] = first 5 chars of chunk[i+1].
This prevents losing information at boundaries.

### The Problem
```
Chunk 1: "...Einstein proposed the theory of relativ"
Chunk 2: "ity in 1905, revolutionizing physics..."
```
Both chunks are now incomplete. Retrieval for "Einstein's theory" might return chunk 1
(no answer) or chunk 2 (no attribution). **Word and sentence boundaries are violated.**

### When to use
- Quick prototyping / baseline benchmarks
- Truly homogeneous data (logs, raw sensor data)
- When you have no structural signals in your text

### LangChain class: `CharacterTextSplitter`

---

## Strategy 2: Recursive Character Splitting (The Modern Default)

### How it works
Instead of splitting anywhere, try a **priority list of separators** in order:

```python
separators = ["\n\n", "\n", " ", ""]
# Try "\n\n" first (paragraph boundary) — ideal
# If chunk still too big, try "\n"  (line boundary)
# If still too big, try " "         (word boundary)
# If still too big, split anywhere  (last resort)
```

This is **recursive** because after splitting on `\n\n`, each resulting chunk
is checked against `chunk_size`. If it's still too big, it recurses with the
next separator in the list.

### Why this is the default
It **respects natural language structure** while still guaranteeing size limits.
Paragraphs are kept together, sentences are the fallback, words are the last resort.

### Example
```
Text (200 chars):
"Machine learning transforms industries.

Neural networks are inspired by the brain.
They have multiple layers."

chunk_size=80:
Chunk 1: "Machine learning transforms industries."        ← split on \n\n ✅
Chunk 2: "Neural networks are inspired by the brain."    ← split on \n\n ✅
Chunk 3: "They have multiple layers."                    ← split on \n\n ✅
```

### LangChain class: `RecursiveCharacterTextSplitter`

---

## Strategy 3: Token-Aware Splitting

### The core insight
LLMs don't see *characters* — they see *tokens*.

A token ≠ a character ≠ a word. It depends on the tokenizer (BPE, WordPiece, etc.):
- "tokenization" → ["token", "ization"] = **2 tokens**  
- "AI" → ["AI"] = **1 token**
- " " + word → often 1 token together

**The problem with character-based splitting:**
```
chunk_size=1000 characters → could be 200 tokens OR 800 tokens depending on content
```

This means you might:
- **Underestimate**: Your "1000 char" chunks are actually 800 tokens, wasting context space
- **Overestimate**: Your "1000 char" chunks overflow the LLM's context window

### LLM context windows (in tokens)
- GPT-3.5: 4,096 tokens
- GPT-4: 128,000 tokens  
- Llama 3.1: 128,000 tokens
- Phi-3: 128,000 tokens
- MiniLM (embedding): 256 tokens ← **your embedding model's limit!**

⚠️ **Critical**: If you use MiniLM for embeddings, chunks longer than 256 tokens
get **silently truncated**. You're embedding an incomplete chunk! Token-aware
splitting prevents this.

### Two approaches

**Approach A: tiktoken (OpenAI's tokenizer, free to use locally)**
```python
# Works great for GPT models and as a general approximation
RecursiveCharacterTextSplitter.from_tiktoken_encoder(
    model_name="gpt2",  # or "cl100k_base" for GPT-4
    chunk_size=200,  # in TOKENS now
)
```

**Approach B: HuggingFace tokenizer (model-specific)**
```python
# Use the exact tokenizer of YOUR embedding model
from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")
```

### LangChain class: `TokenTextSplitter`, `RecursiveCharacterTextSplitter.from_tiktoken_encoder`

---

## Strategy 4: Sentence-Aware Splitting

### The core insight
Sentences are the fundamental unit of meaning in language. Breaking mid-sentence
destroys semantic coherence. Sentence-aware splitting uses **NLP pipelines** to
detect true sentence boundaries.

### Why `\n` and `.` are insufficient
```python
# Naive sentence detection:
text.split(".")
→ ["Dr", " Smith went to Washington", " He ate a sandwich", "5 I", "e", " toast"]
# Problems: abbreviations (Dr.), numbers (5.I.), initials
```

Real NLP handles:
- `Dr. Smith` → not a sentence boundary
- `U.S.A.` → not a sentence boundary  
- `She said "Hello. How are you?"` → not a sentence boundary
- `He ran. She walked.` → two sentences ✅

### NLTK vs spaCy

| Feature | NLTK punkt | spaCy |
|---------|-----------|-------|
| Speed | Fast | Slower |
| Accuracy | Good | Better |
| Setup | `nltk.download('punkt')` | `python -m spacy download en_core_web_sm` |
| Model size | ~15MB | ~12MB (sm) |
| Additional NLP | No | Yes (NER, POS, etc.) |

### Custom sentence splitter
You can also use `sentence-transformers` directly or `spacy` sentence segmentation
and build your own grouping logic (group N sentences per chunk).

### LangChain classes: `NLTKTextSplitter`, `SpacyTextSplitter`

---

## Strategy 5: Structure-Aware Splitting (Markdown / HTML)

### The core insight
Documents have **semantic structure encoded in their format**:
- `# Introduction` → a major topic section
- `## Key Concepts` → a subsection  
- `<h2>Installation</h2>` → a section header

If you ignore this structure, you might split a section header from its content,
or merge two completely unrelated sections together.

### Markdown splitting
LangChain's `MarkdownHeaderTextSplitter` parses headers and attaches them as
**metadata** to every chunk, then splits on those header boundaries.

```markdown
# Chapter 1: AI
## What is ML?
Machine learning is...

## Neural Networks  
Neural networks are...
```

Result:
```python
Chunk 1: "Machine learning is..."  
  metadata: {"Header 1": "Chapter 1: AI", "Header 2": "What is ML?"}

Chunk 2: "Neural networks are..."
  metadata: {"Header 1": "Chapter 1: AI", "Header 2": "Neural Networks"}
```

The metadata is **gold for retrieval filtering**. You can say:
"Only search chunks from Chapter 2" → filter by `metadata["Header 1"] == "Chapter 2"`.

### HTML splitting
Same concept but for web content / scraped pages. Splits on `<h1>`, `<h2>`, etc.

### Combined pipeline
For production: 
```
MarkdownHeaderTextSplitter          → splits by section
  ↓ (chunks may still be large)
RecursiveCharacterTextSplitter      → splits large sections further
```

### LangChain classes: `MarkdownHeaderTextSplitter`, `HTMLHeaderTextSplitter`

---

## Strategy 6: Semantic Chunking (Split Where the Topic Changes)

### The core insight
The previous strategies all split based on **syntactic** signals (characters,
tokens, sentence boundaries, headers). Semantic chunking uses **meaning** instead.

**Idea**: Two consecutive sentences are in the same chunk if they're talking about
the same topic. They should be in different chunks if the topic changes.

How do we measure "same topic"? → **Cosine distance between embeddings**.

### The algorithm (LangChain's SemanticChunker)

```
1. Split text into individual sentences
2. For each sentence, create a "context window": [prev_sentence, current, next_sentence]
3. Embed each context window → get a vector per sentence
4. Compute cosine DISTANCE between consecutive sentence vectors
5. Large distance = topic change = chunk boundary
6. Merge sentences between boundaries into chunks
```

### Breakpoint detection methods

**Percentile** (most common): Find distances in the top Xth percentile → split there.
```
distances = [0.1, 0.12, 0.08, 0.85, 0.11, 0.09, 0.91, 0.13]
95th percentile = 0.88 → split at positions 3 and 6
```

**Standard deviation**: Split where distance > (mean + X * std_dev)

**Interquartile range**: Split where distance > Q3 + X * IQR (robust to outliers)

### Pros and cons

| Pros | Cons |
|------|------|
| Chunks are semantically coherent | Slow (embeds every sentence) |
| No fixed size constraints | Non-deterministic (changes with model) |
| Captures topic shifts precisely | Requires embedding model at index time |
| Works on any document type | Chunks vary wildly in size |

### When to use
- High-quality knowledge bases where precision matters
- Long documents with clear topic shifts
- When you have compute budget at indexing time
- Research papers, books, long articles

### LangChain class: `SemanticChunker` (in `langchain_experimental`)

---

## Strategy 7: Parent-Document Retriever (Small to Search, Big to Read)

### The core problem it solves
You face a paradox:
- **Small chunks** → precise retrieval (dense, focused embedding)
- **Large chunks** → rich context for the LLM

You can't optimize both with a single chunk size. The Parent-Document Retriever
**has both at the same time**.

### Architecture
```
                    INDEX TIME
Document (full)
    │
    ├── Parent Splitter (large) → Parent Doc [800 tokens]
    │         │
    │         └── Child Splitter (small) → Child Chunk 1 [200 tokens]  ← embedded
    │                                   → Child Chunk 2 [200 tokens]  ← embedded
    │                                   → Child Chunk 3 [200 tokens]  ← embedded
    │                                   → Child Chunk 4 [200 tokens]  ← embedded
    │
    ↓
Vector DB stores: Child chunks (small, precise)
DocStore stores:  Parent docs  (large, contextual)

                    QUERY TIME
Query → Embed → Find similar Child Chunks
              → Look up their Parent Document in DocStore
              → Return Parent Document to LLM (not the small child!)
```

### Key benefit
The LLM gets the full parent context (800 tokens), but retrieval was done via the
precise child chunk (200 tokens). Best of both worlds.

### Variants
1. **Small chunk retrieval + Full document return**: child chunks stored, full docs returned
2. **Small chunk retrieval + Parent chunk return**: child chunks stored, medium parents returned
3. **Full document retrieval with summary index**: embed summaries, return full docs

### LangChain class: `ParentDocumentRetriever`

---

## Strategy 8: Overlapping Windows & Late Chunking

### 8A: Sliding Window / Overlapping Chunks

This is a high-overlap version of chunking designed so every possible "answer span"
appears fully within at least one chunk.

```
Text: [....A....][....B....][....C....][....D....]
                    ↓  Sliding window (50% overlap)
Chunk 1: [....A....][....B....]
Chunk 2:        [....B....][....C....]  
Chunk 3:                [....C....][....D....]
```

With 50% overlap, you double your chunk count but guarantee that every 
`chunk_size/2` span of text is captured in full somewhere.

**Used by**: ColBERT-style multi-vector retrievers, BM25 + dense hybrid search.

### 8B: Late Chunking (JinaAI, 2024)

This is a cutting-edge technique that changes **when** you split.

**Traditional approach**:
```
Split first → Embed each chunk independently
```
**Late chunking**:
```
Embed entire document → Then split the token embeddings
```

Why does this matter? When you embed a long document first, each token's 
representation is influenced by its full context (via transformer attention).
Then you split by pooling token embeddings for each chunk region.

Result: each chunk embedding "knows" about the whole document context.

```
Document: "Python is a language. Guido van Rossum created it in 1989."

Traditional: 
  embed("Python is a language.")         → knows nothing about Guido
  embed("Guido van Rossum created it")   → "it" is ambiguous!

Late chunking:
  embed(full document) → pool chunk 1 tokens  → knows "it" = Python
                       → pool chunk 2 tokens  → "it" resolved via attention
```

**Requirement**: Needs a **long-context embedding model** (e.g., JinaAI's 
`jina-embeddings-v3` which supports up to 8192 tokens). Not suitable for MiniLM.

---

## Comparison Table

| Strategy | Size Control | Semantic Quality | Speed | Complexity | Best For |
|----------|-------------|-----------------|-------|-----------|----------|
| Fixed-size | ✅ Perfect | ❌ Poor | ✅✅ Fast | ⭐ Simple | Baselines |
| Recursive char | ✅ Good | ✅ Good | ✅✅ Fast | ⭐⭐ Easy | Default choice |
| Token-aware | ✅✅ Precise | ✅ Good | ✅ Fast | ⭐⭐ Easy | LLM token limits |
| Sentence-aware | ⚠️ Variable | ✅✅ Great | ✅ Fast | ⭐⭐ Easy | Prose documents |
| Structure-aware | ✅ Good | ✅✅ Great | ✅✅ Fast | ⭐⭐ Easy | Docs/HTML/MD |
| Semantic | ⚠️ Variable | ✅✅✅ Best | ❌ Slow | ⭐⭐⭐ Complex | High-quality KB |
| Parent-doc | ✅✅ Dual | ✅✅✅ Best | ✅ Fast | ⭐⭐⭐⭐ Complex | Production RAG |
| Overlapping | ⚠️ Redundant | ✅✅ Great | ✅ Fast | ⭐⭐ Easy | Multi-vector |

---

## Production Decision Guide

```
Is your document structured (headers, HTML)?
  YES → Structure-aware splitter (Strategy 5)
        + Recursive as secondary for large sections
  NO  ↓

Do you need precision > speed at index time?
  YES → Semantic chunker (Strategy 6)
  NO  ↓

Is your embedding model token-limited (e.g., MiniLM = 256 tokens)?
  YES → Always use Token-aware splitting (Strategy 3)
  NO  ↓

Is your text mostly prose (articles, books, reports)?
  YES → Sentence-aware (Strategy 4)
  NO  ↓

Are you building a production system where context quality matters most?
  YES → Parent-Document Retriever (Strategy 7)
  NO  → Recursive Character (Strategy 2) — the safe default
```

---

## The Chunk Size Question

A quick guide for chunk sizes with MiniLM embeddings:

```
MiniLM max tokens: 256
Recommended chunk size: 150-200 tokens (leave room for overlap + metadata)
Chunk overlap: 10-15% of chunk size

In characters (rough conversion: 1 token ≈ 4 characters):
  150 tokens ≈ 600 chars
  200 tokens ≈ 800 chars

So: chunk_size=600, chunk_overlap=60 is a safe starting point for MiniLM
```

For a different embedding model, look up its max sequence length on HuggingFace
and size accordingly.

---

## Files in This Guide

```
rag_chunking/
├── requirements.txt
├── README.md                   ← you are here
├── shared_data.py              ← sample documents used by all demos
│
├── 01_fixed_size.py            ← CharacterTextSplitter
├── 02_recursive_character.py   ← RecursiveCharacterTextSplitter
├── 03_token_aware.py           ← TokenTextSplitter + from_tiktoken_encoder
├── 04_sentence_aware.py        ← NLTKTextSplitter + SpacyTextSplitter
├── 05_structure_aware.py       ← MarkdownHeaderTextSplitter + HTMLHeaderTextSplitter
├── 06_semantic.py              ← SemanticChunker (langchain_experimental)
├── 07_parent_document.py       ← ParentDocumentRetriever
└── 08_late_overlapping.py      ← Sliding window + Late chunking theory
```
