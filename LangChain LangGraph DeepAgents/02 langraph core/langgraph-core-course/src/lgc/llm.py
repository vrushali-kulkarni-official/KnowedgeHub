"""
The model layer for the course.

Design rule for this whole course:

    * In REAL use  -> Gemini via `langchain-google-genai` (ChatGoogleGenerativeAI).
    * In the sandbox / no API key -> a deterministic OFFLINE model.

Why the offline fallback exists: every example in this course must be
runnable and verifiable without burning API credits or needing network access.
The offline model implements the *same* `BaseChatModel` interface, so a node
written in the lesson works unchanged against Gemini.

The moment you set `GOOGLE_API_KEY` in `.env`, `get_llm()` returns the real
Gemini model and every example in `examples/` starts using it. No code changes.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterator, Sequence

from dotenv import load_dotenv

# Load .env from the course root (works no matter where you run from).
_COURSE_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_COURSE_ROOT / ".env")

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda

# --------------------------------------------------------------------------
# Model names (verified against Google's model catalogue, Oct 2026)
# --------------------------------------------------------------------------
# CURRENT STABLE:
#   gemini-3.8-flash   -> GA 2026-10-08. The default recommendation: fast,
#                         cheap, strong at long-horizon + agentic work.
#   gemini-3.6-flash   -> stable, previous generation.
#   gemini-3.5-flash-lite / gemini-3.1-flash-lite -> cheapest tiers.
#   gemini-3.1-pro-preview -> the Pro tier (still "preview" in the API).
# DEPRECATED (do not use in new code):
#   gemini-3.7-flash  -> deprecated 2026-10-08, auto-routed to gemini-3.8-flash
#   gemini-3.5-flash  -> deprecated, auto-routed to gemini-3.6-flash
#   gemini-3-pro-preview -> shut down, use gemini-3.1-pro-preview
DEFAULT_MODEL = "gemini-3.8-flash"
PRO_MODEL = "gemini-3.1-pro-preview"
FLASH_LITE_MODEL = "gemini-3.5-flash-lite"


def _has_gemini_key() -> bool:
    return bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))


def using_real_llm() -> bool:
    """True when we are talking to the actual Gemini API."""
    return _has_gemini_key()


# --------------------------------------------------------------------------
# The offline model
# --------------------------------------------------------------------------
class OfflineChatModel(BaseChatModel):
    """A deterministic, dependency-free stand-in for a real chat model.

    It exists so that every graph in this course can be executed, debugged and
    tested with zero API keys and zero network calls. It implements the same
    `BaseChatModel` surface that LangGraph relies on:

        * `invoke()` / `ainvoke()`  -> returns an AIMessage
        * `with_structured_output()` -> returns a dict matching a Pydantic schema

    The responses are *scripted by intent*, not random: if you ask it to
    classify a message, it classifies; if you ask it to summarise, it
    summarises. That keeps example output stable and reviewable.
    """

    # `responses` lets a caller pin exact replies, e.g. OfflineChatModel(
    #     responses=[AIMessage("hello")]
    # ). Otherwise a deterministic answer is synthesised from the prompt.
    responses: list[BaseMessage] = []
    tag: str = "offline"

    # -- BaseChatModel plumbing -------------------------------------------
    @property
    def _llm_type(self) -> str:
        return "offline-course-model"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        if self.responses:
            # Round-robin through pinned responses.
            idx = getattr(self, "_cursor", 0)
            self._cursor = idx + 1
            msg = self.responses[idx % len(self.responses)]
            return ChatResult(generations=[ChatGeneration(message=msg)])

        prompt = "\n".join(
            m.content if isinstance(m.content, str) else str(m.content) for m in messages
        )
        return ChatResult(generations=[ChatGeneration(message=AIMessage(self._synthesize(prompt)))])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._generate(messages, stop, run_manager, **kwargs)

    # -- Deterministic "reasoning" ----------------------------------------
    def _synthesize(self, prompt: str) -> str:
        p = prompt.lower()
        if "classify" in p or "intent" in p:
            return (
                "[offline-model] Classification: intent=question, urgency=low, "
                "topic=general, summary='User request classified offline.'"
            )
        if "summar" in p:
            return f"[offline-model] Summary of {len(prompt)} chars of input."
        if "json" in p:
            return '{"offline": true}'
        return f"[offline-model] Received {len(prompt)} chars. Replace me with a real Gemini call."

    # -- Structured output ------------------------------------------------
    def with_structured_output(
        self,
        schema: Any,
        *,
        include_raw: bool = False,
        **kwargs: Any,
    ) -> Runnable:
        """Return a runnable that produces a dict shaped like `schema`."""
        fields = _schema_fields(schema)

        def _build(_input: Any) -> dict:
            return {name: _placeholder_for(name, ann) for name, ann in fields.items()}

        if include_raw:

            def _with_raw(inp: Any) -> dict:
                out = _build(inp)
                return {"raw": AIMessage("[offline-model] raw"), "parsed": out, "parsing_error": None}

            return RunnableLambda(_with_raw)
        return RunnableLambda(_build)


def _schema_fields(schema: Any) -> dict[str, Any]:
    """Best-effort extraction of {field_name: annotation} from a Pydantic model."""
    ann = getattr(schema, "model_fields", None)
    if ann is not None:
        return dict(ann)
    if isinstance(schema, dict):
        return dict(schema)
    return {}


# Sensible defaults so structured-output examples produce a reviewable payload.
_SENTINELS = {
    "intent": "question",
    "urgency": "low",
    "topic": "general",
    "summary": "Offline summary.",
    "category": "general",
    "score": 0.5,
    "confidence": 0.9,
    "sentiment": "neutral",
    "priority": "normal",
    "answer": "Offline answer.",
    "title": "Offline title",
    "sentences": ["Offline sentence one.", "Offline sentence two."],
    "tags": ["offline"],
}


def _placeholder_for(name: str, annotation: Any) -> Any:
    if name in _SENTINELS:
        return _SENTINELS[name]
    text = str(annotation)
    if "bool" in text:
        return True
    if "int" in text and "str" not in text:
        return 1
    if "float" in text:
        return 0.5
    if "list" in text:
        return []
    if "dict" in text:
        return {}
    return "offline"


# --------------------------------------------------------------------------
# The public factory
# --------------------------------------------------------------------------
def get_llm(
    model: str | None = None,
    *,
    temperature: float = 0.0,
    **kwargs: Any,
) -> BaseChatModel:
    """Return a chat model.

    Gemini when `GOOGLE_API_KEY` is set, otherwise the offline model.
    """
    if _has_gemini_key():
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model or DEFAULT_MODEL,
            temperature=temperature,
            max_retries=2,
            **kwargs,
        )
    return OfflineChatModel()


def banner() -> str:
    """One-line description of which model backend is active."""
    if _has_gemini_key():
        return f"LLM backend: REAL Gemini ({DEFAULT_MODEL})"
    return "LLM backend: OFFLINE (set GOOGLE_API_KEY in .env to use real Gemini)"


def print_banner() -> None:
    print("=" * 78)
    print(f"  {banner()}")
    print("=" * 78)


def last_user_text(messages: Sequence[BaseMessage]) -> str:
    """Helper used across lessons: pull the most recent human message text."""
    for m in reversed(list(messages)):
        if isinstance(m, HumanMessage):
            return m.content if isinstance(m.content, str) else str(m.content)
    return ""


def iter_chunks(text: str, size: int = 24) -> Iterator[str]:
    """Yield `text` in chunks - used to demo token streaming without a network call."""
    for i in range(0, len(text), size):
        yield text[i : i + size]
