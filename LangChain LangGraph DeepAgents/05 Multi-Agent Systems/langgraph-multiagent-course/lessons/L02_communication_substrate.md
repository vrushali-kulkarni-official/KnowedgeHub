# L02 — The Communication Substrate: State, Messages, Artifacts

**Module:** M66 (part 2) · **Time:** ~1.5h · **Example:** `examples/ex03_communication_media.py`, `examples/ex04_state_filters.py`

---

## 0. The one question that explains all multi-agent bugs

When agent A hands something to agent B, **exactly what travels is decided
by LangGraph's schemas — not by you, at runtime, by accident.**

Most multi-agent bugs are not routing bugs. They are *plumbing* bugs: the
wrong thing crossed the boundary, or nothing crossed, or something crossed
twice.

So before any pattern, you must be fluent in **three media** and **four
filtering rules**. This lesson gives you both.

---

## 1. The three media

There are exactly three places information can live in a LangGraph system.

### 1.1 Messages — the conversation

```python
class TeamState(AgentState):   # AgentState gives you `messages`
    ...
```

`messages` is a channel with the `add_messages` reducer: new messages are
appended, and messages with the same `id` are *replaced*. That replacement
behaviour is what makes `RemoveMessage` and message editing work.

Properties you must internalise:

* It is **append-only** (with edits).
* **Every** agent that receives `messages` sees the **whole** transcript.
* It is **unbounded**. It is the single biggest source of cost in a
  multi-agent system.
* It is fully replayable — which is why it is the right thing to put in a
  checkpoint.

### 1.2 Shared state — structured facts

```python
class TeamState(AgentState):
    findings: Annotated[list[dict], lambda a, b: a + b]
    verdict:  str
    score:    float
```

A channel is one of three kinds:

| kind | reducer | behaviour |
|---|---|---|
| **last value** (no annotation) | last write wins | two writers in one step → `InvalidUpdateError` |
| **append** | `lambda a, b: a + b` | writes accumulate |
| **merge** | `lambda a, b: {**a, **b}` | dicts merge per key |

**The single most important reducer rule (learned the hard way in `ex08`):**

> With an **append** reducer, a node must return **only the new items**.
> Returning `state["list"] + [new]` duplicates everything, because the
> reducer computes `old + returned`.

```python
# WRONG - duplicates every entry on every call
return {"findings": state["findings"] + [new_finding]}

# RIGHT
return {"findings": [new_finding]}
```

### 1.3 Artifacts — big payloads behind a handle

```python
from langgraph.store.memory import InMemoryStore

store = InMemoryStore()
store.put(("docs",), "report-v1", {"text": huge_payload})

# Elsewhere, a tool pulls it by id:
item = store.get(("docs",), "report-v1")
payload = item.value["text"]
```

The `BaseStore` is a key-value store with **namespaces** (tuples). It is
persisted separately from the checkpoint, so a 5 MB document never sits in
your graph state.

**When to use each:**

| data | home | why |
|---|---|---|
| the conversation | `messages` | replayable, append-only, the natural transcript |
| a score, a verdict, a filename | shared state | typed, filtered, cheap |
| a document, raw tool output, a file | the store | too big for a prompt |

---

## 2. The four filtering rules (all verified in `ex04`)

These are the rules that decide what crosses a boundary. Each was measured
against langgraph 1.2.20.

### Rule 1 — `input_schema` filters a normal edge

```python
class FullState(AgentState):
    public_note: str
    secret_note: str

class NarrowState(AgentState):
    public_note: str

g.add_node("narrow", narrow_node, input_schema=NarrowState)
```

The node receives **only** `public_note` (plus `messages`). `secret_note`
never reaches it.

This is the **only** mechanism LangGraph gives you for context isolation.
Use it on every node that does not need the whole state.

### Rule 2 — a `Send` payload BYPASSES `input_schema`

```python
def fanout(state):
    return [Send("narrow", {"public_note": "P", "secret_note": "LEAKED"})]
```

The target node receives **both** keys, even though it declared
`input_schema=NarrowState`.

> **Rule 2 is a security rule.** If your graph state holds anything
> sensitive, a `Send` payload built with `dict(state)` will hand it to every
> branch. Build `Send` payloads from **explicit fields**.

### Rule 3 — `Command(graph=Command.PARENT, update=...)` IS filtered

Unknown keys are dropped **silently** — no exception, no warning:

```python
Command(graph=Command.PARENT, update={
    "messages": [...],
    "declared_key": "kept",
    "undeclared_key": "DROPPED SILENTLY",
})
```

> **Rule 3 is a productivity rule.** You will lose an afternoon to a field
> that "was set but isn't there". Declare it in the parent schema or it
> does not exist.

### Rule 4 — an agent sees the entire `messages` transcript

There is **no** per-agent message window on `create_agent`. If `messages` is
in the state, the agent gets all of it, every call.

`ex11` measured it:

```
prior turns   msgs seen   chars seen
          0           3           23
          5          13         3273
         20          43        13023
         50         103        32523
```

Linear growth, paid by *every* agent on *every* call.

**How to actually control it:** do not put the history in `messages`.
Summarise it into a shared-state key and pass that instead. That is L08.

---

## 3. The "echo" trap (the most expensive bug in this course)

When you add a compiled agent to a graph as a node, **the agent writes its
entire state back to the parent when it finishes.**

```python
class TeamState(AgentState):
    handoff_log: Annotated[list[str], lambda a, b: a + b]   # APPEND

agent = create_agent(model, tools=[...], state_schema=TeamState)
g.add_node("peer", agent)
```

Run it, and the log doubles every time:

```
parent handoff_log = ["a->b"]
agent   handoff_log = ["a->b"]    <- its STALE input, echoed back
parent  += agent's copy           -> ["a->b", "a->b"]
```

**The fix: give the agent a state schema that is SMALLER than the parent's,
and keep append-reducer lists OUT of it.**

```python
class PeerAgentState(AgentState):
    visits: Annotated[dict[str, int], lambda a, b: {**a, **b}]   # merge: safe

class TeamState(AgentState):
    visits:      Annotated[dict[str, int], lambda a, b: {**a, **b}]
    handoff_log: Annotated[list[str], lambda a, b: a + b]          # parent only
```

Why merge reducers are safe: merging a dict with itself is a no-op.
Why append reducers are not: appending a list to itself doubles it.

There is a second, related requirement: **`InjectedState` only works for keys
declared in the agent's own `state_schema`.** If your tool injects
`state["visits"]` and the agent's schema does not declare `visits`, you get
`KeyError: 'visits'`. So the agent's schema must declare what you inject —
but should not declare what you do not need.

---

## 4. ToolRuntime: how a tool sees the world

Tools need access to state, the store, and the config. There are two ways:

### 4.1 `ToolRuntime` — the modern, general way

```python
from langgraph.prebuilt import ToolRuntime

@tool
def my_tool(runtime: ToolRuntime) -> str:
    return f"id={runtime.tool_call_id} state_keys={sorted(runtime.state.keys())}"
```

`ToolRuntime` gives you `state`, `context`, `config`, `stream_writer`,
`tool_call_id`, `store`, `tools`, `execution_info`, `server_info`.

### 4.2 `InjectedState` / `InjectedStore` — targeted injection

```python
from langgraph.prebuilt import InjectedState, InjectedStore

@tool
def read_visits(visits: Annotated[dict, InjectedState("visits")]) -> str:
    ...

@tool
def save(note: str, store: Annotated[object, InjectedStore()]) -> str:
    ...
```

`InjectedState` accepts either a **key name** (`"visits"`) or a **whole
schema** (`Annotated[MyState, InjectedState]`). Both require the key to
exist in the agent's `state_schema`.

### 4.3 The reserved-argument-name trap

From the LangChain v1 source:

> Avoid naming tool arguments `config`, `run_manager`, or `callbacks`. These
> collide with values LangChain injects into tools at call time. A `config`
> argument is shadowed by the injected `RunnableConfig`, so the tool fails
> with `TypeError: ... missing 1 required positional argument: 'config'`.

Use `ToolRuntime` instead.

---

## 5. Putting it together: a decision table for one piece of data

```
"I need to pass a 4000-character document to the writer."
   -> store. Pass the id.                 (artifacts)

"I need to pass the customer's plan and account id to the billing agent."
   -> shared state, typed fields.         (state)
   -> and give the billing node a narrow input_schema.

"I need the billing agent to know what the customer actually said."
   -> messages. But check the size first.

"I need to pass the ticket number the support agent created."
   -> shared state, one typed field.  NOT a message - it is a fact, not a turn.
```

The last one is the distinction people get wrong most often:

> **A fact is not a turn.** "The ticket number is 9001" is a *fact* — put it
> in a typed field. "The support agent said: I opened ticket 9001" is a
> *turn* — it belongs in `messages`.

---

## 6. Run it

```bash
PYTHONPATH=examples .venv/bin/python examples/ex03_communication_media.py
PYTHONPATH=examples .venv/bin/python examples/ex04_state_filters.py
```

`ex03` builds the same pipeline three times — once per medium — and prints
what each agent could see. `ex04` proves all four filtering rules.

---

## What you should be able to do now

- Say which of the three media a given piece of data belongs in, and why.
- Write a reducer correctly (append vs merge vs last-value) and explain what
  each does on a concurrent write.
- State the four filtering rules and predict, for a given graph, exactly what
  each node will receive.
- Explain the echo trap and prevent it in your own schema.
- Use `ToolRuntime`, `InjectedState` and `InjectedStore` correctly.

**Next:** L03 — the two objects that do all the routing: `Command` and
`Send`. Plus the four traps that cost beginners the most time.
