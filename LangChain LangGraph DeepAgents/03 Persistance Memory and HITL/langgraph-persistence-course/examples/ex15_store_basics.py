"""L21 / M60 - The Store: long-term memory across threads.

Run:  python ex15_store_basics.py

A CHECKPOINTER and a STORE solve different problems:

    Checkpointer  "what is the graph's state right now, for THIS thread?"
    Store         "what does the application know, for ANY thread?"

The Store is a namespaced key-value store with optional semantic search.

    from langgraph.store.memory import InMemoryStore
    from langgraph.store.postgres import PostgresStore

    store.put(("users", "alice", "memories"), "pref-1",
              {"content": "prefers dark mode"})

    store.get(("users", "alice", "memories"), "pref-1")
    store.search(("users", "alice"), query="dark mode")
    store.delete(("users", "alice", "memories"), "pref-1")

NAMESPACES are tuples of strings, read RIGHT TO LEFT as a hierarchy:

    ("users", "alice", "memories")
      users  -> alice -> memories

`search()` takes a PREFIX and returns everything under it:

    store.search(("users", "alice"))           -> alice's memories
    store.search(("users", "alice", "memories")) -> exactly that level

This example covers the full CRUD surface, namespace semantics, and how a
graph node reads and writes the store via `get_store()`.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.config import get_store
from langgraph.graph import END, START, StateGraph
from langgraph.store.memory import InMemoryStore

from _common import banner


def main() -> None:
    store = InMemoryStore()

    banner("1. put / get")
    store.put(("users", "alice", "memories"), "pref-1",
              {"content": "prefers dark mode", "kind": "preference"})
    store.put(("users", "alice", "memories"), "fact-1",
              {"content": "works at Acme Corp", "kind": "fact"})

    item = store.get(("users", "alice", "memories"), "pref-1")
    print("get(pref-1):")
    print("  .value    :", item.value)
    print("  .namespace:", item.namespace)
    print("  .key      :", item.key)
    print("  .created_at:", item.created_at)
    print("  .updated_at:", item.updated_at)

    print("\nget(missing) ->", store.get(("users", "alice", "memories"), "nope"))

    banner("2. Namespace hierarchy")
    store.put(("users", "bob", "memories"), "pref-1",
              {"content": "prefers light mode"})
    store.put(("users", "alice", "projects"), "proj-1",
              {"content": "building a flight tracker"})
    store.put(("global", "rules"), "rule-1",
              {"content": "always answer in metric units"})

    print("store.search(('users',))                 ->")
    for it in store.search(("users",)):
        print(f"   {it.namespace} / {it.key} = {it.value['content']!r}")
    print()
    print("store.search(('users', 'alice'))           ->")
    for it in store.search(("users", "alice")):
        print(f"   {it.namespace} / {it.key} = {it.value['content']!r}")
    print()
    print("store.search(('users', 'alice', 'memories')) ->")
    for it in store.search(("users", "alice", "memories")):
        print(f"   {it.namespace} / {it.key} = {it.value['content']!r}")

    banner("3. list_namespaces - what namespaces exist?")
    for ns in store.list_namespaces(prefix=("users",)):
        print("  ", ns)

    banner("4. delete")
    store.delete(("users", "alice", "memories"), "fact-1")
    print("after delete, alice's memories:")
    for it in store.search(("users", "alice", "memories")):
        print(f"   {it.key} = {it.value['content']!r}")

    banner("5. batch() - many operations, one round trip")
    from langgraph.store.base import GetOp, PutOp

    results = store.batch([
        PutOp(("users", "carol", "memories"), "m1", {"content": "likes tea"}),
        PutOp(("users", "carol", "memories"), "m2", {"content": "lives in Oslo"}),
        GetOp(("users", "carol", "memories"), "m1"),
    ])
    for r in results:
        print("  ", r)
    print()
    print("The op types (langgraph.store.base) are NamedTuples:")
    print("  PutOp(namespace, key, value, index, ttl)")
    print("  GetOp(namespace, key, refresh_ttl)")
    print("  SearchOp(namespace_prefix, filter, limit, offset, query, refresh_ttl)")
    print("  ListNamespacesOp(match_conditions, max_depth, limit, offset)")

    banner("6. Using the store FROM a graph node")
    print("Inside a node, call get_store() - no need to thread it through state.")

    class S(TypedDict, total=False):
        note: str

    def remember(state: S) -> dict:
        st = get_store()
        st.put(("users", "dave", "memories"), "m1",
               {"content": "asked about invoices"})
        found = st.search(("users", "dave"))
        return {"note": f"stored {len(found)} memory(ies)"}

    g = StateGraph(S)
    g.add_node("remember", remember)
    g.add_edge(START, "remember")
    g.add_edge("remember", END)

    graph = g.compile(checkpointer=InMemorySaver(), store=store)
    out = graph.invoke({"note": ""}, {"configurable": {"thread_id": "store-1"}})
    print("node said:", out["note"])
    print("store now has:", [i.value["content"] for i in store.search(("users", "dave"))])

    banner("7. THE POINT: memory survives across threads")
    print("Thread 'store-1' wrote a memory. A DIFFERENT thread can read it,")
    print("because the Store is not thread-scoped.")

    def recall(state: S) -> dict:
        st = get_store()
        found = st.search(("users", "dave"))
        return {"note": f"recalled {len(found)}: {found[0].value['content'] if found else '-'}"}

    g2 = StateGraph(S)
    g2.add_node("recall", recall)
    g2.add_edge(START, "recall")
    g2.add_edge("recall", END)
    graph2 = g2.compile(checkpointer=InMemorySaver(), store=store)
    out2 = graph2.invoke({"note": ""}, {"configurable": {"thread_id": "COMPLETELY-DIFFERENT"}})
    print("different thread said:", out2["note"])
    print()
    print("-> With a checkpointer only, that memory would be gone.")

    banner("8. What to store vs what to re-derive")
    print("  STORE (durable, user-specific):")
    print("    preferences  - 'prefers metric units', 'dark mode'")
    print("    facts         - 'works at Acme', 'email is x@y.com'")
    print("    procedures    - 'always check the CRM before answering'")
    print("  DO NOT STORE (re-derive it):")
    print("    the conversation transcript  -> that is the CHECKPOINT's job")
    print("    document content            -> that is your vector store's job")
    print("    anything the model can recompute from the current request")
    print("  Rule of thumb: if re-deriving costs one extra tool call, re-derive.")


if __name__ == "__main__":
    main()
