"""PDF-aware chunker decorator (2026-05-22 follow-up).

The base ``chunk_markdown`` splits text by markdown headings; it has no
concept of PDF pages. SPR-02 voice anchor + SPR-07 gutter cite-jump both
need ``chunks.page`` + ``chunks.bbox`` populated to resolve user
interactions back to chunk_ids.

This module decorates the base chunker. The PDF extractor
(``services.ingestion.extractors.pdf.extract_pdf``) already produces
per-page text in ``PdfExtraction.pages``. We chunk each page's text
INDEPENDENTLY through ``chunk_markdown``, then stamp:

  - ``page``: the 1-based page index (truth — the chunk came from there)
  - ``bbox``: proportional vertical slice of the page rect (truth at
    minimum specificity — without per-fragment coordinates from pypdf,
    we degrade to "this chunk is in vertical band N of M chunks on
    this page")

Why proportional bbox rather than full-page bbox for every chunk:
  - SPR-02's anchor resolution uses 30% overlap. If every chunk on a
    page had the same full-page bbox, every voice-note bbox would tie
    at 100% overlap — the first-returned chunk wins arbitrarily.
  - A proportional vertical split (chunk 1 = top portion, chunk 2 =
    next, ...) gives each chunk a distinct bbox, so voice anchors
    resolve to the chunk whose vertical band their selection sits in.
  - The split is by character count, which is deterministic + stable
    across rebuilds.
  - This is degenerate-but-honest. When a PDF-coordinate-aware chunker
    eventually lands, the bboxes get sharper; the wire contract is
    unchanged.

Why not pypdf layout-extraction:
  - ``pypdf 5.x`` has ``extract_text(extraction_mode="layout")`` which
    preserves whitespace coordinates but not the per-fragment x/y.
    Going further requires ``pdfplumber`` or ``PyMuPDF`` — both real
    deps. The decorator stays inside the existing pypdf footprint so
    no install changes. When the operator decides to add pdfplumber,
    swap this decorator's bbox computation for the real one in one
    place.

US Letter default page rect (612 × 792 pt) is the fallback when pypdf
can't expose ``page.mediabox`` (some encrypted / unusual PDFs). The
actual rect is used when available.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Optional

from processing.chunking.chunker import (
    Chunk,
    DEFAULT_MAX_CHUNK_TOKENS,
    chunk_markdown,
)


# US Letter in PDF user-space points (1/72 inch).
DEFAULT_PAGE_RECT = (0.0, 0.0, 612.0, 792.0)

# Bumped by every change to the chunker geometry. Lives in the
# `chunker_version` column of voice_note_anchor so the SPR-02 re-chunk
# worker knows when to re-resolve.
CHUNKER_VERSION = "pdf-page-tagged-v1"


@dataclass(frozen=True)
class PageTaggedChunk:
    """One chunk annotated with PDF page + bbox.

    Extends the base ``Chunk`` with the SPR-02-required geometry.
    Callers that want plain ``Chunk`` semantics can read ``.chunk``.
    """

    chunk: Chunk
    page: int
    bbox: dict  # {"x0":.., "y0":.., "x1":.., "y1":..}


def _page_rect_for(reader_page) -> tuple[float, float, float, float]:
    """Best-effort read of the page's media-box rect. Falls back to
    US Letter on any exception."""
    try:
        rect = reader_page.mediabox
        # pypdf's RectangleObject exposes lower-left + upper-right.
        return (
            float(rect.left),
            float(rect.bottom),
            float(rect.right),
            float(rect.top),
        )
    except Exception:
        return DEFAULT_PAGE_RECT


def _proportional_bbox(
    *,
    chunk_index: int,
    total_chunks_on_page: int,
    page_rect: tuple[float, float, float, float],
) -> dict:
    """Slice the page rect into ``total_chunks_on_page`` horizontal
    bands, return the chunk_index-th. Top-of-page = first chunk.

    The slicing is deterministic and stable across rebuilds. Two
    sequential chunks get adjacent (non-overlapping) bands so SPR-02's
    bbox-overlap resolution returns a unique winner.
    """
    x0, y0, x1, y1 = page_rect
    page_height = y1 - y0
    if total_chunks_on_page <= 0:
        return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}
    slice_h = page_height / total_chunks_on_page
    # PDF coordinates: y grows upward. "Top" of page = highest y.
    band_top = y1 - chunk_index * slice_h
    band_bot = band_top - slice_h
    return {"x0": x0, "y0": band_bot, "x1": x1, "y1": band_top}


def chunk_pdf_bytes(
    pdf_bytes: bytes,
    *,
    max_chunk_tokens: int = DEFAULT_MAX_CHUNK_TOKENS,
) -> list[PageTaggedChunk]:
    """Top-level entry: PDF bytes → page-tagged chunks.

    Calls pypdf for per-page text + page rect, then runs
    ``chunk_markdown`` per page, stamping page + proportional bbox on
    every chunk.

    No-op gracefully when pypdf isn't installed (returns empty list +
    raises the import error so callers can surface it). The decorator
    pattern means the underlying chunker still works for non-PDF text;
    PDF callers route through here.
    """
    try:
        from pypdf import PdfReader
    except ImportError as e:  # pragma: no cover — same surface as extract_pdf
        raise ImportError(
            "processing.chunking.pdf_chunker requires pypdf. "
            "Same install as services.ingestion.extractors.pdf."
        ) from e

    reader = PdfReader(io.BytesIO(pdf_bytes))
    out: list[PageTaggedChunk] = []
    for page_index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001
            text = ""
        text = text.strip()
        if not text:
            continue

        page_rect = _page_rect_for(page)
        sub_chunks = chunk_markdown(text, max_chunk_tokens=max_chunk_tokens)
        total = len(sub_chunks)
        for idx, c in enumerate(sub_chunks):
            bbox = _proportional_bbox(
                chunk_index=idx,
                total_chunks_on_page=total,
                page_rect=page_rect,
            )
            out.append(PageTaggedChunk(chunk=c, page=page_index, bbox=bbox))
    return out


def chunk_pdf_extraction(
    extraction,  # services.ingestion.extractors.pdf.PdfExtraction
    *,
    max_chunk_tokens: int = DEFAULT_MAX_CHUNK_TOKENS,
) -> list[PageTaggedChunk]:
    """Same as ``chunk_pdf_bytes`` but takes an already-extracted
    ``PdfExtraction`` so callers that already invoked the extractor
    don't pay for a second pypdf pass.

    The page rect is unavailable here because PdfExtraction doesn't
    carry it; falls back to DEFAULT_PAGE_RECT for every page. The
    overlap-resolution math still works (every chunk gets a distinct
    band), just with a US-Letter assumption. When pypdf-page-rects
    are surfaced through PdfExtraction, swap the default for the real
    value.
    """
    out: list[PageTaggedChunk] = []
    for page in extraction.pages:
        if not page.text.strip():
            continue
        sub_chunks = chunk_markdown(
            page.text, max_chunk_tokens=max_chunk_tokens
        )
        total = len(sub_chunks)
        for idx, c in enumerate(sub_chunks):
            bbox = _proportional_bbox(
                chunk_index=idx,
                total_chunks_on_page=total,
                page_rect=DEFAULT_PAGE_RECT,
            )
            out.append(
                PageTaggedChunk(chunk=c, page=page.page_index, bbox=bbox)
            )
    return out


__all__ = [
    "CHUNKER_VERSION",
    "DEFAULT_PAGE_RECT",
    "PageTaggedChunk",
    "chunk_pdf_bytes",
    "chunk_pdf_extraction",
]
