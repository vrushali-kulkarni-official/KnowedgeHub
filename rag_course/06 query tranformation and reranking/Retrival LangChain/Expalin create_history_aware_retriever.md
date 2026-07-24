`create_history_aware_retriever()` is one of the most misunderstood LangChain functions because it looks like "magic", but internally it's actually a very small chain that sits **before your retriever**.

The purpose is simple:

> Convert a conversational question into a standalone search query before retrieval.

---

# The Problem It Solves

Imagine a user asks:

```text
User: Tell me about PostgreSQL
AI: PostgreSQL is a relational database...

User: How does it handle transactions?
```

The second question:

```text
How does it handle transactions?
```

is impossible for a retriever to understand by itself.

A vector DB sees:

```text
How does it handle transactions?
```

What is "it"?

* PostgreSQL?
* MongoDB?
* DynamoDB?

The retriever has no idea.

---

# Without History Aware Retriever

Query sent to retriever:

```text
How does it handle transactions?
```

Retriever searches embeddings for:

```text
How does it handle transactions?
```

Results may contain:

```text
Bank transactions
Payment transactions
Blockchain transactions
```

Totally wrong.

---

# With History Aware Retriever

The chat history is first analyzed.

Input:

```text
History:
User: Tell me about PostgreSQL
AI: PostgreSQL is ...

Question:
How does it handle transactions?
```

LLM rewrites:

```text
How does PostgreSQL handle transactions?
```

NOW retrieval happens.

Retriever searches:

```text
How does PostgreSQL handle transactions?
```

Results become relevant.

---

# Function Signature

Typically:

```python
from langchain.chains.history_aware_retriever import create_history_aware_retriever

history_aware_retriever = create_history_aware_retriever(llm, retriever, prompt)
```

---

# Internally What Gets Created

Conceptually:

```text
                 User Question
                        |
                        v
                Chat History
                        |
                        v
                    Prompt
                        |
                        v
                      LLM
                        |
                        v
            Rewritten Search Query
                        |
                        v
                  Retriever
                        |
                        v
                  Documents
```

---

# Actual Internal Data Flow

Suppose:

```python
chat_history = [
    HumanMessage("Tell me about PostgreSQL"),
    AIMessage("PostgreSQL is a relational database"),
]

input = "How does it handle transactions?"
```

---

## Step 1

LangChain builds prompt variables:

```python
{"chat_history": chat_history, "input": "How does it handle transactions?"}
```

---

## Step 2

Prompt Template Executes

Example prompt:

```python
prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "Given chat history and latest user question "
        "rewrite it as a standalone search query.",
    ),
    MessagesPlaceholder("chat_history"),
    ("human", "{input}"),
])
```

Produces:

```text
SYSTEM:
Given chat history and latest user question,
rewrite it as standalone search query.

USER:
Tell me about PostgreSQL

AI:
PostgreSQL is a relational database

USER:
How does it handle transactions?
```

---

## Step 3

Prompt Sent To LLM

```python
rewritten_query = llm.invoke(...)
```

LLM returns:

```text
How does PostgreSQL handle transactions?
```

---

## Step 4

Retriever Executes

LangChain now calls:

```python
retriever.invoke("How does PostgreSQL handle transactions?")
```

instead of:

```python
retriever.invoke("How does it handle transactions?")
```

---

## Step 5

Documents Returned

```python
[Document(...), Document(...), Document(...)]
```

These documents are returned to the next chain.

---

# Internal Chain Structure

Internally it is basically:

```text
Prompt
  |
  v
LLM
  |
  v
StrOutputParser
  |
  v
Retriever
```

In LCEL notation:

```python
prompt | llm | StrOutputParser() | retriever
```

Not exactly the source code, but conceptually very close.

---

# Actual Source Logic (Simplified)

Internally LangChain does something similar:

```python
if chat_history:
    query = llm.invoke(prompt.format(chat_history=history, input=user_question))

    docs = retriever.invoke(query)

else:
    docs = retriever.invoke(user_question)
```

Notice something important:

### If No Chat History Exists

LangChain skips the LLM.

Directly:

```python
retriever.invoke(user_question)
```

This saves latency and tokens.

---

# Complete Chain Created

The object returned is actually a Runnable.

Conceptually:

```text
RunnableBranch
├── Has History?
│
├── YES
│     Prompt
│       |
│       v
│      LLM
│       |
│       v
│  Rewritten Query
│       |
│       v
│   Retriever
│
└── NO
        |
        v
    Retriever
```

This is closer to the real implementation.

---

# Why RunnableBranch?

Because LangChain checks:

```python
if chat_history:
```

If history exists:

```python
rewrite → retrieve
```

Otherwise:

```python
retrieve directly
```

This branching is implemented using LCEL's `RunnableBranch`.

---

# Input and Output Schema

Input:

```python
{"input": "How does it handle transactions?", "chat_history": [...]}
```

Output:

```python
[Document(...), Document(...), Document(...)]
```

Notice:

The output is **documents**, not text.

This is important.

Many people think:

```text
Question -> create_history_aware_retriever -> Answer
```

Wrong.

It only retrieves.

Output:

```text
Question
   |
   v
Standalone Query
   |
   v
Documents
```

No answer generation happens here.

---

# In a Full Conversational RAG

Usually:

```python
history_aware_retriever
```

is combined with:

```python
create_stuff_documents_chain()
```

inside:

```python
create_retrieval_chain()
```

Full flow:

```text
User Question
      |
      v
Chat History
      |
      v
History Aware Retriever
      |
      +------------------+
      |                  |
      v                  |
Rewrite Query           |
      |                  |
      v                  |
Retriever               |
      |                  |
      +------------------+
              |
              v
         Documents
              |
              v
 Stuff Documents Chain
              |
              v
             LLM
              |
              v
            Answer
```

---

# Production Reality

In production RAG systems, `create_history_aware_retriever()` is usually just the first layer of query transformation.

Many systems expand it to:

```text
User Query
     |
     v
Intent Detection
     |
     v
Entity Extraction
     |
     v
History Rewrite
     |
     v
Query Expansion
     |
     v
Multi Query Generation
     |
     v
Hybrid Search
     |
     v
Reranking
```

LangChain's `create_history_aware_retriever()` only implements the **history rewrite step**.

Think of it as:

```text
Conversation Question
        ↓
Standalone Search Query
```

and nothing more. That's its entire responsibility.
