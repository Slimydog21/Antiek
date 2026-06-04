// AUTO-GENERATED — DO NOT EDIT.
//
// Generated from substrate/contracts/document_model.py + reading_surface.py
// by tools/codegen/emit_document_model.py.
// Re-run after any change:   python tools/codegen/emit_document_model.py
// CI gate that fails on drift: python tools/codegen/check_staleness.py
//
// The Pydantic models are the single source of truth. This is the typed-block
// document the one <Reader> renders and openDocument resolves to (antiek-reader
// SPR-01). The InlineSpan / Block discriminated unions narrow on `type`.

export const DOCUMENT_MODEL_SCHEMA_VERSION = 1;

/**
 * Plain text. The only span carrying no markup.
 */
export interface TextSpan {
  type: "text";
  text: string;
}

/**
 * Bold. ``children`` so ``**a *b* c**`` (strong wrapping emphasis) nests.
 */
export interface StrongSpan {
  type: "strong";
  children: InlineSpan[];
}

/**
 * Italic. ``children`` for nested inline markup (same reason as strong).
 */
export interface EmphasisSpan {
  type: "emphasis";
  children: InlineSpan[];
}

/**
 * A hyperlink. ``href`` is the external/anchor target; the OPTIONAL
 *     ``internal_document_id`` names an in-Antiek document so the Reader can open
 *     it via ``openDocument`` rather than leaving the app. A link is NAVIGATION;
 *     a citation is PROVENANCE — they are deliberately distinct (module docstring).
 */
export interface LinkSpan {
  type: "link";
  href: string;
  internal_document_id?: string | null;
  children: InlineSpan[];
}

/**
 * Inline monospace (`` `code` ``). Text is verbatim — never re-parsed.
 */
export interface CodeSpan {
  type: "code";
  text: string;
}

/**
 * Inline math (``$x$``). ``tex`` is the verbatim TeX source; rendering is
 *     SPR-03's job (KaTeX). Inline math can appear INSIDE a heading's spans —
 *     one of the round-trip edge cases.
 */
export interface MathSpan {
  type: "math";
  tex: string;
}

/**
 * A first-class citation — the provenance edge made renderable.
 * 
 *     Carries the SAME grounding triple the graph edge vocabulary uses
 *     (``source_document_id`` + ``chunk_id``; see ``ops.py`` ``insert_edge`` and
 *     ``ProvenanceLink`` in ``nodes.py``) PLUS a char range into the *source*
 *     document, so clicking the marker opens the real source at the cited passage
 *     in the one Reader (SPR-07). ``marker`` is the rendered label ("[1]",
 *     "(Smith 2020)"). NOT a footnote (which points within this document) and NOT
 *     a link (which navigates by URL) — see the module docstring's rejected
 *     alternatives.
 * 
 *     ``char_start`` / ``char_end`` are OPTIONAL: a citation marker may be
 *     recoverable without a precise source char range (rigor #1 — SPR-02 confirms
 *     against a real extraction). When present, ``char_end >= char_start``.
 */
export interface CitationSpan {
  type: "citation";
  source_document_id: string;
  chunk_id: string;
  marker: string;
  char_start?: number | null;
  char_end?: number | null;
}

/** Inline span — narrow on `type`. */
export type InlineSpan =
  | TextSpan
  | StrongSpan
  | EmphasisSpan
  | LinkSpan
  | CodeSpan
  | MathSpan
  | CitationSpan;

/**
 * One list item. ``blocks`` (a block-list) so an item can hold a
 *     paragraph, a NESTED list, or a code block — nesting falls out for free.
 *     Not a discriminated member; it is the structural child of ``ListBlock``.
 */
export interface ListItem {
  type: "list_item";
  blocks: Block[];
}

/**
 * A heading, level 1–6. ``spans`` (not a bare string) so inline math /
 *     code / emphasis can appear inside a heading — an explicit round-trip edge
 *     case. ``toc()`` derives the table of contents from these blocks.
 */
export interface HeadingBlock {
  type: "heading";
  level: number;
  spans: InlineSpan[];
}

/**
 * A paragraph of flowing inline content.
 */
export interface ParagraphBlock {
  type: "paragraph";
  spans: InlineSpan[];
}

/**
 * An ordered or unordered list. ``ordered=True`` ⇒ numbered. Items carry
 *     block-lists, so ``ListBlock`` nesting (a list whose item contains another
 *     ``ListBlock``) is the recursive case the round-trip test exercises.
 */
export interface ListBlock {
  type: "list";
  ordered?: boolean;
  items: ListItem[];
}

/**
 * A table. ``alignment`` is per-column (``left`` / ``center`` / ``right``
 *     / ``None`` = unspecified); its length is the column count. ``header`` and
 *     each ``rows`` row is a list of CELLS, and each cell is a list of inline
 *     spans — so a cell can hold bold text, a citation, inline math, or be EMPTY
 *     (``[]``), an explicit round-trip edge case.
 */
export interface TableBlock {
  type: "table";
  alignment?: ("left" | "center" | "right" | null)[];
  header?: InlineSpan[][];
  rows?: InlineSpan[][][];
}

/**
 * A fenced code block. ``text`` is verbatim — it may itself CONTAIN the
 *     discriminator string ``"type": "paragraph"`` and must round-trip unharmed,
 *     an explicit edge case. ``lang`` is optional (a fence with no language).
 */
export interface CodeBlock {
  type: "code";
  lang?: string | null;
  text: string;
}

/**
 * A display-math block. ``tex`` is verbatim TeX (may be multi-line).
 *     ``display=True`` distinguishes block from inline at the data layer even
 *     though the type already implies it — kept so a renderer reading only the
 *     field is unambiguous.
 */
export interface MathBlock {
  type: "math";
  display?: boolean;
  tex: string;
}

/**
 * A figure. ``caption`` is inline spans (it can hold a citation). ``src``
 *     and ``alt`` are OPTIONAL because a raw PDF extraction frequently recovers a
 *     caption but not a resolvable image src or alt text (rigor #1 — SPR-02
 *     confirms / tightens against a real extraction).
 */
export interface FigureBlock {
  type: "figure";
  src?: string | null;
  alt?: string | null;
  caption?: InlineSpan[];
}

/**
 * A blockquote. ``blocks`` (a block-list) so a quote can contain
 *     paragraphs, lists, even a nested blockquote.
 */
export interface BlockquoteBlock {
  type: "blockquote";
  blocks: Block[];
}

/**
 * A footnote definition. ``id`` is the marker target ("1", "a"); ``blocks``
 *     is its content. A FOOTNOTE points WITHIN this document (reading
 *     convenience); a CITATION points at a SOURCE document with a provenance
 *     triple — they are deliberately distinct (module docstring).
 */
export interface FootnoteBlock {
  type: "footnote";
  id: string;
  blocks: Block[];
}

/** Block — narrow on `type`. */
export type Block =
  | HeadingBlock
  | ParagraphBlock
  | ListBlock
  | TableBlock
  | CodeBlock
  | MathBlock
  | FigureBlock
  | BlockquoteBlock
  | FootnoteBlock;

/**
 * Provenance/rights metadata for a document. ``content_class`` is typed
 *     against the §9.0 ``ContentClass`` vocabulary owned by ``servable.py`` — this
 *     RECORDS the class; it never re-derives deny-by-default. ``ip_holder_id`` is
 *     present (even if null) for the provenance-chain invariant (CLAUDE.md). It is
 *     OPTIONAL because a freshly-fetched web source may not have one yet; the
 *     serve gate (``substrate.books.serve.serve_full_text``) treats unknown as
 *     non-servable, so an absent class is safe by default.
 */
export interface DocumentAttribution {
  ip_holder_id?: string | null;
  source_url?: string | null;
  content_class?: "public_domain" | "platform_authored" | "publisher_opted_in" | "source_declared_open" | "gated_metadata_only" | "taken_down" | null;
}

/**
 * One derived table-of-contents entry. ``text`` is the heading's plain-text
 *     rendering; ``block_index`` is the heading block's position in
 *     ``Document.blocks`` so the Reader can scroll to it. DERIVED by
 *     ``Document.toc()`` — never stored on the Document (derive-don't-duplicate;
 *     see module docstring).
 */
export interface TocEntry {
  level: number;
  text: string;
  block_index: number;
}

/**
 * The canonical typed-block document — the Unified Reader's spine.
 * 
 *     Every ingest path (SPR-02) emits this; the one ``<Reader>`` (SPR-03)
 *     renders it; ``openDocument`` (SPR-05) resolves to it. The ToC is DERIVED
 *     from heading blocks via ``toc()``; it is never a stored field (a second
 *     copy would drift).
 */
export interface Document {
  id: string;
  title: string;
  attribution?: DocumentAttribution;
  blocks?: Block[];
  schema_version?: number;
}

/**
 * A span in document space: a ``block_id`` within ``document_id``, with an
 *     OPTIONAL ``char_start``/``char_end`` range when the selection is sub-block.
 * 
 *     Reuses the ``char_start`` / ``char_end`` vocabulary of
 *     ``substrate.schemas.events.DocumentRegionSelectedPayload`` rather than
 *     coining ``offset`` / ``span``. A whole-block region omits the char range; a
 *     sub-block highlight carries it (with ``char_end >= char_start``).
 */
export interface Region {
  document_id: string;
  block_id: string;
  char_start?: number | null;
  char_end?: number | null;
}

/**
 * The result of rendering a region: the ``Region`` echoed back plus the
 *     full typed-block ``Document`` the surface renders for it. A surface returns
 *     the typed ``Document`` (not an HTML string) so Read/Write compose over the
 *     SAME typed model the one Reader renders — there is no second, stringly-typed
 *     render path to fork into.
 */
export interface RenderedRegion {
  region: Region;
  document: Document;
}

/**
 * A note (an insight/question graph node) anchored to a region. Carries the
 *     ``node_id`` and the ``Region`` it is anchored to, so the living-note surface
 *     can re-locate the note when the document re-renders. ``node_id`` is the
 *     content-addressed graph node id (the same identity ``InsightNodeContract`` /
 *     ``QuestionNodeContract`` pin).
 */
export interface AnchoredNote {
  node_id: string;
  region: Region;
}
