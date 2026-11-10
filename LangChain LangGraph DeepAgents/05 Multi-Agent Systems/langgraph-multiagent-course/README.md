# Phase 10 — Multi-Agent Systems (LangChain / LangGraph)

A complete, **runnable** course on building multi-agent systems with the
current LangChain v1 + LangGraph v1 APIs.

Everything in this course was **verified by running it** against the real
packages — not written from memory. Every non-obvious behaviour is
reproduced in a runnable example with its exact error message.

---

## What you will learn

| # | lesson | module |
|---|---|---|
| L01 | [Should You Even Use Multiple Agents?](lessons/L01_decision_framework.md) | M66 |
| L02 | [The Communication Substrate: State, Messages, Artifacts](lessons/L02_communication_substrate.md) | M66 |
| L03 | [The Routing Primitives: `Command` and `Send`](lessons/L03_routing_primitives.md) | M66 |
| L04 | [Agents-as-Tools: The Modern Supervisor](lessons/L04_agents_as_tools.md) | M67 |
| L05 | [Hand-Built Supervisors and the Handoff Brief](lessons/L05_handbuilt_supervisor.md) | M67 |
| L06 | [Handoffs and Swarms, Built the Modern Way](lessons/L06_handoffs_and_swarms.md) | M68 |
| L07 | [Hierarchical Teams](lessons/L07_hierarchical_teams.md) | M69 |
| L08 | [Shared State Design at Scale](lessons/L08_shared_state_design.md) | M69 |
| L09 | [Parallel Agents and Aggregation](lessons/L09_parallel_and_aggregation.md) | M70 |
| L10 | [Budgets, Limits and Failure Modes](lessons/L10_budgets_and_failure_modes.md) | M70 |
| L11 | [Observability: Langfuse Trees and Streaming Debug](lessons/L11_observability.md) | M70 |
| L12 | [The Capstone and the Production Checklist](lessons/L12_capstone_and_checklist.md) | M70 |

The original module order was M66 → M70. It is **reordered** here for
pedagogy: you learn the *substrate* (state, messages, artifacts) and the
*primitives* (`Command`, `Send`) before the *patterns* that use them, and
you learn the *patterns* before the *operational* concerns (budgets,
observability). Every original module is covered; nothing was dropped.

---

## Setup

```bash
cd langgraph-multiagent-course

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # or: uv pip install -r requirements.txt

# run everything (offline, no API key needed)
python tests/run_all.py

# run one example
PYTHONPATH=examples python examples/ex17_capstone.py
```

Requires Python ≥ 3.10.

---

## The offline harness — why this course is testable

Multi-agent examples usually only work when a real LLM happens to pick the
right tool. That makes them impossible to debug, impossible to unit-test,
and impossible to read.

This course replaces the model with a deterministic `ScriptedChatModel`
(`examples/_common.py`) that plays back pre-baked messages and **records
every invocation**. So you can assert exactly which agent ran, what the
model saw, and what state each one received.

Swapping in Gemini is four lines:

```python
from langchain.chat_models import init_chat_model
model = init_chat_model("google_genai:gemini-3.8-flash")
```

---

## Verified versions (2026-11-05)

| package | version | status |
|---|---|---|
| `langgraph` | 1.2.20 | current |
| `langchain` | 1.4.9 | current |
| `langchain-core` | 1.7.6 | current |
| `langgraph-prebuilt` | 1.1.1 | current |
| `langfuse` | 5.1.0 | current (MIT) |
| `langchain-google-genai` | 4.4.3 | current |
| `google-genai` | 2.34.0 | current |
| `deepagents` | 0.7.32 | current (for Phase 11) |
| `langgraph-supervisor` | 0.0.31 | **stale** (2025-11-19) — do not use |
| `langgraph-swarm` | 0.1.0 | **stale** (2025-12-04) — do not use |

### The current Gemini model line (verified 2026-11-05)

| model ID | stage | context | max output | $/1M in / out |
|---|---|---|---|---|
| `gemini-4-argon` | Stable | 1,048,576 | 65,536 | $2 / $10 (intro) |
| `gemini-3.8-flash` | Stable | 1,048,576 | 65,536 | $0.75 / $3.75 (intro) |
| `gemini-3.6-flash` | Stable | 1,048,576 | 65,536 | $0.75 / $3.75 |
| `gemini-3.5-flash-lite` | Stable | 1,048,576 | 65,536 | $0.30 / $2.50 |

Retired / auto-routed: `gemini-2.5-pro`, `gemini-2.5-flash`,
`gemini-2.5-flash-lite`, `gemini-3.5-flash`, `gemini-3.7-flash`.

See [CHEATSHEET.md](CHEATSHEET.md) for the full current-vs-deprecated table.

---

## What makes this course different

Every one of these was **measured**, not asserted:

| behaviour | how it was verified |
|---|---|
| `Command(goto=)` from inside `create_agent` silently does nothing | reproduced with its exact log line (ex05) |
| `Command(update=...)` from a tool must contain a matching `ToolMessage` | reproduced with its `ValueError` (ex05) |
| `Command(graph=Command.PARENT, goto=...)` **does** navigate the parent | working handoff (ex09) |
| `create_agent` defaults to `recursion_limit = 9999` | read from the source (ex05, ex14) |
| a `Send` payload **bypasses** `input_schema` | measured (ex04) |
| `Command.PARENT` updates are filtered by the parent schema, silently | measured (ex04) |
| an agent **echoes its state back**, duplicating append-reducer lists | measured (ex09) |
| `InjectedState` needs the key in the agent's `state_schema` | reproduced with `KeyError` (ex09) |
| a node with both `Command(goto=)` and a routing edge double-dispatches | reproduced with `InvalidUpdateError` (ex09) |
| `add_conditional_edges` resolves the branch function's type hints | reproduced with `NameError` (ex07) |
| structured output silently **retries forever** if the model ignores the schema | reproduced with `GraphRecursionError` (ex07) |
| `ToolInvocationError` is recoverable; other tool errors **crash the graph** | both reproduced (ex14) |
| parallel fan-out gives a **~3.9x** speed-up | measured (ex12; 3.83-3.87x across runs) |
| Langfuse produces a real nested agent trace tree | captured offline with an in-memory OTel exporter (ex15) |

---

## Directory layout

```
langgraph-multiagent-course/
├── README.md
├── ROADMAP.md
├── CHEATSHEET.md          current vs deprecated, all the verified gotchas
├── requirements.txt
├── lessons/               L01 .. L12
├── examples/              ex01 .. ex18 + _common.py (the offline harness)
└── tests/
    ├── run_all.py         runs every example, asserts output markers
    └── validate.py        links, syntax, deprecation-string checks
```

---

## The 18 examples

| example | topic |
|---|---|
| ex01 | single agent vs supervisor team, measured |
| ex02 | the four topologies, all runnable |
| ex03 | shared state vs messages vs artifacts |
| ex04 | the four state-filtering rules |
| ex05 | `Command`, `Send`, and the four traps |
| ex06 | agents-as-tools (the modern supervisor) |
| ex07 | structured-output routing |
| ex08 | hand-built supervisor + handoff briefs |
| ex09 | handoffs and swarms, with a loop guard |
| ex10 | hierarchical teams, progress, escalation |
| ex11 | shared state design, the store, summarisation |
| ex12 | parallel fan-out, measured speed-up |
| ex13 | vote / judge / hybrid aggregation |
| ex14 | budgets, limits, the five failure modes |
| ex15 | Langfuse trace trees (offline) |
| ex16 | streaming debugging playbook |
| ex17 | **capstone**: a production-shaped team |
| ex18 | the same system with real Gemini |

---

## Philosophy

1. **Measure, do not assert.** If a lesson says "parallelism is faster", the
   example prints the speed-up.
2. **Reproduce the bug.** Every trap is reproduced with its real error
   message, so you recognise it in the wild.
3. **One source of truth per decision.** Routing decisions, budgets and
   progress all have exactly one writer.
4. **The boring parts matter most.** State schemas, reducers and briefs are
   where multi-agent systems actually fail.

---

## Free and open source

Everything here runs on free, open-source software:

* **LangChain / LangGraph** — MIT
* **Langfuse** — MIT (self-hostable with Docker)
* **Gemini** — free tier is enough for this whole course
* **Postgres + pgvector** — for the persistence phase

No paid framework, no proprietary agent platform, no vendor lock-in.
