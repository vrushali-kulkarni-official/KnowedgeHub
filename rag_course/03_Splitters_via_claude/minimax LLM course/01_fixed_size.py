"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  CHUNKING STRATEGY #1: FIXED-SIZE  (The Naive Baseline)                    ║
╚══════════════════════════════════════════════════════════════════════════════╝

THEORY RECAP (see README.md for full explanation)
──────────────────────────────────────────────────
Fixed-size chunking slices text every N *characters* regardless of word/sentence
boundaries. It optionally adds an overlap so boundaries don't lose context.

                 chunk_size=30, overlap=5
  ┌──────────────────────────────────────────────────────┐
  │ "The quick brown fox jumps over the lazy dog."        │
  └──────────────────────────────────────────────────────┘
         ↓ split
  Chunk 1: "The quick brown fox jumps ove"  (chars 0–29)
  Chunk 2: "s over the lazy dog."           (chars 25–44)  ← 5-char overlap

WHEN TO USE
───────────
  ✅ Baselines and quick experiments
  ✅ Homogeneous data with no linguistic structure (logs, CSVs embedded as text)
  ❌ Prose, articles, code — anything with meaningful structure

LANGCHAIN CLASS
───────────────
  CharacterTextSplitter
    separator:      what to split on (default "\n\n")
    chunk_size:     max characters per chunk
    chunk_overlap:  characters to repeat at chunk boundaries
    length_function: how to measure size (default: len → character count)
"""

# ─── Imports ──────────────────────────────────────────────────────────────────

from langchain_text_splitters import CharacterTextSplitter

# Import our shared sample text and the pretty-printer
from shared_data import PLAIN_TEXT, print_chunks


# ══════════════════════════════════════════════════════════════════════════════
# DEMO A: Pure character split — splits anywhere, even mid-word
# This is the worst version intentionally, so you can see the problem clearly.
# ══════════════════════════════════════════════════════════════════════════════

def demo_a_pure_character():
    """
    separator=""  →  split anywhere, even inside a word.
    This is the absolute naive baseline.
    """
    splitter = CharacterTextSplitter(
        separator="",       # empty string = no preferred split point at all
        chunk_size=200,     # maximum 200 characters per chunk
        chunk_overlap=20,   # last 20 chars of chunk[i] = first 20 chars of chunk[i+1]
        length_function=len # Python's len() counts characters (not tokens, not words)
    )

    chunks = splitter.split_text(PLAIN_TEXT)
    print_chunks(chunks, "1A: Pure Character Split  (separator='', size=200, overlap=20)")

    print("⚠️  Notice: words are cut mid-way!")
    print("   e.g., 'trans-' in one chunk, 'forming' in the next.")
    print("   An embedding of 'trans-' has no useful meaning.")


# ══════════════════════════════════════════════════════════════════════════════
# DEMO B: Word-boundary split — split on spaces, at least words stay intact
# ══════════════════════════════════════════════════════════════════════════════

def demo_b_word_boundary():
    """
    separator=" "  →  split on spaces, so we never cut a word in half.
    Still ignores sentence and paragraph structure.
    
    LangChain NOTE: CharacterTextSplitter tries to split ONLY on the given
    separator. If a piece between two spaces is larger than chunk_size, it
    will fall back to splitting mid-character anyway. For robustness, use
    RecursiveCharacterTextSplitter (Strategy 2).
    """
    splitter = CharacterTextSplitter(
        separator=" ",      # split on spaces → word boundaries preserved
        chunk_size=200,
        chunk_overlap=20,
        length_function=len
    )

    chunks = splitter.split_text(PLAIN_TEXT)
    print_chunks(chunks, "1B: Word-Boundary Split  (separator=' ', size=200, overlap=20)")

    print("✅ Words are intact.")
    print("⚠️  Sentences are still split arbitrarily — watch for mid-sentence cuts.")


# ══════════════════════════════════════════════════════════════════════════════
# DEMO C: Paragraph-boundary split — split on double newlines (\n\n)
# This is actually CharacterTextSplitter's DEFAULT behaviour.
# ══════════════════════════════════════════════════════════════════════════════

def demo_c_paragraph_boundary():
    """
    separator="\n\n"  →  split on blank lines (paragraph breaks).
    This is the default CharacterTextSplitter behaviour.
    
    IMPORTANT: If a paragraph is larger than chunk_size, LangChain will
    split it mid-character (no fallback logic). That's the key weakness
    that RecursiveCharacterTextSplitter fixes in Strategy 2.
    """
    splitter = CharacterTextSplitter(
        separator="\n\n",   # default — split on paragraph breaks
        chunk_size=500,     # larger size so whole paragraphs usually fit
        chunk_overlap=50,
        length_function=len
    )

    chunks = splitter.split_text(PLAIN_TEXT)
    print_chunks(chunks, "1C: Paragraph-Boundary Split  (separator='\\n\\n', size=500)")

    print("✅ Paragraphs are kept together (assuming they fit in chunk_size).")
    print("⚠️  If one paragraph exceeds chunk_size, it will be split mid-sentence.")


# ══════════════════════════════════════════════════════════════════════════════
# DEMO D: Visualising the overlap concept
# ══════════════════════════════════════════════════════════════════════════════

def demo_d_overlap_visualised():
    """
    Uses a tiny string to show exactly where overlap appears.
    Overlap is the tool that prevents losing information at boundaries.
    
    Without overlap: two consecutive chunks can't "see" each other.
    With overlap:    chunk[i+1] starts where chunk[i] was still going.
    """
    short_text = (
        "Alice went to the market. "
        "She bought apples and bread. "
        "Then she walked home slowly. "
        "It started raining on the way."
    )

    print("\n" + "═" * 65)
    print("  1D: Overlap Visualised (short example, size=40, overlap=10)")
    print("═" * 65)
    print(f"\nOriginal text ({len(short_text)} chars):\n  {short_text!r}\n")

    splitter = CharacterTextSplitter(
        separator=" ",
        chunk_size=40,
        chunk_overlap=10,
        length_function=len
    )

    chunks = splitter.split_text(short_text)

    for i, chunk in enumerate(chunks):
        print(f"Chunk {i+1} ({len(chunk):2d} chars): {chunk!r}")

    print()
    # Show overlap explicitly
    if len(chunks) >= 2:
        overlap_candidate = chunks[1][:10]
        tail_of_chunk0 = chunks[0][-10:]
        print(f"End of chunk 0:   {tail_of_chunk0!r}")
        print(f"Start of chunk 1: {chunks[1][:10]!r}")
        # Find common suffix/prefix
        print(f"→ Both chunks share the boundary context (overlap).\n")


# ══════════════════════════════════════════════════════════════════════════════
# KEY TAKEAWAYS printed at the end
# ══════════════════════════════════════════════════════════════════════════════

def print_takeaways():
    print("=" * 65)
    print("KEY TAKEAWAYS — Fixed-Size Chunking")
    print("=" * 65)
    print("""
  1. Character-based splitting IGNORES linguistic structure.
     Words, sentences, and paragraphs may all be cut mid-way.

  2. Overlap reduces (but doesn't eliminate) context loss at boundaries.
     Rule of thumb: overlap = 10–20% of chunk_size.

  3. CharacterTextSplitter has NO fallback logic.
     If the text between two separators is larger than chunk_size,
     it will split mid-character. RecursiveCharacterTextSplitter (Strategy 2)
     fixes this with a cascade of fallback separators.

  4. For MiniLM embeddings: keep chunks under ~600 characters
     (≈ 150 tokens, leaving buffer under the 256-token limit).

  NEXT UP → Strategy 2: Recursive Character Splitting
  → python 02_recursive_character.py
""")


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n🔍 Running all Fixed-Size Chunking demos...\n")

    demo_a_pure_character()
    print("\n" + "─" * 65 + "\n")

    demo_b_word_boundary()
    print("\n" + "─" * 65 + "\n")

    demo_c_paragraph_boundary()
    print("\n" + "─" * 65 + "\n")

    demo_d_overlap_visualised()

    print_takeaways()
