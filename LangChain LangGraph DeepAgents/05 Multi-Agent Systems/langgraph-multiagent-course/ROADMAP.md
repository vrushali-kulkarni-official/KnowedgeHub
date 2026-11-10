# ROADMAP — Phase 10 (Multi-Agent Systems)

Where this course sits in the larger track, and where to go next.

---

## Where you are

```
Phase 0   Orientation & LLM Mental Models
Phase 1   Models & Prompts
Phase 2   Ingestion
Phase 3   Embeddings & Vector Stores
Phase 4   RAG
Phase 5   Tools & MCP
Phase 6   Agents with create_agent
Phase 7   LangGraph Core
Phase 8   Persistence, Memory & Human-in-the-Loop
Phase 9   Production LangGraph
Phase 10  Multi-Agent Systems      <-- YOU ARE HERE
Phase 11  Deep Agents              <-- NEXT
```

Phase 10 assumes you already know: agents, tools, structured output,
middleware, checkpointer/store, interrupts, and graph primitives. It does
not assume you know multi-agent design — that is the whole point.

---

## The study order, and why

The original module order was M66 → M70. This course reorders them.

```
ACT A - DECIDE AND DESIGN            (why, and with what vocabulary)
  L01  decision framework            M66
  L02  communication substrate        M66
  L03  routing primitives            M66

ACT B - BUILD PATTERNS               (the four topologies, in order of
  L04  agents-as-tools / supervisor   complexity)
  L05  hand-built teams
  L06  handoffs & swarms
  L07  hierarchical teams
  L08  shared state design

ACT C - SCALE AND OPERATE            (the concerns that appear when it works)
  L09  parallel agents & aggregation
  L10  budgets & failure modes
  L11  observability
  L12  capstone + checklist
```

**Why this order:**

1. **L01 first**, because the most common mistake is building a multi-agent
   system that should have been one agent. The decision framework is the
   highest-value lesson in the phase.
2. **L02–L03 before any pattern**, because every pattern is built from
   state plumbing and `Command`/`Send`. Learning the supervisor first and
   the substrate later is how you end up with a supervisor you cannot debug.
3. **L04 → L05 → L06 → L07** is increasing complexity: one tool per
   specialist → a shared team state → control that moves → a tree.
4. **L08 after the patterns**, because you cannot design a schema before
   you know what the patterns need to carry.
5. **L09–L11 last**, because they only matter once the system works. A
   budget on a broken design is a waste of your time.

---

## Mapping to the original modules

| original module | covered in | time |
|---|---|---|
| M66 · Multi-agent decision framework | L01, L02, L03 | ~4.5h |
| M67 · Supervisor: by hand + subagents-as-tools | L04, L05 | ~4h |
| M68 · Swarm & handoffs | L06 | ~2.5h |
| M69 · Hierarchical teams & shared state design | L07, L08 | ~4.5h |
| M70 · Parallel agents, aggregation & debugging | L09, L10, L11, L12 | ~9h |

Everything in the original brief is covered, including the three
🔄 "this is stale, use X instead" flags:

* `langgraph-supervisor` → L04 (subagents pattern)
* `langgraph-swarm` → L06 (build handoffs yourself)
* "state filters — what actually transfers" → L02 §2 and L06 §3

---

## Time plan

| day | lessons | hours |
|---|---|---|
| 1 | L01, L02 | 3.0 |
| 2 | L03, L04 | 3.5 |
| 3 | L05, L06 | 4.5 |
| 4 | L07, L08 | 4.5 |
| 5 | L09, L10 | 4.5 |
| 6 | L11, L12 | 4.0 |
| | **total** | **~24h** |

Every lesson has a matching runnable example. The examples ARE the
homework — read the lesson, run the example, change one thing, re-run.

---

## Milestones

### Milestone 1 — you can decide
After L01 you can look at a problem and say whether it needs multiple
agents, and defend the answer with numbers.

### Milestone 2 — you can build
After L04 you can build a supervisor team with the modern pattern and no
deprecated APIs.

### Milestone 3 — you can debug
After L06 you can build a handoff and a swarm, and you know the four traps
and the three loop guards by heart.

### Milestone 4 — you can scale
After L09 you can fan out work in parallel and aggregate the results
without drowning in them.

### Milestone 5 — you can ship
After L12 you have a capstone system, a production checklist, and a trace
you can read.

---

## Phase 11 — Deep Agents (next)

The `deepagents` package (v0.7.32, actively released) builds on LangGraph's
agent runtime and adds:

* a **virtual filesystem** for the agent to read and write
* **task planning** (a todo-list tool)
* **subagent delegation** as a first-class primitive

Everything you learned in Phase 10 is the substrate it assumes:

| Phase 10 | `deepagents` counterpart |
|---|---|
| agents-as-tools (L04) | built-in subagent delegation |
| the store / artifacts (L08) | the virtual filesystem |
| shared state & planning (L05, L08) | the todo-list tool |
| budgets (L10) | the same middleware stack |
| `Command` / `Send` | the same routing primitives |

**Phase 11 prerequisites:** you should be comfortable with `create_agent`,
middleware, the store, and `Command`-based routing. That is exactly what
Phase 10 gives you.

---

## Where to go after that

| direction | what to read |
|---|---|
| durable teams | Phase 8: Postgres checkpointer + `PostgresStore` |
| human-in-the-loop inside a team | Phase 8: `interrupt()` + `HumanInTheLoopMiddleware` |
| deploying a team | Phase 9: `langgraph dev`, the LangGraph SDK, streaming from a server |
| evaluation | `langfuse` datasets + `run_experiment`, or Phoenix (Apache 2.0) |
| retrieval at scale | `langgraph-checkpoint-postgres` + pgvector (Phase 3) |

---

## A note on keeping current

The LangChain ecosystem moves fast. If a lesson contradicts the installed
package, **the package wins** — and the lesson should be fixed. The
quickest check:

```bash
python -c "import langchain, langgraph, importlib.metadata as m; \
print(m.version('langchain'), m.version('langgraph'))"
```

and

```python
import inspect
from langchain.agents import create_agent
print(inspect.signature(create_agent))
```

The CHEATSHEET's current-vs-deprecated table is the fastest way to check
whether an API you have seen online is still alive.
