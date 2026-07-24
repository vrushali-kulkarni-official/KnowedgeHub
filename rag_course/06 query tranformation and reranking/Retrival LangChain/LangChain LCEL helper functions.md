# LangChain LCEL helper functions that create pre-built RAG pipelines.


 to build a complete conversational RAG system:

```
User Question
      │
      ▼
History Aware Retriever
      │
      ▼
Retrieve Documents
      │
      ▼
Stuff Documents into Prompt
      │
      ▼
LLM Generates Answer
```

Let's understand each piece from the ground up.

---

# 1. create_stuff_documents_chain()

This is the easiest one.

## What problem does it solve?

Suppose your retriever returns:

```text
Doc1:
Amazon Bedrock is a fully managed service...

Doc2:
Bedrock provides access to Claude, Llama, Mistral...

Doc3:
Bedrock supports RAG and agents...
```

Now the question is:

> How do we pass these documents to the LLM?

We need to combine them somehow.

There are several strategies:

### Stuff

Put everything directly into the prompt.

```text
Context:
---------
Doc1
Doc2
Doc3
---------

Question:
What is Amazon Bedrock?

Answer:
```

### Map Reduce

Summarize chunks separately then combine.

### Refine

Answer using first chunk then refine with next chunks.

---

The simplest is:

```python
create_stuff_documents_chain()
```

because it literally:

```python
documents
   ↓
join together
   ↓
insert into prompt
   ↓
send to LLM
```

---

## Example

Prompt:

```python
prompt = ChatPromptTemplate.from_template("""
Answer the question using the context.

Context:
{context}

Question:
{input}
""")
```

Then:

```python
document_chain = create_stuff_documents_chain(llm, prompt)
```

Now if retriever returns:

```python
[
    Document("Amazon Bedrock is managed AI service"),
    Document("Supports Claude and Llama"),
]
```

LangChain internally creates:

```text
Answer the question using the context.

Context:

Amazon Bedrock is managed AI service

Supports Claude and Llama

Question:
What is Bedrock?
```

and sends it to the LLM.

---

# Internally

Very simplified:

```python
def create_stuff_documents_chain(llm, prompt):

    def chain(inputs):

        docs = inputs["context"]

        combined_text = "\n\n".join(doc.page_content for doc in docs)

        final_prompt = prompt.format(context=combined_text, input=inputs["input"])

        return llm.invoke(final_prompt)

    return chain
```

Not exact code, but conceptually this is what happens.

---

# 2. create_retrieval_chain()

Now let's move one level up.

---

## Problem

Suppose you already have:

```python
retriever
```

and

```python
document_chain
```

(created using create_stuff_documents_chain)

How do you connect them?

You need:

```text
Question
   ↓
Retriever
   ↓
Documents
   ↓
LLM
```

This is what:

```python
create_retrieval_chain()
```

does.

---

## Example

```python
retrieval_chain = create_retrieval_chain(retriever, document_chain)
```

Now you can do:

```python
retrieval_chain.invoke({"input": "What is Bedrock?"})
```

---

Internally:

### Step 1

Retriever gets question.

```python
docs = retriever.invoke("What is Bedrock?")
```

returns

```python
[Document(...), Document(...)]
```

---

### Step 2

Pass docs to document chain.

```python
document_chain.invoke({"input": question, "context": docs})
```

---

### Step 3

LLM generates answer.

```python
{"answer": "Amazon Bedrock is..."}
```

---

# Internal Flow

Conceptually:

```python
def retrieval_chain(question):

    docs = retriever.invoke(question)

    answer = document_chain.invoke({"input": question, "context": docs})

    return answer
```

That is essentially what happens.

---

# Visual

```text
User Question
      │
      ▼
Retriever
      │
      ▼
Retrieved Docs
      │
      ▼
Stuff Chain
      │
      ▼
LLM
      │
      ▼
Answer
```

---

# 3. create_history_aware_retriever()

This is the most interesting one.

---

## Problem

Normal retrievers fail with conversations.

Example:

### User

```text
Tell me about Amazon Bedrock.
```

Retriever works.

---

### Assistant

```text
Amazon Bedrock is...
```

---

### User

```text
Does it support Claude?
```

Now the retriever receives:

```text
Does it support Claude?
```

This query is terrible.

Retriever doesn't know:

```text
it = Amazon Bedrock
```

because retrievers don't understand conversation history.

---

Without history awareness:

```text
Query:
Does it support Claude?
```

Retriever may retrieve:

```text
Claude AI
Claude pricing
Claude API
```

instead of Bedrock documents.

---

# Solution

Rewrite question first.

Convert:

```text
Does it support Claude?
```

into

```text
Does Amazon Bedrock support Claude?
```

Then retrieve.

---

This is exactly what

```python
create_history_aware_retriever()
```

does.

---

# How it works

You provide:

```python
history_aware_retriever =
create_history_aware_retriever(
    llm,
    retriever,
    contextualize_q_prompt
)
```

---

Prompt:

```python
Given the chat history and latest user question,
rewrite the question so it can be understood
without the chat history.
```

---

Conversation:

```text
User:
Tell me about Bedrock.

Assistant:
Bedrock is AWS's managed AI platform.

User:
Does it support Claude?
```

---

LLM first receives:

```text
History:
User: Tell me about Bedrock

Assistant: Bedrock is AWS AI platform

Question:
Does it support Claude?

Rewrite:
```

LLM outputs:

```text
Does Amazon Bedrock support Claude?
```

---

Retriever then searches using:

```text
Does Amazon Bedrock support Claude?
```

instead of:

```text
Does it support Claude?
```

which dramatically improves retrieval quality.

---

# Internal Flow

Conceptually:

```python
def history_aware_retriever(question, history):

    standalone_question = llm.invoke(rewrite_prompt)

    docs = retriever.invoke(standalone_question)

    return docs
```

---

# Complete RAG Pipeline

Most tutorials combine all three.

```python
history_aware_retriever =
    create_history_aware_retriever(
        llm,
        retriever,
        contextualize_q_prompt
    )

document_chain =
    create_stuff_documents_chain(
        llm,
        qa_prompt
    )

rag_chain =
    create_retrieval_chain(
        history_aware_retriever,
        document_chain
    )
```

---

# End-to-End Execution Example

User:

```text
What is Amazon Bedrock?
```

---

History-aware retriever:

```text
No rewrite needed.
```

Retrieves:

```text
Doc1
Doc2
Doc3
```

---

Stuff chain creates:

```text
Context:
Doc1
Doc2
Doc3

Question:
What is Amazon Bedrock?
```

---

LLM:

```text
Amazon Bedrock is AWS's managed AI service...
```

---

Next turn:

```text
Does it support Claude?
```

---

History-aware retriever:

Rewrites:

```text
Does Amazon Bedrock support Claude?
```

---

Retriever:

```text
find Bedrock + Claude docs
```

---

Stuff chain:

```text
Context:
Bedrock supports Claude 3...

Question:
Does Amazon Bedrock support Claude?
```

---

LLM:

```text
Yes. Bedrock provides access to Claude models...
```

---

# What Actually Gets Built Internally (LCEL)

These helper functions are mostly wrappers around LCEL (LangChain Expression Language).

Under the hood the chain roughly becomes:

```text
input
  │
  ▼
question rewrite (optional)
  │
  ▼
retriever
  │
  ▼
documents
  │
  ▼
format documents
  │
  ▼
prompt template
  │
  ▼
llm
  │
  ▼
output parser
```

So:

* `create_history_aware_retriever()` = Query Rewriting Layer
* `create_stuff_documents_chain()` = Document Formatting + LLM Layer
* `create_retrieval_chain()` = Orchestration Layer connecting retrieval and generation

Together they form a complete conversational RAG pipeline with surprisingly little code.
