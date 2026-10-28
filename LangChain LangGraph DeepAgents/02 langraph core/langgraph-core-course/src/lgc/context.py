"""
Runtime context for the course.

WHY THIS FILE EXISTS
--------------------
Before LangGraph 0.6, the idiomatic way to hand a `user_id` (or an API key, or
a DB handle) to your nodes was to stuff it into `config["configurable"]`:

    config = {"configurable": {"thread_id": "1", "user_id": "u-42"}}

That works, but it mixes two very different things in one namespace:

    1. Framework-level settings   -> `thread_id`, `recursion_limit`
    2. Your app's own values      -> `user_id`, `tenant_id`, `api_key`

`config_schema` tried to fix this and was **deprecated** in 0.6 (removal in
2.0). The modern answer is `context_schema` + `context=` + `Runtime`.

    graph.invoke(input, config={"configurable": {"thread_id": "1"}},
                        context={"user_id": "u-42"})

Context is:
    * read-only  - a node can read `runtime.context` but never write to it
    * run-scoped - it is fixed for the duration of one invocation
    * NOT persisted - it is never written into a checkpoint
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AppContext:
    """Run-scoped, read-only dependencies handed to every node.

    In a real app this is where you would put:
        * `user_id` / `tenant_id` (who is asking)
        * an already-constructed LLM or client (so nodes don't re-create them)
        * feature flags / routing preferences
        * a DB connection

    Note it is a plain dataclass, NOT pydantic. `context_schema` accepts a
    dataclass, a TypedDict or a Pydantic model - all three work.
    """

    user_id: str = "anonymous"
    tenant: str = "default"
    # A ready-to-use model can be passed in, so nodes never rebuild it.
    model: Any = None
    # Free-form bag for anything else.
    extras: dict[str, Any] = field(default_factory=dict)

    def with_model(self, model: Any) -> "AppContext":
        """Return a copy of this context with `model` attached."""
        return AppContext(
            user_id=self.user_id,
            tenant=self.tenant,
            model=model,
            extras=dict(self.extras),
        )
