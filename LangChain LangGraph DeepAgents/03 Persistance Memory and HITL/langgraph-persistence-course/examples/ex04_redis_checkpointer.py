"""L15 / M54 - The community Redis checkpointer.

Run:  python ex04_redis_checkpointer.py     (needs Redis Stack on :6379)

`langgraph-checkpoint-redis` is COMMUNITY-MAINTAINED (langchain-ai org,
MIT license) - it is NOT one of the officially supported LangChain backends.
It is excellent for low-latency, high-throughput, short-lived threads, and it
supports native TTL, which PostgresSaver does not.

!! IMPORTANT REQUIREMENT (verified on 0.5.2) !!
   RedisSaver uses RedisVL for its indexes, which means your Redis server must
   have the **RedisJSON** and **RediSearch** modules -> use Redis Stack
   (https://redis.io/docs/latest/operate/oss_and_stack/stack-with-/), NOT the
   plain `redis-server` package. Plain Redis fails with:

       redisvl.exceptions.RedisVLError: Failed to load data:
       ... unknown command 'JSON.SET' ...

   This example detects that and explains the fix instead of crashing.

Trade-off summary:

    PostgresSaver  -> durable, queryable with SQL, easy to JOIN with your own
                      tables, easy to back up, easy to audit, no extra modules.
    RedisSaver     -> microsecond reads, built-in TTL, but it needs Redis Stack
                      and you must treat it as a cache that can evict.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.checkpoint.redis import RedisSaver
from langgraph.graph import END, START, StateGraph
from redis import Redis

from _common import REDIS_URL, banner


class State(TypedDict, total=False):
    messages: list[str]


def build_graph():
    def node(state: State) -> dict:
        return {"messages": state.get("messages", []) + ["ping"]}

    g = StateGraph(State)
    g.add_node("node", node)
    g.add_edge(START, "node")
    g.add_edge("node", END)
    return g


def has_redisjson() -> bool:
    try:
        r = Redis.from_url(REDIS_URL, decode_responses=True)
        mods = r.execute_command("MODULE", "LIST")
        return any(m[1].lower() in ("rejson", "redisjson") for m in mods)
    except Exception:
        return False


def main() -> None:
    banner("1. Is this Redis actually Redis Stack?")
    print("RedisJSON module present:", has_redisjson())
    print()
    print("RedisSaver (langgraph-checkpoint-redis) uses RedisVL, which requires")
    print("the RedisJSON + RediSearch modules. If the answer above is False you")
    print("get:  unknown command 'JSON.SET'")
    print("Fix: run Redis Stack, e.g.")
    print("  docker run -d -p 6379:6379 redis/redis-stack-server:latest")
    print()

    if not has_redisjson():
        banner("2. Skipping the live write path (Redis Stack not available)")
        print("Everything below is the API you would use; the write path needs")
        print("Redis Stack. The SIGNATURES below are real and introspected:")
        print()
        print("  RedisSaver.from_conn_string(redis_url=None, *, redis_client=None,")
        print("      connection_args=None, ttl=None, checkpoint_prefix='checkpoint',")
        print("      checkpoint_write_prefix='checkpoint_write')")
        print()
        print("  -> note the `ttl` parameter: Redis checkpoints can expire on")
        print("     their own. PostgresSaver has no TTL; you sweep it yourself.")
        print()
        print("  -> RedisSaver also exposes: setup(), delete_thread(thread_id),")
        print("     prune(thread_ids, strategy=...), copy_thread(), delete_for_runs()")
        print()
        print("See the lesson for the full Postgres-vs-Redis decision table.")
        return

    banner("2. Use it exactly like any other checkpointer")
    builder = build_graph()
    with RedisSaver.from_conn_string(REDIS_URL) as saver:
        saver.setup()
        graph = builder.compile(checkpointer=saver)
        cfg = {"configurable": {"thread_id": "redis-thread-1"}}

        graph.invoke({"messages": []}, cfg)
        graph.invoke({"messages": ["second turn"]}, cfg)
        print("state:", graph.get_state(cfg).values)

        banner("3. The state survived a new saver instance")
        with RedisSaver.from_conn_string(REDIS_URL) as saver2:
            g2 = builder.compile(checkpointer=saver2)
            print("state via saver2:", g2.get_state(cfg).values)

        banner("4. Native TTL - Redis expires the checkpoint for you")
        with RedisSaver.from_conn_string(REDIS_URL, ttl={"default_ttl": 60}) as saver3:
            g3 = builder.compile(checkpointer=saver3)
            cfg_ttl = {"configurable": {"thread_id": "redis-ttl-thread"}}
            g3.invoke({"messages": ["ephemeral"]}, cfg_ttl)
            print("ephemeral thread state:", g3.get_state(cfg_ttl).values)
            print("-> after `default_ttl` seconds Redis drops the key on its own.")

        banner("5. Cleanup")
        saver.delete_thread("redis-thread-1")
        print("deleted redis-thread-1")
        print("remaining state:", graph.get_state(cfg).values)


if __name__ == "__main__":
    main()
