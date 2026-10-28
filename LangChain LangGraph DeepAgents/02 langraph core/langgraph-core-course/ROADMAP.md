# ROADMAP — Phase 7 LangGraph Core

> Your progress board. Tick a box when a lesson's checkpoint is done.
> Versions verified **2026-10-26**.

---

## Status

```
L01  [ ]  Graph thinking                         M48a   2h
L02  [ ]  Your first StateGraph                  M48b   3h
L03  [ ]  State & schema types                   M49a   2.5h
L04  [ ]  Reducers  (the big one)                M49b   3h
L05  [ ]  Routing & Command                      M48c   2.5h
L06  [ ]  Config, threads, persistence           M50a   3h
L07  [ ]  Runtime context                        M50b   2h
L08  [ ]  Parallelism & Send                     M51a   2.5h
L09  [ ]  Async & streaming                      M51b   2.5h
L10  [ ]  The Functional API                     M52    2h
L11  [ ]  Subgraphs                              M50c   2.5h
L12  [ ]  Fault tolerance                        M51c   1.5h
L13  [ ]  langgraph dev & LangSmith Studio       M53    1h
L14  [ ]  Capstone                               --     3h
```

---

## The spine

If you only remember five things, remember these. They are the load-bearing
concepts of the whole phase.

- [ ] **State is a set of channels**, each with its own reducer. (L04)
- [ ] **A reducer is a merge rule** `(left, right) -> value`. The default is
      *overwrite*, which silently loses data. (L04)
- [ ] **Supersteps**: all nodes scheduled for a step run in parallel, then a
      checkpoint is written. (L01, L08)
- [ ] **`Command(update=..., goto=...)`** couples a state change with a
      routing decision in one return. (L05)
- [ ] **Context vs state vs store vs prompt** — four different lifetimes. (L07)

---

## Per-lesson checkpoints

### L01 · Graph thinking
- [ ] Can explain a LangGraph graph in one sentence
- [ ] Can predict the superstep count of a given topology
- [ ] Can give two cases where an explicit graph beats an agent loop
- [ ] Did the L01 design exercise in the lesson

### L02 · Your first StateGraph
- [ ] Can write the 5-line skeleton from memory
- [ ] Can produce and read a Mermaid diagram
- [ ] Knows that forgetting `END` is *not* an error, but a missing `START` is

### L03 · State & schema types
- [ ] Chose TypedDict / Pydantic / dataclass deliberately
- [ ] Can split input / output / internal schemas
- [ ] Can build private state with `add_node(input_schema=...)`

### L04 · Reducers
- [ ] Can write `Annotated[list, operator.add]` and `add_messages` from memory
- [ ] Knows the correct import path for `add_messages`
- [ ] Can explain what `add_messages` does beyond appending
- [ ] Can write a custom reducer and state its four rules
- [ ] Has a debugging checklist for "my data disappeared"

### L05 · Routing & Command
- [ ] Can choose between `add_conditional_edges` and `Command` and say why
- [ ] Can use a `path_map` to decouple business labels from node names
- [ ] Can write `Command[Literal[...]]` for static checking

### L06 · Config, threads, persistence
- [ ] Can run a multi-turn conversation on one `thread_id`
- [ ] Can use `get_state` / `get_state_history` / `update_state`
- [ ] Has replayed a run from a checkpoint
- [ ] Knows the `RemainingSteps` headroom rule (stop at `<= 2`)

### L07 · Runtime context
- [ ] Can define a context schema and read `runtime.context`
- [ ] Knows context is read-only, run-scoped and never persisted
- [ ] Can pick between context / state / store / prompt

### L08 · Parallelism & Send
- [ ] Can build a fan-out and a fan-in
- [ ] Knows a fan-in needs a reducer
- [ ] Can write a `Send` map-reduce
- [ ] **Knows the static-diagram gotcha and the "extra execution" trap**

### L09 · Async & streaming
- [ ] Knows an async graph needs `ainvoke`/`astream`
- [ ] Can explain the blocking-in-async trap (and show the 3× measurement)
- [ ] Knows all seven stream modes

### L10 · Functional API
- [ ] Can write `@entrypoint` + `@task` with ordinary control flow
- [ ] Knows `previous` is a parameter
- [ ] Can mix the two APIs

### L11 · Subgraphs
- [ ] Can choose "as a node" vs "call in a node"
- [ ] Understands namespace isolation
- [ ] Has picked a persistence mode deliberately

### L12 · Fault tolerance
- [ ] Can configure retry / timeout / cache per node
- [ ] Can write an `error_handler` with a `NodeError`-annotated parameter
- [ ] Knows `compile(cache=...)` is required for caching
- [ ] Never caches or blindly retries an action node

### L13 · dev & Studio
- [ ] Has run `langgraph dev` and opened Studio
- [ ] Can write a `langgraph.json`
- [ ] Has replayed a run from a step in the UI

### L14 · Capstone
- [ ] Ran the research pipeline end to end
- [ ] Can point at each Phase 7 concept inside it

---

## Stretch goals

- [ ] Rewrite one of your Phase 6 `create_agent` apps as an explicit graph
- [ ] Add a human-in-the-loop `interrupt()` to the capstone (Phase 8 preview)
- [ ] Add Langfuse tracing to the capstone and read the trace
- [ ] Build your own `BaseCheckpointer` (the docs have a conformance suite)
- [ ] Move the capstone to a `SqliteSaver` and inspect the checkpoint table

---

## What comes next (Phase 8)

| Topic | What it is |
|---|---|
| Human-in-the-loop | `interrupt()`, `Command(resume=...)`, approval flows |
| Memory | short-term vs long-term, the store, summarisation strategies |
| Multi-agent | supervisor / swarm / handoff architectures |
| Advanced RAG | query rewriting, hybrid search, reranking, corrective loops |
| Production | deployment, auth, rate limits, evaluation harnesses |
