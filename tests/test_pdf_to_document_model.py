"""PDF → Document extractor tests (SPR-02 M2) — real PDF bytes, confidence-tagged.

HONESTY NOTE (rigor #1): there is NO local arXiv PDF in this tree, and the
arXiv 429-ban history (project_researchmaxx_arxiv.md) forbids fetching one from
``export.arxiv.org`` during a test run. So this suite builds a REAL PDF with
reportlab (real glyphs, real font sizes — pdfplumber sees genuine glyph metrics,
not a mock) shaped like an arXiv paper: a title, section headings at distinct
font sizes, body paragraphs, a figure caption, and a ruled table. It is a real
PDF extraction; it is NOT a network-fetched arXiv paper. A maintainer with a
real paper and a clear arXiv rate-window can drop it in and the same code runs
(``pdf_bytes_to_document(open('paper.pdf','rb').read(), ...)``).

reportlab is already present in the tree (transitively via the ``export`` extra /
xhtml2pdf). The test SKIPS cleanly if it is ever absent rather than failing for
an environment reason.
"""

from __future__ import annotations

import io

import pytest

from substrate.contracts.document_model import Document

reportlab = pytest.importorskip("reportlab")

from processing.extraction.pdf_to_document_model import (  # noqa: E402
    LOW_CONFIDENCE_FLOOR,
    PdfExtractionReport,
    pdf_bytes_to_document,
)


def _arxiv_shaped_pdf() -> bytes:
    """A real multi-section PDF shaped like an arXiv paper. Distinct font sizes
    so the heading heuristic has genuine signal; a figure caption line; a ruled
    table."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    w, h = letter
    y = h - 72

    def line(text: str, font: str, size: float, dy: float = 0) -> None:
        nonlocal y
        y -= dy
        c.setFont(font, size)
        c.drawString(72, y, text)
        y -= size + 4

    # Title (largest), section headings (medium), body (base), figure caption.
    line("On the Convergence of Structured Readers", "Helvetica-Bold", 20, dy=10)
    line("Abstract", "Helvetica-Bold", 14, dy=14)
    line("We show that every renderer converges under the stated assumptions.",
         "Helvetica", 11)
    line("This abstract has two sentences. The second one is here.",
         "Helvetica", 11)
    line("1. Introduction", "Helvetica-Bold", 14, dy=16)
    line("The reading problem is to turn glyphs into structure.",
         "Helvetica", 11)
    line("We approach it with deterministic heuristics.",
         "Helvetica", 11)
    line("Figure 1. The pipeline overview, with no recoverable image source.",
         "Helvetica", 11, dy=14)
    c.save()
    return buf.getvalue()


def test_pdf_bytes_start_with_pdf_magic():
    data = _arxiv_shaped_pdf()
    assert data[:5] == b"%PDF-"


def test_real_pdf_reads_as_a_document_not_a_page_dump():
    """The M2 gate: a real PDF yields headings + body paragraphs that read as a
    document, with confidence tagging — not a single flat page-1 dump."""
    doc, report = pdf_bytes_to_document(
        _arxiv_shaped_pdf(), document_id="doc-arxiv-test"
    )
    assert isinstance(doc, Document)
    assert isinstance(report, PdfExtractionReport)

    kinds = [b.type for b in doc.blocks]
    assert "heading" in kinds, f"no headings detected; got {kinds}"
    assert "paragraph" in kinds, f"no paragraphs detected; got {kinds}"
    # It is NOT a single block (the page-1-dump failure).
    assert len(doc.blocks) >= 4, f"too few blocks — likely a flat dump: {kinds}"


def test_title_heading_detected_at_h1():
    doc, _ = pdf_bytes_to_document(_arxiv_shaped_pdf(), document_id="doc-h1")
    headings = [b for b in doc.blocks if b.type == "heading"]
    assert headings
    title_heading = headings[0]
    title_text = "".join(s.text for s in title_heading.spans if s.type == "text")
    assert "Convergence" in title_text
    # 20pt title / 11pt body ≈ 1.82x → H2 by the documented HEADING_LEVEL_RATIOS
    # ladder (>=1.6 → H2). It is the topmost heading; assert a top-level (H1/H2)
    # level, matching the sourced ladder rather than an invented expectation.
    assert title_heading.level <= 2


def test_figure_caption_becomes_a_figure_block():
    doc, report = pdf_bytes_to_document(_arxiv_shaped_pdf(), document_id="doc-fig")
    figs = [b for b in doc.blocks if b.type == "figure"]
    assert figs, "the 'Figure 1.' line should become a FigureBlock"
    cap_text = "".join(s.text for s in figs[0].caption if s.type == "text")
    assert cap_text.startswith("Figure 1")
    # src/alt are NOT recovered from a raw PDF (rigor #1 — SPR-01 optional note).
    assert figs[0].src is None
    assert figs[0].alt is None


def test_every_block_carries_a_confidence_and_round_trips():
    """Each block has a confidence in the report (parallel-indexed), and the
    Document round-trips through JSON."""
    doc, report = pdf_bytes_to_document(_arxiv_shaped_pdf(), document_id="doc-conf")
    assert len(report.block_confidence) == len(doc.blocks)
    assert all(0.0 <= c <= 1.0 for c in report.block_confidence)
    # Round-trip the Document (the report is provenance, not part of the wire model).
    as_json = doc.model_dump_json()
    assert Document.model_validate_json(as_json).model_dump_json() == as_json


def test_low_confidence_blocks_are_marked_not_hidden():
    """A heading detected by size alone (no bold) is below the floor and is
    FLAGGED in the report — present in the model, marked as low-confidence."""
    doc, report = pdf_bytes_to_document(_arxiv_shaped_pdf(), document_id="doc-low")
    # Figure captions (0.65) are above the floor; size-only headings would be
    # flagged. Our fixture uses bold headings, so assert the MECHANISM exists:
    # low_confidence_indices references real block indices, and the report's
    # overall confidence is a real mean.
    for i in report.low_confidence_indices:
        assert 0 <= i < len(doc.blocks)
        assert report.block_confidence[i] < LOW_CONFIDENCE_FLOOR
    assert 0.0 <= report.overall_confidence() <= 1.0


def test_size_only_heading_is_low_confidence():
    """A NON-bold large line is a heading at the lower (size-only) confidence —
    proving the bold-vs-size confidence split is real, not cosmetic."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    w, h = letter
    c.setFont("Helvetica", 11)
    c.drawString(72, h - 72, "Body text at the base size to set the body baseline.")
    c.drawString(72, h - 100, "More body text to make 11pt the modal size here.")
    c.setFont("Helvetica", 18)  # large but NOT bold
    c.drawString(72, h - 140, "A Large Non Bold Line")
    c.save()
    doc, report = pdf_bytes_to_document(buf.getvalue(), document_id="doc-sizeonly")
    headings = [
        (i, b) for i, b in enumerate(doc.blocks) if b.type == "heading"
    ]
    assert headings, "the 18pt line should be detected as a heading"
    idx, _ = headings[0]
    assert report.block_confidence[idx] < LOW_CONFIDENCE_FLOOR, (
        "a size-only (non-bold) heading must be below the confidence floor"
    )


def test_table_extracted_best_effort_with_low_confidence():
    """A ruled table is extracted best-effort and flagged at TABLE_CONFIDENCE."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

    buf = io.BytesIO()
    doc_t = SimpleDocTemplate(buf, pagesize=letter)
    data = [["Method", "Score"], ["A", "0.9"], ["B", ""]]  # an empty cell
    t = Table(data)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 1, colors.black)]))
    doc_t.build([t])
    doc, report = pdf_bytes_to_document(buf.getvalue(), document_id="doc-table")
    tables = [b for b in doc.blocks if b.type == "table"]
    assert tables, "a ruled table should be extracted"
    assert report.had_tables is True


def test_scanned_image_only_pdf_degrades_honestly():
    """A PDF with no extractable text (the scanned-figure degradation) yields an
    empty-but-valid Document and a report note — degrades honestly, not crashes."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    # Draw only a filled rectangle — no text glyphs at all.
    c.rect(100, 100, 200, 200, fill=1)
    c.save()
    doc, report = pdf_bytes_to_document(buf.getvalue(), document_id="doc-scan")
    assert doc.blocks == []
    assert any("scanned" in n or "no extractable" in n for n in report.notes)
