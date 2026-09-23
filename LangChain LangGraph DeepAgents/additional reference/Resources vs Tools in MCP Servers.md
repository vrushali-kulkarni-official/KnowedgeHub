**Yes, you *can* get a lot of information via tools — but resources exist for a fundamentally different reason.** They are not redundant.

### Core difference

| Aspect              | **Tools**                          | **Resources**                          |
|---------------------|------------------------------------|----------------------------------------|
| **Who controls it** | The **model** (LLM decides when to call) | The **application / client** (host decides when to load) |
| **Nature**          | Actions / functions (can have side effects) | Read-only data / context               |
| **When loaded**     | Dynamically, during the conversation when the model chooses | Explicitly by the client (or user), often proactively |
| **Token cost**      | Tool schemas are usually injected into the system prompt on every turn | Zero cost until the client actually reads them |
| **Typical use**     | "Do something" (query DB, send email, write file, call API) | "Know something" (schemas, docs, file contents, configs, logs) |

### Why the separation was created

1. **Control plane**  
   Tools are *model-driven*. The LLM sees the tool list and autonomously decides “I need this data/action now.”  
   Resources are *application-driven*. The host (Claude Desktop, Cursor, your own agent framework, etc.) decides what context to inject. The model never auto-fetches a resource.

2. **Token efficiency & context bloat**  
   Every tool description lives in the context window on every turn. If you expose dozens of “get_X” tools just to read data, you burn tokens constantly. Resources cost nothing until the client actually calls `resources/read`.

3. **Side-effect safety & permissions**  
   Resources are explicitly read-only. This makes the security model cleaner: granting “read this schema / these docs” is a different trust decision than granting “execute arbitrary queries / write files.”

4. **Caching, subscriptions, and URI addressing**  
   Resources are identified by URIs and support change notifications / subscriptions. Clients can cache them or only re-fetch when the server signals an update. Tools don’t have this built-in model.

5. **Intent signaling**  
   Declaring something as a resource tells both the client and the model: “This is passive context, not an action.” That improves reliability and reduces the chance the model treats a pure data fetch as a state-changing operation.

### Practical example

A good database MCP server typically does **both**:
- **Resources**: table schemas, ER diagrams, documentation → the client can preload or let the user attach them.
- **Tools**: `query`, `execute_sql`, `create_table` → the model decides when to run them.

You *could* expose everything as tools (`get_schema`, `get_docs`, `list_tables`…), and many early MCP servers did exactly that. It works, but it’s less efficient, less cacheable, and mixes “know” with “do.”

### Short rule of thumb
- Does the model need to **decide** when to fetch/act, and/or does it have side effects? → **Tool**
- Is it mostly static or semi-static read-only context that the application should control? → **Resource**

So resources weren’t added because tools are insufficient for *getting* information — they were added because pure tool-calling is the wrong abstraction for passive, application-controlled context.
