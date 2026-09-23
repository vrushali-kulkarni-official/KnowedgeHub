**`@lifespan` in FastMCP** is a decorator that lets you run setup code **once** when your MCP server starts and cleanup code **once** when it stops.

It is the recommended modern way (from FastMCP 3.0+) to manage long-lived resources that should live for the entire lifetime of the server process — not per client connection.

### Why do we need it?

Imagine your server needs:
- A database connection pool
- A Redis/cache client
- A loaded configuration
- An API client that should stay open
- Background tasks or warm data

You don’t want to create these things every time a new client connects. You want them created **once** at startup and cleaned up **once** at shutdown. That’s exactly what `@lifespan` does.

---

### Step-by-step explanation

#### 1. Import the decorator

```python
from fastmcp import FastMCP
from fastmcp.server.lifespan import lifespan
```

#### 2. Write an async generator function and decorate it

```python
@lifespan
async def app_lifespan(server):
    # ---------- SETUP (runs once when server starts) ----------
    print("Starting up...")
    
    # Create shared resources here
    db = await connect_to_database()
    cache = await connect_to_cache()
    
    try:
        # Yield a dictionary → this becomes the "lifespan context"
        yield {
            "db": db,
            "cache": cache,
            "started_at": "2024-01-01"
        }
    finally:
        # ---------- TEARDOWN (runs when server stops) ----------
        print("Shutting down...")
        await db.close()
        await cache.close()
```

**Key points:**
- The function must be an **async generator** (it uses `yield`).
- Everything **before** `yield` = startup code.
- The value you `yield` (usually a `dict`) becomes available to all your tools.
- Everything **after** `yield` (or in a `finally` block) = cleanup code.
- Always use `try/finally` so cleanup still runs even if the server is cancelled or crashes.

#### 3. Pass it to the FastMCP server

```python
mcp = FastMCP("MyServer", lifespan=app_lifespan)
```

#### 4. Use the lifespan context inside your tools

```python
from fastmcp import Context

@mcp.tool
def list_users(ctx: Context) -> list[str]:
    # Access the shared data you yielded earlier
    data = ctx.lifespan_context["db"]   # or whatever key you used
    return data.query("SELECT name FROM users")
```

You can also access it via `ctx.lifespan_context["cache"]`, etc.

---

### Composing multiple lifespans (very useful!)

You can combine several independent lifespans with the `|` operator:

```python
@lifespan
async def config_lifespan(server):
    config = {"debug": True, "version": "1.0"}
    yield {"config": config}

@lifespan
async def data_lifespan(server):
    data = {"items": []}
    yield {"data": data}

@lifespan
async def db_lifespan(server):
    conn = await connect_db()
    try:
        yield {"db": conn}
    finally:
        await conn.close()

# Combine them
mcp = FastMCP(
    "MyServer",
    lifespan=config_lifespan | data_lifespan | db_lifespan
)
```

**How composition works:**
- They start in **left-to-right** order.
- They stop in **right-to-left** order (LIFO — last in, first out).
- All the dictionaries are merged into one big `ctx.lifespan_context`.

---

### Working with older `@asynccontextmanager` style

If you already have a classic FastAPI-style lifespan, you can wrap it:

```python
from contextlib import asynccontextmanager
from fastmcp.server.lifespan import lifespan, ContextManagerLifespan

@asynccontextmanager
async def legacy_lifespan(server):
    # old style code...
    yield {"legacy": True}

@lifespan
async def new_lifespan(server):
    yield {"new": True}

combined = ContextManagerLifespan(legacy_lifespan) | new_lifespan
mcp = FastMCP("MyServer", lifespan=combined)
```

---

### Important mental model

| Concept              | When it runs                  | Good for                          |
|----------------------|-------------------------------|-----------------------------------|
| `@lifespan`          | Once per server process       | DB pools, caches, global clients  |
| Tool / resource code | Every time a client calls it  | Actual business logic             |
| Session state        | Per client connection         | Conversation history, cart, etc.  |

---

### Quick complete example

```python
from fastmcp import FastMCP, Context
from fastmcp.server.lifespan import lifespan

@lifespan
async def app_lifespan(server):
    print("🚀 Server starting...")
    users = {"alice": 1, "bob": 2}          # shared in-memory data
    try:
        yield {"users": users}
    finally:
        print("👋 Server shutting down...")

mcp = FastMCP("UserServer", lifespan=app_lifespan)

@mcp.tool
def get_user_id(name: str, ctx: Context) -> int:
    users = ctx.lifespan_context["users"]
    return users.get(name, -1)

if __name__ == "__main__":
    mcp.run()
```

That’s it!  

`@lifespan` is FastMCP’s clean, modern, composable way to handle server startup and shutdown logic — similar in spirit to FastAPI’s lifespan, but designed specifically for MCP servers and made easy to combine.
