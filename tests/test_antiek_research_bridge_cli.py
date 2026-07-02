"""Top-level Antiek research bridge CLI tests."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from antiek.cli import main
from runtime.db_lock import connect_write
from substrate.graph.schema import init_database_at_path
from substrate.research_bridge.schema import init_research_bridge


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> str:
    d = tempfile.mkdtemp()
    path = os.path.join(d, "dogfood.duckdb")
    ev = os.path.join(d, "events")
    os.makedirs(ev, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", ev)
    init_database_at_path(path)
    con = connect_write(path, purpose="research_bridge_cli_test")
    try:
        init_research_bridge(con)
        con.execute(
            "INSERT INTO deliverables "
            "(deliverable_id, title, deliverable_kind, owner_user_id) VALUES "
            "('dlv-a', 'Draft A', 'research_memo', '__operator__')"
        )
    finally:
        con.close()
    return path


def _seed_minimal_report_rows(db_path: str) -> None:
    con = connect_write(db_path, purpose="seed top-level research bridge cli")
    try:
        con.execute(
            "INSERT INTO research_gap_runs "
            "(run_id, session_id, scope_block_ids, scope_question_ids, "
            " cluster_model_id) VALUES "
            "('run-a', 'sess-a', '[]', '[]', 'model-g')"
        )
        con.execute(
            "INSERT INTO research_gap_prompts "
            "(prompt_id, run_id, order_index, prompt_text, target_provider) VALUES "
            "('prompt-a', 'run-a', 0, 'Prompt A', 'grok')"
        )
        con.execute(
            "INSERT INTO research_gap_prompt_signals "
            "(signal_id, prompt_id, signal_type) VALUES "
            "('sig-a', 'prompt-a', 'would_run')"
        )
    finally:
        con.close()


def test_antiek_research_bridge_dogfood_report_writes_default_path(
    db: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_minimal_report_rows(db)
    monkeypatch.setenv("HOME", str(tmp_path))

    rc = main(["research", "bridge", "dogfood-report", "--db", db])

    assert rc == 0
    report_path = tmp_path / "Desktop" / "Antiek" / "runs" / "adrb" / "dogfood_metrics.md"
    text = report_path.read_text(encoding="utf-8")
    assert "# Antiek Deep Research Bridge Dogfood Metrics" in text
    assert "S3 status: PASS" in text
    assert "Mode B would-run rate: 100.0% (1/1 latest prompt signals)" in text


def test_antiek_research_bridge_dogfood_report_accepts_output_override(
    db: str,
    tmp_path: Path,
) -> None:
    _seed_minimal_report_rows(db)
    out = tmp_path / "metrics.md"

    rc = main([
        "research",
        "bridge",
        "dogfood-report",
        "--db",
        db,
        "--output",
        str(out),
    ])

    assert rc == 0
    assert "S3 status: PASS" in out.read_text(encoding="utf-8")


def test_antiek_research_bridge_dogfood_log_init_preserves_operator_log(
    tmp_path: Path,
) -> None:
    root = tmp_path / "adrb"
    assert main(["research", "bridge", "dogfood-log", "init", "--root", str(root)]) == 0
    operator_log = root / "operator-log.md"
    operator_log.write_text("operator notes\n", encoding="utf-8")

    assert main(["research", "bridge", "dogfood-log", "init", "--root", str(root)]) == 0

    assert operator_log.read_text(encoding="utf-8") == "operator notes\n"


def test_antiek_research_bridge_draft_export_record(db: str, tmp_path: Path) -> None:
    out = tmp_path / "draft-a.md"

    rc = main([
        "research",
        "bridge",
        "draft-export",
        "record",
        "--db",
        db,
        "--session-id",
        "sess-a",
        "--deliverable-id",
        "dlv-a",
        "--output-path",
        str(out),
    ])

    assert rc == 0
    report = tmp_path / "metrics.md"
    assert main([
        "research",
        "bridge",
        "dogfood-report",
        "--db",
        db,
        "--output",
        str(report),
    ]) == 0
    assert "- Mode A draft exports recorded: 1" in report.read_text(encoding="utf-8")


def test_antiek_research_bridge_signals_prints_would_run_percentage(
    db: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_minimal_report_rows(db)

    rc = main(["research", "bridge", "signals", "--db", db])

    assert rc == 0
    assert "all runs: 100.0% would-run (1/1 latest prompt signals)" in capsys.readouterr().out


def test_antiek_research_bridge_signals_can_scope_to_run(
    db: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_minimal_report_rows(db)

    rc = main(["research", "bridge", "signals", "--db", db, "--run-id", "run-a"])

    assert rc == 0
    assert "run run-a: 100.0% would-run (1/1 latest prompt signals)" in (
        capsys.readouterr().out
    )
