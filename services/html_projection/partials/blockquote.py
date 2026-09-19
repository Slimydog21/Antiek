"""Blockquote partial — ``<blockquote>``.

Entry point onto :mod:`._structural`. A quote can contain any block, so its
children go through the shared depth-bounded dispatch rather than being
flattened to inline text.
"""

from __future__ import annotations

from typing import Any

from ._structural import render_blockquote_at


def render(node: dict[str, Any], ctx: Any) -> str:
    return render_blockquote_at(node, ctx, 0)


__all__ = ["render"]
