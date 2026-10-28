"""L20 / M59 - Short-term memory: thread history, trimming, context editing.

Run:  python ex13_short_term_memory.py

Short-term memory = the conversation history that lives in the CHECKPOINT,
scoped to one thread. Three techniques, in increasing order of "smartness":

  1. TRIM MESSAGES        - you drop old messages yourself before calling
                            the model. Simple, total control, but you throw
                            information away.
  2. CONTEXT EDITING      - the agent keeps everything, but when the prompt
                            gets too big it REPLACES old tool OUTPUTS with a
                            placeholder. The conversation shape survives, the
                            bulky payloads do not.
  3. SUMMARIZATION        - the agent replaces old messages with a written
                            summary. Maximum compaction, some information loss.

All three are about ONE thing: the model's context window is finite, and a
long conversation will eventually overflow it.
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain.agents.middleware import ContextEditingMiddleware
from langchain.agents.middleware.context_editing import ClearToolUsesEdit
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from _common import ScriptedChatModel, banner

BIG = "DOC " + ("lorem ipsum dolor sit amet " * 40)


def search_docs(query: str) -> str:
    """Search the knowledge base and return a long document."""
    return f"[results for {query}] {BIG}"


def build_agent(middleware=None):
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "search_docs", "args": {"query": "refunds"}, "id": "t1"}],
            ),
            AIMessage(content="Here is what I found about refunds."),
            AIMessage(
                content="",
                tool_calls=[{"name": "search_docs", "args": {"query": "returns"}, "id": "t2"}],
            ),
            AIMessage(content="And here is the returns policy."),
        ]
    )
    agent = create_agent(
        model=model,
        tools=[search_docs],
        middleware=list(middleware or []),
        checkpointer=InMemorySaver(),
    )
    return agent, model


def main() -> None:
    banner("0. The problem: tool output eats the context window")
    agent, model = build_agent()
    cfg = {"configurable": {"thread_id": "stm-1"}}
    agent.invoke({"messages": [HumanMessage("find refunds")]}, cfg, version="v2")
    agent.invoke({"messages": [HumanMessage("and returns?")]}, cfg, version="v2")
    msgs = agent.get_state(cfg).values["messages"]
    for m in msgs:
        print(f"  {m.type:<6} len={len(str(m.content)):>6} {str(m.content)[:45]!r}")
    print("-> one tool result is already a few KB of text.")

    banner("1. Technique 1: trim_messages (do it yourself)")
    from langchain_core.messages import trim_messages

    trimmed = trim_messages(
        msgs,
        max_tokens=60,
        token_counter="approximate",
        strategy="last",
        include_system=True,
    )
    print("kept", len(trimmed), "of", len(msgs), "messages")
    for m in trimmed:
        print(f"  {m.type:<6} len={len(str(m.content)):>6} {str(m.content)[:45]!r}")
    print()
    print("-> `trim_messages` needs the LangChain core helper; it drops")
    print("   messages, so information is gone forever.")
    print("-> use it when you KNOW what matters (e.g. keep the last N turns).")

    banner("2. Technique 2: ContextEditingMiddleware")
    print("Default edit = ClearToolUsesEdit: when the prompt exceeds `trigger`,")
    print("old tool RESULTS are replaced with a placeholder.")
    print()
    agent2, model2 = build_agent(
        middleware=[
            ContextEditingMiddleware(
                edits=[ClearToolUsesEdit(trigger=100, keep=1, clear_at_least=50)]
            )
        ]
    )
    cfg2 = {"configurable": {"thread_id": "stm-2"}}
    agent2.invoke({"messages": [HumanMessage("find refunds")]}, cfg2, version="v2")
    agent2.invoke({"messages": [HumanMessage("and returns?")]}, cfg2, version="v2")
    msgs2 = agent2.get_state(cfg2).values["messages"]
    for m in msgs2:
        flag = m.response_metadata.get("context_editing", {}) if hasattr(m, "response_metadata") else {}
        print(f"  {m.type:<6} len={len(str(m.content)):>6} cleared={flag.get('cleared')} "
              f"{str(m.content)[:45]!r}")
    print()
    print(">>> IMPORTANT: the stored state is UNCHANGED.")
    print("    ContextEditingMiddleware edits the MODEL REQUEST, not the")
    print("    checkpoint. The stored transcript stays complete.")
    print()
    print("Here is what the MODEL actually received on the last call:")
    for m in model2.calls[-1].messages:
        print(f"  {m.type:<6} len={len(str(m.content)):>6} {str(m.content)[:60]!r}")
    print()
    print("-> The OLD tool result was replaced by a placeholder; the newest")
    print("   one (keep=1) is intact. The AI/tool pairing stays valid.")
    print()
    print("And the checkpoint still holds the FULL text:")
    print("   ", repr(str(msgs2[2].content)[:70]), "...")

    banner("3. What the MODEL actually received")
    # The model call is the last one in the script; inspect its prompt.
    print("-> see the next example (ex14) for summarization.")
    print()
    print("Key insight: the CHECKPOINT keeps the ORIGINAL tool output.")
    print("Only the prompt sent to the model is edited. That means:")
    print("  * the transcript in your DB stays complete and auditable")
    print("  * the model sees a compacted view")
    print("  * re-running from an old checkpoint still has the real data")

    banner("4. The pieces of ContextEditingMiddleware")
    print("ContextEditingMiddleware(")
    print("    edits=[ClearToolUsesEdit(")
    print("        trigger=100_000,     # token count that triggers the edit")
    print("        clear_at_least=0,    # min tokens to try to reclaim")
    print("        keep=3,              # keep the N most recent tool results")
    print("        clear_tool_inputs=False,")
    print("        exclude_tools=(),    # never clear these tools' outputs")
    print("        placeholder='<tool output cleared>',")
    print("    )],")
    print("    token_count_method='approximate',  # or 'model'")
    print(")")
    print()
    print("'approximate' counts ~4 chars/token -> no tokenizer needed.")
    print("'model' uses the model's real tokenizer -> accurate, slower.")

    banner("5. Manual context budgeting (the low-level version)")
    msgs3 = agent.get_state(cfg).values["messages"]
    total = sum(len(str(m.content)) for m in msgs3)
    print(f"raw characters in history: {total}")
    budget = 2000
    kept = []
    running = 0
    for m in reversed(msgs3):
        size = len(str(m.content))
        if running + size > budget and kept:
            break
        kept.append(m)
        running += size
    kept.reverse()
    print(f"kept {len(kept)}/{len(msgs3)} messages within {budget} chars")
    print("-> This is what ContextEditingMiddleware does for you, but with")
    print("   tool-aware semantics and a placeholder instead of a hard cut.")


if __name__ == "__main__":
    main()
