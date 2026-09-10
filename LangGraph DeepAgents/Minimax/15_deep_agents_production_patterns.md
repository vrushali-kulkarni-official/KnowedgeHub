# Module 15 — Deep Agents: Production Patterns

## Prerequisites

- Modules 11–14 (you have a planning, subagent-using, file-aware Deep Agent)
- Module 10 (production hardening fundamentals)

## Why this module matters

You can build a Deep Agent. Now you need to make it **production-grade** for your AI SaaS: prompt engineering, cost control, observability, testing, security, and the patterns that separate hobby agents from products.

This module is the bridge to the Capstone (Module 16).

## Learning objectives

By the end of this module you can:

1. Engineer prompts that get reliable behavior from Deep Agents.
2. Control cost with model routing, caching, and caps.
3. Add observability specific to deep-agent flows.
4. Test deep agents end-to-end.
5. Handle security concerns (prompt injection, data exfiltration, abuse).
6. Use evals to drive iteration.
7. Implement the patterns you'll need in the Capstone.

---

## 15.1 The prompt engineering playbook

### 15.1.1 The structure of a great deep agent prompt

```python
instructions = f"""
# ROLE
You are a {role}. Your job is to {goal}.

# INPUT
You'll receive: {input_format}.

# PROCESS
1. {step_1}
2. {step_2}
3. {step_3}

# TOOLS YOU HAVE
- {tool_1}: {when_to_use}
- {tool_2}: {when_to_use}
- {tool_3}: {when_to_use}

# TOOLS YOU DON'T HAVE
- Don't try to {thing_agents_often_hallucinate}

# OUTPUT
Return: {output_format}

# CONSTRAINTS
- Never {forbidden_action_1}
- Always {required_action_1}
- Cap: max {N} tool calls per task.

# EXAMPLES
Example 1: ...
Example 2: ...
"""
```

Use Markdown headers, bullets, and numbered lists. The model parses these reliably.

### 15.1.2 Few-shot examples

For complex behaviors, include 1–3 examples in the prompt. Show:

- The kind of input you expect.
- The plan the agent should make.
- The tool sequence it should follow.
- The final output format.

Examples in prompts are the single highest-leverage technique for reliability.

### 15.1.3 Negative instructions

Tell the model what NOT to do. Common ones:

```
- Never invent sources. If you can't verify, say so.
- Never execute code. You don't have that tool.
- Never claim a tool succeeded without checking the result.
- Never loop on the same todo. If stuck after 2 attempts, change approach.
```

### 15.1.4 Output format constraints

```
OUTPUT FORMAT:
Return a JSON object with these fields:
- "summary": 2-3 sentence summary
- "findings": list of {title, citation, snippet}
- "open_questions": list of strings
- "confidence": "low" | "medium" | "high"
```

The model is great at structured output when told the exact shape.

---

## 15.2 Cost control for deep agents

### 15.2.1 Model selection per role

| Role | Model suggestion |
|---|---|
| Main parent agent | Strong model (handles planning, delegation) |
| Subagents | Same or one tier down |
| `write_todos` | Trivially cheap on any model |
| Summarizer / compressor | Cheap model |
| LLM-as-judge (evals) | Strong model for reliability |

You can pass different models to different subagents:

```python
SubAgent(
    name="researcher",
    description="...",
    system_prompt="...",
    tools=[...],
    model=get_llm(strong=True),     # stronger model
)

# Main uses the default
agent = create_deep_agent(model=get_llm(), subagents=[...])
```

### 15.2.2 Caching at multiple levels

- **Provider prompt cache:** structured system prompt = high cache hit rate.
- **Result cache:** cache tool results for idempotent tools (search, lookups).
- **Plan cache:** if the user asks the same question, reuse the plan (with `thread_id` reuse).

### 15.2.3 Token budgets

Two layers:

```python
# 1. Per-thread budget
MAX_TOKENS_PER_THREAD = 100_000

# 2. Per-task budget
MAX_TOKENS_PER_TASK = 20_000
```

Track via `response_metadata["token_usage"]`. Increment in Redis. Hard-fail when exceeded.

### 15.2.4 Compaction for long contexts

After N turns, summarize older messages:

```python
def maybe_compact(state):
    if len(state["messages"]) > 30:
        summary = llm.invoke([
            SystemMessage(content="Summarize this conversation in 500 words, preserving key decisions and facts."),
            *state["messages"]
        ])
        return {
            "messages": [
                SystemMessage(content=f"Previous conversation summary: {summary.content}"),
                *state["messages"][-10:]   # last 10 messages verbatim
            ]
        }
    return {}
```

Add as a node before the main agent.

---

## 15.3 Observability for deep agents

### 15.3.1 What to tag

```python
config = {
    "configurable": {"thread_id": thread_id, "user_id": user.id, "tenant_id": tenant.id},
    "tags": ["deep-agent", "production", f"plan:{plan_version}"],
    "metadata": {"user_plan": "pro", "feature": "research"},
}
```

### 15.3.2 Custom events for plan updates

```python
# Custom writer in a custom node (Module 02 §2.6):
def log_plan_update(state, *, writer):
    writer({"event": "plan_update", "todos": state["todos"]})
    return {}
```

This shows up in your stream.

### 15.3.3 LangSmith-specific tips

- Use `project` per environment (dev, staging, prod).
- Filter by `metadata.user_id` for per-user debugging.
- Compare runs by `metadata.plan_version` for prompt A/B tests.

### 15.3.4 Subagent visibility

In LangSmith, subagent runs show as nested spans. Use the `subgraphs` option of `astream` to surface them in your own UI too.

---

## 15.4 Testing deep agents

### 15.4.1 Unit tests (mock everything)

```python
def test_planning_node():
    from app.agents.planning import plan_first
    state = {"messages": [HumanMessage(content="Research X")]}
    # mock the LLM to return a specific plan
    with mock.patch("app.llm.get_llm") as m:
        m.return_value.invoke.return_value.content = "1. Search\n2. Read\n3. Summarize"
        result = plan_first(state)
    assert len(result["todos"]) == 3
```

### 15.4.2 Integration tests (real graph, mocked tools)

```python
def test_research_agent_end_toend():
    # mock search_web, but let everything else run
    tools = [fake_search_web, fake_search_docs]
    agent = create_deep_agent(model=mock_llm, tools=tools, ...)
    result = agent.invoke({"messages": [HumanMessage(content="Research X")]})
    assert "/output/summary.md" in result["files"]
```

### 15.4.3 Eval-driven tests (the gold standard)

A 50-example golden dataset. Run weekly (or on every PR). Score trends over time.

```python
# See Module 10 for the framework
def test_eval_dataset():
    results = evaluate(
        lambda x: agent.invoke(x),
        data="golden-v3",
        evaluators=[accuracy_judge, format_judge, cost_judge],
    )
    assert results["accuracy"] > 0.85
    assert results["avg_cost"] < 0.05
```

### 15.4.4 Regression tests

Every time you fix a bug, add a test case that reproduces it. Tag it `regression`. Run on every PR.

---

## 15.5 Security

### 15.5.1 Prompt injection

The biggest risk for a deep agent: a malicious user crafts input that makes the agent do something unexpected.

Mitigations:

- **Scope tools tightly.** Don't give the agent `delete_user_account` unless you must.
- **HITL on side effects.** Module 06.
- **Input sanitization.** Strip or escape control characters, ignore "ignore previous instructions" patterns in tool outputs.
- **Output validation.** Check the final output before showing it.

### 15.5.2 Data exfiltration

The agent can read files. If it has access to other users' files, that's a leak.

- **Strict namespacing** (Module 14). Path traversal protections in your backend.
- **Tool-level authorization.** Every tool that touches user data checks the user_id from config.

### 15.5.3 Cost abuse

A malicious or buggy user could trigger expensive runs.

- Per-user rate limit.
- Per-user budget cap.
- Hard `recursion_limit`.
- Anomaly detection (alert on unusually long runs).

### 15.5.4 Tool sandboxing

For tools that execute code or shell:

- Use a sandbox (e.g. `subprocess` with timeout + restricted env, or a Docker container).
- Never run on the host machine.

---

## 15.6 The iteration loop

This is how you improve a production agent:

```
1. Production runs → log everything (Module 10)
2. User feedback → label good/bad runs
3. Failed runs → add to dataset
4. Run eval → measure
5. Prompt change → re-run eval → measure
6. Ship if better
```

The dataset is your moat. Every week it gets better; the agent gets better with it.

---

## 15.7 Patterns from real-world deep agents

### 15.7.1 The "Claude Code" pattern

- Subagent for each "expert" (code search, code edit, test runner, reviewer).
- Heavy file system use.
- Long plan, small todos.
- Lots of verification steps.
- Heavy use of paging on long files.

### 15.7.2 The "research assistant" pattern

- One main agent.
- Researcher subagent (web + docs search).
- Writer subagent (polishes text).
- File system for note-taking.
- Final output to `/output/`.

### 15.7.3 The "data analyst" pattern

- Reads CSVs from `/uploads/`.
- Writes Python to a sandbox to compute.
- Writes findings to `/output/report.md`.
- Heavy use of code execution tools.

### 15.7.4 The "customer support" pattern

- Looks up customer in DB.
- Reads knowledge base.
- Drafts reply.
- HITL before sending.
- Per-customer thread isolation.

Pick the pattern closest to your SaaS and adapt.

---

## 15.8 Performance optimization

### 15.8.1 Latency

- Run independent subagents in parallel (use `Send` or `await asyncio.gather`).
- Use the cheapest model that gets the job done.
- Stream responses (Module 07).
- Cache common tool results.

### 15.8.2 Throughput

- Multiple workers, each with their own checkpointer.
- Postgres connection pooling.
- LLM call batching (for some providers).

### 15.8.3 Quality

- Few-shot examples.
- LLM-as-judge on every output.
- Self-critique subagent (Module 13.7.1: a "reviewer" that improves the main agent's work).

---

## 15.9 Documentation as a feature

The agent's behavior is determined by prompts. Treat them as code:

- Version them in Git.
- Document changes.
- A/B test them.
- Have a "prompt changelog."

```python
# app/agents/prompts/__init__.py
RESEARCH_AGENT_INSTRUCTIONS_V3 = """..."""
RESEARCH_AGENT_INSTRUCTIONS_V2 = """..."""
```

Track which version is in production.

---

## 15.10 The deep agent production checklist

- [ ] Prompts versioned, documented, A/B tested.
- [ ] Model selection: strongest for planning, lighter for sub-tasks.
- [ ] Token budgets enforced.
- [ ] Compaction for long conversations.
- [ ] Observability: tags, metadata, custom events.
- [ ] Eval suite: ≥ 50 examples, run weekly.
- [ ] Regression tests for known bugs.
- [ ] Security: scope-limited tools, HITL on side effects, namespaced files.
- [ ] Rate limits + budget caps.
- [ ] Runbooks for common failures.

---

## Hands-on project

**Goal:** Take your Deep Agent to production-ready.

1. Engineer your prompt: role, process, tools, constraints, output format, 2 few-shot examples.
2. Add per-thread token budget with Redis tracking.
3. Add a compaction node that triggers after 30 messages.
4. Wire LangSmith with project + tags + metadata.
5. Build a 30-example golden dataset. Run baseline eval.
6. Add regression tests for 3 known issues.
7. Add input validation (block obvious prompt injection patterns).
8. Add per-user rate limit on your FastAPI route.
9. Document your prompts in a PROMPTS.md.

## Exercises

1. **Prompt A/B test:** write two versions of your instructions. Eval both. Pick the winner.
2. **Compaction test:** simulate a 50-message conversation. Apply compaction. Verify the agent still has context.
3. **Injection test:** try 5 known prompt injection patterns. Verify your agent resists them.
4. **Cost dashboard:** for 10 real runs, log total tokens, cost, latency. Build a Grafana / dashboard view.
5. **Self-critique:** add a "reviewer" subagent that always runs at the end and suggests improvements. Does it help?

## Production checklist

See §15.10.

## Key takeaways

- Prompts are code. Version, test, document.
- Cost is a product feature. Track, limit, optimize.
- Security: scope tools, namespace data, HITL on side effects.
- The dataset is your moat. Build it, grow it, eval against it.
- Iteration loop: production data → dataset → eval → improve → ship.

## Resources

- Module 10 (production fundamentals) for retries, observability, etc.
- LangSmith: https://docs.smith.langchain.com/
- OWASP LLM Top 10: https://owasp.org/www-project-top-10-for-large-language-model-applications/
- Anthropic's "Building effective agents": https://www.anthropic.com/research/building-effective-agents
