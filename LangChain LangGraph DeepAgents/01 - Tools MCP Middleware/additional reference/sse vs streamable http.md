**General HTTP streaming**, **Server-Sent Events (SSE)**, and **Streamable HTTP (as used by MCP)** are related but distinct ways of sending data over HTTP without waiting for a complete response. They sit on a spectrum from low-level protocol features to higher-level application patterns, especially in the context of the Model Context Protocol (MCP).

### 1. General HTTP Streaming

**What it is**  
This is the foundational ability of HTTP to deliver a response body *incrementally* rather than buffering the entire body first. The client can start processing data as soon as the first bytes arrive.

Key mechanisms:
- **HTTP/1.1 Chunked Transfer Encoding** (`Transfer-Encoding: chunked`): The server omits `Content-Length` and sends the body as a series of chunks (each prefixed by its size in hex). A zero-length chunk signals the end. This lets the server stream dynamic content whose total size is unknown in advance.
- **HTTP/2 and HTTP/3**: Native streaming via binary frames and multiplexed streams. Chunked encoding is not used (and is forbidden in HTTP/2+); the protocol itself supports streaming and concurrent streams over one connection.

**When it appeared**  
- Chunked transfer encoding was standardized in **HTTP/1.1** (RFC 2616, June 1999; refined in later RFCs such as RFC 9112).
- HTTP/2 (2015) and HTTP/3 made streaming more efficient and multiplexed.

**Purpose**  
Enable progressive delivery of large or dynamically generated content (logs, progressive HTML rendering, large file downloads, LLM token streams, etc.) without forcing the server to compute/buffer everything first. It keeps connections persistent and reduces latency for the first byte.

**Problems it solved**  
Earlier HTTP/1.0-style responses required a known `Content-Length` (or closing the connection). This forced full buffering, delayed first-byte time, and made progressive rendering or real-time-ish updates difficult.

**When to use**  
Any time you need to stream bytes over HTTP and do not need a standardized event format or bidirectional messaging. Examples: progressive HTML (React streaming), log tailing, large JSON/CSV exports, or raw LLM token streams that the client parses itself.

### 2. Server-Sent Events (SSE)

**What it is**  
A standardized, higher-level protocol *built on top of* HTTP streaming. The server keeps an HTTP response open (`Content-Type: text/event-stream`) and pushes discrete *events* to the client. The client uses the browser’s `EventSource` API (or equivalent).

Event format is text-based and simple:
```
event: message
data: {"foo": "bar"}
id: 123

```
It is **unidirectional** (server → client only). Clients send data back via ordinary HTTP requests if needed.

**When it appeared**  
- Conceptualized by Ian Hickson around **2004** as part of WHATWG Web Applications 1.0.
- First experimental implementation in Opera (**September 2006**).
- Formalized as part of HTML5 / WHATWG Living Standard.
- W3C Recommendation on **3 February 2015**.
- Broad modern browser support (including Edge) by ~2020; works well with HTTP/2+.

**Purpose**  
Provide a simple, standards-based way for servers to push real-time updates (notifications, live feeds, progress, stock tickers, etc.) over plain HTTP without the complexity of WebSockets. It reuses existing HTTP infrastructure, proxies, and authentication.

**Problems it solved relative to raw HTTP streaming**  
- Standardized event framing, automatic reconnection, last-event-id for resume, and a clean client API (`EventSource`).
- Avoided the need for custom parsing of raw chunked streams.
- Better suited than short-polling (which wastes requests and latency) or long-polling (which is awkward).

**Limitations that later approaches addressed**  
- Strictly one-way.
- Requires a long-lived connection (problematic with some load balancers, idle timeouts, or serverless platforms).
- Under HTTP/1.1, browsers limit concurrent connections per domain (historically ~6); HTTP/2 largely removes this.
- No native bidirectional messaging or request-response correlation beyond what the application layers on top.

**When to use**  
Unidirectional server push over HTTP where simplicity and browser support matter: live dashboards, notifications, progress bars, news feeds. Prefer it over WebSockets when you only need server → client traffic and want to stay inside the HTTP ecosystem.

### 3. Streamable HTTP (MCP’s Transport)

**What it is**  
The current recommended remote transport in the **Model Context Protocol (MCP)** — Anthropic’s open protocol for connecting AI models/agents to tools, data sources, and services. It is *not* a general web standard; it is an MCP-specific binding that uses ordinary HTTP (POST + optional SSE).

Core design (as of the 2025-03-26 specification revision and later clarifications):
- Single MCP endpoint (e.g. `/mcp`).
- Client sends every JSON-RPC message as an HTTP **POST**.
- Server replies with either:
  - A single `application/json` response (simple request/response), or
  - A request-scoped **SSE stream** (`text/event-stream`) when multiple messages or progressive results are needed.
- Optional GET for server-initiated streams in earlier revisions; later revisions simplified this.
- Supports sessions (via `Mcp-Session-Id` header in some revisions), authentication (OAuth, API keys, etc.), and works with stateless or stateful servers.

It **replaces** the earlier MCP “HTTP+SSE” transport.

**When it appeared**  
- MCP itself launched publicly around late 2024.
- Original remote transport: **HTTP + SSE** in the **2024-11-05** protocol version (two endpoints: long-lived GET for SSE stream + separate POST for client messages).
- **Streamable HTTP** introduced in the **2025-03-26** specification revision as the replacement. It became the primary/recommended remote transport; the old dual-endpoint HTTP+SSE was deprecated (kept only for backward compatibility).

**Purpose**  
Provide a robust, scalable, infrastructure-friendly way for remote MCP servers (SaaS tools, shared team services, cloud-hosted tool servers) to exchange JSON-RPC messages with clients (Claude Desktop, other agents, etc.). It supports both simple request/response and streaming/progressive results while remaining compatible with modern HTTP infrastructure.

**Problems the previous (HTTP+SSE) approach had that Streamable HTTP solved**  
| Issue with old HTTP+SSE | How Streamable HTTP fixed it |
|-------------------------|------------------------------|
| Two separate endpoints (GET SSE + POST) that had to be correlated | Single endpoint; everything goes through one URL |
| Mandatory long-lived connection for every session | Long-lived connections are optional; simple calls can be pure request/response |
| Hard to run on serverless / ephemeral platforms or behind ordinary load balancers (sticky sessions often required) | Works with stateless servers and ordinary HTTP routing |
| Awkward authentication and session management | Native HTTP headers, standard auth patterns, clearer session IDs |
| Scaling and multi-tenancy friction | Horizontal scaling becomes straightforward |
| One-way streaming bias | True request-scoped bidirectional flow (client POSTs, server can stream related messages back) |

**When to use what in the MCP world**
- **stdio** — Local tools running as a subprocess on the same machine as the client (fastest, simplest, zero network). Ideal for filesystem access, local CLIs, personal utilities.
- **Streamable HTTP** — Remote / hosted MCP servers (the current recommended choice). Use for multi-user SaaS integrations, team-shared tools, cloud deployments, anything that needs auth, scaling, or network access.
- **Legacy HTTP+SSE** — Only for backward compatibility with older clients/servers. Do not build new servers on it.

### Summary Comparison

| Aspect                  | General HTTP Streaming          | SSE                              | Streamable HTTP (MCP)                  |
|-------------------------|---------------------------------|----------------------------------|----------------------------------------|
| Level                   | Protocol feature                | Application protocol on HTTP     | MCP-specific transport on HTTP         |
| Direction               | Response body (server→client)   | Server→client only               | Bidirectional (POST + optional SSE)    |
| Framing                 | Raw chunks / frames             | Standardized text events         | JSON-RPC over HTTP ± SSE               |
| Long-lived connection   | Optional                        | Usually yes                      | Optional (on-demand)                   |
| Standardization        | HTTP specs                      | WHATWG/W3C                       | MCP specification                      |
| Best for                | Any progressive byte stream     | Simple server push               | Remote MCP tool/server communication   |
| Introduced              | HTTP/1.1 (1999)                 | ~2004–2006 (std 2015)            | 2025-03-26 (replaced 2024 SSE transport) |

**Practical rule of thumb**  
- Need raw progressive delivery of bytes? → General HTTP streaming (chunked or HTTP/2 frames).  
- Need simple, standardized one-way push events in a browser? → SSE.  
- Building or consuming a remote MCP server? → Streamable HTTP (the current standard). Use stdio for local-only tools.  

Streamable HTTP deliberately re-uses SSE as an *optional* streaming mechanism inside ordinary HTTP request/response patterns, combining the best of both worlds while fixing the operational pain points of the earlier dual-endpoint design.
