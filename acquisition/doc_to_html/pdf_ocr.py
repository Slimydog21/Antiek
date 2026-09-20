"""OCR fallback for scanned / thin-text PDFs (doc→HTML).

Prefer local DeepSeek-OCR-2 (``substrate.research_bridge.ocr``) when the
VLM service is reachable, then brew CLIs — no invented cloud OCR infra:

1. **DeepSeek-OCR-2** via OpenAI-compatible endpoint (``ocr_available``)
2. ``ocrmypdf`` CLI (Tesseract under the hood) → ``--sidecar`` text
3. else ``pdftoppm`` + ``tesseract`` per page

Gated by ``ocr_cli_available`` (DeepSeek probe and/or binary presence).
This path feeds ``document_reader_html`` sidecars after pypdf text-layer
fails (#3186 / #3190 residual).

Cite: docs/decisions/pdf-html-pypdf-fallback-2026-09-19.md;
docs/decisions/pdf-ocr-html-2026-09-19.md;
docs/decisions/pdf-deepseek-ocr-html-prefer-2026-09-19.md.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

CONVERTER_ENGINE_DEEPSEEK = "deepseek_ocr"
CONVERTER_ENGINE_OCRMYPDF = "ocrmypdf"
CONVERTER_ENGINE_TESSERACT = "tesseract"
CONVERTER_VERSION_OCR = "local-ocr/1.1.0"

# Default OCR wall clock — scanned pages are slow; override via env.
DEFAULT_OCR_TIMEOUT_S = float(os.environ.get("ANTIEK_PDF_OCR_TIMEOUT_S", "120"))
# Cap pages rasterized via pdftoppm+tesseract so a 500-page scan cannot wedge ingest.
DEFAULT_MAX_OCR_PAGES = int(os.environ.get("ANTIEK_PDF_OCR_MAX_PAGES", "40"))


def _which(env_key: str, fallback: str) -> str | None:
    pinned = os.environ.get(env_key, "").strip()
    if pinned:
        return pinned if os.path.isfile(pinned) and os.access(pinned, os.X_OK) else None
    return shutil.which(fallback)


def ocrmypdf_bin() -> str | None:
    return _which("OCRMYPDF_BIN", "ocrmypdf")


def tesseract_bin() -> str | None:
    return _which("TESSERACT_BIN", "tesseract")


def pdftoppm_bin() -> str | None:
    return _which("PDFTOPPM_BIN", "pdftoppm")


def deepseek_ocr_available() -> bool:
    """True when DeepSeek-OCR-2 service can run (env-gated, never raises)."""
    if os.environ.get("ANTIEK_PDF_OCR_DEEPSEEK", "1").strip().lower() in {
        "0",
        "false",
        "off",
        "no",
    }:
        return False
    try:
        from substrate.research_bridge.ocr import ocr_available

        return bool(ocr_available())
    except Exception as exc:  # pragma: no cover — import/probe soft-fail
        logger.debug("DeepSeek OCR probe failed: %s", exc)
        return False


def ocr_cli_available() -> bool:
    """True when at least one OCR path can run (DeepSeek or brew CLIs)."""
    if os.environ.get("ANTIEK_PDF_OCR", "1").strip().lower() in {"0", "false", "off", "no"}:
        return False
    if deepseek_ocr_available():
        return True
    if ocrmypdf_bin():
        return True
    return bool(tesseract_bin() and pdftoppm_bin())


def ocr_unavailable_reason() -> str:
    if os.environ.get("ANTIEK_PDF_OCR", "1").strip().lower() in {"0", "false", "off", "no"}:
        return "ANTIEK_PDF_OCR disabled"
    if deepseek_ocr_available():
        return ""
    missing = []
    if not ocrmypdf_bin():
        missing.append("ocrmypdf")
    if not tesseract_bin():
        missing.append("tesseract")
    if not pdftoppm_bin():
        missing.append("pdftoppm")
    if missing == ["ocrmypdf"] and tesseract_bin() and pdftoppm_bin():
        return ""  # tesseract path still OK
    if not missing:
        return ""
    ds_note = "DeepSeek-OCR-2 unreachable; "
    return (
        ds_note
        + "local OCR tools missing: "
        + ", ".join(missing)
        + ". Start DeepSeek OCR (ANTIEK_OCR_BASE_URL) or install: "
        "brew install tesseract ocrmypdf poppler "
        "(see docs/decisions/pdf-deepseek-ocr-html-prefer-2026-09-19.md)"
    )


def run_pdf_ocr(
    path: Path,
    *,
    timeout: float | None = None,
    max_output_bytes: int = 16 * 1024 * 1024,
    max_pages: int | None = None,
) -> tuple[str, str] | None:
    """OCR a PDF to markdown-ish plain text.

    Returns ``(text, engine)`` where engine is ``deepseek_ocr``, ``ocrmypdf``,
    or ``tesseract``, or ``None`` when unavailable / empty / failed.
    Prefer DeepSeek when reachable; never invents text.
    """
    if not ocr_cli_available():
        logger.info("PDF OCR skipped for %s: %s", path.name, ocr_unavailable_reason())
        return None
    timeout_s = float(timeout if timeout is not None else DEFAULT_OCR_TIMEOUT_S)
    page_cap = int(max_pages if max_pages is not None else DEFAULT_MAX_OCR_PAGES)

    if deepseek_ocr_available():
        got = _run_deepseek_ocr(
            path, timeout_s=timeout_s, max_output=max_output_bytes, max_pages=page_cap
        )
        if got:
            return got, CONVERTER_ENGINE_DEEPSEEK
        logger.info(
            "DeepSeek OCR empty/failed for %s — falling back to ocrmypdf/tesseract",
            path.name,
        )

    if ocrmypdf_bin():
        got = _run_ocrmypdf(path, timeout_s=timeout_s, max_output=max_output_bytes)
        if got:
            return got, CONVERTER_ENGINE_OCRMYPDF

    if tesseract_bin() and pdftoppm_bin():
        got = _run_tesseract_pdftoppm(
            path, timeout_s=timeout_s, max_output=max_output_bytes, max_pages=page_cap
        )
        if got:
            return got, CONVERTER_ENGINE_TESSERACT

    return None


def _run_deepseek_ocr(
    path: Path,
    *,
    timeout_s: float,
    max_output: int,
    max_pages: int,
) -> str | None:
    """Prefer DeepSeek-OCR-2 for scanned PDFs (page-capped, never invents)."""
    try:
        from substrate.research_bridge.ocr import OcrError, ocr_image, raster_dpi
    except Exception as exc:
        logger.debug("DeepSeek OCR import failed: %s", exc)
        return None
    try:
        import pypdfium2 as pdfium  # type: ignore[import-untyped]
    except ImportError:
        logger.debug("pypdfium2 missing — cannot rasterize for DeepSeek OCR")
        return None

    import io
    import time

    try:
        data = path.read_bytes()
    except OSError as exc:
        logger.warning("DeepSeek OCR could not read %s: %s", path.name, exc)
        return None
    if not data:
        return None

    dpi = raster_dpi()
    # Soft wall-clock: VLM OCR is slow; stop after timeout_s even mid-doc.
    deadline = time.monotonic() + max(1.0, timeout_s)
    parts: list[str] = []
    try:
        pdf = pdfium.PdfDocument(io.BytesIO(data))
    except Exception as exc:
        logger.debug("DeepSeek OCR open failed for %s: %s", path.name, exc)
        return None
    try:
        n_pages = len(pdf)
        if n_pages == 0:
            return None
        limit = min(n_pages, max(1, max_pages))
        for page_index in range(limit):
            if time.monotonic() > deadline:
                logger.warning(
                    "DeepSeek OCR hit timeout after page %s of %s",
                    page_index,
                    path.name,
                )
                break
            page = pdf[page_index]
            try:
                bitmap = page.render(scale=dpi / 72.0)
                pil = bitmap.to_pil()
                buf = io.BytesIO()
                pil.save(buf, format="PNG")
                page_md = ocr_image(buf.getvalue(), mime="image/png")
            except OcrError as exc:
                logger.debug(
                    "DeepSeek OCR page %s failed for %s: %s",
                    page_index + 1,
                    path.name,
                    exc,
                )
                continue
            except Exception as exc:
                logger.debug(
                    "DeepSeek OCR raster page %s failed for %s: %s",
                    page_index + 1,
                    path.name,
                    exc,
                )
                continue
            piece = (page_md or "").strip()
            if piece:
                parts.append(f"## Page {page_index + 1}\n\n{piece}")
    finally:
        pdf.close()

    joined = _nonempty("\n\n".join(parts))
    if joined is None:
        return None
    raw = joined.encode("utf-8")
    if len(raw) > max_output:
        joined = raw[:max_output].decode("utf-8", errors="ignore")
    return joined



def _nonempty(text: str | None) -> str | None:
    if text is None:
        return None
    stripped = text.strip()
    return stripped if stripped else None


def _run_ocrmypdf(path: Path, *, timeout_s: float, max_output: int) -> str | None:
    bin_path = ocrmypdf_bin()
    if not bin_path:
        return None
    with tempfile.TemporaryDirectory(prefix="antiek-ocrmypdf-") as tmp:
        tmp_path = Path(tmp)
        sidecar = tmp_path / "sidecar.txt"
        # output-type none + stdout placeholder: we only want the sidecar text.
        cmd = [
            bin_path,
            "--force-ocr",
            "-l",
            os.environ.get("ANTIEK_PDF_OCR_LANG", "eng"),
            "--output-type",
            "none",
            "--sidecar",
            str(sidecar),
            "-q",
            str(path),
            "-",  # required when output-type is none (ocrmypdf ≥17)
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            logger.warning("ocrmypdf timed out after %.1fs for %s", timeout_s, path.name)
            return None
        except FileNotFoundError:
            logger.warning("ocrmypdf binary vanished: %s", bin_path)
            return None
        if result.returncode != 0:
            logger.debug(
                "ocrmypdf exited %d for %s: %s",
                result.returncode,
                path.name,
                (result.stderr or "")[:500],
            )
            return None
        if not sidecar.is_file():
            return None
        text = sidecar.read_text(encoding="utf-8", errors="replace")
        nonempty = _nonempty(text)
        if nonempty is None:
            return None
        text = nonempty
        raw = text.encode("utf-8")
        if len(raw) > max_output:
            text = raw[:max_output].decode("utf-8", errors="ignore")
        # Light markdown: page breaks from ocrmypdf sidecar are form-feeds often.
        return text.replace("\f", "\n\n---\n\n")


def _run_tesseract_pdftoppm(
    path: Path,
    *,
    timeout_s: float,
    max_output: int,
    max_pages: int,
) -> str | None:
    ppm = pdftoppm_bin()
    tess = tesseract_bin()
    if not ppm or not tess:
        return None
    with tempfile.TemporaryDirectory(prefix="antiek-tess-") as tmp:
        tmp_path = Path(tmp)
        prefix = tmp_path / "page"
        # Rasterize (PNG). -f/-l limit pages.
        cmd_ppm = [
            ppm,
            "-png",
            "-r",
            os.environ.get("ANTIEK_PDF_OCR_DPI", "200"),
            "-f",
            "1",
            "-l",
            str(max(1, max_pages)),
            str(path),
            str(prefix),
        ]
        try:
            r1 = subprocess.run(
                cmd_ppm, capture_output=True, text=True, timeout=timeout_s
            )
        except subprocess.TimeoutExpired:
            logger.warning("pdftoppm timed out for %s", path.name)
            return None
        except FileNotFoundError:
            return None
        if r1.returncode != 0:
            logger.debug("pdftoppm failed for %s: %s", path.name, (r1.stderr or "")[:300])
            return None
        pages = sorted(tmp_path.glob("page*.png"))
        if not pages:
            return None
        chunks: list[str] = []
        per_page_timeout = max(15.0, timeout_s / max(len(pages), 1))
        for i, img in enumerate(pages[:max_pages], start=1):
            cmd_t = [
                tess,
                str(img),
                "stdout",
                "-l",
                os.environ.get("ANTIEK_PDF_OCR_LANG", "eng"),
                "--psm",
                "3",
            ]
            try:
                r2 = subprocess.run(
                    cmd_t, capture_output=True, text=True, timeout=per_page_timeout
                )
            except subprocess.TimeoutExpired:
                logger.warning("tesseract timed out on page %s of %s", i, path.name)
                continue
            except FileNotFoundError:
                return None
            if r2.returncode != 0:
                continue
            piece = (r2.stdout or "").strip()
            if piece:
                chunks.append(f"## Page {i}\n\n{piece}")
        joined = _nonempty("\n\n".join(chunks))
        if joined is None:
            return None
        raw = joined.encode("utf-8")
        if len(raw) > max_output:
            joined = raw[:max_output].decode("utf-8", errors="ignore")
        return joined
