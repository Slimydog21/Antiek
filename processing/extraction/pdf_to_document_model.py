"""PDF → the SPR-01 structured ``Document`` (Reader SPR-02 M2) — LOSSY, confidence-tagged.

PDF extraction is fundamentally lossy (rigor #1): a PDF encodes glyph positions,
not document structure. There is no "heading" in a PDF — only a run of larger,
bolder glyphs we INFER is one. Two-column layouts, ligatures, scanned figures,
and exotic math macros all degrade. This module is honest about that: every
block it produces by a heuristic carries an ``extraction_confidence`` (returned
in a sibling ``PdfExtractionReport``, NOT smuggled into the frozen SPR-01 schema),
and low-confidence blocks are MARKED, not hidden.

Why a sibling report rather than a field on the block: the SPR-01 ``Document``
model is ``extra="forbid"`` and is the codegen source of truth (a drift test
fails on any field change). Adding ``extraction_confidence`` to every block would
mutate that contract and force a TS-codegen regen for a property that is
extraction-provenance, not render data. So confidence rides ALONGSIDE the model,
keyed by block index — the same "store provenance beside the artifact" shape M4
uses for the structured-blocks column. SPR-03 renders the Document; a low-
confidence badge (if wanted) reads the report. The Document stays pure.

────────────────────────────────────────────────────────────────────────────
HEURISTIC LEDGER (rigor #5 — every number sourced, none from the air).

* HEADING_SIZE_RATIO = 1.20. A text line whose median glyph size is >= 1.20x the
  document's BODY size (the modal line size — the most common, taken as the body
  baseline) is treated as a heading. Origin: typographic convention — body copy
  sits at 1.0, and the smallest conventional heading step (h6/h5) is ~1.2x body
  (a 12pt body → ~14pt smallest heading). Below 1.2x the size difference is
  within normal body variance (bold inline, footnote refs) and would over-detect.
* HEADING_LEVEL_RATIOS = [(2.0,1),(1.6,2),(1.35,3),(1.2,4)]. The size-ratio → H-
  level ladder. Origin: a conventional modular type scale (~1.25 step): 2.0x+ is
  a title (H1), 1.6x a major section (H2), 1.35x a subsection (H3), 1.2x the
  smallest heading (H4). H5/H6 are not inferred from a PDF — the signal is too
  weak to distinguish; they collapse to H4. Documented degradation, not silent.
* BOLD_HEADING_CONFIDENCE = 0.75 / SIZE_ONLY_HEADING_CONFIDENCE = 0.55. A heading
  detected by size AND a bold fontname is higher-confidence than size alone.
  Origin: bold+large is the strong typographic signal; large-but-not-bold is
  weaker (could be a pull-quote or figure label). Both are heuristic, hence < 1.0.
* PARAGRAPH_CONFIDENCE = 0.9. Body paragraphs are the highest-confidence
  extraction (the default case — anything not a heading/figure/table). Not 1.0:
  reading-order linearization of a two-column page can still interleave columns
  (the documented two-column degradation).
* LINE_GAP_PARAGRAPH_RATIO = 1.6. A vertical gap between consecutive lines >=
  1.6x the median line height starts a new paragraph. Origin: normal leading is
  ~1.2x font size; a paragraph break adds visible space, so ~1.6x is the
  conservative cutoff that splits paragraphs without splitting wrapped lines.
* CAPTION_PREFIX_RE matches "Figure N" / "Fig. N" / "Table N" at a line start.
  Origin: the near-universal caption convention. A figure's IMAGE bytes are not
  recovered (rigor #1 — ``src``/``alt`` stay None per the SPR-01 note); we
  recover the CAPTION as a FigureBlock so the figure is present in reading order.
* TABLE_CONFIDENCE = 0.5 — pdfplumber ``extract_tables`` is best-effort; merged
  cells and borderless tables degrade. Floor at 0.5 so a maintainer sees tables
  are the least-trusted block. (Tables are emitted only when pdfplumber finds a
  ruled grid; a borderless "table" degrades to paragraphs — documented.)

These constants are the FULL answer to "why is a 1.2x font run a heading?" — a
maintainer reconstructs every threshold from here, not from a chat.
"""

from __future__ import annotations

import io
import re
import statistics
from dataclasses import dataclass, field

from substrate.contracts.document_model import (
    DOCUMENT_MODEL_SCHEMA_VERSION,
    Document,
    DocumentAttribution,
    FigureBlock,
    HeadingBlock,
    ParagraphBlock,
    TableBlock,
    TextSpan,
)

# ── Heuristic constants (see the LEDGER in the module docstring) ─────────────
HEADING_SIZE_RATIO = 1.20
HEADING_LEVEL_RATIOS: tuple[tuple[float, int], ...] = (
    (2.00, 1),
    (1.60, 2),
    (1.35, 3),
    (1.20, 4),
)
BOLD_HEADING_CONFIDENCE = 0.75
SIZE_ONLY_HEADING_CONFIDENCE = 0.55
PARAGRAPH_CONFIDENCE = 0.90
LINE_GAP_PARAGRAPH_RATIO = 1.60
TABLE_CONFIDENCE = 0.50
FIGURE_CAPTION_CONFIDENCE = 0.65
# A block whose confidence is below this floor is flagged low-confidence in the
# report (the "marked, not hidden" contract). 0.6 = the model's own "reasonably
# inferred" rung (extract.py confidence calibration table); below it the block
# is "weakly suggested" and the operator should distrust it.
LOW_CONFIDENCE_FLOOR = 0.60

CAPTION_PREFIX_RE = re.compile(r"^\s*(figure|fig\.?|table)\s+\d+", re.IGNORECASE)


@dataclass
class PdfExtractionReport:
    """Extraction provenance that rides ALONGSIDE the Document (never inside the
    frozen schema). ``block_confidence[i]`` is the ``extraction_confidence`` of
    ``document.blocks[i]``; ``low_confidence_indices`` are the blocks flagged
    below the floor (marked, not dropped). ``page_count`` and ``had_tables`` let
    a caller report what degraded."""

    block_confidence: list[float] = field(default_factory=list)
    low_confidence_indices: list[int] = field(default_factory=list)
    page_count: int = 0
    had_tables: bool = False
    notes: list[str] = field(default_factory=list)

    def overall_confidence(self) -> float:
        """Mean block confidence — a coarse "how much to trust this" scalar."""
        if not self.block_confidence:
            return 0.0
        return sum(self.block_confidence) / len(self.block_confidence)


def _is_bold(fontname: str | None) -> bool:
    """A fontname signalling bold. PDF fontnames embed weight in the name
    (``Helvetica-Bold``, ``...,Bold``, ``...-Black``). Heuristic by necessity —
    there is no weight field in the glyph stream."""
    if not fontname:
        return False
    f = fontname.lower()
    return any(tok in f for tok in ("bold", "black", "heavy", "semibold"))


def _heading_level(size_ratio: float) -> int:
    """Map a line/body size ratio to an H-level via the ladder. >= the smallest
    rung is required by the caller before this is consulted."""
    for ratio, level in HEADING_LEVEL_RATIOS:
        if size_ratio >= ratio:
            return level
    return 4  # at/above HEADING_SIZE_RATIO but below the ladder's last rung


@dataclass
class _Line:
    text: str
    size: float
    top: float
    bold: bool


def _words_to_lines(words: list[dict]) -> list[_Line]:
    """Group pdfplumber words into visual lines by their ``top`` coordinate.
    Reading-order WITHIN a line is left-to-right (pdfplumber returns words in
    that order per line already); BETWEEN lines we sort by ``top`` (then x0)
    which linearizes a single column correctly and a two-column page
    IMPERFECTLY (the documented two-column degradation — a column-detection
    pass is an additive future field per the SPR-01 multi-column note)."""
    if not words:
        return []
    # Cluster by top within a small tolerance (same visual line).
    rows: dict[int, list[dict]] = {}
    for w in words:
        key = round(w["top"] / 2.0)  # 2pt bucket — sub-line jitter tolerance
        rows.setdefault(key, []).append(w)
    lines: list[_Line] = []
    for key in sorted(rows):
        ws = sorted(rows[key], key=lambda w: w["x0"])
        text = " ".join(w["text"] for w in ws).strip()
        if not text:
            continue
        sizes = [w.get("size", 0.0) for w in ws if w.get("size")]
        size = statistics.median(sizes) if sizes else 0.0
        bold = any(_is_bold(w.get("fontname")) for w in ws)
        lines.append(_Line(text=text, size=size, top=min(w["top"] for w in ws), bold=bold))
    return lines


def _body_size(lines: list[_Line]) -> float:
    """The body baseline size. Rounded to 0.5pt so near-identical sizes cluster.

    Primary signal: the MODAL (most frequent) line size — body copy dominates a
    document by line count. TIE-BREAK toward the SMALLER size: when two sizes
    are equally frequent (the common case on a short page: one heading line, one
    body line), the body is the smaller one. Origin: the typographic prior that
    body copy is the floor and headings step UP from it — picking the larger on a
    tie would mislabel a title as body and collapse the whole page into one
    paragraph (the exact failure this guards). On a normal multi-paragraph page
    the mode is unambiguous and the tie-break never fires."""
    if not lines:
        return 0.0
    buckets: dict[float, int] = {}
    for ln in lines:
        b = round(ln.size * 2) / 2
        buckets[b] = buckets.get(b, 0) + 1
    best_count = max(buckets.values())
    # Among the most-frequent sizes, take the smallest (the tie-break prior).
    return min(size for size, count in buckets.items() if count == best_count) or 0.0


def pdf_bytes_to_document(
    pdf_bytes: bytes,
    *,
    document_id: str,
    title: str | None = None,
    attribution: DocumentAttribution | None = None,
) -> tuple[Document, PdfExtractionReport]:
    """Extract ``pdf_bytes`` to a (Document, report) pair. The ORIGINAL bytes are
    the caller's to persist for "view original" (M4 stores them); this function
    does not own storage. Deterministic — no model call, no provider key."""
    try:
        import pdfplumber
        from pypdf import PdfReader
    except ImportError as e:  # pragma: no cover — environment guard
        raise ImportError(
            "processing.extraction.pdf_to_document_model requires the pdf extra. "
            "Run `pip install -e '.[pdf]'` to install pdfplumber + pypdf."
        ) from e

    report = PdfExtractionReport()
    blocks: list = []

    # Title from PDF metadata via pypdf when the caller gives none.
    resolved_title = title
    if resolved_title is None:
        try:
            meta = PdfReader(io.BytesIO(pdf_bytes)).metadata
            if meta and meta.title:
                resolved_title = str(meta.title)
        except Exception:  # pragma: no cover — metadata is best-effort
            pass

    def _add(block, confidence: float) -> None:
        idx = len(blocks)
        blocks.append(block)
        report.block_confidence.append(confidence)
        if confidence < LOW_CONFIDENCE_FLOOR:
            report.low_confidence_indices.append(idx)

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        report.page_count = len(pdf.pages)
        for page in pdf.pages:
            # Tables first (best-effort) so we can exclude their region from the
            # text flow. pdfplumber finds ruled grids; borderless tables are not
            # detected and their text degrades to paragraphs (documented).
            tables = []
            try:
                tables = page.extract_tables() or []
            except Exception:  # pragma: no cover — pdfplumber edge
                tables = []
            for t in tables:
                report.had_tables = True
                _add(_table_from_grid(t), TABLE_CONFIDENCE)

            words = page.extract_words(extra_attrs=["size", "fontname"])
            lines = _words_to_lines(words)
            if not lines:
                continue
            body = _body_size(lines)
            line_heights = [
                lines[i + 1].top - lines[i].top for i in range(len(lines) - 1)
            ]
            median_gap = statistics.median(line_heights) if line_heights else 0.0

            # ``para_buf`` is a fresh list per page; ``_flush_para`` takes it as an
            # explicit argument (not a closure over the loop variable) so the
            # buffer of one page can never leak into the next.
            para_buf: list[str] = []

            def _flush_para(buf: list[str]) -> None:
                if buf:
                    text = " ".join(buf).strip()
                    if text:
                        _add(
                            ParagraphBlock(spans=[TextSpan(text=text)]),
                            PARAGRAPH_CONFIDENCE,
                        )
                    buf.clear()

            for k, ln in enumerate(lines):
                ratio = (ln.size / body) if body else 1.0
                is_caption = bool(CAPTION_PREFIX_RE.match(ln.text))

                if is_caption:
                    _flush_para(para_buf)
                    _add(
                        FigureBlock(caption=[TextSpan(text=ln.text)]),
                        FIGURE_CAPTION_CONFIDENCE,
                    )
                    continue

                if ratio >= HEADING_SIZE_RATIO and len(ln.text) < 200:
                    # Large line → heading. (Length guard: a very long "large"
                    # run is more likely a mis-sized paragraph than a heading.)
                    _flush_para(para_buf)
                    conf = (
                        BOLD_HEADING_CONFIDENCE if ln.bold else SIZE_ONLY_HEADING_CONFIDENCE
                    )
                    _add(
                        HeadingBlock(
                            level=_heading_level(ratio),
                            spans=[TextSpan(text=ln.text)],
                        ),
                        conf,
                    )
                    continue

                # Body line. A large vertical gap from the previous line starts a
                # new paragraph; otherwise it is a wrapped continuation.
                if k > 0 and median_gap > 0:
                    gap = ln.top - lines[k - 1].top
                    if gap >= LINE_GAP_PARAGRAPH_RATIO * median_gap:
                        _flush_para(para_buf)
                para_buf.append(ln.text)

            _flush_para(para_buf)

    if not blocks:
        report.notes.append("no extractable text — PDF may be scanned/image-only")
    if report.low_confidence_indices:
        report.notes.append(
            f"{len(report.low_confidence_indices)} block(s) below confidence floor "
            f"{LOW_CONFIDENCE_FLOOR} — heuristic-inferred, distrust"
        )

    doc = Document(
        id=document_id,
        title=resolved_title or "(untitled PDF)",
        attribution=attribution or DocumentAttribution(),
        blocks=blocks,
        schema_version=DOCUMENT_MODEL_SCHEMA_VERSION,
    )
    return doc, report


def _table_from_grid(grid: list[list]) -> TableBlock:
    """A pdfplumber table grid (list of rows of str|None cells) → TableBlock.
    Each cell becomes a single TextSpan (PDF table cells rarely carry recoverable
    inline markup); an empty/merged cell (None) becomes an empty span list — the
    merged/empty-cell edge case, preserved as a real empty cell not a dropped
    column. Alignment is unspecified (PDF gives no column-alignment signal)."""
    rows_in = [r for r in grid if r]
    if not rows_in:
        return TableBlock()
    header = [
        [TextSpan(text=str(c).strip())] if c not in (None, "") else []
        for c in rows_in[0]
    ]
    body_rows = []
    for r in rows_in[1:]:
        body_rows.append(
            [[TextSpan(text=str(c).strip())] if c not in (None, "") else [] for c in r]
        )
    ncols = len(rows_in[0])
    return TableBlock(alignment=[None] * ncols, header=header, rows=body_rows)


__all__ = [
    "PdfExtractionReport",
    "pdf_bytes_to_document",
    "HEADING_SIZE_RATIO",
    "HEADING_LEVEL_RATIOS",
    "LOW_CONFIDENCE_FLOOR",
]
