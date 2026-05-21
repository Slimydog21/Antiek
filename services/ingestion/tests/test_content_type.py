"""Tests for content-type detection (SPR-03 / M2).

Coverage:

- 8 representative URLs (2 of each type) classify correctly via URL
  pattern alone (no network).
- HEAD request fallback dispatches on Content-Type header.
- Ambiguous URLs default to HTML article.
- EPUB detection via mime.
"""

from __future__ import annotations

import os
import sys

import httpx
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from services.ingestion import content_type as ct


def test_arxiv_abs_url_detected_offline():
    res = ct.detect("https://arxiv.org/abs/2402.03300", do_head=False)
    assert res.content_type == ct.ARXIV
    assert res.via == "url_pattern"


def test_arxiv_pdf_url_detected_offline():
    res = ct.detect("https://arxiv.org/pdf/2402.03300", do_head=False)
    assert res.content_type == ct.ARXIV
    assert res.via == "url_pattern"


def test_arxiv_export_host_detected_offline():
    res = ct.detect("https://export.arxiv.org/abs/2402.03300v2", do_head=False)
    assert res.content_type == ct.ARXIV
    assert res.via == "url_pattern"


def test_pdf_url_extension_detected_offline():
    res = ct.detect("https://example.com/paper.pdf", do_head=False)
    assert res.content_type == ct.PDF
    assert res.via == "url_pattern"


def test_pdf_url_with_query_detected_offline():
    res = ct.detect("https://files.example.com/doc.pdf?download=1", do_head=False)
    assert res.content_type == ct.PDF


def test_epub_url_extension_detected_offline():
    res = ct.detect("https://example.com/book.epub", do_head=False)
    assert res.content_type == ct.EPUB
    assert res.via == "url_pattern"


def test_epub_url_with_path_detected_offline():
    res = ct.detect("https://standardebooks.org/some/book.epub", do_head=False)
    assert res.content_type == ct.EPUB


def test_html_url_defaults_when_no_head():
    """Ambiguous URL with do_head=False → HTML article (the spec's
    documented default)."""
    res = ct.detect("https://example.com/article", do_head=False)
    assert res.content_type == ct.HTML_ARTICLE
    assert res.via == "default"


# ---------------------------------------------------------------------------
# 8-URL classification gate from the sprint spec M2
# ---------------------------------------------------------------------------


def test_eight_urls_classify_correctly():
    """Spec acceptance: 8 URLs (2 of each type) classified correctly."""
    cases = [
        # arXiv (2)
        ("https://arxiv.org/abs/2402.03300", ct.ARXIV),
        ("https://arxiv.org/pdf/2402.03300v2", ct.ARXIV),
        # PDF (2)
        ("https://example.com/paper.pdf", ct.PDF),
        ("https://files.example.com/doc.pdf?download=1", ct.PDF),
        # EPUB (2)
        ("https://standardebooks.org/some/book.epub", ct.EPUB),
        ("https://example.com/book.epub#chapter1", ct.EPUB),
        # HTML article (2) — these need do_head=False since we can't
        # call out in this test; falling through to "default" gives
        # HTML article, which is what the spec asks for on ambiguity.
        ("https://example.com/article", ct.HTML_ARTICLE),
        ("https://blog.example.com/post-title", ct.HTML_ARTICLE),
    ]
    for url, expected in cases:
        res = ct.detect(url, do_head=False)
        assert res.content_type == expected, f"{url} → {res.content_type}, want {expected}"


# ---------------------------------------------------------------------------
# HEAD request dispatch
# ---------------------------------------------------------------------------


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)


def test_head_dispatches_to_pdf_on_mime():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.method == "HEAD"
        return httpx.Response(200, headers={"content-type": "application/pdf"})
    res = ct.detect(
        "https://example.com/no-extension-but-pdf",
        client=_mock_client(handler),
    )
    assert res.content_type == ct.PDF
    assert res.via == "head_request"


def test_head_dispatches_to_epub_on_mime():
    def handler(req): return httpx.Response(
        200, headers={"content-type": "application/epub+zip"},
    )
    res = ct.detect(
        "https://example.com/no-extension-but-epub",
        client=_mock_client(handler),
    )
    assert res.content_type == ct.EPUB


def test_head_dispatches_to_html_on_text_html():
    def handler(req): return httpx.Response(
        200, headers={"content-type": "text/html; charset=utf-8"},
    )
    res = ct.detect("https://example.com/article", client=_mock_client(handler))
    assert res.content_type == ct.HTML_ARTICLE
    assert res.via == "head_request"


def test_head_dispatches_to_html_on_unknown_mime():
    """Spec: ambiguous → HTML article."""
    def handler(req): return httpx.Response(
        200, headers={"content-type": "application/octet-stream"},
    )
    res = ct.detect("https://example.com/blob", client=_mock_client(handler))
    assert res.content_type == ct.HTML_ARTICLE


def test_head_failure_falls_back_to_extension():
    def handler(req): return httpx.Response(500)
    res = ct.detect("https://example.com/file.pdf", client=_mock_client(handler))
    # URL pattern catches it before HEAD; .pdf extension matches first
    # pass. Tests the URL-pattern path takes priority.
    assert res.content_type == ct.PDF


def test_head_405_falls_back_to_html():
    """Some servers 405 HEAD; we should fall through to HTML, not crash."""
    def handler(req): return httpx.Response(405)
    res = ct.detect("https://example.com/api/something", client=_mock_client(handler))
    assert res.content_type == ct.HTML_ARTICLE


def test_malformed_url_returns_default():
    """Bad URL shouldn't crash detect()."""
    res = ct.detect("not-a-url", do_head=False)
    # urlparse is forgiving — anything not crashing is fine.
    assert res.content_type in (ct.HTML_ARTICLE,)
