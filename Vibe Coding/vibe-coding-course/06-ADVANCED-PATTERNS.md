# Part 12: Advanced Patterns (Multi-Agent, Memory, Streaming, Caching)

> **Continue from:** `05-VIBE-CODING-WORKFLOW.md`
>
> **In this part:** the patterns that take you from "I have an LLM call" to "I have a real AI product."

---

## 12.1 The Mental Model: An AI App is Just a Loop

Strip away all the libraries and every AI app is the same:

```
User input → Process → LLM call → Process → Output
                            ↓
                      External tools
                      (DBs, APIs, etc.)
                            ↓
                          Memory
```

Everything in this part is variations on this loop. Let's go through each major pattern.

## 12.2 Pattern: Conversational Memory

LLMs are stateless — they don't remember past messages. You have to feed them the history.

### Option 1: Full history (simple, expensive)

```python
# Send all messages every time
messages = [
    SystemMessage(content="You are a helpful assistant."),
    HumanMessage(content="Hi, I'm Alice."),       # Turn 1
    AIMessage(content="Hello Alice!"),
    HumanMessage(content="What's 2+2?"),          # Turn 2
    AIMessage(content="4."),
    HumanMessage(content="And what's 3+3?"),      # Turn 3 (current)
]
response = llm.invoke(messages)
```

**Problem:** Conversation gets long, costs add up, eventually exceeds context window.

### Option 2: Sliding window (simple, more efficient)

Keep the last N messages:

```python
def get_windowed_history(messages: list[BaseMessage], window_size: int = 10) -> list[BaseMessage]:
    """Keep the system message + last N messages."""
    system = [m for m in messages if isinstance(m, SystemMessage)]
    non_system = [m for m in messages if not isinstance(m, SystemMessage)]
    return system + non_system[-window_size:]
```

**Problem:** Lose early context.

### Option 3: Summarization (smart, more code)

When the conversation gets long, summarize the old parts:

```python
from langchain_core.messages import SystemMessage

def get_summarized_history(messages: list[BaseMessage], llm, max_messages: int = 10) -> list[BaseMessage]:
    """
    If we have more than max_messages, summarize the older ones.
    """
    if len(messages) <= max_messages:
        return messages

    # Keep the system message
    system = [m for m in messages if isinstance(m, SystemMessage)][0]
    # Keep the recent messages
    recent = messages[-max_messages:]
    # Summarize the middle
    to_summarize = messages[1:-max_messages]  # exclude system

    summary_prompt = ChatPromptTemplate.from_messages([
        ("system", "Summarize this conversation concisely, preserving key facts and decisions."),
        ("human", "{conversation}"),
    ])
    summary_chain = summary_prompt | llm | StrOutputParser()

    conversation_text = "\n".join([
        f"{m.__class__.__name__}: {m.content}" for m in to_summarize
    ])
    summary = summary_chain.invoke({"conversation": conversation_text})

    # Return: system + summary message + recent
    return [
        system,
        SystemMessage(content=f"Previous conversation summary: {summary}"),
        *recent,
    ]
```

### Option 4: Vector memory (advanced)

Store all past messages in a vector DB. When a new message comes in, retrieve the most relevant past ones.

```python
# In production, use a dedicated conversation memory store
# LangChain has built-in options:
# - ConversationBufferMemory (full history)
# - ConversationBufferWindowMemory (window)
# - ConversationSummaryMemory (summarized)
# - ConversationSummaryBufferMemory (hybrid)
# - VectorStoreRetrieverMemory (vector-based)
# - Zep (a dedicated memory service)
```

**The pro move:** use a windowed approach by default, summarize when needed, and only go vector-based if you have evidence users need long-term recall.

## 12.3 Pattern: Streaming Responses (the ChatGPT feel)

You already saw this in Part 7, but let's do it right with FastAPI and the frontend.

### The Server

```python
# app/api/v1/chat.py
import json
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, SystemMessage

@router.post("/stream")
async def stream_chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Stream a chat response as Server-Sent Events.

    Each event has the format:
        data: {"type": "token", "content": "Hello"}
        data: {"type": "sources", "sources": [...]}
        data: {"type": "done", "message_id": "..."}
        data: [DONE]
    """
    async def event_generator():
        # 1. Search for relevant context
        chunks = search_user_documents(
            user_id=str(current_user.id),
            query=request.message,
            k=5,
        )
        context = format_chunks(chunks)

        # 2. Build messages
        messages = [
            SystemMessage(content=f"Answer based on:\n{context}"),
            HumanMessage(content=request.message),
        ]

        # 3. Stream the response
        full_response = ""
        async for chunk in llm.astream(messages):
            token = chunk.content
            if token:
                full_response += token
                # SSE format
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

        # 4. Send sources
        sources_data = {
            "type": "sources",
            "sources": [
                {
                    "filename": c["metadata"].get("filename"),
                    "page": c["metadata"].get("page_number"),
                }
                for c in chunks
            ],
        }
        yield f"data: {json.dumps(sources_data)}\n\n"

        # 5. Save the messages (after streaming completes)
        # ... save to DB

        # 6. Send done event
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
```

### The Frontend (vanilla JS, no framework)

```javascript
// Connect to the streaming endpoint
async function sendMessage(message) {
  const token = localStorage.getItem("access_token");
  const response = await fetch("/api/v1/chat/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ message }),
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n\n");
    buffer = lines.pop(); // Keep the incomplete line in the buffer

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const data = line.slice(6);
      if (data === "[DONE]") {
        console.log("Stream complete");
        continue;
      }
      const event = JSON.parse(data);
      if (event.type === "token") {
        // Append the token to the UI
        appendToken(event.content);
      } else if (event.type === "sources") {
        // Show the source citations
        showSources(event.sources);
      }
    }
  }
}
```

### The Frontend (React, with hooks)

```jsx
import { useState } from "react";

function useStreamingChat() {
  const [messages, setMessages] = useState([]);
  const [isStreaming, setIsStreaming] = useState(false);

  const sendMessage = async (userMessage) => {
    setIsStreaming(true);
    // Add the user message
    setMessages((m) => [...m, { role: "user", content: userMessage }]);
    // Add a placeholder for the assistant message
    setMessages((m) => [...m, { role: "assistant", content: "" }]);

    const token = localStorage.getItem("access_token");
    const response = await fetch("/api/v1/chat/stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ message: userMessage }),
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const data = line.slice(6);
        if (data === "[DONE]") continue;
        const event = JSON.parse(data);
        if (event.type === "token") {
          // Append the token to the last message
          setMessages((m) => {
            const updated = [...m];
            const last = updated[updated.length - 1];
            last.content += event.content;
            return updated;
          });
        }
      }
    }
    setIsStreaming(false);
  };

  return { messages, isStreaming, sendMessage };
}
```

## 12.4 Pattern: Caching LLM Responses (save money, go faster)

LLM calls are slow and expensive. Cache common queries.

```python
# app/core/cache.py
"""
Redis-based cache for LLM responses.

When to cache:
- The same question gets asked many times
- The answer doesn't need to be fresh (FAQ-style queries)
- The cost of a cache miss is acceptable

When NOT to cache:
- Every response is unique
- The answer must be real-time (e.g., stock prices)
- The user expects fresh data
"""

import hashlib
import json

import redis.asyncio as redis
from langchain_core.messages import BaseMessage

from app.config import settings


class LLMCache:
    """Cache LLM responses in Redis."""

    def __init__(self):
        self.redis: redis.Redis | None = None
        self.ttl = 3600  # Cache for 1 hour

    async def init(self):
        """Connect to Redis. Call this on app startup."""
        self.redis = redis.from_url(settings.redis_url)

    def _make_key(self, messages: list[BaseMessage], model: str) -> str:
        """Create a cache key from the messages and model."""
        # Hash the messages for a stable key
        content = json.dumps(
            [{"role": m.type, "content": m.content} for m in messages],
            sort_keys=True,
        )
        hash_val = hashlib.sha256(f"{model}:{content}".encode()).hexdigest()
        return f"llm_cache:{model}:{hash_val}"

    async def get(self, messages: list[BaseMessage], model: str) -> str | None:
        """Get a cached response, or None if not cached."""
        if not self.redis:
            return None
        key = self._make_key(messages, model)
        return await self.redis.get(key)

    async def set(self, messages: list[BaseMessage], model: str, response: str) -> None:
        """Cache a response."""
        if not self.redis:
            return
        key = self._make_key(messages, model)
        await self.redis.setex(key, self.ttl, response)


# Global cache instance
cache = LLMCache()
```

Use it in your LLM calls:

```python
async def get_llm_response_cached(messages: list[BaseMessage], model: str) -> str:
    # Check cache
    cached = await cache.get(messages, model)
    if cached:
        return cached

    # Not cached, call the LLM
    llm = get_llm(model=model)
    response = await llm.ainvoke(messages)

    # Cache the result
    await cache.set(messages, model, response.content)

    return response.content
```

**The pro move:** cache only the deterministic stuff. Don't cache when temperature > 0 (you want different answers).

**Semantic caching (the smart version):** cache based on meaning, not exact match. "What's your refund policy?" and "How do I get a refund?" should hit the same cache.

```python
# Use langchain's GPTCache, or a semantic cache library
# pip install gptcache
# Or build your own:
# 1. Get the embedding of the user's question
# 2. Look up the most similar cached question (cosine similarity)
# 3. If similarity > 0.95, return the cached answer
# 4. Otherwise, call the LLM and cache the new answer
```

## 12.5 Pattern: Multi-Agent Systems (the "wow" feature)

A multi-agent system is multiple LLM "agents" that collaborate. Each has a role.

**When to use:**
- The task is complex and benefits from division of labor
- Different agents can specialize (researcher, writer, critic)
- You want quality from debate (writer writes, critic reviews, writer revises)

**When NOT to use:**
- The task is simple (one LLM call works fine)
- The cost of 3-5 LLM calls is too much
- You can do it with a better prompt

### Example: A research agent + writer agent

```python
# app/services/llm/agents.py
"""
Multi-agent system: Researcher + Writer + Critic.

Flow:
1. Researcher agent: searches the docs, gathers relevant info
2. Writer agent: drafts an answer based on the research
3. Critic agent: reviews the draft, suggests improvements
4. Writer agent: revises based on feedback
5. Return the final answer
"""

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.services.llm.llm_factory import get_llm
from app.services.llm.vector_store import search_user_documents


async def research_agent(user_id: str, question: str) -> str:
    """
    Step 1: Search the user's documents and synthesize findings.

    Returns a summary of what's relevant in the user's docs.
    """
    chunks = search_user_documents(user_id, question, k=10)
    context = "\n\n".join([c["content"] for c in chunks])

    llm = get_llm()
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a research assistant. Your job is to find and synthesize "
            "relevant information from the provided context to answer a question. "
            "Be thorough. Note all relevant facts, including their sources. "
            "If the context doesn't contain the answer, say so clearly."
        )),
        ("human", (
            f"Context:\n{context}\n\n"
            f"Question: {question}\n\n"
            f"Provide a detailed research summary."
        )),
    ])
    chain = prompt | llm | StrOutputParser()
    return await chain.ainvoke({})


async def writer_agent(research: str, question: str) -> str:
    """
    Step 2: Write a clear answer based on the research.
    """
    llm = get_llm()
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a skilled writer. Your job is to write a clear, "
            "well-structured answer based on the provided research. "
            "Use citations like [1], [2] that reference the research notes. "
            "Be concise but complete. Use markdown formatting."
        )),
        ("human", (
            f"Research notes:\n{research}\n\n"
            f"Question: {question}\n\n"
            f"Write the answer."
        )),
    ])
    chain = prompt | llm | StrOutputParser()
    return await chain.ainvoke({})


async def critic_agent(draft: str, question: str) -> str:
    """
    Step 3: Review the draft and suggest improvements.
    """
    llm = get_llm()
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a critical editor. Your job is to review a draft answer "
            "and identify any issues: factual errors, unsupported claims, "
            "unclear writing, missing context. Be specific. "
            "Output either: 'APPROVED' if the draft is good, or "
            "a list of specific issues to fix."
        )),
        ("human", (
            f"Question: {question}\n\n"
            f"Draft:\n{draft}\n\n"
            f"Review:"
        )),
    ])
    chain = prompt | StrOutputParser() | llm
    return await chain.ainvoke({})


async def multi_agent_answer(user_id: str, question: str) -> dict:
    """
    The full multi-agent pipeline.
    """
    # 1. Research
    research = await research_agent(user_id, question)

    # 2. Write
    draft = await writer_agent(research, question)

    # 3. Critique (loop until approved or max iterations)
    for iteration in range(3):  # max 3 revision loops
        critique = await critic_agent(draft, question)
        if "APPROVED" in critique.upper():
            break
        # Revise based on critique
        llm = get_llm()
        revise_prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a writer. Revise the draft based on the feedback."),
            ("human", f"Draft:\n{draft}\n\nFeedback:\n{critique}\n\nRevised:"),
        ])
        draft = await (revise_prompt | llm | StrOutputParser()).ainvoke({})

    return {
        "answer": draft,
        "iterations": iteration + 1,
        "research": research,
    }
```

**Cost warning:** this calls the LLM 3-5 times. If your LLM is $0.01 per call, that's $0.03-0.05 per user query. Add it up: 10,000 queries = $300-500. For most apps, you don't need this. But for high-value use cases (legal, medical), it can be worth it.

**The pro move:** use a smaller, cheaper model for the critic and a bigger, better model for the writer. Mix and match.

## 12.6 Pattern: Function Calling / Tool Use (the foundation of agents)

We covered this in Part 7, but let's go deeper. Function calling is how LLMs "do" things, not just "say" things.

```python
# A real example: an agent that can search docs AND save notes
from langchain_core.tools import tool

@tool
def search_documents(query: str, user_id: str) -> str:
    """Search the user's uploaded documents for information."""
    chunks = search_user_documents(user_id, query, k=3)
    return "\n\n".join([c["content"] for c in chunks])


@tool
def save_note(user_id: str, content: str, title: str) -> str:
    """Save a note for the user."""
    # In a real app, save to DB
    return f"Note saved: {title}"


@tool
def get_current_date() -> str:
    """Get today's date."""
    from datetime import datetime
    return datetime.now().isoformat()


# Create a tool-using agent
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

tools = [search_documents, save_note, get_current_date]
llm = get_llm().bind_tools(tools)  # Tell the LLM about the tools

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant with access to tools. Use them when needed."),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

agent = create_tool_calling_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

# Use it
result = agent_executor.invoke({
    "input": "Search my docs for the refund policy and save a note about it",
    "chat_history": [],
})
```

The agent will:
1. Decide to call `search_documents`
2. Get the search results
3. Decide to call `save_note` with the relevant info
4. Return a final response

This is the foundation of "agentic" AI. The LLM becomes a decision-maker, not just a text generator.

## 12.7 Pattern: The LangGraph Way (stateful agents)

For complex, multi-step workflows, LangGraph is the modern answer. It models the AI app as a graph of states and transitions.

```python
# app/services/llm/graph.py
"""
A LangGraph workflow for a research agent.

This is more powerful than chains because:
- It can have cycles (loops, retries)
- It maintains state across steps
- It can branch based on conditions
- It's observable (you can see every transition)
"""

from typing import TypedDict  # For type-safe state

from langgraph.graph import END, StateGraph

from app.services.llm.agents import critic_agent, research_agent, writer_agent


# =========================================
# The state (what gets passed between nodes)
# =========================================

class AgentState(TypedDict):
    """The state of our research agent."""
    user_id: str
    question: str
    research: str
    draft: str
    critique: str
    iteration: int
    max_iterations: int
    final_answer: str


# =========================================
# The nodes (the functions that do work)
# =========================================

async def research_node(state: AgentState) -> dict:
    """Step 1: Research."""
    research = await research_agent(state["user_id"], state["question"])
    return {"research": research}


async def write_node(state: AgentState) -> dict:
    """Step 2: Write the draft."""
    draft = await writer_agent(state["research"], state["question"])
    return {"draft": draft}


async def critique_node(state: AgentState) -> dict:
    """Step 3: Critique the draft."""
    critique = await critic_agent(state["draft"], state["question"])
    return {"critique": critique, "iteration": state["iteration"] + 1}


def should_continue(state: AgentState) -> str:
    """Decide whether to revise or finish."""
    if "APPROVED" in state["critique"].upper():
        return "end"
    if state["iteration"] >= state["max_iterations"]:
        return "end"
    return "revise"


async def finalize_node(state: AgentState) -> dict:
    """The final answer."""
    return {"final_answer": state["draft"]}


# =========================================
# The graph
# =========================================

workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("research", research_node)
workflow.add_node("write", write_node)
workflow.add_node("critique", critique_node)
workflow.add_node("finalize", finalize_node)

# Add edges (the flow)
workflow.set_entry_point("research")
workflow.add_edge("research", "write")
workflow.add_edge("write", "critique")

# Conditional edge: based on critique, either go back to write or finalize
workflow.add_conditional_edges(
    "critique",
    should_continue,
    {
        "revise": "write",  # go back to write
        "end": "finalize",   # finish
    },
)
workflow.add_edge("finalize", END)

# Compile
app_graph = workflow.compile()

# Use it
result = await app_graph.ainvoke({
    "user_id": "...",
    "question": "What is our refund policy?",
    "iteration": 0,
    "max_iterations": 3,
})
print(result["final_answer"])
```

**When to use LangGraph:**
- Complex multi-step workflows
- You need cycles (retry, refine)
- You want to visualize the flow
- You're building an "AI agent" in the truest sense

**When NOT to use:**
- Simple chains (use LCEL)
- Single LLM calls (just call the LLM)

## 12.8 Pattern: Async + Batching (for performance)

```python
# Use asyncio.gather to run multiple LLM calls in parallel
import asyncio

async def summarize_chunks(chunks: list[str]) -> list[str]:
    """Summarize multiple chunks in parallel."""
    llm = get_llm()
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Summarize the following text in one sentence."),
        ("human", "{text}"),
    ])
    chain = prompt | llm | StrOutputParser()

    # Run all in parallel
    summaries = await asyncio.gather(*[
        chain.ainvoke({"text": chunk}) for chunk in chunks
    ])
    return summaries


# Use abatch for built-in batching
async def batch_classify(texts: list[str]) -> list[str]:
    """Classify multiple texts in one call."""
    llm = get_llm()
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Classify the sentiment of the text as positive, negative, or neutral."),
        ("human", "{text}"),
    ])
    chain = prompt | llm | StrOutputParser()
    # abatch runs them in parallel
    return await chain.abatch([{"text": t} for t in texts])
```

## 12.9 Pattern: Observability (know what's happening)

You saw Langfuse in Part 9. Here's how to wire it into every LLM call:

```python
# app/services/llm/llm_factory.py
from langfuse.callback import CallbackHandler
from app.config import settings

# Initialize once
langfuse_handler = CallbackHandler(
    public_key=settings.langfuse_public_key,
    secret_key=settings.langfuse_secret_key,
    host=settings.langfuse_host,
) if settings.langfuse_public_key else None


def get_llm_with_observation(name: str, user_id: str | None = None, **kwargs):
    """Get an LLM configured for observation."""
    llm = get_llm(**kwargs)
    if not langfuse_handler:
        return llm
    # Bind the handler via metadata
    llm.metadata = {
        "langfuse_session_id": name,
        "langfuse_user_id": user_id,
    }
    return llm


def get_callback_config(name: str, user_id: str | None = None) -> dict:
    """Get the config to pass to .invoke() / .ainvoke()."""
    if not langfuse_handler:
        return {}
    return {
        "callbacks": [langfuse_handler],
        "metadata": {
            "langfuse_session_id": name,
            "langfuse_user_id": user_id,
        },
    }
```

Use it:

```python
config = get_callback_config("chat_request", user_id=str(user.id))
response = await llm.ainvoke(messages, config=config)
```

Now every call is traced in Langfuse with token counts, latency, prompt, response, and the retrieved context.

## 12.10 Pattern: Cost Control (don't get a $10,000 bill)

```python
# app/core/cost_tracking.py
"""
Track LLM costs. Most providers charge per 1K tokens.
"""

from dataclasses import dataclass
from datetime import datetime

from app.config import settings


# Pricing per 1K tokens (input, output) as of late 2025
# Update these when pricing changes
PRICING = {
    "gemini-2.5-flash": (0.000075, 0.0003),  # very cheap
    "gemini-2.5-pro": (0.00125, 0.005),
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4o": (0.0025, 0.01),
    "claude-sonnet-4-5": (0.003, 0.015),
    "deepseek-chat": (0.00014, 0.00028),  # very cheap
}


@dataclass
class CostRecord:
    user_id: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    timestamp: datetime


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate the cost of a single LLM call."""
    if model not in PRICING:
        return 0.0
    input_price, output_price = PRICING[model]
    cost = (input_tokens / 1000) * input_price + (output_tokens / 1000) * output_price
    return cost


async def log_llm_cost(user_id: str, model: str, input_tokens: int, output_tokens: int) -> None:
    """Log the cost. In production, save to a metrics service."""
    cost = calculate_cost(model, input_tokens, output_tokens)
    from app.core.logging import logger
    logger.info(
        "llm_cost",
        user_id=user_id,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
    )
```

Add to the chat service:

```python
# After the LLM call
cost = calculate_cost(model_name, input_tokens, output_tokens)
# Save to DB, send to billing, etc.
```

**The rules:**

1. **Always set `max_tokens`.** This is your cost ceiling per call.
2. **Set per-user daily/monthly budgets.** If a user is going over, rate-limit them.
3. **Log every call.** You can't optimize what you don't measure.
4. **Use the cheapest model that works.** Start with Flash / mini, upgrade only if needed.
5. **Cache aggressively.** Same question, same answer, free.

## 12.11 Pattern: WebSockets (real-time, bidirectional)

For real-time chat, WebSockets are better than SSE for bidirectional comm:

```python
# app/api/v1/chat_ws.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["chat"])

@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # Receive a message
            data = await websocket.receive_json()
            message = data.get("message")

            # Stream the response
            async for chunk in chain.astream({"question": message}):
                await websocket.send_json({
                    "type": "token",
                    "content": chunk,
                })

            await websocket.send_json({"type": "done"})
    except WebSocketDisconnect:
        pass
```

The frontend:

```javascript
const ws = new WebSocket("ws://localhost:8000/api/v1/chat/ws");
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === "token") appendToken(data.content);
};
ws.send(JSON.stringify({ message: "Hello" }));
```

## 12.12 Quick Recap

You now have the advanced patterns:
- Conversational memory (windowed, summarized, vector)
- Streaming (SSE and WebSockets)
- Caching (Redis + semantic)
- Multi-agent systems (researcher + writer + critic)
- Tool use / function calling
- LangGraph for complex workflows
- Async + batching
- Observability with Langfuse
- Cost control
- WebSockets

In Part 13 we tie everything together in the capstone project: ship DocuMind AI end-to-end.

---
