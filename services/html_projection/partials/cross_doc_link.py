"""Cross-doc-link block partial (HPRJ SPR-02 / M2 + M6).

Renders ``antiek_cross_doc_link`` — a substrate cross-document link bridge.
``attrs.source_document_id`` is the canonical ref (per
``substrate/notebooks/tiptap_codec.py:49``). Resolved at render time;
deleted/missing source → tombstone. The node also carries
``attrs.target_document_id`` / ``attrs.label`` for the link target.
"""

from __future__ import annotations

from typing import Any

from ..context import RenderContext
from ..escape import escape_text
from ._common import attr, inline_text
from ._ref import resolve_or_tombstone


def render(node: dict[str, Any], ctx: RenderContext) -> str:
    ref_id = attr(node, "source_document_id")
    _, tombstone = resolve_or_tombstone(ref_id, "cross_doc_link", ctx)
    if tombstone:
        return tombstone
    label = attr(node, "label") or inline_text(node.get("content")) or "cross-document link"
    target = attr(node, "target_document_id")
    out = ['<div class="antiek-block antiek-crossdoc">']
    out.append(escape_text(label))
    if target:
        out.append(f" &rarr; {escape_text(target)}")
    out.append("</div>")
    return "".join(out)
