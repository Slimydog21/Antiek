"""SPR-03 M5 — OA "PDF" that is really an HTML landing page / paywall.

The 2026-05-29 prod run found 6 of 15 OA "PDF" links were HTML landing pages
served 200-OK (bytes leading b'<!DO'). The shared layered detector
(acquisition.openaccess.pdf_detect) rejects them as a COUNTED per-item failure
(NotAPdf), never a crash and never an ingest. The three layers:

  1. Content-Type — text/html or text/plain is rejected.
  2. Magic bytes — a real PDF leads %PDF-; HTML leads <!DO / <htm / <?xm.
  3. pdf-parse — a %PDF--prefixed but truncated/corrupt body fails pypdf.

These tests exercise each layer on REAL leading bytes, prove a real PDF passes,
and prove a rejection in the OA download path is per-item (the run continues).
"""

from __future__ import annotations

import os
import sys

import httpx
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.books.public_domain import text_to_pdf  # noqa: E402
from acquisition.openaccess import unpaywall  # noqa: E402
from acquisition.openaccess.pdf_detect import (  # noqa: E402
    NotAPdf,
    assert_pdf,
    is_pdf,
    looks_like_pdf_bytes,
)

# A structurally-valid PDF (passes all three layers incl. pypdf parse).
_REAL_PDF = text_to_pdf("This is a genuine open-access paper body. " * 30, title="OA")

# The exact prod failure: an HTML landing page leading b'<!DO'.
_HTML_LANDING = b"<!DOCTYPE html>\n<html><head><title>Paywall</title></head>"

# A %PDF--prefixed but truncated/corrupt body — passes layers 1+2, fails 3.
_TRUNCATED_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF-but-no-xref-or-trailer"


# ---------------------------------------------------------------------------
# Layer-by-layer rejection on real bytes
# ---------------------------------------------------------------------------


def test_layer1_html_content_type_rejected():
    """A text/html Content-Type is rejected even before the byte sniff."""
    with pytest.raises(NotAPdf) as exc:
        # Bytes look like a PDF, but the content-type betrays the landing page.
        assert_pdf(_REAL_PDF, content_type="text/html; charset=utf-8")
    assert "Content-Type" in str(exc.value)


def test_layer2_html_magic_bytes_rejected():
    """The b'<!DO' leading bytes (the prod case) are rejected — even with no /
    a misleading content-type."""
    with pytest.raises(NotAPdf) as exc:
        assert_pdf(_HTML_LANDING, content_type=None)
    assert "HTML/XML" in str(exc.value)
    # And the pure-bytes predicate agrees.
    assert looks_like_pdf_bytes(_HTML_LANDING) is False


def test_layer2_missing_magic_rejected():
    """Bytes that are neither HTML nor %PDF- (e.g. a JSON error body) reject on
    the missing %PDF- signature."""
    with pytest.raises(NotAPdf) as exc:
        assert_pdf(b'{"error":"not found"}', content_type="application/json")
    assert "%PDF-" in str(exc.value)


def test_layer3_truncated_pdf_rejected():
    """A %PDF--prefixed but corrupt/truncated body passes layers 1+2 but fails
    the pypdf parse — caught before it lands as a 0-page husk."""
    # Layers 1+2 pass (it leads %PDF-, content-type is fine)...
    assert looks_like_pdf_bytes(_TRUNCATED_PDF) is True
    # ...but the full check (with parse) rejects it.
    with pytest.raises(NotAPdf) as exc:
        assert_pdf(_TRUNCATED_PDF, content_type="application/pdf")
    assert "parse" in str(exc.value).lower() or "corrupt" in str(exc.value).lower()


def test_real_pdf_passes_all_layers():
    """A genuine PDF passes every layer (no exception); is_pdf agrees."""
    assert_pdf(_REAL_PDF, content_type="application/pdf")  # no raise
    assert is_pdf(_REAL_PDF, content_type="application/pdf") is True
    assert looks_like_pdf_bytes(_REAL_PDF) is True


def test_leading_whitespace_tolerated_on_real_pdf():
    """A stray leading newline before %PDF- (some servers prepend one) is
    tolerated — the head is lstrip'd before the magic-byte check."""
    assert looks_like_pdf_bytes(b"\n\r\n" + _REAL_PDF) is True


# ---------------------------------------------------------------------------
# The rejection is a COUNTED per-item failure in the live OA download path
# ---------------------------------------------------------------------------


def test_oa_download_pdf_raises_notapdf_on_landing_page():
    """unpaywall.download_pdf (the live OA fetch path) raises NotAPdf — a
    counted, recoverable per-item miss — when handed an HTML landing page."""

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=_HTML_LANDING, headers={"content-type": "text/html"},
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(_handler))
    with pytest.raises(NotAPdf):
        unpaywall.download_pdf("https://oa.example/landing.html", client=client)
    client.close()


def test_notapdf_is_recoverable_run_continues():
    """A NotAPdf on one URL is per-item: a caller iterating candidate URLs
    falls through to the next and the run continues (no uncaught exception).
    This mirrors the orchestrator's per-URL fallthrough behavior."""
    urls = {
        "https://oa.example/landing.html": (_HTML_LANDING, "text/html"),
        "https://oa.example/real.pdf": (_REAL_PDF, "application/pdf"),
    }

    def _handler(request: httpx.Request) -> httpx.Response:
        body, ct = urls[str(request.url)]
        return httpx.Response(200, content=body, headers={"content-type": ct}, request=request)

    client = httpx.Client(transport=httpx.MockTransport(_handler))

    got = None
    misses = 0
    for u in ("https://oa.example/landing.html", "https://oa.example/real.pdf"):
        try:
            got = unpaywall.download_pdf(u, client=client)
            break
        except NotAPdf:
            misses += 1
            continue
    client.close()

    assert misses == 1  # the landing page was a counted miss
    assert got == _REAL_PDF  # the run recovered onto the real PDF


def test_real_pdf_passes_oa_download_path():
    """A genuine PDF flows through download_pdf unchanged."""

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=_REAL_PDF, headers={"content-type": "application/pdf"},
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(_handler))
    out = unpaywall.download_pdf("https://oa.example/real.pdf", client=client)
    client.close()
    assert out == _REAL_PDF
