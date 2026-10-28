**FastMCP with FastAPI** means running your MCP server over **HTTP** (instead of stdio) and integrating it with a FastAPI web app.  

You already know the stdio way (`mcp.run()` → local process that Claude Desktop / Cursor talks to via stdin/stdout).  
With FastAPI you get a real web server that multiple clients can connect to over the network.

There are **two main ways** to combine them:

1. **Generate an MCP server FROM an existing FastAPI app**  
   (turn your REST endpoints into MCP tools automatically)
2. **Mount an MCP server INTO a FastAPI app**  
   (add MCP tools/resources next to your normal API routes)

---

### Prerequisites

```bash
pip install fastmcp fastapi uvicorn
# or
uv add fastmcp fastapi uvicorn
```

FastMCP does **not** install FastAPI for you — you need both.

---

### Way 1: Convert existing FastAPI endpoints → MCP tools

This is the most common and powerful pattern.

#### Step 1: Write a normal FastAPI app

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

class Product(BaseModel):
    name: str
    price: float
    category: str
    description: str | None = None

class ProductResponse(BaseModel):
    id: int
    name: str
    price: float
    category: str
    description: str | None = None

app = FastAPI(title="E-commerce API")

products_db = {
    1: ProductResponse(id=1, name="Laptop", price=999.99, category="Electronics"),
    2: ProductResponse(id=2, name="Mouse", price=29.99, category="Electronics"),
}

@app.get("/products")
def list_products(category: str | None = None, max_price: float | None = None):
    """List products with optional filters."""
    products = list(products_db.values())
    if category:
        products = [p for p in products if p.category == category]
    if max_price:
        products = [p for p in products if p.price <= max_price]
    return products

@app.get("/products/{product_id}")
def get_product(product_id: int):
    if product_id not in products_db:
        raise HTTPException(404, "Product not found")
    return products_db[product_id]

@app.post("/products")
def create_product(product: Product):
    new_id = max(products_db.keys()) + 1
    products_db[new_id] = ProductResponse(id=new_id, **product.model_dump())
    return products_db[new_id]
```

#### Step 2: Convert it to an MCP server (one line!)

```python
from fastmcp import FastMCP

mcp = FastMCP.from_fastapi(app=app)

if __name__ == "__main__":
    mcp.run()          # still works with stdio
    # or
    # mcp.run(transport="http", host="0.0.0.0", port=8000)
```

That’s it. FastMCP reads the OpenAPI schema of your FastAPI app and automatically creates MCP tools for every endpoint.

Tool names are generated from the route + method, for example:
- `list_products_products_get`
- `get_product_products__product_id__get`
- `create_product_products_post`

#### Step 3 (optional): Add extra tools or resources

```python
mcp = FastMCP.from_fastapi(app=app)

@mcp.tool
def get_expensive_products(min_price: float = 500) -> list:
    """Return products above a certain price."""
    return [p for p in products_db.values() if p.price >= min_price]
```

#### Step 4: Run it over HTTP

```python
if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)
```

Your MCP endpoint is now at:  
`http://localhost:8000/mcp`

Clients (Claude Desktop, Cursor, your own code, etc.) connect to this URL instead of launching a local process.

---

### Way 2: Mount a pure MCP server inside a FastAPI app

Use this when you want **both**:
- Normal REST API for humans / other services
- MCP tools for AI agents

on the **same port**.

```python
from fastapi import FastAPI
from fastmcp import FastMCP

# 1. Create your MCP server (exactly like you already know)
mcp = FastMCP("My Analytics Tools")

@mcp.tool
def analyze_pricing(category: str) -> dict:
    """Calculate average, min, max price for a category."""
    # your logic here
    return {"avg": 150.0, "min": 20, "max": 999}

# 2. Turn the MCP server into an ASGI app
mcp_app = mcp.http_app(path="/mcp")   # the path inside the mount

# 3. Create FastAPI and pass the lifespan (VERY IMPORTANT)
app = FastAPI(title="My App", lifespan=mcp_app.lifespan)

# 4. Mount it
app.mount("/tools", mcp_app)

# Now you also have normal FastAPI routes
@app.get("/health")
def health():
    return {"status": "ok"}
```

Run it the usual FastAPI way:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Endpoints become:
- REST health check → `http://localhost:8000/health`
- MCP endpoint → `http://localhost:8000/tools/mcp`

**Critical rule**: Always pass `lifespan=mcp_app.lifespan` (or combine lifespans).  
If you forget this, the MCP session manager never starts and tools fail.

---

### Best of both worlds (recommended production pattern)

Generate MCP tools from your existing API **and** serve both on the same FastAPI app:

```python
from fastmcp import FastMCP
from fastapi import FastAPI

# Assume `app` is your existing FastAPI application

mcp = FastMCP.from_fastapi(app=app, name="E-commerce MCP")
mcp_app = mcp.http_app(path="/mcp")

combined = FastAPI(
    title="API + MCP",
    routes=[*mcp_app.routes, *app.routes],
    lifespan=mcp_app.lifespan,
)
```

Now you have:
- Normal REST → `http://localhost:8000/products`
- LLM-friendly MCP → `http://localhost:8000/mcp`

Same code, same database, same business logic — just two different interfaces.

---

### How clients connect

**Claude Desktop / Cursor config** (example):

```json
{
  "mcpServers": {
    "my-api": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

Or with the FastMCP client in Python:

```python
from fastmcp import Client
import asyncio

async def main():
    async with Client("http://localhost:8000/mcp") as client:
        tools = await client.list_tools()
        print([t.name for t in tools])
        
        result = await client.call_tool("list_products_products_get", {"category": "Electronics"})
        print(result.data)

asyncio.run(main())
```

---

### Important tips & gotchas

| Topic | Advice |
|-------|--------|
| **Lifespan** | Always pass `lifespan=mcp_app.lifespan` when mounting. Nested lifespans are ignored. |
| **Tool names** | Give meaningful `operation_id` in FastAPI routes if you want nicer tool names. |
| **Auth** | You can pass headers via `httpx_client_kwargs` when using `from_fastapi`. For mounting, use normal FastAPI middleware / dependencies. |
| **CORS** | Be careful with global CORS middleware when using OAuth-protected MCP — it can break `.well-known` routes. Prefer mounting sub-apps. |
| **Hot reload** | `uvicorn --reload` sometimes has issues with MCP session managers. Prefer restarting the process in production. |
| **Transport** | Prefer `transport="http"` (Streamable HTTP). SSE is legacy. |

---

### Summary – when to use what

| Goal | Approach |
|------|----------|
| You already have a FastAPI API and want AI agents to use it | `FastMCP.from_fastapi(app)` |
| You want pure MCP tools + normal REST on same port | Create `FastMCP` → `http_app()` → mount into FastAPI |
| Production (same codebase for both humans and agents) | Generate MCP from FastAPI + mount both together |

That’s the complete picture of FastMCP + FastAPI.  
You keep writing normal Python functions / FastAPI routes, and FastMCP turns them into a proper MCP server that speaks HTTP.
