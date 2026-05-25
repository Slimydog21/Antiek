"""DRW SPR-08 M1 — text extraction from arbitrary uploaded files.

Honest supported-type matrix (rigor #1) — only libs ALREADY in the project
are used; no heavy OCR/docx deps are added:

    .txt / .md      plain UTF-8 decode                 — clean
    .html / .htm    html2text (falls back to bs4)      — clean
    .pdf            pypdf text layer                   — clean for text PDFs;
                                                          scanned/image PDFs
                                                          yield little/no text
                                                          (degrades, flagged)
    .docx / .rtf    UNSUPPORTED (no python-docx/striprtf installed) — fails
                    loudly with a clear message, never silently ingests junk
    other / binary  UNSUPPORTED                          — fails loudly

A failed extraction returns ``ok=False`` with a reason; the caller turns that
into a clear user message rather than poisoning the graph with garbage text.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

SUPPORTED_EXTENSIONS = ("txt", "md", "markdown", "text", "html", "htm", "pdf")
# Documented as degrading rather than clean — surfaced in the result.
DEGRADING_EXTENSIONS = ("pdf",)


@dataclass(frozen=True)
class ExtractionResult:
    ok: bool
    text: str = ""
    kind: str = ""           # normalized type tag (markdown|text|html|pdf)
    extractor: str = ""      # which path produced the text
    degraded: bool = False   # true if the type may extract incompletely
    reason: str = ""         # failure reason when ok=False


def _ext_of(filename: Optional[str], content_type: Optional[str]) -> str:
    if filename and "." in filename:
        return filename.rsplit(".", 1)[1].lower()
    if content_type:
        ct = content_type.lower()
        if "html" in ct:
            return "html"
        if "pdf" in ct:
            return "pdf"
        if "markdown" in ct:
            return "md"
        if "text" in ct:
            return "txt"
    return ""


def extract_text(
    data, *, filename: Optional[str] = None, content_type: Optional[str] = None,
) -> ExtractionResult:
    """Extract text from ``data`` (bytes or str). Dispatches on extension /
    content-type. Never raises on a bad file — returns ``ok=False``."""
    ext = _ext_of(filename, content_type)
    if ext in ("txt", "text", "md", "markdown"):
        return _decode(data, kind="markdown" if ext in ("md", "markdown") else "text",
                       extractor="utf8")
    if ext in ("html", "htm"):
        return _extract_html(data)
    if ext == "pdf":
        return _extract_pdf(data)
    if ext in ("docx", "rtf", "doc"):
        return ExtractionResult(ok=False, reason=(
            f".{ext} is unsupported (no extractor lib installed). Convert to "
            f"PDF/Markdown/HTML/TXT and re-upload."))
    if not ext:
        # Last resort: try UTF-8; many pasted files are text without an ext.
        res = _decode(data, kind="text", extractor="utf8-sniff")
        if res.ok and res.text.strip():
            return res
        return ExtractionResult(ok=False, reason="unknown file type; could not detect text")
    return ExtractionResult(ok=False, reason=f"unsupported file type: .{ext}")


def _decode(data, *, kind: str, extractor: str) -> ExtractionResult:
    if isinstance(data, str):
        return ExtractionResult(ok=True, text=data, kind=kind, extractor=extractor)
    try:
        return ExtractionResult(ok=True, text=data.decode("utf-8"), kind=kind, extractor=extractor)
    except UnicodeDecodeError:
        try:
            return ExtractionResult(ok=True, text=data.decode("utf-8", errors="replace"),
                                    kind=kind, extractor=extractor + "-lossy", degraded=True)
        except Exception:
            return ExtractionResult(ok=False, reason="undecodable bytes (broken encoding)")


def _extract_html(data) -> ExtractionResult:
    raw = data if isinstance(data, str) else data.decode("utf-8", errors="replace")
    try:
        import html2text
        h = html2text.HTML2Text()
        h.ignore_links = False
        return ExtractionResult(ok=True, text=h.handle(raw), kind="html", extractor="html2text")
    except ImportError:  # pragma: no cover — bs4 fallback
        try:
            from bs4 import BeautifulSoup
            return ExtractionResult(ok=True, text=BeautifulSoup(raw, "html.parser").get_text("\n"),
                                    kind="html", extractor="bs4")
        except ImportError:
            return ExtractionResult(ok=False, reason="no HTML extractor (html2text/bs4) available")


def _extract_pdf(data) -> ExtractionResult:
    import io
    try:
        import pypdf
    except ImportError:  # pragma: no cover
        return ExtractionResult(ok=False, reason="pypdf not available for PDF extraction")
    buf = io.BytesIO(data if isinstance(data, (bytes, bytearray)) else data.encode("utf-8"))
    try:
        reader = pypdf.PdfReader(buf)
        parts = [(page.extract_text() or "") for page in reader.pages]
    except Exception as exc:
        return ExtractionResult(ok=False, reason=f"PDF parse failed: {type(exc).__name__}")
    text = "\n\n".join(p for p in parts if p.strip())
    if not text.strip():
        # Scanned/image PDF with no text layer — honest about the degrade.
        return ExtractionResult(ok=False, kind="pdf", extractor="pypdf", degraded=True,
                                reason="PDF has no extractable text layer (scanned/image PDF; OCR is out of scope)")
    return ExtractionResult(ok=True, text=text, kind="pdf", extractor="pypdf",
                            degraded=True)  # text PDFs can still drop layout/tables
