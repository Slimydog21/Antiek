"""dogfood-report CLI tests (SPR-06).

Verifies the report's structure on three substrate states:

- Fresh DB: 'INSUFFICIENT DATA' branch, exit 0 (don't fail CI for an
  empty substrate).
- Pastes + extractions + gap-runs + signals at PASS rate: exit 0,
  'PASS' header, signal counts correct.
- Pastes + signals at FAIL rate: exit 6, 'FAIL' header.

Also tests the --out flag writes a file at the expected path.
"""

from __future__ import annotations

import io
import json
import os
import sys
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from typing import Iterator

import duckdb
import pytest


@pytest.fixture
def df_env(tmp_path: Path) -> Iterator[Path]:
    """Same shape as tests/research_bridge/test_cli.py::cli_env."""
    db = tmp_path / "df.duckdb"
    os.environ["ANTIEK_DUCKDB_PATH"] = str(db)
    from substrate.graph import init_database_at_path
    from substrate.research_bridge import init_research_bridge_at_path

    init_database_at_path(str(db))
    init_research_bridge_at_path(str(db))
    yield db
    del os.environ["ANTIEK_DUCKDB_PATH"]


def _run(argv: list[str]) -> tuple[int, str, str]:
    from tools.research_bridge_cli.main import main as cli_main
    out, err = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = cli_main(argv)
    except SystemExit as e:
        code = int(e.code) if e.code is not None else 0
    return code, out.getvalue(), err.getvalue()


# ---------------------------------------------------------------------------
# Fresh substrate
# ---------------------------------------------------------------------------


def test_dogfood_report_insufficient_data(df_env: Path) -> None:
    code, out, _ = _run(["dogfood-report"])
    assert code == 0  # empty substrate is not a CI fail
    assert "INSUFFICIENT DATA" in out
    assert "Total pastes: **0**" in out


def test_dogfood_report_json_insufficient(df_env: Path) -> None:
    code, out, _ = _run(["dogfood-report", "--json"])
    assert code == 0
    body = json.loads(out)
    assert body["s3_gate_passed"] is False
    assert body["total_signalled"] == 0
    assert body["n_pastes"] == 0


# ---------------------------------------------------------------------------
# Populated substrate — PASS
# ---------------------------------------------------------------------------


def _bootstrap_pastes_and_signals(
    df_env: Path,
    fixture_text,
    monkeypatch,
    *,
    n_would_run: int,
    n_skip: int,
):
    """Set up enough state for a meaningful dogfood-report run.
    Reuses the dispatch-patching helpers from test_cli."""
    from tests.research_bridge.test_cli import (
        _ingest_and_extract_via_cli,
        _patch_dispatch_sequence,
    )

    doc_a = _ingest_and_extract_via_cli(monkeypatch, "anthropic", fixture_text)
    doc_b = _ingest_and_extract_via_cli(monkeypatch, "alphasense", fixture_text)

    # Read the question_ids the extractor populated.
    db_path = os.environ["ANTIEK_DUCKDB_PATH"]
    con = duckdb.connect(db_path, read_only=True)
    try:
        qids = [
            row[0] for row in con.execute(
                "SELECT question_id FROM research_paste_open_questions "
                "WHERE document_id IN (?, ?)",
                [doc_a, doc_b],
            ).fetchall()
        ]
    finally:
        con.close()

    total = n_would_run + n_skip
    assert total >= 1
    _patch_dispatch_sequence(monkeypatch, [
        {"text": json.dumps({"clusters": [{
            "label": "Verifier productisation timeline",
            "priority_rank": 0,
            "question_ids": qids,
        }]}), "model_id": "fake"},
        {"text": json.dumps({"prompts": [
            {
                "cluster_id": "__placeholder__",
                "order_index": i,
                "prompt_text": f"Verifier productisation status check #{i}",
                "target_provider": "anthropic",
                "rationale": "x",
            }
            for i in range(total)
        ]}), "model_id": "fake"},
    ])
    code, out, _ = _run([
        "find-gaps", doc_a, doc_b, "--label", "df setup", "--json",
    ])
    assert code == 0
    payload = json.loads(out)
    prompt_ids = [
        row[0] for row in duckdb.connect(db_path, read_only=True).execute(
            "SELECT prompt_id FROM research_gap_prompts ORDER BY order_index"
        ).fetchall()
    ]
    assert len(prompt_ids) == total

    # Drop signals
    for i in range(n_would_run):
        c, _, _ = _run(["signal", prompt_ids[i], "--type", "would_run"])
        assert c == 0
    for i in range(n_would_run, total):
        c, _, _ = _run(["signal", prompt_ids[i], "--type", "skip"])
        assert c == 0
    return doc_a, doc_b, prompt_ids


def test_dogfood_report_s3_pass(df_env: Path, fixture_text, monkeypatch) -> None:
    """3 👍 / 2 👎 → 60% → S3 PASS."""
    _bootstrap_pastes_and_signals(
        df_env, fixture_text, monkeypatch,
        n_would_run=3, n_skip=2,
    )
    code, out, _ = _run(["dogfood-report"])
    assert code == 0
    assert "S3 gate — PASS" in out
    # Counts surfaced
    assert "👍 would_run: 3" in out
    assert "👎 skip: 2" in out
    assert "Total pastes: **2**" in out


def test_dogfood_report_s3_fail(df_env: Path, fixture_text, monkeypatch) -> None:
    """1 👍 / 4 👎 → 20% → S3 FAIL → exit code 6."""
    _bootstrap_pastes_and_signals(
        df_env, fixture_text, monkeypatch,
        n_would_run=1, n_skip=4,
    )
    code, out, _ = _run(["dogfood-report"])
    assert code == 6
    assert "S3 gate — FAIL" in out


def test_dogfood_report_writes_file(
    df_env: Path, fixture_text, monkeypatch, tmp_path: Path
) -> None:
    _bootstrap_pastes_and_signals(
        df_env, fixture_text, monkeypatch, n_would_run=4, n_skip=1,
    )
    out_dir = tmp_path / "metrics_dir"
    out_dir.mkdir()
    code, _, err = _run(["dogfood-report", "--out", str(out_dir)])
    assert code == 0
    written = out_dir / "dogfood_metrics.md"
    assert written.exists()
    content = written.read_text(encoding="utf-8")
    assert "S3 gate" in content
    assert "Total pastes" in content


def test_dogfood_report_json_populated(
    df_env: Path, fixture_text, monkeypatch
) -> None:
    _bootstrap_pastes_and_signals(
        df_env, fixture_text, monkeypatch, n_would_run=2, n_skip=1,
    )
    code, out, _ = _run(["dogfood-report", "--json"])
    assert code == 0
    body = json.loads(out)
    assert body["s3_gate_passed"] is True
    assert body["total_signalled"] == 3
    assert body["would_run_count"] == 2
    assert body["n_pastes"] == 2
    assert body["n_gap_runs"] == 1
    assert body["n_prompts"] == 3
