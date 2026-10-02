"""Internal editor-metadata preservation for the trusted sidecar writer."""

from __future__ import annotations

from datetime import datetime

import duckdb

from runtime.db_lock import connect_write
from substrate.books.html_sanitizer import SANITIZER_VERSION
from substrate.graph.schema import init_database
from substrate.reader_html.store import store_reader_html


def _database(tmp_path):
    db_path = str(tmp_path / "graph.duckdb")
    con = connect_write(db_path, purpose="test/reader-html-edit-metadata/schema")
    try:
        init_database(con)
        con.execute(
            """
            INSERT INTO documents (
                document_id, document_type, content_class, source_tier,
                raw_text, metadata, source_uri, title
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                "doc-edit-metadata",
                "web_article",
                "personal_reading",
                4,
                "# Title\n\nBody",
                "{}",
                "https://example.test/source",
                "Title",
            ],
        )
    finally:
        con.close()
    return db_path


def _sidecar(con):
    return con.execute(
        """
        SELECT html_body, sanitizer_version, source_kind, source_url,
               captured_at, edited_at, revision
        FROM document_reader_html WHERE document_id = ?
        """,
        ["doc-edit-metadata"],
    ).fetchone()


def test_explicit_editor_timestamp_survives_insert_and_resanitize_upsert(tmp_path):
    db_path = _database(tmp_path)
    edited_at = datetime(2026, 9, 30, 12, 34, 56, 123456)
    writer = connect_write(db_path, purpose="test/reader-html-edit-metadata/write")
    try:
        initial_html = "<article><p>first <script>drop()</script> body</p></article>"
        initial_length = store_reader_html(
            writer,
            document_id="doc-edit-metadata",
            main_html=initial_html,
            source_kind="upload_md",
            source_url="https://example.test/upload",
            edited_at=edited_at,
        )
        first = _sidecar(writer)
        assert first is not None
        assert first[0] == "<article><p>first  body</p></article>"
        assert first[1] == SANITIZER_VERSION
        assert first[2:4] == ("upload_md", "https://example.test/upload")
        assert first[4] is not None
        assert first[5] == edited_at
        assert first[6] == 1
        assert initial_length == len(first[0].encode("utf-8"))

        # The same trusted writer sanitizes the replacement and preserves the
        # supplied stored editor timestamp while retaining normal upsert rules.
        replacement = "<article><h1>updated</h1><p>café</p></article>"
        updated_length = store_reader_html(
            writer,
            document_id="doc-edit-metadata",
            main_html=replacement,
            source_kind="upload_md",
            source_url="https://example.test/upload",
            edited_at=edited_at,
        )
        second = _sidecar(writer)
        assert second is not None
        assert second[0] == replacement
        assert second[1] == SANITIZER_VERSION
        assert second[2:4] == ("upload_md", "https://example.test/upload")
        assert second[4] is not None and second[4] != first[4]
        assert second[5] == edited_at
        assert second[6] == 2
        assert updated_length == len(second[0].encode("utf-8"))
    finally:
        writer.close()


def test_omitted_and_explicit_none_keep_default_edit_timestamp_clearing(tmp_path):
    db_path = _database(tmp_path)
    old_edit = datetime(2026, 9, 29, 8, 0, 0)
    writer = connect_write(db_path, purpose="test/reader-html-edit-metadata/write")
    try:
        store_reader_html(
            writer,
            document_id="doc-edit-metadata",
            main_html="<p>initial</p>",
            source_kind="upload_html",
            source_url="https://example.test/html",
            edited_at=old_edit,
        )
        initial = _sidecar(writer)
        assert initial is not None and initial[5] == old_edit

        # An omitted optional value has the exact former behavior on conflict.
        store_reader_html(
            writer,
            document_id="doc-edit-metadata",
            main_html="<p>default clears</p>",
            source_kind="upload_html",
            source_url="https://example.test/html",
        )
        omitted = _sidecar(writer)
        assert omitted is not None
        assert omitted[5] is None
        assert omitted[6] == 2
        assert omitted[2:4] == ("upload_html", "https://example.test/html")

        # Explicit None is equivalent to omission, including a further revision.
        second_edit = datetime(2026, 9, 29, 9, 0, 0)
        store_reader_html(
            writer,
            document_id="doc-edit-metadata",
            main_html="<p>mark edited</p>",
            source_kind="upload_html",
            source_url="https://example.test/html",
            edited_at=second_edit,
        )
        store_reader_html(
            writer,
            document_id="doc-edit-metadata",
            main_html="<p>explicit none clears</p>",
            source_kind="upload_html",
            source_url="https://example.test/html",
            edited_at=None,
        )
        explicit_none = _sidecar(writer)
        assert explicit_none is not None
        assert explicit_none[5] is None
        assert explicit_none[6] == 4
    finally:
        writer.close()


def test_store_still_requires_locked_connection(tmp_path):
    db_path = _database(tmp_path)
    con = duckdb.connect(db_path)
    try:
        try:
            store_reader_html(
                con,  # type: ignore[arg-type]
                document_id="doc-edit-metadata",
                main_html="<p>not written</p>",
                source_kind="upload_md",
                edited_at=datetime(2026, 9, 30, 12, 0, 0),
            )
        except TypeError as exc:
            assert "LockedConnection" in str(exc)
        else:
            raise AssertionError("plain DuckDB connection must not write sidecars")
        assert con.execute("SELECT COUNT(*) FROM document_reader_html").fetchone() == (0,)
    finally:
        con.close()
