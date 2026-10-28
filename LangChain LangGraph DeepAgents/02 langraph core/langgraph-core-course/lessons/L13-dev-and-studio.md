# L13 · `langgraph dev` and LangSmith Studio

> **Module M53 · ~1h**
> Goal: run a local Agent Server, drive your graph from a visual debugger, and
> replay a run from any step.

---

## 1. First, the renaming — this trips up every tutorial

The product around LangGraph was renamed in late 2025. Older tutorials, blog
posts and courses use the old names.

| Old name | Current name | What it is |
|---|---|---|
| **LangGraph Studio** | **LangSmith Studio** | the visual IDE for building/debugging agents |
| **LangGraph Platform** | **LangSmith Deployment** | the managed runtime for shipping agents |
| LangGraph API server | **Agent Server** | the process that serves threads, runs, assistants, store, cron |
| `langgraph dev` | `langgraph dev` | **unchanged** — the CLI kept its name |
| `langgraph up` | `langgraph up` | unchanged — local Docker-based server |

The current documentation lives at `docs.langchain.com` and uses the new
names. If a tutorial says "LangGraph Studio", it predates the rename (or is
using the old name loosely) — the product is the same one.

**Requirements:** Studio is a **hosted web UI** at
`https://smith.langchain.com/studio/`. It needs a **free LangSmith
account**. It is not something you install locally — the local part is the
Agent Server, and the Studio UI connects to it over HTTP.

---

## 2. `langgraph dev` — the local Agent Server

```bash
pip install -U "langgraph-cli[inmem]"
langgraph dev
```

Output (verified flags, from `langgraph dev --help` in v0.4.38):

```
- API: http://127.0.0.1:2024
- 🎨 Studio UI: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024
- 📚 API Docs: http://127.0.0.1:2024/docs
This in-memory server is designed for development and testing.
For production use, please use LangSmith Deployment.
```

### What it gives you

| Feature | Detail |
|---|---|
| No Docker | runs in your own Python environment |
| Hot reload | edit a file, the server reloads it |
| In-memory state | persisted to a local `.langgraph_api/` directory |
| Debug Adapter Protocol | attach a real IDE debugger with breakpoints |
| OpenAPI docs | `http://127.0.0.1:2024/docs` |
| MCP + A2A endpoints | the server can expose itself as an MCP server |

### The flags worth knowing

| Flag | Why you want it |
|---|---|
| `--no-browser` | don't auto-open Studio (headless servers, CI) |
| `--port 8000` | change the port (default `2024`) |
| `--host 0.0.0.0` | expose on the network — **only on a trusted network**, the dev server has no auth |
| `--tunnel` | a Cloudflare tunnel to your local server — needed for **Safari**, which blocks `localhost` XHR |
| `--no-reload` | disable hot reload |
| `--debug-port 5678` | enable `debugpy` remote debugging (needs `debugpy` installed) |
| `--config path.json` | use a different config file |
| `--allow-blocking` | don't error on blocking I/O in async code |

> **Safari note (real):** Safari refuses to make cross-origin requests to
> `localhost`. If Studio cannot connect, run `langgraph dev --tunnel` and
> add the tunnel URL as an allowed origin in the Studio UI
> ("Connect to a local server").

---

## 3. `langgraph dev` vs `langgraph up`

| | `langgraph dev` | `langgraph up` |
|---|---|---|
| Docker | **not required** | required |
| Install | `langgraph-cli[inmem]` | `langgraph-cli` |
| State | in-memory, pickled locally | PostgreSQL |
| Redis | no | yes |
| Hot reload | yes (default) | optional (`--watch`) |
| Default port | `2024` | `8123` |
| Use for | daily development | production-like validation before release |

**Workflow:** `langgraph dev` while you write → `langgraph up` before a
release → `langgraph deploy` to ship.

---

## 4. `langgraph.json` — the config file

`langgraph dev` reads `langgraph.json` from the project root. The schema
(verified against `langgraph-cli` 0.4.38):

```json
{
  "python_version": "3.11",
  "dependencies": ["."],
  "graphs": {
    "support": "./graphs/support.py:graph",
    "research": "./graphs/research.py:graph"
  },
  "env": ".env",
  "store": null,
  "checkpointer": null,
  "auth": null
}
```

| Key | Meaning |
|---|---|
| `python_version` | the Python version for the runtime |
| `dependencies` | local paths to install (`"."` = this project) |
| `graphs` | map of graph id → `"path/to/file.py:variable"` |
| `env` | a `.env` file path (or an inline dict) |
| `store` | store config (`ttl`, `index` for semantic search) |
| `checkpointer` | checkpointer config (`ttl`, `serde`) |
| `auth` | auth config |
| `http` | HTTP server config (disable routes, custom Starlette app) |
| `webhooks` | webhook config |

The graph value is `"<module path>:<variable>"` — the variable must be a
**compiled** graph object.

```python
# graphs/support.py
from langgraph.graph import StateGraph, START, END
...

graph = builder.compile()      # <- this exact name
```

### Graph definitions can also be objects

```json
"graphs": {
  "support": {
    "path": "./graphs/support.py:graph",
    "description": "Ticket triage pipeline",
    "mcp_mount_path": "/support"
  }
}
```

The `description` is what an LLM-based router reads to decide which graph to
use — relevant for Phase 9 (multi-agent routing).

---

## 5. Using Studio — the actual workflow

1. `langgraph dev` (with a free LangSmith account signed in).
2. The Studio UI opens, pointed at `http://127.0.0.1:2024`.
3. You see your graph rendered as a diagram, with the real topology — not
   your guess at it.
4. You run a thread. Studio shows:
   - every **node** and its input/output,
   - the **state after each superstep**,
   - the **messages** exchanged,
   - tool calls and their results,
   - token counts and latency.
5. You can **edit a node's output** and re-run from that point.
6. You can **replay** from any checkpoint.

### Replay from a step

Select a node in the graph's timeline, edit the state, and Studio re-runs
the graph from that superstep with your edit. This is the interactive
counterpart to the programmatic time travel in L06.

### Why this is worth the setup

| Problem | Without Studio | With Studio |
|---|---|---|
| "Which node ate my data?" | print statements, guess | click the node, read the state |
| "Why did it take that branch?" | read the code, re-read the code | hover the branch, see the router's output |
| "What did the model actually see?" | reconstruct the prompt by hand | the exact messages, as sent |
| "Can I try a different answer?" | edit code, restart | edit the state, replay |

> **The habit to build:** from L13 onwards, keep the Agent Server running
> while you build every subsequent module. The cost is one terminal; the
> payoff is that you *see* your graph instead of inferring it.

---

## 6. Talking to the server without the UI

The Agent Server exposes a REST API. OpenAPI docs at
`http://127.0.0.1:2024/docs`.

```python
from langgraph_sdk import get_sync_client

client = get_sync_client(url="http://127.0.0.1:2024")
thread = client.threads.create()
run = client.runs.wait(
    thread_id=thread["thread_id"],
    assistant_id="support",
    input={"ticket": "how do I reset my password"},
)
print(run)
```

The SDK (`langgraph-sdk` 0.4.9) also lets you create assistants with
different configs, list threads, and inspect state — everything Studio does,
programmatically. Useful for tests.

---

## 7. Open-source alternatives

You said you prefer free and open source. Good news:

| Tool | License | What it gives you |
|---|---|---|
| **LangGraph + Agent Server** | MIT | the whole graph runtime, free forever |
| **LangSmith Studio** | free tier, hosted | the visual debugger (free account, cloud) |
| **Langfuse** | MIT (self-hostable) | tracing, evals, prompt management — **you are already learning this** |
| **Phoenix** (Arize) | Apache 2.0 | self-hosted LLM tracing + evals |
| **MLflow** | Apache 2.0 | experiment tracking + tracing |

The **graph runtime itself is fully open source** (MIT). The paid parts are
the *hosted* platform features: managed deployment, scaled execution, and
enterprise auth.

### Wiring Langfuse into LangGraph

This is a five-line integration, and it uses only public, stable LangChain
callbacks — no LangGraph internals:

```python
from langfuse.langchain import CallbackHandler
import langfuse

langfuse.init()
handler = CallbackHandler()

graph.invoke(input, config={"callbacks": [handler]})
```

Because LangGraph runs on the LangChain Runnable protocol, **every LangChain
callback works** — Langfuse, LangSmith, Phoenix, MLflow, or your own. This
is the payoff of building on a Runnable-based runtime.

> Note the SDK versions in play: **langfuse 5.0.4** (MIT client; the hosted
> Langfuse Cloud has a free tier and self-hosting is free). The v2-era
> `langfuse.callback` import is gone — it is `langfuse.langchain` now.

---

## 8. A minimal working setup for this course

```
langgraph-core-course/
├── langgraph.json
├── .env
├── graphs/
│   └── support.py        # exports `graph`
└── src/lgc/...
```

`langgraph.json`:

```json
{
  "python_version": "3.11",
  "dependencies": ["."],
  "graphs": { "support": "./graphs/support.py:graph" },
  "env": ".env"
}
```

`graphs/support.py`:

```python
from typing_extensions import TypedDict
from langgraph.graph import END, START, StateGraph

class State(TypedDict):
    ticket: str
    reply: str

def reply_node(state: State) -> dict:
    return {"reply": f"We received: {state['ticket']}"}

builder = StateGraph(State)
builder.add_node("reply_node", reply_node)
builder.add_edge(START, "reply_node")
builder.add_edge("reply_node", END)
graph = builder.compile()
```

Then:

```bash
langgraph dev
```

---

## 9. Checkpoint

- [ ] I know the current product names: **LangSmith Studio**,
      **LangSmith Deployment**, **Agent Server**, and that the CLI is still
      `langgraph`.
- [ ] I know Studio needs a free LangSmith account and lives in the browser.
- [ ] I can install the CLI and run `langgraph dev`, and I know the URL it
      prints.
- [ ] I can write a `langgraph.json` and understand every key in it.
- [ ] I know `dev` vs `up` and when to use each.
- [ ] I know how to replay from a step in Studio, and how to do the same
      thing programmatically.
- [ ] I know Langfuse hooks in via plain LangChain callbacks.

---

**Next → [L14 · Capstone: a research-and-report pipeline](./L14-capstone.md)** —
everything from this phase, combined into one real graph.
