"""Wedge 3 nightly config sweep.

Per `docs/integration_autoresearch.md` Wedge 3 + the Sprint 30+ doc
thread 5:

1. Pull graded outcomes from the cohort window (cohort must have
   ≥ COHORT_MIN_OUTCOMES, otherwise the sweep aborts with `cohort_too_small`)
2. For each candidate config (cartesian over the sweep axes):
   a. Score against the cohort outcomes via the named scoring function
   b. Compare to the baseline config's score on the same cohort
3. Rank candidates by score_improvement; return the top one as a
   `ConfigProposal` for operator review
4. NEVER auto-promote — that's the operator's call per the Loop 3
   unlock criteria

The substrate is pure-functional over (cohort_outcomes, baseline_config,
sweep_axes, scoring_function). The scoring function is caller-supplied;
production wires `score_against_outcomes_table`, tests use stubs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from .proposal import CohortWindow, ConfigProposal, SweepAxes


COHORT_MIN_OUTCOMES = 500  # per §14.1


# ScoringFunction maps a (config_dict, cohort_outcomes_payload) tuple to
# a scalar score. Higher = better. Caller supplies; substrate doesn't
# choose. The scoring function name lives in SweepAxes for replay.
ScoringFunction = Callable[[dict, object], float]


@dataclass(frozen=True)
class SweepCandidate:
    """One config + its score."""

    config: dict
    score: float
    delta_against_baseline: dict


@dataclass(frozen=True)
class SweepInput:
    """The full input envelope to a sweep run."""

    cohort: CohortWindow
    baseline_config: dict
    axes: SweepAxes
    cohort_outcomes: object  # opaque payload; scoring function understands it
    scoring_function: ScoringFunction


@dataclass(frozen=True)
class SweepResult:
    """The full output of a sweep run."""

    status: str  # "ok" | "cohort_too_small" | "no_improvement"
    ranked_candidates: tuple[SweepCandidate, ...]
    baseline_score: float
    proposal: Optional[ConfigProposal] = None


def _candidate_configs(
    baseline: dict,
    axes: SweepAxes,
) -> list[dict]:
    """Enumerate cartesian product of (context_pack_composition × dispatch_tier).

    A candidate config is the baseline with the chosen axis values
    overridden. Empty axes → just the baseline (a no-op sweep).
    """
    compositions = list(axes.context_pack_compositions) or [
        baseline.get("context_pack_composition", "default"),
    ]
    routes = list(axes.dispatch_tier_routes) or [
        baseline.get("dispatch_tier_route", "default"),
    ]
    out: list[dict] = []
    for comp in compositions:
        for route in routes:
            cfg = dict(baseline)
            cfg["context_pack_composition"] = comp
            cfg["dispatch_tier_route"] = route
            out.append(cfg)
    return out


def _diff_against_baseline(baseline: dict, candidate: dict) -> dict:
    """Minimal delta — keys where candidate differs from baseline."""
    delta: dict = {}
    for k, v in candidate.items():
        if baseline.get(k) != v:
            delta[k] = v
    return delta


def rank_candidates(
    candidates: list[SweepCandidate],
) -> list[SweepCandidate]:
    """Sort by score descending. Stable order for ties."""
    return sorted(
        candidates,
        key=lambda c: (-c.score, sorted(c.config.items())),
    )


def run_sweep(inp: SweepInput) -> SweepResult:
    """Run a nightly sweep. Pure-functional; no I/O."""
    if inp.cohort.graded_outcomes_count < COHORT_MIN_OUTCOMES:
        return SweepResult(
            status="cohort_too_small",
            ranked_candidates=(),
            baseline_score=0.0,
        )

    baseline_score = inp.scoring_function(
        inp.baseline_config, inp.cohort_outcomes,
    )

    candidates: list[SweepCandidate] = []
    for cfg in _candidate_configs(inp.baseline_config, inp.axes):
        score = inp.scoring_function(cfg, inp.cohort_outcomes)
        candidates.append(SweepCandidate(
            config=cfg,
            score=score,
            delta_against_baseline=_diff_against_baseline(
                inp.baseline_config, cfg,
            ),
        ))

    ranked = rank_candidates(candidates)

    if not ranked or ranked[0].score <= baseline_score:
        return SweepResult(
            status="no_improvement",
            ranked_candidates=tuple(ranked),
            baseline_score=baseline_score,
        )

    top = ranked[0]
    proposal = ConfigProposal(
        baseline_config=dict(inp.baseline_config),
        proposed_delta=dict(top.delta_against_baseline),
        cohort=inp.cohort,
        axes=inp.axes,
        score=top.score,
        baseline_score=baseline_score,
    )
    return SweepResult(
        status="ok",
        ranked_candidates=tuple(ranked),
        baseline_score=baseline_score,
        proposal=proposal,
    )
