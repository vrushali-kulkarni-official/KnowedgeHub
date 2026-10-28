In LangGraph, the Pregel runtime is the execution engine that runs your graph. It decides which nodes should execute, runs them in the correct order (or in parallel when possible), updates the graph's state, and repeats until the workflow finishes.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub



Think of it as the engine behind LangGraph. You define the workflow; Pregel makes it run.

## 1. First, understand the basic idea

Imagine you are building an AI chatbot that answers questions using your company's documents.

User asks a question

"What is our leave policy?"

Node 1: Understand the question

Determine what information is needed.

Node 2: Retrieve documents

Search the company knowledge base.

Node 3: Generate an answer

Use the retrieved information to answer.

Return the answer

Here is what each LangGraph component means:

| Component      | Meaning                                                                               |
| -------------- | ------------------------------------------------------------------------------------- |
| Node           | A function or unit of work, such as searching documents or calling an LLM.            |
| Edge           | A connection defining where execution can go next.                                    |
| State          | The data the workflow carries, such as the question, retrieved documents, and answer. |
| Pregel runtime | The engine that executes the nodes and manages the progression of the workflow.       |

LangGraph's graph API lets you define nodes, edges, and state. Compiling the graph gives you an executable graph powered by its runtime.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub

+1



## 2. How does the Pregel runtime work?

The Pregel runtime follows an execution model with three phases: Plan, Execute, and Update. One complete cycle through these phases is often called a superstep.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub



### Phase 1 — Plan

The runtime decides which nodes are ready to execute based on the graph's flow and the state updates from the previous step.

### Phase 2 — Execute

The selected nodes run. Independent nodes can execute in parallel. Their updates are not exposed to other nodes running in the same superstep.

### Phase 3 — Update

The runtime applies the results to the appropriate state channels. The new values become available to nodes in the next superstep.

The cycle repeats until no more nodes are ready to execute or a configured execution limit is reached.

### A simple example of parallel execution

Suppose a node determines that a user's question needs two kinds of information:

- Node A searches the HR knowledge base.
- Node B searches the company policy database.

The runtime can schedule both nodes in the same execution phase.

Plan: schedule Node A and Node B

Node A

Search HR documents

Node B

Search policy database

Update state

Make both results available for the next step.

Next node combines the results into an answer

The key detail is that Node A does not automatically see Node B's newly written result while both are still executing in the same superstep. Their updates are applied between steps. This execution boundary makes the workflow's data flow more predictable.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub



## 3. Where does Pregel appear in your Python code?

You generally do not need to create a Pregel runtime yourself. You use the higher-level LangGraph APIs.

Here is a minimal example:

```
from typing_extensions import TypedDictfrom langgraph.graph import StateGraph, START, ENDclass State(TypedDict):    question: str    answer: strdef answer_question(state: State) -> dict:    return {        "answer": f"You asked: {state['question']}"    }# 1. Define the graphbuilder = StateGraph(State)# 2. Add a nodebuilder.add_node("answer_question", answer_question)# 3. Define its execution pathbuilder.add_edge(START, "answer_question")builder.add_edge("answer_question", END)# 4. Compile into an executable graphgraph = builder.compile()# 5. Run itresult = graph.invoke({
```

Expected output:

```
{    "question": "What is Pregel?",    "answer": "You asked: What is Pregel?"}
```

Here is what happens:

1. `StateGraph(State)` defines the graph and its state schema.
2. `add_node()` registers the function that performs the work.
3. `add_edge()` defines the path through the graph.
4. `compile()` creates the executable graph, which uses LangGraph's Pregel runtime.
5. `invoke()` asks that runtime to execute the graph with the supplied input.

These are the standard Graph API steps documented by LangGraph.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub



## 4. What responsibilities does the runtime have?

The runtime is more than an ordinary function calling other functions.

| Responsibility                        | What it means                                                                                              |
| ------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Scheduling                            | Determines which nodes are ready to run.                                                                   |
| Execution                             | Runs selected nodes, concurrently when appropriate.                                                        |
| State coordination                    | Applies node updates so later steps can use them.                                                          |
| Loop progression                      | Continues through cycles until the workflow stops.                                                         |
| Error and execution control           | Coordinates failures, configured timeouts, and execution limits.                                           |
| Streaming and persistence integration | Supports capabilities such as observing progress and saving resumable state when appropriately configured. |

LangGraph provides streaming, persistence, and durable-execution capabilities around graph execution; these are capabilities to configure and use, not a promise that every graph automatically persists its state.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub

+1



## 5. Is Pregel the same thing as LangGraph?

No. Think of the relationship like this:

Your application

Business logic, LLM calls, tools, and data

LangGraph API

StateGraph, nodes, edges, conditional routing

Pregel runtime

Scheduling and executing the workflow

The name comes from Google's Pregel graph-computation algorithm, whose model inspired LangGraph's execution approach. It is not an LLM, a separate AI model, or another package you must independently install.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub



## 6. How does this relate to `create_agent`?

This is especially important when learning LangChain and LangGraph:

- `create_agent` is a higher-level API for creating an agent with model and tool-calling behavior.
- LangGraph provides the underlying orchestration capabilities for stateful agent execution.
- Pregel is the execution engine that runs compiled LangGraph workflows.

LangChain's agents are built on LangGraph, so you can use the convenient agent API without having to build a graph manually. When you need more control over branching, loops, state, or human approval, the lower-level graph API becomes useful.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub



The key idea to remember: You design the graph; Pregel runs it. It plans which nodes should execute, executes them, applies their state updates, and repeats until the workflow is complete.

Official reference: [LangGraph runtime — Pregel](https://docs.langchain.com/oss/python/langgraph/pregel?utm_source=chatgpt.com).
