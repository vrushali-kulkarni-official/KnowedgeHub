# PHASE 5 — Tools & MCP

## Module 37 — Building the Copilot Toolkit

This is where your learning moves from:

> “I know how to define a tool”

to:

> “I can build a **production-grade collection of tools that an AI copilot can safely use**.”

That distinction is extremely important.

A toy tool is:

```python
@tool
def get_weather(city: str) -> str:
    """Get the weather."""
    ...
```

A production tool has to answer questions such as:

* What inputs are allowed?
* What happens if the network hangs?
* Should it retry?
* Which URLs may it access?
* Can it accidentally become an SSRF vulnerability?
* How much data may it return to the LLM?
* What database account does it use?
* Can the LLM modify data?
* How long may a query run?
* What happens when the external service is down?
* How do we test it without calling the real Internet?
* How do we observe its calls?
* Can two different agents reuse the same tool?
* Should this be a LangChain tool, an MCP tool, or both?

That is what this module is really about.

As of **September 2026**, LangChain's current agent API is `create_agent`, its tool abstraction remains the `@tool` decorator, Gemini is integrated through `langchain-google-genai` / `ChatGoogleGenerativeAI`, and the official Python MCP SDK has moved to its v2 line implementing the July 28, 2026 MCP revision. ([Docs by LangChain][1])

---

# 1. First: understand what a "Copilot Toolkit" actually is

Imagine your copilot is a person sitting at a desk.

The LLM is the person's **brain**.

Tools are the person's:

* browser
* calculator
* database access
* internal knowledge search
* GitHub access
* weather API
* ticket system
* filesystem
* CRM
* internal REST APIs

The LLM doesn't magically know how those systems work.

Instead, you give it tools.

Conceptually:

```text
                       ┌────────────────────┐
                       │       Gemini       │
                       │       Brain        │
                       └─────────┬──────────┘
                                 │
                    chooses tool + arguments
                                 │
             ┌───────────────────┼───────────────────┐
             │                   │                   │
             ▼                   ▼                   ▼
       search_web          query_database       call_internal_api
             │                   │                   │
             ▼                   ▼                   ▼
         SearXNG              Postgres             FastAPI
```

A **copilot toolkit** is simply the carefully designed collection of these capabilities.

For your project, I would think about the toolkit like this:

```text
Copilot Toolkit
│
├── Search
│   └── SearXNG
│
├── Knowledge
│   ├── PostgreSQL / pgvector
│   ├── Qdrant
│   └── internal KB search
│
├── Database
│   └── read-only SQL
│
├── HTTP
│   └── selected external/internal APIs
│
├── Productivity
│   ├── GitHub
│   ├── Jira
│   └── Slack
│
└── MCP
    ├── external MCP servers
    └── your own MCP servers
```

The critical design principle is:

> **A tool should expose a narrow capability, not arbitrary infrastructure access.**

Bad:

```text
execute_any_sql
fetch_any_url
run_any_shell_command
```

Much better:

```text
search_products
search_internal_documents
lookup_customer
get_github_issue
get_order_status
search_web
```

---

# 2. Tool architecture: the most important concept in this module

Before building HTTP, DB, or search tools, I want you to learn one architecture pattern.

Do **not** put all your logic directly inside the LangChain decorator.

Instead:

```text
LLM
 │
 ▼
LangChain Tool Adapter
 │
 ▼
Application Service
 │
 ├── HTTP client
 ├── database repository
 ├── SearXNG client
 └── domain logic
```

For example:

```python
# service.py

class WeatherService:
    async def get_weather(self, city: str) -> Weather:
        ...
```

Then:

```python
# tool.py

from langchain.tools import tool

@tool
async def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    result = await weather_service.get_weather(city)
    return result.model_dump_json()
```

Why?

Because now you can test:

```text
WeatherService
```

without LangChain.

And independently test:

```text
LangChain tool
```

with a much smaller test.

This becomes extremely valuable when your application gets large.

---

# 3. Your ideal project structure

For your AI SaaS project, I'd move toward something like:

```text
src/
└── ai_rag/
    ├── main/
    │
    ├── domains/
    │   ├── chat/
    │   ├── rag/
    │   └── tools/
    │
    ├── infrastructure/
    │   ├── http/
    │   ├── postgres/
    │   ├── search/
    │   └── mcp/
    │
    └── core/
        ├── config.py
        ├── logging.py
        └── security.py
```

And specifically:

```text
domains/tools/
│
├── http/
│   ├── service.py
│   ├── schemas.py
│   └── tool.py
│
├── database/
│   ├── service.py
│   ├── schemas.py
│   └── tool.py
│
├── search/
│   ├── service.py
│   ├── schemas.py
│   └── tool.py
│
└── registry.py
```

Then:

```python
# registry.py

TOOLS = [
    search_web,
    query_database,
    call_internal_api,
]
```

And your agent:

```python
from langchain.agents import create_agent

agent = create_agent(
    model=gemini_model,
    tools=TOOLS,
)
```

LangChain currently recommends `create_agent` for the modern agent API. ([Docs by LangChain][2])

---

# 4. Tool design principles

Before individual tools, memorize these principles.

## Principle 1 — Least privilege

Give the tool exactly the permissions it needs.

For example:

```text
Web search
    ↓
Can search
Cannot modify anything
```

Database:

```text
AI database user
    ↓
SELECT only
Cannot INSERT
Cannot UPDATE
Cannot DELETE
Cannot ALTER
Cannot DROP
```

HTTP:

```text
allowed:
api.github.com
internal-api.example.com

not allowed:
127.0.0.1
localhost
169.254.169.254
random-domain.com
```

---

# 5. Principle 2 — Tools need strict boundaries

Imagine:

```python
@tool
async def fetch_url(url: str):
    ...
```

Looks innocent.

But an LLM could call:

```text
http://localhost:8000/admin
```

or:

```text
http://127.0.0.1:8000/secrets
```

or cloud metadata endpoints.

This is an **SSRF** problem.

Even worse:

```text
https://trusted.example.com
```

could redirect to:

```text
http://internal-service:9000
```

Therefore:

> **Never treat a URL supplied by an LLM as trustworthy.**

---

# 6. Principle 3 — output is also part of security

Suppose SearXNG returns:

```text
50 results
10,000 characters each
```

You shouldn't blindly return everything to Gemini.

You want:

```text
5 results
title
URL
short snippet
published date
```

The tool is therefore a **context firewall**.

Think:

```text
External world
      ↓
tool
      ↓
validate
      ↓
normalize
      ↓
truncate
      ↓
LLM
```

This is one of the most important ideas in agent engineering.

---

# 7. Principle 4 — failures must be controlled

External service:

```text
timeout
```

should not become:

```text
LLM receives 200 lines of Python traceback
```

Instead:

```json
{
  "ok": false,
  "error": "Search service timed out"
}
```

Or, depending on your agent architecture, a controlled tool error.

---

# 8. Principle 5 — don't expose infrastructure unnecessarily

Prefer:

```text
search_web
```

over:

```text
http_get("https://searxng...")
```

Prefer:

```text
get_customer(customer_id)
```

over:

```text
query_database(sql)
```

The more generic the tool, the more opportunities there are for:

* incorrect tool use
* prompt injection
* data leakage
* expensive queries
* privilege escalation
* huge responses

---

# Part 1 — Building an HTTP Tool with HTTPX

# 9. Why HTTPX?

For your Python/FastAPI stack, `httpx` is a very strong choice because it supports:

* synchronous requests
* async requests
* connection pooling
* HTTP/2
* explicit timeout configuration
* transports
* testing with mock transports

HTTPX also applies timeouts by default rather than allowing requests to hang indefinitely. ([HTTPX][3])

Install:

```bash
uv add httpx
```

---

# 10. Don't use one giant timeout

This:

```python
httpx.AsyncClient(timeout=30)
```

is valid, but production code often benefits from more granular control.

HTTPX exposes:

```text
connect
read
write
pool
```

timeouts. ([HTTPX][3])

For example:

```python
import httpx

timeout = httpx.Timeout(
    connect=3.0,
    read=10.0,
    write=5.0,
    pool=2.0,
)

client = httpx.AsyncClient(
    timeout=timeout,
)
```

Meaning:

```text
connect → establish network connection
read    → wait for response data
write   → send request data
pool    → wait for an available connection
```

---

# 11. Why retries are different from timeouts

This is extremely important.

A timeout says:

> "The operation took too long."

A retry says:

> "I believe trying again could reasonably succeed."

These are not the same.

For example:

```text
GET → timeout
```

might be retryable.

But:

```text
POST /create-user
```

might have partially succeeded before the timeout.

Blind retrying could create:

```text
user #1
user #2
```

So:

> **Retries require idempotency thinking.**

---

# 12. HTTPX's built-in retry capability

Modern HTTPX provides transport-level connection retries:

```python
transport = httpx.HTTPTransport(
    retries=2
)

client = httpx.Client(
    transport=transport
)
```

But these retries are specifically for connection failures such as `ConnectError` and `ConnectTimeout`; HTTPX recommends general-purpose retry tools such as Tenacity when you need broader policies such as retrying certain status codes. ([HTTPX][4])

Therefore:

```text
HTTPX transport retries
        ↓
connection-level retry
```

while:

```text
Tenacity
        ↓
application retry policy
```

---

# 13. Modern retry pattern

Install:

```bash
uv add tenacity
```

Conceptually:

```python
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
```

For a safe GET operation:

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(
        multiplier=0.5,
        min=0.5,
        max=4,
    ),
    retry=retry_if_exception_type(
        httpx.TransportError
    ),
)
async def fetch(...):
    ...
```

You should still think carefully about:

```text
401 → don't retry
403 → don't retry
404 → don't retry
400 → don't retry
429 → maybe retry with Retry-After
500 → potentially retry
502 → potentially retry
503 → potentially retry
504 → potentially retry
```

A useful production policy is therefore based on **error class**, not:

```python
except Exception:
    retry()
```

Never do that.

---

# 14. URL allowlists

Suppose your tool is supposed to call GitHub.

Don't permit:

```python
url: str
```

and then blindly request it.

Instead define:

```python
ALLOWED_HOSTS = {
    "api.github.com",
}
```

Then validate:

```python
from urllib.parse import urlparse


def validate_url(url: str) -> str:
    parsed = urlparse(url)

    if parsed.scheme != "https":
        raise ValueError("Only HTTPS URLs are allowed")

    if parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError("Host is not allowed")

    if parsed.username or parsed.password:
        raise ValueError("Credentials in URL are not allowed")

    return url
```

This is the basic version.

---

# 15. But hostname allowlisting is not the entire SSRF solution

Consider DNS:

```text
allowed.example.com
       ↓
DNS
       ↓
10.0.0.15
```

The domain itself looks innocent.

The resulting IP is internal.

So serious URL-fetching infrastructure needs to think about:

```text
scheme
hostname
port
DNS resolution
IP address
redirect destination
```

You should also reject dangerous destinations such as:

```text
127.0.0.0/8
10.0.0.0/8
172.16.0.0/12
192.168.0.0/16
169.254.0.0/16
::1
fc00::/7
```

and other loopback/link-local/reserved ranges as appropriate for your deployment.

Even better:

> For most business tools, **don't create a generic URL fetcher at all**.

Instead:

```python
get_github_issue(...)
get_customer(...)
get_weather(...)
```

with a fixed base URL.

That's dramatically easier to secure.

---

# 16. Production HTTP tool architecture

I'd use:

```text
tool.py
   ↓
service.py
   ↓
HTTPX client
   ↓
external API
```

Example:

```python
# github_service.py

class GitHubService:

    def __init__(
        self,
        client: httpx.AsyncClient,
    ):
        self.client = client

    async def get_repository(
        self,
        owner: str,
        repo: str,
    ) -> dict:
        response = await self.client.get(
            f"/repos/{owner}/{repo}"
        )

        response.raise_for_status()

        return response.json()
```

Then:

```python
# github_tool.py

from langchain.tools import tool


@tool
async def get_github_repository(
    owner: str,
    repo: str,
) -> str:
    """Get metadata for a GitHub repository."""

    result = await github_service.get_repository(
        owner=owner,
        repo=repo,
    )

    return json.dumps({
        "name": result["name"],
        "description": result["description"],
        "stars": result["stargazers_count"],
        "url": result["html_url"],
    })
```

Notice what happened.

The API may return:

```text
100+ fields
```

but the LLM gets:

```text
4-5 useful fields
```

That is good tool design.

---

# Part 2 — Database Tool

# 17. Why database tools are dangerous

Database access is one of the most powerful capabilities you can give an agent.

It is also one of the easiest to misuse.

A naïve tool:

```python
@tool
def query_db(sql: str):
    return db.execute(sql)
```

is **not production-grade**.

Even if the LLM "only intends" to read data.

---

# 18. The strongest protection: database permissions

The first security boundary must be:

> **the database itself.**

Suppose PostgreSQL has:

```text
copilot_reader
```

Create a role that has only the required permissions.

Conceptually:

```sql
CREATE ROLE copilot_reader
LOGIN
PASSWORD '...';

GRANT CONNECT
ON DATABASE ai_rag
TO copilot_reader;
```

Then:

```sql
GRANT USAGE
ON SCHEMA public
TO copilot_reader;
```

Then only:

```sql
GRANT SELECT
ON TABLE customers
TO copilot_reader;
```

etc.

Do not give it:

```text
INSERT
UPDATE
DELETE
CREATE
ALTER
DROP
```

This creates a security boundary independent of the LLM.

---

# 19. Why an application-side `SELECT` check is insufficient

You may be tempted to do:

```python
if not sql.lower().startswith("select"):
    raise ValueError()
```

That's useful as a secondary guard, but it should never be your primary security boundary.

SQL is complicated.

For example:

```sql
WITH x AS (
    ...
)
SELECT ...
```

or:

```sql
SELECT some_function(...)
```

or other SQL constructs can make simplistic textual validation unreliable.

Therefore:

```text
LLM-generated SQL
      ↓
application validation
      ↓
read-only DB credentials
      ↓
query timeout
      ↓
row/result limits
```

Use multiple layers.

---

# 20. Schema description in the tool docstring

This is a surprisingly important technique.

The model needs to know what the database contains.

Bad:

```python
@tool
def query_database(query: str):
    """Query the database."""
```

Better:

```python
@tool
def query_database(query: str):
    """
    Read data from the analytics PostgreSQL database.

    Available tables:

    customers(
        id,
        name,
        email,
        created_at
    )

    orders(
        id,
        customer_id,
        amount,
        status,
        created_at
    )

    Relationships:
    orders.customer_id -> customers.id

    Only read-only SELECT queries are supported.
    """
```

Why?

Because tool descriptions are part of the model's tool-use context.

You are effectively giving the LLM:

```text
mini database schema documentation
```

---

# 21. But don't dump the entire production schema

Imagine you have:

```text
350 tables
```

Putting all of them into the tool description is terrible.

It increases:

* context size
* token cost
* confusion
* probability of selecting wrong tables

Instead use:

```text
database discovery tool
```

or:

```text
domain-specific DB tools
```

For example:

```text
sales database
customer database
inventory database
```

This is another reason specialized tools are often better than one universal SQL tool.

---

# 22. Query timeout

Suppose the model generates:

```sql
SELECT *
FROM massive_table
CROSS JOIN massive_table;
```

Without protection, you've created an expensive query.

PostgreSQL provides `statement_timeout`, which aborts statements after the configured number of milliseconds. ([PostgreSQL][5])

For an agent workload, something like:

```text
2–10 seconds
```

may be a reasonable starting point, depending on your data and use case.

---

# 23. Query timeout with a transaction

A useful PostgreSQL concept is:

```sql
SET LOCAL statement_timeout = 5000;
```

Because `SET LOCAL` applies within the transaction.

Conceptually:

```text
BEGIN
    SET LOCAL statement_timeout = 5000;

    SELECT ...

COMMIT
```

This is better than depending only on application-side asyncio timeout.

Why?

Because:

```text
application timeout
```

and:

```text
database cancellation
```

are different mechanisms.

Ideally the database itself knows:

> "This query is not allowed to run longer than 5 seconds."

---

# 24. SQLAlchemy 2.x

For your stack, SQLAlchemy 2-style APIs are the direction to learn.

Current SQLAlchemy documentation is on the 2.x line; the 2.0 documentation currently lists release 2.0.53 from September 14, 2026. ([SQLAlchemy Documentation][6])

Example:

```bash
uv add sqlalchemy psycopg
```

Connection:

```python
from sqlalchemy import create_engine

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)
```

---

# 25. A safe read-only database service

Here is the conceptual version I want you to understand.

```python
from sqlalchemy import text


class ReadOnlyDatabaseService:

    def __init__(
        self,
        engine,
        timeout_ms: int = 5000,
    ):
        self.engine = engine
        self.timeout_ms = timeout_ms

    def execute(self, query: str):
        with self.engine.begin() as conn:

            conn.exec_driver_sql(
                f"SET LOCAL statement_timeout = "
                f"{self.timeout_ms}"
            )

            conn.exec_driver_sql(
                "SET LOCAL transaction_read_only = on"
            )

            result = conn.execute(
                text(query)
            )

            rows = result.fetchmany(100)

            return rows
```

Important:

```python
fetchmany(100)
```

means you aren't blindly loading millions of rows.

---

# 26. Result shaping

Don't return this:

```python
return rows
```

You want something like:

```python
{
    "columns": [
        "id",
        "name",
        "amount",
    ],
    "rows": [
        [1, "Alice", 100],
        [2, "Bob", 200],
    ],
    "row_count": 2,
    "truncated": False,
}
```

The agent now receives a compact representation.

---

# 27. Always control row count

Imagine:

```sql
SELECT *
FROM customers;
```

10 million rows.

Never allow the tool to return 10 million rows.

Use:

```text
maximum rows
maximum bytes
maximum execution time
```

Think of it as a resource budget:

```text
DB tool budget

query time     ≤ 5s
rows returned  ≤ 100
output size    ≤ 30 KB
```

This is a very useful production mindset.

---

# 28. SQL query correction loops

There is another advanced pattern you'll encounter in LangChain:

```text
LLM
 ↓
generate SQL
 ↓
execute
 ↓
error
 ↓
LLM sees error
 ↓
correct SQL
 ↓
execute again
```

This can be useful.

But be careful.

Without limits, you could create:

```text
retry loop
retry loop
retry loop
...
```

So define:

```text
max SQL attempts = 2 or 3
```

and terminate.

---

# 29. LangChain SQL toolkit

LangChain provides database-oriented tools and toolkits, where a toolkit is a collection of related tools. LangChain's integrations documentation explicitly distinguishes a tool from a toolkit in this way. ([Docs by LangChain][7])

You may encounter:

```text
SQLDatabaseToolkit
QuerySQLDatabaseTool
InfoSQLDatabaseTool
ListSQLDatabaseTool
QuerySQLCheckerTool
```

These are useful for learning and prototypes.

However, for your production AI SaaS, I would **not automatically give an unrestricted SQL toolkit access to your production database**.

Instead:

```text
production
    ↓
dedicated read-only role
    ↓
restricted schema
    ↓
query timeout
    ↓
row limit
    ↓
output limit
```

and preferably a purpose-built tool when the business operation is known.

---

# Part 3 — SearXNG

# 30. Why SearXNG fits your preferences

You said you prefer:

* free
* open source
* popular
* self-hostable
* avoid unnecessary vendor dependencies

SearXNG is therefore especially interesting for you.

SearXNG is a self-hosted metasearch engine that queries multiple search engines and presents combined results.

Its current search API supports:

```text
GET /
GET /search

POST /
POST /search
```

and can return JSON when the JSON format is enabled. ([SearXNG Documentation][8])

---

# 31. Why SearXNG instead of directly implementing search providers?

Without SearXNG:

```text
your agent
   │
   ├── Google API
   ├── Bing API
   ├── Brave API
   ├── DuckDuckGo
   └── other provider
```

You must manage each provider separately.

With SearXNG:

```text
your agent
      │
      ▼
   SearXNG
      │
      ├── search engine A
      ├── search engine B
      ├── search engine C
      └── search engine D
```

One interface.

---

# 32. Current Docker deployment

SearXNG's current documentation recommends its container/Compose deployment path for typical containerized installations, with an official Compose template and separate configuration directory. ([SearXNG Documentation][9])

The architecture you want is:

```text
copilot
   │
   │ HTTP
   ▼
searxng
   │
   ├── search engines
   │
   └── valkey
```

Valkey is important when enabling the SearXNG limiter/bot-protection functionality. ([SearXNG Documentation][10])

For your Docker environment, start with the current official Compose template rather than building a custom SearXNG image.

The official documentation currently gives this setup pattern:

```bash
mkdir -p ./searxng/core-config
cd ./searxng/

curl -fsSL \
  -O https://raw.githubusercontent.com/searxng/searxng/master/container/docker-compose.yml \
  -O https://raw.githubusercontent.com/searxng/searxng/master/container/.env.example

cp .env.example .env

docker compose up -d
```

This is the current documented container deployment path. ([SearXNG Documentation][9])

---

# 33. SearXNG JSON configuration

Your key configuration is:

```yaml
search:
  formats:
    - html
    - json
```

The API documentation notes that JSON must be enabled in `settings.yml`; requesting a format that isn't enabled returns `403`. ([SearXNG Documentation][8])

For example:

```yaml
use_default_settings: true

search:
  formats:
    - html
    - json

server:
  limiter: true
```

If you enable the limiter, configure Valkey as well. SearXNG's current docs specifically require Valkey for that limiter. ([SearXNG Documentation][10])

---

# 34. Calling SearXNG

Basic HTTP request:

```python
response = await client.get(
    "/search",
    params={
        "q": query,
        "format": "json",
        "language": "en",
    },
)
```

The API response contains search results.

Conceptually:

```json
{
  "query": "LangGraph tools",
  "results": [
    {
      "title": "...",
      "url": "...",
      "content": "...",
      "engine": "..."
    }
  ]
}
```

---

# 35. Never return the entire SearXNG response

Instead:

```python
def shape_results(data: dict) -> list[dict]:
    results = []

    for item in data.get("results", [])[:5]:

        results.append({
            "title": item.get("title", "")[:200],
            "url": item.get("url", ""),
            "snippet": item.get("content", "")[:500],
        })

    return results
```

Now:

```text
SearXNG
   ↓
raw response
   ↓
deduplicate
   ↓
select top N
   ↓
truncate snippets
   ↓
normalize fields
   ↓
LLM
```

This is what I mean by **result shaping**.

---

# 36. Deduplication

Search engines can sometimes return multiple results pointing to effectively the same URL.

Normalize:

```python
from urllib.parse import urlsplit, urlunsplit


def normalize_url(url: str) -> str:
    parts = urlsplit(url)

    return urlunsplit((
        parts.scheme,
        parts.netloc.lower(),
        parts.path,
        parts.query,
        "",
    ))
```

Then:

```python
seen = set()

for result in results:
    url = normalize_url(result["url"])

    if url in seen:
        continue

    seen.add(url)
```

Now the agent sees less noise.

---

# 37. Add result limits

A good search tool might enforce:

```text
max_results = 5
max_title_chars = 200
max_snippet_chars = 500
max_total_chars = 5_000
```

Why total character limits?

Because even:

```text
5 × 500 = 2,500
```

can become much larger after metadata, URLs, markup and multiple tool calls.

So have both:

```text
per-item limits
```

and:

```text
global limits
```

---

# 38. SearXNG tool

A clean version could look like:

```python
from langchain.tools import tool


@tool
async def search_web(query: str) -> str:
    """
    Search the public web using the internal SearXNG instance.

    Use this when current web information is required.
    Returns a small set of titles, URLs, and snippets.
    """

    results = await searxng_service.search(
        query=query,
        max_results=5,
    )

    return json.dumps(results)
```

Notice how simple the LLM-facing layer is.

All the complexity lives underneath.

---

# Part 4 — Search tool choices

You asked specifically:

> "most commonly used popular toolkits for search, KB query, DB read, etc."

The important distinction is:

```text
tool
```

versus:

```text
toolkit
```

LangChain describes a toolkit as a collection of tools intended to be used together. ([Docs by LangChain][7])

---

# 39. Search options

## SearXNG

Best fit for your stated philosophy:

```text
open source
self-hosted
no required SaaS search API
customizable
```

Great for:

```text
web search
research agents
internal copilots
self-hosted infrastructure
```

---

## Tavily

A very commonly used agent-oriented search integration.

Current LangChain integration:

```bash
uv add langchain-tavily
```

with:

```python
from langchain_tavily import TavilySearch
```

The current integration provides:

```text
TavilySearch
TavilyExtract
TavilyCrawl
TavilyMap
```

and the documented free tier currently includes 1,000 searches/month. ([Docs by LangChain][11])

Good choice when:

```text
you want managed search
and don't want to operate search infrastructure.
```

But for **your learning project**, I'd learn SearXNG first.

---

# 40. Gemini itself can provide search grounding

This is particularly relevant because you've asked to prefer Gemini.

Current LangChain's Gemini integration supports built-in Google Search grounding through tool binding. ([Docs by LangChain][12])

Conceptually:

```python
from langchain_google_genai import ChatGoogleGenerativeAI

model = ChatGoogleGenerativeAI(
    model="...",
)

model_with_search = model.bind_tools([
    {"google_search": {}}
])
```

This can be useful.

But conceptually it is different from:

```text
your own Search tool
```

because you lose some of the control provided by an explicitly managed tool layer.

For your architecture, I'd understand both:

```text
Gemini native search
```

and:

```text
your search_web tool → SearXNG
```

---

# 41. Knowledge-base tools

For your existing RAG architecture, you already have:

```text
Qdrant
Postgres / pgvector
embeddings
retrievers
rerankers
```

So your KB tool should generally be:

```python
@tool
async def search_internal_knowledge(
    query: str,
) -> str:
    """Search the company's internal knowledge base."""
```

Then internally:

```text
query
 ↓
rewrite / normalize
 ↓
dense retrieval
 ↓
sparse retrieval
 ↓
RRF
 ↓
MMR
 ↓
reranker
 ↓
top K
 ↓
compact tool output
```

This is much better than exposing:

```text
qdrant.search(...)
```

directly to the LLM.

The LLM should know:

> "search internal knowledge"

not:

> "use HNSW with ef_search=..."

Infrastructure details belong beneath the tool boundary.

---

# 42. Database tool choices

There are several levels:

### Level 1

Purpose-specific tools:

```text
get_customer
get_order
get_invoice
get_product
```

### Level 2

Read-only SQL tool:

```text
query_database
```

### Level 3

SQL toolkit:

```text
list tables
describe schema
generate SQL
check SQL
execute SQL
```

### Level 4

MCP database server

The last option becomes interesting when you want multiple applications/agents to consume the same database capability.

LangChain currently documents **MCP Toolbox for Databases**, an open-source MCP server intended to expose database tools and handle concerns such as connection pooling and authentication. ([Docs by LangChain][13])

This is something worth learning after you understand the underlying implementation.

---

# Part 5 — MCP

# 43. What problem does MCP solve?

Without MCP:

```text
Agent A
  ├── custom GitHub adapter
  ├── custom DB adapter
  └── custom search adapter

Agent B
  ├── another GitHub adapter
  ├── another DB adapter
  └── another search adapter
```

MCP gives you a standardized interface.

Conceptually:

```text
                    MCP server
                        │
         ┌──────────────┼──────────────┐
         │              │              │
       tools         resources       prompts
```

An MCP server exposes capabilities.

A client connects to it.

LangChain can then turn MCP tools into LangChain tools.

LangChain's current MCP integration uses `langchain-mcp-adapters` and `MultiServerMCPClient`. ([Docs by LangChain][14])

---

# 44. MCP architecture

Think:

```text
                       Gemini
                         │
                    LangChain
                         │
              langchain-mcp-adapters
                         │
              ┌──────────┼─────────┐
              │          │         │
              ▼          ▼         ▼
           GitHub      Postgres   Search
             MCP         MCP        MCP
            server      server     server
```

This means you don't necessarily need to rewrite every capability for every agent framework.

---

# 45. Modern MCP transport

The official MCP Python SDK currently supports:

```text
stdio
Streamable HTTP
SSE
```

and the current stable Python SDK is v2. ([GitHub][15])

For modern remotely deployed MCP systems:

```text
Streamable HTTP
```

is particularly important.

For local tooling:

```text
stdio
```

is very convenient.

---

# 46. Important MCP version change

This is an area where older tutorials will confuse you.

The official Python MCP SDK currently says:

```text
v2 = current stable line
```

and the protocol revision is:

```text
2026-07-28
```

The newer protocol removes the old initialization handshake/session model from the newest protocol generation, using server discovery instead; the SDK's client defaults to compatibility negotiation. ([GitHub][16])

You don't need to implement that protocol manually.

The SDK handles it.

---

# 47. MCP Python SDK naming change

Older tutorials may show:

```python
from mcp.server.fastmcp import FastMCP
```

The official MCP Python SDK v2 changed that architecture; its server abstraction is now:

```python
from mcp.server import MCPServer
```

The official SDK documentation explicitly calls out `FastMCP` → `MCPServer` as a breaking v2 change. ([GitHub][16])

However, there is also a separate Python package called `fastmcp`, and LangChain's current MCP documentation demonstrates that package for custom servers. ([Docs by LangChain][14])

So when reading tutorials, always check which package they mean:

```text
mcp
```

versus:

```text
fastmcp
```

Do not assume they are the same thing.

---

# 48. LangChain consuming MCP

Current LangChain:

```bash
uv add langchain-mcp-adapters
```

Then:

```python
from langchain_mcp_adapters.client import MultiServerMCPClient

client = MultiServerMCPClient(
    {
        "search": {
            "transport": "http",
            "url": "http://localhost:8000/mcp",
        }
    }
)

tools = await client.get_tools()
```

Then:

```python
agent = create_agent(
    model,
    tools,
)
```

LangChain's current adapter supports multiple MCP servers and converts their tools into LangChain tools. ([Docs by LangChain][14])

---

# 49. When should you use LangChain tools vs MCP?

This is important.

Use ordinary LangChain tools when:

```text
tool is internal
tool only belongs to this application
tool has no reason to be independently hosted
```

Example:

```python
search_internal_documents
```

inside your application.

Use MCP when:

```text
multiple applications should consume it
multiple agent frameworks should consume it
you want separate deployment
you want a standardized tool protocol
```

For example:

```text
GitHub MCP server
```

can potentially be consumed by:

```text
your LangChain agent
Claude-compatible clients
other MCP clients
```

That's the architectural advantage.

---

# Part 6 — Testing tools

This is one of the areas I strongly want you to take seriously.

A tool should have:

```text
unit tests
integration tests
security tests
failure tests
```

---

# 50. Test pyramid

Think:

```text
             ▲
             │
       Agent/E2E tests
             │
       Integration tests
             │
        Tool unit tests
             │
         Service tests
             ▼
```

Most tests should be lower down.

---

# 51. Unit testing the service

Suppose:

```python
class SearchService:

    async def search(self, query: str):
        ...
```

Test the service independently.

You should test:

```text
normal response
empty results
malformed response
HTTP 500
HTTP 429
timeout
invalid JSON
huge response
duplicate URLs
```

---

# 52. HTTPX MockTransport

HTTPX provides mock transports specifically for testing and mocking HTTP services. ([HTTPX][4])

Example:

```python
import httpx
import pytest


def handler(request: httpx.Request):
    return httpx.Response(
        200,
        json={
            "name": "demo",
            "status": "ok",
        },
    )


@pytest.mark.anyio
async def test_api_client():

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://example.test",
    ) as client:

        response = await client.get("/health")

    assert response.status_code == 200
```

No Internet.

Fast.

Deterministic.

---

# 53. Test timeout behavior

You want a fake service that raises:

```python
httpx.ReadTimeout(...)
```

and verify your tool produces the expected controlled error.

Example conceptually:

```python
async def handler(request):
    raise httpx.ReadTimeout(
        "service timed out"
    )
```

Then:

```python
with pytest.raises(...):
    await service.fetch(...)
```

or assert your tool returns a controlled failure structure.

---

# 54. Test retry behavior

Suppose:

```text
attempt 1 → 503
attempt 2 → 503
attempt 3 → 200
```

Your unit test should simulate exactly that.

For example:

```python
calls = 0

def handler(request):
    nonlocal calls
    calls += 1

    if calls < 3:
        return httpx.Response(503)

    return httpx.Response(
        200,
        json={"ok": True},
    )
```

Then:

```python
result = await service.fetch(...)

assert result["ok"] is True
assert calls == 3
```

Now your retry policy is actually tested.

---

# 55. Test that you DON'T retry

This is just as important.

For:

```text
400
401
403
404
```

verify:

```python
assert calls == 1
```

You don't want:

```text
401
401
401
401
```

---

# 56. Test URL allowlists

Security tests:

```text
https://allowed.example.com
→ allowed

http://allowed.example.com
→ rejected

https://evil.example.com
→ rejected

http://127.0.0.1
→ rejected

http://localhost
→ rejected
```

And test:

```text
username/password in URL
non-default ports
redirects
IPv4
IPv6
encoded hostnames
```

Security testing isn't "extra".

For agent tools, it is part of the normal unit test suite.

---

# 57. Database unit testing

Don't make all DB tests call your production Postgres.

Split them.

### Unit tests

Mock your DB layer.

Test:

```text
query construction
result shaping
row limits
error handling
timeout configuration
```

### Integration tests

Use an actual PostgreSQL container.

Test:

```text
permissions
real SQL
transactions
statement_timeout
schema
indexes
```

This is one place where Docker is extremely useful.

---

# 58. Database security integration test

A very valuable test:

```sql
SELECT ...
```

should succeed.

Then:

```sql
INSERT ...
```

should fail.

Then:

```sql
UPDATE ...
```

should fail.

Then:

```sql
DELETE ...
```

should fail.

Then:

```sql
DROP TABLE ...
```

should fail.

That proves the **database permission boundary** rather than assuming your Python code is secure.

---

# 59. Test query timeout

Have an integration test with something intentionally slow, for example a controlled PostgreSQL delay.

Then assert the query gets cancelled by your configured timeout.

This verifies:

```text
Python timeout
```

and:

```text
PostgreSQL timeout
```

are actually configured correctly.

---

# 60. SearXNG tests

Do not make every unit test depend upon your live SearXNG instance.

Mock:

```json
{
    "results": [
        {
            "title": "Result 1",
            "url": "https://example.com/1",
            "content": "..."
        }
    ]
}
```

Then verify:

```text
top 5 only
duplicates removed
title truncated
snippet truncated
empty fields handled
malformed result ignored
```

---

# 61. Test total output size

This is a very useful agent-specific test.

For example:

```python
output = await search_tool("test")

assert len(output) <= 5000
```

Now you have an explicit context budget.

---

# 62. Tool contract tests

For every tool, I recommend a checklist.

```text
INPUT
  ✓ schema validation
  ✓ required fields
  ✓ max lengths
  ✓ allowed values

SECURITY
  ✓ authentication
  ✓ authorization
  ✓ allowlist
  ✓ SSRF protections
  ✓ injection protections

RELIABILITY
  ✓ timeout
  ✓ retry
  ✓ rate limiting
  ✓ graceful failures

OUTPUT
  ✓ normalized
  ✓ truncated
  ✓ predictable shape
  ✓ no secrets

OBSERVABILITY
  ✓ duration
  ✓ success/failure
  ✓ tool name
  ✓ request ID / trace ID

TESTING
  ✓ happy path
  ✓ failure path
  ✓ boundary cases
  ✓ security cases
```

This is a very good mental template to internalize.

---

# Part 7 — Tool errors

# 63. Should tools return exceptions or strings?

You will see both patterns.

Bad:

```python
try:
    ...
except Exception as e:
    return str(e)
```

Why?

Because:

```text
database password
hostnames
stack traces
internal paths
driver details
```

might leak.

Instead:

```python
except TimeoutError:
    return {
        "ok": False,
        "error": "Database query timed out.",
    }
```

Log the technical exception internally.

Return the safe explanation externally.

---

# 64. Error taxonomy

I recommend thinking in categories.

```text
VALIDATION_ERROR
AUTH_ERROR
PERMISSION_ERROR
NOT_FOUND
RATE_LIMITED
TIMEOUT
UPSTREAM_ERROR
INTERNAL_ERROR
```

For example:

```json
{
  "ok": false,
  "error": {
    "code": "TIMEOUT",
    "message": "The search service timed out."
  }
}
```

This becomes much easier for agents to reason about than random traceback strings.

---

# Part 8 — Tool observability with Langfuse

Since you're learning Langfuse, this is where it becomes useful.

Your trace should conceptually show:

```text
User request
   │
   ├── Gemini call
   │
   ├── search_web
   │      ├── latency
   │      ├── query
   │      ├── results
   │      └── error?
   │
   ├── query_database
   │      ├── latency
   │      ├── row_count
   │      └── timeout?
   │
   └── Gemini final response
```

This allows you to answer:

```text
Why did the agent choose this tool?
Which tool is slow?
Which tool fails most often?
How many times is a search tool called?
How much context does a tool return?
```

This is exactly why your current learning path of:

```text
LangChain
LangGraph
Langfuse
Deep Agents
```

fits together so well.

---

# Part 9 — Gemini

You specifically asked that LLM calls prefer Gemini.

The current LangChain Gemini integration uses:

```python
from langchain_google_genai import ChatGoogleGenerativeAI
```

and the current integration package has moved to Google's consolidated `google-genai` SDK. The docs also distinguish the older `GoogleGenerativeAI` text-completion interface from `ChatGoogleGenerativeAI`, which is the modern chat-model interface you generally want here. ([Docs by LangChain][12])

Install:

```bash
uv add langchain-google-genai
```

Then:

```python
from langchain_google_genai import ChatGoogleGenerativeAI

model = ChatGoogleGenerativeAI(
    model="...",
)
```

Your agent:

```python
from langchain.agents import create_agent

agent = create_agent(
    model=model,
    tools=[
        search_web,
        search_internal_knowledge,
        query_database,
    ],
)
```

---

# Part 10 — Current vs old patterns

This is the section you specifically requested.

## LangChain

### Modern

```python
from langchain.agents import create_agent
```

Use:

```python
create_agent(...)
```

Current LangChain docs present this as the modern agent API. ([Docs by LangChain][2])

### Old tutorials

You may encounter:

```python
initialize_agent(...)
```

and older `AgentExecutor`-centric examples.

Don't build your new architecture around old tutorials.

---

## Gemini

### Modern

```python
ChatGoogleGenerativeAI
```

from:

```text
langchain-google-genai
```

### Legacy interface

```python
GoogleGenerativeAI
```

is documented as the older text-completion-style interface. ([Docs by LangChain][17])

---

## Vertex Gemini

Older tutorials might show:

```python
ChatVertexAI
```

For Gemini models, current LangChain documentation points toward:

```python
ChatGoogleGenerativeAI
```

instead, while `langchain-google-vertexai` remains relevant for Vertex-specific platform services. ([Docs by LangChain][18])

---

## MCP Python SDK

### Current

```text
mcp 2.x
```

### Previous

```text
mcp 1.x
```

The official SDK states that v1 is now the maintenance line, while v2 is the stable line. ([GitHub][15])

---

## MCP server class

Older:

```python
FastMCP
```

inside the old official SDK layout.

Current official SDK:

```python
MCPServer
```

The naming/architecture changed in v2. ([GitHub][16])

But remember the separate `fastmcp` package exists, so don't blindly replace every `FastMCP` you see.

---

# Part 11 — Your recommended Copilot Toolkit

Given your stack and preferences, I would build your learning implementation as:

```text
                     ┌───────────────┐
                     │    Gemini     │
                     └───────┬───────┘
                             │
                         LangChain
                             │
                     ┌───────┴────────┐
                     │     Tools      │
                     └───────┬────────┘
                             │
       ┌─────────────────────┼────────────────────┐
       │                     │                    │
       ▼                     ▼                    ▼
 search_web            search_kb          query_database
       │                     │                    │
       ▼                     ▼                    ▼
    SearXNG            Qdrant/Postgres        PostgreSQL

       │
       │
       ▼
   http_api tools
       │
       ▼
     HTTPX
```

And separately:

```text
                  MCP ecosystem
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
       GitHub        DB server     other
        MCP            MCP         MCP
          │            │            │
          └────────────┼────────────┘
                       ▼
             langchain-mcp-adapters
                       │
                       ▼
                   LangChain
```

---

# Part 12 — The actual toolkit I would build for your project

Start with these **five**.

### Tool 1 — Web search

```python
search_web(query)
```

Implementation:

```text
LangChain
   ↓
your service
   ↓
HTTPX
   ↓
SearXNG
```

---

### Tool 2 — Internal KB

```python
search_internal_knowledge(query)
```

Implementation:

```text
query
 ↓
retriever
 ↓
dense + sparse
 ↓
RRF
 ↓
MMR
 ↓
reranker
 ↓
top results
```

You already learned RAG, so this tool now becomes the bridge between your RAG system and your agent.

---

### Tool 3 — Read-only DB

```python
query_database(query)
```

Protected by:

```text
read-only DB role
statement_timeout
transaction_read_only
row limit
output limit
query validation
```

---

### Tool 4 — Internal HTTP API

Instead of:

```python
http_get(url)
```

create business-specific tools:

```python
get_customer(...)
get_order(...)
get_project(...)
get_ticket(...)
```

Implementation:

```text
LangChain
   ↓
service
   ↓
HTTPX
   ↓
FastAPI/internal API
```

---

### Tool 5 — MCP capability

Expose selected capabilities through MCP when they need to be shared outside the current LangChain application.

---

# Part 13 — A complete request lifecycle

Let's say the user asks:

> "Find the latest information about our Qdrant deployment and tell me which internal environment uses it."

Gemini may reason:

```text
Need external/current information?
    ↓
search_web
```

Then:

```text
Need internal information?
    ↓
search_internal_knowledge
```

Possibly:

```text
Need structured deployment information?
    ↓
query_database
```

The whole flow becomes:

```text
User
 ↓
Gemini
 ↓
search_web
 ↓
SearXNG
 ↓
results
 ↓
Gemini
 ↓
search_internal_knowledge
 ↓
Qdrant
 ↓
results
 ↓
Gemini
 ↓
final answer
```

This is the fundamental agent loop you are learning.

---

# 14. A particularly important insight: tools are API contracts for LLMs

Normal API design asks:

> "What does a developer need?"

Tool design asks:

> "What does a probabilistic language model need in order to reliably call this?"

That changes how you write the interface.

Bad:

```python
execute(sql: str)
```

Better:

```python
query_analytics(
    question: str,
)
```

Then your system internally handles:

```text
question
 ↓
SQL generation
 ↓
validation
 ↓
execution
 ↓
result shaping
```

Sometimes a little more abstraction produces a much more reliable agent.

---

# 15. What you should build as the Module 37 practical project

I recommend this exact project:

```text
copilot_toolkit/
│
├── pyproject.toml
│
├── src/
│   └── copilot_toolkit/
│       │
│       ├── tools/
│       │   ├── web_search.py
│       │   ├── knowledge_search.py
│       │   ├── database.py
│       │   └── api.py
│       │
│       ├── services/
│       │   ├── searxng.py
│       │   ├── knowledge.py
│       │   ├── database.py
│       │   └── http.py
│       │
│       ├── schemas/
│       │   ├── search.py
│       │   └── database.py
│       │
│       └── config.py
│
├── tests/
│   ├── unit/
│   │   ├── test_searxng.py
│   │   ├── test_http.py
│   │   ├── test_database.py
│   │   └── test_tool_output.py
│   │
│   ├── integration/
│   │   ├── test_postgres.py
│   │   └── test_searxng.py
│   │
│   └── security/
│       ├── test_ssrf.py
│       └── test_db_permissions.py
│
└── docker/
    └── searxng/
```

And dependencies roughly:

```bash
uv add \
    langchain \
    langchain-google-genai \
    httpx \
    tenacity \
    sqlalchemy \
    psycopg \
    langchain-mcp-adapters
```

For tests:

```bash
uv add --dev pytest pytest-asyncio
```

You may not need every dependency immediately; add them as you implement each component.

---

# 16. Learning sequence I recommend

Don't attempt all of this simultaneously.

### Stage A — HTTP tool

Learn:

```text
HTTPX
 ↓
AsyncClient
 ↓
timeouts
 ↓
HTTP errors
 ↓
retry
 ↓
URL validation
 ↓
allowlist
 ↓
result shaping
```

---

### Stage B — Database tool

Learn:

```text
SQLAlchemy
 ↓
Postgres role
 ↓
SELECT-only access
 ↓
statement_timeout
 ↓
transaction_read_only
 ↓
row limit
 ↓
result shaping
```

---

### Stage C — SearXNG

Learn:

```text
Docker Compose
 ↓
SearXNG
 ↓
JSON API
 ↓
HTTPX client
 ↓
result normalization
 ↓
deduplication
 ↓
truncation
 ↓
LangChain @tool
```

---

### Stage D — Tool testing

Learn:

```text
pytest
 ↓
HTTPX MockTransport
 ↓
fake failures
 ↓
retry tests
 ↓
security tests
 ↓
DB integration tests
```

---

### Stage E — MCP

Learn:

```text
MCP concepts
 ↓
MCP server
 ↓
stdio
 ↓
Streamable HTTP
 ↓
MCP client
 ↓
LangChain adapter
 ↓
multiple MCP servers
 ↓
authentication
 ↓
interceptors
```

LangChain's current MCP adapter also supports interceptors, which can be used for things such as authentication, retries, rate limiting, request modification, and access to runtime context. ([Docs by LangChain][14])

---

# 17. The mental model I want you to leave this module with

Don't think:

> "A tool is just a Python function."

Instead think:

```text
                 TOOL
                  │
     ┌────────────┼─────────────┐
     │            │             │
   INPUT       EXECUTION       OUTPUT
     │            │             │
 validation   permissions    normalization
 limits       timeout        truncation
 schema       retries        structured data
 auth         observability   safe errors
```

And underneath:

```text
            TOOL
             │
             ▼
          SERVICE
             │
       ┌─────┼─────┐
       ▼     ▼     ▼
     HTTP    DB   Search
```

And for cross-application interoperability:

```text
             TOOL
              │
              ▼
             MCP
              │
       ┌──────┼──────┐
       ▼      ▼      ▼
    Agent A Agent B Agent C
```

---

# 18. Your key takeaways

The most important lessons in Module 37 are these:

**1. A production tool is an API contract for an LLM.**

**2. Put real implementation logic in services, not inside `@tool`.**

**3. HTTPX should have explicit timeouts; retries need an intentional policy.** HTTPX's built-in transport retries are limited to connection-level failures; broader policies belong at the application layer. ([HTTPX][4])

**4. Never let an LLM freely access arbitrary URLs.** Prefer fixed upstreams or strict allowlists and SSRF protections.

**5. Database security must be enforced by PostgreSQL permissions, not merely Python checks.**

**6. Every database agent workload needs execution and output budgets.**

**7. SearXNG is an excellent open-source/self-hosted search layer for your preferences.** Its current API supports JSON when enabled, and its current container documentation recommends the Compose deployment path. ([SearXNG Documentation][8])

**8. Return compact, structured results to the model.** Do not dump raw API responses into the context.

**9. MCP is about interoperability and standardized tool exposure, not simply "another way to write a Python function."**

**10. For your current stack, the modern direction is `create_agent` + `@tool` + `ChatGoogleGenerativeAI` + optional `langchain-mcp-adapters`.** ([Docs by LangChain][1])

**11. Unit-test tools without the real network whenever possible, then use integration tests for the real infrastructure.** LangChain's current testing guidance also recommends keeping unit and integration tests separate because integration tests are slower and require external credentials. ([Docs by LangChain][19])

**12. For your AI SaaS, your eventual toolkit should look roughly like:**

```text
                    GEMINI
                      │
                 LANGCHAIN
                      │
       ┌──────────────┼──────────────┐
       │              │              │
       ▼              ▼              ▼
   Web Search      Internal KB    Read-only DB
       │              │              │
    SearXNG        Qdrant/PG      PostgreSQL

                      │
                      ▼
                 HTTPX APIs

                      │
                      ▼
                     MCP
              ┌───────┼────────┐
              ▼       ▼        ▼
           GitHub    Jira    Other systems
```

This is a very solid architecture to grow into **LangGraph and Deep Agents** later, because the agent orchestration layer can remain separate from the actual capabilities. Your tools become reusable building blocks rather than code tangled into one agent.

[1]: https://docs.langchain.com/oss/python/langchain/tools?utm_source=chatgpt.com "Tools - Docs by LangChain"
[2]: https://docs.langchain.com/oss/python/langchain/agents?utm_source=chatgpt.com "Agents - Docs by LangChain"
[3]: https://www.python-httpx.org/advanced/timeouts/?utm_source=chatgpt.com "Timeouts - HTTPX"
[4]: https://www.python-httpx.org/advanced/transports/ "Transports - HTTPX"
[5]: https://www.postgresql.org/docs/10/runtime-config-client.html?utm_source=chatgpt.com "PostgreSQL: Documentation: 10: 19.11. Client Connection Defaults"
[6]: https://docs.sqlalchemy.org/en/20/core/engines_connections.html?utm_source=chatgpt.com "Engine and Connection Use — SQLAlchemy 2.0 Documentation"
[7]: https://docs.langchain.com/oss/python/integrations/tools?utm_source=chatgpt.com "Tool integrations - Docs by LangChain"
[8]: https://docs.searxng.org/dev/search_api?utm_source=chatgpt.com "Search API - SearXNG Documentation (2026.9.15+ca4965040)"
[9]: https://docs.searxng.org/admin/installation-docker?utm_source=chatgpt.com "Installation container - SearXNG Documentation (2026.9.15+ca4965040)"
[10]: https://docs.searxng.org/admin/searx.limiter?utm_source=chatgpt.com "Limiter - SearXNG Documentation (2026.9.15+ca4965040)"
[11]: https://docs.langchain.com/oss/python/integrations/tools/tavily_search?utm_source=chatgpt.com "Tavily search integration - Docs by LangChain"
[12]: https://docs.langchain.com/oss/python/integrations/chat/google_generative_ai?utm_source=chatgpt.com "ChatGoogleGenerativeAI integration - Docs by LangChain"
[13]: https://docs.langchain.com/oss/python/integrations/tools/mcp_toolbox?utm_source=chatgpt.com "Mcp toolbox for databases integration - Docs by LangChain"
[14]: https://docs.langchain.com/oss/python/langchain/mcp?utm_source=chatgpt.com "Model Context Protocol (MCP) - Docs by LangChain"
[15]: https://github.com/modelcontextprotocol/python-sdk?utm_source=chatgpt.com "GitHub - modelcontextprotocol/python-sdk: The official Python SDK for Model Context Protocol servers and clients · GitHub"
[16]: https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/whats-new.md?utm_source=chatgpt.com "python-sdk/docs/whats-new.md at main · modelcontextprotocol/python-sdk · GitHub"
[17]: https://docs.langchain.com/oss/python/integrations/llms/google_generative_ai?utm_source=chatgpt.com "GoogleGenerativeAI integration - Docs by LangChain"
[18]: https://docs.langchain.com/oss/python/integrations/providers/google?utm_source=chatgpt.com "Google integrations - Docs by LangChain"
[19]: https://docs.langchain.com/oss/python/langchain/test/integration-testing?utm_source=chatgpt.com "Integration testing - Docs by LangChain"                  
