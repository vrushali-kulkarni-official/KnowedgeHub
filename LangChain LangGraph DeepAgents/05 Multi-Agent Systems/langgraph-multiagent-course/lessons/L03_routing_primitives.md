# L03 — The Routing Primitives: `Command` and `Send`

**Module:** M66 (part 3) · **Time:** ~1.5h · **Example:** `examples/ex05_command_and_send.py`

---

## 0. Everything is these two objects

LangGraph has a lot of routing syntax: conditional edges, `add_sequence`,
branch functions, `Command`, `Send`, `goto`. It feels like a lot of
concepts. It is not. **Two objects do all the work:**

```python
Command(update=..., goto=..., graph=...)   # change state AND/OR jump
Send(node, arg)                            # run `node` with `arg`, in parallel
```

Conditional edges are sugar over the same idea: the branch function returns
a node name (equivalent to `goto`) or a list of `Send`s.

If you understand `Command` and `Send` deeply, everything else in
LangGraph — including every pattern in this course — is a combination of
them.

---

## 1. `Command` — the four fields

```python
from langgraph.types import Command

Command(
    update={...},     # state writes (a dict)
    goto="node_name", # where to go next: a str, a Send, or a list of them
    graph=None,       # None = THIS graph; Command.PARENT = the graph above
    resume=...,       # for interrupt() (Phase 8)
)
```

### 1.1 `update` only — write state, continue normally

```python
def writer(state):
    return Command(update={"note": state["note"] + "!"})
```

Equivalent to `return {"note": ...}`.

### 1.2 `goto` in the same graph — jump to a sibling

```python
def a(state):
    return Command(goto="b", update={"note": "a ran"})

def b(state):
    return {"note": state["note"] + "|b ran"}
```

`a` → `b` → `END`. The `update` is applied at the same time as the jump.

### 1.3 `graph=Command.PARENT` — jump to the graph *above*

This is the one that matters for multi-agent handoffs, and it is the
subtlest.

```python
Command(graph=Command.PARENT, goto="billing", update={...})
```

> **Why is it needed?** Because `create_agent` compiles to a **nested
> graph**. A `goto` issued inside the agent is resolved *inside that nested
> graph*, where your `billing` node does not exist.

See trap 1 below.

### 1.4 `update` MUST contain a matching `ToolMessage`

If a **tool** returns a `Command`, the update must include a `ToolMessage`
whose `tool_call_id` matches the tool call:

```python
@tool
def hand_off(question: str, tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
    return Command(
        graph=Command.PARENT,
        goto="billing",
        update={
            "messages": [
                ToolMessage(content=f"handoff: {question}",
                            tool_call_id=tool_call_id, name="hand_off")
            ]
        },
    )
```

Why? Because the model asked for a tool call and must receive a tool
result. LangGraph enforces the invariant. See trap 2.

> Note: `tool_call_id` must be annotated `Annotated[str, InjectedToolCallId]`
> — the bare class does not work. See trap 3.

---

## 2. `Send` — parallel fan-out

```python
from langgraph.types import Send

def fanout(state):
    return [
        Send("worker", {"task": t, "messages": state["messages"]})
        for t in state["plan"]
    ]

g.add_conditional_edges("planner", fanout, ["worker"])
```

Every `Send` produced by one node runs in the **same superstep**,
concurrently. That is where the parallelism comes from (`ex12` measured
~3.9x with four branches).

**`Send` semantics you must know:**

1. The payload **is** the node's input. It does not merge with the graph
   state.
2. The payload **bypasses `input_schema`** (L02 rule 2). Build it from
   explicit fields.
3. The target node's writes are merged back into the state with the
   channel's reducer — so the target channel needs a **merging** reducer
   or the branches overwrite each other.

```python
results: Annotated[list[dict], lambda a, b: a + b]   # append
```

---

## 3. The four traps

`ex05` reproduces all four, with the exact error messages.

### Trap 1 — a plain `goto` from inside `create_agent` silently does nothing

```python
@tool
def hand_off(tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
    return Command(goto="billing", update={...})      # NO graph=Command.PARENT
```

What you see in the log:

```
Task tools with path ('__pregel_push', 0, False) wrote to unknown channel
branch:to:billing, ignoring it.
```

And then the agent loops until the recursion limit. No exception, no
explanation — just a warning line and a hang.

**Why:** `create_agent` is a nested graph. `goto="billing"` looks for
`billing` in the *agent's internal* graph (its nodes are `model` and
`tools`), does not find it, and drops the instruction.

**Fix:** `graph=Command.PARENT`.

> **General rule:** a `goto` target must be a node in the graph where the
> `Command` is *resolved*. If the `Command` comes from inside a nested
> agent, you need `Command.PARENT`.

### Trap 2 — `Command(update=...)` without a matching `ToolMessage`

```
ValueError: Expected to have a matching ToolMessage in Command.update for
tool 'write_note', got: [AIMessage(content='NOTE: hi', ...)].
```

The model requested a tool; it must get a tool result back. Put a
`ToolMessage(tool_call_id=<the id>)` in the update.

### Trap 3 — `InjectedToolCallId` without `Annotated`

```python
@tool
def hand_off(tool_call_id: InjectedToolCallId) -> Command:   # WRONG
```

The error is swallowed into the tool message (see trap 4's cousin below):

```
Error invoking tool 'hand_off' with kwargs {} with error:
 tool_call_id: Field required
```

The correct form:

```python
from langchain_core.tools import InjectedToolCallId

@tool
def hand_off(tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
```

### Trap 4 — `create_agent` ships with `recursion_limit = 9999`

From the `create_agent` source (`langchain/agents/factory.py`):

```python
config: RunnableConfig = {"recursion_limit": 9_999}
```

A runaway loop therefore makes **~9999 LLM calls** before anything stops
it. That is not a safety net; it is a firehose.

**Always pass an explicit limit:**

```python
app.invoke(inputs, {"recursion_limit": 30})
```

And put a hard cap on the agent itself (L10):

```python
create_agent(model, tools=tools,
             middleware=[ModelCallLimitMiddleware(thread_limit=8, exit_behavior="end")])
```

---

## 4. Tool errors: swallowed or raised?

This is a subtle one worth getting exactly right, because it decides
whether your graph survives a flaky API.

| the error | what happens |
|---|---|
| **Tool invocation error** (bad/missing arguments, schema validation) | turned into ToolMessage **text**; the model sees it and can retry |
| **any other exception raised inside the tool body** | **propagates** and crashes the graph |

Verified in `ex14`:

```
1a. bad arguments      -> "Error invoking tool 'needs_int' with kwargs ...
                            tool_call_id: Field required"   (swallowed, recoverable)
1b. RuntimeError in the tool body -> RuntimeError: upstream 503   (graph dies)
```

**The fix for 1b is inside the tool:**

```python
@tool
def safe_tool(x: str) -> str:
    """Never raises."""
    try:
        return call_service(x)
    except Exception as exc:
        return f"ERROR: {exc}. Tell the user the service is down."
```

An agent cannot recover from a crash, but it *can* recover from a message.

---

## 5. `Command` and `Send` side by side

| | `Command` | `Send` |
|---|---|---|
| purpose | "do this, then go there" | "run these, all at once" |
| who runs it | a node or a tool | a conditional-edge function |
| payload | `update` (state writes) | `arg` (the target's entire input) |
| state merge | the target's normal reducer | the target's normal reducer |
| schema filtering | `update` is filtered by the parent schema (L02 rule 3) | payload is **not** filtered (L02 rule 2) |
| crosses a nested agent? | yes, with `graph=Command.PARENT` | no — `Send` is a graph-level construct |

**Combining them** — this is the fan-out/fan-in shape:

```python
def fanout(state):
    return [Send("worker", {"task": t}) for t in state["plan"]]

def worker(state):
    return {"results": [f"done: {state['task']}"]}   # append reducer
```

---

## 6. A checklist for every routing decision

- [ ] Does the `goto` target exist **in the graph where the Command resolves**?
      (Inside a nested agent → use `Command.PARENT`.)
- [ ] If the `Command` comes from a tool, does the update contain a
      `ToolMessage` with the right `tool_call_id`?
- [ ] Is `tool_call_id` annotated `Annotated[str, InjectedToolCallId]`?
- [ ] Did I pass an explicit `recursion_limit`?
- [ ] Does the channel my branches write to have a **merging** reducer?
- [ ] Is my `Send` payload built from explicit fields (not `dict(state)`)?
- [ ] Do I have a `ModelCallLimitMiddleware` on every agent?

---

## 7. Run it

```bash
PYTHONPATH=examples .venv/bin/python examples/ex05_command_and_send.py
```

The output shows all three `Command` forms working, a three-branch `Send`
fan-out, and each of the four traps with its real error message.

---

## What you should be able to do now

- Write any routing in LangGraph using only `Command` and `Send`.
- Explain, from memory, why `graph=Command.PARENT` is needed for handoffs.
- Diagnose "unknown channel branch" and "expected a matching ToolMessage".
- Explain why `recursion_limit=9999` is a trap and what to do instead.
- Predict whether a tool error will crash your graph or not.

**Next:** L04 — the modern supervisor: agents-as-tools. This is the pattern
that replaces the abandoned `langgraph-supervisor` package.
