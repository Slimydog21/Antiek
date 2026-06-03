"""AFF SPR-09 M5 — the validity control + the 5-state verdict.

The falsifiability machinery. The irrelevant-seed arm (graph-size control: SAME
node count as warm, off-topic) is how we honour the skeptic who says "any
warm−cold gap is just graph-non-emptiness or run variance, not real
compounding." If the instrument measures RELEVANCE — not graph-presence or noise
— the irrelevant arm's delta must be statistically indistinguishable from zero.
If it isn't, the run is ``invalid`` and the warm−cold result is NOT reported as a
flywheel finding (M5). The control must be able to invalidate the headline; if it
can't, the benchmark only flatters the loop.

§2 5-state verdict, validity-gate-FIRST:

  VALIDITY (computed first, on the control comparison):
    * ``invalid``                 — the pooled control delta CI does NOT straddle
                                    0 within ``control_tolerance``, OR any single
                                    control domain's |point| exceeds the material
                                    floor while others are flat. Reporting STOPS.
    * ``underpowered``            — control CI straddles 0 but its half-width >
                                    ``control_tolerance`` (a wide CI straddles 0
                                    because it is NOISY, masking a real
                                    bigger-graph effect). Widen n; do NOT report
                                    "valid/flat".
    * (valid)                     — control straddles 0 AND half-width ≤ tolerance.

  HEADLINE (only if valid; over the high-overlap pooled cell):
    * ``valid_compounds``         — headline ``token_cost_usd`` CI_high < 0 AND
                                    |point| ≥ ``material_floor`` AND
                                    ``sources_fetched`` CI_high ≤ 0 AND the
                                    load-bearing dose-response holds (high-overlap
                                    saves more than partial, non-overlapping CIs).
    * ``null``                    — headline CI straddles 0, or |point| below the
                                    floor. Reported verbatim; NOT re-rolled.
    * ``negative``                — headline CI_low > 0 (warm MORE expensive). A
                                    legitimate falsification.

The headline verdict is reported verbatim — there is no path here that re-runs,
re-seeds, or inflates n to chase a sign. That is the cardinal sin this module
exists to make impossible.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .result_schema import ArmComparison

# Validity states (the gate).
VALIDITY_INVALID = "invalid"
VALIDITY_UNDERPOWERED = "underpowered"
VALIDITY_VALID = "valid"

# Headline verdicts (only meaningful when validity == valid).
VERDICT_COMPOUNDS = "valid_compounds"
VERDICT_NULL = "null"
VERDICT_NEGATIVE = "negative"
VERDICT_NOT_ASSESSED = "not_assessed"  # validity gate failed; headline withheld

HEADLINE_METRIC = "token_cost_usd"
CORROBORATING_METRIC = "sources_fetched"

# Dose-response anti-dust floor (ACV SPR-06 sharpen). The load-bearing
# dose-response ("high-overlap saves MATERIALLY more than partial") must reject a
# non-existent gradient that only LOOKS ordered because of IEEE-754 residue from
# summing a different count of identical per-step costs. The smallest REAL saving
# the cost model can produce is one skipped browse step. SOURCE: the consuming
# loop charges ``DEFAULT_COST_PER_STEP_USD = 0.01`` per uncovered sub-question
# (runtime/research_runner/browse_loop.py:104). One fewer covered step therefore
# moves a delta by ≥0.01; float dust moves it by ~1e-15. A separation floor an
# order of magnitude below one cost-quantum (0.01) but many orders ABOVE float
# dust cleanly admits any real one-step gradient while rejecting the residue.
# When a positive ``material_floor`` is in force we require the STRONGER of the
# two (the material bar that already defines "material" for the headline).
_DOSE_RESPONSE_DUST_FLOOR = 1e-9


@dataclass(frozen=True)
class ValidityReport:
    """The validity gate's verdict + why. ``per_domain_breaches`` names any
    single control domain whose |point| exceeded the material floor (the §2
    'one domain spikes while others are flat' invalidation)."""

    state: str
    reason: str
    control_straddles_zero: bool
    control_ci_half_width: float


@dataclass(frozen=True)
class Verdict:
    """The full 5-state outcome: the validity gate, then the headline verdict
    (withheld unless valid). ``interpretation`` is the one-line human reading the
    artifact carries."""

    validity: str
    headline: str
    interpretation: str
    validity_reason: str
    headline_reason: str


def assess_validity(
    control: ArmComparison,
    *,
    control_tolerance: float,
    material_floor: float,
    per_domain_points: Sequence[float] | None = None,
) -> ValidityReport:
    """Run the validity gate on the irrelevant-vs-cold control comparison.

    ``control_tolerance`` is the half-width band the control's headline-metric CI
    must (a) straddle 0 within and (b) be no wider than. ``per_domain_points``
    optionally carries each control domain's individual point delta so a single
    spiking domain invalidates even when the pooled CI straddles 0."""
    headline = control.metric(HEADLINE_METRIC)
    if headline is None:
        return ValidityReport(
            state=VALIDITY_INVALID,
            reason=f"control comparison has no {HEADLINE_METRIC} metric",
            control_straddles_zero=False,
            control_ci_half_width=0.0,
        )

    half = headline.ci_half_width
    straddles = headline.straddles_zero

    # A single control domain spiking past the material floor while others are
    # flat invalidates the instrument (§2): pooled flatness can mask one
    # graph-presence response. Only a POSITIVE floor can be breached — with
    # floor=0 (the zero-variance mock default) a flat 0 domain is not a spike.
    if per_domain_points and material_floor > 0.0:
        breaches = [p for p in per_domain_points if abs(p) >= material_floor]
        if breaches:
            return ValidityReport(
                state=VALIDITY_INVALID,
                reason=(
                    f"a control domain's |delta| {max(abs(p) for p in breaches):.6g} "
                    f">= material_floor {material_floor:.6g} — the instrument responds "
                    f"to graph-presence, not relevance"
                ),
                control_straddles_zero=straddles,
                control_ci_half_width=half,
            )

    if not straddles:
        return ValidityReport(
            state=VALIDITY_INVALID,
            reason=(
                f"control {HEADLINE_METRIC} CI [{headline.ci_low:.6g}, "
                f"{headline.ci_high:.6g}] does not straddle 0 — the instrument "
                f"measures graph-presence/noise, not relevance"
            ),
            control_straddles_zero=False,
            control_ci_half_width=half,
        )

    if half > control_tolerance:
        return ValidityReport(
            state=VALIDITY_UNDERPOWERED,
            reason=(
                f"control CI half-width {half:.6g} > tolerance {control_tolerance:.6g} "
                f"— the CI straddles 0 because it is noisy; widen n before trusting "
                f"a flat control"
            ),
            control_straddles_zero=True,
            control_ci_half_width=half,
        )

    return ValidityReport(
        state=VALIDITY_VALID,
        reason=(
            f"control {HEADLINE_METRIC} CI straddles 0 within tolerance "
            f"(half-width {half:.6g} <= {control_tolerance:.6g})"
        ),
        control_straddles_zero=True,
        control_ci_half_width=half,
    )


def assess_headline(
    headline: ArmComparison,
    *,
    material_floor: float,
    partial: ArmComparison | None = None,
) -> tuple[str, str]:
    """The headline verdict, assuming validity already passed. Returns
    ``(verdict, reason)``."""
    token = headline.metric(HEADLINE_METRIC)
    if token is None:
        return VERDICT_NULL, f"no {HEADLINE_METRIC} metric on the headline comparison"

    # NEGATIVE: warm strictly more expensive (CI entirely above 0).
    if token.ci_low > 0.0:
        return VERDICT_NEGATIVE, (
            f"headline {HEADLINE_METRIC} CI [{token.ci_low:.6g}, {token.ci_high:.6g}] "
            f"> 0 — warm is MORE expensive (flywheel falsified on this loop)"
        )

    # COMPOUNDS: CI entirely below 0, magnitude clears the floor, corroborated by
    # sources, and the dose-response holds.
    compounds = (
        token.ci_high < 0.0
        and abs(token.delta) >= material_floor
    )
    if compounds:
        sources = headline.metric(CORROBORATING_METRIC)
        sources_ok = sources is None or sources.ci_high <= 0.0
        dose_ok, dose_reason = _dose_response_holds(
            headline, partial, material_floor=material_floor
        )
        if sources_ok and dose_ok:
            return VERDICT_COMPOUNDS, (
                f"headline {HEADLINE_METRIC} CI_high {token.ci_high:.6g} < 0, "
                f"|delta| {abs(token.delta):.6g} >= floor {material_floor:.6g}, "
                f"corroborated by sources and dose-response"
            )
        # Below-the-bar-but-cheaper falls through to NULL with the honest reason.
        if not sources_ok:
            return VERDICT_NULL, (
                f"headline cost cheaper but {CORROBORATING_METRIC} CI_high "
                f"{sources.ci_high:.6g} > 0 — savings not corroborated"
            )
        return VERDICT_NULL, dose_reason

    return VERDICT_NULL, (
        f"headline {HEADLINE_METRIC} CI [{token.ci_low:.6g}, {token.ci_high:.6g}] "
        f"straddles 0 or |delta| {abs(token.delta):.6g} below floor "
        f"{material_floor:.6g} — no material compounding shown"
    )


def _dose_response_holds(
    headline: ArmComparison,
    partial: ArmComparison | None,
    *,
    material_floor: float,
) -> tuple[bool, str]:
    """Load-bearing dose-response (§2): high-overlap must save MATERIALLY more than
    partial, with non-overlapping CIs (relevance produces more savings than
    partial, which beats control). When no partial comparison is supplied,
    dose-response is not assessable and is treated as not-holding with an honest
    reason.

    The separation is MATERIAL, not merely ordered: ``partial.delta − high.delta``
    (how much MORE the high arm saves) must clear ``separation_floor`` =
    ``max(material_floor, _DOSE_RESPONSE_DUST_FLOOR)``. This is the ACV SPR-06
    sharpen-round correctness fix: a bare ``high.delta < partial.delta`` on raw
    floats passed on IEEE-754 dust (e.g. high −0.03 vs partial
    −0.029999999999999995 — the same number summed a different count of times),
    falsely certifying a dose-response where BOTH arms covered every sub-question
    and the gradient was zero. Requiring a separation that clears one cost-quantum
    (or the operator's material floor) means a non-existent gradient does NOT
    pass, so the interpretation string becomes honest as a CONSEQUENCE."""
    if partial is None:
        return False, "dose-response not assessable (no partial-overlap comparison supplied)"
    h = headline.metric(HEADLINE_METRIC)
    p = partial.metric(HEADLINE_METRIC)
    if h is None or p is None:
        return False, "dose-response not assessable (missing metric)"
    # More negative delta = more savings. The high arm must save MATERIALLY more
    # than partial (separation clears the floor) AND its CI must not overlap
    # partial's. ``material_floor`` is the operator-ratified material bar; when it
    # is 0 (the mock default) the dust floor still rejects float residue.
    separation = p.delta - h.delta  # how much MORE the high arm saves; >0 ⇒ ordered
    separation_floor = max(material_floor, _DOSE_RESPONSE_DUST_FLOOR)
    more_savings = separation >= separation_floor
    non_overlapping = h.ci_high < p.ci_low
    if more_savings and non_overlapping:
        return True, (
            f"dose-response holds (high-overlap saves {separation:.6g} more than "
            f"partial >= floor {separation_floor:.6g}, non-overlapping CIs)"
        )
    if not more_savings:
        return False, (
            f"dose-response NOT shown (high {h.delta:.6g} vs partial {p.delta:.6g}; "
            f"separation {separation:.6g} < floor {separation_floor:.6g} — no "
            f"material gradient, not just float dust)"
        )
    return False, (
        f"dose-response NOT shown (high {h.delta:.6g} vs partial {p.delta:.6g}; "
        f"CIs overlap)"
    )


def decide(
    *,
    headline: ArmComparison,
    control: ArmComparison,
    control_tolerance: float,
    material_floor: float,
    partial: ArmComparison | None = None,
    control_per_domain_points: Sequence[float] | None = None,
) -> Verdict:
    """The full validity-gate-FIRST 5-state decision (§2).

    Validity is assessed on the control comparison FIRST. Only if valid is the
    headline verdict assessed; otherwise the headline is withheld
    (``not_assessed``) and the interpretation says the instrument failed its own
    validity check — the warm−cold number is not reported as a flywheel finding."""
    vr = assess_validity(
        control,
        control_tolerance=control_tolerance,
        material_floor=material_floor,
        per_domain_points=control_per_domain_points,
    )

    if vr.state != VALIDITY_VALID:
        interp = (
            f"VALIDITY {vr.state.upper()}: {vr.reason}. Headline warm−cold withheld "
            f"— not reported as a flywheel finding."
        )
        return Verdict(
            validity=vr.state,
            headline=VERDICT_NOT_ASSESSED,
            interpretation=interp,
            validity_reason=vr.reason,
            headline_reason="withheld — validity gate did not pass",
        )

    verdict, reason = assess_headline(
        headline, material_floor=material_floor, partial=partial,
    )
    # NULL has two honestly-distinct shapes: (a) the headline cost itself did not
    # clear the floor (no material saving at all), and (b) the headline cost IS
    # materially cheaper (warm cheaper, Δ<0 below floor) but the load-bearing
    # dose-response did NOT hold. Case (b) must NOT read "no material compounding"
    # — that would understate a real saving; and it must NOT read "dose-response
    # demonstrated" — that is the float-dust lie this sharpen round kills. The
    # token metric tells us which shape we are in.
    token = headline.metric(HEADLINE_METRIC)
    headline_cheaper_below_floor = (
        token is not None and token.ci_high < 0.0 and abs(token.delta) >= material_floor
    )
    null_label = (
        "warm cheaper (Δ<0) but compounds bar NOT met — verdict null (the headline "
        "saving is real; see reason for what was not corroborated)"
        if headline_cheaper_below_floor
        else "null — no material compounding shown (reported verbatim)"
    )
    interp_map = {
        VERDICT_COMPOUNDS: "flywheel demonstrated (warm cheaper, Δ<0)",
        VERDICT_NULL: null_label,
        VERDICT_NEGATIVE: "warm MORE expensive (Δ>0) — flywheel falsified on this loop",
    }
    interpretation = f"VALID; {interp_map.get(verdict, verdict)}: {reason}"
    return Verdict(
        validity=VALIDITY_VALID,
        headline=verdict,
        interpretation=interpretation,
        validity_reason=vr.reason,
        headline_reason=reason,
    )
