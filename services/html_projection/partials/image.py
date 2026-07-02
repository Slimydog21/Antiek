"""Image block partial (HPRJ SPR-02 / M2 + M6).

Renders ``antiek_image`` — a referenced image artifact. ``attrs.image_id``
resolved at render time; deleted/missing → tombstone. TipTap shape
(``substrate/notebooks/tiptap_codec.py:54``: ``image`` → ``attrs.image_id``).

SCRIPT-FREE / SELF-CONTAINED INVARIANT: the projection MUST NOT emit an
``<img src="https://...">`` to an external URL (the zero-script gate M4
flags external img src, and the self-contained invariant forbids external
assets). The image bytes live in the substrate / container, not inline in
the projection. We therefore render an accessible PLACEHOLDER: the alt
text + image id, as text. A reader sees what the image was; the live app
shows the actual image. This is the same lossy-but-honest treatment voice
blocks get (audio bytes are not embedded either).

We deliberately do NOT emit ``<img src="data:...">`` either: a data-URI
would embed binary bytes into the artifact (bloat + the gate's external-src
check would need a data-URI carve-out, muddying the contract). The
placeholder is the clean choice. SPR-03 widgets may revisit inline image
rendering; SPR-02 ships the placeholder.
"""

from __future__ import annotations

from typing import Any

from ..context import RenderContext
from ..escape import escape_text
from ._common import attr, inline_text
from ._ref import resolve_or_tombstone


def render(node: dict[str, Any], ctx: RenderContext) -> str:
    ref_id = attr(node, "image_id")
    resolved, tombstone = resolve_or_tombstone(ref_id, "image", ctx)
    if tombstone:
        return tombstone
    alt = attr(node, "alt") or attr(node, "caption")
    if resolved is not None:
        alt = (
            resolved.payload.get("alt")
            or resolved.payload.get("caption")
            or alt
            or "image"
        )
    if not alt:
        alt = inline_text(node.get("content")) or "image"
    image_id = escape_text(ref_id) if ref_id else ""
    out = ['<div class="antiek-block antiek-image">']
    out.append(f'<div class="antiek-image-alt">{escape_text(alt)}</div>')
    if image_id:
        out.append(f'<div class="antiek-region-ref">image &middot; {image_id}</div>')
    out.append("</div>")
    return "".join(out)
