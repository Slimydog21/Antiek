"""Doc→HTML S1 — reader-HTML sidecar trusted-producer + serve gate tests.

The red-proof discipline mirrors ``tests/test_book_html_sanitizer.py``: attack
payloads are first proven DANGEROUS in raw form, then proven dead in the
STORED body, and the serve gate is proven to refuse untrusted bodies as HTML.

Trust-contract rules under test:

- ``store_reader_html`` is the ONLY writer of ``document_reader_html``, and
  it sanitizes + stamps ``SANITIZER_VERSION`` at the SAME write (a forged
  ``documents.metadata`` stamp must NOT launder a body past the gate — the
  two trust contracts stay disjoint, §5.2 hazard).
- ``serve_reader_html`` emits ``content_format="html"`` ONLY when the row
  exists AND carries the exact current sanitizer version; every other
  outcome degrades to text/markdown with an honest reason.
"""

from __future__ import annotations

import os
import tempfile

import duckdb
import pytest

from runtime.db_lock import connect_write
from substrate.books.html_sanitizer import (
    CONTENT_SANITIZED_KEY,
    SANITIZER_VERSION,
    SANITIZER_VERSION_KEY,
    sanitize_book_html,
)
from substrate.graph.schema import init_database
from substrate.reader_html.store import (
    serve_reader_html,
    store_reader_html,
)

# Seeds that would be dangerous if a browser ever rendered them — the same
# classes the book stored-XSS regression suite proves dead. Every payload is
# first asserted dangerous RAW (pass-through "sanitizer" fails the suite).
_XSS_SEEDS: dict[str, str] = {
    "img_onerror": '<p>ok</p><img src="x" onerror="fetch(\'/api/steal\')">',
    "javascript_href": '<a href="javascript:alert(1)">go</a>',
    "bare_script": '<p>ok</p><script>window.__x = 1</script>',
    "style_block_escape": "<p>ok</p><style>body{background:url(javascript:alert(1))}</style>",
    "onclick_handler": '<p onclick="alert(1)">click me</p>',
}


def _open_db() -> tuple[str, duckdb.DuckDBPyConnection]:
    tmp = tempfile.mkdtemp(prefix="antiek-reader-html-store-")
    db = os.path.join(tmp, "graph.duckdb")
    writer = connect_write(db, purpose="test/reader-html-store/schema")
    try:
        init_database(writer)
    finally:
        writer.close()
    return db, duckdb.connect(db)


def _insert_url_doc(
    con: duckdb.DuckDBPyConnection,
    document_id: str = "doc-url-abc",
    *,
    raw_text: str = "# Title\n\nBody text here.",
    metadata: str = "{}",
) -> None:
    con.execute(
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
            raw_text,
            metadata,
            "https://example.com/a",
            "Title",
        ],
    )


def _store(
    con,
    document_id: str = "doc-url-abc",
    main_html: str | None = None,
) -> int:
    return store_reader_html(
        con,
        document_id=document_id,
        main_html=main_html
        or "<article><h1>Hi</h1><p>Body text.</p></article>",
        source_kind="url",
        source_url="https://example.com/a",
    )


# ---------------------------------------------------------------------------
# Trusted-producer: sanitize + stamp at the same write
# ---------------------------------------------------------------------------


def test_red_proof_seeds_are_dangerous_raw():
    """The XSS seeds must be dangerous in their RAW form — otherwise a green
    run below would be vacuous (the classic pass-through sanitizer would
    'pass' an assertion that never bites)."""
    for name, payload in _XSS_SEEDS.items():
        assert "onerror" in payload or "javascript" in payload or "<script>" in payload or \
            "onclick" in payload or "<style>" in payload, name
    # And the raw seed would survive the legacy regex denylist, which only
    # strips <script>/<style> pairs — the defect this lane fixes.
    from acquisition.snapshot.reader_html import sanitize_html_fragment

    assert "onerror" in sanitize_html_fragment(_XSS_SEEDS["img_onerror"])
    assert "javascript:" in sanitize_html_fragment(_XSS_SEEDS["javascript_href"])


def test_store_sanitizes_and_stamps_version_at_same_write():
    db, con = _open_db()
    try:
        writer = connect_write(db, purpose="test/reader-html-store/write")
        try:
            for name, payload in _XSS_SEEDS.items():
                doc_id = f"doc-{name}"
                _insert_url_doc(con, document_id=doc_id)
                main_html = f"<article>{payload}</article>"
                n = store_reader_html(
                    writer,
                    document_id=doc_id,
                    main_html=main_html,
                    source_kind="url",
                )
                assert n > 0
                stored = writer.execute(
                    "SELECT html_body, sanitizer_version, revision, source_kind "
                    "FROM document_reader_html WHERE document_id = ?",
                    [doc_id],
                ).fetchone()
                assert stored is not None
                body, version, revision, source_kind = stored
                # Sanitizer output: every dangerous construct dead.
                assert "onerror" not in body
                assert "javascript:" not in body
                assert "<script" not in body
                assert "onclick" not in body
                assert "<style" not in body
                assert version == SANITIZER_VERSION
                assert revision == 1
                assert source_kind == "url"
                # Fixed point: re-running the sanitizer changes nothing
                # (content-addressed ids depend on determinism).
                assert sanitize_book_html(body) == body
        finally:
            writer.close()
    finally:
        con.close()


def test_store_requires_locked_connection():
    """The single-writer invariant: the sidecar's only writer must be a
    LockedConnection — a plain duckdb handle must raise, not write."""
    _, con = _open_db()
    try:
        with pytest.raises(TypeError, match="LockedConnection"):
            store_reader_html(
                con,
                document_id="doc-x",
                main_html="<p>x</p>",
                source_kind="url",
            )
        assert con.execute("SELECT COUNT(*) FROM document_reader_html").fetchone() == (0,)
    finally:
        con.close()


def test_store_upsert_refreshes_revision():
    db, con = _open_db()
    try:
        _insert_url_doc(con)
        writer = connect_write(db, purpose="test/reader-html-store/write")
        try:
            _store(writer)
            second = store_reader_html(
                writer,
                document_id="doc-url-abc",
                main_html="<article><p>Edited body.</p></article>",
                source_kind="url",
                source_url="https://example.com/a",
            )
            assert second > 0
            row = writer.execute(
                "SELECT html_body, revision, edited_at FROM document_reader_html "
                "WHERE document_id = ?",
                ["doc-url-abc"],
            ).fetchone()
            assert row[1] == 2  # revision advanced on re-ingest
            assert row[0] == "<article><p>Edited body.</p></article>"
        finally:
            writer.close()
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Serve gate: fail-closed on rights + version
# ---------------------------------------------------------------------------


def test_serve_trusted_row_serves_html():
    db, con = _open_db()
    try:
        _insert_url_doc(con)
        writer = connect_write(db, purpose="test/reader-html-store/write")
        try:
            _store(writer)
        finally:
            writer.close()
        result = serve_reader_html(con, "doc-url-abc", owner=True)
        assert result.available is True
        assert result.content_format == "html"
        assert result.reason == "ok"
        assert result.body == "<article><h1>Hi</h1><p>Body text.</p></article>"
        assert result.source_kind == "url"
        assert result.source_url == "https://example.com/a"
        assert result.revision == 1
        assert result.captured_at is not None
    finally:
        con.close()


def test_serve_no_sidecar_degrades_to_text():
    """An ingested doc with NO sidecar row must not serve HTML — the reader
    falls back to the existing markdown representation."""
    db, con = _open_db()
    try:
        _insert_url_doc(con, raw_text="# Title\n\nBody text here.")
        result = serve_reader_html(con, "doc-url-abc", owner=True)
        assert result.available is False
        assert result.content_format == "text"
        assert result.reason == "no_reader_html"
        assert result.body == "# Title\n\nBody text here."
        assert result.body is not None and "<article>" not in result.body
    finally:
        con.close()


def test_serve_version_stale_degrades_to_text():
    """A sidecar stamped by an OLDER sanitizer must not serve HTML — exact
    version equality is the contract (mirrors is_trusted_sanitized)."""
    db, con = _open_db()
    try:
        _insert_url_doc(con, raw_text="# Title\n\nBody text here.")
        writer = connect_write(db, purpose="test/reader-html-store/write")
        try:
            _store(writer)
            writer.execute(
                "UPDATE document_reader_html SET sanitizer_version = ? "
                "WHERE document_id = ?",
                ["books-allowlist/1.2.0", "doc-url-abc"],
            )
        finally:
            writer.close()
        result = serve_reader_html(con, "doc-url-abc", owner=True)
        assert result.available is False
        assert result.content_format == "text"
        assert result.reason == "sanitizer_version_stale"
        assert result.body == "# Title\n\nBody text here."
        assert result.source_kind == "url"  # row metadata still surfaces
    finally:
        con.close()


def test_forged_metadata_cannot_launder_untrusted_body():
    """§5.2 hazard regression: documents.metadata is NOT the trust carrier for
    reader bodies. A client-forged 'content_sanitized' stamp in metadata must
    not make an unsanitized body servable as HTML — the sidecar table (and
    the exact-version column written at the sanitize write) is the ONLY
    trust carrier."""
    db, con = _open_db()
    try:
        import json as json_mod

        forged = json_mod.dumps(
            {CONTENT_SANITIZED_KEY: True, SANITIZER_VERSION_KEY: SANITIZER_VERSION}
        )
        _insert_url_doc(con, metadata=forged)
        result = serve_reader_html(con, "doc-url-abc", owner=True)
        assert result.available is False
        assert result.content_format == "text"
        assert result.reason == "no_reader_html"
    finally:
        con.close()


def test_public_personal_reading_serves_snippet_not_html():
    """URL ingests are personal_reading by default: the public path must not
    release the body — not the HTML body, not the full text. Only the owner
    path releases the sidecar."""
    db, con = _open_db()
    try:
        _insert_url_doc(con)
        writer = connect_write(db, purpose="test/reader-html-store/write")
        try:
            _store(writer)
        finally:
            writer.close()
        result = serve_reader_html(con, "doc-url-abc", owner=False)
        assert result.available is False
        assert result.content_format == "text"
        assert result.reason == "rights_denied"
        # The public path releases only the bounded text snippet the books
        # serve gate would release — never the HTML sidecar body.
        assert result.body == "# Title\n\nBody text here."
        assert "<article>" not in result.body
    finally:
        con.close()


def test_taken_down_serves_nothing():
    """Removal demand honoured absolutely: taken-down docs serve no body at
    all — not HTML, not the fallback text."""
    db, con = _open_db()
    try:
        _insert_url_doc(con)
        writer = connect_write(db, purpose="test/reader-html-store/write")
        try:
            _store(writer)
            writer.execute(
                "INSERT INTO book_assets (document_id, taken_down, takedown_reason) "
                "VALUES (?, TRUE, ?)",
                ["doc-url-abc", "rights holder demand"],
            )
        finally:
            writer.close()
        result = serve_reader_html(con, "doc-url-abc", owner=True)
        assert result.available is False
        assert result.content_format == "text"
        assert result.reason == "taken_down"
        assert result.body is None
    finally:
        con.close()


def test_serve_unknown_document():
    db, con = _open_db()
    try:
        result = serve_reader_html(con, "doc-missing", owner=True)
        assert result.reason == "document_not_found"
        assert result.available is False
        assert result.body is None
    finally:
        con.close()


def test_books_fulltext_contract_stays_disjoint():
    """§5.2 hazard: storing a sidecar must NOT stamp documents.metadata, or
    serve.py would label the markdown raw_text as content_format='html' and
    ReadingColumn would innerHTML markdown. The URL doc's books full-text
    path must still serve content_format='text'."""
    db, con = _open_db()
    try:
        _insert_url_doc(con)
        writer = connect_write(db, purpose="test/reader-html-store/write")
        try:
            _store(writer)
        finally:
            writer.close()
        from substrate.books.serve import serve_full_text

        result = serve_full_text(con, "doc-url-abc", owner=True)
        assert result.reason == "owner_personal_reading"
        assert result.content_format == "text"
    finally:
        con.close()
