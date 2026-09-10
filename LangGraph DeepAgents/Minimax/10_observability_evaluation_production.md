# Module 10 — Observability, Evaluation & Production Concerns

## Prerequisites

- Modules 04–09 (you have a real, deployed agent system)

## Why this module matters

This is the difference between a demo and a product. You can build a working agent; now you need to:

- **See what it's doing** in production.
- **Measure** if it's actually good.
- **Handle failures** gracefully.
- **Control cost.**
- **Test** changes safely.
- **Iterate** with confidence.

This module is the production handbook.

## Learning objectives

By the end of this module you can:

1. Wire up **LangSmith** (or an open alternative) for tracing.
2. Build **evaluation datasets** and run **automated evals**.
3. Implement **retry, fallback, and timeout** strategies.
4. Add **rate limiting** and **cost controls**.
5. Add **structured logging** and **error tracking**.
6. Write **unit, integration, and end-to-end tests** for graphs.
7. Use **caching** to cut cost and latency.
8. Run **CI** that actually tests your agent.

---

## 10.1 Observability: LangSmith (and open alternatives)

### 10.1.1 What LangSmith gives you

- **Traces** of every run: full tree of LLM calls, tool calls, node transitions.
- **Datasets** for evaluation.
- **Evaluators** (LLM-as-judge, heuristic, human-in-the-loop).
- **Annotation queues** for human review.
- **Monitoring** dashboards (latency, cost, error rate).

It is a hosted product, but there's a generous free tier and it integrates with self-hosted LangSmith. Alternative: **Langfuse** (FOSS, self-hostable). Or DIY with OpenTelemetry.

For this course, we use LangSmith as the example because it's the path of least resistance. You can swap in Langfuse with similar effort.

### 10.1.2 Wiring it up

```bash
# .env
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=ai-saas-prod
```

That's it. LangChain/LangGraph auto-emit traces. No code changes.

### 10.1.3 Tracing in code (for custom spans)

```python
from langsmith import traceable

@traceable(name="custom_step", tags=["user-input"])
def my_step(text: str) -> str:
    return llm.invoke(text)
```

Or use the `RunTree` API for fine-grained control.

### 10.1.4 Metadata and tags

```python
config = {
    "configurable": {"thread_id": thread_id},
    "metadata": {"user_id": user.id, "plan": "pro"},
    "tags": ["production", "chat"],
}
g.invoke(input, config=config)
```

This metadata flows into every trace. Use it for filtering, debugging, billing.

---

## 10.2 Evaluation

### 10.2.1 The eval mindset

An eval = **a dataset + a metric + a runner.**

- **Dataset:** pairs of (input, expected output) or (input, expected behavior).
- **Metric:** how to score a run against expected.
- **Runner:** script that runs the graph on the dataset, scores, aggregates.

### 10.2.2 Building a dataset

For your SaaS, you want three kinds:

1. **Golden examples** — hand-crafted ideal cases.
2. **Regression tests** — bugs you've fixed (so they stay fixed).
3. **Production samples** — periodically labeled by humans.

In LangSmith:

```python
from langsmith import Client
client = Client()
dataset = client.create_dataset("agent-golden-v1")
client.create_examples(
    inputs=[{"messages": [...]}],
    outputs=[{"messages": [...]}],
    dataset_id=dataset.id,
)
```

### 10.2.3 Evaluators

Three flavors:

**Heuristic (deterministic):**
```python
def must_contain_citation(run, example) -> dict:
    answer = run.outputs["messages"][-1].content
    return {"score": 1.0 if "[1]" in answer else 0.0}
```

**LLM-as-judge:**
```python
from langsmith.evaluation import LangChainStringEvaluator

judge = LangChainStringEvaluator("labeled_score_string", config={
    "criteria": {
        "accuracy": "Is the response factually correct given the reference answer?",
    }
})
```

**Human:** mark a run for human review; a human labels it; the label feeds back into the dataset.

### 10.2.4 Running evals

```python
from langsmith.evaluation import evaluate

results = evaluate(
    lambda inputs: g.invoke(inputs),
    data="agent-golden-v1",
    evaluators=[judge, must_contain_citation],
    experiment_prefix="v1.2-rc",
)
```

Run this in CI on every PR. Block merges that drop score by >X%.

---

## 10.3 Error handling

### 10.3.1 Where errors happen

- LLM call (rate limit, timeout, content filter).
- Tool call (network, bad response, auth).
- DB write (Postgres down, lock timeout).
- Checkpointer (Postgres down).

### 10.3.2 The retry policy

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def call_llm(messages):
    return await llm.ainvoke(messages)
```

Wrap your LLM call. Same for tool calls. Don't retry on `BadRequest` (won't help). Retry on `RateLimitError`, `Timeout`, `InternalServerError`.

### 10.3.3 Fallbacks

```python
from langchain_core.runnables import RunnableWithFallbacks

primary = strong_model.with_fallbacks([
    cheap_model,
    heuristic_answer,
])
```

If the primary model fails, try the cheap one, then a deterministic last-resort. Critical for production uptime.

### 10.3.4 Timeouts

```python
import asyncio
async def safe_call(messages, timeout=30):
    return await asyncio.wait_for(call_llm(messages), timeout=timeout)
```

Apply at the tool level too. A 60-second tool call is a bug.

### 10.3.5 The node error handler

You can wrap a node with a try/except and return a fallback state:

```python
def safe_agent(state):
    try:
        return agent(state)
    except Exception as e:
        return {"messages": [AIMessage(content="I'm having trouble, please try again.")]}
```

Use sparingly — better to fix the root cause. But as a safety net, yes.

---

## 10.4 Rate limiting

You need to protect against:
- User spamming the API.
- Runaway agents looping.
- Provider rate limits.
- Your own cost.

### 10.4.1 Per-user rate limit (Redis token bucket)

```python
# app/rate_limit.py
import redis.asyncio as redis

class TokenBucket:
    def __init__(self, redis_client, key, rate, capacity):
        self.r = redis_client
        self.key = key
        self.rate = rate
        self.capacity = capacity

    async def consume(self, tokens=1) -> bool:
        # Lua script for atomic bucket
        ...
```

Or use a library like `slowapi`. Wire it into FastAPI middleware.

### 10.4.2 Per-graph iteration limit

```python
class State(MessagesState):
    step_count: Annotated[int, operator.add]

def route(s):
    if s["step_count"] > 25: return END
    ...
```

### 10.4.3 Cost circuit breaker

```python
# In your LLM factory:
total_spend = redis.incrby(f"spend:{user_id}", estimated_cost)
if total_spend > user_budget:
    raise BudgetExceeded()
```

---

## 10.5 Cost control

### 10.5.1 Token tracking

LangSmith tracks this. For DIY:

```python
def track_tokens(response, user_id):
    usage = response.response_metadata.get("token_usage", {})
    redis.hincrby(f"tokens:{user_id}", "input", usage.get("prompt_tokens", 0))
    redis.hincrby(f"tokens:{user_id}", "output", usage.get("completion_tokens", 0))
```

### 10.5.2 Model routing

Use the cheap model by default; escalate to the strong one only when needed.

```python
def choose_model(state) -> ChatModel:
    if state.get("complex"):
        return strong_llm
    return cheap_llm
```

### 10.5.3 Caching

Two layers:

- **Prompt cache** (provider-side): same prefix → cached. Cheap to enable, big savings.
- **Result cache** (your side): cache common queries.

```python
from langchain_core.globals import set_llm_cache
from langchain_community.cache import RedisCache
import redis

set_llm_cache(RedisCache(redis_client=redis.Redis.from_url(REDIS_URL)))
```

LLM calls with the same prompt will be served from Redis. Massive savings for FAQ-style queries.

### 10.5.4 Prompt compression

For long conversations, summarize older messages before sending to the LLM. Use a `MessagesState` with a custom reducer, or a pre-LLM node that compresses.

---

## 10.6 Logging

### 10.6.1 Structured logging

```python
import structlog
log = structlog.get_logger()

def agent(state, *, writer):
    log.info("agent.start", thread_id=..., user_id=...)
    response = llm.invoke(state["messages"])
    log.info("agent.end", tokens=response.usage_metadata)
    return {"messages": [response]}
```

JSON logs → Loki/CloudWatch/Datadog. Trace IDs propagated.

### 10.6.2 Error tracking

Sentry is the default. Capture every exception in nodes, with state context.

```python
import sentry_sdk
sentry_sdk.init(dsn=SENTRY_DSN)

def safe_node(state):
    try:
        return real_node(state)
    except Exception as e:
        sentry_sdk.capture_exception(e, extra={"state_keys": list(state.keys())})
        raise
```

---

## 10.7 Testing

### 10.7.1 Unit tests for nodes

```python
def test_summarize_node():
    state = {"text": "long text..."}
    out = summarize_node(state)
    assert "summary" in out
    assert len(out["summary"]) > 0
```

Mock the LLM. Use a fake `BaseChatModel`.

### 10.7.2 Graph tests with `InMemorySaver`

```python
def test_react_loop_calls_tool():
    g = builder.compile(checkpointer=InMemorySaver())
    result = g.invoke({"messages": [HumanMessage(content="Weather?")]})
    assert any(m.type == "tool" for m in result["messages"])
```

### 10.7.3 Mocking tools

```python
from langchain_core.tools import tool

@tool
def fake_weather(city: str) -> str:
    return f"FAKE: sunny in {city}"
```

Build a "test graph" that uses fakes, run it through scenarios.

### 10.7.4 End-to-end with real LLM

Mark these as `@pytest.mark.llm`. Run only on CI nightly (or before release), not every commit. They cost money.

```python
@pytest.mark.llm
def test_real_research_agent():
    result = g.invoke({"messages": [HumanMessage(content="What is X?")]})
    assert "..." in result["messages"][-1].content
```

### 10.7.5 Eval as test

Run your eval suite in CI. A drop in score = failing test.

---

## 10.8 CI/CD for your agent

```yaml
# .github/workflows/test.yml
name: test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: test
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install uv && uv sync
      - run: uv run pytest -m "not llm"   # skip real-LLM tests
      - run: uv run ruff check .
      - run: uv run mypy app
      - name: Eval (nightly only)
        if: github.event.schedule
        run: uv run python -m app.evals.run
```

The eval step uses LangSmith to run the dataset and report scores.

---

## 10.9 Common production pitfalls

| Pitfall | Mitigation |
|---|---|
| Loop burns tokens | Hard cap on iterations |
| Tool hangs forever | Per-tool timeout |
| Provider outage | Fallback model |
| Cost explosion | Token tracking + per-user budget |
| Silent quality regression | Eval in CI |
| No way to debug | LangSmith traces |
| Bad data in long conversations | Compression / summarization |
| Users exploit prompt injection | Input sanitization + scope-limited tools |

---

## 10.10 The production readiness checklist

- [ ] Observability: traces in LangSmith (or Langfuse) for 100% of runs.
- [ ] Errors: retry + fallback on all LLM and tool calls.
- [ ] Timeouts: enforced everywhere.
- [ ] Rate limits: per-user, per-tenant.
- [ ] Cost: tracking + per-user budget + caching.
- [ ] Logging: structured JSON, propagated trace IDs.
- [ ] Errors: Sentry (or equivalent) capturing all exceptions.
- [ ] Tests: unit, integration, eval suite.
- [ ] CI: runs tests + lints + evals on every PR.
- [ ] Runbooks: documented procedures for common failures.

---

## Hands-on project

**Goal:** Production-harden your agent.

1. Add LangSmith tracing.
2. Wrap every LLM call with retry + fallback.
3. Add Redis-based rate limiting on your FastAPI routes.
4. Add token tracking; surface it in a `/usage/{user_id}` endpoint.
5. Add structured logging.
6. Build a 20-example golden dataset. Run the eval. Get a baseline score.
7. Set up CI: `pytest` + `ruff` + `mypy` + eval-on-nightly.

## Exercises

1. **Cache test:** query the same thing 3 times. Verify the second/third hit the cache. Measure latency.
2. **Retry test:** inject failures (mock the LLM to raise 2 times then succeed). Verify your retry logic.
3. **Rate limit test:** hammer the API from one user. Verify 429s after the limit.
4. **Eval baseline:** run your golden dataset 3 times (temperature=0). Check score stability.
5. **Cost tracking:** run a 10-turn conversation. Sum the input+output tokens. Compare to estimate.

## Production checklist

See §10.10.

## Key takeaways

- **Observability is non-negotiable.** Traces, metrics, logs.
- **Evals are tests for non-deterministic systems.** Build datasets, measure.
- **Retries, fallbacks, timeouts** at every external boundary.
- **Cost is a product feature.** Track, limit, cache.
- **CI must include the agent's actual behavior**, not just code lints.

## Resources

- LangSmith: https://docs.smith.langchain.com/
- Langfuse (FOSS alt): https://langfuse.com/
- `tenacity` (retries): https://tenacity.readthedocs.io/
- Sentry: https://sentry.io/
- `slowapi` (rate limit): https://github.com/laurentS/slowapi
