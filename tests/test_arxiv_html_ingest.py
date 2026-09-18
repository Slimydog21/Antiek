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
    # Every chunk write pins its provider identity through
    # substrate.graph.embedding_meta._identity, which reads ``.dimension``
    # (commit 8f5096795, "pin chunk embedding provider metadata"). These two
    # stubs were never updated for it, so every PDF-leg test in this file has
    # been dying on AttributeError instead of asserting anything. 16 matches the
    # vector this stub returns and the convention every other stub in tests/
    # already uses.
    dimension = 16

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
    """The explicit PDF-only opt-out: prefer_html=False never calls fetch_html
    and uses the PDF path exclusively.

    This test used to rely on the DEFAULT being False and passed no
    ``prefer_html`` at all. The default is now True (arXiv's HTML rendering
    carries ~2.4x the body text PDF extraction recovers), so the flag is now
    passed explicitly. Every assertion below is unchanged — the opt-out path
    this test guards still exists and still behaves identically; only the way
    the test reaches it is explicit. The new default gets its own assertion in
    ``test_prefer_html_defaults_to_true`` below, which is a STRONGER claim than
    the implicit one this test used to carry."""
    html_called = []

    def spy_fetch_html(arxiv_id: str) -> FetchedHtml | None:
        html_called.append(arxiv_id)
        return _make_fetched_html(arxiv_id)

    paper = _paper("2402.03320", _CC_BY)

    res = ingest_paper_with_rights(
        paper,
        investigation_id="inv-test",
        prefer_html=False,  # explicit opt-out; no longer the default
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


# ---------------------------------------------------------------------------
# F. HTML-first is the DEFAULT, and a 429 on the HTML leg never degrades to PDF
# ---------------------------------------------------------------------------


def test_prefer_html_defaults_to_true(temp_db_and_events):
    """No ``prefer_html`` argument at all → the HTML leg runs and wins.

    This is the fidelity default, not a style choice: arXiv's own HTML
    rendering of a paper carries roughly 2.4x the body text a PDF extraction
    recovers from the same paper, plus the math, tables and two-column reading
    order that PDF extraction flattens. A default of False meant every caller
    that did not opt in threw more than half the body away before chunking.

    ``pdf_bytes`` is supplied alongside an explicit ``fetch_html``: with the
    HTML fetcher wired, the HTML leg wins even though PDF bytes are already in
    hand. (Without a wired ``fetch_html``, in-hand ``pdf_bytes`` deliberately
    suppresses the DEFAULT network fetcher — see
    ``test_pdf_bytes_in_hand_never_triggers_a_default_html_fetch``.)
    """
    import inspect

    import duckdb

    from acquisition.arxiv.adapter import ingest_paper_with_rights as _adapter_fn

    # The signature default itself, so a future edit that flips it back reds here
    # rather than only in the behavioral assertions below.
    assert (
        inspect.signature(_adapter_fn).parameters["prefer_html"].default is True
    )

    html_called: list[str] = []

    def spy_fetch_html(arxiv_id: str) -> FetchedHtml | None:
        html_called.append(arxiv_id)
        return _make_fetched_html(arxiv_id)

    paper = _paper("2402.03400", _CC_BY)

    res = ingest_paper_with_rights(
        paper,
        investigation_id="inv-test",
        # NO prefer_html argument — the default is what is under test.
        fetch_html=spy_fetch_html,
        pdf_bytes=_PDF_BYTES,
        db_path=temp_db_and_events["db_path"],
        embedder=_StubEmbedder(),
    )

    assert html_called == ["2402.03400"]

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

    # The stored body is the sanitized HTML rendering, NOT the PDF text — proof
    # the HTML leg won rather than merely being attempted.
    assert raw_text == sanitize_book_html(_RAW_HTML)
    assert metadata.get("html_sha256") == _make_fetched_html("2402.03400").sha256
    assert _PDF_TEXT.split(".")[0] not in raw_text


def test_html_leg_429_raises_and_never_falls_back_to_pdf(temp_db_and_events, tmp_path):
    """A 429 on the HTML leg arms the ban sentinel and PROPAGATES. It must not
    be read as "this paper has no HTML rendering" and answered by fetching the
    heavier PDF from the same host — that turns a rate-limit into an IP ban.

    Driven through the REAL ``html_fetch.fetch_html`` over an
    ``httpx.MockTransport`` (no network), so this covers the actual 429 handling
    rather than a stub that raises on command.
    """
    import httpx

    from acquisition.arxiv import html_fetch
    from acquisition.arxiv.throttle import ArxivBanned, ArxivThrottle

    throttle = ArxivThrottle(
        state_path=str(tmp_path / "throttle.json"), sleep=lambda _s: None
    )

    hops: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hops.append(str(request.url))
        return httpx.Response(429, headers={"Retry-After": "600"})

    pdf_called: list[str] = []

    def spy_fetch_pdf(arxiv_id: str) -> bytes:
        pdf_called.append(arxiv_id)
        return _PDF_BYTES

    def real_fetch_html(arxiv_id: str) -> FetchedHtml | None:
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            return html_fetch.fetch_html(
                arxiv_id, throttle=throttle, client=client
            )

    paper = _paper("2402.03401", _CC_BY)

    with pytest.raises(ArxivBanned):
        ingest_paper_with_rights(
            paper,
            investigation_id="inv-test",
            fetch_html=real_fetch_html,
            fetch_pdf=spy_fetch_pdf,
            db_path=temp_db_and_events["db_path"],
            embedder=_StubEmbedder(),
        )

    # The HTML hop really went out, and the PDF leg was never reached.
    assert hops and "/html/2402.03401" in hops[0]
    assert pdf_called == []
    # The 429 armed the ban sentinel on the shared state, so the NEXT arXiv
    # request on this box refuses before egressing.
    assert throttle.is_banned()


def test_html_leg_429_does_not_fall_back_even_with_pdf_bytes_in_hand(
    temp_db_and_events, tmp_path
):
    """The no-fallback rule holds even when PDF bytes are already available and
    ingesting them would cost nothing — a 429 is a stop signal about the HOST,
    not a statement about this paper's HTML."""
    import httpx

    from acquisition.arxiv import html_fetch
    from acquisition.arxiv.throttle import ArxivBanned, ArxivThrottle

    throttle = ArxivThrottle(
        state_path=str(tmp_path / "throttle.json"), sleep=lambda _s: None
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    def real_fetch_html(arxiv_id: str) -> FetchedHtml | None:
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            return html_fetch.fetch_html(
                arxiv_id, throttle=throttle, client=client
            )

    paper = _paper("2402.03402", _CC_BY)

    with pytest.raises(ArxivBanned):
        ingest_paper_with_rights(
            paper,
            investigation_id="inv-test",
            fetch_html=real_fetch_html,
            pdf_bytes=_PDF_BYTES,
            db_path=temp_db_and_events["db_path"],
            embedder=_StubEmbedder(),
        )


def test_pdf_bytes_in_hand_never_triggers_a_default_html_fetch(temp_db_and_events):
    """A caller that hands in ``pdf_bytes`` and wires no ``fetch_html`` must not
    cause a live arxiv.org/html request.

    This is the guard rail on the HTML-first default. Making prefer_html True
    without it turns every offline-shaped call — a fixture-bytes ingest, a unit
    test, a replay — into live egress against a host that has IP-banned this box
    before, to fetch a body the caller already holds. The adapter's default HTML
    fetcher is monkeypatched to a tripwire: if it is consulted at all, this test
    fails rather than reaching the network."""
    from acquisition.arxiv import adapter as _adapter

    tripped: list[str] = []

    def _tripwire(arxiv_id: str):
        tripped.append(arxiv_id)
        raise AssertionError(
            "the default arxiv.org/html fetcher was called for a caller that "
            "supplied pdf_bytes — that is live network egress from an "
            "offline-shaped call"
        )

    original = _adapter._default_fetch_html
    _adapter._default_fetch_html = _tripwire
    try:
        paper = _paper("2402.03403", _CC_BY)
        res = ingest_paper_with_rights(
            paper,
            investigation_id="inv-test",
            # NO prefer_html (default True), NO fetch_html, body already in hand.
            pdf_bytes=_PDF_BYTES,
            db_path=temp_db_and_events["db_path"],
            embedder=_StubEmbedder(),
        )
    finally:
        _adapter._default_fetch_html = original

    assert tripped == []
    # The ingest completed on the in-hand bytes rather than being skipped.
    assert res.servable_full_text is True
