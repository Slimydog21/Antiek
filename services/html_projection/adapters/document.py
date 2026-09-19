"""Ingested-document adapter — sanitized reader HTML into a doc-model.

This is the join between the two halves of the HTML thesis. One half —
``services/html_projection/`` — renders a structured doc-model into
script-free HTML, applies a style from the forkable wheel, versions it and
can sign it into a ``.antiek`` container, but has only ever seen research
exports. The other half — an ingested PDF, web page or ``.docx`` — lands as
a flat sanitized HTML blob in the ``document_reader_html`` sidecar, with no
doc-model, no island, no style and no version. The style wheel therefore
could not reach the documents the operator actually ingests.

:func:`adapt_document_for_projection` parses that stored body back into the
TipTap-shaped doc-model the projection contract expects, at which point
every downstream property the export half already has — the island
round-trip, the wheel, the no-model-call restyle, the zero-script gate —
applies to an ingested document unchanged.

WHAT THE INPUT IS. The body has already been through
``substrate.books.html_sanitizer.sanitize_book_html``: its tags are a
subset of that module's ``ALLOWED_TAGS``, every image ``src`` has been
removed, and every active-content container is gone. That sanitizer is the
trust floor and stays the trust floor — this module parses, it does not
re-sanitize, and it mirrors the sanitizer's drop set so it can never render
more than the sanitizer would have kept. The parse is the stdlib
``HTMLParser``, the same tool and for the same reason: the repo declares no
HTML dependency and the sanitizer already proved the technique adequate for
exactly this content. (``_SanitizingParser`` itself reconstructs HTML from
parse events rather than building a tree, so it is the approach that is
reused here, not the class.)

THE RULE THAT SHAPES EVERYTHING ELSE. An unmapped construct renders
VISIBLY as unmapped. It is never quietly skipped and never flattened into
the surrounding prose. A reader has to be able to tell "the source had
nothing here" from "we lost it" — the moment those two look the same, the
reading surface stops being evidence of anything. So every tag the mapping
does not know becomes a ``source:<tag>`` node, which is by construction
outside the contract table and therefore renders through the contract's
unsupported fallback as ``unsupported block (source:dl)``. The node still
carries its text into the inert data island, so the round trip keeps what
the visible surface admits it could not draw.

WHAT IS DELIBERATELY LOSSY, AND WHY IT IS SAID OUT LOUD:

- Image bytes. The sanitizer strips every ``src`` before the body is
  stored, and the projection never emits an external ``<img src>`` anyway
  (the self-contained invariant, enforced by the zero-script gate). An
  image becomes an ``antiek_image`` node and renders as its alt text. The
  ``src`` is carried in the node's attrs when it is http(s) — the island
  keeps the reference even though the visible surface cannot fetch it.
- Decoration the renderer has no mark for. ``inline_text`` styles bold,
  italic, code and links; ``u``/``s``/``sub``/``sup``/``small``/``mark``
  emit their mark anyway and pass through undecorated. The TEXT always
  survives; only the decoration is dropped, and the mark survives in the
  island so a later renderer can honour it.
- Source CSS. Never imported, by design (see the spec's SPR-3 reasoning):
  the source owns structural character, the style wheel owns the reading
  frame.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit

from substrate.books.html_sanitizer import VOID_TAGS

# The stored sidecar is bounded to MAX_READER_HTML_CHARS (500k) at write
# time; this is the defensive ceiling for a caller that hands us something
# else. Truncation mid-tag is safe — the tree builder closes what is open.
MAX_ADAPT_CHARS: int = 1_000_000

# Mapping recursion bound. A doc-model is data and data can be hostile or
# merely pathological (a .docx of nothing but nested divs). Past the bound a
# subtree becomes one visible unmapped node rather than a RecursionError
# inside a request handler.
MAX_TREE_DEPTH: int = 24

# Mirrors substrate/books/html_sanitizer.py:87 _DROP_WITH_CONTENT. The
# sanitizer removes these subtrees wholesale, so in the normal path they
# cannot reach us; repeating the set means a caller who hands this function
# UNSANITIZED html still cannot get script or style text rendered as prose.
# The sanitizer remains the trust floor — this is a floor-consistency rule,
# not a second sanitizer.
_DROP_SUBTREE: frozenset[str] = frozenset({
    "script", "style", "noscript", "template", "iframe",
    "object", "embed", "applet", "svg", "math", "head", "title",
})

# Wrappers that carry no meaning of their own: their children are the
# content. ``html``/``body``/``main`` are here for the unsanitized-input
# case; the rest are in the sanitizer's ALLOWED_TAGS and do appear.
_TRANSPARENT: frozenset[str] = frozenset({
    "", "html", "body", "main", "header", "footer", "nav", "aside",
    "section", "article", "div", "figure", "hgroup",
})

# tag -> TipTap mark type. bold/italic/code/link are the four
# ``partials/_common.inline_text`` decorates; the rest pass through
# undecorated with their text intact (and their mark intact in the island).
_MARK_TAGS: dict[str, str] = {
    "strong": "bold",
    "b": "bold",
    "em": "italic",
    "i": "italic",
    "code": "code",
    "u": "underline",
    "s": "strike",
    "del": "strike",
    "strike": "strike",
    "ins": "insert",
    "sub": "subscript",
    "sup": "superscript",
    "small": "small",
    "mark": "highlight",
    "abbr": "abbr",
    "cite": "cite",
    "q": "quote",
}

# Inline tags handled without a mark of their own.
_INLINE_PASSTHROUGH: frozenset[str] = frozenset({"span", "a", "br", "wbr"})

_HEADINGS: dict[str, int] = {f"h{n}": n for n in range(1, 7)}

_WS_RE = re.compile(r"\s+")

# The URL policy of substrate/books/html_sanitizer.py (_ALLOWED_URL_SCHEMES
# + _safe_url), which remains the authority. It is repeated here because
# this function is public and a caller can reach it without having gone
# through that sanitizer, and because a rejected scheme must not reach the
# data island either.
_ALLOWED_URL_SCHEMES: frozenset[str] = frozenset({"http", "https"})
_URL_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def _safe_url(value: str) -> str:
    """The URL iff its scheme is http(s) or it has none, else ``""``."""
    cleaned = _URL_CONTROL_RE.sub("", value).strip()
    if not cleaned:
        return ""
    try:
        scheme = urlsplit(cleaned).scheme.lower()
    except ValueError:
        return ""
    if scheme and scheme not in _ALLOWED_URL_SCHEMES:
        return ""
    return cleaned


def _int_attr(el: _El, name: str) -> int | None:
    raw = el.attrs.get(name, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if 0 < value <= 1000 else None


# ── Tree building ──


class _El:
    """One parsed element: a tag, its attributes, and its children (each a
    child ``_El`` or a raw text ``str``)."""

    __slots__ = ("tag", "attrs", "children")

    def __init__(self, tag: str, attrs: dict[str, str]) -> None:
        self.tag = tag
        self.attrs = attrs
        self.children: list[_El | str] = []


class _TreeParser(HTMLParser):
    """Build an element tree from parse events.

    Malformed input cannot raise: a close tag with no matching open is
    ignored, and anything still open at EOF is closed by the caller reading
    the root. Comments, declarations and processing instructions are
    dropped, matching the sanitizer.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _El("", {})
        self._stack: list[_El] = [self.root]
        self._drop_stack: list[str] = []

    def _open(self, tag: str, attrs: list[tuple[str, str | None]]) -> _El:
        el = _El(tag, {k.lower(): (v or "") for k, v in attrs})
        self._stack[-1].children.append(el)
        return el

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in _DROP_SUBTREE:
            self._drop_stack.append(tag)
            return
        if self._drop_stack:
            return
        el = self._open(tag, attrs)
        if tag not in VOID_TAGS:
            self._stack.append(el)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in _DROP_SUBTREE or self._drop_stack:
            return
        self._open(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _DROP_SUBTREE:
            # Fail-closed, same posture as the sanitizer: pop only an exact
            # stack-top match, so a mismatched foreign close cannot
            # un-suppress a container that is still logically open.
            if self._drop_stack and self._drop_stack[-1] == tag:
                self._drop_stack.pop()
            return
        if self._drop_stack:
            return
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == tag:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if self._drop_stack:
            return
        self._stack[-1].children.append(data)


def _parse(html_body: str) -> _El:
    parser = _TreeParser()
    parser.feed(html_body[:MAX_ADAPT_CHARS])
    parser.close()
    return parser.root


# ── Text helpers ──


def _collapse(text: str) -> str:
    """HTML inline whitespace semantics: any run of whitespace is one space."""
    return _WS_RE.sub(" ", text)


def _raw_text(node: _El | str) -> str:
    """Every character of text under ``node``, verbatim. Used for ``<pre>``,
    where whitespace is content, and for an unmapped subtree's island copy."""
    if isinstance(node, str):
        return node
    return "".join(_raw_text(child) for child in node.children)


def _trim_run(run: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop a run that is only whitespace, and trim the outer edges of one
    that is not. Keeps the inter-block newlines of pretty-printed HTML from
    becoming empty paragraphs."""
    nodes = [n for n in run]
    while nodes and nodes[0].get("type") == "text" and not nodes[0]["text"].strip():
        nodes.pop(0)
    while nodes and nodes[-1].get("type") == "text" and not nodes[-1]["text"].strip():
        nodes.pop()
    if not nodes:
        return []
    first, last = nodes[0], nodes[-1]
    if first.get("type") == "text":
        first["text"] = first["text"].lstrip()
    if last.get("type") == "text":
        last["text"] = last["text"].rstrip()
    return [n for n in nodes if n.get("type") != "text" or n["text"]]


# ── Inline mapping ──


def _text_node(text: str, marks: list[dict[str, Any]]) -> dict[str, Any]:
    node: dict[str, Any] = {"type": "text", "text": text}
    if marks:
        node["marks"] = [dict(m) for m in marks]
    return node


def _inline(
    children: list[_El | str],
    marks: list[dict[str, Any]],
    blocks_out: list[dict[str, Any]],
    depth: int,
) -> list[dict[str, Any]]:
    """Flatten an inline subtree to TipTap inline nodes.

    A block-level element found inside inline content (the common case is an
    ``<img>`` inside a paragraph) is appended to ``blocks_out`` instead of
    being dropped — dropping it is exactly the silent loss this module
    exists to prevent."""
    out: list[dict[str, Any]] = []
    for child in children:
        if isinstance(child, str):
            text = _collapse(child)
            if text:
                out.append(_text_node(text, marks))
            continue
        tag = child.tag
        if tag == "br":
            out.append({"type": "hardBreak"})
            continue
        if tag == "a":
            href = _safe_url(child.attrs.get("href", ""))
            # A rejected scheme loses the LINK, never the text.
            link = [{"type": "link", "attrs": {"href": href}}] if href else []
            out.extend(_inline(child.children, marks + link, blocks_out, depth))
            continue
        if tag in _MARK_TAGS:
            mark = [{"type": _MARK_TAGS[tag]}]
            out.extend(_inline(child.children, marks + mark, blocks_out, depth))
            continue
        if tag in _INLINE_PASSTHROUGH or tag in _TRANSPARENT:
            out.extend(_inline(child.children, marks, blocks_out, depth))
            continue
        blocks_out.extend(_block(child, depth))
    return out


def _inline_of(el: _El, depth: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    trailing: list[dict[str, Any]] = []
    return _trim_run(_inline(el.children, [], trailing, depth)), trailing


# ── Block mapping ──


def _unmapped(el: _El) -> dict[str, Any]:
    """A construct the mapping does not know.

    The type is deliberately outside the contract table, so the renderer's
    unsupported fallback names it on the visible surface. The text rides
    along in ``content`` so the island keeps what the surface admits it
    could not draw."""
    text = _collapse(_raw_text(el)).strip()
    node: dict[str, Any] = {"type": f"source:{el.tag}", "attrs": {"tag": el.tag}}
    if text:
        node["content"] = [{"type": "text", "text": text}]
    return node


def _image(el: _El) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    alt = el.attrs.get("alt", "").strip()
    if alt:
        attrs["alt"] = alt
    src = _safe_url(el.attrs.get("src", ""))
    if src:
        # Carried for the island only. The projection never emits an
        # external <img src> — the gate forbids it and the partial renders
        # alt text — so this is a reference, not an asset.
        attrs["src"] = src
    title = el.attrs.get("title", "").strip()
    if title:
        attrs["caption"] = title
    return {"type": "antiek_image", "attrs": attrs}


def _list(el: _El, depth: int) -> dict[str, Any]:
    ordered = el.tag == "ol"
    attrs: dict[str, Any] = {}
    if ordered:
        start = _int_attr(el, "start")
        if start is not None and start != 1:
            attrs["start"] = start
    items: list[dict[str, Any]] = []
    for child in el.children:
        if isinstance(child, str):
            continue
        if child.tag == "li":
            items.append(
                {"type": "listItem", "content": _blocks(child.children, depth + 1)}
            )
            continue
        # A non-item inside a list still renders, in its own item.
        items.append({"type": "listItem", "content": _block(child, depth + 1)})
    node: dict[str, Any] = {
        "type": "orderedList" if ordered else "bulletList",
        "content": items,
    }
    if attrs:
        node["attrs"] = attrs
    return node


def _cell(el: _El, depth: int) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    for name in ("colspan", "rowspan"):
        value = _int_attr(el, name)
        if value is not None and value > 1:
            attrs[name] = value
    scope = el.attrs.get("scope", "").strip()
    if el.tag == "th" and scope:
        attrs["scope"] = scope
    node: dict[str, Any] = {
        "type": "tableHeader" if el.tag == "th" else "tableCell",
        "content": _blocks(el.children, depth + 1),
    }
    if attrs:
        node["attrs"] = attrs
    return node


def _row(el: _El, depth: int) -> dict[str, Any]:
    cells: list[dict[str, Any]] = []
    for child in el.children:
        if isinstance(child, str):
            if child.strip():
                cells.append(
                    {
                        "type": "tableCell",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": _collapse(child).strip()}],
                            }
                        ],
                    }
                )
            continue
        if child.tag in ("th", "td"):
            cells.append(_cell(child, depth))
        else:
            cells.append({"type": "tableCell", "content": _block(child, depth + 1)})
    return {"type": "tableRow", "content": cells}


def _table(el: _El, depth: int) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    caption = ""

    def walk(node: _El) -> None:
        nonlocal caption
        for child in node.children:
            if isinstance(child, str):
                continue
            if child.tag in ("thead", "tbody", "tfoot"):
                walk(child)
            elif child.tag == "tr":
                rows.append(_row(child, depth))
            elif child.tag == "caption":
                caption = _collapse(_raw_text(child)).strip()

    walk(el)
    node: dict[str, Any] = {"type": "table", "content": rows}
    if caption:
        node["attrs"] = {"caption": caption}
    return node


def _block(el: _El, depth: int) -> list[dict[str, Any]]:
    """Map one element to zero or more doc-model block nodes."""
    if depth >= MAX_TREE_DEPTH:
        return [_unmapped(el)]
    tag = el.tag
    if tag in _DROP_SUBTREE:
        return []  # unreachable through _parse; kept so the rule is local
    if tag in _TRANSPARENT:
        return _blocks(el.children, depth + 1)
    if tag in _HEADINGS:
        content, trailing = _inline_of(el, depth)
        node = {"type": "heading", "attrs": {"level": _HEADINGS[tag]}, "content": content}
        return [node, *trailing]
    if tag == "p":
        # Routed back through _blocks so an <img> mid-paragraph splits the
        # paragraph IN PLACE rather than being appended after it.
        return _blocks(el.children, depth + 1)
    if tag == "hr":
        return [{"type": "horizontalRule"}]
    if tag in ("ul", "ol"):
        return [_list(el, depth)]
    if tag == "li":
        # A stray item outside a list: keep it as a one-item list.
        return [{"type": "bulletList", "content": [
            {"type": "listItem", "content": _blocks(el.children, depth + 1)}
        ]}]
    if tag == "blockquote":
        return [{"type": "blockquote", "content": _blocks(el.children, depth + 1)}]
    if tag == "pre":
        return [{
            "type": "codeBlock",
            "content": [{"type": "text", "text": _raw_text(el)}],
        }]
    if tag == "table":
        return [_table(el, depth)]
    if tag == "img":
        return [_image(el)]
    if tag in ("figcaption", "caption"):
        content, trailing = _inline_of(el, depth)
        if not content and not trailing:
            return []
        return [{"type": "paragraph", "attrs": {"role": tag}, "content": content}, *trailing]
    if tag in ("tr", "td", "th", "thead", "tbody", "tfoot"):
        # Table parts reached outside a table: render their content rather
        # than the grid they are missing.
        return _blocks(el.children, depth + 1)
    return [_unmapped(el)]


def _blocks(children: list[_El | str], depth: int) -> list[dict[str, Any]]:
    """Map a run of children to block nodes, gathering inline runs into
    paragraphs in document order."""
    if depth >= MAX_TREE_DEPTH:
        text = _collapse("".join(_raw_text(c) for c in children)).strip()
        return [{"type": "paragraph", "content": [{"type": "text", "text": text}]}] if text else []
    out: list[dict[str, Any]] = []
    run: list[dict[str, Any]] = []
    trailing: list[dict[str, Any]] = []

    def flush() -> None:
        nodes = _trim_run(run)
        run.clear()
        if nodes:
            out.append({"type": "paragraph", "content": nodes})
        if trailing:
            out.extend(trailing)
            trailing.clear()

    for child in children:
        if isinstance(child, str):
            text = _collapse(child)
            if text:
                run.append({"type": "text", "text": text})
            continue
        tag = child.tag
        if tag == "br" or tag == "a" or tag in _MARK_TAGS or tag in _INLINE_PASSTHROUGH:
            run.extend(_inline([child], [], trailing, depth))
            continue
        flush()
        out.extend(_block(child, depth))
    flush()
    return out


# ── The adapter ──


def adapt_document_for_projection(
    document_id: str,
    html_body: str,
    source_kind: str,
    source_url: str | None = None,
    *,
    title: str | None = None,
) -> dict[str, Any]:
    """Parse a stored sanitized document body into a projection doc-model.

    Parameters
    ----------
    document_id:
        The substrate document this body belongs to. Carried in the
        doc-model's ``source`` block so the island names its own origin even
        after the artifact has left Antiek.
    html_body:
        The sanitized reader-HTML sidecar body
        (``substrate.reader_html.store.serve_reader_html``). Already through
        ``sanitize_book_html``; this function parses, it does not sanitize.
    source_kind:
        ``url`` / ``upload`` / ``book`` — the sidecar's own ``source_kind``.
    source_url:
        Where the document came from, when there is one.
    title:
        The document's title, if the caller has one. The renderer emits it
        as the artifact's ``<h1>``; source headings keep their own levels
        alongside it (see ``partials/heading.py`` for why they are not
        demoted).

    Returns
    -------
    dict
        A doc-model ready for ``render(doc_model, ctx, style=...)``. It
        round-trips through the data island unchanged, so every style on the
        wheel re-renders it with no model call.
    """
    tree = _parse(html_body or "")
    return {
        "title": title,
        "content": _blocks(tree.children, 0),
        "source": {
            "document_id": document_id,
            "source_kind": source_kind,
            "source_url": source_url,
        },
    }


__all__ = ["MAX_ADAPT_CHARS", "MAX_TREE_DEPTH", "adapt_document_for_projection"]
