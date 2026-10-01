# Agent Streaming

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

| Type value | Meaning | Typical data shape |
|---|---|---|
| `"values"` | Full state after a step | Your state object (dict / Pydantic / dataclass) |
| `"updates"` | Partial state updates from a node | `{"node_name": {updated fields}}` |
| `"messages"` | LLM token / message stream | `(message_chunk, metadata) tuple` |
| `"custom"` | Anything you pushed with a stream writer | Whatever you wrote (any type) |
| `"tasks"` | Task start / result events | Task payload |
| `"checkpoints"` | Checkpoint information | Checkpoint payload |
| `"debug"` | Debug events | Debug payload |


### What comes under "ns" :

namespace (where the event came from)

- () or [] → event came from the root graph/agent
- Non-empty → event came from a subgraph or sub-agent

### What comes under "data" :

data — the actual payload
data holds the real content. Its shape depends entirely on type:

| type | What data contains |
|---|---|
| `"values"` | Full state after the step |
| `"updates"` | Dict mapping node name → the update it produced |
| `"messages"` | Tuple `(message_or_chunk, metadata_dict)` |
| `"custom"` | Anything you emitted via `StreamWriter` / `get_stream_writer()` |
| others | Mode-specific payloads (tasks, checkpoints, etc.) |