## What is TruLens?

**TruLens** is an **LLM application evaluation and observability framework** used to measure the quality of Retrieval-Augmented Generation (RAG) systems, AI agents, chatbots, and LLM applications.

Think of TruLens as **Datadog + Unit Testing + Quality Metrics for LLMs**.

Instead of asking:

> "Did my code execute successfully?"

TruLens asks:

> "Did my RAG retrieve the correct documents?"
> "Was the answer actually grounded in the retrieved context?"
> "Did the model hallucinate?"
> "Is the answer relevant to the user's question?"
> "Which step in my pipeline caused the problem?"

---

# Why do we need TruLens?

A production RAG pipeline usually looks like this:

```
User Query
      │
      ▼
Query Rewrite
      │
      ▼
Dense Search
      │
      ▼
Sparse Search
      │
      ▼
RRF Fusion
      │
      ▼
MMR
      │
      ▼
Cross Encoder Reranker
      │
      ▼
Top-k Context
      │
      ▼
LLM
      │
      ▼
Final Answer
```

Suppose a user asks:

> What is the return policy?

The chatbot answers

> You can return within 90 days.

But the documentation actually says

> Returns are accepted within 30 days.

Now the question becomes

**Where did the error happen?**

Was it because

* Dense search missed the document?
* Sparse search ranked it too low?
* RRF removed it?
* MMR discarded it?
* Reranker chose the wrong chunks?
* LLM hallucinated?

Without evaluation you cannot know.

TruLens helps identify exactly which stage caused the failure.

---

# What TruLens actually does

TruLens performs four major jobs.

```
                 +----------------+
                 | Observe        |
                 +----------------+

                 +----------------+
                 | Record         |
                 +----------------+

                 +----------------+
                 | Evaluate       |
                 +----------------+

                 +----------------+
                 | Analyze        |
                 +----------------+
```

---

# Step 1 — Observe the RAG pipeline

When your application runs, TruLens records everything.

Example

```
Question

↓

Retrieved Chunks

↓

Prompt

↓

LLM Response

↓

Feedback Scores
```

Nothing is hidden.

For every request it stores

```
Question

Retrieved Documents

Similarity Scores

Chunk IDs

Prompt

LLM Output

Latency

Token Usage

Cost

Feedback Metrics
```

This is called a **Record**.

---

# Step 2 — Record every pipeline execution

Suppose your RAG answers

```
Question

How do I reset my password?
```

Retriever returns

```
Chunk 15

Click Forgot Password
```

```
Chunk 88

Passwords expire every 90 days
```

LLM prompt becomes

```
Use the following context...

Chunk 15

Chunk 88

Question:
How do I reset my password?
```

LLM answers

```
Click Forgot Password on the login page.
```

TruLens stores everything.

```
Record

Input

Retrieved Chunks

Prompt

Output

Metrics

Metadata
```

Think of a Record as a complete trace of one RAG execution.

---

# Step 3 — Evaluate using Feedback Functions

This is where TruLens becomes powerful.

It computes quality scores called **Feedback Functions**.

Instead of checking whether code runs, it checks whether the AI produced a good answer.

The feedback function is simply

```
Inputs

↓

LLM Judge

↓

Score
```

Example

```
Question

↓

Context

↓

Answer

↓

GPT-4 Judge

↓

Score = 0.92
```

---

# Architecture

```
Question
      │
      ▼
Retriever
      │
      ▼
Context
      │
      ▼
LLM
      │
      ▼
Answer
      │
      ▼
TruLens Feedback Functions
      │
      ▼
Scores
```

---

# Major evaluation metrics

There are several built-in metrics.

---

# 1. Answer Relevance

Question

```
How do I reset my password?
```

Answer

```
Click Forgot Password.
```

Very relevant.

Score

```
0.98
```

Bad answer

```
Our refund policy is...
```

Score

```
0.05
```

This measures

```
Question

↓

Answer

↓

Similarity
```

---

# 2. Context Relevance

Question

```
Reset password
```

Retrieved chunk

```
Vacation policy
```

Not useful.

Score

```
0.1
```

Good chunk

```
Forgot Password instructions
```

Score

```
0.97
```

Measures

```
Question

↓

Retrieved Context

↓

Relevance
```

---

# 3. Groundedness

One of the most important RAG metrics.

Question

```
Refund period?
```

Retrieved chunk

```
Returns accepted within 30 days.
```

LLM answer

```
Returns accepted within 30 days.
```

Groundedness

```
1.0
```

Hallucination

Retrieved

```
30 days
```

Answer

```
90 days
```

Groundedness

```
0.1
```

Measures

```
Context

↓

Answer

↓

Is answer supported?
```

---

# 4. Context Coverage

Suppose retriever found

```
Chunk A

Chunk B

Chunk C

Chunk D
```

LLM only uses

```
Chunk A
```

Coverage is low.

TruLens estimates how much of the retrieved context actually contributes to the answer.

---

# 5. Context Precision

Suppose retriever returns

```
20 chunks
```

Only

```
2 chunks
```

are useful.

Precision is poor.

```
Useful Context

──────────────
Retrieved Context
```

---

# 6. Context Recall

Suppose the ideal answer requires

```
5 documents
```

Retriever returns

```
3
```

Recall is

```
3 / 5
```

Low recall means relevant information was missed.

---

# 7. Faithfulness

Very similar to groundedness.

Checks whether every factual claim in the answer is supported by the retrieved documents.

---

# 8. Toxicity

Evaluates whether the answer contains offensive, abusive, or harmful language.

---

# 9. Sentiment

Measures whether the answer is positive, neutral, or negative when that matters for the application.

---

# 10. Conciseness

Determines whether the answer is unnecessarily verbose or appropriately concise.

---

# How Feedback Functions work internally

Imagine you have:

```
Question

↓

Retrieved Context

↓

Generated Answer
```

TruLens sends these to an evaluator model (often another LLM).

Example prompt:

```
Question:
How do I reset my password?

Retrieved Context:
Click Forgot Password.

Answer:
Click Forgot Password on the login page.

Rate from 0 to 1 whether the answer is fully supported by the context.
```

The evaluator returns:

```
0.97
```

That becomes the groundedness score.

This is known as an **LLM-as-a-Judge** approach.

---

# Typical inputs for evaluation

Different metrics require different inputs:

| Metric            | Inputs                                         |
| ----------------- | ---------------------------------------------- |
| Answer Relevance  | Question + Answer                              |
| Context Relevance | Question + Retrieved Context                   |
| Groundedness      | Retrieved Context + Answer                     |
| Faithfulness      | Retrieved Context + Answer                     |
| Context Precision | Retrieved Context + Relevance Judgments        |
| Context Recall    | Retrieved Context + Reference/Expected Context |
| Toxicity          | Answer                                         |
| Sentiment         | Answer                                         |
| Conciseness       | Answer                                         |

---

# Tracing an entire request

A single request can be visualized as:

```
User Question
      │
      ▼
Retriever
      │
      ▼
Retrieved Chunks
      │
      ▼
Prompt Builder
      │
      ▼
Final Prompt
      │
      ▼
LLM
      │
      ▼
Answer
      │
      ▼
Feedback Functions
      │
      ▼
Scores Stored
```

Each stage can be inspected independently.

---

# Example diagnosis

Suppose a user asks:

```
How do I cancel my subscription?
```

TruLens reports:

| Metric            | Score |
| ----------------- | ----: |
| Context Relevance |  0.93 |
| Groundedness      |  0.94 |
| Answer Relevance  |  0.96 |

This suggests the retriever found good documents, the answer addressed the question, and the answer stayed faithful to the retrieved context.

Now consider another case:

| Metric            | Score |
| ----------------- | ----: |
| Context Relevance |  0.22 |
| Groundedness      |  0.91 |
| Answer Relevance  |  0.30 |

Here the retriever likely returned irrelevant context. The LLM remained faithful to that context, but because the retrieved documents were unrelated to the user's question, the final answer was also not relevant. The retrieval stage—not the generation stage—is the primary area to improve.

---

# Where TruLens fits in a production RAG system

```
                Production RAG

User
 │
 ▼
Retriever
 │
 ▼
Fusion
 │
 ▼
MMR
 │
 ▼
Reranker
 │
 ▼
LLM
 │
 ▼
Answer
 │
 ├───────────────► User
 │
 ▼
TruLens
 │
 ▼
Logs + Traces + Metrics + Dashboard
```

TruLens sits alongside your application. It does not change retrieval or generation; instead, it observes each request, records the intermediate data, computes evaluation metrics, and provides dashboards and traces to help you identify bottlenecks and regressions.

---

# TruLens vs. Ragas

Both frameworks evaluate RAG systems, but they have different strengths.

| Feature                            | TruLens                             | Ragas                                                         |
| ---------------------------------- | ----------------------------------- | ------------------------------------------------------------- |
| Primary focus                      | Observability and online evaluation | Offline benchmarking and dataset-based evaluation             |
| Pipeline tracing                   | Excellent                           | Limited                                                       |
| Request-level dashboards           | Yes                                 | No                                                            |
| LLM-as-a-judge metrics             | Yes                                 | Yes                                                           |
| Integration with live applications | Strong                              | Moderate                                                      |
| Experiment comparison              | Yes                                 | Yes                                                           |
| Custom feedback functions          | Yes                                 | Yes                                                           |
| Best use case                      | Monitoring production RAG systems   | Comparing retrieval and generation quality during development |

In practice, many teams use **Ragas** to benchmark changes during development (for example, comparing embedding models or retrievers on a labeled dataset) and **TruLens** to monitor quality continuously in staging or production by tracing real user interactions and computing feedback metrics over time.
