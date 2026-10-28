You are at exactly the right point to learn this, because once you understand **`handler(request)`**, most of LangChain's middleware architecture becomes much easier.

The key idea is:

> **`handler(request)` means “continue processing this request through whatever comes next in the middleware pipeline.”**

It does **not** mean “run all middleware.”

It is more like a special **`next()` function** in a chain of responsibility.

The current LangChain middleware API is built around this idea. `wrap_model_call` receives a `ModelRequest` and a handler callback; the handler executes the downstream model pipeline and returns a `ModelResponse`. A middleware may call it zero times, once, or multiple times depending on what it needs to do. Middleware  -listed earlier is the outer layer of the composition. ([LangChain][1])

---

# 1. First: forget LangChain for a moment

Imagine ordinary Python functions:

```python
def function_a():
    print("A")
    function_b()


def function_b():
    print("B")
    function_c()


def function_c():
    print("C")
```

Calling:

```python
function_a()
```

produces:

```text
A
B
C
```

Now imagine we want to make this reusable:

```python
def function_a(next_function):
    print("A")
    next_function()


def function_b(next_function):
    print("B")
    next_function()


def function_c():
    print("C")
```

Now:

```python
function_a(
    lambda: function_b(
        lambda: function_c()
    )
)
```

The important concept is:

```text
next_function()
```

means:

> "I have finished my part. Continue with the next thing."

That is essentially what LangChain's:

```python
handler(request)
```

means.

---

# 2. What exactly is `handler`?

Suppose you write:

```python
@wrap_model_call
def my_middleware(request, handler):
    ...
```

You get two things:

```text
request
handler
```

Think of them as:

```text
request  = "What are we trying to do?"
handler  = "What should happen next?"
```

More precisely, `request` is a `ModelRequest` containing information such as the current state, runtime, model, tools, system prompt, and messages involved in the model call. `handler` is a callable that continues execution downstream and returns the model result. ([LangChain][1])

So:

```python
handler(request)
```

means:

```text
Take this request
       ↓
send it to the next middleware / eventual model
       ↓
give me the result
```

That is the fundamental idea.

---

# 3. The easiest mental model: an onion

Imagine your agent is surrounded by layers:

```text
                ┌──────────────────────┐
                │ Security middleware  │
                │                      │
                │  ┌────────────────┐  │
                │  │ Logging        │  │
                │  │                │  │
                │  │ ┌────────────┐ │  │
                │  │ │ Retry      │ │  │
                │  │ │            │ │  │
                │  │ │   MODEL    │ │  │
                │  │ │            │ │  │
                │  │ └────────────┘ │  │
                │  └────────────────┘  │
                └──────────────────────┘
```

The first middleware receives the request.

It can:

```text
inspect request
       ↓
do its own work
       ↓
handler(request)
       ↓
next layer
```

Then the next middleware does the same thing.

This produces a nested structure like:

```python
security(
    logging(
        retry(
            model
        )
    )
)
```

And that is the key to understanding middleware.

---

# 4. The most important example

Suppose you have three middleware:

```text
Security
Logging
Retry
```

and the actual model:

```text
Gemini
```

You can think of LangChain composing them roughly like:

```python
Security(
    Logging(
        Retry(
            Gemini
        )
    )
)
```

Conceptually:

```python
def security(request, handler):
    if not allowed(request):
        return denial()

    return handler(request)
```

Then:

```python
def logging(request, handler):
    print("Starting")

    response = handler(request)

    print("Finished")

    return response
```

Then:

```python
def retry(request, handler):
    for attempt in range(3):
        try:
            return handler(request)
        except TemporaryError:
            ...
```

Then finally:

```python
def model(request):
    return gemini(request)
```

So the call flow becomes:

```text
Security
   │
   │ handler(request)
   ▼
Logging
   │
   │ handler(request)
   ▼
Retry
   │
   │ handler(request)
   ▼
Gemini
```

Then the response travels back upward:

```text
Gemini
   │
   ▼
Retry
   │
   ▼
Logging
   │
   ▼
Security
   │
   ▼
Caller
```

That is why middleware can perform both:

```text
before the call
```

and:

```text
after the call
```

---

# 5. This is why `handler(request)` is so powerful

`handler(request)` lets middleware surround another operation.

For example:

```python
def logging(request, handler):
    print("BEFORE")

    response = handler(request)

    print("AFTER")

    return response
```

The result is:

```text
BEFORE
   ↓
actual model execution
   ↓
AFTER
```

Therefore one middleware can perform:

```text
authentication
authorization
logging
metrics
timing
retry
caching
routing
redaction
validation
```

without implementing the model itself.

That separation is one of the major benefits of middleware.

---

# 6. Three very important things `handler(request)` can mean

This is where advanced understanding begins.

A middleware can call:

## Zero times

Example: security rejection.

```python
@wrap_model_call
def security(request, handler):

    if not user_is_allowed(request):
        return blocked_response()

    return handler(request)
```

If the user is unauthorized:

```text
security
   ↓
BLOCK
```

The model never runs.

So:

```python
handler(request)
```

was **not called**.

This is called **short-circuiting**.

The current LangChain middleware API explicitly supports skipping the handler to short-circuit execution. ([LangChain][1])

---

# 7. It can call it once

This is the most common case.

```python
response = handler(request)
return response
```

Example:

```text
logging
   ↓
model
```

---

# 8. It can call it multiple times

This is extremely important.

Consider retry:

```python
@wrap_model_call
def retry(request, handler):

    for attempt in range(3):
        try:
            return handler(request)
        except Exception:
            if attempt == 2:
                raise
```

Potentially:

```text
handler(request)  # attempt 1
       ↓
ERROR

handler(request)  # attempt 2
       ↓
ERROR

handler(request)  # attempt 3
       ↓
SUCCESS
```

So `handler` is not necessarily:

```text
"call the model exactly once"
```

It means:

> **"execute the rest of the pipeline from this point."**

LangChain's current reference explicitly documents multiple handler calls for retry behavior. ([LangChain][1])

---

# 9. It can even modify the request before calling the handler

This gives us model routing.

Conceptually:

```python
@wrap_model_call
def routing(request, handler):

    if expensive_task(request):
        request = request.override(model=powerful_model)
    else:
        request = request.override(model=cheap_model)

    return handler(request)
```

So middleware becomes:

```text
incoming request
       ↓
routing middleware
       ↓
modify request.model
       ↓
handler(request)
       ↓
selected model
```

This is a very important distinction:

```text
middleware does not necessarily DO the final operation
```

It can instead:

```text
prepare
modify
validate
authorize
route
then delegate
```

---

# 10. Middleware order matters enormously

Suppose:

```python
middleware=[
    SecurityMiddleware(),
    LoggingMiddleware(),
    RetryMiddleware(),
]
```

The current API composes the first middleware as the outermost layer. ([LangChain][1])

Conceptually:

```text
Security
   ↓
Logging
   ↓
Retry
   ↓
Model
```

But change the order:

```python
middleware=[
    LoggingMiddleware(),
    SecurityMiddleware(),
    RetryMiddleware(),
]
```

Now:

```text
Logging
   ↓
Security
   ↓
Retry
   ↓
Model
```

That can materially change behavior.

---

# 11. Example: logging + security

Suppose the request is unauthorized.

### Ordering A

```text
Security
    ↓
Logging
    ↓
Model
```

Security checks first:

```text
Security: "Not allowed"
         ↓
       STOP
```

Logging never gets the opportunity to log the downstream execution unless the security middleware itself logs.

### Ordering B

```text
Logging
    ↓
Security
    ↓
Model
```

Now logging sees the request first:

```text
Logging START
       ↓
Security DENIED
       ↓
Logging END / DENIED
```

This is why middleware ordering is an architectural decision.

---

# 12. `handler(request)` and tool middleware

There are actually two very similar concepts you should keep separate.

For model calls:

```python
wrap_model_call(request, handler)
```

For tool calls:

```python
wrap_tool_call(request, handler)
```

The idea is the same:

```text
MODEL PIPELINE

request
   ↓
middleware
   ↓
handler(request)
   ↓
next middleware
   ↓
model
```

and:

```text
TOOL PIPELINE

tool request
   ↓
middleware
   ↓
handler(request)
   ↓
next middleware
   ↓
tool
```

LangChain provides both decorators for creating these middleware layers. ([LangChain][2])

This is why:

```text
ToolRetryMiddleware
ToolErrorMiddleware
HumanInTheLoopMiddleware
```

can control what happens around tool execution.

---

# 13. Now let's connect this to `create_agent`

Your mental picture should now be:

```text
create_agent(...)
       │
       ▼
┌──────────────────────────┐
│ middleware pipeline      │
│                          │
│   middleware A           │
│       ↓                  │
│   middleware B           │
│       ↓                  │
│   middleware C           │
│       ↓                  │
│   model                  │
└──────────────────────────┘
       │
       ▼
AIMessage
       │
       ▼
tool calls?
       │
      YES
       ▼
┌──────────────────────────┐
│ tool middleware pipeline │
│                          │
│ security                 │
│ retry                    │
│ error handling           │
│ HITL                     │
│ tool                     │
└──────────────────────────┘
```

Meanwhile the agent loop continues:

```text
Human message
     ↓
Model
     ↓
Tool call?
   /     \
 NO       YES
 |         |
Answer    Tool middleware
             ↓
           Tool
             ↓
        ToolMessage
             ↓
           Model
             ↓
        ...
```

That is the connection between your Module 42, 43, 44 and this Module 45.

`create_agent` currently builds an agent graph where the model and tool execution repeat until the model produces no further tool calls. Middleware can intercept behavior throughout that process. ([LangChain][3])

---

# 14. Built-in middleware #1 — `HumanInTheLoopMiddleware`

This is one of the most important pieces for enterprise agents.

Imagine the agent says:

```text
I should call:

delete_customer(id=123)
```

You probably don't want:

```text
AI → delete database row
```

You want:

```text
AI
 ↓
Human approval
 ↓
delete database row
```

That's what HITL provides.

LangChain's current `HumanInTheLoopMiddleware` intercepts specified tool actions before execution and supports decision types including `approve`, `edit`, `reject`, and currently also `respond`. It requires a checkpointer so execution state can survive the interruption and resume later. ([LangChain][4])

---

# 15. Understanding `interrupt_on`

You configure tool-level policies:

```python
HumanInTheLoopMiddleware(
    interrupt_on={
        "send_email": True,
        "delete_customer": True,
        "search": False,
    }
)
```

Think:

```text
send_email
    ↓
STOP
    ↓
human decides

delete_customer
    ↓
STOP
    ↓
human decides

search
    ↓
RUN AUTOMATICALLY
```

`True` means interrupt.

`False` means auto-approve.

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

The current Python API also supports a `when` predicate so you can interrupt only some calls based on arguments. ([LangChain][5])

For example:

```python
"execute_sql": {
    "allowed_decisions": ["approve", "reject"],
    "when": is_write_query,
}
```

Therefore:

```sql
SELECT * FROM users
```

could run automatically, while:

```sql
DELETE FROM users
```

would stop for review.

That's much better than simply:

```text
ALL SQL = approval required
```

---

# 16. HITL decisions

## `approve`

Human says:

```text
YES
```

The original tool call executes.

---

## `edit`

Human changes the proposed action.

For example:

AI proposes:

```python
send_email(
    to="alice@example.com",
    body="Delete production database"
)
```

Human edits it to:

```python
send_email(
    to="alice@example.com",
    body="Please review the staging database"
)
```

The edited action is executed.

---

## `reject`

Human says:

```text
NO
```

The tool does not execute.

The model can receive the rejection/feedback and continue.

---

## `respond`

Current Python HITL also has a `respond` decision for cases where the human response itself substitutes for the tool execution. ([LangChain][6])

This is useful for tools conceptually similar to:

```text
ask_user
```

or:

```text
approve_this_business_action
```

---

# 17. Why a checkpointer is required

This is extremely important.

Imagine:

```text
12:00:00
Agent decides:
send_email(...)
```

Then HITL interrupts.

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

That is why you need checkpointing. Current LangChain documentation explicitly requires it for HITL and recommends a persistent checkpointer such as PostgreSQL or MongoDB for production rather than an in-memory saver. ([GitHub][7])

For learning:

```python
InMemorySaver()
```

For production:

```text
Postgres
MongoDB
another persistent LangGraph checkpoint implementation
```

And you normally associate the execution with a thread ID.

---

# 18. Built-in middleware #2 — `SummarizationMiddleware`

This answers a different problem:

> "What happens when the conversation becomes too large?"

Imagine:

```text
Message 1
Message 2
Message 3
...
Message 500
Tool result 1
Tool result 2
Tool result 3
...
```

Eventually you approach the model's context limit.

SummarizationMiddleware automatically summarizes older conversation history when configured context thresholds are reached while preserving recent context and maintaining val/id AI/tool message relationships. ([LangChain][8])

Think:

```text
OLD HISTORY

500 messages
      ↓
summarization
      ↓
"Previous discussion:
user wanted X,
we searched Y,
tool returned Z..."
      +
recent messages
```

So instead of:

```text
10 million tokens
```

you might have:

```text
summary
+
recent messages
```

---

# 19. `trigger=`

`trigger` answers:

> "When should summarization happen?"

The modern middleware supports context-size specifications such as token-based and message-based thresholds, with additional context-size forms available in current APIs. ([LangChain][8])

Conceptually:

```python
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

The exact accepted `ContextSize` forms are versioned API details, so when implementing this in your project, use the current installed LangChain reference rather than copying old examples from older LangChain tutorials.

---

# 20. `keep=`

`keep` answers:

> "After summarizing, how much recent history should remain?"

Conceptually:

```text
OLD OLD OLD OLD OLD OLD
          ↓
      summary

RECENT RECENT RECENT
          ↑
         keep
```

So:

```python
trigger = ...
keep = ...
```

roughly means:

```text
trigger → when to compact
keep    → how much recent context to preserve
```

That distinction is extremely important.

---

# 21. Which model should summarize?

This is where your preference for Gemini makes sense.

You don't necessarily need your most capable model to summarize.

For example:

```text
Main model:
Gemini Pro
      ↓
Complex reasoning

Summarizer:
Gemini Flash
      ↓
Cheap/fast context compaction
```

Conceptually:

```python
main_model = ChatGoogleGenerativeAI(
    model="gemini-3.1-pro-preview"
)

summary_model = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash"
)
```

The current `langchain-google-genai` integration uses `ChatGoogleGenerativeAI` as its primary Gemini chat interface, and the current package uses Google's consolidated `google-genai` SDK. ([LangChain][9])

---

# 22. Built-in middleware #3 — `ContextEditingMiddleware`

This is related to summarization but is **not the same thing**.

Summarization says:

```text
compress old conversation into a summary
```

Context editing can instead say:

```text
remove old tool outputs that are no longer useful
```

For example:

```text
Tool call:
search_database()

Tool result:
5 MB of JSON
```

Then another 20 tool calls happen.

The old 5 MB result may no longer be necessary.

Context editing can clear it and replace it with a placeholder.

Current LangChain's `ContextEditingMiddleware` is model-agnostic and currently supports the `ClearToolUsesEdit` strategy. ([LangChain][10])

---

# 23. `ClearToolUsesEdit`

Current API:

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

These are current documented parameters. ([LangChain][11])

---

# 24. Summarization vs Context Editing

Remember this simple rule:

```text
Summarization
=
"Turn old information into a smaller representation."
```

Whereas:

```text
Context editing
=
"Remove old information that we don't need anymore."
```

So:

```text
50 old tool results
       ↓
Context editing
       ↓
clear useless results
```

versus:

```text
long conversation
       ↓
Summarization
       ↓
compressed summary
```

They can be used together.

---

# 25. Built-in middleware #4 — `ModelRetryMiddleware`

This answers:

> "What if the model call temporarily fails?"

For example:

```text
Gemini API
    ↓
timeout
```

Instead of immediately failing:

```text
retry
retry
```

Current `ModelRetryMiddleware` supports configurable retry counts, exception filtering, exponential backoff, maximum delay and jitter. ([LangChain][12])

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

Important:

```text
max_retries=2
```

means **two retries after the original attempt**, not three retries in addition to three attempts.

---

# 26. Why retry only some errors?

Do not blindly retry everything.

For example:

```text
timeout
rate limit
temporary provider failure
connection failure
```

might be retryable.

But:

```text
invalid API key
invalid model name
malformed request
permission denied
```

may not benefit from retrying.

The middleware allows `retry_on` to be an exception tuple or a callable that decides whether an exception should be retried. ([LangChain][13])

---

# 27. Built-in middleware #5 — `ToolRetryMiddleware`

Same idea, but for tools.

Example:

```text
Agent
 ↓
get_weather()
 ↓
network timeout
```

Instead of:

```text
FAIL
```

you can do:

```text
get_weather()
 ↓
timeout
 ↓
retry
 ↓
success
```

Current `ToolRetryMiddleware` supports retry counts, selected tools, exception filtering, exponential backoff and configurable failure behavior. ([LangChain][14])

Conceptually:

```python
ToolRetryMiddleware(
    max_retries=2,
    tools=["get_weather"],
)
```

Now only that tool gets retry behavior.

---

# 28. Model retry vs tool retry

Remember:

```text
ModelRetryMiddleware
        ↓
LLM/API failures
```

whereas:

```text
ToolRetryMiddleware
        ↓
your tool execution failures
```

Example:

```text
Gemini timeout
    → ModelRetryMiddleware
```

versus:

```text
Postgres connection timeout
    → ToolRetryMiddleware
```

These solve different problems.

---

# 29. Built-in middleware #6 — `ToolErrorMiddleware`

Now we have a different problem.

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

That is what `ToolErrorMiddleware` is designed for.

The current implementation can convert selected tool exceptions into error `ToolMessage`s. Importantly, it does **not** automatically retry; retry and error conversion are separate concerns. ([LangChain][15])

---

# 30. `ToolRetryMiddleware` + `ToolErrorMiddleware`

This is a very useful combination.

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

The current documentation specifically recommends composing these so the retry layer can be configured to propagate a final failure to `ToolErrorMiddleware`, which then decides how to represent the error. ([LangChain][15])

For example:

```python
middleware=[
    ToolErrorMiddleware(on_error=handle_tool_error),
    ToolRetryMiddleware(
        max_retries=2,
        on_failure="error",
    ),
]
```

Because middleware composition is nested, ordering matters.

---

# 31. An important security point about tool errors

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

The current LangChain documentation explicitly recommends returning safe error information rather than blindly exposing raw exception messages. ([LangChain][15])

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

# 32. Built-in middleware #7 — `PIIMiddleware`

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

It can also be configured to act on input, output and tool results. ([LangChain][2])

---

# 33. Four PII strategies

### `block`

```text
PII found
   ↓
STOP
```

Good when PII must never enter a particular workflow.

---

### `redact`

```text
john@example.com
```

becomes:

```text
[REDACTED_EMAIL]
```

---

### `mask`

Example:

```text
4111-1111-1111-1234
```

might become something like:

```text
****-****-****-1234
```

---

### `hash`

Something such as an email can be transformed into a stable pseudonymous representation.

Useful when:

```text
you don't want to store the actual value
```

but:

```text
you still want the same person to map to the same identifier
```

The current reference documents these strategies and their intended trade-offs. ([LangChain][2])

---

# 34. PII middleware is not a complete enterprise DLP system

This is an important production distinction.

Don't think:

```text
PIIMiddleware = full security/compliance system
```

Instead:

```text
PIIMiddleware
=
one application-level guardrail
```

You still need things such as:

```text
database permissions
network controls
secret management
audit logs
data classification
provider-side controls
access controls
encryption
retention policies
```

PII middleware is useful, but it should not be your only security layer.

---

# 35. Built-in middleware #8 — `ModelCallLimitMiddleware`

This controls:

> "How many model calls may this agent make?"

Why is this useful?

Because an agent can accidentally do this:

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

Without limits, a bug can become:

```text
huge cost
```

Current `ModelCallLimitMiddleware` supports:

```text
thread_limit
run_limit
exit_behavior
```

and tracks both per-run and persistent per-thread model call counts. ([LangChain][16])

---

# 36. Run limit vs thread limit

This distinction is important.

## Run limit

One invocation:

```text
User asks question
       ↓
agent invocation
```

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

---

## Thread limit

A conversation thread may have:

```text
Run 1 → 4 calls
Run 2 → 3 calls
Run 3 → 2 calls
...
```

The thread-level budget tracks usage across runs.

So:

```text
run limit
=
one execution

thread limit
=
conversation/thread lifetime
```

The current middleware explicitly distinguishes those two scopes. ([LangChain][16])

---

# 37. `exit_behavior`

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

a `ModelCallLimitExceededError` is raised. ([LangChain][16])

For an API-facing production system, you need to decide whether the user should receive:

```text
partial graceful termination
```

or:

```text
explicit application error
```

---

# 38. Built-in middleware #9 — `ToolCallLimitMiddleware`

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

Current documentation describes the difference among these behaviors explicitly. ([LangChain][17])

---

# 39. Why tool limits are extremely important

Imagine a poorly behaving agent:

```text
search
 ↓
search
 ↓
search
 ↓
search
 ↓
search
 ↓
search
 ↓
...
```

This could mean:

```text
cost
latency
database load
API rate limits
```

Tool-call limits give you a hard safety boundary.

---

# 40. Built-in middleware #10 — `LLMToolSelectorMiddleware`

Now we have a different problem.

Suppose your enterprise harness has:

```text
500 tools
```

You don't necessarily want to give all 500 tool schemas to your primary model on every turn.

Why?

Because tool definitions themselves consume context.

Instead:

```text
User question
      ↓
small selection model
      ↓
choose relevant tools
      ↓
main model receives only selected tools
```

That is what `LLMToolSelectorMiddleware` does. The current implementation uses an LLM to choose relevant tools before the main model call. ([LangChain][18])

---

# 41. Example

Imagine:

```text
Tool 1: Salesforce
Tool 2: Jira
Tool 3: GitHub
Tool 4: Slack
Tool 5: PostgreSQL
Tool 6: Weather
Tool 7: ServiceNow
...
500 tools
```

User:

```text
Create a Jira ticket.
```

Tool selector might select:

```text
jira_create_issue
jira_get_project
jira_get_issue
```

instead of all 500.

Then:

```text
Main model
    ↓
sees relevant tools
```

---

# 42. `max_tools`

You can cap the number selected:

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

Current docs expose `max_tools`, `always_include`, retry behavior for malformed selector output, and configurable parsing-failure behavior. ([LangChain][18])

---

# 43. Very important: tool selection itself costs an LLM call

This middleware isn't free.

You now have:

```text
selector model call
      ↓
main model call
```

instead of:

```text
main model call
```

So tool selection makes sense when:

```text
tool count is large
```

and:

```text
saving context / improving tool relevance
```

is worth the extra selection call.

This is why a small inexpensive Gemini model could be attractive for the selector in your architecture.

---

# 44. Model fallback

Now we get to reliability.

Imagine:

```text
Primary model
    ↓
fails
```

You want:

```text
Fallback model
```

Current `ModelFallbackMiddleware` automatically attempts alternative models when model calls fail. Multiple fallback models can be configured in sequence. ([LangChain][19])

Conceptually:

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

This is different from normal retries.

---

# 45. Retry vs fallback

Very important distinction:

### Retry

```text
same model
same general operation
try again
```

Example:

```text
Gemini
 ↓
timeout
 ↓
Gemini
```

### Fallback

```text
another model/provider
```

Example:

```text
Gemini
 ↓
provider unavailable
 ↓
other model
```

So:

```text
Retry = try again
Fallback = try somewhere else
```

---

# 46. Model routing is different again

Fallback answers:

> "The chosen model failed. What should I try next?"

Routing answers:

> "Which model should I choose in the first place?"

For example:

```text
Simple question
    ↓
cheap Gemini model
```

but:

```text
Complex coding/reasoning task
    ↓
strong Gemini model
```

+This is dynamic routing.

---

# 47. `wrap_model_call` is perfect for dynamic routing

Conceptually:

```python
@wrap_model_call
def dynamic_model(request, handler):

    if should_use_powerful_model(request):
        request = request.override(model=powerful_model)
    else:
        request = request.override(model=cheap_model)

    return handler(request)
```

Notice what happened.

The middleware did not call:

```python
powerful_model.invoke(...)
```

itself.

It changed the request:

```text
request.model = powerful_model
```

and then:

```python
handler(request)
```

said:

> "Okay, continue the rest of the pipeline using this modified request."

This is the purest demonstration of why `handler(request)` matters.

---

# 48. Cheap-first + escalation

You can build:

```text
User request
      ↓
routing middleware
      ↓
cheap model
      ↓
if appropriate
      ↓
powerful model
```

There are several ways to define "appropriate":

```text
message complexity
tool count
user tier
task type
token estimate
security classification
department
SLA
budget
```

For example:

```python
if request.runtime.context.user_tier == "premium":
    powerful_model
elif complex_task(request):
    powerful_model
else:
    cheap_model
```

This is particularly useful in an enterprise AI harness.

---

# 49. Combine routing with fallback

You can conceptually build:

```text
Dynamic router
       ↓
selected primary
       ↓
fallback middleware
       ↓
fallback models
```

So:

```text
User
 ↓
Routing
 ↓
Cheap Gemini
 ↓
failure
 ↓
Fallback Gemini / another provider
```

This gives two separate resilience mechanisms:

```text
Routing
=
Which model should I use?

Fallback
=
What do I do if that model fails?
```

Do not mentally combine those concepts into one thing.

---

# 50. LiteLLM as a gateway

This is where your vendor-independent architecture becomes very interesting.

You can have:

```text
LangChain
   ↓
ChatOpenAI
   ↓
your OpenAI-compatible gateway
   ↓
LiteLLM
   ↓
Gemini / OpenAI / Anthropic / local model / etc.
```

`ChatOpenAI` currently supports `base_url` specifically for proxies or service emulators, and OpenAI-compatible endpoints can be used when they conform to the supported API shape. ([LangChain][20])

LiteLLM's current documentation also demonstrates LangChain/ChatOpenAI connections through its proxy base URL. ([LiteLLM][21])

Conceptually:

```python
gateway_model = ChatOpenAI(
    model="your-gateway-model-name",
    base_url="http://your-litellm-gateway:4000/v1",
    api_key="your-gateway-key",
)
```

Then your application doesn't necessarily need to know whether the gateway is routing to:

```text
Gemini
OpenAI
Anthropic
local model
vLLM
...
```

That matches your vendor-independent harness architecture extremely well.

---

# 51. But there is an important architectural distinction

You can do:

```text
LangChain model routing
```

and:

```text
LiteLLM routing
```

They solve different layers.

### LangChain

Knows:

```text
this request is complex
this user is premium
this tool needs approval
```

### LiteLLM

Can know:

```text
provider availability
model deployment
API keys
provider routing
cost tracking
gateway policy
```

So you might eventually have:

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

That is a strong architectural separation.

---

# 52. Built-in middleware #11 — `TodoListMiddleware`

Now we move from reliability/security into planning.

An agent might need to solve:

```text
1. inspect repository
2. inspect database
3. analyze failures
4. modify code
5. run tests
6. produce report
```

A plain agent can try to remember all of this in its conversation.

A todo system makes the plan explicit.

Current `TodoListMiddleware` provides a `write_todos` tool and injects system guidance about using the todo functionality. It also ensures `write_todos` is called at most once per model turn because the tool replaces the complete todo list. ([LangChain][22])

---

# 53. Think of `write_todos` as externalized planning state

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

It's important to understand:

```text
TodoListMiddleware
≠
a magical planner
```

It provides the mechanism for structured task tracking.

The model still decides how and when to use it.

---

# 54. When todo planning is useful

Good use case:

```text
complex multi-step task
```

Bad use case:

```text
"What is 2 + 2?"
```

You don't want:

```text
TODO:
[ ] understand arithmetic
[ ] calculate 2+2
[ ] verify 4
[ ] answer user
```

for every trivial request.

The current middleware itself injects guidance intended to help the model decide when todo functionality is useful. ([LangChain][22])

---

# 55. `SubAgentMiddleware`

This comes from the **Deep Agents** ecosystem rather than being just another LangChain core middleware.

Current Deep Agents provides `SubAgentMiddleware`, which exposes a `task` tool for delegating work to child agents. ([LangChain][23])

Conceptually:

```text
Main agent
    |
    +---- task("research this")
    |          ↓
    |       researcher
    |
    +---- task("analyze code")
               ↓
            coder
```

---

# 56. Why use subagents?

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

Database subagent might have:

```text
schema tools
read-only SQL
analytics
```

So the main agent doesn't need to directly perform every specialist activity.

---

# 57. Context isolation is a huge benefit

Current Deep Agents documentation describes subagents as useful partly because they provide context isolation. A declarative `SubAgent` is isolated by default and receives the delegated task rather than the parent's whole conversation; `mode="fork"` exists for sharing the parent conversation and is currently marked experimental. ([LangChain][24])

Think:

```text
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

That can dramatically simplify complex agent architectures.

---

# 58. `task` is effectively a delegation tool

The interesting thing is:

```text
Main agent
   ↓
task tool
   ↓
SubAgentMiddleware
   ↓
subagent
```

So again the same general LangChain idea appears:

```text
middleware
+
tool
+
agent
```

The middleware is responsible for managing how the subagent capability is exposed and invoked.

---

# 59. Deep Agents already composes lots of middleware

This is one of the reasons Deep Agents is relevant to your learning.

Current `create_deep_agent` assembles middleware for capabilities such as:

```text
filesystem
subagents
summarization
patching dangling tool calls
async subagents
memory
HITL
```

with ordering and profile mechanisms. ([LangChain][25])

So understanding Module 45 is not just learning isolated LangChain classes.

You are learning the architecture that Deep Agents itself uses.

---

# 60. The most important middleware concept: middleware is composition

Let's create a realistic enterprise agent:

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

Do not think:

```text
"LangChain runs these functions one after another."
```

Think:

```text
"LangChain builds a nested execution pipeline."
```

Like:

```text
PII(
    Logging(
        Security(
            Routing(
                Retry(
                    Summarization(
                        Model
                    )
                )
            )
        )
    )
)
```

And separately, the tool side has its own layers.

---

# 61. A practical logging middleware

Let's make the concept concrete.

```python
from langchain.agents.middleware import wrap_model_call


@wrap_model_call
def logging_middleware(request, handler):
    print("MODEL CALL START")

    response = handler(request)

    print("MODEL CALL END")

    return response
```

Flow:

```text
logging starts
       ↓
handler(request)
       ↓
next middleware/model
       ↓
response
       ↓
logging ends
       ↓
return response
```

This is the essence of middleware.

---

# 62. Security middleware

Now:

```python
@wrap_model_call
def security_middleware(request, handler):

    if not user_allowed(request):
        return blocked_response()

    return handler(request)
```

Notice:

```python
return blocked_response()
```

instead of:

```python
return handler(request)
```

That is the important part.

Security can stop the pipeline.

---

# 63. Logging + security together

Suppose:

```python
middleware = [
    logging_middleware,
    security_middleware,
]
```

Conceptually:

```text
logging
   ↓
security
   ↓
model
```

Execution:

```text
Logging START
       ↓
Security check
       ↓
handler(request)
       ↓
Model
       ↓
Security returns
       ↓
Logging END
```

If security blocks:

```text
Logging START
       ↓
Security BLOCK
       ↓
Logging END
```

That is why outer logging is useful.

---

# 64. Retry middleware is the most revealing example

Consider:

```python
@wrap_model_call
def retry_middleware(request, handler):

    attempts = 0

    while attempts < 3:
        try:
            return handler(request)
        except TemporaryError:
            attempts += 1

    raise RuntimeError("Model failed")
```

Look carefully.

`handler` is a **function passed into another function**.

This is ordinary Python higher-order-function behavior.

LangChain is not inventing a special magical concept here.

It is using standard Python function composition to build an agent execution pipeline.

---

# 65. The lambda mental model

This is probably the best way to understand it permanently.

Imagine LangChain internally creates something conceptually similar to:

```python
model = actual_model


def retry_handler(request):
    return retry_logic(request, model)


def security_handler(request):
    return security_logic(request, retry_handler)


def logging_handler(request):
    return logging_logic(request, security_handler)
```

Then:

```python
logging_handler(request)
```

starts everything.

So the handler is essentially:

```text
the next function in the chain
```

---

# 66. `handler` is NOT a list of middleware

This misconception is very common.

Do not think:

```python
handler = [
    security,
    logging,
    retry,
]
```

No.

Think:

```python
handler = callable
```

More like:

```python
handler(request)
```

where that callable itself may already represent:

```text
the remaining middleware stack
+
the model
```

That's why you don't manually loop:

```python
for middleware in middleware_list:
    ...
```

LangChain composes the middleware for you.

---

# 67. This also explains why retries can wrap everything below them

Suppose:

```text
Logging
   ↓
Retry
   ↓
Model
```

If the model fails:

```text
Retry
   ↓
handler(request)
```

runs again.

Depending on what is inside/outside the retry layer, different middleware may execute again.

This means middleware order can affect:

```text
what gets retried
what gets logged
what gets cached
what gets authorized
```

This is an advanced but very important production concept.

---

# 68. Example: where should authorization go?

Usually authorization should be close to the boundary where the dangerous operation happens.

For tool operations, think:

```text
Agent
 ↓
Authorization
 ↓
HITL
 ↓
Retry
 ↓
Tool
```

Then:

```text
authorization
=
"Can this user perform this tool?"

HITL
=
"Does a human need to approve this particular execution?"

Retry
=
"Can we safely retry this failure?"
```

These are different responsibilities.

---

# 69. Don't make one giant middleware

Avoid this:

```python
def everything(request, handler):

    check_auth()

    redact_pii()

    log()

    metrics()

    route_model()

    retry()

    check_cost()

    check_permissions()

    handle_errors()

    ...
```

This becomes difficult to:

```text
test
reason about
reorder
disable
reuse
debug
```

Prefer composable pieces:

```text
SecurityMiddleware
PIIMiddleware
LoggingMiddleware
ModelRoutingMiddleware
RetryMiddleware
```

This fits the whole design philosophy of LangChain middleware.

---

# 70. Current production-oriented baseline

For a serious enterprise agent, I would conceptually start with these categories:

```text
Security
├── authorization
├── tool allowlists
└── PII handling where required

Reliability
├── model retry
├── tool retry
├── tool error handling
└── fallback

Cost / runaway protection
├── model call limits
└── tool call limits

Context management
├── summarization
└── context editing when necessary

Human control
└── HITL for consequential actions

Observability
└── tracing/logging/metrics

Planning
└── TodoListMiddleware for complex jobs

Delegation
└── SubAgentMiddleware when complexity warrants it
```

You should not blindly turn every middleware on for every agent.

---

# 71. What I would enable by default

For your **enterprise AI harness**, a reasonable baseline is:

```text
YES — almost universally useful

✅ structured logging/observability
✅ model retry
✅ tool retry
✅ controlled tool errors
✅ model call limit
✅ tool call limit
✅ authorization/security middleware
✅ PII handling where your data policy requires it
✅ model fallback if availability matters
```

Then:

```text
ENABLE BASED ON WORKLOAD

✅ summarization
✅ context editing
✅ HITL
✅ tool selection
✅ todo planning
✅ subagents
```

Why conditional?

Because these add behavior, latency or complexity that isn't necessarily appropriate for every agent.

---

# 72. For your specific enterprise harness

Your eventual architecture could look something like:

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

This is very close to the kind of architecture an enterprise AI integration harness eventually needs.

---

# 73. What should be separate from LangChain middleware?

This is also important for your architecture.

Don't try to put everything into LangChain.

For example:

```text
TLS
network firewall
API gateway
OAuth
database RBAC
container isolation
Kubernetes security
secret storage
```

should remain infrastructure/application-level controls.

LangChain middleware is primarily:

```text
agent execution policy
```

not:

```text
entire enterprise security platform
```

Think:

```text
Infrastructure security
        +
Application security
        +
Agent middleware
```

not:

```text
Agent middleware = everything
```

---

# 74. Current vs old LangChain style

This part is especially important because you specifically asked for modern implementation.

## Current direction

For new LangChain v1 agent development:

```python
from langchain.agents import create_agent
```

plus:

```python
middleware=[...]
```

is the modern direction.

The current `create_agent` API directly supports middleware, state schemas, context schemas, checkpointers, stores, structured output, and the model/tool loop. ([LangChain][3])

---

# 75. Old `initialize_agent`

You will still find tutorials like:

```python
initialize_agent(...)
```

This belongs to the old/classic agent architecture.

Current LangChain reference marks `initialize_agent` as deprecated and points to:

```python
create_agent
```

instead. ([LangChain][26])

So for your course:

```text
OLD

initialize_agent()
AgentExecutor
old AgentType patterns

↓

CURRENT

create_agent()
middleware
LangGraph-based agent execution
```

---

# 76. Old `AgentExecutor`

You will also find:

```python
AgentExecutor(...)
```

everywhere in older tutorials.

It still exists in the classic ecosystem for compatibility, but current LangChain documentation describes it as a legacy abstraction and recommends the newer agent architecture for new production development. ([LangChain][26])

So don't make `AgentExecutor` the foundation of your Module 45 learning.

Your foundation should be:

```text
create_agent
+
middleware
+
LangGraph state/checkpointing
```

---

# 77. Another important modern distinction

Older LangChain tutorials often teach:

```text
build an agent manually
   ↓
custom executor
   ↓
custom loop
   ↓
callbacks everywhere
```

The modern v1 architecture pushes more of these concerns toward:

```text
create_agent
+
middleware
+
LangGraph runtime/state
```

That gives you reusable components instead of rebuilding the agent infrastructure yourself.

That fits your preference for:

> "use popular premade components rather than maintain everything from scratch."

---

# 78. The complete mental model you should remember

When you see:

```python
def middleware(request, handler):
```

translate it mentally to:

```text
request
=
"What is happening?"

handler
=
"Continue the pipeline."
```

Then ask:

### Before calling `handler`

```text
Should I allow this?
Should I modify it?
Should I route it?
Should I log it?
Should I redact it?
Should I interrupt?
```

### While calling `handler`

```text
Should I retry?
Should I fallback?
Should I call it once?
Should I call it multiple times?
```

### After calling `handler`

```text
Should I inspect the response?
Log it?
Transform it?
Measure it?
Validate it?
```

That is the core middleware pattern.

---

# 79. The single most useful diagram for you

Memorize this:

```text
                    REQUEST
                       │
                       ▼
              ┌────────────────┐
              │ Middleware A   │
              │                │
              │ security       │
              │ logging        │
              │ routing        │
              └───────┬────────┘
                      │
               handler(request)
                      │
                      ▼
              ┌────────────────┐
              │ Middleware B   │
              │                │
              │ retry          │
              │ fallback       │
              └───────┬────────┘
                      │
               handler(request)
                      │
                      ▼
              ┌────────────────┐
              │ Middleware C   │
              │                │
              │ context        │
              └───────┬────────┘
                      │
               handler(request)
                      │
                      ▼
                ┌───────────┐
                │   MODEL   │
                └─────┬─────┘
                      │
                      ▼
                  RESPONSE
                      │
                      ▼
              Middleware C
                      │
                      ▼
              Middleware B
                      │
                      ▼
              Middleware A
                      │
                      ▼
                   USER
```

The really important part is:

```text
handler(request)
```

is the **bridge from one layer to the next layer**.

---

# 80. And this is why middleware can cooperate

You were specifically asking:

> How does `handler(request)` work when handling multiple functions/activities such as security, logging, etc.?

The answer is:

```text
Each middleware does NOT call every other middleware manually.
```

Instead:

```text
Middleware A
   ↓
handler()
   ↓
Middleware B
   ↓
handler()
   ↓
Middleware C
   ↓
handler()
   ↓
Model
```

Each layer only needs to know:

```text
"What should I do before the next thing?"
"What should I do after the next thing?"
"Should I stop?"
"Should I call the next thing again?"
```

That makes the whole system composable.

---

# 81. Your Module 45 "cheat sheet"

| Middleware                  | Main job                                                 | Model or Tool?         |
| --------------------------- | -------------------------------------------------------- | ---------------------- |
| `HumanInTheLoopMiddleware`  | Human approval/edit/rejection                            | Tool                   |
| `SummarizationMiddleware`   | Compress conversation                                    | Model/context          |
| `ContextEditingMiddleware`  | Clear old tool outputs                                   | Model/context          |
| `ModelRetryMiddleware`      | Retry model failures                                     | Model                  |
| `ToolRetryMiddleware`       | Retry tool failures                                      | Tool                   |
| `ToolErrorMiddleware`       | Convert selected tool failures into `ToolMessage` errors | Tool                   |
| `PIIMiddleware`             | Detect/handle PII                                        | Input/output/tool data |
| `ModelCallLimitMiddleware`  | Limit model calls                                        | Model                  |
| `ToolCallLimitMiddleware`   | Limit tool calls                                         | Tool                   |
| `LLMToolSelectorMiddleware` | Select relevant tools                                    | Before model           |
| `ModelFallbackMiddleware`   | Switch model after failures                              | Model                  |
| custom `wrap_model_call`    | Dynamic routing/custom logic                             | Model                  |
| `TodoListMiddleware`        | Structured task planning                                 | Agent/tool             |
| `SubAgentMiddleware`        | Delegate to child agents                                 | Agent/tool             |

These are all part of the current middleware ecosystem/reference, with Deep Agents adding its own middleware such as `SubAgentMiddleware`. ([LangChain][2])

---

# 82. One final conceptual distinction

You will encounter these four ideas repeatedly:

```text
before_model
after_model
wrap_model_call
wrap_tool_call
```

Think:

```text
before_model
    =
"Do something before the model."

after_model
    =
"Do something after the model."

wrap_model_call
    =
"Put yourself around the model call."

wrap_tool_call
    =
"Put yourself around the tool call."
```

The **`handler` pattern belongs primarily to the wrapper hooks**:

```text
wrap_model_call(request, handler)
wrap_tool_call(request, handler)
```

because those hooks need a way to say:

```text
"Okay, I've done my work. Now continue."
```

That continuation is:

```python
handler(request)
```

The current middleware API explicitly exposes these hooks as the interception mechanism for model and tool execution. ([LangChain][2])

---

## The one sentence I want you to remember

> **`handler(request)` is LangChain's "continue the middleware pipeline with this request" mechanism; it lets one middleware sit around the next middleware/model, while deciding whether to continue, modify the request, stop, retry, or otherwise control execution.**

Once that clicks, the rest of Module 45 becomes much less mysterious.

Your next conceptual step should be to study **middleware ordering as an actual execution trace**—for example, exactly what happens when `Security → Logging → Retry → Model` is combined with `ToolRetry → ToolError → HITL → Tool`, including which `handler()` is being called at every point and why changing the list order changes behavior.

[1]: https://reference.langchain.com/python/langchain/agents/middleware/types/AgentMiddleware/wrap_model_call?utm_source=chatgpt.com "wrap_model_call | langchain | LangChain Reference"
[2]: https://reference.langchain.com/python/langchain/agents/middleware?utm_source=chatgpt.com "middleware | langchain | LangChain Reference"
[3]: https://reference.langchain.com/python/langchain/agents/factory/create_agent?utm_source=chatgpt.com "create_agent | langchain | LangChain Reference"
[4]: https://reference.langchain.com/python/langchain/agents/middleware/human_in_the_loop/HumanInTheLoopMiddleware?utm_source=chatgpt.com "HumanInTheLoopMiddleware | langchain | LangChain Reference"
[5]: https://reference.langchain.com/python/langchain/agents/middleware/human_in_the_loop/InterruptOnConfig?utm_source=chatgpt.com "InterruptOnConfig | langchain | LangChain Reference"
[6]: https://reference.langchain.com/python/langchain/agents/middleware/human_in_the_loop?utm_source=chatgpt.com "human_in_the_loop | langchain | LangChain Reference"
[7]: https://github.com/langchain-ai/docs/blob/main/src/oss/langchain/human-in-the-loop.mdx?utm_source=chatgpt.com "docs/src/oss/langchain/human-in-the-loop.mdx at main · langchain-ai/docs · GitHub"
[8]: https://reference.langchain.com/python/langchain/agents/middleware/summarization/SummarizationMiddleware?utm_source=chatgpt.com "SummarizationMiddleware | langchain | LangChain Reference"
[9]: https://reference.langchain.com/python/langchain-google-genai/langchain_google_genai?utm_source=chatgpt.com "langchain_google_genai | LangChain Reference"
[10]: https://reference.langchain.com/python/langchain/agents/middleware/context_editing?utm_source=chatgpt.com "context_editing | langchain | LangChain Reference"
[11]: https://reference.langchain.com/python/langchain/agents/middleware/context_editing/ClearToolUsesEdit?utm_source=chatgpt.com "ClearToolUsesEdit | langchain | LangChain Reference"
[12]: https://reference.langchain.com/python/langchain/agents/middleware/model_retry/ModelRetryMiddleware?utm_source=chatgpt.com "ModelRetryMiddleware | langchain | LangChain Reference"
[13]: https://reference.langchain.com/python/langchain/agents/middleware/tool_retry?utm_source=chatgpt.com "tool_retry | langchain | LangChain Reference"
[14]: https://reference.langchain.com/python/langchain/agents/middleware/tool_retry/ToolRetryMiddleware?utm_source=chatgpt.com "ToolRetryMiddleware | langchain | LangChain Reference"
[15]: https://reference.langchain.com/python/langchain/agents/middleware/tool_error/ToolErrorMiddleware?utm_source=chatgpt.com "ToolErrorMiddleware | langchain | LangChain Reference"
[16]: https://reference.langchain.com/python/langchain/agents/middleware/model_call_limit/ModelCallLimitMiddleware?utm_source=chatgpt.com "ModelCallLimitMiddleware | langchain | LangChain Reference"
[17]: https://reference.langchain.com/python/langchain/agents/middleware/tool_call_limit/ToolCallLimitMiddleware?utm_source=chatgpt.com "ToolCallLimitMiddleware | langchain | LangChain Reference"
[18]: https://reference.langchain.com/python/langchain/agents/middleware/tool_selection/LLMToolSelectorMiddleware?utm_source=chatgpt.com "LLMToolSelectorMiddleware | langchain | LangChain Reference"
[19]: https://reference.langchain.com/python/langchain/agents/middleware/model_fallback/ModelFallbackMiddleware?utm_source=chatgpt.com "ModelFallbackMiddleware | langchain | LangChain Reference"
[20]: https://reference.langchain.com/python/langchain-openai/langchain_openai/chat_models/base/ChatOpenAI?utm_source=chatgpt.com "ChatOpenAI | langchain_openai | LangChain Reference"
[21]: https://docs.litellm.ai/docs/a2a?utm_source=chatgpt.com "Agent Gateway (A2A Protocol) - Overview | liteLLM"
[22]: https://reference.langchain.com/python/langchain/agents/middleware/todo/TodoListMiddleware?utm_source=chatgpt.com "TodoListMiddleware | langchain | LangChain Reference"
[23]: https://reference.langchain.com/python/deepagents/middleware?utm_source=chatgpt.com "middleware | deepagents | LangChain Reference"
[24]: https://reference.langchain.com/python/deepagents/deepagents?utm_source=chatgpt.com "deepagents | LangChain Reference"
[25]: https://reference.langchain.com/python/deepagents/graph/create_deep_agent?utm_source=chatgpt.com "create_deep_agent | deepagents | LangChain Reference"
[26]: https://reference.langchain.com/python/langchain-classic/agents/initialize?utm_source=chatgpt.com "initialize | langchain_classic | LangChain Reference"
