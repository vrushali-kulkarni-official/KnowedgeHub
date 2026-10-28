# 

## stream_mode

- stream_mode="values"
- stream_mode="updates" 
- stream_mode="messages"

##### combined stream_modes:

```python
stream_mode=["messages", "updates"]
```

always use version="v2" unless u realize that v3 is already out
llms just wasted your whole day :( :D :P

 ---



## Stream_mode="values"

```python
snapshot 1:
{
    topic: "ice cream",
    joke: ""
}

snapshot 2:
{
    topic: "ice cream and cats",
    joke: ""
}

snapshot 3:
{
    topic: "ice cream and cats",
    joke: "This is a joke about ice cream and cats"
}
```

The important mental model is:

```text
values
  |
  +---- current entire state
```

Not:

```text
values
  |
  +---- individual token

```

Conceptually this will happen: 

```text
Step 1 → 5 KB
Step 2 → 7 KB
Step 3 → 10 KB
Step 4 → 15 KB
Step 5 → 18 KB
```

---


## stream_mode="updates"

Instead of:

> "Give me the whole state"

it means:

> "Tell me what each node just changed."

With `updates`:

```python
{
    "refine_topic": {
        "topic": "ice cream and cats"
    }
}
```


Suppose your frontend wants to show:

```text
🤖 Agent is thinking...

🔧 Calling weather tool...

✅ Weather tool finished.

🤖 Preparing final response...
```

Then:

```python
if node_name == "model":
    show("Agent is thinking")

elif node_name == "tools":
    show("Executing tools")
```

`updates` means node/step progress, not token progress

---

## `stream_mode="messages"`

`messages` is streaming LLM outputs along with metadata.

So don't design your frontend around:

> "Every chunk equals exactly one token."

Instead think:

> "Each chunk is an incremental piece of the model's streamed output."

`messages` also gives metadata

```python

for chunk in agent.stream(
    inputs,
    stream_mode=["messages"],
    version="v2",
):

if chunk["type"] == "messages":
   message_chunk, metadata = chunk["data"]

```

Metadata contain tags and other information identifying the LLM invocation

```python
metadata["langgraph_node"]
```


---

## Combining modes

stream_mode=["messages", "updates"]

```text
The weather ...
              ↑
        streamed token

STATE UPDATE
{
    "tools": {
        ...
    }
}
```

---

## Astream Events

`astream_events()` is the lower-level event stream API from LangChain's Runnable ecosystem.

`astream_events()` lets you watch this lifecycle.

Think event = what happened?

```text
Agent
│
├── Model
│   ├── start
│   ├── stream
│   └── end
│
├── Tool
│   ├── start
│   └── end
│
└── Model
    ├── start
    ├── stream
    └── end
```


```python
{
    "event": "on_chat_model_stream",
    "name": "model",
    "run_id": "....",
    "parent_ids": ["...."],
    "tags": [...],
    "metadata": {...},
    "data": {...},
}
```


## Tags and Metadata

tags = labels/categories

```python
tags = ["customer-facing", "final-answer"]
```


metadata = structured contextual information

```python
{
    "langgraph_node": "model",
    ...
}
```

---

## using astream_events() vs messages

Use `messages` when your problem is:

> "I want model output."

For example:
```text
messages
    ↓
"Hello world"
```


Use `astream_events` when your problem is:

> "I want to observe execution."

For Example:
```text
model started
model streamed
model streamed
tool started
tool ended
model started
model streamed
model ended
```



## Filter by tag

include_tags=["final-answer"]

exclude_types=["retriever"]

## Event Streaming

```text
agent
  ↓
Event Stream
  ├── messages
  ├── tool_calls
  ├── values
  ├── subgraphs
  ├── output
  └── extensions
```





