"""Prose block partial (HPRJ SPR-02 / M2).

Renders TipTap prose / paragraph / doc nodes. The prose block is the
fallback bedrock: it carries inline text (with marks) and may contain
nested paragraphs. Each top-level text-carrying node becomes a ``<p>``.

The doc-model prose node shape (from
``services/antiek_format/tests/conftest.py:65`` ``antiek_prose``):
``{"type":"antiek_prose","attrs":{"block_id":...},"content":[{"type":"text","text":...}]}``

A bare ``paragraph`` node (standard TipTap) has the same content shape
without the antiek attrs; both render the same way.
"""

from __future__ import annotations

from typing import Any

from ._common import inline_text


def _anchor_attr(node: dict[str, Any]) -> str:
    anchor = (node.get("attrs") or {}).get("anchor_id")
    if isinstance(anchor, str) and anchor.startswith("antiek-chunk-") and len(anchor) == 77:
        suffix = anchor.removeprefix("antiek-chunk-")
        if all(character in "0123456789abcdef" for character in suffix):
            return f' id="{anchor}" data-antiek-chunk-anchor="true"'
    return ""


def render(node: dict[str, Any], ctx: Any) -> str:
    """Render a prose/paragraph node to HTML fragment."""
    content = node.get("content")
    # If the node has a content array of paragraph-like children, render
    # each as a <p>. Otherwise treat the node itself as one paragraph.
    if isinstance(content, list) and content and all(
        isinstance(c, dict) and c.get("type") in ("paragraph", "antiek_prose")
        for c in content
    ):
        paras = "".join(
            f'<p class="antiek-prose">{inline_text(c.get("content"))}</p>'
            for c in content
        )
        return f'<div class="antiek-block">{paras}</div>'
    return f'<p class="antiek-prose"{_anchor_attr(node)}>{inline_text(content)}</p>'
