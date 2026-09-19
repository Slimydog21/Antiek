"""Document-to-canonical-HTML ingestion pipeline (Antiek doc→HTML S-D2H).

Converts documents (PDF, DOCX, EPUB, PPTX, XLSX, CSV, ODT, RTF, HTML, MD,
TXT) to sanitized canonical HTML for the Antiek reader surface. Uses the
anydoc → docling → pypdf → OCR (DeepSeek preferred, else ocrmypdf/tesseract) for reader-HTML sidecars.
"""

from .converter import (
    ANYDOC_BIN,
    BLOCKED_DOMAINS,
    DOCLING_BIN,
    ConversionError,
    FairUseError,
    convert_to_markdown,
    convert_to_markdown_with_engine,
    ingest_asset,
)

__all__ = [
    "ANYDOC_BIN",
    "BLOCKED_DOMAINS",
    "ConversionError",
    "DOCLING_BIN",
    "FairUseError",
    "convert_to_markdown",
    "convert_to_markdown_with_engine",
    "ingest_asset",
]
