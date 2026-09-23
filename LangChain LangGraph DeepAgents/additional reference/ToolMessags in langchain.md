**`trim_messages()`** is a utility in LangChain (from `langchain_core.messages`) that reduces a list of chat messages so their total size stays under a limit (usually tokens, sometimes message count). It is mainly used to keep conversation history inside a model’s context window.

### Purpose
Long-running chats or agents accumulate many messages. Most LLMs have a fixed context window. `trim_messages` drops older (or newer) messages so the remaining history fits while trying to keep the conversation valid for the model.

### Basic signature (Python)
```python
from langchain_core.messages import trim_messages

trim_messages(
    messages,                    # list of messages (or PromptValue)
    *,
    max_tokens: int,             # hard limit
    token_counter,               # how to count tokens
    strategy: "first" | "last" = "last",
    allow_partial: bool = False,
    start_on=None,               # e.g. "human"
    end_on=None,                 # e.g. ("human", "tool")
    include_system: bool = False,
    text_splitter=None,
) -> list[BaseMessage]
```

It can also be used as a **Runnable** (partial application of the kwargs).

### Key parameters

| Parameter | Meaning |
|-----------|---------|
| **`max_tokens`** | Maximum allowed tokens (or message count if using `token_counter=len`) |
| **`token_counter`** | How tokens are counted: a chat model (uses its tokenizer), a custom callable, `len` (counts messages), or `"approximate"` / `count_tokens_approximately` |
| **`strategy`** | `"last"` (keep recent messages – most common) or `"first"` (keep earliest messages) |
| **`allow_partial`** | If `True`, can split a single message when it would exceed the limit |
| **`start_on`** | Ensure the trimmed history starts with a certain message type (usually `"human"`) |
| **`end_on`** | Ensure it ends with certain types (often `("human", "tool")`) |
| **`include_system`** | Prefer to keep the original `SystemMessage` if present |

### Recommended configuration for chat models
Most models expect history that:
- Starts with a `HumanMessage` (or `SystemMessage` + `HumanMessage`)
- Ends with a `HumanMessage` or `ToolMessage`
- Never has a lone `ToolMessage` without its preceding tool-calling `AIMessage`

A typical production-style call looks like:

```python
from langchain_core.messages import trim_messages
from langchain_core.messages.utils import count_tokens_approximately
# or: from langchain_openai import ChatOpenAI

trimmed = trim_messages(
    messages,
    max_tokens=4000,                    # adjust to your model
    strategy="last",
    token_counter=count_tokens_approximately,  # fast & robust
    # token_counter=ChatOpenAI(model="gpt-4o"),  # exact but slower
    start_on="human",
    end_on=("human", "tool"),
    include_system=True,
)
```

Using `token_counter=len` turns it into a simple “keep last N messages” helper.

### Example usage in a LangGraph node
```python
from langchain_core.messages.utils import trim_messages, count_tokens_approximately

def call_model(state):
    messages = trim_messages(
        state["messages"],
        strategy="last",
        token_counter=count_tokens_approximately,
        max_tokens=128_000,          # or whatever your model allows
        start_on="human",
        end_on=("human", "tool"),
        include_system=True,
    )
    response = model.invoke(messages)
    return {"messages": [response]}
```

### Important notes & gotchas
- **Validity of history** – Naïve trimming can leave orphaned `ToolMessage`s. Always use `start_on` / `end_on` (and prefer `include_system=True`) when the result will be fed back to a chat model.
- **Token counting** – Passing a real chat model is most accurate but slower. `count_tokens_approximately` (or the string `"approximate"` in newer versions) is faster and more tolerant of unusual content blocks.
- **Partial messages** – `allow_partial=True` can cut the content of a long message; useful when a single message itself is huge.
- **JavaScript** – The equivalent is `trimMessages` from `@langchain/core/messages` with the same ideas (`maxTokens`, `strategy`, `startOn`, etc.).

In short: `trim_messages` is the standard, configurable way in LangChain to keep conversation history under the token budget while preserving a valid chat structure for the model.
