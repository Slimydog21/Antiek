"""Doc→HTML S1 — GET /sources/{document_id}/reader-html endpoint tests.

Acceptance for the lane:

- a trusted sanitized snapshot IS served as ``content_format="html"``;
- an untrusted / unsanitized / version-stale body is NOT served as HTML
  (mirrors the book stored-XSS regression posture — the version gate is the
  whole point);
- the §5.2 hazard holds: a URL doc with a sidecar still serves
  ``content_format="text"`` from the books full-text endpoint;
- the REAL ingest path (``ingest_url`` with a fake fetch) produces a trusted
  sidecar that the endpoint serves as HTML.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api import books as books_api  # noqa: E402
from interfaces.research.api.app import create_app  # noqa: E402
from runtime.db_lock import connect_write  # noqa: E402
from substrate.books.html_sanitizer import SANITIZER_VERSION  # noqa: E402
from substrate.reader_html.store import store_reader_html  # noqa: E402

_HTML_ARTICLE = b"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Plain Title</title>
  <meta property="og:title" content="Better Title">
</head>
<body>
  <nav>menu nav home</nav>
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
</body>
</html>"""


@pytest.fixture
def temp_substrate(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-reader-html-api-")
    db_path = os.path.join(tmpdir, "graph.duckdb")
    events_dir = os.path.join(tmpdir, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events_dir)
    # Initialize the schema up front so seed writes (and the endpoint's
    # read-only connect) see the full table set.
    from substrate.graph.schema import init_database

    writer = connect_write(db_path, purpose="test/reader-html-api/schema")
    try:
        init_database(writer)
    finally:
        writer.close()
    yield {"db_path": db_path, "events_dir": events_dir, "tmpdir": tmpdir}


@pytest.fixture
def client(temp_substrate):
    app = create_app(
        register_wrestling=False,
        register_providers=False,
        cors_origins=[],
    )
    return TestClient(app)


def _insert_url_doc(db: str, document_id: str = "doc-url-abc") -> None:
    writer = connect_write(db, purpose="test/reader-html-api/seed")
    try:
        writer.execute(
            """
            INSERT INTO documents (
                document_id, document_type, content_class, source_tier,
                raw_text, metadata, source_uri, title
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                document_id,
                "web_article",
                "personal_reading",
                4,
                "# Title\n\nBody text here.",
                "{}",
                "https://example.com/a",
                "Title",
            ],
        )
    finally:
        writer.close()


def _store_sidecar(db: str, document_id: str = "doc-url-abc") -> None:
    writer = connect_write(db, purpose="test/reader-html-api/sidecar")
    try:
        store_reader_html(
            writer,
            document_id=document_id,
            main_html="<article><h1>Hi</h1><p>Body text.</p></article>",
            source_kind="url",
            source_url="https://example.com/a",
        )
    finally:
        writer.close()


def _as_owner(monkeypatch) -> None:
    """Grant the privileged owner policy tag (same pattern as
    test_book_import_api: the owner-full-text endpoints' test hook)."""
    monkeypatch.setattr(
        books_api,
        "_owner_read_policy_tag",
        lambda _request: books_api._OWNER_READ_POLICY_TAG,
    )


# ---------------------------------------------------------------------------
# The acceptance pair: trusted → html, untrusted → never html
# ---------------------------------------------------------------------------


def test_trusted_sanitized_snapshot_served_as_html(
    temp_substrate, client, monkeypatch
):
    _insert_url_doc(temp_substrate["db_path"])
    _store_sidecar(temp_substrate["db_path"])
    _as_owner(monkeypatch)

    resp = client.get("/sources/doc-url-abc/reader-html")
    assert resp.status_code == 200
    body = resp.json()
    assert body["content_format"] == "html"
    assert body["available"] is True
    assert body["reason"] == "ok"
    assert body["body"] == "<article><h1>Hi</h1><p>Body text.</p></article>"
    assert body["source_kind"] == "url"
    assert body["source_url"] == "https://example.com/a"
    assert body["revision"] == 1
    assert body["captured_at"] is not None


def test_untrusted_body_not_served_as_html(temp_substrate, client, monkeypatch):
    """An ingested doc with NO sidecar serves the existing markdown
    representation as text — never HTML."""
    _insert_url_doc(temp_substrate["db_path"])
    _as_owner(monkeypatch)

    resp = client.get("/sources/doc-url-abc/reader-html")
    assert resp.status_code == 200
    body = resp.json()
    assert body["content_format"] == "text"
    assert body["available"] is False
    assert body["reason"] == "no_reader_html"
    assert body["body"] == "# Title\n\nBody text here."
    assert body["body"] is not None and "<article>" not in body["body"]


def test_version_stale_body_not_served_as_html(
    temp_substrate, client, monkeypatch
):
    """A sidecar stamped by an older sanitizer version must degrade to text —
    exact-version equality is the contract (mirrors is_trusted_sanitized)."""
    _insert_url_doc(temp_substrate["db_path"])
    _store_sidecar(temp_substrate["db_path"])
    _as_owner(monkeypatch)
    writer = connect_write(temp_substrate["db_path"], purpose="test/reader-html-api/tamper")
    try:
        writer.execute(
            "UPDATE document_reader_html SET sanitizer_version = ? "
            "WHERE document_id = ?",
            ["books-allowlist/0.9.0", "doc-url-abc"],
        )
    finally:
        writer.close()

    resp = client.get("/sources/doc-url-abc/reader-html")
    assert resp.status_code == 200
    body = resp.json()
    assert body["content_format"] == "text"
    assert body["available"] is False
    assert body["reason"] == "sanitizer_version_stale"
    assert body["body"] == "# Title\n\nBody text here."


def test_missing_document_returns_404(temp_substrate, client):
    resp = client.get("/sources/doc-missing/reader-html")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "document_not_found"


def test_public_request_gets_snippet_not_html(temp_substrate, client):
    """URL ingests are personal_reading by default; the PUBLIC path must not
    release the HTML body (owner resolution binds to a real credential —
    auth-disabled local dev is deliberately NOT owner)."""
    _insert_url_doc(temp_substrate["db_path"])
    _store_sidecar(temp_substrate["db_path"])

    resp = client.get("/sources/doc-url-abc/reader-html")
    assert resp.status_code == 200
    body = resp.json()
    assert body["content_format"] == "text"
    assert body["available"] is False
    assert body["reason"] == "rights_denied"
    assert body["body"] != "<article><h1>Hi</h1><p>Body text.</p></article>"


# ---------------------------------------------------------------------------
# §5.2 hazard regression — the two trust contracts stay disjoint
# ---------------------------------------------------------------------------


def test_url_doc_books_fulltext_still_text(temp_substrate, client, monkeypatch):
    """Storing the sidecar must NOT stamp documents.metadata, or the books
    full-text endpoint would label the MARKDOWN raw_text as html and the
    reader would innerHTML markdown (the exact stored-XSS-adjacent defect
    this lane guards)."""
    _insert_url_doc(temp_substrate["db_path"])
    _store_sidecar(temp_substrate["db_path"])

    resp = client.get("/books/doc-url-abc/full-text")
    assert resp.status_code == 200
    body = resp.json()
    assert body["content_format"] == "text"
    assert body["full_text"] is None  # personal_reading not publicly servable

    _as_owner(monkeypatch)
    owner = client.get("/books/doc-url-abc/owner-full-text")
    assert owner.status_code == 200
    assert owner.json()["content_format"] == "text"
    assert owner.json()["full_text"] == "# Title\n\nBody text here."


# ---------------------------------------------------------------------------
# End-to-end: the REAL ingest path produces a trusted, servable sidecar
# ---------------------------------------------------------------------------


def test_ingested_url_is_viewable_as_sanitized_html(
    temp_substrate, client, monkeypatch
):
    """The acceptance path in full: ingest_url (fake fetch, no network)
    stores the sidecar through the trusted-producer, and the endpoint serves
    it as html — XSS seeds die before storage."""
    from acquisition.urls import ingest_url
    from acquisition.urls.client import FetchedHtml

    class _StubEmbedder:
        def encode(self, text: str) -> list[float]:
            h = abs(hash(text)) % 64
            v = [0.0] * 16
            v[h % 16] = 1.0
            return v

    page = FetchedHtml(
        requested_url="https://example.com/post",
        final_url="https://example.com/post",
        status_code=200,
        content_type="text/html; charset=utf-8",
        charset="utf-8",
        body=_HTML_ARTICLE,
    )
    res = ingest_url(
        "https://example.com/post",
        investigation_id="inv-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        fetched=page,
    )
    assert res.skipped_reason is None
    _as_owner(monkeypatch)

    resp = client.get(f"/sources/{res.document_id}/reader-html")
    assert resp.status_code == 200
    body = resp.json()
    assert body["content_format"] == "html"
    assert body["available"] is True
    assert body["reason"] == "ok"
    assert body["source_kind"] == "url"
    assert body["source_url"] == "https://example.com/post"
    # The isolated main content, sanitized: article heading survives, chrome
    # and script do not.
    assert "Article Heading" in body["body"]
    assert "<script" not in body["body"]
    assert "tracker" not in body["body"]
    # The stored sidecar carries the exact current sanitizer version.
    import duckdb

    con = duckdb.connect(temp_substrate["db_path"])
    try:
        row = con.execute(
            "SELECT sanitizer_version FROM document_reader_html "
            "WHERE document_id = ?",
            [res.document_id],
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    assert row[0] == SANITIZER_VERSION
