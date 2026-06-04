"""AFF SPR-09 PILOT — derive the run parameters from observed variance.

The spec FORBIDS choosing ``n`` a priori and forbids the grader self-certifying
the bar (OPERATOR_INPUTS §0.2). So the parameters are DERIVED from a pilot, not
asserted, and the OPERATOR ratifies them before any scored (``mock_run=false``)
run. This module:

  1. PILOT: runs 5 runs/cell on 2–3 representative questions across all arms and
     reports the realized per-metric coefficient of variation (CV) — measured,
     not assumed.
  2. DERIVE: ``propose_parameters(pilot_cv)`` is a PURE function that turns the
     observed CV into a proposal:
        * ``n``                 — runs/question×arm, from a target CI half-width.
        * ``material_floor``    — the warm-cheaper bar, set strictly OUTSIDE the
                                  cold-arm noise band.
        * ``control_tolerance`` — TIGHTER than the floor (so the control can't
                                  "pass as flat" an effect big enough to count as
                                  compounding).

The pilot may run on the mock path to demonstrate the pipeline. The derived
numbers are a PROPOSAL; the live ``n`` is operator-ratified (§0.2).
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import asdict, dataclass

from .harness import ArmResult, ArmSeed, ColdSeed, IrrelevantSeed, WarmSeed, run_arm
from .question_set import BenchmarkQuestion

# CV metrics the pilot reports + the proposal keys off. Cost is the headline;
# sources + wall corroborate.
PILOT_CV_METRICS = ("token_cost_usd", "sources_fetched", "wall_ms")

# Target CI half-width as a fraction of the cold-arm mean (relative precision).
# A reviewer can change this single number; n scales with the square of the CV
# over this target.
TARGET_RELATIVE_HALF_WIDTH = 0.10

# Bounds so a degenerate (zero-variance mock) pilot proposes a sane n and a
# non-degenerate pilot can't propose an unrunnable one.
MIN_PROPOSED_N = 5
MAX_PROPOSED_N = 200
# Floor for the absolute material-effect bar when the cold mean is ~0 (the mock
# path), expressed in the headline metric's own units (USD). Keeps the floor
# from collapsing to 0 and trivially declaring everything material.
MIN_MATERIAL_FLOOR_USD = 0.0


@dataclass(frozen=True)
class CellStats:
    """Per-arm, per-metric mean + CV over the pilot runs of one cell."""

    arm: str
    metric: str
    mean: float
    cv: float
    n_runs: int


@dataclass(frozen=True)
class PilotReport:
    """The pilot's realized variance. ``cv`` is the headline per-metric CV
    (pooled across the representative questions, cold arm) the proposal keys off;
    ``cell_stats`` is the full per-arm breakdown for the record."""

    cv: dict[str, float]
    cold_means: dict[str, float]
    cell_stats: list[CellStats]
    questions: list[str]
    runs_per_cell: int

    def to_dict(self) -> dict[str, object]:
        return {
            "cv": self.cv,
            "cold_means": self.cold_means,
            "questions": self.questions,
            "runs_per_cell": self.runs_per_cell,
            "cell_stats": [asdict(c) for c in self.cell_stats],
        }


@dataclass(frozen=True)
class ProposedParameters:
    """The DERIVED proposal. Carries the derivation so the operator ratifies a
    number with its rationale attached (§0.2), never a bare value."""

    n: int
    material_floor: float
    control_tolerance: float
    derivation: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _cv(values: Sequence[float]) -> float:
    """Coefficient of variation = stdev / |mean|. Returns 0.0 for a constant
    series (the deterministic mock path) and for a near-zero mean (CV is
    undefined there — reported as 0 and flagged by the zero mean itself)."""
    if len(values) < 2:
        return 0.0
    mean = statistics.fmean(values)
    if abs(mean) < 1e-12:
        return 0.0
    return statistics.stdev(values) / abs(mean)


def propose_parameters(
    pilot_cv: dict[str, float],
    *,
    cold_means: dict[str, float] | None = None,
    target_relative_half_width: float = TARGET_RELATIVE_HALF_WIDTH,
) -> ProposedParameters:
    """PURE: derive ``{n, material_floor, control_tolerance}`` from observed CV.

    ``n`` from a target CI half-width: for a mean estimate the half-width scales
    as ``z·CV/√n`` (relative), so ``n ≈ (z·CV / target)²``. We use the headline
    metric's CV and z=1.96 (95%). The ``material_floor`` is set to ``2·CV`` of the
    cold mean — strictly OUTSIDE the cold-arm noise band (a real effect must
    exceed two relative standard deviations of cold). The ``control_tolerance`` is
    set TIGHTER than the floor (half of it) so the control cannot pass-as-flat an
    effect large enough to count as compounding (§2).

    Degenerate mock path (CV≈0, cold mean≈0): n clamps to MIN_PROPOSED_N, the
    floor and tolerance to their minimums — the derivation string says so plainly
    so the operator does not mistake a zero-variance mock for a powered run."""
    cold_means = cold_means or {}
    headline_cv = float(pilot_cv.get("token_cost_usd", 0.0))
    z = 1.96

    if headline_cv <= 0.0:
        n = MIN_PROPOSED_N
        n_note = (
            f"headline CV is 0 (deterministic/zero-variance pilot — the mock path); "
            f"n clamped to MIN_PROPOSED_N={MIN_PROPOSED_N}. A live pilot with real "
            f"provider variance will raise this."
        )
    else:
        raw_n = (z * headline_cv / target_relative_half_width) ** 2
        n = int(max(MIN_PROPOSED_N, min(MAX_PROPOSED_N, math.ceil(raw_n))))
        n_note = (
            f"n = ceil((z·CV/target)²) = ceil(({z}·{headline_cv:.4g}/"
            f"{target_relative_half_width:.4g})²) = {n} (clamped to "
            f"[{MIN_PROPOSED_N},{MAX_PROPOSED_N}])"
        )

    cold_cost_mean = abs(float(cold_means.get("token_cost_usd", 0.0)))
    # Floor strictly outside the cold noise band: two relative SDs of cold.
    floor = max(MIN_MATERIAL_FLOOR_USD, 2.0 * headline_cv * cold_cost_mean)
    tolerance = floor / 2.0 if floor > 0 else 0.0

    derivation = (
        f"{n_note}. material_floor = 2·CV·|cold_mean| = 2·{headline_cv:.4g}·"
        f"{cold_cost_mean:.6g} = {floor:.6g} USD (strictly outside the cold-arm "
        f"noise band). control_tolerance = floor/2 = {tolerance:.6g} (tighter than "
        f"the floor, so the control cannot pass-as-flat a compounding-sized effect)."
    )
    return ProposedParameters(
        n=n, material_floor=floor, control_tolerance=tolerance, derivation=derivation,
    )


def run_pilot(
    questions: Sequence[BenchmarkQuestion],
    *,
    events_dir: str,
    graphs_dir: str,
    runs_per_cell: int = 5,
) -> PilotReport:
    """Run ``runs_per_cell`` runs/cell on the representative ``questions`` across
    all three arms, and report realized per-metric CV. Drives the real harness
    on the mock path (the demo loop) — the pipeline is demonstrated; the numbers
    are honestly the mock path's (zero-variance) numbers."""
    by_arm: dict[str, dict[str, list[float]]] = {
        "cold": {m: [] for m in PILOT_CV_METRICS},
        "warm": {m: [] for m in PILOT_CV_METRICS},
        "irrelevant": {m: [] for m in PILOT_CV_METRICS},
    }
    seeds: dict[str, ArmSeed] = {"cold": ColdSeed(), "warm": WarmSeed(), "irrelevant": IrrelevantSeed()}

    # run_arm already namespaces user_id by question_id + arm, so run_index need
    # only be unique within a (question, arm) cell — range(runs_per_cell) is that.
    for q in questions:
        for run_index in range(runs_per_cell):
            for arm_name, seed in seeds.items():
                res: ArmResult = run_arm(
                    q, seed, events_dir=events_dir, graphs_dir=graphs_dir,
                    run_index=run_index,
                )
                for m in PILOT_CV_METRICS:
                    by_arm[arm_name][m].append(float(getattr(res.cost, m)))

    cell_stats: list[CellStats] = []
    for arm_name, metrics in by_arm.items():
        for m, values in metrics.items():
            cell_stats.append(CellStats(
                arm=arm_name, metric=m,
                mean=statistics.fmean(values) if values else 0.0,
                cv=_cv(values), n_runs=len(values),
            ))

    # The proposal keys off the COLD arm's CV (the run-to-run noise the floor
    # must clear) and cold means (the floor is relative to cold).
    cv = {m: _cv(by_arm["cold"][m]) for m in PILOT_CV_METRICS}
    cold_means = {m: (statistics.fmean(by_arm["cold"][m]) if by_arm["cold"][m] else 0.0)
                  for m in PILOT_CV_METRICS}

    return PilotReport(
        cv=cv,
        cold_means=cold_means,
        cell_stats=cell_stats,
        questions=[q.question_id for q in questions],
        runs_per_cell=runs_per_cell,
    )
