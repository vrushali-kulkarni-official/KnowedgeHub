"""
shared_data.py
──────────────
Sample documents used across all chunking demos.
Having one shared source lets you compare chunk outputs apples-to-apples.

We have three forms of the same content:
  PLAIN_TEXT   – unstructured prose   (good for strategies 1–4, 6)
  MARKDOWN_DOC – with headers/lists   (good for strategy 5)
  HTML_DOC     – same content in HTML (good for strategy 5)
"""

# ─── 1. PLAIN TEXT ─────────────────────────────────────────────────────────────
# Deliberately written with clear topic shifts so semantic chunking can detect them.
# Also long enough to produce multiple chunks with every strategy.

PLAIN_TEXT = """
Artificial intelligence is the simulation of human intelligence in machines.
These systems are designed to perform tasks that normally require human cognition.
The field of AI was formally founded at the Dartmouth Conference in 1956.
Since then, it has grown into one of the most transformative technologies in history.

Machine learning is a core branch of artificial intelligence.
Instead of being explicitly programmed for each task, ML systems learn from data.
Supervised learning uses labeled examples to train a model.
Unsupervised learning finds hidden patterns in data without labels.
Reinforcement learning trains agents through reward and punishment signals.

Deep learning is a subset of machine learning based on neural networks.
These networks are inspired loosely by the structure of the human brain.
They consist of layers of nodes, each learning progressively abstract features.
Convolutional neural networks excel at image recognition tasks.
Recurrent neural networks are designed for sequential data like text or audio.
Transformers, introduced in 2017, replaced RNNs for most NLP tasks.

Natural language processing allows computers to understand human language.
Tokenization is the process of breaking text into words or subword units.
Word embeddings map words to dense numerical vectors in a high-dimensional space.
The word2vec model showed that similar words cluster together in embedding space.
BERT introduced bidirectional context, improving understanding significantly.
Large language models like GPT-4, Llama, and Claude are trained on vast text corpora.
These models can generate coherent text, answer questions, translate languages, and write code.

Vector databases are a specialized type of storage system for AI applications.
Traditional databases store structured rows and columns.
Vector databases store high-dimensional floating-point arrays called embeddings.
When you encode text with a sentence transformer, you get a 384-dimensional vector.
Searching a vector database means finding vectors that are geometrically closest.
FAISS, developed by Meta, is a widely-used open-source library for this purpose.
ChromaDB and Pinecone are also popular options for production deployments.

Retrieval-Augmented Generation, or RAG, combines information retrieval with text generation.
The basic idea is to give a language model access to external knowledge at query time.
Instead of memorizing all facts during training, the model looks them up on demand.
A query is embedded and compared to stored document embeddings in a vector database.
The most similar documents are retrieved and injected into the prompt as context.
The language model then generates a response grounded in the retrieved information.
RAG significantly reduces hallucinations compared to purely parametric generation.
""".strip()


# ─── 2. MARKDOWN DOCUMENT ──────────────────────────────────────────────────────
# Has H1, H2, H3 headers, bullet lists, and code blocks.
# Strategy 5 (structure-aware) will preserve section hierarchy as metadata.

MARKDOWN_DOC = """
# A Practical Guide to RAG Systems

## Introduction

Retrieval-Augmented Generation (RAG) is a technique that combines the power of
large language models with external knowledge retrieval. Rather than relying solely
on what the model learned during training, RAG allows the system to look up fresh,
specific information at query time.

## Core Components

### The Embedding Model

An embedding model converts text into dense numerical vectors. These vectors
capture semantic meaning — similar texts produce similar vectors. Common choices:

- `all-MiniLM-L6-v2`: lightweight, 384 dimensions, fast
- `all-mpnet-base-v2`: higher quality, 768 dimensions, slower
- `text-embedding-3-small`: OpenAI's efficient model, requires API key

### The Vector Store

The vector store indexes and searches embeddings efficiently. Key options:

- **FAISS**: local, fast, open-source, no server needed
- **ChromaDB**: local + cloud, easy Python API, good for prototyping
- **Pinecone**: managed cloud service, production-grade, free tier available

### The Retriever

The retriever ties together embedding and vector store. It takes a query,
embeds it, and returns the most similar stored documents.

```python
retriever = vectorstore.as_retriever(
    search_type="mmr",          # Maximum Marginal Relevance
    search_kwargs={"k": 5}      # return top 5 results
)
```

## Chunking Strategies

### Why Chunking Matters

Documents must be split into chunks before indexing. The chunk size affects:

1. **Retrieval precision**: smaller chunks → more targeted retrieval
2. **Context completeness**: larger chunks → more context for the LLM
3. **Embedding quality**: chunks must fit within the model's token limit

### Recommended Approach

For most production systems, use a two-stage pipeline:

1. Split by semantic structure (headers, sections)
2. Apply recursive character splitting on oversized sections

## Evaluation

Evaluating a RAG system requires measuring both retrieval quality and answer quality.
Use frameworks like RAGAS to compute metrics such as faithfulness, context precision,
and answer relevance automatically.
""".strip()


# ─── 3. HTML DOCUMENT ─────────────────────────────────────────────────────────
# Same content as markdown but in HTML format.
# Used to demonstrate HTMLHeaderTextSplitter.

HTML_DOC = """<!DOCTYPE html>
<html>
<head><title>RAG Systems Guide</title></head>
<body>
<h1>A Practical Guide to RAG Systems</h1>

<h2>Introduction</h2>
<p>Retrieval-Augmented Generation (RAG) is a technique that combines the power of
large language models with external knowledge retrieval. Rather than relying solely
on what the model learned during training, RAG allows the system to look up fresh,
specific information at query time.</p>

<h2>Core Components</h2>

<h3>The Embedding Model</h3>
<p>An embedding model converts text into dense numerical vectors. These vectors
capture semantic meaning. Common choices include all-MiniLM-L6-v2 for lightweight
use cases and all-mpnet-base-v2 for higher quality embeddings.</p>

<h3>The Vector Store</h3>
<p>The vector store indexes and searches embeddings efficiently. FAISS is a local,
fast, open-source option with no server required. ChromaDB offers a simple Python
API good for prototyping. Pinecone is a managed cloud service for production use.</p>

<h3>The Retriever</h3>
<p>The retriever ties together embedding and vector store. It takes a query,
embeds it, and returns the most similar stored documents. You can configure the
number of results and the search strategy (similarity vs. MMR).</p>

<h2>Chunking Strategies</h2>

<h3>Why Chunking Matters</h3>
<p>Documents must be split into chunks before indexing. The chunk size affects
retrieval precision, context completeness, and embedding quality. Getting chunking
right is one of the highest-leverage improvements you can make to a RAG system.</p>

<h3>Recommended Approach</h3>
<p>For most production systems, use a two-stage pipeline: first split by semantic
structure such as headers and sections, then apply recursive character splitting
on any sections that are still too large.</p>

<h2>Evaluation</h2>
<p>Evaluating a RAG system requires measuring both retrieval quality and answer
quality. Use frameworks like RAGAS to compute faithfulness, context precision,
and answer relevance metrics automatically.</p>

</body>
</html>""".strip()


# ─── Helper: print chunk statistics ───────────────────────────────────────────

def print_chunks(chunks, strategy_name: str, show_content: bool = True):
    """
    Pretty-prints chunks with statistics.
    Works with both str chunks and LangChain Document objects.
    
    Args:
        chunks: list of str or list of Document
        strategy_name: label printed at the top
        show_content: if True, prints chunk text; set False for large outputs
    """
    from langchain_core.documents import Document

    print("\n" + "═" * 65)
    print(f"  {strategy_name}")
    print("═" * 65)

    sizes = []
    for i, chunk in enumerate(chunks):
        # Handle both raw strings and LangChain Document objects
        if isinstance(chunk, Document):
            text = chunk.page_content
            metadata = chunk.metadata
        else:
            text = chunk
            metadata = {}

        size = len(text)
        sizes.append(size)

        if show_content:
            print(f"\n┌─ Chunk {i+1:02d}  ({size} chars) {'─'*(40 - len(str(size)))}")
            # Truncate long chunks for readability
            display = text[:300] + ("..." if len(text) > 300 else "")
            # Indent each line
            for line in display.split("\n"):
                print(f"│  {line}")
            if metadata:
                print(f"│  📎 metadata: {metadata}")
            print(f"└{'─'*54}")

    # Summary statistics
    if sizes:
        print(f"\n📊 Stats: {len(chunks)} chunks | "
              f"min={min(sizes)} | max={max(sizes)} | "
              f"avg={sum(sizes)//len(sizes)} chars")
    print()
