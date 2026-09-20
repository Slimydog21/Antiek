"""DeepSeek-OCR-2 — local VLM OCR client + extractor integration.

Mechanical gates:
  A. client: enable/disable env, availability probe caching, model
     resolution (explicit env; auto-pick prefers deepseek-ocr-2 q8_0)
  B. ocr_image: request shape (image-first, default prompt, max_tokens),
     response parse, bare-HTML-table → GFM normalization, failure modes
     (HTTP error, timeout, empty content, non-JSON)
  C. ocr_pdf: pypdfium2 rasterization drives one OCR call per page with
     ``## Page N`` anchors; the image payload is a real PNG data URL
  D. extractors integration: images and scanned PDFs route to
     deepseek-ocr2 when available and fail honestly when not
"""

from __future__ import annotations

import base64
import io
import json
import sys
from collections.abc import Callable, Generator
from types import ModuleType

import httpx
import pytest

from substrate.research_bridge import extractors, ocr
from substrate.research_bridge.extractors import (
    SUPPORTED_EXTENSIONS,
    extract_text,
)


def _png_bytes() -> bytes:
    """A 1x1 transparent PNG (valid rasterizer-independent fixture)."""
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )


def _blank_pdf_bytes() -> bytes:
    """One-page PDF with no text layer (pypdf writes no content stream)."""
    import pypdf

    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


class _FakeOcr(ModuleType):
    """Stand-in for substrate.research_bridge.ocr used by extractor tests."""

    OcrError = ocr.OcrError
    CONVERTER_VERSION_OCR = ocr.CONVERTER_VERSION_OCR

    def __init__(
        self, *, available: bool = True, markdown: str = "# OCR", error: Exception | None = None
    ):
        super().__init__("ocr")
        self.available = available
        self.markdown = markdown
        self.error = error
        self.calls: list[tuple[bytes, str]] = []

    @property
    def IMAGE_MIME(self) -> dict[str, str]:  # noqa: N802
        return ocr.IMAGE_MIME

    def base_url(self) -> str:
        return "http://127.0.0.1:9/v1"

    def ocr_available(self) -> bool:
        return self.available

    def ocr_pdf(self, data: bytes, **kwargs: object) -> str:
        self.calls.append((data, "pdf"))
        if self.error is not None:
            raise self.error
        return self.markdown

    def ocr_image(self, data: bytes, *, mime: str = "image/png", **kwargs: object) -> str:
        self.calls.append((data, mime))
        if self.error is not None:
            raise self.error
        return self.markdown


def _mock_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    """httpx.Client with a MockTransport AND a base URL (the real factory
    sets base_url; a relative-path POST without one fails before the
    handler runs)."""
    return httpx.Client(base_url="http://test.local", transport=httpx.MockTransport(handler))


def _install_fake_ocr(monkeypatch: pytest.MonkeyPatch, fake: _FakeOcr | None = None) -> _FakeOcr:
    import substrate.research_bridge as _pkg

    binding = fake or _FakeOcr()
    monkeypatch.setitem(sys.modules, "substrate.research_bridge.ocr", binding)
    # ``from substrate.research_bridge import ocr`` resolves the package
    # ATTRIBUTE first (set to the real module on first import), so the
    # package attr must be replaced too — sys.modules alone is not enough.
    monkeypatch.setattr(_pkg, "ocr", binding)
    monkeypatch.setattr(extractors, "ocr", binding, raising=False)
    return binding


@pytest.fixture(autouse=True)
def _no_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None]:
    for key in (
        "ANTIEK_OCR_ENABLED",
        "ANTIEK_OCR_BASE_URL",
        "ANTIEK_OCR_MODEL",
        "ANTIEK_OCR_API_KEY",
        "ANTIEK_OCR_TIMEOUT_S",
        "ANTIEK_OCR_RASTER_DPI",
        "ANTIEK_OCR_IMAGE_FIRST",
    ):
        monkeypatch.delenv(key, raising=False)
    ocr.reset_cache()
    yield
    ocr.reset_cache()


# ---------------------------------------------------------------------------
# A. availability + model resolution
# ---------------------------------------------------------------------------


def test_disabled_via_env_never_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTIEK_OCR_ENABLED", "0")

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request may be made when disabled")

    monkeypatch.setattr(ocr, "_client_factory", lambda: _mock_client(handler))
    assert ocr.ocr_available() is False


def test_available_probes_models_and_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={"data": [{"id": "deepseek-ocr-2@q8_0"}]})

    monkeypatch.setattr(ocr, "_client_factory", lambda: _mock_client(handler))
    assert ocr.ocr_available() is True
    assert ocr.ocr_available() is True  # cached — no second probe
    assert calls == ["/models"]


def test_unreachable_service_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    monkeypatch.setattr(ocr, "_client_factory", lambda: _mock_client(handler))
    assert ocr.ocr_available() is False


def test_resolve_model_explicit_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTIEK_OCR_MODEL", "my-server/ocr")
    assert ocr.resolve_model() == "my-server/ocr"


def test_resolve_model_prefers_v2_q8(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "models": [
                    {"model": "/models/DeepSeek-OCR-2/deepseek-ocr-2-q4_k_m.gguf"},
                    {"model": "/models/DeepSeek-OCR-2/deepseek-ocr-2-q8_0.gguf"},
                    {"model": "/models/DeepSeek-OCR/deepseek-ocr-v1.gguf"},
                ]
            },
        )

    monkeypatch.setattr(ocr, "_client_factory", lambda: _mock_client(handler))
    assert "q8_0" in ocr.resolve_model()


def test_resolve_model_falls_back_to_v1(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": "deepseek-ocr"}]})

    monkeypatch.setattr(ocr, "_client_factory", lambda: _mock_client(handler))
    assert ocr.resolve_model() == "deepseek-ocr"


def test_resolve_model_no_match_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": "llama-3.2"}]})

    monkeypatch.setattr(ocr, "_client_factory", lambda: _mock_client(handler))
    with pytest.raises(ocr.OcrError, match="no DeepSeek-OCR model"):
        ocr.resolve_model()


# ---------------------------------------------------------------------------
# B. ocr_image
# ---------------------------------------------------------------------------


def test_ocr_image_request_shape_and_success(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "# Done\n\nBody."}}]})

    monkeypatch.setattr(ocr, "_client_factory", lambda: _mock_client(handler))
    monkeypatch.setattr(ocr, "resolve_model", lambda: "deepseek-ocr-2@q8_0")

    result = ocr.ocr_image(_png_bytes(), mime="image/png")

    assert result == "# Done\n\nBody."
    body = captured["body"]
    assert body["model"] == "deepseek-ocr-2@q8_0"
    assert body["temperature"] == 0.0
    assert body["max_tokens"] == 8192
    content = body["messages"][0]["content"]
    assert len(content) == 2
    # Image FIRST (llama.cpp serves DeepSeek-OCR-2 only image-first).
    assert content[0]["type"] == "image_url"
    assert content[0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert content[1] == {"type": "text", "text": "Convert the document to markdown."}


def test_ocr_image_normalizes_html_table(monkeypatch: pytest.MonkeyPatch) -> None:
    _pin_resolve_model(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "<table><tr><td>A</td><td>B</td></tr><tr><td>1</td><td>2</td></tr></table>"
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(ocr, "_client_factory", lambda: _mock_client(handler))
    result = ocr.ocr_image(_png_bytes())
    assert "| A | B |" in result
    assert "| 1 | 2 |" in result
    assert "---" in result


def _pin_resolve_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr, "resolve_model", lambda: "deepseek-ocr-2@q8_0")


def test_ocr_image_http_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _pin_resolve_model(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    monkeypatch.setattr(ocr, "_client_factory", lambda: _mock_client(handler))
    with pytest.raises(ocr.OcrError, match="request failed"):
        ocr.ocr_image(_png_bytes())


def test_ocr_image_timeout_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _pin_resolve_model(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    monkeypatch.setattr(ocr, "_client_factory", lambda: _mock_client(handler))
    with pytest.raises(ocr.OcrError, match="timed out"):
        ocr.ocr_image(_png_bytes())


def test_ocr_image_whitespace_content_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _pin_resolve_model(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "   "}}]})

    monkeypatch.setattr(ocr, "_client_factory", lambda: _mock_client(handler))
    assert ocr.ocr_image(_png_bytes()) == ""


def test_ocr_image_missing_content_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _pin_resolve_model(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {}}]})

    monkeypatch.setattr(ocr, "_client_factory", lambda: _mock_client(handler))
    with pytest.raises(ocr.OcrError, match="unexpected"):
        ocr.ocr_image(_png_bytes())


# ---------------------------------------------------------------------------
# C. ocr_pdf
# ---------------------------------------------------------------------------


def test_ocr_pdf_rasterizes_each_page(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/models":
            return httpx.Response(200, json={"data": [{"id": "deepseek-ocr-2@q8_0"}]})
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "Page body"}}]})

    monkeypatch.setattr(ocr, "_client_factory", lambda: _mock_client(handler))

    result = ocr.ocr_pdf(_blank_pdf_bytes(), dpi=72)

    assert result.startswith("## Page 1")
    assert "Page body" in result
    assert len(captured) == 1
    data_url = captured[0]["messages"][0]["content"][0]["image_url"]["url"]
    assert data_url.startswith("data:image/png;base64,")
    png = base64.b64decode(data_url.split(",", 1)[1])
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_ocr_pdf_unopenable_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ocr.OcrError, match="rasterization"):
        ocr.ocr_pdf(b"not a pdf at all")


# ---------------------------------------------------------------------------
# D. extractors integration
# ---------------------------------------------------------------------------


def test_image_extracts_via_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _install_fake_ocr(monkeypatch, _FakeOcr(markdown="# Scan\n\nText."))

    result = extract_text(_png_bytes(), filename="scan.png")

    assert result.ok
    assert result.extractor == "deepseek-ocr2"
    assert result.kind == "markdown"
    assert result.converter_version == ocr.CONVERTER_VERSION_OCR
    assert result.text == "# Scan\n\nText."
    assert fake.calls == [(_png_bytes(), "image/png")]
    assert "png" in SUPPORTED_EXTENSIONS


def test_image_ocr_unavailable_fails_honestly(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_ocr(monkeypatch, _FakeOcr(available=False))

    result = extract_text(_png_bytes(), filename="scan.png")

    assert not result.ok
    assert "OCR unavailable" in result.reason
    assert "ANTIEK_OCR_ENABLED=0" in result.reason


def test_scanned_pdf_escalates_to_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _install_fake_ocr(monkeypatch, _FakeOcr(markdown="## Page 1\n\nScan body"))

    result = extract_text(_blank_pdf_bytes(), filename="scan.pdf")

    assert result.ok
    assert result.extractor == "deepseek-ocr2"
    assert result.kind == "pdf"
    assert result.degraded is True
    assert fake.calls == [(_blank_pdf_bytes(), "pdf")]


def test_scanned_pdf_ocr_unavailable_stays_honest(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_ocr(monkeypatch, _FakeOcr(available=False))

    result = extract_text(_blank_pdf_bytes(), filename="scan.pdf")

    assert not result.ok
    assert "no extractable text layer" in result.reason
    assert "DeepSeek-OCR-2 service is unavailable" in result.reason


def test_scanned_pdf_ocr_error_reports_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_ocr(monkeypatch, _FakeOcr(error=ocr.OcrError("server exploded")))

    result = extract_text(_blank_pdf_bytes(), filename="scan.pdf")

    assert not result.ok
    assert "scanned PDF OCR failed: server exploded" in result.reason


def _text_pdf_bytes() -> bytes:
    """A minimal single-page PDF WITH a text layer (hand-built; no extra deps)."""
    content = b"BT /F1 12 Tf 72 720 Td (Hello from a text layer) Tj ET"
    stream = (
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream"
    )
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        stream,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return out.getvalue()


def test_text_pdf_never_touches_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _install_fake_ocr(monkeypatch, _FakeOcr())

    result = extract_text(_text_pdf_bytes(), filename="text.pdf")

    assert result.ok and result.extractor == "pypdf"
    assert "Hello from a text layer" in result.text
    assert fake.calls == []
