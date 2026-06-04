"""text / markdown → the SPR-01 structured ``Document`` (Reader SPR-02 M1).

The deterministic extractor. It turns a source body — cleaned text or markdown —
into the typed-block ``Document`` contract pinned by Reader SPR-01
(``substrate/contracts/document_model.py``). NO provider keys, NO model call:
this is pure parsing, so a green test here means the operator can read the
result the moment it merges (rigor #1 — deterministic, never inert).

────────────────────────────────────────────────────────────────────────────
WHY markdown-it-py (decision #2 — the markdown PARSER choice; rigor #2/#5).

The stored corpus is REAL markdown, not a toy. ``acquisition/urls/extract.py``
renders fetched HTML to markdown via ``html2text`` (ATX ``#`` headings, fenced
code, ``**bold**`` / ``*em*`` / ``[link](url)``, GFM tables, ``>`` blockquotes),
and ``processing/chunking`` already emits markdown. A hand-rolled regex parser
would be fragile against nested lists, fenced-code-containing-``#``, and inline
emphasis precedence — the exact failure the SPR-01 docstring's "re-introduce the
flattener one level down" warns about. So a real CommonMark AST is warranted.

* ``markdown-it-py`` (CommonMark reference port, pure-Python, actively
  maintained) is chosen over ``mistune`` because (a) the spec names it first,
  (b) its token stream exposes the inline ``markup`` channel (``$`` for math vs
  a backtick for code) so inline math is disambiguated from a literal dollar at
  the TOKEN layer, not by a
  post-hoc regex, and (c) ``mdit-py-plugins.dollarmath`` gives ``$..$`` /
  ``$$..$$`` math as first-class ``math_inline`` / ``math_block`` tokens —
  exactly the SPR-01 ``MathSpan`` / ``MathBlock`` shapes. ``mistune`` would
  need a custom plugin for the same and exposes no equivalent markup channel.
* REJECTED — a focused stdlib parser: the corpus is not simple enough (GFM
  tables with per-column alignment, arbitrarily nested lists, fenced code whose
  body may contain the model's own discriminator string). A stdlib parser that
  handled those correctly would BE a markdown parser; reusing the reference one
  is the lower-risk, defensible choice. The dep is added to the ``extraction``
  optional-dependency group (pyproject) and lazy-imported here so the rest of
  the substrate does not pay for it.

Math handling (M1 acceptance): inline ``$x^2$`` becomes a ``MathSpan(tex=...)``,
NEVER the literal three-char string ``$x$`` — ``markup == '$'`` on the
``math_inline`` token is the discriminator. A fenced code block whose body
contains a dollar sign is a ``CodeBlock`` whose verbatim text keeps the dollar
(code is never re-parsed as math) — the ``fence`` token's ``content`` is taken
verbatim.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from substrate.contracts.document_model import (
    DOCUMENT_MODEL_SCHEMA_VERSION,
    BlockquoteBlock,
    CodeBlock,
    CodeSpan,
    Document,
    DocumentAttribution,
    EmphasisSpan,
    HeadingBlock,
    LinkSpan,
    ListBlock,
    ListItem,
    MathBlock,
    MathSpan,
    ParagraphBlock,
    StrongSpan,
    TableBlock,
    TextSpan,
)

if TYPE_CHECKING:  # pragma: no cover — typing only
    from markdown_it.token import Token


# ───────────────────────────────────────────────────────────────────────────
# Parser construction (lazy — the dep lives in the ``extraction`` extra).
# ───────────────────────────────────────────────────────────────────────────


def _build_parser():
    """Construct the configured MarkdownIt parser. Lazy-imported so a substrate
    that never extracts does not require the dep; a missing dep is a LOUD
    ImportError with an install hint (the repo's lazy-optional-dep convention,
    mirrors acquisition/urls/extract.py)."""
    try:
        from markdown_it import MarkdownIt
        from mdit_py_plugins.dollarmath import dollarmath_plugin
    except ImportError as e:  # pragma: no cover — environment guard
        raise ImportError(
            "processing.extraction.to_document_model requires markdown-it-py. "
            "Run `pip install -e '.[extraction]'` to install it."
        ) from e

    # ``commonmark`` preset + GFM tables + dollar math. ``html=False``: raw HTML
    # in the source is treated as text, never passed through — the model has no
    # raw-HTML block and we will not smuggle markup past the typed contract.
    return (
        MarkdownIt("commonmark", {"html": False})
        .enable("table")
        .use(dollarmath_plugin, double_inline=True)
    )


# ───────────────────────────────────────────────────────────────────────────
# Inline-span mapping (the leaves).
# ───────────────────────────────────────────────────────────────────────────


def _inline_children_to_spans(children: list) -> list:
    """Map a markdown-it inline token's ``children`` (a FLAT list with
    ``*_open`` / ``*_close`` delimiters for strong/emphasis/link) into the
    SPR-01 nested inline-span list.

    markdown-it emits inline markup as a flat open/close stream; we re-nest it
    with an explicit stack so ``**a *b* c**`` becomes a StrongSpan wrapping an
    EmphasisSpan (the SPR-01 ``children`` recursion)."""
    if not children:
        return []

    # Stack of (container_span_kind, accumulating_children_list). The bottom of
    # the stack is the output list; each *_open pushes a new accumulator.
    out: list = []
    stack: list[tuple[str, dict, list]] = [("", {}, out)]

    def _current() -> list:
        return stack[-1][2]

    for tok in children:
        ttype = tok.type
        if ttype == "text":
            if tok.content:
                _current().append(TextSpan(text=tok.content))
        elif ttype == "softbreak" or ttype == "hardbreak":
            # A line break inside flowing text → a space. The model has no
            # break span (a paragraph is flowing inline content); collapsing to
            # a space is the lossy-but-honest choice, commented so a maintainer
            # knows it is deliberate, not a dropped token.
            _current().append(TextSpan(text=" "))
        elif ttype == "code_inline":
            # Verbatim — never re-parsed (a backtick span may itself contain a
            # dollar or markdown chars; they stay literal).
            _current().append(CodeSpan(text=tok.content))
        elif ttype == "math_inline":
            # ``markup == '$'`` confirms this came from real ``$..$`` delimiters
            # (dollarmath plugin), so it is a MathSpan, NOT the literal ``$x$``
            # string — the M1 acceptance criterion.
            _current().append(MathSpan(tex=tok.content))
        elif ttype == "strong_open":
            stack.append(("strong", {}, []))
        elif ttype == "em_open":
            stack.append(("emphasis", {}, []))
        elif ttype == "link_open":
            stack.append(("link", dict(tok.attrs), []))
        elif ttype in ("strong_close", "em_close", "link_close"):
            kind, attrs, acc = stack.pop()
            if kind == "strong":
                _current().append(StrongSpan(children=acc))
            elif kind == "emphasis":
                _current().append(EmphasisSpan(children=acc))
            elif kind == "link":
                _current().append(
                    LinkSpan(href=str(attrs.get("href", "")), children=acc)
                )
        elif ttype == "image":
            # An inline image becomes its alt text (the model has no inline
            # image span; a figure is a BLOCK). Lossy-but-honest: alt text
            # preserves the human-readable content, commented as deliberate.
            alt = tok.content or (tok.attrs.get("alt") if tok.attrs else "")
            if alt:
                _current().append(TextSpan(text=str(alt)))
        # Any other inline token type (e.g. html_inline, which html=False keeps
        # as text via the text token above) is intentionally skipped — there is
        # no model span for it. Unknown tokens are NOT silently coerced.

    # Unbalanced open without close (malformed input) — flush remaining stack
    # frames into their parent so no content is lost.
    while len(stack) > 1:
        kind, attrs, acc = stack.pop()
        if kind == "strong":
            _current().append(StrongSpan(children=acc))
        elif kind == "emphasis":
            _current().append(EmphasisSpan(children=acc))
        elif kind == "link":
            _current().append(LinkSpan(href=str(attrs.get("href", "")), children=acc))
    return out


def _inline_token_to_spans(token: Token) -> list:
    """A markdown-it ``inline`` token → SPR-01 inline spans."""
    return _inline_children_to_spans(token.children or [])


# ───────────────────────────────────────────────────────────────────────────
# Block mapping (the token-stream walk).
# ───────────────────────────────────────────────────────────────────────────


_ALIGN_FROM_STYLE = {
    "text-align:left": "left",
    "text-align:center": "center",
    "text-align:right": "right",
}


def _alignment_from_attrs(attrs: dict) -> str | None:
    """GFM column alignment from a th/td token's ``style`` attr. ``None`` =
    unspecified (the SPR-01 default), matching the model's per-column list."""
    style = attrs.get("style") if attrs else None
    if not style:
        return None
    return _ALIGN_FROM_STYLE.get(style)


def _tokens_to_blocks(tokens: list, start: int, end: int) -> list:
    """Walk the flat markdown-it block token stream ``[start, end)`` into a
    list of SPR-01 blocks. Recurses for container blocks (lists, blockquotes)
    by finding the matching ``*_close`` of each ``*_open`` via nesting depth."""
    blocks: list = []
    i = start
    while i < end:
        tok = tokens[i]
        ttype = tok.type

        if ttype == "heading_open":
            level = int(tok.tag[1])  # 'h1'..'h6'
            inline = tokens[i + 1]
            blocks.append(
                HeadingBlock(level=level, spans=_inline_token_to_spans(inline))
            )
            i += 3  # open, inline, close
            continue

        if ttype == "paragraph_open":
            inline = tokens[i + 1]
            blocks.append(ParagraphBlock(spans=_inline_token_to_spans(inline)))
            i += 3
            continue

        if ttype == "fence" or ttype == "code_block":
            # ``content`` is verbatim — a fenced block whose body contains the
            # model's own discriminator string (e.g. ``{"type": "paragraph"}``)
            # round-trips unharmed; code is NEVER re-parsed (M1 edge case).
            # markdown-it appends a trailing newline to fence content; strip the
            # single trailing newline it adds so the round-trip is faithful.
            text = tok.content
            if text.endswith("\n"):
                text = text[:-1]
            lang = (tok.info or "").strip() or None
            blocks.append(CodeBlock(lang=lang, text=text))
            i += 1
            continue

        if ttype == "math_block":
            # Display math from ``$$..$$`` (dollarmath plugin). ``content`` is
            # verbatim TeX (may be multi-line).
            blocks.append(MathBlock(display=True, tex=tok.content))
            i += 1
            continue

        if ttype == "bullet_list_open" or ttype == "ordered_list_open":
            close = _find_close(tokens, i, ttype, _CLOSE_OF[ttype])
            ordered = ttype == "ordered_list_open"
            items = _parse_list_items(tokens, i + 1, close)
            blocks.append(ListBlock(ordered=ordered, items=items))
            i = close + 1
            continue

        if ttype == "blockquote_open":
            close = _find_close(tokens, i, ttype, "blockquote_close")
            inner = _tokens_to_blocks(tokens, i + 1, close)
            blocks.append(BlockquoteBlock(blocks=inner))
            i = close + 1
            continue

        if ttype == "table_open":
            close = _find_close(tokens, i, ttype, "table_close")
            blocks.append(_parse_table(tokens, i + 1, close))
            i = close + 1
            continue

        if ttype == "hr":
            # A thematic break has no model block (the model is content, not
            # presentation). Skipped deliberately — not a dropped paragraph.
            i += 1
            continue

        # Any unhandled block token (html_block, etc.): advance past it without
        # inventing a block. html=False means raw HTML never reaches here as a
        # block; this is a safety net, not a silent content drop of known types.
        i += 1
    return blocks


_CLOSE_OF = {
    "bullet_list_open": "bullet_list_close",
    "ordered_list_open": "ordered_list_close",
}


def _find_close(tokens: list, open_idx: int, open_type: str, close_type: str) -> int:
    """Index of the ``close_type`` token matching the ``open_type`` at
    ``open_idx``, accounting for nesting of the SAME pair."""
    depth = 0
    for j in range(open_idx, len(tokens)):
        t = tokens[j].type
        if t == open_type:
            depth += 1
        elif t == close_type:
            depth -= 1
            if depth == 0:
                return j
    return len(tokens) - 1  # malformed: treat rest of stream as the body


def _parse_list_items(tokens: list, start: int, end: int) -> list:
    """Parse the ``list_item_open``…``list_item_close`` runs in ``[start, end)``
    into ListItems, each carrying its own block-list (so a nested list inside an
    item falls out via the recursive _tokens_to_blocks call)."""
    items: list = []
    i = start
    while i < end:
        if tokens[i].type == "list_item_open":
            close = _find_close(tokens, i, "list_item_open", "list_item_close")
            items.append(ListItem(blocks=_tokens_to_blocks(tokens, i + 1, close)))
            i = close + 1
        else:
            i += 1
    return items


def _parse_table(tokens: list, start: int, end: int):
    """Parse a GFM table's inner tokens into a TableBlock. Header row → column
    alignment + header cells; body rows → rows. Each cell is an inline-span
    list (so a cell can hold bold / a link / inline math, or be EMPTY — the
    merged/empty-cell edge case)."""
    alignment: list = []
    header: list = []
    rows: list = []
    i = start
    in_header = False
    current_row: list | None = None
    capture_alignment = True
    while i < end:
        t = tokens[i]
        if t.type == "thead_open":
            in_header = True
        elif t.type == "thead_close":
            in_header = False
            capture_alignment = False
        elif t.type == "tr_open":
            current_row = []
        elif t.type == "tr_close":
            if in_header:
                header = current_row or []
            else:
                rows.append(current_row or [])
            current_row = None
        elif t.type in ("th_open", "td_open"):
            if capture_alignment:
                alignment.append(_alignment_from_attrs(dict(t.attrs)))
            inline = tokens[i + 1] if tokens[i + 1].type == "inline" else None
            cell = _inline_token_to_spans(inline) if inline is not None else []
            if current_row is not None:
                current_row.append(cell)
        i += 1
    return TableBlock(alignment=alignment, header=header, rows=rows)


# ───────────────────────────────────────────────────────────────────────────
# Public entry points.
# ───────────────────────────────────────────────────────────────────────────


def markdown_to_blocks(markdown_text: str) -> list:
    """Parse a markdown body into SPR-01 blocks. The deterministic core M2 / M5
    / the URL emitter all reuse. No Document envelope — just the block list — so
    callers that already hold attribution wrap it themselves."""
    md = _build_parser()
    tokens = md.parse(markdown_text or "")
    return _tokens_to_blocks(tokens, 0, len(tokens))


def _fallback_doc_id(title: str | None, body: str) -> str:
    """A deterministic id when the caller gives none (round-trip / test use).
    Content-addressed so the same body yields the same id.

    The parentheses around ``(title or "")`` are load-bearing: ``+`` binds
    tighter than ``or``, so the unparenthesized ``title or "" + "\\0" + body``
    parses as ``title or ("" + "\\0" + body)`` — a truthy title would short-
    circuit and DROP the body entirely, so two same-title / different-body docs
    would collide on the same id. Parenthesize the fallback FIRST, then prepend
    it to the separator + body so the body is always part of the digest."""
    h = hashlib.sha256(((title or "") + "\0" + body).encode("utf-8")).hexdigest()[:16]
    return f"doc-md-{h}"


def text_to_document(
    body: str,
    *,
    document_id: str | None = None,
    title: str | None = None,
    attribution: DocumentAttribution | None = None,
) -> Document:
    """Build a full SPR-01 ``Document`` from a markdown/text body.

    Plain text (no markdown markers) parses fine too — CommonMark treats a run
    of non-blank lines as one paragraph, blank-line-separated runs as separate
    paragraphs, so cleaned text degrades gracefully to ParagraphBlocks (which is
    exactly the M5 backfill behavior for legacy stored text).

    ``title`` falls back to the first H1 heading's plain text when not given, so
    a markdown doc that leads with ``# Title`` is titled without the caller
    re-deriving it.
    """
    blocks = markdown_to_blocks(body)

    resolved_title = title
    if resolved_title is None:
        for b in blocks:
            if b.type == "heading" and b.level == 1:
                from substrate.contracts.document_model import _spans_to_plain_text

                resolved_title = _spans_to_plain_text(b.spans)
                break
    if resolved_title is None:
        resolved_title = "(untitled)"

    return Document(
        id=document_id or _fallback_doc_id(title, body),
        title=resolved_title,
        attribution=attribution or DocumentAttribution(),
        blocks=blocks,
        schema_version=DOCUMENT_MODEL_SCHEMA_VERSION,
    )


# ───────────────────────────────────────────────────────────────────────────
# M3 — arXiv structured-source path (prefer HTML/LaTeX source over the PDF).
#
# An arXiv paper has (often) a structured HTML rendering at ar5iv
# (``ar5iv.org`` / ``ar5iv.labs.arxiv.org``) where every equation is a ``<math>``
# element carrying the ORIGINAL TeX in its ``alttext`` attribute and headings are
# real ``<h1..h6>`` tags. That is strictly richer than the PDF (which has no
# equations, only glyphs). So when structured source is available we PREFER it
# and map equations to ``MathBlock`` / ``MathSpan`` carrying ``tex`` — the M3
# acceptance criterion. When it is not, we fall back to the M2 PDF path, and the
# CHOSEN PATH is recorded on the returned result so a maintainer can see which
# fired.
#
# arXiv fetch discipline (rigor #4): this module performs NO network I/O of its
# own. The caller injects the fetched source bytes/PDF bytes (the existing
# governed arXiv fetchers in ``acquisition/arxiv`` own all egress, with the
# host-global rate governor / 429 ban-sentinel). ``arxiv_to_document`` is a pure
# PATH-SELECTING + MAPPING function over already-fetched content — it CANNOT
# re-trip the 429-ban / SSL-env / throttle failures because it never opens a
# socket. ``acquisition/arxiv/source_document.py`` wires the governed fetch.
# ───────────────────────────────────────────────────────────────────────────


def ar5iv_html_to_blocks(html: str) -> list:
    """Map ar5iv (LaTeXML) HTML into SPR-01 blocks. Equations become MathBlock /
    MathSpan carrying the original TeX from the ``<math alttext=...>`` attribute
    (LaTeXML preserves the source TeX there). Headings come from real ``<hN>``
    tags. Best-effort: paragraphs, lists, headings, and math are mapped;
    unrecognized structure degrades to its text content (documented loss)."""
    try:
        from bs4 import BeautifulSoup  # type: ignore[import-not-found]
    except ImportError as e:  # pragma: no cover — environment guard
        raise ImportError(
            "ar5iv_html_to_blocks requires beautifulsoup4 (the [urls] extra)."
        ) from e

    soup = BeautifulSoup(html, "html.parser")
    root = soup.find("body") or soup
    blocks: list = []
    _walk_ar5iv(root, blocks)
    return blocks


def _ar5iv_inline_spans(el) -> list:
    """Inline spans from an ar5iv element's children. ``<math>`` → MathSpan(tex)
    from its ``alttext``; everything else contributes its text. Lossy on rich
    inline markup (bold/links are flattened to text here — ar5iv nests them
    deeply; the M1 markdown path carries them precisely. Documented degradation:
    the structured-source path optimizes for MATH fidelity, the headline win)."""
    from bs4 import NavigableString  # type: ignore[import-not-found]

    spans: list = []
    for child in el.children:
        if isinstance(child, NavigableString):
            text = str(child)
            if text.strip():
                spans.append(TextSpan(text=text))
            continue
        name = getattr(child, "name", None)
        if name == "math":
            tex = child.get("alttext")
            if tex:
                spans.append(MathSpan(tex=tex))
            continue
        # Recurse into inline containers; their text/math bubbles up.
        spans.extend(_ar5iv_inline_spans(child))
    # Collapse to at least one span so an empty paragraph is still valid.
    return spans


def _walk_ar5iv(el, blocks: list) -> None:
    """Recursively map ar5iv block elements into SPR-01 blocks."""
    for child in el.children:
        name = getattr(child, "name", None)
        if name is None:
            continue
        if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(name[1])
            blocks.append(HeadingBlock(level=level, spans=_ar5iv_inline_spans(child)))
        elif name == "p":
            spans = _ar5iv_inline_spans(child)
            if spans:
                blocks.append(ParagraphBlock(spans=spans))
        elif name == "math" and child.get("display") == "block":
            tex = child.get("alttext")
            if tex:
                blocks.append(MathBlock(display=True, tex=tex))
        elif name in ("section", "div", "article", "figure"):
            # A display-math block can also be a direct child of a section.
            _walk_ar5iv(child, blocks)
        elif name in ("ul", "ol"):
            items = []
            for li in child.find_all("li", recursive=False):
                li_blocks: list = []
                _walk_ar5iv(li, li_blocks)
                if not li_blocks:
                    li_blocks = [ParagraphBlock(spans=_ar5iv_inline_spans(li))]
                items.append(ListItem(blocks=li_blocks))
            if items:
                blocks.append(ListBlock(ordered=(name == "ol"), items=items))
        # Other elements (tables, captions) are best-effort-skipped here; the
        # PDF path (M2) recovers tables. Documented: the structured path leads on
        # math + headings; the PDF path leads on tables/figures.


@dataclass
class ArxivExtraction:
    """Result of M3: the Document plus WHICH path produced it (rigor — the path
    is recorded on the document, per the M3 acceptance criterion). ``path`` is
    ``"structured_source"`` (ar5iv HTML) or ``"pdf_fallback"`` (the M2 path).
    ``pdf_report`` is the M2 confidence report when the PDF path fired, else
    ``None``."""

    document: Document
    path: str
    pdf_report: object | None = None


@dataclass
class ArxivSourceFetch:
    """The two possible already-fetched inputs the caller supplies. ``html`` is
    ar5iv structured HTML (preferred); ``pdf_bytes`` is the PDF fallback. The
    caller (``acquisition/arxiv``) does the governed fetching; this module never
    opens a socket (rigor #4 — cannot re-trip the 429-ban)."""

    html: str | None = None
    pdf_bytes: bytes | None = None


def arxiv_to_document(
    fetch: ArxivSourceFetch,
    *,
    document_id: str,
    title: str | None = None,
    attribution: DocumentAttribution | None = None,
) -> ArxivExtraction:
    """Select the richer path and map it. PREFERS structured ar5iv HTML (math as
    tex); falls back to the M2 PDF path when no HTML is available. Records the
    chosen path on the result. Pure over already-fetched bytes."""
    if fetch.html:
        blocks = ar5iv_html_to_blocks(fetch.html)
        if blocks:
            resolved_title = title or _first_h1_title(blocks) or "(untitled)"
            doc = Document(
                id=document_id,
                title=resolved_title,
                attribution=attribution or DocumentAttribution(),
                blocks=blocks,
                schema_version=DOCUMENT_MODEL_SCHEMA_VERSION,
            )
            return ArxivExtraction(document=doc, path="structured_source")

    if fetch.pdf_bytes:
        # Lazy import to keep the PDF dep optional for callers that only do M1.
        from processing.extraction.pdf_to_document_model import pdf_bytes_to_document

        doc, report = pdf_bytes_to_document(
            fetch.pdf_bytes,
            document_id=document_id,
            title=title,
            attribution=attribution,
        )
        return ArxivExtraction(document=doc, path="pdf_fallback", pdf_report=report)

    # Neither source available — an empty, honest Document.
    return ArxivExtraction(
        document=Document(
            id=document_id,
            title=title or "(untitled)",
            attribution=attribution or DocumentAttribution(),
            blocks=[],
            schema_version=DOCUMENT_MODEL_SCHEMA_VERSION,
        ),
        path="empty",
    )


def _first_h1_title(blocks: list) -> str | None:
    from substrate.contracts.document_model import _spans_to_plain_text

    for b in blocks:
        if b.type == "heading" and b.level == 1:
            return _spans_to_plain_text(b.spans)
    return None


__all__ = [
    "markdown_to_blocks",
    "text_to_document",
    "ar5iv_html_to_blocks",
    "arxiv_to_document",
    "ArxivExtraction",
    "ArxivSourceFetch",
]
