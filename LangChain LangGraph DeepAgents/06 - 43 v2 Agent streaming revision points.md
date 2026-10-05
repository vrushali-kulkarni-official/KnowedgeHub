# Agent Streaming-------------------------------------------------------------------------------------------------------------

## How to write

Instead of:

```python
result = agent.invoke(...)
print(result)
```

you do:

```python
for chunk in agent.stream(...):
    print(chunk)
```

or asynchronously:

```python
async for chunk in agent.astream(...):
    print(chunk)
```

## StreamPart structure for v2 protocol:

```python
{
    "type": ...,
    "ns": ...,
    "data": ...
}
```

### What comes under "type" :

| Type value      | Meaning                                  | Typical data shape                              |
| --------------- | ---------------------------------------- | ----------------------------------------------- |
| `"values"`      | Full state after a step                  | Your state object (dict / Pydantic / dataclass) |
| `"updates"`     | Partial state updates from a node        | `{"node_name": {updated fields}}`               |
| `"messages"`    | LLM token / message stream               | `(message_chunk, metadata) tuple`               |
| `"custom"`      | Anything you pushed with a stream writer | Whatever you wrote (any type)                   |
| `"tasks"`       | Task start / result events               | Task payload                                    |
| `"checkpoints"` | Checkpoint information                   | Checkpoint payload                              |
| `"debug"`       | Debug events                             | Debug payload                                   |

### What comes under "ns" :

namespace (where the event came from)

- () or [] → event came from the root graph/agent
- Non-empty → event came from a subgraph or sub-agent

originate from:

```text
()
```

to:

```text
("researcher",)
```

to:

```text
("researcher", "search")
```

### What comes under "data" :

data — the actual payload
data holds the real content. Its shape depends entirely on type:

| type         | What data contains                                              |
| ------------ | --------------------------------------------------------------- |
| `"values"`   | Full state after the step                                       |
| `"updates"`  | Dict mapping node name → the update it produced                 |
| `"messages"` | Tuple `(message_or_chunk, metadata_dict)`                       |
| `"custom"`   | Anything you emitted via `StreamWriter` / `get_stream_writer()` |
| others       | Mode-specific payloads (tasks, checkpoints, etc.)               |

---

## Stream Events version="v3"

run = agent.stream_events(
    inputs,
    version="v3",
)

Then:

```python
run.messages
run.values
run.updates
run.output
run.subgraphs
...
```

### run.messages

```python
run = agent.stream_events(
    inputs,
    version="v3",
)

for message_stream in run.messages:
    for text in message_stream.text:
        print(text, end="", flush=True)
```

Message types:
.text
.reasoning
.tool_calls
.output

v3:

```text
run.messages
 ↓
ChatModelStream
 ├── text
 ├── reasoning
 ├── tool_calls
 └── output
```

### run.messages vs run.values vs run.updates vs run.output

```text
run.messages
    ↓
LLM-oriented view

run.values
    ↓
state-oriented view

run.updates
   ↓
node/task updates

run.output
    ↓
final state/output
```


### seq in stream_events(v3)

Wall-clock time isn't necessarily sufficient to determine strict ordering.

`The` internal protocol has a monotonic sequence:

```text
seq=41
seq=42
seq=43
```

### Custom event streaming

```python
stream_mode="custom"

get_stream_writer()
```

Example of custom

`{ "type": "custom", "data": { "status": "searching_salesforce" } }`

You could emit:

```text
"salesforce_search_started"
"salesforce_search_completed"
```

