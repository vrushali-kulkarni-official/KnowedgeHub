# L01 · Graph thinking: when do you actually need a graph?

> **Module M48 (part 1) · ~2h**
> Goal: build the mental model that makes every later API obvious.

---

## 0. Where you are right now

You have already built agents with `create_agent` (Phase 6). That function
already *is* a LangGraph graph — LangChain 1.x compiles a `StateGraph`
underneath it and runs it on the same Pregel runtime you are about to learn.

So you are **not** starting from zero. You already know:

| You know this (Phase 6) | You will learn this (Phase 7) |
|---|---|
| `create_agent(model, tools)` | How to build that graph *by hand* |
| Tools + tool calling | How nodes and edges compose |
| A ReAct loop (think → act → observe) | How that loop is expressed as a cycle |
| Message history | How **state** and **reducers** work underneath |
| `AgentState` | How to design your own state schema |

That last row matters. `create_agent` gave you a *black box* called
`AgentState`. Phase 7 takes the lid off. Everything in this module is about
learning to see the graph that `create_agent` is running for you.

---

## 1. The one-sentence model

> **A LangGraph graph is a state machine whose "state" is a dictionary, whose
> "steps" are Python functions, and whose "transitions" are edges.**

Three nouns. Everything else is detail:

| Concept | In Python | In LangGraph |
|---|---|---|
| The data that flows through | `dict` | **State** |
| A unit of work | `def f(state) -> dict` | **Node** |
| Where to go next | `if/else` | **Edge** |

If you remember nothing else from this module, remember that. `START` and
`END` are just sentinel node names for "begin" and "finish".

---

## 2. Supersteps — the concept nobody explains properly

This is the single most important idea in LangGraph, and it explains
almost every confusing behaviour you will hit.

A graph does not run "node by node". It runs in **supersteps**:

```
superstep 0:  all nodes with an incoming edge from START run (in parallel)
superstep 1:  all nodes whose predecessors finished in superstep 0 run (in parallel)
superstep 2:  ...
```

Rules:

1. **Within a superstep, nodes run in parallel.** They are scheduled
   concurrently (in the async runtime).
2. **A superstep is a barrier.** No node in superstep *N+1* starts until
   *every* node in superstep *N* has finished.
3. **A checkpoint is written at every superstep boundary.** That is what makes
   time-travel and human-in-the-loop possible.
4. `recursion_limit` counts **supersteps**, not nodes.

Concrete example:

```
START ──► A ──► B ──► END
```

runs as two node-supersteps: `A`, then `B`.

```
START ──► A ──► C ──► END
        └──► B ──┘
```

runs as **two** supersteps, not three:

```
superstep 1:  {A}                  (A has an edge from START)
superstep 2:  {B, C}               (both have an edge from A — they run together)
```

This is why "fan-out then fan-in" is a *two*-superstep operation and not four.
It also means **the order in which parallel nodes finish is not defined** — a
fact that bites people in L08 when they write a reducer that assumes order.

> **Verified in `examples/L01_graph_thinking.py`:**
> - Two 0.4s parallel nodes complete in **0.41s** total, not 0.8s. They really
>   do run concurrently.
> - `stream_mode="debug"` labels the two fan-out nodes with the **same**
>   `step` number, while `stream_mode="updates"` emits them as two separate
>   chunks. `updates` counts *nodes*; `debug` counts *supersteps*. Do not
>   confuse the two — this trips up everyone once.
> - `graph.get_state_history()` shows the same thing: one checkpoint whose
>   `.next` is `('B', 'C')` means "B and C are scheduled in the same superstep".

> **Practical consequence:** if a node needs the *result* of another node in
> the same superstep, that is a bug in your graph. It is not a race condition
> you can fix with `sleep`; the data simply is not there yet.

---

## 3. Agent loop vs explicit graph — the actual decision

You have written agent loops. Here is the honest comparison.

### The agent loop (what `create_agent` does)

```
while True:
    llm_response = call_model(messages, tools)
    if llm_response has no tool calls:
        break
    execute tools, append results
```

**Properties**

- Control flow is decided at *runtime* by the LLM.
- The loop shape is fixed by the framework.
- You cannot easily say "after the tool runs, do X, then Y".
- You cannot easily draw the graph, because the graph is static but the path
  through it is not.
- State is fixed by the framework (`AgentState`).

### The explicit graph (what you build in Phase 7)

```
classify ──► question ──► retrieve ──► answer ──► END
                │
                └──► bug ──► create_ticket ──► answer ──► END
```

**Properties**

- *Some* control flow is still decided by the LLM (inside `classify`).
- The **shape** of the workflow is yours and is visible in code.
- You can attach retries, timeouts and fallbacks to *specific* nodes.
- You can visualise it (`draw_mermaid()`), debug it in Studio, and migrate it.
- State is yours to design.

### The decision rule

Use the **agent loop** (`create_agent`) when:

- The only decision is "does the LLM want to call a tool, yes or no?"
- Every step is the same kind of step.
- You are prototyping.

Use an **explicit graph** when *any* of these is true:

1. **Different steps need different treatments.** One step needs a 30s
   timeout, another needs a retry, another must never be cached.
2. **You need a deterministic step before/after the LLM.** "Always validate the
   output against a schema, always log, always filter PII." An agent loop
   gives you no hook for "always".
3. **There are named business states.** `pending_review`, `awaiting_payment`,
   `escalated`. Those belong in state, not hidden inside a message list.
4. **Humans are in the loop at a specific point.** Not "sometimes the agent
   asks", but "after node 3, a human must approve".
5. **You need to see and explain the flow.** To a stakeholder, to a reviewer,
   to yourself in six months.
6. **Different steps use different models.** A cheap classifier, an expensive
   writer, a local model for one branch.
7. **You need parallel fan-out.** "Summarise these 200 documents in parallel,
   then merge."

A very common real pattern is a **hybrid**: an explicit graph whose nodes
include LLM steps and agent steps.

```
validate_input ──► agent(create_agent) ──► validate_output ──► END
```

You get the loop's flexibility inside a graph's explicit frame.

### A quick diagnostic

Ask yourself: *"if the LLM made a different choice, would I need to change
code?"*

- If **no** — the LLM's choice is just data flowing through fixed steps →
  explicit graph.
- If **yes** — the LLM's choice literally picks the code path → agent loop.

---

## 4. Graph API vs Functional API (the other half of the decision)

LangGraph 1.x ships **two** APIs over the *same* runtime. They interoperate.

### Graph API (`StateGraph`) — declarative

```python
from langgraph.graph import StateGraph, START, END

builder = StateGraph(State)
builder.add_node("a", node_a)
builder.add_node("b", node_b)
builder.add_edge(START, "a")
builder.add_edge("a", "b")
builder.add_edge("b", END)
graph = builder.compile()
```

You declare **nodes and edges**. LangGraph owns the control flow.

### Functional API (`@entrypoint` / `@task`) — imperative

```python
from langgraph.func import entrypoint, task

@task
def fetch(url: str) -> str:
    ...

@entrypoint()
def workflow(url: str) -> dict:
    body = fetch(url).result()
    if "error" in body:
        body = recover(body).result()
    return {"body": body}
```

You write **ordinary Python control flow**. LangGraph wraps it so it can be
checkpointed, streamed and interrupted.

### The trade-off

| | Graph API | Functional API |
|---|---|---|
| Control flow | declared via edges | ordinary Python |
| State | explicit schema + reducers | function-scoped, implicit |
| Visualisation | ✅ `draw_mermaid()` | ❌ (graph built at runtime) |
| Boilerplate | schema, nodes, edges | decorator only |
| Best for | branching, parallelism, shared state | wrapping existing code, linear pipelines |

**Use both.** A very common shape: a graph for the orchestration, a functional
workflow for one heavy sub-pipeline, connected with a node that calls it.

```python
from langgraph.func import entrypoint

@entrypoint()
def heavy_pipeline(data: dict) -> dict:
    ...

def node_run_pipeline(state):
    return {"result": heavy_pipeline.invoke(state["data"])}
```

---

## 5. The five-step process (how to actually design a graph)

This is the workflow the LangGraph team documents, and it is genuinely the
right way to start. It comes back in every lesson.

### Step 1 — Map the process into discrete steps

Each step becomes a **node**. A node does *one* thing.

> A node that does three things is three nodes wearing a trenchcoat.

Bad: `def handle(state): classify(); retrieve(); generate(); return {...}`
Good: `classify`, `retrieve`, `generate`.

### Step 2 — Decide what each step needs

For each node, classify it:

| Node type | What it does | Typical failure |
|---|---|---|
| **LLM step** | understand, analyse, generate, decide | rate limits, malformed output |
| **Data step** | fetch from an external source | timeouts, 5xx, auth |
| **Action step** | cause an effect in the world | network, partial writes |
| **User-input step** | wait for a human | (never fails, it *waits*) |

This classification is not academic — it determines your **retry policy**, your
**timeout**, and whether the node is **cacheable**:

- LLM step → retry with backoff, often cacheable
- Data step → retry, often cacheable
- Action step → retry carefully (may double-execute!), never cache
- User-input step → `interrupt()`, not retry

### Step 3 — Design the state

State is the **shared memory** of the graph. The question for every candidate
field:

> **Does this need to survive across steps?**
> - Yes → it belongs in state.
> - No, and it's cheap to recompute → compute it on demand.
> - No, and it's expensive to recompute → state (or a cache).

And a golden rule from the official guide:

> **Keep state raw. Format prompts on-demand.**

Store the *data*, not the formatted prompt string. Otherwise you cannot
re-render the same data for a different consumer, and you are stuck whenever
the template changes.

```python
# BAD - you baked the prompt into state
class State(TypedDict):
    prompt: str          # rendered at write time, frozen forever

# GOOD - store the facts, render inside the node
class State(TypedDict):
    email_content: str  # raw
    classification: dict # raw structured output
```

### Step 4 — Build the nodes

A node is a function:

```python
def my_node(state: State) -> dict:
    ...
    return {"some_key": value}   # a *partial update*, not the whole state
```

Note: nodes return **only the keys they change**. LangGraph merges that
partial update into state using the key's reducer (L04).

### Step 5 — Wire the edges

- `add_edge(START, "a")` — where does it begin?
- `add_edge("a", "b")` — unconditional step
- `add_conditional_edges("a", router)` — decide at runtime
- `add_edge("b", END)` — where does it finish?

---

## 6. Your first design exercise (do this before reading L02)

Take a system you know. Here is a realistic one: **a support ticket triage
pipeline**.

Requirements:

```
1. Read the incoming ticket
2. Classify it: bug / billing / question / other
3. If bug   -> extract reproduction steps, file a ticket, THEN draft a reply
4. If billing -> flag for a human, do NOT auto-reply
5. If question -> search the docs, draft a reply from what was found
6. Always: validate the draft before sending
7. If validation fails -> send to a human instead
```

Now answer, in writing:

- **(a)** How many nodes? Name them.
- **(b)** Which nodes are LLM steps? Data steps? Action steps?
- **(c)** What are the state keys? Which need a reducer, and why?
- **(d)** Where are the branch points? What is the router's decision function
      actually reading out of state?
- **(e)** Which node could be dangerously retried? Which must never be cached?

Hold your answers. L02 and L03 will make this concrete, and L04 is where the
reducer question gets interesting.

<details>
<summary>Reference answer (read after you've written your own)</summary>

- **(a)** 8 nodes: `read_ticket`, `classify`, `extract_repro`, `file_bug`,
  `search_docs`, `draft_reply`, `validate_draft`, `send` (plus `escalate`).
- **(b)** LLM: `classify`, `extract_repro`, `draft_reply`, `validate_draft`.
  Data: `search_docs`. Action: `file_bug`, `send`.
- **(c)** `ticket` (raw), `classification` (dict), `repro_steps` (list),
  `bug_id` (str), `doc_snippets` (list), `draft` (str),
  `validation` (dict), `escalation_reason` (str). `doc_snippets` and
  `repro_steps` want append-style reducers.
- **(d)** After `classify` (3-4 ways) and after `validate_draft` (2 ways).
- **(e)** `file_bug` and `send` are actions — a blind retry can create a
  duplicate bug or send the email twice. They need idempotency keys and
  should not be cached.

</details>

---

## 7. Checkpoint

By the end of L01 you should be able to:

- [ ] Explain a LangGraph graph in one sentence without notes.
- [ ] Define a superstep and predict how many supersteps a given graph needs.
- [ ] Give two concrete cases where an explicit graph beats an agent loop.
- [ ] Say when the Functional API is the better fit.
- [ ] Walk through the five-step design process for a new system.
- [ ] Explain why "keep state raw" matters.

---

**Next → [L02 · Your first StateGraph](./L02-first-graph.md)** — we build the
ticket-triage graph for real: `add_node`, `add_edge`, `START`/`END`,
`compile()`, and reading the Mermaid diagram.
