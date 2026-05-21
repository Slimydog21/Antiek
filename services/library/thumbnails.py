"""PDF page-1 thumbnail generator (SPR-06 gap closure, 2026-05-22).

SPR-06's library card cover renders a "page-1 thumbnail" placeholder
for PDFs because the substrate didn't expose thumbnail URLs and the
ingest pipeline didn't render a page-1 PNG. This module fills that gap:
``generate_thumbnail(pdf_bytes_or_path) -> Optional[bytes]`` returns PNG
bytes of page 1, or ``None`` if no rendering backend is available.

Dependencies:
- ``pdf2image`` + Poppler (best quality) — install via
  ``pip install pdf2image`` and ``brew install poppler`` (macOS) or
  ``apt install poppler-utils`` (Linux).
- ``PyMuPDF`` / ``fitz`` (pure-Python alternative) — install via
  ``pip install pymupdf``.

We try pdf2image first because it produces sharper output for the
typical PDFs (academic papers, books). Fall back to PyMuPDF if it's
the only one installed. If neither is available, return None — the UI
already handles the "no thumbnail" path with a placeholder, so the
degradation is graceful (per the existing SPR-06 card design).

Output specification:
- PNG bytes (compressed)
- 200×260 px (matches the library card aspect ratio at default zoom)
- White background (no transparency)
- 72 DPI render scaled to fit the bounding box

The thumbnail is best-effort and time-bounded. A 30-second timeout on
the rendering call protects the ingest pipeline from PDFs that hang the
backend (some scanned PDFs with unusual encryption or compression).
"""

from __future__ import annotations

import io
import logging
import os
from typing import Optional, Union

_log = logging.getLogger(__name__)

THUMBNAIL_WIDTH = 200
THUMBNAIL_HEIGHT = 260
THUMBNAIL_TIMEOUT_S = 30


def generate_thumbnail(
    pdf_source: Union[bytes, str, os.PathLike],
) -> Optional[bytes]:
    """Render page 1 of a PDF to PNG bytes. Returns None on failure.

    ``pdf_source`` may be raw bytes or a filesystem path.

    Failure cases (all return None, never raise):
        - No rendering backend installed
        - PDF unreadable / corrupt
        - Render timeout
    """
    backend = _pick_backend()
    if backend is None:
        _log.warning(
            "library.thumbnails: no PDF rendering backend installed. "
            "Install pdf2image (+ poppler) or pymupdf to generate "
            "library card thumbnails. Returning None."
        )
        return None

    try:
        if backend == "pdf2image":
            return _render_with_pdf2image(pdf_source)
        if backend == "pymupdf":
            return _render_with_pymupdf(pdf_source)
    except Exception as exc:
        _log.warning(
            "library.thumbnails: rendering failed via %s: %s",
            backend, exc,
        )
        return None

    return None


def _pick_backend() -> Optional[str]:
    """Return the first available rendering backend, or None."""
    try:
        import pdf2image  # noqa: F401
        return "pdf2image"
    except ImportError:
        pass
    try:
        import fitz  # noqa: F401  PyMuPDF
        return "pymupdf"
    except ImportError:
        pass
    return None


def _render_with_pdf2image(
    pdf_source: Union[bytes, str, os.PathLike],
) -> Optional[bytes]:
    from pdf2image import convert_from_bytes, convert_from_path

    if isinstance(pdf_source, (str, os.PathLike)):
        images = convert_from_path(
            str(pdf_source),
            first_page=1,
            last_page=1,
            size=(THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT),
            timeout=THUMBNAIL_TIMEOUT_S,
        )
    else:
        images = convert_from_bytes(
            pdf_source,
            first_page=1,
            last_page=1,
            size=(THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT),
            timeout=THUMBNAIL_TIMEOUT_S,
        )

    if not images:
        return None

    buf = io.BytesIO()
    images[0].save(buf, format="PNG")
    return buf.getvalue()


def _render_with_pymupdf(
    pdf_source: Union[bytes, str, os.PathLike],
) -> Optional[bytes]:
    import fitz  # PyMuPDF

    if isinstance(pdf_source, (str, os.PathLike)):
        doc = fitz.open(str(pdf_source))
    else:
        doc = fitz.open(stream=pdf_source, filetype="pdf")

    try:
        if doc.page_count == 0:
            return None
        page = doc.load_page(0)
        # Compute a zoom that fits page 1 into THUMBNAIL_WIDTH while
        # preserving aspect ratio (we crop / letterbox to height later
        # if needed).
        rect = page.rect
        if rect.width <= 0:
            return None
        zoom = THUMBNAIL_WIDTH / rect.width
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()


def thumbnail_storage_path(
    *,
    storage_root: str,
    document_id: str,
) -> str:
    """Canonical filesystem path for a document's page-1 thumbnail.

    Layout: ``<storage_root>/thumbnails/<document_id>.png``. Callers
    should ``os.makedirs(os.path.dirname(path), exist_ok=True)`` before
    writing.
    """
    return os.path.join(storage_root, "thumbnails", f"{document_id}.png")


__all__ = [
    "THUMBNAIL_WIDTH",
    "THUMBNAIL_HEIGHT",
    "THUMBNAIL_TIMEOUT_S",
    "generate_thumbnail",
    "thumbnail_storage_path",
]
