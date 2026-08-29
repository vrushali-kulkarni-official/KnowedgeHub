#!/usr/bin/env python3
"""
Seed a small "golden" corpus into Qdrant for RAGAS evaluation.

The golden corpus has questions we know the answers to, so RAGAS can
measure whether your RAG pipeline is retrieving the right context
and producing the right answer.
"""
from __future__ import annotations

import asyncio
import os
import sys

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models


GOLDEN_DOCS = [
    {
        "id": "doc-1",
        "text": "FastAPI is a modern, fast (high-performance) web framework for building APIs with Python based on standard type hints.",
        "source": "fastapi-docs",
    },
    {
        "id": "doc-2",
        "text": "PostgreSQL is a powerful, open source object-relational database system with 30+ years of active development.",
        "source": "postgres-docs",
    },
    {
        "id": "doc-3",
        "text": "Qdrant is a vector similarity search engine that makes it easy to build AI applications with semantic search.",
        "source": "qdrant-docs",
    },
    {
        "id": "doc-4",
        "text": "LangChain is a framework for developing applications powered by language models.",
        "source": "langchain-docs",
    },
]

GOLDEN_QA = [
    {
        "question": "What is FastAPI?",
        "ground_truth": "FastAPI is a modern Python web framework for building APIs.",
        "contexts": ["doc-1"],
    },
    {
        "question": "What database does the project use?",
        "ground_truth": "PostgreSQL.",
        "contexts": ["doc-2"],
    },
    {
        "question": "What is Qdrant used for?",
        "ground_truth": "Vector similarity search for AI applications.",
        "contexts": ["doc-3"],
    },
]


async def main() -> int:
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    client = AsyncQdrantClient(url=qdrant_url)
    collection = "golden_test_corpus"

    # Recreate the collection clean.
    await client.recreate_collection(
        collection_name=collection,
        vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE),
    )

    # In a real implementation, embed the docs with your embedding model
    # and upload them. For this scaffold, we just record the structure.
    print(f"✅ Collection '{collection}' ready at {qdrant_url}")
    print(f"   {len(GOLDEN_DOCS)} golden documents")
    print(f"   {len(GOLDEN_QA)} golden Q/A pairs")
    print("   (In production, embed with your embedding model and upsert points.)")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
