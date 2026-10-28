"""L21 / M60 - PostgresStore: long-term memory with SEMANTIC SEARCH.

Run:  python ex16_postgres_store.py

PostgresStore is the production sibling of InMemoryStore:

    * persists across restarts
    * survives a multi-process deployment (unlike InMemoryStore)
    * supports SEMANTIC search via pgvector (Postgres >= 15 + pgvector)
    * supports TTL on individual items

    from langgraph.store.postgres import PostgresStore
    from langgraph.store.postgres.base import PostgresIndexConfig

    index = PostgresIndexConfig(
        dims=768,
        embed=embeddings,        # a LangChain Embeddings object
        fields=["content"],      # which field of the value to embed
    )
    with PostgresStore.from_conn_string(url, index=index) as store:
        ...

Requirements verified in this example:
    * PostgreSQL 15+
    * the `vector` extension (pgvector) available to the database
    * `store.setup()` creates the schema (idempotent)
"""

from __future__ import annotations

from langgraph.store.postgres import PostgresStore
from langgraph.store.postgres.base import PostgresIndexConfig
from psycopg import Connection

from _common import PG_URL_TEST, banner, offline_embeddings


def main() -> None:
    banner("0. Requirements check")
    with Connection.connect(PG_URL_TEST) as conn:
        row = conn.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
        print("pgvector extension:", row[0] if row else "MISSING")
        if not row:
            print("Install pgvector first:")
            print("  apt-get install postgresql-15-pgvector")
            print("  CREATE EXTENSION vector;")
            return

    embed = offline_embeddings(dims=256)
    index = PostgresIndexConfig(
        dims=256,
        embed=embed,
        fields=["content"],   # embed the `content` field of the value
    )

    with PostgresStore.from_conn_string(PG_URL_TEST, index=index) as store:
        store.setup()

        banner("1. The tables PostgresStore creates")
        with Connection.connect(PG_URL_TEST) as conn:
            rows = conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' ORDER BY table_name"
            ).fetchall()
            for r in rows:
                print("  -", r[0])

        banner("2. Write some memories")
        memories = [
            ("users", "alice", "memories"),  # namespace
            "m1",
            {"content": "prefers dark mode in the dashboard", "kind": "preference"},
        ]
        store.put(("users", "alice", "memories"), "m1",
                  {"content": "prefers dark mode in the dashboard", "kind": "preference"})
        store.put(("users", "alice", "memories"), "m2",
                  {"content": "works at Acme Corp as a data engineer", "kind": "fact"})
        store.put(("users", "alice", "memories"), "m3",
                  {"content": "always reply in metric units", "kind": "preference"})
        store.put(("users", "bob", "memories"), "m1",
                  {"content": "prefers light mode", "kind": "preference"})

        for it in store.search(("users", "alice", "memories")):
            print(f"  {it.namespace} / {it.key}: {it.value['content']!r}")

        banner("3. Plain prefix search (no query)")
        for it in store.search(("users", "alice")):
            print(f"  {it.key}: {it.value['content']!r}")

        banner("4. SEMANTIC search - 'what units does alice like?'")
        results = store.search(("users", "alice", "memories"),
                                query="measurement units preference", limit=3)
        for it in results:
            score = getattr(it, "score", None)
            print(f"  score={score if score is None else round(score, 4)}  "
                  f"{it.key}: {it.value['content']!r}")
        print()
        print("-> search(query=...) embeds the query and compares it to the")
        print("   stored vectors with pgvector, then filters by namespace.")
        print("-> THAT is the difference from a plain key-value store.")

        banner("5. Semantic search respects the namespace prefix")
        print("search(('users','bob',...)) cannot see alice's memories:")
        for it in store.search(("users", "bob", "memories"), query="dark mode", limit=5):
            print(f"  {it.key}: {it.value['content']!r}")

        banner("6. Metadata filtering")
        store.put(("users", "alice", "memories"), "m4",
                  {"content": "prefers dark mode in the mobile app", "kind": "preference",
                   "source": "mobile"})
        res = store.search(("users", "alice", "memories"),
                            filter={"kind": "preference", "source": "mobile"})
        print("filter kind=preference AND source=mobile ->")
        for it in res:
            print(f"  {it.key}: {it.value['content']!r}")

        banner("7. The store survives a new connection")
        with PostgresStore.from_conn_string(PG_URL_TEST, index=index) as store2:
            store2.setup()
            n = len(store2.search(("users", "alice", "memories")))
            print(f"memories for alice after reopening: {n}")

        banner("8. Delete")
        store.delete(("users", "alice", "memories"), "m1")
        print("after delete:", [i.key for i in store.search(("users", "alice", "memories"))])

        banner("9. The real embedding model (production)")
        print("""
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    embed = GoogleGenerativeAIEmbeddings(
        model="gemini-embedding-001",          # current Gemini embedding model
        google_api_key=os.environ["GOOGLE_API_KEY"],
    )
    index = PostgresIndexConfig(dims=3072, embed=embed, fields=["content"])

Notes:
  * `dims` MUST match the model's output dimensionality.
    gemini-embedding-001 supports 128-3072; 768 / 1536 / 3072 are recommended.
  * If you change dims or the embedding model later, you must RE-INDEX:
    the stored vectors are meaningless to the new model.
        store.delete(...)  /  re-put every item
  * `fields=["content"]` means "embed the value's 'content' key".
    Use fields=["$"] to embed the whole value.
""")


if __name__ == "__main__":
    main()
