# Part 7: LangChain Fundamentals (LLMs, Prompts, Chains)

> **Continue from:** `00-THE-COMPLETE-GUIDE.md`
>
> **In this part:** you learn what LangChain actually is, why we picked it, and how to use it for real.

---

## 7.1 What LangChain Actually Is

Strip away the marketing and LangChain is just three things:

1. **A standard interface to talk to any LLM.** Same code works for OpenAI, Google, Anthropic, local models.
2. **A way to compose LLM calls into pipelines** (chains).
3. **A library of integrations** — vector DBs, document loaders, text splitters, etc.

That's it. It's not magic. It's plumbing. And that's exactly what you want — boring, reliable plumbing you can swap.

## 7.2 Why We Use It (vs Calling OpenAI Directly)

**Direct OpenAI SDK:**
```python
from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello"}],
)
print(response.choices[0].message.content)
```

**LangChain:**
```python
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(model="gpt-4o")
response = llm.invoke("Hello")
print(response.content)
```

Same number of lines. But now to switch to Claude:
```python
# Just change this one line
from langchain_anthropic import ChatAnthropic
llm = ChatAnthropic(model="claude-sonnet-4-5")
# Everything else stays the same
```

To switch to Gemini:
```python
from langchain_google_genai import ChatGoogleGenerativeAI
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")
```

That's the value. The day you want to swap providers, the day your boss says "we're using Claude now" or "we need to go local for compliance," you change one line. With the direct SDK, you rewrite your whole codebase.

## 7.3 The 5 Concepts You Need to Know

| Concept | What it is | Why you care |
|---------|-----------|--------------|
| **Chat model** | The LLM itself | The thing that answers |
| **Prompt template** | A function from variables to a prompt | So you can build prompts dynamically |
| **Output parser** | A function from LLM response to typed data | So you get back Python objects, not strings |
| **Chain** | A pipeline of steps | Compose multiple LLM calls + logic |
| **Tool** | A function the LLM can call | Lets the LLM "do" things, not just talk |

Let's see each one.

## 7.4 The Chat Model (the LLM)

### The LLM Factory (the abstraction layer)

```python
# app/services/llm/llm_factory.py
"""
LLM factory — the single place we create LLM instances.

This is the key to vendor-agnostic code.
All other code in the app imports from here, not from langchain_openai etc.
The day we want to switch providers, we change ONE file.
"""

from functools import lru_cache

from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel

from app.config import settings


@lru_cache
def get_llm(temperature: float | None = None, model: str | None = None) -> BaseChatModel:
    """
    Factory function that returns the right LLM based on settings.

    Args:
        temperature: Override the default temperature (0-1, default = settings)
        model: Override the default model name (default = settings)

    Returns:
        A LangChain chat model instance (the same interface regardless of provider)

    The `@lru_cache` means we reuse the same LLM instance across calls.
    This is good for performance — instantiating these isn't free.
    """
    # Use overrides if provided, else fall back to settings
    temp = temperature if temperature is not None else settings.llm_temperature
    model_name = model or settings.llm_model

    # Match on the provider setting and return the right class
    if settings.llm_provider == "openai":
        return ChatOpenAI(
            model=model_name,
            temperature=temp,
            max_tokens=settings.llm_max_tokens,
            api_key=settings.llm_api_key,
        )
    elif settings.llm_provider == "anthropic":
        return ChatAnthropic(
            model=model_name,
            temperature=temp,
            max_tokens=settings.llm_max_tokens,
            api_key=settings.llm_api_key,
        )
    elif settings.llm_provider == "google":
        return ChatGoogleGenerativeAI(
            model=model_name,
            temperature=temp,
            max_output_tokens=settings.llm_max_tokens,
            google_api_key=settings.llm_api_key,
        )
    elif settings.llm_provider == "openrouter":
        # OpenRouter gives you access to many models through one API.
        # We use the OpenAI-compatible endpoint.
        return ChatOpenAI(
            model=model_name,
            temperature=temp,
            max_tokens=settings.llm_max_tokens,
            api_key=settings.llm_api_key,
            base_url="https://openrouter.ai/api/v1",
        )
    else:
        raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")
```

**The key idea:** nowhere else in your code do you write `ChatOpenAI(...)` or `ChatGoogleGenerativeAI(...)`. You always go through `get_llm()`. This is your abstraction layer.

### Using the LLM

```python
# Anywhere in your code:
from app.services.llm.llm_factory import get_llm

# Get the LLM (cached, fast)
llm = get_llm()

# Call it
response = llm.invoke("What is the capital of France?")
print(response.content)  # "Paris"

# Call it with a system message
from langchain_core.messages import HumanMessage, SystemMessage

messages = [
    SystemMessage(content="You are a helpful assistant. Be concise."),
    HumanMessage(content="What is the capital of France?"),
]
response = llm.invoke(messages)
print(response.content)  # "Paris."
```

**That's it for basic usage.** Three lines to talk to any LLM.

## 7.5 Prompt Templates (dynamic prompts)

Hardcoding prompts is fine for one-offs. For an app, you want reusable, type-safe prompts.

```python
# app/services/llm/prompts.py
"""
Prompt templates.

A prompt template is a function from a dict of variables to a prompt string.
Example:
    template = PromptTemplate.from_template("Tell me a {adjective} joke about {topic}")
    template.format(adjective="funny", topic="cats")
    # → "Tell me a funny joke about cats"
"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder


# =========================================
# A simple chat prompt
# =========================================

# From a list of messages
simple_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant that answers questions about {topic}."),
    ("human", "{question}"),
])

# Use it
messages = simple_prompt.format_messages(topic="Python", question="What are decorators?")
# Send `messages` to the LLM


# =========================================
# A prompt with chat history (for multi-turn conversations)
# =========================================

# MessagesPlaceholder is where the conversation history will be injected
# at runtime. The LLM sees the whole conversation.
chat_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant. Answer based on the context and history."),
    # This is where the retrieved documents go (RAG)
    ("system", "Context:\n{context}"),
    # This is where the chat history goes
    MessagesPlaceholder(variable_name="chat_history"),
    # The current user question
    ("human", "{question}"),
])
```

**Why the placeholder pattern:** chat history and retrieved context are dynamic — you don't bake them into the template, you inject them at request time. The placeholder tells LangChain "fill this in at runtime."

## 7.6 Output Parsers (LLM → Python objects)

LLMs return strings. But you want Python objects — a list, a JSON, a Pydantic model. Output parsers do the conversion.

```python
# app/services/llm/parsers.py
"""
Output parsers — turn LLM text output into typed Python objects.
"""

from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_core.pydantic_v1 import BaseModel, Field  # Note: LangChain uses v1

from app.services.llm.llm_factory import get_llm


# =========================================
# The simplest parser: just give me a string
# =========================================

# `StrOutputParser` extracts the string from the LLM response.
# Most LLMs return an AIMessage object; this just gives you the .content.

# Example use:
#   chain = prompt | llm | StrOutputParser()
#   result = chain.invoke({"topic": "cats", "question": "Are they cute?"})
#   result  # → "Yes, cats are very cute." (a plain str)


# =========================================
# JSON parser: get back a dict
# =========================================

# Sometimes you want structured output. Tell the LLM what you want as JSON.

json_parser = JsonOutputParser()

# You can include format instructions in your prompt:
#   from langchain_core.output_parsers import JsonOutputParser
#   parser.get_format_instructions()
#   # → "Return a JSON object like: {{ \"key\": \"value\" }}" (sort of)


# =========================================
# Pydantic parser: get back a typed object
# =========================================

# The most powerful: define a schema, get back a typed instance.

class Joke(BaseModel):
    """A joke with setup and punchline."""
    setup: str = Field(description="The setup of the joke")
    punchline: str = Field(description="The punchline of the joke")
    rating: int = Field(description="How funny, 1-10")


# To use it:
#   parser = PydanticOutputParser(pydantic_object=Joke)
#   prompt = PromptTemplate.from_template(
#       "Tell me a joke about {topic}.\n{format_instructions}"
#   )
#   chain = prompt.partial(format_instructions=parser.get_format_instructions()) | llm | parser
#   joke = chain.invoke({"topic": "Python"})
#   joke.setup     # → "Why did the Python dev..."
#   joke.punchline # → "...prefer snakes over Java?"
#   joke.rating    # → 7
```

**Pro tip:** modern LLMs (GPT-4o, Claude 3.5+, Gemini 2.5) all support **structured output natively** — you pass a JSON schema and they return JSON. LangChain's `with_structured_output()` is the cleanest way:

```python
from pydantic import BaseModel, Field
from langchain_core.pydantic_v1 import BaseModel as LangChainBaseModel  # Ugh, naming

# Wait, the better way in 2026:
from typing import Literal

class Sentiment(BaseModel):
    """The sentiment of a text."""
    label: Literal["positive", "negative", "neutral"]
    confidence: float = Field(ge=0, le=1)

# Get a structured LLM
structured_llm = llm.with_structured_output(Sentiment)

# Call it
result = structured_llm.invoke("I love this product, it's amazing!")
result.label       # → "positive"
result.confidence  # → 0.95
```

This is **massively** more reliable than parsing strings. Use it whenever you need structured data.

## 7.7 Chains (the LCEL way)

LangChain Expression Language (LCEL) is the modern way to build chains. It's just `|` (pipe) for chaining operations.

```python
# app/services/llm/chains.py
"""
Chains — the heart of LangChain.

LCEL syntax: `chain = component1 | component2 | component3`
Each component has the same interface: takes input, returns output.
This means you can compose them like Unix pipes.
"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.services.llm.llm_factory import get_llm
from app.services.llm.prompts import simple_prompt


# =========================================
# A simple chain
# =========================================

# A chain is just: prompt | llm | parser
# Data flows: variables → formatted prompt → LLM → parsed output

# Step 1: define the prompt
prompt = ChatPromptTemplate.from_template(
    "Explain {concept} in one sentence, as if I'm 5."
)

# Step 2: get the LLM
llm = get_llm()

# Step 3: define the output parser
output_parser = StrOutputParser()

# Step 4: chain them
chain = prompt | llm | output_parser

# Step 5: use it
result = chain.invoke({"concept": "recursion"})
print(result)  # "Recursion is when a function calls itself, like a loop but fancier."
```

**The pipe is the magic.** Each step has `invoke(input) → output`. You can chain any components that match the interface:
- A prompt's output is a `PromptValue`
- An LLM's input is a `PromptValue`, output is an `AIMessage`
- A parser's input is an `AIMessage`, output is whatever you want
- So: `prompt | llm | parser` works.

**The result is also a Runnable**, so you can:
- `chain.invoke(input)` — single call
- `chain.batch([input1, input2, input3])` — batch (parallel)
- `chain.stream(input)` — stream (for real-time UI)
- `chain.ainvoke(input)` — async version

This is the API you use everywhere.

### A more complex chain: with RAG

```python
# A RAG chain (we'll build this fully in Part 8)
from langchain_core.runnables import RunnablePassthrough, RunnableParallel

# This chain:
# 1. Takes a question
# 2. Retrieves relevant context (in parallel with formatting the question)
# 3. Combines them into a prompt
# 4. Calls the LLM
# 5. Parses the output

def get_retriever():
    """Returns the vector store retriever (we'll build this in Part 8)."""
    from app.services.llm.vector_store import get_vector_store
    return get_vector_store().as_retriever(search_kwargs={"k": 5})


# Build the chain
rag_prompt = ChatPromptTemplate.from_messages([
    ("system", """Answer the question based only on the following context.
If the context doesn't contain the answer, say "I don't know."

Context: {context}"""),
    ("human", "{question}"),
])

retriever = get_retriever()

# This is the "branch" that gets run in parallel
setup_and_retrieval = RunnableParallel(
    context=retriever,  # this gets the docs
    question=RunnablePassthrough(),  # this passes the question through
)

# The full chain
rag_chain = setup_and_retrieval | rag_prompt | llm | StrOutputParser()

# Use it
answer = rag_chain.invoke("What is the user's policy on refunds?")
```

**Read that code carefully.** It's the entire RAG pattern in 5 lines. This is why we use LangChain.

## 7.8 Tools (giving the LLM abilities)

The LLM can only output text. But what if you want it to:
- Look up a user's order
- Send an email
- Query your database
- Call an API

That's what tools are. You give the LLM a list of "tools" (Python functions) and it can choose to call them.

```python
# app/services/llm/tools.py
"""
Tools — functions the LLM can decide to call.

This is the foundation of "agents" (Part 12).
For now, just learn what a tool looks like.
"""

from langchain_core.tools import tool


@tool
def get_weather(city: str) -> str:
    """
    Get the current weather for a city.

    Args:
        city: The name of the city, e.g. "San Francisco"

    Returns:
        A string describing the weather
    """
    # In reality, you'd call a weather API here
    # For demo, we return a fake response
    return f"It's always sunny in {city}!"


@tool
def search_documents(query: str, user_id: str) -> str:
    """
    Search the user's documents for relevant information.

    Args:
        query: What to search for
        user_id: Whose documents to search

    Returns:
        A string with the most relevant passages
    """
    # In a real app, this would query your vector DB
    from app.services.llm.vector_store import get_vector_store
    vector_store = get_vector_store()
    docs = vector_store.similarity_search(query, k=3, filter={"user_id": user_id})
    return "\n\n".join([doc.page_content for doc in docs])


# Bind tools to the LLM
llm_with_tools = get_llm().bind_tools([get_weather, search_documents])

# Now when you invoke it, the LLM can decide to call a tool
response = llm_with_tools.invoke("What's the weather in Tokyo and also search my docs for 'expense policy'")

# The response may contain tool_calls
print(response.tool_calls)
# [{'name': 'get_weather', 'args': {'city': 'Tokyo'}, 'id': '...'},
#  {'name': 'search_documents', 'args': {'query': 'expense policy', 'user_id': '...'}, 'id': '...'}]
```

**The docstring is the API.** The LLM reads your docstring to understand what the tool does and what arguments it needs. Write good docstrings. They're more important than the code.

**Type hints matter too.** LangChain uses them to tell the LLM what types to pass.

## 7.9 The Message System (how to structure conversation)

The LLM doesn't have memory. You build conversation by sending a list of messages every time.

```python
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

# A conversation history
messages = [
    SystemMessage(content="You are a helpful assistant."),
    HumanMessage(content="Hi, I'm Alice."),
    AIMessage(content="Hello Alice! How can I help you today?"),
    HumanMessage(content="What's 2+2?"),
    AIMessage(content="4."),
    HumanMessage(content="And what's 3+3?"),  # New question
]

# Send it all — the LLM sees the full context
response = llm.invoke(messages)
print(response.content)  # "6."
```

For a real app, you'd:
1. Store these messages in your database
2. Load the recent ones (windowed memory) when the user asks a question
3. Send them all to the LLM
4. Save the new response to the DB

We'll build exactly this in the chat endpoint later.

## 7.10 The Streaming Pattern (for real-time UI)

LLMs are slow. Gemini Flash takes ~1 second, GPT-4o can take 10+ seconds. You don't want your UI to sit there spinning.

Streaming = getting tokens as they're generated.

```python
# Sync streaming (for testing)
for chunk in llm.stream("Tell me a long story about a dragon"):
    print(chunk.content, end="", flush=True)
print()  # Newline at the end

# Async streaming (for FastAPI)
async for chunk in llm.astream("Tell me a long story"):
    print(chunk.content, end="", flush=True)

# Streaming a full chain
chain = prompt | llm | StrOutputParser()
async for chunk in chain.astream({"concept": "Python"}):
    print(chunk.content, end="", flush=True)
```

**In FastAPI, you expose this as Server-Sent Events:**

```python
from fastapi.responses import StreamingResponse

@router.post("/chat/stream")
async def stream_chat(question: str):
    async def generate():
        async for chunk in chain.astream({"question": question}):
            # SSE format: "data: <content>\n\n"
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")
```

The frontend reads this with the EventSource API or a library and updates the UI as tokens arrive. That's how ChatGPT's UI works.

## 7.11 Token Usage and Cost (don't go bankrupt)

Every LLM call costs money. You need to track it.

```python
# Get token usage from a response
response = llm.invoke("What is the capital of France?")
print(response.usage_metadata)
# {'input_tokens': 14, 'output_tokens': 5, 'total_tokens': 19}

# For a chain, you can enable usage tracking
from langchain_core.callbacks import get_openai_callback  # works for any provider

# For any LLM, you can use a callback:
from langchain_core.callbacks import BaseCallbackHandler

class TokenCountingHandler(BaseCallbackHandler):
    def __init__(self):
        self.total_tokens = 0
    def on_llm_end(self, response, **kwargs):
        if response.llm_output and "token_usage" in response.llm_output:
            self.total_tokens += response.llm_output["token_usage"].get("total_tokens", 0)

# Or simpler: just check response.usage_metadata
# In production, you'd log this to a metrics service
```

**The "bill shock" prevention rules:**
1. Always set `max_tokens` (prevents runaway output)
2. Always set timeouts (prevents runaway waits)
3. Log every call with token counts
4. Set per-user rate limits
5. Cap context window size (don't send 100K tokens by accident)

## 7.12 Error Handling (LLMs fail in weird ways)

```python
from tenacity import retry, stop_after_attempt, wait_exponential
from langchain_core.exceptions import LangChainException

# Common LLM errors:
# - RateLimitError: too many requests
# - APIConnectionError: network blip
# - TimeoutError: LLM took too long
# - OutputParserException: LLM didn't follow the schema
# - ContextWindowExceededError: prompt too long

# Retry with exponential backoff
@retry(
    stop=stop_after_attempt(3),  # try 3 times
    wait=wait_exponential(multiplier=1, min=4, max=10),  # wait 4s, 8s, 10s
)
async def safe_llm_call(prompt: str) -> str:
    try:
        response = await llm.ainvoke(prompt)
        return response.content
    except Exception as e:
        print(f"LLM call failed: {e}")
        raise

# Or use LangChain's built-in handling
llm_with_retries = llm.with_retry(
    stop_after_attempt=3,
    wait_exponential_jitter=True,
)
```

**The pro move:** every LLM call in production should have a timeout, a retry policy, and a fallback. The LLM API will go down. You need to handle it.

## 7.13 Quick Recap

In this part you learned:
- Why we use LangChain (vendor abstraction)
- The factory pattern for LLM creation
- Prompts, output parsers, chains (LCEL)
- Tools, messages, streaming
- Token counting and error handling

In Part 8 we put it all together for the most important AI pattern: RAG.

---
