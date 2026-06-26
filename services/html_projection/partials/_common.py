"""Shared helpers for block partials (HPRJ SPR-02 / M2).

Partials receive a node (a TipTap node dict), the ``RenderContext`` (for
ref resolution), and return a fragment of HTML (no ``<html>``/``<body>``
wrapping — the core renderer assembles the document shell). Every partial
MUST:

  - escape all user/substrate text via ``escape.escape_text`` /
    ``escape.escape_attr`` (never interpolate raw strings);
  - emit NO script, NO event-handler attrs, NO external src/href
    (the zero-script gate will catch any slip — but partials are the
    right place to get it right);
  - be pure: no wall-clock, no I/O, no globals.

``inline_text`` flattens a TipTap content array (text nodes + marks) to
an HTML string with marks wrapped in the right tags. It handles bold,
italic, code, and link marks; unknown marks pass their text through
undecorated (the text is still escaped, so no injection). This mirrors
``services/antiek_format/markdown_projector.py`` ``_inline_from_content``
but emits HTML.
"""

from __future__ import annotations

from typing import Any

from ..escape import escape_attr, escape_text


def inline_text(content: Any) -> str:
    """Flatten a TipTap content array to escaped HTML inline text.

    Handles ``text`` nodes with ``bold``/``italic``/``code``/``link``
    marks. Nested content arrays (e.g. inside a paragraph) recurse.
    Unknown node types contribute their recursed inline text if they
    have a ``content`` array, else nothing (never a crash).
    """
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for node in content:
        if not isinstance(node, dict):
            continue
        ntype = node.get("type")
        if ntype == "text":
            text = escape_text(str(node.get("text", "") or ""))
            marks = node.get("marks") or []
            for mark in marks:
                if not isinstance(mark, dict):
                    continue
                mt = mark.get("type", "")
                mattrs = mark.get("attrs") or {}
                if mt == "bold":
                    text = f"<strong>{text}</strong>"
                elif mt == "italic":
                    text = f"<em>{text}</em>"
                elif mt == "code":
                    text = f"<code>{text}</code>"
                elif mt == "link":
                    href = escape_attr(str(mattrs.get("href", "") or ""))
                    text = f'<a href="{href}">{text}</a>'
                # unknown mark: pass through (text already escaped)
            parts.append(text)
        elif isinstance(node.get("content"), list):
            parts.append(inline_text(node["content"]))
        elif ntype == "hardBreak":
            parts.append("<br>")
    return "".join(parts)


def attr(node: dict, name: str, default: str = "") -> str:
    """Read a string attr from a node's ``attrs`` dict, defaulting to
    ``default``. Coerces to str; never raises."""
    attrs = node.get("attrs") or {}
    val = attrs.get(name)
    if val is None:
        return default
    return str(val)


def block_id_of(node: dict) -> str:
    """The node's ``attrs.block_id`` (empty string if absent)."""
    return attr(node, "block_id")


__all__ = ["attr", "block_id_of", "inline_text"]
