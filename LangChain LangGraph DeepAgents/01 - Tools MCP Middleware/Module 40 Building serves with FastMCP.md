# PHASE 5 — Tools & MCP

## Module 40 — MCP Part 1: Building MCP Servers with FastMCP

You have already studied ordinary LangChain tools and manually built the agent loop. That is exactly the right foundation for MCP.

The key idea of this module is:

> **LangChain tools are a framework-level concept. MCP is a protocol-level interoperability standard.**

Once you understand that distinction, MCP becomes much easier.

I’ll teach this from the ground up and then move into the current 2026 implementation model, including the important changes introduced by the **MCP 2026-07-28 specification** and **FastMCP 4**. As of September 2026, FastMCP 4 is the current stable standalone FastMCP release, while the official MCP Python SDK is on v2. ([GoFastMCP][1])

---

# 1. First: Why does MCP exist?

You already know how to create a LangChain tool:

```python
from langchain.tools import tool


@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    ...
```

Your LangChain agent can use this.

But there is a limitation.

That tool is fundamentally a **Python object inside your application**.

For example:

```text
Your LangChain application
        |
        +-- get_weather()
        +-- search_docs()
        +-- read_database()
        +-- create_ticket()
```

Suppose tomorrow you want:

```text
Cursor
Claude Code
VS Code
Goose
another Python application
another company's AI agent
your own LangGraph application
```

to use the same capabilities.

Without a common protocol, every consumer needs a separate integration.

You could end up with:

```text
Your Python app -> Python function
Cursor          -> custom integration
VS Code         -> custom integration
Claude          -> custom integration
Node app        -> custom integration
Java app        -> custom integration
```

That is the problem MCP addresses.

---

# 2. MCP in one sentence

The **Model Context Protocol (MCP)** is an open protocol that standardizes how an AI application discovers and uses external **tools, resources, and prompts**. LangChain can consume MCP servers and adapt their tools into normal LangChain tools. ([Docs by LangChain][2])

Think of MCP as:

```text
        "USB for AI tools/context"
```

That analogy is not technically exact, but it is useful.

USB standardizes:

```text
device <-> computer
```

MCP standardizes:

```text
AI application <-> capabilities/data
```

---

# 3. Very important: MCP is NOT an LLM

This is one of the first concepts you should permanently remember.

MCP does **not** mean:

```text
MCP = AI model
```

It means:

```text
MCP = communication protocol
```

For example:

```text
                    ┌──────────────────────┐
                    │       LLM            │
                    │ Gemini / Claude / ... │
                    └──────────┬───────────┘
                               │
                         agent / host
                               │
                         MCP client
                               │
                         MCP protocol
                               │
                    ┌──────────▼───────────┐
                    │     MCP server       │
                    │                      │
                    │ tools                │
                    │ resources            │
                    │ prompts              │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │ external systems     │
                    │ DB / API / files     │
                    │ Git / Jira / CRM     │
                    └──────────────────────┘
```

The LLM could be:

```text
Gemini
Claude
OpenAI
local model
another model
```

The MCP server does not care.

That protocol-level separation is a major reason MCP is useful for your planned vendor-independent enterprise AI harness.

---

# 4. MCP architecture

There are three important words:

```text
Host
Client
Server
```

They are easy to confuse.

## 4.1 Host

The **host** is your main AI application.

Examples:

```text
Cursor
Claude Code
VS Code
your LangChain application
your LangGraph application
your enterprise AI application
```

The host is responsible for things such as:

```text
LLM orchestration
user interaction
agent loop
security policies
permission decisions
MCP connections
```

---

# 5. MCP Client

An MCP **client** is the connection managed by the host to one MCP server.

Conceptually:

```text
Host
 |
 +-- MCP Client -> Server A
 |
 +-- MCP Client -> Server B
 |
 +-- MCP Client -> Server C
```

A host can therefore use many MCP servers.

For example, your enterprise AI harness might eventually have:

```text
Enterprise AI Harness
       |
       +-- MCP client
       |      |
       |      +-- Microsoft 365 server
       |
       +-- MCP client
       |      |
       |      +-- Salesforce server
       |
       +-- MCP client
       |      |
       |      +-- ServiceNow server
       |
       +-- MCP client
              |
              +-- Internal company server
```

This is where MCP becomes extremely interesting for your enterprise architecture.

---

# 6. MCP Server

An MCP server exposes capabilities.

For example:

```text
Company HR MCP Server

Tools:
    get_employee
    create_leave_request
    cancel_leave_request

Resources:
    employee_policy
    holiday_calendar

Prompts:
    summarize_employee_policy
```

The MCP server doesn't necessarily contain an LLM.

It can simply be:

```text
Python application
      |
      +-- REST APIs
      +-- PostgreSQL
      +-- Redis
      +-- filesystem
      +-- internal microservices
```

---

# 7. The three main MCP primitives

MCP gives servers three important primitives:

```text
Tools
Resources
Prompts
```

The easiest way to remember them is:

| Primitive | Mental model                              |
| --------- | ----------------------------------------- |
| Tool      | "Do something"                            |
| Resource  | "Give me some data"                       |
| Prompt    | "Give me a reusable interaction template" |

There is also an important control distinction:

```text
Tools     -> model-controlled
Resources -> application-controlled
Prompts   -> user-controlled
```

That distinction is part of the MCP design model. ([Model Context Protocol][3])

Let's understand each deeply.

---

# 8. MCP Tools

You already understand tools from your previous modules.

An MCP tool is essentially:

> A function that the MCP client can ask the MCP server to execute.

Example:

```python
@mcp.tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b
```

The interesting part is that this isn't merely a Python function anymore.

FastMCP turns it into a protocol-exposed capability.

FastMCP automatically uses:

* the function name
* type annotations
* docstring
* return type

to construct the MCP tool definition and its schema. ([FastMCP][4])

---

# 9. What actually happens when an MCP tool is used?

Imagine:

```python
@mcp.tool
def get_customer(customer_id: str) -> dict:
    """Get customer information by customer ID."""
    ...
```

Conceptually the client first discovers tools:

```text
Client
  |
  | tools/list
  |
  ▼
Server
  |
  | available tools
  ▼
Client
```

It may learn:

```json
{
  "name": "get_customer",
  "description": "Get customer information by customer ID.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "customer_id": {
        "type": "string"
      }
    },
    "required": ["customer_id"]
  }
}
```

Then the model decides:

> I need `get_customer`.

The host asks the MCP client to invoke it:

```text
tools/call
```

with something conceptually equivalent to:

```json
{
  "name": "get_customer",
  "arguments": {
    "customer_id": "C123"
  }
}
```

The server:

```text
receives request
      ↓
validates arguments
      ↓
executes Python function
      ↓
returns MCP result
```

FastMCP handles the protocol mechanics around this for you. ([FastMCP][4])

---

# 10. Why schemas matter so much

Notice this:

```python
def get_customer(customer_id: str) -> dict:
```

The type annotation isn't merely for Python readability.

FastMCP uses it to create the tool schema.

For example:

```python
def calculate(
    quantity: int,
    price: float,
) -> float:
    ...
```

communicates:

```text
quantity -> integer
price    -> number
result   -> number
```

This becomes machine-readable information for the MCP client and ultimately for the AI application.

This is one reason your previous learning of:

```text
Python
Pydantic
type hints
structured outputs
tool schemas
```

is directly relevant.

---

# 11. Tool descriptions are extremely important

Consider:

```python
@mcp.tool
def search(q: str) -> list[dict]:
    """Search data."""
```

versus:

```python
@mcp.tool
def search_employee_directory(
    query: str,
    department: str | None = None,
    max_results: int = 10,
) -> list[dict]:
    """Search the company employee directory.

    Use this when the user wants to find an employee by
    name, email address, department, or employee ID.

    Args:
        query: Name, email, employee ID, or other identifying text.
        department: Optional department to restrict the search.
        max_results: Maximum number of employees to return.
    """
```

The second is much more useful to an agent.

Remember:

> **A tool description is part of the interface between your software and the model.**

It is therefore closer to an API contract than an ordinary comment.

---

# 12. Tool annotations

Modern MCP tools can expose hints such as:

```text
readOnlyHint
destructiveHint
idempotentHint
openWorldHint
```

FastMCP exposes these through tool annotations. ([FastMCP][4])

For example:

```python
@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
    }
)
def get_employee(employee_id: str) -> dict:
    ...
```

Conceptually:

```text
get_employee
    ↓
does not modify data
```

Whereas:

```python
delete_employee(...)
```

might have:

```text
destructiveHint = true
```

### Important security warning

These are **hints**.

They are not your authorization system.

Do NOT think:

```text
destructiveHint=False
        =
secure
```

It doesn't.

You still need:

```text
authentication
authorization
input validation
policy enforcement
rate limiting
audit logging
```

This connects directly to the tool-security module you just completed.

---

# 13. MCP Resources

Tools answer:

> "Do something."

Resources answer:

> "Give me some information."

A resource is generally read-oriented.

Example:

```python
@mcp.resource("company://policies/leave")
def leave_policy() -> str:
    return """
    Employees receive 20 days of annual leave.
    """
```

A client can request:

```text
resources/read
```

for:

```text
company://policies/leave
```

FastMCP describes resources as read-only data or dynamically generated content exposed through URIs. ([FastMCP][5])

---

# 14. Why resources aren't simply tools

You might think:

```python
@mcp.tool
def get_leave_policy():
    ...
```

Why have:

```python
@mcp.resource
def leave_policy():
    ...
```

at all?

Because they communicate different semantics.

### Tool

```text
"Perform an operation."
```

Example:

```text
create_leave_request()
```

### Resource

```text
"Here is a piece of data."
```

Example:

```text
company://policies/leave
```

That semantic distinction allows clients and hosts to treat them differently.

---

# 15. Resource URI

A resource has an identifier such as:

```text
company://policies/leave
```

or:

```text
company://employees/C123
```

or:

```text
database://sales/customer/C123
```

The URI doesn't necessarily mean the server is exposing an actual HTTP URL.

It is primarily an identifier within MCP.

Think:

```text
URI = address of a piece of MCP-accessible information
```

---

# 16. Resource templates

This gets more powerful.

Suppose you want:

```text
employee://123
employee://456
employee://789
```

Instead of manually registering thousands of resources, you can define a resource template.

Conceptually:

```python
@mcp.resource("employee://{employee_id}")
def employee(employee_id: str) -> dict:
    ...
```

Then:

```text
employee://123
```

causes:

```text
employee("123")
```

to be evaluated.

FastMCP supports resource templates specifically for dynamically parameterized resource access. ([FastMCP][5])

---

# 17. MCP Prompts

Prompts are reusable prompt templates exposed by a server.

Example:

```python
@mcp.prompt
def summarize_document(topic: str) -> str:
    """Create a prompt for summarizing a document."""
    return f"Summarize the document about {topic}."
```

The important difference is:

```text
Tool    -> execute operation
Resource -> provide data
Prompt  -> provide reusable instructions/template
```

FastMCP's prompt decorator derives prompt metadata from the function name, docstring and arguments. ([FastMCP][6])

---

# 18. Why would a server provide prompts?

Imagine a company has an internal compliance system.

It could expose:

```text
Prompt:
    review_contract
```

with a standardized corporate instruction such as:

```text
Review the supplied contract for:

1. liability
2. data protection
3. termination
4. indemnification
5. intellectual property

Do not provide legal advice.
Highlight clauses requiring human review.
```

Now every compatible client can use that standardized prompt.

That can be useful for centralized prompt governance.

---

# 19. Tools vs resources vs prompts

Memorize this table:

| Primitive | Purpose                       | Typical example               |
| --------- | ----------------------------- | ----------------------------- |
| Tool      | perform action / computation  | `create_ticket()`             |
| Resource  | expose data                   | `company://policies/security` |
| Prompt    | reusable instruction template | `review_contract()`           |

Another useful mental model:-+

```text
Tool:
    "DO"

Resource:
    "READ"

Prompt:
    "GUIDE"
```

---

# 20. MCP transport

Now we get to a very important concept.

MCP defines **what** is communicated.

A transport defines **how it physically travels**.

Think:

```text
MCP protocol
    +
transport
```

The two major transports you need to know are:

```text
STDIO
Streamable HTTP
```

There is also historical HTTP+SSE, which you should understand because you will encounter it in old tutorials.

---

# 21. STDIO transport

STDIO means:-

```text
standard input
standard output
```

A host launches the MCP server as a child process.

For example:

```text
LangChain application
       |
       | launches
       ▼
python server.py
       |
       +---- stdin
       +---- stdout
```

Communication occurs through the process pipes.

The MCP client writes requests into the server's stdin.

The server writes protocol responses to stdout.

This is particularly appropriate for local integrations where the client owns the server process lifecycle. FastMCP describes this model directly. ([FastMCP][7])

---

# 22. Why STDIO is excellent for local MCP servers

Imagine Cursor wants to use your server.

You can have:

```text
Cursor
  |
  | spawn
  ▼
my_server.py
```

No:

```text
Docker
HTTP
TLS
DNS
reverse proxy
network port
OAuth
load balancer
```

is required.

That makes STDIO incredibly convenient for:

```text
local developer tools
IDE integrations
desktop AI applications
personal automation
local filesystem tools
local Git tools
```

---

# 23. Critical STDIO rule

With STDIO:

> **stdout belongs to the MCP protocol.**

Therefore do not casually do:

```python
print("hello")
```

to stdout while the server is operating over STDIO.

You can corrupt the protocol stream.

Use proper logging instead.

For example:

```python
import logging

logger = logging.getLogger(__name__)

logger.info("Database connected")
```

or FastMCP's logging/context facilities.

FastMCP provides logging utilities and client-facing context logging. ([FastMCP][8])

A useful mental model is:

```text
stdout -> protocol
stderr/logging -> diagnostics
```

---

# 24. Streamable HTTP

Now imagine:

```text
Company AI Harness
         |
         | HTTPS
         ▼
https://mcp.company.com/mcp
         |
         ▼
MCP server
```

This is where Streamable HTTP becomes useful.

Current MCP and FastMCP deployments recommend Streamable HTTP for remote services. FastMCP's current client documentation explicitly identifies HTTP/Streamable HTTP as the recommended production transport. ([FastMCP][7])

---

# 25. Why Streamable HTTP matters

Suppose your company has:

```text
2000 employees
```

and you want:

```text
Microsoft 365 MCP server
```

to be used from many AI clients.

You don't want every client doing:

```text
spawn a Python process
```

Instead you can have:

```text
                          ┌─────────────┐
Employee 1 ──────────────►│             │
Employee 2 ──────────────►│             │
Employee 3 ──────────────►│ MCP server  │
Employee 4 ──────────────►│             │
...                       │             │
Employee 2000 ───────────►│             │
                          └─────────────┘
```

running as:

```text
Docker container
Kubernetes deployment
VM
internal service
cloud service
```

---

# 26. Streamable HTTP vs old HTTP+SSE

This is an important modern/deprecated distinction.

Older MCP implementations frequently used:

```text
HTTP + SSE
```

SSE means:

```text
Server-Sent Events
```

It was an important part of earlier MCP transport designs.

Today:

```text
NEW PROJECT
    ↓
Streamable HTTP
```

The older SSE transport remains for compatibility, but FastMCP recommends Streamable HTTP for new deployments. ([FastMCP][7])

So when you see a tutorial saying:

```python
transport="sse"
```

do not immediately copy it.

Ask:

> Is this a legacy example?

For a new server, start with Streamable HTTP.

---

# 27. Major 2026 MCP change: protocol sessions

This is something many older tutorials will confuse you about.

Older MCP versions used:

```text
initialize
initialized
Mcp-Session-Id
```

and stateful connections.

The current MCP specification revision, **2026-07-28**, removed protocol-level sessions and the `Mcp-Session-Id` header from the modern protocol path. Requests are now independent and can be routed to different server instances. ([Model Context Protocol Blog][9])

This has a major infrastructure implication.

Older architecture:

```text
             ┌──────────┐
client ─────►│ LB       │
             └────┬─────┘
                  │
             sticky session
                  │
              Server A
```

Modern protocol:

```text
             ┌──────────┐
client ─────►│ LB       │
             └────┬─────┘
                  │
             ┌────┴─────────────┐
             │                  │
          Server A           Server B
```

A modern request can go to either.

This makes MCP much easier to deploy behind normal HTTP infrastructure.

---

# 28. But does that mean MCP applications cannot have state?

No.

This distinction is extremely important:

```text
protocol state
        ≠
application state
```

The new MCP protocol does not use hidden transport-level session state in the old way.

But your application can still have state.

For example:

```text
PostgreSQL
Redis
user session
database record
explicit workflow ID
job ID
task ID
```

FastMCP's current guidance explicitly distinguishes protocol-level statelessness from application-level state. ([GoFastMCP][10])

---

# 29. Now let's build your first MCP server

For your stack, I recommend:

```text
Python
uv
FastMCP
Pydantic
```

You already know `uv`, so this fits your workflow nicely.

Current FastMCP documentation recommends installing it with:

```bash
uv add fastmcp
```

and current FastMCP 4 documentation identifies version 4 as the stable line. ([FastMCP][11])

---

# 30. Create a project

```bash
mkdir mcp-server-demo
cd mcp-server-demo

uv init
uv add fastmcp
```

Your project might look like:

```text
mcp-server-demo/
├── pyproject.toml
├── uv.lock
└── server.py
```

---

# 31. First FastMCP server

Create:

```python
from fastmcp import FastMCP


mcp = FastMCP("CompanyServer")


@mcp.tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b
```

That's it.

You have created an MCP server containing one tool.

---

# 32. Understand this line

```python
mcp = FastMCP("CompanyServer")
```

You can think of `mcp` as:

```text
MCP server registry + protocol implementation
```

It knows about:

```text
tools
resources
prompts
transport
protocol behavior
validation
serialization
```

You then register capabilities against it.

---

# 33. Understand `@mcp.tool`

This:

```python
@mcp.tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b
```

is conceptually doing something like:

```text
Python function
      |
      | inspect name
      | inspect type hints
      | inspect docstring
      | inspect return type
      ▼
MCP tool definition
      |
      ▼
available to MCP client
```

FastMCP automatically generates the input schema from the function signature and type annotations. ([FastMCP][4])

---

# 34. Run it locally with STDIO

You can explicitly run the server using STDIO.

For a normal Python entry point, you can use:

```python
from fastmcp import FastMCP


mcp = FastMCP("CompanyServer")


@mcp.tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


if __name__ == "__main__":
    mcp.run(transport="stdio")
```

Then:

```bash
uv run python server.py
```

The process becomes an MCP server communicating over stdin/stdout.

---

# 35. But how do I test it?

You don't have to immediately connect an LLM.

This is an important learning principle:

> **MCP can be learned independently from agent/LLM behavior.**

You can test the protocol and server independently.

FastMCP provides its own client tooling, and also an in-memory transport which is particularly useful for testing. ([FastMCP][7])

For example:

```python
import asyncio

from fastmcp import Client
from pathlib import Path


async def main():
    client = Client(Path("server.py"))

    async with client:
        tools = await client.list_tools()

        for tool in tools:
            print(tool.name)

        result = await client.call_tool(
            "add",
            {
                "a": 10,
                "b": 20,
            },
        )

        print(result)


if __name__ == "__main__":
    asyncio.run(main())
```

Notice something important here.

Current FastMCP 4 deprecates:

```python
Client("server.py")
```

for inferring STDIO from strings.

Use:

```python
Client(Path("server.py"))
```

instead. Strings are now intended for URLs; the old string-based local-file inference will be removed in FastMCP 5. ([FastMCP][7])

This is a perfect example of why following old MCP tutorials blindly can cause trouble.

---

# 36. Why `Path` instead of string?

This:

```python
Client(Path("server.py"))
```

clearly means:

> "I intentionally want to execute this local program."

Whereas:

```python
Client("https://company.com/mcp")
```

clearly means:

> "I want to connect to a remote HTTP MCP server."

This reduces ambiguity and improves security around dynamically supplied server locations. FastMCP specifically warns that transport inference treats supplied server configuration as trusted. ([FastMCP][7])

---

# 37. Let's make the server more realistic

Let's create a tiny company directory server.

```python
from fastmcp import FastMCP


mcp = FastMCP("CompanyDirectory")


EMPLOYEES = {
    "E001": {
        "name": "Aarav",
        "department": "Engineering",
        "email": "aarav@example.com",
    },
    "E002": {
        "name": "Diya",
        "department": "Finance",
        "email": "diya@example.com",
    },
}
```

Now add a tool:

```python
@mcp.tool
def get_employee(employee_id: str) -> dict:
    """Get employee information by employee ID."""
    employee = EMPLOYEES.get(employee_id)

    if employee is None:
        raise ValueError(f"Employee {employee_id} does not exist.")

    return employee
```

---

# 38. Why use `str` instead of `dict` everywhere?

Because the signature is effectively your interface contract.

This:

```python
employee_id: str
```

says:

```text
The caller supplies one string.
```

The client can construct the proper schema automatically.

This makes tools much easier to consume than arbitrary Python functions.

---

# 39. Pydantic models

This is where your previous Pydantic knowledge becomes useful.

Imagine:

```python
from pydantic import BaseModel


class Employee(BaseModel):
    employee_id: str
    name: str
    department: str
    email: str
```

Then:

```python
@mcp.tool
def get_employee(employee_id: str) -> Employee:
    """Get an employee by employee ID."""
    ...
```

FastMCP supports Pydantic types and generates structured schemas from them. ([FastMCP][4])

That makes MCP very natural for you because you've already learned:

```text
Pydantic
structured outputs
schema validation
```

---

# 40. Input validation

FastMCP uses Pydantic-style validation by default and can operate in strict input-validation mode. ([FastMCP][4])

For example:

```python
@mcp.tool
def add(a: int, b: int) -> int:
    return a + b
```

With default flexible validation, a client may provide:

```json
{
  "a": "10",
  "b": "20"
}
```

and compatible values can be coerced.

Strict validation can instead reject those mismatches.

For security-sensitive enterprise tools, this becomes something to think about carefully.

---

# 41. Your tool-security module still applies

Do not assume:

```text
MCP = security
```

MCP standardizes communication.

It does not magically make tools safe.

Your previous principles remain:

```text
authentication
authorization
allowlist
input validation
rate limiting
audit logging
secret isolation
prompt injection resistance
dangerous-action controls
```

For example:

```python
@mcp.tool
def delete_customer(customer_id: str):
    ...
```

is still dangerous.

MCP does not decide whether the current user is allowed to delete that customer.

Your authorization layer must do that.

---

# 42. MCP Context

Now we get to one of the more advanced FastMCP concepts.

Sometimes a tool needs more than its explicit arguments.

For example:

```text
tool arguments:
    employee_id

but internally I also need:
    request ID
    logging
    user identity
    progress reporting
    resource access
```

That's where:

```python
Context
```

comes in.

FastMCP's `Context` gives server code access to MCP features such as logging, progress, resource access, request information and other request-scoped behavior. ([FastMCP][12])

---

# 43. Current FastMCP context injection style

The modern preferred style is:

```python
from fastmcp import FastMCP
from fastmcp.server.context import Context
from fastmcp.dependencies import CurrentContext


mcp = FastMCP("CompanyServer")


@mcp.tool
async def process_employee(
    employee_id: str,
    ctx: Context = CurrentContext(),
) -> str:
    """Process an employee record."""

    await ctx.info(
        f"Processing employee {employee_id}"
    )

    return "Processed"
```

Current FastMCP documentation recommends `CurrentContext()` dependency injection as the preferred way to access the context. ([FastMCP][12])

---

# 44. Notice something very important

We have:

```python
employee_id: str
```

and:

```python
ctx: Context = CurrentContext()
```

But the client does **not** need to supply `ctx`.

Why?

Because `ctx` is an internal dependency.

So conceptually:

```text
MCP client sees:

employee_id
```

while FastMCP internally provides:

```text
ctx
```

This is similar to dependency injection concepts you have seen in FastAPI.

That's an important connection for you:

```text
FastAPI dependency injection
        +
FastMCP dependency injection
```

are conceptually similar:

```text
some dependencies are application-provided,
not user-provided.
```

---

# 45. What can `Context` do?

Current FastMCP context includes things such as:

```text
logging
progress reporting
resource access
prompt access
request state
request metadata
server access
session visibility
```

and more. ([FastMCP][12])

For example:

```python
await ctx.info("Starting operation")
```

or:

```python
await ctx.report_progress(
    progress=50,
    total=100,
)
```

---

# 46. Progress reporting

Imagine:

```python
@mcp.tool
async def process_documents(
    documents: list[str],
    ctx: Context = CurrentContext(),
) -> str:
```

You could report:

```text
0%
20%
40%
60%
80%
100%
```

using:

```python
await ctx.report_progress(...)
```

so a capable client can show progress to the user. ([FastMCP][13])

This is especially useful for enterprise operations such as:

```text
process 10,000 documents
generate report
bulk synchronization
data migration
large API operation
```

---

# 47. FastMCP Lifespan

Now let's talk about:

```text
lifespan
```

This is analogous to application startup/shutdown lifecycle management.

Suppose your server needs to initialize:

```text
database connection pool
Redis client
HTTP client
configuration
ML model
connection to external service
```

You do not want every tool invocation to recreate them.

Instead:

```text
server starts
      ↓
initialize resources
      ↓
serve tools
      ↓
server shuts down
      ↓
cleanup resources
```

FastMCP 4 has first-class lifespan support for server-level setup/teardown. ([FastMCP][14])

---

# 48. Basic lifespan

Current FastMCP style:

```python
from fastmcp import FastMCP
from fastmcp.server.lifespan import lifespan


@lifespan
async def app_lifespan(server):
    print("Server starting")

    db = await create_database_pool()

    try:
        yield {
            "db": db,
        }
    finally:
        print("Server shutting down")

        await db.close()


mcp = FastMCP(
    "CompanyServer",
    lifespan=app_lifespan,
)
```

The important structure is:

```python
try:
    yield {...}
finally:
    cleanup()
```

That ensures cleanup occurs even when shutdown/cancellation happens. ([FastMCP][14])

---

# 49. Lifespan context

Your tool can access the data produced by lifespan:

```python
@mcp.tool
async def get_employee(
    employee_id: str,
    ctx: Context = CurrentContext(),
) -> dict:

    db = ctx.lifespan_context["db"]

    ...
```

So you effectively have:

```text
server startup
      |
      +-- create DB pool
      |
      ▼
lifespan context
      |
      +-- tool 1
      +-- tool 2
      +-- tool 3
      |
      ▼
server shutdown
      |
      +-- close DB pool
```

FastMCP documents the lifespan context specifically for sharing initialized server-level resources with tools. ([FastMCP][14])

---

# 50. Lifespan vs request context

Do not confuse:

```text
lifespan
```

with:

```text
request context
```

Think:

### Lifespan

```text
whole server lifetime
```

### Context

```text
current request
```

For example:

```text
Server starts
 |
 |--- DB pool ----------------------|
 |                                  |
 | Tool request A                   |
 |   Context A                      |
 |                                  |
 | Tool request B                   |
 |   Context B                      |
 |                                  |
 | Tool request C                   |
 |   Context C                      |
 |                                  |
Server stops
 |
DB pool closes
```

That mental model is extremely useful.

---

# 51. Why lifespan matters in production

Bad:

```python
@mcp.tool
def get_user(...):
    db = create_database_connection()
    ...
    db.close()
```

for every call.

Imagine:

```text
100 requests/sec
```

You would be constantly opening and closing connections.

Better:

```text
server starts
    ↓
connection pool created
    ↓
tools reuse it
```

This is standard application engineering, and FastMCP gives you lifecycle machinery to implement it cleanly.

---

# 52. Combine everything into one server

Let's build a more complete server.

```python
from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context
from fastmcp.server.lifespan import lifespan


@lifespan
async def app_lifespan(server):
    print("Starting Company Directory server")

    database = {
        "E001": {
            "name": "Aarav",
            "department": "Engineering",
            "email": "aarav@example.com",
        },
        "E002": {
            "name": "Diya",
            "department": "Finance",
            "email": "diya@example.com",
        },
    }

    try:
        yield {
            "database": database,
        }
    finally:
        print("Stopping Company Directory server")


mcp = FastMCP(
    "CompanyDirectory",
    lifespan=app_lifespan,
)


@mcp.tool
async def get_employee(
    employee_id: str,
    ctx: Context = CurrentContext(),
) -> dict:
    """Get employee information by employee ID."""

    await ctx.info(
        f"Looking up employee {employee_id}"
    )

    database = ctx.lifespan_context["database"]

    employee = database.get(employee_id)

    if employee is None:
        raise ValueError(
            f"Employee {employee_id} does not exist."
        )

    return employee


@mcp.resource("company://policy/leave")
def leave_policy() -> str:
    """Company leave policy."""
    return """
    Employees receive 20 days of annual leave per year.
    """


@mcp.prompt
def summarize_employee(employee_id: str) -> str:
    """Create a prompt for summarizing an employee record."""

    return (
        f"Summarize the employee record for {employee_id}. "
        "Focus on department and role."
    )
```

Now one MCP server exposes:

```text
Tool:
    get_employee

Resource:
    company://policy/leave

Prompt:
    summarize_employee
```

This is the core of MCP server development.

---

# 53. Running this server as Streamable HTTP

Add:

```python
if __name__ == "__main__":
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=8000,
    )
```

Then:

```bash
uv run python server.py
```

FastMCP's current HTTP deployment documentation exposes the MCP endpoint at:

```text
http://localhost:8000/mcp
```

by default. ([FastMCP][15])

So your architecture becomes:

```text
Client
   |
   | HTTP
   |
   ▼
http://localhost:8000/mcp
   |
   ▼
FastMCP
   |
   +-- tools
   +-- resources
   +-- prompts
```

---

# 54. Why `/mcp`?

MCP is not simply:

```text
GET /weather
```

like a conventional REST API.

Instead:

```text
POST /mcp
```

acts as the MCP protocol endpoint.

The messages inside the protocol describe:

```text
tools/list
tools/call
resources/list
resources/read
prompts/list
prompts/get
...
```

So:

```text
HTTP
```

is merely the transport.

Inside it is:

```text
MCP protocol
```

which uses structured protocol messages.

---

# 55. Built-in HTTP vs ASGI deployment

FastMCP supports two broad approaches.

### Simple

```python
mcp.run(
    transport="http",
    host="0.0.0.0",
    port=8000,
)
```

This is excellent for:

```text
development
simple internal services
small deployments
```

### ASGI

FastMCP can expose a standard ASGI application:

```python
app = mcp.http_app()
```

and then you can run:

```bash
uvicorn app:app \
    --host 0.0.0.0 \
    --port 8000
```

FastMCP documents this approach specifically for more production-oriented deployments and integration with ASGI infrastructure. ([FastMCP][15])

---

# 56. FastMCP + FastAPI

This is especially relevant to you because you're learning FastAPI.

You can have something conceptually like:

```text
FastAPI application
       |
       +-- /api/*
       |
       +-- /health
       |
       +-- /auth/* 
       |
       +-- /mcp
               |
               ▼
            FastMCP
```

FastMCP can be mounted into an ASGI application.

One important current detail: when mounting FastMCP's Streamable HTTP app inside another ASGI framework, the MCP application's lifespan must be correctly propagated, otherwise its session manager/lifecycle initialization can fail. ([FastMCP][16])

So don't blindly copy old snippets that simply mount an app without handling lifespan.

---

# 57. Running MCP inside Docker

Since Docker is already part of your preferred deployment model, MCP servers fit naturally into containers.

Conceptually:

```text
Docker
    └── MCP container
    ├── Python
    ├── FastMCP
    ├── your code
    └── dependencies
```

For example:

```dockerfile
FROM python:3.14-slim

WORKDIR /app

RUN pip install --no-cache-dir fastmcp

COPY server.py .

EXPOSE 8000

CMD [
    "python",
    "server.py"
]
```

where `server.py` contains:

```python
if __name__ == "__main__":
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=8000,
    )
```

Then:

```bash
docker build -t company-mcp-server .
```

and:

```bash
docker run \
    --rm \
    -p 8000:8000 \
    company-mcp-server
```

Your MCP server is now:

```text
http://localhost:8000/mcp
```

---

# 58. Production container architecture

For your enterprise AI harness, think bigger:

```text
                    Internet / Corporate Network
                              |
                         Reverse Proxy
                         / API Gateway
                              |
                    ┌─────────▼─────────┐
                    │ Authentication    │
                    │ Authorization     │
                    │ Rate limiting     │
                    │ Audit             │
                    └─────────┬─────────┘
                              |
                    ┌─────────▼─────────┐
                    │    MCP Service    │
                    │                   │
                    │ FastMCP           │
                    │ tools             │
                    │ resources         │
                    │ prompts           │
                    └─────────┬─────────┘
                              |
                  ┌───────────┼───────────┐
                  │           │           │
                 DB          APIs       SaaS
```

This is much closer to how you should think about enterprise MCP architecture.

---

# 59. MCP server should not become a giant "god server"

Avoid:

```text
enterprise-mcp-server.py
```

containing:

```text
Microsoft
Salesforce
ServiceNow
Jira
Postgres
Redis
HR
Finance
Legal
Security
CRM
everything
```

Instead think in capabilities.

For example:

```text
mcp-salesforce
mcp-servicenow
mcp-jira
mcp-hr
mcp-company-search
mcp-finance
```

Then the host can compose them.

This also works well with MCP's interoperable architecture.

---

# 60. MCP vs LangChain tools

This is probably the most important architectural question for you.

Suppose you have:

```python
@tool
def search_docs(...):
    ...
```

versus:

```python
@mcp.tool
def search_docs(...):
    ...
```

They may look deceptively similar.

But they solve different problems.

---

# 61. LangChain tool

A LangChain tool is primarily:

```text
application/framework abstraction
```

It is excellent when:

```text
you control the agent
you control the Python application
you want simplicity
the tool is local
```

For example:

```text
LangGraph agent
      |
      +-- search_docs
      +-- get_weather
      +-- query_db
```

Very simple.

---

# 62. MCP tool

An MCP tool is:

```text
protocol-level interoperable capability
```

Now:

```text
Claude
Cursor
VS Code
LangChain
custom Python host
Node host
another AI platform
```

can potentially consume the same MCP server.

That is the key difference.

---

# 63. When should you use plain LangChain tools?

Use a normal LangChain tool when:

```text
the tool is private to one application
```

For example:

```python
@tool
def calculate_discount(...):
    ...
```

Suppose only your internal LangGraph agent uses it.

MCP may provide little benefit.

Your architecture becomes unnecessarily complicated:

```text
agent
  |
MCP client
  |
MCP server
  |
function
```

when you could simply have:

```text
agent
  |
function
```

---

# 64. When should you use MCP?

MCP becomes compelling when:

```text
multiple AI clients need the same capability
```

or:

```text
you want third-party interoperability
```

or:

```text
you want capabilities deployed independently
```

or:

```text
you want a standard interface for external agent ecosystems
```

For example:

```text
Company Salesforce MCP Server
             |
       ┌─────┼──────┐
       │     │      │
     Cursor Claude LangChain
                    |
                 LangGraph
```

One service, many consumers.

---

# 65. The simplest mental decision rule

Ask:

> "Is this capability primarily an internal function of my application, or is it an independently consumable capability?"

### Internal function

Use:

```text
LangChain tool
```

### Independently consumable capability

Consider:

```text
MCP server
```

---

# 66. Another useful analogy

Think of:

```text
LangChain tool
```

like:

```text
a Python library function
```

while:

```text
MCP server
```

is closer to:

```text
a standardized service/API
```

There is more machinery around MCP because that machinery buys interoperability.

---

# 67. MCP does not replace LangChain

This is another common misconception.

You can have:

```text
LangChain
   |
   ▼
MCP client
   |
   ▼
MCP server
```

LangChain still handles:

```text
agent
LLM
messages
graph
memory
state
orchestration
middleware
guardrails
```

MCP handles:

```text
standardized access to external capabilities
```

That's why they complement each other.

Current LangChain documentation explicitly provides an MCP adapter that discovers tools from MCP servers and turns them into LangChain tools usable by `create_agent`. ([Docs by LangChain][2])

---

# 68. LangChain + MCP architecture

The modern conceptual architecture is:

```text
                    ┌───────────────┐
                    │ Gemini        │
                    │ Chat Model    │
                    └───────┬───────┘
                            │
                       LangChain
                            │
                     create_agent
                            │
                     MCPAdapter
                            │
                    FastMCP Client
                            │
                    Streamable HTTP
                            │
                    ┌───────▼────────┐
                    │ MCP Server     │
                    │                │
                    │ tools           │
                    │ resources       │
                    │ prompts         │
                    └────────────────┘
```

This is exactly where your LangChain learning and MCP learning meet.

---

# 69. Current LangChain MCP integration

As of the current LangChain documentation, there is a newer:

```python
from langchain.mcp import MCPAdapter
```

API.

For example:

```python
from langchain.mcp import MCPAdapter


async with MCPAdapter(
    "https://example.com/mcp"
) as adapter:

    tools = await adapter.list_tools()
```

Then those tools can be passed to:

```python
create_agent(...)
```

LangChain's current MCP documentation says this adapter is built around FastMCP and handles transport/protocol connection details. The `langchain.mcp` namespace is currently documented as beta and requires `langchain[mcp]`. ([Docs by LangChain][2])

---

# 70. What about `langchain-mcp-adapters`?

You are likely to find tutorials using:

```python
from langchain_mcp_adapters.client import MultiServerMCPClient
```

That is a very important historical/current migration point.

LangChain's current documentation says MCP integration before LangChain 1.4.0 used the separate `langchain-mcp-adapters` package and directs users to migration documentation. ([Docs by LangChain][2])

So when following tutorials:

```text
older tutorial
    ↓
langchain-mcp-adapters
```

versus current LangChain docs:

```text
current direction
    ↓
langchain.mcp
    MCPAdapter
```

Do not assume an older tutorial represents the current preferred API.

---

# 71. Gemini with LangChain

You specifically prefer Gemini through LangChain when an LLM call is needed.

That works perfectly with this architecture.

You can conceptually have:

```python
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_agent
from langchain.mcp import MCPAdapter
```

Then:

```text
Gemini
   |
LangChain agent
   |
MCPAdapter
   |
MCP server
```

The important thing to understand at this stage is:

> **The MCP server doesn't care that Gemini is being used.**

You could replace Gemini later without changing the MCP server.

That gives you the model independence you care about.

---

# 72. This is important for your planned enterprise AI harness

Suppose your company customer says:

> We currently use Gemini.

You connect:

```text
AI Harness
   |
Gemini
   |
MCP servers
```

Later they say:

> We want Claude.

You can change:

```text
Gemini
```

to:

```text
Claude
```

while keeping:

```text
MCP servers
```

because MCP is the capability interoperability layer.

Likewise:

```text
Microsoft ecosystem
Google ecosystem
Salesforce
ServiceNow
Jira
internal APIs
```

can potentially expose or consume standardized MCP interfaces.

That is where your vendor-independent architecture becomes much more interesting.

---

# 73. A realistic enterprise example

Imagine an employee asks:

> "Find my customer's latest support case and summarize it."

Architecture:

```text
Employee
   |
   ▼
Enterprise AI Harness
   |
   ▼
LLM / Agent
   |
   ├── MCP Client
   │
   └──────► ServiceNow MCP Server
                  |
                  ▼
              ServiceNow API
```

The LLM might decide:

```text
search_cases(...)
```

Then the MCP layer performs:

```text
tools/call
```

The server calls:

```text
ServiceNow REST API
```

returns structured data, and the model summarizes it.

---

# 74. Add Salesforce

Now the agent asks:

> "Compare the customer's Salesforce opportunity with the latest ServiceNow issue."

The architecture becomes:

```text
                     Agent
                       |
                 MCP Adapter
                  /       \
                 /         \
                ▼           ▼
        Salesforce MCP   ServiceNow MCP
              |                |
              ▼                ▼
        Salesforce API     ServiceNow API
```

This is one of the strongest use cases for MCP.

---

# 75. Add your own internal system

You might have:

```text
Internal HR MCP
Internal Finance MCP
Internal Knowledge MCP
Internal Security MCP
```

Your agent sees standardized capabilities rather than your company's internal implementation details.

That separation is extremely valuable.

---

# 76. MCP server design principle

One of the most important things I want you to learn is:

> **An MCP server should expose capabilities, not implementation details.**

Bad:

```text
run_sql
```

and then let the LLM write arbitrary SQL against production.

Better:

```text
search_customer
get_customer_orders
get_invoice
create_support_ticket
```

Why?

Because these create a more constrained capability boundary.

This is directly aligned with the security principles from your previous module.

---

# 77. Tools should be narrow

Bad:

```python
@mcp.tool
def execute_anything(command: str):
    ...
```

Dangerous because:

```text
command
```

is almost unconstrained.

Better:

```python
@mcp.tool
def get_invoice(invoice_id: str) -> Invoice:
    ...
```

Narrow tool:

```text
lower ambiguity
better schema
better authorization
better auditing
better model behavior
```

---

# 78. Resources should represent meaningful data boundaries

Bad:

```text
database://everything
```

Better:

```text
company://policies/security
company://policies/leave
company://products/catalog
```

The resource URI becomes a meaningful conceptual boundary.

---

# 79. Prompts should encode reusable organizational behavior

For example:

```text
prompt:
    review_expense_report
```

can encode:

```text
Company finance review standards.
```

This can centralize frequently used instructions.

---

# 80. MCP server and security boundary

For enterprise usage, think:

```text
MCP server
=
capability boundary
```

For example:

```text
Salesforce MCP
```

should decide:

```text
What APIs can be called?
Which records?
Which user?
Which operations?
Which scopes?
```

not merely:

```text
Can the LLM invent a valid JSON call?
```

---

# 81. Authentication vs authorization

Suppose your remote MCP server is:

```text
https://mcp.company.com/mcp
```

Authentication answers:

> Who are you?

Authorization answers:

> What are you allowed to do?

You could have:

```text
Employee A
```

authenticated successfully but only allowed:

```text
salesforce.read
```

while:

```text
Manager B
```

may have:

```text
salesforce.read
salesforce.update
```

This becomes important in your later MCP security modules.

---

# 82. Current HTTP deployment security

FastMCP explicitly recommends authentication for remote MCP servers. Current FastMCP supports authentication approaches including bearer tokens, JWT, OAuth, and related mechanisms. ([FastMCP][15])

For an enterprise deployment, never think:

```text
remote MCP server = public unauthenticated endpoint
```

Your normal architecture should be:

```text
HTTPS
+
authentication
+
authorization
+
rate limiting
+
audit logging
+
network controls
+
tool-level policy
```

---

# 83. Important current MCP 2026 change: no server-initiated requests in the modern protocol

This matters because older tutorials may show servers doing things like:

```text
server -> client
```

during a request through an old live session.

The current 2026-07-28 protocol removes that old persistent callback channel.

Instead, modern MCP introduced **multi-round-trip requests**.

Conceptually:

```text
Client
   |
   | tool call
   ▼
Server
   |
   | "I need more input"
   ▼
Client
   |
   | answers
   ▼
Server
```

This allows modern stateless HTTP behavior without maintaining the old protocol-level session.

The official 2026 specification describes this as MRTR, or Multi Round-Trip Requests. ([Model Context Protocol Blog][9])

You don't need to implement that yet, but you should know about it so older tutorials don't confuse you.

---

# 84. FastMCP 4 removed some old behavior

FastMCP 4 specifically removed or changed some APIs from earlier generations.

Important examples:

### Old

```text
official MCP SDK v1:
from mcp.server.fastmcp import FastMCP
```

### Current standalone FastMCP

```python
from fastmcp import FastMCP
```

### Current official MCP Python SDK v2

```python
from mcp.server import MCPServer
```

The official SDK v2 explicitly renamed its old `FastMCP` high-level server to `MCPServer`. ([GitHub][17])

---

# 85. Don't confuse these two projects

This is worth highlighting again.

## Project A

Official MCP Python SDK:

```text
package:
jjmcp
```

Current stable:

```text
v2
```

Main high-level server class:

```python
MCPServer
```

([GitHub][18])

## Project B

Standalone FastMCP:

```text
package:
fastmcp
```

Current stable:

```text
FastMCP 4
```

Main server class:

```python
FastMCP
```

([GoFastMCP][10])

For **this module**, when I say:

```text
FastMCP
```

I mean:

```python
from fastmcp import FastMCP
```

---

# 86. Current vs deprecated cheat sheet

| Older material                                                   | Current approach                                                         |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `from mcp.server.fastmcp import FastMCP`                         | standalone `from fastmcp import FastMCP`, or official SDK v2 `MCPServer` |
| HTTP + SSE for new servers                                       | Streamable HTTP                                                          |
| `Client("server.py")` in FastMCP 4                               | `Client(Path("server.py"))`                                              |
| old protocol `initialize` / `Mcp-Session-Id` as the modern model | MCP 2026-07-28 independent requests                                      |
| server-initiated callback assumptions                            | modern multi-round-trip request model                                    |
| old FastMCP APIs removed in v4                                   | current FastMCP 4 APIs                                                   |
| blindly exposing giant generic tools                             | narrow capability-focused tools                                          |
| unauthenticated public HTTP server                               | authenticated/authorized remote MCP service                              |

The protocol/session and SDK changes are documented by the MCP project and FastMCP maintainers. ([Model Context Protocol Blog][9])

---

# 87. One more important FastMCP 4 deprecation

You may see:

```python
Client("server.py")
```

in tutorials.

Current FastMCP 4:

```python
Client(Path("server.py"))
```

FastMCP explicitly marks string-based local-file transport inference as deprecated and says it will be removed in FastMCP 5. ([FastMCP][7])

So I would teach you the `Path` version from the beginning.

---

# 88. FastMCP versioning recommendation

FastMCP's current versioning policy is unusual because the MCP ecosystem evolves rapidly.

Their documentation explicitly recommends exact version pinning for production. For example:

```toml
dependencies = [
    "fastmcp==4.0.5",
]
```

rather than loosely:

```toml
fastmcp>=4.0.0
```

because breaking changes can occur in minor releases when required by protocol evolution. ([FastMCP][11])

For your production projects, that is a very sensible practice.

Your development workflow can then be:

```text
pyproject.toml
      ↓
uv lock
      ↓
tested version
      ↓
Docker image
      ↓
production
```

which fits your existing dependency-management philosophy.

---

# 89. FastMCP is intentionally schema-driven

Your learning of Pydantic now comes together beautifully.

You can use:

```python
from pydantic import BaseModel, Field
```

and build structured tools around it.

For example:

```python
class CustomerQuery(BaseModel):
    customer_id: str = Field(
        description="Unique customer ID."
    )
    include_orders: bool = Field(
        default=False,
        description="Whether to include recent orders."
    )
```

Then your MCP tool can use structured input rather than accepting an unconstrained blob of text.

This is exactly the kind of design you want for reliable enterprise agents.

---

# 90. The full mental model

At this point, you should be able to visualize:

```text
                         USER
                          |
                          ▼
                  ┌───────────────┐
                  │   AI HOST     │
                  │               │
                  │ LangChain     │
                  │ LangGraph     │
                  │ Agent loop    │
                  └───────┬───────┘
                          |
                    MCP Client
                          |
              ┌───────────┴───────────┐
              |                       |
          STDIO                 Streamable HTTP
              |                       |
              ▼                       ▼
       local process             remote service
                                      |
                                      ▼
                              ┌───────────────┐
                              │  MCP SERVER   │
                              │               │
                              │  Tools        │
                              │  Resources    │
                              │  Prompts      │
                              └───────┬───────┘
                                      |
                           ┌──────────┼──────────┐
                           |          |          |
                          API        DB       Files
```

---

# 91. What happens during a real tool call?

Let's walk through one from beginning to end.

User says:

```text
"Get employee E001."
```

### Step 1 — LLM reasons

The agent decides:

```text
I should use get_employee.
```

### Step 2 — Agent creates tool call

Conceptually:

```text
get_employee(
    employee_id="E001"
)
```

### Step 3 — LangChain/MCP adapter

The host sends the MCP call.

### Step 4 — MCP client

The MCP client serializes the request according to MCP.

### Step 5 — Transport

For remote deployment:

```text
HTTP
```

carries the MCP message.

### Step 6 — MCP server

FastMCP receives it.

### Step 7 — validation

FastMCP validates:

```text
employee_id
```

### Step 8 — execution

Your function executes:

```python
get_employee("E001")
```

### Step 9 — result

The result is converted into an MCP-compatible result.

### Step 10 — return

The response travels back:

```text
server
  ↓
HTTP
  ↓
MCP client
  ↓
LangChain
  ↓
agent
```

### Step 11 — LLM

The agent gives the tool result back to the model.

### Step 12 — final response

The model responds:

```text
E001 is Aarav from Engineering.
```

That is the complete path.

---

# 92. MCP is therefore a decoupling layer

This is perhaps the deepest architectural concept in this module.

Without MCP:

```text
Agent ─────── tightly coupled ─────── tool implementation
```

With MCP:

```text
Agent
  |
MCP protocol
  |
server
  |
implementation
```

The agent doesn't need to know:

```text
PostgreSQL
REST API
Python
Java
Go
ServiceNow SDK
Salesforce SDK
```

It only understands:

```text
MCP capability
```

That is why MCP can be powerful in large organizations.

---

# 93. What MCP does NOT solve

This is equally important.

MCP does not automatically solve:

```text
authorization
business logic
identity
data governance
prompt injection
data leakage
tool abuse
LLM hallucination
incorrect tool selection
rate limiting
secret management
audit policy
```

You still need those layers.

A secure enterprise system might be:

```text
                    AI Model
                       |
                Agent / LangGraph
                       |
               Tool policy layer
                       |
                MCP client
                       |
          Authentication / identity
                       |
               Authorization
                       |
                MCP server
                       |
              Business logic
                       |
           ┌───────────┼───────────┐
           ▼           ▼           ▼
          APIs         DB         SaaS
```

MCP is one layer in this architecture, not the entire architecture.

---

# 94. A very important distinction for your future AI harness

I would separate your enterprise platform into these conceptual layers:

```text
Layer 1
Identity
    Keycloak / OIDC / OAuth

Layer 2
Agent orchestration
    LangGraph / Deep Agents

Layer 3
Model abstraction
    Gemini / Claude / OpenAI / local LLM

Layer 4
Tool policy
    allowlists
    permissions
    approvals
    audit

Layer 5
MCP interoperability
    MCP clients
    MCP servers

Layer 6
Enterprise systems
    Salesforce
    ServiceNow
    Jira
    O365
    Google Workspace
    internal APIs
```

That is much cleaner than thinking:

```text
MCP = entire AI platform
```

---

# 95. A recommended learning project for you

Don't just read this module.

Build one small but realistic server:

```text
company-directory-mcp
```

with:

```text
Tools
    get_employee
    search_employees

Resources
    company://policies/leave
    company://policies/security

Prompts
    summarize_employee
    explain_company_policy

Context
    logging
    progress

Lifespan
    shared database/client

Transport 1
    stdio

Transport 2
    Streamable HTTP

Deployment
    Docker
```

That single project will teach you most of Module 40.

---

# 96. Suggested project structure

For your coding style, I would eventually structure it approximately like:

```text
company-directory-mcp/
│
├── pyproject.toml
├── uv.lock
├── Dockerfile
├── README.md
│
└── src/
    └── company_mcp/
        ├── __init__.py
        ├── server.py
        │
        ├── tools/
        │   ├── __init__.py
        │   └── employees.py
        │
        ├── resources/
        │   ├── __init__.py
        │   └── policies.py
        │
        ├── prompts/
        │   ├── __init__.py
        │   └── employee.py
        │
        ├── infrastructure/
        │   ├── database.py
        │   └── clients.py
        │
        └── config.py
```

Don't start with this complexity immediately.

Start with:

```text
server.py
```

Then split it once you understand the fundamentals.

---

# 97. Your Module 40 learning ladder

I recommend mastering the module in this order:

### Level 1 — MCP fundamentals

Understand:

```text
Host
Client
Server
Protocol
Transport
Tool
Resource
Prompt
```

### Level 2 — FastMCP basics

Build:

```python
FastMCP(...)
@mcp.tool
@mcp.resource
@mcp.prompt
```

### Level 3 — schemas

Learn:

```text
type hints
Pydantic
validation
structured outputs
tool descriptions
annotations
```

### Level 4 — Context

Learn:

```text
Context
CurrentContext
logging
progress
request state
```

### Level 5 — Lifespan

Learn:

```text
startup
shared resources
cleanup
lifespan context
```

### Level 6 — transports

Master:

```text
STDIO
Streamable HTTP
legacy SSE
```

### Level 7 — deployment

Master:

```text
Docker
ASGI
reverse proxy
HTTPS
authentication
```

### Level 8 — interoperability

Connect:

```text
FastMCP server
      ↓
LangChain MCPAdapter
      ↓
LangGraph/Agent
      ↓
Gemini
```

### Level 9 — architecture

Understand when:

```text
plain LangChain tool
```

is better than:

```text
MCP
```

---

# 98. The most important things you should remember from Module 40

By the end of this module, these should be automatic in your head:

```text
MCP is a protocol, not an LLM.
```

```text
Host manages AI/application orchestration.
```

```text
Client connects a host to a server.
```

```text
Server exposes capabilities.
```

```text
Tools = executable actions.
```

```text
Resources = readable data.
```

```text
Prompts = reusable interaction templates.
```

```text
STDIO = local process integration.
```

```text
Streamable HTTP = modern remote deployment.
```

```text
SSE = legacy/backward compatibility.
```

```text
MCP 2026-07-28 removed protocol-level sessions.
```

```text
Application state can still exist.
```

```text
FastMCP 4 is the current standalone FastMCP line.
```

```text
Official MCP Python SDK v2 uses MCPServer.
```

```text
FastMCP @mcp.tool turns Python functions
into interoperable MCP capabilities.
```

```text
LangChain tools and MCP tools are not competitors.
```

```text
LangChain tools = application/framework abstraction.
```

```text
MCP = interoperability/protocol abstraction.
```

And the most important architectural rule:

> **Use a normal LangChain tool when a capability is simply an internal implementation detail of your agent; use MCP when the capability should become a reusable, independently consumable, interoperable service.**

That distinction will save you from unnecessarily wrapping every function in MCP while still giving you the interoperability benefits where they actually matter.

### Current references used for this module

The important current-state facts above are based primarily on the MCP specification/release documentation, the official MCP Python SDK v2 documentation, the current FastMCP 4 documentation, and current LangChain MCP documentation. ([Model Context Protocol Blog][9])

The natural next step after this module is **Module 40A: build the `company-directory-mcp` server together from an empty `uv` project, first over STDIO, then Streamable HTTP, then Docker, and finally connect it to a LangChain agent using Gemini**.

[1]: https://blog.gofastmcp.com/3mufbh2vcv22o?utm_source=chatgpt.com "FastMCP 4 is GA - fastmcp"
[2]: https://docs.langchain.com/oss/python/langchain/mcp "Model Context Protocol (MCP) - Docs by LangChain"
[3]: https://modelcontextprotocol.io/specification/draft/server/index?utm_source=chatgpt.com "Overview - Model Context Protocol"
[4]: https://gofastmcp.com/servers/tools "Tools - FastMCP"
[5]: https://gofastmcp.com/servers/resources "Resources & Templates - FastMCP"
[6]: https://gofastmcp.com/servers/prompts "Prompts - FastMCP"
[7]: https://gofastmcp.com/clients/transports "Client Transports - FastMCP"
[8]: https://gofastmcp.com/python-sdk/fastmcp-utilities-logging?utm_source=chatgpt.com "logging - FastMCP"
[9]: https://blog.modelcontextprotocol.io/posts/2026-07-28/?utm_source=chatgpt.com "The 2026-07-28 Specification | Model Context Protocol Blog"
[10]: https://blog.gofastmcp.com/3mufbh2vcv22o "FastMCP 4 is GA - fastmcp"
[11]: https://gofastmcp.com/getting-started/installation "Installation - FastMCP"
[12]: https://gofastmcp.com/servers/context "MCP Context - FastMCP"
[13]: https://gofastmcp.com/servers/progress?utm_source=chatgpt.com "Progress Reporting - FastMCP"
[14]: https://gofastmcp.com/servers/lifespan "Lifespans - FastMCP"
[15]: https://gofastmcp.com/deployment/http "HTTP Deployment - FastMCP"
[16]: https://gofastmcp.com/deployment/http?utm_source=chatgpt.com "HTTP Deployment"
[17]: https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/whats-new.md?utm_source=chatgpt.com "python-sdk/docs/whats-new.md at main · modelcontextprotocol/python-sdk · GitHub"
[18]: https://github.com/modelcontextprotocol/python-sdk?utm_source=chatgpt.com "GitHub - modelcontextprotocol/python-sdk: The official Python SDK for Model Context Protocol servers and clients · GitHub"
