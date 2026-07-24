"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  CHUNKING STRATEGY #2: RECURSIVE CHARACTER SPLITTING  (The Modern Default)   ║
╚══════════════════════════════════════════════════════════════════════════════╝

WHY THIS EXISTS
───────────────
Strategy 1 (fixed-size) had a fatal flaw: if the text between two separators
is larger than chunk_size, it just cuts mid-character. No fallback.

RecursiveCharacterTextSplitter solves this with a **cascade of separators**
tried in priority order:

  Priority list (default):  ["\n\n", "\n", " ", ""]

  Step 1: Try to split on "\n\n" (paragraph boundary — best option)
          If ALL resulting pieces fit in chunk_size → done! ✅
          If some pieces are still too large → recurse on those pieces ↓

  Step 2: Try to split those oversized pieces on "\n" (line boundary)
          If they all fit → done! ✅
          If still too large → recurse ↓

  Step 3: Try to split on " " (word boundary)
          If they all fit → done! ✅
          If still too large → recurse ↓

  Step 4: Split on "" (anywhere — last resort)
          This always produces sub-chunks ≤ chunk_size.

HOW OVERLAP WORKS HERE
──────────────────────
After all splits, consecutive chunks share `chunk_overlap` characters.
LangChain merges small splits BACK together (up to chunk_size) before
adding overlap, so you get max-density chunks without exceeding the limit.

VISUALISATION
─────────────
  Document → try \n\n splits → [A][B][C]
                                     ↑ C is too big
  C → try \n splits → [C1][C2][C3]
                           ↑ C2 is too big
  C2 → try space splits → [C2a][C2b]   ← all small enough now

  Final chunks: [A][B][C1][C2a][C2b][C3]  (with overlap added)

WHY IT'S THE DEFAULT
──────────────────────
  ✅ Respects paragraph/sentence/word boundaries in priority order
  ✅ Always produces chunks ≤ chunk_size (guaranteed)
  ✅ Works well on any prose text out of the box
  ✅ Zero extra dependencies

LANGCHAIN CLASS
───────────────
  RecursiveCharacterTextSplitter(
      separators=...,      # list of separators (default as above)
      chunk_size=...,      # max chars per chunk
      chunk_overlap=...,   # shared chars between consecutive chunks
      length_function=..., # how to measure (default: len = char count)
  )
"""

# ─── Imports ──────────────────────────────────────────────────────────────────

from langchain_text_splitters import RecursiveCharacterTextSplitter
from shared_data import PLAIN_TEXT, MARKDOWN_DOC, print_chunks


# ══════════════════════════════════════════════════════════════════════════════
# DEMO A: Default separators — the out-of-the-box behaviour
# ══════════════════════════════════════════════════════════════════════════════


def demo_a_default():
    """
    Using all defaults — this is what you already used in your first RAG.
    We'll inspect the output carefully to understand the recursive fallbacks.
    """
    splitter = RecursiveCharacterTextSplitter(
        # separators=["\n\n", "\n", " ", ""]  ← this is the default, shown explicitly
        chunk_size=400,
        chunk_overlap=40,  # 10% of chunk_size — a good rule of thumb
        length_function=len,  # character count (we'll upgrade to token count in Step 3)
    )

    chunks = splitter.split_text(PLAIN_TEXT)
    print_chunks(chunks, "2A: Default Recursive Split (size=400, overlap=40)")

    print("✅ No mid-word cuts!")
    print("✅ Paragraphs kept together when possible.")
    print("   Compare to Strategy 1A — major improvement with zero extra work.")


# ══════════════════════════════════════════════════════════════════════════════
# DEMO B: Custom separators for code
# The default separators are English-prose-optimised. For code, we want
# different boundaries: class → function → block → line → statement
# ══════════════════════════════════════════════════════════════════════════════


def demo_b_code_splitter():
    """
    RecursiveCharacterTextSplitter ships with language-specific separator
    presets. For Python code the priorities are:
        class → function def → blank line → newline → space → char

    This keeps function bodies together and splits at natural code boundaries.
    """
    sample_code = '''
def calculate_embeddings(texts: list[str], model_name: str) -> list[list[float]]:
    """
    Batch-embed a list of texts using a sentence-transformer model.
    Returns a list of embedding vectors.
    """
    from sentence_transformers import SentenceTransformer
    
    model = SentenceTransformer(model_name)
    embeddings = model.encode(texts, show_progress_bar=True)
    return embeddings.tolist()


def build_faiss_index(embeddings: list[list[float]]) -> object:
    """
    Build a FAISS flat L2 index from embedding vectors.
    Flat index = exact search, no approximation.
    """
    import numpy as np
    import faiss
    
    dim = len(embeddings[0])           # dimensionality of each vector
    index = faiss.IndexFlatL2(dim)     # L2 distance = Euclidean distance
    
    vectors = np.array(embeddings, dtype="float32")
    index.add(vectors)                 # add all vectors to the index
    
    return index


class RAGPipeline:
    """Full RAG pipeline: embed → store → retrieve → generate."""
    
    def __init__(self, model_name: str, llm):
        self.model_name = model_name
        self.llm = llm
        self.index = None
        self.documents = []
    
    def index_documents(self, docs: list[str]):
        embeddings = calculate_embeddings(docs, self.model_name)
        self.index = build_faiss_index(embeddings)
        self.documents = docs
    
    def query(self, question: str, k: int = 3) -> str:
        q_emb = calculate_embeddings([question], self.model_name)[0]
        # ... retrieve and generate
        pass
'''

    # LangChain provides pre-built language separators
    # from_language() sets the right separators for common languages
    from langchain_text_splitters import Language

    splitter = RecursiveCharacterTextSplitter.from_language(
        language=Language.PYTHON,  # uses Python-optimised separator list
        chunk_size=400,
        chunk_overlap=40,
    )

    chunks = splitter.split_text(sample_code)
    print_chunks(chunks, "2B: Python Code Splitter (from_language=PYTHON)")

    print("Available language presets:")
    # Show some of the available languages
    languages = [lang.value for lang in Language][:10]
    print(f"  {languages}  ... and more")


# ══════════════════════════════════════════════════════════════════════════════
# DEMO C: Comparing separator lists side by side
# This makes the "recursive" logic tangible.
# ══════════════════════════════════════════════════════════════════════════════


def demo_c_separator_comparison():
    """
    Same text, two different separator configurations.
    Shows how the separator list changes chunk quality.
    """
    # A short text where we can see the difference clearly
    tricky_text = (
        "Section A: Cats\n\n"
        "Cats are independent animals. They sleep 12-16 hours a day. "
        "They have excellent night vision and are natural hunters.\n\n"
        "Section B: Dogs\n\n"
        "Dogs are loyal companions. They form strong bonds with humans. "
        "Dogs were the first domesticated animals, over 15,000 years ago.\n\n"
        "Section C: Birds\n\n"
        "Birds are warm-blooded vertebrates. Over 10,000 species exist. "
        "They have feathers, wings, and lay eggs."
    )

    print("\n" + "═" * 65)
    print("  2C: Separator Comparison")
    print("═" * 65)

    # Config 1: Only paragraph-level (coarse)
    coarse = RecursiveCharacterTextSplitter(
        separators=["\n\n"],  # ONLY split on double newlines
        chunk_size=150,
        chunk_overlap=0,
    )
    coarse_chunks = coarse.split_text(tricky_text)
    print(f"\n[Config 1] separators=['\\n\\n'] only → {len(coarse_chunks)} chunks")
    for i, c in enumerate(coarse_chunks):
        # Replace newlines in display for readability
        display = c.replace("\n", "↵")
        print(f"  Chunk {i + 1} ({len(c):3d} chars): {display[:70]}...")

    # Config 2: Full cascade (fine)
    fine = RecursiveCharacterTextSplitter(
        separators=["\n\n", "\n", " ", ""],  # full cascade
        chunk_size=150,
        chunk_overlap=15,
    )
    fine_chunks = fine.split_text(tricky_text)
    print(f"\n[Config 2] separators=[\\n\\n, \\n, ' ', ''] → {len(fine_chunks)} chunks")
    for i, c in enumerate(fine_chunks):
        display = c.replace("\n", "↵")
        print(f"  Chunk {i + 1} ({len(c):3d} chars): {display[:70]}")


# ══════════════════════════════════════════════════════════════════════════════
# DEMO D: Getting Document objects (with metadata) instead of raw strings
# In real RAG, you work with Documents, not bare strings, so you can track
# which file each chunk came from.
# ══════════════════════════════════════════════════════════════════════════════


def demo_d_document_objects():
    """
    split_documents() takes LangChain Document objects and preserves metadata.
    This is what you use in real pipelines (not split_text).

    Each Document has:
      .page_content  →  the text
      .metadata      →  dict with source file, page number, etc.
    """
    from langchain_core.documents import Document

    # Simulate documents loaded from different files
    raw_docs = [
        Document(
            page_content=PLAIN_TEXT[:500],
            metadata={"source": "ai_intro.txt", "page": 1},
        ),
        Document(
            page_content=MARKDOWN_DOC[:500],
            metadata={"source": "rag_guide.md", "page": 1},
        ),
    ]

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=200,
        chunk_overlap=20,
    )

    # split_documents returns a list of Documents with PRESERVED metadata
    split_docs = splitter.split_documents(raw_docs)

    print("\n" + "═" * 65)
    print("  2D: Document Objects with Metadata")
    print("═" * 65)
    for i, doc in enumerate(split_docs):
        print(
            f"\nChunk {i + 1:02d} | source={doc.metadata['source']} | "
            f"{len(doc.page_content)} chars"
        )
        print(f"  {doc.page_content[:100].replace(chr(10), ' ')}...")

    print(f"\n→ {len(split_docs)} total chunks, all with source metadata preserved ✅")
    print("→ When you store these in FAISS, the metadata travels with the chunk.")
    print("  You can later filter retrieval by 'source' to restrict to one file.")


# ══════════════════════════════════════════════════════════════════════════════
# KEY TAKEAWAYS
# ══════════════════════════════════════════════════════════════════════════════


def print_takeaways():
    print("\n" + "=" * 65)
    print("KEY TAKEAWAYS — Recursive Character Splitting")
    print("=" * 65)
    print("""
  1. The DEFAULT separator list ["\n\n", "\n", " ", ""] handles most
     prose text correctly out of the box. Start here.

  2. It GUARANTEES chunk_size is respected — unlike CharacterTextSplitter.

  3. For code, use from_language(Language.PYTHON/JS/etc.) for better splits.

  4. Use split_documents() (not split_text()) in real pipelines so metadata
     (source file, page number) travels with each chunk.

  5. Rule of thumb for chunk parameters:
       chunk_size=500, chunk_overlap=50  →  balanced default for prose
       chunk_size=200, chunk_overlap=20  →  fine-grained for factoid QA
       chunk_size=1000, chunk_overlap=100 →  coarse for summarisation

  LIMITATION: Still measures size in characters, not tokens.
  A 500-char chunk might be 100 tokens or 400 tokens depending on the text.
  → Fix this in Strategy 3: Token-Aware Splitting.

  NEXT UP → Strategy 3: Token-Aware Splitting
  → python 03_token_aware.py
""")


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n🔍 Running all Recursive Character Splitting demos...\n")

    demo_a_default()
    print("\n" + "─" * 65 + "\n")

    demo_b_code_splitter()
    print("\n" + "─" * 65 + "\n")

    demo_c_separator_comparison()
    print("\n" + "─" * 65 + "\n")

    demo_d_document_objects()

    print_takeaways()
