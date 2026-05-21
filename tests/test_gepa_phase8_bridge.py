"""GEPA → Phase 8 bridge tests."""

from __future__ import annotations

import uuid

from compounding.skill_growth import (
    BridgeOutcome,
    GepaToPhase8Bridge,
    PatchDecision,
    SkillPatchGate,
    bridge_gepa_result_to_phase8,
)
from tools.gepa.optimizer import GEPAResult
from tools.gepa.pareto_front import ScoreVector, Variant


def _variant(
    rubric: float = 0.8,
    verifier: float = 0.9,
    cost_penalty: float = -0.10,
    grounding: float = 0.95,
    *,
    variant_id: str | None = None,
) -> Variant:
    return Variant(
        variant_id=variant_id or f"v-{uuid.uuid4().hex[:8]}",
        prompt_text="x",
        score=ScoreVector(
            rubric_score=rubric,
            verifier_pass_rate=verifier,
            cost_penalty=cost_penalty,
            grounding_preserved=grounding,
        ),
        rationale="test",
    )


def _result(*variants: Variant) -> GEPAResult:
    return GEPAResult(
        pareto_front=list(variants),
        total_iterations=1,
        total_variants_evaluated=len(variants),
        rejected_dominated=0,
    )


# ── Empty front ────────────────────────────────────────────────────


def test_empty_front_produces_no_outcomes():
    gate = SkillPatchGate(mode="enforcing", epsilon=0.0, minimum_cohort_size=1)
    outcomes = bridge_gepa_result_to_phase8(
        gate=gate,
        result=_result(),
        baseline_score=0.5,
        cohort_size=100,
        backtest_fn=lambda v: 0.9,
    )
    assert outcomes == []


# ── Shadow mode runs every variant ──────────────────────────────────


def test_shadow_mode_runs_every_pareto_variant():
    """Per §6.4: shadow mode runs every variant to collect uniform
    calibration data."""
    gate = SkillPatchGate(mode="shadow", epsilon=0.02, minimum_cohort_size=1)
    variants = [
        _variant(rubric=0.85, verifier=0.95),
        _variant(rubric=0.80, verifier=0.92),
        _variant(rubric=0.75, verifier=0.88),
    ]
    outcomes = bridge_gepa_result_to_phase8(
        gate=gate,
        result=_result(*variants),
        baseline_score=0.5,
        cohort_size=100,
        backtest_fn=lambda v: 0.9,
    )
    assert len(outcomes) == 3
    for o in outcomes:
        assert o.patch_outcome.decision == PatchDecision.SHADOW


# ── Enforcing mode short-circuits on first ACCEPT ───────────────────


def test_enforcing_mode_stops_at_first_accept():
    """First variant in composite-preference order that beats the
    baseline + epsilon wins; subsequent variants are NOT proposed."""
    gate = SkillPatchGate(
        mode="enforcing", epsilon=0.01, minimum_cohort_size=1,
    )
    # Three variants on the front; the one with highest composite
    # score beats baseline by 0.40 → ACCEPT immediately.
    high = _variant(rubric=0.95, verifier=0.95, grounding=0.95)
    mid = _variant(rubric=0.80, verifier=0.85, grounding=0.85)
    low = _variant(rubric=0.70, verifier=0.75, grounding=0.75)
    outcomes = bridge_gepa_result_to_phase8(
        gate=gate,
        result=_result(low, mid, high),
        baseline_score=0.5,
        cohort_size=100,
        backtest_fn=lambda v: v.score.rubric_score,
    )
    assert len(outcomes) == 1
    assert outcomes[0].variant_id == high.variant_id
    assert outcomes[0].patch_outcome.decision == PatchDecision.ACCEPT


def test_enforcing_mode_keeps_looking_after_reject():
    """When the top-preferred variant fails the gate, the bridge
    keeps walking down the front until it either accepts or exhausts."""
    gate = SkillPatchGate(
        mode="enforcing", epsilon=0.05, minimum_cohort_size=1,
    )
    # The top-preferred (by composite score) variant has a poor
    # backtest score — rejected. The second variant beats baseline by
    # more than epsilon — accepted.
    top = _variant(rubric=0.95, verifier=0.95, grounding=0.95, variant_id="v-top")
    mid = _variant(rubric=0.90, verifier=0.90, grounding=0.90, variant_id="v-mid")
    backtest_table = {top.variant_id: 0.51, mid.variant_id: 0.80}

    outcomes = bridge_gepa_result_to_phase8(
        gate=gate,
        result=_result(top, mid),
        baseline_score=0.5,
        cohort_size=100,
        backtest_fn=lambda v: backtest_table[v.variant_id],
    )
    assert len(outcomes) == 2
    assert outcomes[0].variant_id == "v-top"
    assert outcomes[0].patch_outcome.decision == PatchDecision.REJECT
    assert outcomes[1].variant_id == "v-mid"
    assert outcomes[1].patch_outcome.decision == PatchDecision.ACCEPT


def test_enforcing_mode_all_rejected_returns_full_sequence():
    """When no variant on the front beats baseline+ε, the bridge
    walks every candidate and returns the full sequence of REJECTs."""
    gate = SkillPatchGate(
        mode="enforcing", epsilon=0.10, minimum_cohort_size=1,
    )
    variants = [_variant() for _ in range(3)]
    outcomes = bridge_gepa_result_to_phase8(
        gate=gate,
        result=_result(*variants),
        baseline_score=0.95,  # baseline already strong; nothing wins
        cohort_size=100,
        backtest_fn=lambda v: 0.50,
    )
    assert len(outcomes) == 3
    assert all(o.patch_outcome.decision == PatchDecision.REJECT for o in outcomes)


# ── Baseline variant exclusion ──────────────────────────────────────


def test_baseline_variant_is_skipped():
    """The current production prompt's variant is excluded so we don't
    grade the baseline against itself."""
    gate = SkillPatchGate(
        mode="enforcing", epsilon=0.01, minimum_cohort_size=1,
    )
    baseline = _variant(variant_id="v-baseline")
    challenger = _variant(variant_id="v-new", rubric=0.95)
    outcomes = bridge_gepa_result_to_phase8(
        gate=gate,
        result=_result(baseline, challenger),
        baseline_score=0.7,
        cohort_size=100,
        backtest_fn=lambda v: 0.9 if v.variant_id == "v-new" else 0.7,
        baseline_variant_id="v-baseline",
    )
    # Only v-new is evaluated.
    assert len(outcomes) == 1
    assert outcomes[0].variant_id == "v-new"


# ── Custom composite key ────────────────────────────────────────────


def test_custom_composite_key_changes_ordering():
    """Operator supplies a domain-specific composite — variants are
    walked in that order."""
    gate = SkillPatchGate(mode="enforcing", epsilon=0.01, minimum_cohort_size=1)
    # Same overall sum-of-scores; differ in cost_penalty.
    cheap = _variant(
        rubric=0.7, verifier=0.7, cost_penalty=-0.05, grounding=0.7,
        variant_id="v-cheap",
    )
    expensive = _variant(
        rubric=0.9, verifier=0.9, cost_penalty=-0.50, grounding=0.7,
        variant_id="v-expensive",
    )

    # Composite that PENALIZES cost more heavily — flips the order.
    def cost_first(s: ScoreVector) -> float:
        return s.cost_penalty * 10.0 + s.rubric_score

    backtest_table = {"v-cheap": 0.95, "v-expensive": 0.92}
    outcomes = bridge_gepa_result_to_phase8(
        gate=gate,
        result=_result(cheap, expensive),
        baseline_score=0.5,
        cohort_size=100,
        backtest_fn=lambda v: backtest_table[v.variant_id],
        composite_key=cost_first,
    )
    # cost_first puts cheap first because cost_penalty is closer to 0.
    assert outcomes[0].variant_id == "v-cheap"
