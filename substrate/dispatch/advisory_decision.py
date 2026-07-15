"""Pure advisory ranking for operator-visible model decisions."""

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

_TASK_TIER_AFFINITY: dict[DecisionTask, dict[str, float]] = {
    "deep_research": {"pro": 1.0, "synthesis": 0.9, "flash": 0.55, "verify": 0.5},
    "research_synthesis": {"synthesis": 1.0, "pro": 0.8, "verify": 0.65, "flash": 0.35},
    "reading": {"flash": 1.0, "pro": 0.75, "synthesis": 0.5, "verify": 0.45},
    "twin_note": {"flash": 1.0, "pro": 0.65, "synthesis": 0.4, "verify": 0.35},
    "writing": {"synthesis": 1.0, "pro": 0.9, "flash": 0.45, "verify": 0.4},
    "multimedia": {"synthesis": 1.0, "pro": 0.85, "flash": 0.5, "verify": 0.45},
    "general": {"pro": 1.0, "synthesis": 0.85, "flash": 0.7, "verify": 0.55},
}


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
    quality_score: float
    quality_basis: Literal["measured", "static_prior"]
    eligible: bool
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
    return value


def rank_model_candidates(
    task: DecisionTask,
    candidates: tuple[DecisionCandidate, ...],
) -> DecisionResult:
    """Rank server-derived candidates without granting dispatch authority."""
    affinity = _TASK_TIER_AFFINITY[task]
    working: list[tuple[DecisionCandidate, float, Literal["measured", "static_prior"]]] = []
    for candidate in candidates:
        benchmark = _finite_optional(candidate.benchmark_score, "benchmark_score")
        _finite_optional(candidate.estimated_usd_low, "estimated_usd_low")
        _finite_optional(candidate.estimated_usd_high, "estimated_usd_high")
        if benchmark is not None and not 0.0 <= benchmark <= 1.0:
            raise ValueError("benchmark_score must be between zero and one")
        if candidate.benchmark_samples is not None and candidate.benchmark_samples < 1:
            raise ValueError("benchmark_samples must be positive")
        quality = benchmark if benchmark is not None else affinity.get(candidate.tier, 0.25)
        basis: Literal["measured", "static_prior"] = (
            "measured" if benchmark is not None else "static_prior"
        )
        working.append((candidate, quality, basis))

    any_measured = any(basis == "measured" for _, _, basis in working)

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
            -row[1],
            any_measured and row[2] != "measured",
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
            eligible=candidate.ready and candidate.would_exceed_budget is False,
            rank=index,
        )
        for index, (candidate, quality, basis) in enumerate(working, start=1)
    )
    recommended = next((row.candidate.tier for row in ranked if row.eligible), None)
    return DecisionResult(task=task, recommended_tier=recommended, ranked=ranked)


__all__ = [
    "DecisionCandidate",
    "DecisionResult",
    "DecisionTask",
    "RankedDecisionCandidate",
    "rank_model_candidates",
]
