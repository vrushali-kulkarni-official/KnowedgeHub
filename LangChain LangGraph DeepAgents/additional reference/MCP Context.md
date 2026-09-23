# MCP `Context` — from beginner to advanced with FastMCP 4

This is one of the most important concepts to understand deeply because **`Context` is the bridge between your MCP handler and the runtime around that handler**.

A useful mental model is:

> **Tool arguments are what the caller/model asks your function to do. `Context` is the information and capabilities the MCP runtime gives your function while that request is being executed.**

I’ll build this from the ground up and use the **current FastMCP 4.0.5** APIs as the baseline. FastMCP 4.0.5 was released on September 17, 2026, and FastMCP 4 is the stable line for the new MCP protocol. ([GitHub][1])

There is also a very important protocol change you need to understand before learning `Context`:

**MCP 2026-07-28 made the protocol itself stateless and removed protocol-level sessions from Streamable HTTP.** Older MCP clients can still use the legacy session-based protocol, and FastMCP 4 can serve both. ([GitHub][2])

That distinction will matter especially for **request state, session state, and session visibility**.

---

# 1. First: what problem does `Context` solve?

Imagine you write this:

```python
from fastmcp import FastMCP

mcp = FastMCP("Demo")


@mcp.tool
async def process_file(file_path: str) -> str:
    return f"Processing {file_path}"
```

The caller gives:

```text
file_path = "/reports/2026.csv"
```

That is the obvious input.

But imagine the operation takes 30 seconds.

Your function might also need to know:

* Which MCP request is this?
* Which client called me?
* Can I report progress?
* Can I read another resource exposed by my server?
* Can I retrieve one of my server's prompts?
* Can I store information temporarily during this request?
* Which tools should this particular client see?
* Which transport am I running over?
* What metadata did the client send?
* What FastMCP server am I running inside?
* Which server-side state/resources are available?

You don't want to put all of those things into the model-visible tool schema.

For example, you **do not** want your tool to look like:

```python
async def process_file(
    file_path: str,
    request_id: str,
    client_id: str,
    progress_callback: ...,
    server: ...,
    session_id: str,
):
    ...
```

Those aren't business arguments.

They are **runtime dependencies**.

That's where `Context` comes in.

FastMCP injects a context dependency into your tool/resource/prompt, and dependency parameters are kept out of the MCP schema exposed to clients. ([GitHub][3])

---

# 2. The most important mental model

Think about three layers:

```text
                  MCP CLIENT / AGENT
                         │
                         │
                         │ tool call
                         ▼
              ┌─────────────────────┐
              │      MCP SERVER     │
              │                     │
              │  Tool arguments     │
              │       +             │
              │     Context         │
              │                     │
              └──────────┬──────────┘
                         │
              ┌──────────┴──────────┐
              │                     │
         Business input         Runtime info
         from caller            from MCP/FastMCP
              │                     │
        file_path="x"       request_id
                             progress
                             metadata
                             resources
                             state
                             session
                             server
```

So:

```python
async def my_tool(
    file_path: str,
    ctx: Context,
):
    ...
```

means:

```text
file_path
    ↓
provided by the MCP caller/model

ctx
    ↓
provided by FastMCP itself
```

The model sees `file_path`.

The model **doesn't see `ctx` as a tool argument**. ([GitHub][3])

That distinction is fundamental.

---

# 3. Current FastMCP way of injecting `Context`

There are actually several styles you'll encounter.

## Current preferred style

FastMCP 4's current documentation prefers dependency injection with `CurrentContext()`:

```python
from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context

mcp = FastMCP("Context Demo")


@mcp.tool
async def process_file(
    file_path: str,
    ctx: Context = CurrentContext(),
) -> str:
    await ctx.info(f"Processing {file_path}")
    return f"Processed {file_path}"
```

The important part is:

```python
ctx: Context = CurrentContext()
```

FastMCP recognizes this as a dependency.

The client still sees only:

```text
file_path
```

in the tool schema. ([GitHub][3])

---

# 4. What about this older style?

You'll see:

```python
async def process_file(
    file_path: str,
    ctx: Context,
):
    ...
```

This still works in FastMCP 4 for backwards compatibility. The current docs explicitly call it **legacy type-hint injection**. ([GitHub][3])

So learn to recognize both:

```python
# Current preferred style
ctx: Context = CurrentContext()
```

and:

```python
# Older but still supported
ctx: Context
```

For your new code, I'd learn the first one.

---

# 5. Why `CurrentContext()` is interesting

It is part of FastMCP's dependency-injection system.

Conceptually:

```text
your function
      │
      │ asks for Context
      ▼
FastMCP dependency system
      │
      │ finds current request
      ▼
Context object for THIS request
      │
      ├── request ID
      ├── metadata
      ├── progress channel
      ├── resource access
      ├── prompt access
      ├── request state
      ├── visibility
      └── server access
```

This is conceptually similar to FastAPI dependencies.

For example, in FastAPI you might write:

```python
async def endpoint(request: Request):
    ...
```

and the framework gives you the current request.

In FastMCP:

```python
async def tool(ctx: Context = CurrentContext()):
    ...
```

and FastMCP gives you the current MCP context.

---

# 6. One Context object per request

This is extremely important.

Suppose client A makes:

```text
tools/call #1
```

FastMCP creates a context for that request.

Then:

```text
tools/call #2
```

gets another request context.

Conceptually:

```text
Request #101
    └── Context #101

Request #102
    └── Context #102

Request #103
    └── Context #103
```

You should **not** treat `Context` as some global singleton containing everybody's state.

It represents the execution environment of the current operation. FastMCP's current docs explicitly state that context is available during a request and that request state is discarded when the request returns. ([GitHub][3])

---

# 7. The capabilities you asked about

We'll now go through:

1. Logging
2. Progress reporting
3. Resource access
4. Prompt access
5. Request state
6. Request metadata
7. Server access
8. Session visibility
9. Related session state
10. Transport/request/session identity
11. What happens with FastAPI
12. Deprecated/old vs modern MCP

---

# 8. Logging

There are actually **two very different things** people call logging here.

This distinction is extremely important.

## A. Application/server logging

This means:

```text
your MCP server
        ↓
logs for operators/developers
        ↓
stdout/stderr/files/OpenTelemetry/log collector
```

For example:

```python
import logging

logger = logging.getLogger(__name__)


@mcp.tool
async def process_file(
    file_path: str,
    ctx: Context = CurrentContext(),
):
    logger.info("Processing file %s", file_path)

    ...
```

This is normal Python logging.

For production systems, you can later connect this to:

* Python `logging`
* structured logging
* OpenTelemetry
* Grafana/Loki
* ELK/OpenSearch
* cloud logging
* your own observability pipeline

This is the logging model I'd use for an enterprise MCP server.

---

# 9. What are `ctx.info()`, `ctx.debug()`, etc.?

You may see:

```python
await ctx.debug("Starting")
await ctx.info("Processing")
await ctx.warning("Something looks suspicious")
await ctx.error("Something failed")
```

FastMCP still exposes these APIs. ([GitHub][3])

However, there is an important **modern MCP warning**.

The MCP specification dated **2026-07-28 deprecated protocol-level Logging**. New implementations are explicitly advised not to build new systems around MCP Logging. The specification recommends ordinary logging to stderr for stdio or observability tooling such as OpenTelemetry instead. ([GitHub][2])

So:

```text
ctx.info()
ctx.debug()
ctx.warning()
ctx.error()
```

are something you should **understand** because you'll encounter them, but don't make MCP's deprecated logging capability the foundation of your production observability design.

### Modern recommendation

Use:

```python
logger.info(...)
```

for server/operator logs.

Use OpenTelemetry for serious distributed observability.

Use `Context` primarily for the capabilities that are actually useful to the MCP request itself, such as:

```text
progress
resource access
prompt access
request state
request metadata
session-specific visibility
```

---

# 10. Why was MCP Logging deprecated?

Originally MCP had a mechanism like:

```text
server
  ↓
notifications/message
  ↓
client
```

So the server could say:

```text
"Downloading..."
"50% complete..."
"Finished"
```

But modern MCP moved toward cleaner request semantics and statelessness.

The 2026-07-28 specification formally deprecated Roots, Sampling, and Logging. ([GitHub][2])

Therefore don't confuse:

```text
logging
```

with:

```text
progress
```

Those are different concerns.

---

# 11. Progress reporting

Progress is still extremely useful.

Imagine:

```python
@mcp.tool
async def import_large_dataset(
    files: list[str],
    ctx: Context = CurrentContext(),
) -> str:
    ...
```

Without progress:

```text
User:
    "Import these 20 files"

         ↓

        30 sec silence

         ↓

    "Done"
```

That is terrible UX.

With progress:

```text
0/20
1/20
2/20
...
19/20
20/20
```

The client can render:

```text
████████████████░░░░ 80%
```

or:

```text
Importing file 16/20
```

The server reports progress; the client decides how to display it. ([GitHub][4])

---

# 12. Basic progress example

```python
from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context

mcp = FastMCP("Progress Demo")


@mcp.tool
async def import_files(
    files: list[str],
    ctx: Context = CurrentContext(),
) -> str:

    total = len(files)

    for index, file in enumerate(files, start=1):
        # Do the actual work
        await process_file(file)

        await ctx.report_progress(
            progress=index,
            total=total,
            message=f"Processed {file}",
        )

    return f"Imported {total} files"
```

The important method is:

```python
await ctx.report_progress(
    progress=...,
    total=...,
    message=...,
)
```

The MCP SDK requires progress to increase rather than stay the same or move backwards. ([GitHub][4])

---

# 13. What does `progress` actually mean?

This is subtle.

It doesn't have to mean:

```text
percentage
```

You could use:

```text
progress = number of files processed
total = total number of files
```

or:

```text
progress = rows processed
total = total rows
```

or:

```text
progress = bytes downloaded
total = content length
```

For example:

```python
await ctx.report_progress(
    progress=500,
    total=10000,
    message="Downloaded 500 rows",
)
```

means:

```text
500 / 10000
```

The client may turn that into 5%.

---

# 14. What if you don't know the total?

Don't lie.

Bad:

```python
await ctx.report_progress(5, 100)
```

when you actually have no idea whether there will be 10 items or 50,000 items.

Instead:

```python
await ctx.report_progress(
    progress=5,
    message="Processed 5 records",
)
```

Then:

```text
total = None
```

The client cannot show a percentage, but it can show activity. ([GitHub][4])

---

# 15. Very important: progress ≠ logging

Imagine downloading 100 files.

### Progress

```text
17 / 100
```

is telling the **client/user**:

> How far along is this operation?

### Logging

```text
HTTP GET https://internal-api/files/17
status=200
duration_ms=120
```

is telling the **operator/developer**:

> What happened internally?

So:

```text
Progress
    → user experience

Logging
    → observability/debugging
```

This distinction becomes very important in production.

---

# 16. Resource access through Context

Now a more interesting capability.

Suppose your MCP server has:

```python
@mcp.resource("resource://company/policy")
async def company_policy() -> str:
    return "Company policy..."
```

Normally a client can request the resource.

But suppose a tool itself needs the resource.

You can do:

```python
data = await ctx.read_resource(
    "resource://company/policy"
)
```

FastMCP exposes both resource listing and resource reading through `Context`. ([GitHub][5])

---

# 17. Complete resource example

```python
from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context

mcp = FastMCP("Resource Demo")


@mcp.resource("resource://company/policy")
async def company_policy() -> str:
    return """
    Employees must not expose customer secrets.
    """


@mcp.tool
async def check_request(
    request: str,
    ctx: Context = CurrentContext(),
) -> str:

    resource_result = await ctx.read_resource(
        "resource://company/policy"
    )

    policy = resource_result.contents[0].content

    return f"""
Request:
{request}

Policy:
{policy}
"""
```

Conceptually:

```text
tool
 │
 │ ctx.read_resource(...)
 ▼
FastMCP resource registry
 │
 ▼
resource://company/policy
 │
 ▼
resource function
 │
 ▼
ResourceResult
```

---

# 18. Why is this useful?

This becomes useful when you want tools to compose server capabilities.

For example:

```text
Tool
 │
 ├── read configuration resource
 ├── read policy resource
 ├── read user data resource
 └── perform operation
```

Imagine:

```text
Tool: approve_expense()
```

Before approving:

```text
read resource://policies/expense-approval
```

Then:

```text
read resource://employees/{employee_id}
```

Then perform the approval.

This can make an MCP server modular.

---

# 19. `list_resources()`

You can also ask:

```python
resources = await ctx.list_resources()
```

FastMCP currently documents:

```python
ctx.list_resources()
ctx.read_resource(uri)
```

as the resource access methods. ([GitHub][3])

For example:

```python
resources = await ctx.list_resources()

for resource in resources:
    print(resource.uri)
```

This is useful for:

* discovery
* dynamic tool behavior
* administrative tooling
* debugging
* inspecting mounted providers

But don't blindly expose an internal list of resources to a model just because your server can enumerate them.

Discovery itself is a security and information-disclosure consideration.

---

# 20. Resource URI vs filesystem path

This distinction is very important.

A resource:

```text
resource://company/policy
```

is an MCP resource identifier.

It doesn't necessarily mean:

```text
/path/on/disk/company/policy
```

MCP resources are an abstraction.

The implementation behind:

```text
resource://customer/123
```

could be:

```text
PostgreSQL
Redis
filesystem
REST API
object storage
generated content
memory
```

So don't mentally equate:

```text
resource URI
```

with:

```text
file path
```

---

# 21. Prompt access through Context

This one is often misunderstood.

A **prompt** in MCP is a registered prompt template.

For example:

```python
@mcp.prompt
def analyze_data(dataset: str) -> str:
    return f"""
    Analyze the following dataset:

    {dataset}
    """
```

Another part of your MCP server can retrieve it through Context.

FastMCP exposes:

```python
await ctx.list_prompts()
```

and:

```python
await ctx.get_prompt(...)
```

for this. ([GitHub][3])

---

# 22. Example

```python
@mcp.prompt
def analyze_data(dataset: str) -> str:
    return f"Analyze the dataset: {dataset}"


@mcp.tool
async def run_analysis(
    dataset_name: str,
    ctx: Context = CurrentContext(),
):

    result = await ctx.get_prompt(
        "analyze_data",
        {"dataset": dataset_name},
    )

    messages = result.messages

    return {
        "messages": messages,
    }
```

Conceptually:

```text
Tool
  │
  │ get_prompt()
  ▼
Prompt registry
  │
  ▼
analyze_data
  │
  ▼
rendered prompt
  │
  ▼
messages
```

---

# 23. Why would a server want another server prompt?

At first this might seem strange.

Why not just write:

```python
prompt = f"Analyze {dataset}"
```

inside the tool?

Because the prompt itself can be a reusable MCP component.

Imagine a large enterprise MCP server containing:

```text
prompts/
    financial_analysis
    security_review
    legal_summary
    customer_response
    incident_analysis
```

Then multiple tools can use standardized prompt templates.

This gives you a sort of:

```text
prompt catalog
```

inside the MCP server.

---

# 24. `list_prompts()`

You can inspect available prompts:

```python
prompts = await ctx.list_prompts()
```

Then:

```python
for prompt in prompts:
    print(prompt.name)
```

Current FastMCP documents both:

```python
ctx.list_prompts()
ctx.get_prompt(name, arguments)
```

as the prompt-access APIs. ([GitHub][3])

---

# 25. Request state

This is one of the most important parts.

Suppose your request goes through:

```text
Middleware
      ↓
Tool
      ↓
Helper
```

Middleware figures out:

```text
user_id = "alice"
```

But your tool needs `user_id`.

You could pass it manually:

```python
await tool(..., user_id=user_id)
```

But that's undesirable because `user_id` is not really a user/model tool argument.

FastMCP provides **request state**.

---

# 26. Request-state mental model

Think:

```text
ONE MCP REQUEST
─────────────────────────────────────────

Middleware
    │
    │ set_state("user_id", "alice")
    ▼
Request Context
    │
    ▼
Tool
    │
    │ get_state("user_id")
    ▼
"alice"

─────────────────────────────────────────
request ends
─────────────────────────────────────────

state disappears
```

Current FastMCP exposes:

```python
await ctx.set_state(...)
await ctx.get_state(...)
await ctx.delete_state(...)
```

for request-scoped state. ([GitHub][3])

---

# 27. Example middleware → tool

```python
from fastmcp.server.middleware import Middleware, MiddlewareContext


class AddUser(Middleware):

    async def on_call_tool(self, context, call_next):

        if context.fastmcp_context:
            await context.fastmcp_context.set_state(
                "user_id",
                "alice",
            )

        return await call_next(context)
```

Then:

```python
@mcp.tool
async def who_am_i(
    ctx: Context = CurrentContext(),
) -> str:

    user_id = await ctx.get_state("user_id")

    return f"You are {user_id}"
```

This creates an internal communication channel:

```text
Middleware
      │
      │ request state
      ▼
Context
      │
      ▼
Tool
```

FastMCP specifically documents this middleware → handler pattern. ([GitHub][3])

---

# 28. Why not use a normal Python variable?

You might think:

```python
user_id = ...
```

and then access it from another function.

The problem is execution architecture.

FastMCP may have:

```text
middleware
    ↓
dispatch machinery
    ↓
authorization
    ↓
transforms
    ↓
tool execution
```

Those layers don't share a simple function stack.

Request state gives you a framework-managed place to put request-specific information.

---

# 29. Serializable request state

By default:

```python
await ctx.set_state(
    "user_id",
    "alice",
)
```

stores a serializable value.

This is useful for things like:

```text
user_id
tenant_id
trace_id
request policy
authorization decisions
feature flags
configuration
correlation information
```

---

# 30. Non-serializable request state

Now the really useful part.

Suppose middleware creates:

```python
http_client = ...
```

You don't want to serialize that.

It might contain sockets, connection pools, locks, etc.

FastMCP allows:

```python
await ctx.set_state(
    "http_client",
    http_client,
    serializable=False,
)
```

Then:

```python
client = await ctx.get_state("http_client")
```

You can use that client during the current request. FastMCP specifically documents non-serializable request-scoped resources such as database connections or HTTP clients. ([GitHub][3])

---

# 31. Extremely important state distinction

You now need to understand **three different types of state**.

```text
                 STATE
                   │
        ┌──────────┼──────────┐
        │          │          │
   Local Python  Request   Persistent/
     variable    state      session state
```

### Local Python variable

```python
user_id = "alice"
```

Lifetime:

```text
current function / call stack
```

### Request state

```python
await ctx.set_state(...)
```

Lifetime:

```text
current MCP request
```

### Session/application state

```python
UserSession
SessionId
```

Lifetime:

```text
across multiple MCP requests
```

This distinction is critical.

---

# 32. Do NOT use request state for this

Don't do:

```python
await ctx.set_state("shopping_cart", cart)
```

expecting it to survive:

```text
tool call #1
     ↓
tool call #2
     ↓
tool call #3
```

Request state ends with the request.

FastMCP's current documentation explicitly directs developers to separate request state from state that persists across calls. ([GitHub][3])

---

# 33. Modern MCP changed the meaning of "session"

This is where older tutorials can really confuse you.

Old MCP:

```text
initialize
   ↓
session established
   ↓
Middleware, MiddlewareContext many requests
   ↓
same MCP session
```

Modern MCP 2026-07-28:

```text
request #1 ── independent
request #2 ── independent
request #3 ── independent
```

The protocol removed the `initialize`/`initialized` handshake and the `Mcp-Session-Id` header from Streamable HTTP. ([GitHub][2])

---

# 34. So how do you maintain application state now?

FastMCP 4 introduced explicit application-level state mechanisms for the modern stateless protocol.

Two important concepts are:

```text
UserSession
```

and:

```text
SessionId
```

FastMCP describes these as explicit server-side application sessions rather than relying on an MCP protocol session. ([Jiezhi's Blog][6])

---

# 35. `UserSession`

Imagine:

```text
authenticated user = Alice

Alice
 └── state
      ├── selected_project
      ├── current_customer
      └── workflow_id
```

You can inject a `UserSession`.

Conceptually:

```python
from fastmcp.server.sessions import UserSession


@mcp.tool
async def remember(
    fact: str,
    session: UserSession,
) -> str:

    await session.set("fact", fact)

    return "Remembered"
```

Then another request can read:

```python
value = await session.get("fact")
```

The key difference is:

```text
Context request state
    → one request

UserSession
    → across requests
```

Modern FastMCP keys `UserSession` state to the authenticated principal. ([Jiezhi's Blog][6])

---

# 36. Why authentication matters

This is an important security detail.

Suppose you have:

```text
session_id = "abc123"
```

If sessions are unauthenticated, that identifier can effectively become a bearer capability.

Someone who obtains it may be able to access the session.

Modern FastMCP therefore emphasizes:

```text
authentication
        +
server-side state
        +
principal isolation
```

rather than treating a random session identifier itself as a complete security boundary. ([Jiezhi's Blog][7])

For your eventual enterprise AI harness, this is a very important design principle.

---

# 37. `SessionId`

Sometimes one user needs multiple independent sessions.

For example:

```text
Alice
 ├── project A
 ├── project B
 └── project C
```

Then FastMCP supports a `SessionId` argument.

The agent can hold:

```text
session_id = "..."
```

and pass it on later calls.

FastMCP can validate that the session belongs to the authenticated principal. ([Jiezhi's Blog][6])

---

# 38. Request metadata

Now let's discuss:

```python
ctx.request_context.meta
```

This is different from request state.

### Request state

Server-side:

```text
middleware
    ↓
server
```

### Request metadata

Caller-provided:

```text
client
    ↓
MCP request metadata
    ↓
server
```

Current FastMCP exposes client metadata through:

```python
ctx.request_context.meta
```

when provided. ([GitHub][3])

---

# 39. What is `_meta`?

At the MCP protocol level, requests can carry a `_meta` object.

Conceptually:

```json
{
  "method": "tools/call",
  "params": {
    "name": "search",
    "arguments": {
      "query": "postgres"
    },
    "_meta": {
      "some.client.metadata": "value"
    }
  }
}
```

The metadata is not necessarily part of the normal tool arguments.

It is contextual protocol metadata.

Modern MCP also uses `_meta` for protocol information such as client information and capabilities. ([GitHub][2])

---

# 40. Example of reading metadata

Conceptually:

```python
@mcp.tool
async def send_email(
    to: str,
    subject: str,
    ctx: Context = CurrentContext(),
):

    meta = ctx.request_context.meta

    if meta:
        ...
```

FastMCP's current docs demonstrate accessing client-provided metadata through `ctx.request_context.meta`. ([GitHub][3])

---

# 41. VERY IMPORTANT: metadata is not automatically trustworthy

Suppose the client sends:

```json
{
    "_meta": {
        "user_id": "admin"
    }
}
```

You must **not** conclude:

```text
user is admin
```

because the client said so.

That is merely:

```text
client-supplied metadata
```

not:

```text
verified identity
```

For authorization:

```text
❌ trust _meta.user_id

✅ trust verified authentication context
```

This distinction becomes critical in enterprise environments.

---

# 42. Good uses for metadata

Metadata can be useful for:

```text
locale = "en-IN"
timezone = "Asia/Kolkata"
UI preference
feature flags
trace correlation
client capability hints
non-security routing hints
request behavior hints
```

Example:

```text
locale = "en-IN"
```

might influence formatting:

```text
₹1,25,000
```

rather than:

```text
$1,250
```

But metadata should not automatically become an authorization decision.

---

# 43. Request ID

Another important Context property:

```python
ctx.request_id
```

This identifies the current MCP request. FastMCP documents it as request-specific metadata. ([GitHub][3])

Imagine:

```text
request_id = 8c6...
```

Then your logs can contain:

```text
INFO request=8c6... Starting tool
INFO request=8c6... Querying postgres
INFO request=8c6... Finished
```

This lets you connect multiple events to one request.

---

# 44. Request ID vs session ID

Don't confuse:

```text
request ID
```

with:

```text
session ID
```

Conceptually:

```text
REQUEST ID
    identifies ONE request

SESSION ID
    identifies a broader application session
    when you're using a session concept
```

For example:

```text
Alice's session
    ├── request A
    ├── request B
    └── request C
```

would conceptually look like:

```text
session = S1

request = R1
request = R2
request = R3
```

However, under the modern MCP 2026-07-28 protocol, there is no longer a protocol-level HTTP session ID. FastMCP's application-level `UserSession`/`SessionId` should not be confused with the old MCP `Mcp-Session-Id`. ([GitHub][2])

---

# 45. Client ID

FastMCP also exposes:

```python
ctx.client_id
```

when the client identifies itself.

This is useful for:

```text
observability
debugging
analytics
client-specific behavior
```

But again:

```text
client_id
```

is not automatically equivalent to:

```text
authenticated human identity
```

Those are separate concepts.

---

# 46. Transport information

FastMCP also exposes:

```python
ctx.transport
```

Possible values documented currently include:

```text
stdio
sse
streamable-http
```

The current FastMCP docs note that SSE is available for compatibility, while new deployments should use Streamable HTTP. ([GitHub][3])

Example:

```python
transport = ctx.transport

if transport == "stdio":
    ...
elif transport == "streamable-http":
    ...
```

---

# 47. Why would a tool care about transport?

Most tools shouldn't.

But infrastructure-oriented tools sometimes need different behavior.

For example:

```text
stdio
    local process
    simple
    no HTTP headers

streamable HTTP
    remote
    network
    authentication
    HTTP headers
    load balancing
```

You might adjust:

```text
timeouts
response formatting
debugging
network assumptions
```

based on transport.

But avoid scattering transport-specific logic throughout your business layer.

A better architecture is:

```text
transport-specific concern
          ↓
middleware / adapter
          ↓
domain code
```

---

# 48. HTTP request vs MCP request

This is another subtle but important concept.

For HTTP transport you can have:

```text
HTTP request
```

and:

```text
MCP request
```

They are related, but not identical.

FastMCP explicitly distinguishes the MCP request context from the HTTP request. ([GitHub][3])

That means:

```python
ctx.request_context
```

is not the same thing as:

```python
fastapi.Request
```

---

# 49. When to use the HTTP request

If you need:

```text
HTTP headers
client IP
HTTP method
raw HTTP details
```

use FastMCP's HTTP dependency helpers such as:

```python
get_http_request()
get_http_headers()
```

rather than trying to treat the MCP context as a normal FastAPI request. ([GitHub][3])

Conceptually:

```text
                HTTP request
                    │
                    ▼
             FastMCP transport
                    │
                    ▼
              MCP request
                    │
                    ▼
                 Context
```

---

# 50. Server access

Sometimes you need access to the actual FastMCP server instance.

FastMCP exposes:

```python
ctx.fastmcp
```

For example:

```python
@mcp.tool
async def server_info(
    ctx: Context = CurrentContext(),
) -> str:

    return ctx.fastmcp.name
```

The current FastMCP documentation explicitly provides `ctx.fastmcp` for this purpose. ([GitHub][3])

---

# 51. Why would a tool need the server?

Potential uses include:

```text
inspect server configuration
inspect registered components
access providers
component management
dynamic behavior
administrative operations
```

For example, FastMCP supports server-side component access such as:

```python
await ctx.fastmcp.list_tools()
```

or retrieving a specific component through the server.

Current FastMCP's architecture uses providers/transforms/components heavily, so this becomes more powerful than simply having a list of decorated functions. ([GitHub][8])

---

# 52. But don't overuse `ctx.fastmcp`

This is an architectural warning.

You could write:

```python
@mcp.tool
async def some_tool(ctx: Context = CurrentContext()):
    tool = await ctx.fastmcp.get_tool(...)
    ...
```

But if every business function starts reaching into:

```text
ctx.fastmcp
ctx.request_context
ctx.transport
ctx.session
```

your domain code becomes tightly coupled to FastMCP.

A healthier architecture is:

```text
MCP layer
   │
   ├── Context
   ├── metadata
   ├── authentication
   └── transport
        │
        ▼
Application layer
        │
        ▼
Domain layer
        │
        ▼
Database / APIs
```

Your domain code shouldn't know that MCP exists whenever possible.

---

# 53. Session visibility

Now we get to a particularly interesting FastMCP feature.

Suppose your MCP server has:

```text
20 tools
10 resources
8 prompts
```

But Alice should only see:

```text
5 tools
3 resources
```

while Bob should see:

```text
12 tools
7 resources
```

FastMCP has component visibility mechanisms.

Current Context exposes:

```python
ctx.enable_components(...)
ctx.disable_components(...)
ctx.reset_visibility()
```

and they affect visibility for the current session without changing other sessions. ([GitHub][5])

---

# 54. Example: enable one tool

Conceptually:

```python
await ctx.enable_components(
    names={"advanced_search"}
)
```

Now the current session can see:

```text
advanced_search
```

while other sessions are unaffected.

---

# 55. Tag-based visibility

You can tag tools:

```python
@mcp.tool(tags={"public"})
def search_public(...):
    ...


@mcp.tool(tags={"admin"})
def delete_user(...):
    ...
```

Then visibility can be controlled by tag.

FastMCP's visibility model supports tag-based filtering across components. ([GitHub][9])

Conceptually:

```text
public
 ├── search
 ├── help
 └── status

admin
 ├── delete_user
 ├── audit_logs
 └── system_config
```

---

# 56. Example role-based visibility

You could have:

```text
employee
    ↓
enable public

manager
    ↓
enable public + manager

admin
    ↓
enable public + manager + admin
```

This is very useful for your future enterprise AI harness idea.

For example:

```text
Employee
 ├── HR policies
 ├── search company docs
 └── create ticket

Manager
 ├── everything above
 ├── team reports
 └── approvals

Admin
 ├── everything above
 ├── audit
 ├── user administration
 └── security tools
```

---

# 57. But visibility is NOT authorization

This is perhaps the most important security warning in the visibility section.

Hiding:

```text
delete_database
```

from the tool listing does not magically become an authorization mechanism.

FastMCP's current documentation explicitly warns that when something must **never** be reachable, you should not rely on visibility alone; use authentication/authorization or don't register the component. ([GitHub][9])

So:

```text
Visibility
    = what should this client/session see?

Authorization
    = what is this identity actually allowed to do?
```

They're different.

---

# 58. Example

Suppose:

```python
@mcp.tool(tags={"admin"})
async def delete_user(user_id: str):
    ...
```

You hide it from ordinary employees.

Good.

But you still need:

```text
authentication
+
authorization
```

before deleting the user.

The correct mental model:

```text
             request
                │
          authenticated?
                │
          authorized?
                │
             allowed
                │
        visible component?
                │
              tool
```

Visibility is part of the UX/component surface.

Authorization is the security boundary.

---

# 59. Visibility vs provider vs middleware

FastMCP 3/4's architecture gives you several layers to control behavior.

Think:

```text
Provider
    ↓
creates/obtains components

Transform / visibility
    ↓
controls which components are exposed

Middleware
    ↓
controls request execution

Authorization
    ↓
controls access

Tool
    ↓
does actual work
```

That is far more scalable than writing giant `if user.role == ...` blocks inside every tool.

FastMCP's provider/transform architecture became a major part of the framework beginning with v3. ([GitHub][1])

---

# 60. `get_context()` for deeper helper functions

Suppose you have:

```python
@mcp.tool
async def analyze(...):
    await helper(...)
```

and:

```python
async def helper(...):
    ...
```

The helper doesn't receive:

```python
ctx
```

You have two approaches.

### Preferred architecture

Pass it explicitly:

```python
async def helper(ctx: Context, data):
    ...
```

This is dependency-transparent.

### FastMCP context lookup

FastMCP also provides:

```python
from fastmcp.server.dependencies import get_context
```

Then:

```python
async def helper(data):

    ctx = get_context()

    await ctx.info("Processing")
```

Current FastMCP documents `get_context()` for nested code that needs the active request context. It only works within an active MCP request. ([GitHub][3])

---

# 61. Why shouldn't you use `get_context()` everywhere?

Because this:

```python
async def helper():
    ctx = get_context()
```

hides a dependency.

Someone reading:

```python
await helper()
```

can't tell that:

```text
helper()
```

silently depends on:

```text
an active FastMCP request
```

Whereas:

```python
await helper(ctx)
```

makes the dependency obvious.

So I'd use:

```text
Context parameter
    ↓
normal MCP boundary
```

and:

```text
get_context()
    ↓
occasionally useful for deep framework-oriented helpers
```

---

# 62. Context lifecycle

Let's visualize a request.

```text
MCP client
    │
    │ tools/call
    ▼
Transport
    │
    ▼
FastMCP request dispatcher
    │
    ▼
Create/request Context
    │
    ▼
Middleware
    │
    ├── authentication
    ├── metadata extraction
    ├── request state
    ├── authorization
    └── logging/tracing
    │
    ▼
Tool
    │
    ├── ctx.report_progress()
    ├── ctx.read_resource()
    ├── ctx.get_prompt()
    ├── ctx.get_state()
    └── ctx...
    │
    ▼
Result
    │
    ▼
Context/request ends
```

This picture is worth remembering.

---

# 63. Context is not a database

Don't treat:

```python
ctx.set_state(...)
```

as:

```text
database storage
```

It's runtime state.

For durable data:

```text
PostgreSQL
Redis
object storage
etc.
```

For request-local state:

```text
Context
```

For application session state:

```text
UserSession / SessionId
```

For domain state:

```text
database
```

That's a clean separation.

---

# 64. Context is also not "the user"

Another frequent beginner mistake is:

```python
ctx.client_id
```

and then assuming:

```text
client_id = authenticated employee
```

No.

A client can identify itself.

Authentication establishes identity.

For an enterprise system:

```text
MCP client
    ↓
OAuth / authentication
    ↓
verified principal
    ↓
authorization
    ↓
tool access
```

Use `Context` to reach runtime information, but don't invent your security model from arbitrary metadata.

---

# 65. FastAPI integration

Because you're learning:

```text
FastMCP + FastAPI
```

this is worth seeing.

Modern FastMCP provides an ASGI application that you mount into FastAPI.

A current pattern is:

```python
from fastapi import FastAPI
from fastmcp import FastMCP

mcp = FastMCP("My MCP Server")


@mcp.tool
async def hello(name: str) -> str:
    return f"Hello {name}"


mcp_app = mcp.http_app(path="/")

app = FastAPI(
    lifespan=mcp_app.lifespan,
)

app.mount(
    "/mcp",
    mcp_app,
)
```

The official FastMCP documentation recommends passing the MCP application's lifespan into the parent FastAPI application. ([GitHub][10])

---

# 66. Your resulting application

You can think of your server like:

```text
                   FastAPI
                     │
       ┌─────────────┴──────────────┐
       │                            │
       ▼                            ▼
 /api/users                    /mcp
 /api/health                   MCP endpoint
 /api/admin                        │
                                  ▼
                              FastMCP
                                  │
                         ┌────────┼────────┐
                         │        │        │
                       tools  resources  prompts
```

So FastMCP doesn't have to replace FastAPI.

It can be one part of your application.

---

# 67. Modern HTTP transport

For new deployments:

```text
Streamable HTTP
```

is the modern choice.

FastMCP's docs describe SSE as a legacy compatibility transport, while recommending Streamable HTTP for new applications. ([GitHub][11])

So don't build a new project around:

```python
transport="sse"
```

unless you specifically need compatibility with an older client.

---

# 68. Old vs current: the table you should remember

| Topic                        | Older approach               | Current direction                                                      |
| ---------------------------- | ---------------------------- | ---------------------------------------------------------------------- |
| HTTP transport               | HTTP+SSE                     | **Streamable HTTP**                                                    |
| Protocol handshake           | `initialize` / `initialized` | **Removed in 2026-07-28 protocol**                                     |
| MCP HTTP session             | `Mcp-Session-Id`             | **Removed from modern protocol**                                       |
| Cross-call state             | protocol session state       | **Application-level state such as `UserSession` / `SessionId`**        |
| Context injection            | `ctx: Context`               | **`ctx: Context = CurrentContext()` preferred; old style still works** |
| Server logging               | MCP Logging                  | **Python logging / OpenTelemetry preferred**                           |
| MCP Logging API              | `logging/setLevel` etc.      | **Deprecated**                                                         |
| Server sampling              | `ctx.sample()`               | **Removed from FastMCP 4 server API; call your LLM directly**          |
| Roots                        | `ctx.list_roots()`           | **Removed from FastMCP 4 server API**                                  |
| Tool progress                | progress notifications       | **Still current**                                                      |
| Resource access              | `ctx.read_resource()`        | **Current**                                                            |
| Prompt access                | `ctx.get_prompt()`           | **Current**                                                            |
| Request state                | context request state        | **Current for one request**                                            |
| Persistent application state | old session semantics        | **`UserSession` / `SessionId` on modern protocol**                     |
| Per-session visibility       | supported                    | **Current FastMCP capability**                                         |

The protocol-level deprecations and statelessness come from the 2026-07-28 MCP specification, while the FastMCP-specific state/session and visibility mechanisms are current FastMCP features. ([GitHub][2])

---

# 69. One particularly important deprecated area: Sampling

Because you're also learning LangChain, this is especially relevant to you.

Older MCP tutorials may show something like:

```python
await ctx.sample(...)
```

This meant:

```text
MCP server
    ↓
ask client
    ↓
client's LLM
    ↓
answer
    ↓
server
```

But modern MCP/FastMCP has moved away from that server-initiated pattern.

FastMCP 4 removed server-side sampling APIs because the modern stateless protocol no longer has the same live server-to-client request channel. The recommended model is to perform generation directly on the server, or use the modern multi-round-trip interaction pattern where appropriate. ([GitHub][3])

For your preference, that means your future architecture can be:

```text
MCP Tool
   │
   ▼
LangChain
   │
   ▼
Gemini
```

instead of making an MCP sampling mechanism the dependency.

That fits your preferred LangChain/Gemini architecture nicely.

---

# 70. How all of these features fit together

Let's create a realistic enterprise tool.

Suppose:

```python
@mcp.tool
async def analyze_invoice(
    invoice_id: str,
    ctx: Context = CurrentContext(),
):
    ...
```

What might happen?

### Step 1 — authentication

Middleware verifies:

```text
employee = bhargav
tenant = company_a
role = finance_manager
```

### Step 2 — request state

Middleware stores:

```python
await ctx.set_state("tenant_id", "company_a")
await ctx.set_state("role", "finance_manager")
```

### Step 3 — tool begins

Tool gets:

```text
invoice_id
```

from the caller.

Context provides:

```text
request ID
metadata
state
transport
server access
```

### Step 4 — progress

```python
await ctx.report_progress(
    25,
    100,
    "Loading invoice",
)
```

### Step 5 — resource access

```python
policy = await ctx.read_resource(
    "resource://finance/approval-policy"
)
```

### Step 6 — prompt access

```python
prompt = await ctx.get_prompt(
    "invoice_analysis",
    {"invoice_id": invoice_id},
)
```

### Step 7 — LLM

Your own server does:

```text
FastMCP
   ↓
LangChain
   ↓
Gemini
```

### Step 8 — progress again

```python
await ctx.report_progress(
    80,
    100,
    "Analyzing invoice",
)
```

### Step 9 — final result

```text
invoice approved
```

This is where `Context` becomes much more than a definition.

---

# 71. A capstone example

Here is a simplified example tying several concepts together:

```python
import logging

from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context

logger = logging.getLogger(__name__)

mcp = FastMCP("Enterprise Finance")


@mcp.resource("resource://finance/policy")
async def finance_policy() -> str:
    return """
    Invoices over ₹100,000 require manager approval.
    Invoices over ₹1,000,000 require director approval.
    """


@mcp.prompt
def invoice_analysis(invoice_id: str) -> str:
    return f"""
    Analyze invoice {invoice_id}.

    Determine:
    - amount
    - vendor
    - approval level
    - anomalies
    """


@mcp.tool
async def analyze_invoice(
    invoice_id: str,
    ctx: Context = CurrentContext(),
) -> dict:

    # -----------------------------------------
    # 1. Normal server-side logging
    # -----------------------------------------

    logger.info(
        "Starting invoice analysis",
        extra={
            "request_id": ctx.request_id,
            "invoice_id": invoice_id,
        },
    )

    # -----------------------------------------
    # 2. Request state
    # -----------------------------------------

    tenant_id = await ctx.get_state("tenant_id")

    if tenant_id is None:
        tenant_id = "default"

    # -----------------------------------------
    # 3. Progress
    # -----------------------------------------

    await ctx.report_progress(
        progress=20,
        total=100,
        message="Loading invoice",
    )

    # -----------------------------------------
    # 4. Resource access
    # -----------------------------------------

    policy_result = await ctx.read_resource(
        "resource://finance/policy"
    )

    policy = policy_result.contents[0].content

    # -----------------------------------------
    # 5. Prompt access
    # -----------------------------------------

    prompt_result = await ctx.get_prompt(
        "invoice_analysis",
        {"invoice_id": invoice_id},
    )

    # -----------------------------------------
    # 6. More progress
    # -----------------------------------------

    await ctx.report_progress(
        progress=60,
        total=100,
        message="Analyzing invoice",
    )

    # -----------------------------------------
    # 7. Application logic
    # -----------------------------------------

    # Here you could call:
    #
    # LangChain
    #     ↓
    # Gemini
    #
    # or your database/API layer.

    analysis = {
        "invoice_id": invoice_id,
        "tenant_id": tenant_id,
        "policy": policy,
        "prompt_messages": prompt_result.messages,
    }

    # -----------------------------------------
    # 8. Final progress
    # -----------------------------------------

    await ctx.report_progress(
        progress=100,
        total=100,
        message="Analysis complete",
    )

    logger.info(
        "Invoice analysis completed",
        extra={
            "request_id": ctx.request_id,
            "invoice_id": invoice_id,
        },
    )

    return analysis
```

This is not yet an enterprise production architecture, but it demonstrates the relationship between the concepts.

---

# 72. What should actually belong in `Context`?

This is the architectural rule I'd like you to internalize:

### Put in tool arguments

Things the caller is explicitly asking the tool to operate on:

```python
invoice_id
customer_id
query
file_uri
limit
```

### Put in Context

Runtime capabilities:

```text
request ID
progress
resource access
prompt access
request state
request metadata
transport
server runtime
visibility
```

### Put in authentication/security dependencies

Identity:

```text
authenticated user
tenant
roles
permissions
OAuth claims
```

### Put in database/application session

Long-lived business state:

```text
shopping cart
workflow
conversation record
selected project
draft
approval process
```

### Put in application/domain services

Actual business logic:

```text
invoice approval
customer lookup
ticket creation
report generation
```

That separation will keep your MCP server maintainable.

---

# 73. The most common beginner mistakes

## Mistake 1 — putting runtime information in tool arguments

Bad:

```python
async def search(
    query: str,
    user_id: str,
    request_id: str,
):
```

when these should come from runtime/auth context.

---

## Mistake 2 — treating `_meta` as trusted identity

Bad:

```python
user_id = ctx.request_context.meta.user_id
```

and then:

```python
if user_id == "admin":
    allow_delete()
```

Client metadata is not automatically a trusted identity boundary.

---

## Mistake 3 — using request state as persistent storage

Bad:

```python
await ctx.set_state("conversation", conversation)
```

and expecting the next call to see it.

Use application/session state or your database instead.

---

## Mistake 4 — using visibility as authorization

Bad:

```text
admin tool is hidden
therefore secure
```

No.

Visibility controls the exposed component surface.

Authorization protects the operation.

---

## Mistake 5 — using `ctx.info()` as your production logging architecture

You should understand it because it's part of the ecosystem, but MCP Logging itself is deprecated in the 2026-07-28 specification. Use normal Python logging and OpenTelemetry for operational observability. ([GitHub][2])

---

## Mistake 6 — believing `session_id` means old MCP HTTP session

Modern MCP removed protocol-level sessions from the current Streamable HTTP specification.

FastMCP's newer:

```text
UserSession
SessionId
```

are application-level state mechanisms. ([GitHub][2])

---

## Mistake 7 — building new systems around SSE

Use:

```text
Streamable HTTP
```

for new HTTP-based MCP deployments.

SSE remains for compatibility with older clients. ([GitHub][11])

---

# 74. The Context cheat sheet

When you see:

```python
ctx: Context = CurrentContext()
```

think:

```text
CURRENT MCP REQUEST
│
├── Identification
│   ├── request_id
│   ├── client_id
│   └── session/application state concepts
│
├── Request information
│   ├── metadata
│   ├── transport
│   └── HTTP context when applicable
│
├── Execution communication
│   └── report_progress()
│
├── Server data
│   ├── list_resources()
│   ├── read_resource()
│   ├── list_prompts()
│   └── get_prompt()
│
├── Runtime state
│   ├── set_state()
│   ├── get_state()
│   └── delete_state()
│
├── Visibility
│   ├── enable_components()
│   ├── disable_components()
│   └── reset_visibility()
│
└── Server
    └── fastmcp
```

That's the conceptual map.

---

# 75. What I would learn next, in this exact order

Since your goal is **deep understanding**, I would not try to memorize all of Context simultaneously.

Use this progression:

```text
STEP 1
Context injection
    ↓
CurrentContext()
    ↓
request_id
```

```text
STEP 2
Progress
    ↓
report_progress()
    ↓
long-running tools
```

```text
STEP 3
Resources
    ↓
list_resources()
read_resource()
```

```text
STEP 4
Prompts
    ↓
list_prompts()
get_prompt()
```

```text
STEP 5
Request state
    ↓
set_state()
get_state()
delete_state()
```

```text
STEP 6
Request metadata
    ↓
request_context.meta
headers
transport
client information
```

```text
STEP 7
Middleware
    ↓
middleware → request state → tool
```

```text
STEP 8
Application state
    ↓
UserSession
SessionId
```

```text
STEP 9
Visibility
    ↓
enable_components()
disable_components()
tags
namespaces
```

```text
STEP 10
Architecture
    ↓
FastAPI
    +
FastMCP
    +
Auth
    +
Postgres/Redis
    +
LangChain/Gemini
    +
OpenTelemetry
```

That sequence will give you a much stronger understanding than memorizing the `Context` API.

---

# 76. One final architecture to keep in your head

For the kind of enterprise AI/MCP systems you're learning to build, this is the architecture I'd want you to eventually think in:

```text
                         CLIENT / AGENT
                              │
                              │ MCP request
                              ▼
                     ┌──────────────────┐
                     │   FastMCP / MCP  │
                     └────────┬─────────┘
                              │
                      Authentication
                              │
                      Authorization
                              │
                         Middleware
                              │
                ┌─────────────┼─────────────┐
                │             │             │
          Request State   Metadata      Observability
                │             │             │
                └─────────────┼─────────────┘
                              │
                         Context
                              │
       ┌──────────────┬───────┼───────┬──────────────┐
       │              │       │       │              │
   Progress       Resources Prompts  Visibility    Runtime
                                                   server
       │              │       │       │              │
       └──────────────┴───────┼───────┴──────────────┘
                              │
                           Tool
                              │
                 ┌────────────┴────────────┐
                 │                         │
           Application layer          LangChain
                 │                         │
          PostgreSQL / Redis            Gemini
                 │
                 ▼
             Enterprise
             systems/APIs
```

And the most important boundary is:

```text
MODEL-CONTROLLED
────────────────────────
tool arguments
        │
        ▼
your tool
        ▲
        │
RUNTIME-CONTROLLED
────────────────────────
Context
authentication
metadata
state
progress
resources
server
```

Once this clicks, `Context` stops being "a mysterious object FastMCP gives me" and becomes something much more intuitive:

> **`Context` is the runtime capability object for the current MCP execution.**

That is the concept I would want you to retain.

### Sources

The current FastMCP 4.0.5 release and current Context APIs are documented by PrefectHQ's FastMCP repository/docs. ([GitHub][1])

The current MCP protocol changes, including stateless MCP, removal of protocol-level HTTP sessions, and deprecation of Logging/Roots/Sampling, are defined in the 2026-07-28 MCP specification. ([GitHub][2])

The official Python SDK documentation also confirms current request-context and progress behavior. ([GitHub][12])

[1]: https://github.com/PrefectHQ/fastmcp/blob/main/docs/updates.mdx?utm_source=chatgpt.com "fastmcp/docs/updates.mdx at main · PrefectHQ/fastmcp · GitHub"
[2]: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/changelog.mdx?utm_source=chatgpt.com "modelcontextprotocol/docs/specification/2026-07-28/changelog.mdx at main · modelcontextprotocol/modelcontextprotocol · GitHub"
[3]: https://github.com/PrefectHQ/fastmcp/blob/main/docs/servers/context.mdx "fastmcp/docs/servers/context.mdx at main · PrefectHQ/fastmcp · GitHub"
[4]: https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/handlers/progress.md?utm_source=chatgpt.com "python-sdk/docs/handlers/progress.md at main · modelcontextprotocol/python-sdk · GitHub"
[5]: https://github.com/PrefectHQ/fastmcp/blob/main/docs/servers/context.mdx?utm_source=chatgpt.com "fastmcp/docs/servers/context.mdx at main · PrefectHQ/fastmcp · GitHub"
[6]: https://jiezhi.github.io/dochub/fastmcp/python-sdk/fastmcp-server-sessions/?utm_source=chatgpt.com "sessions - FastMCP Docs (mirror)"
[7]: https://jiezhi.github.io/dochub/fastmcp/servers/sessions/?utm_source=chatgpt.com "Session State - FastMCP Docs (mirror)"
[8]: https://github.com/PrefectHQ/fastmcp/blob/main/docs/servers/middleware.mdx?utm_source=chatgpt.com "fastmcp/docs/servers/middleware.mdx at main · PrefectHQ/fastmcp · GitHub"
[9]: https://github.com/PrefectHQ/fastmcp/blob/main/docs/servers/server.mdx?utm_source=chatgpt.com "fastmcp/docs/servers/server.mdx at main · PrefectHQ/fastmcp · GitHub"
[10]: https://github.com/PrefectHQ/fastmcp/blob/main/docs/deployment/http.mdx?utm_source=chatgpt.com "fastmcp/docs/deployment/http.mdx at main · PrefectHQ/fastmcp · GitHub"
[11]: https://github.com/PrefectHQ/fastmcp/blob/main/docs/deployment/running-server.mdx?utm_source=chatgpt.com "fastmcp/docs/deployment/running-server.mdx at main · PrefectHQ/fastmcp · GitHub"
[12]: https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/handlers/context.md?utm_source=chatgpt.com "python-sdk/docs/handlers/context.md at main · modelcontextprotocol/python-sdk · GitHub"
