`create_retrieval_chain()` is the LangChain helper that wires together two steps into one RAG pipeline: first it retrieves relevant documents, then it hands those documents to a “combine documents” chain that produces the final answer. LangChain’s classic reference describes it exactly that way, and the deprecated `RetrievalQA` docs point to `create_retrieval_chain` as the modern replacement pattern. ([LangChain Reference][1])

## The mental model

Think of it as a factory line:

1. User asks a question.
2. Retriever fetches the most relevant chunks.
3. Retrieved chunks are inserted into a prompt as `context`.
4. LLM reads the prompt and writes the answer.
5. The chain returns both the answer and the retrieved context. ([LangChain Reference][1])

So `create_retrieval_chain()` does **not** do embeddings, chunking, or vector search by itself. It orchestrates the pieces you already built. The actual retrieval logic comes from your retriever; the answer-generation logic comes from the `combine_docs_chain` you pass in. ([aidoczh.com][2])

## What it takes as input

At a high level, it takes:

* `retriever`: a `BaseRetriever` or a Runnable that returns a list of documents
* `combine_docs_chain`: a Runnable that accepts the retrieved docs plus the original inputs and returns text/answer content ([aidoczh.com][2])

A key detail: if you pass a normal `BaseRetriever`, the chain expects the query under the `input` key. If `chat_history` is not present, LangChain fills it with `[]` so conversational retrieval prompts can still work smoothly. ([aidoczh.com][2])

## What it returns

The returned object is an LCEL Runnable. The result is a dictionary containing at least:

* `context`: the retrieved documents
* `answer`: the generated answer ([aidoczh.com][2])

That is very different from the older `RetrievalQA` style, which often hid more of the plumbing. LangChain’s deprecation note for `RetrievalQA` specifically points you toward `create_retrieval_chain` instead. ([LangChain Reference][3])

## What happens internally

Internally, the chain is just composition:

* it forwards the user query to the retriever
* it gets back a list of documents
* it injects those documents into the downstream chain under `context`
* it forwards the original inputs too
* it ensures `chat_history` exists, defaulting to an empty list if needed ([aidoczh.com][2])

That means the “brain” of the final answer is still your prompt + LLM. The retrieval helper only ensures the right documents arrive in the right place.

## The most common setup

In practice, `create_retrieval_chain()` is usually paired with `create_stuff_documents_chain()`. The “stuff” chain formats multiple documents into a single context block, then the prompt references `{context}` and `{input}`. ([aidoczh.com][2])

### Typical code

```python
from langchain.chains.retrieval import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o-mini")

prompt = ChatPromptTemplate.from_messages([
    ("system", "Use the given context to answer the question.\n\nContext:\n{context}"),
    ("human", "{input}"),
])

question_answer_chain = create_stuff_documents_chain(llm, prompt)
rag_chain = create_retrieval_chain(retriever, question_answer_chain)

result = rag_chain.invoke({"input": "What does the refund policy say?"})
print(result["answer"])
print(result["context"])
```

The important idea is that `retriever` finds the docs, and `create_stuff_documents_chain()` tells the LLM how to read them. `create_retrieval_chain()` connects the two. ([aidoczh.com][2])

## Step-by-step with a tiny example

Imagine you have three chunks in a vector store:

* Chunk A: “Refunds are allowed within 30 days.”
* Chunk B: “Shipping takes 5–7 business days.”
* Chunk C: “Warranty lasts 1 year.”

User asks: “How long do I have for a refund?”

### What happens

1. The retriever embeds the question and searches the store.
2. It returns Chunk A as the top match.
3. `create_retrieval_chain()` passes Chunk A into the prompt as `context`.
4. The LLM answers: “You have 30 days for a refund.” ([LangChain Reference][1])

The LLM did not need to scan all 3 chunks manually. Retrieval narrowed the information first.

## Example 1: Simple FAQ bot

Use this when the content is small enough that one prompt with a few retrieved chunks is enough.

```python
from langchain.chains.retrieval import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate

prompt = ChatPromptTemplate.from_messages([
    ("system", "Answer only from the context.\nContext:\n{context}"),
    ("human", "{input}"),
])

doc_chain = create_stuff_documents_chain(llm, prompt)
rag_chain = create_retrieval_chain(retriever, doc_chain)

answer = rag_chain.invoke({"input": "What are your office hours?"})
```

This is perfect for policy bots, internal handbook bots, product FAQ bots, and support bots where a short answer is enough. That pattern matches the official retrieval-chain design: retrieve docs, then pass them on to the answer chain. ([LangChain Reference][1])

## Example 2: Customer support assistant

For a production support app, your retriever might search:

* help-center articles
* product manuals
* shipping rules
* billing policy pages

Your prompt can enforce behavior:

```python
prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a support assistant. Use only the context. "
        "If the answer is not in the context, say you don't know.\n\nContext:\n{context}",
    ),
    ("human", "{input}"),
])
```

This is one of the main production uses of retrieval chains: keep the model grounded in your approved knowledge base instead of letting it improvise from its general training. The chain’s structure supports that by always injecting retrieved context before generation. ([LangChain Reference][1])

## Example 3: Internal company knowledge bot

Say your company has:

* HR handbook
* engineering runbooks
* security policy
* onboarding docs

A user asks: “What is the laptop reimbursement policy?”

The retriever finds the policy chunk, and the answer chain responds using only that chunk. That lets you build a single Q&A interface over many documents without sending the whole corpus into the prompt every time. ([LangChain Reference][1])

## Example 4: Multi-turn chat with history

`create_retrieval_chain()` itself does not magically “understand” prior conversation. It can, however, carry `chat_history` through the pipeline so a history-aware retriever or prompt can use it. LangChain’s reference says the chain adds `chat_history` as `[]` if it is missing, which makes conversational retrieval easier to wire up. ([aidoczh.com][2])

A common production pattern is:

```python
from langchain.chains.history_aware_retriever import create_history_aware_retriever
from langchain.chains.retrieval import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
```

Flow:

1. Rewrite the follow-up question using chat history.
2. Retrieve docs using the rewritten query.
3. Answer from retrieved context. ([aidoczh.com][2])

Example conversation:

* User: “Tell me about the refund policy.”
* User: “What about if the item was damaged?”

The second question is vague. A history-aware retriever turns it into something like: “What is the refund policy for damaged items?” Then `create_retrieval_chain()` uses those docs to answer. The retrieval chain is the delivery layer; the history-aware retriever is the query-rewriting layer. ([aidoczh.com][2])

## Why people use it in production

In real systems, it gives you a clean separation of concerns:

* retriever decides **what** knowledge is relevant
* prompt decides **how** to use the knowledge
* LLM decides **what to say**
* the chain glues them together ([LangChain Reference][1])

That makes it easier to swap components:

* change vector DB
* change embedding model
* change prompt style
* change LLM
* add reranking
* add filters or metadata constraints

The retrieval chain itself stays the same.

## Production architecture examples

### 1) Support portal

* Documents: Zendesk articles, PDFs, release notes
* Retriever: vector + metadata filters by product/version
* Combine chain: strict answer-from-context prompt
* Result: grounded support responses, fewer hallucinations

### 2) Legal or compliance search

* Documents: policies, contracts, clauses
* Retriever: top-k with metadata filter for jurisdiction
* Combine chain: answer with citations or clause references
* Result: faster policy lookup

### 3) Enterprise knowledge search

* Documents: Confluence pages, Notion exports, Google Drive docs
* Retriever: hybrid search or vector search
* Combine chain: concise executive answer or detailed technical answer
* Result: one interface over many sources

### 4) E-commerce assistant

* Documents: product manuals, shipping FAQ, returns policy, catalog descriptions
* Retriever: product-specific metadata + semantic search
* Combine chain: explain product details, compare options, answer support questions
* Result: useful pre-sales and post-sales assistant

All of these follow the same core retrieval-chain design: retrieve relevant docs, then pass them to the answer chain. ([LangChain Reference][1])

## Common mistakes

### 1) Using the wrong input key

If you use a normal `BaseRetriever`, send the query as `{"input": "..."}`. The reference explicitly says the retriever expects `input` in that case. ([aidoczh.com][2])

### 2) Forgetting `{context}` in the prompt

If the prompt does not include a placeholder for retrieved docs, the LLM never sees them.

### 3) Forgetting `chat_history` for conversational flows

The chain may default it to `[]`, but your prompt or retriever still has to be designed for history if you want follow-up questions to work well. ([aidoczh.com][2])

### 4) Thinking the retriever “understands” the question like a human

A retriever usually performs similarity search or some other retrieval strategy. It does not reason. The LLM does the reasoning after retrieval.

### 5) Using too many chunks

If you stuff too many documents into the prompt, the answer can get noisy and token-heavy. In production, teams often add reranking, smaller chunk sizes, metadata filters, or max token controls upstream.

## Import path gotcha

This is the part that trips people up most often. LangChain’s docs and issue tracker show inconsistent import paths across versions and package splits. One common working pattern reported in current issues is:

```python
from langchain.chains.retrieval import create_retrieval_chain
```

Some pages still show `from langchain.chains import create_retrieval_chain`, and some LangChain Classic reference material points to `langchain_classic.chains.retrieval`. The issue tracker specifically notes that the docs have disagreed about this path. ([GitHub][4])

So the safe rule is: match the import path to the package/version you actually installed, and prefer the path that your version’s reference page shows. ([GitHub][5])

## Very simple one-sentence summary

`create_retrieval_chain()` is the LangChain “glue” that takes a retriever and an answer-generation chain, retrieves relevant documents, puts them into `context`, and returns an answer plus the retrieved docs. ([LangChain Reference][1])

I can also give you a full end-to-end production RAG example with FAISS/Chroma, prompts, and `create_retrieval_chain()` wired together step by step.

[1]: https://reference.langchain.com/python/langchain-classic/chains/retrieval/create_retrieval_chain?utm_source=chatgpt.com "create_retrieval_chain | langchain_classic"
[2]: https://aidoczh.com/langchain/api_reference/_modules/langchain/chains/retrieval.html?utm_source=chatgpt.com "langchain.chains.retrieval 的源代码"
[3]: https://reference.langchain.com/python/langchain-classic/chains/retrieval_qa/base/RetrievalQA?utm_source=chatgpt.com "RetrievalQA | langchain_classic"
[4]: https://github.com/langchain-ai/langchain/issues/29560?utm_source=chatgpt.com "DOC: Incorrect Import Path for `create_retrieval_chain` in ..."
[5]: https://github.com/langchain-ai/langchain/issues/31593?utm_source=chatgpt.com "DOC: Inconsistent import path for create_retrieval_chain ..."
