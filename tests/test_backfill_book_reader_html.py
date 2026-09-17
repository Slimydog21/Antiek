"""Tests for tools/backfill_book_reader_html.py against a synthetic DuckDB.

Seeds book_assets with and without document_reader_html, including a gated
row, and asserts:

* dry-run counts / convertible inventory
* --apply writes sidecars via store_reader_html (sanitizer version stamped)
* content_class is NEVER mutated (gated stays gated)
* idempotent second --apply
* HTML-shaped / book_import bodies pass through without markdown escaping
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime.db_lock import connect_read, connect_write  # noqa: E402
from substrate.books.html_sanitizer import (  # noqa: E402
    SANITIZER_VERSION,
    sanitized_html_provenance,
)
from substrate.graph.schema import init_database  # noqa: E402
from substrate.reader_html.store import store_reader_html  # noqa: E402
from tools import backfill_book_reader_html as tool  # noqa: E402


@pytest.fixture
def seeded_db():
    tmp = tempfile.mkdtemp(prefix="antiek-book-reader-html-bf-")
    db_path = os.path.join(tmp, "graph.duckdb")
    con = connect_write(db_path, purpose="book-reader-html-bf-test-init")
    try:
        init_database(con)
        seeds = [
            # already has sidecar
            (
                "doc-has-sidecar",
                "user_owned",
                "# Already HTML native\n\nBody.",
                "{}",
                True,
            ),
            # markdown gap — public
            (
                "doc-gap-pd",
                "public_domain",
                "# Gettysburg\n\nFour score and seven years ago.",
                "{}",
                False,
            ),
            # markdown gap — gated (must stay gated; sidecar still allowed)
            (
                "doc-gap-gated",
                "restricted_pending_opt_in",
                "# Gated Radar Notes\n\n## Page 1\n\nClassified-ish corpus body.",
                "{}",
                False,
            ),
            # empty raw_text — skip
            (
                "doc-gap-empty",
                "user_owned",
                "",
                "{}",
                False,
            ),
            # HTML body from book_import provenance
            (
                "doc-gap-html",
                "user_owned",
                "<section id=\"antiek-chapter-0\"><h1>Import</h1>"
                "<p>Hello <script>alert(1)</script></p></section>",
                json.dumps(
                    {
                        **sanitized_html_provenance(),
                        "book_import": {
                            "converter_version": "book-import-epub/1.0.0",
                            "source_format": "epub",
                        },
                    }
                ),
                False,
            ),
        ]
        for document_id, content_class, raw_text, metadata, with_sidecar in seeds:
            con.execute(
                "INSERT INTO documents (document_id, source_tier, document_type, "
                "content_class, raw_text, metadata, title, source_uri) "
                "VALUES (?, 2, 'book', ?, ?, ?, ?, ?)",
                [
                    document_id,
                    content_class,
                    raw_text,
                    metadata,
                    document_id,
                    f"antiek://test/{document_id}",
                ],
            )
            con.execute(
                "INSERT INTO book_assets (document_id, license_basis, page_count) "
                "VALUES (?, ?, 1)",
                [document_id, content_class],
            )
            if with_sidecar:
                store_reader_html(
                    con,
                    document_id=document_id,
                    main_html="<p>Already stored</p>",
                    source_kind="book",
                    source_url=f"antiek://test/{document_id}",
                )
    finally:
        con.close()
    return db_path


def _sidecar_ids(db_path: str) -> set[str]:
    con = connect_read(db_path)
    try:
        return {
            row[0]
            for row in con.execute(
                "SELECT document_id FROM document_reader_html"
            ).fetchall()
        }
    finally:
        con.close()


def _classes(db_path: str) -> dict[str, str | None]:
    con = connect_read(db_path)
    try:
        return {
            doc_id: cc
            for doc_id, cc in con.execute(
                "SELECT document_id, content_class FROM documents"
            ).fetchall()
        }
    finally:
        con.close()


def test_raw_text_to_main_html_markdown_escapes():
    html, kind = tool.raw_text_to_main_html("# Hi\n\n<a>x</a>")
    assert kind == tool.SOURCE_KIND_BOOK
    assert "<h1>Hi</h1>" in html
    assert "&lt;a&gt;x&lt;/a&gt;" in html


def test_raw_text_to_main_html_book_import_passthrough():
    body = "<section><p>ok</p><script>x</script></section>"
    html, kind = tool.raw_text_to_main_html(
        body,
        {**sanitized_html_provenance(), "book_import": {"source_format": "epub"}},
    )
    assert kind == tool.SOURCE_KIND_BOOK_IMPORT
    assert html == body


def test_dry_run_inventory(seeded_db, capsys):
    plan = tool.run(seeded_db, apply=False)
    out = capsys.readouterr().out
    assert plan.book_assets_active == 5
    assert plan.with_sidecar == 1
    assert plan.missing_sidecar == 4
    assert plan.convertible == 3  # pd + gated + html; empty skipped
    assert plan.skipped_empty == 1
    assert plan.by_content_class["restricted_pending_opt_in"] == 1
    assert "DRY RUN" in out
    assert _sidecar_ids(seeded_db) == {"doc-has-sidecar"}


def test_apply_writes_sidecars_preserves_rights(seeded_db):
    before_classes = _classes(seeded_db)
    plan = tool.run(seeded_db, apply=True)
    assert plan.convertible == 3
    ids = _sidecar_ids(seeded_db)
    assert "doc-has-sidecar" in ids
    assert "doc-gap-pd" in ids
    assert "doc-gap-gated" in ids
    assert "doc-gap-html" in ids
    assert "doc-gap-empty" not in ids

    after_classes = _classes(seeded_db)
    assert after_classes == before_classes
    assert after_classes["doc-gap-gated"] == "restricted_pending_opt_in"

    con = connect_read(seeded_db)
    try:
        version, kind, body = con.execute(
            "SELECT sanitizer_version, source_kind, html_body "
            "FROM document_reader_html WHERE document_id = ?",
            ["doc-gap-pd"],
        ).fetchone()
        assert version == SANITIZER_VERSION
        assert kind == "book"
        assert "<h1>Gettysburg</h1>" in body

        version2, kind2, body2 = con.execute(
            "SELECT sanitizer_version, source_kind, html_body "
            "FROM document_reader_html WHERE document_id = ?",
            ["doc-gap-html"],
        ).fetchone()
        assert version2 == SANITIZER_VERSION
        assert kind2 == "book_import"
        assert "<script" not in body2.lower()
        assert "alert" not in body2.lower()
    finally:
        con.close()


def test_apply_idempotent(seeded_db):
    tool.run(seeded_db, apply=True)
    first = _sidecar_ids(seeded_db)
    tool.run(seeded_db, apply=True)
    assert _sidecar_ids(seeded_db) == first


def test_cli_requires_db(tmp_path):
    missing = tmp_path / "nope.duckdb"
    assert tool.main(["--db-path", str(missing)]) == 2
