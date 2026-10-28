# Understanding `@entrypoint` and `@task` in LangGraph's Functional API

The easiest way to understand these two decorators is to think of a LangGraph workflow as a normal Python function that has been given workflow execution capabilities.

- `@task` marks a function as a task that LangGraph can execute and whose result you can retrieve.
- `@entrypoint()` marks a function as the main entry point of a workflow.
- `.result()` retrieves the output of a task.
- LangGraph can persist workflow state, resume execution, and coordinate tasks using its checkpointing and execution mechanisms.

The key idea is that you write ordinary Python control flow instead of explicitly building a graph of nodes and edges.

This is especially useful when your workflow naturally contains `if` statements, loops, function calls, and error-recovery logic.

## 1. First, understand the problem these decorators solve

Imagine you are building a simple web-research workflow:

1. Fetch a web page.
2. Check whether fetching succeeded.
3. If it failed, try to recover.
4. Return the final page content.

In ordinary Python, you might write:

```
def fetch(url: str) -> str:    ...def recover(body: str) -> str:    ...def workflow(url: str) -> dict:    body = fetch(url)    if "error" in body:        body = recover(body)    return {"body": body}
```

This is perfectly valid Python. So why do we need LangGraph?

Because real AI workflows can run for a long time, call external APIs, invoke LLMs, pause for human approval, and need to resume after interruptions.

LangGraph's Functional API lets you keep familiar Python code while adding workflow execution, checkpointing, streaming, and human-in-the-loop capabilities.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub

+1



## 2. What does `@task` mean?

Look at your code:

```
from langgraph.func import task@taskdef fetch(url: str) -> str:    ...
```

The `@task` decorator tells LangGraph:

> Treat this function as a unit of work managed by the LangGraph runtime.

Think of a task as a step in your workflow.

For example, in an AI application, tasks might perform the following operations:

| Task                 | Responsibility                 |
| -------------------- | ------------------------------ |
| `fetch_document()`   | Retrieve a document from a URL |
| `extract_text()`     | Extract readable text          |
| `embed_text()`       | Generate embeddings            |
| `search_vector_db()` | Retrieve relevant chunks       |
| `call_llm()`         | Call an LLM                    |
| `save_result()`      | Store the result               |

You write each task as an ordinary Python function. LangGraph adds workflow-related behavior around it.

### What changes when you add `@task`?

There are three important differences.

First: it participates in LangGraph execution.

A task is intended to be called from within an entrypoint or a supported StateGraph execution context, rather than directly from your main application code.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub

+1



Second: calling a task gives you a future-like object.

Consider:

```
result = fetch(url)
```

Conceptually, `result` is not yet the actual page content. It is a handle through which you can obtain the task's result.

You retrieve the actual result using:

```
body = result.result()
```

In your original example, these two operations are combined:

```
body = fetch(url).result()
```

Third: tasks can participate in checkpointing.

When checkpointing is enabled, LangGraph can save completed task results and reuse them when resuming a workflow, helping to avoid repeating work unnecessarily. Task inputs and outputs must be serializable when checkpointing is used.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub

+1



## 3. What exactly does `.result()` do?

This is one of the most important pieces to understand.

```
body = fetch(url).result()
```

Break it into two parts:

```
future = fetch(url)body = future.result()
```

The first line requests execution of the task and obtains its future-like handle.

The second line waits for the result and gives you the actual return value.

For example, suppose your task is:

```
@taskdef fetch(url: str) -> str:    return "<html><body>Hello!</body></html>"
```

Then, inside a workflow:

```
future = fetch("https://example.com")body = future.result()print(body)
```

The `body` variable contains:

```
<html><body>Hello!</body></html>
```

Compare this with a normal Python call:

| Normal Python                                                      | LangGraph Functional API                                       |
| ------------------------------------------------------------------ | -------------------------------------------------------------- |
| `body = fetch(url)`                                                | `future = fetch(url)`                                          |
| The function returns its result directly.                          | The task call produces a future-like handle.                   |
| No LangGraph task management is involved.                          | LangGraph manages the task as part of workflow execution.      |
| No automatic workflow checkpointing from the function call itself. | Task results can participate in checkpointing when configured. |

Important: `.result()` is the synchronous way to retrieve the outcome. With asynchronous tasks and an async entrypoint, you normally use `await` instead.

For example:

```
@taskasync def fetch(url: str) -> str:    ...@entrypoint()async def workflow(url: str) -> dict:    body = await fetch(url)    return {"body": body}
```

The asynchronous approach is useful for I/O-heavy work such as HTTP requests and database operations.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://reference.langchain.com\&sz=32)

LangChain Reference

+1



## 4. What does `@entrypoint()` mean?

Now look at your second decorator:

```
from langgraph.func import entrypoint@entrypoint()def workflow(url: str) -> dict:    ...
```

The `@entrypoint()` decorator tells LangGraph:

> This function is the main starting point of the workflow. Manage its execution as a LangGraph workflow.

Think of the entrypoint as the workflow orchestrator.

It determines which tasks run, in what order they are requested, which conditions are evaluated, and what final value is returned.

For your example, the entrypoint manages this logic:

- Execute `fetch`.
- Wait for the fetch result.
- Inspect the result.
- Execute `recover` only if the condition is true.
- Return the final body.

The important distinction is that the entrypoint coordinates the workflow, while individual `@task` functions perform units of work.

### Another important detail

After decorating the function, you generally run the workflow through the LangGraph interface:

```
result = workflow.invoke("https://example.com")
```

You can also use interfaces such as `workflow.stream(...)` or `workflow.ainvoke(...)`, depending on whether you need streaming or asynchronous execution.

You should not treat the decorated entrypoint as an ordinary undecorated function that you simply call with `workflow(url)`. The decorator turns it into a LangGraph workflow object.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://reference.langchain.com\&sz=32)

LangChain Reference

+1



## 5. Now let's execute your entire example step by step

Your code:

```
from langgraph.func import entrypoint, task@taskdef fetch(url: str) -> str:    ...@entrypoint()def workflow(url: str) -> dict:    body = fetch(url).result()    if "error" in body:        body = recover(body).result()    return {"body": body}
```

For this example, assume that `recover` is another function decorated with `@task`, even though its definition was omitted from your snippet.

Here is a concrete illustration:

```
from langgraph.func import entrypoint, task@taskdef fetch(url: str) -> str:    print("Fetching the page...")    # Simplified example: no real HTTP request is made.    return "error: temporary server failure"@taskdef recover(body: str) -> str:    print("Attempting recovery...")    # Simplified example: pretend we successfully recovered.    return "Page content recovered successfully"@entrypoint()def workflow(url: str) -> dict:    body = fetch(url).result()    if "error" in body:        body = recover(body).result()    return {"body": body}
```

You start the workflow like this:

```
result = workflow.invoke("https://example.com")print(result)
```

Let's walk through the execution.

Step 1: Start the workflow

`workflow.invoke("https://example.com")`

The URL becomes the entrypoint's input.

Step 2: Fetch the page

`body = fetch(url).result()`

The workflow requests the fetch task and waits for its result.

Result: `"error: temporary server failure"`

Step 3: Evaluate the condition

`if "error" in body:`

The condition is true, so the workflow enters the recovery branch.

Step 4: Run the recovery task

`body = recover(body).result()`

The workflow waits for recovery to finish and replaces the old `body` value with the recovery result.

Result: `"Page content recovered successfully"`

Step 5: Return the final result

`return {"body": body}`

{"body": "Page content recovered successfully"}

Notice that the `if` statement is just a normal Python `if` statement. You do not need to build a separate conditional graph node yourself.

That's the main advantage of the Functional API.

## 6. What if fetching succeeds?

Suppose `fetch(url)` returns:

```
"Page content downloaded successfully"
```

Then:

```
if "error" in body:    body = recover(body).result()
```

evaluates to false.

The recovery task is not called, and the workflow immediately reaches:

```
return {"body": body}
```

The final output becomes:

```
{    "body": "Page content downloaded successfully"}
```

This illustrates how you can control workflow branching using ordinary Python conditions.

One subtle but important point: your example only checks for the word `"error"` in the returned content. If `fetch()` raises an exception instead of returning an error string, `.result()` raises that exception and the `if` statement is never reached. Handling exceptions requires appropriate exception-handling or retry logic.

## 7. Why are both decorators needed?

Here is the relationship between the two:

## `@entrypoint()`

Manages the overall workflow

### `@task fetch`

Retrieve the content

### Python `if`

Inspect the result

### `@task recover`

Runs only when the condition requires it

### Final result

Returned by the entrypoint

You could compare the roles to a team:

- Entrypoint = manager: coordinates the overall process.
- Task = worker: performs a particular operation.
- `.result()` = collect the worker's result.
- Python `if` statement = decision-making logic.

You do not necessarily need to mark every helper function as a task. Use `@task` for units of work that benefit from LangGraph's task execution behavior, particularly around checkpointing, retries, timeouts, or parallel work.

## 8. Can tasks execute in parallel?

Yes. The future-like task interface is useful when multiple independent tasks can run without waiting for one another.

For example:

```
from langgraph.func import entrypoint, task@taskdef fetch(url: str) -> str:    # Fetch content...    return f"Content from {url}"@entrypoint()def workflow(urls: list[str]) -> list[str]:    futures = [fetch(url) for url in urls]    results = [future.result() for future in futures]    return results
```

Here, the workflow requests all the fetch tasks before collecting their results. That is the basic pattern for parallelizable work. Actual concurrency depends on the execution context and task implementation; this is not a guarantee that every synchronous task runs on its own thread.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub

+1



## 9. What does this have to do with checkpointing and resuming?

This is where LangGraph adds functionality beyond a plain Python workflow.

Suppose a workflow does the following:

1. Fetches a document.
2. Processes the document.
3. Pauses for human approval.
4. Resumes after approval.

Without persistence, you would have to manage the paused workflow's progress yourself.

With a suitable checkpointer configured, LangGraph can persist workflow execution information, including completed task results, and use that information when resuming the workflow. The Functional API also supports streaming and human-in-the-loop interruptions.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub

+1



For example:

```
from langgraph.checkpoint.memory import InMemorySaverfrom langgraph.func import entrypoint, task@taskdef fetch(url: str) -> str:    return f"Fetched {url}"@entrypoint(checkpointer=InMemorySaver())def workflow(url: str) -> dict:    body = fetch(url).result()    return {"body": body}
```

`InMemorySaver()` is useful for learning and testing because it stores checkpoint information in memory. It is not durable storage across process restarts. A production application that needs durable recovery should use a suitable persistent checkpointer and configure a thread ID for invocations.

Also, checkpointing does not mean every external operation is guaranteed to happen exactly once under all failure conditions. For important side effects, such as charging a payment method, use idempotency mechanisms and appropriate error handling.

## 10. Functional API versus Graph API

LangGraph has two main ways to define workflows.

| Feature                  | Functional API                                                 | Graph API                                                 |
| ------------------------ | -------------------------------------------------------------- | --------------------------------------------------------- |
| Workflow definition      | Python functions                                               | Nodes and edges                                           |
| Conditional branching    | Regular `if` statements                                        | Conditional edges or routing functions                    |
| Loops                    | Regular Python loops                                           | Graph structure and routing                               |
| Individual units of work | `@task` functions                                              | Nodes                                                     |
| Main workflow            | `@entrypoint()`                                                | `StateGraph` compiled into a runnable                     |
| State handling           | Primarily normal function variables and task results           | Explicit graph state and, when needed, reducers           |
| Best fit                 | Existing Python control flow and straightforward orchestration | Explicit, inspectable graph topology and stateful routing |

Both APIs use the underlying LangGraph runtime and support capabilities such as checkpointing. The Functional API doesn't require you to manually define a static graph structure; the Graph API makes that structure more explicit and easier to visualize.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub

+1



## The five things to remember

1. `@task` turns a function into a LangGraph-managed unit of work.
2. `@entrypoint()` turns a function into the main workflow.
3. `.result()` waits for a task's result and retrieves its actual value.
4. `if`, `for`, and ordinary Python code control the Functional API workflow.
5. Checkpointing requires configuration if you need persisted progress and resumability.

Your original example is therefore equivalent to a workflow manager asking one task to fetch content, examining its answer, asking another task to recover if necessary, and returning the final result—all while keeping the orchestration logic in ordinary Python.
