"""
================================================================================
MODULE 1 — RAG FUNDAMENTALS: The Basic Pipeline
================================================================================

WHAT IS RAG?
------------
Retrieval-Augmented Generation is a pattern where you *augment* an LLM's
prompt with relevant context retrieved from a knowledge base, BEFORE asking
the LLM to answer.

The 2-phase pipeline you'll see in this file:
  1. INDEXING (run once, offline):
       Documents -> Chunks -> Embeddings -> Vector Database
  2. RETRIEVAL + GENERATION (run per query, online):
       User Query -> Embed Query -> Find Similar Chunks -> Stuff into Prompt
                  -> LLM -> Answer

WHY RAG?
--------
* LLMs are frozen in time (knowledge cutoff) — they don't know your private
  data, recent events, or proprietary docs.
* LLMs hallucinate — they confidently make things up. RAG grounds answers
  in actual sources.
* Fine-tuning is expensive. RAG is cheap: just embed + retrieve.
* You can cite sources. With pure LLMs you can't.

MODERN CODE NOTES (the things that make this *not legacy*):
-----------------------------------------------------------
* LangChain Expression Language (LCEL): chains are built with the `|`
  operator, like Unix pipes. NO deprecated `LLMChain` / `RetrievalQA` class
  instantiation anywhere.
* `from __future__ import annotations` lets us use modern type-hint syntax
  on older Python interpreters too.
* LangChain 0.3+ package split: each integration lives in its own package
  (e.g. `langchain-huggingface`, `langchain-google-genai`). The monolithic
  `langchain` package is just a meta-package now.
* Sentence-transformers runs locally on CPU — no API cost for embeddings.
* FAISS-CPU is a lightweight in-memory vector index that persists to disk
  as a single folder. No server required.
* Gemini's free tier handles the LLM side. `gemini-2.0-flash` is fast and
  generous on free quotas.

EVERYTHING IN THIS FILE WILL BE REUSED IN LATER MODULES.
Module 2 swaps the loader. Module 3 swaps the splitter. Module 4 swaps the
embedder. Module 5 swaps the vector store. Module 6+ adds smarter retrieval.
The shape of the chain — `assign(context=...) | prompt | llm | parser` —
stays the same. That's the point of LCEL.
================================================================================
"""

from __future__ import annotations  # Enables PEP 604/585 type hints on 3.8/3.9

# =============================================================================
# IMPORTS
# =============================================================================
# We import only what we use. This is good hygiene and also keeps the
# dependency graph clear when you read this file in 6 months.
import os
from pathlib import Path

# Third-party
from dotenv import load_dotenv

# LangChain 0.3+ modern imports — note the per-package split.
# Each integration is its own PyPI package; this is the new way.

from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import FAISS
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Load environment variables from `.env` (if present) into os.environ.
# In production, you'd pull secrets from AWS/GCP Secret Manager, Vault, etc.
# For local dev, .env is the standard. Never commit your real .env to git.
load_dotenv()


# =============================================================================
# CONFIGURATION
# =============================================================================
# 12-Factor App principle: config comes from the environment, not from
# hard-coded constants scattered through the code. For a real project you'd
# build a Pydantic `Settings` class that reads from env vars with defaults
# and validation. For a single lesson, top-of-file constants are fine.

DOCS_PATH = Path(__file__).parent / "data" / "sample_doc.txt"
INDEX_DIR = Path(__file__).parent / "faiss_index"

# --- Embedding model ---------------------------------------------------------
# `all-MiniLM-L6-v2` is the canonical "first try" embedding model:
#   * Tiny  (~80 MB on disk)
#   * Fast on CPU (perfect for weak hardware — no GPU needed)
#   * 384-dim vectors (cheap to store + search)
#   * Strong baseline quality on English text
# It is the most-cited open-source embedding in the RAG literature.
# Module 4 will compare this to alternatives (Gemini's embeddings,
# multilingual models, larger MTEB leaders).
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# --- LLM model --------------------------------------------------------------
# Gemini 2.0 Flash is fast, capable, and has a generous free tier.
# temperature=0 is the right default for RAG: you want deterministic,
# faithful answers, not creative ones. Higher temperatures make the LLM
# "ignore" the context more often. We'll revisit this in Module 9.
GEMINI_MODEL = "gemini-2.0-flash"


# =============================================================================
# PHASE 1 — INDEXING (offline, run once, then cache to disk)
# =============================================================================
def build_index() -> FAISS:
    """
    Build a FAISS vector index from a text file and persist it to disk.

    This function demonstrates the OFFLINE side of RAG. In production you
    would:
      * Run this as a separate CLI / scheduled job / ETL pipeline.
      * Store the index in a managed service (Pinecone, Weaviate, pgvector).
      * Handle incremental updates, deletions, ACL filtering, etc.
    For learning purposes, a local FAISS file is perfect.
    """
    # -------------------------------------------------------------------------
    # STEP 1: LOAD
    # -------------------------------------------------------------------------
    # A "Document" in LangChain is a simple object with two attributes:
    #   - page_content: str  (the actual text)
    #   - metadata:     dict (anything you want to attach: source, page#, etc.)
    # Every loader returns a list[Document].
    #
    # TextLoader reads a plain .txt file. By default the whole file becomes
    # ONE Document. We'll see PDF, HTML, web, Notion, GitHub loaders in
    # Module 2.
    print(f"[1/4] Loading document: {DOCS_PATH}")
    loader = TextLoader(str(DOCS_PATH), encoding="utf-8")
    documents = loader.load()
    print(f"      -> {len(documents)} document(s) loaded.")

    # -------------------------------------------------------------------------
    # STEP 2: SPLIT (chunking)
    # -------------------------------------------------------------------------
    # LLMs have a limited context window. Even Gemini's 1M-token window is
    # finite, and stuffing a 500-page PDF in there is wasteful and *dilutes*
    # the model's attention (a phenomenon called "lost in the middle").
    # We split documents into small chunks so we can retrieve only the
    # relevant ones at query time.
    #
    # RecursiveCharacterTextSplitter is the modern default. It tries to keep
    # semantic units together: paragraphs first, then sentences, then words.
    # The default separator list is ["\n\n", "\n", " ", ""].
    #
    # chunk_size:    max characters per chunk. 1000 is a sensible default.
    # chunk_overlap: characters shared between adjacent chunks. 200 keeps
    #                context flowing across boundaries (e.g. a sentence that
    #                straddles two chunks isn't lost).
    #
    # In Module 3 we'll explore semantic chunking, sentence-aware chunking,
    # markdown-aware chunking, token-aware chunking, and parent-child
    # chunking — they're all variations on this one idea.
    print("[2/4] Splitting into chunks...")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
    )
    chunks = splitter.split_documents(documents)
    print(f"      -> {len(chunks)} chunks produced.")

    # -------------------------------------------------------------------------
    # STEP 3: EMBED
    # -------------------------------------------------------------------------
    # An "embedding" is a dense vector of floats (384 numbers for our model)
    # that captures the SEMANTIC meaning of a piece of text. Two pieces of
    # text with similar meaning have vectors that are close in cosine
    # distance. This is what makes "find me chunks relevant to this question"
    # possible — the question and the answer chunks live in the same space.
    #
    # HuggingFaceEmbeddings wraps sentence-transformers. The first run
    # downloads the model (~80 MB) into ~/.cache/huggingface. Subsequent
    # runs use the cached copy.
    #
    # model_kwargs={"device": "cpu"}  -> keep it on CPU. Weak hardware rule.
    # encode_kwargs={"normalize_embeddings": True}
    #   -> L2-normalizes every vector so cosine similarity reduces to a
    #      simple dot product. FAISS uses this automatically, but being
    #      explicit removes a class of subtle bugs.
    print(f"[3/4] Embedding chunks with {EMBEDDING_MODEL_NAME}...")
    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL_NAME,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )

    # -------------------------------------------------------------------------
    # STEP 4: STORE
    # -------------------------------------------------------------------------
    # FAISS (Facebook AI Similarity Search) is a high-performance ANN
    # (Approximate Nearest Neighbor) library. `FAISS.from_documents` is a
    # convenience that does three things in one call:
    #   1) embed every chunk with the provided embedder
    #   2) build an in-memory index of those vectors
    #   3) return a wrapper you can query
    #
    # `save_local()` writes the index to disk as a folder containing two
    # files: `index.faiss` (the vectors) and `index.pkl` (the doc store).
    # We'll load it back in `main()` if it already exists — embedding all
    # chunks is the SLOW part of RAG, so we always cache.
    #
    # Alternatives we'll explore in Module 5:
    #   * Chroma         — duckdb/sqlite-backed, easy persistence
    #   * pgvector       — Postgres extension, fits your existing stack
    #   * Qdrant/Milvus  — production-grade vector DBs with metadata filters
    print(f"[4/4] Building FAISS index, saving to {INDEX_DIR}...")
    vectorstore = FAISS.from_documents(chunks, embeddings)
    vectorstore.save_local(str(INDEX_DIR))
    print("      -> Index built and saved.")
    return vectorstore


# =============================================================================
# PHASE 2 — RETRIEVAL + GENERATION (online, run per query)
# =============================================================================
def format_docs(docs) -> str:
    """
    Concatenate retrieved chunks into a single context string.

    Why a plain string? Because our prompt template has a `{context}`
    placeholder that must be filled with a string. In Module 6 we'll
    discuss better ways to format retrieved docs (JSON, structured XML,
    source-tagged blocks) that improve citation faithfulness and let the
    LLM quote reliably.

    The separator `---` makes it easy for the LLM to see chunk boundaries.
    """
    return "\n\n---\n\n".join(doc.page_content for doc in docs)


def build_rag_chain(vectorstore: FAISS):
    """
    Build the LCEL RAG chain.

    LCEL (LangChain Expression Language) is the modern way to compose
    LangChain components. The `|` operator is composition, like Unix pipes:

        prompt | llm | parser

    means "feed the prompt output into the LLM, then feed LLM output into
    the parser". Every component is a `Runnable`, so they all support
    `.invoke`, `.stream`, `.batch`, and async variants for free.

    Read the shape of the chain carefully — this is the canonical RAG
    pattern in modern LangChain and it will not change across the course.
    """
    # -------------------------------------------------------------------------
    # RETRIEVER
    # -------------------------------------------------------------------------
    # A "retriever" is anything that takes a string query and returns a
    # list of Documents. Vector stores expose `.as_retriever()` which wraps
    # similarity search with sensible defaults.
    #
    # search_type="similarity"      -> plain cosine/dot-product top-k.
    # search_kwargs={"k": 4}        -> return 4 chunks. This is the #1 knob
    #                                  to tune. Too few -> missing context.
    #                                  Too many -> dilutes attention, burns
    #                                  tokens, and may include noise.
    retriever = vectorstore.as_retriever(
        search_type="similarity",
        search_kwargs={"k": 4},
    )

    # -------------------------------------------------------------------------
    # LLM
    # -------------------------------------------------------------------------
    # ChatGoogleGenerativeAI is the modern Gemini integration.
    # temperature=0: deterministic, faithful. Right default for RAG.
    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Copy .env.example to .env and fill it in."
        )
    llm = ChatGoogleGenerativeAI(
        model=GEMINI_MODEL,
        temperature=0,
        # max_output_tokens=1024,  # uncomment to cap output length / cost
    )

    # -------------------------------------------------------------------------
    # PROMPT
    # -------------------------------------------------------------------------
    # The prompt is where ~80% of RAG quality lives. A great RAG prompt:
    #   1) Tells the model its only source of truth is the context.
    #   2) Tells it to admit ignorance when the context is insufficient.
    #   3) Asks for citations so the user can verify.
    # We'll iterate on this prompt in Module 6 and beyond (chain-of-thought,
    # self-verification, structured outputs, etc.).
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            "You are a precise assistant. Answer the user's question "
            "using ONLY the context provided below. If the context does "
            "not contain the answer, reply exactly: "
            "'I don't know based on the provided context.' "
            "Always cite the relevant context using [source: <id>] notation.\n\n"
            "Context:\n{context}",
        ),
        ("human", "{question}"),
    ])

    # -------------------------------------------------------------------------
    # CHAIN (the heart of RAG, in LCEL)
    # -------------------------------------------------------------------------
    # The shape of this chain is the heart of RAG:
    #
    #   {"context": retriever, "question": input}  ->  prompt  ->  llm  ->  parser
    #
    # Concretely:
    #   1) Input dict: {"question": "..."}
    #   2) RunnablePassthrough.assign injects a NEW key "context" by running
    #      the retriever on the question, then formats those docs as a
    #      string. The original "question" key passes through unchanged.
    #      After this step the dict is: {"question": "...", "context": "..."}.
    #   3) The dict fills the prompt's {question} and {context} placeholders.
    #   4) The prompt goes into the LLM.
    #   5) The LLM's response goes through StrOutputParser, which strips
    #      the chat-message wrapper and returns a plain string.
    rag_chain = (
        RunnablePassthrough.assign(
            # The lambda re-reads "question" from the input dict and pipes
            # it into the retriever. This is the canonical LCEL idiom.
            context=(lambda x: x["question"]) | retriever | format_docs,
        )
        | prompt
        | llm
        | StrOutputParser()
    )
    return rag_chain


# =============================================================================
# ENTRYPOINT
# =============================================================================
def main() -> None:
    """
    Build (or load) the index, build the RAG chain, and run a few demo
    questions. One question is designed to be in the doc (should answer
    correctly), one is out-of-scope (should say "I don't know"), and one
    is a chat-style follow-up that exercises the prompt.

    In Module 8 we'll add conversation memory so the chain can handle
    follow-ups like "what about the previous one?" — for now each query
    is independent.
    """
    # ----- Phase 1: index -----
    if not INDEX_DIR.exists():
        vectorstore = build_index()
    else:
        # Reuse the saved index. Embedding all chunks is the SLOW part of
        # RAG (a few seconds for our toy doc, minutes for a real corpus).
        # Always cache between runs. In production this is the difference
        # between a 200 ms query and a 20-second query.
        print(f"Loading existing index from {INDEX_DIR}...")
        embeddings = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL_NAME,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        vectorstore = FAISS.load_local(
            str(INDEX_DIR),
            embeddings,
            # FAISS loads a pickle file (index.pkl) under the hood. Pickle
            # is unsafe with untrusted data — anyone can ship a pickle
            # that runs arbitrary code on load. We pass
            # `allow_dangerous_deserialization=True` because we built this
            # file ourselves in `build_index()`. Never set this flag for
            # an index you didn't create.
            allow_dangerous_deserialization=True,
        )

    # ----- Phase 2: chain -----
    chain = build_rag_chain(vectorstore)

    # ----- Demo queries -----
    # The first two have answers in the doc — RAG should answer them.
    # The third does NOT — the LLM should fall back to "I don't know".
    questions = [
        "What is the name of the company's flagship product?",
        "Who is the CTO?",
        "What is the weather like in Paris tomorrow?",
    ]
    for q in questions:
        print(f"\nQ: {q}")
        # .invoke() runs the whole chain end-to-end. .stream() would give
        # us tokens as they're generated — we'll use that in Module 12
        # when we wrap this in a streaming API.
        answer = chain.invoke({"question": q})
        print(f"A: {answer}")


if __name__ == "__main__":
    main()
