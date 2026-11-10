"""EX16 - Debugging a multi-agent system with LangGraph streaming.

Run:  PYTHONPATH=examples .venv/bin/python examples/ex16_debugging_streaming.py

`graph.invoke()` gives you the final answer and nothing else.  When a
multi-agent system misbehaves, you need to see the intermediate steps.

LangGraph gives you FOUR streaming modes, and each answers a different
question:

  stream_mode="values"    - the FULL state after every step.
                            "What did the shared state look like?"
  stream_mode="updates"   - only what CHANGED, per node.
                            "Which node did what?"
  stream_mode="messages"  - LLM tokens, as they arrive.
                            "What is the model actually saying?"
  stream_mode="tasks"     - task-level input, result and error.
                            "Where did it fail?"

AND ONE FLAG:
  subgraphs=True          - include the steps of NESTED agents, tagged with
                            their namespace tuple.

THE NAMESPACE IS THE KEY
------------------------
When a supervisor calls a worker, the worker's internal steps are tagged:

    ('supervisor:8f3c-...',)

That tuple tells you EXACTLY which nested agent produced the step.  Without
`subgraphs=True` you only see the top level, and a multi-agent system looks
like a single agent that mysteriously does a lot.
"""

from __future__ import annotations

from typing import Annotated

from langchain.agents import AgentState, create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph

from _common import once_then_final, scripted, text_of, user

LIMIT = {"recursion_limit": 20}


# ---------------------------------------------------------------------------
# A team with something to debug
# ---------------------------------------------------------------------------


@tool
def web_search(query: str) -> str:
    """Search the web."""
    return f"web: 2 results for {query}"


def build_team():
    researcher = create_agent(
        scripted(
            router=once_then_final(
                "web_search", {"query": "langgraph"}, final="3 findings about langgraph"
            )
        ),
        tools=[web_search],
        name="researcher",
    )

    def as_tool(name, description, agent):
        @tool(f"ask_{name}", description=description)
        def ask(task: str) -> str:
            r = agent.invoke({"messages": [HumanMessage(content=task)]}, LIMIT)
            return text_of(r["messages"][-1])

        return ask

    supervisor = create_agent(
        scripted(
            router=once_then_final(
                "ask_researcher", {"task": "research langgraph"}, final="Summary ready."
            )
        ),
        tools=[as_tool("researcher", "Delegate research.", researcher)],
        name="supervisor",
    )

    class TeamState(AgentState):
        results: Annotated[list[str], lambda a, b: a + b]

    def sup_node(state: TeamState):
        r = supervisor.invoke({"messages": state["messages"]}, LIMIT)
        return {"messages": [r["messages"][-1]], "results": [text_of(r["messages"][-1])]}

    g = StateGraph(TeamState)
    g.add_node("supervisor", sup_node)
    g.add_edge(START, "supervisor")
    g.add_edge("supervisor", END)
    return g.compile()


def norm(chunk):
    """Normalise the different chunk shapes into (namespace, mode, payload)."""
    if isinstance(chunk, tuple) and len(chunk) == 3:
        return chunk
    if isinstance(chunk, tuple) and len(chunk) == 2:
        return chunk[0], "?", chunk[1]
    return None, "?", chunk


def main() -> None:
    print("=" * 74)
    print("EX16  Debugging with streaming")
    print("=" * 74)

    app = build_team()
    inputs = {"messages": [user("Research LangGraph")], "results": []}

    print("\n1. stream_mode='updates' + subgraphs=True")
    print("-" * 74)
    print("   (namespace, mode, {node: update})")
    for chunk in app.stream(inputs, stream_mode=["updates"], subgraphs=True):
        ns, mode, payload = norm(chunk)
        if isinstance(payload, dict):
            for node, upd in payload.items():
                keys = list(upd.keys()) if isinstance(upd, dict) else type(upd).__name__
                print(f"   ns={ns} node={node!r} updated={keys}")

    print("\n2. stream_mode='tasks' + subgraphs=True")
    print("-" * 74)
    print("   (namespace, mode, {id, name, error, result})")
    for chunk in app.stream(inputs, stream_mode=["tasks"], subgraphs=True):
        ns, mode, payload = norm(chunk)
        if isinstance(payload, dict):
            name = payload.get("name")
            has_result = "result" in payload
            err = payload.get("error")
            print(f"   ns={ns} task={name!r} result={has_result} error={err}")

    print("\n3. stream_mode='values'")
    print("-" * 74)
    print("   (the FULL state after each step)")
    for i, chunk in enumerate(app.stream(inputs, stream_mode="values")):
        payload = chunk
        if isinstance(chunk, tuple):
            payload = chunk[-1]
        if isinstance(payload, dict):
            print(f"   step {i}: keys={sorted(payload.keys())} results={payload.get('results')}")

    print("\n4. stream_mode='messages'")
    print("-" * 74)
    print("   (LLM messages as they are produced, tagged with their node)")
    for chunk in app.stream(inputs, stream_mode="messages", subgraphs=True):
        ns, mode, payload = norm(chunk)
        if isinstance(payload, tuple) and len(payload) == 2:
            msg, meta = payload
            node = meta.get("langgraph_node")
            name = meta.get("langgraph_checkpoint_ns")
            print(f"   ns={ns} node={node!r} type={msg.type} "
                  f"content={text_of(msg)[:44]!r}")

    print()
    print("=" * 74)
    print("THE DEBUGGING PLAYBOOK")
    print("=" * 74)
    print(
        """
  SYMPTOM: the final answer is wrong.
    -> stream_mode="updates", subgraphs=True.
       Find the LAST node that ran before the bad answer.  Which agent
       produced it?  Look at its namespace.

  SYMPTOM: an agent seems to ignore the brief.
    -> stream_mode="messages".  Read what the specialist ACTUALLY received.
       A `HumanMessage` with the wrong text means the handoff is broken,
       not the model.

  SYMPTOM: the run hangs or loops.
    -> stream_mode="tasks".  The task names repeat.  That is your loop.
       Add a visit counter (EX09) and a ModelCallLimitMiddleware (EX14).

  SYMPTOM: the shared state looks wrong.
    -> stream_mode="values".  Step through the state and find the step
       where it went wrong.  Then check the reducer (EX08: append reducers
       and the echo trap).

  SYMPTOM: a branch of a fan-out produced nothing.
    -> stream_mode="updates", subgraphs=True.  Look for a namespace that
       appears with a `tools` span but no `model` span afterwards.

  THE THREE NUMBERS TO CHECK FIRST
    1. How many model calls?  (should match your expectation)
    2. How many agents ran?  (did a specialist run twice?)
    3. How big was each agent's input?  (context isolation working?)
"""
    )


if __name__ == "__main__":
    main()
