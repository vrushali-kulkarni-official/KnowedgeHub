# L14 · Capstone: a deep-research pipeline

> **New module · ~3h**
> Goal: put every Phase 7 concept into one real graph and be able to point at
> each one inside it.

The graph lives in [`graphs/research.py`](../graphs/research.py) and is served
by `langgraph dev` (see [`langgraph.json`](../langgraph.json)).

---

## 1. The pipeline

```
START ──► plan ──► dispatch ──┬──► research ──┐
                (Command)      │   (x N, Send) │
                               │               ▼
                               └──────────► synthesize
                                                │
                                                ▼
                                     critique_and_revise   ← SUBGRAPH
                                                │
                                                ▼
                                          finalize ──► END
```

What it does:

1. **`plan`** — ask the model to break a topic into 3 sub-questions.
2. **`dispatch`** — prepare the work list, then fan out one `Send` per
   question so all three `research` runs happen in parallel.
3. **`research`** — answer one question using retrieved context.
4. **`synthesize`** — reduce the findings into a draft report.
5. **`critique_and_revise`** — a **subgraph**: critique the draft, revise it,
   re-critique — in a **bounded** loop.
6. **`finalize`** — emit the final report.

---

## 2. Every Phase 7 concept, and where it lives

| Concept | Where in the code |
|---|---|
| **State schema with three reducer styles** | `ResearchState` — `questions`/`findings` use `Annotated[..., operator.add]`; `plan`/`draft`/`critique` overwrite; `needs_revision` is a plain flag |
| **Runtime context** | `ResearchContext` (dataclass) + `context_schema=ResearchContext` |
| **`Command` with typed destinations** | `plan` returns `Command[Literal["dispatch"]]` |
| **`Command` with `update=` + `goto=`** | `plan` updates the state *and* routes in one return |
| **`Send` map-reduce** | `route_research` returns one `Send` per work item |
| **The `Send` diagram gotcha** | the fan-out is declared with `add_conditional_edges(..., path_map)` so the static graph stays honest |
| **Fan-in reducer** | `operator.add` on `findings` merges the three parallel results |
| **Subgraph** | `critique_graph` compiled separately, then `add_node("critique_and_revise", critique_graph)` |
| **Shared-key subgraph** | the subgraph's `CritiqueState` shares `draft`, `critique`, `revision`, `needs_revision` with the parent |
| **Conditional edge inside the subgraph** | `route_revision` → `"revise"` or `END` |
| **A bounded loop** | `route_revision` checks `runtime.context.max_revisions` |
| **Retry policy** | `add_node("research", research, retry_policy=RetryPolicy(max_attempts=3, ...))` |
| **Persistence** | `compile(checkpointer=InMemorySaver())` in the example; `thread_id` per conversation |
| **Streaming** | `stream_mode="updates"` in the example |
| **Mermaid visualisation** | `graph.get_graph().draw_mermaid()` |

---

## 3. Run it

```bash
python examples/L14_capstone.py
```

Or with the visual debugger:

```bash
langgraph dev
# open the Studio URL it prints, pick the "research" graph, run it
```

---

## 4. Things worth noticing

### 4.1 The `Send` target sees ONLY the payload

```python
def research(state: ResearchState, runtime: Runtime[ResearchContext]) -> dict:
    question = state["question"]     # <- this is the Send payload
    ...
```

`research` cannot see `topic`, `plan` or `findings`. It gets exactly
`{"question": q}` and nothing else. That is the `Send` contract, and it is
why the node is so easy to test.

If it needed more, you send more:

```python
Send("research", {"question": q, "style": state["style"]})
```

### 4.2 The fan-in is order-independent

`findings` uses `operator.add`, so the three parallel results merge — but
**in whatever order they finish**. The `synthesize` node therefore sorts
deterministically before building the report. If order matters, use
distinct keys and merge explicitly (L08).

### 4.3 The refinement loop is bounded

```python
def route_revision(state, runtime) -> Literal["revise", "done"]:
    if not state.get("needs_revision"):
        return "done"
    if state.get("revision", 0) >= runtime.context.max_revisions:
        return "done"
    return "revise"
```

Two conditions. Drop the second and a critic that never says "APPROVED"
loops until `GraphRecursionError`. **Every loop in a graph needs a budget.**

The budget lives in the **context**, not the state: it is a policy of the
run, not a fact about the data.

### 4.4 The subgraph shares keys, so it inherits the parent's state

`critique_graph` is compiled from `CritiqueState`, which declares
`draft`, `critique`, `revision` and `needs_revision` — all of which also
exist in `ResearchState`. So when the parent adds it as a node, the
subgraph reads the parent's `draft` directly and writes `critique` back
into the parent's state.

The subgraph's *private* concern (the critique loop) does not pollute the
parent's schema, because those keys are declared in both.

### 4.5 The context carries the model

```python
@dataclass
class ResearchContext:
    user_id: str = "anonymous"
    model: Any = None
    corpus: dict[str, str] = field(default_factory=dict)
    max_questions: int = 3
    max_revisions: int = 2
```

The model is built **once per run** and injected. Nodes never construct
their own LLM, so swapping `gemini-3.8-flash` for `gemini-3.1-pro-preview`
is a one-line change at the call site, and tests can inject a fake.

The `corpus` and the budgets are also context — they are run-scoped policy,
not data that should be checkpointed.

---

## 5. Things you could add next

These are all small, and all use things you now know.

| Idea | How |
|---|---|
| **Human approval before sending** | `interrupt()` in `finalize` (Phase 8) |
| **Real retrieval** | replace `_lookup()` with a vector store; keep the `Send` fan-out |
| **Streaming tokens to a UI** | `stream_mode="messages"` |
| **Tracing** | `config={"callbacks": [langfuse_handler]}` |
| **Persist to disk** | `SqliteSaver` instead of `InMemorySaver` |
| **A second specialist agent** | another subgraph, routed by topic |
| **Cache the research step** | `CachePolicy(ttl=3600)` + `compile(cache=InMemoryCache())` |
| **Retry only transient failures** | `RetryPolicy(retry_on=(ConnectionError, TimeoutError))` |

---

## 6. The checkpoint

- [ ] Ran the pipeline end to end
- [ ] Can point at each Phase 7 concept in the code
- [ ] Can explain why the `Send` target only sees its payload
- [ ] Can explain why the refinement loop needs a budget
- [ ] Can explain what the subgraph inherits from the parent
- [ ] Have added at least one improvement from section 5

---

**Next → [The cheat sheet](../CHEATSHEET.md)** — and then **Phase 8**:
human-in-the-loop, memory, multi-agent architectures and production patterns.
