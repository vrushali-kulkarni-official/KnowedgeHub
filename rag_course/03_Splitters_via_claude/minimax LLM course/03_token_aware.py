"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  CHUNKING STRATEGY #3: TOKEN-AWARE SPLITTING                               ║
╚══════════════════════════════════════════════════════════════════════════════╝

THE CORE PROBLEM WITH CHARACTER COUNTING
─────────────────────────────────────────
Every strategy so far measures chunk size in CHARACTERS. But LLMs and embedding
models don't process characters — they process TOKENS.

What is a token?
  Token = a subword unit produced by a tokenizer (BPE, WordPiece, etc.)
  
  "tokenization"  → ["token", "ization"]              = 2 tokens
  "AI"            → ["AI"]                             = 1 token
  "ChatGPT"       → ["Chat", "G", "PT"]               = 3 tokens
  " the"          → [" the"]                           = 1 token  (space included!)
  "2024"          → ["2024"]                           = 1 token
  
  Rough approximation:  1 token ≈ 4 characters  (but highly variable!)
  A technical document: 1 token ≈ 3–5 chars
  Simple common words:  1 token ≈ 4–5 chars
  Rare/technical words: 1 token ≈ 2–3 chars (split into more pieces)

WHY THIS MATTERS CRITICALLY FOR RAG
─────────────────────────────────────
1. EMBEDDING MODEL TRUNCATION (silent data loss! 🚨)
   
   MiniLM (all-MiniLM-L6-v2) has a MAX of 256 tokens.
   If you pass a chunk with 300 tokens, it silently truncates to 256.
   You're embedding an INCOMPLETE chunk — the last 44 tokens are just gone.
   The embedding then doesn't represent what you think it does.
   
   With chunk_size=1000 chars:
     Best case: ~250 tokens (dense prose) → fits fine in MiniLM ✅
     Worst case: ~800 tokens (short common words) → TRUNCATED! ❌
   
   Fix: use token-aware splitting with chunk_size=180 tokens max for MiniLM.

2. LLM CONTEXT WINDOW OVERFLOW
   
   When building your prompt: System + Context chunks + Question must all
   fit in the LLM's context window (measured in tokens).
   
   If you feed 5 chunks and each "looks" like 500 chars but is actually
   350 tokens, your 5-chunk context = 1750 tokens just for the docs.
   Add a 200-token question + 500-token system prompt = 2450 tokens.
   
   For a small LLM (2048 token limit), you've already overflowed!

TWO TOKENIZERS COMPARED
─────────────────────────
  tiktoken (OpenAI)           |  HuggingFace tokenizers
  ─────────────────────────── |  ─────────────────────────────
  Fast, written in Rust       |  Pure Python + Rust options
  Used by: GPT-2/3/4, etc.    |  Used by: BERT, LLaMA, MiniLM
  Free to use locally         |  Free, model-specific
  Encodes cl100k_base, gpt2   |  Each model has its own tokenizer
  
  For approximation: tiktoken gpt2 is a good generic choice.
  For precision: use the exact tokenizer of your embedding model.

LANGCHAIN CLASSES
─────────────────
  TokenTextSplitter                      → uses tiktoken under the hood
  RecursiveCharacterTextSplitter
    .from_tiktoken_encoder(model_name)   → recursive + token counting
  
  Custom: pass a HuggingFace tokenizer's len function to any splitter
"""

# ─── Imports ──────────────────────────────────────────────────────────────────

import tiktoken
from transformers import AutoTokenizer
from langchain_text_splitters import (
    TokenTextSplitter,
    RecursiveCharacterTextSplitter,
)
from shared_data import PLAIN_TEXT, print_chunks


# ══════════════════════════════════════════════════════════════════════════════
# HELPER: Count tokens with different tokenizers
# ══════════════════════════════════════════════════════════════════════════════

def count_tokens_comparison(text: str):
    """
    Show how different tokenizers count the same text differently.
    This demonstrates why character count is a poor proxy for token count.
    """
    print("\n" + "═" * 65)
    print("  TOKEN COUNT COMPARISON for a sample paragraph")
    print("═" * 65)

    sample = text[:500]    # first 500 characters
    char_count = len(sample)

    # Tiktoken (OpenAI's tokenizer)
    enc_gpt2 = tiktoken.get_encoding("gpt2")
    enc_cl100k = tiktoken.get_encoding("cl100k_base")    # used by GPT-3.5/4
    gpt2_tokens = len(enc_gpt2.encode(sample))
    cl100k_tokens = len(enc_cl100k.encode(sample))

    # HuggingFace tokenizer for MiniLM (your embedding model)
    minilm_tok = AutoTokenizer.from_pretrained(
        "sentence-transformers/all-MiniLM-L6-v2"
    )
    minilm_tokens = len(minilm_tok.encode(sample))

    print(f"\n  Text length : {char_count} characters")
    print(f"  ─────────────────────────────")
    print(f"  tiktoken gpt2    : {gpt2_tokens} tokens  ({char_count/gpt2_tokens:.1f} chars/token)")
    print(f"  tiktoken cl100k  : {cl100k_tokens} tokens  ({char_count/cl100k_tokens:.1f} chars/token)")
    print(f"  MiniLM tokenizer : {minilm_tokens} tokens  ({char_count/minilm_tokens:.1f} chars/token)")
    print(f"\n  ⚠️  MiniLM max = 256 tokens")
    if minilm_tokens > 256:
        print(f"     This 500-char sample = {minilm_tokens} tokens → WOULD BE TRUNCATED by MiniLM!")
    else:
        print(f"     This 500-char sample = {minilm_tokens} tokens → fits in MiniLM ✅")


# ══════════════════════════════════════════════════════════════════════════════
# DEMO A: TokenTextSplitter — tiktoken-based, direct token counting
# ══════════════════════════════════════════════════════════════════════════════

def demo_a_token_text_splitter():
    """
    TokenTextSplitter uses tiktoken internally.
    chunk_size and chunk_overlap are in TOKENS, not characters.
    
    This is the simplest token-aware option but it's NOT recursive —
    it splits greedily on token count, potentially breaking sentences.
    Think of it as fixed-size chunking but in token space.
    """
    splitter = TokenTextSplitter(
        # Uses tiktoken's cl100k_base encoding by default
        chunk_size=100,       # 100 TOKENS per chunk (not 100 characters!)
        chunk_overlap=10,     # 10-token overlap
    )

    chunks = splitter.split_text(PLAIN_TEXT)
    print_chunks(chunks, "3A: TokenTextSplitter  (100 tokens, 10 overlap)")

    # Verify actual token counts in each chunk
    enc = tiktoken.get_encoding("cl100k_base")
    token_counts = [len(enc.encode(c)) for c in chunks]
    print(f"Actual token counts per chunk: {token_counts}")
    print(f"Max token count: {max(token_counts)} (all should be ≤ 100)")
    print("\n⚠️  Like fixed-size, this may break sentences — just in token space.")


# ══════════════════════════════════════════════════════════════════════════════
# DEMO B: RecursiveCharacterTextSplitter + tiktoken (BEST of both worlds)
# ══════════════════════════════════════════════════════════════════════════════

def demo_b_recursive_with_tiktoken():
    """
    from_tiktoken_encoder() creates a RecursiveCharacterTextSplitter where:
      - The separator cascade ["\n\n", "\n", " ", ""] is still used
      - But chunk_size is measured in TOKENS (via tiktoken)
    
    This gives you:
      ✅ Respects paragraph/sentence/word boundaries (recursive)
      ✅ Accurate token counting (no silent truncation)
    
    This is the recommended upgrade from plain RecursiveCharacterTextSplitter
    for most production systems.
    """
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        # Which tiktoken encoding to use for counting
        encoding_name="cl100k_base",    # GPT-3.5/4 encoding
        # Or: model_name="gpt-3.5-turbo"  — same thing, but by model name
        
        chunk_size=120,     # 120 TOKENS — safe for MiniLM (max 256 tokens)
        chunk_overlap=12,   # 10% overlap in tokens
    )

    chunks = splitter.split_text(PLAIN_TEXT)
    print_chunks(chunks, "3B: Recursive + tiktoken  (120 tokens, 12 overlap)")

    # Double-check with the actual MiniLM tokenizer
    minilm_tok = AutoTokenizer.from_pretrained(
        "sentence-transformers/all-MiniLM-L6-v2"
    )
    minilm_counts = [len(minilm_tok.encode(c)) for c in chunks]
    print(f"MiniLM token counts per chunk: {minilm_counts}")
    over_limit = [c for c in minilm_counts if c > 256]
    if over_limit:
        print(f"⚠️  {len(over_limit)} chunks exceed MiniLM's 256-token limit!")
    else:
        print(f"✅ All {len(chunks)} chunks fit within MiniLM's 256-token limit!")


# ══════════════════════════════════════════════════════════════════════════════
# DEMO C: Custom length_function using HuggingFace tokenizer
# The most precise approach: count tokens using YOUR exact embedding model
# ══════════════════════════════════════════════════════════════════════════════

def demo_c_custom_hf_tokenizer():
    """
    You can pass ANY function as length_function. Here we use the exact
    tokenizer of our embedding model (MiniLM) so chunk_size = MiniLM tokens.
    
    This is the most accurate approach: chunk_size directly matches what
    the embedding model will see. No approximation, no surprises.
    """
    # Load the tokenizer for our embedding model
    minilm_tokenizer = AutoTokenizer.from_pretrained(
        "sentence-transformers/all-MiniLM-L6-v2"
    )

    def count_minilm_tokens(text: str) -> int:
        """Count how many tokens MiniLM would produce for this text."""
        # encode() includes [CLS] and [SEP] special tokens (adds 2)
        # We subtract 2 to count only content tokens
        tokens = minilm_tokenizer.encode(text)
        return len(tokens) - 2    # subtract [CLS] and [SEP]

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=180,              # 180 MiniLM tokens (leaves buffer under 256)
        chunk_overlap=18,            # 10% overlap in MiniLM tokens
        length_function=count_minilm_tokens,  # ← KEY: use MiniLM's counting
        # The separators are still character-based but sizing is token-based
    )

    chunks = splitter.split_text(PLAIN_TEXT)
    print_chunks(chunks, "3C: Recursive + MiniLM tokenizer  (180 MiniLM tokens)")

    # Verify
    actual_counts = [count_minilm_tokens(c) for c in chunks]
    print(f"MiniLM token counts: {actual_counts}")
    print(f"All ≤ 180 tokens: {all(c <= 180 for c in actual_counts)} "
          f"(guaranteed by splitter)")
    print(f"\n→ These chunks will NEVER be truncated by MiniLM's 256-token limit ✅")


# ══════════════════════════════════════════════════════════════════════════════
# DEMO D: Side-by-side comparison — chars vs. tokens
# Shows concretely why character counting misleads you
# ══════════════════════════════════════════════════════════════════════════════

def demo_d_chars_vs_tokens():
    """
    Compare chunk size metrics: character count vs. actual token count.
    This visualises the variance that makes character-based sizing unreliable.
    """
    print("\n" + "═" * 65)
    print("  3D: Character Count vs Token Count Mismatch")
    print("═" * 65)

    # Create chunks using character-based splitting
    char_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=0)
    chunks = char_splitter.split_text(PLAIN_TEXT)

    enc = tiktoken.get_encoding("cl100k_base")
    minilm_tok = AutoTokenizer.from_pretrained(
        "sentence-transformers/all-MiniLM-L6-v2"
    )

    print(f"\n{'Chunk':<6} {'Chars':>6} {'tiktoken':>10} {'MiniLM':>8} {'Truncated?':>12}")
    print("─" * 50)
    for i, chunk in enumerate(chunks):
        chars = len(chunk)
        tik_count = len(enc.encode(chunk))
        mini_count = len(minilm_tok.encode(chunk)) - 2
        truncated = "🚨 YES" if mini_count > 256 else "✅ no"
        print(f"{i+1:<6} {chars:>6} {tik_count:>10} {mini_count:>8} {truncated:>12}")

    print(f"\n→ char_size=500 produces chunks ranging in MiniLM tokens from "
          f"{min(len(minilm_tok.encode(c))-2 for c in chunks)} to "
          f"{max(len(minilm_tok.encode(c))-2 for c in chunks)}.")
    print("→ High variance! Token-aware splitting eliminates this uncertainty.")


# ══════════════════════════════════════════════════════════════════════════════
# KEY TAKEAWAYS
# ══════════════════════════════════════════════════════════════════════════════

def print_takeaways():
    print("\n" + "=" * 65)
    print("KEY TAKEAWAYS — Token-Aware Splitting")
    print("=" * 65)
    print("""
  1. LLMs and embedding models operate on TOKENS, not characters.
     1 token ≈ 4 chars, but this varies widely and is not reliable.

  2. MiniLM (your current embedding model) silently truncates at 256 tokens.
     Character-based chunks of 500 chars can be 100–400 MiniLM tokens.
     This causes silent data loss in your embeddings.

  3. RECOMMENDED for MiniLM:
     RecursiveCharacterTextSplitter with length_function = MiniLM tokenizer
     chunk_size=180 tokens (leaves buffer for special tokens + metadata)

  4. Two approaches ranked by precision:
     Best:    Custom HuggingFace length_function (your exact model's tokens)
     Good:    from_tiktoken_encoder (fast, good approximation)
     Avoid:   Plain TokenTextSplitter alone (no recursive fallback)

  5. For a different embedding model, find its max_seq_length on HuggingFace
     and set chunk_size to about 70–80% of that value.

  NEXT UP → Strategy 4: Sentence-Aware Splitting
  → python 04_sentence_aware.py
""")


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n🔍 Running all Token-Aware Splitting demos...\n")
    print("(First run may download tokenizer — only once, then cached)\n")

    count_tokens_comparison(PLAIN_TEXT)
    print("\n" + "─" * 65 + "\n")

    demo_a_token_text_splitter()
    print("\n" + "─" * 65 + "\n")

    demo_b_recursive_with_tiktoken()
    print("\n" + "─" * 65 + "\n")

    demo_c_custom_hf_tokenizer()
    print("\n" + "─" * 65 + "\n")

    demo_d_chars_vs_tokens()

    print_takeaways()
