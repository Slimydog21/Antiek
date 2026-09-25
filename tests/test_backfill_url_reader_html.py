"""One-row legacy URL reader HTML recovery on a synthetic DuckDB."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from runtime.db_lock import connect_read, connect_write
from substrate.books.html_sanitizer import SANITIZER_VERSION
from substrate.constants import PERSONAL_READING_CONTENT_CLASS
from substrate.graph.schema import init_database
from substrate.reader_html.store import serve_reader_html, store_reader_html
from tools import backfill_url_reader_html as tool


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    path = str(tmp_path / "synthetic.duckdb")
    with connect_write(path, purpose="test/url-reader-backfill/init") as con:
        init_database(con)
        rows = [
            ("target", "web_article", PERSONAL_READING_CONTENT_CLASS,
             "# Heading\n\nBody <script>alert(1)</script>\n\n"
             "![remote](https://example.invalid/tracker.png)\n\n"
             "[bad](javascript:alert)", "__operator__"),
            ("other", "web_article", PERSONAL_READING_CONTENT_CLASS,
             "# Unrelated body", "__operator__"),
            ("wrong-type", "book", PERSONAL_READING_CONTENT_CLASS, "text", "__operator__"),
            ("wrong-class", "web_article", "restricted_pending_opt_in", "text", "__operator__"),
            ("empty", "web_article", PERSONAL_READING_CONTENT_CLASS, " ", "__operator__"),
            ("foreign", "web_article", PERSONAL_READING_CONTENT_CLASS, "text", "friend"),
            ("takedown", "web_article", PERSONAL_READING_CONTENT_CLASS, "text", "__operator__"),
            ("existing", "web_article", PERSONAL_READING_CONTENT_CLASS, "text", "__operator__"),
        ]
        for doc_id, doc_type, content_class, raw, owner in rows:
            con.execute(
                "INSERT INTO documents (document_id, source_tier, document_type, "
                "content_class, raw_text, metadata, title, source_uri, owner_user_id) "
                "VALUES (?, 4, ?, ?, ?, '{}', ?, ?, ?)",
                [doc_id, doc_type, content_class, raw, "PRIVATE TITLE", "https://private.invalid/url", owner],
            )
        con.execute(
            "INSERT INTO book_assets (document_id, taken_down) VALUES ('takedown', TRUE)"
        )
        store_reader_html(con, document_id="existing", main_html="<p>edited</p>",
                          source_kind="url")
        con.execute("UPDATE document_reader_html SET edited_at = now() WHERE document_id = 'existing'")
    return path


def _sidecars(path: str) -> list[tuple[Any, ...]]:
    with connect_read(path) as con:
        return con.execute(
            "SELECT document_id, html_body, sanitizer_version, source_kind, "
            "source_url, edited_at, revision FROM document_reader_html ORDER BY document_id"
        ).fetchall()


def test_report_and_apply_one_row_without_changing_others(db_path: str, capsys: pytest.CaptureFixture[str]) -> None:
    before = _sidecars(db_path)
    assert tool.main(["--db-path", db_path, "--document-id", "target"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "eligible"
    assert len(report["raw_sha256"]) == 64
    assert _sidecars(db_path) == before
    assert tool.main(["--db-path", db_path, "--document-id", "target", "--apply",
                      "--expected-sha256", report["raw_sha256"]]) == 0
    output = capsys.readouterr().out
    assert "PRIVATE TITLE" not in output
    assert "private.invalid" not in output
    assert "tracker.png" not in output
    assert "alert(1)" not in output
    assert json.loads(output)["status"] == "written"
    after = _sidecars(db_path)
    assert len(after) == len(before) + 1
    assert after[0] == before[0]
    assert after[1][0] == "target"
    html = after[1][1]
    assert after[1][2] == SANITIZER_VERSION
    assert after[1][3] == "url_text_derived"
    assert after[1][4] is None
    assert "<h1>Heading</h1>" in html
    assert "<script" not in html
    assert "<img" not in html
    assert "javascript:" not in html
    assert "&lt;script&gt;" in html
    assert tool.main(["--db-path", db_path, "--document-id", "target", "--apply",
                      "--expected-sha256", report["raw_sha256"]]) == 0
    assert json.loads(capsys.readouterr().out)["reason"] == "already_present"
    assert _sidecars(db_path) == after
    with connect_read(db_path) as con:
        owner = serve_reader_html(con, "target", owner=True)
        non_owner = serve_reader_html(con, "target", owner=False)
    assert owner.content_format == "html"
    assert owner.source_kind == "url_text_derived"
    assert non_owner.content_format == "text"
    assert non_owner.body is None or non_owner.body != owner.body


@pytest.mark.parametrize("doc_id,reason", [
    ("missing", "not_found"),
    ("wrong-type", "wrong_document_type"),
    ("wrong-class", "wrong_content_class"),
    ("empty", "empty_raw_text"),
    ("foreign", "not_single_operator_owned"),
    ("takedown", "taken_down"),
    ("existing", "already_present"),
])
def test_refusal_has_no_mutation(db_path: str, doc_id: str, reason: str) -> None:
    before = _sidecars(db_path)
    report = tool.run(db_path, doc_id)
    assert report["reason"] == reason
    result = tool.run(db_path, doc_id, apply=True,
                      expected_sha256=report["raw_sha256"] or "0" * 64)
    assert result["reason"] == reason or (doc_id == "missing" and result["reason"] == "digest_changed")
    assert _sidecars(db_path) == before


def test_digest_race_and_input_output_bounds(db_path: str) -> None:
    digest = tool.run(db_path, "target")["raw_sha256"]
    with connect_write(db_path, purpose="test/url-reader-backfill/change") as con:
        con.execute("UPDATE documents SET raw_text = 'changed body' WHERE document_id = 'target'")
    assert tool.run(db_path, "target", apply=True, expected_sha256=digest)["reason"] == "digest_changed"
    assert len(_sidecars(db_path)) == 1
    with connect_write(db_path, purpose="test/url-reader-backfill/bound") as con:
        con.execute("UPDATE documents SET raw_text = ? WHERE document_id = 'target'", ["&" * 200_000])
    report = tool.run(db_path, "target")
    assert report["reason"] == "oversized_text_or_html"
    assert tool.run(db_path, "target", apply=True,
                    expected_sha256=report["raw_sha256"])["reason"] == report["reason"]
    with connect_write(db_path, purpose="test/url-reader-backfill/bound-input") as con:
        con.execute("UPDATE documents SET raw_text = ? WHERE document_id = 'target'", ["x" * 500_001])
    assert tool.run(db_path, "target")["reason"] == "oversized_text_or_html"
    assert len(_sidecars(db_path)) == 1


def test_rights_drift_refuses_write(db_path: str) -> None:
    before = _sidecars(db_path)
    with connect_write(db_path, purpose="test/url-reader-backfill/rights") as con:
        con.execute(
            "UPDATE documents SET metadata = ? WHERE document_id = 'target'",
            [json.dumps({"license_uri": "https://arxiv.org/licenses/nonexclusive-distrib/1.0/",
                         "arxiv_id": "2501.00001"})],
        )
    report = tool.run(db_path, "target")
    assert report["reason"] == "rights_refused"
    assert tool.run(db_path, "target", apply=True,
                    expected_sha256=report["raw_sha256"])["reason"] == "rights_refused"
    assert _sidecars(db_path) == before


def test_cli_requires_exact_id_and_digest(db_path: str) -> None:
    with pytest.raises(SystemExit):
        tool.main(["--db-path", db_path, "--document-id", "*"])
    with pytest.raises(SystemExit):
        tool.main(["--db-path", db_path, "--document-id", "target", "--apply"])
