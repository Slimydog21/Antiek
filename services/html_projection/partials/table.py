"""Table partial — a real ``<table>``, not a flattened run of cell text.

Entry point onto :mod:`._structural`. This is the block that proves the
ingest bridge: a table in a PDF or a ``.docx`` is a grid of related values,
and a projection that renders it as one paragraph of concatenated cells has
not lost the formatting, it has lost the data.
"""

from __future__ import annotations

from typing import Any

from ._structural import render_table_at


def render(node: dict[str, Any], ctx: Any) -> str:
    return render_table_at(node, ctx, 0)


__all__ = ["render"]
