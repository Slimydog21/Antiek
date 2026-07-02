"""AI Q&A block partial (HPRJ SPR-02 / M2).

Renders ``antiek_ai_qa``. Shape (from
``services/antiek_format/tests/conftest.py:126``):
``{"type":"antiek_ai_qa","attrs":{"block_id":...,"question":...,
"answer":...,"attribution":...}}``

Mirrors ``markdown_projector.py:191`` (Q/A/attribution) in HTML.
"""

from __future__ import annotations

from typing import Any

from ..escape import escape_text
from ._common import attr, inline_text


def render(node: dict[str, Any], ctx: Any) -> str:
    question = attr(node, "question")
    answer = attr(node, "answer")
    if not answer:
        answer = inline_text(node.get("content"))
    attribution = attr(node, "attribution")
    out = ['<div class="antiek-block antiek-qa">']
    if question:
        out.append(f'<div class="antiek-qa-q">Q: {escape_text(question)}</div>')
    if answer:
        out.append(f'<div class="antiek-qa-a">A: {escape_text(answer)}</div>')
    if attribution:
        out.append(f'<div class="antiek-qa-attr">{escape_text(attribution)}</div>')
    out.append("</div>")
    return "".join(out)
