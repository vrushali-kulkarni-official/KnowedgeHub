"""
================================================================================
MODULE 2 — DOCUMENT LOADERS
================================================================================

WHAT IS A LOADER?
-----------------
A loader is a class that turns a source of text (file, web page, database
row, API response, ...) into a list of LangChain `Document` objects:

    Document(page_content: str, metadata: dict)

Loaders are the *first* step of the indexing pipeline you saw in Module 1.
Everything downstream (chunking, embedding, retrieval) operates on the
output of loaders. Garbage in -> garbage out.

WHY A SEPARATE LAYER?
---------------------
Because real data lives in a thousand formats. You don't want to write
PDF parsing in your RAG code. You want:

    loader = SomeLoader("path/to/file")
    docs   = loader.load()          # list[Document]
    chunks = text_splitter.split_documents(docs)  # Module 3
    vs.add_documents(chunks)        # Module 5

The loader hides the parsing; the splitter hides the chunking; the vector
store hides the indexing. Each layer is swappable. That's the
LangChain philosophy.

THE DOCUMENT OBJECT (read this carefully, it's the lingua franca):
-----------------------------------------------------------------
A Document has exactly two fields:

    doc.page_content  -> str   the actual text
    doc.metadata      -> dict  whatever you want to attach

Metadata is GOLD. It travels with the chunk through the entire pipeline
and ends up in your LLM's context. Common uses:

    metadata = {
        "source":    "s3://bucket/file.pdf",  # where did this come from?
        "page":      14,                      # PDF page number
        "row":       27,                      # CSV row number
        "url":       "https://...",           # web source
        "author":    "...",                   # document author
        "created_at": "2025-01-01",           # when written
        "category":  "finance",               # for filtering
    }

Downstream, metadata lets you do:
  * Citations ("according to file.pdf page 14...")
  * Filters ("only search docs in category=finance")
  * ACL ("user X can only see docs with visibility=team-X")

LEGACY VS MODERN IMPORTS:
-------------------------
  * Legacy:   from langchain.document_loaders import ...
  * Modern:   from langchain_community.document_loaders import ...
  * Some integrations moved to dedicated packages:
      - langchain-unstructured   -> the `unstructured` library
      - langchain-aws            -> S3
      - langchain-google-*       -> Drive, Cloud Storage
  * Always pin the modern path. The legacy `langchain.document_loaders`
    import is a compatibility shim that will eventually be removed.

WHAT THIS MODULE COVERS:
------------------------
  1.  Text / Markdown / PDF / DOCX / CSV  (local files -- the workhorses)
  2.  Web pages  (WebBaseLoader)
  3.  GitHub    (code + issues)
  4.  Directory (load every file in a folder in one call)
  5.  Lazy loading  (.lazy_load() -- for huge files)
  6.  Custom loader  (subclass BaseLoader)
  7.  Enriching metadata  (the production move)

Every loader is a function that returns list[Document]. That's the
interface you build the rest of the system around.
================================================================================
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Iterator

from dotenv import load_dotenv

# LangChain 0.3+ — note the per-package imports. Never import from
# `langchain.document_loaders` in modern code; it's a deprecated shim.
from langchain_community.document_loaders import (
    CSVLoader,
    DirectoryLoader,
    Docx2txtLoader,
    PyPDFLoader,
    TextLoader,
    UnstructuredMarkdownLoader,
    WebBaseLoader,
)
from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document

load_dotenv()


# =============================================================================
# CONFIG
# =============================================================================
DATA_DIR = Path(__file__).parent / "data"
PDF_PATH = DATA_DIR / "sample.pdf"
DOCX_PATH = DATA_DIR / "sample.docx"
CSV_PATH = DATA_DIR / "employees.csv"
MD_PATH = DATA_DIR / "model_card.md"
HANDOFF = """  (skipped -- set {env} in .env to enable)"""


# =============================================================================
# THE INSPECTOR HELPER
# =============================================================================
# This is your "debug the loader" tool. Every time you write a custom
# loader, run the output through `inspect_docs`. You'll spot:
#   * wrong encodings (mojibake like "Ã©")
#   * empty docs (loader silently produced nothing)
#   * missing metadata (citations become impossible)
#   * huge single docs (chunking will produce one giant chunk)
def inspect_docs(docs: list[Document], label: str, max_chars: int = 120) -> None:

    # Pretty-print a summary of a list of Documents.
    print(f"\n--- {label} ---")
    print(f"  count:  {len(docs)}")
    if not docs:
        return
    total_chars = sum(len(d.page_content) for d in docs)
    print(f"  total chars: {total_chars:,}")
    print(f"  avg chars/doc: {total_chars // max(len(docs), 1):,}")
    print(f"  first doc metadata keys: {list(docs[0].metadata.keys())}")
    print(f"  first doc metadata:      {docs[0].metadata}")
    print(f"  first doc preview: {docs[0].page_content[:max_chars]!r}...")
    if len(docs) > 1:
        print(f"  last doc preview:  {docs[-1].page_content[:max_chars]!r}...")


# =============================================================================
# 1. TEXT & MARKDOWN
# =============================================================================
def load_text(path: Path) -> list[Document]:
    """
    TextLoader — the simplest loader. Reads a plain text file, returns ONE
    Document with the entire content.

    Why one Document and not one-per-line? Because the default behaviour
    of TextLoader is `lazy=False` and the whole file becomes a single doc
    for downstream chunking to slice up. If you want one Document per
    line, you can write a 5-line custom loader (see below).

    The `encoding` argument matters. The wrong encoding will silently
    mangle non-ASCII characters. `utf-8` covers 99% of modern text; for
    legacy Windows files you may need `cp1252` or `latin-1`.
    """
    loader = TextLoader(str(path), encoding="utf-8")
    return loader.load()


def load_markdown(path: Path) -> list[Document]:
    """
    UnstructuredMarkdownLoader vs TextLoader for .md files:

    * TextLoader                    -> treats the file as plain text
      (loses header/section structure; chunker sees a wall of text)

    * UnstructuredMarkdownLoader    -> uses the `unstructured` library
      to PARSE the markdown and produce one Document PER ELEMENT
      (heading, paragraph, list, code block, table). Metadata includes
      the element type and header hierarchy.

    The second is much better for markdown-heavy corpora (docs, READMEs,
    wikis). It costs you an extra dependency (`unstructured`) and slower
    parsing, but the structural awareness is worth it.

    Fall back to TextLoader if `unstructured` isn't installed.
    """
    try:
        loader = UnstructuredMarkdownLoader(str(path), mode="single")
        return loader.load()
    except ImportError:
        # graceful fallback so the lesson still runs
        print("  (unstructured not installed -- falling back to TextLoader)")
        return TextLoader(str(path), encoding="utf-8").load()


# =============================================================================
# 2. PDF
# =============================================================================
def load_pdf(path: Path) -> list[Document]:
    """
    PyPDFLoader — the modern default for PDFs.

    Behaviour:
      * One Document per PAGE (not per file).
      * Metadata is auto-populated with:
          { 'source': '<full path>', 'page': <0-indexed int> }

    Why PyPDFLoader and not PDFPlumber / UnstructuredPDF?
      * PyPDFLoader uses `pypdf` -- pure Python, fast, no system deps.
      * PDFPlumber is better for tables; we'd use it for financial
        reports.
      * UnstructuredPDFLoader gives the best quality (layout-aware) but
        needs the heavy `unstructured` library and sometimes Tesseract.

    THE GOTCHA: many real PDFs are scanned images, not text. PyPDFLoader
    will return documents with empty page_content. For those you need
    OCR (UnstructuredPDFLoader with strategy="hi_res" + Tesseract).
    We'll cover OCR in a later module.
    """
    loader = PyPDFLoader(str(path))
    docs = loader.load()
    # Enrich metadata with page_count + load_timestamp. This is the
    # production move: every loader should be wrapped with metadata
    # enrichment so downstream filtering / citations are easy.
    for d in docs:
        d.metadata["page_count"] = len(docs)
        d.metadata["loaded_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    return docs


# =============================================================================
# 3. DOCX (Microsoft Word)
# =============================================================================
def load_docx(path: Path) -> list[Document]:
    """
    Docx2txtLoader — the lightweight DOCX reader. Uses `docx2txt`
    under the hood (no python-docx needed, no LibreOffice needed).

    Output: a single Document with the full text. Headings, lists and
    tables are flattened to plain text. For structural awareness use
    `UnstructuredWordDocumentLoader` (requires `unstructured`).
    """
    loader = Docx2txtLoader(str(path))
    return loader.load()


# =============================================================================
# 4. CSV
# =============================================================================
def load_csv(path: Path) -> list[Document]:
    """
    CSVLoader — each ROW becomes one Document.

    By default the ENTIRE row is joined into page_content as
    "column: value\ncolumn: value\n...". The `source_column` argument
    lets you pick which column should populate the `source` metadata
    field (so each row's source is meaningful, e.g. the employee name).

    For huge CSVs prefer `lazy_load()` to avoid loading everything into
    memory (see `load_csv_lazy` below).
    """
    loader = CSVLoader(
        file_path=str(path),
        encoding="utf-8",
        # source_column="name",   # uncomment to use 'name' as the source
        # csv_args={"delimiter": ",", "quotechar": '"'},
    )
    return loader.load()


# =============================================================================
# 5. WEB
# =============================================================================
def load_web(url: str) -> list[Document]:
    """
    WebBaseLoader — fetches a URL with `requests` and parses the HTML
    with `BeautifulSoup`. By default it grabs the visible text.

    Gotchas:
      * Many sites block scrapers. Set a custom User-Agent header.
      * JS-rendered pages (SPAs) return empty content -- for those you
        need a headless browser loader (e.g. `FireCrawlLoader`).
      * For many pages at once use `SitemapLoader` (load the sitemap,
        then scrape each URL).
    """
    loader = WebBaseLoader(
        url,
        # header_template={           # custom UA helps avoid 403s
        #     "User-Agent": "Mozilla/5.0 (compatible; MyRAGBot/0.1)"
        # },
        # verify_ssl=False,           # last resort; not recommended
    )
    return loader.load()


# =============================================================================
# 6. GITHUB
# =============================================================================
def load_github_files(
    repo: str,
    file_filter: str,
    access_token: str | None = None,
) -> list[Document]:
    """
    GithubFileLoader — load source files from a public/private repo.

    Requires a GitHub personal access token (https://github.com/settings/tokens).
    Free. Public repos work with the token too (and get higher rate limits:
    5000 req/hr vs 60 req/hr unauthenticated).

    `file_filter` is a glob, e.g. "docs/**/*.md" or "**/*.py".
    """
    # Lazy import: only fail if user actually calls this function
    from langchain_community.document_loaders import GithubFileLoader

    loader = GithubFileLoader(
        repo=repo,
        branch="main",
        access_token=access_token or os.getenv("GITHUB_TOKEN"),
        github_api_url="https://api.github.com",
        file_filter=file_filter,
    )
    return loader.load()


# =============================================================================
# 7. DIRECTORY (load every file in a folder in one call)
# =============================================================================
def load_directory(
    path: Path,
    glob: str = "**/*",
    loader_cls: type[BaseLoader] = TextLoader,
) -> list[Document]:
    """
    DirectoryLoader — recursively walk a folder and load every matching
    file using a single loader class.

    Production pattern: dispatch by extension. Below we use TextLoader
    for everything; for mixed corpora you'd build a per-extension
    registry. We'll do that at the bottom of the file.
    """
    loader = DirectoryLoader(
        str(path),
        glob=glob,
        loader_cls=loader_cls,
        # show_progress=True,        # nice for big folders
        # silent_errors=True,        # skip unreadable files instead of crash
        # use_multithreading=True,   # parallel loading -- watch CPU/memory
        # max_concurrency=4,
    )
    return loader.load()


# =============================================================================
# 8. LAZY LOADING (the production move for big files)
# =============================================================================
def load_pdf_lazy(path: Path) -> Iterator[Document]:
    """
    `.load()` materialises the entire file in memory.
    `.lazy_load()` returns an iterator that yields Documents one at a
    time. Critical for:
      * huge PDFs (1000+ pages)
      * massive CSVs
      * streaming web content
    Use it inside a pipeline that consumes one doc at a time:
        for doc in loader.lazy_load():
            vectorstore.add_documents([doc])
    """
    loader = PyPDFLoader(str(path))
    return loader.lazy_load()


# =============================================================================
# 9. CUSTOM LOADER (subclass BaseLoader)
# =============================================================================
class LineByLineLoader(BaseLoader):
    """
    A minimal custom loader. Reads a text file and emits one Document
    per non-empty line. Demonstrates the BaseLoader contract:

        class MyLoader(BaseLoader):
            def __init__(self, path): self.path = path
            def lazy_load(self) -> Iterator[Document]:
                with open(self.path) as f:
                    for i, line in enumerate(f):
                        if line.strip():
                            yield Document(
                                page_content=line.strip(),
                                metadata={"source": self.path, "line": i + 1},
                            )

    That's the whole interface. You get `.load()` and `.lazy_load()`
    for free from BaseLoader. Any loader in `langchain_community` follows
    this same pattern -- when in doubt, read the source.
    """

    def __init__(self, file_path: str | Path, encoding: str = "utf-8") -> None:
        self.file_path = Path(file_path)
        self.encoding = encoding

    def lazy_load(self) -> Iterator[Document]:
        with self.file_path.open(encoding=self.encoding) as f:
            for line_no, line in enumerate(f, start=1):
                stripped = line.strip()
                if stripped:  # skip blank lines
                    yield Document(
                        page_content=stripped,
                        metadata={
                            "source": str(self.file_path),
                            "line": line_no,
                        },
                    )


# =============================================================================
# 10. PER-EXTENSION DIRECTORY DISPATCH (the production pattern)
# =============================================================================
# A single text loader is fine for a folder of .txt files, but the
# moment you have a folder of mixed PDFs, DOCXs, MDs, CSVs, you need
# extension-based dispatch. The function below shows the canonical
# pattern -- extend it as your data sources grow.
def load_mixed_directory(path: Path) -> list[Document]:
    """Walk a folder and load every file with the right loader per type."""
    registry: dict[str, type[BaseLoader]] = {
        ".txt": TextLoader,
        ".md": TextLoader,  # swap to UnstructuredMarkdownLoader if you install `unstructured`
        ".pdf": PyPDFLoader,
        ".docx": Docx2txtLoader,
        ".csv": CSVLoader,
    }
    all_docs: list[Document] = []
    for file in sorted(path.rglob("*")):
        if not file.is_file():
            continue
        loader_cls = registry.get(file.suffix.lower())
        if loader_cls is None:
            print(f"  [skip] no loader for {file.name}")
            continue
        # Each loader has its own constructor signature. The simplest
        # generic call works for TextLoader/CSVLoader/Docx2txtLoader,
        # but PyPDFLoader also needs `str(path)`. The union of the two
        # is `str(path)` which is what we pass here.
        docs = loader_cls(str(file)).load()
        # Normalise metadata so every doc carries its source filename
        for d in docs:
            d.metadata.setdefault("source_file", file.name)
        all_docs.extend(docs)
    return all_docs


# =============================================================================
# 11. METADATA ENRICHMENT (the production move that makes RAG usable)
# =============================================================================
def enrich_metadata(docs: list[Document], **extra) -> list[Document]:
    """
    Add a stable set of metadata fields to every document. Run this as
    the LAST step before embedding. Why?
      * `source` is already there -- we add normalised versions.
      * `ingested_at` tells you when the chunk entered the index.
      * `content_hash` lets you dedupe and detect drift.
      * Anything you pass in `extra` (e.g. tenant_id, project_id) gets
        merged in. This is how you do multi-tenant RAG: stamp every doc
        with the tenant id, then filter by it on retrieval.
    """
    for i, d in enumerate(docs):
        d.metadata["doc_index"] = i
        d.metadata["ingested_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        d.metadata["char_count"] = len(d.page_content)
        d.metadata.update(extra)
    return docs


# =============================================================================
# MAIN — run every demo in turn
# =============================================================================
def main() -> None:
    # ------------------------------------------------------------------ 1
    inspect_docs(load_text(MD_PATH), "1. TextLoader on model_card.md")

    # ------------------------------------------------------------------ 2
    inspect_docs(
        load_markdown(MD_PATH), "2. UnstructuredMarkdownLoader on model_card.md"
    )

    # ------------------------------------------------------------------ 3
    inspect_docs(load_pdf(PDF_PATH), "3. PyPDFLoader on sample.pdf")

    # ------------------------------------------------------------------ 4
    inspect_docs(load_docx(DOCX_PATH), "4. Docx2txtLoader on sample.docx")

    # ------------------------------------------------------------------ 5
    inspect_docs(load_csv(CSV_PATH), "5. CSVLoader on employees.csv")

    # ------------------------------------------------------------------ 6
    # Only run the web demo if the network is reachable. Comment out
    # this block if you're offline.
    # LangChain's own RAG docs page is small, static, and well-behaved --
    # a more reliable choice for a demo than Wikipedia (which rate-limits
    # cloud IPs aggressively). Swap it for whatever URL you actually want
    # to scrape.
    try:
        inspect_docs(
            load_web("https://python.langchain.com/docs/concepts/rag/"),
            "6. WebBaseLoader on langchain.com RAG concepts page",
        )
    except Exception as e:
        print(
            f"\n--- 6. WebBaseLoader ---{HANDOFF.format(env='INTERNET')}\n  reason: {e}"
        )

    # ------------------------------------------------------------------ 7
    # GitHub requires a GITHUB_TOKEN. Skipped if not set.
    if os.getenv("GITHUB_TOKEN"):
        try:
            inspect_docs(
                load_github_files(
                    repo="langchain-ai/langchain",
                    file_filter="README.md",
                ),
                "7. GithubFileLoader on langchain README",
            )
        except Exception as e:
            print(f"\n--- 7. GithubFileLoader ---\n  error: {e}")
    else:
        print(f"\n--- 7. GithubFileLoader ---{HANDOFF.format(env='GITHUB_TOKEN')}")

    # ------------------------------------------------------------------ 8
    inspect_docs(
        load_directory(DATA_DIR, glob="**/*.txt"),
        "8. DirectoryLoader on data/**/*.txt (TextLoader for everything)",
    )

    # ------------------------------------------------------------------ 9
    # Lazy load -- print 3 pages and the byte savings message
    lazy = load_pdf_lazy(PDF_PATH)
    print("\n--- 9. lazy_load() yields pages one by one ---")
    for i, doc in enumerate(lazy):
        if i >= 3:
            print(f"  ... ({i + 1}+ pages streamed, none held in memory at once)")
            break
        print(f"  page {doc.metadata['page']}: {doc.page_content[:80]!r}...")

    # ----------------------------------------------------------------- 10
    # Custom loader on a CSV -- one Document per non-empty line
    custom = LineByLineLoader(CSV_PATH).load()
    inspect_docs(custom, "10. Custom LineByLineLoader on employees.csv")

    # ----------------------------------------------------------------- 11
    # Mixed directory + metadata enrichment -- this is the canonical
    # "ready-to-embed" output of a real ingestion job.
    mixed = load_mixed_directory(DATA_DIR)
    mixed = enrich_metadata(mixed, project="orbital-ai", tenant="hq")
    print("\n--- 11. Mixed-directory load + metadata enrichment ---")
    print(f"  total documents: {len(mixed)}")
    print(
        f"  sample enriched metadata: {json.dumps(mixed[0].metadata, indent=2, default=str)}"
    )


if __name__ == "__main__":
    main()
