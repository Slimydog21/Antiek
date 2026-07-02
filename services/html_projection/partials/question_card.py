"""Question-card block partial (HPRJ SPR-02 / M2 + M6).

Renders ``antiek_question_card`` — an open-question reference. ``attrs.question_id``
resolved at render time; deleted/missing → tombstone. TipTap shape
(``substrate/notebooks/tiptap_codec.py:51``: ``question_card`` →
``attrs.question_id``).
"""

from __future__ import annotations

from typing import Any

from ..context import RenderContext
from ..escape import escape_text
from ._common import attr, inline_text
from ._ref import resolve_or_tombstone


def render(node: dict[str, Any], ctx: RenderContext) -> str:
    ref_id = attr(node, "question_id")
    resolved, tombstone = resolve_or_tombstone(ref_id, "question_card", ctx)
    if tombstone:
        return tombstone
    if resolved is not None:
        question = (
            resolved.payload.get("question")
            or resolved.payload.get("text")
            or attr(node, "question")
            or inline_text(node.get("content"))
        )
    else:
        question = attr(node, "question") or inline_text(node.get("content"))
    out = ['<div class="antiek-block antiek-question">']
    if question:
        out.append(f'<div class="antiek-question-q">{escape_text(question)}</div>')
    out.append("</div>")
    return "".join(out)
