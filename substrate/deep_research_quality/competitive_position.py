"""Competitive-position engine — map Antiek's measured DR quality vs competitors (study-the-competition ask).

The operator's explicit ask: *"I want to provide the highest quality deep
research product in the world (so study the technical decisions made by
competition, write specs, and execute meaningful code to reach that goal)."* The
spec is written (``deep-research-quality-competitive-spec.md`` — five architectural
levers A–E), and Antiek's quality is now *measurable* via the rubric scorer
(#1817, five falsifiable axes). But **nothing composes the two into a competitive
position**: where does Antiek lead, lag, or gap each competitor, on each axis,
with evidence? **This module is that composition** — the structured execution of
"study the competition," turning curated competitor profiles + Antiek's measured
scores into an auditable, falsifiable gap analysis.

**The honesty keystone — measured vs declared.** The classic competitive-analysis
lie is comparing your *measured* score against a competitor's *marketing claim*.
This module refuses that. Every competitor score carries a ``basis``:
``"measured"`` (their actual DR output was run through the same rubric — a real,
reproducible comparison) or ``"declared"`` (curated from their published
claims/docs — an *apparent* position, not a confirmed one). A lead against a
declared score is ``"apparent_lead"``; only a lead against a measured score is
``"confirmed_lead"``. The operator never mistakes "they claim X" for "they
measured X." This is the defensibility axis of the whole competitive analysis.

**Two axis systems, kept distinct (do not conflate).** The rubric scorer (#1817)
measures five *quality* axes (citation_density, grounding_completeness,
uncertainty_surfacing, conflict_resolution, synthesis_present). The competitive
spec names five *architectural* levers (A search/retrieval, B citation rigor,
C source coverage, D synthesis quality, E iteration/cost/transparency). These
overlap but are NOT identical (lever A "search/retrieval architecture" has no
single rubric axis; rubric axis "uncertainty_surfacing" spans levers B+D). This
module models BOTH and lets the caller map rubric axes to levers explicitly — it
never silently assumes a 1:1 correspondence (that would hide a modeling decision
behind a false equivalence, hard to vary → wrong).

**Why pure + import-free of #1817.** The rubric scorer ships in a separate
off-main PR; hard-importing ``DRQualityScore`` would stack two PRs and break
independent bar-cleanliness on a frozen main. Instead this module defines a
compatible :class:`MeasuredQuality` / :class:`AxisScore` (same field semantics)
that the route layer adapts 1:1 from ``DRQualityScore`` / ``RubricAxisScore``.

**The load-bearing invariants (each is a test):**

1. **Measured-vs-declared never conflated.** A comparison's ``confidence`` is
   ``"confirmed"`` only when BOTH Antiek's and the competitor's scores are
   measured; ``"apparent"`` when either is declared; ``"unknown"`` when either is
   unmeasured (``None``). Never fabricated to confirmed.
2. **An unmeasured axis never produces a numeric verdict.** If Antiek's score on
   an axis is ``None`` (rubric could not measure it), the position is
   ``"unknown"`` with delta ``None`` — never a fabricated lead/lag from a 0.0.
3. **Delta is signed and auditable.** ``delta = antiek_score - competitor_score``
   when both known; both raw scores survive on the record. A reviewer reproduces
   the verdict, never trusts a black-box label.
4. **Position uses an epsilon noise floor.** A delta within ``±epsilon`` is
   ``"parity"`` — float noise and genuine ties are not misreported as movement.
5. **No competitor → no analysis.** An empty competitor set yields an empty
   report (flagged), never a fabricated "Antiek leads everyone" from nothing.
6. **Every position is grounded in a reason.** Each ``AxisPosition`` carries a
   human-readable rationale naming the axis, both scores, the delta, and the
   basis — so the gap analysis is defensible, not asserted.
7. **Deterministic + pure.** Same inputs → byte-identical report, ordered by
   (competitor, axis). No I/O, clock, dispatch, or LLM.
8. **Advisory only.** This module produces a position map; it never dispatches a
   competitor's product, never mutates Antiek's config, and never auto-routes
   around a competitor. The operator reads the map and decides where to invest.
9. **Lever coverage is surfaced, not fabricated.** An architectural lever with no
   rubric-axis mapping is reported as ``"unmapped"`` (the caller must curate the
   mapping) — never a synthesized score from thin air.
10. **Competitor identity is stable.** Comparison is keyed by ``competitor_id``;
    the same competitor across runs produces comparable positions (no random ids).

**Composition (the study-the-competition loop):**

    Antiek DR artifact ─→ #1817 rubric_scorer ─→ MeasuredQuality (5 axes) ─┐
                                                                            │
    competitor study (curated profiles: declared/measured per axis) ────────┤
                                                                            ├─→ [THIS]
    architectural levers A–E (the spec) + axis→lever mapping ──────────────┤       │
                                                                            │       ▼
                                                                            │  CompetitivePositionReport
                                                                            │  (per competitor × axis: lead/parity/lag/gap,
                                                                            │   confirmed vs apparent, lever coverage)
                                                                            │       │
                                                                            ▼       ▼
                                              operator: where to invest to reach "highest quality DR in the world"
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

# A delta within ±epsilon is "parity" (float noise / genuinely tied).
_DEFAULT_EPSILON: float = 1e-9

_MEASURED = "measured"
_DECLARED = "declared"

# Position verdicts.
_LEAD = "lead"
_PARITY = "parity"
_LAG = "lag"
_UNKNOWN = "unknown"

# Confidence levels (the measured-vs-declared honesty keystone).
_CONFIRMED = "confirmed"  # both scores measured
_APPARENT = "apparent"  # at least one declared
_CONF_UNKNOWN = "unknown"  # at least one unmeasured (None)

# Lever mapping verdict.
_UNMAPPED = "unmapped"


class CompetitivePositionError(ValueError):
    """A position input violates a load-bearing invariant."""


@dataclass(frozen=True)
class AxisScore:
    """One quality-axis score (compatible with #1817 ``RubricAxisScore``).

    ``score`` is ``None`` when the axis could not be measured for this artifact
    (the rubric reports ``measured=False``). ``basis`` is ``"measured"`` (run
    through the rubric) or ``"declared"`` (curated from published claims).
    """

    axis: str
    score: float | None
    basis: str  # "measured" | "declared"

    def __post_init__(self) -> None:
        if self.basis not in (_MEASURED, _DECLARED):
            raise CompetitivePositionError(
                f"basis must be 'measured' or 'declared', got {self.basis!r}"
            )
        if self.score is not None and not (0.0 <= self.score <= 1.0):
            raise CompetitivePositionError(
                f"axis {self.axis!r}: score must be in [0.0, 1.0] or None, got {self.score}"
            )


@dataclass(frozen=True)
class MeasuredQuality:
    """One product's quality profile across axes (compatible with #1817 ``DRQualityScore``).

    For Antiek this comes from the rubric scorer (all ``basis="measured"``). For a
    competitor it is a curated profile (mix of measured, if their output was
    benched, and declared, from their claims).
    """

    product_id: str
    axes: tuple[AxisScore, ...]

    def score_for(self, axis: str) -> AxisScore | None:
        for a in self.axes:
            if a.axis == axis:
                return a
        return None


@dataclass(frozen=True)
class AxisPosition:
    """Antiek's position vs one competitor on one axis, fully auditable."""

    competitor_id: str
    axis: str
    antiek_score: float | None
    competitor_score: float | None
    delta: float | None  # antiek - competitor when both known; None otherwise
    position: str  # lead / parity / lag / unknown
    confidence: str  # confirmed / apparent / unknown
    antiek_basis: str
    competitor_basis: str
    rationale: str


@dataclass(frozen=True)
class CompetitorComparison:
    """Antiek vs one competitor across all axes."""

    competitor_id: str
    positions: list[AxisPosition] = field(default_factory=list)
    confirmed_leads: tuple[str, ...] = ()  # axes where confirmed lead
    apparent_leads: tuple[str, ...] = ()
    lags: tuple[str, ...] = ()
    parities: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()

    @property
    def lead_count(self) -> int:
        return len(self.confirmed_leads) + len(self.apparent_leads)


@dataclass(frozen=True)
class LeverCoverage:
    """One architectural lever's coverage state (mapped or unmapped)."""

    lever: str
    mapped_axes: tuple[str, ...]
    state: str  # "mapped" | "unmapped"
    note: str


@dataclass(frozen=True)
class CompetitivePositionReport:
    """The full competitive gap analysis. Pure value; advisory."""

    antiek_id: str
    comparisons: list[CompetitorComparison] = field(default_factory=list)
    lever_coverage: list[LeverCoverage] = field(default_factory=list)
    overall_confirmed_lead_axes: tuple[str, ...] = ()  # lead vs ALL competitors, confirmed
    notes: list[str] = field(default_factory=list)

    @property
    def has_competitors(self) -> bool:
        return len(self.comparisons) > 0


def _confidence(antiek_basis: str, competitor_basis: str,
                antiek_score: float | None, competitor_score: float | None) -> str:
    """Honest confidence: confirmed only when both measured AND both scores known."""
    if antiek_score is None or competitor_score is None:
        return _CONF_UNKNOWN
    if antiek_basis == _MEASURED and competitor_basis == _MEASURED:
        return _CONFIRMED
    return _APPARENT


def _position_and_delta(
    antiek: float | None, competitor: float | None, epsilon: float
) -> tuple[float | None, str]:
    if antiek is None or competitor is None:
        return None, _UNKNOWN
    delta = antiek - competitor
    if delta > epsilon:
        return delta, _LEAD
    if delta < -epsilon:
        return delta, _LAG
    return delta, _PARITY


def _rationale(
    *, competitor_id: str, axis: str, antiek: float | None, competitor: float | None,
    delta: float | None, position: str, confidence: str,
    antiek_basis: str, competitor_basis: str,
) -> str:
    a = f"{antiek:.4g}" if antiek is not None else "unmeasured"
    c = f"{competitor:.4g}" if competitor is not None else "unmeasured"
    d = f"{delta:+.4g}" if delta is not None else "n/a"
    return (
        f"{position} vs {competitor_id!r} on {axis!r}: "
        f"antiek={a} ({antiek_basis}) competitor={c} ({competitor_basis}) "
        f"delta={d} confidence={confidence}"
    )


def compare_against_competitor(
    *,
    antiek: MeasuredQuality,
    competitor: MeasuredQuality,
    axes: Sequence[str],
    epsilon: float = _DEFAULT_EPSILON,
) -> CompetitorComparison:
    """Compute Antiek's position vs one competitor across the given axes.

    Each axis produces an :class:`AxisPosition` with honest measured-vs-declared
    confidence. Axes where either score is unmeasured (``None``) are ``"unknown"``
    — never a fabricated lead/lag.
    """
    if epsilon < 0:
        raise CompetitivePositionError(f"epsilon must be >= 0 (got {epsilon})")
    positions: list[AxisPosition] = []
    confirmed_leads: list[str] = []
    apparent_leads: list[str] = []
    lags: list[str] = []
    parities: list[str] = []
    unknowns: list[str] = []

    for axis in axes:
        a_score_obj = antiek.score_for(axis)
        c_score_obj = competitor.score_for(axis)
        a_score = a_score_obj.score if a_score_obj is not None else None
        c_score = c_score_obj.score if c_score_obj is not None else None
        a_basis = a_score_obj.basis if a_score_obj is not None else _DECLARED
        c_basis = c_score_obj.basis if c_score_obj is not None else _DECLARED

        delta, position = _position_and_delta(a_score, c_score, epsilon)
        confidence = _confidence(a_basis, c_basis, a_score, c_score)

        positions.append(
            AxisPosition(
                competitor_id=competitor.product_id,
                axis=axis,
                antiek_score=a_score,
                competitor_score=c_score,
                delta=delta,
                position=position,
                confidence=confidence,
                antiek_basis=a_basis,
                competitor_basis=c_basis,
                rationale=_rationale(
                    competitor_id=competitor.product_id, axis=axis,
                    antiek=a_score, competitor=c_score, delta=delta,
                    position=position, confidence=confidence,
                    antiek_basis=a_basis, competitor_basis=c_basis,
                ),
            )
        )
        if position == _LEAD:
            (confirmed_leads if confidence == _CONFIRMED else apparent_leads).append(axis)
        elif position == _LAG:
            lags.append(axis)
        elif position == _PARITY:
            parities.append(axis)
        else:
            unknowns.append(axis)

    return CompetitorComparison(
        competitor_id=competitor.product_id,
        positions=positions,
        confirmed_leads=tuple(confirmed_leads),
        apparent_leads=tuple(apparent_leads),
        lags=tuple(lags),
        parities=tuple(parities),
        unknowns=tuple(unknowns),
    )


def assess_lever_coverage(
    *,
    levers: Sequence[str],
    axis_to_lever: Mapping[str, str],
    measured_axes: Sequence[str],
) -> list[LeverCoverage]:
    """Map architectural levers to the rubric axes that evidence them.

    A lever with no axis mapping is ``"unmapped"`` (the caller must curate the
    mapping) — never a synthesized score. A lever whose mapped axes are all
    unmeasured is noted honestly.
    """
    measured_set = {a for a in measured_axes}
    coverage: list[LeverCoverage] = []
    for lever in levers:
        mapped = tuple(sorted(a for a, lv in axis_to_lever.items() if lv == lever))
        if not mapped:
            coverage.append(
                LeverCoverage(lever=lever, mapped_axes=(), state=_UNMAPPED,
                              note=f"lever {lever!r} has no rubric-axis mapping — curate one"))
            continue
        measured_mapped = [a for a in mapped if a in measured_set]
        if not measured_mapped:
            coverage.append(
                LeverCoverage(lever=lever, mapped_axes=mapped, state="mapped",
                              note=f"lever {lever!r} mapped to {mapped} but none measured this run"))
        else:
            coverage.append(
                LeverCoverage(lever=lever, mapped_axes=mapped, state="mapped",
                              note=f"lever {lever!r} evidenced by measured axes {tuple(measured_mapped)}"))
    return coverage


def build_competitive_position(
    *,
    antiek: MeasuredQuality,
    competitors: Sequence[MeasuredQuality],
    axes: Sequence[str],
    levers: Sequence[str] | None = None,
    axis_to_lever: Mapping[str, str] | None = None,
    epsilon: float = _DEFAULT_EPSILON,
) -> CompetitivePositionReport:
    """Build the full competitive gap analysis: Antiek vs each competitor, per axis.

    Produces a :class:`CompetitivePositionReport` with one :class:`CompetitorComparison`
    per competitor (ordered by competitor_id), optional architectural-lever coverage,
    and the set of axes where Antiek has a *confirmed* lead against ALL competitors.
    Advisory only — the operator reads the map and decides where to invest.
    """
    if epsilon < 0:
        raise CompetitivePositionError(f"epsilon must be >= 0 (got {epsilon})")
    notes: list[str] = [
        "authority=advisory — competitive position map; never dispatches competitor products or auto-routes",
        "measured-vs-declared is the honesty keystone: confirmed leads require both scores measured",
    ]
    if not competitors:
        notes.append("no competitors provided — empty report (not inventing 'Antiek leads everyone')")
        return CompetitivePositionReport(antiek_id=antiek.product_id, comparisons=[], notes=notes)

    axes_tuple = tuple(dict.fromkeys(axes))  # dedup preserve order
    seen_competitors: set[str] = set()
    comparisons: list[CompetitorComparison] = []
    for comp in competitors:
        cid = (comp.product_id or "").strip()
        if not cid:
            raise CompetitivePositionError("competitor product_id must be non-empty")
        if cid == antiek.product_id:
            raise CompetitivePositionError(
                f"competitor product_id {cid!r} equals antiek product_id — cannot compare against self"
            )
        if cid in seen_competitors:
            notes.append(f"duplicate competitor {cid!r} — skipped")
            continue
        seen_competitors.add(cid)
        comparisons.append(
            compare_against_competitor(
                antiek=antiek, competitor=comp, axes=axes_tuple, epsilon=epsilon
            )
        )

    comparisons.sort(key=lambda c: c.competitor_id)

    # Overall confirmed lead: axes where Antiek confirmed-leads EVERY competitor.
    if comparisons:
        per_comp_confirmed = [set(c.confirmed_leads) for c in comparisons]
        overall_confirmed = sorted(set.intersection(*per_comp_confirmed)) if per_comp_confirmed else []
        if overall_confirmed:
            notes.append(
                f"{len(overall_confirmed)} axis/axes where Antiek has a CONFIRMED lead vs all "
                f"competitors: {overall_confirmed}"
            )
    else:
        overall_confirmed = []

    lever_coverage: list[LeverCoverage] = []
    if levers is not None:
        lever_coverage = assess_lever_coverage(
            levers=levers,
            axis_to_lever=axis_to_lever or {},
            measured_axes=[a for a in axes_tuple if antiek.score_for(a) is not None],
        )

    return CompetitivePositionReport(
        antiek_id=antiek.product_id,
        comparisons=comparisons,
        lever_coverage=lever_coverage,
        overall_confirmed_lead_axes=tuple(overall_confirmed),
        notes=notes,
    )
