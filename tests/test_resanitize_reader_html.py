"""Tests for tools/resanitize_reader_html.py against a synthetic DuckDB.

Seeds document_reader_html rows stamped with the current sanitizer version and
with a stale one — including a stale row with empty raw_text and a stale row an
operator edited — and asserts:

* --report inventories stale rows by content_class and version without writing
* --apply re-stamps repairable rows from raw_text (sanitizer version current,
  body re-sanitized, source_kind preserved), honouring --limit exactly
* empty-raw_text and operator-edited rows are reported, never rewritten
* content_class is NEVER mutated
* a repeat --apply finds nothing left for the rows it already re-stamped
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime.db_lock import connect_read, connect_write  # noqa: E402
from substrate.books.html_sanitizer import SANITIZER_VERSION  # noqa: E402
from substrate.graph.schema import init_database  # noqa: E402
from substrate.reader_html.store import store_reader_html  # noqa: E402
from tools import resanitize_reader_html as tool  # noqa: E402

STALE_VERSION = "books-allowlist/1.2.0"


@pytest.fixture
def seeded_db():
    tmp = tempfile.mkdtemp(prefix="antiek-resanitize-")
    db_path = os.path.join(tmp, "graph.duckdb")
    con = connect_write(db_path, purpose="resanitize-test-init")
    try:
        init_database(con)
        # (document_id, content_class, raw_text, stamped_version, edited)
        seeds = [
            ("doc-current", "user_owned", "# Fresh\n\nBody.", SANITIZER_VERSION, False),
            ("doc-stale-pd", "public_domain", "# Gettysburg\n\nFour score.", STALE_VERSION, False),
            (
                "doc-stale-gated",
                "restricted_pending_opt_in",
                "# Gated\n\nClassified-ish body.",
                STALE_VERSION,
                False,
            ),
            (
                "doc-stale-html",
                "user_owned",
                "<section><h1>Import</h1><p>Hello <script>alert(1)</script></p>"
                "<embed src=\"x\"><p>After the embed.</p></section>",
                STALE_VERSION,
                False,
            ),
            ("doc-stale-empty", "user_owned", "", STALE_VERSION, False),
            ("doc-stale-edited", "user_owned", "# Edited\n\nBody.", STALE_VERSION, True),
        ]
        for document_id, content_class, raw_text, version, edited in seeds:
            con.execute(
                "INSERT INTO documents (document_id, source_tier, document_type, "
                "content_class, raw_text, metadata, title, source_uri) "
                "VALUES (?, 2, 'book', ?, ?, '{}', ?, ?)",
                [document_id, content_class, raw_text, document_id, f"antiek://test/{document_id}"],
            )
            store_reader_html(
                con,
                document_id=document_id,
                main_html="<p>Truncated at the first embed</p>",
                source_kind="url",
                source_url=f"antiek://test/{document_id}",
            )
            # store_reader_html always stamps the current version; the stale
            # rows are what a sanitizer bump leaves behind, so downgrade them
            # the way history did — in place.
            con.execute(
                "UPDATE document_reader_html SET sanitizer_version = ?, "
                "edited_at = CASE WHEN ? THEN now() ELSE NULL END WHERE document_id = ?",
                [version, edited, document_id],
            )
    finally:
        con.close()
    return db_path


def _versions(db_path: str) -> dict[str, str]:
    con = connect_read(db_path)
    try:
        return dict(
            con.execute(
                "SELECT document_id, sanitizer_version FROM document_reader_html"
            ).fetchall()
        )
    finally:
        con.close()


def _classes(db_path: str) -> dict[str, str | None]:
    con = connect_read(db_path)
    try:
        return dict(
            con.execute("SELECT document_id, content_class FROM documents").fetchall()
        )
    finally:
        con.close()


def _body(db_path: str, document_id: str) -> str:
    con = connect_read(db_path)
    try:
        return con.execute(
            "SELECT html_body FROM document_reader_html WHERE document_id = ?",
            [document_id],
        ).fetchone()[0]
    finally:
        con.close()


def test_report_inventories_stale_rows_without_writing(seeded_db, capsys):
    before = _versions(seeded_db)
    plan, written = tool.run(seeded_db, apply=False)
    out = capsys.readouterr().out
    assert written is None
    assert plan.sidecar_rows == 6
    assert plan.current == 1
    assert plan.stale == 5
    assert plan.repairable == 3  # pd + gated + html
    assert plan.skipped_empty == 1
    assert plan.skipped_edited == 1
    assert plan.by_content_class == {
        "public_domain": 1,
        "restricted_pending_opt_in": 1,
        "user_owned": 3,
    }
    assert plan.by_stamped_version == {STALE_VERSION: 5}
    assert "REPORT (nothing written)" in out
    assert "skip=empty_raw_text" in out
    assert "skip=edited" in out
    assert _versions(seeded_db) == before


def test_apply_restamps_from_raw_text_and_preserves_rights(seeded_db):
    before_classes = _classes(seeded_db)
    plan, written = tool.run(seeded_db, apply=True)
    assert plan.stale == 5
    assert written == 3
    versions = _versions(seeded_db)
    assert versions["doc-stale-pd"] == SANITIZER_VERSION
    assert versions["doc-stale-gated"] == SANITIZER_VERSION
    assert versions["doc-stale-html"] == SANITIZER_VERSION
    # Reported, never rewritten.
    assert versions["doc-stale-empty"] == STALE_VERSION
    assert versions["doc-stale-edited"] == STALE_VERSION
    assert _classes(seeded_db) == before_classes

    # The body came from raw_text through the current sanitizer, not from the
    # old (truncated) output: the content after the <embed> survives and the
    # script does not.
    body = _body(seeded_db, "doc-stale-html")
    assert "After the embed." in body
    assert "<script" not in body.lower()
    assert "<embed" not in body.lower()
    assert "<h1>Gettysburg</h1>" in _body(seeded_db, "doc-stale-pd")

    con = connect_read(seeded_db)
    try:
        kind, revision = con.execute(
            "SELECT source_kind, revision FROM document_reader_html WHERE document_id = ?",
            ["doc-stale-pd"],
        ).fetchone()
    finally:
        con.close()
    assert kind == "url"  # the row's own provenance is kept
    assert revision == 2


def test_limit_caps_the_restamp_exactly_and_repeat_finds_nothing_left(seeded_db):
    plan_before, _ = tool.run(seeded_db, apply=False)
    plan_after_first, written = tool.run(seeded_db, apply=True, limit=2)
    assert written == 2
    plan_report, _ = tool.run(seeded_db, apply=False)
    assert plan_report.stale == plan_before.stale - written
    # The remaining repairable row goes on the next pass; a further pass has
    # nothing left for the rows already re-stamped.
    _, second = tool.run(seeded_db, apply=True, limit=5)
    assert second == 1
    _, third = tool.run(seeded_db, apply=True, limit=5)
    assert third == 0
    final, _ = tool.run(seeded_db, apply=False)
    assert final.repairable == 0
    assert final.stale == 2  # empty + edited, reported and left alone
    assert plan_after_first.stale == plan_before.stale  # plans describe the pre-apply scan


def test_limit_zero_writes_nothing(seeded_db):
    before = _versions(seeded_db)
    _, written = tool.run(seeded_db, apply=True, limit=0)
    assert written == 0
    assert _versions(seeded_db) == before


def test_cli_requires_db_and_refuses_report_with_apply(tmp_path):
    missing = tmp_path / "nope.duckdb"
    assert tool.main(["--db-path", str(missing), "--report"]) == 2
    with pytest.raises(SystemExit):
        tool.main(["--db-path", str(missing), "--report", "--apply"])
