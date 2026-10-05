# Built-in middleware


## Understanding `interrupt_on`

```python
HumanInTheLoopMiddleware(
    interrupt_on={
        "send_email": True,
        "delete_customer": True,
        "search": False,
    }
)
```

You can also specify exact decisions:

```python
{
    "delete_customer": {
        "allowed_decisions": ["approve", "reject"]
    }
}
```

That means:

```text
Approve
Reject

but NOT edit
```


#### interrupt with `When`

```python
"execute_sql": {
    "allowed_decisions": ["approve", "reject"],
    "when": is_write_query,
}
```

---


## Built-in middleware #1 — `HumanInTheLoopMiddleware`


### HITL decisions

#### Decision: `approve`

Human says:

```text
YES
```

The original tool call executes.

#### Decision: `edit`

Human says: 

``` text
changes the proposed action.
```


#### Decision: `reject`

Human says:

```text
NO
```

The tool does not execute.

The model can receive the rejection/feedback and continue.

#### Decision: `respond`

Used for cases where the human response itself substitutes for the tool execution. 

This is useful for tools conceptually similar to:

```text
ask_user
```

---


## Checkpointer

Imagine HITL interrupts.

Your process now has:

```text
WAITING FOR HUMAN
```

Five minutes later:

```text
human approves
```

LangGraph needs to know:

```text
Which conversation?
What was the state?
What tool call was pending?
What happens next?
```

That is why you need checkpointing.

For learning:

```python
InMemorySaver()
```

For production:

```text
InPostgresSaver()
```


## Built-in middleware #2 — `SummarizationMiddleware`

> "What happens when the conversation becomes too large?"

SummarizationMiddleware automatically summarizes older conversation history when configured context thresholds are reached while preserving recent context and maintaining val/id AI/tool message relationships.

```text
long conversation
       ↓
Summarization
       ↓
compressed summary
```

#### `trigger=`

`trigger` answers:

> "When should summarization happen?"

Context-size specifications:
1. token-based thresholds
2. message-based thresholds

```python

summarizer = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash"
)

SummarizationMiddleware(
    model=summarizer,
    trigger=("tokens", 100_000),
)
```

means approximately:

```text
when context reaches this size
        ↓
summarize
```

It is common (and recommended) to use a cheaper/faster model

#### `keep=`

> "After summarizing, how much recent history should remain?"

```text
OLD OLD OLD OLD OLD OLD
          ↓
      summary

RECENT RECENT RECENT
          ↑
         keep
```

roughly means:

```text
trigger → when to compact
keep    → how much recent context to preserve
```


---


## Built-in middleware #3 — `ContextEditingMiddleware`


Context editing can clear it and replace it with a placeholder.

that is:	
```text
remove old tool outputs that are no longer useful
```

So:
```text
50 old tool results
       ↓
Context editing
       ↓
clear useless results
```



#### ClearToolUsesEdit

```python
ClearToolUsesEdit(
    trigger=100_000,
    clear_at_least=...,
    keep=3,
    clear_tool_inputs=False,
    exclude_tools=(),
)
```

The important ideas are:

```text
trigger
    ↓
when to start clearing

clear_at_least
    ↓
minimum token reduction desired

keep
    ↓
preserve the newest N tool results

exclude_tools
    ↓
never clear results from these tools
```


---

## Built-in middleware #4 — `ModelRetryMiddleware`

> "What if the model call temporarily fails?"


Conceptually:

```python
ModelRetryMiddleware(
    max_retries=2,
)
```

means:

```text
initial model call
      ↓
failure
      ↓
retry 1
      ↓
failure
      ↓
retry 2
```

---

## Built-in middleware #5 — `ToolRetryMiddleware`

```python
ToolRetryMiddleware(
    max_retries=2,
    tools=["get_weather"],
)
```

```text
get_weather()
 ↓
timeout
 ↓
retry
 ↓
success
```

---

## Built-in middleware #6 — `ToolErrorMiddleware`

Suppose:

```python
get_customer(id="123")
```

throws:

```python
ValueError(...)
```

You don't necessarily want the whole agent execution to crash.

You might instead tell the model:

```text
The customer lookup failed.
Try another ID.
```

```python
middleware=[
    ToolErrorMiddleware(on_error=handle_tool_error),
    
]
```

#### `ToolRetryMiddleware` + `ToolErrorMiddleware`

Think:

```text
Tool
 ↓
Retry
 ↓
still failed
 ↓
Error middleware
 ↓
ToolMessage(status="error")
 ↓
LLM
```

or example:

```python
middleware=[
    ToolErrorMiddleware(on_error=handle_tool_error),
    ToolRetryMiddleware(
        max_retries=2,
        on_failure="error",
    ),
]
```


#### important security point about tool errors:

Do **not** blindly do:

```python
return str(exc)
```

because exception messages can reveal:

```text
database credentials
internal hostnames
file paths
SQL
stack details
API keys
```

A better pattern:

```python
def handle_tool_error(exc, request):

    if isinstance(exc, ValueError):
        return (
            f"Tool `{request.tool_call['name']}` "
            "received invalid input."
        )

    return None
```

Notice:

```text
model gets useful information
```

but:

```text
internal exception details stay hidden
```

---


## Built-in middleware #7 — `PIIMiddleware`

PII means:

```text
Personally Identifiable Information
```

Current built-in PII middleware can detect types such as:

```text
email
credit card
IP address
MAC address
URL
```

and can apply strategies such as:

```text
block
redact
mask
hash
```

### `block`

```text
PII found
   ↓
STOP
```

### `redact`

```text
john@example.com
```

becomes:

```text
[REDACTED_EMAIL]
```


### `mask`

Example:

```text
4111-1111-1111-1234
```

might become something like:

```text
****-****-****-1234
```

### `hash`

Useful when:

```text
you don't want to store the actual value
```

but:

```text
you still want the same person to map to the same identifier
```


---

## Built-in middleware #8 — `ModelCallLimitMiddleware`

This controls:

> "How many model calls may this agent make?"

Because an agent can get stuck in an infinite loop

```text
Model
 ↓
Tool
 ↓
Model
 ↓
Tool
 ↓
Model
 ↓
Tool
 ↓
Model
 ↓
...
```

### Run limit vs Thread limit

#### Run limit

Suppose:
```python
run_limit=10
```

Then:
```text
this invocation
    ↓
max 10 model calls
```

run limit = one execution


#### Thread limit

The thread-level budget tracks usage across runs.

thread limit = conversation/thread lifetime

`exit_behavior`

Current model-call limits support:

```text
"end"
"error"
```

With:

```python
exit_behavior="end"
```

the agent ends gracefully.

With:

```python
exit_behavior="error"
```

a `ModelCallLimitExceededError` is raised.


---


## Built-in middleware #9 — `ToolCallLimitMiddleware`

This is similar but applies to tools.

Example:

```python
ToolCallLimitMiddleware(
    tool_name="search_database",
    run_limit=5,
)
```

means:

```text
search_database
      ↓
maximum five calls in a run
```

It also supports run/thread limits and several exit behaviors:

```text
continue
error
end
```


---


## Built-in middleware #10 — `LLMToolSelectorMiddleware`

Suppose your enterprise harness has:

```text
500 tools
```

Then:

```text
User question
      ↓
Less Expensive selection model
      ↓
choose relevant tools
      ↓
Expensive main model receives only selected tools
```

Code:

```python
LLMToolSelectorMiddleware(
    model=selector_model,
    max_tools=10,
)
```

You can also specify tools that should always be included:

```python
always_include=["ask_user"]
```


---

## ModelFallbackMiddleware

```text
Model A
  ↓
failure
  ↓
Model B
  ↓
failure
  ↓
Model C
```

### Retry vs fallback

Retry:

```text
same model
same general operation
try again
```

Fallback

```text
another model/provider
```


### Fallback vs Routing

Fallback answers:

> "The chosen model failed. What should I try next?"

Routing answers:

> "Which model should I choose in the first place?"


For example:

```text
Simple question
    ↓
cheap model
```

but:

```text
Complex coding/reasoning task
    ↓
strong model
```


## Built-in middleware: ModelRouterMiddleware

``` Python

router = ModelRouterMiddleware(
    choices={
        "fast": ModelChoice(
            model="openai:gpt-4o-mini",
            criteria="Simple questions, direct lookups, text extraction, and short summaries.",
        ),
        "powerful": ModelChoice(
            model="openai:gpt-4o",
            criteria="Complex reasoning, debugging, architecture layout, and high-stakes math.",
        ),
    },
    instructions="Select the least expensive model that can successfully complete the user's task.",
)


agent = create_agent(
    model="openai:gpt-4o-mini", # Default baseline model
    tools=[], 
    middleware=[router]
)


```


---

## LiteLLM

```text
                   ┌───────────────┐
                   │ LangChain     │
                   │ agent routing │
                   └──────┬────────┘
                          │
                          ▼
                   ┌───────────────┐
                   │ LiteLLM       │
                   │ gateway       │
                   └──────┬────────┘
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
           Gemini      OpenAI      Local LLM
```


## Built-in middleware #11 — `TodoListMiddleware`

Instead of the model just thinking:

```text
"I still have three things to do."
```

it can maintain:

```text
[ ] inspect database
[x] inspect logs
[ ] fix code
[ ] run tests
```

That gives the agent a structured planning state.


## Subagents

Suppose your main agent has:

```text
500 tools
```

That is not ideal.

Instead:

```text
Main agent
   ↓
delegation
```

Research subagent might have:

```text
search tools
browser
document tools
```

Coding subagent might have:

```text
filesystem
Git
test runner
```


## Context isolation

`SubAgent` is isolated by default and receives the delegated task rather than the parent's whole conversation;

``` Text
Main conversation

200,000 tokens
       ↓
"Research X"
       ↓
Research subagent

only receives:
"Research X"
```

Instead of:

```text
Research subagent receives
the entire massive conversation
```

#### task

task` is effectively a delegation tool

```text
Main agent
   ↓
task tool
   ↓
SubAgentMiddleware
   ↓
subagent
```

---

## Important Middleware

```text
create_agent(
    model=...
    tools=[...]
    middleware=[
        PII,
        Logging,
        Security,
        ModelRouting,
        ModelRetry,
        ContextEditing,
        Summarization,
        ToolRetry,
        ToolError,
        HITL,
    ],
)
```

```text
                         USER
                          │
                          ▼
                  ┌───────────────┐
                  │ FastAPI       │
                  │ authentication│
                  └───────┬───────┘
                          │
                          ▼
                  ┌───────────────┐
                  │ create_agent  │
                  └───────┬───────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ▼                 ▼                 ▼
      PII              Security          Routing
        │                 │                 │
        └─────────────────┼─────────────────┘
                          ▼
                     Context
                          │
                          ▼
                       Retry
                          │
                          ▼
                    Gemini / Gateway
                          │
                          ▼
                      AIMessage
                          │
                     tool_calls?
                       /      \
                     NO        YES
                              │
                              ▼
                         Tool Security
                              │
                           HITL?
                           /   \
                         YES    NO
                          │      │
                       Human    ToolRetry
                          │      │
                          └──┬───┘
                             ▼
                            Tool
                             │
                             ▼
                         ToolMessage
                             │
                             ▼
                           Model
```



	


