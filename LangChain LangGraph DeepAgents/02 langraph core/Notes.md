# L01 - Graph thinking

## Pregel
The engine that executes the nodes and manages the progression of the workflow.

### Supersteps

The Pregel runtime follows an execution model with three phases: Plan, Execute, and Update. 
One complete cycle through these phases is often called a superstep.

```
#### Phase 1 — Plan

The runtime decides which nodes are ready to execute based on the graph's flow and the state updates from the previous step.

#### Phase 2 — Execute

The selected nodes run. Independent nodes can execute in parallel. Their updates are not exposed to other nodes running in the same superstep.

#### Phase 3 — Update

The runtime applies the results to the appropriate state channels. The new values become available to nodes in the next superstep.
```


`compile()` creates the executable graph, which uses LangGraph's Pregel runtime.

---

## Functional API

The key idea is that you write ordinary Python control flow instead of explicitly building a graph of nodes and edges. LangGraph wraps it so it can be checkpointed, streamed and interrupted.

LangGraph's Functional API lets you keep familiar Python code while adding workflow execution, checkpointing, streaming, and human-in-the-loop capabilities.


- `@task` marks a function as a task that LangGraph can execute and whose result you can retrieve.
- `@entrypoint()` marks a function as the main entry point of a workflow.
- `.result()` retrieves the output of a task.

## The five-step process

#### Step 1: Map the process into discrete steps
Each step becomes a **node**. A node should do only *one* thing.

#### step-2-decide-what-each-step-needs
For each node, classify it:

- LLM step 
- Data step 
- Action step 
- User-input step

#### Step 3 — Design the state
State is the **shared memory** of the graph. The question for every candidate field:

> **Does this need to survive across steps?**
>
> - Yes → it belongs in state.
> - No, and it's cheap to recompute → compute it on demand.
> - No, and it's expensive to recompute → state (or a cache).

#### Step 4 — Build the nodes
create the node as a function
Note: nodes return **only the keys they change**. LangGraph merges that
partial update into state using the key's reducer


#### Step 5 — Wire the edges
- `add_edge(START, "a")` — where does it begin?
- `add_edge("a", "b")` — unconditional step
- `add_conditional_edges("a", router)` — decide at runtime
- `add_edge("b", END)` — where does it finish?


---


# L02 · Your first StateGraph

## LangGraph skeleton
Every LangGraph program has the same skeleton:

```python
from langgraph.graph import StateGraph, START, END

builder = StateGraph(State)      # 1. describe the state
builder.add_node("a", node_a)    # 2. add the nodes
builder.add_edge(START, "a")     # 3. wire the edges
builder.add_edge("a", END)
graph = builder.compile()        # 4. compile
result = graph.invoke(input)     # 5. run
```

#### Reducers
The node returns only the key it changed. 
LangGraph then merged that partial update into the existing state.
That merge behaviour is the whole of **reducers**

--- 

## Components: 

### add_node — the full signature (v1.2)

```python
builder.add_node(
    "name",                 # the node's name in the graph
    action,                 # the function to run
    *,
    defer=False,            # run only after the whole superstep is otherwise done
    metadata=None,          # arbitrary metadata for tracing
    input_schema=None,      # restrict what this node can read
    retry_policy=None,      # RetryPolicy(...)  -> L12
    cache_policy=None,      # CachePolicy(...)   -> L12
    error_handler=None,     # recovery branch after retries exhaust -> L12
    destinations=None,      # (("a","b"),) -> allowed targets for Command routing
    timeout=None,           # float | timedelta | TimeoutPolicy -> L12
)
```

Use snake_case, no spaces to name the node

### add_edge — unconditional transitions

```python
builder.add_edge(["a", "b"], "c")   # c runs after BOTH a and b finish
```

Two convenience shortcuts:

```python
builder.set_entry_point("first_node")   # == add_edge(START, "first_node")
builder.set_finish_point("last_node")   # == add_edge("last_node", END)
```

---

### add_sequence — the fast path for linear graphs

```python
builder = StateGraph(State)
builder.add_sequence([node_a, node_b, node_c])   # a -> b -> c
```

### compile() 

```python
graph = builder.compile(
    checkpointer=None,      # persistence (L06)
    store=None,             # long-term memory store (L07)
    cache=None,             # node cache (L12)
    interrupt_before=None,  # debugging aid
    interrupt_after=None,   # debugging aid
    debug=False,
    name=None,              # graph name (shows up in traces/Studio)
    transformers=None,      # stream transformers
)
```

 
`compile()` returns a `CompiledStateGraph`, which is a **Runnable**. That
means it composes with the rest of LangChain:

```python
from langchain_core.runnables import RunnableLambda

chain = RunnableLambda(lambda x: x["name"]) | graph
```

and it can be used as a node inside another graph (L11) or as a tool.


---

# L03 · State & schema types

## Types of state

- TypedDict:
```python
from typing_extensions import TypedDict

class State(TypedDict):
    ticket: str
    category: str
    doc_snippets: list[str]
```

- Pydantic `BaseModel`:
```python
from pydantic import BaseModel, Field

class State(BaseModel):
    ticket: str
    category: str = "unknown"
    doc_snippets: list[str] = Field(default_factory=list)
```

- dataclass:
```python
from dataclasses import dataclass, field

@dataclass
class State:
    ticket: str
    category: str = "unknown"
    doc_snippets: list[str] = field(default_factory=list)
```


## MessagesState
LangGraph ships `MessagesState` as a prebuilt state for chat:
```python
class MessagesState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
```


## Input schema vs output schema vs internal schema

By default a graph has **one** schema: what goes in is what comes out.
```python
builder = StateGraph(OverallState)     # one schema
```

But you can split it into three:
```python
builder = StateGraph(
    OverallState,          # internal schema - what nodes exchange
    input_schema=InputState,    # what invoke() accepts
    output_schema=OutputState,  # what invoke() returns
)
```

example:

```python
class InputState(TypedDict):
    question: str

class OutputState(TypedDict):
    answer: str

class OverallState(InputState, OutputState):
    """Internal schema: nodes see both question and answer."""

def answer_node(state: InputState) -> OverallState:
    return {"answer": "bye", "question": state["question"]}
```


##  Private state
Sometimes two nodes need to exchange a big intermediate value that nobody else should see and nobody should get back.

```python

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

```


---


# L04 · Reducers

## State is a set of independent *channels*
```
State
├── messages    (channel, reducer = add_messages)
├── errors      (channel, reducer = operator.add)
├── draft       (channel, reducer = LastValue / overwrite)
└── needs_human (channel, reducer = LastValue / overwrite)
```

- `draft`'s reducer: **overwrite** → `draft = "hello"`
- `messages`' reducer: **append** → `messages = [...existing, new]`

A reducer is just a function:

```python
def reducer(left, right) -> new_value
```

where `left` is the current channel value and `right` is what the node just wrote.

if 2 nodes try to update the same node in parallel in 1 superstep then you get → `InvalidUpdateError: At key 'draft': Can receive only one value per step.`

## Annotated[list, operator.add]` — the append reducer

The most common reducer you will write is "append".

```python
def append(left: list[str], right: list[str]) -> list[str]:
    """Combine two list updates by concatenation."""
    return left + right

class State(TypedDict):
    snippets: Annotated[list[str], append]
```

### add_messages
`add_messages` is LangGraph's built-in reducer for chat message lists. 

```python
from langgraph.graph.message import add_messages   # <-- the canonical import

class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
```

#### What `add_messages` does beyond appending:

1. **Assigns IDs.** Every message without an `id` gets a deterministic id.
  
2. **Deduplicates by ID.** Writing a message with an ID that already exists *replaces* it instead of appending a duplicate.

3. **Handles `RemoveMessage`.** Writing `RemoveMessage(id=...)` deletes that message from the list.

4. **Accepts shorthand.** You can write `{"role": "user", "content": "hi"` and it becomes a `HumanMessage`.

5. **Coerces to message objects.** Strings, dicts, and tuples all work.


### Overwrite` — bypassing a reducer on purpose

Sometimes you genuinely want to *replace* an accumulated list, not append.

```python
from langgraph.types import Overwrite

def reset_events(state):
    return {"events": Overwrite([])}
```

`Overwrite` tells LangGraph: "ignore the reducer for this write, set the
channel to exactly this."


## Most Common errors

#### Silent message loss
if no reducer, then default is *overwrite*. 
The second write replaces the first. No error, no warning. Your agent "forgets" things.

#### The `errors` merge trap
```python
# node A returns {"errors": ["bad sql"]}
# node B returns {"errors": []}
# -> state["errors"] == ["bad sql"]   NOT []
```

A node that *clears* the error list with `{"errors": []}` does **not** clear
it — the reducer concatenates, so `["bad sql"] + [] == ["bad sql"]`.

#### A reducer that silently ignores write

```python
def merge_dicts(left: dict, right: dict) -> dict:
    return left        # BUG: right is discarded
```

No error. The node's write vanishes.

#### `right` is `None`

```python
def merge(left, right):
    return left + right      # TypeError if right is None
```

---

## The reducer decision table

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

## Rules of thumb

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


---


# L05 · Routing: conditional edges and `Command`


## add_conditional_edges
```python
builder.add_conditional_edges(
    source,                 # the node AFTER which the branch happens
    path,                   # callable | Runnable -> branch name(s)
    path_map=None,          # dict[str, str] | list[str] | None
)
```

### The router

```python
def route(state: State) -> str:
    return "search_docs"     # a BRANCH NAME
```

It receives the state and returns one branch name (or a list of them for a fan-out).

### path_map

```python
builder.add_conditional_edges(
    "classify",
    route,                   # returns "question" / "bug" / "billing"
    {
        "question": "search_docs",   # business label -> node name
        "bug": "file_bug",
        "billing": "escalate",
    },
)
```

### The router can be a Runnable

```python
from langchain_core.runnables import RunnableLambda

builder.add_conditional_edges(
    "classify",
    RunnableLambda(lambda s: "search_docs" if s["score"] > 0.8 else "file_bug"),
)
```

### A router can return a list (fan-out)

```python
def route(state) -> list[str]:
    return ["search_docs", "notify"]     # both run, in parallel
```


---

## Command

```python
from langgraph.types import Command

def classify(state: State) -> Command:
    category = do_classification(state)
    return Command(
        update={"category": category},   # state update
        goto="search_docs",              # where to go next
    )
```

#### Full signature

```python
Command(
    *,
    graph: str | None = None,   # route to a node in a NAMED SUBGRAPH
    update: Any | None = None,  # the state update
    resume: dict | Any | None = None,  # value to deliver to an interrupt()
    goto: Send | Sequence[Send | N] | N = (),  # next node(s)
)
```


#### Old Style (add_conditional_edges) Vs New Style (Command)

**OLD STYLE - add_conditional_edges:**

```python
# OLD STYLE - two mechanisms, two places
def classify(state):
    return {"category": do_classification(state)}

def route(state):
    return "search_docs" if state["category"] == "question" else "file_bug"

builder.add_node("classify", classify)
builder.add_conditional_edges("classify", route, {...})
```

**MODERN STYLE - Command:**

```python
# MODERN STYLE - one function, one return
def classify(state) -> Command:
    category = do_classification(state)
    goto = "search_docs" if category == "question" else "file_bug"
    return Command(update={"category": category}, goto=goto)
```

#### Typed destinations — static checking

The type parameter tells your editor and type-checker which nodes are legal targets

```python
from typing import Literal

def classify(state: State) -> Command[Literal["search_docs", "file_bug"]]:
    ...
```

#### destinations on `add_node`

you can also declare the allowed targets on the node itself:
```python
builder.add_node(
    "classify",
    classify,
    destinations=("search_docs", "file_bug"),
)
```

#### Routing with `Send` (dynamic fan-out)
 
```python
from langgraph.types import Send

def fan_out(state) -> Command:
    return Command(goto=[Send("process", {"doc": d}) for d in state["docs"]])
```


#### Routing inside a named subgraph

```python
return Command(graph="worker", goto="next_step")
```

`graph=` names the subgraph to route into; `goto=` names the node *inside* that subgraph


#### Command(resume=...)
When a graph is paused by `interrupt()`, the resuming call supplies the value:

```python
# the interrupt() returns "approved"
graph.invoke(Command(resume="approved"), config)   
```

Used for human-in-the-loop


#### Command(update={...})
`Command(update={...})` goes through the **same reducers** as a normal node return.

```python
return Command(update={"messages": [AIMessage("hi")]})
```

---

## Loops

```python
def should_continue(state) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and not last.tool_calls:
        return "end"
    return "tools"

builder.add_conditional_edges(
    "agent", should_continue, {"end": END, "tools": "tools"}
)
```


---


# L06 · Config, threads, persistence and time travel


## RunnableConfig` — the runtime control panel

Every `invoke`/`stream` accepts a `config`:
```python
graph.invoke(
    {"question": "hi"},
    config={"configurable": {"thread_id": "user-42"}, "recursion_limit": 25},
)
```



## Threads and checkpointers

```python
from langgraph.checkpoint.memory import InMemorySaver
config = {"configurable": {"thread_id": "chat-1"}}

graph = builder.compile(checkpointer=InMemorySaver())
graph.invoke({"messages": [HumanMessage("My name is Ada")]}, config)
```

With a checkpointer:

- state is saved after every superstep;
- the same `thread_id` resumes where it left off;
- you can inspect, edit and rewind history.

**`thread_id` is mandatory once you have a checkpointer**

`InMemorySaver` is for tests and demos.
`PostgresSaver` is for production


## Multi-turn conversation

```python
graph = builder.compile(checkpointer=InMemorySaver())
config = {"configurable": {"thread_id": "chat-1"}}

graph.invoke({"messages": [HumanMessage("My name is Ada")]}, config)
graph.invoke({"messages": [HumanMessage("What is my name?")]}, config)
# -> the model remembers "Ada" because it's the same thread
```

Each `invoke` on the same thread **continues** the conversation. 

The`add_messages` reducer appends, so the history accumulates.

New thread = new memory.** Use a new `thread_id` and the model forgets.


##  Inspecting and editing state

### get_state

```python
snapshot = graph.get_state(config)
snapshot.values        # the current state dict
snapshot.next          # tuple of node names that will run next
snapshot.config        # the config of this checkpoint
snapshot.metadata      # step count, writes, source, etc.
snapshot.interrupts    # any pending interrupts
snapshot.tasks         # the tasks in the current superstep
```


### get_state_history` — the timeline

```python
for snap in graph.get_state_history(config):
    print(snap.metadata.get("step"), snap.next, snap.values)
```

Each entry is a checkpoint. 
This is the raw material for time travel.


### `update_state` — write to a thread

```python
graph.update_state(config, {"category": "billing"})
```

This writes a value as if a node had returned it, creating a new checkpoint.

#### Use `update_state` to:
- correct state after a human review;
- seed a thread with initial data;
- patch a value and re-run from there.
 

## Time travel

```python
# 1. find the checkpoint you want
history = list(graph.get_state_history(config))
target = history[2]        # some earlier checkpoint

# 2. re-run from there with a new input
graph.invoke({"messages": [HumanMessage("Actually, say something else")]},
             config=target.config)
```

The graph resumes from that checkpoint with the *new* input, producing a new branch of history.


## Recursion limit

`recursion_limit` bounds the number of **supersteps** in a run.

```python
graph.invoke(input, {"recursion_limit": 5})
```

Default is **10000**. When exceeded:

```
GraphRecursionError: Recursion limit of 5 reached without hitting a stop
condition. You can increase the limit by setting the `recursion_limit` config key.
```

> **Remember:** it counts *supersteps*, not nodes. A fan-out of 10 parallel
> nodes is still one superstep.


### The proactive way to stop: `RemainingSteps`

Rather than waiting for the limit to be hit, you can ask "how many steps do I
have left?" and stop gracefully.

```python
from langgraph.managed import RemainingSteps

class State(TypedDict):
    steps: RemainingSteps
```

`RemainingSteps` is a managed channel: it exists only for the duration of the run and is never persisted.

with `recursion_limit=7`, a node read `state["steps"] == 6` — i.e. the number of supersteps still available.


## interrupt_before` / `interrupt_after`
```python
graph = builder.compile(interrupt_before=["search_docs"])
```

The graph stops *before* running `search_docs`, and the state is checkpointed.
You can then inspect the state, modify it, and resume.


## Durability modes

lets you choose *when* state is written to the checkpointer.

```python
graph.invoke(input, config, durability="sync")     # default-ish
graph.invoke(input, config, durability="async")    # write in the background
graph.invoke(input, config, durability="exit")     # only at the end of the run
```

| Mode    | When state is persisted               | Trade-off                                    |
| ------- | ------------------------------------- | -------------------------------------------- |
| `sync`  | at every superstep, before continuing | safest, slowest                              |
| `async` | at every superstep, in the background | fast; a crash can lose the last step         |
| `exit`  | only when the run finishes            | fastest; no time travel, no interrupt resume |

Use `sync` for anything with human-in-the-loop or side effects. Use `async`
for long, read-only pipelines where losing the last step is acceptable.


---


# Runtime context

`config` is for configurations that are available to everyone to see or edit
llm and chat configurations belong here. Eg: Thread id.

`Runtime context` is not to be seen by anyone and is injected at runtime and the llm never reads it unless explicitly said to.
Application's values adn secrets belong here. Eg. user id.

## The problem

Before LangGraph 0.6, the way to give a node a `user_id` was to stuff it into `config["configurable"]`:

```python
# OLD STYLE
config = {
    "configurable": {
        "thread_id": "chat-1",   # <- framework concern
        "user_id": "u-42",       # <- YOUR concern
        "tenant": "acme",        # <- YOUR concern
    }
}
```

and read it in a node with `config["configurable"]["user_id"]`.

**Why this is bad:**

1. **Easy to leak.** `configurable` is echoed into traces and callbacks.
2. **Easy to mutate.** Nothing stops a node from writing to it.



## The modern answer: `context_schema` + `context=` + `Runtime`

`context_schema` is the definition or declaration of the details that you want in your context that will be injected at the runtime.

`context` is the actual values of the details defined in the context_schema.

`Runtime` is the actual variable/object that is passed to every node and the one that actually holds the `context` values/

**Example:**

```python
from dataclasses import dataclass

# context_schema
@dataclass
class AppContext:
    user_id: str
    tenant: str = "default"

builder = StateGraph(State, context_schema=AppContext)
...

# context
graph.invoke(input, context={"user_id": "u-42", "tenant": "acme"})
```

and in a node:
```python
from langgraph.runtime import Runtime

# Runtime
def my_node(state: State, runtime: Runtime[AppContext]) -> dict:
    user_id = runtime.context.user_id
    ...
```

#### Properties of context

- Read-only
- scoped of the context is only for the current Run
- **never** written into a checkpoint
- Typed Checked (pydantic)
- Injected/passed automatically to every node and every conditional edge


## context schema

#### context_schema vs state_schema
`context_schema` is *not* the same as `state_schema`
The state schema describes a **dict** that tells about all the values of the current node state; 
whereas context schema describes an **object** you access / inject at runtime with`runtime.context.user_id`.


Context schema can defined using:
- @dataclass
- TypedDict
- Pydantic

## Reading context in nodes and conditional edges
passed as the variable runtime with data type Runtime[AppContext]

Example:
```python
def node(state: State, runtime: Runtime[AppContext]) -> dict:
    print(runtime.context.user_id)
    return {...}
```



## The four kinds of "context"

1. **Static runtime context**
- used for: user id, db handle, model, flags, etc
- read only
- Lifetime is only current run
- How to access: `runtime.context` / `context=`

2. **Dynamic runtime context (state)**
- used for: messages, intermediate results, etc
- Can read and write
- Lifetime is only current run
- How to access: `state["key"]`

3. **Cross-conversation memory (store)**
- used for: user preferences, long-term facts
- Can read and write
- Lifetime is across all threads
- `runtime.store` / `get_store()`

4. **LLM context**
- used as: The text in the prompt
- Lifetime is only a single llm call

### The decision rule
- Does it change during a run? → **state**.
- Does it need to survive across conversations? → **store**.
- Is it fixed for the run and read-only? → **context**.
- Is it text for the model?* → the prompt (built from the above, not stored in state


## The Store — cross-conversation memory

The store is the key value database that outlives a single thread.

```python
from langgraph.store.memory import InMemoryStore

store = InMemoryStore()
graph = builder.compile(store=store)
```

In a node:
```python
def node(state, runtime: Runtime[AppContext]) -> dict:
    # namespace = (user_id, "memories") -> per-user partition
    mem = runtime.store.get(("u-42", "memories"), "preferred_style")
    runtime.store.put(("u-42", "memories"), "preferred_style", {"value": "concise"})
    ...
```


#### Checkpointer vs Store

|           | Checkpointer                | Store                           |
| --------- | --------------------------- | ------------------------------- |
| Keyed by  | `thread_id`                 | you choose the namespace + key  |
| Holds     | the graph's state           | arbitrary application data      |
| Lifecycle | one conversation            | long-lived                      |
| Use for   | resuming, time travel, HITL | user memory, preferences, facts |


## All `Runtime` services

- `runtime.context` : typed static context
- `runtime.store` :  the store (if compiled with one)
- `runtime.stream_writer` : push custom data to the stream        
- `runtime.previous` : he previous return value of a Functional API entrypoint
- `runtime.execution_info` : metadata about the current run 
- `runtime.heartbeat()` : signal "still alive" for idle timeouts


---


# L08 · Parallelism, fan-in and `Send`


## Fan-out with plain edges

All three run **concurrently** in superstep 1. 
```python
builder.add_edge(START, "search_web")
builder.add_edge(START, "search_docs")
builder.add_edge(START, "search_db")
```


## Fan-in — the join
runs after **all nodes** have finished.* That is the join.
```python
builder.add_edge(["search_web", "search_docs", "search_db"], "synthesize")
```

### The join needs a reducer

All three search nodes write to the same key (say `results`). They run in the same superstep, so that key receives three writes at once.

```python
class State(TypedDict):
    results: Annotated[list[str], operator.add]   # <-- REQUIRED
```



#### The arrival-order problem
> **Parallel nodes finish in whatever order they finish. The reducer sees
> writes in that order, not in the order you declared the edges.

So order is **not deterministic**.

 So give each parallel node a *different* key, and merge explicitly in the joiner. That is often clearer than relying on a reducer.

```python
class State(TypedDict):
    web: list[str]
    docs: list[str]
```

```python
def synthesize(state):
    return {"answer": build(state["web"] + state["docs"])}   # deterministic order
```


## The `Send` API — dynamic fan-out

`Send` fans out to a **dynamic** set, one task per item.

```python
from langgraph.types import Send

def continue_to_process(state: State) -> list[Send]:
    return [Send("process", {"doc": doc}) for doc in state["documents"]]

builder.add_conditional_edges("split", continue_to_process, ["process"])
```


### using `send` in conditional edge vs in Command
```python
# via a conditional edge (classic)
def route(state): return [Send("process", {"doc": d}) for d in state["docs"]]
builder.add_conditional_edges("split", route, ["process"])

# via Command (modern style, same thing)
def split(state) -> Command:
    return Command(goto=[Send("process", {"doc": d}) for d in state["docs"]])
```



## `defer=True` — run last

A deferred node is scheduled at the **end** of the current superstep, after
all non-deferred nodes have finished. Use it when a node must see every
parallel branch's output.
```python
builder.add_node("summarize", summarize, defer=True)
```


---


# L09 · Async and streaming


##  Async nodes

```python
async def fetch(state: State) -> dict:
    resp = await httpx.AsyncClient().get(state["url"])
    return {"body": resp.text}
```

**The hard rule (verified):** a graph containing an async node **cannot** be run with the synchronous `invoke()`.

Mixing sync and async nodes in one graph is fine — just use the async API.

```python
result = await graph.ainvoke(input)
```



## Streaming — the seven modes
- values
- updates 
- checkpoints
- tasks
- debug
- messages
- custom

```python
StreamMode = Literal['values', 'updates', 'checkpoints', 'tasks', 'debug', 'messages', 'custom']
```


### `values` — the full state after each superstep

```python
for state in graph.stream(inp, stream_mode="values"):
    print(state)
```

Yields the **entire state** after every superstep.


### `updates` — only what changed

```python
for chunk in graph.stream(inp, stream_mode="updates"):
    print(chunk)
# {'node_name': {'key': 'value'}}
```

**The most useful mode for debugging.** The key is the node that ran;  the value is that node's partial update. 

### `checkpoints` — a full `StateSnapshot` per superstep

The streaming form of `get_state_history`(Back to the Future Discussion)

```python
for snap in graph.stream(inp, stream_mode="checkpoints"):
    print(snap.next, snap.values)
```

### `messages` — LLM token streaming

```python
for token, metadata in graph.stream(inp, stream_mode="messages"):
    print(token.content, end="", flush=True)
```

This is the mode you want for a chat UI. It streams **LLM tokens** as they are produced, from any node that calls a chat model.

### `tasks` — task-level events

```python
for task in graph.stream(inp, stream_mode="tasks"):
    print(task)
```

Finer-grained than `updates`: reports individual task starts and results

### `debug` — the firehose

```python
for event in graph.stream(inp, stream_mode="debug"):
    print(event["type"], event.get("step"))
```

Everything: chain starts/ends, task starts/ends, writes. Verbose, but it is where the **step number** lives, which is how you identify superstep boundaries.

### `custom` — your own events

Emitted by `runtime.stream_writer(...)` (or `get_stream_writer()`) inside a node:

```python
def node(state, runtime: Runtime) -> dict:
    runtime.stream_writer({"progress": "50% done"})
    return {...}
```

```python
for event in graph.stream(inp, stream_mode="custom"):
    print(event)
```


## Async streaming

```python
async for mode, chunk in graph.astream(inp, stream_mode=["updates", "messages"]):
    ...
```


## Streaming from a subgraph

Subgraph events are namespaced. Turn them on with `subgraphs=True`:

```python
for ns, chunk in graph.stream(inp, stream_mode="updates", subgraphs=True):
    print(ns, chunk)
```



---


# L10 · The Functional API


## `@task` — a unit of work

```python
from langgraph.func import task

@task
def fetch(url: str) -> str:
    return requests.get(url).text
```

Calling `fetch(url)` **does not execute it immediately**. It returns a
future-like object. You resolve it with `.result()`:

```python
body = fetch(url).result()      # sync
body = await fetch(url)          # async
```


## `@entrypoint` signature

```python
@entrypoint(
    checkpointer=None,      # persistence
    store=None,             # long-term memory
    cache=None,             # node cache
    context_schema=None,    # runtime context (L07)
    cache_policy=None,      # CachePolicy
    retry_policy=None,      # RetryPolicy
    timeout=None,           # float | timedelta | TimeoutPolicy
)
```


### Parameters for entrypoint function

- your own arguments : whatever you pass to `invoke()`
- `previous` : the previous run's return value **for this thread** (needs a checkpointer)
- `runtime` : the `Runtime` object (context, store, stream writer)

```python
@entrypoint(checkpointer=InMemorySaver())
def counter(x: int, previous: int | None) -> int:
    return (previous or 0) + x
```



---

 
# L11 · Subgraphs


## Two ways to add a subgraph

| Pattern                             | When                                                      | State schemas                |
| ----------------------------------- | --------------------------------------------------------- | ---------------------------- |
| **Add the subgraph as a node**      | Parent and subgraph **share state keys**                  | same keys; no wrapper needed |
| **Call the subgraph inside a node** | Schemas are **different**, or you need to transform state | you write the mapping        |




## Pattern A — the subgraph as a node 

```python
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END

class State(TypedDict):
    foo: str
    bar: str

# --- the subgraph ---
def subgraph_node_1(state: State) -> dict:
    return {"bar": "bar-value"}

def subgraph_node_2(state: State) -> dict:
    # reads the parent's 'foo' AND the 'bar' set by node 1
    return {"foo": state["foo"] + state["bar"]}

subgraph = (
    StateGraph(State)
    .add_node("subgraph_node_1", subgraph_node_1)
    .add_node("subgraph_node_2", subgraph_node_2)
    .add_edge(START, "subgraph_node_1")
    .add_edge("subgraph_node_1", "subgraph_node_2")
    .add_edge("subgraph_node_2", END)
    .compile()
)

# --- the parent ---
parent = (
    StateGraph(State)
    .add_node("parent_node_1", lambda s: {"foo": "hi " + s["foo"]})
    .add_node("subgraph_node", subgraph)      # <- the compiled subgraph
    .add_edge(START, "parent_node_1")
    .add_edge("parent_node_1", "subgraph_node")
    .add_edge("subgraph_node", END)
    .compile()
)

print(parent.invoke({"foo": "world", "bar": ""}))
# {'foo': 'hi worldbar-value', 'bar': 'bar-value'}
```



## Pattern B — calling the subgraph inside a node

```python
class SubgraphState(TypedDict):
    bar: str

class ParentState(TypedDict):
    a: str
    out: str

subgraph = (
    StateGraph(SubgraphState)
    .add_node("s1", lambda s: {"bar": "hi " + s["bar"]})
    .add_edge(START, "s1")
    .add_edge("s1", END)
    .compile()
)

def call_subgraph(state: ParentState) -> dict:
    # transform parent state -> subgraph input
    result = subgraph.invoke({"bar": state["a"]})
    # transform subgraph output -> parent update
    return {"out": result["bar"]}

parent = (
    StateGraph(ParentState)
    .add_node("call_subgraph", call_subgraph)
    .add_edge(START, "call_subgraph")
    .add_edge("call_subgraph", END)
    .compile()
)

print(parent.invoke({"a": "world", "out": ""}))
# {'a': 'world', 'out': 'hi world'}
```



## Subgraph persistence — three modes

| Mode                   | `compile(checkpointer=...)` on the subgraph | Behaviour                                                                           |
| ---------------------- | ------------------------------------------- | ----------------------------------------------------------------------------------- |
| **Stateful** (default) | the subgraph's own checkpointer             | the subgraph persists its own state across calls, keyed by the parent's `thread_id` |
| **Stateless**          | `checkpointer=None`                         | the subgraph starts fresh each time it is invoked                                   |
| **Per-call**           | `checkpointer=False`                        | a new checkpointer for each call                                                    |

**The question to ask:** *"should the billing expert subagent remember the
customer's earlier questions, or start fresh each time it's called?"*

- **Start fresh** → stateless. Simplest to reason about; this is the default
  choice for a reusable pipeline.
- **Remember across turns of the same conversation** → stateful.
- **Remember across the whole session but not forever** → per-call.


## How subgraph inherits `thread_id` and config
The subgraph runs with the parent's config, including `thread_id`. That is why a stateful subgraph's memory is scoped to the conversation.

If the subgraph needs a **different** thread (e.g. a long-lived background job), pass an explicit config:

```python
def call_subgraph(state):
    return subgraph.invoke(
        {"x": state["x"]},
        {"configurable": {"thread_id": f"job-{state['job_id']}"}},
    )
```










