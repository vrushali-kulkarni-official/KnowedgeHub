"""EX01 — Single agent + tools vs. a supervisor team: the numbers that decide.

Run:  PYTHONPATH=examples .venv/bin/python examples/ex01_decision_matrix.py

THE QUESTION THIS ANSWERS
-------------------------
"Should I split my agent into several agents?"

The honest answer is "usually not". A single agent with good tools is cheaper,
faster and easier to debug. Multi-agent earns its keep for exactly three
reasons:

  1. CONTEXT ISOLATION - a specialist that only ever sees its own slice of
     the world does not get distracted by the rest of it.
  2. PARALLELISM      - independent subtasks can run at the same time.
  3. SPECIALIZATION   - one focused prompt beats one muddled prompt.

This example *measures* those effects instead of asserting them.

IMPORTANT MEASUREMENT NOTE
--------------------------
When a supervisor calls a worker agent, the worker's messages live in the
WORKER's state - they are NOT copied into the supervisor's transcript.  So if
you count only the top-level `result["messages"]` you will under-count badly.

You must count model calls at the MODEL level (each scripted model records
its own invocations).  That is exactly what this example does.
"""

from __future__ import annotations

import time

from langchain.agents import create_agent
from langchain_core.tools import tool

from _common import once_then_final, scripted, user, text_of

# Every invoke in this course sets an explicit recursion_limit.  Without it,
# create_agent defaults to 9999 supersteps (verified in langchain 1.4.9) and a
# runaway loop becomes a hang instead of an error.
LIMIT = {"recursion_limit": 20}

# ---------------------------------------------------------------------------
# 1. A single agent that can do everything
# ---------------------------------------------------------------------------


@tool
def web_search(query: str) -> str:
    """Search the web for factual information."""
    return f"web results for '{query}': LangGraph is a graph framework."


@tool
def read_invoice(invoice_id: str) -> str:
    """Read a billing invoice."""
    return f"invoice {invoice_id}: total 49.00 EUR, status paid."


@tool
def open_ticket(title: str) -> str:
    """Open a support ticket."""
    return f"ticket created: {title}"


@tool
def send_email(to: str, body: str) -> str:
    """Send an email to a customer."""
    return f"email sent to {to}"


# ---------------------------------------------------------------------------
# 2. A supervisor team: 1 supervisor + 3 specialists, each with 1 tool
# ---------------------------------------------------------------------------


def make_worker(name: str, tool_obj, model):
    """A specialist agent wrapped so a supervisor can call it as a tool."""
    agent = create_agent(model, tools=[tool_obj], name=name)

    @tool(f"ask_{name}", description=f"Delegate a {name} task to a specialist.")
    def ask_specialist(task: str) -> str:
        result = agent.invoke({"messages": [user(task)]}, LIMIT)
        return text_of(result["messages"][-1])

    return ask_specialist, agent


def build_single_agent():
    """One agent, four tools, one model."""
    model = scripted(
        router=once_then_final(
            "web_search",
            {"query": "langgraph"},
            final="LangGraph is a low-level orchestration framework.",
            call_id="c1",
        )
    )
    agent = create_agent(
        model,
        tools=[web_search, read_invoice, open_ticket, send_email],
        name="solo_agent",
    )
    return agent, [model]


def build_supervisor_team():
    """One supervisor, three specialists - four models in total."""
    researcher_model = scripted(
        router=once_then_final(
            "web_search",
            {"query": "langgraph"},
            final="LangGraph is a low-level orchestration framework.",
            call_id="c1",
        )
    )
    billing_model = scripted(
        router=once_then_final(
            "read_invoice",
            {"invoice_id": "INV-1"},
            final="invoice INV-1: 49.00 EUR, paid.",
            call_id="c2",
        )
    )
    support_model = scripted(
        router=once_then_final(
            "open_ticket",
            {"title": "access issue"},
            final="ticket created: access issue",
            call_id="c3",
        )
    )

    researcher, _ = make_worker("researcher", web_search, researcher_model)
    billing, _ = make_worker("billing", read_invoice, billing_model)
    support, _ = make_worker("support", open_ticket, support_model)

    supervisor_model = scripted(
        router=once_then_final(
            "ask_researcher",
            {"task": "what is langgraph"},
            final="LangGraph is a low-level orchestration framework.",
            call_id="c0",
        )
    )
    supervisor = create_agent(
        supervisor_model, tools=[researcher, billing, support], name="supervisor"
    )
    return supervisor, [supervisor_model, researcher_model, billing_model, support_model]


def measure(label, agent, models, question):
    """Count model calls across the WHOLE agent tree, not just the top level."""
    start = time.perf_counter()
    result = agent.invoke({"messages": [user(question)]}, LIMIT)
    elapsed = (time.perf_counter() - start) * 1000

    messages = result["messages"]
    # The honest metric: how many LLM round trips happened anywhere.
    model_calls = sum(m.n_calls for m in models)
    tool_calls = sum(1 for m in messages if m.type == "tool")
    # Cheap proxy for "tokens" - characters in the TOP-LEVEL transcript.
    # A supervisor transcript stays small; the worker transcript is separate.
    chars = sum(len(text_of(m)) for m in messages)
    return {
        "label": label,
        "agents": len(models),
        "model_calls": model_calls,
        "tool_calls": tool_calls,
        "messages": len(messages),
        "prompt_chars": chars,
        "ms": elapsed,
        "answer": text_of(messages[-1]),
    }


def main() -> None:
    print("=" * 74)
    print("EX01  Single agent vs supervisor team")
    print("=" * 74)

    question = "What is LangGraph?"
    solo, solo_models = build_single_agent()
    team, team_models = build_supervisor_team()

    a = measure("single agent + 4 tools", solo, solo_models, question)
    b = measure("supervisor + 3 specialists", team, team_models, question)

    print(f"\nQuestion: {question!r}\n")
    header = f"{'metric':<24}{'single agent':>18}{'supervisor team':>20}"
    print(header)
    print("-" * len(header))
    for key in ("agents", "model_calls", "tool_calls", "messages", "prompt_chars", "ms"):
        av = f"{a[key]:.2f}" if key == "ms" else str(a[key])
        bv = f"{b[key]:.2f}" if key == "ms" else str(b[key])
        print(f"{key:<24}{av:>18}{bv:>20}")
    print()

    print("ANSWER")
    print("-------")
    print(f"  single agent  -> {a['answer'][:66]}")
    print(f"  supervisor    -> {b['answer'][:66]}")
    print()
    print("READING THE NUMBERS")
    print("---------------------")
    extra = b["model_calls"] - a["model_calls"]
    print(f"  The supervisor team used {extra} extra LLM round trip(s).")
    print()
    print("  * model_calls is the number that matters for MONEY and LATENCY.")
    print("    Every extra agent boundary is at least one extra round trip.")
    print("  * prompt_chars shows CONTEXT ISOLATION working: the supervisor's")
    print("    transcript stays short because the specialist's transcript stays")
    print("    inside the specialist.")
    print("  * The team is only worth it when the specialist's narrow focus")
    print("    produces a BETTER answer, or when subtasks run in PARALLEL (L08).")
    print()
    print("  => Default answer: keep ONE agent until you can name which of the")
    print("     three reasons you need (isolation / parallelism / specialization).")


if __name__ == "__main__":
    main()
