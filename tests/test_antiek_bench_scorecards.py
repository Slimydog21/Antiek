"""Antiek-bench scorecard contract tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from substrate.antiek_bench import (
    AntiekBenchScorecard,
    latest_scorecard_path,
    read_latest_scorecard,
    run_mock_weekly_scorecard,
)
from substrate.antiek_bench.scorecards import latest_proposal_path


def test_mock_run_writes_schema_valid_scorecard_with_two_task_classes(tmp_path: Path) -> None:
    scorecard, proposal = run_mock_weekly_scorecard(base_dir=tmp_path, week_id="2026-W28")

    assert latest_scorecard_path(tmp_path).is_file()
    loaded = read_latest_scorecard(base_dir=tmp_path)
    assert loaded == scorecard
    assert isinstance(loaded, AntiekBenchScorecard)
    assert len({entry.task_class for entry in loaded.entries}) >= 2
    assert proposal.week_id == "2026-W28"


def test_scorecard_and_fixture_proposal_do_not_include_secrets_or_full_prompts(
    tmp_path: Path,
) -> None:
    run_mock_weekly_scorecard(
        base_dir=tmp_path,
        route_receipts=[
            {
                "route_receipt_id": "receipt-1",
                "raw_prompt": "private prompt sk-test-secret should not persist",
                "api_key": "sk-test-secret",
            }
        ],
        week_id="2026-W28",
    )

    scorecard_json = latest_scorecard_path(tmp_path).read_text(encoding="utf-8")
    proposal_json = latest_proposal_path(tmp_path).read_text(encoding="utf-8")
    combined = f"{scorecard_json}\n{proposal_json}".lower()
    assert "receipt-1" in combined
    assert "private prompt" not in combined
    assert "sk-test-secret" not in combined
    assert "api_key" not in combined
    assert "raw_prompt" not in combined


def test_weekly_proposal_lists_added_and_retired_fixtures_with_receipt_evidence(
    tmp_path: Path,
) -> None:
    _, proposal = run_mock_weekly_scorecard(
        base_dir=tmp_path,
        route_receipts=[
            {"route_receipt_id": "receipt-research"},
            {"route_receipt_id": "receipt-reading"},
        ],
        week_id="2026-W28",
    )

    actions = {item.action for item in proposal.proposals}
    assert actions == {"add", "retire"}
    assert all(item.evidence_route_receipt_ids for item in proposal.proposals)
    proposal_payload = json.loads(latest_proposal_path(tmp_path).read_text(encoding="utf-8"))
    assert proposal_payload["week_id"] == "2026-W28"


def test_mock_scorecard_requires_two_task_classes() -> None:
    with pytest.raises(ValueError, match="at least two task classes"):
        AntiekBenchScorecard(
            scorecard_id="bad",
            generated_at="2026-07-09T00:00:00Z",
            week_id="2026-W28",
            mock_run=True,
            entries=[
                {
                    "task_class": "research_question",
                    "provider": "zai",
                    "model": "glm-5.2",
                    "quality_score": 0.5,
                    "groundedness": 0.5,
                    "citation_precision": 0.5,
                    "insight_density": 0.5,
                    "synthesis_coherence": 0.5,
                    "verifier_disagreement": 0.5,
                }
            ],
        )
