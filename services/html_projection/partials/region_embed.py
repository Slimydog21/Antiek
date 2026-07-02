"""Region-embed block partial (HPRJ SPR-02 / M2 + M6).

Renders ``antiek_region_embed`` — an embedded PDF region reference. The
node carries ``attrs.document_id`` (the source PDF) and optionally
``attrs.passage_text`` (the region's text). The ref is resolved live at
render time via ``ctx.resolver``; a deleted/missing ref renders the
tombstone (M6).

TipTap node shape (from ``substrate/notebooks/tiptap_codec.py:47``:
``region_embed`` → ``attrs.document_id``).
"""

from __future__ import annotations

from typing import Any

from ..context import RenderContext
from ..escape import escape_text
from ._common import attr, inline_text
from ._ref import resolve_or_tombstone


def render(node: dict[str, Any], ctx: RenderContext) -> str:
    ref_id = attr(node, "document_id")
    resolved, tombstone = resolve_or_tombstone(ref_id, "region_embed", ctx)
    if tombstone:
        return tombstone
    if resolved is not None:
        passage = (
            resolved.payload.get("passage_text")
            or resolved.payload.get("text")
            or attr(node, "passage_text")
            or inline_text(node.get("content"))
        )
        doc_id = escape_text(str(resolved.payload.get("document_id", ref_id)))
    else:
        passage = attr(node, "passage_text") or inline_text(node.get("content"))
        doc_id = escape_text(ref_id)
    out = ['<div class="antiek-block antiek-region">']
    if passage:
        out.append(f'<div class="antiek-highlight-passage">{escape_text(passage)}</div>')
    if doc_id:
        out.append(f'<div class="antiek-region-ref">region &middot; {doc_id}</div>')
    out.append("</div>")
    return "".join(out)
