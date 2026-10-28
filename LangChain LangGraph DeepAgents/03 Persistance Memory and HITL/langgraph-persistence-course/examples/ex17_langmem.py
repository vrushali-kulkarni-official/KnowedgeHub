"""L21 / M60 - langmem: automatic long-term memory.

Run:  python ex17_langmem.py

langmem (MIT, still PRE-1.0 - pin your version!) gives you two ways to build
long-term memory:

  A. TOOL-BASED (explicit)
       The agent decides what is worth remembering and calls a tool.
       create_manage_memory_tool(...)  -> create / update / delete a memory
       create_search_memory_tool(...)  -> recall relevant memories
       You control exactly what is stored. No LLM surprise.

  B. MANAGER-BASED (automatic)
       create_memory_store_manager(model, ...) reads a conversation, extracts
       memories, and writes them to the Store.
       The namespace can be TEMPLATED:
           namespace=("memories", "{langgraph_user_id}")
       where {langgraph_user_id} is filled from config["configurable"].

This example uses a scripted model so it runs offline. With a real model the
manager issues a tool call named `Memory` (plus `PatchDoc` / `PatchFunctionErrors`
for updates) - that is trustcall's strict structured-calling contract.

Memory design (the part everyone gets wrong):
    FACT       - "works at Acme"                -> stable, checkable
    PREFERENCE - "prefers metric units"         -> changes rarely, applies always
    PROCEDURE  - "check the CRM before quoting" -> how to act, not what is true
Store these with a `kind` field. Conflicting memories are resolved by the
manager (it can UPDATE an existing memory instead of creating a duplicate).
"""

from __future__ import annotations

import asyncio
import json

from langchain_core.messages import AIMessage, HumanMessage
from langmem import create_manage_memory_tool, create_memory_store_manager, create_search_memory_tool
from langgraph.store.memory import InMemoryStore

from _common import ScriptedChatModel, banner


async def main() -> None:
    store = InMemoryStore()

    # ======================================================================
    banner("A. TOOL-BASED memory: the agent decides what to remember")
    manage_tool = create_manage_memory_tool(
        namespace=("memories", "{langgraph_user_id}"),
        store=store,
        actions_permitted=("create", "update", "delete"),
    )
    search_tool = create_search_memory_tool(
        namespace=("memories", "{langgraph_user_id}"),
        store=store,
    )

    print("built with langmem.create_manage_memory_tool(...)")
    print("manage tool name:", manage_tool.name)
    print("manage tool args:", json.dumps(manage_tool.args, indent=2)[:600])
    print()
    print("built with langmem.create_search_memory_tool(...)")
    print("search tool name:", search_tool.name)

    cfg = {"configurable": {"thread_id": "t1", "langgraph_user_id": "alice"}}

    banner("A2. The agent calls manage_memory")
    result = await manage_tool.ainvoke(
        {
            "action": "create",
            "content": "prefers metric units",
            "category": "preference",
        },
        config=cfg,
    )
    print("result:", result)

    await manage_tool.ainvoke(
        {
            "action": "create",
            "content": "works at Acme Corp as a data engineer",
            "category": "fact",
        },
        config=cfg,
    )
    print()
    print("what is in the store now:")
    for it in store.search(("memories", "alice")):
        print(f"  {it.key}: {it.value}")

    banner("A3. The agent calls search_memory")
    found = await search_tool.ainvoke({"query": "units"}, config=cfg)
    print("result:", found)

    banner("A4. Namespace isolation")
    cfg_bob = {"configurable": {"thread_id": "t2", "langgraph_user_id": "bob"}}
    await manage_tool.ainvoke(
        {"action": "create", "content": "prefers light mode", "category": "preference"},
        config=cfg_bob,
    )
    print("alice sees:", [i.value.get("content") for i in store.search(("memories", "alice"))])
    print("bob sees  :", [i.value.get("content") for i in store.search(("memories", "bob"))])

    # ======================================================================
    banner("B. MANAGER-BASED memory: automatic extraction")
    print("create_memory_store_manager(model, namespace=..., store=...)")
    print("The namespace TEMPLATE {langgraph_user_id} is resolved from")
    print("config['configurable']['langgraph_user_id'].")
    print()

    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "Memory",
                    "args": {"content": "alice prefers metric units"},
                    "id": "mem-1",
                }],
            )
        ]
    )
    manager = create_memory_store_manager(
        model,
        store=store,
        namespace=("memories", "{langgraph_user_id}"),
    )

    print(">>> FIRST: run the manager over memories written by the TOOL.")
    print("    The manager reads existing memories to decide whether to")
    print("    CREATE, UPDATE or leave them alone. It expects every value")
    print("    to have a top-level 'kind' key.")
    try:
        await manager.ainvoke(
            {"messages": [HumanMessage("I always want metric units, never imperial.")]},
            config=cfg,
        )
        print("    -> ok")
    except KeyError as e:
        print(f"    -> KeyError: {e}")
        print("    -> GOTCHA: the two langmem APIs use DIFFERENT value shapes:")
        print("         manage_memory tool writes : {'content': '...'}")
        print("         the manager expects         : {'kind': ..., 'content': ...}")
        print("       If you mix them in one namespace, the manager crashes.")
        print("       Pick ONE shape and use it everywhere.")

    banner("B2. FIX: write memories in the manager-compatible shape")
    for it in list(store.search(("memories", "alice"))):
        store.delete(it.namespace, it.key)
    store.put(("memories", "alice"), "mem-pref",
              {"kind": "preference", "content": "prefers metric units"})
    store.put(("memories", "alice"), "mem-fact",
              {"kind": "fact", "content": "works at Acme Corp as a data engineer"})
    print("alice's memories (canonical shape):")
    for it in store.search(("memories", "alice")):
        print(f"  {it.key}: {it.value}")

    print()
    out = await manager.ainvoke(
        {"messages": [HumanMessage("I always want metric units, never imperial.")]},
        config=cfg,
    )
    print("manager output:", out)
    print()
    print("store now:")
    for it in store.search(("memories", "alice")):
        print(f"  {it.namespace} / {it.key} = {it.value}")

    # ======================================================================
    banner("C. HOT PATH vs BACKGROUND")
    print("HOT PATH (inline):")
    print("    await manager.ainvoke(...)   # inside your request handler")
    print("    + the memory is fresh immediately")
    print("    + simple, no extra infrastructure")
    print("    - you pay the LLM latency on EVERY request")
    print("    - the request is slower")
    print()
    print("BACKGROUND (out of band):")
    print("    asyncio.create_task(manager.ainvoke(...))   # fire and forget")
    print("    or a separate worker that drains a queue")
    print("    + the user is not blocked by extraction")
    print("    + you can batch, retry and rate-limit extraction")
    print("    - the memory is not there YET (eventual consistency)")
    print("    - you need somewhere to put the failures")
    print()
    print("The LangGraph-native way to do background work in a node:")
    print()
    print("    from langgraph.types import Command")
    print("    # ...or simply run the manager in a FastAPI BackgroundTasks")
    print("    #    / Celery task / arq job / K8s CronJob.")
    print()
    print("Practical default: run extraction in the BACKGROUND, and let the")
    print("agent READ memories at the start of the next turn.")

    banner("D. Memory design: facts vs preferences vs procedures")
    examples = [
        ("fact", "user's email is a@b.com", "stable fact, verifiable"),
        ("preference", "prefers dark mode", "applies to every future interaction"),
        ("procedure", "always confirm before emailing", "how the agent should ACT"),
    ]
    for kind, content, why in examples:
        print(f"  {kind:<12} {content:<40} ({why})")
    print()
    print("Give every memory a `kind`. It lets you:")
    print("  * filter recall by kind (procedures are global, facts are personal)")
    print("  * resolve conflicts by kind (a new fact beats an old fact;")
    print("    a new preference REPLACES the old preference)")
    print("  * expire things that should not live forever")

    banner("E. Conflicting memories")
    print("Say 'actually, use imperial units now':")
    model2 = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "Memory",
                    "args": {"content": "alice uses imperial units"},
                    "id": "mem-2",
                }],
            )
        ]
    )
    manager2 = create_memory_store_manager(
        model2, store=store, namespace=("memories", "{langgraph_user_id}")
    )
    await manager2.ainvoke(
        {"messages": [HumanMessage("actually use imperial units now")]}, config=cfg
    )
    print("alice's memories now:")
    for it in store.search(("memories", "alice")):
        print(f"  {it.key}: {it.value.get('content')}")
    print()
    print("-> With a real model the manager SEEES the existing memories")
    print("   (it searches the store first) and emits a PATCH instead of a")
    print("   duplicate, so you get one row per fact, not a pile of rows.")

    banner("F. langmem version status")
    print("langmem is MIT-licensed but STILL PRE-1.0 (0.0.x).")
    print("Pin it exactly and read the changelog before upgrading:")
    print('    uv add "langmem==0.0.30"')
    print("If you want zero extra dependencies, the Store API on its own")
    print("(put/get/search/delete) gives you everything you need - langmem")
    print("just adds the LLM-driven extraction on top.")


if __name__ == "__main__":
    asyncio.run(main())
