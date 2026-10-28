# L03 · State & schema types

> **Module M49 (part 1) · ~2.5h**
> Goal: design a state schema you will still like in six months.

---

## 1. What "state" actually is

State is a **dictionary**. That is the whole contract.

- Keys are declared in a schema so LangGraph knows what exists.
- Each key has a **type** (for validation and for your editor).
- Each key has a **reducer** (how updates merge) — L04.
- Nodes read the whole state (or a subset) and return a **partial update**.

There is no "state object" class to instantiate, no ORM, no schema migration
tool. You declare a shape and LangGraph enforces it.

---

## 2. Three ways to declare a state schema

All three are supported. Pick by taste and by what your team already uses.

### 2a. `TypedDict` — the default choice

```python
from typing_extensions import TypedDict

class State(TypedDict):
    ticket: str
    category: str
    doc_snippets: list[str]
```

Why: it is the standard Python idiom for "a dict with a known shape", it
supports `Annotated` (needed for reducers), and it has **zero runtime
validation** — which is fast and forgiving.

> Use `typing_extensions.TypedDict`, not `typing.TypedDict`, on Python < 3.12.
> `typing_extensions` backports `Required`/`NotRequired` and works everywhere.

### 2b. Pydantic `BaseModel` — when you want validation

```python
from pydantic import BaseModel, Field

class State(BaseModel):
    ticket: str
    category: str = "unknown"
    doc_snippets: list[str] = Field(default_factory=list)
```

Why: Pydantic **validates the input** at the graph boundary. If someone
invokes your graph with `{"ticket": 123}`, it fails fast with a clear error
instead of exploding three nodes deep.

Downside: Pydantic models are not dicts, so `state["ticket"]` does not work
— you use `state.ticket`. Nodes must return a full instance or a dict
( LangGraph accepts both for updates, but attribute access is the idiom).

> **Pick one style and stay consistent.** Mixing `state["x"]` and `state.x` in
> one graph is the fastest way to confuse yourself.

### 2c. `dataclass` — cheap, typed, no validation

```python
from dataclasses import dataclass, field

@dataclass
class State:
    ticket: str
    category: str = "unknown"
    doc_snippets: list[str] = field(default_factory=list)
```

Why: standard library, fast, gives you defaults and `__repr__` for free.

---

## 3. Which one should *you* use?

| Situation                                             | Use         |
| ----------------------------------------------------- | ----------- |
| Internal workflow, you control all callers            | `TypedDict` |
| Graph is an API boundary (web service, agent server)  | `BaseModel` |
| You want `Annotated` reducers + maximum compatibility | `TypedDict` |
| You already have a Pydantic domain model              | `BaseModel` |

**Course default: `TypedDict`.** It is what the LangGraph docs use, it is
what `MessagesState` is built on, and it composes with `Annotated` reducers
without extra ceremony.

---

## 4. `MessagesState` — the one state you will use constantly

LangGraph ships a prebuilt state for chat:

```python
from langgraph.graph import MessagesState

class MyState(MessagesState):
    extra_field: int
```

`MessagesState` is literally:

```python
class MessagesState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
```

That single `Annotated` is doing a *lot* of work — it is the reducer that
makes message history append correctly. L04 unpacks it.

You can also use it directly:

```python
from langgraph.graph import StateGraph, MessagesState
```

---

## 5. Input schema vs output schema vs internal schema

By default a graph has **one** schema: what goes in is what comes out.

```python
builder = StateGraph(OverallState)     # one schema
```

You can split it into three:

```python
builder = StateGraph(
    OverallState,          # internal schema - what nodes exchange
    input_schema=InputState,    # what invoke() accepts
    output_schema=OutputState,  # what invoke() returns
)
```

A worked example:

```python
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END

class InputState(TypedDict):
    question: str

class OutputState(TypedDict):
    answer: str

class OverallState(InputState, OutputState):
    """Internal schema: nodes see both question and answer."""

def answer_node(state: InputState) -> OverallState:
    return {"answer": "bye", "question": state["question"]}

graph = (
    StateGraph(OverallState, input_schema=InputState, output_schema=OutputState)
    .add_node("answer_node", answer_node)
    .add_edge(START, "answer_node")
    .add_edge("answer_node", END)
    .compile()
)

print(graph.invoke({"question": "hi"}))
# {'answer': 'bye'}          <-- 'question' is FILTERED OUT
```

**Why this matters**

1. **Input validation.** `invoke({"wrong": "shape"})` fails immediately.
2. **Output hygiene.** Internal scratch fields (`_raw_response`, `_debug`) do
   not leak to your API response.
3. **A stable contract.** The internal schema can change without breaking
   callers.

**Warning:** the output schema filters by **key**, and it does *not* require
the key to be present. If `answer` was never written, it is simply absent.

---

## 6. Private state — the `input_schema=` trick on `add_node`

Sometimes two nodes need to exchange a big intermediate value that nobody
else should see and nobody should get back.

`add_node` accepts its **own** `input_schema`:

```python
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END

class OverallState(TypedDict):
    a: str

class Node1Output(TypedDict):
    private_data: str      # NOT in the public state

class Node2Input(TypedDict):
    private_data: str

def node_1(state: OverallState) -> Node1Output:
    return {"private_data": "set by node_1"}

def node_2(state: Node2Input) -> OverallState:
    return {"a": "set by node_2"}

def node_3(state: OverallState) -> OverallState:
    return {"a": "set by node_3"}

graph = (
    StateGraph(OverallState)
    .add_node("node_1", node_1, input_schema=OverallState)
    .add_node("node_2", node_2, input_schema=Node2Input)   # sees private_data
    .add_node("node_3", node_3, input_schema=OverallState)  # does NOT
    .add_sequence(["node_1", "node_2", "node_3"])
    .add_edge(START, "node_1")
    .compile()
)

print(graph.invoke({"a": "set at start"}))
# {'a': 'set by node_3'}    <-- private_data never appears in the output
```

**How it works:** the private key lives in a *separate channel* of the graph
state. `node_2` declares an `input_schema` that includes it, so LangGraph
routes the value to it. `node_3` does not, so it never sees it. The public
output schema hides it.

**When to use it**

- Large payloads (a full document, a dataframe) that only one branch needs.
- Secrets or PII you do not want in the final output.
- Per-branch scratch space that would otherwise collide with another branch's
  key of the same name.

> **Note the direction.** This pattern gives a node a *different view* of
> state. It does not let a node write to a key that no other node declares.
> If two parallel branches both want a private scratch key, give them
> different key names, or use `input_schema` plus distinct output types.

---

## 7. State design principles

### 7.1 Minimal

Every key costs you: schema noise, checkpoint size, mental overhead, and a
merge rule to get right. Do not put things in state "in case".

Ask: **which node reads this?** If nobody reads it, it is a local variable.

### 7.2 Raw, not formatted

> **Store the data. Format the prompt inside the node.**

```python
# BAD - the rendered prompt is frozen in state
class State(TypedDict):
    prompt: str

# GOOD - raw facts in state, rendering is a node-local concern
class State(TypedDict):
    email_content: str
    classification: dict
```

Why it matters:

- Two nodes can format the same data differently.
- You can change the template without touching the schema or migrating
  checkpoints.
- Debugging is clearer — you see the actual inputs, not a pre-baked string.
- The checkpoint stays small and portable.

### 7.3 Append-only where possible

If a key only ever grows (`messages`, `events`, `citations`, `tool_calls`),
give it an **append reducer** and never rewrite it. Append-only state is:

- trivially mergeable in parallel branches,
- safe to checkpoint and to replay,
- easy to reason about for auditing.

This is L04's core idea, and it is why the default message reducer appends.

### 7.4 Derived data does not belong in state

```python
# BAD - token_count is derivable from messages
class State(TypedDict):
    messages: list
    token_count: int

# GOOD - compute it in the node that needs it
```

If two nodes would compute the same derived value, they can both compute it.
Duplication of a cheap computation is cheaper than a stale derived field.

### 7.5 One writer per key per superstep

This is the rule that makes parallel branches work. If two nodes running in
the *same* superstep write the same key, LangGraph cannot decide who wins.

- **Error** (no reducer): `InvalidUpdateError`
- **Error** (reducer, but a reducer that can't merge): e.g. `int + str`
- **Fine** (append reducer): both append, no conflict
- **Fine** (different keys): no conflict

L04 covers the reducer side of this; L08 covers the parallel side.

### 7.6 Give every key a default

Optional keys should be `.get()`-safe, and Pydantic/dataclass states should
declare defaults:

```python
class State(TypedDict):
    category: str                       # required
    doc_snippets: NotRequired[list[str]]  # optional
```

or with Pydantic:

```python
class State(BaseModel):
    category: str = "unknown"
    doc_snippets: list[str] = Field(default_factory=list)
```

---

## 8. A worked state design (the ticket pipeline)

```python
from typing import Annotated, Literal, NotRequired
from typing_extensions import TypedDict

class Classification(TypedDict):
    intent: Literal["question", "bug", "billing", "other"]
    urgency: Literal["low", "medium", "high"]
    topic: str

class TicketState(TypedDict):
    # --- raw inputs ---
    ticket: str
    sender_email: str

    # --- LLM outputs (structured, raw) ---
    classification: NotRequired[Classification]

    # --- fetched data ---
    doc_snippets: Annotated[list[str], operator.add]   # append reducer (L04)
    bug_id: NotRequired[str]

    # --- generated content ---
    draft: NotRequired[str]
    validation: NotRequired[dict]

    # --- control flags ---
    needs_human: bool
```

Note:

- `classification` is a **dict**, not a rendered string.
- `doc_snippets` is append-only with a reducer.
- `bug_id` and `draft` are optional, written by exactly one node each.
- `needs_human` is a plain bool with a default — it is *overwritten*, never
  merged, which is exactly right for a flag.

---

## 9. Checkpoint

- [ ] I know state is a dict with a declared shape.
- [ ] I can pick between `TypedDict`, `BaseModel` and `dataclass` and say why.
- [ ] I know `MessagesState` and what makes it special.
- [ ] I can split input / output / internal schemas and explain the benefit.
- [ ] I can create private state with `add_node(input_schema=...)`.
- [ ] I can justify "raw, not formatted", "minimal", "append-only", "derived
  data does not belong", and "one writer per key per superstep".

---

**Next → [L04 · Reducers](./L04-reducers.md)** — the single most important
concept in LangGraph. `Annotated`, `operator.add`, `add_messages`, custom
reducers, `Overwrite`, and how reducer mistakes *silently lose data*.
