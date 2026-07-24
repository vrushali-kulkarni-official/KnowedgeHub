"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  CHUNKING STRATEGY #5: STRUCTURE-AWARE SPLITTING  (Markdown & HTML)       ║
╚══════════════════════════════════════════════════════════════════════════════╝

THE CORE INSIGHT
────────────────
Documents are not just flat text — they have structure:
  # Chapter 1        ← major topic boundary
  ## Section 1.1     ← subsection boundary
  ### Subsection     ← sub-subsection boundary
  **Bold text**      ← emphasis, often key terms
  - bullet item      ← list structure
  <h1>, <h2>, <p>   ← HTML equivalents

If you ignore this structure, you might:
  ❌ Put a header in one chunk and its explanation in the next
  ❌ Merge two completely unrelated sections because they're close in the file
  ❌ Lose the metadata about which section a piece of text belongs to

Structure-aware splitting uses document markers as primary split points AND
captures them as metadata on every resulting chunk.

METADATA IS THE SUPERPOWER
────────────────────────────
When your chunks carry header metadata, you can:

  1. FILTER retrieval: "Only search chunks from Section 3"
     → vectorstore.similarity_search(query, filter={"Header 2": "Installation"})
  
  2. DISPLAY context: Show users "This answer is from: Chapter 2 > Setup"
  
  3. RERANK smarter: Boost chunks where query terms appear in the header
  
  4. HYBRID search: Combine semantic search with structural filtering

THE TWO-STAGE PIPELINE
───────────────────────
Step 1: MarkdownHeaderTextSplitter / HTMLHeaderTextSplitter
         → Splits at header boundaries
         → Each chunk gets header metadata
         → Chunks may still be very large (a whole section)

Step 2: RecursiveCharacterTextSplitter (or token-aware)
         → Splits oversized sections into smaller pieces
         → Metadata from step 1 is PRESERVED on all sub-chunks

LANGCHAIN CLASSES
─────────────────
  MarkdownHeaderTextSplitter    →  for .md files, README, documentation
  HTMLHeaderTextSplitter        →  for web pages, scraped HTML
  (both from langchain_text_splitters)
"""

# ─── Imports ──────────────────────────────────────────────────────────────────

from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    HTMLHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)
from shared_data import MARKDOWN_DOC, HTML_DOC, print_chunks


# ══════════════════════════════════════════════════════════════════════════════
# DEMO A: MarkdownHeaderTextSplitter — basic usage
# ══════════════════════════════════════════════════════════════════════════════

def demo_a_markdown_basic():
    """
    MarkdownHeaderTextSplitter splits at Markdown headers and attaches
    the header hierarchy as metadata to each chunk.
    
    We define which header levels to split on and what to call them in metadata.
    Any header level NOT listed is treated as content (not a split point).
    """
    # Define which headers to split on and their metadata key names
    headers_to_split_on = [
        ("#",   "Header 1"),    # # Title         → metadata["Header 1"]
        ("##",  "Header 2"),    # ## Section      → metadata["Header 2"]
        ("###", "Header 3"),    # ### Subsection  → metadata["Header 3"]
    ]

    splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on,
        # strip_headers=True  ← default: remove header lines from chunk content
        #                       set False to keep headers inside chunks too
    )

    # split_text returns a list of Document objects (not bare strings)
    # because we need to carry the metadata
    doc_chunks = splitter.split_text(MARKDOWN_DOC)

    print("═" * 65)
    print("  5A: MarkdownHeaderTextSplitter — Basic Usage")
    print("═" * 65)

    for i, doc in enumerate(doc_chunks):
        print(f"\n┌─ Chunk {i+1:02d}  ({len(doc.page_content)} chars)")
        # Show the metadata — this is the header hierarchy
        print(f"│  📎 metadata: {doc.metadata}")
        # Show first 200 chars of content
        content_preview = doc.page_content[:200].replace("\n", "↵")
        print(f"│  📄 content:  {content_preview}{'...' if len(doc.page_content) > 200 else ''}")
        print(f"└{'─'*54}")

    print(f"\n→ {len(doc_chunks)} chunks, each tagged with section hierarchy")
    print("→ Notice: chunks automatically get header context even if header")
    print("  is stripped from content — perfect for filtered retrieval!")


# ══════════════════════════════════════════════════════════════════════════════
# DEMO B: MarkdownHeaderTextSplitter + RecursiveCharacterTextSplitter
# The production two-stage pipeline
# ══════════════════════════════════════════════════════════════════════════════

def demo_b_two_stage_pipeline():
    """
    Stage 1: Split at header boundaries (coarse — sections)
    Stage 2: Split large sections further (fine — paragraphs/sentences)
    
    Crucially: Stage 2 PRESERVES Stage 1's metadata on all sub-chunks.
    """
    # ─── Stage 1: Header splitting ────────────────────────────────────────────
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[
            ("#",   "Header 1"),
            ("##",  "Header 2"),
            ("###", "Header 3"),
        ]
    )
    header_docs = header_splitter.split_text(MARKDOWN_DOC)

    print("═" * 65)
    print("  5B: Two-Stage Pipeline  (headers → recursive)")
    print("═" * 65)
    print(f"\n  Stage 1 produced {len(header_docs)} header-level chunks")

    # ─── Stage 2: Further split large chunks ──────────────────────────────────
    char_splitter = RecursiveCharacterTextSplitter(
        chunk_size=300,
        chunk_overlap=30,
    )

    # split_documents PRESERVES the metadata from Stage 1!
    final_docs = char_splitter.split_documents(header_docs)

    print(f"  Stage 2 produced {len(final_docs)} final chunks\n")

    for i, doc in enumerate(final_docs):
        print(f"  Chunk {i+1:02d} | {len(doc.page_content):4d} chars | "
              f"metadata={doc.metadata}")
        # Show just the first line of content
        first_line = doc.page_content.split("\n")[0][:60]
        print(f"          └─ {first_line}...")

    print(f"\n→ All {len(final_docs)} chunks have section metadata ✅")
    print("→ Even tiny sub-chunks know which section they came from.")


# ══════════════════════════════════════════════════════════════════════════════
# DEMO C: Metadata-based retrieval filtering
# Shows why the metadata is actually useful at query time
# ══════════════════════════════════════════════════════════════════════════════

def demo_c_metadata_filtering():
    """
    Demonstrates how to filter retrieval using the header metadata.
    
    In a real RAG system, you'd pass `filter` to vectorstore.similarity_search().
    Here we simulate it to show the concept.
    
    Real usage example (Chroma):
      vectorstore.similarity_search(
          query="what is an embedding?",
          filter={"Header 2": "Core Components"}   ← only search this section
      )
    
    Real usage (FAISS):
      FAISS doesn't support metadata filtering natively.
      Use Chroma or Qdrant if you need filter-by-metadata retrieval.
    """
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("#", "H1"), ("##", "H2"), ("###", "H3")]
    )
    char_splitter = RecursiveCharacterTextSplitter(chunk_size=300, chunk_overlap=30)

    header_docs = header_splitter.split_text(MARKDOWN_DOC)
    all_chunks = char_splitter.split_documents(header_docs)

    # Simulate filtering: find chunks from the "Core Components" section
    target_section = "Core Components"
    filtered = [
        doc for doc in all_chunks
        if doc.metadata.get("H2") == target_section
    ]

    print("\n" + "═" * 65)
    print(f"  5C: Metadata Filtering — showing only '{target_section}'")
    print("═" * 65)
    print(f"\n  Total chunks: {len(all_chunks)}")
    print(f"  Chunks in '{target_section}': {len(filtered)}\n")

    for i, doc in enumerate(filtered):
        print(f"  [{i+1}] metadata={doc.metadata}")
        print(f"       {doc.page_content[:100].replace(chr(10),' ')}...\n")

    # Show ALL unique section values — useful for building a filter UI
    all_h2_values = sorted({
        doc.metadata.get("H2", "(none)")
        for doc in all_chunks
    })
    print(f"  All H2 sections in document: {all_h2_values}")
    print("  → You can build a section-selector UI using these values!")


# ══════════════════════════════════════════════════════════════════════════════
# DEMO D: HTMLHeaderTextSplitter — for web-scraped content
# ══════════════════════════════════════════════════════════════════════════════

def demo_d_html_splitter():
    """
    HTMLHeaderTextSplitter works the same way as MarkdownHeaderTextSplitter
    but parses HTML heading tags (<h1>, <h2>, etc.) instead of Markdown hashes.
    
    Use case: you've scraped a documentation page or Wikipedia article.
    The HTML structure encodes the same hierarchy as Markdown headers.
    """
    headers_to_split_on = [
        ("h1", "Title"),
        ("h2", "Section"),
        ("h3", "Subsection"),
    ]

    html_splitter = HTMLHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on
    )

    html_chunks = html_splitter.split_text(HTML_DOC)

    print("\n" + "═" * 65)
    print("  5D: HTMLHeaderTextSplitter")
    print("═" * 65)

    for i, doc in enumerate(html_chunks):
        print(f"\n  Chunk {i+1:02d} | {len(doc.page_content)} chars | metadata={doc.metadata}")
        print(f"    {doc.page_content[:120].replace(chr(10), ' ')}...")

    print(f"\n→ {len(html_chunks)} HTML chunks with header hierarchy as metadata")

    # Stage 2: Further split long HTML chunks
    char_splitter = RecursiveCharacterTextSplitter(chunk_size=250, chunk_overlap=25)
    final_html_chunks = char_splitter.split_documents(html_chunks)

    print(f"→ After stage-2 splitting: {len(final_html_chunks)} final chunks")
    print("→ All have HTML section metadata preserved ✅")


# ══════════════════════════════════════════════════════════════════════════════
# DEMO E: Custom regex-based splitter for other structured formats
# Sometimes you have formats that aren't standard markdown or HTML
# ══════════════════════════════════════════════════════════════════════════════

def demo_e_custom_structure():
    """
    For non-standard structured formats, you can build a custom splitter
    using regex. Example: a document delimited by "SECTION:" markers,
    like legal documents, configuration files, or custom DSLs.
    """
    import re

    custom_structured_text = """
SECTION: Overview
This document describes the deployment process for our RAG system.
The system consists of an embedding pipeline and a retrieval API.

SECTION: Prerequisites  
Install Python 3.11+. Configure a virtual environment. 
Set the OPENAI_API_KEY or HUGGINGFACE_TOKEN environment variable.
Ensure Docker is installed and running on the host machine.

SECTION: Installation
Run pip install -r requirements.txt to install all dependencies.
Then run python setup.py to initialize the vector database.
The setup script will download the embedding model (~90MB) on first run.

SECTION: Deployment
Build the Docker image with docker build -t rag-api .
Deploy with docker-compose up -d to start all services.
The API will be available on port 8080 by default.
""".strip()

    # Split on "SECTION:" markers
    section_pattern = re.compile(r"^SECTION:\s*(.+)$", re.MULTILINE)

    print("\n" + "═" * 65)
    print("  5E: Custom Structure — 'SECTION:' Marker Splitting")
    print("═" * 65)

    sections = section_pattern.split(custom_structured_text)
    # section_pattern.split() alternates: [pre, title, content, title, content, ...]

    from langchain_core.documents import Document
    custom_chunks = []
    # sections[0] = text before first SECTION: (usually empty)
    for j in range(1, len(sections), 2):
        if j + 1 < len(sections):
            section_title = sections[j].strip()
            section_body = sections[j + 1].strip()
            custom_chunks.append(Document(
                page_content=section_body,
                metadata={"section": section_title}
            ))

    for i, doc in enumerate(custom_chunks):
        print(f"\n  Chunk {i+1}: section='{doc.metadata['section']}'")
        print(f"    {doc.page_content[:100]}...")

    print(f"\n→ {len(custom_chunks)} chunks, each tagged with section name")
    print("→ Pattern: whenever documents use consistent delimiters,")
    print("  write a custom splitter rather than fighting the generic ones.")


# ══════════════════════════════════════════════════════════════════════════════
# KEY TAKEAWAYS
# ══════════════════════════════════════════════════════════════════════════════

def print_takeaways():
    print("\n" + "=" * 65)
    print("KEY TAKEAWAYS — Structure-Aware Splitting")
    print("=" * 65)
    print("""
  1. Header metadata is the superpower of structure-aware splitting.
     Every chunk knows its place in the document hierarchy.
     Use this for filtered retrieval (search only in one section).

  2. ALWAYS combine with a secondary splitter:
     MarkdownHeaderTextSplitter → RecursiveCharacterTextSplitter
     The header splitter creates sections; the char splitter sizes them.

  3. For metadata filtering at query time:
     FAISS: doesn't support it natively → switch to ChromaDB or Qdrant
     ChromaDB: filter={"Header 2": "Installation"}
     Qdrant:   FieldCondition(key="Header 2", match=...)

  4. If you have non-standard structured documents (legal text, configs,
     custom DSLs), build a regex-based custom splitter (Demo E).

  5. Docling (which you already use!) can convert PDFs → Markdown,
     giving you structure metadata even from unstructured PDFs.
     
     Pipeline:  PDF → Docling → Markdown → MarkdownHeaderTextSplitter

  NEXT UP → Strategy 6: Semantic Chunking (split on topic changes)
  → python 06_semantic.py
""")


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n🔍 Running all Structure-Aware Splitting demos...\n")

    demo_a_markdown_basic()
    print("\n" + "─" * 65 + "\n")

    demo_b_two_stage_pipeline()
    print("\n" + "─" * 65 + "\n")

    demo_c_metadata_filtering()
    print("\n" + "─" * 65 + "\n")

    demo_d_html_splitter()
    print("\n" + "─" * 65 + "\n")

    demo_e_custom_structure()

    print_takeaways()
