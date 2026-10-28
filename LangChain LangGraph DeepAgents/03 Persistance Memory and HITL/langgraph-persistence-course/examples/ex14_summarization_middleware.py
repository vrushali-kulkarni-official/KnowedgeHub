"""L20 / M59 - SummarizationMiddleware: compacting a long conversation.

Run:  python ex14_summarization_middleware.py

Context editing (previous example) drops BULK. Summarization drops
INFORMATION: old messages are replaced by a written summary produced by a
model you choose.

    SummarizationMiddleware(
        model=<a cheap model>,
        trigger=("messages", 30),   # or ("tokens", N) or ("fraction", 0.8)
        keep=("messages", 20),      # keep the last N messages verbatim
    )

How the trigger works:
    ("messages", N)  summarize once the history has N messages
    ("tokens", N)    summarize once the history has ~N tokens
    ("fraction", f)  summarize once the history is f of the model's window

`keep` works the same way: the most recent K messages stay verbatim, the
older ones get replaced by the summary.

Use a CHEAP model for summarization. You are paying for every summarization.
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from _common import ScriptedChatModel, banner


def build_agent(trigger=("messages", 6), keep=("messages", 2)):
    # The agent's model: just answers.
    agent_model = ScriptedChatModel(
        responses=[AIMessage(content="ok") for _ in range(20)],
        repeat_last=True,
    )
    # The summarizer: a different (in production: cheaper) model.
    summarizer = ScriptedChatModel(
        responses=[
            AIMessage(
                content="SUMMARY: The user asked about refunds, then returns. "
                "We found the refund policy and the returns policy in the docs."
            )
        ],
        repeat_last=True,
    )
    agent = create_agent(
        model=agent_model,
        tools=[],
        middleware=[
            SummarizationMiddleware(model=summarizer, trigger=trigger, keep=keep)
        ],
        checkpointer=InMemorySaver(),
    )
    return agent, agent_model, summarizer


def main() -> None:
    banner("0. Build a conversation that is too long")
    agent, agent_model, summarizer = build_agent()
    cfg = {"configurable": {"thread_id": "sum-1"}}

    for i in range(5):
        agent.invoke({"messages": [HumanMessage(f"question number {i}")]}, cfg, version="v2")

    msgs = agent.get_state(cfg).values["messages"]
    print(f"messages in state: {len(msgs)}")
    for m in msgs:
        print(f"  {m.type:<6} {str(m.content)[:60]!r}")

    banner("1. Was a summary produced?")
    print("summarizer calls:", len(summarizer.calls))
    if summarizer.calls:
        sent = summarizer.calls[0].messages
        print(f"the summarizer was given {len(sent)} messages:")
        for m in sent[:4]:
            print(f"   {m.type:<6} {str(m.content)[:60]!r}")
        print("   ...")

    banner("2. What the agent's model sees now")
    if agent_model.calls:
        for m in agent_model.calls[-1].messages:
            print(f"  {m.type:<6} {str(m.content)[:70]!r}")
    print()
    print("-> The history is now: [summary] + the last few messages.")
    print("-> That is the context-window budget in action.")

    banner("3. The summary is IN the state (unlike context editing)")
    msgs2 = agent.get_state(cfg).values["messages"]
    has_summary = any("SUMMARY" in str(m.content) for m in msgs2)
    print("state contains the summary:", has_summary)
    print()
    print("-> ContextEditingMiddleware edits the REQUEST only (state keeps")
    print("   everything). SummarizationMiddleware REWRITES the state.")
    print("   Choose based on whether you need the full transcript later:")
    print("     * need a complete transcript  -> context editing")
    print("     * only need the agent to work -> summarization")

    banner("4. Trigger and keep, side by side")
    for trig in [("messages", 4), ("messages", 100), ("tokens", 50)]:
        a, _, _ = build_agent(trigger=trig, keep=("messages", 2))
        c = {"configurable": {"thread_id": f"t-{trig[0]}-{trig[1]}"}}
        for i in range(4):
            a.invoke({"messages": [HumanMessage(f"q{i}")]}, c, version="v2")
        n = len(a.get_state(c).values["messages"])
        print(f"  trigger={str(trig):<22} -> {n} messages after 4 turns")

    banner("4b. (\"fraction\", f) needs a model PROFILE")
    print("Fractional triggers are relative to the model's context window,")
    print("so LangGraph must know that window. For a real model, pass it:")
    print()
    print("    from langchain_google_genai import ChatGoogleGenerativeAI")
    print("    model = ChatGoogleGenerativeAI(")
    print("        model='gemini-2.5-flash',")
    print("        google_api_key=os.environ['GOOGLE_API_KEY'],")
    print("        profile={'max_input_tokens': 1048576},")
    print("    )")
    print("    SummarizationMiddleware(model=model, trigger=('fraction', 0.8))")
    print()
    try:
        build_agent(trigger=("fraction", 0.5))
    except ValueError as e:
        print("Without a profile you get:")
        print("   ", str(e).splitlines()[0])
    print()
    print("-> Absolute triggers ('messages'/'tokens') always work.")

    banner("5. Which model should summarize?")
    print("  * Use the SAME model if quality matters most.")
    print("  * Use a CHEAPER model (e.g. gemini-2.5-flash-lite) for summaries -")
    print("    you call it on every trigger, and summaries are usually")
    print("    forgiving of imperfection.")
    print("  * You can pass a model STRING:")
    print("      SummarizationMiddleware(model='google_genai:gemini-2.5-flash-lite')")


if __name__ == "__main__":
    main()
