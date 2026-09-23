**MCP (Model Context Protocol) is now fully stateless at the protocol layer.** The latest specification (2026-07-28) completely removed protocol-level sessions, the `initialize` / `notifications/initialized` handshake, and the `Mcp-Session-Id` header. This was one of the biggest changes since MCP launched.

### What “stateless” actually means here

Previously, MCP worked like a traditional stateful protocol:
- Client and server did a handshake (`initialize`).
- Server issued a session ID.
- Every later request had to carry that session ID.
- The server remembered negotiated capabilities, client info, and any application state tied to that session.
- This forced sticky sessions or a shared session store (e.g. Redis) so the same server instance could handle related requests.

Now the protocol itself remembers **nothing** between requests. Every request is completely self-contained. The server processes it independently, with no memory of previous requests—even if they arrived on the same connection.

This is similar to how ordinary REST/HTTP APIs work: each call carries everything needed to process it.

### How state is managed now (the key shift)

The protocol no longer owns or tracks state. Responsibility moved to the **application layer** using an **explicit handle pattern**.

#### The explicit handle pattern (recommended way)

1. A tool creates some state and returns a handle (an opaque ID).
2. The AI model receives that handle and passes it back as a normal argument on later tool calls.
3. The server uses the handle to look up the real state from its own durable storage (database, cache, object store, etc.).

**Practical example: Shopping cart**

**Old (stateful) way:**
- Client connects → gets session ID.
- Server keeps the shopping cart in memory (or Redis) keyed by the session ID.
- Later `add_item` or `checkout` calls just use the session; the server already “knows” the cart.

**New (stateless) way:**
```
1. Model calls: create_basket()
   → Server creates a cart in its database and returns: { "basket_id": "cart_abc123" }

2. Model calls: add_item(basket_id="cart_abc123", item="shoes", qty=1)
   → Server loads the cart using "cart_abc123", adds the item, saves it.

3. Model calls: checkout(basket_id="cart_abc123")
   → Server loads the same cart and processes payment.
```

The model itself is responsible for remembering and threading the `basket_id` from one tool call to the next. The protocol no longer hides this correlation inside a session header.

Other common examples:
- Browser automation: `start_browser()` returns `browser_id`; later calls pass `browser_id`.
- File editing workflow: `open_document()` returns `doc_id`; subsequent edits pass `doc_id`.
- Multi-step analysis: `start_analysis()` returns `run_id`; later steps pass `run_id`.
- Pagination: list endpoints return opaque cursors that the client must pass back.

### Other places state still exists (but is now explicit)

| Kind of state                  | Where it lives now                                      | How it is handled |
|--------------------------------|---------------------------------------------------------|-------------------|
| Protocol version & capabilities | Carried in every request’s `_meta` field               | Client includes `io.modelcontextprotocol/protocolVersion` and `clientCapabilities` on every call. Optional `server/discover` for upfront discovery. |
| Client / server identity       | `_meta` on every request/response                       | Recommended but not required. |
| Application / business state   | Server’s own database or store + explicit handles      | Handle pattern above. |
| Authentication                 | Token / credentials on every request                    | No session to attach identity to; validate on each call. |
| Long-running tasks             | Tasks extension + durable task store                    | Separate from core protocol. |
| Subscriptions / change notifications | Client re-establishes `subscriptions/listen` if the stream drops | No server-side subscription state survives a disconnect. |
| Multi-round-trip needs (e.g. “are you sure?”) | Opaque `requestState` returned by the server and sent back by the client | Replaces old server-initiated callbacks. Must be protected (signed/HMAC) if it affects authorization. |

### Why this change was made

- **Scalability** — Any request can hit any server instance. Plain round-robin load balancing works. No sticky sessions, no shared session store required for the protocol itself.
- **Simpler infrastructure** — MCP servers can run like ordinary stateless HTTP services (Cloudflare Workers, Cloud Run, Kubernetes pods, etc.).
- **Visibility & control** — State is now visible to the model. The agent can reason about handles, compose them, decide when to share or isolate them, and the correlation appears in logs/audits.
- **Reliability** — Removing hidden session state eliminates a whole class of production bugs (session affinity failures, memory leaks, sticky-routing complexity).

### Important clarifications

- **Your application can still be stateful.** Statelessness applies only to the *protocol*. You can (and usually should) keep durable state in a database. You just reference it via explicit handles instead of relying on a protocol session.
- **The model now carries the continuity.** This is intentional. Previously the session was invisible to the model; now the handle is ordinary data the model can see and manage.
- **Security note** — Because handles and any `requestState` travel through the client, protect them if they affect authorization or sensitive data (sign them, use short TTLs, store real secrets only server-side).

In short: MCP removed *protocol-managed* state so the system can scale like modern web services. Application state that needs to span multiple tool calls is now managed the same way good REST APIs have always managed it—by returning an explicit ID and requiring the caller (in this case the AI model) to pass it back.
