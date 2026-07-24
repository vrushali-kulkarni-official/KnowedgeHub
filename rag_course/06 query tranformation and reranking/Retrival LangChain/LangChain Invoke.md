# Q:
explain what does .invoke() function do?

is it langchain specific ? or is it available for all functions in python ?

in the below program explain how the parameters are passes in the invoke function?

what if there are multiple inputs to be passes in the invoke fuct? 

how does the retriever work ? where and how does the retriever take input ? and how does the retriever work ? what if I want to pass multiple inputs to retriever? 

what value goes inside context for this line :  context=(lambda x: x["question"]) | retriever | format_docs
only the output of (lambda x: x["question"]) or the output of format_docs ?

when is the prompt in the following line actually invoked in the program?  prompt = ChatPromptTemplate.from_messages([
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
what value goes inside it ? when and from where does it get the context value and when does it get the question value ? 

program:


from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import FAISS
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

DOCS_PATH = Path(__file__).parent / "data" / "sample_doc.txt"
INDEX_DIR = Path(__file__).parent / "faiss_index"

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

GEMINI_MODEL = "gemini-2.0-flash"

def build_index() -> FAISS:
    print(f"[1/4] Loading document: {DOCS_PATH}")
    loader = TextLoader(str(DOCS_PATH), encoding="utf-8")
    documents = loader.load()
    print(f"      -> {len(documents)} document(s) loaded.")

    print("[2/4] Splitting into chunks...")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
    )
    chunks = splitter.split_documents(documents)
    print(f"      -> {len(chunks)} chunks produced.")

    print(f"[3/4] Embedding chunks with {EMBEDDING_MODEL_NAME}...")
    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL_NAME,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )

    print(f"[4/4] Building FAISS index, saving to {INDEX_DIR}...")
    vectorstore = FAISS.from_documents(chunks, embeddings)
    vectorstore.save_local(str(INDEX_DIR))
    print("      -> Index built and saved.")
    return vectorstore

def format_docs(docs) -> str:
    return "\n\n---\n\n".join(doc.page_content for doc in docs)

def build_rag_chain(vectorstore: FAISS):
    retriever = vectorstore.as_retriever(
        search_type="similarity",
        search_kwargs={"k": 4},
    )

    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Copy .env.example to .env and fill it in."
        )
    llm = ChatGoogleGenerativeAI(
        model=GEMINI_MODEL,
        temperature=0,
    )

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

    rag_chain = (
        RunnablePassthrough.assign(
            context=(lambda x: x["question"]) | retriever | format_docs,
        )
        | prompt
        | llm
        | StrOutputParser()
    )
    return rag_chain

def main() -> None:
    if not INDEX_DIR.exists():
        vectorstore = build_index()
    else:
        print(f"Loading existing index from {INDEX_DIR}...")
        embeddings = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL_NAME,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        vectorstore = FAISS.load_local(
            str(INDEX_DIR),
            embeddings,
            allow_dangerous_deserialization=True,
        )

    chain = build_rag_chain(vectorstore)

    questions = [
        "What is the name of the company's flagship product?",
        "Who is the CTO?",
        "What is the weather like in Paris tomorrow?",
    ]
    for q in questions:
        print(f"\nQ: {q}")
        answer = chain.invoke({"question": q})
        print(f"A: {answer}")

if __name__ == "__main__":
    main()



# A:

These are exactly the right questions to ask when learning LCEL (LangChain Expression Language). The biggest challenge for beginners is understanding **how data flows through the chain**.

Let's trace your program step-by-step.

---

# 1. What is `.invoke()`?

`.invoke()` is **not a Python function**.

It is a **LangChain Runnable method**.

Example:

```python
answer = chain.invoke({"question": q})
```

Here:

```python
chain
```

is not a normal Python function.

It is a LangChain Runnable object created by:

```python
rag_chain = RunnablePassthrough.assign(...) | prompt | llm | StrOutputParser()
```

All LCEL components implement a common interface:

```python
.invoke(input)
.batch(inputs)
.stream(input)
.ainvoke(input)
```

Think of it like:

```python
result = some_runnable.invoke(input)
```

which means:

```python
result = some_runnable.run(input)
```

(not actual code, just conceptual)

---

# 2. Is `.invoke()` available for all Python functions?

No.

Normal Python functions:

```python
def add(a, b):
    return a + b
```

are called like:

```python
add(2, 3)
```

not:

```python
add.invoke(...)
```

This would fail:

```python
AttributeError
```

because normal functions don't have an `.invoke()` method.

---

# 3. What input does invoke receive?

You call:

```python
chain.invoke({"question": q})
```

Example:

```python
chain.invoke({"question": "Who is the CTO?"})
```

So the chain receives:

```python
{"question": "Who is the CTO?"}
```

This becomes the input to the first Runnable.

---

# 4. What happens first?

The chain begins here:

```python
RunnablePassthrough.assign(
    context=(lambda x: x["question"]) | retriever | format_docs,
)
```

Input:

```python
{"question": "Who is the CTO?"}
```

---

# 5. What does RunnablePassthrough do?

It preserves the original input.

Input:

```python
{"question": "Who is the CTO?"}
```

Output (initially):

```python
{"question": "Who is the CTO?"}
```

Then `.assign()` adds new keys.

---

# 6. What does assign() do?

This:

```python
.assign(
    context=...
)
```

means:

```python
take existing input
compute context
add it as a new field
```

Conceptually:

```python
output = {**input, "context": computed_value}
```

---

# 7. How does this pipeline work?

```python
(lambda x: x["question"]) | retriever | format_docs
```

The `|` operator means:

```python
output_of_left
    becomes
input_of_right
```

Like Unix pipes.

---

## Step 1

Input:

```python
{"question": "Who is the CTO?"}
```

Lambda:

```python
lambda x: x["question"]
```

returns:

```python
"Who is the CTO?"
```

---

## Step 2

Retriever receives:

```python
"Who is the CTO?"
```

Notice:

The retriever does NOT receive the whole dictionary.

It only receives:

```python
"Who is the CTO?"
```

because that's the output of the lambda.

---

# 8. How does retriever work?

Created here:

```python
retriever = vectorstore.as_retriever()
```

A retriever expects:

```python
str
```

as input.

Example:

```python
retriever.invoke("Who is the CTO?")
```

Internally:

### A. Embed query

```python
"Who is the CTO?"
```

↓

embedding model

↓

vector

Example:

```python
[0.23, -0.11, 0.91, ...]
```

---

### B. Search FAISS

FAISS compares:

```python
query vector
```

against

```python
chunk vectors
```

stored in the index.

---

### C. Return top matches

Example:

```python
[
    Document(page_content="The CTO is Sarah Chen."),
    Document(page_content="Sarah joined in 2021."),
]
```

---

# 9. What if I want multiple inputs to retriever?

A retriever normally expects:

```python
query: str
```

Suppose you have:

```python
{"question": "...", "department": "engineering"}
```

You must combine them yourself:

```python
(lambda x:
    f"{x['question']} department:{x['department']}"
)
| retriever
```

or use a custom retriever.

The retriever only receives whatever the previous stage outputs.

---

# 10. What does format_docs receive?

Retriever returns:

```python
[Document(...), Document(...), Document(...)]
```

That becomes input to:

```python
format_docs
```

So:

```python
format_docs(docs)
```

receives:

```python
list[Document]
```

---

Example:

```python
[Document(page_content="CTO is Sarah"), Document(page_content="Sarah joined 2021")]
```

---

Returns:

```python
CTO is Sarah

---

Sarah joined 2021
```

as a string.

---

# 11. What goes into context?

Excellent question.

This line:

```python
context=
    (lambda x: x["question"])
    | retriever
    | format_docs
```

stores the **final output** of the pipeline.

Not the lambda output.

Not the retriever output.

The FINAL output.

So:

```python
context =
"CTO is Sarah

---

Sarah joined 2021"
```

---

After assign:

Input:

```python
{"question": "Who is the CTO?"}
```

becomes:

```python
{"question": "Who is the CTO?", "context": "CTO is Sarah\n\n---\n\nSarah joined 2021"}
```

---

# 12. What gets passed to prompt?

The prompt receives:

```python
{"question": "Who is the CTO?", "context": "CTO is Sarah..."}
```

---

# 13. When is the prompt actually invoked?

Here:

```python
RunnablePassthrough.assign(...)
| prompt
| llm
```

When execution reaches:

```python
| prompt
```

LangChain automatically calls:

```python
prompt.invoke(...)
```

internally.

You don't see it happening.

It is done by the chain.

---

# 14. How does prompt get context?

Because assign created it.

Remember:

Before prompt:

```python
{"question": "Who is the CTO?", "context": "CTO is Sarah..."}
```

Prompt sees:

```python
{context}
```

and

```python
{question}
```

placeholders.

It fills them automatically.

---

# 15. What does the final prompt look like?

System message:

```text
You are a precise assistant.

Context:
CTO is Sarah...

---
Sarah joined 2021
```

Human message:

```text
Who is the CTO?
```

---

# 16. Then what happens?

Prompt output:

```python
ChatPromptValue
```

↓

passed to

```python
llm
```

↓

Gemini generates:

```text
The CTO is Sarah Chen. [source: 1]
```

↓

passed to

```python
StrOutputParser()
```

↓

returns plain string

```python
"The CTO is Sarah Chen. [source: 1]"
```

---

# Complete Data Flow

For:

```python
chain.invoke({"question": "Who is the CTO?"})
```

the execution is:

```text
INPUT
{
  question: "Who is the CTO?"
}

        ↓

lambda
x["question"]

        ↓

"Who is the CTO?"

        ↓

retriever

        ↓

[
  Document(...),
  Document(...)
]

        ↓

format_docs

        ↓

"CTO is Sarah..."

        ↓

assign

{
  question: "Who is the CTO?",
  context: "CTO is Sarah..."
}

        ↓

prompt

System: Context: CTO is Sarah...
Human: Who is the CTO?

        ↓

Gemini

"The CTO is Sarah."

        ↓

StrOutputParser

"The CTO is Sarah."

        ↓

RETURNED BY invoke()
```

A useful mental model is:

```python
invoke(input)
```

starts the chain, and every component receives the output of the component immediately before it. The `assign()` step is special because it keeps the original input and adds new fields (like `context`) that later components such as the prompt can use.
