"""ACV SPR-06 — the reuse-CONSUMING benchmark run reports a REAL negative delta.

The companion to ``test_run_mock.py`` (which proves the DEMO loop's honest null).
This drives ``run_benchmark(loop_kind="consuming")`` over the real frozen set and
asserts the headline ``token_cost_usd`` delta is strictly NEGATIVE with a CI
upper bound below zero — the warm arm genuinely does less work because the
reuse-consuming loop short-circuits the sub-questions the pack covers — WHILE the
irrelevant-vs-cold control stays flat (the §2 validity gate still holds). This is
the measurement the keystone caveat said only a reuse-consuming loop could
produce.

These run against the CONSUMING loop; ``test_run_mock.py`` / ``test_harness.py``
run against the DEMO loop. Both must hold: the demo loop's null is honest, the
consuming loop's saving is real — and neither is faked.
"""

from __future__ import annotations

import os

import pytest

from compounding.benchmark.aggregate import aggregate_comparison
from compounding.benchmark.measure import CostToResolve
from compounding.benchmark.question_set import load_question_set
from compounding.benchmark.run import run_benchmark
from compounding.benchmark.validity import (
    HEADLINE_METRIC,
    VALIDITY_VALID,
    VERDICT_COMPOUNDS,
    _dose_response_holds,
)


@pytest.fixture
def dirs(tmp_path):
    return os.path.join(tmp_path, "events"), os.path.join(tmp_path, "graphs")


def test_consuming_run_reports_strictly_negative_delta(dirs):
    """The reuse-consuming benchmark's headline token_cost_usd delta is strictly
    negative AND its bootstrap CI upper bound is below zero — a real saving beyond
    the floor, not noise and not a clamp."""
    events_dir, graphs_dir = dirs
    qs = load_question_set()
    result = run_benchmark(
        qs, events_dir=events_dir, graphs_dir=graphs_dir,
        n=3, resamples=500, loop_kind="consuming",
    )
    assert result.loop_kind == "consuming"
    token = result.headline.metric(HEADLINE_METRIC)
    assert token.delta < 0.0, f"warm must be cheaper on the consuming loop, got {token.delta}"
    assert token.ci_high < 0.0, (
        f"the CI upper bound must be below 0 (saving beyond the floor), got "
        f"[{token.ci_low}, {token.ci_high}]"
    )


def test_consuming_run_control_stays_flat(dirs):
    """The irrelevant-vs-cold control stays flat on the consuming loop (off-topic
    units share no salient tokens with the questions → cover nothing → no
    saving), so the validity gate still passes — the saving is RELEVANCE, not
    graph-presence."""
    events_dir, graphs_dir = dirs
    qs = load_question_set()
    result = run_benchmark(
        qs, events_dir=events_dir, graphs_dir=graphs_dir,
        n=3, resamples=500, loop_kind="consuming",
    )
    control = next(c for c in result.comparisons if c.label == "irrelevant_vs_cold_control")
    ctrl = control.metric(HEADLINE_METRIC)
    assert ctrl.delta == 0.0, f"the irrelevant control must stay flat, got {ctrl.delta}"
    assert result.validity == VALIDITY_VALID


def test_consuming_run_is_not_the_demo_null(dirs):
    """Sanity that the consuming loop is doing something the demo loop is NOT: the
    same run on the demo loop reports a 0 delta, the consuming loop reports < 0.
    The demo loop's null and the consuming loop's saving are BOTH true."""
    events_dir, graphs_dir = dirs
    qs = load_question_set()
    demo = run_benchmark(
        qs, events_dir=os.path.join(events_dir, "demo"),
        graphs_dir=os.path.join(graphs_dir, "demo"), n=3, resamples=300, loop_kind="demo",
    )
    consuming = run_benchmark(
        qs, events_dir=os.path.join(events_dir, "cons"),
        graphs_dir=os.path.join(graphs_dir, "cons"), n=3, resamples=300, loop_kind="consuming",
    )
    assert demo.headline.metric(HEADLINE_METRIC).delta == 0.0
    assert consuming.headline.metric(HEADLINE_METRIC).delta < 0.0


# ── ACV SPR-06 sharpen: the dose-response claim must be HONEST (no float dust) ──


def test_consuming_interpretation_does_not_falsely_claim_dose_response(dirs):
    """REGRESSION (cardinal-sin perimeter). On a consuming-MOCK run BOTH the high
    and partial arms tautologically cover every sub-question (the warm seed embeds
    the whole question), so their deltas are equal up to IEEE-754 residue — there
    is NO real dose-response gradient. The interpretation string must say so
    truthfully and must NOT claim a dose-response was demonstrated.

    This test FAILS on the pre-sharpen behavior, where ``_dose_response_holds``
    compared raw floats with a bare ``<`` and passed on dust (high −0.03 vs
    partial −0.029999999999999995), producing
    ``"flywheel demonstrated … corroborated by … dose-response"`` — a green signal
    that did not mean what it said."""
    events_dir, graphs_dir = dirs
    qs = load_question_set()
    result = run_benchmark(
        qs, events_dir=events_dir, graphs_dir=graphs_dir,
        n=5, resamples=500, loop_kind="consuming",
    )
    interp = result.headline_interpretation
    # M2's bar still met: the headline saving is real (strictly negative, CI_high<0).
    token = result.headline.metric(HEADLINE_METRIC)
    assert token.delta < 0.0 and token.ci_high < 0.0, interp

    # The verdict must NOT be COMPOUNDS (which would require a real dose-response),
    # and the string must NOT assert a demonstrated dose-response / flywheel.
    assert result.headline != VERDICT_COMPOUNDS, (
        f"a tautological consuming-mock has no dose-response gradient; it must not "
        f"verdict COMPOUNDS. interp={interp!r}"
    )
    lowered = interp.lower()
    assert "flywheel demonstrated" not in lowered, interp
    assert "corroborated by sources and dose-response" not in lowered, interp
    # And it must affirmatively report the dose-response was NOT shown.
    assert "dose-response not shown" in lowered, interp


def _delta_only(delta: float, *, ci_low: float, ci_high: float):
    """A single-point ArmComparison carrying a chosen token_cost_usd delta+CI, so
    we can exercise ``_dose_response_holds`` on the exact float-dust values the
    consuming mock produces without re-running the whole harness."""
    # warm−cold == delta is what aggregate reports; feed one warm run = cold+delta.
    cold = CostToResolve(
        token_cost_usd=0.03, input_tokens=0, output_tokens=0, sources_fetched=0,
        wall_ms=0.0, novel_insight_yield=0, redundant_rederivations=0,
    )
    warm = CostToResolve(
        token_cost_usd=0.03 + delta, input_tokens=0, output_tokens=0,
        sources_fetched=0, wall_ms=0.0, novel_insight_yield=0, redundant_rederivations=0,
    )
    cmp = aggregate_comparison("x", [warm], [cold], seed=1)
    # Overwrite the CI to the exact bounds we want to probe (n=1 ⇒ point CI anyway).
    m = cmp.metric(HEADLINE_METRIC)
    object.__setattr__(m, "ci_low", ci_low)
    object.__setattr__(m, "ci_high", ci_high)
    return cmp


def test_dose_response_holds_rejects_float_dust():
    """UNIT: the exact float-dust pair the consuming mock produces — high −0.03
    vs partial −0.029999999999999995 — must NOT register as a dose-response. The
    separation (~3e-18) is below the dust floor (1e-9), so it is NOT material.
    The pre-sharpen ``h.delta < p.delta`` bare comparison returned True here."""
    high = -0.03
    partial = -0.029999999999999995
    assert high < partial  # the bare comparison the OLD code used — passes on dust
    h_cmp = _delta_only(high, ci_low=high, ci_high=high)
    p_cmp = _delta_only(partial, ci_low=partial, ci_high=partial)
    ok, reason = _dose_response_holds(h_cmp, p_cmp, material_floor=0.0)
    assert ok is False, f"float dust must NOT pass dose-response, got: {reason}"
    assert "not shown" in reason.lower(), reason


def test_dose_response_holds_admits_real_gradient():
    """UNIT: a MATERIAL gradient (high saves a full cost-quantum more than partial)
    still passes — the fix rejects dust without weakening the genuine gate."""
    high = -0.03   # high arm saves 0.03
    partial = -0.01  # partial saves only 0.01 → high saves 0.02 MORE (≥ dust floor)
    h_cmp = _delta_only(high, ci_low=high, ci_high=high)
    p_cmp = _delta_only(partial, ci_low=partial, ci_high=partial)
    ok, reason = _dose_response_holds(h_cmp, p_cmp, material_floor=0.0)
    assert ok is True, f"a real 0.02 gradient must pass dose-response, got: {reason}"
