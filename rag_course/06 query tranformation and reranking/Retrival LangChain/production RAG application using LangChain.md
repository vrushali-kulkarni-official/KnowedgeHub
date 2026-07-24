If you're talking about a **production RAG application using LangChain**, then the answer is:

**No, you don't manually call every component one-by-one for every request.**

That's exactly why functions like:

```python
create_history_aware_retriever()
create_stuff_documents_chain()
create_retrieval_chain()
```

exist.

They build a **single runnable pipeline (chain)** that can be invoked with one call.

---

# Without Chains

Imagine you manually do everything:

```python
# Step 1: Rewrite query using chat history
new_query = llm.invoke(...)

# Step 2: Retrieve docs
docs = retriever.invoke(new_query)

# Step 3: Format docs
context = format_docs(docs)

# Step 4: Create prompt
prompt = prompt_template.format(context=context, question=user_question)

# Step 5: Generate answer
answer = llm.invoke(prompt)

return answer
```

This works.

But now imagine:

* Query rewriting
* Metadata filtering
* Hybrid search
* Reranking
* Compression
* Citation generation
* Streaming
* Tool calling

The code becomes ugly quickly.

---

# LangChain's Idea

Instead of writing:

```python
step1()
step2()
step3()
step4()
step5()
```

for every request,

you define the workflow once:

```python
rag_chain = create_retrieval_chain(...)
```

and later simply do:

```python
response = rag_chain.invoke({"input": question, "chat_history": history})
```

Internally LangChain executes all the steps.

---

# Example

---

## Build Once At Startup

When application starts:

```python
retriever = vectorstore.as_retriever()

history_aware_retriever = create_history_aware_retriever(
    llm, retriever, contextualize_q_prompt
)

qa_chain = create_stuff_documents_chain(llm, qa_prompt)

rag_chain = create_retrieval_chain(history_aware_retriever, qa_chain)
```

This happens only once.

---

## Request #1

User asks:

```text
What is RAG?
```

You do:

```python
rag_chain.invoke({"input": "What is RAG?", "chat_history": []})
```

---

## Request #2

User asks:

```text
How does it differ from fine tuning?
```

You do:

```python
rag_chain.invoke({
    "input": "How does it differ from fine tuning?",
    "chat_history": history,
})
```

Same chain object.

No rebuilding.

---

# What Happens Internally?

Suppose:

```python
rag_chain.invoke(...)
```

LangChain executes:

```text
User Question
      |
      v
History Aware Retriever
      |
      +--> LLM rewrites query
      |
      v
Retriever
      |
      +--> Vector Search
      |
      v
Retrieved Documents
      |
      v
Stuff Documents Chain
      |
      +--> Build final prompt
      |
      +--> Insert context
      |
      +--> Call LLM
      |
      v
Answer
```

All hidden behind:

```python
rag_chain.invoke()
```

---

# But What About Production Systems?

Here's where things get interesting.

Most large production RAG systems don't stop at:

```python
create_retrieval_chain()
```

They often build custom pipelines.

For example:

```text
Query
  |
Intent Detection
  |
Query Rewrite
  |
Hybrid Search
  |
Metadata Filter
  |
RRF Fusion
  |
Reranker
  |
Context Compression
  |
Prompt Builder
  |
LLM
```

This is more complicated than LangChain's standard retrieval chain.

---

# How Production Teams Handle This

They usually use:

### Option 1 (Simple)

Use LangChain chains directly:

```python
create_retrieval_chain()
```

Good for:

* Internal tools
* MVPs
* Small apps

---

### Option 2 (Most Common)

Use LangChain components but build custom workflow.

Example:

```python
def answer(question):

    query = rewrite(question)

    docs_dense = dense_search(query)

    docs_sparse = bm25_search(query)

    docs = rrf_fusion(docs_dense, docs_sparse)

    docs = rerank(query, docs)

    response = llm.invoke(build_prompt(question, docs))

    return response
```

Many production systems look closer to this.

---

### Option 3 (Very Large Scale)

Use orchestration frameworks such as:

* [LangGraph](https://langchain.com/langgraph?utm_source=chatgpt.com)
* [Haystack](https://haystack.deepset.ai?utm_source=chatgpt.com)
* [LlamaIndex Workflows](https://www.llamaindex.ai?utm_source=chatgpt.com)

These allow graph-based workflows:

```text
Query
   |
   +----> Dense Search
   |
   +----> BM25 Search
   |
   +----> Entity Extraction
            |
            v
         Fusion
            |
         Reranker
            |
           LLM
```

---

# What Most Real-World RAG Teams Do

For serious production systems, it's typically:

```python
# Build once
retriever = ...
reranker = ...
llm = ...

# Per request
response = rag_pipeline.invoke(...)
```

The pipeline itself is built once and reused.

So you do **not** recreate:

```python
create_history_aware_retriever(...)
create_stuff_documents_chain(...)
create_retrieval_chain(...)
```

for every request.

You create them during application startup and then repeatedly call:

```python
rag_chain.invoke(...)
```

or

```python
rag_chain.stream(...)
```

for each user query.

A useful mental model is:

```text
Application Startup
    |
    +--> Build Chain Once
                |
                v
           rag_chain

User Request #1 --> rag_chain.invoke()

User Request #2 --> rag_chain.invoke()

User Request #3 --> rag_chain.invoke()
```

The chain object is reusable; only the input changes for each request.
