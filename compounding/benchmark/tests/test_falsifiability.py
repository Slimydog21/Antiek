"""AFF SPR-09 M5 + M4 non-vacuity — the falsifiability gates.

These tests prove the instrument's SCALE works regardless of the loop, by
injecting SYNTHETIC measurements directly into the aggregator + validity layer:

  * ``test_positive_delta_reported`` — warm > cold synthetic runs MUST yield a
    strictly POSITIVE reported delta (the harness does not clamp/abs/floor). If
    this failed, the benchmark could only ever report savings — a failed
    benchmark per the spec's one cardinal sin.
  * ``test_negative_delta_reported`` — warm < cold yields a strictly NEGATIVE
    delta (the flywheel-works direction is also reportable).
  * ``test_pure_noise_straddles_zero`` — warm == cold distribution → every delta
    CI straddles 0; the instrument does not manufacture signal.
  * ``test_irrelevant_seed_straddles_zero`` — a flat irrelevant control passes
    the validity gate as ``valid``.
  * ``test_irrelevant_nonzero_flags_invalid`` — a control engineered to show a
    non-zero delta past the floor flags the run ``validity: invalid`` and the
    headline is WITHHELD (the control actually gates).

The synthetic injection is the right altitude: a test that drove the reuse-blind
demo loop would only ever see delta≈0 and could not prove the scale responds to a
real warm<cold or warm>cold signal. These tests prove the response; the mock RUN
(test_run_mock.py) proves the honest demo-loop null.
"""

from __future__ import annotations

from compounding.benchmark.aggregate import aggregate_comparison
from compounding.benchmark.measure import CostToResolve
from compounding.benchmark.validity import (
    VALIDITY_INVALID,
    VALIDITY_VALID,
    VERDICT_COMPOUNDS,
    VERDICT_NEGATIVE,
    VERDICT_NOT_ASSESSED,
    VERDICT_NULL,
    decide,
)


def _cost(token: float, *, sources: int = 0, wall: float = 0.0) -> CostToResolve:
    return CostToResolve(
        token_cost_usd=token, input_tokens=0, output_tokens=0,
        sources_fetched=sources, wall_ms=wall, novel_insight_yield=0,
        redundant_rederivations=0,
    )


def _runs(values: list[float], **kw) -> list[CostToResolve]:
    return [_cost(v, **kw) for v in values]


# ── M4 non-vacuity: the delta is signed, never clamped ────────────────────────


def test_positive_delta_reported():
    """warm MORE expensive than cold → strictly POSITIVE delta. The gate that
    fails if the harness clamps to >= 0."""
    warm = _runs([0.30, 0.32, 0.31, 0.29, 0.30])
    cold = _runs([0.10, 0.11, 0.09, 0.10, 0.10])
    cmp = aggregate_comparison("warm_vs_cold", warm, cold, seed=7)
    delta = cmp.metric("token_cost_usd")
    assert delta is not None
    assert delta.delta > 0.0, "warm>cold MUST report a strictly positive delta — not clamped"
    assert delta.ci_low > 0.0, "the whole CI should be above 0 for a clean warm>cold signal"


def test_negative_delta_reported():
    """warm CHEAPER than cold (the flywheel-works direction) → strictly NEGATIVE
    delta, also reportable verbatim."""
    warm = _runs([0.10, 0.11, 0.09, 0.10, 0.10])
    cold = _runs([0.30, 0.32, 0.31, 0.29, 0.30])
    cmp = aggregate_comparison("warm_vs_cold", warm, cold, seed=7)
    delta = cmp.metric("token_cost_usd")
    assert delta.delta < 0.0
    assert delta.ci_high < 0.0


def test_pure_noise_straddles_zero():
    """warm and cold drawn from the SAME distribution → the delta CI straddles 0.
    The instrument does not manufacture signal from noise."""
    warm = _runs([0.20, 0.22, 0.18, 0.21, 0.19, 0.20, 0.205])
    cold = _runs([0.21, 0.19, 0.205, 0.20, 0.215, 0.195, 0.20])
    cmp = aggregate_comparison("warm_vs_cold", warm, cold, seed=11)
    delta = cmp.metric("token_cost_usd")
    assert delta.straddles_zero, f"noise must straddle 0, got [{delta.ci_low},{delta.ci_high}]"


def test_same_seed_reproduces_same_delta():
    """Deterministic seeding (M4): identical inputs + seed → identical delta and
    CI bounds across runs."""
    warm = _runs([0.30, 0.25, 0.35, 0.28, 0.31, 0.27])
    cold = _runs([0.10, 0.12, 0.09, 0.11, 0.10, 0.13])
    a = aggregate_comparison("c", warm, cold, seed=42).metric("token_cost_usd")
    b = aggregate_comparison("c", warm, cold, seed=42).metric("token_cost_usd")
    assert (a.delta, a.ci_low, a.ci_high) == (b.delta, b.ci_low, b.ci_high)


def test_wider_variance_widens_ci():
    """Rigor: the CI is computed from the runs, not hard-coded — more spread in
    the per-run diffs widens the interval."""
    cold = _runs([0.10] * 8)
    tight = aggregate_comparison("t", _runs([0.20, 0.21, 0.19, 0.20, 0.205, 0.195, 0.20, 0.20]), cold, seed=3)
    wide = aggregate_comparison("w", _runs([0.40, 0.05, 0.35, 0.02, 0.38, 0.01, 0.30, 0.10]), cold, seed=3)
    assert wide.metric("token_cost_usd").ci_half_width > tight.metric("token_cost_usd").ci_half_width


# ── M5 validity control: flat passes, spike invalidates ───────────────────────


def _flat_control():
    base = _runs([0.20, 0.21, 0.19, 0.20, 0.205, 0.195])
    return aggregate_comparison("irrelevant_vs_cold", base, base, seed=5)


def test_irrelevant_seed_straddles_zero():
    """The irrelevant-seed arm (same as cold) → control delta CI straddles 0 →
    validity gate passes as ``valid``."""
    control = _flat_control()
    headline = aggregate_comparison(
        "warm_vs_cold",
        _runs([0.10, 0.11, 0.09, 0.10, 0.10, 0.105]),
        _runs([0.20, 0.21, 0.19, 0.20, 0.205, 0.195]),
        seed=5,
    )
    partial = aggregate_comparison(
        "partial",
        _runs([0.16, 0.17, 0.15, 0.16, 0.165, 0.155]),
        _runs([0.20, 0.21, 0.19, 0.20, 0.205, 0.195]),
        seed=5,
    )
    v = decide(
        headline=headline, control=control,
        control_tolerance=0.05, material_floor=0.02, partial=partial,
        control_per_domain_points=[0.0, 0.001, -0.001, 0.0],
    )
    assert v.validity == VALIDITY_VALID, v.validity_reason


def test_irrelevant_nonzero_flags_invalid():
    """SEED-AND-CATCH: inject an irrelevant control engineered to show a non-zero
    delta past the floor → the run is flagged ``validity: invalid`` and the
    headline is WITHHELD. Proves the control actually gates (M5)."""
    # Irrelevant arm is much cheaper than cold even though it is OFF-TOPIC — the
    # instrument is responding to graph-presence, not relevance.
    control = aggregate_comparison(
        "irrelevant_vs_cold",
        _runs([0.10, 0.11, 0.09, 0.10, 0.10, 0.105]),   # irrelevant
        _runs([0.30, 0.31, 0.29, 0.30, 0.305, 0.295]),   # cold
        seed=5,
    )
    headline = aggregate_comparison(
        "warm_vs_cold",
        _runs([0.08, 0.09, 0.07, 0.08, 0.085, 0.075]),
        _runs([0.30, 0.31, 0.29, 0.30, 0.305, 0.295]),
        seed=5,
    )
    v = decide(
        headline=headline, control=control,
        control_tolerance=0.02, material_floor=0.05,
    )
    assert v.validity == VALIDITY_INVALID, "a non-zero control MUST invalidate"
    assert v.headline == VERDICT_NOT_ASSESSED, "the headline MUST be withheld when invalid"


def test_single_control_domain_spike_invalidates():
    """§2: a single control domain spiking past the floor while the pooled CI
    straddles 0 still invalidates (pooled flatness can mask one response)."""
    control = _flat_control()  # pooled straddles 0
    headline = aggregate_comparison(
        "warm_vs_cold",
        _runs([0.10] * 6), _runs([0.20] * 6), seed=5,
    )
    v = decide(
        headline=headline, control=control,
        control_tolerance=0.05, material_floor=0.03,
        control_per_domain_points=[0.0, 0.10, 0.0, 0.0],  # one domain spikes 0.10 > floor 0.03
    )
    assert v.validity == VALIDITY_INVALID
    assert v.headline == VERDICT_NOT_ASSESSED


def test_underpowered_when_control_ci_too_wide():
    """§2: a control CI that straddles 0 only because it is NOISY (half-width >
    tolerance) is ``underpowered``, NOT ``valid`` — widen n."""
    control = aggregate_comparison(
        "irrelevant_vs_cold",
        _runs([0.50, 0.01, 0.45, 0.02, 0.40, 0.05]),   # huge spread
        _runs([0.20, 0.20, 0.20, 0.20, 0.20, 0.20]),
        seed=5,
    )
    headline = aggregate_comparison("warm_vs_cold", _runs([0.10] * 6), _runs([0.20] * 6), seed=5)
    v = decide(headline=headline, control=control, control_tolerance=0.01, material_floor=0.05)
    assert v.validity == "underpowered", v.validity_reason
    assert v.headline == VERDICT_NOT_ASSESSED


# ── M5 headline verdicts (only when valid) ────────────────────────────────────


def test_valid_compounds_requires_dose_response():
    """A clean warm<cold headline with a flat control, corroborating sources, AND
    a load-bearing dose-response (high saves more than partial) → ``compounds``."""
    cold = _runs([0.30] * 8, sources=10)
    control = aggregate_comparison("irrelevant_vs_cold", _runs([0.30] * 8, sources=10), cold, seed=9)
    headline = aggregate_comparison("warm_vs_cold", _runs([0.10] * 8, sources=4), cold, seed=9)
    partial = aggregate_comparison("partial", _runs([0.22] * 8, sources=7), cold, seed=9)
    v = decide(
        headline=headline, control=control,
        control_tolerance=0.01, material_floor=0.05, partial=partial,
    )
    assert v.validity == VALIDITY_VALID
    assert v.headline == VERDICT_COMPOUNDS, v.headline_reason


def test_valid_but_no_dose_response_is_null():
    """warm<cold but high-overlap does NOT save more than partial (dose-response
    fails) → ``null``, not ``compounds`` — relevance must out-perform partial."""
    cold = _runs([0.30] * 8, sources=10)
    control = aggregate_comparison("irrelevant_vs_cold", _runs([0.30] * 8, sources=10), cold, seed=9)
    headline = aggregate_comparison("warm_vs_cold", _runs([0.20] * 8, sources=4), cold, seed=9)
    # partial saves MORE than high-overlap — dose-response inverted.
    partial = aggregate_comparison("partial", _runs([0.10] * 8, sources=7), cold, seed=9)
    v = decide(
        headline=headline, control=control,
        control_tolerance=0.01, material_floor=0.05, partial=partial,
    )
    assert v.validity == VALIDITY_VALID
    assert v.headline == VERDICT_NULL, v.headline_reason


def test_valid_negative_when_warm_more_expensive():
    """A flat control + a headline whose CI is entirely ABOVE 0 → ``negative``
    (warm more expensive; flywheel falsified) — the positive number is emitted."""
    cold = _runs([0.10] * 8)
    control = aggregate_comparison("irrelevant_vs_cold", _runs([0.10] * 8), cold, seed=9)
    headline = aggregate_comparison("warm_vs_cold", _runs([0.30] * 8), cold, seed=9)
    v = decide(headline=headline, control=control, control_tolerance=0.01, material_floor=0.05)
    assert v.validity == VALIDITY_VALID
    assert v.headline == VERDICT_NEGATIVE, v.headline_reason
