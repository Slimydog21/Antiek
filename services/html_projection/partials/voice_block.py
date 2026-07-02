"""Voice-block partial (HPRJ SPR-02 / M2).

Renders ``antiek_voice_block``. Shape (from
``services/antiek_format/tests/conftest.py:117``):
``{"type":"antiek_voice_block","attrs":{"block_id":...,
"duration_seconds":...,"transcript":...}}``

The audio itself is a binary in the ``.antiek`` container
(``blocks/<block_id>.audio``); the projection is SCRIPT-FREE and
SELF-CONTAINED, so we do NOT embed audio bytes (no ``<audio src>`` to an
external blob, no data-URI — the latter would bloat the artifact and the
gate flags external-ish sources). Instead we surface the duration and
transcript as readable text. This matches the markdown projector's
lossy-voice treatment (``markdown_projector.py:167``) and the SPEC.md §8
note that voice playback is a best-effort in projections.
"""

from __future__ import annotations

from typing import Any

from ..escape import escape_text
from ._common import attr, inline_text


def render(node: dict[str, Any], ctx: Any) -> str:
    duration_raw = attr(node, "duration_seconds") or attr(node, "duration")
    try:
        duration = int(float(duration_raw)) if duration_raw else 0
    except (TypeError, ValueError):
        duration = 0
    mins, secs = divmod(duration, 60)
    transcript = attr(node, "transcript")
    if not transcript:
        transcript = inline_text(node.get("content"))
    out = ['<div class="antiek-block antiek-voice">']
    out.append(
        f'<div class="antiek-voice-meta">voice note &middot; {mins}:{secs:02d}</div>'
    )
    if transcript:
        out.append(f'<div class="antiek-voice-transcript">{escape_text(transcript)}</div>')
    out.append("</div>")
    return "".join(out)
