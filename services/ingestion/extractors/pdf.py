"""PDF extractor for the unified ingestion pipeline.

Uses ``pypdf`` (already a project optional-dep). Extracts page-by-page
text + a coarse title heuristic (the PDF metadata title, falling back
to the first line of the first page).

Image-only PDFs (scanned documents where there's no text layer) are
flagged in ``ExtractedDocument.metadata['ocr_required'] = True`` and
the page count + raw images count is recorded for diagnostic value.
OCR is OUT of scope per the sprint spec — we flag, we don't run it.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class PdfPage:
    page_index: int  # 1-based
    text: str
    word_count: int


@dataclass(frozen=True)
class PdfExtraction:
    title: Optional[str]
    author: Optional[str]
    pages: list[PdfPage] = field(default_factory=list)
    word_count: int = 0
    text: str = ""
    ocr_required: bool = False


def extract_pdf(*, pdf_bytes: bytes) -> PdfExtraction:
    """Extract a PDF byte blob → per-page text + metadata."""
    try:
        from pypdf import PdfReader
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "services.ingestion.extractors.pdf requires pypdf. "
            "Run `pip install -e '.[pdf]'` to install it."
        ) from e

    reader = PdfReader(io.BytesIO(pdf_bytes))
    info = reader.metadata or {}
    title = (info.get("/Title") or info.get("title") or "").strip() or None
    author = (info.get("/Author") or info.get("author") or "").strip() or None

    pages: list[PdfPage] = []
    full_text_parts: list[str] = []
    for idx, page in enumerate(reader.pages, start=1):
        try:
            t = page.extract_text() or ""
        except Exception:  # noqa: BLE001 — some pages raise on extract
            t = ""
        t = t.strip()
        words = t.split()
        pages.append(PdfPage(page_index=idx, text=t, word_count=len(words)))
        if t:
            full_text_parts.append(t)
    total_words = sum(p.word_count for p in pages)

    # Title fallback: first line of first non-empty page.
    if not title:
        for p in pages:
            if p.text:
                line = p.text.splitlines()[0].strip() if p.text.splitlines() else ""
                if line:
                    title = line[:200]
                    break

    ocr_required = total_words < 20 and len(pages) > 0

    return PdfExtraction(
        title=title,
        author=author,
        pages=pages,
        word_count=total_words,
        text="\n\n".join(full_text_parts),
        ocr_required=ocr_required,
    )
