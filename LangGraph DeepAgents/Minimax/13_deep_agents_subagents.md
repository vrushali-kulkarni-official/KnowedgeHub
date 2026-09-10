# Module 13 — Deep Agents: Subagents

## Prerequisites

- Module 12 (you have a planning Deep Agent)

## Why this module matters

The single biggest lever for long-running agents is **context isolation**. Subagents let the parent delegate a chunk of work; the parent gets a summary back, not the entire transcript.

This is what makes a Claude-Code-style agent feasible: coding happens in subagents, the main agent only sees the results.

## Learning objectives

By the end of this module you can:

1. Define and use subagents.
2. Understand the `task` tool and how delegation works.
3. Choose between general-purpose vs specialized subagents.
4. Manage context with subagent isolation.
5. Handle subagent failures.
6. Build a hierarchy of agents for complex domains.
7. Debug multi-subagent runs.

---

## 13.1 The `task` tool

A Deep Agent can call `task(description, subagent_type)` to spawn a subagent. The subagent:

- Is itself a full Deep Agent (or any agent).
- Has its own context window, files, todos.
- Returns a final summary to the parent.
- The parent's context does **not** contain the subagent's full transcript — only the summary.

The parent's system prompt is told: "When you encounter a complex task, spawn a subagent. The subagent has its own context."

---

## 13.2 Defining subagents

Pass `subagents` to `create_deep_agent`:

```python
from deepagents import create_deep_agent
from deepagents.sub_agent import SubAgent

researcher = SubAgent(
    name="researcher",
    description="Performs deep research on a specific topic and returns a written summary with citations.",
    system_prompt="""
    You are a research specialist. Given a topic:
    1. Plan with write_todos.
    2. Use search_web to gather sources.
    3. Take detailed notes to /notes/.
    4. Write a final report to /report.md.
    """,
    tools=[search_web],
)

writer = SubAgent(
    name="writer",
    description="Takes a research summary and produces a polished document.",
    system_prompt="You are a writer. Refine the input into clear prose.",
    tools=[],
)

main = create_deep_agent(
    model=get_llm(),
    tools=[search_docs],
    subagents=[researcher, writer],
    instructions="""You are a project manager. For research tasks, delegate to the researcher subagent.
    For polishing, delegate to the writer subagent.""",
)
```

The parent now has a `task(description="...", subagent_type="researcher")` tool. The model decides when to use it.

---

## 13.3 General-purpose vs specialized subagents

Two kinds:

**General-purpose** (the default, automatic):

- Always available, no config needed.
- "Given this task, do whatever you need."
- Good for: open-ended tasks the parent doesn't have a specialist for.

**Specialized** (you define):

- Have specific tools, instructions, and identity.
- Good for: known patterns (researcher, coder, reviewer).

For most production agents, define 2–5 specialized subagents + use the general-purpose one as fallback.

---

## 13.4 Context isolation in detail

When a parent calls `task("research X", subagent_type="researcher")`:

1. Parent's context window: contains the `task` tool call.
2. **New context** created for the subagent.
3. Subagent runs to completion. Full tool calls, full todos, full files — none of this is in the parent's context.
4. Subagent's final message is added to the parent's context.
5. Parent continues.

The result: parent can do many high-level tasks without its context ballooning.

### 13.4.1 What about files?

Subagents **share** the parent's file system by default. The parent can read what the subagent wrote. The subagent can read what the parent wrote. This is intentional — they can collaborate on artifacts.

You can isolate a subagent's files by giving it its own backend (Module 14).

---

## 13.5 Subagent communication patterns

### 13.5.1 Fire-and-forget

```
Parent: "Research X and write findings."
   → task("researcher", "Research X, write to /findings.md")
   → continues
```

The parent doesn't need the result inline; it just needs the file written.

### 13.5.2 Result needed

```
Parent: "What's the latest stock price of AAPL?"
   → task("researcher", "Get current AAPL stock price")
   → receives "AAPL is at $150"
   → uses it in next turn
```

Subagent returns a final message; parent uses it.

### 13.5.3 Iterative

```
Parent: "Write a function that does X."
   → task("coder", "Write function X")
   → review
   → task("coder", "Refactor based on feedback")
```

The parent loops the subagent, each call with fresh context.

---

## 13.6 Choosing the right number of subagents

| Subagents | Use when |
|---|---|
| 0 | Single-domain agent, simple tasks |
| 1–2 | One specialist, simple hierarchy |
| 3–5 | Standard SaaS agent (researcher, writer, coder, reviewer) |
| 5+ | Complex domains with clear role splits |

**Diminishing returns**: more subagents = harder to debug, more LLM calls (cost), more prompt complexity. Don't go beyond what you actually need.

---

## 13.7 Subagent failures

A subagent can fail:
- Hits recursion limit.
- Throws an error.
- Times out.
- Returns garbage.

Handle by:
- **Retries:** wrap the subagent task in a retry.
- **Fallback:** if researcher fails, ask a different specialist.
- **Escalation:** if both fail, pause for human review.

```python
def safe_task(state):
    try:
        return real_task(state)
    except Exception as e:
        # log, return error to parent
        return {"messages": [AIMessage(content=f"Subagent failed: {e!r}. Please try a different approach.")]}
```

The parent sees the failure and can adjust.

---

## 13.8 Subagent prompts

A subagent's system prompt should be:

- **Specialized** — only do X, not everything.
- **Self-contained** — explain its role, its tools, its output format.
- **Concise** — subagents have their own context; longer prompts = more tokens per call.
- **Output-focused** — "return a summary in markdown" beats "do the work."

```python
researcher_prompt = """
You are the RESEARCHER subagent. You specialize in deep, citation-backed research.

INPUT: a topic or question.

OUTPUT: a markdown report at /output/{slug}.md with:
- Title
- Summary (2-3 sentences)
- Key Findings (bulleted, with citations)
- Open Questions

PROCESS:
1. Plan with write_todos.
2. Use search_web to find 5-10 authoritative sources.
3. Take notes to /notes/ as you go.
4. Synthesize into the report.
5. Verify all citations are correct.

CONSTRAINTS:
- Never invent sources. If you can't find a citation, say so.
- Aim for 800-1500 words.
"""
```

---

## 13.9 Inspecting subagent runs

A subagent's run is a separate thread (or subgraph) in the trace. In LangSmith, you see it as a nested span. In your app:

```python
# Stream with subagent visibility
async for event in agent.astream(input, config, stream_mode="updates"):
    node, update = next(iter(event.items()))
    if "subagent" in node.lower():
        # this is from a subagent
        ...
```

You can also use the `subgraphs=True` option in `astream` (depending on version) to surface all subagent events.

---

## 13.10 The "subagent as tool" alternative

Sometimes you don't need full agent behavior for a sub-task. You just need a function.

```python
@tool
def run_researcher(topic: str) -> str:
    """Delegate to the researcher subagent. Returns a markdown report."""
    result = researcher_agent.invoke({"messages": [HumanMessage(content=topic)]})
    return result["messages"][-1].content

main_agent = create_deep_agent(
    model=get_llm(),
    tools=[run_researcher, ...],   # tools include other agents
    subagents=[...],
)
```

Same effect, different mechanism. The `task` tool is more flexible (full agent context). The tool-wrapped version is more explicit.

---

## 13.11 Cost and performance

Subagents multiply cost:

- Each subagent invocation = LLM call(s) to plan + tool calls + LLM call to summarize.
- The summary itself is a context-blowing LLM call.

Monitor per-task cost. If subagent-heavy tasks are too expensive:

- Use the same model for subagents (or even a smaller one).
- Cap subagent tool calls.
- Run subagents in parallel (`Send` / parallel `task` calls) when independent.

---

## 13.12 Common subagent pitfalls

| Pitfall | Fix |
|---|---|
| Too many subagents | Limit to 3–5 |
| Subagent does what parent could do | Fold it into the parent |
| Subagent context not isolated | Make sure you're using the `task` tool, not passing full state |
| Subagent returns huge result | Force it to return a summary, not the full transcript |
| Subagent recursion | Cap depth (parent can't spawn sub-sub-sub-sub) |
| Subagent silently fails | Catch + report |
| Parent uses subagent when it shouldn't | Better instructions on when to delegate |

---

## Hands-on project

**Goal:** Build a multi-agent SaaS assistant with 3 specialized subagents.

1. **Researcher:** web search → markdown report.
2. **Writer:** polish text into a final document.
3. **Reviewer:** critique and suggest improvements.
4. **Parent:** orchestrates. Given a user request, plans with `write_todos`, then delegates.
5. Test scenarios:
   - "Write a blog post about X" → researcher → writer → reviewer → final.
   - "Just answer this question" → no subagents.
   - "Refine this draft" → writer only.

## Exercises

1. **Compare with/without subagents:** run a complex task with and without subagent delegation. Compare quality and cost.
2. **Subagent parallelism:** make the parent call 3 researchers in parallel for 3 sub-topics, then combine. Measure speedup.
3. **Failure recovery:** make the researcher deliberately fail. Verify the parent gets a useful error and recovers.
4. **Subagent specialization:** write prompts for 3 specialists. Run 10 tasks. Does each agent do its job, or do they overlap?
5. **HitL on subagent results:** interrupt the parent after a subagent returns, let a human edit the summary, then continue.

## Production checklist

- [ ] Each subagent has a clear, distinct role and prompt.
- [ ] Subagent prompts include output format.
- [ ] Subagent failures handled.
- [ ] Subagent depth limited.
- [ ] Subagent cost monitored.
- [ ] Tracing on (subagent runs visible in LangSmith).

## Key takeaways

- Subagents = context isolation. They do the heavy lifting; parent stays focused.
- The `task` tool spawns a subagent. Use it for any complex subtask.
- Specialize subagents. Don't make them "general-purpose everything."
- Subagents share files with the parent by default — useful for collaboration.
- Cost multiplies. Monitor and cap.

## Resources

- Deep Agents subagents: see the `subagents` parameter docs.
- LangGraph subgraphs: Module 08 (the underlying mechanism).
- Anthropic's "Building effective agents": https://www.anthropic.com/research/building-effective-agents
