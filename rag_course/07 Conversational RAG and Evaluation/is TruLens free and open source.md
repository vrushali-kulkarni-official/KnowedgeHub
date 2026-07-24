Yes. **TruLens is free and open source**, but there are a few different pieces to understand.

## 1. TruLens OSS (Open Source) ✅

The core **TruLens** framework is:

* ✅ Free to use
* ✅ Open source (Apache 2.0 License)
* ✅ Can run completely on your own machine
* ✅ No paid account required

It allows you to evaluate:

* RAG systems
* AI agents
* LLM applications
* Chatbots
* Workflows
* Prompt chains

using Python.

---

## 2. What you get for free

The open-source version includes:

### Instrumentation

Automatically records:

* prompts
* responses
* retrieved chunks
* context
* latency
* token usage
* traces

---

### Evaluations

You can create feedback functions for:

* Context relevance
* Answer relevance
* Groundedness
* Toxicity
* Sentiment
* Custom metrics

Example:

```python
feedback = Feedback(provider.relevance).on_input_output()
```

---

### RAG Evaluation

Measure:

* Retrieval quality
* Chunk relevance
* Hallucinations
* Groundedness
* Faithfulness
* Precision
* Recall

---

### Tracing

Every LLM call can be traced.

Example:

```
User

↓

Retriever

↓

LLM

↓

Response
```

---

### Dashboard

Comes with a local dashboard where you can inspect:

* traces
* evaluations
* metrics
* feedback scores

---

### Framework integrations

Supports many frameworks including:

* LangChain
* LlamaIndex
* Haystack
* LiteLLM
* OpenAI SDK
* Custom Python apps

---

## 3. What is NOT included?

Some organizations build additional enterprise tooling around observability, collaboration, or hosted services, but the core TruLens evaluation framework itself is available as open source. If you're comparing products, check the specific offering because hosted/cloud features may differ from the OSS package.

---

# Is it production ready?

Yes.

Many companies use TruLens OSS in production for:

* RAG evaluation
* AI agent evaluation
* Continuous monitoring
* Regression testing
* Quality benchmarking

---

# What databases can it use?

TruLens can persist data in databases such as:

* SQLite (default)
* PostgreSQL
* Snowflake
* Other supported SQL backends via SQLAlchemy

---

# Does it require OpenAI?

No.

You can evaluate applications built with:

* OpenAI
* Gemini
* Anthropic
* Azure OpenAI
* Ollama
* Hugging Face models
* Local LLMs
* Any custom LLM

Some evaluation metrics use an LLM as a "judge," so you can choose whichever supported model/provider you prefer.

---

# Is it actively maintained?

Yes. TruLens continues to be actively developed with ongoing updates for modern LLM frameworks, evaluation methods, and observability capabilities.

---

## Summary

| Feature                 | TruLens OSS |
| ----------------------- | ----------- |
| Free                    | ✅ Yes       |
| Open Source             | ✅ Yes       |
| License                 | Apache 2.0  |
| Local execution         | ✅ Yes       |
| RAG evaluation          | ✅ Yes       |
| Agent evaluation        | ✅ Yes       |
| LLM tracing             | ✅ Yes       |
| Dashboard               | ✅ Yes       |
| LangChain support       | ✅ Yes       |
| LlamaIndex support      | ✅ Yes       |
| Custom applications     | ✅ Yes       |
| Requires OpenAI         | ❌ No        |
| Suitable for production | ✅ Yes       |

For your learning path toward becoming an **Applied AI Engineer**, TruLens is one of the key evaluation tools worth learning alongside **Ragas**, **LangSmith**, and **Langfuse**. They complement each other rather than being direct replacements:

* **TruLens**: evaluation and quality measurement.
* **Ragas**: specialized evaluation metrics for RAG systems.
* **LangSmith**: tracing, debugging, testing, and evaluation for LLM applications.
* **Langfuse**: open-source observability, tracing, prompt management, and evaluation.
