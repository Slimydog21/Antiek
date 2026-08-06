"""Tests for HTML-first arXiv ingest wiring (SWARM_BRIEF).

Coverage:

A. prefer_html=True + valid FetchedHtml → stored as sanitized HTML with
   provenance metadata (content_sanitized, content_sanitizer_version).
B. prefer_html=True + fetch_html returns None → falls back to PDF path
   unchanged (existing behavior preserved).
C. prefer_html=False (default) → PDF path only, fetch_html never called.
D. ArxivBanned from fetch_html propagates (never silently swallowed).
E. Existing adapter tests still pass (run separately, reported in DONE.md).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.arxiv import (  # noqa: E402
    ArxivPaper,
    ingest_paper_with_rights,
)
from acquisition.arxiv.client import _parse_response  # noqa: E402
from acquisition.arxiv.html_fetch import FetchedHtml  # noqa: E402
from acquisition.books.public_domain import text_to_pdf  # noqa: E402
from substrate.books.html_sanitizer import (  # noqa: E402
    SANITIZER_VERSION,
    sanitize_book_html,
)
from substrate.constants import GATED_DEFAULT_CONTENT_CLASS  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _feed(arxiv_id: str, license_uri: str) -> bytes:
    lic = (
        f'<arxiv:license>{license_uri}</arxiv:license>' if license_uri else ""
    )
    return (
        f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/{arxiv_id}v1</id>
    <updated>2024-02-15T12:00:00Z</updated>
    <published>2024-02-05T09:15:33Z</published>
    <title>Paper {arxiv_id}</title>
    <summary>Abstract for {arxiv_id}.</summary>
    <author><name>Jane Doe</name></author>
    <arxiv:primary_category term="cs.AI"/>
    {lic}
  </entry>
</feed>
"""
    ).encode()


_CC_BY = "http://creativecommons.org/licenses/by/4.0/"
_ARXIV_DEFAULT = "http://arxiv.org/licenses/nonexclusive-distrib/1.0/"


def _paper(arxiv_id: str, license_uri: str) -> ArxivPaper:
    return _parse_response(_feed(arxiv_id, license_uri))[0]


# A tiny PDF with enough words to clear MIN_INGEST_WORD_COUNT (100).
_PDF_TEXT = (
    "This is a synthetic academic paper body used as ingest test fixture. "
    * 40
)
_PDF_BYTES = text_to_pdf(_PDF_TEXT, title="Test Paper")


# A realistic arXiv HTML rendering — article-sliced, enough chars to pass
# the MIN_HTML_CHARS gate, and containing content that survives sanitization.
_RAW_HTML = """\
<html><body>
<article class="ltx_document">
<h1 class="ltx_title">Test Paper Title</h1>
<p class="ltx_p">This is the first paragraph of the paper body. It contains
enough text to be meaningful for chunking and word-count purposes.</p>
<h2 class="ltx_title">1 Introduction</h2>
<p class="ltx_p">We present a novel approach to testing arXiv HTML ingestion.
Our method ensures that raw HTML is always sanitized before storage, preventing
stored-XSS vulnerabilities in the reading surface.</p>
<h2 class="ltx_title">2 Methods</h2>
<p class="ltx_p">The sanitizer strips script tags, event handlers, and
javascript: URLs. Only allowlisted structural tags survive reconstruction.</p>
</article>
</body></html>
"""


def _make_fetched_html(arxiv_id: str = "2402.03300") -> FetchedHtml:
    """Build a ``FetchedHtml`` fixture from the canned HTML body."""
    html = _RAW_HTML
    body_bytes = html.encode("utf-8")
    return FetchedHtml(
        arxiv_id=arxiv_id,
        source_url=f"https://arxiv.org/html/{arxiv_id}",
        html=html,
        sha256=hashlib.sha256(body_bytes).hexdigest(),
        byte_size=len(body_bytes),
        char_count=len(html),
    )


class _StubEmbedder:
    def encode(self, text: str) -> list[float]:
        h = abs(hash(text)) % 64
        v = [0.0] * 16
        v[h % 16] = 1.0
        return v


@pytest.fixture
def temp_db_and_events(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-arxiv-html-")
    db_path = os.path.join(tmpdir, "graph.duckdb")
    events_dir = os.path.join(tmpdir, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events_dir)
    yield {"db_path": db_path, "events_dir": events_dir, "tmpdir": tmpdir}


# ---------------------------------------------------------------------------
# A. HTML-first path: prefer_html=True + valid HTML → sanitized + stored
# ---------------------------------------------------------------------------


def test_html_first_stores_sanitized_html_with_provenance(temp_db_and_events):
    """prefer_html=True + valid FetchedHtml → document stored with sanitized
    HTML as raw_text, content_sanitized=True in metadata, and correct
    sanitizer_version."""
    import duckdb

    paper = _paper("2402.03300", _CC_BY)
    fetched = _make_fetched_html("2402.03300")

    res = ingest_paper_with_rights(
        paper,
        investigation_id="inv-test",
        prefer_html=True,
        fetch_html=lambda _id: fetched,
        db_path=temp_db_and_events["db_path"],
        embedder=_StubEmbedder(),
    )

    # CC-BY → source_declared_open, servable.
    assert res.content_class == "source_declared_open"
    assert res.servable_full_text is True

    con = duckdb.connect(temp_db_and_events["db_path"])
    try:
        row = con.execute(
            "SELECT raw_text, metadata FROM documents WHERE document_id = ?",
            [res.document_id],
        ).fetchone()
    finally:
        con.close()

    assert row is not None
    raw_text, metadata_raw = row
    metadata = json.loads(metadata_raw) if isinstance(metadata_raw, str) else metadata_raw

    # The raw_text must be the sanitized output (not the raw HTML).
    expected_sanitized = sanitize_book_html(_RAW_HTML)
    assert raw_text == expected_sanitized

    # Sanitizer provenance must be stamped.
    assert metadata.get("content_sanitized") is True
    assert metadata.get("content_sanitizer_version") == SANITIZER_VERSION

    # arXiv-specific provenance fields present.
    assert metadata.get("html_source_url") == fetched.source_url
    assert metadata.get("html_sha256") == fetched.sha256


def test_html_first_with_gated_license(temp_db_and_events):
    """prefer_html=True with default-arXiv-terms → gated, not servable."""
    paper = _paper("2402.03301", _ARXIV_DEFAULT)
    fetched = _make_fetched_html("2402.03301")

    res = ingest_paper_with_rights(
        paper,
        investigation_id="inv-test",
        prefer_html=True,
        fetch_html=lambda _id: fetched,
        db_path=temp_db_and_events["db_path"],
        embedder=_StubEmbedder(),
    )

    assert res.content_class == GATED_DEFAULT_CONTENT_CLASS
    assert res.servable_full_text is False
    assert res.redistributable is False


def test_html_first_xss_payloads_stripped(temp_db_and_events):
    """Seeded XSS payloads in the raw HTML must be stripped by the sanitizer
    before storage — red-proof test."""
    xss_html = """\
<html><body>
<article class="ltx_document">
<h1>Paper with XSS</h1>
<p><img src=x onerror=alert(1)></p>
<p><a href="javascript:alert(1)">click</a></p>
<script>alert('xss')</script>
<p>Safe paragraph.</p>
</article>
</body></html>
"""
    body_bytes = xss_html.encode("utf-8")
    fetched = FetchedHtml(
        arxiv_id="2402.03302",
        source_url="https://arxiv.org/html/2402.03302",
        html=xss_html,
        sha256=hashlib.sha256(body_bytes).hexdigest(),
        byte_size=len(body_bytes),
        char_count=len(xss_html),
    )
    paper = _paper("2402.03302", _CC_BY)

    res = ingest_paper_with_rights(
        paper,
        investigation_id="inv-test",
        prefer_html=True,
        fetch_html=lambda _id: fetched,
        db_path=temp_db_and_events["db_path"],
        embedder=_StubEmbedder(),
    )

    import duckdb

    con = duckdb.connect(temp_db_and_events["db_path"])
    try:
        (raw_text,) = con.execute(
            "SELECT raw_text FROM documents WHERE document_id = ?",
            [res.document_id],
        ).fetchone()
    finally:
        con.close()

    # None of the XSS payloads survive sanitization.
    assert "onerror" not in raw_text
    assert "javascript:" not in raw_text
    assert "<script" not in raw_text.lower()
    assert "alert" not in raw_text
    # The safe content survives.
    assert "Safe paragraph" in raw_text


# ---------------------------------------------------------------------------
# B. HTML absent → PDF fallback unchanged
# ---------------------------------------------------------------------------


def test_html_absent_falls_back_to_pdf(temp_db_and_events):
    """When fetch_html returns None (no HTML rendering), the function falls
    back to the PDF path — same behavior as prefer_html=False."""
    import duckdb

    paper = _paper("2402.03310", _CC_BY)

    res = ingest_paper_with_rights(
        paper,
        investigation_id="inv-test",
        prefer_html=True,
        fetch_html=lambda _id: None,  # HTML absent
        pdf_bytes=_PDF_BYTES,
        db_path=temp_db_and_events["db_path"],
        embedder=_StubEmbedder(),
    )

    # PDF path produces a book, not an academic_paper with HTML provenance.
    assert res.servable_full_text is True

    con = duckdb.connect(temp_db_and_events["db_path"])
    try:
        row = con.execute(
            "SELECT raw_text, metadata FROM documents WHERE document_id = ?",
            [res.document_id],
        ).fetchone()
    finally:
        con.close()

    assert row is not None
    raw_text, metadata_raw = row
    metadata = json.loads(metadata_raw) if isinstance(metadata_raw, str) else metadata_raw

    # PDF path: raw_text is extracted markdown, NOT sanitized HTML.
    assert "Test Paper" in raw_text or "synthetic" in raw_text
    # PDF path: no sanitizer provenance on the document.
    assert metadata.get("content_sanitized") is not True


def test_html_absent_uses_injected_fetch_pdf(temp_db_and_events):
    """When fetch_html returns None and pdf_bytes is omitted, the injected
    fetch_pdf is called (proves the fallback path uses the injectable)."""
    seen = {}

    def fake_fetch_pdf(arxiv_id: str) -> bytes:
        seen["id"] = arxiv_id
        return _PDF_BYTES

    paper = _paper("2402.03311", _CC_BY)

    res = ingest_paper_with_rights(
        paper,
        investigation_id="inv-test",
        prefer_html=True,
        fetch_html=lambda _id: None,
        fetch_pdf=fake_fetch_pdf,
        db_path=temp_db_and_events["db_path"],
        embedder=_StubEmbedder(),
    )

    assert seen["id"] == "2402.03311"
    assert res.servable_full_text is True


# ---------------------------------------------------------------------------
# C. prefer_html=False → PDF only, fetch_html never called
# ---------------------------------------------------------------------------


def test_prefer_html_false_never_calls_fetch_html(temp_db_and_events):
    """When prefer_html is False (the default), fetch_html is never called
    and the PDF path is used exclusively."""
    html_called = []

    def spy_fetch_html(arxiv_id: str) -> FetchedHtml | None:
        html_called.append(arxiv_id)
        return _make_fetched_html(arxiv_id)

    paper = _paper("2402.03320", _CC_BY)

    res = ingest_paper_with_rights(
        paper,
        investigation_id="inv-test",
        # prefer_html defaults to False
        fetch_html=spy_fetch_html,
        pdf_bytes=_PDF_BYTES,
        db_path=temp_db_and_events["db_path"],
        embedder=_StubEmbedder(),
    )

    assert html_called == []  # never called
    assert res.servable_full_text is True


# ---------------------------------------------------------------------------
# D. ArxivBanned from fetch_html propagates
# ---------------------------------------------------------------------------


def test_arxiv_banned_from_fetch_html_propagates(temp_db_and_events):
    """If fetch_html raises ArxivBanned, the exception propagates — the
    caller must pause the batch, never silently swallow."""
    import time

    from acquisition.arxiv.throttle import ArxivBanned

    def banned_fetch_html(arxiv_id: str) -> FetchedHtml | None:
        now = time.time()
        raise ArxivBanned(banned_until=now + 300.0, now=now)

    paper = _paper("2402.03330", _CC_BY)

    with pytest.raises(ArxivBanned):
        ingest_paper_with_rights(
            paper,
            investigation_id="inv-test",
            prefer_html=True,
            fetch_html=banned_fetch_html,
            pdf_bytes=_PDF_BYTES,
            db_path=temp_db_and_events["db_path"],
            embedder=_StubEmbedder(),
        )


# ---------------------------------------------------------------------------
# E. Document id stability
# ---------------------------------------------------------------------------


def test_html_path_uses_arxiv_doc_id(temp_db_and_events):
    """The HTML path uses arxiv_doc_id (stable on arxiv_id), not a hash of
    the HTML bytes."""
    from acquisition.arxiv.adapter import arxiv_doc_id

    paper = _paper("2402.03340", _CC_BY)
    fetched = _make_fetched_html("2402.03340")

    res = ingest_paper_with_rights(
        paper,
        investigation_id="inv-test",
        prefer_html=True,
        fetch_html=lambda _id: fetched,
        db_path=temp_db_and_events["db_path"],
        embedder=_StubEmbedder(),
    )

    assert res.document_id == arxiv_doc_id("2402.03340")
    assert res.document_id == "doc-arxiv-2402.03340"
