**`count_tokens_approximately()`** is a fast heuristic token counter from LangChain Core (`langchain_core.messages.utils`). It does **not** run a real tokenizer (like tiktoken). Instead it estimates tokens from character counts plus a few fixed overheads.

### Core idea

It treats ~4 characters as 1 token (a common rough rule for English text) and adds a small fixed cost per message. The goal is speed (often 100–1000× faster than real tokenizers) for things like `trim_messages` on the hot path, where an exact count is unnecessary.

### Signature (current)

```python
count_tokens_approximately(
    messages: Iterable[MessageLikeRepresentation],
    *,
    chars_per_token: float = 4.0,
    extra_tokens_per_message: float = 3.0,
    count_name: bool = True,
    tokens_per_image: int = 85,
    use_usage_metadata_scaling: bool = False,
    tools: list[BaseTool | dict[str, Any]] | None = None,
) -> int
```

### How it actually works (step by step)

1. **Convert inputs**  
   Messages are normalized with `convert_to_messages(...)`.

2. **Optional tool schemas**  
   If you pass `tools`, each tool is turned into a dict (name + description + parameters) and `json.dumps`’d. The character length of that JSON is converted to tokens with `ceil(chars / chars_per_token)` and added once.

3. **Per-message character accumulation**
   - **Plain string content** → `len(content)`.
   - **List of content blocks** (multimodal):
     - `"text"` blocks → length of the text.
     - `"image"` / `"image_url"` blocks → add a **fixed** `tokens_per_image` (default 85, matching OpenAI’s low-res image cost) instead of counting base64.
     - Anything else → `len(repr(block))` (this is a known source of over-counting for Anthropic-style `tool_use` blocks).
   - **AIMessage tool calls** (when content is *not* already a list) → `len(repr(tool_calls))`.
   - **ToolMessage** → also counts the `tool_call_id`.
   - Always adds the role string (`"user"`, `"assistant"`, etc.) and, if `count_name=True`, the message name.

4. **Convert characters → tokens**  
   For each message:
   ```python
   token_count += math.ceil(message_chars / chars_per_token)
   token_count += extra_tokens_per_message   # default 3
   ```
   Rounding up per message ensures that summing individual message counts gives the same total as counting the whole list.

5. **Optional usage-metadata scaling** (`use_usage_metadata_scaling=True`)  
   Looks at the most recent `AIMessage` that has `usage_metadata["total_tokens"]`.  
   Computes a scale factor = reported_tokens / approximate_tokens_up_to_that_message, clamps it to [1.0, 1.25], and multiplies the final count by it. Only activates when all AI messages share the same `model_provider`.

6. **Final result**  
   `math.ceil(token_count)`.

### Important caveats

- It is intentionally approximate. Real tokenizers (tiktoken, Anthropic’s, Gemini’s, etc.) will give different numbers.
- Unknown content blocks fall back to `repr()`, which can significantly over-count (especially Anthropic `tool_use` / nested dicts).
- Images are handled with a fixed penalty so huge base64 strings don’t explode the count.
- The defaults (`chars_per_token=4.0`, `extra_tokens_per_message=3.0`) are tuned for typical OpenAI-style chat formatting; you can tweak them (e.g. Anthropic users sometimes use ~3.3).

In short: it walks every message, sums character lengths (with special cases for images, tool calls, roles, and names), divides by ~4, adds a few tokens of overhead per message, optionally scales by real usage metadata, and returns an integer. Fast, simple, and good enough for trimming, but never a substitute for a model’s real tokenizer when you need accuracy.
