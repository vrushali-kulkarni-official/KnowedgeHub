The two pieces of code you posted solve **two different problems**:

```python
@dataclass(frozen=True)
class RequestContext:
    user_id: str
    api_client: "ApiClient"
```

defines **what contextual information your application wants to carry during one agent/tool execution**.

And:

```python
ToolRuntime[RequestContext]
```

means **“give this tool access to the current runtime, and tell Python/type checkers that its `context` is a `RequestContext`.”**

LangChain's current Python API supports `ToolRuntime` specifically for accessing runtime information such as `context`, state, config, store, and the current tool-call ID. The runtime parameter is injected automatically and is hidden from the model's tool schema. ([LangChain Reference][1])

Let's build this from the ground up.

---

# 1. First: what is `@dataclass`?

Suppose you write normal Python like this:

```python
class RequestContext:
    def __init__(self, user_id, api_client):
        self.user_id = user_id
        self.api_client = api_client
```

You have to manually write the constructor.

Python's `dataclass` can generate that boilerplate for you.

```python
from dataclasses import dataclass

@dataclass
class RequestContext:
    user_id: str
    api_client: "ApiClient"
```

Python essentially gives you a constructor similar to:

```python
def __init__(self, user_id: str, api_client: "ApiClient"):
    self.user_id = user_id
    self.api_client = api_client
```

So now you can do:

```python
context = RequestContext(
    user_id="user_123",
    api_client=my_api_client,
)
```

You can think of a dataclass as:

> **A convenient Python container for related data.**

Python's documentation describes `@dataclass` as a way to automatically generate methods such as `__init__()` based on the fields you define. ([Python documentation][2])

---

# 2. What does `frozen=True` mean?

Now look at:

```python
@dataclass(frozen=True)
```

`frozen=True` basically means:

> **After the object is created, don't allow its fields to be reassigned.**

For example:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class RequestContext:
    user_id: str
```

You can create it:

```python
context = RequestContext(user_id="user_123")
```

You can read it:

```python
print(context.user_id)
```

But this is not allowed:

```python
context.user_id = "user_456"
```

Python raises a `FrozenInstanceError`. ([Python documentation][2])

---

# 3. Why would we want `frozen=True`?

This becomes particularly useful for **request/runtime context**.

Imagine your application receives:

```text
User → FastAPI → Agent → Tool
```

Suppose the request is for:

```text
user_id = "user_123"
```

You construct:

```python
RequestContext(
    user_id="user_123",
    api_client=api_client
)
```

You generally don't want some random tool halfway through execution to do:

```python
runtime.context.user_id = "admin"
```

That could be extremely dangerous.

Instead, the context represents:

> "These are the trusted values associated with this execution."

So freezing it makes the intent clearer:

```python
@dataclass(frozen=True)
class RequestContext:
    user_id: str
    api_client: "ApiClient"
```

It's basically saying:

> **Create this request context once and treat its fields as read-only during the run.**

There is one important nuance: `frozen=True` is **not deep immutability**. Python prevents reassignment of the dataclass fields, but objects stored inside those fields can still themselves be mutable.

For example:

```python
@dataclass(frozen=True)
class Context:
    settings: dict
```

This is still possible:

```python
context.settings["mode"] = "admin"
```

because you didn't replace the `settings` field itself; you modified the dictionary.

So think:

> `frozen=True` = **read-only fields**, not "everything inside is magically immutable."

---

# 4. Now let's understand `RequestContext`

Your code:

```python
@dataclass(frozen=True)
class RequestContext:
    user_id: str
    api_client: "ApiClient"
```

contains two pieces of information.

### `user_id`

```python
user_id: str
```

means:

```text
Who is making this request?
```

Example:

```python
"user_123"
```

### `api_client`

```python
api_client: "ApiClient"
```

means:

```text
What application/API client should this tool use?
```

For example, imagine you have:

```python
class ApiClient:
    async def get_user_profile(self, user_id: str):
        ...
```

You could place one configured instance into the context.

So:

```python
context = RequestContext(
    user_id="user_123",
    api_client=api_client
)
```

now carries both:

```text
user_id
   ↓
"user_123"

api_client
   ↓
configured API client object
```

This is extremely useful in enterprise AI systems because you often need to pass trusted application information into tools without asking the LLM to generate it.

---

# 5. Why `"ApiClient"` is in quotes

This part:

```python
api_client: "ApiClient"
```

may look strange.

You might normally write:

```python
api_client: ApiClient
```

The quotes are a **forward reference**.

They tell Python/type checking tools:

> "ApiClient is a type, but its definition may not be available at this exact point."

For example:

```python
@dataclass(frozen=True)
class RequestContext:
    user_id: str
    api_client: "ApiClient"


class ApiClient:
    ...
```

The quotes allow the annotation to refer to a class that is defined later or is otherwise not yet available when the class body is evaluated.

Depending on your Python version and annotation setup, you can also use:

```python
from __future__ import annotations
```

and then write:

```python
api_client: ApiClient
```

without quotes.

---

# 6. Now the important part: `ToolRuntime`

This:

```python
ToolRuntime
```

is a LangChain/LangGraph runtime object automatically provided to a tool while the tool is executing.

Current LangChain documentation says `ToolRuntime` can expose things such as:

```text
runtime.context
runtime.state
runtime.config
runtime.store
runtime.tool_call_id
runtime.stream_writer
runtime.tools
```

and the tool system automatically injects it when your tool has a parameter typed as `ToolRuntime`. ([LangChain Reference][1])

This is a very important concept.

---

# 7. Think of `ToolRuntime` as a tool's "backpack"

Imagine your tool is a worker.

The LLM says:

> "Please look up the user's profile."

LangChain executes your tool.

While executing it, LangChain can give the tool a backpack containing useful runtime information:

```text
                ToolRuntime
             ┌───────────────────┐
             │ context            │
             │ state              │
             │ config             │
             │ store              │
             │ tool_call_id       │
             │ stream_writer      │
             │ tools              │
             └───────────────────┘
```

Your tool can open the backpack and access what it needs.

For example:

```python
runtime.context
```

or:

```python
runtime.state
```

or:

```python
runtime.tool_call_id
```

---

# 8. But what is `ToolRuntime[RequestContext]`?

Now we reach the part that usually confuses beginners.

Look at:

```python
ToolRuntime[RequestContext]
```

This is **generic typing**.

It basically means:

> "`ToolRuntime`, where the runtime context is a `RequestContext`."

It does **not** mean:

```text
ToolRuntime = RequestContext
```

That's wrong.

Instead, think:

```text
ToolRuntime
│
├── context → RequestContext
├── state
├── config
├── store
├── tool_call_id
└── ...
```

So:

```python
ToolRuntime[RequestContext]
```

means:

```text
The runtime's .context property is expected to be a RequestContext.
```

That gives you nice type checking and IDE autocomplete.

---

# 9. Without the generic type

You could write:

```python
@tool
def get_user_info(runtime: ToolRuntime) -> str:
    ...
```

But your type checker doesn't know exactly what:

```python
runtime.context
```

contains.

It may effectively be some generic/unknown context type.

---

# 10. With `ToolRuntime[RequestContext]`

You write:

```python
@tool
def get_user_info(
    runtime: ToolRuntime[RequestContext],
) -> str:
    ...
```

Now Python tooling knows:

```text
runtime.context
        ↓
RequestContext
```

Therefore:

```python
runtime.context.user_id
```

is known to be valid.

And:

```python
runtime.context.api_client
```

is known to exist.

That is the main purpose of the `[RequestContext]`.

---

# 11. Very important: the LLM does NOT provide `runtime`

Suppose your tool is:

```python
@tool
def get_user_info(
    runtime: ToolRuntime[RequestContext],
) -> str:
    """Get information about the current user."""
    
    user_id = runtime.context.user_id

    return f"User ID is {user_id}"
```

You might wonder:

> "How does the LLM know what `runtime` is?"

It doesn't need to.

This is one of the important LangChain features.

The runtime parameter is **injected by the framework**, and it is hidden from the model's tool-call schema. ([Docs by LangChain][3])

So conceptually the model sees something like:

```text
get_user_info()
```

not:

```text
get_user_info(runtime=???)
```

The model doesn't have to invent:

```python
runtime = ...
```

LangChain supplies it.

---

# 12. Compare normal tool arguments with runtime arguments

This distinction is extremely important.

Imagine:

```python
@tool
def search_orders(
    order_status: str,
    runtime: ToolRuntime[RequestContext],
) -> str:
    ...
```

There are two fundamentally different types of parameters.

### Model-controlled parameter

```python
order_status: str
```

The LLM may generate:

```json
{
  "order_status": "pending"
}
```

### Framework-controlled parameter

```python
runtime: ToolRuntime[RequestContext]
```

The LLM does **not** generate this.

LangChain injects it.

So:

```text
LLM
 │
 │ chooses
 ▼
order_status = "pending"
 │
 ▼
LangChain
 │
 │ injects
 ▼
runtime = ToolRuntime(...)
 │
 ▼
your Python function
```

This separation is extremely useful for security.

---

# 13. Why this is better than asking the LLM for `user_id`

Imagine your tool instead looked like:

```python
@tool
def get_user_info(user_id: str) -> str:
    ...
```

The model might generate:

```json
{
    "user_id": "user_123"
}
```

That is a problem if `user_id` is supposed to represent the **authenticated user**.

Why?

Because now the model is participating in deciding the identity.

You really don't want:

```text
Authenticated user:
user_123

LLM:
"I'll call the tool using user_999."
```

Instead:

```python
@tool
def get_user_info(
    runtime: ToolRuntime[RequestContext],
) -> str:
    user_id = runtime.context.user_id
```

Now the application supplies:

```text
authenticated user
       ↓
RequestContext
       ↓
ToolRuntime
       ↓
runtime.context.user_id
```

The LLM doesn't get to choose it.

This is one reason runtime context is such a useful pattern for production agent systems.

---

# 14. Let's build your exact example

Let's pretend we have this client:

```python
class ApiClient:
    async def get_user_profile(self, user_id: str):
        ...
```

Then:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class RequestContext:
    user_id: str
    api_client: ApiClient
```

Now define a tool:

```python
from langchain.tools import tool, ToolRuntime


@tool
async def get_user_profile(
    runtime: ToolRuntime[RequestContext],
) -> str:
    """Get the profile of the authenticated user."""

    user_id = runtime.context.user_id
    api_client = runtime.context.api_client

    profile = await api_client.get_user_profile(user_id)

    return str(profile)
```

Let's look at this one piece at a time.

---

# 15. `runtime.context`

This:

```python
runtime.context
```

means:

> Give me the context associated with this current agent execution.

Because you wrote:

```python
ToolRuntime[RequestContext]
```

your IDE/type checker understands that:

```python
runtime.context
```

is:

```python
RequestContext
```

Therefore:

```python
runtime.context.user_id
```

works.

And:

```python
runtime.context.api_client
```

works.

---

# 16. The complete execution flow

Imagine the user is authenticated as:

```text
user_123
```

Your FastAPI application creates:

```python
context = RequestContext(
    user_id="user_123",
    api_client=api_client,
)
```

Then your agent is invoked with that context.

Conceptually:

```text
                    Your application
                          │
                          │
                          ▼
              RequestContext(...)
              ┌───────────────────┐
              │ user_id           │
              │ "user_123"        │
              │                   │
              │ api_client        │
              │ ApiClient(...)     │
              └───────────────────┘
                          │
                          ▼
                     LangChain
                          │
                          ▼
                  ToolRuntime(...)
              ┌─────────────────────┐
              │ context             │──────► RequestContext
              │ state               │
              │ config              │
              │ store               │
              │ tool_call_id        │
              │ ...                 │
              └─────────────────────┘
                          │
                          ▼
                  your @tool function
                          │
                          ▼
               runtime.context.user_id
                          │
                          ▼
                      "user_123"
```

That's the whole idea.

---

# 17. Where does the context actually come from?

With current LangChain agent APIs, you can define the context schema and pass the actual context when invoking the agent.

For example:

```python
from dataclasses import dataclass
from langchain.agents import create_agent


@dataclass(frozen=True)
class RequestContext:
    user_id: str
    api_client: ApiClient
```

Then:

```python
agent = create_agent(
    model=model,
    tools=[get_user_profile],
    context_schema=RequestContext,
)
```

And when calling the agent:

```python
result = await agent.ainvoke(
    {
        "messages": [
            {
                "role": "user",
                "content": "Get my profile",
            }
        ]
    },
    context=RequestContext(
        user_id="user_123",
        api_client=api_client,
    ),
)
```

LangChain then makes that context available through `ToolRuntime`. Current LangChain documentation demonstrates the same `context_schema=...` + `context=...` pattern. ([Docs by LangChain][3])

---

# 18. So there are three separate concepts

This is perhaps the most important mental model.

## A. Context schema

You define:

```python
@dataclass(frozen=True)
class RequestContext:
    user_id: str
    api_client: ApiClient
```

This says:

> "This is the information my application wants to carry for one execution."

---

## B. Runtime

LangChain creates:

```python
ToolRuntime(...)
```

This says:

> "Here is all the runtime information available while this tool is executing."

---

## C. Generic type

You write:

```python
ToolRuntime[RequestContext]
```

This says:

> "The `.context` inside this runtime is specifically a `RequestContext`."

---

# 19. Think of it like a box inside a bigger box

This mental picture may help.

```text
ToolRuntime
┌────────────────────────────────────────┐
│                                        │
│  context                               │
│  ┌──────────────────────────────────┐  │
│  │ RequestContext                   │  │
│  │                                  │  │
│  │ user_id = "user_123"             │  │
│  │ api_client = ApiClient(...)      │  │
│  └──────────────────────────────────┘  │
│                                        │
│  state = ...                           │
│  config = ...                          │
│  store = ...                           │
│  tool_call_id = ...                    │
│  stream_writer = ...                   │
│                                        │
└────────────────────────────────────────┘
```

Therefore:

```python
runtime.context.user_id
```

means:

```text
runtime
  ↓
context
  ↓
user_id
```

---

# 20. Why `ToolRuntime` is especially useful for your enterprise AI project

This concept maps very well to the enterprise AI harness you're thinking about.

Imagine an employee logs into your system.

Your application knows:

```text
user_id
tenant_id
roles
permissions
API clients
database clients
security policies
```

You could define something like:

```python
@dataclass(frozen=True)
class RequestContext:
    user_id: str
    tenant_id: str
    api_client: ApiClient
```

Then tools can access trusted execution context:

```python
@tool
async def search_company_documents(
    query: str,
    runtime: ToolRuntime[RequestContext],
) -> str:

    tenant_id = runtime.context.tenant_id

    ...
```

Notice the important separation:

```text
query
  ↑
LLM can choose

tenant_id
  ↑
application chooses
```

That's a powerful architecture.

The model can say:

> "Search for information about the leave policy."

But the application determines:

> "Search within tenant ACME's authorized data."

That's very different from letting the model supply:

```text
tenant_id="ACME"
```

itself.

---

# 21. `frozen=True` also makes more sense in this architecture

Consider:

```python
@dataclass(frozen=True)
class RequestContext:
    user_id: str
    tenant_id: str
    api_client: ApiClient
```

Once the request begins:

```text
Request starts
     ↓
RequestContext created
     ↓
user_id = user_123
tenant_id = company_456
     ↓
agent
     ↓
tool
     ↓
another tool
```

You generally want these identity/context fields to remain stable during the execution.

So:

```python
frozen=True
```

helps express:

> "This is execution context, not mutable agent state."

---

# 22. Context vs State

This distinction will become very important as you learn LangGraph.

They are not the same thing.

### Context

Usually means:

```text
Who is this?
What dependencies/configuration does this execution have?
```

Examples:

```text
user_id
tenant_id
API client
service client
permissions/configuration
```

### State

Usually means:

```text
What has happened in the agent workflow?
```

Examples:

```text
messages
current task status
intermediate results
authenticated flag
workflow data
```

So conceptually:

```text
Context
  └── "Who/what is executing this?"

State
  └── "What has happened during this execution?"
```

`ToolRuntime` can give a tool access to both. Current documentation explicitly distinguishes runtime `context` from graph/agent `state`. ([LangChain Reference][1])

---

# 23. Another very useful example

Suppose you create:

```python
@dataclass(frozen=True)
class RequestContext:
    user_id: str
    api_client: ApiClient
```

Then:

```python
@tool
async def delete_document(
    document_id: str,
    runtime: ToolRuntime[RequestContext],
) -> str:
    """Delete a document owned by the current user."""

    user_id = runtime.context.user_id
    api_client = runtime.context.api_client

    await api_client.delete_document(
        document_id=document_id,
        user_id=user_id,
    )

    return "Document deleted."
```

The model chooses:

```text
document_id
```

But the application determines:

```text
user_id
api_client
```

That separation is exactly the sort of pattern you want when building serious agent systems.

---

# 24. Why not simply make `user_id` a normal argument?

You could technically do:

```python
@tool
async def delete_document(
    document_id: str,
    user_id: str,
):
    ...
```

But then the model-facing tool schema includes both.

The LLM could potentially construct:

```json
{
  "document_id": "123",
  "user_id": "456"
}
```

Whereas with:

```python
@tool
async def delete_document(
    document_id: str,
    runtime: ToolRuntime[RequestContext],
):
```

the model-facing part is essentially:

```json
{
  "document_id": "123"
}
```

while your trusted application context supplies:

```python
runtime.context.user_id
```

This is one of the key security/design advantages of injected runtime data. LangChain explicitly documents that the runtime parameter is hidden from the model's tool signature. ([Docs by LangChain][3])

---

# 25. One more thing: `ToolRuntime` isn't something you normally construct yourself

Beginners often see:

```python
runtime: ToolRuntime[RequestContext]
```

and think they need:

```python
runtime = ToolRuntime(...)
```

Usually, **no**.

You write:

```python
@tool
def my_tool(
    runtime: ToolRuntime[RequestContext],
):
    ...
```

and LangChain handles the injection during tool execution. ([LangChain Reference][1])

Your job is primarily to **consume** the runtime:

```python
runtime.context
runtime.state
runtime.store
runtime.tool_call_id
```

rather than manually constructing it.

---

# 26. What does the square bracket really mean?

You may already know Python generics, but let's connect it clearly.

You can have:

```python
list[str]
```

which means:

> list containing strings.

You can have:

```python
dict[str, int]
```

which means:

> dictionary mapping strings to integers.

Similarly:

```python
ToolRuntime[RequestContext]
```

means roughly:

> ToolRuntime associated with `RequestContext`.

So:

```python
list[str]
```

↓

```text
container = list
item type = str
```

And:

```python
ToolRuntime[RequestContext]
```

↓

```text
container/runtime = ToolRuntime
context type = RequestContext
```

That's the mental model I want you to remember.

---

# 27. Your original code translated into plain English

Your code:

```python
@dataclass(frozen=True)
class RequestContext:
    user_id: str
    api_client: "ApiClient"
```

means:

> Create a small immutable-ish data container representing the trusted context of one request. It contains the authenticated user's ID and an API client.

And:

```python
ToolRuntime[RequestContext]
```

means:

> Give the tool the LangChain runtime object, whose `context` is expected to contain a `RequestContext`.

Then:

```python
runtime.context.user_id
```

means:

> From the current tool execution → get the request context → get the authenticated user ID.

And:

```python
runtime.context.api_client
```

means:

> From the current tool execution → get the request context → get the API client.

---

# 28. The entire concept in one diagram

```text
                 APPLICATION
                      │
                      │
                      │ creates trusted context
                      ▼
       ┌───────────────────────────────┐
       │ RequestContext                │
       │                               │
       │ user_id = "user_123"          │
       │ api_client = ApiClient(...)   │
       └───────────────┬───────────────┘
                       │
                       │ context=
                       ▼
                LANGCHAIN AGENT
                       │
                       │
                       ▼
                TOOL EXECUTION
                       │
                       │ injects automatically
                       ▼
       ┌────────────────────────────────┐
       │ ToolRuntime[RequestContext]    │
       │                                │
       │ context ────────────────┐      │
       │ state                   │      │
       │ config                  │      │
       │ store                   │      │
       │ tool_call_id            │      │
       └─────────────────────────┼──────┘
                                 │
                                 ▼
                      RequestContext
                      ┌───────────────┐
                      │ user_id       │
                      │ api_client    │
                      └───────────────┘
```

---

# 29. The three things I'd memorize

For your current LangChain learning, remember these three sentences:

### `@dataclass`

> **A convenient way to define a data container.**

### `frozen=True`

> **Don't allow the dataclass fields to be reassigned after creation.**

### `ToolRuntime[RequestContext]`

> **Give my tool the current LangChain runtime, and make its `context` a `RequestContext`.**

And the most important practical distinction:

```text
LLM-controlled input
        ≠
trusted application context
```

For production agents, keeping that distinction clear is extremely important.

One small version note: current LangChain/LangGraph documentation uses this runtime/context model in the v1 APIs, and `ToolRuntime` is specifically designed for tool execution; `Runtime` is the related type used in graph nodes and middleware. ([LangChain Reference][1])

Next, the most useful thing to learn after this is **how `context_schema`, `ToolRuntime`, `state_schema`, and `AgentState` differ**, because those four concepts are very easy to mix up when you first start building LangGraph agents.

[1]: https://reference.langchain.com/python/langgraph.prebuilt/tool_node/ToolRuntime?utm_source=chatgpt.com "ToolRuntime | langgraph.prebuilt | LangChain Reference"
[2]: https://docs.python.org/3.13/library/dataclasses.html?utm_source=chatgpt.com "dataclasses — Data Classes — Python 3.13.15 documentation"
[3]: https://docs.langchain.com/oss/python/langchain/short-term-memory?utm_source=chatgpt.com "Short-term memory - Docs by LangChain"

