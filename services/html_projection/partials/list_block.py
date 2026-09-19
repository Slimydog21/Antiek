"""List partial — ``<ul>`` / ``<ol>`` with nesting.

Entry point onto :mod:`._structural`, where the list lives because a list
item can hold paragraphs, tables and further lists and the recursion has
to share one depth bound with the other structural blocks.
"""

from __future__ import annotations

from typing import Any

from ._structural import render_list_at


def render(node: dict[str, Any], ctx: Any) -> str:
    return render_list_at(node, ctx, 0)


__all__ = ["render"]
