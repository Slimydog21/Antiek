"""Thematic-break partial — ``<hr>``.

A rule carries no text, which is exactly why it needs a partial: without
one it would hit the unsupported fallback and a reader would see a warning
box where the source had a section break. It is the cheapest possible
block and the one most likely to be dismissed as not worth mapping.
"""

from __future__ import annotations

from typing import Any


def render(node: dict[str, Any], ctx: Any) -> str:
    return '<hr class="antiek-rule">'


__all__ = ["render"]
