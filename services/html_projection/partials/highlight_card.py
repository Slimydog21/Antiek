"""Highlight-card block partial (HPRJ SPR-02 / M2).

Renders ``antiek_highlight_card``. Shape (from
``services/antiek_format/tests/conftest.py:57``):
``{"type":"antiek_highlight_card","attrs":{"block_id":...,
"passage_text":...,"operator_framing":...}}``

The passage is the highlighted source text; the framing is the operator's
editorial note. Both are escaped. Mirrors the markdown projector's
highlight rendering (``markdown_projector.py:159``) but emits HTML.
"""

from __future__ import annotations

from typing import Any

from ..escape import escape_text
from ._common import attr, inline_text


def render(node: dict[str, Any], ctx: Any) -> str:
    passage = attr(node, "passage_text")
    if not passage:
        passage = inline_text(node.get("content"))
    framing = attr(node, "operator_framing")
    out = ['<div class="antiek-block antiek-highlight">']
    if passage:
        out.append(f'<div class="antiek-highlight-passage">{escape_text(passage)}</div>')
    if framing:
        out.append(f'<div class="antiek-highlight-framing">{escape_text(framing)}</div>')
    out.append("</div>")
    return "".join(out)
