# Orbital AI — ML Model Card

## Model: `star-track-reranker-v3`

### Intended use
Cross-encoder re-ranker used inside the Prometheus RAG pipeline to
re-order the top-50 retrieved candidates down to the top-5 that
actually go into the LLM prompt.

### Architecture
`BAAI/bge-reranker-base` fine-tuned on 38,000 internal (query, doc,
relevance) triples mined from production logs.

### Training data
- 38k triples from the Bengaluru RAG query logs (Mar–Dec 2024)
- 12k triples from the Frankfurt logs (Oct–Dec 2024)
- 4k synthetic adversarial triples from the safety team

### Metrics
| Metric             | Value |
|--------------------|-------|
| NDCG@10            | 0.83  |
| MRR                | 0.79  |
| Latency p50        | 38 ms |
| Latency p95        | 91 ms |

### Known limitations
- Degrades on queries longer than 64 tokens (truncation).
- Not yet evaluated on multilingual queries (FR, JA, HI).
- The re-ranker can over-fit to recent query distributions;
  we re-train on a rolling 90-day window.
