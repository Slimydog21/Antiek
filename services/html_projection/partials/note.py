"""Note block partial (HPRJ SPR-02 / M2 + M6).

Renders ``antiek_note`` / ``note_block`` — a referenced note. ``attrs.note_id``
resolved at render time; deleted/missing → tombstone. TipTap shape
(``substrate/notebooks/tiptap_codec.py:48``: ``note_block`` → ``note``,
``attrs.note_id``).
"""

from __future__ import annotations

from typing import Any

from ..context import RenderContext
from ..escape import escape_text
from ._common import attr, inline_text
from ._ref import resolve_or_tombstone


def render(node: dict[str, Any], ctx: RenderContext) -> str:
    ref_id = attr(node, "note_id")
    resolved, tombstone = resolve_or_tombstone(ref_id, "note", ctx)
    if tombstone:
        return tombstone
    if resolved is not None:
        body = (
            resolved.payload.get("body")
            or resolved.payload.get("text")
            or attr(node, "body")
            or inline_text(node.get("content"))
        )
    else:
        body = attr(node, "body") or inline_text(node.get("content"))
    out = ['<div class="antiek-block antiek-note">']
    if body:
        out.append(escape_text(body))
    out.append("</div>")
    return "".join(out)
