# Module 4 — Documents, Loaders & Chunking

This module is one of the most important parts of a RAG system.

A surprising number of RAG problems that appear to be “embedding problems” or “retrieval problems” actually begin much earlier:

```text
Bad source
   ↓
Bad parsing
   ↓
Bad normalization
   ↓
Bad chunking
   ↓
Bad metadata / IDs
   ↓
Bad retrieval
   ↓
"Why is my RAG giving bad answers?"
```

The central idea I want you to build in your head is:

> **A RAG system does not retrieve “documents”. It ultimately retrieves small, searchable units of meaning that came from documents.**

So Module 4 is really about designing the pipeline that turns messy real-world information into reliable retrieval units.

I checked the current LangChain, Docling, PyMuPDF, Unstructured, Trafilatura, Crawlee, Qdrant, Langfuse and Gemini documentation while preparing this, so the examples below use the modern package/API direction rather than older LangChain tutorials. In particular, LangChain's current `Document` abstraction remains `page_content + metadata`, the splitter package is now `langchain-text-splitters`, and several older Community loaders have been deprecated in favor of dedicated integration packages. ([LangChain Reference Docs][1])

---

# 0. First build the complete mental model

Before learning individual loaders or splitters, understand this pipeline:

```text
                 INGESTION PIPELINE

 Source
   │
   ├── PDF
   ├── DOCX
   ├── HTML
   ├── GitHub
   ├── website
   ├── Markdown
   └── TXT
   │
   ▼
┌───────────────────┐
│ Discovery         │
│ What should       │
│ I ingest?         │
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Fetch / Load      │
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Parse              │
│ PDF → structure   │
│ HTML → content    │
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Normalize          │
│ Standard internal  │
│ representation     │
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Clean              │
│ remove noise       │
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Split              │
│ document → chunks  │
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Enrich metadata    │
│ source/page/etc.   │
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Identity           │
│ deterministic IDs  │
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Hash / change      │
│ detection          │
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Embed              │
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Vector DB          │
│ Qdrant             │
└───────────────────┘
```

This distinction is extremely important:

### Loading is not parsing

A loader answers:

> “How do I obtain data from this source and turn it into something my pipeline can process?”

### Parsing answers

> “How do I interpret the structure of the source?”

### Cleaning answers

> “Which extracted material is actually useful?”

### Chunking answers

> “How should this material be divided into independently retrievable units?”

### Metadata answers

> “What context do I need to retain so that retrieval remains useful and traceable?”

### IDs answer

> “How do I know that this exact chunk is the same chunk I saw yesterday?”

That last question becomes critical when your RAG application becomes production software.

---

# 1. What exactly is a LangChain `Document`?

The modern LangChain `Document` is conceptually very simple:

```python
from langchain_core.documents import Document

doc = Document(
    page_content="Python is a programming language.",
    metadata={
        "source": "python-book.pdf",
        "page": 10,
    },
)
```

The important fields are:

```text
Document
├── page_content
└── metadata
```

LangChain's current reference describes `Document` as a container for text plus associated metadata and explicitly distinguishes it from chat messages: `Document` is for retrieval workflows, whereas conversation input/output uses message types. ([LangChain Reference Docs][1])

---

## 1.1 Why is the field called `page_content`?

This confuses almost everyone initially.

It does **not** necessarily mean:

> “content from one PDF page”

It is historical terminology.

For example:

```python
Document(
    page_content="This entire HTML article...",
    metadata={"source": "https://example.com/article"}
)
```

Here `page_content` could represent an entire web page.

Or:

```python
Document(
    page_content="Section 4.2 ...",
    metadata={"source": "manual.pdf", "page": 20}
)
```

Or:

```python
Document(
    page_content="A chunk of a GitHub README...",
    metadata={"repo": "vbcreators/project"}
)
```

Think of it simply as:

> **the textual payload of this retrieval unit**

---

# 2. Why metadata is almost as important as the text

Suppose the vector database retrieves this:

```text
"To rotate an access token, send a POST request..."
```

That is not enough.

You also want:

```python
{
    "source": "keycloak-guide.pdf",
    "page": 84,
    "section": "Token Rotation",
    "document_id": "...",
    "chunk_id": "...",
    "language": "en",
}
```

Why?

Because metadata enables:

### Filtering

For example:

```text
retrieve only:

project = "AI-RAG"
document_type = "official-doc"
language = "en"
```

### Citation

Your application can say:

> Source: Keycloak Guide, page 84

### Access control

Imagine:

```python
metadata = {
    "tenant_id": "company-a",
    "classification": "internal",
}
```

Then your retriever can ensure company B never retrieves company A's content.

### Debugging

When retrieval is bad, you need to know:

```text
Where did this chunk come from?
Which page?
Which version?
Which parser?
Which ingestion run?
```

Without metadata, debugging becomes painful.

---

# 3. A useful production distinction: source metadata vs chunk metadata

I recommend mentally separating these.

## Source-level metadata

Describes the original object:

```python
{
    "source_uri": "...",
    "source_type": "pdf",
    "document_id": "...",
    "document_hash": "...",
    "ingested_at": "...",
    "modified_at": "...",
}
```

## Chunk-level metadata

Describes the particular retrieval unit:

```python
{
    "chunk_id": "...",
    "chunk_index": 17,
    "page": 12,
    "section": "Authentication",
}
```

That distinction becomes extremely useful when you implement incremental ingestion.

---

# 4. Loaders: what problem do they actually solve?

A loader is an adapter.

Different sources have completely different interfaces:

```text
local directory
Git
GitHub
website
PDF
database
Notion
S3
Markdown
DOCX
```

You don't want every downstream component to know how every source works.

Instead:

```text
source-specific adapter
        ↓
common Document representation
        ↓
common ingestion pipeline
```

This is exactly why the `Document` abstraction is useful.

---

# 5. Directory loaders

A directory loader is useful when you have:

```text
data/
├── handbook.pdf
├── architecture.md
├── faq.txt
├── policies/
│   ├── security.pdf
│   └── privacy.pdf
└── docs/
    └── api.md
```

Instead of manually opening each file, you discover and load them systematically.

LangChain still exposes `DirectoryLoader` through `langchain-community`. -**([LangChain Reference Docs][2])

Conceptually:

```python
from langchain_community.document_loaders import DirectoryLoader

loader = DirectoryLoader(
    "data/",
    glob="**/*.md",
)

documents = loader.load()
```

But production ingestion requires more thinking than:

```python
glob="**/*"
```

You need to consider:

```text
Which extensions?
Which files?
Symlinks?
Hidden files?
Temporary files?
Git metadata?
Binary files?
Maximum file size?
Permissions?
```

A safer design is:

```text
discover
   ↓
filter
   ↓
classify
   ↓
select parser
```

rather than blindly parsing everything.

---

# 6. GitHub / Git loaders

There are several different meanings of “GitHub ingestion”.

### A. Repository source files

You might want:

```text
src/
README.md
docs/
```

### B. Issues

You may want:

```text
Issue #124
Issue #125
Issue #126
```

### C. Pull requests

### D. Wiki/documentation

These are semantically different datasets.

LangChain currently has several Git/GitHub-oriented integrations including `GitLoader`, `GithubFileLoader`, `GitHubIssuesLoader`, etc. ([LangChain Reference Docs][2])

For a code RAG system, don't think:

> “GitHub is one document.”

Think:

```text
Repository
├── source files
├── docs
├── README
├── issues
├── PRs
└── discussions
```

Each may deserve different metadata and chunking policies.

---

# 7. The PDF problem

PDF is probably the most important real-world parsing problem in RAG.

Because a PDF is **not fundamentally a text document**.

It is closer to:

> a set of instructions describing where things appear on a page.

For example:

```text
PDF page
│
├── text at x=100,y=100
├── text at x=200,y=100
├── image
├── table
├── header
└── footer
```

So extracting:

```text
line 1
line 2
line 3
```

is not necessarily enough.

---

# 8. PDFs have different categories

You should immediately classify PDFs into roughly these groups.

## Type 1 — Native text PDF

Text can be selected with your mouse.

Good.

Example:

```text
research paper
digital manual
generated report
```

---

## Type 2 — Scanned PDF

Each page is basically:

```text
image
```

There may be no usable text layer.

You need OCR.

---

## Type 3 — Hybrid PDF

Some pages have text.

Some pages are scans.

Some figures contain text.

This is extremely common.

---

## Type 4 — Complex layout

For example:

```text
two-column academic paper

+-----------+-----------+
| text      | text      |
| text      | text      |
| table     | text      |
+-----------+-----------+
```

Naive extraction can produce:

```text
left paragraph
right paragraph
left paragraph continuation
right paragraph continuation
```

which destroys semantic order.

---

# 9. PDF tool comparison

This is where your requested comparison becomes important.

## `pypdf`

`pypdf` is excellent as a basic PDF library, especially when you need standard PDF manipulation and straightforward text extraction.

LangChain's `PyPDFLoader` currently uses `pypdf`. ([LangChain Reference Docs][3])

Think:

```text
pypdf
=
general-purpose PDF library
+
simple text extraction
```

### Strengths

Very useful when:

* PDF is straightforward
* text layer is clean
* you need basic PDF manipulation
* you want a relatively lightweight dependency

### Weaknesses

It isn't the tool I would choose as the centerpiece of a sophisticated document-understanding pipeline involving:

```text
complex layout
tables
figures
multi-column documents
OCR
document structure
```

---

# 10. PyMuPDF / PyMuPDF4LLM

This is a much more interesting option for RAG.

Current PyMuPDF4LLM provides:

```python
import pymupdf4llm

markdown = pymupdf4llm.to_markdown("document.pdf")
```

and can also output JSON containing layout/bounding-box information. It supports OCR-aware extraction and can use OCR only when appropriate, with options such as `force_ocr=True` or `use_ocr=False`. ([pymupdf.readthedocs.io][4])

That's significant.

Instead of:

```text
PDF → plain text
```

you can think:

```text
PDF
 ↓
layout-aware extraction
 ↓
Markdown
```

### Why Markdown?

Because Markdown naturally represents:

```markdown
# Chapter

## Section

Paragraph...

- item
- item

| Name | Value |
|------|------:|
| A    | 10    |
| B    | 20    |
```

This is very valuable for structure-aware chunking.

PyMuPDF4LLM's current API supports Markdown, text, JSON, page chunks, tables and OCR options. ([pymupdf.readthedocs.io][4])

---

# 11. OCR with PyMuPDF4LLM

Current PyMuPDF4LLM can automatically decide whether OCR is useful, and also supports Tesseract and other OCR adaptors. `force_ocr=True` forces OCR; `use_ocr=False` disables it. ([pymupdf.readthedocs.io][5])

This gives you an important principle:

> **Don't OCR everything blindly.**

OCR is slower and can introduce recognition errors.

A reasonable pipeline is:

```text
PDF page
   ↓
Does it have usable native text?
   ├── yes → native extraction
   │
   └── no → OCR
```

This is much better than:

```text
every PDF → render every page → OCR every page
```

---

# 12. Tesseract

Tesseract is an OCR engine.

It solves:

```text
image → text
```

It does **not** solve:

```text
entire document understanding problem
```

This distinction is important.

You can have:

```text
Tesseract:
"Annual Revenue 2025"
```

but still have no idea that:

```text
Annual Revenue 2025
        ↓
      Table
        ↓
Region | Revenue
India  | 10M
US     | 20M
```

The OCR engine recognizes text.

The document parser tries to understand structure.

---

# 13. Docling

For your particular goals, **Docling is one of the tools I would learn deeply.**

Current LangChain integration provides:

```bash
uv add langchain-docling
```

and:

```python
from langchain_docling import DoclingLoader

loader = DoclingLoader(
    file_path=["document.pdf"]
)

docs = loader.load()
```

LangChain's current integration describes Docling as parsing formats such as PDF, DOCX, PPTX and HTML into a rich representation containing layout, tables and other document structure. The integration supports Markdown export or document chunks. ([Docs by LangChain][6])

Docling itself is actively developed; its 2026 releases include ongoing improvements around OCR, chunking, tables and document processing. ([GitHub][7])

---

# 14. Why Docling is especially interesting for RAG

Imagine this document:

```text
                    Annual Report

Revenue
---------------------------------

Region          Revenue       Growth

India           $20M          12%
US              $50M           9%
Europe          $31M           4%
```

A naive PDF-to-text parser may produce:

```text
Annual Report
Revenue
Region Revenue Growth
India $20M 12%
US $50M 9%
Europe $31M 4%
```

Docling aims to preserve much more of the document's structure.

That matters because retrieval should ideally preserve the relationship between:

```text
heading
paragraph
table
table rows
caption
```

rather than treating everything as one flat string.

---

# 15. Docling and Markdown

For your architecture, I strongly recommend thinking:

```text
source-specific parser
        ↓
canonical Markdown
        ↓
LangChain Document
        ↓
structure-aware splitter
```

For example:

```python
Document(
    page_content="""
# Authentication

## Access Tokens

Access tokens are...

## Refresh Tokens

Refresh tokens are...

| Token | Lifetime |
|------|----------|
| Access | 15m |
| Refresh | 30d |
""",
    metadata={
        "source": "auth-guide.pdf"
    },
)
```

Now the same downstream chunking logic can process:

```text
PDF
DOCX
HTML
Markdown
```

much more consistently.

---

# 16. Unstructured

Unstructured takes a different approach.

Instead of thinking only:

```text
file → text
```

it produces semantic document elements such as:

```text
Title
NarrativeText
ListItem
Table
Header
Footer
Image
PageNumber
CodeSnippet
```

and tracks rich metadata. ([Unstructured][8])

For example:

```json
{
  "type": "NarrativeText",
  "text": "The API uses OAuth...",
  "metadata": {
    "page_number": 5,
    "filename": "guide.pdf",
    "parent_id": "..."
  }
}
```

That is powerful for document understanding.

---

# 17. Unstructured's element model

This is an important mental model:

```text
PDF
 ↓
partition
 ↓
elements

Title
NarrativeText
NarrativeText
Table
NarrativeText
Footer
```

Instead of immediately joining everything:

```text
Title
NarrativeText
...
```

you can make decisions based on the type.

For example:

```python
if element.category == "Footer":
    discard()

if element.category == "Table":
    preserve_as_table()

if element.category == "NarrativeText":
    include()
```

That is much more sophisticated than plain text extraction.

Unstructured's current documentation explicitly describes element-level metadata, hierarchy, IDs, page numbers, coordinates and categories. ([Unstructured][8])

---

# 18. Unstructured and OCR

Unstructured currently supports OCR agents including:

```text
Tesseract
Paddle OCR
Google Vision OCR
```

with Tesseract being the default OCR agent unless otherwise configured. ([Unstructured][9])

For PDFs, its `partition_pdf` supports strategies including:

```text
auto
fast
hi_res
ocr_only
```

and can infer table structure. ([Unstructured][10])

So Unstructured is particularly useful when you want to reason about document *elements*, not just strings.

---

# 19. MarkItDown

Microsoft's MarkItDown is another useful tool whose central philosophy is essentially:

```text
many formats
   ↓
Markdown
```

Current usage includes:

```bash
pip install "markitdown[all]"
```

and:

```python
from markitdown import MarkItDown

md = MarkItDown()
result = md.convert("document.pdf")

print(result.markdown)
```

The project supports multiple input types and currently includes optional PDF table extraction modes, although its PDF table support remains best-effort/optional and should not be treated as equivalent to a full document-layout parser. ([GitHub][11])

Its GitHub issue tracker also shows ongoing edge cases in PDF and OCR conversion, so I would treat it as a useful general Markdown converter rather than my primary high-fidelity PDF parser. ([GitHub][12])

---

# 20. My recommendation for your stack

For the project you are building, I would standardize around this:

```text
                    ┌── PDF ──────── Docling
                    │
                    ├── DOCX ────── Docling
                    │
Raw source ─────────┼── PPTX ────── Docling
                    │
                    ├── HTML ────── Trafilatura
                    │
                    ├── Markdown ── direct
                    │
                    ├── TXT ─────── direct
                    │
                    └── GitHub ──── Git/GitHub loaders

                              ↓

                    Canonical Markdown

                              ↓

                    LangChain Document

                              ↓

                    Structure-aware chunks
```

Why?

Because you said you prefer:

* open source
* mature libraries
* minimal custom infrastructure
* maintainable production systems

And this combination gives you exactly that.

---

# 21. My PDF decision tree

I would teach yourself this decision tree:

```text
PDF
 │
 ├── Simple native text?
 │       │
 │       └── PyMuPDF4LLM can be enough
 │
 ├── Complex layout / tables / mixed document types?
 │       │
 │       └── Docling
 │
 ├── Need semantic element classification?
 │       │
 │       └── Unstructured
 │
 └── Scanned?
         │
         └── OCR-aware pipeline
```

And for your **main production RAG pipeline**:

> **Docling first, PyMuPDF4LLM as a lighter/alternative PDF parser, Unstructured when you specifically need its element-centric processing.**

---

# 22. Modern LangChain direction: integration packages

This is important because many tutorials online are old.

Historically you will see:

```python
from langchain_community.document_loaders import ...
```

for almost everything.

That is no longer the direction you should blindly follow.

LangChain's current ecosystem increasingly uses dedicated integration packages.

For example:

```text
Docling
→ langchain-docling

Unstructured
→ langchain-unstructured

Text splitters
→ langchain-text-splitters
```

Current LangChain reference explicitly marks some older community integrations as deprecated, including `UnstructuredFileLoader`; its replacement is `langchain-unstructured.UnstructuredLoader`. ([LangChain Reference Docs][13])

So this:

```python
from langchain_community.document_loaders import UnstructuredFileLoader
```

is an **old/deprecated direction**.

Use:

```python
from langchain_unstructured import UnstructuredLoader
```

instead. ([LangChain Reference Docs][14])

---

# 23. Web content is a completely different problem

Web pages contain enormous amounts of junk:

```text
header
navigation
cookie banners
advertisements
sidebars
related posts
footer
comments
social widgets
```

Suppose the actual article is:

```text
FastAPI Dependency Injection
```

but the HTML contains:

```text
Home
Products
Pricing
Login
ADVERTISEMENT

FastAPI Dependency Injection
...

Subscribe
Related posts
Footer
Privacy
Cookie settings
```

You do not want embeddings of all of that.

---

# 24. Trafilatura

Trafilatura is very useful here.

Its purpose is essentially:

```text
HTML
 ↓
extract meaningful main content + metadata
```

It specifically targets the extraction of useful text while reducing recurring boilerplate such as headers and footers. ([GitHub][15])

It also supports:

```text
sitemaps
RSS/Atom feeds
crawling
URL discovery
Markdown output
```

Its current documentation explicitly recommends sitemaps/feeds as efficient discovery mechanisms before broad crawling. ([Trafilatura][16])

---

# 25. Why sitemap crawling is better than blind crawling

Imagine this website:

```text
example.com

/
/about
/blog
/blog/post1
/blog/post2
/docs
/docs/api
/docs/auth
/docs/security
```

A blind crawler starts:

```text
homepage
 ↓
follow link
 ↓
follow link
 ↓
follow link
 ↓
...
```

This can be wasteful.

A sitemap may directly provide:

```text
/blog/post1
/blog/post2
/docs/api
/docs/auth
/docs/security
```

Then your system already has the universe of discoverable URLs.

Trafilatura explicitly describes sitemaps as useful for exhaustive discovery, and Crawlee provides a dedicated `SitemapRequestLoader`. ([Trafilatura][16])

---

# 26. Crawlee

When your web ingestion becomes serious, I would move crawling responsibilities toward Crawlee rather than writing your own crawler.

Why?

A production crawler eventually needs:

```text
URL queue
retries
concurrency
sessions
robots.txt
deduplication
backoff
storage
request management
```

Crawlee's current Python API provides these kinds of crawler features, including robots.txt handling and sitemap support. ([Crawlee][17])

---

# 27. Crawling and extraction should be separate

This is an extremely useful architecture pattern.

Do not think:

```text
crawler = content extractor
```

Think:

```text
                 DISCOVERY

        Crawlee / sitemap
               ↓
             URLs
               ↓
                 FETCH
               ↓
             raw HTML
               ↓
               PARSE
               ↓
           Trafilatura
               ↓
        canonical Markdown
```

This separation makes the system easier to maintain.

---

# 28. Robots.txt

This isn't merely a technical issue.

A crawler should respect site crawling policies.

Crawlee provides an explicit `respect_robots_txt_file` option, which can cause disallowed URLs to be skipped. ([Crawlee][17])

So production crawler design should roughly be:

```text
robots.txt
    ↓
allowed?
    ├── no → skip
    └── yes
         ↓
       fetch
```

Also respect:

```text
rate limits
site terms
authentication boundaries
copyright
privacy
server load
```

"Can technically fetch" is not the same as "should crawl".

---

# 29. A very important SSRF consideration

Suppose your application allows:

```text
POST /crawl
{
    "url": "https://whatever-user-provided-url"
}
```

A naive server may be tricked into requesting:

```text
http://localhost:8000
http://127.0.0.1
http://169.254.169.254
http://internal-service
```

That becomes an SSRF problem.

LangChain's current `SitemapLoader` documentation itself warns about malicious sitemap URLs and SSRF considerations and recommends restricting crawler network access. ([LangChain Reference Docs][18])

This is exactly the kind of production edge case that argues for mature crawler infrastructure rather than writing your own HTTP crawler from scratch.

---

# 30. Now we reach the heart of RAG: chunking

Suppose the source document contains:

```text
50,000 words
```

You usually do not want:

```text
one embedding = 50,000 words
```

Instead:

```text
document
  ↓
chunk 1
chunk 2
chunk 3
...
chunk N
```

Each chunk becomes an independently retrievable unit.

---

# 31. Why chunking exists

Three major reasons.

## Context limits

The retrieval result eventually enters an LLM context window.

## Retrieval precision

You want:

```text
question
   ↓
specific relevant chunk
```

rather than:

```text
huge document
```

## Embedding quality

Embeddings generally work better when each embedding represents a reasonably coherent semantic unit.

---

# 32. The biggest chunking mistake

A beginner asks:

> “What is the ideal chunk size?”

There isn't one universal answer.

The better question is:

> “What unit of information should be independently retrievable for my application?”

For example:

### Legal contract

A clause may be the natural unit.

### API documentation

A subsection may be the natural unit.

### Research paper

A paragraph or subsection may be appropriate.

### Code

A function/class may be the natural unit.

### FAQ

One question + answer may be the natural unit.

---

# 33. `RecursiveCharacterTextSplitter`

This is the standard starting point for generic text.

Current LangChain documentation explicitly recommends `RecursiveCharacterTextSplitter` for generic use. It recursively tries separators such as:

```text
\n\n
\n
space
""
```

so it tries to preserve paragraphs before sentences/words as much as possible. ([Docs by LangChain][19])

Example:

```python
from langchain_text_splitters import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=150,
)

chunks = splitter.split_documents(documents)
```

Notice the import:

```python
from langchain_text_splitters import ...
```

not old tutorial-style imports from the main `langchain` package.

---

# 34. What does "recursive" mean?

Suppose your text is:

```text
Paragraph A

Paragraph B

Paragraph C
```

The splitter first tries:

```text
\n\n
```

If a section is still too large, it tries:

```text
\n
```

Then:

```text
space
```

Then, ultimately, individual characters.

So it is approximately:

```text
large boundary
    ↓
medium boundary
    ↓
small boundary
    ↓
character
```

This is much better than simply doing:

```python
text[i:i+1000]
```

because the naive version has zero understanding of boundaries.

---

# 35. Chunk size is not "tokens"

This matters.

By default, `RecursiveCharacterTextSplitter` measures chunk size in characters. LangChain's current documentation explicitly states this. ([Docs by LangChain][19])

So:

```python
chunk_size=1000
```

does not mean:

```text
1000 tokens
```

It means approximately:

```text
1000 characters
```

That distinction becomes important when comparing against model context windows.

---

# 36. Chunk overlap

Suppose:

```text
Chunk 1:
AAAAAAAAAAAAAAAA
                 BBBBBBB

Chunk 2:
                 BBBBBBB
                         CCCCCCCC
```

The overlapping `BBBBBBB` helps prevent an important concept near the boundary from being split away from its surrounding context.

For example:

```text
chunk 1:
OAuth authorization requires a PKCE code verifier...

chunk 2:
the code verifier must be compared with the code challenge...
```

Without overlap, relevant context can become isolated.

---

# 37. But larger overlap is not automatically better

Imagine:

```text
chunk size = 1000
overlap = 800
```

Then adjacent chunks duplicate huge amounts of text.

You may get:

```text
1000
  ↓
800 repeated
  ↓
1000
  ↓
800 repeated
```

Problems:

* storage increases
* embedding cost increases
* retrieval returns duplicates
* context gets filled with repeated material

Overlap should be purposeful rather than reflexive.

---

# 38. A reasonable starting point

For general text, start with something like:

```python
chunk_size = 800–1500 characters
chunk_overlap = 100–250 characters
```

But treat those as experimental defaults, not laws.

Then measure:

```text
retrieval recall
answer quality
duplicate retrieval
context size
latency
embedding cost
```

The best chunk size is application dependent.

---

# 39. Structure-aware splitting

This is where RAG becomes much better.

Suppose you have:

```markdown
# Authentication

## OAuth

OAuth is...

## PKCE

PKCE is...

## Device Code

Device Code is...
```

You don't necessarily want:

```text
characters 0-1000
characters 1000-2000
```

You want something closer to:

```text
Authentication
 ├── OAuth
 ├── PKCE
 └── Device Code
```

That is why LangChain has structure-aware splitters.

---

# 40. `MarkdownHeaderTextSplitter`

Current LangChain provides:

```python
from langchain_text_splitters import MarkdownHeaderTextSplitter

headers_to_split_on = [
    ("#", "Header 1"),
    ("##", "Header 2"),
    ("###", "Header 3"),
]

splitter = MarkdownHeaderTextSplitter(
    headers_to_split_on=headers_to_split_on
)

chunks = splitter.split_text(markdown)
```

It associates chunks with header metadata, for example:

```python
{
    "Header 1": "Authentication",
    "Header 2": "PKCE"
}
```

Current LangChain documentation describes precisely this header-aware behavior. ([LangChain Reference Docs][20])

---

# 41. Why header metadata is powerful

Suppose the chunk says:

```text
The verifier is generated by the client...
```

That sentence alone isn't great.

But metadata gives:

```python
{
    "Header 1": "OAuth",
    "Header 2": "PKCE",
}
```

Now the retrieval system knows:

```text
OAuth
  └── PKCE
       └── The verifier is generated...
```

This is much more useful.

---

# 42. `HTMLHeaderTextSplitter`

The HTML equivalent is:

```python
from langchain_text_splitters import HTMLHeaderTextSplitter

splitter = HTMLHeaderTextSplitter(
    headers_to_split_on=[
        ("h1", "Header 1"),
        ("h2", "Header 2"),
        ("h3", "Header 3"),
    ]
)
```

It creates `Document` objects based on HTML headers and associates header hierarchy with metadata. ([LangChain Reference Docs][21])

Current LangChain also has additional HTML-oriented splitters such as:

```text
HTMLSectionSplitter
HTMLSemanticPreservingSplitter
```

so the modern splitter ecosystem is broader than just `HTMLHeaderTextSplitter`. ([Docs by LangChain][22])

---

# 43. The strongest general pattern

For Markdown-like documents, I recommend a **two-stage split**.

```text
Document
   ↓
split by semantic structure
   ↓
sections
   ↓
split large sections by length
   ↓
final chunks
```

For example:

```text
Markdown
 ↓
MarkdownHeaderTextSplitter
 ↓
sections
 ↓
RecursiveCharacterTextSplitter
 ↓
final chunks
```

This is much better than immediately applying character splitting.

Why?

Because:

```text
structure gives meaning
length gives control
```

---

# 44. Token-based splitting

Sometimes characters are not the right unit.

LLMs operate in tokens.

Therefore, if you need a hard token budget, use a token-aware splitter.

LangChain's current `TokenTextSplitter` supports token-based splitting and can use a tokenizer configuration. The package also provides `from_tiktoken_encoder`. ([LangChain Reference Docs][23])

Conceptually:

```text
characters
≠
tokens
```

For example:

```text
"authentication"
```

may not correspond to one token.

---

# 45. When should you use token splitting?

Use it when you have a requirement like:

```text
Each chunk must remain below X tokens.
```

This can matter when:

* embedding models have token limits
* rerankers have limits
* LLM context is tightly controlled
* cost matters
* you need predictable prompt sizes

But don't automatically replace all structure-aware splitting with token splitting.

A good design is:

```text
semantic boundaries first
        ↓
token/size constraint second
```

---

# 46. Structure first, size second

This is one of the most important rules in modern RAG ingestion.

Bad:

```text
raw text
 ↓
1000 characters
```

Better:

```text
document structure
 ↓
semantic section
 ↓
if too large:
     recursively split
 ↓
final chunk
```

Think:

> **Use structure to decide where a chunk should ideally end; use length constraints to prevent pathological chunk sizes.**

---

# 47. Tables are special

Tables are not ordinary prose.

Consider:

```markdown
| Plan | Requests | Price |
|------|----------|------:|
| Free | 1000 | $0 |
| Pro  | 10000 | $20 |
```

Naively splitting by characters could produce:

```text
| Plan | Requests |
```

in one chunk and:

```text
| Price |
| Free | $0 |
```

in another.

Now the semantic relationship is broken.

For this reason:

> **A parser that understands tables is often more valuable than a sophisticated embedding model.**

This is one reason tools such as Docling are attractive for complex documents. LangChain's Docling integration explicitly exposes rich document structure, including tables. ([Docs by LangChain][6])

---

# 48. Experimental semantic chunking

You mentioned this correctly as “awareness only”.

The idea is:

```text
paragraph 1 ── semantically related ── paragraph 2
paragraph 3 ── topic shift ── paragraph 4
```

Instead of splitting purely by:

```text
character count
```

you estimate semantic similarity and split when the topic changes.

Conceptually:

```text
paragraphs
   ↓
embeddings
   ↓
similarity
   ↓
semantic boundaries
```

This can be useful, but don't make it your default starting point.

Why?

Because semantic chunking introduces:

* embedding cost
* additional latency
* more tuning
* more complexity
* model dependence
* harder debugging

Start with:

```text
structure-aware + recursive length control
```

before adding semantic segmentation.

---

# 49. Chunk metadata

Now suppose you generated:

```python
Document(
    page_content="PKCE prevents authorization-code interception attacks...",
    metadata={...}
)
```

What should metadata contain?

I recommend thinking in layers.

---

## Source identity

```python
{
    "source": "...",
    "source_type": "pdf",
    "document_id": "...",
}
```

---

## Location

```python
{
    "page": 42,
    "section": "OAuth / PKCE",
}
```

---

## Versioning

```python
{
    "document_hash": "...",
    "source_modified_at": "...",
}
```

---

## Security

```python
{
    "tenant_id": "...",
    "visibility": "internal",
    "permissions": [...]
}
```

---

## Processing information

```python
{
    "parser": "docling",
    "parser_version": "...",
    "ingestion_version": "v3",
}
```

---

## Chunk identity

```python
{
    "chunk_id": "...",
    "chunk_index": 7,
}
```

That gives you an extremely powerful metadata object.

---

# 50. Why permissions belong in metadata

Imagine a company RAG.

```text
User Alice:
can read:
  finance

User Bob:
can read:
  engineering
```

Suppose:

```python
chunk.metadata = {
    "tenant_id": "company-x",
    "access_groups": ["finance"],
}
```

Then retrieval can enforce:

```text
user permissions
       ↓
metadata filter
       ↓
vector search
```

This is dramatically safer than retrieving first and hoping your application remembers to hide forbidden text later.

---

# 51. Deterministic chunk IDs

This is one of the most important advanced topics.

Suppose today you ingest:

```text
document.pdf
```

and create:

```text
chunk 0
chunk 1
chunk 2
```

Tomorrow you run ingestion again.

If IDs are random:

```text
UUID-A
UUID-B
UUID-C
```

you can't easily tell:

```text
Was this the same chunk?
```

You may accidentally create duplicates.

---

# 52. Deterministic identity

Instead derive identity from stable information.

For example:

```text
source_id
+
normalized_content
+
location
+
chunking_version
```

Then hash it:

```python
import hashlib

def stable_chunk_id(
    source_id: str,
    content: str,
    section: str,
) -> str:
    payload = f"{source_id}\n{section}\n{content}".encode()

    return hashlib.sha256(payload).hexdigest()
```

Now the same content produces the same ID.

---

# 53. UUID version instead of raw hash

You can also derive a UUID deterministically.

For example:

```python
from uuid import UUID, uuid5

NAMESPACE = UUID("12345678-1234-5678-1234-567812345678")

chunk_id = uuid5(
    NAMESPACE,
    f"{source_id}:{content_hash}:{section}"
)
```

That gives you:

```text
same input
   ↓
same UUID
```

---

# 54. Qdrant makes this particularly useful

Qdrant's current point APIs use IDs for upserting and explicitly document idempotent behavior: re-uploading the same point ID overwrites the point rather than creating a duplicate. Qdrant also states that `upload_records` has been replaced by `upload_points`. ([Qdrant][24])

That means a production ingestion system can do:

```text
chunk_id
   ↓
Qdrant point ID
```

Then:

```text
same chunk
   ↓
same ID
   ↓
upsert
```

Beautiful.

---

# 55. Important subtlety: what exactly should the ID contain?

Do **not** blindly use only:

```text
hash(content)
```

Why?

Two different documents could contain:

```text
"Introduction"
```

and produce identical IDs.

Better:

```text
source identity
+
content identity
+
location/context
```

For example:

```text
document_id
+
page
+
section_path
+
content_hash
```

---

# 56. Chunk ID should include chunking version

This is an advanced but very useful idea.

Suppose you change:

```text
chunking algorithm v1
```

to:

```text
chunking algorithm v2
```

The same document could now produce completely different chunks.

So include:

```python
chunking_version = "v2"
```

in the identity if you want the new representation to coexist distinctly.

For example:

```text
doc123:v2:section7:hashabc
```

Otherwise migrations can get messy.

---

# 57. Content hashing

Now we get to incremental ingestion.

Suppose you have:

```text
10,000 documents
```

and one PDF changes.

You don't want:

```text
re-parse all 10,000
re-chunk all 10,000
re-embed all 10,000
re-upload all 10,000
```

Instead:

```text
detect changed sources
       ↓
process only changed sources
```

---

# 58. Document hash

Compute:

```python
import hashlib

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
```

For a file:

```python
from pathlib import Path

content_hash = hashlib.sha256(
    Path(path).read_bytes()
).hexdigest()
```

Store:

```text
document_id
content_hash
modified_at
```

Then next run:

```text
current hash == stored hash?
       │
     yes ──→ skip
       │
      no
       ↓
    reprocess
```

---

# 59. Why timestamps alone are not enough

You might think:

```text
modified_at changed
→ reprocess
```

The problem is that timestamps can be unreliable.

Examples:

```text
file copied
timestamp changed
content unchanged
```

or:

```text
content changed
timestamp preserved
```

Hashes answer a stronger question:

> “Did the content itself change?”

So use timestamps for discovery optimization, but hashes for content identity.

---

# 60. Keep raw originals

This is an extremely strong production practice.

Store:

```text
raw/
├── documents/
├── original HTML/
└── original metadata/
```

Then:

```text
raw original
    ↓
parser
    ↓
normalized markdown
    ↓
chunks
    ↓
embeddings
```

Why?

Because if your parser changes:

```text
Docling v2 → Docling v3
```

you can reprocess the original source.

Without raw originals, you may only have:

```text
already-cleaned chunks
```

and have lost information.

---

# 61. Your ingestion should really have multiple artifacts

I recommend:

```text
raw source
     ↓
parsed representation
     ↓
canonical Markdown
     ↓
cleaned Markdown
     ↓
chunks
     ↓
embeddings
```

Don't think of ingestion as:

```text
PDF → vector database
```

Think:

```text
raw → normalized → chunked → indexed
```

That makes the architecture explainable.

---

# 62. Incremental ingestion architecture

A mature ingestion system might have:

```text
                INGESTION RUN
                     │
                     ▼
              discover sources
                     │
                     ▼
              compare hashes
              /             \
         unchanged          changed
            │                  │
           skip             process
                               │
                               ▼
                             parse
                               │
                               ▼
                             clean
                               │
                               ▼
                            chunk
                               │
                               ▼
                     deterministic IDs
                               │
                               ▼
                           embed
                               │
                               ▼
                           upsert
```

This can reduce huge amounts of unnecessary work.

---

# 63. Deduplication

Now suppose your website has:

```text
/article/123
/article/123?utm_source=x
/article/123?utm_campaign=y
```

They may contain essentially the same content.

You don't want three identical copies.

Deduplication has levels.

---

# 64. Exact deduplication

The easiest form:

```text
normalized text
      ↓
SHA-256
      ↓
hash
```

Then:

```python
seen = set()

for document in documents:
    h = sha256(document.page_content.encode()).hexdigest()

    if h in seen:
        continue

    seen.add(h)
```

This catches exact duplicates.

---

# 65. Normalize before hashing

This matters.

These could be logically identical:

```text
Hello world
```

and:

```text
Hello world\n
```

or:

```text
HELLO WORLD
```

depending on your application.

You can normalize:

```python
def normalize_text(text: str) -> str:
    return " ".join(text.split())
```

Then hash:

```python
hash(normalize_text(text))
```

But be careful:

> Aggressive normalization can destroy meaningful structure.

For example:

```markdown
# Heading
```

should not necessarily become:

```text
Heading
```

before every kind of hashing.

Different hashes may need different canonicalization policies.

---

# 66. Near-duplicate detection

Exact hashing won't detect:

```text
Version A:
OAuth requires a client secret...

Version B:
OAuth requires clients to provide a client secret...
```

These are semantically very similar.

That is where embeddings can help.

Conceptually:

```text
chunk A → embedding A
chunk B → embedding B

cosine_similarity(A, B)
```

If:

```text
similarity > threshold
```

they may be duplicates.

---

# 67. Why near-duplication is harder

Suppose two paragraphs both discuss:

```text
authentication
```

but are actually different:

```text
how authentication works
vs
how to configure authentication
```

High similarity doesn't always mean duplication.

Therefore:

> **Near-duplicate detection should usually be conservative.**

Don't delete content just because cosine similarity is high.

A good architecture is:

```text
exact duplicate
    ↓
automatically remove

near duplicate
    ↓
flag / cluster / review / conservative policy
```

rather than:

```text
similari11111ty > 0.85
→ DELETE
```

---

# 68. Boilerplate stripping

This is especially important for websites.

Suppose 500 pages contain:

```text
VB Creators
Home
Products
Pricing
Contact
```

and one actual article.

If you retain boilerplate, embeddings repeatedly learn:

```text
Home Products Pricing Contact
```

instead of the page's actual subject.

That reduces signal.

Trafilatura is particularly useful here because its extraction goal is to separate meaningful main content from common page boilerplate. ([GitHub][15])

---

# 69. Important cleaning rule

Don't aggressively clean everything.

For example, blindly doing:

```python
text = re.sub(...)
text = text.lower()
text = remove punctuation(...)
```

may be harmful.

You can destroy:

```text
code
URLs
API names
product names
section structure
mathematical notation
table structure
```

The goal is:

> **remove noise while preserving retrieval semantics.**

---

# 70. Canonical Markdown

You specifically asked about standardizing output to Markdown.

I think that is a very good architecture.

Your internal contract can be:

```python
class ParsedDocument:
    markdown: str
    metadata: dict
```

Then every parser must produce:

```text
canonical Markdown
```

For example:

```text
PDF
 ↓
Docling
 ↓
Markdown

DOCX
 ↓
Docling
 ↓
Markdown

HTML
 ↓
Trafilatura
 ↓
Markdown

Markdown
 ↓
identity
```

Now downstream components don't care whether the original source was:

```text
PDF
HTML
DOCX
```

---

# 71. Why Markdown is a great intermediate format

Because it represents:

```text
headers
paragraphs
lists
code
tables
links
emphasis
```

reasonably well.

And LangChain already has Markdown-aware splitting.

So:

```text
parser output
     ↓
Markdown
     ↓
MarkdownHeaderTextSplitter
     ↓
RecursiveCharacterTextSplitter
```

is a beautiful pipeline.

---

# 72. A complete recommended ingestion architecture for you

Given your current learning path, I'd use:

```text
                        ┌──────────── PDF
                        │
                        │       Docling
                        │
                        ├──────── DOCX
                        │
                        │       Docling
                        │
                        ├──────── HTML
                        │
                        │       Trafilatura
                        │
                        ├──────── GitHub
                        │
                        │       Git/GitHub loader
                        │
                        └──────── Markdown/TXT
                                direct
                                  │
                                  ▼
                         canonical Markdown
                                  │
                                  ▼
                          cleaning pipeline
                                  │
                                  ▼
                      metadata normalization
                                  │
                                  ▼
                    MarkdownHeaderTextSplitter
                                  │
                                  ▼
                 RecursiveCharacterTextSplitter
                                  │
                                  ▼
                        deterministic chunk ID
                                  │
                                  ▼
                          content hash
                                  │
                                  ▼
                     embedding model / API
                                  │
                                  ▼
                               Qdrant
```

---

# 73. Where LangGraph fits later

You don't need LangGraph to understand basic ingestion.

Initially:

```python
def ingest_document(...):
    ...
```

is enough.

But as your system becomes advanced, ingestion can become a workflow:

```text
START
  ↓
discover
  ↓
hash
  ↓
changed?
 ├── no → END
 └── yes
      ↓
    parse
      ↓
    clean
      ↓
    chunk
      ↓
 validate
      ↓
 embed
      ↓
 upsert
      ↓
    END
```

That is a natural place where LangGraph can eventually become useful, especially when you have branching, retries, human review, and durable execution.

But don't use LangGraph simply because you are learning LangGraph.

First understand the data pipeline.

---

# 74. Where Langfuse fits

Langfuse is not your document parser.

It is useful for observing the ingestion/retrieval process.

For example, you may later track:

```text
ingestion run
   ├── parser latency
   ├── chunk count
   ├── embedding latency
   ├── failed documents
   └── retrieval evaluation
```

Langfuse's current Python v4 migration documentation also shows the modern LangChain integration path and notes deprecated older parameters such as `update_trace`. ([Langfuse][25])

So don't copy old examples blindly:

```python
CallbackHandler(update_trace=True)
```

That is no longer current.

---

# 75. What about Gemini?

For **this module**, most operations do not require an LLM:

```text
PDF parsing
HTML extraction
chunking
hashing
dedup
metadata
```

So I would deliberately **not** add an LLM call.

You only need Gemini later for things such as:

```text
semantic classification
LLM-assisted document labeling
semantic chunking experiments
synthetic query generation
retrieval evaluation
```

Your preference for Gemini fits the LangChain ecosystem well. The current `langchain-google-genai` integration uses Google's consolidated `google-genai` SDK, and `ChatGoogleGenerativeAI` is the current primary chat interface. ([LangChain Reference Docs][26])

So for an optional later exercise:

```python
from langchain_google_genai import ChatGoogleGenerativeAI

llm = ChatGoogleGenerativeAI(
    model="gemini-3.1-pro-preview",
)
```

The exact model you eventually choose should depend on current availability/cost and your application's needs. ([LangChain Reference Docs][27])

---

# 76. Current vs old/deprecated: memorize this table

| Older / legacy direction                                  | Modern direction                            |
| --------------------------------------------------------- | ------------------------------------------- |
| giant `langchain` package imports                         | dedicated integration packages              |
| `langchain_community.UnstructuredFileLoader`              | `langchain_unstructured.UnstructuredLoader` |
| old splitter imports from miscellaneous LangChain modules | `langchain-text-splitters`                  |
| `upload_records` in Qdrant                                | `upload_points`                             |
| random vector IDs                                         | deterministic application IDs               |
| blindly OCR every PDF                                     | native extraction first, OCR selectively    |
| raw HTML as RAG text                                      | main-content extraction first               |
| blind full-site crawling                                  | sitemap/discovery + controlled crawling     |
| character-only splitting everywhere                       | structure-aware splitting first             |
| reindex everything on every run                           | content hashes + delta ingestion            |

The deprecated `UnstructuredFileLoader` and replacement are explicitly documented in the current LangChain reference, while Qdrant's current docs explicitly mark `upload_records` as replaced by `upload_points`. ([LangChain Reference Docs][13])

---

# 77. The most important beginner-to-advanced progression

I would learn Module 4 in this order.

## Level 1 — Basic document model

Understand:

```python
Document(
    page_content="...",
    metadata={}
)
```

Then manually create:

```text
3 documents
```

and inspect them.

---

## Level 2 — Load simple files

Build:

```text
TXT
Markdown
directory
```

---

## Level 3 — PDF basics

Experiment with:

```text
pypdf
PyMuPDF4LLM
Docling
```

using the **same PDF**.

Compare outputs.

This exercise is extremely important.

You will visually see why parser choice matters.

---

## Level 4 — Markdown normalization

Take:

```text
PDF
HTML
DOCX
```

and make all of them produce:

```text
canonical Markdown
```

---

## Level 5 — Basic chunking

Learn:

```python
RecursiveCharacterTextSplitter
```

and inspect:

```text
chunk sizes
overlap
boundaries
```

---

## Level 6 — Structure-aware chunking

Learn:

```python
MarkdownHeaderTextSplitter
HTMLHeaderTextSplitter
```

then combine:

```text
semantic split
+
length split
```

---

## Level 7 — Metadata

Add:

```text
source
document_id
page
section
timestamp
permissions
```

---

## Level 8 — Deterministic identity

Implement:

```text
source
+
content hash
+
section
+
chunking version
```

→ deterministic ID.

---

## Level 9 — Incremental ingestion

Build:

```text
hash unchanged → skip
hash changed → reprocess
```

---

## Level 10 — Deduplication

Add:

```text
exact hash dedup
```

then experiment with:

```text
embedding-based near dedup
```

---

## Level 11 — Production ingestion

Finally build:

```text
crawler
parser
normalizer
cleaner
chunker
metadata enricher
hash detector
ID generator
embedding worker
Qdrant upsert
```

with retries and observability.

---

# 78. A project structure I would recommend for your AI-RAG project

Given the architecture you have been building, something along these lines is a good long-term direction:

```text
src/ai_rag/
│
├── domains/
│   └── ingestion/
│       ├── models/
│       │   ├── source.py
│       │   ├── parsed_document.py
│       │   └── chunk.py
│       │
│       ├── ports/
│       │   ├── loader.py
│       │   ├── parser.py
│       │   ├── chunker.py
│       │   └── repository.py
│       │
│       └── services/
│           ├── ingestion_service.py
│           ├── dedup_service.py
│           └── identity_service.py
│
├── infrastructure/
│   ├── document_loaders/
│   │   ├── docling_loader.py
│   │   ├── web_loader.py
│   │   └── github_loader.py
│   │
│   ├── parsing/
│   │   ├── pdf_parser.py
│   │   └── html_parser.py
│   │
│   ├── chunking/
│   │   ├── markdown_chunker.py
│   │   └── recursive_chunker.py
│   │
│   ├── embeddings/
│   └── vectorstore/
│       └── qdrant.py
│
└── workflows/
    └── ingestion_graph.py
```

The key design principle is:

> **Your domain should not care whether you used Docling, PyMuPDF4LLM, Trafilatura, or Qdrant.**

The infrastructure layer cares.

That makes changing tools possible later.

---

# 79. Your internal canonical data model

I would eventually evolve toward something conceptually like:

```python
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SourceDocument:
    document_id: str
    source_uri: str
    source_type: str
    content_hash: str
    fetched_at: datetime


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    page_content: str
    section_path: tuple[str, ...]
    metadata: dict
```

Then adapters convert external systems into this internal model.

This makes the rest of your application independent of the parser.

---

# 80. One very important architectural distinction

Do **not** confuse:

```text
document
```

with:

```text
chunk
```

A document might be:

```text
50 pages
```

while its retrievable chunks might be:

```text
120 chunks
```

Therefore:

```text
document_id
```

and:

```text
chunk_id
```

are different identities.

Think:

```text
DOCUMENT
  │
  ├── chunk 0
  ├── chunk 1
  ├── chunk 2
  └── ...
```

This hierarchy becomes extremely useful for:

```text
citations
deletions
reprocessing
access control
versioning
debugging
```

---

# 81. Advanced idea: document version vs content version

Suppose:

```text
manual.pdf
```

changes three times:

```text
v1
v2
v3
```

You might maintain:

```text
document_id = manual.pdf
version = 3
content_hash = abc123...
```

while the individual chunks are:

```text
manual.pdf:v3:chunk...
```

This allows you to answer questions like:

> “Which document version produced this retrieved chunk?”

That is extremely useful in enterprise RAG.

---

# 82. Advanced idea: ingestion version

There is another dimension:

```text
document version
```

versus:

```text
pipeline version
```

For example:

```text
document:
v4

pipeline:
parser=docling-2.x
chunker=v3
cleaning=v2
embedding=model-A
```

Why does this matter?

Because changing your parser can alter chunks even when the source file has not changed.

So production metadata often benefits from recording:

```text
parser version
chunking version
embedding model
ingestion pipeline version
```

This makes migrations reproducible.

---

# 83. The entire module in one picture

This is the picture I want you to remember:

```text
                         RAW WORLD
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
       PDF                 WEB                GITHUB
        │                   │                   │
    Docling             Crawlee            Git loaders
        │              / Trafilatura            │
        │                   │                   │
        └───────────────────┼───────────────────┘
                            │
                            ▼
                   CANONICAL MARKDOWN
                            │
                            ▼
                        CLEANING
                            │
                            ▼
                 STRUCTURE-AWARE SPLIT
                            │
                  ┌─────────┴─────────┐
                  │                   │
           Markdown headers      HTML headers
                  │                   │
                  └─────────┬─────────┘
                            ▼
                  LENGTH CONSTRAINT
                            │
                            ▼
              RecursiveCharacterSplitter
                            │
                            ▼
                       CHUNKS
                            │
                            ▼
                     METADATA
                            │
                            ▼
                  CONTENT / CHUNK HASH
                            │
                            ▼
                  DETERMINISTIC ID
                            │
                            ▼
                       EMBEDDING
                            │
                            ▼
                         QDRANT
                            │
                            ▼
                     RETRIEVAL
```

That architecture is far more important than memorizing individual class names.

---

# 84. What I would choose for **your** project

Given your preference for open-source, mature, popular components and your existing Python + LangChain + LangGraph + Qdrant direction, my default stack would be:

### Documents

```text
LangChain Document
```

### PDF

```text
Docling
```

with:

```text
PyMuPDF4LLM
```

as an excellent lighter/alternative PDF path.

### OCR

```text
Tesseract
```

when needed, rather than automatically OCRing everything.

### Web extraction

```text
Trafilatura
```

### Serious crawling

```text
Crawlee
```

### Discovery

```text
sitemap
+
RSS/Atom where available
```

### Splitting

```text
MarkdownHeaderTextSplitter
        ↓
RecursiveCharacterTextSplitter
```

### HTML

```text
Trafilatura
        ↓
Markdown
        ↓
MarkdownHeaderTextSplitter
```

or native HTML header splitting where you deliberately retain HTML structure.

### Identity

```text
SHA-256 content hashing
+
deterministic UUID / stable hash IDs
```

### Storage

```text
raw originals
+
PostgreSQL metadata
+
Qdrant vectors/payload
```

### Observability

```text
Langfuse
```

### Optional LLM operations

```text
Gemini through langchain-google-genai
```

rather than introducing OpenAI/Anthropic just for convenience. The current Google integration is based on the consolidated `google-genai` SDK and exposes `ChatGoogleGenerativeAI` as the primary LangChain interface. ([LangChain Reference Docs][26])

---

# 85. The three principles I most want you to remember

### Principle 1

> **Parsing quality comes before embedding quality.**

A fantastic embedding model cannot reconstruct a table that your parser destroyed.

---

### Principle 2

> **Structure-aware chunks are generally preferable to arbitrary character slices.**

Use document structure first and length limits second.

LangChain's current documentation recommends `RecursiveCharacterTextSplitter` as a good generic baseline, while providing specialized Markdown/HTML structure-aware splitters for structured documents. ([Docs by LangChain][19])

---

### Principle 3

> **Production ingestion is an indexing system, not a “PDF-to-vector” script.**

A mature ingestion system must answer:

```text
What changed?
What didn't change?
Where did this chunk originate?
Can I reproduce it?
Can I delete it?
Can I update it?
Can I prove which source produced it?
Who is allowed to see it?
Can I process 1 document instead of 100,000?
```

Once you think this way, your RAG architecture becomes much more robust.

---

# 86. What you should be able to do after Module 4

Before moving to the next module, you should be comfortable doing this:

```python
source
   ↓
discover
   ↓
load
   ↓
parse
   ↓
normalize to Markdown
   ↓
clean
   ↓
structure-aware split
   ↓
size-aware split
   ↓
metadata enrichment
   ↓
content hash
   ↓
deterministic chunk ID
   ↓
dedup
   ↓
embed
   ↓
Qdrant
```

And you should be able to explain **why every stage exists**.

That understanding is much more valuable than memorizing:

```python
RecursiveCharacterTextSplitter(...)
```

---

## The practical learning path I recommend next

The best way to continue Module 4 is to turn this into a **hands-on lab series**, rather than throwing one giant project at you:

```text
Lab 1 → Document + metadata
Lab 2 → Directory/TXT/Markdown loaders
Lab 3 → PDF comparison: pypdf vs PyMuPDF4LLM vs Docling
Lab 4 → OCR with a scanned PDF
Lab 5 → HTML + Trafilatura
Lab 6 → Sitemap + Crawlee
Lab 7 → RecursiveCharacterTextSplitter
Lab 8 → MarkdownHeaderTextSplitter
Lab 9 → Two-stage structure + size chunking
Lab 10 → Chunk metadata
Lab 11 → Deterministic IDs
Lab 12 → Content hashing
Lab 13 → Incremental ingestion
Lab 14 → Exact + near dedup
Lab 15 → End-to-end ingestion pipeline → Qdrant
Lab 16 → Langfuse instrumentation
Lab 17 → Production-grade ingestion graph with LangGraph
```

That sequence will let you **actually build and debug each concept**, rather than merely recognizing the terminology.

[1]: https://reference.langchain.com/python/langchain-core/documents/base/Document?utm_source=chatgpt.com "Document | langchain_core | LangChain Reference"
[2]: https://reference.langchain.com/python/langchain-community?utm_source=chatgpt.com "langchain_community | LangChain Reference"
[3]: https://reference.langchain.com/python/langchain-community/document_loaders/blackboard?utm_source=chatgpt.com "blackboard | langchain_community | LangChain Reference"
[4]: https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/api.html?utm_source=chatgpt.com "The PyMuPDF4LLM API - PyMuPDF documentation"
[5]: https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/?utm_source=chatgpt.com "PyMuPDF4LLM - PyMuPDF documentation"
[6]: https://docs.langchain.com/oss/python/integrations/document_loaders/docling?utm_source=chatgpt.com "Docling integration - Docs by LangChain"
[7]: https://github.com/docling-project/docling/releases?utm_source=chatgpt.com "Releases · docling-project/docling · GitHub"
[8]: https://docs.unstructured.io/open-source/concepts/document-elements?utm_source=chatgpt.com "Document elements and metadata - Unstructured"
[9]: https://docs.unstructured.io/open-source/how-to/set-ocr-agent?utm_source=chatgpt.com "Set the OCR agent - Unstructured"
[10]: https://docs.unstructured.io/open-source/core-functionality/partitioning?utm_source=chatgpt.com "Partitioning - Unstructured"
[11]: https://github.com/microsoft/markitdown/blob/main/README.md?utm_source=chatgpt.com "markitdown/README.md at main · microsoft/markitdown · GitHub"
[12]: https://github.com/microsoft/markitdown/issues?utm_source=chatgpt.com "Issues · microsoft/markitdown · GitHub"
[13]: https://reference.langchain.com/python/langchain-community/document-loaders?utm_source=chatgpt.com "document-loaders | langchain_community | LangChain Reference"
[14]: https://reference.langchain.com/python/langchain-unstructured/document_loaders/UnstructuredLoader?utm_source=chatgpt.com "UnstructuredLoader | langchain_unstructured | LangChain Reference"
[15]: https://github.com/adbar/trafilatura?utm_source=chatgpt.com "GitHub - adbar/trafilatura: Python & Command-line tool to gather text and metadata on the Web: Crawling, scraping, extraction, output as CSV, JSON, HTML, MD, TXT, XML · GitHub"
[16]: https://trafilatura.readthedocs.io/en/latest/tutorial-corpus.html?utm_source=chatgpt.com "Tutorial: Building a web corpus — Trafilatura 2.2.0 documentation"
[17]: https://crawlee.dev/python/api/class/_BasicCrawlerOptions?utm_source=chatgpt.com "_BasicCrawlerOptions | API | Crawlee for Python · Fast, reliable Python web crawlers."
[18]: https://reference.langchain.com/python/langchain-community/document_loaders?utm_source=chatgpt.com "document_loaders | langchain_community | LangChain Reference"
[19]: https://docs.langchain.com/oss/python/integrations/splitters/recursive_text_splitter?utm_source=chatgpt.com "Splitting recursively - Text splitter integration guide - Docs by LangChain"
[20]: https://reference.langchain.com/python/langchain-text-splitters/markdown/MarkdownHeaderTextSplitter?utm_source=chatgpt.com "MarkdownHeaderTextSplitter | langchain_text_splitters | LangChain Reference"
[21]: https://reference.langchain.com/python/langchain-text-splitters/html/HTMLHeaderTextSplitter?utm_source=chatgpt.com "HTMLHeaderTextSplitter | langchain_text_splitters | LangChain Reference"
[22]: https://docs.langchain.com/oss/python/integrations/splitters/split_html?utm_source=chatgpt.com "Split HTML - text splitter integration - Docs by LangChain"
[23]: https://reference.langchain.com/python/langchain-text-splitters/base/TokenTextSplitter?utm_source=chatgpt.com "TokenTextSplitter | langchain_text_splitters | LangChain Reference"
[24]: https://qdrant.tech/documentation/manage-data/points/?utm_source=chatgpt.com "Points - Qdrant"
[25]: https://langfuse.com/docs/observability/sdk/upgrade-path/python-v2-to-v3?utm_source=chatgpt.com "Python v2 → v3 - Langfuse"
[26]: https://reference.langchain.com/python/langchain-google-genai/langchain_google_genai?utm_source=chatgpt.com "langchain_google_genai | LangChain Reference"
[27]: https://reference.langchain.com/python/langchain-google-genai/chat_models/ChatGoogleGenerativeAI?utm_source=chatgpt.com "ChatGoogleGenerativeAI | langchain_google_genai | LangChain Reference"
