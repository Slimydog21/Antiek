"""DeepSeek-OCR-2 — local vision-language OCR for the Antiek substrate.

Talks to an OpenAI-compatible server running the DeepSeek-OCR-2 VLM
(llama.cpp ``llama-server`` on :1235 is the verified reference; LM Studio
or any compatible endpoint also works). Used by ``extractors.py`` as the
scanned-document / image arm of universal ingest:

* image files (png/jpg/jpeg/webp/bmp/tif/tiff/gif) → ``ocr_image``
* scanned/image-only PDFs (no text layer) → ``ocr_pdf`` rasterizes each
  page with pypdfium2 and OCRs the pages in order.

Honesty contract (mirrors ``extractors.ExtractionResult``): every failure
is an exception-free ``OcrError`` with a reason the caller turns into a
clear user message; nothing is ever silently substituted. The service is
opportunistic — when it is not reachable the caller keeps its previous
behavior (with a reason that says OCR was unavailable, not that OCR is
out of scope).

Request format is the verified-working one from the deepseek-ocr CLI
(2026-08-11): prompt ``Convert the document to markdown.`` (the official
model-card instruction; deterministic), image part FIRST (llama.cpp
serves DeepSeek-OCR-2 correctly only in that order), temperature 0.

Config (env):
    ANTIEK_OCR_ENABLED        "0" disables the OCR path entirely (default "1")
    ANTIEK_OCR_BASE_URL       OpenAI-compatible base URL (default
                              http://127.0.0.1:1235/v1 — the llama.cpp v2 server)
    ANTIEK_OCR_MODEL          explicit model id (default: auto-picked from
                              /v1/models, preferring deepseek-ocr-2 q8_0)
    ANTIEK_OCR_API_KEY        Bearer token for authenticated endpoints (optional)
    ANTIEK_OCR_TIMEOUT_S      per-request timeout, default 300 (VLM OCR is slow)
    ANTIEK_OCR_RASTER_DPI     PDF rasterization DPI, default 200
    ANTIEK_OCR_IMAGE_FIRST    "0" restores text-first order for servers that
                              require it (default "1" — image first)
"""

from __future__ import annotations

import base64
import io
import os
import time
from html.parser import HTMLParser
from typing import Any

import httpx

CONVERTER_VERSION_OCR = "deepseek-ocr2/1.0.0"

DEFAULT_BASE_URL = "http://127.0.0.1:1235/v1"
DEFAULT_PROMPT = "Convert the document to markdown."
DEFAULT_MAX_TOKENS = 8192
DEFAULT_TIMEOUT_S = 300.0
DEFAULT_RASTER_DPI = 200
PROBE_TIMEOUT_S = 1.5
_CACHE_TTL_S = 30.0

# Extension → image MIME for the data URL.
IMAGE_MIME: dict[str, str] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "bmp": "image/bmp",
    "tif": "image/tiff",
    "tiff": "image/tiff",
    "gif": "image/gif",
}

# model id → (preferred?) — auto-pick prefers DeepSeek-OCR-2 with q8_0
# quantization, then any DeepSeek-OCR-2, then any deepseek-ocr.
_MODEL_PREFERENCE = (
    ("deepseek-ocr-2", "q8_0"),
    ("deepseek-ocr-2", ""),
    ("deepseek-ocr", ""),
)


class OcrError(Exception):
    """Raised when OCR cannot run or the service failed. ``str(exc)`` is a
    user-presentable reason."""


# Module-level cache: (timestamp, payload) for availability, model list and
# resolved model id, so a fast-failing probe is not repeated on every upload.
_cache: dict[str, tuple[float, Any]] = {}


def _cache_get(key: str) -> Any:
    hit = _cache.get(key)
    if hit is None:
        return None
    ts, value = hit
    if time.monotonic() - ts > _CACHE_TTL_S:
        _cache.pop(key, None)
        return None
    return value


def _cache_set(key: str, value: Any) -> None:
    _cache[key] = (time.monotonic(), value)


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def enabled() -> bool:
    """OCR path enabled? ``ANTIEK_OCR_ENABLED=0`` opts out (default on)."""
    return _env("ANTIEK_OCR_ENABLED", "1") != "0"


def base_url() -> str:
    return _env("ANTIEK_OCR_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def timeout_s() -> float:
    try:
        return float(_env("ANTIEK_OCR_TIMEOUT_S", str(DEFAULT_TIMEOUT_S)))
    except ValueError:
        return DEFAULT_TIMEOUT_S


def raster_dpi() -> int:
    try:
        return max(72, int(_env("ANTIEK_OCR_RASTER_DPI", str(DEFAULT_RASTER_DPI))))
    except ValueError:
        return DEFAULT_RASTER_DPI


def api_key() -> str:
    return _env("ANTIEK_OCR_API_KEY", "")


# Test seam: replaced by tests with an httpx.Client using MockTransport.
def _client_factory() -> httpx.Client:
    return httpx.Client(
        base_url=base_url(),
        timeout=httpx.Timeout(
            connect=PROBE_TIMEOUT_S, read=timeout_s(), write=timeout_s(), pool=PROBE_TIMEOUT_S
        ),
        headers={"Authorization": f"Bearer {api_key()}"} if api_key() else {},
    )


def _models() -> list[str]:
    """Model ids advertised by the server (OpenAI ``id`` or llama.cpp ``model``)."""
    cached = _cache_get("models")
    if cached is not None:
        return [str(m) for m in cached]
    try:
        with _client_factory() as client:
            resp = client.get(
                "/models",
                timeout=httpx.Timeout(
                    connect=PROBE_TIMEOUT_S,
                    read=PROBE_TIMEOUT_S,
                    write=PROBE_TIMEOUT_S,
                    pool=PROBE_TIMEOUT_S,
                ),
            )
            resp.raise_for_status()
            payload = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OcrError(
            f"DeepSeek-OCR-2 service unreachable at {base_url()}: {type(exc).__name__}"
        ) from exc
    if not isinstance(payload, dict):
        raise OcrError("DeepSeek-OCR-2 returned a non-object model list")
    raw_items = payload.get("data") or payload.get("models") or []
    ids: list[str] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        for key in ("id", "model", "name"):
            value = item.get(key)
            if isinstance(value, str) and value:
                ids.append(value)
                break
    _cache_set("models", ids)
    return ids


def ocr_available() -> bool:
    """True iff the OCR path can run right now (service up + model present).
    Cached briefly; never raises — a dead service reads as unavailable."""
    if not enabled():
        return False
    cached = _cache_get("available")
    if cached is not None:
        return bool(cached)
    try:
        models = _models()
        ok = bool(models)
    except OcrError:
        ok = False
    _cache_set("available", ok)
    return bool(ok)


def resolve_model() -> str:
    """Model id to send. ``ANTIEK_OCR_MODEL`` wins; otherwise auto-pick from
    the server's model list preferring DeepSeek-OCR-2 q8_0."""
    explicit = _env("ANTIEK_OCR_MODEL", "")
    if explicit:
        return explicit
    cached = _cache_get("model_id")
    if cached is not None:
        return str(cached)
    models = _models()
    chosen: str | None = None
    for needle, qualifier in _MODEL_PREFERENCE:
        matches = [
            m for m in models if needle in m.lower() and (not qualifier or qualifier in m.lower())
        ]
        if matches:
            chosen = sorted(matches)[0]
            break
    if chosen is None:
        raise OcrError(
            f"no DeepSeek-OCR model advertised by the server at {base_url()} "
            f"(saw {sorted(models)[:5]!r}); set ANTIEK_OCR_MODEL explicitly"
        )
    _cache_set("model_id", chosen)
    return chosen


def _normalize_html_table(md: str) -> str:
    """If the model answered with a bare HTML <table>, convert it to GFM so
    the 'returns Markdown' contract holds. Anything else passes through
    untouched (fidelity over rewriting)."""

    class _TableParser(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.rows: list[list[str]] = []
            self.cur_row: list[str] | None = None
            self.cur_cell: list[str] | None = None

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag == "table":
                self.cur_row = None
            elif tag == "tr":
                self.cur_row = []
            elif tag in ("td", "th") and self.cur_row is not None:
                self.cur_cell = []

        def handle_endtag(self, tag: str) -> None:
            if tag in ("td", "th") and self.cur_cell is not None and self.cur_row is not None:
                self.cur_row.append("".join(self.cur_cell).strip())
                self.cur_cell = None
            elif tag == "tr" and self.cur_row is not None:
                self.rows.append(self.cur_row)
                self.cur_row = None

        def handle_data(self, data: str) -> None:
            if self.cur_cell is not None:
                self.cur_cell.append(data)

    s = md.strip()
    if not (s.startswith("<table") and s.endswith("</table>")):
        return md
    p = _TableParser()
    p.feed(s)
    if not p.rows:
        return md
    ncols = max(len(r) for r in p.rows)
    lines: list[str] = []
    for i, row in enumerate(p.rows):
        cells = [
            c.replace("|", "\\|").replace("\n", " ") for c in (row + [""] * (ncols - len(row)))
        ]
        lines.append("| " + " | ".join(cells) + " |")
        if i == 0:
            lines.append("|" + "|".join("---" for _ in row) + "|")
    return "\n".join(lines)


def _chat_completion(image_data_url: str, prompt: str) -> str:
    image_first = _env("ANTIEK_OCR_IMAGE_FIRST", "1") != "0"
    image_part = {"type": "image_url", "image_url": {"url": image_data_url}}
    text_part = {"type": "text", "text": prompt}
    content = [image_part, text_part] if image_first else [text_part, image_part]
    body = {
        "model": resolve_model(),
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.0,
        "max_tokens": DEFAULT_MAX_TOKENS,
    }
    try:
        with _client_factory() as client:
            resp = client.post("/chat/completions", json=body)
            resp.raise_for_status()
            payload = resp.json()
    except httpx.TimeoutException as exc:
        raise OcrError(
            f"DeepSeek-OCR-2 request timed out after {timeout_s():.0f}s: {type(exc).__name__}"
        ) from exc
    except httpx.HTTPError as exc:
        raise OcrError(f"DeepSeek-OCR-2 request failed: {type(exc).__name__}") from exc
    except ValueError as exc:
        raise OcrError("DeepSeek-OCR-2 returned non-JSON") from exc
    try:
        content_out = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise OcrError(f"unexpected DeepSeek-OCR-2 response: {str(payload)[:300]}") from exc
    if not isinstance(content_out, str):
        raise OcrError(f"unexpected DeepSeek-OCR-2 content type: {type(content_out).__name__}")
    return _normalize_html_table(content_out.strip())


def ocr_image(
    data: bytes | bytearray, *, mime: str = "image/png", prompt: str = DEFAULT_PROMPT
) -> str:
    """OCR a single image; returns Markdown. Raises ``OcrError`` on any
    failure (empty/error response included)."""
    if not data:
        raise OcrError("empty image payload")
    data_url = f"data:{mime};base64,{base64.b64encode(bytes(data)).decode()}"
    return _chat_completion(data_url, prompt)


def ocr_pdf(
    data: bytes | bytearray, *, dpi: int | None = None, prompt: str = DEFAULT_PROMPT
) -> str:
    """Rasterize every page of a PDF (pypdfium2) and OCR each page in order.

    Returns Markdown with ``## Page N`` anchors so the chunker sees
    structural anchors instead of one blob (mirrors the books reader lane).
    Raises ``OcrError`` on rasterization or OCR failure."""
    try:
        import pypdfium2 as pdfium  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover — guarded by the pdf extra
        raise OcrError(
            "pypdfium2 not installed (add the 'pdf' extra) for PDF rasterization"
        ) from exc
    dpi = dpi or raster_dpi()
    parts: list[str] = []
    try:
        pdf = pdfium.PdfDocument(io.BytesIO(bytes(data)))
    except Exception as exc:
        raise OcrError(f"PDF rasterization failed to open: {type(exc).__name__}") from exc
    try:
        if len(pdf) == 0:
            raise OcrError("PDF has no pages")
        for page_index in range(len(pdf)):
            page = pdf[page_index]
            bitmap = page.render(scale=dpi / 72.0)
            pil = bitmap.to_pil()
            buf = io.BytesIO()
            pil.save(buf, format="PNG")
            page_md = ocr_image(buf.getvalue(), mime="image/png", prompt=prompt)
            parts.append(f"## Page {page_index + 1}\n\n{page_md}")
    finally:
        pdf.close()
    return "\n\n".join(parts).strip()


def reset_cache() -> None:
    """Test seam: drop the availability/model caches."""
    _cache.clear()
