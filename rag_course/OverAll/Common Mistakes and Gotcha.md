# gotchas in rag pyhton

If you're learning RAG (Retrieval-Augmented Generation) with Python and LangChain, there are a lot of "gotchas" that can make your system behave incorrectly even though the code runs without errors.

Here are some of the most common ones.

# 1. Bad Chunking = Bad Retrieval

Many beginners split documents arbitrarily:

```python
RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
```

But if your chunk cuts a sentence or paragraph in half, retrieval quality drops.

### Example

Bad chunk:

```
The capital of France is
```

Next chunk:

```
Paris. It is known for...
```

Retriever may fail to find the answer.

### Better

Split on:

* paragraphs
* headings
* markdown sections
* semantic boundaries

---

# 2. Embedding Model Mismatch

A common mistake:

```python
# Build index
all - MiniLM - L6 - v2

# Query
bge - small - en
```

Documents and query must use the **same embedding model**.

Otherwise vectors live in different semantic spaces.

---

# 3. Forgetting to Normalize Embeddings

Some vector stores use:

```python
distance = cosine similarity
```

Others use:

```python
distance = L2 distance
```

For FAISS:

```python
HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    encode_kwargs={"normalize_embeddings": True},
)
```

Without normalization, similarity search may perform worse.

---

# 4. Chunk Size Too Large

People often do:

```python
chunk_size = 5000
```

Problems:

* retrieval becomes less precise
* embeddings become less focused
* context window fills quickly

Typical values:

```python
chunk_size = 500 - 1000
chunk_overlap = 50 - 200
```

---

# 5. Chunk Size Too Small

Opposite problem:

```python
chunk_size = 50
```

Information gets fragmented.

Question:

```
What are the company's PTO policies?
```

Answer may require 3 chunks.

Retriever returns only one.

---

# 6. Top-k Too Low

```python
retriever = vectorstore.as_retriever(search_kwargs={"k": 1})
```

If the first chunk isn't perfect:

```
No answer found
```

Try:

```python
k = 3
k = 5
k = 10
```

---

# 7. Top-k Too High

```python
k = 50
```

Now the LLM receives:

* useful chunks
* irrelevant chunks
* duplicated chunks

This causes:

* hallucinations
* higher token costs
* slower responses

---

# 8. Retriever Finds Similar Text, Not Correct Text

Embeddings perform semantic search.

Question:

```
What is PTO?
```

Retriever may find:

```
Vacation policy
```

instead of:

```
Paid Time Off (PTO)
```

This is expected.

Vector search is approximate.

---

# 9. Poor Documents

Garbage in → garbage out.

Examples:

```python
loader.load()
```

Document contains:

```
Header
Header
Header
Page 1
Footer
```

on every page.

Retriever becomes polluted with useless chunks.

Always inspect documents before indexing.

---

# 10. Not Storing Metadata

Bad:

```python
Document(page_content=text)
```

Better:

```python
Document(page_content=text, metadata={"source": "handbook.pdf", "page": 12})
```

Then you can cite sources later.

---

# 11. Hallucinations Still Happen

Many beginners think:

```
RAG = no hallucinations
```

False.

The LLM can still:

* misunderstand context
* invent details
* combine facts incorrectly

Prompting helps:

```python
If the answer is not in the context,
say "I don't know".
```

---

# 12. Context Overflow

Suppose:

```python
k = 10
```

Each chunk:

```python
1000 tokens
```

Context:

```python
10,000 tokens
```

Question:

```python
100 tokens
```

Prompt:

```python
500 tokens
```

You may exceed model limits.

---

# 13. FAISS Index Not Persisted

Bad:

```python
vectorstore = FAISS.from_documents(...)
```

Every run:

```python
re-embed everything
```

Slow and expensive.

Use:

```python
vectorstore.save_local("faiss_index")
```

Later:

```python
FAISS.load_local(...)
```

---

# 14. Retrieval Quality Looks Good But Isn't

Many beginners test:

```python
"What is the PTO policy?"
```

after indexing a PTO document.

Of course it works.

Real tests:

* paraphrased questions
* vague questions
* typo-filled questions
* questions requiring multiple chunks

Example:

```
How many vacation days do employees need to take at minimum?
```

instead of:

```
What is the mandatory PTO minimum?
```

---

# 15. LCEL Variable Name Mismatches

Very common in LangChain.

Prompt:

```python
{context}
{question}
```

Chain:

```python
{"docs": retriever, "query": RunnablePassthrough()}
```

Error:

```
Missing input variable 'context'
```

Prompt variables and chain outputs must match exactly.

---

# 16. Retrievers Only See What You Pass

In your LCEL chain:

```python
context = (lambda x: x["question"]) | retriever | format_docs
```

The retriever receives only:

```python
x["question"]
```

not the whole dictionary.

Many beginners assume retriever gets:

```python
{"question": "...", "chat_history": "...", "user_id": ...}
```

It doesn't unless you explicitly pass them.

---

# 17. "Working" ≠ "Good"

A RAG system can:

* run successfully
* return answers
* have no exceptions

and still retrieve terrible context.

Always inspect:

```python
docs = retriever.invoke(question)

for d in docs:
    print(d.page_content)
```

before blaming the LLM.

---

# 18. Most RAG Problems Are Retrieval Problems

Beginners often think:

```
Need a better LLM
```

But usually the issue is:

* chunking
* embeddings
* indexing
* retrieval strategy
* metadata

A stronger model cannot answer correctly if the right information never reaches it.

### Debugging Order

When a RAG answer is wrong:

1. Check retrieved chunks.
2. Check chunking strategy.
3. Check embeddings.
4. Check top-k.
5. Check prompt.
6. Only then consider changing the LLM.

For your current LangChain + FAISS + Gemini setup, the most useful debugging statement is often:

```python
docs = retriever.invoke(question)

print("\nRetrieved Chunks:")
for i, doc in enumerate(docs, 1):
    print(f"\n--- Chunk {i} ---")
    print(doc.page_content[:500])
```

If the correct information is not in those chunks, the LLM never had a chance to answer correctly.


# Q2: 
but what is gotchas

is it a technical term?
is it a slang?

what exactly it means in AI or RAG or python context?




# A2:
"Gotcha" is not a formal technical term. It's an informal English word that became very common in programming and engineering.

### Literal meaning

"Gotcha" comes from:

> "Got you!"

Meaning:

> "Aha! I caught you making a mistake."

Example:

```text
You forgot a semicolon.
Gotcha!
```

---

## In programming

A **gotcha** means:

> A subtle behavior, hidden trap, surprising rule, or common mistake that catches many developers.

It's usually something that:

* isn't obvious
* isn't necessarily a bug
* often surprises beginners
* can even surprise experienced developers

---

### Example 1: Python mutable default arguments

```python
def add_item(item, my_list=[]):
    my_list.append(item)
    return my_list
```

Many beginners expect:

```python
add_item("A")
# ["A"]

add_item("B")
# ["B"]
```

Actual result:

```python
["A"]
["A", "B"]
```

This is a famous Python gotcha.

The code is valid.

No error occurs.

But the behavior surprises people.

---

### Example 2: Floating-point numbers

```python
0.1 + 0.2
```

Expected:

```python
0.3
```

Actual:

```python
0.30000000000000004
```

Another classic gotcha.

---

## In AI / LangChain / RAG

A gotcha is usually:

> Something that makes your system behave unexpectedly even though the code looks correct.

### Example

```python
retriever = vectorstore.as_retriever(search_kwargs={"k": 1})
```

The code runs.

No exception.

But retrieval quality becomes terrible.

That's a RAG gotcha.

---

### Another RAG gotcha

```python
chunk_size = 10000
```

Everything indexes successfully.

Search works.

Answers are bad.

The hidden trap is oversized chunks.

Again, a gotcha.

---

## Difference between Bug and Gotcha

### Bug

Something is actually wrong.

```python
print(x)
```

Output:

```python
NameError: x is not defined
```

That's a bug/error.

---

### Gotcha

Code runs successfully.

```python
vectorstore.save_local(...)
```

You forget to load it later.

Program still runs.

But it re-embeds everything every time.

Unexpected behavior.

That's a gotcha.

---

## Why programmers use the word so much

When you read:

* "Python gotchas"
* "Docker gotchas"
* "LangChain gotchas"
* "RAG gotchas"

it usually means:

> "Here are the common traps, surprising behaviors, and mistakes you should know before using this technology."

For example:

### Python Gotchas

* mutable default arguments
* late binding in closures
* floating-point precision

### Docker Gotchas

* data disappears if volumes aren't used
* localhost inside a container isn't your host machine

### RAG Gotchas

* poor chunking
* embedding mismatch
* top-k too high/low
* context window overflow
* retrieval quality not inspected

---

### A good mental definition

A **gotcha** is:

> A hidden trap that doesn't look wrong at first glance but can cause unexpected results if you don't know about it.

That's how the word is used in Python, AI, LangChain, RAG, databases, Docker, and software engineering in general.

