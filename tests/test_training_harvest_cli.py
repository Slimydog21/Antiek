"""Tests for the RLM-5 trajectory harvest CLI."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from tools.training.harvest import compute_quality, harvest_records, main  # noqa: E402


def _event(
    investigation_id: str,
    event_id: str,
    action_type: str,
    payload: dict,
    *,
    emitted_at: str = "2026-07-01T00:00:00Z",
    role: str | None = None,
    policy_id: str = "stub/policy",
) -> dict:
    return {
        "event_id": event_id,
        "investigation_id": investigation_id,
        "action_type": action_type,
        "payload": payload,
        "role": role,
        "policy_id": policy_id,
        "emitted_at": emitted_at,
        "synthesis_id": "syn-1",
        "document_id": "doc-1",
    }


def _good_events(investigation_id: str = "inv-good") -> list[dict]:
    return [
        _event(
            investigation_id,
            "e1",
            "decompose.question.delivered",
            {"sub_questions": [{"question": "Q1"}]},
            role="decomposer",
        ),
        _event(
            investigation_id,
            "e2",
            "synthesize.delivered",
            {"thesis": "T"},
            role="synthesizer",
        ),
        _event(
            investigation_id,
            "e3",
            "constraint.loop_resolved",
            {"final_status": "passed", "total_iterations": 1, "final_violation_count": 0},
        ),
        _event(
            investigation_id,
            "e4",
            "synthesis.archived",
            {"target_question": "Q", "status": "archived"},
        ),
        _event(
            investigation_id,
            "e5",
            "outcome.recorded",
            {
                "thesis_outcomes": [
                    {"thesis_claim": "T", "outcome": "confirmed", "evidence": "E"}
                ]
            },
        ),
        _event(
            investigation_id,
            "e6",
            "investigation.completed",
            {
                "thesis_summary": "T",
                "implicit_recommendation": "proceed",
                "constraint_loop_status": "passed",
            },
        ),
    ]


def test_compute_quality_uses_constraint_archive_and_outcomes():
    quality = compute_quality(_good_events())
    assert quality.constraint_pass_rate == 1.0
    assert quality.synthesis_archived == 1.0
    assert quality.outcome_correlation == 1.0
    assert quality.composite == 1.0


def test_harvest_records_filters_by_quality_threshold():
    bad = [
        _event(
            "inv-bad",
            "b1",
            "investigation.completed",
            {
                "thesis_summary": "weak",
                "implicit_recommendation": "pass",
                "constraint_loop_status": "max_iterations_reached",
            },
        )
    ]
    records = harvest_records(
        [*_good_events(), *bad],
        since="2026-01-01",
        quality_threshold=0.7,
    )
    assert [record.investigation_id for record in records] == ["inv-good"]
    assert records[0].to_jsonable()["reward"]["total"] == 1.0
    assert records[0].to_jsonable()["task"]["task_id"] == "inv-good"


def test_harvest_records_filters_by_since_date():
    old = [
        {
            **event,
            "investigation_id": "inv-old",
            "emitted_at": "2025-12-31T23:59:59Z",
        }
        for event in _good_events("inv-old")
    ]
    records = harvest_records(
        [*_good_events("inv-new"), *old],
        since="2026-01-01",
        quality_threshold=0.7,
    )
    assert [record.investigation_id for record in records] == ["inv-new"]


def test_role_filter_keeps_only_matching_rollout_steps():
    records = harvest_records(
        _good_events(),
        since="2026-01-01",
        quality_threshold=0.7,
        role_filter="synthesizer",
    )
    steps = records[0].to_jsonable()["rollout"]["steps"]
    assert len(steps) == 1
    assert steps[0]["info"]["role"] == "synthesizer"


def test_main_writes_verifiers_jsonl_from_input_jsonl(tmp_path: Path, capsys):
    input_path = tmp_path / "events.jsonl"
    output_path = tmp_path / "trajectories.jsonl"
    input_path.write_text(
        "\n".join(json.dumps(event) for event in _good_events()) + "\n",
        encoding="utf-8",
    )

    rc = main([
        "--input-jsonl",
        str(input_path),
        "--since",
        "2026-01-01",
        "--quality-threshold",
        "0.7",
        "--output",
        str(output_path),
    ])

    assert rc == 0
    assert json.loads(capsys.readouterr().out)["records_written"] == 1
    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert set(row) == {"task", "rollout", "reward", "metadata"}
    assert row["metadata"]["format"] == "antiek.verifiers.trajectory.v1"
    assert row["reward"]["passed"] is True
