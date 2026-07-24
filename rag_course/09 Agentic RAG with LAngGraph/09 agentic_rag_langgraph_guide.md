# Agentic RAG with LangGraph — From Theory to Production

> Assumes you already know: loaders, chunking, embeddings, vector DBs (Qdrant), caching, query
> enrichment, hybrid search, RRF, MMR, cross-encoder reranking, metadata filtering, evaluation.
> This guide builds **on top** of that — it does not re-teach retrieval internals, it teaches you
> how to wrap all of that inside an **agentic control loop** using LangGraph.

---

## Part 0 — Naive RAG vs Agentic RAG (the mental model)

**Naive RAG** is a fixed pipeline:

```
query -> retrieve -> stuff context -> LLM -> answer
```

It always retrieves, always from the same source, never checks if the retrieved docs are
actually good enough, never retries, never asks for help. This breaks in production because:

- Some queries need **no retrieval at all** ("hi", "summarize what you just said").
- Some queries need **multiple sources** (internal docs + SQL + web).
- Retrieved chunks are sometimes **irrelevant** (bad embedding match, wrong metadata filter) and
  a naive pipeline will happily hallucinate an answer from garbage context.
- Complex queries need to be **decomposed** into sub-queries.
- Enterprises need **auditability, retries, human approval, and cost control**.

**Agentic RAG** turns the fixed pipeline into a **graph with a brain**: an LLM (or a set of small
classifiers) makes *decisions* at each step — whether to retrieve, where to retrieve from, whether
the retrieved content is good enough, whether to rewrite the query, whether to escalate to a
human, etc. LangGraph is the tool we use to build that decision graph because:

- It models your app as an explicit **state machine** (nodes = steps, edges = transitions),
  instead of a hidden agent loop you can't inspect.
- It supports **conditional branching**, **cycles/loops** (retry until good), **parallel
  fan-out/fan-in** (multi-source retrieval), **persistence** (multi-turn memory), and
  **human-in-the-loop interrupts** — all first-class, all things a real agentic RAG system needs.
- Unlike a plain LangChain chain (`Runnable | Runnable | Runnable`), a graph can **loop back**
  and **change its own path at runtime**. That's the difference between "pipeline" and "agent".

---

## Part 1 — LangGraph core concepts (the vocabulary you need)

| Concept | What it is |
|---|---|
| `State` | A typed dict (usually a `TypedDict` or Pydantic model) that flows through the graph. Every node reads it and returns updates to it. |
| `Node` | A plain Python function `(state) -> partial_state_update`. This is where your retrieval, grading, generation code lives. |
| `Edge` | A fixed connection `node_a -> node_b`. |
| `Conditional Edge` | A function that inspects state and **decides which node to go to next**. This is how "routing" and "decide whether to retrieve" are implemented. |
| `START` / `END` | Special sentinel nodes marking entry/exit of the graph. |
| `StateGraph` | The builder object you add nodes/edges to, then `.compile()` into a runnable graph. |
| `Checkpointer` | Persists state after every node (e.g. `InMemorySaver`, `PostgresSaver`). Gives you multi-turn memory, resumability, and human-in-the-loop. |
| `Command` | A node can return `Command(goto=..., update=...)` to update state AND route in one step. |
| `Send` | Used for **fan-out**: dynamically launch N parallel copies of a node (e.g., "search each of these 3 sources in parallel"). |
| `interrupt()` | Pauses the graph and waits for a human to respond — used for human-in-the-loop approval. |

Install (you likely already have most of this):

```bash
pip install -U langgraph langchain langchain-openai langchain-qdrant qdrant-client langchain-community
```

We'll build **five progressively more advanced graphs**. Each one adds exactly one new
enterprise capability on top of the previous one, so you can see *why* each piece exists.

---

## LEVEL 1 — Baseline: Retrieve-then-Generate as an explicit graph (not agentic yet)

This is the "hello world" — it's the naive pipeline you already know, just expressed as a
LangGraph graph instead of a LangChain chain. We build this first so Level 2's "decide whether to
retrieve" change is obvious by comparison.

```python
"""
LEVEL 1: Naive RAG expressed as a LangGraph StateGraph.
No decision-making yet — always retrieves, always answers.
This just teaches you the LangGraph skeleton: State -> Nodes -> Edges -> compile.
"""

from typing import TypedDict, List
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from langgraph.graph import StateGraph, START, END

# ---------------------------------------------------------------------------
# 1. DEFINE STATE
# The State is the "shared memory" that flows through every node in the graph.
# Every node receives the full state and returns a dict of the fields it updates.
# ---------------------------------------------------------------------------
class RAGState(TypedDict):
    question: str            # the user's original question
    documents: List[Document]  # retrieved chunks (you already know how to hybrid-search/rerank these)
    answer: str               # final generated answer

# ---------------------------------------------------------------------------
# 2. SET UP YOUR EXISTING RETRIEVAL STACK
# Nothing new here — this is the Qdrant retriever you already built with
# hybrid search / RRF / MMR / reranking. We just wrap it as a function.
# ---------------------------------------------------------------------------
client = QdrantClient(url="http://localhost:6333")
vector_store = QdrantVectorStore(
    client=client,
    collection_name="enterprise_docs",
    embedding=None,  # plug in your real embedding model here
)
# In production this retriever already includes your reranker/MMR/RRF logic —
# treat it as a black box "retrieve(query) -> List[Document]" for this guide.
retriever = vector_store.as_retriever(search_kwargs={"k": 5})

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# ---------------------------------------------------------------------------
# 3. DEFINE NODES
# A node is just a function: (state) -> dict of updated fields.
# ---------------------------------------------------------------------------
def retrieve_node(state: RAGState) -> dict:
    """Always retrieves documents for the question. No decision-making."""
    docs = retriever.invoke(state["question"])
    return {"documents": docs}  # only return the keys you're updating

def generate_node(state: RAGState) -> dict:
    """Stuffs retrieved docs into a prompt and generates the final answer."""
    context = "\n\n".join(d.page_content for d in state["documents"])
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Answer ONLY using the provided context. If the answer isn't in the context, say you don't know."),
        ("human", "Context:\n{context}\n\nQuestion: {question}")
    ])
    chain = prompt | llm
    response = chain.invoke({"context": context, "question": state["question"]})
    return {"answer": response.content}

# ---------------------------------------------------------------------------
# 4. BUILD THE GRAPH
# StateGraph(RAGState) tells LangGraph what shape the state dict has.
# add_edge draws a fixed arrow between two nodes.
# ---------------------------------------------------------------------------
builder = StateGraph(RAGState)
builder.add_node("retrieve", retrieve_node)
builder.add_node("generate", generate_node)

builder.add_edge(START, "retrieve")       # graph always starts at retrieve
builder.add_edge("retrieve", "generate")  # then always goes to generate
builder.add_edge("generate", END)         # then finishes

graph = builder.compile()

# ---------------------------------------------------------------------------
# 5. RUN IT
# ---------------------------------------------------------------------------
result = graph.invoke({"question": "What is our refund policy?"})
print(result["answer"])
```

**Why this isn't "agentic" yet:** there is no branching, no decision, no loop. It's a chain with
extra ceremony. Level 2 fixes that.

---

## LEVEL 2 — Adaptive Retrieval: "Should I even retrieve?" + Query Routing

**Enterprise problem it solves:** Not every query needs RAG. "Hi, how are you?" or "What did I
just ask you?" doesn't need a vector search — retrieving anyway wastes latency, money, and can
actually *hurt* answer quality (irrelevant context confuses the LLM). This is called **Adaptive
RAG** / **query routing**.

**How:** Add a **router node** at the start. Instead of a plain function, it uses the LLM with
**structured output** (a Pydantic schema) to classify the query, then a **conditional edge** sends
the state down a different path based on that classification.

```python
"""
LEVEL 2: Adaptive RAG — an LLM router decides whether to retrieve at all,
and if so, which single source to use (vectorstore vs a direct LLM answer).
NEW CONCEPTS: structured output for classification, conditional_edges (routing).
"""

from typing import TypedDict, List, Literal
from pydantic import BaseModel, Field
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

class RAGState(TypedDict):
    question: str
    route: str
    documents: List[Document]
    answer: str

# ---------------------------------------------------------------------------
# STRUCTURED OUTPUT ROUTER
# We define a Pydantic schema describing exactly what decision we want back.
# `.with_structured_output(Schema)` forces the LLM to return valid JSON matching
# this schema (uses function-calling / tool-calling under the hood) — this is
# the standard, don't-reinvent-it way to get reliable decisions out of an LLM.
# ---------------------------------------------------------------------------
class RouteDecision(BaseModel):
    """Decide how to handle the user's question."""
    route: Literal["vectorstore", "direct_answer"] = Field(
        description=(
            "'vectorstore' if the question needs our internal knowledge base "
            "(company policies, product docs, etc). "
            "'direct_answer' if it's small talk, a follow-up needing no new facts, "
            "or general knowledge the LLM already knows confidently."
        )
    )

router_llm = llm.with_structured_output(RouteDecision)

def route_node(state: RAGState) -> dict:
    """Classifies the query. This is a NODE, not a conditional edge itself —
    the node writes the decision to state; a separate function reads it to route."""
    decision = router_llm.invoke(
        f"Classify this user question: {state['question']}"
    )
    return {"route": decision.route}

# ---------------------------------------------------------------------------
# CONDITIONAL EDGE FUNCTION
# This function's job is ONLY to look at state and return the name of the
# next node. It does not mutate state.
# ---------------------------------------------------------------------------
def decide_next_step(state: RAGState) -> str:
    if state["route"] == "vectorstore":
        return "retrieve"
    return "direct_answer"

def retrieve_node(state: RAGState) -> dict:
    # ... your real Qdrant hybrid retriever call goes here ...
    docs = [Document(page_content="(pretend this is a retrieved chunk)")]
    return {"documents": docs}

def generate_from_docs_node(state: RAGState) -> dict:
    context = "\n\n".join(d.page_content for d in state["documents"])
    resp = llm.invoke(f"Context:\n{context}\n\nQuestion: {state['question']}")
    return {"answer": resp.content}

def direct_answer_node(state: RAGState) -> dict:
    """No retrieval needed — answer straight from the LLM."""
    resp = llm.invoke(state["question"])
    return {"answer": resp.content}

# ---------------------------------------------------------------------------
# BUILD GRAPH WITH BRANCHING
# add_conditional_edges(source_node, routing_function, {label: destination})
# ---------------------------------------------------------------------------
builder = StateGraph(RAGState)
builder.add_node("route", route_node)
builder.add_node("retrieve", retrieve_node)
builder.add_node("generate_from_docs", generate_from_docs_node)
builder.add_node("direct_answer", direct_answer_node)

builder.add_edge(START, "route")
builder.add_conditional_edges(
    "route",              # after this node runs...
    decide_next_step,     # ...call this function to decide where to go...
    {                      # ...and map its string return value to a node name
        "retrieve": "retrieve",
        "direct_answer": "direct_answer",
    },
)
builder.add_edge("retrieve", "generate_from_docs")
builder.add_edge("generate_from_docs", END)
builder.add_edge("direct_answer", END)

graph = builder.compile()

print(graph.invoke({"question": "hey, how's it going?"})["answer"])
print(graph.invoke({"question": "what's our enterprise refund policy?"})["answer"])
```

**Key idea to internalize:** a *node* changes state, a *conditional edge function* only reads
state and returns a routing label. Keep them separate — this is the pattern for every decision
point in agentic RAG.

---

## LEVEL 3 — Self-Correcting RAG: Grading, Query Rewriting, and Retry Loops (Corrective RAG / Self-RAG)

**Enterprise problem it solves:** Even with great hybrid search + reranking, sometimes the top-k
chunks are just not relevant to the actual question (wrong document set, ambiguous query, bad
metadata filter). A naive system generates an answer anyway → **hallucination risk**. Enterprise
RAG needs a **quality gate**: grade the retrieved docs, and if they're bad, **rewrite the query and
retry** (this is the core idea behind **CRAG – Corrective RAG** and **Self-RAG**), with a **max
retry count** so it can't loop forever.

This is also where LangGraph's **cycles** (loops) become essential — something a plain LangChain
`Runnable` chain cannot express cleanly.

```python
"""
LEVEL 3: Corrective RAG (CRAG) style self-correction loop.
NEW CONCEPTS: grading node, query rewriting node, a LOOP (cycle) in the graph,
a retry counter to guarantee termination, and a groundedness/hallucination check
before returning the final answer.
"""

from typing import TypedDict, List, Literal
from pydantic import BaseModel, Field
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

class RAGState(TypedDict):
    question: str
    original_question: str   # keep the original around for the final answer/citations
    documents: List[Document]
    answer: str
    retry_count: int         # SAFETY: prevents infinite loops
    is_grounded: bool

# ---------------------------------------------------------------------------
# GRADER: for each doc, ask an LLM "is this relevant to the question?"
# In production you'd batch this / use a cheap+fast model, not gpt-4o.
# This is the "self-reflection" step from Self-RAG / CRAG papers.
# ---------------------------------------------------------------------------
class GradeDocuments(BaseModel):
    """Binary relevance score for a retrieved document."""
    is_relevant: bool = Field(description="True if the document is relevant to the question")

grader_llm = llm.with_structured_output(GradeDocuments)

def retrieve_node(state: RAGState) -> dict:
    # Plug in your real Qdrant hybrid+MMR+rerank retriever here.
    docs = [Document(page_content="some retrieved chunk about pricing")]
    return {"documents": docs}

def grade_documents_node(state: RAGState) -> dict:
    """Filters out irrelevant docs. If NONE survive, downstream routing will
    trigger a query rewrite + retry."""
    good_docs = []
    for doc in state["documents"]:
        grade = grader_llm.invoke(
            f"Question: {state['question']}\nDocument: {doc.page_content}\n"
            f"Is this document relevant to answering the question?"
        )
        if grade.is_relevant:
            good_docs.append(doc)
    return {"documents": good_docs}

def decide_after_grading(state: RAGState) -> str:
    """Conditional edge: if we have relevant docs -> generate.
    If not, and we haven't exceeded retries -> rewrite the query and try again.
    If we've exhausted retries -> fall back gracefully instead of looping forever."""
    if len(state["documents"]) > 0:
        return "generate"
    if state["retry_count"] >= 2:      # SAFETY VALVE — max 2 retries
        return "give_up_gracefully"
    return "rewrite_query"

def rewrite_query_node(state: RAGState) -> dict:
    """Uses the LLM to reformulate the query for better retrieval — e.g.
    expanding acronyms, fixing ambiguity, adding synonyms. This is the same
    idea as your 'query enrichment' step, but triggered conditionally instead
    of always running."""
    resp = llm.invoke(
        f"The following search query returned no relevant results: '{state['question']}'. "
        f"Rewrite it to be clearer and more specific for a semantic search engine. "
        f"Return ONLY the rewritten query."
    )
    return {
        "question": resp.content,
        "retry_count": state["retry_count"] + 1,
    }

def give_up_gracefully_node(state: RAGState) -> dict:
    """Enterprise systems must never silently hallucinate — if retrieval keeps
    failing, say so honestly instead of guessing."""
    return {"answer": "I couldn't find reliable information to answer this confidently. "
                       "Could you rephrase, or should I escalate this to a human?"}

def generate_node(state: RAGState) -> dict:
    context = "\n\n".join(d.page_content for d in state["documents"])
    resp = llm.invoke(f"Context:\n{context}\n\nQuestion: {state['original_question']}")
    return {"answer": resp.content}

# ---------------------------------------------------------------------------
# HALLUCINATION / GROUNDEDNESS CHECK (Self-RAG style)
# After generating, verify the answer is actually supported by the docs.
# If not grounded, we loop back to generate again (or you could re-retrieve).
# ---------------------------------------------------------------------------
class GroundednessGrade(BaseModel):
    is_grounded: bool = Field(description="True if the answer is fully supported by the given documents")

groundedness_llm = llm.with_structured_output(GroundednessGrade)

def check_groundedness_node(state: RAGState) -> dict:
    context = "\n\n".join(d.page_content for d in state["documents"])
    grade = groundedness_llm.invoke(
        f"Documents:\n{context}\n\nAnswer:\n{state['answer']}\n\n"
        f"Is the answer fully supported by the documents (no invented facts)?"
    )
    return {"is_grounded": grade.is_grounded}

def decide_after_groundedness(state: RAGState) -> str:
    if state["is_grounded"] or state["retry_count"] >= 2:
        return "end"          # accept the answer (or we've retried enough — ship it with a caveat)
    return "generate"          # regenerate from the same docs with stricter instructions

# ---------------------------------------------------------------------------
# BUILD THE GRAPH — note the CYCLE: rewrite_query -> retrieve -> grade -> (loop)
# ---------------------------------------------------------------------------
builder = StateGraph(RAGState)
builder.add_node("retrieve", retrieve_node)
builder.add_node("grade_documents", grade_documents_node)
builder.add_node("rewrite_query", rewrite_query_node)
builder.add_node("generate", generate_node)
builder.add_node("check_groundedness", check_groundedness_node)
builder.add_node("give_up_gracefully", give_up_gracefully_node)

builder.add_edge(START, "retrieve")
builder.add_edge("retrieve", "grade_documents")
builder.add_conditional_edges("grade_documents", decide_after_grading, {
    "generate": "generate",
    "rewrite_query": "rewrite_query",
    "give_up_gracefully": "give_up_gracefully",
})
builder.add_edge("rewrite_query", "retrieve")   # <-- THE LOOP: retry retrieval with the new query
builder.add_edge("generate", "check_groundedness")
builder.add_conditional_edges("check_groundedness", decide_after_groundedness, {
    "end": END,
    "generate": "generate",
})
builder.add_edge("give_up_gracefully", END)

graph = builder.compile()

result = graph.invoke({
    "question": "what is our refund policy for enterprise plans?",
    "original_question": "what is our refund policy for enterprise plans?",
    "documents": [],
    "retry_count": 0,
    "is_grounded": False,
    "answer": "",
})
print(result["answer"])
```

**This is the "safety net" pattern.** Every enterprise agentic RAG system needs: (1) a relevance
gate, (2) a bounded retry loop, (3) a groundedness/hallucination gate, (4) a graceful fallback.

---

## LEVEL 4 — Multi-Source Retrieval & Tool-Calling Agent Routing

**Enterprise problem it solves:** Real enterprises don't have one knowledge base. You might need:
Qdrant (product docs), a SQL database (order/customer data), a live web search (competitor info),
and a Confluence/Notion connector (internal wiki). The agent must **pick the right source(s)**, and
sometimes **multiple sources in parallel**.

There are two standard LangGraph patterns for this — **use both, don't reinvent them**:

1. **Tool-calling agent** (`create_react_agent` from `langgraph.prebuilt`) — wrap each source as a
   `@tool`, let the LLM decide which tool(s) to call, in what order, how many times. Best when the
   number/choice of sources is genuinely dynamic per-query.
2. **Explicit `Send` fan-out** — when you already know you want to query ALL sources in parallel
   every time (e.g., always search vector DB + SQL together, merge results) and want deterministic
   parallelism rather than LLM-decided tool calls.

### 4a. Tool-calling agent over multiple retrievers (recommended default)

```python
"""
LEVEL 4a: Multi-source RAG using LangGraph's prebuilt ReAct-style tool agent.
NEW CONCEPTS: wrapping retrievers as `@tool`s, `create_retriever_tool` helper,
`create_react_agent` (a pre-built LangGraph graph — don't hand-roll the ReAct
loop yourself, LangGraph already ships it), and letting the LLM choose tools.
"""

from langchain.tools.retriever import create_retriever_tool
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import InMemorySaver

client = QdrantClient(url="http://localhost:6333")

# ---------------------------------------------------------------------------
# SOURCE 1: Product docs (Qdrant) — your existing hybrid+rerank retriever,
# wrapped as a LangChain "retriever tool". create_retriever_tool is a
# LIBRARY FUNCTION — we don't write our own tool-wrapping logic.
# ---------------------------------------------------------------------------
product_docs_store = QdrantVectorStore(client=client, collection_name="product_docs", embedding=None)
product_docs_tool = create_retriever_tool(
    product_docs_store.as_retriever(search_kwargs={"k": 5}),
    name="search_product_docs",
    description="Search internal product documentation, features, and how-to guides.",
)

# ---------------------------------------------------------------------------
# SOURCE 2: Billing/policy docs (a different Qdrant collection, different
# metadata filters — this is where your metadata-filtering knowledge plugs in)
# ---------------------------------------------------------------------------
billing_docs_store = QdrantVectorStore(client=client, collection_name="billing_policies", embedding=None)
billing_docs_tool = create_retriever_tool(
    billing_docs_store.as_retriever(search_kwargs={"k": 5, "filter": {"must": [{"key": "dept", "match": {"value": "billing"}}]}}),
    name="search_billing_policies",
    description="Search billing, pricing, and refund policy documents.",
)

# ---------------------------------------------------------------------------
# SOURCE 3: Live structured data — a normal Python tool, not a retriever.
# Agentic RAG isn't limited to vector search; "retrieval" can be an API/SQL call.
# ---------------------------------------------------------------------------
@tool
def get_customer_order_status(customer_id: str) -> str:
    """Look up a customer's live order status from the orders database."""
    # In production: parameterized SQL query against your OLTP/warehouse.
    return f"Order for {customer_id}: shipped, arriving in 2 days."

# ---------------------------------------------------------------------------
# SOURCE 4: Web search fallback for things not in internal knowledge.
# ---------------------------------------------------------------------------
from langchain_community.tools.tavily_search import TavilySearchResults
web_search_tool = TavilySearchResults(max_results=3)

tools = [product_docs_tool, billing_docs_tool, get_customer_order_status, web_search_tool]

# ---------------------------------------------------------------------------
# BUILD THE AGENT
# create_react_agent builds an entire LangGraph StateGraph for you:
#   agent_node (LLM decides which tool(s) to call, or answers) <-> tools_node
# looping until the LLM stops calling tools. This IS the "agentic" core.
# checkpointer = InMemorySaver() gives it conversational memory across turns
# (swap for PostgresSaver in production for durability across restarts).
# ---------------------------------------------------------------------------
llm = ChatOpenAI(model="gpt-4o", temperature=0)
agent = create_react_agent(
    model=llm,
    tools=tools,
    checkpointer=InMemorySaver(),
    prompt=(
        "You are an enterprise support assistant. Decide which tool(s) you need "
        "to answer the user. Use search_billing_policies for pricing/refunds, "
        "search_product_docs for feature questions, get_customer_order_status for "
        "order-specific questions, and web_search only if internal sources don't cover it. "
        "Cite which source each fact came from."
    ),
)

# `thread_id` scopes memory to a conversation — same pattern as a chat session id.
config = {"configurable": {"thread_id": "user-123-session-1"}}
response = agent.invoke(
    {"messages": [{"role": "user", "content": "What's your refund policy, and what's the status of order #556?"}]},
    config=config,
)
print(response["messages"][-1].content)
```

**Why `create_react_agent` instead of hand-rolling the loop:** LangGraph ships a battle-tested
tool-calling loop (parallel tool calls, error handling on bad tool args, streaming support) — you
plug in tools and a model, you don't rebuild the agent loop node-by-node.

### 4b. Deterministic parallel fan-out with `Send` (query ALL sources every time)

```python
"""
LEVEL 4b: When you want to ALWAYS query multiple sources in parallel and merge
results (rather than letting the LLM choose), use LangGraph's `Send` primitive.
NEW CONCEPT: Send() for dynamic parallel fan-out / fan-in (map-reduce pattern).
"""

from typing import TypedDict, List, Annotated
import operator
from langchain_core.documents import Document
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

class FanOutState(TypedDict):
    question: str
    # `Annotated[..., operator.add]` tells LangGraph HOW to merge updates coming
    # back from parallel branches: concatenate the lists instead of overwriting.
    documents: Annotated[List[Document], operator.add]
    answer: str

SOURCES = ["product_docs", "billing_policies", "web_search"]

def dispatch_to_sources(state: FanOutState):
    """This is a special routing function used with add_conditional_edges that
    returns a LIST of Send objects — one per source — causing LangGraph to run
    `search_one_source` once PER SOURCE, in parallel, each with its own input."""
    return [Send("search_one_source", {"question": state["question"], "source": s}) for s in SOURCES]

def search_one_source(state: dict) -> dict:
    """Runs once per source (in parallel). Each call is isolated."""
    source, question = state["source"], state["question"]
    # Route to the real retriever for that source (your Qdrant collections, web search, etc.)
    docs = [Document(page_content=f"result from {source} for '{question}'", metadata={"source": source})]
    return {"documents": docs}  # gets merged via operator.add into the shared state

def merge_and_generate(state: FanOutState) -> dict:
    """Fan-in: all parallel branches have completed and their `documents` lists
    have already been merged by LangGraph before this node runs."""
    context = "\n\n".join(f"[{d.metadata['source']}] {d.page_content}" for d in state["documents"])
    return {"answer": f"(generated from merged context)\n{context}"}

builder = StateGraph(FanOutState)
builder.add_node("search_one_source", search_one_source)
builder.add_node("merge_and_generate", merge_and_generate)

# Conditional edge from START that fans out via Send() instead of picking one path
builder.add_conditional_edges(START, dispatch_to_sources, ["search_one_source"])
builder.add_edge("search_one_source", "merge_and_generate")
builder.add_edge("merge_and_generate", END)

graph = builder.compile()
result = graph.invoke({"question": "what's included in the enterprise plan?", "documents": []})
print(result["answer"])
```

**When to use 4a vs 4b:** 4a (LLM tool-calling) when source selection genuinely varies per query
and you want the model reasoning about *which* tools to call and in what sequence. 4b (`Send`
fan-out) when you always want breadth (query everything, merge, let reranking sort out quality) —
cheaper to reason about, fully deterministic, easier to test and audit.

---

## LEVEL 5 — Full Enterprise Agentic RAG Graph (putting it all together)

This combines everything above into one production-shaped graph, plus the remaining enterprise
concerns: **query decomposition**, **human-in-the-loop for low-confidence answers**, **durable
persistence (Postgres checkpointer)**, **streaming**, and **subgraphs** for modularity.

```python
"""
LEVEL 5: Enterprise-shaped Agentic RAG graph.
Combines: adaptive routing (L2) + self-correction loop (L3) + multi-source
tool-calling (L4) + NEW: query decomposition, human-in-the-loop escalation,
durable persistence, and streaming.
"""

from typing import TypedDict, List, Literal, Optional
from pydantic import BaseModel, Field
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.postgres import PostgresSaver  # durable, production checkpointer

llm = ChatOpenAI(model="gpt-4o", temperature=0)

class EnterpriseRAGState(TypedDict):
    question: str
    sub_questions: List[str]      # decomposed sub-queries for complex questions
    route: str
    documents: List[Document]
    answer: str
    confidence: float
    retry_count: int
    needs_human_review: bool

# ---------------------------------------------------------------------------
# STEP A — QUERY DECOMPOSITION
# Complex enterprise questions ("compare our enterprise vs pro plan pricing
# AND tell me if my current plan supports SSO") often need to be split into
# independently-retrievable sub-questions. This is standard multi-hop RAG.
# ---------------------------------------------------------------------------
class Decomposition(BaseModel):
    sub_questions: List[str] = Field(description="1-4 atomic sub-questions needed to fully answer the user")

def decompose_node(state: EnterpriseRAGState) -> dict:
    decomposer = llm.with_structured_output(Decomposition)
    result = decomposer.invoke(
        f"Break this question into atomic sub-questions if it has multiple parts. "
        f"If it's already simple, return it as a single sub-question.\nQuestion: {state['question']}"
    )
    return {"sub_questions": result.sub_questions}

# ---------------------------------------------------------------------------
# STEP B — RETRIEVE PER SUB-QUESTION (reuses your Level 3/4 subgraph logic in
# practice; simplified here to a single call for readability)
# ---------------------------------------------------------------------------
def retrieve_all_node(state: EnterpriseRAGState) -> dict:
    all_docs = []
    for sq in state["sub_questions"]:
        # plug in Level 4's multi-source retrieval / Level 3's grading loop here
        all_docs.append(Document(page_content=f"evidence for: {sq}"))
    return {"documents": all_docs}

# ---------------------------------------------------------------------------
# STEP C — GENERATE + SELF-ASSESS CONFIDENCE
# The model reports its own confidence; low confidence triggers human review.
# (In production, back this up with the Level 3 groundedness grader too —
# don't rely on self-reported confidence alone.)
# ---------------------------------------------------------------------------
class AnswerWithConfidence(BaseModel):
    answer: str
    confidence: float = Field(description="0.0 to 1.0 — how confident you are this answer is fully correct and grounded")

def generate_node(state: EnterpriseRAGState) -> dict:
    context = "\n\n".join(d.page_content for d in state["documents"])
    structured_llm = llm.with_structured_output(AnswerWithConfidence)
    result = structured_llm.invoke(f"Context:\n{context}\n\nQuestion: {state['question']}")
    return {"answer": result.answer, "confidence": result.confidence}

def decide_after_generate(state: EnterpriseRAGState) -> str:
    """Route low-confidence answers to a human reviewer instead of sending
    them straight to the customer — a standard enterprise guardrail."""
    if state["confidence"] < 0.6:
        return "human_review"
    return "end"

# ---------------------------------------------------------------------------
# STEP D — HUMAN-IN-THE-LOOP
# `interrupt()` PAUSES graph execution and surfaces a payload to your
# application/UI. Whoever calls the graph next with a `Command(resume=...)`
# continues execution from exactly this point. This requires a checkpointer
# (state must be persisted while we wait for the human).
# ---------------------------------------------------------------------------
def human_review_node(state: EnterpriseRAGState) -> dict:
    human_decision = interrupt({
        "question": state["question"],
        "draft_answer": state["answer"],
        "confidence": state["confidence"],
        "instruction": "Approve, edit, or reject this draft answer before it's sent to the customer.",
    })
    # `human_decision` is whatever value your app passes back via Command(resume=...)
    return {"answer": human_decision.get("final_answer", state["answer"])}

# ---------------------------------------------------------------------------
# BUILD GRAPH
# ---------------------------------------------------------------------------
builder = StateGraph(EnterpriseRAGState)
builder.add_node("decompose", decompose_node)
builder.add_node("retrieve_all", retrieve_all_node)
builder.add_node("generate", generate_node)
builder.add_node("human_review", human_review_node)

builder.add_edge(START, "decompose")
builder.add_edge("decompose", "retrieve_all")
builder.add_edge("retrieve_all", "generate")
builder.add_conditional_edges("generate", decide_after_generate, {
    "human_review": "human_review",
    "end": END,
})
builder.add_edge("human_review", END)

# ---------------------------------------------------------------------------
# DURABLE PERSISTENCE — swap InMemorySaver for PostgresSaver in production so
# that interrupted (awaiting-human) conversations survive a server restart.
# ---------------------------------------------------------------------------
with PostgresSaver.from_conn_string("postgresql://user:pass@localhost:5432/langgraph") as checkpointer:
    checkpointer.setup()  # creates tables on first run
    graph = builder.compile(checkpointer=checkpointer)

    config = {"configurable": {"thread_id": "conversation-42"}}

    # STREAMING — enterprise UIs need token/step streaming, not a blocking call.
    # stream_mode="updates" yields each node's output as it completes.
    for chunk in graph.stream(
        {"question": "Compare enterprise vs pro pricing and does pro support SSO?",
         "sub_questions": [], "documents": [], "answer": "", "confidence": 0.0,
         "retry_count": 0, "needs_human_review": False},
        config=config,
        stream_mode="updates",
    ):
        print(chunk)

    # If the graph paused at human_review (interrupt), resume it like this once
    # a human has responded in your UI:
    # graph.invoke(Command(resume={"final_answer": "edited final answer text"}), config=config)
```

### Enterprise topics this Level-5 graph (plus the earlier levels) demonstrates

| Topic | Where it's handled |
|---|---|
| **Deciding when to retrieve** | Level 2 router (`route_node` + conditional edge) |
| **Routing to the right source** | Level 2 (single-choice) and Level 4 (multi-source) |
| **Multi-source retrieval** | Level 4a (tool-calling) and 4b (`Send` fan-out) |
| **Query decomposition (multi-hop)** | Level 5 `decompose_node` |
| **Self-correction / retry** | Level 3 grading + rewrite loop |
| **Hallucination/groundedness checks** | Level 3 `check_groundedness_node` |
| **Confidence-based escalation** | Level 5 `decide_after_generate` |
| **Human-in-the-loop** | Level 5 `interrupt()` / `Command(resume=...)` |
| **Durable memory / multi-turn** | `checkpointer` (`InMemorySaver` → `PostgresSaver`) + `thread_id` |
| **Streaming** | `graph.stream(..., stream_mode="updates")` |
| **Modularity at scale** | Compile a sub-graph (e.g., all of Level 3) and add it as a single node in a bigger graph — LangGraph graphs are composable as nodes |
| **Cost control** | Use a small/cheap model for routing & grading nodes, a strong model only for final generation (mixed model routing, shown implicitly by using `gpt-4o-mini` vs `gpt-4o` above) |
| **Observability / auditability** | Every node transition + state snapshot is inspectable via the checkpointer, and traces natively to LangSmith if you set `LANGCHAIN_TRACING_V2=true` |
| **Guardrails against prompt injection** | Treat retrieved/tool content as untrusted data, never as instructions — validate tool outputs, restrict which tools an agent can call per user role, and keep system prompts separate from retrieved context |
| **Metadata filtering, hybrid search, rerank, caching** | Plug into the `retrieve_*` nodes — you already built these, they just live inside a node now |

---

## Common Beginner Mistakes

1. **Confusing a node function with a conditional-edge function.** A node returns *state updates*
   (a dict). A conditional-edge function returns a *string label* (or list of `Send`s). Mixing
   these up is the #1 source of confusing bugs.
2. **Forgetting to only return the keys you changed.** Returning the entire state dict from every
   node works but is wasteful and risks accidentally overwriting fields (especially with list
   fields that should be merged, not replaced — remember `Annotated[list, operator.add]`).
3. **No retry limit on loops.** Any cycle (`rewrite_query -> retrieve -> grade -> rewrite_query...`)
   without a counter/guard can loop forever (or until you hit a token/cost limit the hard way).
4. **Always retrieving.** Skipping the "should I even retrieve" router and calling the vector DB
   on every single message, including "thanks!" or "what did you just say?" — wastes latency and
   money, and can *reduce* answer quality by injecting irrelevant context.
5. **Trusting retrieved/tool content as instructions.** If a retrieved document or tool output
   contains text like "ignore previous instructions", a poorly designed agent may follow it
   (prompt injection). Always treat retrieved content as *data*, never as *commands*.
6. **Using one giant LLM call to do routing + grading + generation.** This makes debugging and
   cost control impossible. Split responsibilities into small nodes with small, cheap, structured
   outputs (classification/boolean), and reserve the expensive model call for final generation.
7. **No groundedness check before shipping the answer.** Self-reported "confidence" from the LLM
   is a weak signal on its own — pair it with an actual grounding check against retrieved docs.
8. **Not using a checkpointer / `thread_id`, then wondering why multi-turn memory doesn't work,**
   or why `interrupt()` fails ("interrupt" requires a checkpointer to persist paused state).
9. **Hand-rolling a ReAct tool loop instead of using `create_react_agent`.** It already handles
   parallel tool calls, malformed tool-call args, and streaming — reinventing it introduces bugs
   LangGraph has already solved.
10. **Ignoring `recursion_limit`.** LangGraph graphs have a max step count (default 25); a
    misbehaving loop will hit `GraphRecursionError` — a beginner will be confused by this instead
    of realizing their conditional edge never routes to `END`.
11. **Forgetting `Send` targets need to be declared** in `add_conditional_edges(..., ["node_name"])`
    (the third argument) — omitting it, or mismatching the node name string, silently breaks fan-out.
12. **Blocking `.invoke()` everywhere in a chat UI** instead of `.stream()`, producing poor perceived
    latency for users even though the actual pipeline is fast.

---

## Interview Questions & Answers (Intermediate → Advanced)

**Q1. What's the fundamental architectural difference between a LangChain `Runnable` chain and a LangGraph `StateGraph` for RAG?**
A chain is a directed acyclic sequence (`A | B | C`) with no branching or cycles — execution order
is fixed at definition time. A `StateGraph` is an explicit graph with a shared mutable state, real
conditional branching, and cycles, so the execution path can change at runtime based on
intermediate results (grading, routing, retries). Agentic behavior fundamentally requires cycles
and conditional control flow, which chains can't express natively.

**Q2. How do you prevent infinite loops in a self-correcting RAG graph?**
Carry an explicit counter (e.g. `retry_count`) in state, increment it in the retry node, and check
it in the conditional edge before deciding to loop again vs. falling back gracefully. Additionally,
LangGraph enforces a global `recursion_limit` (configurable, default 25) as a hard backstop.

**Q3. When would you choose a tool-calling ReAct agent (`create_react_agent`) over an explicit hand-built graph for multi-source retrieval?**
Use the ReAct agent when source selection is genuinely dynamic and benefits from LLM reasoning
about *which* tools to call, in what order, and whether to call more than one (e.g., open-ended
support queries). Use an explicit graph (with conditional edges or `Send` fan-out) when the
retrieval strategy is deterministic/known in advance, when you need tighter latency/cost control,
or when you need the flow to be fully auditable/testable step-by-step for compliance reasons.

**Q4. Explain how `Send` differs from a normal conditional edge.**
A normal conditional edge picks exactly one next node from a fixed set. `Send(node_name, payload)`
lets you dynamically fan out to N parallel invocations of the *same* node with *different* inputs
— the number of parallel branches is decided at runtime (e.g., "one branch per retrieved source" or
"one branch per sub-question"), enabling map-reduce-style parallelism.

**Q5. How does LangGraph merge state updates coming back from parallel branches, and why does that matter?**
By default, a key returned by two branches would conflict/overwrite unless you specify a reducer.
`Annotated[List[X], operator.add]` tells LangGraph to concatenate list updates instead of
overwriting them — essential for fan-in patterns like merging documents from parallel
multi-source retrieval.

**Q6. Why is a checkpointer required for `interrupt()`-based human-in-the-loop workflows?**
`interrupt()` pauses graph execution mid-run and returns control to the caller; the graph's exact
state at that point must be durably persisted so that, potentially much later (after a human
responds through a UI), execution can resume from that exact node with that exact state. Without a
checkpointer, there is nothing to resume from.

**Q7. How would you control cost in a production agentic RAG system with many LLM-based decision points (routing, grading, groundedness checks, generation)?**
Use small/cheap models (or even non-LLM classifiers/embeddings similarity) for high-frequency,
low-complexity decisions like routing and binary relevance grading, and reserve larger models for
final answer generation. Cache repeated classifications and retrieval results. Batch document
grading calls where possible. Track per-node token cost via tracing (LangSmith) to find the
biggest cost centers.

**Q8. What's the risk of using an LLM's self-reported confidence score as your only quality gate, and how do you mitigate it?**
LLMs are often miscalibrated — they can be confidently wrong, especially when hallucinating fluent
but ungrounded text. Mitigate by combining self-reported confidence with an independent
groundedness/entailment check (does the answer's claims actually appear in the retrieved context?),
and by routing low-confidence *or* ungrounded answers to human review rather than either signal
alone.

**Q9. How do you defend an agentic RAG system against prompt injection via retrieved documents or tool outputs?**
Treat all retrieved/tool content strictly as data, never as instructions — never let system-level
behavior be altered by content that arrived through a tool result or a document. Use structured
output schemas so the model's "decisions" are constrained to a fixed set of valid values instead of
free-form text it could be tricked into producing. Restrict which tools/sources an agent can access
per user role (least privilege), and consider a dedicated content-scanning step or guardrail model
between retrieval and generation for high-risk domains.

**Q10. In a multi-hop question requiring query decomposition, how do you keep track of which retrieved evidence supports which sub-question, for citation purposes?**
Store documents with metadata tagging their originating sub-question/source (as shown with
`metadata={"source": ...}` in the fan-out example), and carry that metadata through generation so
the final answer (or a structured output with a `citations` field) can map claims back to specific
sub-questions and source documents — critical for enterprise auditability.

**Q11. Why might you compile a whole sub-graph (e.g., the full CRAG self-correction loop) and use it as a single node inside a larger graph, rather than flattening everything into one big graph?**
Modularity and testability: a compiled sub-graph behaves like any other runnable node from the
parent graph's perspective, so you can unit-test the self-correction loop in isolation, version it
independently, and reuse it across multiple parent graphs (e.g., a customer-support graph and an
internal-ops graph both reusing the same "reliable retrieval" sub-graph) without duplicating logic.

**Q12. How would you evaluate an agentic RAG system differently from a naive RAG pipeline?**
Beyond standard RAG metrics (context relevance, faithfulness/groundedness, answer relevance — which
you already evaluate), you also need to evaluate the *agent's decisions themselves*: routing
accuracy (did it correctly decide to retrieve / pick the right source?), retry efficiency (how many
loop iterations on average, cost per query), tool-selection correctness, and end-to-end task success
rate across multi-step trajectories — not just the final answer in isolation. Trace-level evaluation
(e.g., via LangSmith) of the full node path, not just input/output pairs, becomes necessary.

**Q13. What happens if a conditional edge function returns a string that isn't in the mapping dict passed to `add_conditional_edges`?**
It raises a runtime error — LangGraph can't resolve the next node. This is a common source of
production incidents when an LLM-based router (structured output notwithstanding) returns an
unexpected label; always constrain router outputs with an enum/`Literal` type via structured output
rather than free-text parsing, and consider a default/fallback branch.

**Q14. How do you handle partial failures in a multi-source `Send` fan-out (e.g., one source's API times out)?**
Wrap each per-source node body in try/except and return a partial/empty result with an
error flag in metadata rather than letting the exception propagate and kill the whole graph run;
downstream grading/merging logic can then simply treat that source as having contributed no
documents, and you can surface a degraded-but-successful response instead of a hard failure.

**Q15. Why keep `original_question` separate from `question` in state during a rewrite loop?**
The `question` field gets mutated by the query-rewriter node to improve retrieval, but the
*intent* the user actually asked about (and expects the final answer phrased around) is the
original wording. Generating the final answer against `original_question` while retrieving against
the rewritten version keeps the response user-facing and natural instead of echoing back an
internally-reformulated query.

---

## Suggested Learning Path From Here

1. Rebuild Level 1–3 yourself against your real Qdrant collections (swap the placeholder
   `Document` objects for your actual hybrid+MMR+rerank retriever calls).
2. Add LangSmith tracing (`LANGCHAIN_TRACING_V2=true`) and *look at the actual graph execution
   trace* for a few queries — seeing routing/retry decisions visually is the fastest way to build
   intuition.
3. Swap `InMemorySaver` for `PostgresSaver` and test that an `interrupt()`-paused conversation
   survives a process restart.
4. Combine Level 4b (`Send` fan-out across sources) with Level 3 (grading loop) so each source's
   results are graded independently before merging — closer to true enterprise-grade CRAG.
5. Load-test the compiled graph and profile per-node latency/cost to find where a cheaper model or
   caching would help most.
