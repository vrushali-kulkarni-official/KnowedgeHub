"""
production_chunking_pipeline.py
════════════════════════════════════════════════════════════════════
Production-Grade RAG: Multi-Strategy Chain Chunking Pipeline
════════════════════════════════════════════════════════════════════

Your learning progression so far:
  [✓] Basic RAG       → TextLoader + FAISS + RunnablePassthrough chain
  [✓] Docling loader  → multi-format document ingestion
  [→] THIS FILE       → production chunking (you are here)
  [ ] Hybrid search   → dense + sparse retrieval
  [ ] Re-ranking      → cross-encoder re-rankers
  [ ] Evaluation      → RAGAS, faithfulness, relevance scores

════════════════════════════════════════════════════════════════════
WHAT IS CHAIN CHUNKING?
════════════════════════════════════════════════════════════════════

Chain chunking means applying multiple chunking strategies in a
SEQUENTIAL PIPELINE where the output of stage N is the INPUT of stage N+1.

No single strategy is perfect:
  ┌──────────────────────┬─────────────────────┬──────────────────────┐
  │ Strategy             │ What it's good at   │ What it misses       │
  ├──────────────────────┼─────────────────────┼──────────────────────┤
  │ Structural           │ Respects doc layout │ Sections can be huge │
  │ Semantic             │ Topic coherence     │ Can cross sections   │
  │ Token-aware          │ Hard size limits    │ No semantic meaning  │
  │ Recursive            │ Natural boundaries  │ No structure/meaning │
  └──────────────────────┴─────────────────────┴──────────────────────┘

The chain fixes each one's weakness with the next stage:

  Raw Document
    │
    ▼ Stage 1: STRUCTURAL  ← "Where are the logical section breaks?"
    │  Respects headers/sections. Gives each chunk its document address.
    │  Problem it leaves: sections can still be 5000+ tokens.
    │
    ▼ Stage 2: TOKEN GUARD  ← "Are any sections absurdly large?"
    │  Coarsely splits anything too large before semantic analysis.
    │  Problem it leaves: chunks may span multiple topics.
    │
    ▼ Stage 3: SEMANTIC     ← "Where does the topic actually change?"
    │  Uses embeddings to find real topic boundaries within each section.
    │  Problem it leaves: semantic chunks can still exceed LLM token limit.
    │
    ▼ Stage 4: RECURSIVE    ← "Does every chunk fit in the LLM context?"
    │  Hard token-limit enforcement. Splits on sentence → word → char.
    │  This is the final safety net.
    │
    ▼ Stage 5: METADATA     ← "Can we filter/rank/debug these chunks?"
       Enriches every chunk with token count, position, section path, etc.
       Enables filtered retrieval in production.

This is assembly-line thinking: each stage has ONE job and hands off to next.

════════════════════════════════════════════════════════════════════
INSTALLS
════════════════════════════════════════════════════════════════════
pip install langchain langchain-experimental langchain-community
pip install langchain-huggingface sentence-transformers
pip install tiktoken faiss-cpu
"""

# ── Core imports ───────────────────────────────────────────────────
from langchain.text_splitter import (
    RecursiveCharacterTextSplitter,  # The workhorse — tried-and-true baseline
    MarkdownHeaderTextSplitter,       # Structure-aware: understands heading hierarchy
)
from langchain_experimental.text_splitter import SemanticChunker  # Embedding-based boundary detection
from langchain_huggingface import HuggingFaceEmbeddings
from langchain.schema import Document
from typing import List, Callable
import tiktoken  # OpenAI's tokenizer — accurate token counter for most modern LLMs


# ════════════════════════════════════════════════════════════════════
# PART 1 — INDIVIDUAL TECHNIQUES  (understand each one in isolation)
# ════════════════════════════════════════════════════════════════════


# ──────────────────────────────────────────────────────────────────
# TECHNIQUE 1: RECURSIVE CHARACTER SPLITTING
# ──────────────────────────────────────────────────────────────────
"""
THE WORKHORSE. Used as a component inside almost every production pipeline.

How it actually works (step by step):
  1. Try to split the text on '\n\n' (paragraph breaks)
  2. If any piece is STILL bigger than chunk_size, try splitting it on '\n'
  3. Still too big? Try '. ' (end of sentence)
  4. Still too big? Try ' ' (word boundary)
  5. Absolute last resort: '' (split character by character)

The "recursive" part: it recursively applies smaller splits ONLY to the
pieces that are still over the limit — it doesn't mangle already-small pieces.

Analogy: Like tearing a document by hand —
  First tear by full pages, then by paragraphs, then by sentences,
  then by words. You only go smaller when you have to.

chunk_overlap explained with a concrete example:
  chunk_size=20, overlap=5, text = "AAAAAABBBBBCCCCCDDDDD"

  chunk_overlap=0: "AAAAAABBBBBCCCCCDDDDD" splits to:
    ["AAAAAABBBBB", "CCCCCDDDDD"]

  chunk_overlap=5: "AAAAAABBBBBCCCCCDDDDD" splits to:
    ["AAAAAABBBBB", "BBBBBCCCCC", "CCCCCDDDDD"]
    Notice how "BBBBB" appears in both the 1st and 2nd chunk!

  Why overlap? If the answer to a query spans a chunk boundary
  without overlap: chunk1 ends with "The result is" and chunk2 starts
  with "42 which proves..." — the retriever might miss it!
  With overlap: both chunks contain "The result is 42" — retrieval succeeds.
"""

recursive_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,     # Max characters per chunk. NOT tokens — see Technique 3.
    chunk_overlap=200,   # Characters shared between consecutive chunks (20% overlap is typical)

    length_function=len,  # How to measure "size" — can swap for token counter (see below)!

    separators=[
        "\n\n",  # 1st choice: paragraph break (most natural boundary)
        "\n",    # 2nd choice: line break
        ". ",    # 3rd choice: sentence end — NOTE the space! Avoids splitting "Dr. Smith"
        "! ",    # Exclamation sentences
        "? ",    # Question sentences
        "; ",    # Semicolon (clause boundary — less disruptive than full sentence split)
        ", ",    # Comma (minor pause — used only when nothing else works)
        " ",     # Word boundary (splits into individual words as last meaningful option)
        "",      # Absolute last resort: individual characters
    ],

    add_start_index=True,  # Adds "start_index" to metadata — tells you byte offset in original
                           # Useful for: source highlighting, deduplication, debugging
)


# ──────────────────────────────────────────────────────────────────
# TECHNIQUE 2: STRUCTURE-AWARE / MARKDOWN HEADER SPLITTING
# ──────────────────────────────────────────────────────────────────
"""
Splits a document by its HEADING HIERARCHY instead of size.

Why this matters in production:
  Imagine a 10-page technical manual. Without structural splitting,
  a size-based chunker might produce a chunk that starts in the
  "Installation" section and ends in the "Troubleshooting" section.
  That chunk is useless — it answers NEITHER installation NOR troubleshooting queries.

  Structural splitting ensures: one section = one or more chunks, never mixed.

The METADATA superpower:
  Each chunk gets metadata describing WHERE in the document it came from:
    {"h1": "Python Guide", "h2": "Installation", "h3": "Windows"}

  This enables FILTERED retrieval in production:
    vectorstore.similarity_search(
        query="how do I install Python?",
        filter={"h2": "Installation"}  ← only search THIS section!
    )

  Works perfectly with DOCLING output — Docling converts PDFs/HTML to markdown,
  so the heading structure from the original document is preserved!

strip_headers=False means:
  The heading text ("## Installation") stays INSIDE the chunk content.
  Good for retrieval — the chunk itself says what section it's from.
  strip_headers=True would remove the heading, giving smaller but context-poor chunks.
"""

HEADERS_TO_SPLIT_ON = [
    ("#",    "h1"),   # H1 heading text stored in metadata under key "h1"
    ("##",   "h2"),   # H2 heading text stored under key "h2"
    ("###",  "h3"),   # H3 heading text stored under key "h3"
    ("####", "h4"),   # H4 heading text stored under key "h4"
]

markdown_header_splitter = MarkdownHeaderTextSplitter(
    headers_to_split_on=HEADERS_TO_SPLIT_ON,
    strip_headers=False,  # Keep "## Installation" text inside the chunk
)

# Example of what this produces:
# Input:  "# Python Guide\n## Installation\nRun the installer.\n## Config\nEdit .env"
# Output: [
#   Document("# Python Guide\n## Installation\nRun the installer.", {"h1": "Python Guide", "h2": "Installation"}),
#   Document("## Config\nEdit .env",                                {"h1": "Python Guide", "h2": "Config"}),
# ]


# ──────────────────────────────────────────────────────────────────
# TECHNIQUE 3: TOKEN-AWARE SPLITTING
# ──────────────────────────────────────────────────────────────────
"""
ALWAYS USE IN PRODUCTION. Character count ≠ token count.

Why character counting fails:
  LLMs have TOKEN limits, not character limits.
  Different text content tokenizes VERY differently:

  "Hello world"                = 2 tokens     (5.5 chars/token)
  "supercalifragilistic"       = 6 tokens     (3.3 chars/token)
  "你好世界"                   = 4-8 tokens   (0.5-1 chars/token)
  "from langchain import..."   = ~6 tokens    (dense code is token-heavy)

  With chunk_size=4000 chars, one chunk might be 800 tokens,
  another might be 2400 tokens. You have NO IDEA what you're sending to the LLM.

The fix: change `length_function` from `len` (chars) to a token counter.
  This is the single most impactful change you can make to a naive splitter.

cl100k_base tokenizer:
  Used by GPT-3.5, GPT-4, text-embedding-ada-002, and Claude (approximately).
  For HuggingFace models, the tokenizer differs slightly but cl100k_base
  is a very good approximation for chunk sizing purposes.
"""

# Step 1: Set up the token counter
_encoding = tiktoken.get_encoding("cl100k_base")  # OpenAI's tokenizer, widely applicable


def count_tokens(text: str) -> int:
    """
    Counts the actual number of tokens in a string.
    Swap this in as `length_function` to make ANY splitter token-aware.
    """
    return len(_encoding.encode(text))


# Step 2: Same RecursiveCharacterTextSplitter, but now measuring in TOKENS
token_aware_splitter = RecursiveCharacterTextSplitter(
    chunk_size=512,               # 512 TOKENS per chunk (not characters!)
    chunk_overlap=50,             # 50 TOKEN overlap (~1-3 sentences of overlap)
    length_function=count_tokens, # ← THE KEY CHANGE. Everything else stays the same.
    separators=["\n\n", "\n", ". ", " ", ""],
)

# One-liner tip for production:
# SAFE_CHARS_PER_TOKEN = 3.5  (conservative estimate for English text)
# chunk_size_chars = desired_tokens * SAFE_CHARS_PER_TOKEN
# But using count_tokens directly is always more accurate.


# ──────────────────────────────────────────────────────────────────
# TECHNIQUE 4: SEMANTIC CHUNKING
# ──────────────────────────────────────────────────────────────────
"""
The "intelligent" splitter. Splits where MEANING changes, not where size limits are hit.

How the algorithm works under the hood:
  1. Split text into individual sentences (simple sentence tokenization)
  2. For each sentence, create an embedding (a vector of ~384 numbers representing meaning)
  3. Calculate cosine similarity between every pair of consecutive sentences:
       sim(sentence_i, sentence_i+1)
  4. Find where similarity DROPS significantly → that's a topic boundary → SPLIT HERE

  High similarity (0.85+) → sentences are about the same thing → keep together
  Low similarity (0.30-)  → topic has changed → split the chunk here

Concrete example:
  S1: "Python is an interpreted language."           ─┐ high sim 0.91
  S2: "It runs on Linux, Mac, and Windows."          ─┘ (both about Python)
  S3: "Machine learning needs large training sets."  ─┐ low sim 0.28 ← SPLIT
  S4: "Neural networks learn from examples."         ─┘ (both about ML)

  Result: Chunk A = [S1, S2], Chunk B = [S3, S4]
  These chunks are SEMANTICALLY COHERENT — each answers a different kind of query.

breakpoint_threshold_type options:
  "percentile"         → Find all similarity scores between consecutive sentences.
                         Split at the bottom Nth percentile of scores.
                         breakpoint_threshold_amount=70 means:
                         "split at the 30% of sentence pairs with lowest similarity"
                         Higher = more splits (smaller, precise chunks)
                         Lower  = fewer splits (larger, broader chunks)

  "standard_deviation" → Split where similarity drops > N standard deviations below mean.
                         More adaptive to each document's specific style.

  "interquartile"      → Split using IQR outlier detection.
                         Good for documents with very varied content density.

Production tradeoff:
  PRO: Chunks are semantically coherent → higher retrieval precision
  CON: Slow (embeds every sentence at index time), variable chunk sizes
  CON: Needs the SAME embedding model for both chunking AND retrieval
"""

# Initialize embeddings (same model you're already using for retrieval!)
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True},  # Required for cosine similarity
)

semantic_splitter = SemanticChunker(
    embeddings=embeddings,
    breakpoint_threshold_type="percentile",
    breakpoint_threshold_amount=70,  # Tune this: 60-80 is the typical production range
)


# ════════════════════════════════════════════════════════════════════
# PART 2 — PRODUCTION CHAIN CHUNKING PIPELINE
# ════════════════════════════════════════════════════════════════════


class ProductionRAGChunker:
    """
    Chain chunking pipeline: chains 4 strategies sequentially.

    Design principle: each stage has ONE responsibility and one failure mode.
    The chain covers each stage's failure mode with the next stage.

    Stage 1 (Structural)  → splits at document section boundaries
                            failure mode: sections can still be 5000+ tokens
    Stage 2 (Token Guard) → prevents oversized sections from reaching Stage 3
                            failure mode: chunks may span multiple topics
    Stage 3 (Semantic)    → splits at topic boundaries within each section
                            failure mode: semantic chunks can still exceed token limit
    Stage 4 (Recursive)   → hard token limit enforcement
                            failure mode: none — this is the safety net
    Stage 5 (Metadata)    → enriches chunks for filtered retrieval + debugging

    Usage:
        chunker = ProductionRAGChunker(embeddings=my_embeddings, max_chunk_tokens=512)
        chunks = chunker.chunk(documents)   # ← drop-in after your DoclingLoader
        vectorstore = FAISS.from_documents(chunks, embeddings)
    """

    def __init__(
        self,
        embeddings,
        max_chunk_tokens: int = 512,   # Hard upper limit on tokens per final chunk
        overlap_tokens: int = 50,       # Token overlap between consecutive chunks
        semantic_threshold: int = 70,   # Semantic split aggressiveness (60-80 typical)
        verbose: bool = True,           # Print pipeline progress
    ):
        self.embeddings = embeddings
        self.max_chunk_tokens = max_chunk_tokens
        self.overlap_tokens = overlap_tokens
        self.verbose = verbose

        # Set up the token counter once (reused by all stages)
        _enc = tiktoken.get_encoding("cl100k_base")
        self.count_tokens: Callable[[str], int] = lambda text: len(_enc.encode(text))

        # ── Stage 1: Markdown/Header structural splitter ─────────────────
        self._structural_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[
                ("#", "h1"), ("##", "h2"), ("###", "h3"), ("####", "h4"),
            ],
            strip_headers=False,   # Keep header text inside chunk for context
        )

        # ── Stage 2: Token guard (coarse split — 4× final limit) ─────────
        # Why 4× and not 1×? Because we want Stage 3 (semantic) to have
        # enough context to detect topic shifts. If we split too aggressively
        # here, we'll prevent semantic from finding the real boundaries.
        # 4× is a commonly used heuristic in production pipelines.
        self._guard_splitter = RecursiveCharacterTextSplitter(
            chunk_size=max_chunk_tokens * 4,   # Generous: 4× final limit
            chunk_overlap=100,
            length_function=self.count_tokens,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

        # ── Stage 3: Semantic splitter ────────────────────────────────────
        self._semantic_splitter = SemanticChunker(
            embeddings=embeddings,
            breakpoint_threshold_type="percentile",
            breakpoint_threshold_amount=semantic_threshold,
        )

        # ── Stage 4: Final recursive split — hard token limit enforcement ─
        self._final_splitter = RecursiveCharacterTextSplitter(
            chunk_size=max_chunk_tokens,
            chunk_overlap=overlap_tokens,
            length_function=self.count_tokens,  # Token-aware, not character-aware
            separators=[
                "\n\n",  # 1st: paragraph (best natural boundary)
                "\n",    # 2nd: line break
                ". ",    # 3rd: sentence (space after period — avoids "Dr. Smith")
                "! ",    # Exclamation sentence
                "? ",    # Question sentence
                "; ",    # Semicolon clause
                " ",     # Word boundary
                "",      # Character (absolute last resort)
            ],
        )

    # ─────────────────────────────────────────────────────────────────────
    # STAGE 1: STRUCTURAL SPLITTING
    # ─────────────────────────────────────────────────────────────────────
    def _stage1_structural(self, documents: List[Document]) -> List[Document]:
        """
        Split documents along heading/section boundaries.

        What it does:
          Takes each document, finds its markdown heading structure,
          and produces one Document per logical section.
          Each output Document gets metadata describing its position in the hierarchy.

        Why it's first in the chain:
          Section boundaries are MORE IMPORTANT than topic boundaries or token limits.
          A chunk should NEVER span two different document sections.
          If we did semantic splitting first, it could produce a chunk that starts
          in the "Installation" section and ends in the "Troubleshooting" section —
          structurally meaningless.

        Metadata inheritance:
          Output chunks get BOTH the original document metadata (source, page, etc.)
          AND the new structural metadata (h1, h2, h3).
          This merged metadata is preserved through ALL subsequent stages.

        Input/Output example:
          IN:  [Document("# Intro\ncontent1\n## Details\ncontent2",
                          meta={"source": "guide.pdf"})]

          OUT: [Document("# Intro\ncontent1",
                          meta={"source": "guide.pdf", "h1": "Intro"}),
                Document("## Details\ncontent2",
                          meta={"source": "guide.pdf", "h1": "Intro", "h2": "Details"})]
        """
        output = []

        for doc in documents:
            try:
                # Split this document by markdown headers
                sections = self._structural_splitter.split_text(doc.page_content)

                for section in sections:
                    # Merge parent metadata + structural metadata.
                    # Parent meta (source, page) + structural meta (h1, h2, h3)
                    # If keys conflict, structural metadata wins (more specific).
                    combined_meta = {**doc.metadata, **section.metadata}

                    output.append(Document(
                        page_content=section.page_content,
                        metadata=combined_meta,
                    ))

            except Exception:
                # Document has no markdown structure (plain text, CSV, etc.)
                # Pass through unchanged — later stages will still process it.
                output.append(doc)

        self._log(f"Stage 1 | {len(documents):>4} docs → {len(output):>4} structural sections")
        return output

    # ─────────────────────────────────────────────────────────────────────
    # STAGE 2: TOKEN GUARD (coarse oversized-section prevention)
    # ─────────────────────────────────────────────────────────────────────
    def _stage2_token_guard(self, documents: List[Document]) -> List[Document]:
        """
        Pre-split any structurally oversized sections before semantic analysis.

        Problem this stage solves:
          Stage 1 can produce very large sections — a single chapter might be
          10,000 tokens. SemanticChunker works by embedding every SENTENCE
          in the input. A 10,000-token section might have 400 sentences,
          meaning 400 embedding calls just for that one section. That's slow
          and wastes compute.

        Solution:
          Apply a GENEROUS token limit (4× the final limit) before semantic analysis.
          This reduces the worst-case sentence count per section significantly
          while still giving the semantic chunker enough context to work with.

        Why 4× and not 1×?
          If we used the final limit here, we'd be doing the semantic chunker's
          job for it (chunking too finely before it can find semantic boundaries).
          4× is a balance: prevent absurdly large inputs to Stage 3,
          but don't over-constrain the semantic analysis.

        Note: This stage uses token-aware splitting (length_function=count_tokens).
        A "4000 char" guard would be inaccurate — a "2048 token" guard is precise.
        """
        output = self._guard_splitter.split_documents(documents)
        self._log(f"Stage 2 | {len(documents):>4} sections → {len(output):>4} token-guarded sections")
        return output

    # ─────────────────────────────────────────────────────────────────────
    # STAGE 3: SEMANTIC SPLITTING
    # ─────────────────────────────────────────────────────────────────────
    def _stage3_semantic(self, documents: List[Document]) -> List[Document]:
        """
        Split each section at semantic topic boundaries using embedding similarity.

        What it does:
          For each section from Stage 2, embeds its sentences and finds where
          the topic meaningfully changes. Produces smaller, topically coherent chunks.

        Critical design decision — process each document INDEPENDENTLY:
          We never pass ALL documents into SemanticChunker at once.
          If we did, a semantic boundary might cross a structural boundary
          (a topic shift at the END of Section A and START of Section B
          might be detected as a single semantic split, producing a chunk
          that spans two sections — exactly what Stage 1 was supposed to prevent).

          Processing each document independently preserves Stage 1's work.

        Minimum length guard:
          Sections under 100 tokens don't benefit from semantic splitting
          (there aren't enough sentences to compare similarity scores).
          We skip them to avoid API calls and potential errors.

        Metadata propagation (CRITICAL):
          Each semantic sub-chunk INHERITS the parent section's metadata.
          Without this, we'd lose the structural metadata from Stage 1!
          Every final chunk must know it came from h1="Intro", h2="Installation".

        Example:
          IN:  Document("Python syntax is clean. No semicolons needed.
                         Java requires semicolons. It runs on the JVM.",
                         meta={"h1": "Languages", "h2": "Comparison"})

          Semantic analysis:
            sim("Python syntax is clean.", "No semicolons needed.") = 0.89 → same topic
            sim("No semicolons needed.", "Java requires semicolons.") = 0.71 → same topic
            sim("Java requires semicolons.", "It runs on the JVM.") = 0.84 → same topic
            (In this short example, maybe no split — depends on threshold)

          OUT: [Document("Python syntax is clean. No semicolons needed.",
                          meta={"h1": "Languages", "h2": "Comparison"}),   # inherited!
                Document("Java requires semicolons. It runs on the JVM.",
                          meta={"h1": "Languages", "h2": "Comparison"})]   # inherited!
        """
        output = []

        for doc in documents:
            # Skip semantic analysis for very short sections
            if self.count_tokens(doc.page_content) < 100:
                output.append(doc)
                continue

            try:
                # Process THIS SECTION ALONE — never batch across sections
                semantic_chunks = self._semantic_splitter.split_documents([doc])

                for chunk in semantic_chunks:
                    # Propagate the parent's metadata (h1, h2, source, page, etc.)
                    # to EVERY child chunk produced by semantic splitting.
                    # Without this, semantic chunks lose their structural context.
                    chunk.metadata = {**doc.metadata, **chunk.metadata}
                    output.append(chunk)

            except Exception as exc:
                # Semantic splitting can fail on edge cases:
                # - Very short text (only 1-2 sentences, nothing to compare)
                # - Unusual unicode characters
                # - Empty strings
                # Always fall back to keeping the chunk as-is.
                self._log(f"  ⚠ Semantic fallback: {str(exc)[:60]}")
                output.append(doc)

        self._log(f"Stage 3 | {len(documents):>4} guarded sections → {len(output):>4} semantic chunks")
        return output

    # ─────────────────────────────────────────────────────────────────────
    # STAGE 4: RECURSIVE FINAL SPLIT (hard token limit enforcement)
    # ─────────────────────────────────────────────────────────────────────
    def _stage4_final_split(self, documents: List[Document]) -> List[Document]:
        """
        THE SAFETY NET. Hard enforcement of the token limit.

        Problem this stage solves:
          Semantic chunks can still be too large for the LLM context window.
          A single long paragraph might be semantically coherent (one topic)
          but 900 tokens — above our 512-token limit.

          This stage GUARANTEES that no chunk exceeds max_chunk_tokens.

        Why it's last:
          If we applied token limits earlier, we'd be over-constraining
          the semantic analysis. The semantic chunker needs to see the full
          topic context to detect boundaries correctly. By applying the hard
          limit AFTER semantic splitting, we preserve semantic coherence as
          much as possible and only force-split when absolutely necessary.

        Uses recursive splitting (not simple character truncation!) so it
        still respects sentence → word → character boundaries.
        It won't cut "The answer is" from "42 which proves our hypothesis."

        After this stage: EVERY chunk is guaranteed ≤ max_chunk_tokens.
        """
        output = self._final_splitter.split_documents(documents)
        self._log(f"Stage 4 | {len(documents):>4} semantic chunks → {len(output):>4} final chunks")
        return output

    # ─────────────────────────────────────────────────────────────────────
    # STAGE 5: METADATA ENRICHMENT
    # ─────────────────────────────────────────────────────────────────────
    def _stage5_metadata(self, documents: List[Document]) -> List[Document]:
        """
        Enrich every chunk with production-useful metadata.

        In a production RAG system, rich metadata enables:
          1. FILTERED RETRIEVAL:
               vectorstore.similarity_search(query, filter={"h2": "Installation"})
               → only searches chunks from the Installation section

          2. HYBRID RANKING:
               Prefer longer, more complete chunks over tiny fragments
               using metadata["token_count"] as a ranking signal

          3. PARENT-CHILD NAVIGATION:
               When a chunk is retrieved, fetch its adjacent chunks
               using metadata["prev_chunk_id"] and metadata["next_chunk_id"]
               This is used in "Small-to-Big" retrieval patterns

          4. DEBUGGING:
               When you ask "why did the retriever return this?",
               metadata["section_path"] and metadata["content_preview"] tell you
               exactly where in the document this chunk came from

          5. ANALYTICS:
               Track which sections are most frequently retrieved,
               identify "dead" sections that never get retrieved
        """
        total = len(documents)

        for idx, doc in enumerate(documents):
            # Build a human-readable section path from structural metadata
            # e.g., "Python Guide > Installation > Windows" or just "root"
            section_parts = [
                doc.metadata.get("h1", ""),
                doc.metadata.get("h2", ""),
                doc.metadata.get("h3", ""),
                doc.metadata.get("h4", ""),
            ]
            section_path = " > ".join(p for p in section_parts if p) or "root"

            doc.metadata.update({
                # ── Identity ──────────────────────────────────────────────
                "chunk_id": idx,              # Unique sequential ID in this batch
                "total_chunks": total,        # Total chunks from this pipeline run

                # ── Size metrics (for filtering and ranking) ──────────────
                "token_count":  self.count_tokens(doc.page_content),
                "char_count":   len(doc.page_content),
                "word_count":   len(doc.page_content.split()),

                # ── Position (for "fetch adjacent chunks" pattern) ────────
                "is_first_chunk": idx == 0,
                "is_last_chunk":  idx == total - 1,
                "prev_chunk_id":  idx - 1 if idx > 0 else None,
                "next_chunk_id":  idx + 1 if idx < total - 1 else None,

                # ── Navigation ────────────────────────────────────────────
                # Human-readable location in the document hierarchy
                "section_path": section_path,

                # ── Debugging ─────────────────────────────────────────────
                # First 80 chars (no newlines) — lets you identify the chunk
                # without loading full page_content
                "content_preview": doc.page_content[:80].replace("\n", " ").strip(),
            })

        return documents

    # ─────────────────────────────────────────────────────────────────────
    # MAIN PUBLIC METHOD — run the full chain
    # ─────────────────────────────────────────────────────────────────────
    def chunk(self, documents: List[Document]) -> List[Document]:
        """
        Execute the full chain chunking pipeline.

        This is the DROP-IN replacement for your current splitter.
        Replace:
            chunks = recursive_splitter.split_documents(docs)
        With:
            chunks = chunker.chunk(docs)

        Everything downstream (FAISS.from_documents, retriever, RAG chain)
        works exactly the same — chunks are still a List[Document].
        """
        self._log(f"\n{'━' * 60}")
        self._log(f" Chain Chunking Pipeline  |  {len(documents)} input document(s)")
        self._log(f"{'━' * 60}")

        # Run each stage, passing its output as the next stage's input
        chunks = self._stage1_structural(documents)   # Coarse: by structure
        chunks = self._stage2_token_guard(chunks)      # Guard: prevent huge sections
        chunks = self._stage3_semantic(chunks)          # Fine: by topic
        chunks = self._stage4_final_split(chunks)       # Safe: enforce token limit
        chunks = self._stage5_metadata(chunks)          # Enrich: add production metadata

        # Final validation report
        oversized = [c for c in chunks if self.count_tokens(c.page_content) > self.max_chunk_tokens]
        avg_tokens = sum(self.count_tokens(c.page_content) for c in chunks) // max(len(chunks), 1)

        self._log(f"\n  ✓ Pipeline complete: {len(documents)} docs → {len(chunks)} chunks")
        self._log(f"  ✓ Avg token count per chunk: {avg_tokens}")
        if oversized:
            self._log(f"  ⚠ {len(oversized)} chunks still exceed {self.max_chunk_tokens} tokens")
        self._log(f"{'━' * 60}\n")

        return chunks

    def _log(self, msg: str) -> None:
        """Internal logger — respects verbose flag."""
        if self.verbose:
            print(msg)


# ════════════════════════════════════════════════════════════════════
# PART 3 — USAGE: DROP INTO YOUR EXISTING RAG PIPELINE
# ════════════════════════════════════════════════════════════════════

def build_rag_with_chain_chunking():
    """
    Shows how chain chunking plugs into the RAG pipeline you've already built.

    Your current pipeline:
      DoclingLoader → RecursiveCharacterTextSplitter → HuggingFaceEmbeddings → FAISS → chain

    Updated pipeline:
      DoclingLoader → ProductionRAGChunker → HuggingFaceEmbeddings → FAISS → chain
      (only the chunker changes — everything else stays the same)
    """
    from langchain_community.vectorstores import FAISS
    from langchain_core.runnables import RunnablePassthrough
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate

    # ── 1. Load documents (Docling output → markdown with structure preserved) ──
    # Replace this with your DoclingLoader
    sample_docs = [
        Document(
            page_content="""
# Python Programming Guide

Python is a high-level language known for readability.
Guido van Rossum created it in 1991.
It runs on Linux, macOS, and Windows.

## Installation

### Windows

Download the installer from python.org.
Run the .exe file as administrator.
Check "Add Python to PATH" — this is critical!
After installation, verify: open cmd and type `python --version`.

### Linux

Most Linux distributions include Python.
For Ubuntu: `sudo apt-get install python3`
For Fedora: `sudo dnf install python3`

## Core Language Features

### Variables and Types

Python uses dynamic typing — no type declarations needed.
Variables are just names pointing to objects.
Common types: int, float, str, list, dict, tuple, bool, None.

### Functions

Define functions with `def`. They accept positional and keyword arguments.
Functions are first-class objects — you can pass them as arguments.
Use `*args` for variable positional arguments, `**kwargs` for keyword arguments.

## Advanced Topics

### Async Programming

Python supports async/await since version 3.5.
Use `asyncio` for I/O-bound concurrent operations.
The event loop manages coroutine scheduling.
This is critical for building high-performance web scrapers and API clients.

### Decorators

Decorators wrap functions to add behavior without modifying source code.
The `@property` decorator creates managed attributes.
Common use cases: caching, logging, authentication, rate limiting.
""",
            metadata={"source": "python_guide.pdf", "page": 1, "doc_type": "tutorial"}
        )
    ]

    # ── 2. Initialize embeddings ─────────────────────────────────────────────
    embeddings_model = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )

    # ── 3. Chain chunking (the new step) ────────────────────────────────────
    chunker = ProductionRAGChunker(
        embeddings=embeddings_model,
        max_chunk_tokens=256,     # 256 tokens for demo; use 512 in production
        overlap_tokens=30,
        semantic_threshold=70,
        verbose=True,
    )

    chunks = chunker.chunk(sample_docs)

    # Inspect a few chunks to see the difference
    print("\n── SAMPLE CHUNKS ──")
    for chunk in chunks[:3]:
        print(f"\nContent preview : {chunk.metadata['content_preview']}")
        print(f"Token count     : {chunk.metadata['token_count']}")
        print(f"Section path    : {chunk.metadata['section_path']}")
        print(f"Chunk ID        : {chunk.metadata['chunk_id']} / {chunk.metadata['total_chunks']}")

    # ── 4. Build FAISS vectorstore (same as your existing code) ─────────────
    vectorstore = FAISS.from_documents(chunks, embeddings_model)
    retriever = vectorstore.as_retriever(
        search_type="mmr",      # MMR = Maximal Marginal Relevance
                                # Balances relevance AND diversity of retrieved chunks
                                # Better than pure similarity search in production
        search_kwargs={
            "k": 6,             # Retrieve top 6 chunks
            "fetch_k": 20,      # Consider top 20 by similarity, then apply MMR to pick 6
            "lambda_mult": 0.5, # 0.0 = max diversity, 1.0 = max similarity, 0.5 = balanced
        }
    )

    # ── 5. RAG chain (same as your existing code) ────────────────────────────
    def format_docs(docs: List[Document]) -> str:
        """
        Format retrieved chunks for the prompt.
        In production: include section_path to give LLM source context.
        """
        return "\n\n".join(
            f"[Source: {doc.metadata.get('section_path', 'unknown')}]\n{doc.page_content}"
            for doc in docs
        )

    prompt = ChatPromptTemplate.from_template("""
Answer the question based only on the following context.
If the context doesn't contain the answer, say "I don't know."

Context:
{context}

Question: {question}

Answer:""")

    # Your existing chain pattern — nothing changes here
    # (Note: swap out the LLM with whatever you're using)
    # rag_chain = (
    #     RunnablePassthrough.assign(
    #         context=(lambda x: x["question"]) | retriever | format_docs
    #     )
    #     | prompt
    #     | llm                   ← your existing LLM
    #     | StrOutputParser()
    # )

    print("\n── RAG PIPELINE READY ──")
    print(f"Vectorstore loaded with {len(chunks)} chunks")
    print("Chain chunking pipeline integrated successfully.")

    return vectorstore, retriever, chunks


# ════════════════════════════════════════════════════════════════════
# PART 4 — QUICK REFERENCE: WHEN TO USE EACH TECHNIQUE
# ════════════════════════════════════════════════════════════════════

"""
DECISION GUIDE — choosing the right stage configuration:

Document type                 | Recommended config
──────────────────────────────┬─────────────────────────────────────────────
Structured docs               │ All 4 stages (markdown header splitter works)
  (PDFs via Docling,          │ semantic_threshold=70-75
   wikis, technical manuals)  │
──────────────────────────────┼─────────────────────────────────────────────
Plain text / prose            │ Skip Stage 1 (no headers to split on)
  (articles, books,           │ Keep Stages 2, 3, 4
   transcripts)               │ semantic_threshold=65 (more aggressive)
──────────────────────────────┼─────────────────────────────────────────────
Code files                    │ Skip Stage 3 (semantic on code is unreliable)
  (source code, notebooks)    │ Use Stage 1 with code-specific separators
                              │ Use Stage 4 with code separators: ["\nclass", "\ndef", "\n\n"]
──────────────────────────────┼─────────────────────────────────────────────
Short documents               │ Use only Stage 4 (recursive + token-aware)
  (FAQ entries, data sheets,  │ Stages 1-3 add overhead without benefit
   single-topic documents)    │ on already-small, single-topic documents
──────────────────────────────┴─────────────────────────────────────────────

Token limit guidance:
  max_chunk_tokens=256  → Very granular. High precision, more chunks to search.
  max_chunk_tokens=512  → Standard production default. Good balance.
  max_chunk_tokens=1024 → Larger context per chunk. Fewer retrievals needed.
                          Risk: LLM gets overwhelmed with information per chunk.

Overlap guidance:
  overlap = 10% of chunk_size is a common rule of thumb.
  512 tokens → 50 token overlap
  1024 tokens → 100 token overlap
"""

if __name__ == "__main__":
    build_rag_with_chain_chunking()
