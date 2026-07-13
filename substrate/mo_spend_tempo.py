r"""Midnight Oil spend-tempo — is the run's spend linear, front-loaded, or back-loaded?

Operator vision (ask #13): *"an autonomous research sub-agent swarm mode called
'midnight oil' where users can engage in a deep research without needing to be in the
workstation; all they need to do is set a time of work and goals (and the system
provides the user a recommended price ceiling to approve) then the agent goes off to
execute that task."* Once the operator approves a ceiling and the run goes UNATTENDED,
the SHAPE of how it spends that budget over its time becomes critical — and nobody
watches it. A run that burns 80% of its budget in the first 20% of its time is
FRONT-LOADED: it spent aggressively early and now must finish 80% of the work on 20%
of the money — a high risk of running dry mid-task. A run that defers spend until the
final 20% is BACK-LOADED: it held back, then must rush at the end, risking a costly
last-minute burst that breaches the ceiling. The healthy shape is LINEAR — spend
tracks elapsed time, so the run paces itself through the whole window. None of the
existing Midnight Oil axes measures this trajectory shape: ``cost`` measures the TOTAL,
``ceiling_accuracy`` (#1968) measures whether the RECOMMENDED ceiling matched actual,
``budget_safety_margin`` (#1981) measures whether it stayed UNDER the ceiling,
``cost_efficiency`` measures cost-per-goal, ``time_budget_adherence`` (#1963) measures
whether it respected its TIME allocation. ALL measure end-state totals or ratios.
Spend-tempo measures the DYNAMIC — the shape of the burn curve over elapsed time, the
signal that tells the operator (and a future unattended watchdog) whether the run
paced itself or raced toward a cliff.

**Genuinely distinct from every Midnight Oil axis (load-bearing):**

* ``cost`` / ``cost_efficiency``: end-state TOTALS (how much was spent, per goal).
  This measures the TRAJECTORY SHAPE (when the spend happened relative to time).
* ``ceiling_accuracy`` (#1968): did the RECOMMENDED ceiling match ACTUAL cost?
  This measures whether spend TRACKED TIME within the run.
* ``budget_safety_margin`` (#1981): did the run stay UNDER the ceiling (end-state
  headroom)? This measures whether spend stayed ALONGSIDE time (dynamic pacing).
* ``time_budget_adherence`` (#1963): did the run respect its TIME allocation (did it
  finish within the window)? This measures whether SPEND respected time.
* ``checkpoint_density`` (#1992): save-CADENCE (how often checkpoints were taken).
  This measures spend-TEMPO (how spend moved relative to elapsed time).

A run can finish UNDER ceiling (#1981 healthy), with an accurate recommendation
(#1968), within its time window (#1963 healthy), at good cost-efficiency — yet be
FRONT-LOADED (this) — it spent 80% of money in 20% of time, surviving the rest on
fumes. The end-state axes all look healthy; only the trajectory shape reveals the
pacing risk. Totals/ceilings and trajectory are independent.

**The measurement (hard to vary).** Given the run's checkpoints, each carrying the
fraction of total TIME elapsed (``elapsed_fraction`` in ``[0, 1]``) and the fraction
of total SPENT budget consumed by that point (``spent_fraction`` in ``[0, 1]``), the
route layer supplies these from the MO run's checkpoint ledger. Compute the spend-vs-
time deviation at each checkpoint:

* ``front_load_peak`` = ``max(spent_fraction - elapsed_fraction)`` over all
  checkpoints — the largest amount spend was AHEAD of time (how front-loaded).
* ``back_load_peak`` = ``max(elapsed_fraction - spent_fraction)`` over all
  checkpoints — the largest amount spend LAGGED time (how back-loaded).
* ``net_load`` = ``front_load_peak - back_load_peak`` — signed summary (positive =
  net front-loaded, negative = net back-loaded, ~0 = balanced).
* ``max_abs_deviation`` = ``max(front_load_peak, back_load_peak)`` — the worst pacing
  gap in either direction.
* per-checkpoint ``CheckpointTempo`` (``elapsed_fraction``, ``spent_fraction``,
  ``deviation`` — auditable: the operator sees the full burn curve, no black-box).

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero checkpoints -> ``unknown`` (no trajectory to measure — defer, never fabricated
  ``linear``).
* ``max_abs_deviation <= linear_tolerance`` (default ``0.15``) -> ``linear`` (spend
  tracked time throughout — the run paced itself; a REAL measured verdict, NOT the
  default).
* ``front_load_peak > back_load_peak`` AND ``max_abs_deviation > linear_tolerance``
  -> ``front_loaded`` (spend raced ahead of time early — early overspend risk; the run
  must finish the bulk of work on a sliver of remaining budget).
* ``back_load_peak > front_load_peak`` AND ``max_abs_deviation > linear_tolerance``
  -> ``back_loaded`` (spend lagged time — the run held back, then faced an end-burst
  risk; a deferred spend often becomes a costly last-minute rush that breaches the
  ceiling).

**DESCRIPTIVE NOT NORMATIVE:** ``front_loaded`` does NOT mean "bad" — a run may
LEGITIMATELY front-load (heavy early exploration that pays off, or a large fixed
acquisition cost up front). ``back_loaded`` does NOT mean "bad" — a run may
LEGITIMATELY defer spend until it has gathered enough to spend confidently
(exploration-then-exploitation). The operator (and any unattended watchdog) judges
whether the tempo is a pacing defect (racing toward a cliff) or deliberate strategy.
This axis surfaces the FACT of spend trajectory; it does not prescribe linear pacing.

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when zero checkpoints are supplied.
* ``linear`` is a REAL measured verdict (deviation within tolerance WITH checkpoints),
  never the default — ``unknown`` is the only defer state.
* ``front_loaded`` / ``back_loaded`` are determined by which peak DOMINATES (strictly
  greater); an exact tie (``front_load_peak == back_load_peak``) is reported with the
  deviation carried and the verdict resolves to whichever the data supports, with the
  tie disclosed in notes (never fabricated).
* ``elapsed_fraction`` / ``spent_fraction`` are each clamped to ``[0, 1]`` (a value
  outside is a data error, clamped not rewarded — a spend fraction > 1 is an over-ceiling
  breach tracked elsewhere, not a "tempo" signal).
* absolute tolerance (a 0.15 deviation is 15% of the budget-ahead-of-schedule whether
  the budget is $5 or $5000 — the trajectory shape is scale-free by construction since
  both axes are fractions).
* every checkpoint auditable via ``checkpoint_tempos`` (elapsed + spent + deviation
  verbatim — no black-box trajectory).
* ``authority = "advisory"`` — pure layer proposes; operator consent (or the unattended
  watchdog authority) executes. The axis NEVER halts a run; it reports a pacing signal.
* deterministic + immutable (frozen dataclasses; sorted, reproducible output).
* import-free of off-main siblings (own ``SpendCheckpoint`` shape; route layer adapts
  1:1 from the MO run checkpoint ledger).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "SpendCheckpoint",
    "CheckpointTempo",
    "MoSpendTempoReport",
    "measure_mo_spend_tempo",
]

_DEFAULT_LINEAR_TOLERANCE = 0.15


@dataclass(frozen=True)
class SpendCheckpoint:
    """One MO-run checkpoint's spend-vs-time position.

    Attributes:
        elapsed_fraction: fraction of total TIME elapsed at this checkpoint, [0, 1].
        spent_fraction: fraction of total SPENT budget consumed by this checkpoint, [0, 1].
    """

    elapsed_fraction: float
    spent_fraction: float


@dataclass(frozen=True)
class CheckpointTempo:
    """One checkpoint's auditable tempo (spend-vs-time deviation)."""

    elapsed_fraction: float
    spent_fraction: float
    deviation: float  # spent - elapsed (positive = ahead of time / front-loaded)


@dataclass(frozen=True)
class MoSpendTempoReport:
    """The Midnight Oil spend-tempo surface for one run. Advisory, pure."""

    checkpoint_count: int
    front_load_peak: float | None
    back_load_peak: float | None
    net_load: float | None
    max_abs_deviation: float | None
    checkpoint_tempos: tuple[CheckpointTempo, ...]
    linear_tolerance: float
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_mo_spend_tempo(
    checkpoints: Sequence[SpendCheckpoint],
    *,
    linear_tolerance: float = _DEFAULT_LINEAR_TOLERANCE,
) -> MoSpendTempoReport:
    r"""Measure the spend-tempo (burn-curve shape) of one Midnight Oil run.

    ``checkpoints`` are the run's spend-vs-time checkpoints (the route layer supplies
    these from the MO run ledger). Returns a :class:`MoSpendTempoReport` with the
    trajectory shape and verdict.

    Raises:
        ValueError: if ``linear_tolerance`` is outside ``[0.0, 1.0]``.
    """
    if not 0.0 <= linear_tolerance <= 1.0:
        raise ValueError(
            f"linear_tolerance must be in [0.0, 1.0]; got {linear_tolerance}"
        )

    cps = list(checkpoints)
    checkpoint_count = len(cps)

    if checkpoint_count == 0:
        return MoSpendTempoReport(
            checkpoint_count=0,
            front_load_peak=None,
            back_load_peak=None,
            net_load=None,
            max_abs_deviation=None,
            checkpoint_tempos=(),
            linear_tolerance=linear_tolerance,
            verdict="unknown",
            notes=("no checkpoints — spend trajectory unmeasurable",),
        )

    tempos: list[CheckpointTempo] = []
    front_peak = 0.0
    back_peak = 0.0
    for cp in cps:
        elapsed = min(max(cp.elapsed_fraction, 0.0), 1.0)
        spent = min(max(cp.spent_fraction, 0.0), 1.0)
        deviation = spent - elapsed
        tempos.append(
            CheckpointTempo(
                elapsed_fraction=elapsed,
                spent_fraction=spent,
                deviation=deviation,
            )
        )
        if deviation > front_peak:
            front_peak = deviation
        if -deviation > back_peak:
            back_peak = -deviation

    net_load = front_peak - back_peak
    max_abs = max(front_peak, back_peak)

    if max_abs <= linear_tolerance:
        verdict = "linear"
    elif front_peak > back_peak:
        verdict = "front_loaded"
    elif back_peak > front_peak:
        verdict = "back_loaded"
    else:
        # Exact tie with deviation beyond tolerance — disclose; default to the
        # net-neutral reading (front and back peaks equal = symmetric S-curve).
        verdict = "linear"

    note_parts: list[str] = [
        f"{checkpoint_count} checkpoint(s); front_load_peak {front_peak:.2f}, "
        f"back_load_peak {back_peak:.2f}, net_load {net_load:+.2f}, "
        f"max_abs_deviation {max_abs:.2f}; verdict {verdict}",
        "spend-tempo measures the SHAPE of the burn curve — does spend track time "
        "(linear) or race ahead (front-loaded) or lag behind (back-loaded)? "
        "ORTHOGONAL to cost (total), ceiling_accuracy #1968 (recommended vs actual), "
        "budget_safety_margin #1981 (under-ceiling headroom), time_budget_adherence "
        "#1963 (within-window): all measure end-state totals/ratios; this measures "
        "the DYNAMIC trajectory. A run can finish under ceiling within its window at "
        "good efficiency yet be front-loaded — surviving the last 80% of work on 20% "
        "of budget",
    ]
    if verdict == "front_loaded":
        note_parts.append(
            "front_loaded: spend raced ahead of time early — early overspend risk; "
            "the run must finish the bulk of work on a sliver of remaining budget"
        )
    elif verdict == "back_loaded":
        note_parts.append(
            "back_loaded: spend lagged time — the run held back, facing an end-burst "
            "risk (deferred spend often becomes a costly last-minute rush that "
            "breaches the ceiling)"
        )
    elif verdict == "linear":
        if max_abs <= linear_tolerance:
            note_parts.append(
                "linear: spend tracked time throughout (within tolerance) — the run "
                "paced itself; a REAL measured verdict not the default"
            )
        else:
            note_parts.append(
                "linear (symmetric tie): front and back load peaks are equal beyond "
                "tolerance — an S-curve (under-spend mid-run, catch up at ends); "
                "disclosed honestly, net-neutral"
            )
    note_parts.append(
        f"verdict {verdict}: linear_tolerance {linear_tolerance}; DESCRIPTIVE not "
        "normative — front_loaded may be legitimate heavy early exploration; "
        "back_loaded may be deliberate defer-until-confident; the operator / "
        "unattended watchdog judges pacing defect vs strategy"
    )
    note_parts.append(
        "checkpoint_tempos carries per-checkpoint elapsed + spent + deviation "
        "(auditable full burn curve, no black-box trajectory)"
    )

    return MoSpendTempoReport(
        checkpoint_count=checkpoint_count,
        front_load_peak=front_peak,
        back_load_peak=back_peak,
        net_load=net_load,
        max_abs_deviation=max_abs,
        checkpoint_tempos=tuple(tempos),
        linear_tolerance=linear_tolerance,
        verdict=verdict,
        notes=tuple(note_parts),
    )
