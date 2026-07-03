"""Dogfood session reconciliation tests for the Deep Research Bridge."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from runtime.db_lock import connect_read, connect_write
from substrate.graph.schema import init_database_at_path
from substrate.research_bridge.dogfood_log import write_dogfood_scaffold
from substrate.research_bridge.dogfood_reconcile import reconcile_dogfood_sessions
from substrate.research_bridge.schema import init_research_bridge

PROJECT_NAMES = (
    "Sell-side AI infra memo",
    "Anthropic market scan",
    "AlphaSense earnings read",
    "Mixed-provider author brief",
    "Operator status-quo replacement",
)


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> str:
    d = tempfile.mkdtemp()
    path = os.path.join(d, "dogfood.duckdb")
    ev = os.path.join(d, "events")
    os.makedirs(ev, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", ev)
    init_database_at_path(path)
    con = connect_write(path, purpose="research_bridge_dogfood_reconcile_test")
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


def _complete_project_entry(name: str, idx: int) -> str:
    return f"""## Project name

{name}

## Goal

Produce dogfood project {idx}.

## Session ID

sess-{idx}

## Provider mix

Grok and Claude.

## Block count at start / end

- Start: {idx}
- End: {idx + 1}

## Mode(s) used

A and B.

## Draft produced

runs/adrb/drafts/project-{idx}.md

## Did mode A produce something I'd send / publish?

with-edits. It needed a pass but preserved the outline.

## Did mode B's prompts cause me to actually run prompts?

Yes. Prompt {idx} was run manually.

## What failed?

The first outline was too broad.

## What surprised me?

The gap prompts found a missing comparison.

## Would I open this again tomorrow?

Yes.
"""


def _write_complete_log(root: Path) -> None:
    planned_lines = "\n".join(
        f"{idx}. {name}" for idx, name in enumerate(PROJECT_NAMES, start=1)
    )
    entries = "\n".join(
        _complete_project_entry(name, idx)
        for idx, name in enumerate(PROJECT_NAMES, start=1)
    )
    (root / "operator-log.md").write_text(
        f"""# Antiek Deep Research Bridge Operator Log

## Five projects chosen up front

{planned_lines}

## Project entries

{entries}
""",
        encoding="utf-8",
    )


def test_reconcile_dogfood_sessions_reports_missing_substrate_rows(
    db: str,
    tmp_path: Path,
) -> None:
    write_dogfood_scaffold(tmp_path)
    _write_complete_log(tmp_path)

    con = connect_read(db)
    try:
        result = reconcile_dogfood_sessions(con, root=tmp_path)
    finally:
        con.close()

    assert result.ok is False
    assert len(result.sessions) == 5
    assert (
        "Sell-side AI infra memo: session sess-1 has no substrate evidence"
        in result.missing_requirements
    )


def test_reconcile_dogfood_sessions_accepts_sessions_with_substrate_evidence(
    db: str,
    tmp_path: Path,
) -> None:
    write_dogfood_scaffold(tmp_path)
    _write_complete_log(tmp_path)
    con = connect_write(db, purpose="seed dogfood reconciliation")
    try:
        for idx in range(1, 6):
            con.execute(
                "INSERT INTO documents "
                "(document_id, source_tier, document_type) VALUES (?, 3, ?)",
                [f"doc-{idx}", "external_deep_research"],
            )
            con.execute(
                "INSERT INTO research_pastes "
                "(document_id, source, source_confidence, raw_sha256, "
                " paste_byte_length, parser_version, session_id) VALUES "
                "(?, 'grok', 1.0, ?, 10, 1, ?)",
                [f"doc-{idx}", f"sha-{idx}", f"sess-{idx}"],
            )
        con.execute(
            "INSERT INTO research_gap_runs "
            "(run_id, session_id, scope_block_ids, scope_question_ids, cluster_model_id) "
            "VALUES ('run-1', 'sess-1', '[]', '[]', 'model-g')"
        )
        con.execute(
            "INSERT INTO research_gap_prompts "
            "(prompt_id, run_id, order_index, prompt_text, target_provider) VALUES "
            "('prompt-1', 'run-1', 0, 'Prompt 1', 'grok')"
        )
        con.execute(
            "INSERT INTO research_gap_prompt_signals "
            "(signal_id, prompt_id, signal_type) VALUES "
            "('signal-1', 'prompt-1', 'would_run')"
        )
        con.execute(
            "INSERT INTO research_draft_exports "
            "(export_id, session_id, deliverable_id, output_path) VALUES "
            "('export-1', 'sess-2', 'dlv-a', '/tmp/draft.md')"
        )
    finally:
        con.close()

    con = connect_read(db)
    try:
        result = reconcile_dogfood_sessions(con, root=tmp_path)
    finally:
        con.close()

    assert result.ok is True
    assert result.sessions[0].blocks_pasted == 1
    assert result.sessions[0].gap_runs == 1
    assert result.sessions[0].prompt_signals == 1
    assert result.sessions[1].draft_exports == 1


def test_reconcile_dogfood_sessions_requires_pasted_block_per_project(
    db: str,
    tmp_path: Path,
) -> None:
    write_dogfood_scaffold(tmp_path)
    _write_complete_log(tmp_path)
    con = connect_write(db, purpose="seed dogfood reconciliation without one paste")
    try:
        for idx in range(1, 5):
            con.execute(
                "INSERT INTO documents "
                "(document_id, source_tier, document_type) VALUES (?, 3, ?)",
                [f"doc-{idx}", "external_deep_research"],
            )
            con.execute(
                "INSERT INTO research_pastes "
                "(document_id, source, source_confidence, raw_sha256, "
                " paste_byte_length, parser_version, session_id) VALUES "
                "(?, 'grok', 1.0, ?, 10, 1, ?)",
                [f"doc-{idx}", f"sha-{idx}", f"sess-{idx}"],
            )
        con.execute(
            "INSERT INTO research_draft_exports "
            "(export_id, session_id, deliverable_id, output_path) VALUES "
            "('export-5', 'sess-5', 'dlv-a', '/tmp/draft-5.md')"
        )
    finally:
        con.close()

    con = connect_read(db)
    try:
        result = reconcile_dogfood_sessions(con, root=tmp_path)
    finally:
        con.close()

    assert result.ok is False
    assert (
        "Operator status-quo replacement: session sess-5 has no pasted research block"
        in result.missing_requirements
    )
    assert (
        "Operator status-quo replacement: session sess-5 has no substrate evidence"
        not in result.missing_requirements
    )
