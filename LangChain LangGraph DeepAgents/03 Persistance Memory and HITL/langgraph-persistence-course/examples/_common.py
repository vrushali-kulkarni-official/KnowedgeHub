"""Shared helpers for the Phase 8 course examples.

Nothing here is course content — it is the tiny amount of scaffolding that lets
every example run offline (no LLM API key) and against a real PostgreSQL.

Swap `_common.py` for your own config module in production.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Sequence

# Load .env if there is one (optional - the examples work without it).
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

# --------------------------------------------------------------------------
# Database connection
# --------------------------------------------------------------------------
# Every Postgres example reads this. Override with an env var so you can point
# at your own database without editing code.
PG_URL = os.getenv(
    "LANGGRAPH_PG_URL",
    "postgresql://langgraph:langgraph@127.0.0.1:5432/langgraph",
)
PG_URL_TEST = os.getenv(
    "LANGGRAPH_PG_URL_TEST",
    "postgresql://langgraph:langgraph@127.0.0.1:5432/langgraph_test",
)

REDIS_URL = os.getenv("LANGGRAPH_REDIS_URL", "redis://localhost:6379/0")


# --------------------------------------------------------------------------
# A deterministic chat model
# --------------------------------------------------------------------------
# Why not call a real LLM?
#
#   * Every lesson here is about *persistence*, not about model quality.
#   * A real model makes examples non-deterministic and slow.
#   * You should be able to run the whole course with zero API keys.
#
# `ScriptedChatModel` returns pre-baked responses in order, and records every
# call so you can assert on what the agent saw.
#
# In your own project, replace it with:
#
#     from langchain.chat_models import init_chat_model
#     model = init_chat_model("google_genai:gemini-2.5-flash")
#
# Everything else in this course is unchanged.


@dataclass
class _Call:
    """One recorded call to the model."""

    messages: list[BaseMessage]
    tools: list[Any] | None


class ScriptedChatModel(BaseChatModel):
    """A chat model that replays a fixed script of responses.

    Attributes:
        responses: Responses returned in order, one per call.
        repeat_last: When the script runs out, repeat the final response
            instead of raising. Handy for middleware that calls the model a
            variable number of times.
        calls: Recorded calls (populated at runtime).
    """

    responses: list[AIMessage] = field(default_factory=list)
    repeat_last: bool = True
    calls: list[_Call] = field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"scripted": len(self.responses)}

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "ScriptedChatModel":
        """Agents call `bind_tools`; a scripted model ignores the tools but
        must not blow up."""
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.calls.append(_Call(messages=list(messages), tools=kwargs.get("tools")))
        idx = len(self.calls) - 1
        if idx < len(self.responses):
            msg = self.responses[idx]
        elif self.responses and self.repeat_last:
            msg = self.responses[-1]
        else:
            msg = AIMessage(content="<script exhausted>")
        return ChatResult(generations=[ChatGeneration(message=msg)])


def scripted_model(*contents: str, repeat_last: bool = True) -> ScriptedChatModel:
    """Build a model that replies with the given strings, in order."""
    return ScriptedChatModel(
        responses=[AIMessage(content=c) for c in contents],
        repeat_last=repeat_last,
    )


def tool_call_model(*tool_calls: tuple[str, dict]) -> ScriptedChatModel:
    """Build a model that emits tool calls, in order.

    Each item is `(tool_name, args)`.
    """
    responses = [
        AIMessage(
            content="",
            tool_calls=[{"name": name, "args": args, "id": f"call_{i}_{name}"}],
        )
        for i, (name, args) in enumerate(tool_calls)
    ]
    return ScriptedChatModel(responses=responses)


def banner(title: str) -> None:
    """Pretty section header so example output is readable."""
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def show(label: str, value: Any) -> None:
    print(f"{label}: {value}")


# --------------------------------------------------------------------------
# A tiny offline embedding model
# --------------------------------------------------------------------------
# PostgresStore's semantic search needs an `Embeddings` object. In production
# you would use a real model, e.g.
#
#     from langchain_google_genai import GoogleGenerativeAIEmbeddings
#     embed = GoogleGenerativeAIEmbeddings(
#         model="gemini-embedding-001", google_api_key=os.environ["GOOGLE_API_KEY"]
#     )
#
# For the course we use a bag-of-words hashing embedder: same words -> similar
# vectors. It is NOT a real semantic model, but it exercises the exact same
# code path (embedding -> pgvector -> cosine similarity) so you can see the
# plumbing work without an API key.
from langchain_core.embeddings import Embeddings  # noqa: E402


class TokenHashEmbeddings(Embeddings):
    """Deterministic bag-of-words hashing embedder (offline stand-in).

    `langchain_core.embeddings.Embeddings` is a plain ABC (not a pydantic
    model), so this is a normal class with an explicit __init__.
    """

    def __init__(self, dims: int = 256):
        self.dims = dims

    def _vec(self, text: str) -> list[float]:
        import hashlib
        import math

        vec = [0.0] * self.dims
        for token in text.lower().split():
            token = token.strip(".,!?;:'\"()[]{}").strip()
            if not token:
                continue
            h = hashlib.blake2b(token.encode(), digest_size=8).digest()
            idx = int.from_bytes(h[:4], "big") % self.dims
            sign = 1.0 if h[4] % 2 == 0 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


def offline_embeddings(dims: int = 256) -> TokenHashEmbeddings:
    return TokenHashEmbeddings(dims=dims)
