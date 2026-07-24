# Q:
what is runnable in AI langchain. please explain in detail 

and then explain from langchain_core.runnables import RunnablePassthrough

after that explain 
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
    ]) rag_chain = (
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

This code is using **LCEL (LangChain Expression Language)**, which is built around the concept of **Runnables**.

To understand `RunnablePassthrough`, you first need to understand what a **Runnable** is.

---

# 1. What is a Runnable in LangChain?

A **Runnable** is any object that can take an input and produce an output.

Think of it like a machine:

```text
Input
  ↓
Runnable
  ↓
Output
```

Example:

```python
from langchain_core.runnables import RunnableLambda

add_one = RunnableLambda(lambda x: x + 1)

result = add_one.invoke(5)

print(result)
```

Output:

```python
6
```

Here:

```python
5
 ↓
add_one
 ↓
6
```

The runnable receives an input and returns an output.

---

# Why LangChain Uses Runnables

Before LCEL, chains were built manually:

```python
docs = retriever.get_relevant_documents(question)

prompt = template.format(context=docs, question=question)

response = llm.invoke(prompt)
```

Lots of intermediate variables.

With Runnables:

```python
retriever | prompt | llm
```

Data automatically flows through the pipeline.

---

# Every Step is a Runnable

Examples:

### Prompt

```python
prompt = ChatPromptTemplate(...)
```

Runnable:

```python
input dict
    ↓
prompt
    ↓
formatted prompt
```

---

### LLM

```python
llm = ChatOpenAI(...)
```

Runnable:

```python
prompt
   ↓
llm
   ↓
AIMessage
```

---

### Output Parser

```python
StrOutputParser()
```

Runnable:

```python
AIMessage
    ↓
parser
    ↓
string
```

---

### Retriever

```python
retriever
```

Runnable:

```python
question
    ↓
retriever
    ↓
documents
```

---

# Runnable Interface

Every runnable has methods like:

### invoke()

Single input

```python
chain.invoke("hello")
```

---

### batch()

Multiple inputs

```python
chain.batch(["hello", "how are you"])
```

---

### stream()

Token streaming

```python
for chunk in chain.stream("hello"):
    print(chunk)
```

---

# LCEL Operator |

This:

```python
a | b | c
```

means:

```python
output1 = a(input)

output2 = b(output1)

output3 = c(output2)
```

Exactly like Unix pipes.

---

Example

```python
chain = prompt | llm | StrOutputParser()
```

Flow:

```text
User Question
      ↓
Prompt
      ↓
Formatted Prompt
      ↓
LLM
      ↓
AIMessage
      ↓
Parser
      ↓
String
```

---

# 2. What is RunnablePassthrough?

Now let's focus on:

```python
from langchain_core.runnables import RunnablePassthrough
```

A RunnablePassthrough does exactly what its name suggests.

It passes data through unchanged.

Example:

```python
runnable = RunnablePassthrough()

result = runnable.invoke("hello")
```

Output:

```python
hello
```

Input:

```python
hello
```

Output:

```python
hello
```

No modification.

---

# Why is it Useful?

Because sometimes you want to keep the original input while adding new fields.

Imagine:

```python
{"question": "What is FAISS?"}
```

You want:

```python
{"question": "What is FAISS?", "context": "Retrieved documents..."}
```

without losing the question.

That's where:

```python
RunnablePassthrough.assign()
```

comes in.

---

# RunnablePassthrough.assign()

Example:

```python
chain = RunnablePassthrough.assign(age=lambda x: 25)
```

Input:

```python
{"name": "John"}
```

Output:

```python
{"name": "John", "age": 25}
```

It keeps existing fields and adds new ones.

---

Another example:

```python
chain = RunnablePassthrough.assign(length=lambda x: len(x["text"]))
```

Input:

```python
{"text": "hello"}
```

Output:

```python
{"text": "hello", "length": 5}
```

---

# Visualizing assign()

Input:

```python
{"question": "What is FAISS?"}
```

After assign:

```python
{"question": "What is FAISS?", "context": "FAISS is a vector search library..."}
```

The original question survives.

That's the key idea.

---

# 3. Understanding Your Prompt

You have:

```python
prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "... Context:\n{context}",
    ),
    ("human", "{question}"),
])
```

This creates a prompt template.

---

Expected Input

The prompt expects:

```python
{"context": "...", "question": "..."}
```

because it contains:

```python
{context}
```

and

```python
{question}
```

---

If given:

```python
{"context": "FAISS is a vector DB", "question": "What is FAISS?"}
```

The final prompt becomes:

```text
SYSTEM:
You are a precise assistant...

Context:
FAISS is a vector DB

HUMAN:
What is FAISS?
```

---

# 4. Understanding the Entire Chain

Now let's dissect:

```python
rag_chain = (
    RunnablePassthrough.assign(
        context=(lambda x: x["question"]) | retriever | format_docs,
    )
    | prompt
    | llm
    | StrOutputParser()
)
```

This is the most important part.

---

# Step 1 Input

Suppose:

```python
rag_chain.invoke({"question": "What is FAISS?"})
```

Input:

```python
{"question": "What is FAISS?"}
```

---

# Step 2 RunnablePassthrough.assign

You have:

```python
context = (lambda x: x["question"]) | retriever | format_docs
```

Let's examine that pipeline.

---

## First Runnable

```python
lambda x: x["question"]
```

Input:

```python
{"question": "What is FAISS?"}
```

Output:

```python
"What is FAISS?"
```

---

## Retriever

```python
retriever
```

Input:

```python
"What is FAISS?"
```

Output:

```python
[Document(...), Document(...), Document(...)]
```

---

## format_docs

Maybe:

```python
def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)
```

Output:

```python
"FAISS is Facebook AI Similarity Search..."
```

---

So:

```python
(lambda x: x["question"])
    | retriever
    | format_docs
```

produces:

```python
"FAISS is Facebook AI Similarity Search..."
```

---

# assign Adds This Result

Original:

```python
{"question": "What is FAISS?"}
```

New field:

```python
"context": "FAISS is Facebook AI Similarity Search..."
```

Result:

```python
{"question": "What is FAISS?", "context": "FAISS is Facebook AI Similarity Search..."}
```

---

# Why RunnablePassthrough?

Without it:

```python
retriever
```

would replace the entire input.

You would lose:

```python
question
```

With passthrough:

```python
question
```

is preserved.

---

# Step 3 Prompt

Now prompt receives:

```python
{"question": "What is FAISS?", "context": "FAISS is Facebook AI Similarity Search..."}
```

and fills:

```python
{context}
```

and

```python
{question}
```

---

Generated prompt:

```text
SYSTEM:
You are a precise assistant...

Context:
FAISS is Facebook AI Similarity Search...

HUMAN:
What is FAISS?
```

---

# Step 4 LLM

```python
| llm
```

The prompt is sent to the model.

Output:

```python
AIMessage(content="FAISS is a similarity search library...")
```

---

# Step 5 StrOutputParser

```python
| StrOutputParser()
```

Converts:

```python
AIMessage(content="...")
```

into:

```python
"FAISS is a similarity search library..."
```

---

# Complete Data Flow

```text
User Input
{
  "question": "What is FAISS?"
}
          │
          ▼
RunnablePassthrough.assign()
          │
          ▼
lambda x["question"]
          │
          ▼
Retriever
          │
          ▼
Documents
          │
          ▼
format_docs
          │
          ▼
{
  "question": "What is FAISS?",
  "context": "retrieved text"
}
          │
          ▼
Prompt Template
          │
          ▼
Formatted Chat Prompt
          │
          ▼
LLM
          │
          ▼
AIMessage
          │
          ▼
StrOutputParser
          │
          ▼
Final String Answer
```

---

The most important concept in this code is that:

```python
RunnablePassthrough.assign(...)
```

creates a new key (`context`) while preserving the original input (`question`).

Without it, the retriever would output only documents and the prompt would no longer have access to the `question` variable needed for `{question}`.



# Q2:

i am a beginer in python AI and LCEL

please explain what is lambda  which is used everywhere:

eg: chain = RunnablePassthrough.assign(
    length=lambda x: len(x["text"])
)

rag_chain = (
    RunnablePassthrough.assign(
        context=(lambda x: x["question"]) | retriever | format_docs,
    )
    | prompt
    | llm
    | StrOutputParser()
)

context=(lambda x: x["question"]) | retriever | format_docs


# A2:

Since you're learning Python, AI, and LangChain from scratch, it's worth understanding **lambda** properly because you'll see it everywhere in LangChain, LCEL, FastAPI, Pandas, and many other Python libraries.

---

# What is a lambda?

A **lambda** is simply a **small anonymous function**.

Anonymous means:

* It is a function
* But it doesn't have a name

---

## Normal Function

Suppose you write:

```python
def get_question(x):
    return x["question"]
```

Usage:

```python
result = get_question({"question": "What is FAISS?"})
```

Output:

```python
"What is FAISS?"
```

---

## Same Thing Using Lambda

```python
lambda x: x["question"]
```

This is exactly equivalent to:

```python
def get_question(x):
    return x["question"]
```

Python automatically assumes:

```python
return x["question"]
```

---

# Lambda Syntax

General form:

```python
lambda arguments: expression
```

Example:

```python
lambda x: x + 1
```

Equivalent to:

```python
def add_one(x):
    return x + 1
```

---

Another example:

```python
lambda name: "Hello " + name
```

Equivalent to:

```python
def greet(name):
    return "Hello " + name
```

---

# Why Use Lambda?

Imagine you need a tiny function only once.

Instead of:

```python
def get_question(x):
    return x["question"]


chain = get_question | retriever
```

you can write:

```python
chain = (lambda x: x["question"]) | retriever
```

Shorter and cleaner.

---

# Understanding the `x`

When beginners see:

```python
lambda x: x["question"]
```

they often ask:

> Where did x come from?

The answer:

`x` is whatever input the runnable receives.

---

Example:

```python
f = lambda x: x["question"]

input_data = {"question": "What is FAISS?"}

print(f(input_data))
```

Output:

```python
What is FAISS?
```

Python internally does:

```python
x = {"question": "What is FAISS?"}
```

then:

```python
x["question"]
```

---

# Example 1

```python
lambda x: x + 10
```

Input:

```python
5
```

Output:

```python
15
```

---

Equivalent to:

```python
def add_ten(x):
    return x + 10
```

---

# Example 2

```python
lambda x: len(x)
```

Input:

```python
"hello"
```

Output:

```python
5
```

---

Equivalent to:

```python
def get_length(x):
    return len(x)
```

---

# Example 3

```python
lambda x: x.upper()
```

Input:

```python
"hello"
```

Output:

```python
"HELLO"
```

---

Equivalent to:

```python
def make_upper(x):
    return x.upper()
```

---

# Your First LangChain Example

You have:

```python
RunnablePassthrough.assign(length=lambda x: len(x["text"]))
```

Let's understand step by step.

---

Input:

```python
{"text": "hello world"}
```

---

Lambda executes:

```python
len(x["text"])
```

becomes:

```python
len("hello world")
```

Output:

```python
11
```

---

Assign adds this new field:

Result:

```python
{"text": "hello world", "length": 11}
```

---

Visual:

```text
Input
{
  "text": "hello world"
}

        │
        ▼

lambda x: len(x["text"])

        │
        ▼

11

        │
        ▼

{
  "text": "hello world",
  "length": 11
}
```

---

# Your RAG Example

Let's examine:

```python
context = (lambda x: x["question"]) | retriever | format_docs
```

This is actually three runnables connected together.

---

## Input

```python
{"question": "What is FAISS?"}
```

---

## Step 1

```python
lambda x: x["question"]
```

Equivalent to:

```python
def extract_question(x):
    return x["question"]
```

Output:

```python
"What is FAISS?"
```

---

Visual:

```text
{
  "question": "What is FAISS?"
}
          │
          ▼
lambda x: x["question"]
          │
          ▼
"What is FAISS?"
```

---

## Step 2

Retriever receives:

```python
"What is FAISS?"
```

and searches your vector database.

Maybe it returns:

```python
[
    Document(page_content="FAISS is a vector search library"),
    Document(page_content="Created by Facebook AI"),
]
```

---

Visual:

```text
"What is FAISS?"
          │
          ▼
Retriever
          │
          ▼
Documents
```

---

## Step 3

`format_docs`

Maybe:

```python
def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)
```

Input:

```python
[Document(...), Document(...)]
```

Output:

```python
FAISS is a vector search library

Created by Facebook AI
```

---

Visual:

```text
Documents
     │
     ▼
format_docs
     │
     ▼
Context String
```

---

# Why Is Lambda Needed?

The retriever expects:

```python
str
```

like:

```python
"What is FAISS?"
```

But your chain input is:

```python
{"question": "What is FAISS?"}
```

The retriever cannot search using a dictionary.

So you first extract the question:

```python
lambda x: x["question"]
```

which converts:

```python
{"question": "What is FAISS?"}
```

into:

```python
"What is FAISS?"
```

Now the retriever can use it.

---

# Equivalent Code Without Lambda

Your LCEL:

```python
context = (lambda x: x["question"]) | retriever | format_docs
```

can be written as normal Python:

```python
def build_context(x):
    question = x["question"]

    docs = retriever.invoke(question)

    return format_docs(docs)
```

The lambda version is simply a compact way of writing:

```python
question = x["question"]
```

inside the chain.

---

# A Useful Rule for LangChain Beginners

Whenever you see:

```python
lambda x: ...
```

translate it mentally into:

```python
def some_function(x):
    return ...
```

For example:

```python
lambda x: x["question"]
```

becomes:

```python
def some_function(x):
    return x["question"]
```

and

```python
lambda x: len(x["text"])
```

becomes:

```python
def some_function(x):
    return len(x["text"])
```

This trick makes LCEL chains much easier to read when you're starting out.

For learning purposes, I actually recommend writing normal `def` functions first and only switching to `lambda` once you're comfortable. Most LCEL examples become much easier to understand when you rewrite every lambda as a regular function and trace the data flowing through the chain step by step.


