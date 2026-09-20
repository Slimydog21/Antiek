"""DRW SPR-08 M1 — text extraction from arbitrary uploaded files.

Honest supported-type matrix:

    .txt / .md      plain UTF-8 decode                 — clean
    .html / .htm    html2text (falls back to bs4)      — clean
    .pdf            pypdf text layer, then DeepSeek-OCR-2   — text PDFs clean;
                    fallback for scanned/image PDFs (no     OCR flagged degraded
                    text layer) when the local OCR service
                    is reachable
    .png/.jpg/.jpeg/
    .webp/.bmp/.tif/
    .tiff/.gif      DeepSeek-OCR-2 local VLM (image OCR)    — clean for scans,
                                                              photos, handwriting
    Office / ODF /
    RTF / CSV       optional firecrawl-anydoc binding  — clean GFM markdown
    other / binary  UNSUPPORTED                         — fails loudly

A failed extraction returns ``ok=False`` with a reason; the caller turns that
into a clear user message rather than poisoning the graph with garbage text.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version
from typing import Protocol, cast

CONVERTER_VERSION_ANYDOC = "anydoc/0.1.6"

# Python's anydoc binding accepts canonical format names rather than every
# filename alias understood by the Rust core.
_ANYDOC_FORMAT_BY_EXTENSION = {
    "doc": "doc",
    "docx": "docx",
    "docm": "docx",
    "ppt": "ppt",
    "pps": "ppt",
    "pot": "ppt",
    "pptx": "pptx",
    "pptm": "pptx",
    "ppsx": "pptx",
    "ppsm": "pptx",
    "xlsx": "xlsx",
    "xls": "xlsx",
    "xlsm": "xlsx",
    "xlsb": "xlsx",
    "odt": "odt",
    "ods": "ods",
    "odp": "odp",
    "rtf": "rtf",
    "csv": "csv",
}

# Image inputs are OCR'd by the local DeepSeek-OCR-2 VLM (substrate.research_bridge.ocr).
_IMAGE_EXTENSIONS = ("png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff", "gif")

_IMAGE_CONTENT_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/bmp": "bmp",
    "image/tiff": "tif",
    "image/gif": "gif",
}

_CONTENT_TYPE_EXTENSIONS = {
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.ms-word.document.macroenabled.12": "docm",
    "application/vnd.ms-powerpoint": "ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/vnd.ms-powerpoint.presentation.macroenabled.12": "pptm",
    "application/vnd.openxmlformats-officedocument.presentationml.slideshow": "ppsx",
    "application/vnd.ms-powerpoint.slideshow.macroenabled.12": "ppsm",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-excel.sheet.macroenabled.12": "xlsm",
    "application/vnd.ms-excel.sheet.binary.macroenabled.12": "xlsb",
    "application/vnd.oasis.opendocument.text": "odt",
    "application/vnd.oasis.opendocument.spreadsheet": "ods",
    "application/vnd.oasis.opendocument.presentation": "odp",
    "application/rtf": "rtf",
    "text/rtf": "rtf",
    "text/csv": "csv",
    "application/csv": "csv",
    **_IMAGE_CONTENT_TYPES,
    # EPUB is intentionally recognized only so it fails closed instead of
    # reaching UTF-8 sniffing; its authorized acquisition path owns conversion.
    "application/epub+zip": "epub",
}

SUPPORTED_EXTENSIONS = (
    "txt",
    "md",
    "markdown",
    "text",
    "html",
    "htm",
    "pdf",
    *_IMAGE_EXTENSIONS,
    *_ANYDOC_FORMAT_BY_EXTENSION,
)
# Documented as degrading rather than clean — surfaced in the result.
DEGRADING_EXTENSIONS = ("pdf", *_IMAGE_EXTENSIONS)


class _AnydocBinding(Protocol):
    def to_markdown_bytes(
        self,
        data: bytes | bytearray,
        format: str | None = None,
    ) -> str: ...


@dataclass(frozen=True)
class ExtractionResult:
    ok: bool
    text: str = ""
    kind: str = ""  # normalized type tag (markdown|text|html|pdf)
    extractor: str = ""  # which path produced the text
    degraded: bool = False  # true if the type may extract incompletely
    reason: str = ""  # failure reason when ok=False
    converter_version: str = ""  # byte-to-text converter identity


def _ext_of(filename: str | None, content_type: str | None) -> str:
    if filename and "." in filename:
        return filename.rsplit(".", 1)[1].lower()
    if content_type:
        ct = content_type.partition(";")[0].strip().lower()
        if ct in _CONTENT_TYPE_EXTENSIONS:
            return _CONTENT_TYPE_EXTENSIONS[ct]
        if "html" in ct:
            return "html"
        if "pdf" in ct:
            return "pdf"
        if "markdown" in ct:
            return "md"
        if "text" in ct:
            return "txt"
    return ""


def _anydoc_converter_version() -> str:
    try:
        installed_version = distribution_version("firecrawl-anydoc")
    except PackageNotFoundError:
        # Hermetic tests inject only the binding module; the locked production
        # extra resolves 0.1.6, so the declared base remains an honest fallback.
        return CONVERTER_VERSION_ANYDOC
    return f"anydoc/{installed_version}"


def extract_text(
    data: str | bytes | bytearray,
    *,
    filename: str | None = None,
    content_type: str | None = None,
) -> ExtractionResult:
    """Extract text from ``data`` (bytes or str). Dispatches on extension /
    content-type. Never raises on a bad file — returns ``ok=False``."""
    ext = _ext_of(filename, content_type)
    if ext in ("txt", "text", "md", "markdown"):
        return _decode(
            data,
            kind="markdown" if ext in ("md", "markdown") else "text",
            extractor="utf8",
        )
    if ext in ("html", "htm"):
        return _extract_html(data)
    if ext == "pdf":
        return _extract_pdf(data)
    if ext in _IMAGE_EXTENSIONS:
        return _extract_image(data, filename=filename, content_type=content_type)
    if ext in _ANYDOC_FORMAT_BY_EXTENSION:
        return _extract_via_anydoc(data, filename=filename, content_type=content_type)
    if not ext:
        # Last resort: try UTF-8; many pasted files are text without an ext.
        res = _decode(data, kind="text", extractor="utf8-sniff")
        if res.ok and res.text.strip():
            return res
        return ExtractionResult(ok=False, reason="unknown file type; could not detect text")
    return ExtractionResult(ok=False, reason=f"unsupported file type: .{ext}")


def _extract_via_anydoc(
    data: str | bytes | bytearray,
    *,
    filename: str | None,
    content_type: str | None,
) -> ExtractionResult:
    ext = _ext_of(filename, content_type)
    format_hint = _ANYDOC_FORMAT_BY_EXTENSION.get(ext)
    if format_hint is None:
        return ExtractionResult(ok=False, reason=f"unsupported file type: .{ext}")

    converter_version = _anydoc_converter_version()
    try:
        anydoc = cast(_AnydocBinding, import_module("anydoc"))
    except ImportError:
        return ExtractionResult(
            ok=False,
            kind="markdown",
            extractor="anydoc",
            converter_version=converter_version,
            reason="install the 'docs' extra (firecrawl-anydoc) to ingest Office/ODF/RTF/CSV",
        )

    payload = data if isinstance(data, (bytes, bytearray)) else data.encode("utf-8")
    try:
        markdown = anydoc.to_markdown_bytes(payload, format_hint)
    except Exception as exc:
        return ExtractionResult(
            ok=False,
            kind="markdown",
            extractor="anydoc",
            converter_version=converter_version,
            degraded=True,
            reason=f"anydoc could not convert .{ext}: {type(exc).__name__}",
        )

    if not markdown.strip():
        return ExtractionResult(
            ok=False,
            kind="markdown",
            extractor="anydoc",
            converter_version=converter_version,
            degraded=True,
            reason=f".{ext} converted to empty markdown (no extractable content)",
        )
    return ExtractionResult(
        ok=True,
        text=markdown,
        kind="markdown",
        extractor="anydoc",
        converter_version=converter_version,
    )


def _decode(
    data: str | bytes | bytearray,
    *,
    kind: str,
    extractor: str,
) -> ExtractionResult:
    if isinstance(data, str):
        return ExtractionResult(ok=True, text=data, kind=kind, extractor=extractor)
    try:
        return ExtractionResult(
            ok=True,
            text=data.decode("utf-8"),
            kind=kind,
            extractor=extractor,
        )
    except UnicodeDecodeError:
        try:
            return ExtractionResult(
                ok=True,
                text=data.decode("utf-8", errors="replace"),
                kind=kind,
                extractor=extractor + "-lossy",
                degraded=True,
            )
        except Exception:
            return ExtractionResult(ok=False, reason="undecodable bytes (broken encoding)")


def _extract_html(data: str | bytes | bytearray) -> ExtractionResult:
    raw = data if isinstance(data, str) else data.decode("utf-8", errors="replace")
    try:
        import html2text

        h = html2text.HTML2Text()
        h.ignore_links = False
        return ExtractionResult(ok=True, text=h.handle(raw), kind="html", extractor="html2text")
    except ImportError:  # pragma: no cover — bs4 fallback
        try:
            from bs4 import BeautifulSoup

            return ExtractionResult(
                ok=True,
                text=BeautifulSoup(raw, "html.parser").get_text("\n"),
                kind="html",
                extractor="bs4",
            )
        except ImportError:
            return ExtractionResult(
                ok=False,
                reason="no HTML extractor (html2text/bs4) available",
            )


def _extract_pdf(data: str | bytes | bytearray) -> ExtractionResult:
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
        # Scanned/image PDF with no text layer — escalate to the local
        # DeepSeek-OCR-2 service when it is reachable, otherwise stay
        # honest about the degrade (never pretend OCR happened).
        return _ocr_scanned_pdf(data)
    return ExtractionResult(
        ok=True,
        text=text,
        kind="pdf",
        extractor="pypdf",
        degraded=True,
    )  # text PDFs can still drop layout/tables


def _ocr_scanned_pdf(data: str | bytes | bytearray) -> ExtractionResult:
    """Scanned/image-only PDF → DeepSeek-OCR-2 (rasterize + OCR every page).

    Opportunistic: when the local OCR service is unreachable the result is
    the historical honest failure (augmented with the actionable reason),
    never a silent no-op and never a fake success.
    """
    from substrate.research_bridge import ocr

    if not ocr.ocr_available():
        return ExtractionResult(
            ok=False,
            kind="pdf",
            extractor="pypdf",
            degraded=True,
            reason=(
                "PDF has no extractable text layer (scanned/image PDF) and the "
                f"DeepSeek-OCR-2 service is unavailable at {ocr.base_url()} "
                "(start the OCR server, set ANTIEK_OCR_BASE_URL, or disable OCR "
                "with ANTIEK_OCR_ENABLED=0)"
            ),
        )
    payload = data if isinstance(data, (bytes, bytearray)) else data.encode("utf-8")
    try:
        markdown = ocr.ocr_pdf(payload)
    except ocr.OcrError as exc:
        return ExtractionResult(
            ok=False,
            kind="pdf",
            extractor="deepseek-ocr2",
            converter_version=ocr.CONVERTER_VERSION_OCR,
            degraded=True,
            reason=f"scanned PDF OCR failed: {exc}",
        )
    if not markdown.strip():
        return ExtractionResult(
            ok=False,
            kind="pdf",
            extractor="deepseek-ocr2",
            converter_version=ocr.CONVERTER_VERSION_OCR,
            degraded=True,
            reason="scanned PDF OCR returned empty markdown",
        )
    return ExtractionResult(
        ok=True,
        text=markdown,
        kind="pdf",
        extractor="deepseek-ocr2",
        converter_version=ocr.CONVERTER_VERSION_OCR,
        degraded=True,
    )  # OCR can drop layout/hallucinate — flagged honest


def _extract_image(
    data: str | bytes | bytearray,
    *,
    filename: str | None,
    content_type: str | None,
) -> ExtractionResult:
    """Image (scan/photo/screenshot) → DeepSeek-OCR-2 VLM → Markdown."""
    from substrate.research_bridge import ocr

    ext = _ext_of(filename, content_type)
    mime = ocr.IMAGE_MIME.get(ext, "image/png")
    if not ocr.ocr_available():
        return ExtractionResult(
            ok=False,
            kind="markdown",
            extractor="deepseek-ocr2",
            degraded=True,
            reason=(
                f"image OCR unavailable: no DeepSeek-OCR-2 service at {ocr.base_url()} "
                "(start the OCR server, set ANTIEK_OCR_BASE_URL, or disable OCR "
                "with ANTIEK_OCR_ENABLED=0)"
            ),
        )
    payload = data if isinstance(data, (bytes, bytearray)) else data.encode("utf-8")
    try:
        markdown = ocr.ocr_image(payload, mime=mime)
    except ocr.OcrError as exc:
        return ExtractionResult(
            ok=False,
            kind="markdown",
            extractor="deepseek-ocr2",
            converter_version=ocr.CONVERTER_VERSION_OCR,
            degraded=True,
            reason=f"image OCR failed: {exc}",
        )
    if not markdown.strip():
        return ExtractionResult(
            ok=False,
            kind="markdown",
            extractor="deepseek-ocr2",
            converter_version=ocr.CONVERTER_VERSION_OCR,
            degraded=True,
            reason="image OCR returned empty markdown",
        )
    return ExtractionResult(
        ok=True,
        text=markdown,
        kind="markdown",
        extractor="deepseek-ocr2",
        converter_version=ocr.CONVERTER_VERSION_OCR,
        degraded=True,
    )  # OCR can drop layout/hallucinate — flagged honest
