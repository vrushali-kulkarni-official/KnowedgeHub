"""
RAGAS tests — RAG-specific metrics.

RAGAS measures whether your RAG pipeline:
  - Retrieves the right context (ContextPrecision, ContextRecall)
  - Generates an answer that's faithful to that context (Faithfulness)
  - Produces a relevant answer (AnswerRelevancy)
  - Matches a reference answer (AnswerSimilarity)

You'll need a "golden" dataset of question + ground truth + relevant doc IDs.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from datasets import Dataset
from ragas import evaluate
from ragas.metrics import (
    answer_relevancy,
    answer_similarity,
    context_precision,
    context_recall,
    faithfulness,
)


# Your golden dataset. Add real examples from your domain.
GOLDEN_DATASET: list[dict[str, Any]] = [
    {
        "question": "What is FastAPI?",
        "ground_truth": "FastAPI is a modern Python web framework for building APIs with type hints.",
        "contexts": [
            "FastAPI is a modern, fast (high-performance) web framework for building APIs with Python based on standard type hints."
        ],
        "answer": "FastAPI is a Python web framework for building APIs that uses type hints.",
    },
    {
        "question": "What is Qdrant?",
        "ground_truth": "Qdrant is a vector similarity search engine.",
        "contexts": [
            "Qdrant is a vector similarity search engine that makes it easy to build AI applications with semantic search."
        ],
        "answer": "Qdrant is a vector database for semantic search and AI apps.",
    },
]


def run_my_rag(question: str) -> tuple[str, list[str]]:
    """Call your actual RAG pipeline. Returns (answer, retrieved_contexts)."""
    from brain.rag import retrieve, generate
    docs = retrieve(question, k=3)
    contexts = [d.text for d in docs]
    answer = generate(question, contexts)
    return answer, contexts


def build_dataset() -> Dataset:
    """Build a fresh RAGAS dataset by running your RAG pipeline on golden Qs."""
    records = []
    for sample in GOLDEN_DATASET:
        question = sample["question"]
        answer, contexts = run_my_rag(question)
        records.append({
            "question": question,
            "answer": answer,
            "contexts": contexts,
            "ground_truth": sample["ground_truth"],
        })
    return Dataset.from_list(records)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path := __import__("pathlib").Path)
    args = parser.parse_args()

    dataset = build_dataset()

    # Evaluate on 4 core RAG metrics.
    result = evaluate(
        dataset,
        metrics=[
            faithfulness,
            context_precision,
            context_recall,
            answer_relevancy,
            answer_similarity,
        ],
    )

    # Convert to dict for JSON serialization.
    scores = {k: float(v) for k, v in result.items() if isinstance(v, (int, float))}
    print("RAGAS scores:", json.dumps(scores, indent=2))

    args.output.write_text(json.dumps(scores, indent=2), encoding="utf-8")

    # Fail the build if any metric drops below threshold.
    THRESHOLDS = {
        "faithfulness": 0.7,
        "context_precision": 0.7,
        "context_recall": 0.7,
        "answer_relevancy": 0.7,
    }
    failures = {k: v for k, v in scores.items() if k in THRESHOLDS and v < THRESHOLDS[k]}
    if failures:
        print(f"❌ Below threshold: {failures}")
        return 1
    print("✅ All RAG metrics above threshold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
