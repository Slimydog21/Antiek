"""Claim-card block partial (HPRJ SPR-02 / M2 + M6).

Renders ``antiek_claim_card`` — a live claim reference. ``attrs.claim_id``
is resolved at render time; a deleted/missing claim renders the tombstone
(M6). TipTap shape (``substrate/notebooks/tiptap_codec.py:46``:
``claim_card`` → ``attrs.claim_id``).
"""

from __future__ import annotations

from typing import Any

from ..context import RenderContext
from ..escape import escape_text
from ._common import attr, inline_text
from ._ref import resolve_or_tombstone


def render(node: dict[str, Any], ctx: RenderContext) -> str:
    ref_id = attr(node, "claim_id")
    resolved, tombstone = resolve_or_tombstone(ref_id, "claim_card", ctx)
    if tombstone:
        return tombstone
    if resolved is not None:
        statement = (
            resolved.payload.get("statement")
            or resolved.payload.get("text")
            or attr(node, "statement")
            or inline_text(node.get("content"))
        )
    else:
        # No ref_id — render inline content (block isn't a ref).
        statement = attr(node, "statement") or inline_text(node.get("content"))
    out = ['<div class="antiek-block antiek-claim">']
    if statement:
        out.append(f'<div class="antiek-claim-statement">{escape_text(statement)}</div>')
    else:
        out.append('<div class="antiek-claim-statement">(empty claim)</div>')
    out.append("</div>")
    return "".join(out)
