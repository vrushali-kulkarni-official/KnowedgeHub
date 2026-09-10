# Module 02 — State (the heart of LangGraph)

## Prerequisites

- Module 00 (env + LLM factory + first graph)
- Module 01 (mental model)

## Why this module matters

State is the *only* thing nodes share. Get the state design wrong and every other choice falls apart. Get it right and the rest of LangGraph feels natural.

This module is dense. Take it slow. The patterns here are reused in every later module.

## Learning objectives

By the end of this module you can:

1. Choose the right state schema style: `TypedDict`, `dataclass`, or Pydantic.
2. Use the standard reducer `add_messages` and write custom reducers.
3. Distinguish **overwrite** (default) from **append/merge** (via `Annotated`).
4. Use the built-in `MessagesState`.
5. Implement state channels with isolated updates and the `OverlayState` patterns.
6. Design state that scales to multi-actor and multi-agent use cases.

---

## 2.1 What state is (recap, precisely)

The state is a typed Python dict (or dataclass / Pydantic model). At every step:

1. LangGraph holds the current state.
2. A node is called with the current state.
3. The node returns a dict: only the keys it wants to update.
4. LangGraph merges the returned dict into the state using a **reducer per key**.
5. The new state is passed to the next node.

That's the whole story. Now we make it concrete.

---

## 2.2 Schema style: `TypedDict` vs `dataclass` vs Pydantic

### 2.2.1 `TypedDict` (default, recommended to start)

```python
from typing import TypedDict

class State(TypedDict):
    messages: list
    user_id: str
    step_count: int
```

Pros: standard library, no overhead, easy.
Cons: no runtime validation; type checkers only see it as a `dict`.

### 2.2.2 `dataclass`

```python
from dataclasses import dataclass, field
from typing import Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

@dataclass
class State:
    messages: Annotated[list[BaseMessage], add_messages] = field(default_factory=list)
    user_id: str = ""
    step_count: int = 0
```

Pros: methods, default values, IDE autocomplete, immutability options.
Cons: slightly more boilerplate, copy semantics for nested mutation.

### 2.2.3 Pydantic (`BaseModel`)

```python
from pydantic import BaseModel
from typing import Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

class State(BaseModel):
    messages: Annotated[list[BaseMessage], add_messages] = []
    user_id: str
    step_count: int = 0
```

Pros: runtime validation, JSON serialization, `.model_dump()`.
Cons: performance overhead, validation can surprise you mid-graph.

### 2.2.4 Which to pick

| Use case | Pick |
|---|---|
| Quick prototypes, most apps | `TypedDict` |
| Apps that need methods on state or default factories | `dataclass` |
| Apps that need runtime validation, JSON I/O | Pydantic |
| Anything you'll serialize to Postgres JSONB | Pydantic (best) |

You can mix. Most production codebases use `TypedDict` for inner graphs, Pydantic for outer API models.

---

## 2.3 Reducers: the merge rules

### 2.3.1 The default reducer: overwrite

If a field has no reducer, the node's return value for that key **replaces** the current value.

```python
class State(TypedDict):
    user_id: str
    last_step: str

def node_a(state: State) -> dict:
    return {"last_step": "a"}    # overwrites last_step

def node_b(state: State) -> dict:
    return {}                      # last_step stays as "a"
```

### 2.3.2 `add_messages` — the most important reducer

`add_messages` is the canonical reducer for chat history. It:

- **Appends** new messages.
- **Deduplicates** by `id` (so retries are safe).
- **Updates** existing messages by `id` (so you can patch an `AIMessage` after streaming).

```python
from typing import Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
```

Usage:

```python
def chat_node(state):
    ai_msg = llm.invoke(state["messages"])
    return {"messages": [ai_msg]}   # appended, not replaced
```

### 2.3.3 Operator reducers

```python
from typing import Annotated
import operator

class State(TypedDict):
    # lists: append
    todos: Annotated[list[str], operator.add]
    # numbers: sum
    token_count: Annotated[int, operator.add]
    # sets: union
    seen_ids: Annotated[set[str], operator.or_]
```

### 2.3.4 Custom reducers

A reducer is `(current_value, new_value) -> merged_value`.

```python
def merge_dicts(a: dict, b: dict) -> dict:
    return {**a, **b}   # shallow merge; new keys overwrite

class State(TypedDict):
    context: Annotated[dict, merge_dicts]
```

Use custom reducers when:

- You want field-level merge (e.g. partial JSON updates).
- You want to maintain a sliding window (e.g. last N messages).
- You want a max-size constraint.

### 2.3.5 The reducer cheat sheet

| Want | Reducer |
|---|---|
| Replace value | (no annotation) |
| Append to list | `Annotated[list, operator.add]` |
| Sum numbers | `Annotated[int, operator.add]` |
| Chat-style messages | `Annotated[list[BaseMessage], add_messages]` |
| Merge dicts shallow | custom `merge_dicts` |
| Sliding window | custom |
| Union sets | `Annotated[set, operator.or_]` |

---

## 2.4 `MessagesState` and the `messages` channel

LangGraph ships a pre-built state for chat:

```python
from langgraph.graph import MessagesState
# Equivalent to:
# class MessagesState(TypedDict):
#     messages: Annotated[list[BaseMessage], add_messages]
```

Use it when your state is just messages. Extend it for real apps:

```python
class State(MessagesState):
    user_id: str
    retrieved_docs: list[str]
```

---

## 2.5 Channels: under the hood (theory you need)

Each field of your state is a **channel** with its own value, reducer, and (optionally) initial value. LangGraph tracks them independently.

This matters because:

- A node can return `{ "messages": [...] }` and not touch `user_id` — that field is preserved.
- Different channels can be persisted, streamed, and updated separately.
- The `Send` API (Module 03) lets you dynamically fan out to nodes that only need a subset of state.

You'll rarely think about channels directly, but when state behaves weirdly, you'll be glad you know they exist.

---

## 2.6 Isolated updates: the `writer` pattern

Sometimes a node wants to update state *during* execution, not just at the end. Use the `config` parameter to access the runtime:

```python
from langgraph.types import StreamWriter

def streaming_node(state: State, writer: StreamWriter):
    writer({"progress": "step 1 done"})
    # ... do work ...
    writer({"progress": "step 2 done"})
    return {"messages": [...]}     # final update
```

`writer` is what powers the `custom` stream mode (Module 07).

---

## 2.7 State design patterns

### 2.7.1 Pattern: minimal state

Only put in state what **must** be shared between nodes or **must** be persisted.

❌ Don't:
```python
class State(TypedDict):
    raw_pdf_bytes: bytes              # huge, not needed downstream
    intermediate_calculation: float  # only used by one node
```

✅ Do:
```python
class State(TypedDict):
    pdf_text: str                     # smaller, reused
    final_answer: str                 # only the final result
```

### 2.7.2 Pattern: typed enums for routing flags

```python
from enum import Enum

class StepName(str, Enum):
    SEARCH = "search"
    ANSWER = "answer"

class State(TypedDict):
    current_step: StepName
```

Routing functions return these. Type-checker catches typos.

### 2.7.3 Pattern: input vs output state

Public APIs care about a *subset* of state. Define input/output schemas:

```python
class InputState(TypedDict):
    question: str

class OutputState(TypedDict):
    answer: str

class OverallState(InputState, OutputState):
    intermediate: list[str]
```

```python
builder = StateGraph(OverallState, input=InputState, output=OutputState)
```

This gives you a clean public contract while keeping internal state private.

### 2.7.4 Pattern: state validation on edges

Before routing, validate that the state is "ready":

```python
def ready_to_answer(state: State) -> str:
    if not state.get("retrieved_docs"):
        return "search"
    return "answer"
```

### 2.7.5 Pattern: scratchpads and todos

Long-running agents need a place to track plans. Add it to state:

```python
class State(TypedDict):
    todos: Annotated[list[Todo], operator.add]
    messages: Annotated[list[BaseMessage], add_messages]
```

This is what Deep Agents' `write_todos` tool mutates (Module 12).

---

## 2.8 Common state pitfalls (and fixes)

| Pitfall | Fix |
|---|---|
| Forgetting `add_messages` and overwriting history on every turn | Use `Annotated[list[BaseMessage], add_messages]` |
| Mutating state inside a node (`state["x"] = ...`) | Always **return** a new dict; LangGraph handles merging |
| Putting huge blobs in state | Store a reference (path, ID) in state, not the data |
| Putting Pydantic objects in state directly | Convert via `.model_dump()` first, or use Pydantic state |
| Confusing dataclass copy semantics | With dataclass state, returns are still dicts; copies are handled by LangGraph |

---

## Hands-on project

**Goal:** Build a state schema for a "research assistant" graph.

1. Define a state with:
   - `messages` (chat history)
   - `query` (the user's question)
   - `retrieved_docs` (list of strings)
   - `draft_answer` (string)
   - `iterations` (int, summed)
   - `needs_more_search` (bool)
2. Use proper reducers for each field.
3. Write a node that:
   - Appends to `messages` (use `add_messages`)
   - Increments `iterations` (use `operator.add`)
   - Sets `draft_answer`
4. Verify by running the graph twice and checking `iterations` accumulates correctly.
5. Add an input/output schema split. Make `query` only in input, `draft_answer` only in output.

## Exercises

1. **Without `add_messages`,** run a 3-turn conversation. What happens to the history? Now add it back. What changes?
2. **Write a sliding-window reducer** that keeps only the last 10 messages. Test it.
3. **Custom reducer challenge:** write a reducer for a "context" dict that merges deeply (one level), not shallowly. Test with nested dicts.
4. **Add a `last_tool_call` field** that always holds *only* the most recent tool call. Which reducer? (Hint: it's not append.)
5. **Add runtime validation** to your state by switching to Pydantic. What breaks? Why?

## Production checklist

- [ ] Every state field has a deliberate reducer (default = overwrite, explicit = your call).
- [ ] No huge blobs in state. Store references.
- [ ] Input/output schemas defined for the public API.
- [ ] State is JSON-serializable (or you've deliberately chosen Postgres BYTEA / a custom serializer).
- [ ] You never mutate state in-place inside a node.

## Key takeaways

- State is a typed dict with **per-field reducers**. The reducer is the merge rule.
- `add_messages` is the chat reducer. Use it everywhere.
- Keep state small and shared. Treat it like a database row, not a scratchpad.
- Input/output schemas give you a public contract for the graph.

## Resources

- LangGraph state docs: https://langchain-ai.github.io/langgraph/concepts/low_level/
- Reducer reference: https://langchain-ai.github.io/langgraph/concepts/low_level/#reducers
- `add_messages` source: `from langgraph.graph.message import add_messages`
