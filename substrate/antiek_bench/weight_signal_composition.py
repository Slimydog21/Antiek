"""Diff-aware weight composition — the recursion glue the weight loop was missing (ask #11).

The operator's ask #11: *"...recursive where it learns from usage patterns to
understand what worked and what didn't in a given week to re-write the
benchmark..."* The bench recursion has two loops, kept deliberately separate
(``task_rewrite.py`` docstring): the **weight loop** (continuous redistribution
of emphasis across the *existing* task set) and the **structure loop** (discrete
*which tasks should exist*). Both existing weight implementations —
``propose_next_week_weights`` (#810) and ``default_laplace_weights`` (#1831) —
are **failure-driven only**: a task's mass is ``n_failure + 1``. That answers
"where did models fail this week" but NEVER "where is behavior *changing*."

The week-over-week diff (``week_diff.py``, #1862) produces exactly that
directional signal — which ``(task_family, model)`` improved, regressed, stayed
unchanged, or is new/dropped/unknown. Its own docstring names the weight loop as
a consumer ("regressed task → ..."), yet nothing composes the diff INTO the
weight proposal. **This module is that composition** — the pure glue that gives
the weight loop a directional gradient on top of the failure-driven base mass.
It closes the recursion edge the operator named and that #1862 anticipated.

**Why boost regressions only.** A regressed family is where model behavior is
actively slipping — re-measuring it next week has the highest information value
for "what didn't work *this* week," and a high-but-*stable* failure rate (which
failure counts alone reward forever) is not the same signal. So a net-regressed
family gets a multiplicative boost on its base mass. Improvement is deliberately
*not* down-weighted here: reducing a task's emphasis because it saturated is the
**structure loop's** graduate decision (#1843), not the weight loop's —
conflating them would hide a discrete structure decision behind a continuous
knob (hard to vary → wrong). Relative normalization after boosting still leaves
every family at or above its ``min_weight`` floor, so no family is silently
zeroed.

**Pure + import-free of #1862.** ``week_diff.py`` ships in a separate off-main
PR; hard-importing its shapes would stack two PRs and break independent
bar-cleanliness on a frozen main. Instead this module defines a compatible
minimal :class:`ModelDelta` (``task_family`` + ``direction``) that the route
layer adapts 1:1 from ``ScoreDelta``. The module owns the ONE thing no other
does: turning the directional diff into a weight-proposal input.

**The load-bearing invariants (each is a test):**

1. **No diff signal → no boost.** A family with no comparable model deltas (all
   new/dropped/unknown, or absent from the signals) keeps its base mass exactly.
   Inventing a regression would fabricate a boost.
2. **Only net-regressed families boost.** A family boosts IFF
   ``n_regressed > n_improved`` (strict) AND ``regression_boost > 0``. A tie or
   net improvement → no boost.
3. **Boost is multiplicative and auditable.** ``mass = base * (1 + regression_boost)``;
   the base mass, the applied factor, and the product all survive on the record.
4. **Unknowns never produce a boost.** A model delta whose direction is
   ``unknown`` / ``new`` / ``dropped`` counts toward *neither* improved nor
   regressed. "We don't know" never becomes "it regressed."
5. **Empty usage → incomplete, no invented weights.** No base mass means no
   weights — the diff gives direction, not a mandate to measure (mirrors #810).
6. **Weights sum to exactly 1.0** when non-empty (largest-remainder rounding,
   consistent with #1831 / #810).
7. **``min_weight`` floor is HARD** — when feasible
   (``len(families) * min_weight <= 1.0``) every family lands at or above the
   floor via iterative water-filling, so a directional boost can shrink a
   non-regressed family's share but can never silently zero it. An infeasible
   floor is honestly skipped (never silently relaxed).
8. **Deterministic + pure.** Same signals + usage mass → byte-identical proposal.
   No I/O, no clock, no dispatch, no LLM.
9. **No family is invented from one side alone.** A family in the diff but not in
   the usage mass is NOT weighted (noted); a family in the usage mass but not in
   the diff gets no boost (noted) — both surfaces are honest about the gap.
10. **``regression_boost >= 0``** — a negative boost would down-weight the very
    regressions this module exists to emphasize (incoherent); validated on use.

**Composition (the recursive loop):**

    usage outcomes ──→ #810/#1831 failure-driven base mass (per task_family) ─┐
                                                                               │
    two weekly snapshots ─→ #1862 diff ─→ [THIS] diff-aware boost ─→ weights ─┤
                                                                               │
    next-week bench emphasis ◄─────────────────────────────────────────────────┘
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

# Directions compatible with #1862 ScoreDelta.direction.
_IMPROVED = "improved"
_REGRESSED = "regressed"
_UNCHANGED = "unchanged"
_UNKNOWN = "unknown"
_NEW = "new"
_DROPPED = "dropped"
_VALID_DIRECTIONS = frozenset(
    {_IMPROVED, _REGRESSED, _UNCHANGED, _UNKNOWN, _NEW, _DROPPED}
)

# Family-level net directions (this module's vocabulary, not model-level).
_NO_SIGNAL = "no_signal"  # family has no comparable model deltas
_NEITHER = "neither"  # comparable models exist but improved == regressed


class WeightCompositionError(ValueError):
    """A composition input violates a load-bearing invariant."""


@dataclass(frozen=True)
class ModelDelta:
    """One ``(task_family, model)`` directional verdict.

    Compatible with #1862's ``ScoreDelta`` (the route layer maps its ``direction``
    field verbatim). Only the family and the direction are needed to aggregate a
    family-level signal — the raw scores stay on the diff.
    """

    task_family: str
    direction: str


@dataclass(frozen=True)
class FamilyDirectionSignal:
    """One task family's directional verdict, aggregated from its model deltas.

    ``net_direction`` is the family-level conclusion the weight loop learns from:
    ``regressed`` iff more models regressed than improved (strict); ``improved``
    iff the reverse; ``neither`` if comparable models exist but tie;
    ``no_signal`` if the family has no comparable model deltas.
    """

    task_family: str
    n_improved: int = 0
    n_regressed: int = 0
    n_unchanged: int = 0
    n_unknown: int = 0
    n_new: int = 0
    n_dropped: int = 0

    @property
    def n_comparable(self) -> int:
        """Models with a real directional verdict (improved/regressed/unchanged)."""
        return self.n_improved + self.n_regressed + self.n_unchanged

    @property
    def net_direction(self) -> str:
        if self.n_regressed > self.n_improved:
            return _REGRESSED
        if self.n_improved > self.n_regressed:
            return _IMPROVED
        if self.n_comparable > 0:
            return _NEITHER
        return _NO_SIGNAL


def aggregate_family_directions(
    deltas: Sequence[ModelDelta],
) -> list[FamilyDirectionSignal]:
    """Aggregate model-level deltas into per-family directional signals.

    Each model delta contributes to exactly one counter on its family. Unknown /
    new / dropped deltas are recorded (audit) but never counted as improved or
    regressed — they cannot produce a boost. Deterministic: families are emitted
    in sorted ``task_family`` order.
    """
    builders: dict[str, dict[str, int]] = {}
    for delta in deltas:
        family = (delta.task_family or "").strip()
        if not family:
            raise WeightCompositionError("ModelDelta.task_family must be non-empty")
        direction = delta.direction
        if direction not in _VALID_DIRECTIONS:
            raise WeightCompositionError(
                f"unknown direction {direction!r} for family {family!r}"
            )
        bucket = builders.setdefault(
            family,
            {
                "n_improved": 0,
                "n_regressed": 0,
                "n_unchanged": 0,
                "n_unknown": 0,
                "n_new": 0,
                "n_dropped": 0,
            },
        )
        bucket[f"n_{direction}"] += 1
    return [
        FamilyDirectionSignal(task_family=family, **builders[family])
        for family in sorted(builders)
    ]


@dataclass(frozen=True)
class FamilyWeightRecord:
    """One family's composed weight, fully auditable.

    Everything needed to reproduce the verdict survives: the base mass the caller
    supplied, the directional conclusion, whether the boost fired, the exact
    factor applied, and the resulting normalized weight. No black-box weights.
    """

    task_family: str
    weight: float
    base_mass: float
    net_direction: str
    boosted: bool
    factor_applied: float
    n_improved: int
    n_regressed: int
    n_comparable: int
    rationale: str


@dataclass(frozen=True)
class DiffAwareWeightProposal:
    """A week's diff-aware weight proposal. Pure value; advisory, never mutates."""

    week_id: str
    authority: str
    incomplete: bool
    family_weights: list[FamilyWeightRecord]
    boosted_families: tuple[str, ...] = ()
    unweighted_diff_families: tuple[str, ...] = ()
    notes: list[str] = field(default_factory=list)

    @property
    def has_weights(self) -> bool:
        return len(self.family_weights) > 0


def _largest_remainder(weights: dict[str, float]) -> dict[str, float]:
    """Round fractions to 8 decimals so they sum to exactly 1.0.

    Mirrors #1831's discipline: rounding drift is distributed to the largest
    weight so the published total is exactly 1.0 (conservation of mass).
    """
    scaled = {k: round(w, 8) for k, w in weights.items()}
    if not scaled:
        return scaled
    drift = round(1.0 - sum(scaled.values()), 8)
    if abs(drift) < 1e-12:
        return scaled
    largest = max(scaled, key=lambda k: scaled[k])
    scaled[largest] = round(scaled[largest] + drift, 8)
    return scaled


def _apply_floor(weights: dict[str, float], min_weight: float) -> dict[str, float]:
    """Apply a HARD per-family weight floor via iterative water-filling.

    When feasible (``n * min_weight <= 1.0``) every family lands at or above
    ``min_weight`` and the weights still sum to 1.0. Items that would fall below
    the floor are clamped to it; the remaining budget is redistributed
    proportionally across the rest, repeating until stable. This is the
    anti-conflation guard: a directional boost can shrink a non-regressed
    family's share but can never silently zero it. An infeasible floor
    (``n * min_weight > 1.0``) is a no-op — a hard floor that cannot fit is not
    silently relaxed, it is honestly skipped.
    """
    keys = list(weights)
    n = len(keys)
    if n == 0 or min_weight <= 0 or n * min_weight > 1.0 + 1e-12:
        return dict(weights)
    clamped: dict[str, float] = {}
    pool = dict(weights)
    for _ in range(n + 1):
        unclamped = [k for k in keys if k not in clamped]
        if not unclamped:
            break
        budget = 1.0 - sum(clamped.values())
        if budget <= 0:
            break
        pool_total = sum(pool[k] for k in unclamped)
        if pool_total <= 0:
            share = budget / len(unclamped)
            for k in unclamped:
                pool[k] = share
            break
        shares = {k: pool[k] / pool_total * budget for k in unclamped}
        below = {k for k, v in shares.items() if v < min_weight - 1e-12}
        if not below:
            for k in unclamped:
                pool[k] = shares[k]
            break
        for k in below:
            clamped[k] = min_weight
    out: dict[str, float] = dict(clamped)
    for k in keys:
        if k not in clamped:
            out[k] = pool[k]
    return out


def compose_diff_aware_weights(
    *,
    signals: Sequence[FamilyDirectionSignal],
    usage_mass: Mapping[str, float],
    regression_boost: float = 1.0,
    min_weight: float = 0.0,
    week_id: str = "",
) -> DiffAwareWeightProposal:
    """Compose the directional diff into a diff-aware weight proposal.

    Parameters
    ----------
    signals:
        Per-family directional signals (from :func:`aggregate_family_directions`
        over #1862's diff). Families absent here get no boost.
    usage_mass:
        Per-family failure-driven base mass (the caller computes this from usage
        outcomes, e.g. ``n_failure + 1`` as in #810/#1831). A family absent here
        is not weighted even if the diff knows about it.
    regression_boost:
        Multiplicative boost added to a net-regressed family's base mass
        (``mass = base * (1 + regression_boost)``). Must be ``>= 0``. Default
        ``1.0`` doubles a regressed family's mass.
    min_weight:
        Floor on each family's normalized weight, honored when feasible
        (``len(families) * min_weight <= 1.0``). Guards against a boost silently
        zeroing a non-regressed family. Default ``0.0`` (no floor).

    A net-regressed family is one whose model deltas contain strictly more
    regressions than improvements. Everything else keeps its base mass; relative
    normalization then redistributes the boosted mass. The proposal is
    ``incomplete`` (no weights) only when there is no usable usage mass at all.
    """
    notes: list[str] = [
        "authority=advisory — proposal only; does not mutate antiek_bench",
        "boost is failure-driven base mass modulated by the directional diff only",
    ]
    if regression_boost < 0:
        raise WeightCompositionError(
            f"regression_boost must be >= 0 (got {regression_boost})"
        )
    if min_weight < 0:
        raise WeightCompositionError(f"min_weight must be >= 0 (got {min_weight})")

    week = (week_id or "").strip()
    signal_index: dict[str, FamilyDirectionSignal] = {
        (s.task_family or "").strip(): s for s in signals
    }

    usage: dict[str, float] = {}
    for family, mass in usage_mass.items():
        key = (family or "").strip()
        if not key:
            continue
        try:
            mass_f = float(mass)
        except (TypeError, ValueError):
            notes.append(f"ignored non-numeric usage mass for family {key!r}")
            continue
        usage[key] = max(0.0, mass_f)

    if not usage:
        notes.append("no usable usage mass — incomplete proposal (not inventing weights)")
        return DiffAwareWeightProposal(
            week_id=week,
            authority="advisory",
            incomplete=True,
            family_weights=[],
            notes=notes,
        )

    unweighted_diff = sorted(set(signal_index) - set(usage))
    if unweighted_diff:
        notes.append(
            f"{len(unweighted_diff)} family/families have a directional signal but "
            "no usage mass — not inventing weights"
        )
    no_signal_families = sorted(set(usage) - set(signal_index))
    if no_signal_families:
        notes.append(
            f"{len(no_signal_families)} family/families in usage mass have no "
            "directional signal — no boost applied"
        )

    families = sorted(usage)
    boosted: list[str] = []
    raw: dict[str, float] = {}
    audit: dict[str, tuple[str, bool, float, FamilyDirectionSignal]] = {}
    for family in families:
        base = usage[family]
        sig = signal_index.get(family, FamilyDirectionSignal(task_family=family))
        eligible = sig.net_direction == _REGRESSED
        factor = (1.0 + regression_boost) if eligible and regression_boost > 0 else 1.0
        is_boosted = eligible and regression_boost > 0
        if is_boosted:
            boosted.append(family)
        direction = sig.net_direction
        raw[family] = base * factor
        audit[family] = (direction, is_boosted, factor, sig)

    total = sum(raw.values())
    if total <= 0:
        notes.append("all base masses were zero — falling back to uniform weighting")
        n = len(families)
        rounded = _largest_remainder({f: 1.0 / n for f in families})
        records = _build_records(families, rounded, audit, usage, uniform=True)
        return DiffAwareWeightProposal(
            week_id=week,
            authority="advisory",
            incomplete=False,
            family_weights=records,
            boosted_families=tuple(boosted),
            unweighted_diff_families=tuple(unweighted_diff),
            notes=notes,
        )

    weights = {f: raw[f] / total for f in families}
    if min_weight > 0:
        weights = _apply_floor(weights, min_weight)

    rounded = _largest_remainder(weights)
    records = _build_records(families, rounded, audit, usage, uniform=False)
    return DiffAwareWeightProposal(
        week_id=week,
        authority="advisory",
        incomplete=False,
        family_weights=records,
        boosted_families=tuple(boosted),
        unweighted_diff_families=tuple(unweighted_diff),
        notes=notes,
    )


def _build_records(
    families: list[str],
    weights: dict[str, float],
    audit: dict[str, tuple[str, bool, float, FamilyDirectionSignal]],
    usage: dict[str, float],
    *,
    uniform: bool,
) -> list[FamilyWeightRecord]:
    """Assemble the auditable per-family records in sorted family order."""
    records: list[FamilyWeightRecord] = []
    for family in families:
        direction, is_boosted, factor, sig = audit[family]
        base = usage[family]
        if uniform:
            rationale = "uniform fallback — all base masses were zero"
        elif is_boosted:
            rationale = (
                f"up-weighted: net regressed "
                f"(regressed={sig.n_regressed} > improved={sig.n_improved}); "
                f"base={base:g} × factor={factor:g}"
            )
        elif direction == _REGRESSED:
            rationale = (
                f"net regressed but boost=0; base mass only (base={base:g})"
            )
        elif direction == _IMPROVED:
            rationale = (
                f"base mass only: net improved "
                f"(improved={sig.n_improved}, regressed={sig.n_regressed}); "
                "improvement is not down-weighted "
                "(saturated-task reduction is the structure loop's job)"
            )
        elif direction == _NEITHER:
            rationale = (
                f"base mass only: comparable but tied "
                f"(improved={sig.n_improved}, regressed={sig.n_regressed}; "
                f"base={base:g})"
            )
        else:  # _NO_SIGNAL
            rationale = f"base mass only: no directional signal (base={base:g})"
        records.append(
            FamilyWeightRecord(
                task_family=family,
                weight=weights[family],
                base_mass=base,
                net_direction=direction,
                boosted=is_boosted,
                factor_applied=factor,
                n_improved=sig.n_improved,
                n_regressed=sig.n_regressed,
                n_comparable=sig.n_comparable,
                rationale=rationale,
            )
        )
    return records
