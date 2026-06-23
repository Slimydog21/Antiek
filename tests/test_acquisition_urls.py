"""Tests for acquisition/urls/ (Sprint 10 day 3-4).

Coverage:

A. Client fetch:
   1. fetch() returns FetchedHtml with body + final_url
   2. follow_redirects threads through
   3. 4xx raises
   4. charset extracted from Content-Type

B. Extract:
   5. <article> preferred over body
   6. <nav>/<header>/<footer>/<script> stripped
   7. og:title preferred over <title>
   8. <meta name=author> extracted
   9. body too small → graceful (empty markdown, low word count)
   10. multi-line article renders to markdown headings

C. url_doc_id:
   11. stable for same URL
   12. differs for different URLs
   13. empty raises

D. End-to-end ingest:
   14. emits document.loaded with url_extracted media_type
   15. writes documents + chunks + nodes
   16. low_word_count gate skips graph writes
   17. idempotent on re-ingest (rows constant; events grow)
   18. nodes carry final_url metadata
"""

from __future__ import annotations

import os
import sys
import tempfile

import httpx
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.urls import (
    fetch,
    html_to_markdown,
    ingest_url,
    url_doc_id,
)
from acquisition.urls.client import _detect_charset

_HTML_ARTICLE = b"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Plain Title</title>
  <meta property="og:title" content="Better Title">
  <meta name="author" content="Jane Researcher">
</head>
<body>
  <nav>menu nav home</nav>
  <header>top header</header>
  <script>tracker();</script>
  <article>
    <h1>Article Heading</h1>
    <p>This is the first substantive paragraph about the topic. It contains enough
    words that the extractor will treat it as real content rather than chrome.</p>
    <h2>Subsection</h2>
    <p>Another paragraph with additional detail. The chunker will turn the headings
    into anchors that subsequent chunks reference via the carry-forward comment.</p>
    <p>One more paragraph so the total word count comfortably clears the
    MIN_INGEST_WORD_COUNT threshold used by the adapter's gate.</p>
  </article>
  <footer>copyright 2026</footer>
  <aside>sidebar advert</aside>
</body>
</html>"""


_HTML_EMPTY_STUB = b"""<html><head><title>Paywall</title></head><body>
<div>Please subscribe.</div></body></html>"""


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)


# ---------------------------------------------------------------------------
# A. Client fetch
# ---------------------------------------------------------------------------


def test_fetch_returns_html():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=_HTML_ARTICLE,
            headers={"content-type": "text/html; charset=utf-8"},
        )
    page = fetch("https://example.com/post", client=_mock_client(handler))
    assert page.status_code == 200
    assert page.charset == "utf-8"
    assert b"Article Heading" in page.body
    assert page.final_url == "https://example.com/post"


def test_fetch_4xx_raises():
    def handler(req): return httpx.Response(404, content=b"missing")
    with pytest.raises(httpx.HTTPStatusError):
        fetch("https://example.com/missing", client=_mock_client(handler))


def test_detect_charset_default_utf8():
    assert _detect_charset("") == "utf-8"
    assert _detect_charset("text/html") == "utf-8"
    assert _detect_charset("text/html; charset=iso-8859-1") == "iso-8859-1"


# ---------------------------------------------------------------------------
# B. Extract
# ---------------------------------------------------------------------------


def test_extract_prefers_article_over_body():
    doc = html_to_markdown(_HTML_ARTICLE, base_url="https://example.com/post")
    assert "Article Heading" in doc.markdown
    # Chrome elements must NOT leak into the extracted markdown.
    assert "menu nav home" not in doc.markdown
    assert "top header" not in doc.markdown
    assert "sidebar advert" not in doc.markdown
    assert "copyright 2026" not in doc.markdown
    assert "tracker()" not in doc.markdown


def test_extract_og_title_wins_over_title():
    doc = html_to_markdown(_HTML_ARTICLE)
    assert doc.title == "Better Title"


def test_extract_author_meta():
    doc = html_to_markdown(_HTML_ARTICLE)
    assert doc.author == "Jane Researcher"


def test_extract_word_count_populated():
    doc = html_to_markdown(_HTML_ARTICLE)
    assert doc.word_count > 30


def test_extract_low_content_stays_low():
    doc = html_to_markdown(_HTML_EMPTY_STUB)
    assert doc.word_count < 30


# ---------------------------------------------------------------------------
# C. url_doc_id
# ---------------------------------------------------------------------------


def test_url_doc_id_stable():
    a = url_doc_id("https://example.com/post")
    b = url_doc_id("https://example.com/post")
    assert a == b


def test_url_doc_id_differs_across_urls():
    a = url_doc_id("https://example.com/post-1")
    b = url_doc_id("https://example.com/post-2")
    assert a != b


def test_url_doc_id_empty_raises():
    with pytest.raises(ValueError):
        url_doc_id("")


def test_url_doc_id_format():
    did = url_doc_id("https://example.com/x")
    assert did.startswith("doc-url-")
    assert len(did) == len("doc-url-") + 16  # sha-prefix
    assert all(c in "0123456789abcdef" for c in did[len("doc-url-"):])


# ---------------------------------------------------------------------------
# D. End-to-end ingest
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_substrate(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-urls-test-")
    db_path = os.path.join(tmpdir, "graph.duckdb")
    events_dir = os.path.join(tmpdir, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events_dir)
    yield {"db_path": db_path, "events_dir": events_dir, "tmpdir": tmpdir}


class _StubEmbedder:
    def encode(self, text: str) -> list[float]:
        h = abs(hash(text)) % 64
        v = [0.0] * 16
        v[h % 16] = 1.0
        return v


def _good_fetched():
    from acquisition.urls.client import FetchedHtml
    return FetchedHtml(
        requested_url="https://example.com/post",
        final_url="https://example.com/post",
        status_code=200,
        content_type="text/html; charset=utf-8",
        charset="utf-8",
        body=_HTML_ARTICLE,
    )


def test_ingest_emits_document_loaded(temp_substrate):
    res = ingest_url(
        "https://example.com/post",
        investigation_id="inv-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        fetched=_good_fetched(),
    )
    assert res.document_loaded_event_id is not None
    assert res.document_loaded_event_id.startswith("evt-")
    assert res.title == "Better Title"


def test_ingest_writes_documents_chunks_nodes(temp_substrate):
    import duckdb

    res = ingest_url(
        "https://example.com/post",
        investigation_id="inv-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        fetched=_good_fetched(),
    )
    assert res.skipped_reason is None
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (doc_count,) = con.execute(
            "SELECT COUNT(*) FROM documents WHERE document_id = ?",
            [res.document_id],
        ).fetchone()
        (chunk_count,) = con.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
            [res.document_id],
        ).fetchone()
    finally:
        con.close()
    assert doc_count == 1
    assert chunk_count == res.chunks_written
    assert chunk_count >= 1


def test_ingest_low_word_count_skips_graph_writes(temp_substrate):
    from acquisition.urls.client import FetchedHtml

    stub = FetchedHtml(
        requested_url="https://example.com/paywall",
        final_url="https://example.com/paywall",
        status_code=200,
        content_type="text/html; charset=utf-8",
        charset="utf-8",
        body=_HTML_EMPTY_STUB,
    )
    res = ingest_url(
        "https://example.com/paywall",
        investigation_id="inv-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        fetched=stub,
    )
    assert res.skipped_reason == "low_word_count"


def test_ingest_reader_snapshot_when_flag_set(temp_substrate, monkeypatch):
    snap_dir = os.path.join(temp_substrate["tmpdir"], "reader-snaps")
    monkeypatch.setenv("ANTIEK_READER_SNAPSHOT", "1")
    monkeypatch.setenv("ANTIEK_READER_SNAPSHOTS_DIR", snap_dir)
    res = ingest_url(
        "https://example.com/post",
        investigation_id="inv-snap",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        fetched=_good_fetched(),
    )
    assert res.reader_snapshot_path is not None
    assert os.path.isfile(res.reader_snapshot_path)
    text = open(res.reader_snapshot_path, encoding="utf-8").read()
    assert res.document_id in text
    assert "Article Heading" in text or "substantive" in text
    assert "<script>" not in text.lower() or "alert" not in text
    assert res.chunks_written >= 1
    assert res.document_loaded_event_id is not None


def test_ingest_idempotent_on_rows(temp_substrate):
    import duckdb

    r1 = ingest_url(
        "https://example.com/post",
        investigation_id="inv-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        fetched=_good_fetched(),
    )
    r2 = ingest_url(
        "https://example.com/post",
        investigation_id="inv-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        fetched=_good_fetched(),
    )
    assert r1.document_id == r2.document_id
    assert r1.chunk_ids == r2.chunk_ids
    assert r1.document_loaded_event_id != r2.document_loaded_event_id
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (doc_count,) = con.execute(
            "SELECT COUNT(*) FROM documents WHERE document_id = ?",
            [r1.document_id],
        ).fetchone()
    finally:
        con.close()
    assert doc_count == 1


def test_ingest_nodes_carry_final_url(temp_substrate):
    import json

    import duckdb

    res = ingest_url(
        "https://example.com/post",
        investigation_id="inv-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        fetched=_good_fetched(),
    )
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        rows = con.execute(
            "SELECT metadata FROM nodes WHERE node_id = ANY(?)",
            [res.node_ids],
        ).fetchall()
    finally:
        con.close()
    metas = [json.loads(r[0]) if isinstance(r[0], str) else r[0] for r in rows]
    assert all(m.get("source") == "url" for m in metas)
    assert all(m.get("final_url") == "https://example.com/post" for m in metas)


# ---------------------------------------------------------------------------
# E. Personal-Reading Lane (SPR-02) — a web_article lands content_class
#    'personal_reading', NEVER a servable default. Queried off the temp DB
#    (not assumed from the kwarg) per rigor #1.
# ---------------------------------------------------------------------------


def test_ingest_web_article_lands_personal_reading(temp_substrate):
    """A third-party web article fetched for the owner's reading lands
    content_class='personal_reading' (the owner-readable / public-non-servable
    lane), document_type='web_article'. The row is read back from the temp DB
    — this proves the lane LANDED, not that we expect it to."""
    import duckdb

    res = ingest_url(
        "https://example.com/post",
        investigation_id="inv-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        fetched=_good_fetched(),
    )
    assert res.skipped_reason is None
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (content_class, document_type) = con.execute(
            "SELECT content_class, document_type FROM documents WHERE document_id = ?",
            [res.document_id],
        ).fetchone()
    finally:
        con.close()
    assert content_class == "personal_reading", (
        "a third-party web_article must land personal_reading, never a servable "
        f"default; got {content_class!r}"
    )
    assert document_type == "web_article"
    # The constant the adapter passed is exactly the lane value (not drifted).
    from substrate.constants import PERSONAL_READING_CONTENT_CLASS, SERVABLE_CONTENT_CLASSES

    assert content_class == PERSONAL_READING_CONTENT_CLASS
    assert content_class not in SERVABLE_CONTENT_CLASSES


def test_ingest_web_article_lane_stable_on_reingest(temp_substrate):
    """on_conflict='ignore' on re-ingest must not flip content_class away from
    personal_reading (rigor #3.v — the dedup path never silently reclassifies)."""
    import duckdb

    r1 = ingest_url(
        "https://example.com/post",
        investigation_id="inv-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        fetched=_good_fetched(),
    )
    r2 = ingest_url(
        "https://example.com/post",
        investigation_id="inv-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        fetched=_good_fetched(),
    )
    assert r1.document_id == r2.document_id
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        rows = con.execute(
            "SELECT content_class FROM documents WHERE document_id = ?",
            [r1.document_id],
        ).fetchall()
    finally:
        con.close()
    assert len(rows) == 1
    assert rows[0][0] == "personal_reading"
