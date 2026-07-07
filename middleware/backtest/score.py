"""Deterministic scoring for Phase-8 backtest reports.

The gate compares candidate patches against a baseline using a numeric
score. This module turns already-loaded ``BacktestReport`` objects into
that score without mutating the graph, skills, or event log.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .types import BacktestReport

DEFAULT_MIN_GRADED_OUTCOMES = 50

_THESIS_OUTCOME_SCORE = {
    "confirmed": 1.0,
    "partially_confirmed": 0.5,
    "unresolved": 0.5,
    "disconfirmed": 0.0,
}

_PROCEED_OUTCOME_SCORE = {
    "confirmed": 1.0,
    "partially_confirmed": 0.5,
    "not_observed": 0.5,
    "disconfirmed": 0.0,
}


@dataclass(frozen=True)
class BacktestScore:
    """One report converted into a bounded gate score."""

    synthesis_id: str
    score: float
    graded_outcomes: int
    thesis_score: float | None
    decision_score: float | None
    structural_penalty: float


@dataclass(frozen=True)
class BacktestCohortScore:
    """Aggregate score used by Phase-8 gate calibration."""

    score: float
    reports_scored: int
    graded_outcomes: int
    minimum_graded_outcomes: int = DEFAULT_MIN_GRADED_OUTCOMES

    @property
    def ready_for_gate(self) -> bool:
        return self.graded_outcomes >= self.minimum_graded_outcomes


@dataclass(frozen=True)
class BacktestComparison:
    """Baseline-vs-candidate score pair for the Phase-8 gate."""

    baseline_score: float
    candidate_score: float
    delta: float
    cohort_size: int
    ready_for_gate: bool
    notes: str


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


def _mean(values: Iterable[float]) -> float | None:
    items = list(values)
    if not items:
        return None
    return sum(items) / len(items)


def _thesis_scores(outcome: dict[str, Any]) -> list[float]:
    rows = outcome.get("thesis_outcomes")
    if not isinstance(rows, list):
        return []
    scores: list[float] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        status = row.get("outcome")
        if isinstance(status, str) and status in _THESIS_OUTCOME_SCORE:
            scores.append(_THESIS_OUTCOME_SCORE[status])
    return scores


def _decision_score(outcome: dict[str, Any]) -> float | None:
    row = outcome.get("decision_alignment")
    if not isinstance(row, dict):
        return None
    actual = row.get("actual_decision")
    expected = row.get("agent_implicit_recommendation")
    if not isinstance(actual, str) or not isinstance(expected, str):
        return None
    if actual == "not_observed":
        proceeded = row.get("thesis_outcome_when_proceeded")
        if isinstance(proceeded, str) and proceeded in _PROCEED_OUTCOME_SCORE:
            return _PROCEED_OUTCOME_SCORE[proceeded]
        return None
    return 1.0 if actual == expected else 0.0


def _structural_penalty(report: BacktestReport) -> float:
    edge_penalty = 0.15 * report.load_bearing_edges_invalidated
    chunk_penalty = 0.05 * report.cited_chunks_demoted
    return min(0.5, edge_penalty + chunk_penalty)


def score_backtest_report(report: BacktestReport) -> BacktestScore:
    """Convert one ``BacktestReport`` to a bounded score.

    Outcome rows carry the main signal. Invalidated cited edges and
    demoted cited chunks are bounded penalties because they indicate
    the original synthesis depended on substrate that later degraded.
    """
    thesis_values: list[float] = []
    decision_values: list[float] = []
    for outcome in report.outcomes:
        thesis_values.extend(_thesis_scores(outcome))
        decision = _decision_score(outcome)
        if decision is not None:
            decision_values.append(decision)

    thesis_score = _mean(thesis_values)
    decision_score = _mean(decision_values)
    components = [
        score for score in (thesis_score, decision_score) if score is not None
    ]
    evidence_score = 0.5 if not components else sum(components) / len(components)
    penalty = _structural_penalty(report)
    return BacktestScore(
        synthesis_id=report.synthesis_id,
        score=_clamp01(evidence_score - penalty),
        graded_outcomes=report.outcomes_recorded,
        thesis_score=thesis_score,
        decision_score=decision_score,
        structural_penalty=penalty,
    )


def score_backtest_cohort(
    reports: Iterable[BacktestReport],
    *,
    minimum_graded_outcomes: int = DEFAULT_MIN_GRADED_OUTCOMES,
) -> BacktestCohortScore:
    """Aggregate report scores into the Phase-8 gate cohort signal."""
    scored = [score_backtest_report(report) for report in reports]
    graded = sum(item.graded_outcomes for item in scored)
    score = 0.0 if not scored else sum(item.score for item in scored) / len(scored)
    return BacktestCohortScore(
        score=score,
        reports_scored=len(scored),
        graded_outcomes=graded,
        minimum_graded_outcomes=minimum_graded_outcomes,
    )


def compare_backtest_cohorts(
    *,
    baseline_reports: Iterable[BacktestReport],
    candidate_reports: Iterable[BacktestReport],
    minimum_graded_outcomes: int = DEFAULT_MIN_GRADED_OUTCOMES,
) -> BacktestComparison:
    """Compare baseline and candidate cohorts for ``SkillPatchGate``.

    Candidate replay is responsible for producing ``candidate_reports``.
    This function only compares already-materialized reports and refuses
    readiness until both sides meet the documented Wedge-2 outcome floor.
    """
    baseline = score_backtest_cohort(
        baseline_reports,
        minimum_graded_outcomes=minimum_graded_outcomes,
    )
    candidate = score_backtest_cohort(
        candidate_reports,
        minimum_graded_outcomes=minimum_graded_outcomes,
    )
    cohort_size = min(baseline.graded_outcomes, candidate.graded_outcomes)
    ready = baseline.ready_for_gate and candidate.ready_for_gate
    if ready:
        notes = (
            f"candidate delta={candidate.score - baseline.score:.4f} "
            f"over {cohort_size} graded outcomes"
        )
    else:
        notes = (
            "backtest cohorts not ready: "
            f"baseline_graded={baseline.graded_outcomes}, "
            f"candidate_graded={candidate.graded_outcomes}, "
            f"minimum={minimum_graded_outcomes}"
        )
    return BacktestComparison(
        baseline_score=baseline.score,
        candidate_score=candidate.score,
        delta=candidate.score - baseline.score,
        cohort_size=cohort_size,
        ready_for_gate=ready,
        notes=notes,
    )


__all__ = [
    "DEFAULT_MIN_GRADED_OUTCOMES",
    "BacktestCohortScore",
    "BacktestComparison",
    "BacktestScore",
    "compare_backtest_cohorts",
    "score_backtest_cohort",
    "score_backtest_report",
]
