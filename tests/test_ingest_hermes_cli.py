"""CLI contract for tools.ingest_hermes — dry-run default, plan, apply."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from runtime.db_lock import connect_read
from substrate.graph.schema import init_database_at_path
from tools.ingest_hermes import main, plan


@pytest.fixture
def hermes_dir(tmp_path: Path):
    d = tmp_path / "events"
    d.mkdir()
    line = json.dumps(
        {
            "event_id": "e1",
            "investigation_id": "inv-cli",
            "emitted_at": "2026-07-01T00:00:00Z",
            "action_type": "synthesize",
            "payload": {"sub_question": "what compounds?"},
        }
    )
    (d / "t.jsonl").write_text(line + "\n", encoding="utf-8")
    return d


def test_plan_counts(hermes_dir: Path):
    # plan requires allowed_roots — set env so default_allowed_roots includes hermes_dir
    os.environ["ANTIEK_HERMES_EVENTS_DIR"] = str(hermes_dir)
    try:
        events, invs, ids = plan(hermes_dir, limit=None)
    finally:
        os.environ.pop("ANTIEK_HERMES_EVENTS_DIR", None)
    assert events == 1
    assert invs == 1
    assert ids == ["inv-cli"]


def test_dry_run_exits_zero_without_db(hermes_dir: Path, capsys):
    os.environ["ANTIEK_HERMES_EVENTS_DIR"] = str(hermes_dir)
    try:
        code = main(["--events-dir", str(hermes_dir)])
    finally:
        os.environ.pop("ANTIEK_HERMES_EVENTS_DIR", None)
    assert code == 0
    out = capsys.readouterr().out
    assert "DRY-RUN" in out
    assert "inv-cli" in out


def test_dry_run_writes_evidence_without_payload_text(hermes_dir: Path, tmp_path: Path):
    receipt = tmp_path / "receipt.json"
    os.environ["ANTIEK_HERMES_EVENTS_DIR"] = str(hermes_dir)
    try:
        code = main(["--events-dir", str(hermes_dir), "--evidence-json", str(receipt)])
    finally:
        os.environ.pop("ANTIEK_HERMES_EVENTS_DIR", None)
    assert code == 0
    data = json.loads(receipt.read_text(encoding="utf-8"))
    assert data["schema"] == "antiek.hermes_ingest_cli.evidence.v1"
    assert data["mode"] == "dry_run"
    assert data["writes_performed"] is False
    assert data["payload_text_included"] is False
    assert data["provider_calls_made"] is False
    assert data["parsed_events"] == 1
    assert data["investigation_ids"] == ["inv-cli"]
    assert "what compounds" not in receipt.read_text(encoding="utf-8")


def test_apply_writes_scratch_graph_and_evidence(hermes_dir: Path, tmp_path: Path):
    db = tmp_path / "graph.duckdb"
    receipt = tmp_path / "apply-receipt.json"
    init_database_at_path(str(db))
    os.environ["ANTIEK_HERMES_EVENTS_DIR"] = str(hermes_dir)
    try:
        code = main(
            [
                "--events-dir",
                str(hermes_dir),
                "--db-path",
                str(db),
                "--limit",
                "1",
                "--apply",
                "--evidence-json",
                str(receipt),
            ]
        )
    finally:
        os.environ.pop("ANTIEK_HERMES_EVENTS_DIR", None)
    assert code == 0
    with connect_read(str(db)) as con:
        rows = con.execute(
            "SELECT document_id, document_type, title FROM documents"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "uploaded_markdown"
    data = json.loads(receipt.read_text(encoding="utf-8"))
    assert data["mode"] == "apply"
    assert data["writes_performed"] is True
    assert data["new"] == 1
    assert data["cache"] == 0
    assert data["err"] == 0
    assert data["malformed"] == 0
    assert data["results"] == [
        {
            "investigation_id": "inv-cli",
            "document_id": rows[0][0],
            "status": "ok",
            "events_count": 1,
            "was_new": True,
            "source_label": "hermes:inv-cli",
            "document_type": "uploaded_markdown",
            "error": None,
        }
    ]
    assert data["distillation_run"] is False
    assert data["provider_calls_made"] is False


def test_outside_root_fails(tmp_path: Path):
    outsider = tmp_path / "not-hermes"
    outsider.mkdir()
    code = main(["--events-dir", str(outsider)])
    assert code == 2
