"""The structured document model — the typed-block reading spine (Reader SPR-01).

Owned by **antiek-reader SPR-01** (The Unified Reader). This is the canonical
data contract every ingest path emits (SPR-02), the one ``<Reader>`` renders
(SPR-03), and the shape ``openDocument`` resolves to (SPR-05). It replaces the
flattened-text storage decision diagnosed at
``apps/reading/src/components/reader/ReadingColumn.tsx:60`` ("the served body is
already cleaned text, not rich markup") — the model that makes "fun to read"
possible because a paragraph is a ``ParagraphBlock``, a table is a
``TableBlock``, and a citation is a first-class ``CitationSpan``, not a footnote
hack or a literal ``[link](url)`` string.

────────────────────────────────────────────────────────────────────────────
WHY THIS SHAPE — the rejected alternatives (rigor #5; the answer lives here,
not in a chat).

* **citation as a first-class inline span, NOT a footnote and NOT a link.**
  A citation carries ``source_document_id`` + ``chunk_id`` + a char range into
  the *source* document — exactly the triple the graph already attributes
  evidence on (``substrate/graph/ops.py`` ``insert_edge``'s
  ``source_document_id`` / ``chunk_id``; the ``ProvenanceLink`` contract in
  ``nodes.py``). A footnote (``[1]`` → a ``FootnoteBlock``) is a *reading
  convenience* that points elsewhere in the SAME document; a link
  (``LinkSpan``) points at a URL or another Antiek document for navigation.
  A citation is neither: it is the provenance edge made renderable, so clicking
  it opens the real source in the one Reader (SPR-07's provenance close). If
  citation were a footnote we could not carry the source char range; if it were
  a link we could not carry the chunk_id the §9.0 gate keys on. So it is its
  own span. *Reversal:* if SPR-02 finds no real extraction can recover a
  source char range, ``char_start``/``char_end`` degrade to optional (already
  modeled below) without collapsing citation into a different type.

* **list items are block-lists, NOT strings.** A list item can contain a
  paragraph, a nested list, even a code block (a numbered procedure with code
  steps). Modeling an item as ``list[Block]`` makes nesting and rich item
  content fall out for free; modeling it as ``str`` would re-introduce the
  flattener one level down. *Rejected:* ``items: list[str]``.

* **table cells are inline-span lists, NOT strings.** A cell can hold bold
  text, a citation, inline math. ``alignment`` is per-column (``left`` /
  ``center`` / ``right`` / ``None`` = unspecified) so a real GFM/LaTeX table
  round-trips. *Rejected:* ``cells: list[list[str]]``.

* **the ToC is DERIVED from heading blocks, never stored.** Storing it twice
  invites the two copies to drift (the exact failure ``servable.py`` and
  ``emit_types.py`` both guard against with derive-don't-duplicate). ``toc()``
  walks the blocks; there is no ``toc`` field. *Rejected:* ``toc: list[...]``.

* **``schema_version`` is carried on the Document, not inferred.** A document
  persisted under v1 must be readable after the model evolves; the version is
  the migration handle. Mirrors ``EVENT_SCHEMA_VERSION`` /
  ``CONTRACT_SCHEMA_VERSION``.

────────────────────────────────────────────────────────────────────────────
REUSE, NOT SYNONYMS (rigor #4; diligence done against the live tree).

* ``content_class`` on ``DocumentAttribution`` is typed against
  ``substrate.contracts.servable.ContentClass`` — the §9.0 servability
  vocabulary, single-owned by ``servable.py`` (which mirrors the classifier).
  This model RECORDS the class; it never re-derives deny-by-default.
* ``source_document_id`` + ``chunk_id`` on ``CitationSpan`` are the SAME names
  the graph edge vocabulary uses (``ops.py`` ``insert_edge``;
  ``ProvenanceLink`` in ``nodes.py``) — not ``doc_id`` / ``source_chunk``.
* ``ip_holder_id`` / ``source_url`` mirror the ``insert_document`` /
  ``ServableEntryContract`` columns. Every document carries an
  ``ip_holder_id`` "even if null" (the provenance-chain invariant, CLAUDE.md).

ASSUMPTIONS (rigor #1 — what is pinned vs what SPR-02 must confirm against a
real arXiv extraction):

* ``FigureBlock.src`` / ``alt`` and ``MathBlock`` multi-line tex are pinned as
  *optional where a real extraction may not recover them* (``alt`` text and a
  resolvable ``src`` are frequently absent from a raw PDF). Marked optional with
  this note rather than invented-as-required. SPR-02 confirms or tightens.
* ``CitationSpan.char_start`` / ``char_end`` are optional for the same reason
  (a citation marker may be recoverable without a precise source char range).
* No multi-column / float-positioning model. Out of scope for the keystone; a
  real two-column arXiv paper linearizes to a single block stream. If SPR-02
  needs column provenance it is an additive field, not a re-cut.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from .servable import ContentClass

# Bump on ANY change to a block/span field shape. Mirrors
# ``EVENT_SCHEMA_VERSION`` / ``CONTRACT_SCHEMA_VERSION``; it is the migration
# handle for documents persisted under an older model.
DOCUMENT_MODEL_SCHEMA_VERSION: int = 1


# ───────────────────────────────────────────────────────────────────────────
# Inline spans — the leaves of block content.
#
# Discriminated on ``type``. ``citation`` is first-class (see module docstring).
# ───────────────────────────────────────────────────────────────────────────


class _SpanBase(BaseModel):
    # ``extra="forbid"`` so an unknown field is a loud failure, not a silent
    # drop — the exact discipline the contracts package uses everywhere.
    model_config = ConfigDict(extra="forbid")


class TextSpan(_SpanBase):
    """Plain text. The only span carrying no markup."""

    type: Literal["text"] = "text"
    text: str


class StrongSpan(_SpanBase):
    """Bold. ``children`` so ``**a *b* c**`` (strong wrapping emphasis) nests."""

    type: Literal["strong"] = "strong"
    children: list[InlineSpan]


class EmphasisSpan(_SpanBase):
    """Italic. ``children`` for nested inline markup (same reason as strong)."""

    type: Literal["emphasis"] = "emphasis"
    children: list[InlineSpan]


class LinkSpan(_SpanBase):
    """A hyperlink. ``href`` is the external/anchor target; the OPTIONAL
    ``internal_document_id`` names an in-Antiek document so the Reader can open
    it via ``openDocument`` rather than leaving the app. A link is NAVIGATION;
    a citation is PROVENANCE — they are deliberately distinct (module docstring).
    """

    type: Literal["link"] = "link"
    href: str
    internal_document_id: str | None = None
    children: list[InlineSpan]


class CodeSpan(_SpanBase):
    """Inline monospace (`` `code` ``). Text is verbatim — never re-parsed."""

    type: Literal["code"] = "code"
    text: str


class MathSpan(_SpanBase):
    """Inline math (``$x$``). ``tex`` is the verbatim TeX source; rendering is
    SPR-03's job (KaTeX). Inline math can appear INSIDE a heading's spans —
    one of the round-trip edge cases."""

    type: Literal["math"] = "math"
    tex: str


class CitationSpan(_SpanBase):
    """A first-class citation — the provenance edge made renderable.

    Carries the SAME grounding triple the graph edge vocabulary uses
    (``source_document_id`` + ``chunk_id``; see ``ops.py`` ``insert_edge`` and
    ``ProvenanceLink`` in ``nodes.py``) PLUS a char range into the *source*
    document, so clicking the marker opens the real source at the cited passage
    in the one Reader (SPR-07). ``marker`` is the rendered label ("[1]",
    "(Smith 2020)"). NOT a footnote (which points within this document) and NOT
    a link (which navigates by URL) — see the module docstring's rejected
    alternatives.

    ``char_start`` / ``char_end`` are OPTIONAL: a citation marker may be
    recoverable without a precise source char range (rigor #1 — SPR-02 confirms
    against a real extraction). When present, ``char_end >= char_start``.
    """

    type: Literal["citation"] = "citation"
    source_document_id: str
    chunk_id: str
    marker: str
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)


# The inline-span discriminated union. ``Annotated[..., Field(discriminator=)]``
# makes Pydantic pick the member by the ``type`` literal — the same mechanism
# the event schema uses for ``action_type``.
InlineSpan = Annotated[
    Union[
        TextSpan,
        StrongSpan,
        EmphasisSpan,
        LinkSpan,
        CodeSpan,
        MathSpan,
        CitationSpan,
    ],
    Field(discriminator="type"),
]


# ───────────────────────────────────────────────────────────────────────────
# Blocks — the structural units of a document body.
# ───────────────────────────────────────────────────────────────────────────


class _BlockBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HeadingBlock(_BlockBase):
    """A heading, level 1–6. ``spans`` (not a bare string) so inline math /
    code / emphasis can appear inside a heading — an explicit round-trip edge
    case. ``toc()`` derives the table of contents from these blocks."""

    type: Literal["heading"] = "heading"
    level: int = Field(ge=1, le=6)
    spans: list[InlineSpan]


class ParagraphBlock(_BlockBase):
    """A paragraph of flowing inline content."""

    type: Literal["paragraph"] = "paragraph"
    spans: list[InlineSpan]


class ListItem(_BlockBase):
    """One list item. ``blocks`` (a block-list) so an item can hold a
    paragraph, a NESTED list, or a code block — nesting falls out for free.
    Not a discriminated member; it is the structural child of ``ListBlock``."""

    type: Literal["list_item"] = "list_item"
    blocks: list[Block]


class ListBlock(_BlockBase):
    """An ordered or unordered list. ``ordered=True`` ⇒ numbered. Items carry
    block-lists, so ``ListBlock`` nesting (a list whose item contains another
    ``ListBlock``) is the recursive case the round-trip test exercises."""

    type: Literal["list"] = "list"
    ordered: bool = False
    items: list[ListItem]


class TableBlock(_BlockBase):
    """A table. ``alignment`` is per-column (``left`` / ``center`` / ``right``
    / ``None`` = unspecified); its length is the column count. ``header`` and
    each ``rows`` row is a list of CELLS, and each cell is a list of inline
    spans — so a cell can hold bold text, a citation, inline math, or be EMPTY
    (``[]``), an explicit round-trip edge case."""

    type: Literal["table"] = "table"
    alignment: list[Literal["left", "center", "right"] | None] = Field(default_factory=list)
    header: list[list[InlineSpan]] = Field(default_factory=list)
    rows: list[list[list[InlineSpan]]] = Field(default_factory=list)


class CodeBlock(_BlockBase):
    """A fenced code block. ``text`` is verbatim — it may itself CONTAIN the
    discriminator string ``"type": "paragraph"`` and must round-trip unharmed,
    an explicit edge case. ``lang`` is optional (a fence with no language)."""

    type: Literal["code"] = "code"
    lang: str | None = None
    text: str


class MathBlock(_BlockBase):
    """A display-math block. ``tex`` is verbatim TeX (may be multi-line).
    ``display=True`` distinguishes block from inline at the data layer even
    though the type already implies it — kept so a renderer reading only the
    field is unambiguous."""

    type: Literal["math"] = "math"
    display: bool = True
    tex: str


class FigureBlock(_BlockBase):
    """A figure. ``caption`` is inline spans (it can hold a citation). ``src``
    and ``alt`` are OPTIONAL because a raw PDF extraction frequently recovers a
    caption but not a resolvable image src or alt text (rigor #1 — SPR-02
    confirms / tightens against a real extraction)."""

    type: Literal["figure"] = "figure"
    src: str | None = None
    alt: str | None = None
    caption: list[InlineSpan] = Field(default_factory=list)


class BlockquoteBlock(_BlockBase):
    """A blockquote. ``blocks`` (a block-list) so a quote can contain
    paragraphs, lists, even a nested blockquote."""

    type: Literal["blockquote"] = "blockquote"
    blocks: list[Block]


class FootnoteBlock(_BlockBase):
    """A footnote definition. ``id`` is the marker target ("1", "a"); ``blocks``
    is its content. A FOOTNOTE points WITHIN this document (reading
    convenience); a CITATION points at a SOURCE document with a provenance
    triple — they are deliberately distinct (module docstring)."""

    type: Literal["footnote"] = "footnote"
    id: str
    blocks: list[Block]


# The block discriminated union.
Block = Annotated[
    Union[
        HeadingBlock,
        ParagraphBlock,
        ListBlock,
        TableBlock,
        CodeBlock,
        MathBlock,
        FigureBlock,
        BlockquoteBlock,
        FootnoteBlock,
    ],
    Field(discriminator="type"),
]


# ───────────────────────────────────────────────────────────────────────────
# Document + attribution + derived ToC.
# ───────────────────────────────────────────────────────────────────────────


class DocumentAttribution(BaseModel):
    """Provenance/rights metadata for a document. ``content_class`` is typed
    against the §9.0 ``ContentClass`` vocabulary owned by ``servable.py`` — this
    RECORDS the class; it never re-derives deny-by-default. ``ip_holder_id`` is
    present (even if null) for the provenance-chain invariant (CLAUDE.md). It is
    OPTIONAL because a freshly-fetched web source may not have one yet; the
    serve gate (``substrate.books.serve.serve_full_text``) treats unknown as
    non-servable, so an absent class is safe by default."""

    model_config = ConfigDict(extra="forbid")

    ip_holder: str | None = None
    source_url: str | None = None
    content_class: ContentClass | None = None


class TocEntry(BaseModel):
    """One derived table-of-contents entry. ``text`` is the heading's plain-text
    rendering; ``index`` is the heading block's position in ``Document.blocks``
    so the Reader can scroll to it. DERIVED by ``Document.toc()`` — never stored
    on the Document (derive-don't-duplicate; see module docstring)."""

    model_config = ConfigDict(extra="forbid")

    level: int = Field(ge=1, le=6)
    text: str
    block_index: int = Field(ge=0)


def _spans_to_plain_text(spans: list) -> str:
    """Flatten inline spans to plain text for a ToC label / alt fallback.
    Walks ``children`` recursively; a citation contributes its ``marker``,
    math its ``tex``. Lossy by design (ToC labels are plain text)."""
    out: list[str] = []
    for span in spans:
        t = span.type
        if t in ("text", "code"):
            out.append(span.text)
        elif t == "math":
            out.append(span.tex)
        elif t == "citation":
            out.append(span.marker)
        elif t in ("strong", "emphasis", "link"):
            out.append(_spans_to_plain_text(span.children))
    return "".join(out)


class Document(BaseModel):
    """The canonical typed-block document — the Unified Reader's spine.

    Every ingest path (SPR-02) emits this; the one ``<Reader>`` (SPR-03)
    renders it; ``openDocument`` (SPR-05) resolves to it. The ToC is DERIVED
    from heading blocks via ``toc()``; it is never a stored field (a second
    copy would drift).
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    attribution: DocumentAttribution = Field(default_factory=DocumentAttribution)
    blocks: list[Block] = Field(default_factory=list)
    # The migration handle. Defaults to the current version; a document loaded
    # from storage carries the version it was written under.
    schema_version: int = DOCUMENT_MODEL_SCHEMA_VERSION

    def toc(self) -> list[TocEntry]:
        """Derive the table of contents from heading blocks. Single source of
        truth: the ``blocks`` list. No ``toc`` field exists to drift from it."""
        entries: list[TocEntry] = []
        for i, block in enumerate(self.blocks):
            if block.type == "heading":
                entries.append(
                    TocEntry(
                        level=block.level,
                        text=_spans_to_plain_text(block.spans),
                        block_index=i,
                    )
                )
        return entries


# Resolve forward references (``InlineSpan`` / ``Block`` are used in annotations
# before their members are fully defined; the recursive ``ListItem.blocks`` /
# ``BlockquoteBlock.blocks`` / ``StrongSpan.children`` need this).
StrongSpan.model_rebuild()
EmphasisSpan.model_rebuild()
LinkSpan.model_rebuild()
HeadingBlock.model_rebuild()
ParagraphBlock.model_rebuild()
ListItem.model_rebuild()
ListBlock.model_rebuild()
TableBlock.model_rebuild()
FigureBlock.model_rebuild()
BlockquoteBlock.model_rebuild()
FootnoteBlock.model_rebuild()
Document.model_rebuild()


__all__ = [
    "DOCUMENT_MODEL_SCHEMA_VERSION",
    # spans
    "TextSpan",
    "StrongSpan",
    "EmphasisSpan",
    "LinkSpan",
    "CodeSpan",
    "MathSpan",
    "CitationSpan",
    "InlineSpan",
    # blocks
    "HeadingBlock",
    "ParagraphBlock",
    "ListItem",
    "ListBlock",
    "TableBlock",
    "CodeBlock",
    "MathBlock",
    "FigureBlock",
    "BlockquoteBlock",
    "FootnoteBlock",
    "Block",
    # document
    "DocumentAttribution",
    "TocEntry",
    "Document",
]
