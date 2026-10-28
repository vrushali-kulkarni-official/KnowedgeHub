"""Pretty-printing helpers used by the lessons and examples."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import BaseMessage


def hr(title: str = "", width: int = 78) -> None:
    """A horizontal rule with an optional title."""
    if not title:
        print("-" * width)
        return
    pad = width - len(title) - 3
    left = pad // 2
    right = pad - left
    print("-" * left + f" {title} " + "-" * right)


def section(title: str, width: int = 78) -> None:
    print()
    hr(title, width)
    print()


def show(value: Any, label: str | None = None) -> None:
    """Print a value with optional label, truncating long strings."""
    if label:
        print(f"{label}: ", end="")
    text = repr(value)
    if len(text) > 400:
        text = text[:400] + " ...<truncated>"
    print(text)


def show_state(state: dict, label: str = "state") -> None:
    """Print a LangGraph state dict, expanding message lists."""
    print(f"--- {label} ---")
    for k, v in state.items():
        if isinstance(v, list) and v and isinstance(v[0], BaseMessage):
            print(f"  {k}: [{len(v)} message(s)]")
            for m in v:
                role = getattr(m, "type", type(m).__name__)
                content = m.content if isinstance(m.content, str) else str(m.content)
                if len(content) > 160:
                    content = content[:160] + " ..."
                print(f"      - {role}: {content}")
        else:
            shown = repr(v)
            if len(shown) > 300:
                shown = shown[:300] + " ...<truncated>"
            print(f"  {k}: {shown}")
    print("---")


def show_mermaid(graph: Any, title: str = "graph") -> None:
    """Print the Mermaid source of a compiled graph."""
    section(title)
    try:
        print(graph.get_graph().draw_mermaid())
    except Exception as exc:  # pragma: no cover - visualisation is best-effort
        print(f"(could not draw graph: {exc})")
