# PHASE 6 — Agents with `create_agent`

## Module 44 — Middleware Anatomy

You are at the point where the important shift happens:

> **An agent is no longer just “model + tools + loop”. Middleware lets you control the machinery around that loop.**

Current LangChain v1 documentation describes the agent as a model/tool loop, with middleware forming the **harness** around that loop. `create_agent()` is the current agent factory, and middleware is the primary customization mechanism. ([Docs by LangChain][1])

I checked the current LangChain documentation and API reference while preparing this lesson. The current middleware API is in the LangChain 1.x line, with the reference currently showing `1.4.x` APIs. The hook set you listed is the current one:

```text
before_agent
before_model
wrap_model_call
after_model
wrap_tool_call
after_agent
```

There is **no current `before_tool`, `after_tool`, or `modify_model_request` hook** in the released v1 middleware API. `modify_model_request` appeared in the early LangChain 1.0 alpha design, but the released API uses `wrap_model_call` instead. ([LangChain Reference][2])

---

# 1. First: what problem does middleware actually solve?

You already know the basic agent loop:

```text
User
  ↓
Model
  ↓
Does model want a tool?
  ├── No → Final answer
  │
  └── Yes
        ↓
      Tool
        ↓
      Tool result
        ↓
      Model again
        ↓
      ...
```

Without middleware, your control over the internals is relatively limited.

Suppose you now need:

```text
• log every model call
• count model calls
• block certain requests
• dynamically change the system prompt
• dynamically choose the model
• dynamically filter tools
• retry failed model calls
• retry failed tool calls
• enforce authorization
• prevent certain tools from executing
• perform PII checks
• terminate an agent early
• collect usage statistics
• add state shared between middleware hooks
• inject user-specific runtime context
```

You could manually build all of this into a custom LangGraph workflow.

But that would mean maintaining a lot of plumbing yourself.

Middleware gives you a standardized interception system for exactly this kind of cross-cutting behavior. LangChain's own documentation specifically positions middleware for logging, prompt/tool transformation, retries, fallbacks, rate limits, guardrails, PII handling and early termination. ([Docs by LangChain][3])

So mentally:

```text
                   create_agent()
                        │
          ┌─────────────┴─────────────┐
          │                           │
      Middleware                  Agent loop
          │                           │
          │       ┌───────────────┐   │
          ├──────►│     Model     │◄──┤
          │       └───────┬───────┘   │
          │               │           │
          │          tool_calls?      │
          │               │           │
          │        ┌──────▼──────┐    │
          └───────►│    Tools    │────┘
                   └─────────────┘
```

The key concept is:

> **Middleware does not replace the agent loop. It hooks into the agent loop.**

And importantly, middleware is not a completely separate runtime. `create_agent()` produces a compiled LangGraph graph, and the middleware hooks run inside that graph. ([Docs by LangChain][3])

---

# 2. The most important mental model: node-style vs wrap-style hooks

There are two categories.

## Node-style hooks

These are:

```text
before_agent
before_model
after_model
after_agent
```

They execute at particular lifecycle points.

Think:

```text
"Run this function HERE."
```

For example:

```python
@before_model
def log_model_start(state, runtime):
    print("Model is about to run")
    return None
```

---

## Wrap-style hooks

These are:

```text
wrap_model_call
wrap_tool_call
```

They receive a `handler`.

Think:

```text
"Give me control over whether/how the next thing actually runs."
```

Conceptually:

```python
def middleware(request, handler):
    # before
    result = handler(request)
    # after
    return result
```

This gives you capabilities that a simple `before_model` does not:

```text
call handler zero times
call handler once
call handler multiple times
modify request before handler
modify response after handler
retry
cache
short-circuit
replace execution
```

The current LangChain documentation explicitly describes wrap hooks as allowing the handler to be called zero, one, or multiple times. ([Docs by LangChain][4])

This distinction is one of the most important things to understand in this entire module.

---

# 3. The complete lifecycle

Let's build the complete picture.

Suppose:

```python
agent = create_agent(
    model=...,
    tools=[...],
    middleware=[
        MiddlewareA(),
        MiddlewareB(),
    ],
)
```

A normal execution looks conceptually like this:

```text
┌──────────────────────────────┐
│       Agent invocation       │
└──────────────┬───────────────┘
               ↓
       before_agent
               ↓
        ┌──────────────┐
        │  Agent loop  │
        └──────┬───────┘
               ↓
        before_model
               ↓
      wrap_model_call
               ↓
            MODEL
               ↓
        after_model
               ↓
       tool calls?
          /      \
        no        yes
        ↓          ↓
     finish    wrap_tool_call
                   ↓
                 TOOL
                   ↓
             tool result
                   ↓
             back to loop
                   │
                   └──────────► before_model
                                ...
               ↓
        after_agent
               ↓
             END
```

The crucial thing is that:

> `before_model`, `wrap_model_call`, and `after_model` happen **for every model iteration**, not only once.

`before_agent` and `after_agent` happen once for the invocation. `wrap_tool_call` happens around tool execution whenever a tool call occurs. ([Docs by LangChain][4])

---

# 4. Hook #1 — `before_agent`

## What is it?

`before_agent` executes **once**, at the beginning of the agent invocation. ([Docs by LangChain][4])

Conceptually:

```text
agent.invoke(...)
       ↓
before_agent()
       ↓
agent loop
```

Typical uses:

```text
• initialize state
• validate invocation
• perform request-level checks
• attach metadata/state
• perform authentication checks
• terminate the invocation before model execution
```

Example:

```python
from typing import Any
from langchain.agents.middleware import before_agent, AgentState
from langgraph.runtime import Runtime


@before_agent
def initialize_request(
    state: AgentState,
    runtime: Runtime,
) -> dict[str, Any] | None:
    print("Agent invocation started")
    return None
```

Returning:

```python
None
```

means:

> I have nothing to change. Continue.

Returning a dictionary:

```python
return {
    "some_state_field": value
}
```

means:

> Update the agent state.

---

# 5. `before_agent` versus `before_model`

This distinction is extremely important.

Suppose the agent needs 5 model calls.

`before_agent`:

```text
runs once
```

`before_model`:

```text
runs 5 times
```

Example:

```text
User request
   ↓
before_agent        ← once
   ↓
before_model        ← model call #1
   ↓
model
   ↓
tool
   ↓
before_model        ← model call #2
   ↓
model
   ↓
tool
   ↓
before_model        ← model call #3
   ↓
model
   ↓
...
```

So:

### Use `before_agent`

for invocation-level logic.

### Use `before_model`

for per-model-call logic.

This is one of the easiest places to accidentally put logic at the wrong level.

---

# 6. Hook #2 — `before_model`

`before_model` runs immediately before each model call. It receives:

```python
state
runtime
```

The current API is essentially:

```python
def before_model(
    state: StateT,
    runtime: Runtime[ContextT],
) -> dict | None:
    ...
```

It can:

```text
• inspect state
• inspect runtime context
• update state
• control routing using jump_to
```

The decorator supports `can_jump_to`, including:

```text
"tools"
"model"
"end"
```

as valid destinations. ([LangChain Reference][5])

Example:

```python
from typing import Any
from langchain.agents.middleware import before_model, AgentState
from langgraph.runtime import Runtime


@before_model
def log_before_model(
    state: AgentState,
    runtime: Runtime,
) -> dict[str, Any] | None:

    print(
        f"Messages so far: {len(state['messages'])}"
    )

    return None
```

---

# 7. `before_model` does NOT receive a `ModelRequest`

This distinction is very important.

You may see:

```python
@before_model
def something(state, runtime):
    ...
```

but:

```python
@wrap_model_call
def something(request, handler):
    ...
```

Why?

Because these hooks operate at different levels.

### `before_model`

You are operating at the **agent state/lifecycle level**.

```text
state
runtime
```

### `wrap_model_call`

You are operating at the **actual model-call request level**.

```text
request
handler
```

That means:

```python
before_model
```

is ideal for:

```text
logging
validation
state counters
conditional routing
```

while:

```python
wrap_model_call
```

is ideal for:

```text
change model
change prompt
change tools
change messages
retry
fallback
cache
short-circuit
```

This distinction replaces much of the functionality older examples used to associate with `modify_model_request`. ([LangChain Reference][6])

---

# 8. Hook #3 — `wrap_model_call`

This is arguably the most powerful middleware hook.

The shape is:

```python
def wrap_model_call(
    request,
    handler,
):
    ...
```

Think of:

```python
handler(request)
```

as:

> "Actually perform the model call."

The middleware controls that call.

---

# 9. The simplest `wrap_model_call`

```python
from collections.abc import Callable

from langchain.agents.middleware import (
    wrap_model_call,
    ModelRequest,
    ModelResponse,
)


@wrap_model_call
def log_model_call(
    request: ModelRequest,
    handler: Callable[[ModelRequest], ModelResponse],
) -> ModelResponse:

    print("Model is about to run")

    response = handler(request)

    print("Model finished")

    return response
```

The flow becomes:

```text
wrap_model_call
     │
     ├── before
     │
     ▼
 handler(request)
     │
     ▼
   MODEL
     │
     ▼
 response
     │
     ├── after
     ▼
 return response
```

---

# 10. Why is `handler` so important?

Because the middleware can decide whether to call it.

## Case 1 — call once

Normal execution:

```python
return handler(request)
```

---

## Case 2 — call zero times

Short-circuit:

```python
return cached_response
```

The real model is never called.

This is useful for:

```text
• caching
• policy blocks
• deterministic responses
• test doubles
• local routing
```

The current reference explicitly states that wrap middleware may skip calling the handler to short-circuit execution. ([LangChain Reference][7])

---

## Case 3 — call multiple times

For example:

```python
for attempt in range(3):
    try:
        return handler(request)
    except Exception:
        if attempt == 2:
            raise
```

Now one logical agent model step could result in three actual model attempts.

That is why retry functionality naturally belongs in `wrap_model_call`.

LangChain now also provides prebuilt `ModelRetryMiddleware`, so in production you often should use the prebuilt component rather than maintaining retry behavior yourself. ([LangChain Reference][8])

That fits your preference for using mature premade components.

---

# 11. Modifying the model request

This is where the modern replacement for `modify_model_request` becomes clear.

Current code:

```python
@wrap_model_call
def customize_model(
    request: ModelRequest,
    handler,
):
    new_request = request.override(
        model=my_model,
        tools=my_tools,
    )

    return handler(new_request)
```

`ModelRequest.override()` returns a **new request** and follows an immutable pattern rather than modifying the original request in place. ([LangChain Reference][6])

You can override things such as:

```text
model
system_message
messages
tools
tool_choice
response_format
model_settings
state
```

Current reference also explicitly marks `system_prompt` inside `override()` as deprecated and says to use `system_message` instead. ([LangChain Reference][6])

So this:

```python
request.override(system_prompt="...")
```

is old/deprecated.

Use:

```python
request.override(
    system_message=...
)
```

instead.

---

# 12. Example — dynamically changing the model

Imagine:

```text
simple request → fast/cheap model
complex request → stronger model
```

Current middleware pattern:

```python
@wrap_model_call
def dynamic_model(
    request: ModelRequest,
    handler,
):
    if len(request.messages) > 10:
        model = complex_model
    else:
        model = simple_model

    return handler(
        request.override(model=model)
    )
```

LangChain's current custom middleware documentation uses this exact architectural pattern. ([Docs by LangChain][4])

---

# 13. Dynamic prompt: `@dynamic_prompt`

You will frequently need:

```text
same agent
+
different user/context
=
different system prompt
```

For example:

```text
user role = administrator
```

versus:

```text
user role = normal employee
```

The current convenience decorator is:

```python
@dynamic_prompt
```

It is specifically implemented as convenience middleware around `wrap_model_call`. It receives a `ModelRequest`, which contains state and runtime, and returns either a string or `SystemMessage`. ([LangChain Reference][9])

Example:

```python
from langchain.agents.middleware import dynamic_prompt, ModelRequest


@dynamic_prompt
def make_prompt(request: ModelRequest) -> str:
    user_name = request.runtime.context.user_name

    return (
        "You are an enterprise assistant. "
        f"Address the user as {user_name}."
    )
```

Then:

```python
agent = create_agent(
    model="google_genai:gemini-3.6-flash",
    tools=[],
    middleware=[make_prompt],
    context_schema=Context,
)
```

The current LangChain docs themselves use Gemini model identifiers in `create_agent` examples, so Gemini fits cleanly into this API. ([Docs by LangChain][1])

---

# 14. When should you use `@dynamic_prompt` versus `@wrap_model_call`?

A useful rule:

```text
Only changing system prompt?
        ↓
@dynamic_prompt
```

More general model manipulation?

```text
change model
change tools
change messages
change settings
retry
cache
short-circuit
        ↓
@wrap_model_call
```

So:

```python
@dynamic_prompt
```

is the specialized convenience abstraction.

Whereas:

```python
@wrap_model_call
```

is the general-purpose interception mechanism.

---

# 15. Hook #4 — `after_model`

`after_model` runs after the model has returned its result.

The resulting model messages are already part of the agent state when this hook runs. The documentation demonstrates reading:

```python
state["messages"][-1]
```

inside `after_model`. ([Docs by LangChain][4])

Example:

```python
@after_model
def log_model_response(
    state: AgentState,
    runtime: Runtime,
):
    last_message = state["messages"][-1]

    print("Model returned:")
    print(last_message)

    return None
```

This is useful for:

```text
logging
validation
usage tracking
output checks
state updates
early termination
```

---

# 16. `after_model` does NOT mean "after the whole agent"

This is a very common misunderstanding.

Suppose:

```text
model → tool → model → tool → model → final
```

Then:

```text
after_model
```

may run three times.

Whereas:

```text
after_agent
```

runs once.

So:

```text
after_model = after one model step

after_agent = after the entire agent execution
```

---

# 17. Hook #5 — `wrap_tool_call`

This is the tool equivalent of `wrap_model_call`.

But there is an important LangChain design decision:

> There is no separate `before_tool` or `after_tool`.

Instead, both behaviors belong inside:

```python
wrap_tool_call
```

The current API reference defines `wrap_tool_call` as the interception point for retries, monitoring and modification, and explicitly provides the handler that actually executes the tool. ([LangChain Reference][10])

Conceptually:

```python
@wrap_tool_call
def middleware(request, handler):

    # BEFORE TOOL
    ...

    result = handler(request)

    # AFTER TOOL
    ...

    return result
```

So `wrap_tool_call` is effectively:

```text
┌──────────────────────────┐
│      wrap_tool_call      │
│                          │
│   before logic           │
│        ↓                 │
│   handler(request)       │
│        ↓                 │
│   actual tool            │
│        ↓                 │
│   after logic            │
│                          │
└──────────────────────────┘
```

---

# 18. What does `ToolCallRequest` contain?

Current middleware receives a `ToolCallRequest`.

It gives you access to:

```text
request.tool_call
request.tool
request.state
request.runtime
```

The official reference describes it as containing the tool call dictionary, actual tool, state and runtime. ([LangChain Reference][10])

The tool call looks conceptually like:

```python
{
    "id": "call_123",
    "name": "delete_document",
    "args": {
        "document_id": "doc-42"
    },
}
```

So you can inspect:

```python
tool_name = request.tool_call["name"]
arguments = request.tool_call["args"]
call_id = request.tool_call["id"]
```

---

# 19. Using `wrap_tool_call` like `before_tool`

Example:

```python
@wrap_tool_call
def inspect_tool(
    request,
    handler,
):
    print("Tool:", request.tool_call["name"])
    print("Args:", request.tool_call["args"])

    return handler(request)
```

This is your:

```text
before_tool
```

behavior.

---

# 20. Using `wrap_tool_call` like `after_tool`

```python
@wrap_tool_call
def inspect_tool(
    request,
    handler,
):
    result = handler(request)

    print("Tool completed")
    print("Result:", result)

    return result
```

This is your:

```text
after_tool
```

behavior.

---

# 21. Combining before and after logic

This is the pattern you will use constantly:

```python
import time


@wrap_tool_call
def monitor_tool(request, handler):
    start = time.perf_counter()

    print(
        f"START tool={request.tool_call['name']}"
    )

    try:
        result = handler(request)

        elapsed = time.perf_counter() - start

        print(
            f"SUCCESS tool={request.tool_call['name']} "
            f"time={elapsed:.3f}s"
        )

        return result

    except Exception:
        elapsed = time.perf_counter() - start

        print(
            f"FAILED tool={request.tool_call['name']} "
            f"time={elapsed:.3f}s"
        )

        raise
```

This gives you:

```text
before
  ↓
timer
  ↓
tool
  ↓
success/failure
  ↓
after
```

---

# 22. The particularly important part: denying tool execution

This is extremely useful for enterprise agents.

Imagine the model requests:

```text
delete_file
```

but the current user isn't allowed to perform that action.

You do **not** want:

```python
raise PermissionError(...)
```

as your only mechanism.

Instead, middleware can return a `ToolMessage` describing an error and **not call the handler**.

For example:

```python
from langchain.agents.middleware import wrap_tool_call
from langchain.messages import ToolMessage


@wrap_tool_call
def authorization_gate(request, handler):
    tool_name = request.tool_call["name"]

    if tool_name == "delete_file":
        return ToolMessage(
            content="Permission denied: you are not allowed to use delete_file.",
            name=tool_name,
            tool_call_id=request.tool_call["id"],
            status="error",
        )

    return handler(request)
```

The critical line is:

```python
return ToolMessage(...)
```

instead of:

```python
return handler(request)
```

Therefore:

```text
Model requests delete_file
        ↓
wrap_tool_call
        ↓
permission check
        ↓
DENIED
        ↓
ToolMessage(status="error")
        ↓
actual delete_file NEVER executes
```

The current LangChain tool middleware API supports returning `ToolMessage` or `Command` from `wrap_tool_call`; LangChain's own human-in-the-loop implementation also uses error `ToolMessage`s with the corresponding `tool_call_id` when a tool call is rejected. ([LangChain Reference][10])

---

# 23. Why `tool_call_id` matters

Suppose the model generated:

```python
{
    "id": "call_abc123",
    "name": "delete_file",
    ...
}
```

Your tool response must correspond to that call.

Therefore:

```python
tool_call_id=request.tool_call["id"]
```

is very important.

Conceptually:

```text
AIMessage
    │
    └── tool_call id = call_abc123
                  │
                  ▼
            ToolMessage
              id = call_abc123
```

Without the correct association, the model/tool-call message relationship becomes inconsistent.

---

# 24. Why return an error `ToolMessage` instead of raising?

There is an important semantic difference.

## Raising an exception

```python
raise PermissionError(...)
```

means:

```text
middleware
   ↓
exception
   ↓
agent execution may fail
```

## Returning an error ToolMessage

```python
return ToolMessage(
    ...,
    status="error",
)
```

means:

```text
middleware
    ↓
tool call was rejected
    ↓
model receives structured tool error
    ↓
model can decide what to do next
```

That makes the second approach particularly useful for policies where the agent should be allowed to recover.

For example:

```text
Model:
"Call delete_file"

Middleware:
"Permission denied"

Model:
"Okay, I cannot delete it. I'll tell the user."
```

That is much closer to the agent's normal reasoning loop.

---

# 25. Tool authorization: model filtering is NOT enough

There are two different security layers you should understand.

## Layer 1 — hide/filter tools from the model

You can use `wrap_model_call` to expose only relevant tools:

```python
return handler(
    request.override(tools=relevant_tools)
)
```

Current LangChain documentation explicitly demonstrates dynamic tool selection and lists permission control as one of its uses. ([Docs by LangChain][4])

But this should be considered:

```text
model-facing control
```

not your final security boundary.

---

## Layer 2 — enforce authorization when execution happens

Use:

```python
wrap_tool_call
```

to enforce the actual authorization decision.

That gives you:

```text
Tool visible?
     ↓
possibly yes

Tool requested?
     ↓
authorization middleware
     ↓
allowed → execute
denied  → ToolMessage(error)
```

For a production enterprise harness, this distinction is extremely important.

The model should not be trusted to enforce your authorization policy.

---

# 26. Hook #6 — `after_agent`

This runs once after the agent finishes execution. ([LangChain Reference][11])

Example:

```python
from langchain.agents.middleware import after_agent


@after_agent
def cleanup(
    state,
    runtime,
):
    print("Agent execution completed")
    return None
```

Typical uses:

```text
• final audit logging
• metrics
• cleanup
• final state processing
• post-execution bookkeeping
```

Think:

```text
before_agent = beginning of entire invocation

after_agent = end of entire invocation
```

---

# 27. Complete lifecycle example

Suppose we have:

```python
middleware=[
    logging_middleware,
    security_middleware,
]
```

One invocation might look like:

```text
START
 │
 ├─ logging.before_agent
 │
 ├─ security.before_agent
 │
 └─ Agent loop
      │
      ├─ logging.before_model
      ├─ security.before_model
      │
      ├─ logging.wrap_model_call
      │    └─ security.wrap_model_call
      │         └─ MODEL
      │
      ├─ security.after_model
      └─ logging.after_model
      │
      ├─ TOOL CALL?
      │      │
      │      ├─ logging.wrap_tool_call
      │      │    └─ security.wrap_tool_call
      │      │         └─ TOOL
      │      │
      │      └─ result
      │
      ├─ logging.before_model
      ├─ security.before_model
      │
      ├─ logging.wrap_model_call
      │    └─ security.wrap_model_call
      │         └─ MODEL
      │
      ├─ ...
      │
      └─ Agent finished
 │
 ├─ security.after_agent
 └─ logging.after_agent

END
```

---

# 28. Middleware composition order

This is one of the most important advanced topics.

Suppose:

```python
middleware=[
    middleware1,
    middleware2,
    middleware3,
]
```

The current LangChain execution rules are:

### `before_*`

First → last:

```text
middleware1
middleware2
middleware3
```

### `wrap_*`

Nested, where the first middleware is the **outermost**:

```text
middleware1
    ↓
middleware2
    ↓
middleware3
    ↓
actual call
```

### `after_*`

Reverse:

```text
middleware3
middleware2
middleware1
```

LangChain documents these exact composition rules. ([Docs by LangChain][4])

---

# 29. Why are wrap hooks reversed on the way out?

Think of normal Python function nesting.

Suppose:

```python
middleware1(
    middleware2(
        middleware3(
            model()
        )
    )
)
```

Execution enters:

```text
1
↓
2
↓
3
↓
MODEL
```

but returns:

```text
MODEL
 ↓
 3
 ↓
 2
 ↓
 1
```

Exactly like:

```python
try:
    result = handler(request)
finally:
    ...
```

This is why the first middleware is the outermost layer.

---

# 30. A concrete composition example

Suppose:

```python
middleware=[
    logging,
    authorization,
    retry,
]
```

Then model execution is conceptually:

```text
logging
   ↓
authorization
   ↓
retry
   ↓
MODEL
```

If the model fails:

```text
MODEL
  ↑
retry       ← catches/retries
  ↑
authorization
  ↑
logging
```

That's a powerful architectural pattern.

For example:

```text
logging
    outermost

authorization
    middle

retry
    closest to actual model
```

But there is no universal "correct" order. Order should reflect what you need each layer to observe and protect.

---

# 31. Multiple middleware and state conflicts

This gets more advanced.

Suppose two middleware layers return state updates:

```python
Command(update={"trace_layer": "inner"})
```

and:

```python
Command(update={"trace_layer": "outer"})
```

For non-reducer fields, LangChain's current composition rules result in the **outer middleware winning conflicts**. For reducer-managed fields such as `messages`, updates are combined according to the reducer. ([Docs by LangChain][4])

This matters especially when you create many middleware layers.

---

# 32. Why `messages` behave differently

The agent state contains:

```python
messages
```

with a message reducer.

Conceptually:

```python
{
    "messages": [new_message]
}
```

does not mean:

```text
replace all messages
```

Instead, the messages reducer combines them.

That's why an update such as:

```python
Command(
    update={
        "messages": [
            SystemMessage(...)
        ]
    }
)
```

adds a message rather than simply throwing away the existing conversation.

The current middleware documentation specifically explains that `Command` updates flow through graph reducers and that message updates are additive. ([Docs by LangChain][4])

---

# 33. Middleware state

Now we get to one of the most important concepts:

```text
state_schema
```

The agent has a state.

At minimum, current `AgentState` includes things such as:

```text
messages
jump_to
structured_response
```

with `messages` using a reducer. ([LangChain Reference][12])

You can extend that state.

For example:

```python
from typing_extensions import NotRequired
from langchain.agents.middleware import AgentState


class CustomState(AgentState):
    model_call_count: NotRequired[int]
    user_id: NotRequired[str]
```

Now middleware can use:

```python
state["model_call_count"]
```

---

# 34. What does `state_schema` actually do?

This is a subtle but important point.

`state_schema` does **not** mean:

> "Put values into my state."

It means:

> "This is the schema that describes the state fields this middleware expects/uses."

For example:

```python
class TrackingState(AgentState):
    model_call_count: NotRequired[int]
```

declares:

```text
model_call_count
```

as a valid state field.

You still need to supply or update its value.

For example:

```python
return {
    "model_call_count": 1
}
```

The current `create_agent()` API also supports a top-level `state_schema`, but the reference recommends keeping middleware-specific state extensions scoped to the middleware when possible. ([LangChain Reference][13])

That is a very good design principle.

---

# 35. Middleware-specific state

For example:

```python
class CounterState(AgentState):
    model_call_count: NotRequired[int]
```

Then:

```python
@after_model(state_schema=CounterState)
def count_model_call(
    state: CounterState,
    runtime,
):
    count = state.get("model_call_count", 0)

    return {
        "model_call_count": count + 1
    }
```

Then:

```python
@before_model(state_schema=CounterState, can_jump_to=["end"])
def enforce_limit(
    state: CounterState,
    runtime,
):
    count = state.get("model_call_count", 0)

    if count >= 10:
        return {
            "jump_to": "end"
        }

    return None
```

Now the two pieces cooperate through state:

```text
after_model
    ↓
count = 1

after_model
    ↓
count = 2

after_model
    ↓
count = 3

...

before_model
    ↓
count >= 10?
    ↓
jump_to = "end"
```

This is one of the most useful middleware patterns.

LangChain's current documentation demonstrates this exact general approach using a model-call counter. ([Docs by LangChain][4])

---

# 36. State versus context

This distinction is absolutely fundamental.

You now have two things:

```text
State
Context
```

They are **not the same**.

---

## State

Think:

> "What is happening inside this agent execution?"

Examples:

```text
messages
model_call_count
security_flags
workflow_status
temporary data
agent-specific counters
```

State belongs to the agent execution graph.

---

## Context

Think:

> "What external information/dependencies should this invocation have access to?"

Examples:

```text
user_id
user_name
tenant_id
database connection
request metadata
permissions
configuration
```

The current LangChain Runtime documentation describes runtime context as static invocation-scoped information such as user IDs, database connections and dependencies, and explicitly positions it as dependency injection for tools and middleware. ([Docs by LangChain][14])

---

# 37. `context_schema`

You can define:

```python
from dataclasses import dataclass


@dataclass
class Context:
    user_id: str
    user_name: str
```

Then:

```python
agent = create_agent(
    model="google_genai:gemini-3.6-flash",
    tools=[],
    context_schema=Context,
)
```

And at invocation time:

```python
agent.invoke(
    {
        "messages": [
            {
                "role": "user",
                "content": "Hello",
            }
        ]
    },
    context=Context(
        user_id="user-123",
        user_name="Bhargav",
    ),
)
```

That is current API design. ([Docs by LangChain][14])

---

# 38. Why context shouldn't just be state

You might ask:

> Why not put `user_id` directly in state?

You technically can in some architectures, but context solves a different problem.

Suppose:

```python
user_id = "user-123"
```

is a property of the current invocation.

You generally don't want the model conversation to treat that as ordinary conversational state.

Similarly:

```python
db_connection
```

should not become part of messages.

And:

```python
permission_checker
```

certainly isn't something you want the model generating.

Context is therefore excellent for:

```text
dependencies
identity
configuration
authorization information
request-scoped resources
```

---

# 39. Accessing context in middleware

In node-style middleware:

```python
@before_model
def inspect_user(state, runtime):
    user_id = runtime.context.user_id

    print("Current user:", user_id)

    return None
```

The Runtime documentation explicitly shows middleware accessing:

```python
runtime.context
```

inside `before_model` and `after_model`. ([Docs by LangChain][14])

---

# 40. Accessing context inside `wrap_model_call`

For wrap-style hooks, you get runtime through the request:

```python
@wrap_model_call
def inspect_user(request, handler):

    user_id = request.runtime.context.user_id

    return handler(request)
```

The current docs explicitly distinguish these two access patterns:

```text
node-style:
    runtime

wrap-style:
    request.runtime
```

([Docs by LangChain][14])

---

# 41. Accessing context inside `wrap_tool_call`

Same idea:

```python
@wrap_tool_call
def authorize(request, handler):

    user_id = request.runtime.context.user_id

    ...
```

The current `ToolCallRequest` gives middleware access to runtime, state, tool call and tool. ([LangChain Reference][10])

---

# 42. `Runtime` and `ToolRuntime` are different

Since you recently studied Runtime/ToolRuntime, connect that knowledge here.

### Middleware

Uses:

```python
Runtime[Context]
```

### Tools

Can use:

```python
ToolRuntime[Context]
```

`ToolRuntime` includes tool-specific information such as:

```text
state
context
tool_call_id
config
store
stream_writer
tools
```

The current reference explicitly distinguishes `ToolRuntime` from the `Runtime` injected into graph nodes and middleware. ([LangChain Reference][15])

So mentally:

```text
middleware
      ↓
   Runtime
      ↓
 context / store / execution info / ...

tool
      ↓
 ToolRuntime
      ↓
 state / context / tool_call_id / store / ...
```

---

# 43. `jump_to`: controlling the agent graph

Now we reach control flow.

Middleware can return:

```python
{
    "jump_to": "end"
}
```

to redirect the agent.

Current supported destinations are:

```text
"end"
"tools"
"model"
```

for hooks configured to allow those jumps. ([Docs by LangChain][4])

---

# 44. What does `jump_to="end"` mean?

Suppose:

```text
User
 ↓
before_model
 ↓
security check
 ↓
BLOCK
```

You can return:

```python
{
    "messages": [
        AIMessage(
            content="I cannot process this request."
        )
    ],
    "jump_to": "end",
}
```

Then:

```text
before_model
     ↓
jump_to=end
     ↓
skip remaining agent loop
     ↓
after_agent
     ↓
finish
```

LangChain's current documentation demonstrates exactly this early-termination pattern. ([Docs by LangChain][4])

---

# 45. Why `can_jump_to` exists

You will often see:

```python
@before_model(can_jump_to=["end"])
```

Why specify it?

Because middleware is part of a graph.

LangChain wants the possible control-flow destinations to be known/configured.

Example:

```python
@before_model(can_jump_to=["end"])
```

means:

```text
This middleware is allowed to route execution to END.
```

For a class:

```python
from langchain.agents.middleware import (
    AgentMiddleware,
    hook_config,
)


class SecurityMiddleware(AgentMiddleware):

    @hook_config(can_jump_to=["end"])
    def before_model(self, state, runtime):
        ...
```

The current API uses `hook_config` for class-based hook routing configuration. ([LangChain Reference][16])

---

# 46. A practical early-stop example

```python
from typing import Any

from langchain.agents.middleware import (
    before_model,
    AgentState,
)
from langchain.messages import AIMessage
from langgraph.runtime import Runtime


@before_model(can_jump_to=["end"])
def message_limit(
    state: AgentState,
    runtime: Runtime,
) -> dict[str, Any] | None:

    if len(state["messages"]) >= 50:
        return {
            "messages": [
                AIMessage(
                    content="Conversation limit reached."
                )
            ],
            "jump_to": "end",
        }

    return None
```

The important conceptual distinction is:

```text
return None
```

means:

```text
continue normally
```

while:

```python
{
    "jump_to": "end"
}
```

means:

```text
change graph control flow
```

---

# 47. `jump_to` is not ordinary business state

This is subtle.

Don't think:

```python
state["jump_to"] = "end"
```

means:

> "I have permanently stored that the agent is finished."

Instead think:

> "This invocation currently needs to transition to this graph destination."

The current `AgentState` definition marks `jump_to` as ephemeral/private state. ([LangChain Reference][12])

So:

```text
jump_to = control-flow metadata
```

not:

```text
application data
```

---

# 48. `wrap_model_call` and state updates

There is one advanced difference you should know.

Node-style hooks can simply return:

```python
{
    "counter": 5
}
```

But wrap-style model middleware returns a model response.

So when a `wrap_model_call` also needs to update state, current LangChain provides:

```text
ExtendedModelResponse
+
Command
```

Example:

```python
from langgraph.types import Command
from langchain.agents.middleware import ExtendedModelResponse
```

Conceptually:

```python
response = handler(request)

return ExtendedModelResponse(
    model_response=response,
    command=Command(
        update={
            "last_model_call_tokens": 150
        }
    ),
)
```

The current docs explicitly describe `ExtendedModelResponse` as the mechanism for returning a model response plus a state-update `Command`. ([Docs by LangChain][4])

---

# 49. Why does `wrap_tool_call` work differently?

A tool wrapper can directly return:

```text
ToolMessage
```

or:

```text
Command
```

Current API:

```python
ToolMessage | Command
```

That means:

```python
return ToolMessage(...)
```

is enough for a normal tool result.

Or:

```python
return Command(
    update={...}
)
```

for more advanced graph state/control operations. ([LangChain Reference][10])

---

# 50. Decorator middleware versus class-based middleware

You have two modern styles.

## Decorator

Best for:

```text
one hook
small logic
simple middleware
quick prototypes
```

Example:

```python
@before_model
def logger(state, runtime):
    print("before model")
    return None
```

The current documentation recommends decorator-based middleware for quick/single-hook cases. ([Docs by LangChain][4])

---

## Class

Best for:

```text
multiple hooks
configuration
reusable middleware
sync + async implementations
state_schema
additional tools
complex behavior
```

Example:

```python
from typing import Any

from langchain.agents.middleware import (
    AgentMiddleware,
    AgentState,
)
from langgraph.runtime import Runtime


class LoggingMiddleware(AgentMiddleware):

    def before_model(
        self,
        state: AgentState,
        runtime: Runtime,
    ) -> dict[str, Any] | None:

        print("Model starting")
        return None

    def after_model(
        self,
        state: AgentState,
        runtime: Runtime,
    ) -> dict[str, Any] | None:

        print("Model finished")
        return None
```

Then:

```python
agent = create_agent(
    model="google_genai:gemini-3.6-flash",
    middleware=[
        LoggingMiddleware()
    ],
)
```

The current docs specifically recommend classes for multiple hooks, configuration and reusable middleware, and note that classes can provide sync and async implementations. ([Docs by LangChain][4])

---

# 51. A realistic class-based middleware

Now let's combine several ideas.

```python
from typing import Any
from typing_extensions import NotRequired

from langchain.agents.middleware import (
    AgentMiddleware,
    AgentState,
    hook_config,
)
from langgraph.runtime import Runtime


class RequestState(AgentState):
    model_call_count: NotRequired[int]


class ModelLimitMiddleware(
    AgentMiddleware[RequestState]
):
    state_schema = RequestState

    @hook_config(can_jump_to=["end"])
    def before_model(
        self,
        state: RequestState,
        runtime: Runtime,
    ) -> dict[str, Any] | None:

        count = state.get(
            "model_call_count",
            0,
        )

        if count >= 10:
            return {
                "jump_to": "end"
            }

        return None

    def after_model(
        self,
        state: RequestState,
        runtime: Runtime,
    ) -> dict[str, Any] | None:

        count = state.get(
            "model_call_count",
            0,
        )

        return {
            "model_call_count": count + 1
        }
```

The lifecycle becomes:

```text
before_model
    ↓
count < 10 ?
    ↓
MODEL
    ↓
after_model
    ↓
count += 1
```

Next iteration:

```text
before_model
    ↓
count < 10 ?
```

and eventually:

```text
count >= 10
    ↓
jump_to=end
```

This is a clean example of state + hooks + graph control working together.

---

# 52. One very important modern detail: async middleware

Current middleware supports asynchronous versions such as:

```text
abefore_agent
abefore_model
aafter_model
aafter_agent
awrap_model_call
awrap_tool_call
```

The API reference explicitly lists asynchronous counterparts. ([LangChain Reference][17])

This matters for your FastAPI backend.

For example:

```python
class AuditMiddleware(AgentMiddleware):

    async def abefore_model(
        self,
        state,
        runtime,
    ):
        await write_audit_event(...)
        return None
```

and:

```python
async def awrap_tool_call(
    self,
    request,
    handler,
):
    ...
    result = await handler(request)
    ...
    return result
```

---

# 53. A very important async pitfall

The current implementation explicitly warns about defining only async wrap methods and then invoking the agent synchronously.

For example, if you only implement:

```python
async def awrap_tool_call(...):
    ...
```

but then use:

```python
agent.invoke(...)
```

or:

```python
agent.stream(...)
```

you can hit a `NotImplementedError`.

Either:

```text
provide the sync hook
```

or:

```text
use ainvoke()/astream()
```

The current LangChain source explicitly documents this behavior. ([GitHub][18])

For your FastAPI architecture, where you are already working heavily with async code, this is particularly relevant.

---

# 54. The modern replacement for `modify_model_request`

This deserves its own section because you specifically mentioned it.

You may encounter older material like:

```python
class SomeMiddleware(AgentMiddleware):

    def modify_model_request(
        self,
        request,
        state,
    ):
        ...
```

Do **not** learn that as the current API.

The LangChain 1.0 alpha blog described `modify_model_request` as part of the early middleware design. ([LangChain][19])

The released v1 API instead uses:

```python
wrap_model_call(
    request,
    handler,
)
```

That is much more powerful because it gives you:

```text
request modification
+
retry
+
short-circuit
+
response processing
```

Current `wrap_model_call` is explicitly documented as the released hook. ([LangChain Reference][20])

So remember:

```text
OLD / alpha concept:
modify_model_request

CURRENT:
wrap_model_call
```

---

# 55. There is no `before_tool`

You specifically called this out, and you're correct.

Current `AgentMiddleware` does **not** define:

```python
before_tool
```

or:

```python
after_tool
```

The current reference lists `wrap_tool_call` instead. ([LangChain Reference][2])

In fact, there was a feature request to add these observational hooks, and it was closed as **not planned**. ([GitHub][21])

So don't build your architecture around:

```python
before_tool()
after_tool()
```

That would be teaching the wrong API.

Use:

```python
wrap_tool_call()
```

and put your before/after logic around:

```python
handler(request)
```

---

# 56. `wrap_tool_call` can also modify the tool call

This is another powerful feature.

Suppose the model produces:

```python
{
    "name": "search",
    "args": {
        "query": "something"
    }
}
```

Middleware can create a modified request:

```python
modified_call = {
    **request.tool_call,
    "args": {
        **request.tool_call["args"],
        "query": sanitize(
            request.tool_call["args"]["query"]
        ),
    },
}

return handler(
    request.override(
        tool_call=modified_call
    )
)
```

The current implementation supports modifying the tool request before execution, as well as retrying, caching and short-circuiting. ([GitHub][18])

So you can think of `wrap_tool_call` as:

```text
tool request firewall + interceptor + executor wrapper
```

---

# 57. The complete "security gate" pattern

For your kind of enterprise agent architecture, this pattern is especially important:

```python
from langchain.agents.middleware import wrap_tool_call
from langchain.messages import ToolMessage


@wrap_tool_call
def security_gate(request, handler):

    tool_name = request.tool_call["name"]

    user_role = request.runtime.context.user_role

    allowed_tools = {
        "employee": {
            "search_docs",
            "get_weather",
        },
        "admin": {
            "search_docs",
            "get_weather",
            "delete_document",
        },
    }

    allowed = allowed_tools.get(
        user_role,
        set(),
    )

    if tool_name not in allowed:
        return ToolMessage(
            content=(
                f"Tool '{tool_name}' is not "
                "permitted for this user."
            ),
            name=tool_name,
            tool_call_id=request.tool_call["id"],
            status="error",
        )

    return handler(request)
```

Notice the architecture:

```text
User identity
      ↓
Runtime context
      ↓
security middleware
      ↓
tool requested
      ↓
authorization decision
    /       \
  allow     deny
   ↓          ↓
handler     ToolMessage(error)
   ↓
tool
```

This is a much stronger pattern than:

```text
"Please don't use dangerous tools"
```

inside the system prompt.

---

# 58. Middleware ordering in a real stack

Suppose you have:

```python
middleware=[
    AuditMiddleware(),
    SecurityMiddleware(),
    ModelRetryMiddleware(),
    ToolRetryMiddleware(),
]
```

Don't think of this as simply:

```text
1
2
3
4
```

Think of it as layers.

For a model call:

```text
Audit
  ↓
Security
  ↓
Retry
  ↓
MODEL
```

For the return:

```text
MODEL
  ↑
Retry
  ↑
Security
  ↑
Audit
```

For tools, all relevant `wrap_tool_call` middleware form the equivalent nested chain.

The current docs explicitly state:

```text
before → first to last
wrap  → first is outermost
after → last to first
```

([Docs by LangChain][4])

---

# 59. What if a middleware doesn't define a particular hook?

That's completely normal.

Suppose:

```python
class LoggingMiddleware(AgentMiddleware):

    def before_model(...):
        ...
```

and nothing else.

It doesn't need to implement:

```text
before_agent
after_model
wrap_model_call
wrap_tool_call
after_agent
```

You only implement the lifecycle points you need.

That is one of the big advantages of middleware composition.

---

# 60. When should you use which hook?

A useful decision table:

| Requirement                     | Hook                                             |
| ------------------------------- | ------------------------------------------------ |
| Run once when invocation starts | `before_agent`                                   |
| Run before every model call     | `before_model`                                   |
| Change model                    | `wrap_model_call`                                |
| Change prompt                   | `dynamic_prompt` / `wrap_model_call`             |
| Change tools sent to model      | `wrap_model_call`                                |
| Change messages sent to model   | `wrap_model_call`                                |
| Retry model                     | `wrap_model_call` / prebuilt retry middleware    |
| Cache model result              | `wrap_model_call`                                |
| Skip model entirely             | `wrap_model_call`                                |
| Inspect model response          | `after_model`                                    |
| Update state after model        | `after_model`                                    |
| End agent early                 | node hook + `jump_to="end"`                      |
| Inspect tool call               | `wrap_tool_call`                                 |
| Modify tool arguments           | `wrap_tool_call`                                 |
| Retry tool                      | `wrap_tool_call` / prebuilt retry middleware     |
| Cache tool result               | `wrap_tool_call`                                 |
| Deny tool                       | `wrap_tool_call` → `ToolMessage(status="error")` |
| Run once after whole agent      | `after_agent`                                    |

---

# 61. A complete mental model

At this point, I want you to visualize the entire system like this:

```text
                 create_agent()
                       │
                       ▼
                ┌─────────────┐
                │ before_agent│
                └──────┬──────┘
                       │
                       ▼
              ┌─────────────────┐
              │   AGENT LOOP    │
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
              │  before_model   │
              └────────┬────────┘
                       │
                       ▼
        ┌───────────────────────────────┐
        │        wrap_model_call        │
        │                               │
        │   middleware 1                │
        │      ↓                        │
        │   middleware 2                │
        │      ↓                        │
        │   middleware 3                │
        │      ↓                        │
        │     MODEL                     │
        │                               │
        └───────────────┬───────────────┘
                        │
                        ▼
                ┌────────────┐
                │ after_model│
                └─────┬──────┘
                      │
               tool calls?
                /         \
              no           yes
              │             │
              │             ▼
              │     ┌─────────────────┐
              │     │ wrap_tool_call  │
              │     │                 │
              │     │ auth            │
              │     │ logging         │
              │     │ retry           │
              │     │ cache           │
              │     │        ↓        │
              │     │      TOOL       │
              │     └────────┬────────┘
              │              │
              │              ▼
              │         tool result
              │              │
              │              └───────┐
              │                      │
              └──────────────────────┘
                       │
                       ▼
                 before_model
                       │
                      ...
                       │
                       ▼
                 after_agent
                       │
                       ▼
                      END
```

That is the mental model I recommend keeping in your head.

---

# 62. Current vs old/deprecated — what you should actually learn

Here is the important modernization table.

| Older/old material                       | Current approach                                  |
| ---------------------------------------- | ------------------------------------------------- |
| Legacy `initialize_agent()`              | `create_agent()`                                  |
| Legacy `AgentExecutor` architecture      | `create_agent()` for new v1 agent applications    |
| LangGraph `create_react_agent()`         | `create_agent()`                                  |
| Alpha `modify_model_request`             | `wrap_model_call`                                 |
| `before_tool`                            | No such current hook; use `wrap_tool_call`        |
| `after_tool`                             | No such current hook; use `wrap_tool_call`        |
| Direct mutation of model request         | `request.override(...)`                           |
| `request.override(system_prompt=...)`    | `request.override(system_message=...)`            |
| Manually implementing common retry logic | Prefer prebuilt retry middleware when appropriate |

Current references explicitly mark legacy `initialize_agent`/classic agent patterns and LangGraph `create_react_agent` as deprecated in favor of `create_agent`. ([LangChain Reference][22])

The modern `create_agent()` reference is the API you should build your Module 44 knowledge around. ([LangChain Reference][13])

---

# 63. One subtle modern point: don't overbuild custom middleware

You specifically prefer established libraries and premade components.

That is exactly the right instinct here.

Current LangChain already provides middleware such as:

```text
SummarizationMiddleware
HumanInTheLoopMiddleware
ModelCallLimitMiddleware
ToolCallLimitMiddleware
ModelFallbackMiddleware
PIIMiddleware
TodoListMiddleware
ToolRetryMiddleware
ModelRetryMiddleware
ContextEditingMiddleware
LLMToolSelectorMiddleware
```

and more. ([LangChain Reference][2])

So your decision tree should generally be:

```text
Does LangChain already provide the behavior?
             │
        yes  │  no
        ↓         ↓
   use built-in   custom middleware
```

Don't build:

```python
MyOwnRetryMiddleware
```

just because you can, when a maintained `ModelRetryMiddleware` already solves the problem.

Build custom middleware when your actual business policy is unique.

---

# 64. An ideal architecture for learning

I recommend learning middleware in this order:

### Level 1 — observation

Learn:

```python
before_agent
before_model
after_model
after_agent
```

without changing anything.

You should be able to answer:

```text
When does this execute?
How many times?
What does it receive?
What can it return?
```

---

### Level 2 — state

Learn:

```python
state_schema
```

and:

```python
return {"counter": ...}
```

Understand reducers.

---

### Level 3 — runtime context

Learn:

```python
context_schema
```

and:

```python
runtime.context
```

Understand why:

```text
state ≠ context
```

---

### Level 4 — control flow

Learn:

```python
jump_to
can_jump_to
hook_config
```

and understand:

```text
model
tools
end
```

---

### Level 5 — model interception

Learn:

```python
wrap_model_call
ModelRequest
handler
request.override(...)
```

This is where middleware becomes extremely powerful.

---

### Level 6 — tool interception

Learn:

```python
wrap_tool_call
ToolCallRequest
handler
ToolMessage
```

especially:

```text
authorization
retry
validation
caching
request modification
denial
```

---

### Level 7 — composition

Finally master:

```python
middleware=[
    A(),
    B(),
    C(),
]
```

and reason about:

```text
first → last
nested
last → first
```

That is where you'll move from "I know the APIs" to actually understanding middleware architecture.

---

# 65. A very small complete example

Here's a compact example that combines the core concepts without introducing unnecessary complexity:

```python
from dataclasses import dataclass
from typing import Any
from typing_extensions import NotRequired

from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    AgentState,
    after_agent,
    after_model,
    before_agent,
    before_model,
    dynamic_prompt,
    wrap_model_call,
    wrap_tool_call,
    ModelRequest,
)
from langchain.messages import ToolMessage
from langgraph.runtime import Runtime


# -------------------------
# Runtime context
# -------------------------

@dataclass
class Context:
    user_id: str
    user_role: str
    user_name: str


# -------------------------
# Custom agent state
# -------------------------

class MyState(AgentState):
    model_calls: NotRequired[int]


# -------------------------
# before_agent
# -------------------------

@before_agent
def start_log(
    state: AgentState,
    runtime: Runtime[Context],
) -> None:

    print(
        f"Starting agent for {runtime.context.user_id}"
    )


# -------------------------
# before_model
# -------------------------

@before_model(state_schema=MyState)
def count_before_model(
    state: MyState,
    runtime: Runtime[Context],
) -> dict[str, Any] | None:

    print("About to call model")

    return None


# -------------------------
# dynamic prompt
# -------------------------

@dynamic_prompt
def user_prompt(
    request: ModelRequest,
) -> str:

    context = request.runtime.context

    return (
        "You are an enterprise assistant.\n"
        f"User: {context.user_name}\n"
        f"Role: {context.user_role}\n"
    )


# -------------------------
# wrap_model_call
# -------------------------

@wrap_model_call
def log_model(
    request,
    handler,
):

    print("MODEL START")

    response = handler(request)

    print("MODEL END")

    return response


# -------------------------
# after_model
# -------------------------

@after_model(state_schema=MyState)
def model_finished(
    state: MyState,
    runtime: Runtime[Context],
) -> dict[str, Any]:

    count = state.get(
        "model_calls",
        0,
    )

    return {
        "model_calls": count + 1
    }


# -------------------------
# wrap_tool_call
# -------------------------

@wrap_tool_call
def authorize_tool(
    request,
    handler,
):

    tool_name = request.tool_call["name"]

    role = request.runtime.context.user_role

    if (
        tool_name == "delete_file"
        and role != "admin"
    ):
        return ToolMessage(
            content=(
                "Permission denied."
            ),
            name=tool_name,
            tool_call_id=request.tool_call["id"],
            status="error",
        )

    return handler(request)


# -------------------------
# after_agent
# -------------------------

@after_agent
def finish_log(
    state,
    runtime,
):

    print(
        "Agent execution completed"
    )

    return None


# -------------------------
# Agent
# -------------------------

agent = create_agent(
    model="google_genai:gemini-3.6-flash",
    tools=[],
    context_schema=Context,
    middleware=[
        start_log,
        count_before_model,
        user_prompt,
        log_model,
        model_finished,
        authorize_tool,
        finish_log,
    ],
)
```

Notice how the responsibilities are separated:

```text
start_log
    invocation-level

count_before_model
    per-model lifecycle

user_prompt
    prompt customization

log_model
    model interception

model_finished
    post-model state update

authorize_tool
    execution-time authorization

finish_log
    invocation finalization
```

That separation is exactly what good middleware architecture should look like.

---

# 66. The biggest conceptual distinction to memorize

I would memorize these six sentences:

```text
before_agent
    = before the entire invocation

before_model
    = before each model step

wrap_model_call
    = control the actual model call

after_model
    = after each model step

wrap_tool_call
    = control the actual tool execution

after_agent
    = after the entire invocation
```

And then:

```text
state
    = execution data

context
    = invocation dependencies/context

Runtime
    = access to context and runtime facilities

ModelRequest
    = actual request going to the model

ToolCallRequest
    = actual tool execution request

handler
    = "continue to the real operation"
```

That mental model will carry you through most of the rest of LangChain's agent architecture.

---

# 67. The "middleware formula"

You can reduce almost every middleware implementation to this:

### Node-style

```python
def hook(state, runtime):
    inspect_or_update()
    return state_update_or_none
```

### Model wrapper

```python
def wrap_model(request, handler):
    modify_or_check_request()

    response = handler(request)

    modify_or_check_response()

    return response
```

### Tool wrapper

```python
def wrap_tool(request, handler):
    authorize_or_modify()

    result = handler(request)

    inspect_or_transform_result()

    return result
```

That is the core of Module 44.

---

# 68. Final picture: where this sits in your overall learning path

You already studied:

```text
PHASE 1
Models + prompts

PHASE 2
Ingestion

PHASE 3
Embeddings + vector stores

PHASE 4
RAG

PHASE 5
Tools + MCP

PHASE 6
Agents
```

You've now studied:

```text
Module 42
create_agent fundamentals

Module 43
Agent streaming

Module 44
Middleware
```

The progression is actually very logical:

```text
Tools
   ↓
Agent decides when to use tools
   ↓
Streaming lets you observe execution
   ↓
Middleware lets you CONTROL execution
```

So middleware is the point where you move from:

> **"I can build an agent."**

to:

> **"I can engineer the behavior of an agent system."**

That distinction is extremely important for production systems.

---

## Module 44 — the knowledge checklist

Before considering this module mastered, you should be able to explain, without looking at documentation:

```text
□ What is middleware?

□ Why is middleware needed around create_agent?

□ Node-style vs wrap-style hooks?

□ before_agent vs before_model?

□ wrap_model_call vs before_model?

□ Why does wrap_model_call receive handler?

□ What happens if handler is called 0 times?

□ What happens if handler is called multiple times?

□ How does request.override() work?

□ What is dynamic_prompt?

□ after_model vs after_agent?

□ Why is there no before_tool / after_tool?

□ How does wrap_tool_call replace both?

□ What is ToolCallRequest?

□ How do you deny a tool call?

□ Why is tool_call_id important?

□ Why use ToolMessage(status="error")?

□ What is state_schema?

□ What is context_schema?

□ State vs context?

□ runtime.context vs request.runtime.context?

□ What is jump_to?

□ What does jump_to="end" do?

□ Why do we need can_jump_to?

□ What is AgentMiddleware?

□ Decorator vs class middleware?

□ How does middleware composition work?

□ Why are before hooks first→last?

□ Why are after hooks last→first?

□ Why are wrap hooks nested?

□ What happens with conflicting state updates?

□ What is ExtendedModelResponse?

□ Why use Command for wrap-model state updates?

□ Which old APIs should no longer be learned?
```

Once those are clear, you have the conceptual foundation needed for the next layer of agent engineering: **guardrails, retries/fallbacks, dynamic models/tools, stateful middleware, human-in-the-loop, and eventually Deep Agents' middleware stack**. Current LangChain already exposes many of those as maintained middleware components rather than expecting you to implement everything yourself. ([LangChain Reference][2])

[1]: https://docs.langchain.com/oss/python/langchain/agents "Agents - Docs by LangChain"
[2]: https://reference.langchain.com/python/langchain/middleware?utm_source=chatgpt.com "middleware | langchain | LangChain Reference"
[3]: https://docs.langchain.com/oss/python/langchain/middleware "Overview - Docs by LangChain"
[4]: https://docs.langchain.com/oss/python/langchain/middleware/custom "Custom middleware - Docs by LangChain"
[5]: https://reference.langchain.com/python/langchain/agents/middleware/types/before_model?utm_source=chatgpt.com "before_model | langchain | LangChain Reference"
[6]: https://reference.langchain.com/python/langchain/agents/middleware/types/ModelRequest/override?utm_source=chatgpt.com "override | langchain | LangChain Reference"
[7]: https://reference.langchain.com/python/langchain/agents/middleware/types/AgentMiddleware/wrap_model_call?utm_source=chatgpt.com "wrap_model_call | langchain | LangChain Reference"
[8]: https://reference.langchain.com/python/langchain/agents/middleware/model_retry?utm_source=chatgpt.com "model_retry | langchain | LangChain Reference"
[9]: https://reference.langchain.com/python/langchain/agents/middleware/types/dynamic_prompt?utm_source=chatgpt.com "dynamic_prompt | langchain | LangChain Reference"
[10]: https://reference.langchain.com/python/langchain/agents/middleware/types/AgentMiddleware/wrap_tool_call?utm_source=chatgpt.com "wrap_tool_call | langchain | LangChain Reference"
[11]: https://reference.langchain.com/python/langchain/agents/middleware/types/after_agent?utm_source=chatgpt.com "after_agent | langchain | LangChain Reference"
[12]: https://reference.langchain.com/python/langchain/agents/middleware/types/AgentState?utm_source=chatgpt.com "AgentState | langchain | LangChain Reference"
[13]: https://reference.langchain.com/python/langchain/agents/factory/create_agent?utm_source=chatgpt.com "create_agent | langchain | LangChain Reference"
[14]: https://docs.langchain.com/oss/python/langchain/runtime "Runtime - Docs by LangChain"
[15]: https://reference.langchain.com/python/langgraph.prebuilt/tool_node/ToolRuntime?utm_source=chatgpt.com "ToolRuntime | langgraph.prebuilt | LangChain Reference"
[16]: https://reference.langchain.com/python/langchain/agents/middleware?utm_source=chatgpt.com "middleware | langchain | LangChain Reference"
[17]: https://reference.langchain.com/python/langchain/agents/middleware/types/AgentMiddleware?utm_source=chatgpt.com "AgentMiddleware | langchain | LangChain Reference"
[18]: https://github.com/langchain-ai/langchain/blob/master/libs/langchain_v1/langchain/agents/middleware/types.py?utm_source=chatgpt.com "langchain/libs/langchain_v1/langchain/agents/middleware/types.py at master · langchain-ai/langchain · GitHub"
[19]: https://www.langchain.com/blog/agent-middleware?utm_source=chatgpt.com "Agent Middleware"
[20]: https://reference.langchain.com/python/langchain/agents/middleware/types/wrap_model_call?utm_source=chatgpt.com "wrap_model_call | langchain | LangChain Reference"
[21]: https://github.com/langchain-ai/langchain/issues/33441?utm_source=chatgpt.com "Add observational hooks (before_tool/after_tool) for tool calls in AgentMiddleware · Issue #33441 · langchain-ai/langchain · GitHub"
[22]: https://reference.langchain.com/python/langchain-classic/agents/initialize?utm_source=chatgpt.com "initialize | langchain_classic | LangChain Reference"
