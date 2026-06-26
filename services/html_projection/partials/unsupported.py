"""Unsupported-block fallback partial (HPRJ SPR-02 / M1).

Renders a VISIBLE placeholder for a node whose ``type`` is not in the
contract table. Master-spec invariant: never a silent drop, never a
crash. The placeholder names the type so a reader knows something was
there and what kind it claimed to be.

The raw node JSON is NOT inlined into the visible HTML — it stays only
inside the inert data island (the round-trip preserves it byte-for-byte).
This keeps the visible surface honest about what could not be rendered
without leaking unescaped structure (the node could contain anything;
inlining it as visible text would be an injection risk and a lie about
what the reader is seeing). The data island is the round-trip channel;
the visible surface is the reading experience. They are separate.

The type string is escaped (it comes from the doc-model and could be
hostile). The placeholder is gate-clean: no script, no handler, no
external asset.
"""

from __future__ import annotations

from ..escape import escape_text


def render(node_type: str) -> str:
    """Render the unsupported-block placeholder for ``node_type``."""
    safe = escape_text(node_type)
    return (
        f'<div class="antiek-block antiek-unsupported">'
        f"unsupported block ({safe})"
        "</div>"
    )


__all__ = ["render"]
