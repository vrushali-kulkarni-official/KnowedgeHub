# L04 · Reducers

> **Module M49 (part 2) · ~3h**
> Goal: never lose a message again, and understand exactly *why* reducers
> behave the way they do.
>
> **This is the most important lesson in Phase 7.** Almost every "LangGraph
> randomly loses my message" bug is a reducer bug.

---

## 1. The mental model: channels and reducers

Here is the model that makes everything else obvious.

> **State is not one dict. State is a set of independent *channels*.**
> **Each channel has its own rule for combining writes.**

```
State
├── messages    (channel, reducer = add_messages)
├── errors      (channel, reducer = operator.add)
├── draft       (channel, reducer = LastValue / overwrite)
└── needs_human (channel, reducer = LastValue / overwrite)
```

When a node returns `{"draft": "hello"}`, LangGraph asks the `draft`
channel's reducer: *"combine this write with what is already there."*

- `draft`'s reducer: **overwrite** → `draft = "hello"`
- `messages`' reducer: **append** → `messages = [...existing, new]`

That is the entire mechanism. A reducer is just a function:

```python
def reducer(left, right) -> new_value
```

where `left` is the current channel value and `right` is what the node just
wrote.

### Why this design exists

Because **nodes in the same superstep run in parallel**, and parallel writes
to the same channel need a *defined* merge order. A reducer is that
definition.

- No reducer → "only one writer per step" is enforced with an error.
- With a reducer → many writers are fine, because the reducer knows how to
  combine them.

---

## 2. The default: overwrite

If a key has no reducer, LangGraph uses `LastValue`: the newest write wins.

```python
class State(TypedDict):
    draft: str

def node_a(s): return {"draft": "from A"}
def node_b(s): return {"draft": "from B"}
```

- Run A then B sequentially → `draft == "from B"` (B overwrote A).
- Run A and B **in parallel** → `InvalidUpdateError: At key 'draft': Can
  receive only one value per step.`

That error is LangGraph refusing to guess. It is a *good* error. It means
"you have a design decision here — make it explicit".

---

## 3. `Annotated[list, operator.add]` — the append reducer

The most common reducer you will write is "append".

```python
import operator
from typing import Annotated
from typing_extensions import TypedDict

class State(TypedDict):
    snippets: Annotated[list[str], operator.add]
```

`operator.add` on two lists concatenates them. So:

```python
def node_a(s): return {"snippets": ["a"]}
def node_b(s): return {"snippets": ["b"]}
```

- Sequentially: `["a"]` → `["a", "b"]`
- **In parallel**: `["a", "b"]` — order is whatever order the writes land in.
  **Do not depend on the order.**

You can also write the reducer by hand when you need the logic to be obvious:

```python
def append(left: list[str], right: list[str]) -> list[str]:
    """Combine two list updates by concatenation."""
    return left + right

class State(TypedDict):
    snippets: Annotated[list[str], append]
```

> **The reducer must be left-associative-ish and total.** It must handle the
> case where `left` is the empty list (the initial channel value) and where
> `right` is `None` (a node returned `{"snippets": None}`). Be defensive.

---

## 4. `add_messages` — the special one

`add_messages` is LangGraph's built-in reducer for chat message lists. It
does *more* than `operator.add`, which is why you should use it for messages.

```python
from langgraph.graph.message import add_messages   # <-- the canonical import

class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
```

> **Import path note (v1.7 core / v1.2 graph).** `add_messages` lives in
> `langgraph.graph.message`. It is **not** exported from `langchain_core.messages`
> in the current release. Older tutorials show
> `from langchain_core.messages import add_messages` — that import no longer
> exists. Use `langgraph.graph.message`.

### What `add_messages` does beyond appending

1. **Assigns IDs.** Every message without an `id` gets a deterministic one
   (UUIDv7-ish, derived from position) so it can be referenced later.
2. **Deduplicates by ID.** Writing a message with an ID that already exists
   *replaces* it instead of appending a duplicate.
3. **Handles `RemoveMessage`.** Writing `RemoveMessage(id=...)` deletes that
   message from the list.
4. **Accepts shorthand.** You can write `{"role": "user", "content": "hi"}`
   and it becomes a `HumanMessage`.
5. **Coerces to message objects.** Strings, dicts, and tuples all work.

### The update-by-ID pattern

This is the feature that makes `add_messages` special:

```python
from langchain_core.messages import AIMessage, HumanMessage

m = AIMessage("first", id="m1")
state = {"messages": [m]}

# Later, a node wants to EDIT that message rather than append a new one:
state = {"messages": [AIMessage("edited", id="m1")]}
# -> messages is now a single message with content "edited"
```

Because the IDs match, `add_messages` replaces instead of appending. This is
how you "edit history" in LangGraph.

### Removing a message

```python
from langchain_core.messages import RemoveMessage

def trim(state):
    return {"messages": [RemoveMessage(id=state["messages"][0].id)]}
```

### The `MessagesState` shortcut

```python
from langgraph.graph import MessagesState

class MyState(MessagesState):
    extra: int
```

is exactly `Annotated[list[AnyMessage], add_messages]` plus `extra: int`.
Use it.

---

## 5. Custom reducers — when `operator.add` is not enough

A reducer is a plain function `(left, right) -> value`. Write one when the
merge rule is domain logic.

### Example 1: keep the *last* non-empty value

```python
def keep_last_non_empty(left: str, right: str) -> str:
    return right or left
```

### Example 2: merge dicts

```python
def merge_dicts(left: dict, right: dict) -> dict:
    return {**left, **right}
```

### Example 3: dedupe while preserving order

```python
def dedupe_append(left: list[str], right: list[str]) -> list[str]:
    out = list(left)
    for item in right:
        if item not in out:
            out.append(item)
    return out
```

### Example 4: cap the size of a log

```python
MAX_EVENTS = 100

def capped_append(left: list, right: list) -> list:
    combined = left + right
    return combined[-MAX_EVENTS:]
```

### The rules a reducer must follow

| Rule                                                                     | Why                                                                                 |
| ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------- |
| Must be **deterministic**                                                | the same inputs must always give the same output, or checkpoints are not replayable |
| Must handle `left` being the **initial/empty** value                     | that is the first call                                                              |
| Must handle `right` being `None`                                         | a node may return `{"key": None}`                                                   |
| Should not **mutate** `left` in place                                    | you corrupt the checkpointed value                                                  |
| Should be **commutative or order-tolerant** if used in parallel branches | parallel write order is not defined                                                 |

---

## 6. `Overwrite` — bypassing a reducer on purpose

Sometimes you genuinely want to *replace* an accumulated list, not append.

```python
from langgraph.types import Overwrite

def reset_events(state):
    return {"events": Overwrite([])}
```

`Overwrite` tells LangGraph: "ignore the reducer for this write, set the
channel to exactly this."

There is also a JSON-friendly form for clients that cannot send Python
objects:

```python
return {"events": {"__overwrite__": []}}
```

> **Warning:** in a single superstep, **only one node** may `Overwrite` the
> same key. Two nodes doing it → `InvalidUpdateError`.

---

## 7. The silent-failure catalogue ⚠️

This is the section that saves you a day. **Reducer bugs usually do not
raise. They silently do the wrong thing.**

### 7.1 Silent message loss — the classic

```python
# BROKEN
class State(TypedDict):
    messages: list          # no reducer!

def node_a(state): return {"messages": [AIMessage("A")]}
def node_b(state): return {"messages": [AIMessage("B")]}

# node_a then node_b  ->  messages == [B]      <-- A is GONE
```

Because there is no reducer, the default is *overwrite*. The second write
replaces the first. No error, no warning. Your agent "forgets" things.

**The fix:**

```python
class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
```

**How to spot it:** if a message "disappears", the key has no reducer, or the
reducer is not `add_messages`/`operator.add`.

### 7.2 The `errors` merge trap

```python
# node A returns {"errors": ["bad sql"]}
# node B returns {"errors": []}
# -> state["errors"] == ["bad sql"]   NOT []
```

A node that *clears* the error list with `{"errors": []}` does **not** clear
it — the reducer concatenates, so `["bad sql"] + [] == ["bad sql"]`.

This was **verified** in `examples/L04_reducers.py`: with
`Annotated[list[str], operator.add]`, the final `errors` is `['bad sql']` even
though the last node said "no errors".

The fix depends on which semantics you want:

```python
# (a) STICKY errors - "no NEW errors" keeps what was already there
def sticky_errors(left: list[str], right: list[str]) -> list[str]:
    return right or left

# (b) LATEST VERDICT wins - the last node is authoritative, so [] clears
def latest_verdict(left: list[str], right: list[str]) -> list[str]:
    return list(right)

# (c) Or just use Overwrite([]) in the node that wants to clear.
```

**The general lesson:** a reducer is a *merge* rule. If two nodes mean
different things by the same write ("here is an error" vs "there are no
errors"), an append reducer cannot express that. Decide which semantics you
want — and write the reducer to match.

### 7.3 A reducer that silently ignores writes

```python
def merge_dicts(left: dict, right: dict) -> dict:
    return left        # BUG: right is discarded
```

No error. The node's write vanishes. When you debug "my update disappeared",
read your reducer before you read your node.

### 7.4 `right` is `None`

```python
def merge(left, right):
    return left + right      # TypeError if right is None
```

Some nodes return `{"key": None}` to mean "no value". Make your reducer
tolerant:

```python
def merge(left: list, right: list | None) -> list:
    return left + (right or [])
```

### 7.5 Reducing on a key that is not in the schema

If a node returns a key that is not declared in the state schema, LangGraph
raises `InvalidUpdateError` — this one is loud, which is a relief.

---

## 8. Debugging reducers — a practical checklist

When data "disappears":

1. **Print the schema.**

   ```python
   print(State.__annotations__)
   ```

   Look for the key. Is it `Annotated[...]` or bare?

2. **Print the reducer.**

   ```python
   print(State.__annotations__["messages"])
   ```

   The second element of the `Annotated` is the reducer.

3. **Watch the writes.** `stream_mode="updates"` shows exactly what each node
   returned:

   ```python
   for chunk in graph.stream(inp, stream_mode="updates"):
       print(chunk)
   ```

   If a node's chunk is missing your key, the *node* is the bug, not the
   reducer.

4. **Read the graph's own channel config.**

   ```python
   print(graph.channels)     # NOTE: on the COMPILED graph, not get_graph()
   ```

   Output looks like:

   ```
   {'messages': BinaryOperatorAggregate, '__start__': EphemeralValue,
    '__pregel_tasks': Topic, 'branch:to:n': EphemeralValue}
   ```

   `BinaryOperatorAggregate` = a reducer is attached. This is the fastest way
   to see what LangGraph actually believes.

5. **Check for parallel writers.** Two nodes in the same superstep writing
   the same key is the number one cause of `InvalidUpdateError`.

---

## 9. The reducer decision table

| What you want              | What to write                               |
| -------------------------- | ------------------------------------------- |
| Append to a list           | `Annotated[list[str], operator.add]`        |
| Chat message history       | `Annotated[list[AnyMessage], add_messages]` |
| Merge dicts                | `Annotated[dict, merge_dicts]`              |
| Replace everything         | `Annotated[list, ...]` + `Overwrite(value)` |
| Last write wins (explicit) | no reducer (the default)                    |
| Dedupe on append           | `Annotated[list[str], dedupe_append]`       |
| Domain-specific merge      | your own `(left, right) -> value`           |

---

## 10. Rules of thumb

1. **Every list key that more than one node can touch needs a reducer.**
2. **Messages always use `add_messages`**, never `operator.add` (you lose
   ID-based updates, `RemoveMessage` and coercion).
3. **A reducer is a merge rule, not a filter.** If a node needs to "clear" a
   channel, either use `Overwrite` or write a reducer whose semantics match
   ("empty right means clear").
4. **Never mutate `left` in a reducer.** Return a new object.
5. **Make reducers total.** Handle `None`, empty lists, empty dicts.
6. **Test reducers in isolation.** They are pure functions. A unit test is
   three lines and pays for itself immediately.

```python
def test_add_messages_appends():
    from langgraph.graph.message import add_messages
    from langchain_core.messages import HumanMessage, AIMessage
    out = add_messages([HumanMessage("a")], [AIMessage("b")])
    assert len(out) == 2
```

---

## 11. Checkpoint

- [ ] I can explain state-as-channels and the `(left, right) -> value` reducer
  contract in my own words.
- [ ] I know the default is overwrite and that this is the #1 cause of
  silently lost messages.
- [ ] I can write `Annotated[list, operator.add]` and `add_messages` from
  memory, and know the correct import path.
- [ ] I know what `add_messages` does *beyond* appending (IDs, replace-by-ID,
  `RemoveMessage`, coercion).
- [ ] I can write a custom reducer and know the four rules it must follow.
- [ ] I know `Overwrite` and when to use it.
- [ ] I can explain the `errors: []` trap.
- [ ] I have a debugging checklist for "my data disappeared".

---

**Next → [L05 · Routing: conditional edges and `Command`](./L05-routing-and-command.md)**
— how a node decides where to go next, and the modern `Command` style.
