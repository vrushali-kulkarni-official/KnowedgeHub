# L11 — Observability: Langfuse Trace Trees and Streaming Debugging

**Module:** M70 (part 3) · **Time:** ~2h · **Example:** `examples/ex15_langfuse_traces.py`, `examples/ex16_debugging_streaming.py`

---

## 0. Why a multi-agent system needs a different kind of logging

A single agent produces a **line**: one conversation, one model call at a
time. You read it top to bottom.

A multi-agent system produces a **tree**:

```
LangGraph
  supervisor
    researcher
      model
      tools
    writer
      model
```

When the answer is wrong, the questions are entirely different:

* Which agent made the bad call?
* What did the supervisor see when it chose that agent?
* How many tokens did the whole tree burn?
* Did the specialist get a useful brief, or a useless one?

You cannot answer these from the final state. You need a trace.

---

## 1. Langfuse: free, open source, self-hostable

Langfuse is **MIT licensed**. You can run it yourself with Docker, or use
the hosted version. It is the most popular open-source LLM observability
tool in the LangChain ecosystem.

```bash
pip install langfuse
```

### Two ways to use it

**a) The LangChain callback handler** — automatic, one line:

```python
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

lf = Langfuse(
    public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
    secret_key=os.environ["LANGFUSE_SECRET_KEY"],
    host="https://cloud.langfuse.com",       # or your self-hosted URL
)
handler = CallbackHandler()

out = app.invoke(inputs, {"callbacks": [handler], "recursion_limit": 30})
```

**b) Manual spans** — for your own nodes:

```python
with lf.start_as_current_observation(name="fanout", input={"topics": topics}) as obs:
    merged = merge(results)
    obs.update(output={"merged": merged})
```

---

## 2. The one thing you must do: NAME YOUR AGENTS

```python
create_agent(model, tools=[...], name="researcher")
#                                   ^^^^^^^^^^^^^
```

Without a name, every agent span is called `LangGraph` and the tree is
useless. With names, you get:

```
LangGraph
  supervisor
    supervisor            <- the supervisor AGENT (named)
      model
        ScriptedChatModel
      tools
        ask_researcher
          researcher      <- the specialist AGENT (named)
            model
            model
            tools
              web_search
```

That tree is from `ex15`, captured **offline** — see §5.

The `name=` also shows up in the `AIMessage.name` field, which is how you
can tell which agent produced which message:

```python
for m in out["messages"]:
    print(m.name, text_of(m)[:60])
```

---

## 3. Reading a multi-agent trace

| what you see | what it means |
|---|---|
| a supervisor span with **many** child agent spans | the supervisor is looping — add a visit counter / limits |
| a specialist span with a **huge** input | your handoff brief is too long; context isolation is failing |
| a specialist span with a **tiny** input | your brief is too short; the specialist is guessing |
| **many** `tools` spans under one agent | a runaway tool loop |
| an agent span with **no** `model` child | it never called the model — a routing failure |
| a `tools` span with **no** following `model` span | the tool crashed the agent (L10 §5.1) |

---

## 4. Streaming: the local debugging toolkit

LangGraph's streaming is the fastest way to debug, and it needs no
external service.

### The four modes

| mode | question it answers |
|---|---|
| `stream_mode="values"` | what did the shared state look like after each step? |
| `stream_mode="updates"` | which node changed what? |
| `stream_mode="messages"` | what is the model actually saying, token by token? |
| `stream_mode="tasks"` | where did it fail? (task input / result / error) |

### The flag that matters: `subgraphs=True`

Without it you only see the top level, and a multi-agent system looks like
a single agent that mysteriously does a lot.

```python
for chunk in app.stream(inputs, stream_mode=["updates"], subgraphs=True):
    ns, mode, payload = chunk        # 3-tuple when subgraphs=True
```

The **namespace tuple** tells you exactly which nested agent produced the
step:

```
ns=('supervisor:54edd013-fe11-5bd9-25c1-2c8ca6b5327e',) node='model'
ns=('supervisor:54edd013-...', 'tools:0416a685-...') node='tools'
ns=() node='supervisor'
```

Read it as a path: `supervisor` → `tools`. The `tools` part is the
*specialist's* tools node, nested inside the supervisor agent.

### Chunk shapes (get this right or you will be confused)

| call | chunk shape |
|---|---|
| `stream_mode="values"` | the state dict itself |
| `stream_mode="messages"` | `(message, metadata)` tuples |
| `stream_mode=["updates"]`, `subgraphs=True` | `(namespace, mode, payload)` |
| `stream_mode="tasks"` | `(namespace, mode, payload)` |

---

## 5. Running Langfuse offline (no server, no key)

Langfuse v5 is built on **OpenTelemetry**. You can point it at an
in-memory exporter and inspect the exact tree your code produces. This is
how `ex15` is testable in CI.

```python
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

exporter = InMemorySpanExporter()
provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(exporter))

lf = Langfuse(
    public_key="pk-lf-offline",
    secret_key="sk-lf-offline",
    base_url="http://localhost:9999",      # nothing is actually sent
    tracer_provider=provider,
    tracing_enabled=True,
)
handler = CallbackHandler()

app.invoke(inputs, {"callbacks": [handler]})

spans = exporter.get_finished_spans()        # <- assert on these in tests
```

> **This is a genuinely useful pattern beyond testing:** you can assert on
> the *shape* of your agent tree in a unit test. "The supervisor must spawn
> exactly two specialist spans" is a testable invariant.

---

## 6. The debugging playbook

**SYMPTOM: the final answer is wrong.**
→ `stream_mode="updates"`, `subgraphs=True`. Find the **last** node that
ran before the bad answer. Which agent produced it? Look at its namespace.

**SYMPTOM: an agent seems to ignore the brief.**
→ `stream_mode="messages"`. Read what the specialist **actually**
received. A `HumanMessage` with the wrong text means the *handoff* is
broken, not the model. This is the single most useful check in
multi-agent debugging.

**SYMPTOM: the run hangs or loops.**
→ `stream_mode="tasks"`. The task names repeat. That is your loop. Add a
visit counter (L06) and a `ModelCallLimitMiddleware` (L10).

**SYMPTOM: the shared state looks wrong.**
→ `stream_mode="values"`. Step through the state and find the step where
it went wrong. Then check the reducer (L08) and the echo trap (L02).

**SYMPTOM: a fan-out branch produced nothing.**
→ `stream_mode="updates"`, `subgraphs=True`. Look for a namespace with a
`tools` span and no following `model` span.

**The three numbers to check first**
1. How many model calls? (does it match your expectation?)
2. How many agents ran? (did a specialist run twice?)
3. How big was each agent's input? (is context isolation working?)

---

## 7. Langfuse v5 API notes (verified)

* `Langfuse(...).start_observation(name=..., input=...)` — create a span.
* `Langfuse(...).start_as_current_observation(...)` — a context manager.
* `lf.score_current_trace(name="helpfulness", value=0.8)` — score a run.
* `lf.update_current_span(...)`, `lf.update_current_generation(...)`.
* `lf.get_trace_url(trace_id)` — a link to the trace in the UI.
* **There is no `api.trace.list()` in v5.** Use
  `api.observations.get_many(user_id=...)` and
  `api.trace.delete_multiple(trace_ids=[...])`.

---

## 8. Run it

```bash
PYTHONPATH=examples .venv/bin/python examples/ex15_langfuse_traces.py
PYTHONPATH=examples .venv/bin/python examples/ex16_debugging_streaming.py
```

---

## What you should be able to do now

- Set up Langfuse for a multi-agent system and read the trace tree.
- Explain why `name=` on every agent is non-negotiable.
- Choose the right streaming mode for a given symptom.
- Read a namespace tuple and say which nested agent produced a step.
- Run Langfuse offline against an in-memory exporter and assert on the tree
  in a test.

**Next:** L12 — the capstone, and the production checklist.
