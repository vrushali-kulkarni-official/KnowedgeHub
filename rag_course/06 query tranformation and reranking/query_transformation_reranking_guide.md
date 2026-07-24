# Query Transformation, Re-Ranking & Self-Query — Production RAG Guide

This continues your pipeline:
`TextLoader/Docling → Chunking (structural/token-guard/semantic/recursive) → MiniLM Embeddings → FAISS → Retrieval Strategies (similarity/MMR/metadata/hybrid)`

The next stage sits **between the user's question and the LLM call**, and **between retrieval and the LLM call**:

```
question
   │
   ▼
[QUERY TRANSFORMATION]   ← rewrite/expand/decompose the query BEFORE hitting the vector store
   │
   ▼
[RETRIEVAL]              ← your existing similarity/MMR/hybrid retriever (often run per-transformed-query)
   │
   ▼
[RE-RANKING]             ← re-score the retrieved docs with a more expensive, more accurate model
   │
   ▼
[CONTEXT] → prompt → llm → StrOutputParser()
```

Query transformation fixes a **recall** problem (the right chunk never gets retrieved because the query is phrased badly).
Re-ranking fixes a **precision** problem (the right chunk *was* retrieved, but buried at position #7 instead of #1).

---

## PART 1 — CONCEPTS

### 1.1 Query Transformation

**Problem it solves:** embedding similarity is a blunt instrument. A user's question ("how do I fix the thing that keeps crashing") and the document that answers it ("Resolving Application Termination Errors in v2.3") can be semantically related to a human but far apart in embedding space because of vocabulary mismatch, ambiguity, or because the question requires *reasoning* the retriever can't do.

**Core idea:** instead of embedding the raw user query, transform it (once, or into multiple variants) into a form that embeds closer to the target chunks.

### 1.2 Re-Ranking

**Problem it solves:** your retriever (bi-encoder, e.g. MiniLM) embeds the query and each document **independently**, then compares vectors with cosine similarity / dot product. This is fast (you can index millions of docs) but lossy — the model never actually looks at the query and document *together*.

**Core idea:** retrieve a larger candidate set cheaply (e.g. top-20 via FAISS), then re-score that small set with a model that *does* look at query+document jointly (a cross-encoder), and keep only the top-k (e.g. top-3) for the LLM context.

This is the same "retrieve-then-rerank" pattern used by every major search engine and is one of the highest ROI additions you can make to a RAG pipeline — usually more impactful than swapping embedding models.

### 1.3 Self-Query

**Problem it solves:** some questions aren't *purely* semantic. "Show me blog posts about RAG published after 2024 by Jane" mixes a semantic part ("RAG") with structured filter conditions (`date > 2024`, `author == "Jane"`). A plain similarity search can't apply those filters — it doesn't know your metadata schema.

**Core idea:** use an LLM to translate the natural-language question into **(semantic search string, structured metadata filter)**, then apply both — semantic search on the vector store + a hard filter on metadata fields (like a `WHERE` clause). It's a retrieval *strategy*, not a transformation of the query text alone — it transforms the query into a *structured retrieval plan*.

---

## PART 2 — QUERY TRANSFORMATION TECHNIQUES

### 2.1 Query Rewriting (the simplest case)

Just ask an LLM to rewrite the raw, often messy user question into a clean, retrieval-optimized query — expand abbreviations, fix grammar, resolve pronouns using chat history, remove conversational filler.

**When it helps:** conversational RAG (multi-turn chat) where the latest message alone is ambiguous ("what about for the second one?"), and when users type casually/with typos.

```python
"""
query_rewriting.py
-------------------
Query Rewriting: condense conversation history + a follow-up question
into a single, standalone, retrieval-optimized query.

This is the #1 fix for conversational RAG bugs where retrieval works
fine on turn 1 but falls apart on turn 2+ ("what about that one?").
"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_groq import ChatGroq  # swap for whatever LLM wrapper you use

# A small, cheap, fast LLM is enough for rewriting -- you don't need your
# biggest model here, this is a mechanical transformation, not reasoning.
rewriter_llm = ChatGroq(model="llama-3.1-8b-instant", temperature=0)

REWRITE_PROMPT = ChatPromptTemplate.from_template(
    """Given a chat history and the latest user question, which might
reference context in the chat history, formulate a standalone question
which can be understood WITHOUT the chat history.

Do NOT answer the question. Just reformulate it if needed, otherwise
return it as-is. Output ONLY the reformulated question, nothing else.

Chat History:
{chat_history}

Latest Question:
{question}

Standalone Question:"""
)

# LCEL chain: prompt -> llm -> parse to plain string
query_rewrite_chain = REWRITE_PROMPT | rewriter_llm | StrOutputParser()


def rewrite_query(question: str, chat_history: list[tuple[str, str]]) -> str:
    """
    chat_history: list of (user_msg, ai_msg) tuples from earlier turns.
    Returns a standalone, retriever-friendly query string.
    """
    # Flatten history into plain text the prompt can read.
    history_text = "\n".join(f"User: {u}\nAssistant: {a}" for u, a in chat_history)
    return query_rewrite_chain.invoke({
        "chat_history": history_text,
        "question": question,
    })


# --- Example wiring into YOUR existing RAG chain -----------------------
# Original:
#   rag_chain = (
#       RunnablePassthrough.assign(context=(lambda x: x["question"]) | retriever | format_docs)
#       | prompt | llm | StrOutputParser()
#   )
#
# With rewriting inserted BEFORE retrieval:

from langchain_core.runnables import RunnablePassthrough, RunnableLambda


def format_docs(docs):
    return "\n\n".join(d.page_content for d in docs)


rag_chain_with_rewrite = (
    # Step 1: overwrite "question" with its rewritten, standalone version.
    RunnablePassthrough.assign(
        question=lambda x: rewrite_query(x["question"], x.get("chat_history", []))
    )
    # Step 2: same as your original retrieval+context assembly, but now
    # operating on the *rewritten* question.
    | RunnablePassthrough.assign(
        context=(lambda x: x["question"]) | retriever | format_docs
    )
    | prompt
    | llm
    | StrOutputParser()
)
```

---

### 2.2 Multi-Query Retrieval

Instead of betting everything on one phrasing of the query, ask the LLM to generate **N diverse rephrasings**, retrieve for *each*, then take the union (deduplicated) of all retrieved chunks. This widens recall — different phrasings hit different corners of embedding space, increasing the chance that *at least one* surfaces the right chunk.

**When it helps:** broad/ambiguous questions, queries with synonyms the corpus doesn't share, low-recall situations where you suspect the retriever is missing relevant chunks entirely.

**Trade-off:** N retrieval calls instead of 1 → higher latency/cost; needs a dedup step since the same chunk often comes back from multiple sub-queries.

```python
"""
multi_query.py
---------------
Multi-Query Retrieval: generate several reformulations of the user's
question, retrieve for each, and merge+deduplicate the results.

LangChain ships a ready-made MultiQueryRetriever that wraps ANY base
retriever (your FAISS similarity/MMR retriever works as-is).
"""

import logging
from langchain.retrievers.multi_query import MultiQueryRetriever
from langchain_groq import ChatGroq

# Turn on logging to actually SEE the generated queries -- invaluable
# for debugging why retrieval did/didn't pick up a document.
logging.basicConfig()
logging.getLogger("langchain.retrievers.multi_query").setLevel(logging.INFO)

llm_for_queries = ChatGroq(model="llama-3.1-8b-instant", temperature=0.3)
# temperature>0 here is intentional: we WANT diverse phrasings, not one
# deterministic best guess.

# `retriever` below = the FAISS retriever you already built, e.g.:
#   retriever = vectorstore.as_retriever(search_type="mmr", search_kwargs={"k": 4})
multi_query_retriever = MultiQueryRetriever.from_llm(
    retriever=retriever,  # your existing base retriever (similarity/MMR/hybrid)
    llm=llm_for_queries,  # LLM used purely to GENERATE query variants
    # include_original=True keeps the user's literal question as one of
    # the queries fired at the retriever, in addition to the generated ones.
    include_original=True,
)

# Internally, calling .invoke(question) does roughly:
#   1. LLM generates ~3 alternative phrasings of `question`
#   2. base retriever.invoke() runs for EACH phrasing (+ original if set)
#   3. all returned docs are merged, deduplicated by content
#   4. the deduplicated list is returned
unique_docs = multi_query_retriever.invoke("What are the side effects of long covid?")
# Example generated variants you'd see in the logs:
#   - "What symptoms are associated with long COVID?"
#   - "What are the long-term health effects after a COVID-19 infection?"
#   - "List complications reported in long covid patients."

# Drop straight into your existing LCEL chain -- it's just a retriever:
rag_chain_multi_query = (
    RunnablePassthrough.assign(
        context=(lambda x: x["question"]) | multi_query_retriever | format_docs
    )
    | prompt
    | llm
    | StrOutputParser()
)
```

If you want full control over the generated variants (custom prompt, custom parsing) instead of the built-in class:

```python
"""
multi_query_manual.py
----------------------
Hand-rolled multi-query for when you want to control the prompt,
the number of variants, or do custom dedup/scoring logic.
"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda

MULTI_QUERY_PROMPT = ChatPromptTemplate.from_template(
    """You are an AI assistant that generates multiple search queries
based on a single input query. Generate {n} different search queries
related to: {question}

Output ONLY the queries, one per line, no numbering, no extra text."""
)


def parse_queries(text: str) -> list[str]:
    # Split LLM output into a clean list of query strings.
    return [line.strip() for line in text.split("\n") if line.strip()]


generate_queries_chain = (
    MULTI_QUERY_PROMPT
    | llm_for_queries
    | StrOutputParser()
    | RunnableLambda(parse_queries)
)


def reciprocal_rank_fusion(results: list[list], k: int = 60) -> list:
    """
    Merge several ranked lists of documents into one ranked list using
    Reciprocal Rank Fusion (RRF) -- the standard way to combine results
    from multiple retrieval passes (also used to fuse dense + sparse
    results in hybrid search, which you've already implemented).

    score(doc) = sum over all lists containing doc of  1 / (k + rank_in_that_list)

    k=60 is the conventional damping constant from the original RRF paper;
    it down-weights the importance of exact rank position so a doc that's
    #1 in one list and #1 in another doesn't completely dominate.
    """
    fused_scores: dict[str, float] = {}
    doc_lookup: dict[str, object] = {}

    for docs in results:
        for rank, doc in enumerate(docs):
            key = doc.page_content  # use content as a dedup key
            doc_lookup[key] = doc
            fused_scores.setdefault(key, 0.0)
            fused_scores[key] += 1.0 / (rank + k)

    # Sort by fused score, descending.
    reranked_keys = sorted(fused_scores, key=lambda k_: fused_scores[k_], reverse=True)
    return [doc_lookup[key] for key in reranked_keys]


def multi_query_retrieve(question: str, n: int = 4) -> list:
    queries = generate_queries_chain.invoke({"question": question, "n": n})
    all_results = [retriever.invoke(q) for q in queries]
    return reciprocal_rank_fusion(all_results)
```

---

### 2.3 HyDE (Hypothetical Document Embeddings)

**The trick:** instead of embedding the *question*, ask the LLM to write a **hypothetical answer/document** as if it already knew the answer, and embed *that*. Why does this work? Questions and answers live in different regions of embedding space ("What causes inflation?" looks nothing like "Inflation is caused by..." in vector space) — but a *hypothetical answer* looks a lot like the *real* answer chunk sitting in your vector store, even if the hypothetical answer is factually wrong or made up. You're matching answer-style text to answer-style text instead of question-style text to answer-style text.

**When it helps:** technical/specialized domains, short or vague queries, cases where your corpus is written in a declarative/encyclopedic style rather than Q&A style (manuals, papers, docs — exactly what Docling is good at ingesting).

**When it hurts:** very short factual lookups where the question phrasing already closely matches the source (HyDE adds an LLM call for no benefit), or domains where hallucinated hypothetical answers could be wildly off-topic and actively mislead retrieval.

```python
"""
hyde.py
-------
HyDE: generate a hypothetical answer to the question, embed THAT,
and use it to search the vector store -- instead of embedding the
raw question.

Key insight: we never show the hypothetical answer to the user, and we
don't even need it to be factually correct. We only need it to be
STYLISTICALLY similar to a real answer, so its embedding lands near the
real answer chunks in vector space.
"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_community.vectorstores import FAISS

HYDE_PROMPT = ChatPromptTemplate.from_template(
    """Write a short, confident, factual-sounding passage that would
answer the following question. Write it as if it were an excerpt from
a textbook or documentation -- do not mention that this is hypothetical,
do not hedge, do not say "I don't know."

Question: {question}

Passage:"""
)

# Cheap/fast LLM is fine -- we're generating throwaway text, not the
# final user-facing answer.
hyde_chain = HYDE_PROMPT | llm_for_queries | StrOutputParser()


def hyde_retrieve(question: str, vectorstore: FAISS, k: int = 4):
    # 1. Generate the hypothetical document.
    hypothetical_doc = hyde_chain.invoke({"question": question})

    # 2. Embed the HYPOTHETICAL DOCUMENT (not the question!) and search.
    #    similarity_search() internally embeds the string you pass it
    #    using the same MiniLM embedding model your FAISS index was built
    #    with, then does the nearest-neighbor lookup.
    results = vectorstore.similarity_search(hypothetical_doc, k=k)
    return results


# --- Wiring into LCEL ---------------------------------------------------
# We build a "retriever-shaped" Runnable so it slots into your existing
# RunnablePassthrough.assign(context=...) pattern unchanged.
from langchain_core.runnables import RunnableLambda

hyde_retriever = RunnableLambda(
    lambda question: hyde_retrieve(question, vectorstore, k=4)
)

rag_chain_hyde = (
    RunnablePassthrough.assign(
        context=(lambda x: x["question"]) | hyde_retriever | format_docs
    )
    | prompt
    | llm
    | StrOutputParser()
)

# NOTE: LangChain also has a prebuilt HypotheticalDocumentEmbedder that
# wraps an embeddings model + LLM + prompt into a single Embeddings
# object you can pass straight into FAISS.from_documents(...) -- useful
# if you want HyDE baked into index-build time prompting too:
#
#   from langchain.chains import HypotheticalDocumentEmbedder
#   hyde_embeddings = HypotheticalDocumentEmbedder.from_llm(
#       llm_for_queries, base_embeddings, prompt_key="web_search"
#   )
```

---

### 2.4 Step-Back Prompting

**The trick:** for questions that require specific reasoning, first ask the LLM to generate a more **abstract / general** "step-back" question, retrieve context for that general question, *and* retrieve context for the original specific question, then combine both contexts. The general question often surfaces broader background/definitional chunks that the specific question alone would never retrieve, but which the LLM needs to reason correctly.

**Example:** "What was the GDP of the country where the 2008 Olympics were held, in 2007?" → step-back: "What were major economic indicators of countries hosting the Olympics?" / "Where was the 2008 Olympics held?" — the step-back surfaces the China/Beijing fact that the specific question's embedding alone might not retrieve well.

**When it helps:** multi-hop questions, questions requiring background knowledge to even interpret correctly, domains with a clear specific→general conceptual hierarchy (legal, medical, scientific).

```python
"""
step_back.py
-------------
Step-Back Prompting: derive a more general/abstract version of the
question, retrieve for BOTH the general and the specific question, and
union the contexts. The general question often retrieves the
"background knowledge" chunks the specific question's wording misses.
"""

from langchain_core.prompts import ChatPromptTemplate, FewShotChatMessagePromptTemplate
from langchain_core.output_parsers import StrOutputParser

# Few-shot examples teach the LLM the PATTERN of stepping back, which
# works far more reliably than a zero-shot instruction alone.
examples = [
    {
        "input": "Could the members of The Police perform lawful arrests?",
        "output": "What can the members of The Police do?",
    },
    {
        "input": "Jan Sindel's was born in what country?",
        "output": "What is Jan Sindel's personal history?",
    },
]

example_prompt = ChatPromptTemplate.from_messages([
    ("human", "{input}"),
    ("ai", "{output}"),
])

few_shot_prompt = FewShotChatMessagePromptTemplate(
    example_prompt=example_prompt,
    examples=examples,
)

STEP_BACK_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are an expert at world knowledge. Your task is to "
        "step back and paraphrase a question to a more generic "
        "step-back question, which is easier to answer. Here are "
        "a few examples:",
    ),
    few_shot_prompt,
    ("human", "{question}"),
])

step_back_chain = STEP_BACK_PROMPT | llm_for_queries | StrOutputParser()


def step_back_retrieve(question: str) -> str:
    step_back_question = step_back_chain.invoke({"question": question})

    # Retrieve for BOTH the original specific question and the
    # generated general one, then merge the chunk sets.
    specific_docs = retriever.invoke(question)
    general_docs = retriever.invoke(step_back_question)

    # Simple union with dedup by content; for production, swap this for
    # the reciprocal_rank_fusion() helper defined in multi_query_manual.py
    seen, merged = set(), []
    for doc in specific_docs + general_docs:
        if doc.page_content not in seen:
            seen.add(doc.page_content)
            merged.append(doc)
    return format_docs(merged)


rag_chain_step_back = (
    RunnablePassthrough.assign(context=lambda x: step_back_retrieve(x["question"]))
    | prompt
    | llm
    | StrOutputParser()
)
```

---

### 2.5 Query Decomposition (Sub-Question Splitting)

**The trick:** for compound/multi-part questions ("Compare the pricing and the rate-limit policy of API A and API B"), ask the LLM to break it into atomic sub-questions, retrieve separately for each, answer each (optionally), and synthesize a final answer. This is "multi-query" taken further — the variants aren't *paraphrases* of the same question, they're genuinely *different* sub-questions.

**When it helps:** comparison questions, "and"/"also" compound questions, questions implying multiple lookups (multi-hop).

```python
"""
decomposition.py
-----------------
Query Decomposition: split a compound question into independent
sub-questions, retrieve+answer each separately, then synthesize.

Different from multi-query: multi-query generates PARAPHRASES of the
SAME question to widen recall. Decomposition generates DIFFERENT
sub-questions because the original question actually requires multiple
independent lookups.
"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda

DECOMPOSE_PROMPT = ChatPromptTemplate.from_template(
    """Break the following question down into a series of independent
sub-questions that, together, are needed to fully answer it. If the
question is already atomic and doesn't need decomposition, return it
as the single sub-question.

Output ONLY the sub-questions, one per line, no numbering.

Question: {question}
Sub-questions:"""
)

decompose_chain = (
    DECOMPOSE_PROMPT
    | llm_for_queries
    | StrOutputParser()
    | RunnableLambda(lambda text: [q.strip() for q in text.split("\n") if q.strip()])
)

ANSWER_SUBQ_PROMPT = ChatPromptTemplate.from_template(
    """Answer the question based only on this context:
{context}

Question: {sub_question}
Answer:"""
)
answer_subq_chain = ANSWER_SUBQ_PROMPT | llm | StrOutputParser()

SYNTHESIZE_PROMPT = ChatPromptTemplate.from_template(
    """Using the question-answer pairs below, write one coherent final
answer to the ORIGINAL question.

Original question: {question}

Q&A pairs:
{qa_pairs}

Final answer:"""
)
synthesize_chain = SYNTHESIZE_PROMPT | llm | StrOutputParser()


def decomposed_rag(question: str) -> str:
    sub_questions = decompose_chain.invoke({"question": question})

    qa_pairs = []
    for sub_q in sub_questions:
        docs = retriever.invoke(sub_q)  # retrieve per sub-question
        context = format_docs(docs)
        sub_answer = answer_subq_chain.invoke({
            "context": context,
            "sub_question": sub_q,
        })
        qa_pairs.append(f"Q: {sub_q}\nA: {sub_answer}")

    return synthesize_chain.invoke({
        "question": question,
        "qa_pairs": "\n\n".join(qa_pairs),
    })


# Usage: decomposed_rag("Compare the refund policy and shipping times of Vendor A vs Vendor B")
```

---

### 2.6 Quick comparison table

| Technique | What it changes | Extra LLM calls | Best for | Risk |
|---|---|---|---|---|
| Rewriting | Phrasing/clarity, resolves coref | 1 | Multi-turn chat | Loses nuance if over-aggressive |
| Multi-Query | Generates N paraphrases, unions results | 1 (generates N at once) | Vocabulary mismatch, low recall | Latency, needs dedup |
| HyDE | Embeds a generated answer, not the question | 1 | Vague/short queries, declarative corpora | Hallucinated doc derails retrieval if domain is too niche |
| Step-Back | Adds a general question alongside the specific one | 1 | Multi-hop, requires background knowledge | Doubles retrieval calls |
| Decomposition | Splits into independent sub-questions, answers each | N+1 | Compound/comparison questions | Highest latency/cost of the group |

---

## PART 3 — RE-RANKING

### 3.1 Why bi-encoders (your MiniLM retriever) aren't enough

```
Bi-encoder (what FAISS/MiniLM does):

  query ──► [Encoder] ──► vector_q
                                       ──► cosine_similarity(vector_q, vector_d)
  doc   ──► [Encoder] ──► vector_d

  Query and doc NEVER see each other. Each is squashed into a fixed-size
  vector independently, ahead of time (docs are embedded once at index
  time). Fast: compare against millions of precomputed doc vectors in ms.
  Lossy: a single 384-dim vector can't capture every nuance of a chunk.


Cross-encoder (what a re-ranker does):

  [query + doc] ──► [Transformer processes BOTH together] ──► relevance_score

  The model attends across query AND document tokens jointly, so it can
  catch fine-grained relevance signals a bi-encoder misses (negation,
  exact term overlap, entity matching, logical relationships).
  Accurate: much better at fine relevance distinctions.
  Slow: can't precompute -- must run inference per (query, doc) PAIR at
  query time. Doing this for your whole corpus would be far too slow,
  which is why it's only run on the SMALL candidate set the bi-encoder
  already narrowed down.
```

This is exactly why production retrieval is almost always **two-stage**:

```
Stage 1 (Retrieval, bi-encoder/FAISS): corpus of millions → top 20-50 candidates  [fast, recall-oriented]
Stage 2 (Re-ranking, cross-encoder):   20-50 candidates   → top 3-5 for the LLM   [slow but precise, precision-oriented]
```

### 3.2 When re-ranking actually helps (and when it's a waste)

**Helps a lot when:**
- Your corpus is large/diverse and similarity search returns a noisy top-k (lots of "kinda related" chunks).
- Queries are short/ambiguous, where bi-encoder similarity is unreliable.
- You're retrieving a generous `k` (e.g. 15-20) specifically to feed a reranker, rather than a tight `k=3` (a wide net + reranker beats a tight net every time, *if* you rerank).
- Hybrid search (dense+sparse) is already in play — reranking is the standard final fusion step, often outperforming RRF alone.

**Doesn't help / can hurt when:**
- Your retriever's top-k is already small and clearly relevant (tiny, narrow corpus) — reranking adds latency for no quality gain.
- You retrieve too few candidates upfront (e.g. only k=3) — the reranker has nothing better to promote; garbage in, garbage out. Always over-retrieve, then rerank down.
- Strict latency budgets (e.g. sub-200ms) where an extra cross-encoder pass is too costly — consider a lighter/distilled reranker or skip it.

### 3.3 Cross-Encoder Re-Ranking (open-source, e.g. `ms-marco` / `BGE-reranker`)

```python
"""
cross_encoder_rerank.py
------------------------
Two-stage retrieval: FAISS does broad recall (k=20), a local
cross-encoder model re-scores and keeps only the top 3-5 for the LLM.

Uses LangChain's ContextualCompressionRetriever, which wraps your base
retriever and applies a "compressor" (the reranker) to its output --
this is the standard LangChain integration pattern for ANY reranker.
"""

from langchain.retrievers import ContextualCompressionRetriever
from langchain.retrievers.document_compressors import CrossEncoderReranker
from langchain_community.cross_encoders import HuggingFaceCrossEncoder

# Popular open-source cross-encoder rerankers (pick one):
#   "cross-encoder/ms-marco-MiniLM-L-6-v2"   -- fast, general web-search tuned
#   "BAAI/bge-reranker-base"                 -- strong general-purpose, multilingual variants exist
#   "BAAI/bge-reranker-large"                -- higher accuracy, higher latency
# These run LOCALLY via sentence-transformers, same family as your
# existing HuggingFaceEmbeddings MiniLM setup -- no new infra needed.
cross_encoder_model = HuggingFaceCrossEncoder(model_name="BAAI/bge-reranker-base")

# top_n = how many documents survive AFTER reranking (what actually
# reaches the LLM as context). This is your PRECISION knob.
reranker = CrossEncoderReranker(model=cross_encoder_model, top_n=3)

# base_retriever should over-retrieve generously -- this is your RECALL
# knob. k=20 here gives the reranker a wide pool to choose the true top 3
# from, instead of betting everything on FAISS's raw top-3.
base_retriever = vectorstore.as_retriever(search_kwargs={"k": 20})

# ContextualCompressionRetriever's contract: call base_retriever, then
# pass its output through `base_compressor` (the reranker) before
# returning -- it's a drop-in replacement for any retriever in your LCEL
# chain, no other code changes needed.
compression_retriever = ContextualCompressionRetriever(
    base_compressor=reranker,
    base_retriever=base_retriever,
)

# --- Slots straight into your existing RAG chain pattern ---------------
rag_chain_reranked = (
    RunnablePassthrough.assign(
        context=(lambda x: x["question"]) | compression_retriever | format_docs
    )
    | prompt
    | llm
    | StrOutputParser()
)

# Sanity check: inspect what the reranker actually kept, and its score,
# before wiring it into the full chain -- always verify reranking output
# manually at least once on a real query from your domain.
docs = compression_retriever.invoke("What causes vector index drift in FAISS?")
for d in docs:
    print(d.metadata.get("relevance_score"), "::", d.page_content[:80])
```

### 3.4 Cohere Rerank (managed API alternative)

If you'd rather not run a cross-encoder locally (heavier than MiniLM, real latency on CPU), a hosted reranking API is the common production shortcut:

```python
"""
cohere_rerank.py
-----------------
Same ContextualCompressionRetriever pattern, swapping the local
cross-encoder for Cohere's managed Rerank API. Useful when you don't
want to host a cross-encoder model yourself, or need higher throughput
than a local CPU/GPU can give you.
"""

from langchain.retrievers import ContextualCompressionRetriever
from langchain_cohere import CohereRerank

compressor = CohereRerank(
    model="rerank-english-v3.0",  # or rerank-multilingual-v3.0
    top_n=3,
)

base_retriever = vectorstore.as_retriever(search_kwargs={"k": 20})

compression_retriever = ContextualCompressionRetriever(
    base_compressor=compressor,
    base_retriever=base_retriever,
)

# Identical usage to the local cross-encoder version -- this is the
# point of the ContextualCompressionRetriever abstraction: swapping
# rerank PROVIDERS never touches your chain wiring.
rag_chain_cohere_rerank = (
    RunnablePassthrough.assign(
        context=(lambda x: x["question"]) | compression_retriever | format_docs
    )
    | prompt
    | llm
    | StrOutputParser()
)
```

### 3.5 Manual reranking (no LangChain abstraction — useful to understand the internals)

```python
"""
manual_rerank.py
------------------
What CrossEncoderReranker does under the hood, spelled out explicitly.
Worth reading once even if you use the prebuilt class day-to-day --
this is the actual mechanism, and you'll want this level of control
when you build hybrid scoring (e.g. blend rerank score with recency,
popularity, or a metadata-based boost).
"""

from sentence_transformers import CrossEncoder

# CrossEncoder model expects a LIST of (query, doc_text) PAIRS and
# returns a relevance score per pair -- this is the key structural
# difference from your bi-encoder embeddings.encode(text), which takes
# ONE text at a time and has no notion of "pairs."
model = CrossEncoder("BAAI/bge-reranker-base", max_length=512)


def rerank(query: str, docs: list, top_n: int = 3) -> list:
    # Step 1: build (query, doc_content) pairs for every retrieved doc.
    pairs = [(query, doc.page_content) for doc in docs]

    # Step 2: cross-encoder scores each pair JOINTLY -- this is the
    # expensive step, O(num_candidates) model forward-passes.
    scores = model.predict(pairs)  # returns a numpy array of floats

    # Step 3: attach scores back onto the docs so we can inspect/debug,
    # then sort descending by score and keep only the top_n.
    scored_docs = list(zip(docs, scores))
    scored_docs.sort(key=lambda pair: pair[1], reverse=True)

    reranked = []
    for doc, score in scored_docs[:top_n]:
        doc.metadata["rerank_score"] = float(score)  # keep for debugging/logging
        reranked.append(doc)
    return reranked


def retrieve_and_rerank(question: str, k_retrieve: int = 20, k_final: int = 3):
    candidates = retriever.invoke(question)  # wide net, your FAISS retriever
    return rerank(question, candidates, top_n=k_final)  # narrow down with cross-encoder
```

### 3.6 Re-ranking integration patterns (summary)

| Pattern | How it works | When to use |
|---|---|---|
| **Retrieve-then-rerank** (above) | Over-retrieve (k≈20) → cross-encoder rerank → top-k to LLM | Default production pattern, almost always worth adding |
| **Cascade / multi-stage** | Cheap bi-encoder (k=100) → mid-cost reranker (k=20) → expensive reranker (k=3) | Very large corpora, latency budget allows staged filtering |
| **Reranking after fusion** | Hybrid search (dense+sparse via RRF) → rerank the fused list | You already have hybrid search — rerank the RRF output instead of either list alone |
| **Reranking after multi-query** | Multi-query retrieval → dedup → rerank the unioned candidate pool | Combine recall-boosting (multi-query) with precision-boosting (rerank) — very strong combo |

---

## PART 4 — SELF-QUERY RETRIEVAL

### 4.1 The idea

Self-query asks an LLM to translate a natural-language question into a **structured query**: a semantic search string + a metadata filter, by reading your **declared metadata schema**. This requires your vector store's documents to actually carry useful metadata (e.g. `source`, `author`, `published_date`, `category`, `page`) — exactly the kind of metadata you'd attach during your Docling-based loading/chunking stage.

```
"RAG papers from after 2023 by Lewis"
            │
            ▼  (LLM reads the metadata field descriptions you provide)
   ┌────────────────────────────────────────────┐
   │ query: "RAG"                                │   ← goes through normal
   │ filter: AND(                                │      semantic similarity
   │   author == "Lewis",                        │   ← goes through metadata
   │   published_date > 2023-01-01               │      filtering on the
   │ )                                            │      vector store
   └────────────────────────────────────────────┘
```

### 4.2 Code

```python
"""
self_query.py
---------------
SelfQueryRetriever: LLM converts a natural-language question into a
(semantic query + structured metadata filter) pair, then runs that
filtered semantic search against the vector store.

CRITICAL prerequisite: your documents must actually have populated
`metadata` dicts (e.g. {"source": "...", "category": "...", "year": 2023}).
If your current FAISS index was built from plain TextLoader output with
empty metadata, you'll need to attach metadata at load/chunk time first
-- this is a great use of the structural info Docling gives you when
parsing PDFs/HTML/Markdown (headings, page numbers, section titles).
"""

from langchain.chains.query_constructor.schema import AttributeInfo
from langchain.retrievers.self_query.base import SelfQueryRetriever
from langchain_groq import ChatGroq

# Step 1: describe your metadata schema to the LLM in plain English.
# This is the MOST important part to get right -- the LLM can only
# build correct filters for fields it knows exist and understands.
metadata_field_info = [
    AttributeInfo(
        name="category",
        description="The topic category of the document. One of "
        "['rag', 'embeddings', 'chunking', 'vector-db', 'llm-eval']",
        type="string",
    ),
    AttributeInfo(
        name="source",
        description="The original filename the chunk was extracted from",
        type="string",
    ),
    AttributeInfo(
        name="published_year",
        description="The year the source document was published",
        type="integer",
    ),
    AttributeInfo(
        name="author",
        description="The author of the source document",
        type="string",
    ),
]

# Step 2: describe what the page_content (the unfiltered, semantic part)
# actually represents -- helps the LLM decide what stays in the semantic
# query vs what becomes a structured filter.
document_content_description = (
    "Technical notes and articles about building production RAG systems"
)

query_constructor_llm = ChatGroq(model="llama-3.1-8b-instant", temperature=0)

# Step 3: build the retriever. Under the hood this:
#   1. Prompts the LLM with your schema + the user's question
#   2. LLM outputs a structured query (semantic text + filter expression)
#   3. The filter is translated into YOUR vector store's native filter
#      syntax (FAISS, Chroma, Pinecone, etc. each need a "translator" --
#      LangChain handles this automatically based on vectorstore type)
#   4. Runs vectorstore.similarity_search(query, filter=filter) for you
self_query_retriever = SelfQueryRetriever.from_llm(
    llm=query_constructor_llm,
    vectorstore=vectorstore,  # your existing FAISS store
    document_contents=document_content_description,
    metadata_field_info=metadata_field_info,
    enable_limit=True,  # lets the LLM also infer "top 5" style limits from phrasing
    verbose=True,  # prints the constructed structured query -- great for debugging
)

# --- Example queries and what gets constructed --------------------------
# "What has Lewis written about RAG after 2023?"
#   -> semantic query: "RAG"
#   -> filter: AND(eq("author", "Lewis"), gt("published_year", 2023))
#
# "chunking notes from chunking.md"
#   -> semantic query: "chunking"
#   -> filter: eq("source", "chunking.md")
#
# "anything about embeddings"   (no metadata signal in the question)
#   -> semantic query: "embeddings"
#   -> filter: None   (falls back to plain semantic search, correctly)

docs = self_query_retriever.invoke("What has Lewis written about RAG after 2023?")

# --- Wiring into your RAG chain: identical pattern as always -----------
rag_chain_self_query = (
    RunnablePassthrough.assign(
        context=(lambda x: x["question"]) | self_query_retriever | format_docs
    )
    | prompt
    | llm
    | StrOutputParser()
)
```

**Important caveat for FAISS specifically:** FAISS's native metadata filtering support is more limited than purpose-built vector DBs (Chroma, Pinecone, Weaviate, Qdrant) — LangChain's FAISS wrapper applies metadata filters as a **post-filter** on top of the similarity search results rather than pushing the filter down into the index itself. That works fine at moderate scale but means you should over-retrieve (`k`) before filtering, the same principle as reranking — otherwise valid documents that didn't make the unfiltered top-k get filtered out for nothing. At larger scale, this is one of the practical reasons production systems migrate off FAISS to a DB with native filtered search (Qdrant/Weaviate/pgvector).

### 4.3 Self-query vs. manual metadata filtering (which you already learned)

| | Manual metadata filtering (what you implemented earlier) | Self-Query |
|---|---|---|
| Who writes the filter | You, in code (`filter={"category": "rag"}`) | The LLM, inferred from natural language |
| When to use | You (the developer) know the exact filter ahead of time — e.g. a UI dropdown, an API parameter | The *end user* expresses the filter conversationally and you can't predict it in code |
| Failure mode | None — it's deterministic, you wrote it | LLM mis-parses the schema/intent → wrong or missing filter; needs `verbose=True` debugging and good `AttributeInfo` descriptions |
| Cost | Free (no extra LLM call) | +1 LLM call per query (the "query constructor" step) |

In production, these aren't mutually exclusive — you'll often combine both: self-query for the parts of the filter that come from free-text user intent, manual filtering for parts that come from your application's own context (e.g. `tenant_id` you always inject server-side regardless of what the LLM infers — **never trust the LLM to be your only enforcement of access-control filters**).

---

## PART 5 — PUTTING IT ALL TOGETHER

A realistic production pipeline composing everything above:

```python
"""
full_pipeline.py
------------------
Composed pipeline: query rewriting (handles chat history) -> multi-query
expansion (recall) -> dedup/fusion -> cross-encoder reranking (precision)
-> final LLM call.

This is intentionally "more than you need" for most use cases -- start
with retrieve-then-rerank alone (Part 3) and ONLY add query transformation
on top once you've measured a real recall problem (see evaluation note
at the bottom). Stacking every technique by default adds latency/cost
for diminishing returns.
"""

from langchain_core.runnables import RunnablePassthrough, RunnableLambda


def full_retrieval_pipeline(question: str, chat_history: list = None) -> str:
    chat_history = chat_history or []

    # 1. Rewrite for conversational context (Part 2.1)
    standalone_question = rewrite_query(question, chat_history)

    # 2. Multi-query expansion for recall (Part 2.2)
    queries = generate_queries_chain.invoke({"question": standalone_question, "n": 3})
    queries.append(standalone_question)  # always include the literal rewritten question

    # 3. Retrieve for each query against your base FAISS retriever,
    #    then fuse with Reciprocal Rank Fusion (Part 2.2)
    result_lists = [retriever.invoke(q) for q in queries]
    fused_candidates = reciprocal_rank_fusion(result_lists)[:20]  # cap before reranking

    # 4. Cross-encoder rerank down to a tight, high-precision set (Part 3.5)
    final_docs = rerank(standalone_question, fused_candidates, top_n=4)

    # 5. Build context and call the LLM
    context = format_docs(final_docs)
    return rag_answer_chain.invoke({
        "context": context,
        "question": standalone_question,
    })


# Equivalent as a single LCEL chain, if you prefer that style throughout:
full_pipeline_chain = (
    RunnablePassthrough.assign(
        question=lambda x: rewrite_query(x["question"], x.get("chat_history", []))
    )
    | RunnablePassthrough.assign(
        context=RunnableLambda(
            lambda x: format_docs(
                rerank(
                    x["question"],
                    reciprocal_rank_fusion([
                        retriever.invoke(q)
                        for q in generate_queries_chain.invoke({
                            "question": x["question"],
                            "n": 3,
                        })
                        + [x["question"]]
                    ])[:20],
                    top_n=4,
                )
            )
        )
    )
    | prompt
    | llm
    | StrOutputParser()
)
```

### A note on evaluation (your natural next topic after this)

None of this matters if you can't measure whether it's actually helping. Before you move on, it's worth keeping a small "golden set" of (question, expected source chunk) pairs from your own corpus, and tracking:
- **Hit rate / Recall@k** — is the right chunk anywhere in the top-k retrieved, before reranking?
- **MRR (Mean Reciprocal Rank)** — how high up is the right chunk ranked, after reranking?
- **Faithfulness / groundedness** of the final answer — does the LLM's answer actually stick to the retrieved context?

Frameworks like **RAGAS** or **TruLens** automate exactly this, and it's the natural module to study right after this one — it's how you'd actually prove, with numbers, that adding HyDE or a reranker improved your specific pipeline rather than just adding latency.
