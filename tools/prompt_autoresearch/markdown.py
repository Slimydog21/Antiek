"""Markdown escaping helpers for operator-facing autoresearch reports."""

from __future__ import annotations


_INLINE_ESCAPES = frozenset("\\`*_{}[]()#+|")


def markdown_inline(value: str) -> str:
    """Escape inline Markdown control characters and collapse line breaks."""
    text = value.replace("\r", " ").replace("\n", " ")
    return "".join(f"\\{char}" if char in _INLINE_ESCAPES else char for char in text)


def markdown_code_span(value: str) -> str:
    """Render a value as a Markdown code span, even when it contains backticks."""
    text = value.replace("\r", " ").replace("\n", " ")
    if "`" not in text:
        return f"`{text}`"

    fence = "`"
    while fence in text:
        fence += "`"
    return f"{fence} {text} {fence}"
