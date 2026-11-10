"""Shared offline harness for the Phase 10 (Multi-Agent Systems) examples.

Everything in this course runs WITHOUT network access and WITHOUT an API key.
We use a deterministic ``ScriptedChatModel`` that plays back pre-baked
``AIMessage`` objects.  This is the single most important trick for learning
agentic frameworks:

    If your example only works when a real LLM happens to pick the right tool,
    you cannot debug it, cannot unit-test it, and cannot read it.

A scripted model lets us assert *exactly* which tool the supervisor picked,
which agents ran, and what state each one saw.

Real-world swap
---------------
Replace ``scripted(...)`` with a real Gemini model:

    from langchain.chat_models import init_chat_model
    model = init_chat_model("google_genai:gemini-3.8-flash")

and add the key:

    export GOOGLE_API_KEY=...
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Sequence

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

# --------------------------------------------------------------------------
# A tiny tool-call recorder
# --------------------------------------------------------------------------


@dataclass
class ToolCallLog:
    """Records every tool invocation so tests can assert on behaviour."""

    calls: list[dict[str, Any]] = field(default_factory=list)

    def record(self, name: str, args: dict[str, Any], result: Any = None) -> None:
        self.calls.append({"name": name, "args": args, "result": result})

    def names(self) -> list[str]:
        return [c["name"] for c in self.calls]

    def count(self, name: str) -> int:
        return sum(1 for c in self.calls if c["name"] == name)

    def args_for(self, name: str) -> list[dict[str, Any]]:
        return [c["args"] for c in self.calls if c["name"] == name]


# --------------------------------------------------------------------------
# The scripted chat model
# --------------------------------------------------------------------------


class ScriptedChatModel(BaseChatModel):
    """A deterministic, offline stand-in for a real chat model.

    Two scripting styles are supported:

    1. **Static list** — a queue of ``AIMessage`` objects is returned in order.
    2. **Router function** — a callable receives the current message list and
       returns the next ``AIMessage``.  This is what lets us model "the model
       decides which specialist to call" without a real model.

    The model also records every invocation, so a lesson can assert *what the
    model saw* — which is the fastest way to understand context plumbing.
    """

    model_name: str = "scripted"
    profile: dict[str, Any] | None = None
    """Token profile, e.g. {"max_input_tokens": 1_048_576}.  Required by
    middleware that use fractional token triggers (SummarizationMiddleware)."""

    responses: list[AIMessage] = []
    router: Callable[[list[BaseMessage]], AIMessage | None] | None = None
    log: ToolCallLog = field(default_factory=ToolCallLog)
    seen_messages: list[list[BaseMessage]] = field(default_factory=list)
    _cursor: int = 0

    # ---- BaseChatModel plumbing -----------------------------------------

    @property
    def _llm_type(self) -> str:
        return "scripted-chat-model"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.seen_messages.append(list(messages))

        msg: AIMessage | None = None
        if self.router is not None:
            # A router may return None to mean "fall through to the static
            # response queue" (useful for scripted multi-turn flows).
            msg = self.router(list(messages))

        if msg is None:
            if self._cursor < len(self.responses):
                msg = self.responses[self._cursor]
                self._cursor += 1
            else:  # pragma: no cover - defensive
                msg = AIMessage(content="<scripted model exhausted>")

        return ChatResult(
            generations=[ChatGeneration(message=msg)],
            llm_output={"model_name": self.model_name},
        )

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "ScriptedChatModel":
        # The real implementation converts tools to an OpenAI-style schema.
        # We only need the *names* so a router can assert "the model was
        # offered exactly these tools".
        names = []
        for t in tools:
            if hasattr(t, "name"):
                names.append(t.name)
            elif isinstance(t, dict):
                names.append(t.get("name") or t.get("function", {}).get("name"))
            else:  # pragma: no cover
                names.append(str(t))
        object.__setattr__(self, "_tool_names", names)
        return self

    # ---- helpers --------------------------------------------------------

    @property
    def tool_names(self) -> list[str]:
        return getattr(self, "_tool_names", [])

    @property
    def n_calls(self) -> int:
        """How many times this model was actually invoked."""
        return len(self.seen_messages)

    def last_seen(self) -> list[BaseMessage]:
        return self.seen_messages[-1] if self.seen_messages else []


def once_per_turn(
    tool_name: str,
    args: dict[str, Any],
    final: str = "Done.",
    call_id: str = "call_1",
) -> Callable[[list[BaseMessage]], AIMessage]:
    """Like :func:`once_then_final`, but per TURN rather than per agent.

    ``once_then_final`` refuses to call the tool again if it EVER saw a
    ToolMessage with that name.  In a SWARM the same peer runs several times
    in one conversation, so that check stops the swarm after one round.

    This variant only looks at the LAST message: if the model just saw the
    tool's result, it answers; otherwise it calls the tool again.
    """

    def _route(messages: list[BaseMessage]) -> AIMessage:
        last = messages[-1] if messages else None
        if isinstance(last, ToolMessage) and last.name == tool_name:
            return AIMessage(content=final)
        return AIMessage(
            content="",
            tool_calls=[
                {"name": tool_name, "args": args, "id": call_id, "type": "tool_call"}
            ],
        )

    return _route


def scripted(
    responses: Sequence[AIMessage] | None = None,
    router: Callable[[list[BaseMessage]], AIMessage | None] | None = None,
    name: str = "scripted",
    profile: dict[str, Any] | None = None,
) -> ScriptedChatModel:
    """Convenience constructor for :class:`ScriptedChatModel`."""
    return ScriptedChatModel(
        model_name=name,
        responses=list(responses or []),
        router=router,
        profile=profile,
    )


make_scripted = scripted  # alias used by some examples


def once_then_final(
    tool_name: str,
    args: dict[str, Any],
    final: str = "Done.",
    call_id: str = "call_1",
) -> Callable[[list[BaseMessage]], AIMessage]:
    """A router that calls a tool exactly once, then produces a final answer.

    This is the workhorse of the course.  Without it, a scripted router that
    *always* requests the same tool makes the agent loop forever — a real
    "infinite ReAct loop" that you will meet in production.
    """

    def _route(messages: list[BaseMessage]) -> AIMessage:
        already_ran = any(
            isinstance(m, ToolMessage) and m.name == tool_name for m in messages
        )
        if already_ran:
            return AIMessage(content=final)
        return AIMessage(
            content="",
            tool_calls=[
                {"name": tool_name, "args": args, "id": call_id, "type": "tool_call"}
            ],
        )

    return _route


# --------------------------------------------------------------------------
# Message builders — keep the examples readable
# --------------------------------------------------------------------------


def ai(content: str = "", **kwargs: Any) -> AIMessage:
    """Build an ``AIMessage`` with optional ``tool_calls``."""
    return AIMessage(content=content, **kwargs)


def tool_call(name: str, args: dict[str, Any], call_id: str = "call_1") -> AIMessage:
    """Build an ``AIMessage`` that requests one tool call."""
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
    )


def tool_result(content: str, call_id: str = "call_1", name: str = "tool") -> ToolMessage:
    """Build a ``ToolMessage`` (the tool's reply to the model)."""
    return ToolMessage(content=content, tool_call_id=call_id, name=name)


def user(content: str) -> HumanMessage:
    return HumanMessage(content=content)


def dump(obj: Any) -> str:
    """Pretty, deterministic JSON for teaching output."""
    return json.dumps(obj, indent=2, default=str, sort_keys=False)


def text_of(msg: BaseMessage) -> str:
    """Extract plain text from a message (handles list-style content)."""
    c = msg.content
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts = []
        for block in c:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
        return "".join(parts)
    return str(c)


def as_text(msg: BaseMessage) -> str:
    """Alias kept for readability in lesson snippets."""
    return text_of(msg)


def iter_tool_calls(msg: BaseMessage) -> Iterator[tuple[str, dict[str, Any], str]]:
    """Yield ``(name, args, id)`` for each tool call on a message."""
    for tc in getattr(msg, "tool_calls", None) or []:
        yield tc["name"], tc.get("args", {}) or {}, tc.get("id", "")
