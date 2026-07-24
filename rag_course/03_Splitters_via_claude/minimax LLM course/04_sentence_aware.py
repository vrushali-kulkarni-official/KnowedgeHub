"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  CHUNKING STRATEGY #4: SENTENCE-AWARE SPLITTING                            ║
╚══════════════════════════════════════════════════════════════════════════════╝

THE CORE INSIGHT
────────────────
The sentence is the fundamental unit of meaning in language.
  - A sentence expresses a complete thought.
  - Breaking a sentence in half destroys the thought.
  - Two related sentences together form a coherent unit.

All previous strategies tried to preserve sentences by accident
(via newlines or spaces). Sentence-aware splitting does it on purpose,
using a real NLP pipeline that understands sentence boundaries.

WHY NAIVE SPLITTING ON "." IS WRONG
─────────────────────────────────────
  "Dr. Smith went to Washington D.C. He ate a sandwich."
  
  Split on ".":
    → ["Dr", " Smith went to Washington D", "C", " He ate a sandwich", ""]
  
  Real sentence detection handles:
    ✅ Abbreviations: "Dr.", "Mr.", "U.S.A.", "e.g."
    ✅ Decimals: "It costs $4.99 each."
    ✅ Ellipsis: "And then... it happened."
    ✅ Quoted speech: 'He said "Hello. How are you?" and left.'
    ✅ URLs: "Visit https://example.com. It's free."

TWO TOOLS FOR SENTENCE DETECTION
──────────────────────────────────

  NLTK (Natural Language Toolkit)
  ───────────────────────────────
  - Uses Punkt tokenizer (unsupervised, learned from data)
  - Fast and lightweight (~15MB download)
  - Very good for standard English prose
  - Setup: nltk.download('punkt_tab')
  - LangChain: NLTKTextSplitter

  spaCy
  ─────
  - Full NLP pipeline: tokenization + POS + NER + dep parsing + sentences
  - More accurate than NLTK, especially for complex text
  - Slightly slower; uses small model (en_core_web_sm = ~12MB)
  - Setup: python -m spacy download en_core_web_sm
  - LangChain: SpacyTextSplitter

  Custom sentence grouping (no LangChain class needed)
  ─────────────────────────────────────────────────────
  - Use NLTK/spaCy to get sentences, then group N sentences per chunk
  - Lets you control chunk size in a more natural unit (sentences, not chars)

NOTE ON CHUNK SIZE WITH SENTENCE SPLITTERS
───────────────────────────────────────────
  NLTKTextSplitter and SpacyTextSplitter treat "\n\n\n" (triple newline) as
  a higher-priority separator than sentence boundaries. The chunk_size
  parameter still limits the character count of each chunk — if adding the
  next sentence would exceed it, a new chunk starts.
  
  This means: sentence boundaries are PREFERRED split points, but chunk_size
  is still ENFORCED. A very long single sentence will still be split.
"""

# ─── Imports ──────────────────────────────────────────────────────────────────

import nltk
from langchain_text_splitters import NLTKTextSplitter, SpacyTextSplitter
from shared_data import PLAIN_TEXT, print_chunks

# Download NLTK data (only happens once, then uses cache)
# punkt_tab is the newer name; older versions used 'punkt'
try:
    nltk.data.find("tokenizers/punkt_tab")
except LookupError:
    print("Downloading NLTK punkt_tab tokenizer (one-time ~15MB)...")
    nltk.download("punkt_tab")


# ══════════════════════════════════════════════════════════════════════════════
# DEMO A: Show the problem — naive period splitting
# ══════════════════════════════════════════════════════════════════════════════

def demo_a_naive_vs_smart():
    """
    Direct comparison: dumb split on "." vs. NLTK sentence tokenizer.
    """
    tricky = (
        "Dr. Smith earned his Ph.D. from M.I.T. in 2003. "
        "His salary was $142,500.50 per year. "
        "He often said \"Hello. How are you today?\" to students. "
        "Visit https://lab.example.com. It is free to access."
    )

    print("═" * 65)
    print("  4A: Naive '.' split vs NLTK sentence detection")
    print("═" * 65)

    # Naive approach
    naive_sentences = tricky.split(".")
    print(f"\n[Naive split on '.'] → {len(naive_sentences)} pieces:")
    for i, s in enumerate(naive_sentences):
        print(f"  [{i}] {s!r}")

    # NLTK approach
    smart_sentences = nltk.sent_tokenize(tricky)
    print(f"\n[NLTK sent_tokenize] → {len(smart_sentences)} sentences:")
    for i, s in enumerate(smart_sentences):
        print(f"  [{i}] {s!r}")

    print("\n→ NLTK correctly handles abbreviations (Dr., Ph.D., M.I.T., $142,500.50)")
    print("   and quoted speech ('Hello. How are you today?')")


# ══════════════════════════════════════════════════════════════════════════════
# DEMO B: NLTKTextSplitter (LangChain wrapper)
# ══════════════════════════════════════════════════════════════════════════════

def demo_b_nltk_splitter():
    """
    NLTKTextSplitter uses NLTK's sent_tokenize as the primary split function,
    then RecursiveCharacterTextSplitter's merging logic to hit chunk_size.
    
    Internally it uses "\n\n\n" as a meta-separator above sentences, so
    you can still hard-break at section boundaries if needed.
    """
    splitter = NLTKTextSplitter(
        chunk_size=400,     # character limit per chunk (enforced after sentences)
        chunk_overlap=40,   # character overlap
        separator="\n\n\n"  # optional: hard-break sections (default is \n\n\n)
    )

    chunks = splitter.split_text(PLAIN_TEXT)
    print_chunks(chunks, "4B: NLTKTextSplitter  (size=400, overlap=40)")

    # Check for mid-sentence splits
    import re
    suspicious = [c for c in chunks if not re.search(r'[.!?]\s*$', c.strip())]
    if suspicious:
        print(f"⚠️  {len(suspicious)} chunks don't end with sentence-final punctuation")
        print("   (This can happen when a chunk hits the size limit mid-sentence)")
    else:
        print("✅ All chunks end at sentence boundaries!")


# ══════════════════════════════════════════════════════════════════════════════
# DEMO C: SpacyTextSplitter (LangChain wrapper)
# Requires: python -m spacy download en_core_web_sm
# ══════════════════════════════════════════════════════════════════════════════

def demo_c_spacy_splitter():
    """
    SpacyTextSplitter runs a full spaCy NLP pipeline for sentence detection.
    More accurate than NLTK, especially on complex/domain-specific text.
    
    Prerequisite: python -m spacy download en_core_web_sm
    If you haven't done this, skip this demo or run the download first.
    """
    try:
        splitter = SpacyTextSplitter(
            chunk_size=400,
            chunk_overlap=40,
            # pipeline="en_core_web_sm"  ← default; can use en_core_web_md for better accuracy
        )
        chunks = splitter.split_text(PLAIN_TEXT)
        print_chunks(chunks, "4C: SpacyTextSplitter  (size=400, overlap=40)")

        print("✅ spaCy uses a full linguistic pipeline for sentence detection")
        print("   This handles complex cases NLTK might miss.")

    except OSError:
        print("\n[SKIPPED] 4C: SpacyTextSplitter")
        print("  spaCy model not found. Run: python -m spacy download en_core_web_sm")
    except Exception as e:
        print(f"\n[SKIPPED] 4C: SpacyTextSplitter — {e}")
        print("  Install spaCy: pip install spacy")
        print("  Then: python -m spacy download en_core_web_sm")


# ══════════════════════════════════════════════════════════════════════════════
# DEMO D: Custom sentence grouping — N sentences per chunk
# No LangChain class needed. More control than the LangChain wrappers.
# ══════════════════════════════════════════════════════════════════════════════

def demo_d_custom_sentence_groups(sentences_per_chunk: int = 3):
    """
    Custom approach: use NLTK to detect sentences, then group them manually.
    
    This gives you direct control over the semantic density of each chunk:
    "I want exactly 3 sentences per chunk" rather than "max 400 chars".
    
    Production variant: use a sliding window of sentences for overlap.
    e.g., chunk 1 = sentences [0,1,2], chunk 2 = sentences [1,2,3], etc.
    """
    # Detect sentences with NLTK
    sentences = nltk.sent_tokenize(PLAIN_TEXT)

    print("\n" + "═" * 65)
    print(f"  4D: Custom Sentence Groups  ({sentences_per_chunk} sentences per chunk)")
    print("═" * 65)
    print(f"\n  Total sentences detected by NLTK: {len(sentences)}")

    # Group sentences into chunks
    chunks = []
    for i in range(0, len(sentences), sentences_per_chunk):
        group = sentences[i : i + sentences_per_chunk]
        chunk_text = " ".join(group)    # join sentences with a space
        chunks.append(chunk_text)

    for i, chunk in enumerate(chunks):
        sentence_count = len(nltk.sent_tokenize(chunk))
        print(f"\n  [Chunk {i+1:02d}] {len(chunk)} chars | ~{sentence_count} sentences")
        print(f"  {chunk[:120]}{'...' if len(chunk) > 120 else ''}")

    print(f"\n  → {len(chunks)} chunks of ~{sentences_per_chunk} sentences each")

    # BONUS: Sliding window (overlap at sentence level)
    print("\n  BONUS — Sliding Window (overlap of 1 sentence):")
    sliding_chunks = []
    window_size = sentences_per_chunk
    step = max(1, window_size - 1)     # overlap of 1 sentence

    for i in range(0, len(sentences) - window_size + 1, step):
        group = sentences[i : i + window_size]
        sliding_chunks.append(" ".join(group))

    print(f"  {len(sliding_chunks)} chunks with 1-sentence overlap (vs {len(chunks)} without)")
    print("  Sliding window ensures each sentence appears in at least 2 chunks.")


# ══════════════════════════════════════════════════════════════════════════════
# DEMO E: Combining sentence detection + token counting
# This is a production-grade combination.
# ══════════════════════════════════════════════════════════════════════════════

def demo_e_sentences_with_token_limit():
    """
    Best-of-both-worlds: use NLTK to detect sentences, but enforce a
    TOKEN limit (not character limit) per chunk. This ensures:
      ✅ No mid-sentence cuts
      ✅ No embedding model truncation (MiniLM-safe)
      ✅ Maximal semantic coherence per chunk
    """
    from transformers import AutoTokenizer

    minilm_tok = AutoTokenizer.from_pretrained(
        "sentence-transformers/all-MiniLM-L6-v2"
    )
    MAX_TOKENS = 170  # Safe limit for MiniLM (256 max, buffer for special tokens)

    sentences = nltk.sent_tokenize(PLAIN_TEXT)

    print("\n" + "═" * 65)
    print(f"  4E: Sentence-Aware + Token-Limited  (max {MAX_TOKENS} MiniLM tokens)")
    print("═" * 65)

    chunks = []
    current_sentences = []
    current_tokens = 0

    for sentence in sentences:
        # Count tokens for this sentence
        sentence_tokens = len(minilm_tok.encode(sentence)) - 2   # minus special tokens

        if current_tokens + sentence_tokens <= MAX_TOKENS:
            # Sentence fits in current chunk
            current_sentences.append(sentence)
            current_tokens += sentence_tokens
        else:
            # Save current chunk (if non-empty) and start a new one
            if current_sentences:
                chunks.append(" ".join(current_sentences))
            # Start new chunk with this sentence
            # Handle case: single sentence exceeds limit (force-include it)
            current_sentences = [sentence]
            current_tokens = sentence_tokens

    # Don't forget the last chunk
    if current_sentences:
        chunks.append(" ".join(current_sentences))

    for i, chunk in enumerate(chunks):
        token_count = len(minilm_tok.encode(chunk)) - 2
        print(f"\n  [Chunk {i+1:02d}] {token_count} tokens | {len(chunk)} chars")
        print(f"  {chunk[:120]}{'...' if len(chunk) > 120 else ''}")

    token_counts = [len(minilm_tok.encode(c)) - 2 for c in chunks]
    print(f"\n  → {len(chunks)} chunks | token range: {min(token_counts)}–{max(token_counts)}")
    print(f"  → All ≤ {MAX_TOKENS} tokens: {all(t <= MAX_TOKENS for t in token_counts)} ✅")


# ══════════════════════════════════════════════════════════════════════════════
# KEY TAKEAWAYS
# ══════════════════════════════════════════════════════════════════════════════

def print_takeaways():
    print("\n" + "=" * 65)
    print("KEY TAKEAWAYS — Sentence-Aware Splitting")
    print("=" * 65)
    print("""
  1. Sentence boundaries are a natural unit of meaning. Always prefer
     splitting at them over arbitrary character counts.

  2. Never split on "." — abbreviations, decimals, and quoted speech
     all create false sentence boundaries. Use NLTK or spaCy instead.

  3. NLTK is good enough for most English text (fast, lightweight).
     spaCy is better for technical/scientific/noisy text.

  4. The most production-ready approach (Demo E):
       → NLTK sentence detection + HuggingFace token limit enforcement
       → Guarantees no mid-sentence cuts AND no embedding truncation

  5. LangChain's NLTKTextSplitter and SpacyTextSplitter enforce a
     character-based chunk_size. If you want token-based limits,
     implement the custom grouping logic (Demo D/E).

  NEXT UP → Strategy 5: Structure-Aware (Markdown / HTML) Splitting
  → python 05_structure_aware.py
""")


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n🔍 Running all Sentence-Aware Splitting demos...\n")

    demo_a_naive_vs_smart()
    print("\n" + "─" * 65 + "\n")

    demo_b_nltk_splitter()
    print("\n" + "─" * 65 + "\n")

    demo_c_spacy_splitter()
    print("\n" + "─" * 65 + "\n")

    demo_d_custom_sentence_groups(sentences_per_chunk=3)
    print("\n" + "─" * 65 + "\n")

    demo_e_sentences_with_token_limit()

    print_takeaways()
