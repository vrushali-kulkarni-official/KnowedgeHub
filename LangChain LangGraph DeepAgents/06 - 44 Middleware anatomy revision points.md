# Middleware

### used of
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

## Middleware Categories:
- Node-style hooks
	
``` text
before_agent
before_model
after_model
after_agent
```

For example:
```python
@before_model
def log_model_start(state, runtime):
    print("Model is about to run")
    return None
``` 

- Wrap-style hooks

```text
wrap_model_call
wrap_tool_call
```

For example:
```python
def middleware(request, handler):
    # before
    result = handler(request)
    # after
    return result
```

## Middleware lifecycle

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



## Hook #1 — `before_agent`

```python
@before_agent
def initialize_request(
    state: AgentState,
    runtime: Runtime,
) -> dict[str, Any] | None:
    print("Agent invocation started")
    return None
```


## 6. Hook #2 — `before_model`

Generally has `AgentState` & `Runtime`

``` python

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

is ideal for:

```text
logging
validation
state counters
conditional routing
```


## Hook #3 — `wrap_model_call`

Generally has `request` and `handler`

```python
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



---

## What is request

Think of request as:

> "Here is everything you need to know about the operation that is about to happen."

LangChain's ModelRequest contains things such as:

``` Python
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


## What is `handler`?

`handler` means:
> "Continue the normal operation."
or in simple words:
> "I'm done with my part. Please continue."

So `handler` is basically the **next step in the pipeline**.

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

---

## Cache middleware Short Circuit

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



---

## What is AgentState or simply State

AgentState is memory of its current execution

In Simple words:
> **State = information that belongs to the agent's ongoing computation.**

Conversation messages is just one part of state.

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

Agent State normally contains:
```
messages
current task status
tool results
intermediate values
custom agent variables
structured response
```


## Runtime

A very easy way to think about it:
> **"What environment/context is this execution happening in?"*

So:
> **Runtime is the environment surrounding the current agent execution.**

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

## Before Model vs Wrap Model Call

#### Before Model

You are operating at the **agent state/lifecycle level**.
``` text
state
runtime
```

used for:
``` text
logging
validation
state counters
conditional routing
```


#### wrap_model_call

You are operating at the **actual model-call request level**.
``` text
request
handler
```

used for:
```
change model
change prompt
change tools
change messages
retry
fallback
cache
short-circuit
```


--- 

## Modifying request `ModelRequest.override()`

`ModelRequest.override()` returns a **new request** and follows an immutable pattern rather than modifying the original request in place.

can override:
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

---

### Dynamic prompt: `@dynamic_prompt`


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

```python

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


---


## Hook #4 — `after_model`

Runs after the model has returned its result.

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


## Hook #5 — `wrap_tool_call

tool equivalent of `wrap_model_call

> There is no separate `before_tool` or `after_tool
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

It gives you access to:

```text
request.tool_call
request.tool
request.state
request.runtime
```

So you can inspect:

```python
tool_name = request.tool_call["name"]
arguments = request.tool_call["args"]
call_id = request.tool_call["id"]
```

---

## Hook #6 — `after_agent`

This runs once after the agent finishes execution.

```python
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

---

## How multiple middlewares stack

The current LangChain execution rules are:
First → last

For Example:
```
middleware=[
    middleware1,
    middleware2,
    middleware3,
]
```

Then First → last is:
```text
middleware1
middleware2
middleware3
```






```python
agent = create_agent(
    model=...,
    tools=...,
    middleware=[
        logging_middleware,      # outermost
        security_middleware,
        retry_middleware,        # innermost
    ]
)
```

LangChain nests them like Russian dolls (onion layers):

```
logging → security → retry → real model/tool → retry → security → logging
```


---

## Complete lifecycle

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

## jump_to`: controlling the agent graph

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

#### can_jump_to

means:
```text
This middleware is allowed to route execution to END.
```

``` Python
@before_model(can_jump_to=["end"])
```

For example:
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

The actual jump takes place using "jump_to" and not using "can_jump_to":

So:

```python
{
    "jump_to": "end"
}
```

means:

```text
change graph control flow
```

But Remember jump_to and can_jump_to is used to control-flow and not application data:

```text
jump_to = control-flow metadata
```

not:

```text
application data
```

---

## ExtendedModelResponse and Command

`ExtendedModelResponse` as the mechanism for returning a model response plus a state-update 

state-update are sent via `Command`

For Example:

```python
response = handler(request)

return ExtendedModelResponse(
    model_response=response,
    command=Command(
        update={last_model_call_tokens": 150
        }
    ),
)
```

---

## Async Trap

you can use:
```text
abefore_agent
abefore_model
aafter_model
aafter_agent
awrap_model_call
awrap_tool_call
```

but you have to also use Async invocation:
```
use ainvoke()/astream()
```
or else if you do:
```
use invoke()/stream()
```
then you can hit a `NotImplementedError'