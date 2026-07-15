"""Pure advisory ranking for operator-visible model decisions.

SPR-01 (Cycle 594): Delete fabricated static-task-tier affinities.
Only a current, comparable Antiek-bench cohort may produce a measured pick.
Recommendation requires at least two operationally eligible measured candidates
from the same validated report snapshot. Missing or partial evidence yields
null quality scores and no recommendation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

DecisionTask = Literal[
    "deep_research",
    "research_synthesis",
    "reading",
    "twin_note",
    "writing",
    "multimedia",
    "general",
]


@dataclass(frozen=True)
class DecisionCandidate:
    tier: str
    provider: str
    model: str
    ready: bool
    estimated_usd_low: float | None
    estimated_usd_high: float | None
    would_exceed_budget: bool | None
    benchmark_score: float | None = None
    benchmark_samples: int | None = None


@dataclass(frozen=True)
class RankedDecisionCandidate:
    candidate: DecisionCandidate
    quality_score: float | None
    quality_basis: Literal["measured", "absent"]
    operationally_eligible: bool
    rank: int


@dataclass(frozen=True)
class DecisionResult:
    task: DecisionTask
    recommended_tier: str | None
    ranked: tuple[RankedDecisionCandidate, ...]


def _finite_optional(value: float | None, name: str) -> float | None:
    if value is None:
        return None
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if name.startswith("estimated_usd_") and value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def rank_model_candidates(
    task: DecisionTask,
    candidates: tuple[DecisionCandidate, ...],
) -> DecisionResult:
    """Rank server-derived candidates without granting dispatch authority.

    A measured pick requires at least two operationally eligible measured
    candidates from the same report snapshot and task.  A single measured
    candidate cannot win against unmeasured routes — measurement availability
    is not comparative superiority.
    """
    working: list[tuple[DecisionCandidate, float | None, Literal["measured", "absent"]]] = []
    for candidate in candidates:
        benchmark = _finite_optional(candidate.benchmark_score, "benchmark_score")
        _finite_optional(candidate.estimated_usd_low, "estimated_usd_low")
        _finite_optional(candidate.estimated_usd_high, "estimated_usd_high")
        if benchmark is not None and not 0.0 <= benchmark <= 1.0:
            raise ValueError("benchmark_score must be between zero and one")
        if candidate.benchmark_samples is not None and candidate.benchmark_samples < 1:
            raise ValueError("benchmark_samples must be positive")
        quality: float | None = benchmark
        basis: Literal["measured", "absent"] = "measured" if benchmark is not None else "absent"
        working.append((candidate, quality, basis))

    eligible_measured_count = sum(
        1
        for candidate, _, basis in working
        if basis == "measured"
        and candidate.ready
        and candidate.would_exceed_budget is False
    )
    has_measured_pick = eligible_measured_count >= 2

    def budget_rank(candidate: DecisionCandidate) -> int:
        if candidate.would_exceed_budget is False:
            return 0
        if candidate.would_exceed_budget is None:
            return 1
        return 2

    working.sort(
        key=lambda row: (
            not row[0].ready,
            budget_rank(row[0]),
            0 if row[2] == "measured" else 1,
            -(row[1] if row[1] is not None else -1.0),
            row[0].tier,
            row[0].provider,
            row[0].model,
        )
    )
    ranked = tuple(
        RankedDecisionCandidate(
            candidate=candidate,
            quality_score=quality,
            quality_basis=basis,
            operationally_eligible=candidate.ready and candidate.would_exceed_budget is False,
            rank=index,
        )
        for index, (candidate, quality, basis) in enumerate(working, start=1)
    )
    recommended = None
    if has_measured_pick:
        recommended = next(
            (
                row.candidate.tier
                for row in ranked
                if row.operationally_eligible and row.quality_basis == "measured"
            ),
            None,
        )
    return DecisionResult(task=task, recommended_tier=recommended, ranked=ranked)


__all__ = [
    "DecisionCandidate",
    "DecisionResult",
    "DecisionTask",
    "RankedDecisionCandidate",
    "rank_model_candidates",
]
