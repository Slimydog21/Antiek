"""Cite-link block partial (HPRJ SPR-02 / M2).

Renders ``antiek_cite_link``. Shape (from
``services/antiek_format/tests/conftest.py:134``):
``{"type":"antiek_cite_link","attrs":{"block_id":...,"label":...,
"target_url":...}}``

The target_url may be a relative deep-link (``/wrestle/doc-...?chunk=...``)
or an absolute URL. The projection is self-contained, so an external
``https://`` href would not resolve offline — but a citation link is a
*reference*, not an asset, and the link text is always rendered (the
reader sees the citation even if the link doesn't resolve offline). We
render the href as-is (escaped) so the link works when the artifact IS
online. The zero-script gate does NOT flag ``<a href="https://...">`` —
only ``javascript:`` hrefs and external ``img src`` — so this is
gate-clean. Mirrors ``markdown_projector.py:204``.
"""

from __future__ import annotations

from typing import Any

from ..escape import escape_attr, escape_text
from ._common import attr, inline_text


def render(node: dict[str, Any], ctx: Any) -> str:
    label = attr(node, "label")
    if not label:
        label = inline_text(node.get("content")) or "cite"
    target = attr(node, "target_url") or attr(node, "deeplink")
    if target:
        return (
            f'<div class="antiek-block antiek-cite">'
            f'<a href="{escape_attr(target)}">{escape_text(label)}</a>'
            f"</div>"
        )
    return (
        f'<div class="antiek-block antiek-cite">{escape_text(label)}</div>'
    )
