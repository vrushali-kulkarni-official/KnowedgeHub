# L20 · Short-Term Memory

> **Phase 8 — Persistence, Memory & Human-in-the-Loop**
> Module M59 · *Short-term memory*
>
> Run: `python examples/ex13_short_term_memory.py`
> Run: `python examples/ex14_summarization_middleware.py`

---

## 0. What "short-term memory" means in LangGraph

**Short-term memory = the conversation history that lives in the checkpoint,
scoped to one thread.**

There is no separate "memory object" for it. You already have it:

```python
graph.get_state(config).values["messages"]
```

That is the whole idea. The only problem is that it grows forever, and the
model's context window does not.

So this lesson is really about one question:

> **How do I decide what part of the history the model should see?**

Three answers, in increasing order of sophistication:

| Technique | What it does | Information lost |
|---|---|---|
| `trim_messages` | drops old messages entirely | everything dropped |
| `ContextEditingMiddleware` | replaces old **tool outputs** with a placeholder | tool payloads only |
| `SummarizationMiddleware` | replaces old messages with a **written summary** | compressed |

---

## 1. The context-window budget

A model's context window is finite. Gemini's are large:

| Model | Context window |
|---|---|
| `gemini-3.8-flash` | 1M tokens |
| `gemini-3.6-flash` | 1M tokens |
| `gemini-3.5-flash-lite` | 1M tokens |
| `gemini-3.1-flash-lite` | 1M tokens |

But "large" is not "infinite". A single tool result can be 10k tokens. Twenty
turns of that is 200k. And every token costs money and latency on **every**
subsequent turn.

> **Budgeting rule:** the history you send on turn *n* is re-sent on turn
> *n+1*, *n+2*, … If your history grows by 5k tokens per turn, turn 20 costs
> 100k tokens of input. Compaction is not an optimisation, it's a requirement.

---

## 2. Technique 1: `trim_messages` (manual)

```python
from langchain_core.messages import trim_messages

trimmed = trim_messages(
    messages,
    max_tokens=60,
    token_counter="approximate",   # or a model, or your own function
    strategy="last",               # keep the newest
    include_system=True,            # but never drop the system prompt
    start_on="human",               # don't start mid-conversation
)
```

Useful arguments:

| Argument | Meaning |
|---|---|
| `max_tokens` | the budget |
| `token_counter` | `"approximate"` (chars/4), a `BaseChatModel`, or `Callable[[list[BaseMessage]], int]` |
| `strategy` | `"last"` (keep newest) or `"first"` (keep oldest) |
| `include_system` | keep system messages even if over budget |
| `start_on` / `end_on` | force the conversation to start/end on a message type |
| `allow_partial` | allow cutting a single message in half |

**Pros:** total control, zero magic, easy to reason about.
**Cons:** you throw away information. If the user said "my order is #4821"
twenty turns ago, trimming drops it and the agent forgets.

**Use when:** you know exactly what matters (e.g. keep the last N turns of a
support chat).

---

## 3. Technique 2: `ContextEditingMiddleware`

The smarter version: keep the *shape* of the conversation, drop the *bulk*.

```python
from langchain.agents import create_agent
from langchain.agents.middleware import ContextEditingMiddleware
from langchain.agents.middleware.context_editing import ClearToolUsesEdit

agent = create_agent(
    model=model,
    tools=[search_docs],
    middleware=[
        ContextEditingMiddleware(
            edits=[
                ClearToolUsesEdit(
                    trigger=100_000,        # token count that triggers the edit
                    clear_at_least=0,       # min tokens to try to reclaim
                    keep=3,                 # keep the N most recent tool results
                    clear_tool_inputs=False,
                    exclude_tools=(),       # never clear these tools' outputs
                    placeholder="<tool output cleared>",
                )
            ],
            token_count_method="approximate",   # or "model"
        )
    ],
)
```

### 3.1 What it does, exactly

When the prompt exceeds `trigger` tokens:

1. It finds all `ToolMessage`s.
2. It keeps the newest `keep` of them.
3. It replaces the **rest** with the placeholder.
4. The AI/tool pairing stays valid (the `ToolMessage` is still there).

Verified in `ex13`:

```
Here is what the MODEL actually received on the last call:
  human  len=    12 'find refunds'
  ai     len=     0 ''
  tool   len=     9 '[cleared]'                      <- replaced
  ai     len=    35 'Here is what I found about refunds.'
  human  len=    12 'and returns?'
  ai     len=     0 ''
  tool   len=  1106 '[results for returns] DOC lorem ipsum dolor sit amet lorem i'  <- kept

And the checkpoint still holds the FULL text:
   '[results for refunds] DOC lorem ipsum dolor sit amet lorem ipsum dolor' ...
```

### 3.2 ⚠️ It edits the REQUEST, not the state

This is the crucial distinction:

> The **checkpoint** keeps the complete, unmodified transcript. Only the
> **prompt sent to the model** is edited.

Consequences:

| | Context editing | Summarization |
|---|---|---|
| Checkpoint contents | unchanged (full transcript) | **rewritten** (summary replaces old messages) |
| You can replay the thread with full fidelity | ✅ | ❌ (old messages are gone) |
| Audit trail complete | ✅ | ⚠️ (only the summary) |
| The model sees | a compacted view | a compacted view |

**Choose based on whether you need the full transcript later.**
For regulated or auditable use-cases, prefer context editing (or summarization
into a *separate* field).

### 3.3 `token_count_method`

| Value | How it counts | Cost |
|---|---|---|
| `"approximate"` | ~4 characters per token | free |
| `"model"` | the model's real tokenizer | one tokenizer call per request |

`"approximate"` is usually fine. Use `"model"` when your tool outputs are
long and you need precision.

### 3.4 `exclude_tools`

Some tools are small and always relevant (`get_user_id`). Others are huge
(`search_documents`). Exclude the small ones so they're never cleared:

```python
ClearToolUsesEdit(trigger=100_000, keep=3, exclude_tools=("get_user_id",))
```

---

## 4. Technique 3: `SummarizationMiddleware`

The most aggressive: a model writes a summary and that replaces the old
history.

```python
from langchain.agents.middleware import SummarizationMiddleware

agent = create_agent(
    model=model,
    tools=[...],
    middleware=[
        SummarizationMiddleware(
            model=cheap_model,               # a SEPARATE model
            trigger=("messages", 30),        # or ("tokens", N) or ("fraction", 0.8)
            keep=("messages", 20),           # keep the last 20 verbatim
            trim_tokens_to_summarize=4000,
        )
    ],
)
```

### 4.1 The trigger

| Trigger | Meaning |
|---|---|
| `("messages", 30)` | summarize once the history has 30 messages |
| `("tokens", 40_000)` | summarize once the history has ~40k tokens |
| `("fraction", 0.8)` | summarize at 80% of the model's window |

### 4.2 ⚠️ `("fraction", f)` needs a model PROFILE

Verified error:

```
ValueError: Model profile information is required to use fractional token
limits, and is unavailable for the specified model. Please use absolute
token counts instead, or pass `ChatModel(..., profile={"max_input_tokens": ...})`.
```

Because a fraction is relative to the window, LangGraph must know the window.
With Gemini:

```python
from langchain_google_genai import ChatGoogleGenerativeAI

model = ChatGoogleGenerativeAI(
    model="gemini-3.8-flash",
    google_api_key=os.environ["GOOGLE_API_KEY"],
    profile={"max_input_tokens": 1_048_576},
)
SummarizationMiddleware(model=model, trigger=("fraction", 0.8))
```

**Absolute triggers (`"messages"` / `"tokens"`) always work** with any model.
Use them if you don't want to configure profiles.

### 4.3 Verified behaviour (`ex14`)

```
1. Was a summary produced?
   summarizer calls: 1

2. What the agent's model sees now
  human  'Here is a summary of the conversation to date:\n\nSUMMARY: The user aske'
  ai     'ok'
  human  'question number 3'
  ai     'ok'
  human  'question number 4'

3. The summary is IN the state (unlike context editing)
   state contains the summary: True
```

### 4.4 Which model should summarize?

**Use a cheaper model.** You call it on every trigger, and summaries are
forgiving.

| Purpose | Model |
|---|---|
| Main agent | `gemini-3.8-flash` |
| Summarization, memory extraction | `gemini-3.5-flash-lite` |

```python
SummarizationMiddleware(model="google_genai:gemini-3.5-flash-lite")
```

### 4.5 The default summary prompt

The middleware ships with a detailed `summary_prompt` that asks the model to
extract SESSION INTENT / SUMMARY / ARTIFACTS / NEXT STEPS. Override it if
your domain needs different sections:

```python
SummarizationMiddleware(
    model=cheap_model,
    summary_prompt="""Summarize this support conversation.
    Keep: order id, customer name, the problem, what was promised.
    Drop: small talk.""",
)
```

---

## 5. Choosing a technique

| Situation | Technique |
|---|---|
| Short chats (< 20 turns) | none |
| One huge tool output | `ContextEditingMiddleware` with a low `trigger` |
| Long tool-heavy research session | `ContextEditingMiddleware` + `SummarizationMiddleware` |
| Long support chat where order details matter | `SummarizationMiddleware` with a custom prompt that keeps order ids |
| Need the full transcript for audit | `ContextEditingMiddleware` (state stays intact) |
| Cost is the priority | `SummarizationMiddleware` with a flash-lite model |

### 5.1 You can combine them

```python
middleware=[
    ContextEditingMiddleware(edits=[ClearToolUsesEdit(trigger=50_000, keep=2)]),
    SummarizationMiddleware(model=cheap_model, trigger=("messages", 60),
                            keep=("messages", 20)),
]
```

Order matters: context editing runs first (it shrinks the prompt cheaply),
then summarization decides whether the (now smaller) prompt still needs a
summary.

---

## 6. Manual budgeting (the low-level version)

Sometimes you need full control — e.g. building the prompt yourself:

```python
def fit_budget(messages, budget_chars=2000):
    kept, running = [], 0
    for m in reversed(messages):
        size = len(str(m.content))
        if running + size > budget_chars and kept:
            break
        kept.append(m)
        running += size
    return list(reversed(kept))
```

This is what `ContextEditingMiddleware` does for you, but with tool-aware
semantics (it never breaks an AI→Tool pairing) and a placeholder instead of a
hard cut.

---

## 7. What short-term memory is NOT

| Not short-term memory | Where it belongs |
|---|---|
| "The user's name is Alice" | **long-term** (the Store) — L21 |
| "This customer is a VIP" | **long-term** |
| "The user's company policy is X" | **long-term** (or a tool call) |
| The current conversation | **short-term** (the checkpoint) |
| Document contents | your **vector store** (Phase 3) |

The rule: **short-term memory is scoped to one thread and dies with it.**
If a fact should survive the conversation, it is long-term memory.

---

## 8. Common mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| No compaction at all | 400 errors, exploding costs | add one of the three |
| Trimming away the system prompt | agent loses its instructions | `include_system=True` |
| Trimming away the user's key detail | agent "forgets" mid-conversation | use summarization with a good prompt |
| Using the expensive model to summarize | cost doubles | flash-lite |
| `("fraction", 0.8)` without a profile | `ValueError` on construction | add `profile=` or use absolute triggers |
| Expecting context editing to shrink the DB | the checkpoint still holds everything | that's by design; prune separately |
| Summarizing when you need an audit trail | original messages gone | use context editing |

---

## 9. Checkpoint yourself

- [ ] I can explain where short-term memory physically lives.
- [ ] I know the three techniques and what each one loses.
- [ ] I know context editing edits the **request**, not the **state**.
- [ ] I know when to use `("fraction", …)` and what it requires.
- [ ] I can pick the right summarization model.

**Next → [L21: Long-term memory — Store & langmem](./L21-long-term-memory-store-and-langmem.md)**
