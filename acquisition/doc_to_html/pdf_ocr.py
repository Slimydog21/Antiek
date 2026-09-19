"""Local OCR fallback for scanned / thin-text PDFs (doc→HTML).

Uses tools already on the host — no invented cloud OCR infra:

1. ``ocrmypdf`` CLI (Tesseract under the hood) → ``--sidecar`` text
2. else ``pdftoppm`` + ``tesseract`` per page

Gated by binary presence (``ocr_cli_available``). DeepSeek-OCR-2 remains on
the research_bridge arm; this path is for ``document_reader_html`` sidecars
after pypdf text-layer fails (#3186 residual).

Cite: docs/decisions/pdf-html-pypdf-fallback-2026-09-19.md;
docs/decisions/pdf-ocr-html-2026-09-19.md.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

CONVERTER_ENGINE_OCRMYPDF = "ocrmypdf"
CONVERTER_ENGINE_TESSERACT = "tesseract"
CONVERTER_VERSION_OCR = "local-ocr/1.0.0"

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


def ocr_cli_available() -> bool:
    """True when at least one local OCR path can run."""
    if os.environ.get("ANTIEK_PDF_OCR", "1").strip().lower() in {"0", "false", "off", "no"}:
        return False
    if ocrmypdf_bin():
        return True
    return bool(tesseract_bin() and pdftoppm_bin())


def ocr_unavailable_reason() -> str:
    if os.environ.get("ANTIEK_PDF_OCR", "1").strip().lower() in {"0", "false", "off", "no"}:
        return "ANTIEK_PDF_OCR disabled"
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
    return (
        "local OCR tools missing: "
        + ", ".join(missing)
        + ". Install: brew install tesseract ocrmypdf poppler "
        "(see docs/decisions/pdf-ocr-html-2026-09-19.md)"
    )


def run_pdf_ocr(
    path: Path,
    *,
    timeout: float | None = None,
    max_output_bytes: int = 16 * 1024 * 1024,
    max_pages: int | None = None,
) -> tuple[str, str] | None:
    """OCR a PDF to markdown-ish plain text.

    Returns ``(text, engine)`` where engine is ``ocrmypdf`` or ``tesseract``,
    or ``None`` when unavailable / empty / failed. Never invents text.
    """
    if not ocr_cli_available():
        logger.info("PDF OCR skipped for %s: %s", path.name, ocr_unavailable_reason())
        return None
    timeout_s = float(timeout if timeout is not None else DEFAULT_OCR_TIMEOUT_S)
    page_cap = int(max_pages if max_pages is not None else DEFAULT_MAX_OCR_PAGES)

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
        text = _nonempty(text)
        if text is None:
            return None
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
