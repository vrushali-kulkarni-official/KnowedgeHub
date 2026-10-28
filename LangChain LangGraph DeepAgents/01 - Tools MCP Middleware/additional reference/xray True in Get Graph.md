**`xray=True`** controls how deeply LangGraph expands **subgraphs** when you call `get_graph()`.

### What `xray` means

| Value | Behavior |
|-------|----------|
| `xray=False` (default) | Shows only the **top-level** graph. Subgraphs appear as **single black-box nodes**. |
| `xray=True` | Fully expands **all nested subgraphs** (recursive). You see the internal nodes and edges of every subgraph. |
| `xray=1` (or any integer) | Expands subgraphs only up to that **depth**. Useful when the graph is deeply nested and you don’t want everything expanded. |

### Visual difference

**Without xray (`xray=False`):**
```
__start__ → agent → tools → __end__
```
Here `agent` or `tools` might actually be a whole subgraph, but you only see one box.

**With xray (`xray=True`):**
```
__start__
    → agent
        → llm_call
        → should_continue
        → tool_node
    → tools
        → search
        → calculator
    → __end__
```
You now see the **internal structure** of every subgraph.

### Example usage

```python
# Only top-level view (compact)
print(agent.get_graph(xray=False).draw_mermaid())

# Full internal view of all subgraphs
print(agent.get_graph(xray=True).draw_mermaid())

# Expand only 1 level deep
print(agent.get_graph(xray=1).draw_mermaid())
```

### When to use which?

- **`xray=False`** → Quick overview of the high-level flow.
- **`xray=True`** → Debugging or understanding complex agents that contain nested graphs (e.g. ReAct agents, multi-agent systems, tool-calling subgraphs).
- **`xray=N`** → When the graph is very deep and expanding everything makes the Mermaid diagram too large/messy.

In short: **`xray=True` gives you X-ray vision into the nested graphs**.
