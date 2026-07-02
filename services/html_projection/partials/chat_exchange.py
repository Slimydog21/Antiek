"""Chat-exchange block partial (HPRJ SPR-02 / M2 + M6).

Renders ``antiek_chat_exchange`` — a referenced chat exchange snippet.
``attrs.exchange_id`` resolved at render time; deleted/missing → tombstone.
TipTap shape (``substrate/notebooks/tiptap_codec.py:52``: ``chat_exchange``
→ ``attrs.exchange_id``).

A resolved exchange carries a list of turns ``[{role, text}, ...]``. Each
turn renders as a labeled line.
"""

from __future__ import annotations

from typing import Any

from ..context import RenderContext
from ..escape import escape_text
from ._common import inline_text
from ._ref import resolve_or_tombstone


def render(node: dict[str, Any], ctx: RenderContext) -> str:
    ref_id = node.get("attrs", {}).get("exchange_id") if isinstance(node.get("attrs"), dict) else ""
    ref_id = str(ref_id) if ref_id else ""
    resolved, tombstone = resolve_or_tombstone(ref_id, "chat_exchange", ctx)
    if tombstone:
        return tombstone
    turns: list[dict[str, Any]] = []
    if resolved is not None:
        turns = list(resolved.payload.get("turns") or [])
    if not turns:
        inline = inline_text(node.get("content"))
        if inline:
            turns = [{"role": "", "text": inline}]
    out = ['<div class="antiek-block antiek-chat">']
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        role = escape_text(str(turn.get("role", "") or ""))
        text = escape_text(str(turn.get("text", "") or ""))
        out.append('<div class="antiek-chat-turn">')
        if role:
            out.append(f'<span class="antiek-chat-role">{role}:</span> ')
        out.append(text)
        out.append("</div>")
    out.append("</div>")
    return "".join(out)
