"""One-row legacy URL reader HTML recovery on a synthetic DuckDB."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
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
    assert report["raw_sha256"] is None
    assert report["raw_length"] is None
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
    approved_digest = tool.run(db_path, "target")["raw_sha256"]
    with connect_write(db_path, purpose="test/url-reader-backfill/rights") as con:
        con.execute(
            "UPDATE documents SET metadata = ? WHERE document_id = 'target'",
            [json.dumps({"license_uri": "https://arxiv.org/licenses/nonexclusive-distrib/1.0/",
                         "arxiv_id": "2501.00001"})],
        )
    report = tool.run(db_path, "target")
    assert report["reason"] == "rights_refused"
    assert report["raw_sha256"] is None
    assert report["raw_length"] is None
    assert tool.run(db_path, "target", apply=True,
                    expected_sha256=approved_digest)["reason"] == "rights_refused"
    assert _sidecars(db_path) == before


def test_report_owner_transfer_keeps_metadata_and_body_on_one_snapshot(
    db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_digest = tool.run(db_path, "target")["raw_sha256"]
    original_row = tool._row
    transferred = False
    with duckdb.connect(db_path) as updater:
        def transfer_after_preflight(con: Any, document_id: str) -> tuple[Any, ...] | None:
            nonlocal transferred
            row = original_row(con, document_id)
            if not transferred:
                updater.execute(
                    "UPDATE documents SET owner_user_id = 'friend', "
                    "raw_text = 'private body for friend' WHERE document_id = 'target'"
                )
                transferred = True
            return row

        with monkeypatch.context() as patch:
            patch.setattr(tool, "_row", transfer_after_preflight)
            report = tool.run(db_path, "target")
        assert transferred
        assert report["status"] == "eligible"
        assert report["raw_sha256"] == original_digest
        denied = tool.run(db_path, "target")
        assert denied["reason"] == "not_single_operator_owned"
        assert denied["raw_sha256"] is None


def test_null_body_is_empty_not_rights_refused(db_path: str) -> None:
    with connect_write(db_path, purpose="test/url-reader-backfill/null") as con:
        con.execute("UPDATE documents SET raw_text = NULL WHERE document_id = 'target'")
    report = tool.run(db_path, "target")
    assert report["reason"] == "empty_raw_text"
    assert report["raw_sha256"] is None


def test_cli_requires_exact_id_and_digest(db_path: str) -> None:
    with pytest.raises(SystemExit):
        tool.main(["--db-path", db_path, "--document-id", "*"])
    with pytest.raises(SystemExit):
        tool.main(["--db-path", db_path, "--document-id", "target", "--apply"])


def test_authenticated_reader_and_style_routes_after_apply(
    db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    digest = tool.run(db_path, "target")["raw_sha256"]
    assert tool.run(db_path, "target", apply=True, expected_sha256=digest)["status"] == "written"
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "synthetic-bearer")
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "owner@example.invalid")
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer synthetic-bearer"}
        reader = client.get("/sources/target/reader-html", headers=headers)
        assert reader.status_code == 200
        assert reader.json()["source_kind"] == "url_text_derived"
        assert reader.json()["content_format"] == "html"
        styled = client.get("/documents/target/render?style=academic-paper", headers=headers)
        assert styled.status_code == 200, styled.text
        assert "Antiek presentation reconstructed from retained text" in styled.text
        assert "The original page layout was not recovered" in styled.text
        assert "&lt;script&gt;" in styled.text
        assert "<script" not in styled.text
        assert "<img" not in styled.text

        assert client.get("/documents/target/render").status_code == 401
        assert client.get("/sources/target/reader-html").status_code == 401
        assert client.get("/documents/target/render", headers={
            "Authorization": "Bearer wrong-token",
        }).status_code == 401

        monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "owner@example.invalid,other@example.invalid")
        denied = client.get("/documents/target/render", headers=headers)
        assert denied.status_code == 403
        assert denied.json()["detail"] == "rights_denied"
