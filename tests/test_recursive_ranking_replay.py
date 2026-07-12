from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from substrate.context_pack import build_canonical_recursive_pack
from substrate.context_pack.recursive_feedback import (
    FeedbackUnitRef,
    FileRecursiveFeedbackStore,
    build_outcome_receipt,
)
from substrate.context_pack.recursive_ranking import (
    MIN_REPLAY_SESSIONS,
    ReplaySession,
    apply_advisory_ranking,
    build_ranking_snapshot,
    replay_report_html,
    weekly_replay,
)
from substrate.engagement_spine import InMemoryEngagementStore, record_twin_insight

NOW_MS = 10_000_000_000


def _pack():
    store = InMemoryEngagementStore()
    for asset, text in (
        ("a", "First baseline thought."),
        ("a", "Second baseline thought."),
        ("a", "Third baseline thought."),
        ("b", "Diverse counterevidence."),
    ):
        record_twin_insight(asset, text, store=store)
    return build_canonical_recursive_pack(
        store=store,
        owner_user_id="owner",
        asset_ids=["a", "b"],
        asset_owner=lambda _asset: "owner",
        goal="baseline thought counterevidence",
        per_asset_limit=4,
    )


def _feedback(unit_id: str, index: int, outcome: str = "saved", age_days: int = 0):
    return build_outcome_receipt(
        owner_user_id="owner",
        observation_id=f"observation-{unit_id}-{index}-{outcome}",
        context_pack_event_id=f"context-{index}",
        dispatch_event_id=f"dispatch-{index}",
        units=[
            FeedbackUnitRef(
                unit_id=unit_id,
                text_digest=hashlib.sha256(unit_id.encode()).hexdigest(),
            )
        ],
        task_class="research_reasoning",
        model_policy_id="provider/model",
        outcome=outcome,
        observed_at_ms=NOW_MS - age_days * 86_400_000,
    )


def test_minimum_samples_time_decay_and_no_signal_honesty():
    pack = _pack()
    target = pack.units[-1].unit_id
    receipts = [
        _feedback(target, 1, age_days=0),
        _feedback(target, 2, age_days=28),
        _feedback(target, 3, outcome="no_signal"),
    ]
    sparse = build_ranking_snapshot(
        owner_user_id="owner",
        task_class="research_reasoning",
        receipts=receipts,
        now_ms=NOW_MS,
    )
    assert sparse.features == ()
    receipts.append(_feedback(target, 4, outcome="contradicted"))
    snapshot = build_ranking_snapshot(
        owner_user_id="owner",
        task_class="research_reasoning",
        receipts=receipts,
        now_ms=NOW_MS,
    )
    assert snapshot.features[0].sample_count == 3
    assert snapshot.features[0].contradiction_count == 1
    assert snapshot.features[0].score > 0


def test_advisory_order_preserves_content_provenance_and_diversity():
    pack = _pack()
    target = next(unit for unit in pack.units if unit.asset_id == "b")
    receipts = [_feedback(target.unit_id, index) for index in range(3)]
    snapshot = build_ranking_snapshot(
        owner_user_id="owner",
        task_class="research_reasoning",
        receipts=receipts,
        now_ms=NOW_MS,
    )
    ranked = apply_advisory_ranking(
        pack,
        owner_user_id="owner",
        snapshot=snapshot,
    )
    assert {unit.unit_id: asdict(unit) for unit in ranked.units} == {
        unit.unit_id: asdict(unit) for unit in pack.units
    }
    assert ranked.exclusions == pack.exclusions
    assert ranked.token_estimate == pack.token_estimate
    assert [unit.unit_id for unit in ranked.units] != [unit.unit_id for unit in pack.units]
    assert all(
        not (
            ranked.units[index].asset_id
            == ranked.units[index + 1].asset_id
            == ranked.units[index + 2].asset_id
        )
        for index in range(len(ranked.units) - 2)
    )


def test_cross_owner_feedback_is_rejected():
    receipt = _feedback("unit", 1)
    try:
        build_ranking_snapshot(
            owner_user_id="other-owner",
            task_class="research_reasoning",
            receipts=[receipt],
            now_ms=NOW_MS,
        )
    except PermissionError:
        pass
    else:
        raise AssertionError("foreign feedback entered ranking")


def test_future_feedback_is_rejected():
    with pytest.raises(ValueError, match="future feedback"):
        build_ranking_snapshot(
            owner_user_id="owner",
            task_class="research_reasoning",
            receipts=[_feedback("unit", 1, age_days=-1)],
            now_ms=NOW_MS,
        )


def test_replay_relevance_must_be_grounded_in_baseline():
    with pytest.raises(ValueError, match="reference baseline"):
        ReplaySession(
            session_id="invalid-relevance",
            task_class="research_reasoning",
            baseline_unit_ids=("unit-a",),
            baseline_text_digests=(hashlib.sha256(b"unit-a").hexdigest(),),
            relevant_unit_ids=("unit-foreign",),
        )


def test_weekly_replay_is_blinded_uncertain_and_never_auto_promotes():
    unit_ids = ("unit-a", "unit-b", "unit-c")
    receipts = [_feedback("unit-c", index) for index in range(3)]
    snapshot = build_ranking_snapshot(
        owner_user_id="owner",
        task_class="research_reasoning",
        receipts=receipts,
        now_ms=NOW_MS,
    )
    sessions = [
        ReplaySession(
            session_id=f"private-session-{index}",
            task_class="research_reasoning",
            baseline_unit_ids=unit_ids,
            baseline_text_digests=tuple(
                hashlib.sha256(unit_id.encode()).hexdigest() for unit_id in unit_ids
            ),
            relevant_unit_ids=("unit-c",),
        )
        for index in range(MIN_REPLAY_SESSIONS)
    ]
    report = weekly_replay(
        week_id="2026-W28",
        task_class="research_reasoning",
        sessions=sessions,
        snapshot=snapshot,
    )
    assert report.minimum_samples_met is True
    assert report.advisory_mean_reciprocal_rank > report.baseline_mean_reciprocal_rank
    assert report.auto_promoted is False
    assert report.confidence_low <= report.delta_mean <= report.confidence_high
    html = replay_report_html(report)
    assert "auto_promoted=false" in html
    assert "private-session" not in html
    assert "unit-c" not in html


def test_weekly_replay_ignores_stale_content_features():
    unit_ids = ("unit-a", "unit-b", "unit-c")
    snapshot = build_ranking_snapshot(
        owner_user_id="owner",
        task_class="research_reasoning",
        receipts=[_feedback("unit-c", index) for index in range(3)],
        now_ms=NOW_MS,
    )
    session = ReplaySession(
        session_id="stale-content-session",
        task_class="research_reasoning",
        baseline_unit_ids=unit_ids,
        baseline_text_digests=(
            hashlib.sha256(b"unit-a").hexdigest(),
            hashlib.sha256(b"unit-b").hexdigest(),
            hashlib.sha256(b"changed-unit-c-text").hexdigest(),
        ),
        relevant_unit_ids=("unit-c",),
    )
    report = weekly_replay(
        week_id="2026-W28",
        task_class="research_reasoning",
        sessions=[session],
        snapshot=snapshot,
    )
    assert report.advisory_mean_reciprocal_rank == report.baseline_mean_reciprocal_rank
    assert report.delta_mean == 0


def test_weekly_cli_writes_html_and_secret_free_json(tmp_path):
    feedback_dir = tmp_path / "feedback"
    store = FileRecursiveFeedbackStore(feedback_dir)
    for receipt in [_feedback("unit-c", index) for index in range(3)]:
        store.append("owner", receipt)
    sessions_path = tmp_path / "sessions.json"
    sessions_path.write_text(
        json.dumps(
            [
                {
                    "session_id": f"private-session-{index}",
                    "task_class": "research_reasoning",
                    "baseline_unit_ids": ["unit-a", "unit-b", "unit-c"],
                    "baseline_text_digests": [
                        hashlib.sha256(value.encode()).hexdigest()
                        for value in ("unit-a", "unit-b", "unit-c")
                    ],
                    "relevant_unit_ids": ["unit-c"],
                }
                for index in range(MIN_REPLAY_SESSIONS)
            ]
        )
    )
    html_path = tmp_path / "report.html"
    json_path = tmp_path / "report.json"
    repo = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            str(repo / "tools" / "recursive_context_weekly.py"),
            "--feedback-dir",
            str(feedback_dir),
            "--owner-id",
            "owner",
            "--sessions-json",
            str(sessions_path),
            "--task-class",
            "research_reasoning",
            "--week-id",
            "2026-W28",
            "--output-html",
            str(html_path),
            "--output-json",
            str(json_path),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    html = html_path.read_text()
    report_json = json_path.read_text()
    assert "<!doctype html>" in html
    assert '"auto_promoted": false' in report_json
    assert "private-session" not in html + report_json
    assert "unit-c" not in html + report_json
    assert "owner" not in html + report_json
