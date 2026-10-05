# Custom Middleware

---

## Decorator vs class-based middleware

#### A. Decorator-based:

```python
from langchain.agents.middleware import before_model

@before_model
def log_request(state, runtime):
    print("model is about to run")
    return None
```

use when you have:
```text
one hook
simple behavior
no configuration
```

#### Class-based middleware: 

```python

from langchain.agents.middleware import AgentMiddleware

class AuditMiddleware(AgentMiddleware):

    def before_model(self, state, runtime):
        ...

    def after_model(self, state, runtime):
        ...

    def after_agent(self, state, runtime):
        ...
```

```text
multiple hooks
configuration
state
sync + async versions
reusable behavior
constructor parameters
```


## Agent State

```text
Agent State
────────────────────────────
messages
structured_response
run_input_tokens
run_output_tokens
run_total_tokens
run_cost_usd
────────────────────────────
```



## State

> information produced or accumulated during agent execution.

Examples:

```text
messages
token counters
tool results
agent flags
temporary workflow state
```


## Context

> trusted information supplied to the execution from the outside.

Examples:

```text
user_id
tenant_id
organization
user role
subscription plan
permissions
database dependency
application configuration
```


## @dynamic_prompt

 `@dynamic_prompt` can be used for for generating a model system prompt dynamically from the `ModelRequest:

```python
from dataclasses import dataclass

from langchain.agents import create_agent
from langchain.agents.middleware import dynamic_prompt, ModelRequest


@dataclass
class AgentContext:
    tenant_id: str
    user_role: str


@dynamic_prompt
def tenant_system_prompt(request: ModelRequest) -> str:
    context = request.runtime.context

    return (
        "You are an enterprise assistant.\n"
        f"Tenant: {context.tenant_id}\n"
        f"User role: {context.user_role}\n"
    )


agent = create_agent(
    model=model,
    tools=tools,
    middleware=[tenant_system_prompt],
    context_schema=AgentContext,
)
```


## system_prompt  vs system_message

`system_prompt` as deprecated for request overrides 

Now prefers `system_message`


So when modifying the system prompt, use:

```python
request.override(
    system_message=...
)
```

not:

```python
request.override(
    system_prompt=...
)
```


## content_blocks

The current custom middleware documentation explicitly recommends preserving existing structure by working with `content_blocks`

So instead of assuming:

```python
request.system_message.content
```

is always a simple string, modern middleware should generally work with:

```python
request.system_message.content_blocks
```

For example:

```python
from langchain.messages import SystemMessage


new_content = list(
    request.system_message.content_blocks
)

new_content.append(
    {
        "type": "text",
        "text": "Additional tenant context."
    }
)

new_system_message = SystemMessage(
    content=new_content
)

return handler(
    request.override(
        system_message=new_system_message
    )
)
```

---

## Hitting Database for Agent prompt:

instead of hitting the DB again and again:
```python
@dynamic_prompt
def tenant_prompt(request):
    return database.get_tenant_prompt(
        request.runtime.context.tenant_id
    )
```


A better architecture can be:

```text
API request
    ↓
load tenant configuration from DB (all at once)
    ↓
build trusted AgentContext
    ↓
invoke agent
    ↓
dynamic_prompt reads context
```


So middleware becomes cheap:

```python
@dynamic_prompt
def tenant_prompt(request):
    context = request.runtime.context
    return context.tenant_system_instructions
```


---

## Introduction to Guardrails (only)

A guardrail is simply:

> **A rule that decides whether execution is allowed to continue.**

There are two major positions:

```text
BEFORE MODEL

input
 ↓
guard
 ↓
LLM
```

and:

```text
AFTER MODEL

LLM
 ↓
output
 ↓
guard
 ↓
continue / stop
```



```text
User
 ↓
before_model
 ↓
policy violation?
 ├── yes → end
 └── no  → model
```


```text
maximum message length
tenant authorization
tool allowlist
token budget
role permissions
known forbidden patterns
```


---


## Introduction to Audit middleware (only)

```text
who?
tenant?
when?
which model?
which tools?
how many tokens?
how much cost?
did guardrail trigger?
did it finish?
did it fail?
```


For example:

```python
class AuditMiddleware(AgentMiddleware):

    def before_agent(self, state, runtime):
        # create audit context
        return None

    def after_model(self, state, runtime):
        # record model result / token usage
        return None

    def after_agent(self, state, runtime):
        # finalize audit record
        return None
```

#### Use Langfuse for:

```text
traces
spans
LLM calls
latency
token usage
evaluation
debugging
observability
```


---

## Token budgets

LangChain currently has `ModelCallLimitMiddleware`, which limits model call count,

But `TokenBudgetMiddleware` does not exist yet

modern LangChain standardizes token information through:

```python
AIMessage.usage_metadata
```

Typical structure:

```python
{
    "input_tokens": 1200,
    "output_tokens": 300,
    "total_tokens": 1500,
}
```

The architecture is:

```text
             MODEL
               ↓
       AIMessage.usage_metadata
               ↓
          after_model
               ↓
        accumulate counters
               ↓
        next before_model
               ↓
          budget check
```

A production system may combine:

```text
current token usage
+
estimated input tokens
+
maximum permitted output tokens
```

So a robust enterprise architecture often combines:

```text
middleware budget policy
+
model/provider output limits
+
provider account limits
+
application rate limits
```

---

## Testing custom middleware

```text
unit tests
+
fake handler
+
fake model
+
small number of integration tests
```

```python
def fake_handler(request):
    assert ...
    return ModelResponse(
        result=[
            AIMessage(content="fake response")
        ]
    )
```

Then:

```python
response = middleware.wrap_model_call(
    request,
    fake_handler,
)
```

Your fake handler can deliberately fail:

```python
attempts = 0

def fake_handler(request):
    nonlocal attempts
    attempts += 1

    if attempts < 3:
        raise RuntimeError("temporary failure")

    return fake_response
```

Now you can assert:

```python
assert attempts == 3
```

