"""Heading block partial — the source document's outline.

An ingested document's heading levels are its structure: the table of
contents, the reading order, the thing a screen reader navigates by. They
are preserved VERBATIM (``attrs.level`` 1-6, clamped), not renumbered
against the projection's own ``<h1>`` title. A source ``<h1>`` therefore
stays an ``<h1>`` even when the renderer has already emitted a title — the
alternative, silently demoting every heading by one, would make the
projected outline disagree with the source outline, and the source outline
is the one the reader is trying to read.

A heading with no level renders as ``<h2>``: the most common case in a
document body, and never a level the title occupies.
"""

from __future__ import annotations

from typing import Any

from ._common import attr, inline_text


def render(node: dict[str, Any], ctx: Any) -> str:
    raw = attr(node, "level")
    try:
        level = int(raw) if raw else 2
    except ValueError:
        level = 2
    level = min(6, max(1, level))
    return f'<h{level} class="antiek-heading">{inline_text(node.get("content"))}</h{level}>'


__all__ = ["render"]
