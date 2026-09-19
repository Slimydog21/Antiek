"""Structural document blocks — headings, lists, tables, code, quotes, rules.

These six types are the vocabulary every *document* has and no research
export needed: an ingested PDF, web page or ``.docx`` is mostly headings,
lists and tables, and the SPR-02 contract covered none of them. A node it
does not know renders as ``unsupported block (...)``, which is the right
answer for an unknown Antiek block and the wrong one for a table — so the
table would have been honestly, visibly, permanently lost.

They live in ONE module because they are mutually recursive: a list item
holds paragraphs and nested lists, a blockquote holds anything, a table
cell holds paragraphs. Splitting them across six files would mean six
lazy cross-imports and six copies of the depth bound. Each contract row
still gets its own partial module (the taxonomy stays legible); those
modules are entry points onto the functions here.

RECURSION BOUND: ``MAX_NEST``. A doc-model is data, and data can be
hostile or merely pathological (a ``.docx`` of nothing but nested lists).
Past the bound a node renders the unsupported placeholder naming its type
and the limit — visible, honest, and bounded, never a RecursionError
inside a request handler.

NEVER A SILENT DROP: every child that is not structural is handed to the
renderer's own block dispatch, so an unknown type inside a list item gets
the same visible placeholder it would get at top level. The escape
discipline is the partial contract's: all text through
``escape.escape_text``, all attribute values through ``escape_attr``, no
script, no external asset.
"""

from __future__ import annotations

from typing import Any

from ..escape import escape_attr, escape_text
from . import unsupported as unsupported_partial
from ._common import attr, inline_text

# Deep enough for any real document (the ingest renderer bounds its own
# markdown nesting at 8 for the same reason), shallow enough that the
# recursion cannot exhaust the stack.
MAX_NEST: int = 8

_LIST_TYPES = frozenset({"antiek_list", "list", "bulletList", "orderedList"})
_QUOTE_TYPES = frozenset({"antiek_blockquote", "blockquote"})
_TABLE_TYPES = frozenset({"antiek_table", "table"})
_PARAGRAPH_TYPES = frozenset({"antiek_prose", "prose", "paragraph"})


def _bare(node_type: str) -> str:
    return node_type[len("antiek_"):] if node_type.startswith("antiek_") else node_type


def _int_attr(node: dict[str, Any], name: str) -> int | None:
    """A non-negative integer attr, or None. Never raises: the doc-model is
    JSON and a caller can put anything in it."""
    raw = attr(node, name)
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value >= 0 else None


def _is_inline(node: Any) -> bool:
    """Whether a child node carries inline content rather than a block.

    ``inline_text`` understands ``text`` and ``hardBreak``; anything else is
    a block and must go through the block dispatch so it cannot be flattened
    into a run of text (which is how structure gets lost quietly)."""
    return isinstance(node, dict) and node.get("type") in ("text", "hardBreak")


# ── The depth-aware block dispatch ──


def render_block_at(node: Any, ctx: Any, depth: int) -> str:
    """Render one node at nesting ``depth``.

    Structural types recurse here (carrying the depth); everything else
    goes to the renderer's own top-level dispatch, which reaches the Antiek
    partials and the unsupported fallback. The renderer import is deferred
    to call time because the renderer imports every partial at module
    import — the lazy import is the only way round that cycle, and it costs
    nothing after the first call (``sys.modules`` caches it)."""
    if not isinstance(node, dict):
        return unsupported_partial.render("<non-dict-node>")
    node_type = str(node.get("type", "") or "")
    if not node_type:
        return unsupported_partial.render("<empty-type>")
    if depth >= MAX_NEST:
        return unsupported_partial.render(f"{node_type} beyond nesting depth {MAX_NEST}")
    if node_type in _LIST_TYPES:
        return render_list_at(node, ctx, depth)
    if node_type in _QUOTE_TYPES:
        return render_blockquote_at(node, ctx, depth)
    if node_type in _TABLE_TYPES:
        return render_table_at(node, ctx, depth)
    from .. import renderer

    return renderer.render_block(node, ctx)


def render_children(nodes: Any, ctx: Any, depth: int) -> str:
    """Render a content array of BLOCK nodes at ``depth``.

    Inline children (``text``/``hardBreak``) that appear where blocks were
    expected are gathered into a paragraph rather than dropped — a
    hand-written doc-model that puts bare text in a list item still reads
    correctly."""
    if not isinstance(nodes, list):
        return ""
    out: list[str] = []
    run: list[Any] = []

    def flush() -> None:
        if not run:
            return
        text = inline_text(list(run))
        run.clear()
        if text:
            out.append(f'<p class="antiek-prose">{text}</p>')

    for child in nodes:
        if _is_inline(child):
            run.append(child)
            continue
        flush()
        out.append(render_block_at(child, ctx, depth))
    flush()
    return "".join(out)


def _tight_children(nodes: Any, ctx: Any, depth: int) -> str:
    """Like :func:`render_children`, but a lone paragraph renders as bare
    inline text. List items and table cells read better without a block
    paragraph's margins wrapped round their only line, and the difference
    is purely presentational — the island still carries the paragraph."""
    if isinstance(nodes, list) and len(nodes) == 1:
        only = nodes[0]
        if isinstance(only, dict) and only.get("type") in _PARAGRAPH_TYPES:
            return inline_text(only.get("content"))
    if isinstance(nodes, list) and nodes and all(_is_inline(n) for n in nodes):
        return inline_text(nodes)
    return render_children(nodes, ctx, depth)


# ── Lists ──


def render_list_at(node: dict[str, Any], ctx: Any, depth: int) -> str:
    """``bulletList`` / ``orderedList`` → ``<ul>`` / ``<ol>``.

    Ordered-ness comes from the node type, or from ``attrs.ordered`` for the
    generic ``antiek_list`` form. ``attrs.start`` is emitted only when it is
    not 1, matching how the ingest renderer writes it."""
    node_type = str(node.get("type", ""))
    ordered = node_type == "orderedList" or str(attr(node, "ordered")).lower() in (
        "true",
        "1",
    )
    start = _int_attr(node, "start")
    if ordered:
        open_tag = "<ol class=\"antiek-list\">" if start in (None, 1) else (
            f'<ol class="antiek-list" start="{escape_attr(str(start))}">'
        )
        close_tag = "</ol>"
    else:
        open_tag, close_tag = '<ul class="antiek-list">', "</ul>"
    items = node.get("content")
    out = [open_tag]
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                out.append(f"<li>{unsupported_partial.render('<non-dict-node>')}</li>")
                continue
            if _bare(str(item.get("type", ""))) not in ("listItem", "list_item"):
                # Not a list item: render it as a block inside its own <li>
                # rather than dropping it, so a malformed list still shows
                # everything it carried.
                out.append(f"<li>{render_block_at(item, ctx, depth + 1)}</li>")
                continue
            out.append(f"<li>{_tight_children(item.get('content'), ctx, depth + 1)}</li>")
    out.append(close_tag)
    return "".join(out)


# ── Blockquotes ──


def render_blockquote_at(node: dict[str, Any], ctx: Any, depth: int) -> str:
    """``blockquote`` → ``<blockquote>`` carrying full block content."""
    inner = render_children(node.get("content"), ctx, depth + 1)
    return f'<blockquote class="antiek-quote">{inner}</blockquote>'


# ── Tables ──

_HEADER_CELL_TYPES = frozenset({"tableHeader", "table_header", "antiek_table_header"})
_CELL_TYPES = _HEADER_CELL_TYPES | {"tableCell", "table_cell", "antiek_table_cell"}
_ROW_TYPES = frozenset({"tableRow", "table_row", "antiek_table_row"})


def _cell(node: dict[str, Any], ctx: Any, depth: int) -> str:
    tag = "th" if str(node.get("type", "")) in _HEADER_CELL_TYPES else "td"
    attrs = ""
    for name in ("colspan", "rowspan"):
        value = _int_attr(node, name)
        if value is not None and value > 1:
            attrs += f' {name}="{escape_attr(str(value))}"'
    scope = attr(node, "scope")
    if tag == "th" and scope in ("row", "col", "rowgroup", "colgroup"):
        attrs += f' scope="{escape_attr(scope)}"'
    return f"<{tag}{attrs}>{_tight_children(node.get('content'), ctx, depth + 1)}</{tag}>"


def render_table_at(node: dict[str, Any], ctx: Any, depth: int) -> str:
    """``table`` → a real ``<table>``, header row in ``<thead>``.

    The wrapper div carries the horizontal scroll so a wide source table
    cannot blow out the reading measure the style wheel sets."""
    rows = node.get("content")
    head: list[str] = []
    body: list[str] = []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict) or str(row.get("type", "")) not in _ROW_TYPES:
                body.append(f"<tr><td>{render_block_at(row, ctx, depth + 1)}</td></tr>")
                continue
            cells = row.get("content")
            cell_nodes = [c for c in cells if isinstance(c, dict)] if isinstance(cells, list) else []
            rendered = "".join(_cell(c, ctx, depth) for c in cell_nodes if str(c.get("type", "")) in _CELL_TYPES)
            # A cell of an unexpected type still renders, in its own td.
            rendered += "".join(
                f"<td>{render_block_at(c, ctx, depth + 1)}</td>"
                for c in cell_nodes
                if str(c.get("type", "")) not in _CELL_TYPES
            )
            marked = f"<tr>{rendered}</tr>"
            all_header = bool(cell_nodes) and all(
                str(c.get("type", "")) in _HEADER_CELL_TYPES for c in cell_nodes
            )
            (head if all_header and not body and not head else body).append(marked)
    out = ['<div class="antiek-table-wrap"><table class="antiek-table">']
    caption = attr(node, "caption")
    if caption:
        out.append(f"<caption>{escape_text(caption)}</caption>")
    if head:
        out.append(f"<thead>{''.join(head)}</thead>")
    if body:
        out.append(f"<tbody>{''.join(body)}</tbody>")
    out.append("</table></div>")
    return "".join(out)


__all__ = [
    "MAX_NEST",
    "render_block_at",
    "render_blockquote_at",
    "render_children",
    "render_list_at",
    "render_table_at",
]
