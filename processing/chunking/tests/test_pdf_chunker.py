"""Tests for the PDF page-tagging chunker decorator."""

from __future__ import annotations

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def _fake_extraction(pages_text: list[str]):
    """Build a minimal PdfExtraction shim for tests."""
    from services.ingestion.extractors.pdf import PdfExtraction, PdfPage
    pages = [
        PdfPage(page_index=i, text=t, word_count=len(t.split()))
        for i, t in enumerate(pages_text, start=1)
    ]
    return PdfExtraction(
        title="test",
        author=None,
        pages=pages,
        word_count=sum(p.word_count for p in pages),
        text="\n\n".join(t for t in pages_text if t),
    )


def test_each_chunk_has_a_page():
    from processing.chunking.pdf_chunker import chunk_pdf_extraction
    ext = _fake_extraction([
        "# Page one\n\nFirst page body text.",
        "# Page two\n\nSecond page body text.",
        "# Page three\n\nThird page body.",
    ])
    chunks = chunk_pdf_extraction(ext)
    assert len(chunks) == 3
    assert [c.page for c in chunks] == [1, 2, 3]


def test_multiple_chunks_on_one_page_get_distinct_bboxes():
    from processing.chunking.pdf_chunker import chunk_pdf_extraction
    # Build a page with two headings → two chunks.
    long_page = "# Section A\n\nA body.\n\n# Section B\n\nB body."
    ext = _fake_extraction([long_page])
    chunks = chunk_pdf_extraction(ext)
    assert len(chunks) >= 2
    bboxes = [c.bbox for c in chunks if c.page == 1]
    assert len(bboxes) == len({tuple(b.items()) for b in bboxes}), (
        "every chunk on the page should have a distinct bbox"
    )


def test_bbox_bands_are_adjacent_and_non_overlapping():
    """SPR-02's overlap resolution needs distinct bands; we want
    "chunk i top edge = chunk i+1 bottom edge" within rounding."""
    from processing.chunking.pdf_chunker import chunk_pdf_extraction
    page = "# A\n\nA.\n\n# B\n\nB.\n\n# C\n\nC."
    ext = _fake_extraction([page])
    chunks = sorted(
        (c for c in chunk_pdf_extraction(ext) if c.page == 1),
        key=lambda c: -c.bbox["y1"],  # top band first
    )
    for i in range(len(chunks) - 1):
        # PDF y is upward — top band has the larger y. The band below
        # should have its top edge at the bottom edge of the band above.
        assert abs(chunks[i].bbox["y0"] - chunks[i + 1].bbox["y1"]) < 0.01


def test_empty_pages_skipped():
    from processing.chunking.pdf_chunker import chunk_pdf_extraction
    ext = _fake_extraction(["", "", "# Real page\n\nText here."])
    chunks = chunk_pdf_extraction(ext)
    assert len(chunks) == 1
    assert chunks[0].page == 3


def test_no_pages_returns_empty():
    from processing.chunking.pdf_chunker import chunk_pdf_extraction
    ext = _fake_extraction([])
    assert chunk_pdf_extraction(ext) == []


def test_chunker_version_constant():
    from processing.chunking.pdf_chunker import CHUNKER_VERSION
    assert CHUNKER_VERSION == "pdf-page-tagged-v1"
