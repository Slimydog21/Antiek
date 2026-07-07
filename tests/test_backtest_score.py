"""Backtest score adapter tests for Phase-8 gate calibration."""

from __future__ import annotations

from middleware.backtest import (
    BacktestReport,
    ChunkTierChange,
    SupersededEdge,
    compare_backtest_cohorts,
    score_backtest_cohort,
    score_backtest_report,
)


def _report(
    *,
    synthesis_id: str = "syn-1",
    outcomes: tuple[dict, ...] = (),
    invalidated_edges: int = 0,
    demoted_chunks: int = 0,
) -> BacktestReport:
    return BacktestReport(
        synthesis_id=synthesis_id,
        synthesis_timestamp="2026-01-01T00:00:00Z",
        target_question="Will X work?",
        status="passed",
        implicit_recommendation="proceed",
        substrate_manifest_counts={},
        added_edges_since=0,
        superseded_edges_since=invalidated_edges,
        cited_edges_now_superseded=tuple(
            SupersededEdge(
                edge_id=f"edge-{i}",
                superseded_by=None,
                valid_until="2026-01-02T00:00:00Z",
                source="A",
                target="B",
                relation="supports",
            )
            for i in range(invalidated_edges)
        ),
        chunks_retired_downward=tuple(
            ChunkTierChange(
                chunk_id=f"chunk-{i}",
                original_tier=1,
                override_tier=3,
                reason="newer contrary evidence",
                set_at="2026-01-02T00:00:00Z",
            )
            for i in range(demoted_chunks)
        ),
        outcomes=outcomes,
    )


def test_score_backtest_report_combines_outcomes_and_structural_penalty():
    report = _report(
        outcomes=(
            {
                "thesis_outcomes": [
                    {"thesis_claim": "A", "outcome": "confirmed"},
                    {"thesis_claim": "B", "outcome": "disconfirmed"},
                ],
                "decision_alignment": {
                    "agent_implicit_recommendation": "proceed",
                    "actual_decision": "proceed",
                },
            },
        ),
        invalidated_edges=1,
        demoted_chunks=1,
    )

    score = score_backtest_report(report)

    assert score.synthesis_id == "syn-1"
    assert score.graded_outcomes == 1
    assert score.thesis_score == 0.5
    assert score.decision_score == 1.0
    assert score.structural_penalty == 0.2
    assert score.score == 0.55


def test_score_backtest_report_defaults_ungraded_reports_to_neutral():
    score = score_backtest_report(_report())

    assert score.graded_outcomes == 0
    assert score.thesis_score is None
    assert score.decision_score is None
    assert score.score == 0.5


def test_score_backtest_cohort_requires_minimum_graded_outcomes():
    reports = tuple(
        _report(
            synthesis_id=f"syn-{i}",
            outcomes=({
                "thesis_outcomes": [{"outcome": "confirmed"}],
                "decision_alignment": {
                    "agent_implicit_recommendation": "conditional",
                    "actual_decision": "conditional",
                },
            },),
        )
        for i in range(50)
    )

    ready = score_backtest_cohort(reports)
    not_ready = score_backtest_cohort(reports[:49])

    assert ready.ready_for_gate is True
    assert ready.graded_outcomes == 50
    assert ready.score == 1.0
    assert not_ready.ready_for_gate is False


def test_compare_backtest_cohorts_reports_delta_when_ready():
    baseline = tuple(
        _report(
            synthesis_id=f"base-{i}",
            outcomes=({"thesis_outcomes": [{"outcome": "partially_confirmed"}]},),
        )
        for i in range(50)
    )
    candidate = tuple(
        _report(
            synthesis_id=f"candidate-{i}",
            outcomes=({"thesis_outcomes": [{"outcome": "confirmed"}]},),
        )
        for i in range(50)
    )

    comparison = compare_backtest_cohorts(
        baseline_reports=baseline,
        candidate_reports=candidate,
    )

    assert comparison.ready_for_gate is True
    assert comparison.baseline_score == 0.5
    assert comparison.candidate_score == 1.0
    assert comparison.delta == 0.5
    assert comparison.cohort_size == 50
    assert "candidate delta=0.5000" in comparison.notes


def test_compare_backtest_cohorts_refuses_underpowered_candidate():
    baseline = tuple(
        _report(
            synthesis_id=f"base-{i}",
            outcomes=({"thesis_outcomes": [{"outcome": "confirmed"}]},),
        )
        for i in range(50)
    )
    candidate = baseline[:49]

    comparison = compare_backtest_cohorts(
        baseline_reports=baseline,
        candidate_reports=candidate,
    )

    assert comparison.ready_for_gate is False
    assert comparison.cohort_size == 49
    assert "candidate_graded=49" in comparison.notes
