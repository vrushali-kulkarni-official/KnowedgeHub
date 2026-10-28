"""L22 / M61 - Data lifecycle: TTL cleanup and "delete this user".

Run:  python ex19_data_lifecycle.py

Persistent state is a liability. This example covers the three jobs you need:

  1. TTL on STORE items        - PostgresStore supports per-item TTL and a
                                 built-in TTL sweeper.
  2. TTL on CHECKPOINT threads - PostgresSaver has NO TTL. You sweep it.
  3. GDPR / "right to be forgotten" - delete EVERYTHING for one user:
        - checkpoint threads
        - long-term memories
        - vector rows (your own RAG store)
        - traces in Langfuse

Everything runs against a real PostgreSQL.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.store.base import TTLConfig
from langgraph.store.postgres import PostgresStore
from langgraph.store.postgres.base import PostgresIndexConfig
from psycopg import Connection

from _common import PG_URL_TEST, banner, offline_embeddings

USER = "user-to-delete"


def now() -> datetime:
    return datetime.now(timezone.utc)


def main() -> None:
    embed = offline_embeddings(dims=256)
    index = PostgresIndexConfig(dims=256, embed=embed, fields=["content"])

    # ======================================================================
    banner("1. TTL on STORE items (built into PostgresStore)")
    # NOTE the two flags - they change the semantics completely:
    #   refresh_on_read=False -> ABSOLUTE expiry (reading does not extend)
    #   omit_expired=True     -> expired items are HIDDEN even before a sweep
    ttl_config = TTLConfig(
        default_ttl=60.0,
        sweep_interval_minutes=1,
        refresh_on_read=False,
        omit_expired=True,
    )
    with PostgresStore.from_conn_string(PG_URL_TEST, index=index, ttl=ttl_config) as store:
        store.setup()

        store.put(("users", USER, "memories"), "ephemeral",
                  {"kind": "fact", "content": "this expires in 60 minutes"})
        store.put(("users", USER, "memories"), "permanent",
                  {"kind": "fact", "content": "this has no TTL"})
        print("after put:", [i.key for i in store.search(("users", USER, "memories"))])

        banner("1b. IMPORTANT UNIT: the store TTL is in MINUTES")
        with Connection.connect(PG_URL_TEST) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT key, ttl_minutes, expires_at FROM store "
                    "WHERE prefix LIKE %s ORDER BY key",
                    (f"%users%{USER}%",),
                )
                for r in cur.fetchall():
                    print(f"   key={r[0]:<12} ttl_minutes={r[1]} expires_at={r[2]}")
        print()
        print("-> `ttl=60` means 60 MINUTES, not 60 seconds.")
        print("   The column is literally named `ttl_minutes`.")
        print("   (And it is an INT column, so sub-minute TTLs round to 0.)")

        banner("1b-bis. THE TWO FLAGS THAT CHANGE EVERYTHING")
        print("By DEFAULT (refresh_on_read=True, omit_expired=False):")
        print("  * READING an item RESETS its expiry  -> SLIDING expiration")
        print("  * EXPIRED items are still returned by search() until a sweep")
        print()
        print("For 'this memory is invalid after 24h' semantics you want:")
        print("    TTLConfig(default_ttl=1440, refresh_on_read=False,")
        print("               omit_expired=True)")
        print()
        print("For 'this memory lives as long as it keeps being used':")
        print("    TTLConfig(default_ttl=1440)   # the default, sliding")
        print()

        banner("1c. sweep_ttl() removes expired items")
        print("simulating the passage of time by rewinding expires_at...")
        with Connection.connect(PG_URL_TEST, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE store SET expires_at = NOW() - INTERVAL '1 hour' "
                    "WHERE prefix LIKE %s AND ttl_minutes IS NOT NULL",
                    (f"%users%{USER}%",),
                )
                print("   rows rewound:", cur.rowcount)
        print("before sweep:", [i.key for i in store.search(("users", USER, "memories"))])
        swept = store.sweep_ttl()
        print("sweep_ttl() removed:", swept)
        print("after sweep :", [i.key for i in store.search(("users", USER, "memories"))])
        print()
        print("-> PostgresStore supports per-item TTL AND a background sweeper:")
        print("     store.start_ttl_sweeper()   # run it in a background thread")
        print("     store.stop_ttl_sweeper()")
        print("   The sweeper deletes rows where expires_at < NOW().")

        banner("2. Per-item TTL override")
        store.put(("users", USER, "memories"), "custom-ttl",
                  {"kind": "fact", "content": "expires in 10 minutes"}, ttl=10)
        store.put(("users", USER, "memories"), "no-ttl",
                  {"kind": "fact", "content": "never expires"})
        print("stored:", [i.key for i in store.search(("users", USER, "memories"))])
        print("-> put(..., ttl=MINUTES) overrides the default per item.")
        print("-> pass ttl=None explicitly for 'never expires'.")

    # ======================================================================
    banner("3. CHECKPOINT threads have NO TTL - you sweep them")
    with PostgresSaver.from_conn_string(PG_URL_TEST) as saver:
        saver.setup()

        # Simulate 3 threads, one of them old.
        for i in range(3):
            tid = f"{USER}-thread-{i}"
            saver.put(
                {"configurable": {"thread_id": tid, "checkpoint_ns": ""}},
                {"v": 4, "id": f"cp-{i}", "ts": now().isoformat(), "channel_values": {},
                 "channel_versions": {}, "versions_seen": {}},
                {"source": "input", "step": -1, "parents": {}},
                {},
            )
        print("threads:", [t for t in ("a", "b", "c")])

        banner("4. A retention job: delete threads older than N days")
        print("""
    def purge_old_threads(saver, conn, days: int) -> int:
        cutoff = now() - timedelta(days=days)
        with conn.cursor() as cur:
            cur.execute(
                \"\"\"
                SELECT DISTINCT thread_id FROM checkpoints
                WHERE checkpoint->>'ts' < %s
                \"\"\", (cutoff,))
            stale = [r[0] for r in cur.fetchall()]
        for tid in stale:
            saver.delete_thread(tid)
        return len(stale)

  Run it from cron / Celery beat / a K8s CronJob.
""")
        # Do it for real, using the oldest-checkpoint timestamp per thread.
        with Connection.connect(PG_URL_TEST) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT thread_id, min(checkpoint->>'ts') FROM checkpoints "
                    "GROUP BY thread_id ORDER BY 2"
                )
                for row in cur.fetchall():
                    print(f"  thread={row[0]} oldest={row[1]}")

        banner("5. THE GDPR DELETE: 'delete this user completely'")
        print("A user is not one table. A user is:")
        print("   1. checkpoint threads   (their conversations)")
        print("   2. long-term memories  (the store)")
        print("   3. vector rows         (your RAG collection)")
        print("   4. traces              (Langfuse)")
        print("   5. your own app tables (users, billing, ...)")
        print()
        print("Here is a runnable implementation of 1 and 2 (and the shape")
        print("of 3, 4 and 5):")

        # ---- 1. threads -------------------------------------------------
        with Connection.connect(PG_URL_TEST) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT DISTINCT thread_id FROM checkpoints WHERE thread_id LIKE %s",
                    (f"{USER}%",),
                )
                threads = [r[0] for r in cur.fetchall()]
        print(f"\n  1. threads found for {USER}: {threads}")
        for tid in threads:
            saver.delete_thread(tid)
        print("     -> deleted")

        # ---- 2. memories ------------------------------------------------
        with PostgresStore.from_conn_string(PG_URL_TEST, index=index) as store:
            items = list(store.search(("users", USER)))
            for it in items:
                store.delete(it.namespace, it.key)
            print(f"  2. memories found: {len(items)} -> deleted")

            # ---- 3. vector rows -----------------------------------------
            print("""
  3. vector rows (your RAG collection) - delete by metadata:
     with PGVector.from_config(...) as vstore:
         vstore.delete(
             ids=vstore.get(ids={"user_id": USER})["ids"]
         )
     # or, if your vectors are in the LangGraph store, they were already
     # removed in step 2 (search + delete covers every namespace under
     # ('users', USER)).
""")

            # ---- 4. Langfuse traces ------------------------------------
            print("""
  4. Langfuse traces - verified against langfuse 5.0.4:

     from langfuse import Langfuse

     client = Langfuse(public_key=..., secret_key=..., base_url=...)

     # 4a. find the trace ids that belong to this user.
     #     Langfuse v5 has NO api.trace.list(); you find observations
     #     (which carry their trace_id) and filter there:
     obs = client.api.observations.get_many(user_id=USER, limit=100)
     trace_ids = {o.trace_id for o in obs.data if o.trace_id}

     # 4b. delete them. This cascades to their observations, scores
     #     and events.
     client.api.trace.delete_multiple(trace_ids=list(trace_ids))
     client.flush()

     # single trace:
     client.api.trace.delete(trace_id="...")

  Tip: tag every Langfuse trace with the user id so this lookup is
  exact (see the session_id / user_id fields on the trace).
""")

            # ---- 5. your own tables ------------------------------------
            print("""
  5. your own tables:
     DELETE FROM app_users WHERE id = %s;
     DELETE FROM app_sessions WHERE user_id = %s;
     -- keep an anonymised tombstone if your audit rules require it:
     INSERT INTO deleted_users (id, deleted_at) VALUES (%s, now());
""")

        banner("6. The shape of a complete delete_user() service")
        print("""
    def delete_user(user_id: str) -> dict:
        counts = {}

        # 1. threads
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT thread_id FROM checkpoints
                         WHERE thread_id LIKE %s", (f"{user_id}%",))
            threads = [r[0] for r in cur.fetchall()]
        for t in threads:
            saver.delete_thread(t)
        counts["threads"] = len(threads)

        # 2. memories (every namespace under the user's prefix)
        with PostgresStore.from_conn_string(url, index=index) as store:
            for ns in store.list_namespaces(prefix=("users", user_id)):
                for item in store.search(ns):
                    store.delete(item.namespace, item.key)
            counts["memories"] = ...

        # 3. vector rows
        counts["vectors"] = vstore.delete_by_user(user_id)

        # 4. traces
        counts["traces"] = delete_langfuse_traces(user_id)

        # 5. your tables
        counts["app_rows"] = delete_app_rows(conn, user_id)

        return counts      # <- log this. It is your proof of deletion.
""")
        print("Return a COUNT of what was deleted and log it. When the user")
        print("asks 'did you delete everything?', you can answer with data.")


if __name__ == "__main__":
    main()
