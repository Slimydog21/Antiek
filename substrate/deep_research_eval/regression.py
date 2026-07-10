"""Week-over-week regression detection, fail closed on comparability.

``compare_runs`` REFUSES (raises ``NotComparableError``) when the two runs
carry different comparability keys or when either run is incomplete — it never
warns-and-proceeds. The raised error carries the explicit ``NOT_COMPARABLE``
verdict for reporting surfaces that want a record instead of a traceback.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from .runner import EvalRun

Verdict = Literal["REGRESSION", "COMPARABLE", "NOT_COMPARABLE"]

# Default thresholds (documented in-code per the W0 brief):
# - judge: a >0.05 drop in mean judge score (5% of the 0..1 scale) is beyond
#   pinned-judge noise on a 20-query frozen set and flags a real regression.
# - coverage: a >0.10 drop in mean coverage_hit_rate means the candidate is
#   mechanically missing anchors the baseline hit — judge-independent evidence.
DEFAULT_MAX_JUDGE_SCORE_DROP = 0.05
DEFAULT_MAX_COVERAGE_DROP = 0.10


@dataclass(frozen=True)
class RegressionThresholds:
    max_judge_score_drop: float = DEFAULT_MAX_JUDGE_SCORE_DROP
    max_coverage_drop: float = DEFAULT_MAX_COVERAGE_DROP


@dataclass(frozen=True)
class RegressionVerdict:
    verdict: Verdict
    baseline_run_id: str
    candidate_run_id: str
    judge_score_delta: float
    coverage_delta: float
    reasons: tuple[str, ...]


class NotComparableError(ValueError):
    """Raised when a comparison must be refused. Carries the explicit verdict."""

    def __init__(self, verdict: RegressionVerdict) -> None:
        self.verdict = verdict
        super().__init__("; ".join(verdict.reasons))


def _refuse(baseline: EvalRun, candidate: EvalRun, reasons: tuple[str, ...]) -> NotComparableError:
    return NotComparableError(
        RegressionVerdict(
            verdict="NOT_COMPARABLE",
            baseline_run_id=baseline.run_id,
            candidate_run_id=candidate.run_id,
            judge_score_delta=0.0,
            coverage_delta=0.0,
            reasons=reasons,
        )
    )


def compare_runs(
    baseline: EvalRun,
    candidate: EvalRun,
    thresholds: RegressionThresholds | None = None,
) -> RegressionVerdict:
    """Compare candidate against baseline; REGRESSION on judge-score OR
    coverage drop beyond threshold. Raises ``NotComparableError`` (fail
    closed) on comparability-key mismatch or incomplete runs."""
    limits = thresholds if thresholds is not None else RegressionThresholds()
    for name, value in (
        ("max_judge_score_drop", limits.max_judge_score_drop),
        ("max_coverage_drop", limits.max_coverage_drop),
    ):
        # NaN/inf thresholds would make every drop comparison False — fail OPEN.
        # Refuse them (and negatives) up front.
        if not math.isfinite(value) or value < 0.0:
            raise ValueError(f"regression threshold {name} must be finite and non-negative")

    if baseline.comparability_key != candidate.comparability_key:
        raise _refuse(
            baseline,
            candidate,
            (
                "comparability keys differ: "
                f"baseline={baseline.comparability_key} candidate={candidate.comparability_key}",
            ),
        )
    incomplete = tuple(
        f"{label} run {run.run_id} is incomplete "
        f"({run.measured_count}/{len(run.scores)} queries measured)"
        for label, run in (("baseline", baseline), ("candidate", candidate))
        if not run.complete
    )
    if incomplete:
        raise _refuse(baseline, candidate, incomplete)

    judge_score_delta = round(candidate.mean_judge_score - baseline.mean_judge_score, 6)
    coverage_delta = round(
        candidate.mean_coverage_hit_rate - baseline.mean_coverage_hit_rate, 6
    )
    reasons: list[str] = []
    if judge_score_delta < -limits.max_judge_score_drop:
        reasons.append(
            f"mean judge score dropped {-judge_score_delta:.6f} "
            f"(> {limits.max_judge_score_drop:.6f} threshold)"
        )
    if coverage_delta < -limits.max_coverage_drop:
        reasons.append(
            f"mean coverage_hit_rate dropped {-coverage_delta:.6f} "
            f"(> {limits.max_coverage_drop:.6f} threshold)"
        )
    verdict: Verdict = "REGRESSION" if reasons else "COMPARABLE"
    return RegressionVerdict(
        verdict=verdict,
        baseline_run_id=baseline.run_id,
        candidate_run_id=candidate.run_id,
        judge_score_delta=judge_score_delta,
        coverage_delta=coverage_delta,
        reasons=tuple(reasons) if reasons else ("within thresholds",),
    )
