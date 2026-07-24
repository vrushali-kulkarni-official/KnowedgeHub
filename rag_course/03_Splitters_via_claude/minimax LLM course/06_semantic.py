"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  CHUNKING STRATEGY #6: SEMANTIC CHUNKING  (Split on Topic Changes)         ║
╚══════════════════════════════════════════════════════════════════════════════╝

THE CORE INSIGHT
────────────────
Every strategy so far splits based on SYNTACTIC signals:
  - Characters, tokens (Strategies 1–3)
  - Sentence boundaries (Strategy 4)
  - Header markers (Strategy 5)

Semantic chunking splits based on MEANING:
  "Put sentences in the same chunk if they discuss the same topic.
   Start a new chunk when the topic changes."

This is a fundamentally different approach. Instead of rules, it uses
your EMBEDDING MODEL to measure when meaning changes.

THE ALGORITHM
─────────────
  1. Split text into individual sentences (using NLTK)
  
  2. Create a "context window" around each sentence:
     sentence[i] gets context = sentence[i-1] + sentence[i] + sentence[i+1]
     This prevents single sentences from being embedded without context.
  
  3. Embed each context window → a vector per sentence
  
  4. Compute cosine DISTANCE between consecutive sentence vectors:
     distance[i] = 1 - cosine_similarity(embed[i], embed[i+1])
     
     Low distance (≈0.0) = very similar topics → keep in same chunk
     High distance (≈1.0) = very different topics → split here
  
  5. Find "breakpoints" — sentences where the distance spikes:
     Three methods to define "spike":
       a) percentile: distances in the top X% are breakpoints
       b) standard deviation: distances > (mean + X*std) are breakpoints
       c) interquartile: distances > Q3 + X*IQR are breakpoints
  
  6. Merge all sentences between breakpoints into one chunk

VISUALISATION
─────────────
  Sentences: [S1][S2][S3][S4][S5][S6][S7][S8]
  Distances:      0.1 0.1 0.9 0.1 0.1 0.8 0.1
                          ↑           ↑
                      breakpoint  breakpoint
  
  Chunks: [S1 S2 S3] [S4 S5 S6] [S7 S8]

THE COST: WHY IT'S NOT THE DEFAULT
────────────────────────────────────
  - Embeds EVERY sentence (or context window) in the document
  - For a 100-sentence document: 100 embedding calls
  - With MiniLM on CPU: maybe 1–2 seconds/100 sentences → tolerable
  - At scale (10,000-sentence corpus): ~2 minutes just to chunk
  - At production scale: use a GPU or accept slower indexing time

  But it's an OFFLINE cost (only at index time, not at query time).
  If your knowledge base is small-medium (< 50 docs), the quality
  improvement often outweighs the cost.

LANGCHAIN CLASS
───────────────
  SemanticChunker  (in langchain_experimental.text_splitter)
  Works with ANY LangChain-compatible embeddings object, including
  your free HuggingFace MiniLM — no OpenAI required.
"""

# ─── Imports ──────────────────────────────────────────────────────────────────

from langchain_experimental.text_splitter import SemanticChunker
from langchain_huggingface import HuggingFaceEmbeddings
from shared_data import PLAIN_TEXT, print_chunks

# ─── Load embeddings once (slow first time, cached after) ─────────────────────
# Using your existing MiniLM model — free, local, no API key needed.
# This will download ~90MB on first run, then uses cache.

print("⏳ Loading MiniLM embedding model (first run downloads ~90MB, then cached)...")

EMBEDDINGS = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    model_kwargs={"device": "cpu"},    # use CPU — works on any machine
    encode_kwargs={"normalize_embeddings": True}  # cosine similarity needs normalised vectors
)

print("✅ Embedding model loaded.\n")


# ══════════════════════════════════════════════════════════════════════════════
# DEMO A: SemanticChunker with percentile breakpoints
# ══════════════════════════════════════════════════════════════════════════════

def demo_a_percentile():
    """
    breakpoint_threshold_type="percentile"
    breakpoint_threshold_amount=95  (95th percentile)
    
    Meaning: "A split happens when the cosine distance between two
    consecutive sentence windows is in the top 5% of all distances
    in this document."
    
    Higher percentile → fewer splits → larger chunks
    Lower percentile  → more splits  → smaller chunks
    """
    chunker = SemanticChunker(
        embeddings=EMBEDDINGS,
        breakpoint_threshold_type="percentile",
        breakpoint_threshold_amount=90,    # top 10% of distances trigger a split
    )

    chunks = chunker.split_text(PLAIN_TEXT)
    print_chunks(chunks, "6A: SemanticChunker — Percentile (threshold=90)")

    print("→ Chunks are formed by topic, not size. Notice topic-coherent groups!")
    print("→ Chunk size is variable — that's expected and intentional.")


# ══════════════════════════════════════════════════════════════════════════════
# DEMO B: SemanticChunker with standard deviation breakpoints
# ══════════════════════════════════════════════════════════════════════════════

def demo_b_standard_deviation():
    """
    breakpoint_threshold_type="standard_deviation"
    breakpoint_threshold_amount=1.5  (mean + 1.5 * std)
    
    A split happens when the distance between two consecutive sentences
    is more than (mean + 1.5 standard deviations) above the average distance.
    
    This is a statistical approach: splits only at UNUSUALLY large jumps.
    More robust than percentile when documents have uneven topic density.
    """
    chunker = SemanticChunker(
        embeddings=EMBEDDINGS,
        breakpoint_threshold_type="standard_deviation",
        breakpoint_threshold_amount=1.5,   # 1.5 standard deviations above mean
    )

    chunks = chunker.split_text(PLAIN_TEXT)
    print_chunks(chunks, "6B: SemanticChunker — Std Deviation (threshold=1.5)")

    print("→ Fewer, larger chunks than percentile method — only true topic shifts trigger splits.")


# ══════════════════════════════════════════════════════════════════════════════
# DEMO C: SemanticChunker with interquartile range breakpoints
# ══════════════════════════════════════════════════════════════════════════════

def demo_c_interquartile():
    """
    breakpoint_threshold_type="interquartile"
    
    Splits where distance > Q3 + threshold * IQR.
    IQR = interquartile range = Q3 - Q1 (middle 50% spread).
    
    This is MORE ROBUST to outliers than standard deviation.
    Useful when one topic shift is dramatically more extreme than others —
    std deviation would set too high a bar, missing subtle shifts.
    """
    chunker = SemanticChunker(
        embeddings=EMBEDDINGS,
        breakpoint_threshold_type="interquartile",
        breakpoint_threshold_amount=1.5,
    )

    chunks = chunker.split_text(PLAIN_TEXT)
    print_chunks(chunks, "6C: SemanticChunker — Interquartile (threshold=1.5)")


# ══════════════════════════════════════════════════════════════════════════════
# DEMO D: Visualise distance scores — the "seam" between sentences
# This reveals what the chunker sees internally
# ══════════════════════════════════════════════════════════════════════════════

def demo_d_visualise_distances():
    """
    We manually compute the pairwise cosine distances between sentences
    to show you what SemanticChunker is seeing inside.
    
    This is the "graph" that determines where splits happen.
    You should see low distances within topics and high distances at topic transitions.
    """
    import nltk
    import numpy as np

    try:
        nltk.data.find("tokenizers/punkt_tab")
    except LookupError:
        nltk.download("punkt_tab")

    sentences = nltk.sent_tokenize(PLAIN_TEXT)

    print("\n" + "═" * 65)
    print("  6D: Inter-Sentence Cosine Distances")
    print("═" * 65)
    print(f"\n  Embedding {len(sentences)} sentences (this may take 10–30 seconds on CPU)...")

    # Embed all sentences
    vectors = EMBEDDINGS.embed_documents(sentences)
    vectors = np.array(vectors)

    # Compute cosine distance between consecutive sentences
    # Cosine distance = 1 - cosine_similarity
    # Since embeddings are normalised: cosine_sim = dot product
    distances = []
    for i in range(len(vectors) - 1):
        cos_sim = np.dot(vectors[i], vectors[i + 1])   # both normalised → dot = cosine sim
        cos_dist = 1.0 - cos_sim
        distances.append(cos_dist)

    # Display as a bar chart in ASCII
    max_dist = max(distances) if distances else 1
    threshold_95 = np.percentile(distances, 90)

    print(f"\n  {'Boundary':<12} {'Distance':>8}  {'Bar (▓=high = likely split)'}")
    print(f"  {'─'*12} {'─'*8}  {'─'*30}")
    for i, dist in enumerate(distances):
        bar_len = int(dist / max_dist * 30)
        bar = "▓" * bar_len + "░" * (30 - bar_len)
        split_marker = " ← SPLIT" if dist >= threshold_95 else ""
        # Show first 25 chars of sentence[i] as label
        label = sentences[i][:20].replace("\n", " ") + "..."
        print(f"  [{i:2d}→{i+1:2d}] {dist:.3f}   {bar}{split_marker}")

    # Show which boundaries would become splits
    split_indices = [i for i, d in enumerate(distances) if d >= threshold_95]
    print(f"\n  Boundaries above 90th percentile: {split_indices}")
    print(f"  These {len(split_indices)} boundaries would create {len(split_indices)+1} chunks")
    print(f"\n  Notice: high-distance boundaries occur where topic changes in the text.")


# ══════════════════════════════════════════════════════════════════════════════
# DEMO E: SemanticChunker + secondary size-based splitter
# Production pattern: semantic splits → then enforce size limit
# ══════════════════════════════════════════════════════════════════════════════

def demo_e_semantic_then_size():
    """
    Pure semantic chunking can produce very large or very small chunks.
    A long single-topic passage might become a 2000-token chunk — too big
    for your embedding model or LLM context window.
    
    Production fix: semantic chunking first, then split any oversized chunks
    with RecursiveCharacterTextSplitter.
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    # Stage 1: Semantic splits
    semantic_chunker = SemanticChunker(
        embeddings=EMBEDDINGS,
        breakpoint_threshold_type="percentile",
        breakpoint_threshold_amount=90,
    )
    semantic_chunks = semantic_chunker.split_text(PLAIN_TEXT)

    print("\n" + "═" * 65)
    print("  6E: Semantic → Size Enforcement Pipeline")
    print("═" * 65)
    print(f"\n  Stage 1 (semantic): {len(semantic_chunks)} chunks")
    sizes_1 = [len(c) for c in semantic_chunks]
    print(f"  Sizes: min={min(sizes_1)} max={max(sizes_1)} chars")

    # Stage 2: Enforce size limit on any oversized chunks
    size_splitter = RecursiveCharacterTextSplitter(
        chunk_size=600,        # ~150 tokens for MiniLM
        chunk_overlap=60,
    )

    from langchain_core.documents import Document
    semantic_docs = [Document(page_content=c) for c in semantic_chunks]
    final_docs = size_splitter.split_documents(semantic_docs)

    sizes_2 = [len(d.page_content) for d in final_docs]
    print(f"  Stage 2 (size limit): {len(final_docs)} chunks")
    print(f"  Sizes: min={min(sizes_2)} max={max(sizes_2)} chars")
    print(f"\n  Result: semantically coherent AND size-bounded chunks ✅")

    # Show a few
    for i, doc in enumerate(final_docs[:3]):
        print(f"\n  [Chunk {i+1}] {len(doc.page_content)} chars")
        print(f"    {doc.page_content[:120].replace(chr(10),' ')}...")


# ══════════════════════════════════════════════════════════════════════════════
# KEY TAKEAWAYS
# ══════════════════════════════════════════════════════════════════════════════

def print_takeaways():
    print("\n" + "=" * 65)
    print("KEY TAKEAWAYS — Semantic Chunking")
    print("=" * 65)
    print("""
  1. Semantic chunking is the highest-quality approach for documents
     with clear topic transitions (research papers, long articles, books).

  2. It's SLOW at index time because it embeds every sentence.
     It's FAST at query time — no difference from other strategies.
     Acceptable for small-medium knowledge bases. At scale, use a GPU.

  3. Three breakpoint methods:
       percentile:    most intuitive, consistent chunk counts
       std_deviation: more stable across different document types
       interquartile: robust to outliers (extreme topic jumps)
     → Start with percentile(90), tune as needed.

  4. ALWAYS follow semantic chunking with a size-based secondary splitter
     (Demo E). Pure semantic chunks can be 10 chars or 2000 chars.

  5. Works with FREE local embeddings (MiniLM). No OpenAI API needed.

  6. The internal distance graph (Demo D) is a powerful debugging tool.
     If your chunks look wrong, plot the distances and see where splits
     are being placed.

  NEXT UP → Strategy 7: Parent-Document Retriever
  → python 07_parent_document.py
""")


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n🔍 Running all Semantic Chunking demos...\n")
    print("Note: each demo re-embeds sentences — expect 10–60s per demo on CPU.\n")

    demo_a_percentile()
    print("\n" + "─" * 65 + "\n")

    demo_b_standard_deviation()
    print("\n" + "─" * 65 + "\n")

    demo_c_interquartile()
    print("\n" + "─" * 65 + "\n")

    demo_d_visualise_distances()
    print("\n" + "─" * 65 + "\n")

    demo_e_semantic_then_size()

    print_takeaways()
