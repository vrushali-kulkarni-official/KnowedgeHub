"""L22 / M61 - Multi-tenant memory: isolation done properly.

Run:  python ex18_tenant_isolation.py

The moment you have more than one customer, EVERY piece of persistent state
must be scoped. There are only two ways to scope things:

    thread_id   -> scopes the CHECKPOINT (a conversation)
    namespace   -> scopes the STORE (long-term memory)

A thread id that contains a user id is NOT isolation - it is a convention.
Namespace isolation is structural, because the store's search() takes a
namespace PREFIX and can never cross it.

This example:
  * writes memories for two tenants
  * proves tenant A cannot read tenant B
  * shows the ONE mistake that breaks isolation: putting the tenant id in
    the wrong position of the namespace
  * shows how to make the tenant id a template so it cannot be forgotten
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.config import get_store
from langgraph.graph import END, START, StateGraph
from langgraph.store.postgres import PostgresStore
from langgraph.store.postgres.base import PostgresIndexConfig

from _common import PG_URL_TEST, banner, offline_embeddings


class LogState(TypedDict, total=False):
    log: Annotated[list[str], operator.add]


def main() -> None:
    embed = offline_embeddings(dims=256)
    index = PostgresIndexConfig(dims=256, embed=embed, fields=["content"])

    with PostgresStore.from_conn_string(PG_URL_TEST, index=index) as store:
        store.setup()

        banner("1. Write memories for TWO tenants")
        store.put(("tenant", "acme", "users", "alice", "memories"), "m1",
                  {"kind": "preference", "content": "prefers metric units"})
        store.put(("tenant", "acme", "users", "alice", "memories"), "m2",
                  {"kind": "fact", "content": "email alice@acme.com"})
        store.put(("tenant", "acme", "users", "bob", "memories"), "m1",
                  {"kind": "preference", "content": "prefers light mode"})
        store.put(("tenant", "globex", "users", "alice", "memories"), "m1",
                  {"kind": "fact", "content": "email alice@globex.com"})

        print("tenant acme:")
        for it in store.search(("tenant", "acme")):
            print(f"  {it.namespace} / {it.key} = {it.value['content']!r}")
        print("tenant globex:")
        for it in store.search(("tenant", "globex")):
            print(f"  {it.namespace} / {it.key} = {it.value['content']!r}")

        banner("2. ISOLATION: a scoped search cannot cross the tenant")
        acme_alice = [i.value["content"] for i in store.search(("tenant", "acme", "users", "alice"))]
        globex_alice = [i.value["content"] for i in store.search(("tenant", "globex", "users", "alice"))]
        print("acme/alice   :", acme_alice)
        print("globex/alice :", globex_alice)
        assert "email alice@globex.com" not in acme_alice
        assert "email alice@acme.com" not in globex_alice
        print("-> acme/alice CANNOT see globex/alice's memories. Verified.")

        banner("3. The namespace ORDER matters")
        print("('tenant', 'acme', 'users', 'alice')  -> acme + alice")
        print("('tenant', 'users', 'alice', 'acme')  -> different meaning!")
        print()
        print("A search is a PREFIX match, so the position of the tenant id")
        print("defines the scope. Put the tenant id EARLY so that:")
        print("  store.search((tenant_id, ...))  -> only that tenant")
        print("and always start your search from the tenant level.")

        banner("4. THE MISTAKE: tenant id in the middle")
        # A common bug: the user id comes first.
        store.put(("users", "alice", "acme", "memories"), "m1",
                  {"kind": "fact", "content": "alice at acme - shared namespace bug"})
        leaked = [i.value["content"] for i in store.search(("tenant", "acme"))]
        print("search(('tenant','acme')) now also returns:")
        for c in leaked:
            print("   ", c)
        print()
        print("-> The row was written OUTSIDE the tenant's namespace, so a")
        print("   tenant-scoped search picks it up. That is a data leak.")
        print("-> The fix is a NAMESPACING HELPER that nobody can bypass:")
        print()
        print("    def ns(tenant_id: str, user_id: str, *rest: str):")
        print("        return ('tenant', tenant_id, 'users', user_id, *rest)")
        print()
        print("   Never build a namespace with an f-string at the call site.")

        banner("5. The template approach: the tenant id comes from config")
        print("langmem's NamespaceTemplate resolves {var} from")
        print("config['configurable'][var] - so the scope cannot be forgotten:")
        print()
        print("    manager = create_memory_store_manager(")
        print("        model, namespace=('tenant', '{tenant_id}', 'users',")
        print("                           '{langgraph_user_id}')")
        print()
        print("    config = {'configurable': {")
        print("        'tenant_id': tenant_id,")
        print("        'langgraph_user_id': user_id,")
        print("        'thread_id': thread_id,")
        print("    }}")
        print()
        print("The same trick works for the CHECKPOINT: make the thread id")
        print("a composite string built in ONE place.")
        print()
        print("    def thread_id(tenant_id: str, conversation_id: str) -> str:")
        print("        return f'{tenant_id}:{conversation_id}'")
        print("    # -> 'acme:conv-42'")

        banner("6. Same rule for CHECKPOINTS")
        with PostgresSaver.from_conn_string(PG_URL_TEST) as saver:
            saver.setup()
            g = StateGraph(LogState)
            g.add_node("n", lambda s: {"log": ["x"]})
            g.add_edge(START, "n")
            g.add_edge("n", END)
            graph = g.compile(checkpointer=saver, store=store)

            for tenant in ("acme", "globex"):
                tid = f"{tenant}:conv-1"
                graph.invoke({"log": []}, {"configurable": {"thread_id": tid}})
            acme_state = graph.get_state({"configurable": {"thread_id": "acme:conv-1"}})
            globex_state = graph.get_state({"configurable": {"thread_id": "globex:conv-1"}})
            print("acme:conv-1   ->", acme_state.values)
            print("globex:conv-1 ->", globex_state.values)
            print("-> different threads, different state. The composite thread")
            print("   id makes the tenant boundary visible in the DB.")

        banner("7. Defense in depth: verify isolation in a test")
        print("Write a test that asserts the isolation, so a refactor that")
        print("breaks it fails CI:")
        print()
        print("    def test_tenant_isolation(store):")
        print("        store.put(('tenant','a','users','u1','memories'), 'k',")
        print("                  {'content': 'A SECRET'})")
        print("        seen = [i.value for i in store.search(('tenant','b'))]")
        print("        assert seen == []")
        print()
        print("Do this for every scope in your system. It is cheap.")


if __name__ == "__main__":
    main()
