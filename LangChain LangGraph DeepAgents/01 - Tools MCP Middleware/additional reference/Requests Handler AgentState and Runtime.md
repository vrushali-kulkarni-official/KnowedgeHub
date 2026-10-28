In LangChain’s current agent middleware API, these four concepts fit together very naturally:

> **`request` = what is happening right now**
> **`handler` = what normally happens next**
> **`AgentState` = what the agent currently remembers**
> **`Runtime` = extra execution/context information available during this run**

LangChain’s current `wrap_model_call` middleware receives a `ModelRequest` containing the model, messages, state, runtime, tools, and other model-call settings. The `handler` is the callback that actually continues execution. ([GitHub][1])

---

# 1. First, see the big picture

Imagine your agent receives:

> User: "What's the weather in Mumbai?"

The agent loop roughly looks like:

```text
User request
     │
     ▼
Agent
     │
     ▼
Middleware
     │
     ├── request
     │     ├── current messages
     │     ├── current state
     │     ├── runtime/context
     │     ├── model
     │     └── tools
     │
     ├── inspect / modify
     │
     └── handler(request)
              │
              ▼
         actual model call
              │
              ▼
         AI response
              │
              ▼
         possibly tool call
```

The important idea is:

**middleware sits in the middle of the agent execution.**

It can look at what is about to happen, change it, allow it to continue, retry it, or stop it. That is exactly what `wrap_model_call` and `wrap_tool_call` are designed for. ([LangChain Reference][2])

---

# 2. What is `request`?

Think of `request` as:

> **"Here is everything you need to know about the operation that is about to happen."**

For model middleware, the request is a `ModelRequest`.

Current LangChain's `ModelRequest` contains things such as:

```python
request.model
request.messages
request.system_message
request.tools
request.tool_choice
request.response_format
request.state
request.runtime
request.model_settings
```

([GitHub][1])

So when you write:

```python
@wrap_model_call
def my_middleware(request, handler):
    ...
```

`request` is basically a package of information about the **current model invocation**.

For example:

```python
def my_middleware(request, handler):

    print(request.messages)
    print(request.state)
    print(request.runtime)

    return handler(request)
```

You can think:

```text
request
│
├── model
├── messages
├── tools
├── state
├── runtime
└── settings
```

### Simple analogy

Imagine you're at a restaurant.

The waiter brings you an order ticket:

```text
Order:
Customer: Bhargav
Table: 5
Food: Pizza
Special instructions: No onions
```

That ticket is similar to `request`.

The middleware looks at the ticket before the kitchen processes it.

---

# 3. What is `handler`?

This is probably the most important one to understand.

`handler` means:

> **"Continue the normal operation."**

For `wrap_model_call`, LangChain gives middleware a handler callback that executes the model request. You call:

```python
return handler(request)
```

to let the request continue to the next middleware / actual model execution. ([LangChain Reference][2])

For example:

```python
@wrap_model_call
def logging_middleware(request, handler):

    print("Before model")

    response = handler(request)

    print("After model")

    return response
```

Conceptually:

```text
middleware starts
       │
       ▼
print("Before model")
       │
       ▼
handler(request)
       │
       ▼
model runs
       │
       ▼
response
       │
       ▼
print("After model")
       │
       ▼
return response
```

So `handler` is basically the **next step in the pipeline**.

---

# 4. Why doesn't middleware simply call the model directly?

Because middleware is supposed to sit **between layers**.

Imagine you have:

```python
middleware=[security, logging, retry]
```

The execution can conceptually look like:

```text
security
   │
   ▼
logging
   │
   ▼
retry
   │
   ▼
model
```

Each middleware receives a handler representing the next layer.

So:

```python
return handler(request)
```

means:

> "I'm done with my part. Continue."

This is why middleware can behave like nested wrappers.

For example:

```python
def security(request, handler):
    print("security before")
    result = handler(request)
    print("security after")
    return result
```

and:

```python
def logging(request, handler):
    print("logging before")
    result = handler(request)
    print("logging after")
    return result
```

Conceptually:

```text
security before
    ↓
logging before
    ↓
model
    ↓
logging after
    ↓
security after
```

LangChain documents middleware as composing automatically, with the first middleware being the outermost layer. ([LangChain Reference][2])

---

# 5. `handler` is more powerful than just "call next"

You can also **not call it**.

For example, you could implement a cache:

```python
@wrap_model_call
def cache_middleware(request, handler):

    cached = get_cached_response(request.messages)

    if cached:
        return cached

    return handler(request)
```

Now the execution is:

```text
Request
  │
  ▼
Cache middleware
  │
  ├── cached? ── yes ──► return cached response
  │
  └── no
       │
       ▼
   handler(request)
       │
       ▼
     model
```

The LangChain middleware API explicitly supports skipping the handler to short-circuit execution. It can also call it multiple times, which is useful for retry logic. ([LangChain Reference][2])

For example:

```python
for attempt in range(3):
    try:
        return handler(request)
    except Exception:
        if attempt == 2:
            raise
```

---

# 6. What is `AgentState`?

Now we move to the agent's **memory of its current execution**.

`AgentState` is the state maintained by the agent.

In the current LangChain implementation, the default state includes the conversation `messages`, and can also contain things such as `structured_response` and internal execution fields. ([GitHub][3])

A simplified mental model is:

```python
state = {
    "messages": [
        HumanMessage(...),
        AIMessage(...),
        ToolMessage(...),
    ]
}
```

So:

> **State = information that belongs to the agent's ongoing computation.**

For example:

```text
User says:
"What's the weather?"

                    ↓

state
┌─────────────────────────────┐
│ messages                    │
│                             │
│ Human: What's the weather?  │
└─────────────────────────────┘
```

Then the model decides to call:

```text
get_weather("Mumbai")
```

State becomes something conceptually like:

```text
state
┌──────────────────────────────────────┐
│ messages                             │
│                                      │
│ Human: What's the weather?           │
│ AI: calling get_weather              │
│ Tool: 31°C                           │
└──────────────────────────────────────┘
```

Then the model answers:

```text
AI: Mumbai is currently 31°C.
```

That also becomes part of the state.

---

# 7. Why is `AgentState` different from conversation history?

Because state is a **broader concept**.

Conversation messages are one part of state.

You can define custom state:

```python
class MyState(AgentState):
    user_name: str
    request_count: int
    is_admin: bool
```

Then conceptually:

```text
AgentState
│
├── messages
├── user_name
├── request_count
└── is_admin
```

This is useful for agent logic that needs information beyond messages.

For example:

```python
if request.state["is_admin"]:
    ...
```

LangChain supports supplying a custom state schema that extends `AgentState`. ([LangChain Reference][4])

---

# 8. Very important: State is not the same thing as Runtime

This distinction will become extremely important for you as you move deeper into LangGraph.

### State

Think:

> **"What has happened / what does the agent currently contain?"**

Examples:

```text
messages
current task status
tool results
intermediate values
custom agent variables
structured response
```

### Runtime

Think:

> **"What environment/context is this execution happening in?"**

LangGraph's `Runtime` provides information such as runtime context, store, stream writer, execution information, and server information. ([GitHub][5])

For example:

```text
Runtime
│
├── context
├── store
├── stream_writer
├── execution_info
└── server_info
```

---

# 9. What is `Runtime`?

A very easy way to think about it:

> **Runtime is the environment surrounding the current agent execution.**

For example, suppose your application calls an agent for user `user_123`.

You might pass:

```python
@dataclass
class Context:
    user_id: str
    organization_id: str
```

Then invoke the agent with runtime context.

Middleware can access:

```python
request.runtime.context.user_id
```

LangChain specifically documents runtime context as a way to provide dependencies such as user IDs, database connections, or other invocation-specific information without hardcoding them or using global state. ([GitHub][5])

---

# 10. Why is Runtime useful?

Suppose your application has:

```text
User: Bhargav
Company: VB Creators
User role: Admin
Database connection: DB-123
```

These are not necessarily things the model should generate or maintain as part of the conversation.

They are **application/runtime information**.

So you might have:

```python
@dataclass
class Context:
    user_id: str
    company_id: str
```

And then:

```python
request.runtime.context.user_id
```

gives middleware access to the current user.

For example:

```python
@wrap_model_call
def dynamic_prompt(request, handler):

    user_id = request.runtime.context.user_id

    print("Running for:", user_id)

    return handler(request)
```

The official runtime documentation shows this same pattern for dynamic prompts. ([GitHub][5])

---

# 11. A very simple comparison

Here is the mental model I recommend memorizing:

| Thing        | Think of it as              | Main question                                   |
| ------------ | --------------------------- | ----------------------------------------------- |
| `request`    | Current operation's package | **What is happening now?**                      |
| `handler`    | Next-step function          | **What should happen next?**                    |
| `AgentState` | Agent's working memory      | **What does the agent currently know/contain?** |
| `Runtime`    | Execution environment       | **Who/where/how is this execution running?**    |

---

# 12. How they appear together

This is the important part.

A model middleware function commonly looks like:

```python
@wrap_model_call
def my_middleware(request, handler):

    state = request.state
    runtime = request.runtime

    print("STATE:", state)
    print("USER:", runtime.context.user_id)

    return handler(request)
```

So:

```text
request
│
├── state
│    └── AgentState
│
└── runtime
     └── Runtime
```

And separately:

```text
handler
   │
   └── executes the next stage
```

This is exactly how the current `ModelRequest` API is structured: `ModelRequest` contains both `state` and `runtime`. ([GitHub][1])

---

# 13. An analogy that makes all four click

Imagine an airport.

### `AgentState` = passenger's journey record

```text
Passenger:
- checked in
- security completed
- boarding pass issued
- gate B12
```

That's the **current state**.

### `Runtime` = airport environment

```text
Airport:
- terminal
- current time
- security system
- available services
- operational information
```

That's the **execution environment**.

### `request` = current operation ticket

```text
Passenger Bhargav
Flight AI123
Gate B12
Operation: boarding
```

That's the **current request**.

### `handler` = next operation

```text
handler(request)
```

means:

> "Continue the normal boarding process."

---

# 14. Model middleware example

Let's put everything together.

```python
from langchain.agents.middleware import wrap_model_call


@wrap_model_call
def my_middleware(request, handler):

    # 1. Current agent state
    state = request.state

    # 2. Current runtime environment
    runtime = request.runtime

    # 3. Inspect current user
    user_id = runtime.context.user_id

    # 4. Inspect conversation
    messages = state["messages"]

    print("User:", user_id)
    print("Messages:", messages)

    # 5. Continue normal execution
    response = handler(request)

    # 6. Inspect model response
    print("Model responded")

    return response
```

The flow is:

```text
                    middleware
                        │
                        ▼
                 ┌──────────────┐
                 │   request    │
                 └──────┬───────┘
                        │
              ┌─────────┴─────────┐
              ▼                   ▼
         request.state      request.runtime
              │                   │
              ▼                   ▼
        AgentState             Runtime
              │                   │
              │              context/user/etc
              │
          messages/etc
                        │
                        ▼
                 handler(request)
                        │
                        ▼
                    model call
```

---

# 15. Now the tool middleware version

There is a similar concept when intercepting tool calls.

Current LangChain/LangGraph uses a `ToolCallRequest` containing:

```text
tool_call
tool
state
runtime
```

([LangChain Reference][6])

So:

```python
@wrap_tool_call
def my_tool_middleware(request, handler):

    print(request.tool_call)
    print(request.tool)
    print(request.state)
    print(request.runtime)

    return handler(request)
```

Here the meaning is:

```text
request
│
├── tool_call     ← what tool does the model want?
├── tool          ← actual tool object
├── state         ← current agent state
└── runtime       ← current execution environment
```

And:

```python
handler(request)
```

means:

> "Actually execute the tool."

---

# 16. `request` differs depending on middleware hook

This is another important detail.

For:

```python
wrap_model_call
```

you get something like:

```python
request: ModelRequest
```

For:

```python
wrap_tool_call
```

you get:

```python
request: ToolCallRequest
```

They both provide state/runtime, but the operation they're describing is different.

### Model

```text
ModelRequest

"What is about to happen to the model?"
```

### Tool

```text
ToolCallRequest

"What tool call is about to happen?"
```

---

# 17. `before_model` is slightly different

This is also useful because you're learning middleware systematically.

With a node-style hook like:

```python
@before_model
def before_model(state, runtime):
    ...
```

you don't get:

```python
request
handler
```

Instead, you directly receive:

```text
state
runtime
```

The current middleware API distinguishes these lifecycle hooks from wrap-style hooks. For `wrap_model_call`, runtime is carried inside `ModelRequest`; for node-style hooks such as `before_model`, `state` and `runtime` are passed directly. ([GitHub][5])

So:

```python
@before_model
def before_model(state, runtime):
    ...
```

versus:

```python
@wrap_model_call
def wrap_model(request, handler):
    state = request.state
    runtime = request.runtime
    ...
```

---

# 18. The easiest way to remember everything

I would memorize this:

```text
REQUEST
"What is happening?"

STATE
"What does the agent currently contain?"

RUNTIME
"What environment is this execution running in?"

HANDLER
"Continue the operation."
```

Or even shorter:

```text
request  → current operation
state    → agent memory
runtime  → execution environment
handler  → next step
```

---

# 19. One final complete example

Imagine:

```python
@wrap_model_call
def security_middleware(request, handler):

    # Agent's current information
    state = request.state

    # Application/execution information
    runtime = request.runtime

    # Current user
    user_id = runtime.context.user_id

    # Current conversation
    messages = state["messages"]

    # Security decision
    if not is_allowed(user_id):
        return blocked_response()

    # Continue to next middleware/model
    return handler(request)
```

The mental flow is:

```text
User
 │
 ▼
Agent
 │
 ▼
security_middleware
 │
 ├── request
 │    │
 │    ├── state ───► "What does the agent know?"
 │    │
 │    └── runtime ─► "Who/where is this execution?"
 │
 ├── reject?
 │      │
 │      ├── YES ──► return response
 │      │
 │      └── NO
 │
 ▼
handler(request)
 │
 ▼
next middleware
 │
 ▼
model
```

That is the core architecture behind a lot of the middleware code you'll encounter in **LangChain + LangGraph + Deep Agents**. LangChain's current `create_agent` API uses middleware around the agent loop, while runtime context is supplied through the underlying LangGraph runtime. ([LangChain Reference][4])

One subtle but very important next concept is **`state` vs `context` vs `config` vs `store` vs `checkpointer`**, because those five are easy to mix up when learning LangGraph.

[1]: https://github.com/langchain-ai/langchain/blob/master/libs/langchain_v1/langchain/agents/middleware/types.py?utm_source=chatgpt.com "langchain/libs/langchain_v1/langchain/agents/middleware/types.py at master · langchain-ai/langchain · GitHub"
[2]: https://reference.langchain.com/python/langchain/agents/middleware/types/AgentMiddleware/wrap_model_call?utm_source=chatgpt.com "wrap_model_call | langchain | LangChain Reference"
[3]: https://github.com/langchain-ai/langchain/blob/master/openwiki/agent-execution.md?utm_source=chatgpt.com "langchain/openwiki/agent-execution.md at master · langchain-ai/langchain · GitHub"
[4]: https://reference.langchain.com/python/langchain/agents/factory/create_agent?utm_source=chatgpt.com "create_agent | langchain | LangChain Reference"
[5]: https://github.com/langchain-ai/docs/blob/main/src/oss/langchain/runtime.mdx?utm_source=chatgpt.com "docs/src/oss/langchain/runtime.mdx at main · langchain-ai/docs · GitHub"
[6]: https://reference.langchain.com/python/langgraph.prebuilt/tool_node/ToolCallRequest?utm_source=chatgpt.com "ToolCallRequest | langgraph.prebuilt | LangChain Reference"

