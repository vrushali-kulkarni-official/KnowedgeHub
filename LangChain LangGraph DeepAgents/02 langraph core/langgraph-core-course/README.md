# Phase 7 — LangGraph Core

A hands-on course that takes you from *"what even is a graph?"* to shipping a
real, persistent, observable LangGraph application.

**Every claim in these lessons was verified by running it** against
`langgraph 1.2.17` / `langchain 1.4.7` on 2026-10-26. Where the behaviour
is surprising, the lesson says so and shows the measurement.

---

## Who this is for

You already know Python, `uv`, Pydantic, and you have built agents with
`create_agent` (Phase 6), RAG (Phase 4), and tools/MCP (Phase 5).

This phase takes the lid off `create_agent` and shows you the graph it has
been running for you all along.

---

## Setup

```bash
cd langgraph-core-course

# with uv (recommended)
uv venv --python 3.11
uv pip install -e ".[dev,sqlite]"

# or plain pip
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,sqlite]"
```

Copy the env template and (optionally) add a Gemini key:

```bash
cp .env.example .env
# edit .env -> GOOGLE_API_KEY=...
```

> **You do not need an API key to do this course.** Every example falls back
> to a deterministic offline model when `GOOGLE_API_KEY` is absent, so you can
> run, debug and understand every single concept with zero cost. Add the key
> when you want to see real LLM behaviour.

The model layer lives in `src/lgc/llm.py`:

| Backend | When | Model |
|---|---|---|
| **Gemini** | `GOOGLE_API_KEY` is set | `gemini-3.8-flash` (GA, Oct 2026) |
| **Offline** | no key | a deterministic `BaseChatModel` stand-in |

---

## Run everything

```bash
for f in examples/L*.py; do
  echo "=========== $f ==========="
  python "$f"
done
```

Or one at a time:

```bash
python examples/L04_reducers.py
```

---

## The lessons, in the order that actually teaches

| # | Lesson | Module | Time | What you can do after it |
|---|---|---|---|---|
| 01 | [Graph thinking](lessons/L01-graph-thinking.md) | M48a | 2h | Decide between an agent loop and an explicit graph |
| 02 | [Your first StateGraph](lessons/L02-first-graph.md) | M48b | 3h | Build, run and *see* a graph |
| 03 | [State & schema types](lessons/L03-state-schemas.md) | M49a | 2.5h | Design a state schema you will still like in 6 months |
| 04 | [Reducers](lessons/L04-reducers.md) | M49b | 3h | Never silently lose a message again |
| 05 | [Routing & `Command`](lessons/L05-routing-and-command.md) | M48c | 2.5h | Control exactly where a run goes next |
| 06 | [Config, threads, persistence](lessons/L06-config-threads-persistence.md) | M50a | 3h | Make a graph stateful; rewind it |
| 07 | [Runtime context](lessons/L07-runtime-context.md) | M50b | 2h | Pass app values in cleanly (and stop using `configurable`) |
| 08 | [Parallelism & `Send`](lessons/L08-parallel-and-send.md) | M51a | 2.5h | Build map-reduce pipelines that actually run in parallel |
| 09 | [Async & streaming](lessons/L09-async-and-streaming.md) | M51b | 2.5h | Get real concurrency; stream to a UI |
| 10 | [The Functional API](lessons/L10-functional-api.md) | M52 | 2h | Wrap existing code without rewriting it |
| 11 | [Subgraphs](lessons/L11-subgraphs.md) | M50c | 2.5h | Compose graphs and map state between them |
| 12 | [Fault tolerance](lessons/L12-fault-tolerance.md) | M51c | 1.5h | Survive flaky APIs without double-charging anyone |
| 13 | [`langgraph dev` & Studio](lessons/L13-dev-and-studio.md) | M53 | 1h | Debug a graph visually instead of guessing |
| 14 | [Capstone](lessons/L14-capstone.md) | — | 3h | Everything, combined into one real pipeline |
| — | [Cheat sheet](CHEATSHEET.md) | — | — | Current vs deprecated, API quick reference |

### Why this order, and not M48 → M53

| Change | Why |
|---|---|
| **Routing (L05) moved after reducers (L04)** | `Command(update=...)` writes to state. Routing without reducers is routing with a footgun. |
| **Context (L07) moved after config (L06)** | Context *is* the modern answer to a config question. You need the old thing first. |
| **Parallelism (L08) moved after reducers (L04)** | Fan-in without a reducer is an `InvalidUpdateError`. L04 is the prerequisite. |
| **Subgraphs (L11) moved after parallel/async (L08–L09)** | You need the superstep model to reason about namespaces and joins. |
| **Fault tolerance (L12) before Studio (L13)** | So you can debug real failures in Studio, not just happy paths. |
| **L12–L14 are new** | Retries/timeouts/caching and a capstone are not optional for real work. |

---

## The one-paragraph summary

A LangGraph graph is a **state machine whose state is a dict, whose steps are
Python functions, and whose transitions are edges**. State is not one dict —
it is a set of independent **channels**, each with its own **reducer** that
decides how a node's write merges in. The graph runs in **supersteps**: every
node scheduled for a step runs (in parallel), then a checkpoint is written.
That single idea — channels, reducers, supersteps — explains every
surprising behaviour in this course.

---

## Project layout

```
langgraph-core-course/
├── README.md                 <- you are here
├── ROADMAP.md                <- progress tracker
├── CHEATSHEET.md             <- current vs deprecated + API reference
├── pyproject.toml
├── langgraph.json            <- the Agent Server config (L13)
├── .env.example
├── src/lgc/                  <- course helpers
│   ├── llm.py                <- Gemini + offline fallback
│   ├── context.py            <- the AppContext dataclass
│   └── printing.py           <- pretty output
├── graphs/research.py        <- the capstone graph (also served by `langgraph dev`)
├── lessons/L01..L14.md       <- the course
└── examples/L01..L14.py      <- runnable, verified code for every lesson
```

---

## A note on versions

Everything here targets the **current** release line, verified 2026-10-26:

| Package | Version |
|---|---|
| `langgraph` | 1.2.17 |
| `langchain` | 1.4.7 |
| `langchain-core` | 1.7.0 |
| `langchain-google-genai` | 4.4.2 |
| `langfuse` | 5.0.4 |
| `langgraph-cli` | 0.4.38 |
| `langgraph-sdk` | 0.4.9 |

The [cheat sheet](CHEATSHEET.md) lists everything that was **deprecated** and
what replaced it. Short version: `config_schema` → `context_schema`,
`MemorySaver` → `InMemorySaver`, `langgraph.prebuilt.create_agent` →
`langchain.agents.create_agent`, `langchain_core.messages.add_messages` →
`langgraph.graph.message.add_messages`, "LangGraph Studio" → "LangSmith
Studio".

---

## Free & open source

Everything in this course works with zero paid services:

- **LangGraph** — MIT, the whole runtime.
- **Gemini Developer API** — generous free tier.
- **Langfuse** — MIT, self-hostable, tracing + evals (you are learning it anyway).
- **Phoenix** (Arize, Apache 2.0) or **MLflow** — alternative tracers.
- **LangSmith Studio** — free tier, hosted visual debugger. The *runtime* it
  debugs is entirely open source; only the UI is hosted.
