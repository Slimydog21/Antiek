"""Dogfood readiness gate tests for the Deep Research Bridge."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database_at_path
from substrate.research_bridge.dogfood_log import write_dogfood_scaffold
from substrate.research_bridge.dogfood_readiness import (
    audit_dogfood_readiness,
    render_readiness_json,
    render_readiness_summary,
    validate_metrics_artifact,
)
from substrate.research_bridge.dogfood_report import build_report_from_db_path
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
    con = connect_write(path, purpose="research_bridge_dogfood_readiness_test")
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


def _seed_complete_substrate_rows(db_path: str) -> None:
    con = connect_write(db_path, purpose="seed dogfood readiness")
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
                "(run_id, session_id, scope_block_ids, scope_question_ids, "
                " cluster_model_id) VALUES (?, ?, '[]', '[]', 'model-g')",
                [f"run-{idx}", f"sess-{idx}"],
            )
            con.execute(
                "INSERT INTO research_gap_prompts "
                "(prompt_id, run_id, order_index, prompt_text, target_provider) VALUES "
                "(?, ?, 0, ?, 'grok')",
                [f"prompt-{idx}", f"run-{idx}", f"Prompt {idx}"],
            )
            con.execute(
                "INSERT INTO research_gap_prompt_signals "
                "(signal_id, prompt_id, signal_type) VALUES (?, ?, 'would_run')",
                [f"signal-{idx}", f"prompt-{idx}"],
            )
        con.execute(
            "INSERT INTO research_draft_exports "
            "(export_id, session_id, deliverable_id, output_path) VALUES "
            "('export-1', 'sess-1', 'dlv-a', '/tmp/draft.md')"
        )
    finally:
        con.close()


def _write_complete_verdict(path: Path) -> None:
    path.write_text(
        """# Antiek Deep Research Bridge Post-Dogfood Verdict

## Evidence Sources

- Operator log: `runs/adrb/operator-log.md`
- Metrics report: `runs/adrb/dogfood_metrics.md`

## Mode A Verdict

Verdict: ITERATE

Evidence:
- `operator-log.md` records mixed draft usefulness across five projects.
- `dogfood_metrics.md` records Mode A draft-export evidence.

Salvage if killed or iterated:
- Keep draft export tracking and tighten outline generation.

## Mode B Verdict

Verdict: SHIP

Evidence:
- `operator-log.md` records prompts the operator actually ran.
- `dogfood_metrics.md` records 100.0% would-run signals.

Salvage if killed or iterated:
- Keep prompt signal tracking.

## Next 3 Sharp Questions

1. Which prompts become reusable templates?
2. Which Mode A failures come from missing source context?
3. What operator workflow cost remains after session reconciliation passes?

## Wave 4

Decision: decline Wave 4 until the next dogfood cycle adds new evidence.
""",
        encoding="utf-8",
    )


def test_validate_metrics_artifact_requires_current_report(
    db: str,
    tmp_path: Path,
) -> None:
    root = tmp_path / "adrb"
    write_dogfood_scaffold(root)
    path = root / "dogfood_metrics.md"
    path.write_text("stale\n", encoding="utf-8")

    result = validate_metrics_artifact(db, dogfood_root=root)

    assert result.ok is False
    assert result.current is False
    assert "dogfood_metrics.md is stale; regenerate dogfood-report" in (
        result.missing_requirements
    )


def test_audit_dogfood_readiness_fails_honestly_on_scaffold(
    db: str,
    tmp_path: Path,
) -> None:
    root = tmp_path / "adrb"
    verdict = tmp_path / "adrb_post_dogfood_verdict.md"
    write_dogfood_scaffold(root)

    readiness = audit_dogfood_readiness(
        db,
        dogfood_root=root,
        verdict_path=verdict,
    )

    assert readiness.ok is False
    assert "expected 5 planned projects, found 0" in readiness.missing_requirements
    assert "dogfood_metrics.md is missing" in readiness.missing_requirements
    assert "verdict document is missing" in readiness.missing_requirements
    summary = render_readiness_summary(readiness)
    assert "dogfood log: FAIL (0/5 complete projects)" in summary
    assert "session reconciliation: FAIL (0/5 reconciled sessions)" in summary


def test_audit_dogfood_readiness_accepts_complete_current_evidence(
    db: str,
    tmp_path: Path,
) -> None:
    root = tmp_path / "adrb"
    verdict = tmp_path / "adrb_post_dogfood_verdict.md"
    write_dogfood_scaffold(root)
    _write_complete_log(root)
    _seed_complete_substrate_rows(db)
    (root / "dogfood_metrics.md").write_text(
        build_report_from_db_path(db, dogfood_root=root),
        encoding="utf-8",
    )
    _write_complete_verdict(verdict)

    readiness = audit_dogfood_readiness(
        db,
        dogfood_root=root,
        verdict_path=verdict,
    )

    assert readiness.ok is True
    assert readiness.metrics_artifact.current is True
    assert readiness.verdict_validation.mode_a_verdict == "ITERATE"
    assert readiness.verdict_validation.mode_b_verdict == "SHIP"
    assert "DOGFOOD_READINESS_OK" in render_readiness_summary(readiness)


def test_render_readiness_json_exposes_stable_machine_contract(
    db: str,
    tmp_path: Path,
) -> None:
    root = tmp_path / "adrb"
    verdict = tmp_path / "adrb_post_dogfood_verdict.md"
    write_dogfood_scaffold(root)

    readiness = audit_dogfood_readiness(
        db,
        dogfood_root=root,
        verdict_path=verdict,
    )

    payload = json.loads(render_readiness_json(readiness))

    assert payload["ok"] is False
    assert payload["dogfood_root"] == str(root)
    assert payload["metrics_path"] == str(root / "dogfood_metrics.md")
    assert payload["verdict_path"] == str(verdict)
    assert "dogfood_metrics.md is missing" in payload["missing_requirements"]
    assert payload["checks"]["dogfood_log"]["complete_project_entries"] == 0
    assert payload["checks"]["wave4_candidates"]["ok"] is True
    assert payload["checks"]["session_reconciliation"]["reconciled_sessions"] == 0
    assert payload["checks"]["metrics_artifact"]["current"] is False
    assert payload["checks"]["verdict_document"]["mode_a_verdict"] is None
