# Conversational RAG + RAG Evaluation — Full Practical Guide

You're at a good point to learn this — you already have retrieval, query transformation, and re-ranking. Conversational RAG and Evaluation are the two layers that make a RAG system *usable* (handles multi-turn dialogue) and *trustworthy* (you can prove it works and catch regressions). Let's go deep.

---

# PART 1: CONVERSATIONAL RAG

## 1.1 What is Conversational RAG?

Plain RAG answers **one isolated question** using retrieved context. It has no memory of what was asked before.

**Conversational RAG** adds a *state* (chat history) so the system can handle follow-ups, pronouns, and implicit references — the way a human conversation works.

Example of why this matters:

```
Turn 1 User: "What are the side effects of Metformin?"
Turn 2 User: "What about for elderly patients?"
```

In Turn 2, "What about" and "elderly patients" make no sense to a vector search by themselves. A plain RAG system would embed `"What about for elderly patients?"` and retrieve garbage — there's no mention of Metformin in that query.

Conversational RAG needs to:
1. **Understand turn 2 depends on turn 1** (coreference / ellipsis resolution)
2. **Rewrite/condense** it into a standalone query: `"What are the side effects of Metformin in elderly patients?"`
3. **Retrieve** using that standalone query
4. **Generate** an answer using both retrieved docs AND chat history (for tone/continuity)
5. **Store** the new turn back into memory

This pipeline (condense → retrieve → generate → store) is the backbone of every production conversational RAG system (ChatGPT-with-docs, customer support bots, etc.)

---

## 1.2 The Core Architecture

```
┌──────────────┐     ┌────────────────────┐     ┌───────────┐     ┌──────────┐
│ Chat History │ --> │ History-Aware      │ --> │ Retriever │ --> │   LLM    │
│ (memory)     │     │ Query Reformulation│     │           │     │ Generate │
└──────────────┘     └────────────────────┘     └───────────┘     └──────────┘
        ^                                                               │
        └────────────────────── store new turn ─────────────────────────┘
```

Let's build each piece with heavily commented code using LangChain (since that's your stack).

---

## 1.3 Memory Types

### A) ConversationBufferMemory — stores EVERYTHING verbatim

**What it is:** Keeps the raw list of every human/AI message, no compression. Simple, accurate, but **grows unboundedly** — eventually blows your context window and increases cost/latency.

```python
"""
CONVERSATION BUFFER MEMORY
 ---------------------------
Stores the FULL raw conversation history.
Pros: 100% accurate, no information loss.
Cons: Token usage grows linearly with conversation length.
       Not viable for long-running sessions (will exceed context window).
Use case: Short-lived sessions (single support ticket, short Q&A session).
"""

from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.messages import HumanMessage, AIMessage


class ConversationBufferMemory:
    def __init__(self):
        # Internally this is just a list of Message objects (Human/AI)
        self.history = InMemoryChatMessageHistory()

    def add_user_message(self, text: str):
        # Append raw human message - no summarization, no truncation
        self.history.add_message(HumanMessage(content=text))

    def add_ai_message(self, text: str):
        # Append raw AI message - no summarization, no truncation
        self.history.add_message(AIMessage(content=text))

    def get_messages(self):
        # Returns ALL messages so far, in chronological order.
        # As the conversation grows, this list (and token count) grows too.
        return self.history.messages

    def as_text(self) -> str:
        """Flatten messages into plain text - useful for prompt injection."""
        lines = []
        for msg in self.get_messages():
            role = "User" if isinstance(msg, HumanMessage) else "Assistant"
            lines.append(f"{role}: {msg.content}")
        return "\n".join(lines)


# --- usage ---
memory = ConversationBufferMemory()
memory.add_user_message("What are the side effects of Metformin?")
memory.add_ai_message(
    "Common side effects include nausea, diarrhea, and stomach upset."
)
memory.add_user_message("What about for elderly patients?")

print(memory.as_text())
# User: What are the side effects of Metformin?
# Assistant: Common side effects include nausea, diarrhea, and stomach upset.
# User: What about for elderly patients?
```

### B) ConversationSummaryMemory — compresses old turns into a running summary

**What it is:** Instead of storing every message, an LLM periodically **summarizes** the conversation so far. Keeps token usage roughly constant regardless of conversation length, at the cost of some detail loss (and an extra LLM call to summarize).

```python
"""
CONVERSATION SUMMARY MEMORY
----------------------------
Instead of keeping raw messages, this periodically asks an LLM to
COMPRESS the conversation into a running summary string.

Pros: Token usage stays roughly CONSTANT no matter how long the chat gets.
Cons: Lossy - fine details/exact wording can be dropped or distorted
       by the summarizing LLM. Costs extra LLM calls (summarization itself).
Use case: Long-running conversations (multi-day support chats, agents
          that run for hours) where exact wording of old turns matters less
          than the overall gist.
"""

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate


class ConversationSummaryMemory:
    def __init__(self, llm: ChatOpenAI):
        self.llm = llm
        self.summary = ""  # running summary, starts empty

        # Prompt that tells the LLM: take old summary + new exchange -> new summary
        self.summarizer_prompt = ChatPromptTemplate.from_template(
            """Progressively summarize the conversation below.
Current summary:
{summary}

New lines to add:
{new_lines}

Produce a NEW summary that incorporates the new lines, staying concise
but keeping all facts/entities/decisions relevant for future turns."""
        )

    def add_exchange(self, user_msg: str, ai_msg: str):
        """Called after every user+AI turn pair to update the summary."""
        new_lines = f"User: {user_msg}\nAssistant: {ai_msg}"

        chain = self.summarizer_prompt | self.llm
        # This is the "compression" step - an LLM call that costs tokens
        # but keeps the STORED summary itself small.
        result = chain.invoke({"summary": self.summary, "new_lines": new_lines})
        self.summary = result.content  # overwrite with the new, compressed summary

    def get_summary(self) -> str:
        return self.summary


# --- usage ---
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
mem = ConversationSummaryMemory(llm)

mem.add_exchange(
    "What are the side effects of Metformin?",
    "Common side effects include nausea, diarrhea, and stomach upset.",
)
mem.add_exchange(
    "What about for elderly patients?",
    "In elderly patients, Metformin carries an additional risk of lactic acidosis "
    "due to reduced kidney function, so dosage should be monitored carefully.",
)

print(mem.get_summary())
# -> "The user asked about Metformin side effects (nausea, diarrhea, stomach upset)
#     and specifically about elderly patients, who have an additional risk of
#     lactic acidosis due to reduced kidney function."
```

**Hybrid in production:** Most real systems use **ConversationSummaryBufferMemory** — keep the last N raw messages verbatim (for exact recent context) AND a summary of everything older. LangChain has this built in (`ConversationSummaryBufferMemory`), but conceptually it's just combining the two classes above with a token threshold.

---

## 1.4 History-Aware Retrieval (Query Condensation)

This is the **most important piece** of conversational RAG. The idea: before retrieving, rewrite the latest user question into a **standalone** question using chat history, via an LLM call.

```python
"""
HISTORY-AWARE RETRIEVER (a.k.a. "condense question" pattern)
---------------------------------------------------------------
Production conversational RAG NEVER searches with the raw last message.
It first asks an LLM: "given this chat history + new question,
rewrite the question to be fully self-contained (standalone)."

This solves:
  - Pronoun resolution ("it", "that", "those")
  - Ellipsis ("What about elderly patients?" -> missing subject)
  - Topic continuation across turns

This is literally the LangChain `create_history_aware_retriever` pattern,
written manually so you understand the mechanics.
"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser

# This prompt is the workhorse of conversational RAG.
# Note: it does NOT answer the question. It only REWRITES it.
CONDENSE_QUESTION_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "Given a chat history and the latest user question which might "
        "reference context in the chat history, formulate a STANDALONE question "
        "which can be understood WITHOUT the chat history. "
        "Do NOT answer the question. Just reformulate it if needed, "
        "otherwise return it as-is.",
    ),
    MessagesPlaceholder("chat_history"),  # injects prior turns here
    ("human", "{input}"),  # the new, possibly ambiguous question
])


def condense_question(llm, chat_history: list, new_question: str) -> str:
    """
    chat_history: list of HumanMessage/AIMessage objects (raw buffer,
                  or could be a summary string converted to a single message)
    new_question: the latest raw user input (possibly ambiguous)
    """
    chain = CONDENSE_QUESTION_PROMPT | llm | StrOutputParser()
    standalone_question = chain.invoke({
        "chat_history": chat_history,
        "input": new_question,
    })
    return standalone_question


# --- usage ---
from langchain_core.messages import HumanMessage, AIMessage

history = [
    HumanMessage(content="What are the side effects of Metformin?"),
    AIMessage(
        content="Common side effects include nausea, diarrhea, and stomach upset."
    ),
]

standalone = condense_question(llm, history, "What about for elderly patients?")
print(standalone)
# -> "What are the side effects of Metformin in elderly patients?"
# THIS is what gets embedded and sent to the vector DB - not the raw "What about..."
```

### Wiring it into a full retrieval chain (LangChain's actual helper)

```python
"""
FULL HISTORY-AWARE RAG CHAIN
------------------------------
This wires together:
  1. create_history_aware_retriever -> condenses question, then retrieves
  2. create_stuff_documents_chain   -> stuffs retrieved docs into final answer prompt
  3. create_retrieval_chain          -> glues 1+2 together

This is the canonical LangChain pattern for conversational RAG.
"""

from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains.history_aware_retriever import create_history_aware_retriever
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

# assume `retriever` already exists from your earlier vector-DB work
# (similarity / MMR / hybrid - doesn't matter which, this layer is retriever-agnostic)

# Step 1: history-aware retriever
# Internally: runs CONDENSE_QUESTION_PROMPT -> gets standalone query -> calls retriever.invoke(query)
history_aware_retriever = create_history_aware_retriever(
    llm,
    retriever,
    CONDENSE_QUESTION_PROMPT,
)

# Step 2: the "answer generation" prompt - uses retrieved docs + chat history + question
ANSWER_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a helpful medical assistant. Use the following retrieved "
        "context to answer the user's question. If you don't know, say so.\n\n"
        "Context:\n{context}",
    ),
    MessagesPlaceholder("chat_history"),
    ("human", "{input}"),
])
answer_chain = create_stuff_documents_chain(llm, ANSWER_PROMPT)

# Step 3: combine into one runnable chain
conversational_rag_chain = create_retrieval_chain(history_aware_retriever, answer_chain)

# --- usage across turns ---
chat_history = []

response_1 = conversational_rag_chain.invoke({
    "input": "What are the side effects of Metformin?",
    "chat_history": chat_history,
})
chat_history.append(HumanMessage(content="What are the side effects of Metformin?"))
chat_history.append(AIMessage(content=response_1["answer"]))

response_2 = conversational_rag_chain.invoke({
    "input": "What about for elderly patients?",  # ambiguous on its own
    "chat_history": chat_history,  # but resolved using history
})
print(response_2["answer"])
```

### Production with persistent, per-session memory (RunnableWithMessageHistory)

```python
"""
SESSION-BASED RETRIEVAL
-------------------------
In production you have MANY users, each with their OWN conversation.
You can't use one global `chat_history` list - you need memory keyed
by session_id (could be a user_id, a chat thread id, etc.), backed by
a real store (Redis, Postgres, DynamoDB...) not just RAM.

RunnableWithMessageHistory handles the "look up history for this
session_id, inject it, then save the new turn back" lifecycle for you.
"""

from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_community.chat_message_histories import RedisChatMessageHistory


def get_session_history(session_id: str):
    # Each session gets its OWN history object, backed by Redis here.
    # In production swap this for Postgres/DynamoDB-backed history for durability.
    return RedisChatMessageHistory(session_id=session_id, url="redis://localhost:6379")


conversational_rag_with_memory = RunnableWithMessageHistory(
    conversational_rag_chain,
    get_session_history,
    input_messages_key="input",
    history_messages_key="chat_history",
    output_messages_key="answer",
)

# --- usage: each user has a distinct session_id ---
config_user_42 = {"configurable": {"session_id": "user_42_thread_1"}}

r1 = conversational_rag_with_memory.invoke(
    {"input": "What are the side effects of Metformin?"},
    config=config_user_42,
)
r2 = conversational_rag_with_memory.invoke(
    {"input": "What about for elderly patients?"},  # automatically resolved
    config=config_user_42,
)
# A DIFFERENT user (session_id) gets a completely separate, isolated history.
config_user_99 = {"configurable": {"session_id": "user_99_thread_1"}}
r3 = conversational_rag_with_memory.invoke(
    {"input": "Hi, who are you?"},
    config=config_user_99,
)
```

This is the **real production pattern**: session isolation + durable backing store, so a server restart or horizontal scaling doesn't lose anyone's conversation.

---

## 1.5 Contextual Compression

Different concept from memory — this compresses **retrieved documents**, not chat history. After retrieval, you often get long chunks where only a sentence or two is actually relevant. Contextual compression strips out the irrelevant parts before stuffing into the LLM prompt — saves tokens and reduces noise/distraction for the LLM.

```python
"""
CONTEXTUAL COMPRESSION RETRIEVER
-----------------------------------
Wraps a base retriever. After retrieval, for EACH document, an LLM
(or a smaller extractor model) trims the doc down to only the parts
relevant to the query, discarding irrelevant filler.

Why this matters in conversational RAG specifically:
  Conversations drift across many subtopics. Chunks retrieved for an
  earlier-established topic may contain large irrelevant sections.
  Compression keeps the final context focused, even as the
  conversation (and condensed queries) evolve turn to turn.
"""

from langchain.retrievers import ContextualCompressionRetriever
from langchain.retrievers.document_compressors import LLMChainExtractor

# This compressor does an LLM call per retrieved doc:
# "extract only the parts of this document relevant to the query"
compressor = LLMChainExtractor.from_llm(llm)

compression_retriever = ContextualCompressionRetriever(
    base_compressor=compressor,
    base_retriever=retriever,  # your existing similarity/MMR/hybrid retriever
)

# --- usage ---
docs = compression_retriever.invoke(
    "What are the side effects of Metformin in elderly patients?"
)
for d in docs:
    print(
        d.page_content
    )  # much shorter than raw chunks - only relevant sentences survive
```

You'd swap `history_aware_retriever`'s inner `retriever` for this `compression_retriever` to get **history-aware + compressed** retrieval in one pipeline.

---

## 1.6 Putting it ALL together (one diagram in code form)

```python
"""
FULL PRODUCTION CONVERSATIONAL RAG PIPELINE
----------------------------------------------
Combines: session memory + history-aware condensation + compression + generation
"""

# 1. Base retriever (from your earlier vector DB work - hybrid search, MMR, etc.)
base_retriever = vectorstore.as_retriever(search_type="mmr", search_kwargs={"k": 8})

# 2. Wrap with contextual compression (trims irrelevant parts of each chunk)
compressed_retriever = ContextualCompressionRetriever(
    base_compressor=LLMChainExtractor.from_llm(llm),
    base_retriever=base_retriever,
)

# 3. Wrap with history-awareness (condenses follow-ups into standalone queries)
history_aware = create_history_aware_retriever(
    llm, compressed_retriever, CONDENSE_QUESTION_PROMPT
)

# 4. Answer generation chain
answer_chain = create_stuff_documents_chain(llm, ANSWER_PROMPT)

# 5. Glue retrieval + generation
rag_chain = create_retrieval_chain(history_aware, answer_chain)

# 6. Wrap with per-session persistent memory
final_chain = RunnableWithMessageHistory(
    rag_chain,
    get_session_history,  # Redis/Postgres backed, keyed by session_id
    input_messages_key="input",
    history_messages_key="chat_history",
    output_messages_key="answer",
)

# This `final_chain` is what you'd expose behind your API endpoint.
```

---

# PART 2: EVALUATION OF RAG

## 2.1 What is RAG Evaluation?

RAG has **two failure surfaces**, so evaluation must check both:

1. **Retrieval quality** — did we fetch the right documents?
2. **Generation quality** — did the LLM use those documents correctly (no hallucination, answers the actual question)?

A system can fail in either layer independently:
- Good retrieval + bad generation → LLM hallucinates despite having correct context.
- Bad retrieval + good generation → LLM faithfully repeats wrong/irrelevant documents.

This is why RAG-specific metrics exist — generic "is the answer good" LLM-judge scoring isn't enough; you need metrics that isolate *which* layer broke.

## 2.2 The Core RAG Metrics (RAGAS framework)

RAGAS (RAG Assessment) is the most widely used open-source eval framework. Its four core metrics:

| Metric | What it measures | Needs |
|---|---|---|
| **Faithfulness** | Is every claim in the answer actually supported by the retrieved context? (hallucination check) | answer + context |
| **Answer Relevancy** | Does the answer actually address the question (not faithful-but-off-topic)? | question + answer |
| **Context Precision** | Of the retrieved chunks, what fraction are actually relevant/useful (ranked appropriately)? | question + context + ground truth |
| **Context Recall** | Of all the information needed to answer, how much did retrieval actually surface? | context + ground truth |

```python
"""
RAGAS EVALUATION - the 4 core metrics
----------------------------------------
RAGAS uses an LLM-as-judge internally to score each metric (0-1 scale).

faithfulness:        answer claims vs retrieved context (catches hallucination)
answer_relevancy:    answer vs question (catches off-topic/evasive answers)
context_precision:   ranks how "signal vs noise" the retrieved chunks are
context_recall:      checks if retrieval missed information needed for a
                      complete answer (compared against a ground-truth answer)
"""

from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
)
from datasets import Dataset

# RAGAS expects this exact schema - one row per (question, retrieved_docs, answer, ground_truth)
eval_data = {
    "question": ["What are the side effects of Metformin in elderly patients?"],
    "answer": [
        # this is what YOUR RAG pipeline actually generated
        "In elderly patients, Metformin can cause lactic acidosis due to "
        "reduced kidney function, along with the usual nausea and diarrhea."
    ],
    "contexts": [
        # this is what YOUR retriever actually returned (list of chunk strings)
        [
            "Metformin commonly causes nausea, diarrhea, and stomach upset.",
            "In patients with reduced renal function, Metformin carries an "
            "elevated risk of lactic acidosis, particularly in elderly populations.",
        ]
    ],
    "ground_truth": [
        # the IDEAL/reference answer - written by a human expert, used to
        # check recall (did we surface everything needed?)
        "Elderly patients on Metformin face increased risk of lactic acidosis "
        "due to age-related kidney function decline, in addition to common "
        "side effects like nausea and diarrhea."
    ],
}

dataset = Dataset.from_dict(eval_data)

results = evaluate(
    dataset,
    metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
)

print(results)
# Example output:
# {'faithfulness': 1.0, 'answer_relevancy': 0.94, 'context_precision': 0.88, 'context_recall': 0.92}
#
# faithfulness=1.0      -> every claim in the answer IS backed by the retrieved context
# answer_relevancy=0.94 -> answer is highly on-topic for the question
# context_precision=0.88 -> retrieved chunks were mostly relevant (some noise)
# context_recall=0.92   -> retrieval captured most of what was needed
```

### Why Faithfulness specifically matters so much

```python
"""
FAITHFULNESS - DEEP DIVE
---------------------------
Faithfulness works by:
  1. Breaking the generated answer into individual factual claims/statements
  2. For EACH claim, asking an LLM judge: "is this claim supported/entailed
     by the retrieved context, yes/no?"
  3. faithfulness score = (# supported claims) / (total claims)

This is the PRIMARY hallucination detector in RAG evaluation.
"""


# Example of what's happening under the hood (simplified manual version):
def manual_faithfulness_check(answer: str, context: str, llm) -> float:
    # Step 1: extract claims from the answer
    claim_extraction_prompt = f"""
    Break the following answer into a list of individual factual claims,
    one per line:

    Answer: {answer}
    """
    claims_text = llm.invoke(claim_extraction_prompt).content
    claims = [c.strip("- ").strip() for c in claims_text.split("\n") if c.strip()]

    # Step 2: for each claim, check if it's entailed by context
    supported = 0
    for claim in claims:
        verify_prompt = f"""
        Context: {context}
        Claim: {claim}

        Is this claim DIRECTLY supported by the context above? Answer only YES or NO.
        """
        verdict = llm.invoke(verify_prompt).content.strip().upper()
        if verdict.startswith("YES"):
            supported += 1

    return supported / len(claims) if claims else 0.0
```

## 2.3 TruLens — alternative framework with a different philosophy

RAGAS is dataset-batch oriented (run on a fixed eval set). **TruLens** focuses on **live tracing/instrumentation** — it wraps your actual app and scores every real production call, plus gives you a dashboard for ongoing monitoring.

```python
"""
TRULENS - the "RAG Triad" + live app instrumentation
---------------------------------------------------------
TruLens defines the "RAG Triad" (their version of RAGAS's metrics):
  - Context Relevance:  query <-> retrieved context
  - Groundedness:       context <-> generated answer (== faithfulness)
  - Answer Relevance:   query <-> generated answer

Key difference from RAGAS: TruLens wraps your LIVE running app
(via instrumentation hooks) so you get per-request traces + scores
in a dashboard, not just a one-off batch evaluation.
"""

from trulens.core import TruSession
from trulens.apps.langchain import TruChain
from trulens.providers.openai import OpenAI as TruOpenAI_Provider
from trulens.core import Feedback
import numpy as np

session = TruSession()  # boots up TruLens's local tracking DB

provider = TruOpenAI_Provider(model_engine="gpt-4o-mini")  # the LLM-judge backend

# Define the three feedback functions (the "RAG Triad")
f_groundedness = (
    Feedback(provider.groundedness_measure_with_cot_reasons, name="Groundedness")
    .on(context_key="context")
    .on_output()
)  # context -> answer

f_context_relevance = (
    Feedback(provider.context_relevance_with_cot_reasons, name="Context Relevance")
    .on_input()
    .on(context_key="context")
    .aggregate(np.mean)
)  # query -> context

f_answer_relevance = Feedback(
    provider.relevance_with_cot_reasons, name="Answer Relevance"
).on_input_output()  # query -> answer

# Wrap your ACTUAL LangChain conversational_rag_chain from Part 1
tru_recorder = TruChain(
    conversational_rag_chain,
    app_id="conversational_rag_v1",
    feedbacks=[f_groundedness, f_context_relevance, f_answer_relevance],
)

# Now every real call gets automatically traced + scored:
with tru_recorder as recording:
    response = conversational_rag_chain.invoke({
        "input": "What about for elderly patients?",
        "chat_history": chat_history,
    })

# View results in TruLens's local dashboard:
# session.run_dashboard()   # launches a Streamlit app showing all traces + scores
```

**RAGAS vs TruLens — when to use which:**
- **RAGAS** → offline batch evaluation against a curated eval set (CI/CD regression gate, before deploying a change).
- **TruLens** → live monitoring of production traffic (catching drift/degradation over time, debugging specific bad responses with full traces).

Most production teams use **both**: RAGAS in CI, TruLens in prod monitoring.

## 2.4 Custom Metrics

Off-the-shelf metrics don't cover domain-specific correctness. Example: in a medical RAG, you might need a **"contraindication safety"** metric that off-the-shelf RAGAS doesn't have.

```python
"""
CUSTOM METRIC EXAMPLE: "Safety Compliance" for medical RAG
----------------------------------------------------------------
Business requirement: the answer must NEVER omit known contraindications
if the context mentions them. Generic faithfulness/relevancy metrics
don't specifically check for "did we OMIT a critical safety fact?"
(faithfulness checks hallucination, not omission).
"""

from langchain_core.prompts import ChatPromptTemplate

SAFETY_JUDGE_PROMPT = ChatPromptTemplate.from_template(
    """You are a clinical safety auditor.

Retrieved context (ground truth medical info):
{context}

Generated answer:
{answer}

Question: Does the context mention ANY contraindication, warning, or risk
that is MISSING from the generated answer?

Respond in this exact JSON format:
{{"missing_safety_info": true/false, "explanation": "..."}}"""
)


def safety_compliance_metric(question: str, context: str, answer: str, llm) -> dict:
    chain = SAFETY_JUDGE_PROMPT | llm
    result = chain.invoke({"context": context, "answer": answer})

    import json

    parsed = json.loads(result.content)

    # score = 1.0 if NOTHING critical was omitted, else 0.0
    score = 0.0 if parsed["missing_safety_info"] else 1.0
    return {
        "metric": "safety_compliance",
        "score": score,
        "explanation": parsed["explanation"],
    }


# --- usage ---
result = safety_compliance_metric(
    question="What are the side effects of Metformin in elderly patients?",
    context="Metformin carries risk of lactic acidosis in patients with renal impairment, "
    "especially elderly patients. Contraindicated in severe renal failure (eGFR<30).",
    answer="Metformin commonly causes nausea and diarrhea.",  # BAD - omits the critical risk
    llm=llm,
)
print(result)
# {'metric': 'safety_compliance', 'score': 0.0,
#  'explanation': 'The answer omits the lactic acidosis risk and renal contraindication
#                  mentioned in the context, which is critical safety information.'}
```

This is the pattern for ANY custom metric: **(1) define exactly what "good" means for your domain, (2) write an LLM-judge prompt that checks for it, (3) parse a structured score out.**

## 2.5 Regression Testing / Tracking

This is what makes evaluation *useful in CI/CD*, not just a one-off report. You build a **fixed golden dataset** (questions + ideal answers + ideal source chunks), and run it automatically every time you change anything (new chunking strategy, new embedding model, new prompt, new re-ranker) — to catch regressions before deploying.

```python
"""
REGRESSION TEST SUITE FOR RAG
---------------------------------
Treat your RAG pipeline like normal software: you need a test suite
that runs on every change and FAILS THE BUILD if quality drops below
a threshold. This is exactly like unit tests, but with LLM-judged scores
instead of assert equal.
"""

import json
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    context_precision,
    context_recall,
    answer_relevancy,
)

# 1. GOLDEN DATASET - curated once, version-controlled (e.g. golden_eval_set.json)
#    Each entry has a real-world question + a human-verified ground truth answer.
GOLDEN_SET_PATH = "golden_eval_set.json"


def load_golden_set():
    with open(GOLDEN_SET_PATH) as f:
        return json.load(f)
    # Example structure:
    # [
    #   {"question": "...", "ground_truth": "..."},
    #   {"question": "...", "ground_truth": "..."},
    #   ... (50-200 curated, representative questions)
    # ]


# 2. THRESHOLDS - the minimum acceptable score per metric, decided once,
#    based on your CURRENT best-known baseline (don't let it silently regress)
THRESHOLDS = {
    "faithfulness": 0.90,
    "answer_relevancy": 0.85,
    "context_precision": 0.80,
    "context_recall": 0.80,
}


def run_regression_suite(rag_pipeline, llm):
    golden_set = load_golden_set()

    questions, answers, contexts, ground_truths = [], [], [], []

    for item in golden_set:
        # Run the ACTUAL pipeline (whatever version you're testing - new chunker,
        # new embedding model, new prompt, etc.) to get a real answer + real context
        result = rag_pipeline.invoke({"input": item["question"], "chat_history": []})

        questions.append(item["question"])
        answers.append(result["answer"])
        contexts.append([doc.page_content for doc in result["context"]])
        ground_truths.append(item["ground_truth"])

    dataset = Dataset.from_dict({
        "question": questions,
        "answer": answers,
        "contexts": contexts,
        "ground_truth": ground_truths,
    })

    scores = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
    ).to_pandas()

    # 3. AGGREGATE per metric, then check against thresholds
    summary = {}
    failed = []
    for metric, threshold in THRESHOLDS.items():
        avg_score = scores[metric].mean()
        summary[metric] = avg_score
        if avg_score < threshold:
            failed.append(f"{metric}: {avg_score:.3f} < threshold {threshold}")

    return summary, failed


# --- usage in a CI pipeline (e.g. GitHub Actions) ---
summary, failures = run_regression_suite(conversational_rag_chain, llm)
print("Eval summary:", summary)

if failures:
    print("REGRESSION DETECTED:")
    for f in failures:
        print(" -", f)
    raise SystemExit(1)  # non-zero exit -> CI build fails -> blocks merge/deploy
else:
    print("All metrics passed thresholds. Safe to deploy.")
```

```python
"""
TRACKING SCORES OVER TIME (regression dashboard, not just pass/fail)
------------------------------------------------------------------------
Beyond pass/fail gating, you want a HISTORY of scores across commits/versions
to spot slow degradation (e.g. faithfulness creeping down 0.95 -> 0.91 -> 0.87
over several "small" changes, none individually failing the threshold).
"""

import csv
from datetime import datetime


def log_eval_run(summary: dict, version_tag: str, log_path="eval_history.csv"):
    """Append this run's scores to a CSV - one row per evaluation run."""
    row = {
        "timestamp": datetime.utcnow().isoformat(),
        "version": version_tag,  # e.g. git commit hash or "chunking_v3"
        **summary,  # faithfulness, answer_relevancy, etc.
    }

    file_exists = False
    try:
        with open(log_path, "r"):
            file_exists = True
    except FileNotFoundError:
        pass

    with open(log_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


# --- usage ---
log_eval_run(summary, version_tag="recursive_chunking_v2_bge_embeddings")
# Later: load eval_history.csv into pandas, plot faithfulness/context_recall
# over time per version -> classic regression-tracking dashboard.
```

---

## 2.6 Putting Evaluation Into Your Actual Pipeline

The realistic workflow you'd follow:

1. Build a **golden dataset** of 50–200 representative questions with human-verified ground-truth answers (and ideally the ground-truth "should-retrieve" chunk IDs, for cleaner context_recall checks).
2. Run **RAGAS** on it whenever you change chunking/embeddings/retrieval/prompts — gate deploys on thresholds.
3. Add **custom metrics** for domain-specific correctness RAGAS can't see (safety, compliance, tone, formatting).
4. Deploy **TruLens** (or similar) in production for live monitoring/tracing of real traffic — this catches issues your golden set didn't anticipate (new question types, edge cases, drift).
5. **Log every eval run** with a version tag so you can track metric trends over time, not just pass/fail per change.

---

## Where this fits in your overall learning roadmap

You now have, end-to-end:
**Loading (docling) → Chunking → Embeddings → Vector DB/Retrieval → Query Transform/Re-rank → Conversational layer → Evaluation.**

The natural next steps after this (if you want to keep going toward "fully production"): **observability/tracing (LangSmith/Langfuse), caching (semantic cache for repeated queries), guardrails (PII/safety filters), and agentic RAG (tool-calling + RAG combined).** Happy to go deep on any of those next, or help you wire this Conversational RAG + Eval code directly into your existing project.