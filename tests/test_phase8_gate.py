"""Phase 8 accept/reject gate tests (Sprint 20-21, autoresearch Wedge 2)."""

from __future__ import annotations

import pytest

from compounding.skill_growth import (
    DEFAULT_PHASE8_EPSILON,
    DEFAULT_PHASE8_MINIMUM_COHORT_SIZE,
    PHASE8_EPSILON_ENV,
    PHASE8_MINIMUM_COHORT_SIZE_ENV,
    PHASE8_MODE_ENFORCING,
    PHASE8_MODE_ENV,
    PHASE8_MODE_SHADOW,
    PatchDecision,
    SkillPatchGate,
    apply_patch_with_gate,
    phase8_gate_from_env,
    propose_skill_patch,
)


def test_shadow_mode_applies_patch_regardless():
    gate = SkillPatchGate(mode="shadow", epsilon=0.05)
    applied = []
    outcome = apply_patch_with_gate(
        gate=gate,
        baseline_backtest_score=0.5,
        candidate_backtest_score=0.4,  # would REJECT in enforcing mode
        cohort_size=100,
        apply_fn=lambda: applied.append(True),
    )
    assert outcome.decision == PatchDecision.SHADOW
    assert applied == [True]
    assert "shadow-mode" in outcome.notes


def test_enforcing_mode_rejects_below_epsilon():
    gate = SkillPatchGate(mode="enforcing", epsilon=0.05, minimum_cohort_size=10)
    applied = []
    outcome = apply_patch_with_gate(
        gate=gate,
        baseline_backtest_score=0.5,
        candidate_backtest_score=0.52,  # delta=0.02, below epsilon=0.05
        cohort_size=100,
        apply_fn=lambda: applied.append(True),
    )
    assert outcome.decision == PatchDecision.REJECT
    assert applied == []


def test_enforcing_mode_accepts_above_epsilon():
    gate = SkillPatchGate(mode="enforcing", epsilon=0.05, minimum_cohort_size=10)
    applied = []
    outcome = apply_patch_with_gate(
        gate=gate,
        baseline_backtest_score=0.5,
        candidate_backtest_score=0.7,
        cohort_size=100,
        apply_fn=lambda: applied.append(True),
    )
    assert outcome.decision == PatchDecision.ACCEPT
    assert applied == [True]


def test_enforcing_mode_rejects_below_minimum_cohort():
    """Per integration_autoresearch.md §6.3: backtest score is not
    discriminating below the architectural cohort threshold."""
    gate = SkillPatchGate(mode="enforcing", epsilon=0.01, minimum_cohort_size=50)
    applied = []
    outcome = apply_patch_with_gate(
        gate=gate,
        baseline_backtest_score=0.5,
        candidate_backtest_score=0.8,  # would normally accept
        cohort_size=10,  # below minimum
        apply_fn=lambda: applied.append(True),
    )
    assert outcome.decision == PatchDecision.REJECT
    assert applied == []
    assert "cohort_size" in outcome.notes


def test_propose_skill_patch_returns_envelope():
    envelope = propose_skill_patch(
        domain="quantum",
        proposed_skill_text="New rule: Lukin lab papers are Tier-1.",
        investigation_id="inv-x",
    )
    assert envelope["patch_id"].startswith("patch-")
    assert envelope["domain"] == "quantum"
    assert envelope["source_investigation_id"] == "inv-x"
    assert "proposed_at" in envelope


def test_shadow_mode_carries_would_be_decision():
    """Shadow mode records the WOULD-BE decision in notes so the
    calibration period can compare shadow predictions to operator
    manual review."""
    gate = SkillPatchGate(mode="shadow", epsilon=0.10)
    # Would accept in enforcing mode.
    outcome = gate.decide(
        baseline_backtest_score=0.4,
        candidate_backtest_score=0.6,
        cohort_size=100,
    )
    assert outcome.decision == PatchDecision.SHADOW
    assert "would-be-accept=True" in outcome.notes


def test_phase8_gate_from_env_defaults_to_shadow():
    gate = phase8_gate_from_env({})
    assert gate.mode == PHASE8_MODE_SHADOW
    assert gate.epsilon == DEFAULT_PHASE8_EPSILON
    assert gate.minimum_cohort_size == DEFAULT_PHASE8_MINIMUM_COHORT_SIZE


def test_phase8_gate_from_env_enables_enforcing_with_tuned_thresholds():
    gate = phase8_gate_from_env({
        PHASE8_MODE_ENV: PHASE8_MODE_ENFORCING,
        PHASE8_EPSILON_ENV: "0.075",
        PHASE8_MINIMUM_COHORT_SIZE_ENV: "12",
    })
    assert gate.mode == PHASE8_MODE_ENFORCING
    assert gate.epsilon == 0.075
    assert gate.minimum_cohort_size == 12


def test_phase8_gate_from_env_rejects_invalid_mode():
    with pytest.raises(ValueError, match="mode"):
        phase8_gate_from_env({PHASE8_MODE_ENV: "observe"})


def test_phase8_gate_from_env_rejects_invalid_numeric_values():
    with pytest.raises(ValueError, match=PHASE8_EPSILON_ENV):
        phase8_gate_from_env({PHASE8_EPSILON_ENV: "wide"})
    with pytest.raises(ValueError, match="epsilon"):
        phase8_gate_from_env({PHASE8_EPSILON_ENV: "-0.01"})
    with pytest.raises(ValueError, match=PHASE8_MINIMUM_COHORT_SIZE_ENV):
        phase8_gate_from_env({PHASE8_MINIMUM_COHORT_SIZE_ENV: "many"})
    with pytest.raises(ValueError, match="minimum_cohort_size"):
        phase8_gate_from_env({PHASE8_MINIMUM_COHORT_SIZE_ENV: "0"})
