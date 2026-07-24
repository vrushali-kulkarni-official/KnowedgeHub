# Module 1 — RAG Fundamentals

The simplest possible **production-shaped** RAG pipeline. Every later module
is a refinement of this exact pattern.

## Architecture

```
INDEXING (once)            RETRIEVAL + GEN (per query)
================           ==========================
docs -> chunks             query -> embed -> top-k
       -> embed                   -> prompt = ctx + q
              -> FAISS                 -> Gemini
                                        -> answer
```

## Run it

```bash
# 1. Create a virtualenv (do this once per module)
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Add your FREE Gemini key
cp .env.example .env
# Edit .env and paste your key from https://aistudio.google.com/app/apikey

# 4. Run
python basic_rag.py
```

First run downloads the embedding model (~80 MB) and builds the index.
Subsequent runs reuse `faiss_index/` and start in seconds.

## What you should see

```
Q: What is the name of the company's flagship product?
A: The flagship product is StarTrack-9. [source: <id>]

Q: Who is the CTO?
A: Marcus Holloway. [source: <id>]

Q: What is the weather like in Paris tomorrow?
A: I don't know based on the provided context.
```

## Swap your own data in

Replace `data/sample_doc.txt` with any `.txt` file and re-run. The first
run rebuilds the index; subsequent runs reuse it. For PDFs / web pages /
Notion / GitHub, you'll need different loaders — see **Module 2**.

## Where this is going

| Module | What changes                     | Why                                    |
|--------|----------------------------------|----------------------------------------|
| 2      | Loader                           | Support PDFs, web, Markdown, code, ... |
| 3      | Splitter                         | Smarter chunking strategies            |
| 4      | Embedder                         | Multilingual, larger, Gemini embeddings|
| 5      | Vector store                     | Chroma, pgvector, Qdrant               |
| 6      | Retriever                        | MMR, hybrid, multi-query, re-ranking   |
| 7      | Pre-retrieval                    | Query rewriting, HyDE, step-back       |
| 8      | Memory                           | Multi-turn conversations               |
| 9      | Observability + evaluation       | RAGAS, LangSmith                       |
| 10     | Agentic RAG                      | Self-RAG, CRAG, routing, tools         |
| 11     | Optimization                     | Late interaction, hierarchical index   |
| 12     | Production API                   | FastAPI, streaming, deployment        |

## Hardware notes

* All embeddings run on CPU (`device="cpu"`). `all-MiniLM-L6-v2` uses ~500 MB
  RAM and is fast on any modern laptop.
* FAISS is in-process; no separate server.
* Only the LLM call hits the network (Gemini free tier).
* No GPU required for any module in this course.
