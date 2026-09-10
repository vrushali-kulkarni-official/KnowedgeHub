# Module 11 — Deep Agents: The Big Picture

## Prerequisites

- Modules 04–10 (you can build, deploy, observe, and harden a LangGraph agent)

## Why this module matters

You now know how to build agents in LangGraph. The Deep Agents library is the **opinionated layer on top** for a specific pattern: "give an agent a goal and a toolbox, let it plan and execute autonomously over many steps."

If you've used Claude Code, Devin, or similar coding agents, you've used a system with these exact properties. Deep Agents packages the architecture so you don't reinvent it.

## Learning objectives

By the end of this module you can:

1. Explain what Deep Agents is and what problem it solves.
2. Identify when to use Deep Agents vs raw LangGraph.
3. Use the four pillars: planning, subagents, file system, detailed instructions.
4. Create your first `create_deep_agent`.
5. Understand what's happening under the hood (it's a LangGraph graph).

---

## 11.1 What is Deep Agents?

Deep Agents is a Python library from the LangChain team. Its tagline: **"Build agents that plan, sub-agent, and file-system their way through complex tasks."**

It's a thin (but opinionated) wrapper around LangGraph that:

- Pre-builds a ReAct-style graph for you.
- Injects four key tools: `write_todos`, `task` (spawn subagent), `ls`/`read_file`/`write_file`/`edit_file`.
- Uses a detailed system prompt that primes the model to plan and use these tools.
- Lets you customize via `tools`, `subagents`, `instructions`, and `backend`.

The result: with ~20 lines of code, you have a capable autonomous agent. With customization, you can build a Claude-Code-style tool for any domain.

---

## 11.2 The four pillars

```
                  ┌─────────────────────────────────────┐
                  │           Deep Agent                │
                  │                                     │
                  │  ┌──────────────┐                   │
                  │  │  PLAN FIRST  │  ← write_todos    │
                  │  └──────────────┘                   │
                  │          │                          │
                  │          ▼                          │
                  │  ┌──────────────┐                   │
                  │  │  USE TOOLS   │  ← your tools     │
                  │  └──────────────┘                   │
                  │          │                          │
                  │          ▼                          │
                  │  ┌──────────────┐                   │
                  │  │ DELEGATE     │  ← task tool      │
                  │  │ TO SUBAGENTS │    (with own ctx) │
                  │  └──────────────┘                   │
                  │          │                          │
                  │          ▼                          │
                  │  ┌──────────────┐                   │
                  │  │ PERSIST DATA │  ← virtual FS     │
                  │  │ IN FILES     │    (backends)     │
                  │  └──────────────┘                   │
                  └─────────────────────────────────────┘
```

### 11.2.1 Pillar 1: Planning (`write_todos`)

The agent uses a `write_todos` tool to maintain a plan. It updates it as it learns. This is what keeps a long-running agent on track.

### 11.2.2 Pillar 2: Subagents (`task`)

The agent can spawn **subagents** — full Deep Agents themselves, with their own context, tools, and instructions. The parent gets a summary back. This is **context isolation**: the parent's context doesn't bloat with subagent work.

### 11.2.3 Pillar 3: File system (`ls`, `read_file`, `write_file`, `edit_file`)

A **virtual file system** with pluggable backends. The agent reads, writes, and edits files. This is the agent's persistent scratchpad — much more scalable than stuffing everything in messages.

### 11.2.4 Pillar 4: Detailed instructions

The system prompt is intentionally long and prescriptive. It tells the model: plan first, use subagents for big tasks, write things to files, etc. You can override or extend it.

---

## 11.3 When to use Deep Agents vs raw LangGraph

| Scenario | Use |
|---|---|
| One-shot LLM call | LangChain |
| Fixed multi-step pipeline | LCEL / LangGraph |
| Tool-using chatbot with HITL | LangGraph |
| Multi-step with persistence, no autonomy | LangGraph |
| "Figure this out, use whatever tools you have" goal-seeking agent | **Deep Agents** |
| Claude-Code-style coding/research agent | **Deep Agents** |
| Multi-agent system with explicit roles | LangGraph (or Deep Agents with subagents) |

**Rule of thumb:** if you find yourself writing a long system prompt that says "make a plan, break it into steps, delegate complex parts, save intermediate results to files" — that's a Deep Agents use case.

---

## 11.4 Installation

```bash
uv add deepagents
```

That's it. It pulls LangGraph under the hood.

---

## 11.5 Your first Deep Agent

```python
# app/agents/researcher.py
from deepagents import create_deep_agent
from app.tools.search import search_web, search_docs
from app.llm import get_llm

agent = create_deep_agent(
    model=get_llm(),
    tools=[search_web, search_docs],
    instructions="""
    You are a research assistant. Given a topic:
    1. Plan your research with write_todos.
    2. Search broadly first, then narrow.
    3. Save findings to files in the /notes/ directory.
    4. Write a final summary to /output/summary.md.
    """,
)

# Use it:
result = agent.invoke({
    "messages": [{"role": "user", "content": "Research the impact of X on Y."}]
})
print(result["messages"][-1].content)
```

That's it. The agent will:
- Make a plan.
- Use `search_web` and `search_docs`.
- Write notes to files.
- Iterate until done.

---

## 11.6 What's actually under the hood

`create_deep_agent` returns a compiled `StateGraph`. The structure:

```
START → llm → (tool_calls?) → tools → llm → ... → END
              ↓                                    
       (no tool_calls)                          
```

With these nodes:
- `llm` — the agent's reasoning step.
- `tools` — a `ToolNode` containing your tools **plus** the built-in ones:
  - `write_todos` (planning)
  - `task` (spawn subagent)
  - `ls`, `read_file`, `write_file`, `edit_file` (file system)

The state extends `MessagesState` with `todos` and `files` channels.

You can inspect:

```python
from IPython.display import Image
Image(agent.get_graph().draw_mermaid_png())
```

It looks like a normal ReAct graph, just with extra tools injected.

---

## 11.7 Configuring the model

```python
from app.llm import get_llm
agent = create_deep_agent(model=get_llm(), ...)
```

`model` can be:
- A `BaseChatModel` (e.g. `get_llm()`).
- A string like `"openai:gpt-4o"` (uses LangChain's `init_chat_model`).

Always go through your factory. The abstraction matters even more with Deep Agents, because the planning behavior depends heavily on model choice.

---

## 11.8 Detailed instructions

The default instructions are good. You almost always want to override them with your own. Key points to specify:

- **Role:** what kind of agent this is.
- **Goal:** what success looks like.
- **Process:** the steps you expect.
- **Constraints:** what NOT to do.
- **Output format:** what to return to the user.

```python
instructions = """
You are a {domain} agent. Your job is to {goal}.

PROCESS:
1. First, write a plan with write_todos.
2. ...

CONSTRAINTS:
- Never execute code without explicit user approval.
- Always cite sources.
- Keep total tool calls under 30.

OUTPUT:
- Final answer should be in markdown.
- Save artifacts to /output/.
"""
```

Modules 12–15 go deep on instructions for planning, subagents, files, and production.

---

## 11.9 Inspecting a run

```python
result = agent.invoke({"messages": [HumanMessage(content="...")]})
result.keys()
# dict_keys(['messages', 'todos', 'files'])

result["todos"]    # the plan as a list
result["files"]    # the virtual file system as a dict
```

You can also stream:

```python
async for event in agent.astream({"messages": [...]}, stream_mode=["updates", "messages"]):
    ...
```

Same five modes from Module 07.

---

## 11.10 Persistence for Deep Agents

Deep Agents inherits LangGraph's persistence. Add a checkpointer:

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

checkpointer = AsyncPostgresSaver.from_conn_string(DB_URI)

agent = create_deep_agent(
    model=get_llm(),
    tools=[...],
    checkpointer=checkpointer,
)
```

Use `thread_id`s in config to scope conversations. The `todos` and `files` are persisted per-thread.

---

## 11.11 Limitations to know

- **Token cost**: long planning + many tool calls = expensive. Cap with `recursion_limit` and explicit step caps.
- **Determinism**: same prompt can yield different plans. Always have an eval (Module 10).
- **Subagent recursion**: a subagent can spawn its own subagents. Cap the depth.
- **File system leakage**: in production, you want a per-user/per-thread backend (Module 14).

---

## Hands-on project

**Goal:** Build your first real Deep Agent.

1. Define three tools: `search_web` (mock), `get_weather` (mock), `calculate` (real).
2. Create a Deep Agent that can research a topic and produce a summary.
3. Write detailed instructions emphasizing planning, file writing, and citation.
4. Run it on 3 different topics. Inspect `result["todos"]` and `result["files"]` each time.
5. Stream the run. Watch it plan, then act.

## Exercises

1. **Compare with raw LangGraph:** rebuild the same agent using raw LangGraph (no Deep Agents). Compare code volume and capability.
2. **Instruction tuning:** run the agent with default instructions vs your own. Which plans better?
3. **Visualize the graph:** `agent.get_graph().draw_mermaid_png()`. Understand every node.
4. **Cap test:** set `recursion_limit=5` and run a complex prompt. What happens?
5. **Persistence:** add a checkpointer. Run, kill the process, run again with same `thread_id`. Does the agent remember its plan?

## Production checklist

- [ ] All tools have detailed docstrings (the agent relies on them).
- [ ] Instructions are detailed and explicit about process and constraints.
- [ ] Recursion limit set (50–100).
- [ ] Persistence configured (Postgres checkpointer).
- [ ] Per-thread isolation (one `thread_id` per user session).
- [ ] Evals in place (Module 10 patterns).

## Key takeaways

- Deep Agents = opinionated LangGraph for goal-seeking agents.
- Four pillars: planning, subagents, file system, instructions.
- It IS a LangGraph graph under the hood. You can inspect and customize.
- When in doubt: "would I describe this as a Claude-Code-style agent?" If yes, Deep Agents.

## Resources

- Deep Agents repo: https://github.com/langchain-ai/deepagents
- Docs: https://docs.langchain.com/oss/python/deepagents/overview (or current equivalent)
- Underlying LangGraph: everything from Modules 02–10.
