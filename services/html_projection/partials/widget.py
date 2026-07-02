"""Widget block partial — wires the SPR-03 widget seam into the renderer.

Renders ``antiek_widget``: a chart / sparkline / dep-graph / stat-chip / donut /
timeline / cite-block from the SPR-03 library. ``attrs.kind`` selects the
widget; ``attrs.data`` (a dict) is its input — or, when ``data`` is absent, the
remaining attrs (minus ``kind``). Dispatch goes through
``tokens.render_widget(kind, data)`` — the registered SPR-03 widget, which is
script-free + deterministic by construction. An unknown kind renders the seam's
visible unsupported-widget placeholder, never a crash.

This is the seam the SPR-03 contract reserved (`contract.widget`) and that
SPR-05/06 artifacts can now use to embed a chart in a synthesis or notebook
projection — closing the gap where the seven widgets were built but unreachable
from the renderer.
"""

from __future__ import annotations

from typing import Any

from .. import tokens
from .. import widgets as _widgets  # noqa: F401 — import registers the 7 widgets
from ._common import attr


def render(node: dict[str, Any], ctx: Any) -> str:
    attrs = node.get("attrs")
    if not isinstance(attrs, dict):
        attrs = {}
    kind = attr(node, "kind")
    if not kind:
        # kindless widget -> the seam's deterministic placeholder.
        return tokens.render_widget("", {})
    data = attrs.get("data")
    if not isinstance(data, dict):
        data = {k: v for k, v in attrs.items() if k != "kind"}
    return tokens.render_widget(str(kind), data)
