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

from ..escape import escape_attr
from ._common import attr, inline_text


def _semantic_anchor_attrs(node: dict[str, Any]) -> str:
    attributes: list[str] = []
    node_id = attr(node, "node_id")
    source_document_id = attr(node, "source_document_id")
    if node_id:
        attributes.append(f'data-antiek-node-id="{escape_attr(node_id)}"')
    if source_document_id:
        attributes.append(
            f'data-antiek-source-document-id="{escape_attr(source_document_id)}"'
        )
    return "" if not attributes else " " + " ".join(attributes)


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
            f'<p class="antiek-prose"{_semantic_anchor_attrs(c)}>'
            f'{inline_text(c.get("content"))}</p>'
            for c in content
        )
        return f'<div class="antiek-block">{paras}</div>'
    return (
        f'<p class="antiek-prose"{_semantic_anchor_attrs(node)}>'
        f"{inline_text(content)}</p>"
    )
