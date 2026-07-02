"""Dogfood metrics report for the Deep Research Bridge."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from runtime.db_lock import connect_read, connect_write
from substrate.graph.schema import init_database_at_path
from substrate.research_bridge.dogfood_report import (
    build_dogfood_metrics,
    main,
    render_dogfood_report,
)
from substrate.research_bridge.draft_export import record_draft_export
from substrate.research_bridge.schema import init_research_bridge


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> str:
    d = tempfile.mkdtemp()
    path = os.path.join(d, "dogfood.duckdb")
    ev = os.path.join(d, "events")
    os.makedirs(ev, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", ev)
    init_database_at_path(path)
    con = connect_write(path, purpose="research_bridge_dogfood_test")
    try:
        init_research_bridge(con)
    finally:
        con.close()
    return path


def _seed_report_rows(db_path: str) -> None:
    con = connect_write(db_path, purpose="seed dogfood report")
    try:
        con.execute(
            "INSERT INTO documents (document_id, source_tier, document_type) VALUES "
            "('doc-a', 3, 'external_deep_research'), "
            "('doc-b', 3, 'external_deep_research'), "
            "('doc-c', 3, 'external_deep_research')"
        )
        con.execute(
            "INSERT INTO deliverables "
            "(deliverable_id, title, deliverable_kind, owner_user_id) VALUES "
            "('dlv-a', 'Mode A Draft', 'research_memo', '__operator__')"
        )
        con.execute(
            "INSERT INTO research_pastes "
            "(document_id, source, source_confidence, raw_sha256, "
            " paste_byte_length, parser_version, session_id, pasted_at) VALUES "
            "('doc-a', 'grok', 1.0, 'sha-a', 10, 1, 'sess-a', "
            " TIMESTAMP '2026-07-01 09:00:00'), "
            "('doc-b', 'anthropic', 0.9, 'sha-b', 20, 1, 'sess-a', "
            " TIMESTAMP '2026-07-01 09:03:00'), "
            "('doc-c', 'chatgpt', 0.8, 'sha-c', 30, 1, 'sess-b', "
            " TIMESTAMP '2026-07-02 10:00:00')"
        )
        con.execute(
            "INSERT INTO research_paste_extractions "
            "(extraction_id, document_id, extractor_version, model_id, "
            " status, cost_usd) VALUES "
            "('ext-a', 'doc-a', 1, 'model-a', 'ok', 0.25), "
            "('ext-b', 'doc-b', 1, 'model-a', 'ok', 0.50)"
        )
        con.execute(
            "INSERT INTO research_gap_runs "
            "(run_id, session_id, scope_block_ids, scope_question_ids, "
            " cluster_model_id, total_cost_usd) VALUES "
            "('run-a', 'sess-a', '[\"doc-a\", \"doc-b\"]', '[]', 'model-g', 0.75)"
        )
        con.execute(
            "INSERT INTO research_gap_prompts "
            "(prompt_id, run_id, order_index, prompt_text, target_provider) VALUES "
            "('prompt-a', 'run-a', 0, 'Prompt A', 'grok'), "
            "('prompt-b', 'run-a', 1, 'Prompt B', 'anthropic'), "
            "('prompt-c', 'run-a', 2, 'Prompt C', 'chatgpt')"
        )
        con.execute(
            "INSERT INTO research_gap_prompt_signals "
            "(signal_id, prompt_id, signal_type, occurred_at) VALUES "
            "('sig-a-old', 'prompt-a', 'skip', TIMESTAMP '2026-07-01 00:00:00'), "
            "('sig-a-new', 'prompt-a', 'would_run', TIMESTAMP '2026-07-01 00:01:00'), "
            "('sig-b', 'prompt-b', 'skip', TIMESTAMP '2026-07-01 00:02:00'), "
            "('sig-c', 'prompt-c', 'would_run', TIMESTAMP '2026-07-01 00:03:00')"
        )
        record_draft_export(
            con,
            session_id="sess-a",
            deliverable_id="dlv-a",
            output_path="~/Desktop/Antiek/runs/adrb/drafts/dlv-a.md",
        )
    finally:
        con.close()


def test_dogfood_metrics_reconcile_with_bridge_substrate(db: str) -> None:
    _seed_report_rows(db)
    con = connect_read(db)
    try:
        metrics = build_dogfood_metrics(con)
    finally:
        con.close()

    assert metrics.total_blocks_pasted == 3
    assert metrics.total_extractions == 2
    assert metrics.total_gap_runs == 1
    assert metrics.total_mode_a_draft_exports == 1
    assert metrics.total_llm_cost_usd == pytest.approx(1.5)
    assert metrics.would_run == 2
    assert metrics.total_signaled_prompts == 3
    assert metrics.would_run_pct == pytest.approx(2 / 3)
    assert metrics.s3_status == "PASS"
    assert metrics.average_blocks_per_session == pytest.approx(1.5)
    assert metrics.sessions_with_blocks_no_gap_runs == ("sess-b",)
    assert metrics.block_sessions[0].session_id == "sess-a"
    assert metrics.block_sessions[0].blocks_pasted == 2
    assert metrics.block_sessions[0].first_block_at == "2026-07-01 09:00:00"
    assert metrics.block_sessions[0].latest_block_at == "2026-07-01 09:03:00"
    assert metrics.block_sessions[1].session_id == "sess-b"
    assert metrics.block_sessions[1].blocks_pasted == 1
    assert metrics.by_session[0].session_id == "sess-a"
    assert metrics.by_session[0].would_run_pct == pytest.approx(2 / 3)


def test_dogfood_report_flags_failed_s3(db: str) -> None:
    con = connect_write(db, purpose="seed failed s3")
    try:
        con.execute(
            "INSERT INTO research_gap_runs "
            "(run_id, session_id, scope_block_ids, scope_question_ids, cluster_model_id) "
            "VALUES ('run-a', 'sess-a', '[]', '[]', 'model-g')"
        )
        con.execute(
            "INSERT INTO research_gap_prompts "
            "(prompt_id, run_id, order_index, prompt_text, target_provider) "
            "VALUES ('prompt-a', 'run-a', 0, 'Prompt A', 'grok')"
        )
        con.execute(
            "INSERT INTO research_gap_prompt_signals "
            "(signal_id, prompt_id, signal_type) VALUES "
            "('sig-a', 'prompt-a', 'skip')"
        )
    finally:
        con.close()
    con = connect_read(db)
    try:
        report = render_dogfood_report(build_dogfood_metrics(con))
    finally:
        con.close()

    assert "S3 status: FAIL" in report
    assert "Mode B would-run rate: 0.0% (0/1 latest prompt signals)" in report


def test_dogfood_report_cli_writes_markdown(db: str, tmp_path: Path) -> None:
    _seed_report_rows(db)
    out = tmp_path / "dogfood_metrics.md"

    rc = main(["--db", db, "--output", str(out)])

    assert rc == 0
    text = out.read_text(encoding="utf-8")
    assert "# Antiek Deep Research Bridge Dogfood Metrics" in text
    assert "S3 status: PASS" in text
    assert "- Mode A draft exports recorded: 1" in text
    assert "- Sessions with blocks but no gap run: sess-b" in text
    assert "## Block Timing By Session" in text
    assert (
        "- sess-a: 2 block(s), first block at 2026-07-01 09:00:00, "
        "latest block at 2026-07-01 09:03:00"
    ) in text
