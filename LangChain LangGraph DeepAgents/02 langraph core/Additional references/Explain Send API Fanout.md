# LangGraph `Send` API — Dynamic Fan-Out

The `Send` API in LangGraph lets you dynamically create multiple executions of the same node, each with different input data, at runtime. It is especially useful for parallel processing, map-reduce workflows, and orchestrator-worker agents.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub+1



Let's understand it from the basics.

## 1. First, understand the problem `Send` solves

Imagine you're building an AI application that creates a research report.

The user asks:

> Research LangGraph, RAG, and MCP, then write a report covering all three topics.

Your graph might look like this:

Orchestrator

Decides which tasks are needed

Worker 1

Research LangGraph

Worker 2

Research RAG

Worker 3

Research MCP

Synthesizer

Combines the research into one report

Notice that all three workers do the same kind of work, but each receives a different topic.

Now imagine that the user's request contains 2, 10, 100, or an unknown number of topics.

You don't want to manually create a different graph node for every topic. You want one reusable worker node that LangGraph can invoke as many times as needed.

That is the problem `Send` solves.

## 2. What does dynamic fan-out mean?

Let's break down the terminology.

- Fan-out: One execution branches into multiple tasks.
- Dynamic: The number of tasks is decided at runtime, based on the data available.
- Worker: A node that performs one unit of work.
- Fan-in: The results from multiple tasks come back together for the next stage.

The key idea is that LangGraph can discover how many worker executions to create while the graph is running, rather than requiring you to define every branch in advance.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub



Compare the two approaches:

Static fan-out

You define the branches beforehand:

```
builder.add_edge("start", "worker_a")builder.add_edge("start", "worker_b")
```

Useful when you already know which branches are needed.

Dynamic fan-out with `Send`

You create the branches from the data at runtime:

```
return [    Send("worker", {"item": item})    for item in state["items"]]
```

Useful when the number of items is determined only while the graph is running.

## 3. Understand the `Send` syntax

In Python, import it like this:

```
from langgraph.types import Send
```

The basic structure is:

```
Send("node_name", custom_input)
```

There are two important arguments.

| Argument       | Meaning                                              |
| -------------- | ---------------------------------------------------- |
| `"node_name"`  | Which existing graph node should execute?            |
| `custom_input` | What input should that particular execution receive? |

For example:

```
Send("research_worker", {"topic": "LangGraph"})
```

This means:

> Ask LangGraph to run the `research_worker` node with `{"topic": "LangGraph"}` as its input.

And this:

```
Send("research_worker", {"topic": "RAG"})
```

sends different input to the same node.

`Send` is not itself a worker or an LLM call. It is an instruction to LangGraph about which node to run and what data to give it.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub



## 4. Complete working example

Let's build a small graph that generates a joke for every subject, then combines the results.

The subjects could be `cats`, `dogs`, and `robots`. Our graph will create three executions of the same worker node.

### Step 1 — Define the state

```
from typing import Annotatedfrom typing_extensions import TypedDictimport operatorclass OverallState(TypedDict):    subjects: list[str]    jokes: Annotated[list[str], operator.add]    summary: strclass WorkerState(TypedDict):    subject: str    jokes: Annotated[list[str], operator.add]
```

There are two state schemas here.

`OverallState` describes the graph's overall data:

- `subjects`: all the subjects to process.
- `jokes`: the collected results.
- `summary`: the final combined output.

`WorkerState` describes what each worker needs:

- `subject`: the one subject assigned to that worker.
- `jokes`: the result produced by that worker.

Why can the worker receive a `subject` even though the overall state has a `subjects` list? Because `Send` lets us provide a custom input state to an individual execution.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub



### Step 2 — Write the fan-out function

```
from langgraph.types import Senddef dispatch_workers(state: OverallState) -> list[Send]:    return [        Send("generate_joke", {"subject": subject})        for subject in state["subjects"]    ]
```

Let's expand this line by line:

```
for subject in state["subjects"]
```

This iterates over the subjects:

```
["cats", "dogs", "robots"]
```

For each subject, it creates a `Send` instruction:

```
Send("generate_joke", {"subject": "cats"})Send("generate_joke", {"subject": "dogs"})Send("generate_joke", {"subject": "robots"})
```

The function returns a list of three instructions. LangGraph uses them to schedule three executions of the `generate_joke` node.

The important part is that you didn't write three workers. You wrote one worker and a function that assigns it three tasks.

### Step 3 — Write the worker node

```
def generate_joke(state: WorkerState) -> dict:    subject = state["subject"]    return {        "jokes": [f"Joke about {subject}"]    }
```

Each execution receives its own input.

| Worker execution | Input subject | Output                  |
| ---------------- | ------------- | ----------------------- |
| 1                | `cats`        | `["Joke about cats"]`   |
| 2                | `dogs`        | `["Joke about dogs"]`   |
| 3                | `robots`      | `["Joke about robots"]` |

These executions can run in parallel, subject to the runtime's available resources and limits.

### Step 4 — Write the fan-in node

```
def summarize(state: OverallState) -> dict:    return {        "summary": "\n".join(state["jokes"])    }
```

This node reads the collected jokes and combines them into one string.

### Step 5 — Connect and compile the graph

```
from langgraph.graph import StateGraph, START, ENDbuilder = StateGraph(OverallState)builder.add_node("generate_joke", generate_joke)builder.add_node("summarize", summarize)# Dynamically send work to the worker node.builder.add_conditional_edges(START, dispatch_workers)# Collect worker results, then summarize.builder.add_edge("generate_joke", "summarize")builder.add_edge("summarize", END)graph = builder.compile()
```

Notice this line:

```
builder.add_conditional_edges(START, dispatch_workers)
```

The function `dispatch_workers` decides the destinations at runtime. Because it returns `Send` objects, it can send work to the same node multiple times with different inputs.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub



### Step 6 — Run the graph

```
result = graph.invoke({    "subjects": ["cats", "dogs", "robots"],    "jokes": [],    "summary": "",})print(result["summary"])
```

Conceptual output:

```
Joke about cats
Joke about dogs
Joke about robots
```

The exact ordering of parallel results should not be relied upon unless you explicitly preserve and sort by an identifier or position.

## 5. How the graph executes, step by step

## 1

Dispatch

The graph starts with the three subjects. `dispatch_workers` creates three `Send` instructions.

Data: cats, dogs, robots

## 2

Fan-out

LangGraph schedules three executions of `generate_joke`, each with its own `subject` input.

One node definition, three task executions.

## 3

Collect results

The worker executions return their jokes. LangGraph merges the updates into the shared `jokes` state key.

## 4

Fan-in and summarize

After the worker stage completes, `summarize` receives the collected jokes and creates the final summary.

## 6. A crucial concept: reducers

Look again at this declaration:

```
jokes: Annotated[list[str], operator.add]
```

This is important when using `Send` for parallel work.

Imagine all three workers return a state update like this:

```
{"jokes": ["Joke about cats"]}{"jokes": ["Joke about dogs"]}{"jokes": ["Joke about robots"]}
```

All three are trying to update the same state key, `jokes`.

Without an appropriate reducer, multiple writes to the same key in a single execution step can cause a concurrent-update error. With `operator.add`, LangGraph combines the lists rather than replacing one result with another.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub



Conceptually:

```
[] + ["Joke about cats"]   + ["Joke about dogs"]   + ["Joke about robots"]
```

becomes a list containing all three jokes.

Remember: `Send` creates the parallel work. A reducer determines how the results are merged.

They solve two different problems.

## 7. `Send` vs. conditional edges vs. `Command`

These APIs are related, but their jobs differ.

| API                       | Main purpose                                                              |
| ------------------------- | ------------------------------------------------------------------------- |
| `add_edge()`              | Define a fixed transition between nodes.                                  |
| `add_conditional_edges()` | Choose the next destination based on runtime logic.                       |
| `Send()`                  | Create an execution of a target node with custom input.                   |
| `Command()`               | Combine a state update with a routing decision, using `goto` when needed. |

A conditional edge can return a single destination, or it can return multiple `Send` instructions. Use `Send` when you need multiple executions with different inputs—not simply because you need an `if/else` branch.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub



## 8. When should you use `Send`?

Use it when the number of tasks or their inputs are determined at runtime.

Common examples include:

- RAG: Process multiple documents or chunks independently.
- Research agents: Assign one worker to each research question or section.
- Enterprise AI integrations: Query multiple relevant systems or process multiple records.
- Batch processing: Run the same transformation on an arbitrary number of items.
- Map-reduce: Map individual items to parallel workers, then reduce the results.

For your LangGraph learning, the most important use case is the orchestrator-worker pattern: the orchestrator decides what work is required, `Send` dispatches tasks to reusable worker nodes, and a downstream node combines their results. This is one of LangGraph's built-in workflow patterns.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub



### The mental model to remember

`Send` = “Run this node once for this particular piece of work.”

Return a list of `Send` objects to create multiple task executions. Use reducers to combine parallel state updates, then connect the graph to a downstream node that uses the collected results.

That is the essence of dynamic fan-out in LangGraph.
