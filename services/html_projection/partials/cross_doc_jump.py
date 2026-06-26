"""Cross-doc-jump block partial (HPRJ SPR-02 / M2).

Renders ``antiek_cross_doc_jump``. Shape (from
``services/antiek_format/tests/conftest.py:142``):
``{"type":"antiek_cross_doc_jump","attrs":{"block_id":...,"label":...,
"target_document_id":...}}``

A cross-document jump targets another Antiek document by id. The
projection is self-contained, so the jump target is not navigable from
inside the artifact — we surface the label + target document id as text
(the reader sees the cross-reference; the live app resolves the jump).
Mirrors ``markdown_projector.py:209``.
"""

from __future__ import annotations

from typing import Any

from ..escape import escape_text
from ._common import attr, inline_text


def render(node: dict[str, Any], ctx: Any) -> str:
    label = attr(node, "label")
    if not label:
        label = inline_text(node.get("content")) or "cross-document jump"
    target_doc = attr(node, "target_document_id")
    out = ['<div class="antiek-block antiek-crossdoc">']
    out.append(escape_text(label))
    if target_doc:
        out.append(f" &rarr; {escape_text(target_doc)}")
    out.append("</div>")
    return "".join(out)
