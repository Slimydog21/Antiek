"""MASTER.md-section block partial (HPRJ SPR-02 / M2 + M6).

Renders ``antiek_master_md_section`` — a referenced synthesis section.
``attrs.synthesis_id`` resolved at render time; deleted/missing → tombstone.
TipTap shape (``substrate/notebooks/tiptap_codec.py:50``:
``master_md_section`` → ``attrs.synthesis_id``).
"""

from __future__ import annotations

from typing import Any

from ..context import RenderContext
from ..escape import escape_text
from ._common import attr, inline_text
from ._ref import resolve_or_tombstone


def render(node: dict[str, Any], ctx: RenderContext) -> str:
    ref_id = attr(node, "synthesis_id")
    resolved, tombstone = resolve_or_tombstone(ref_id, "master_md_section", ctx)
    if tombstone:
        return tombstone
    heading = attr(node, "heading") or attr(node, "title")
    body = ""
    if resolved is not None:
        heading = (
            resolved.payload.get("heading")
            or resolved.payload.get("title")
            or heading
        )
        body = (
            resolved.payload.get("body")
            or resolved.payload.get("text")
            or ""
        )
    else:
        body = inline_text(node.get("content"))
    out = ['<div class="antiek-block antiek-mdsection">']
    if heading:
        out.append(f'<div class="antiek-mdsection-head">{escape_text(heading)}</div>')
    if body:
        out.append(f'<div class="antiek-prose">{escape_text(body)}</div>')
    out.append("</div>")
    return "".join(out)
