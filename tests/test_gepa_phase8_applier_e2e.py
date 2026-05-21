"""GEPA → Phase 8 gate → prompt applier end-to-end integration test.

Drives a complete chain:
  GEPAResult (Pareto front of prompt variants)
    → GepaToPhase8Bridge sorts + walks them through SkillPatchGate
    → ACCEPTED variants land on disk via apply_prompt_variant
    → load_active_variant returns the latest applied text

Confirms the compounding loop's substrate-side artifacts are
consistent: when the bridge accepts, the file shows up; when the
bridge rejects, no file lands; when shadow mode runs, the
calibration data is collected but no file is applied.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from compounding.skill_growth import (
    PatchDecision,
    PromptApplyError,
    SkillPatchGate,
    apply_prompt_variant,
    bridge_gepa_result_to_phase8,
    load_active_variant,
)
from tools.gepa.optimizer import GEPAResult
from tools.gepa.pareto_front import ScoreVector, Variant


@pytest.fixture()
def base_dir():
    tmpdir = tempfile.mkdtemp(prefix="antiek-gepa-e2e-")
    try:
        yield Path(tmpdir)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _variant(
    *,
    variant_id: str,
    prompt: str,
    rubric: float = 0.8,
    verifier: float = 0.9,
    cost_penalty: float = -0.10,
    grounding: float = 0.95,
) -> Variant:
    return Variant(
        variant_id=variant_id,
        prompt_text=prompt,
        score=ScoreVector(
            rubric_score=rubric,
            verifier_pass_rate=verifier,
            cost_penalty=cost_penalty,
            grounding_preserved=grounding,
        ),
        rationale="e2e test variant",
    )


def _result(*variants: Variant) -> GEPAResult:
    return GEPAResult(
        pareto_front=list(variants),
        total_iterations=1,
        total_variants_evaluated=len(variants),
        rejected_dominated=0,
    )


# ── ACCEPT → file lands + pointer updates ─────────────────────────


def test_e2e_accept_lands_variant_on_disk(base_dir):
    """Bridge accepts the highest-composite variant; applier writes
    the file + pointer; load_active_variant returns it."""
    gate = SkillPatchGate(
        mode="enforcing", epsilon=0.02, minimum_cohort_size=10,
    )
    high = _variant(
        variant_id="gepa-synthesizer-aaaa1111",
        prompt="SYSTEM: you are a precise synthesizer.",
        rubric=0.95, verifier=0.97,
    )
    mid = _variant(
        variant_id="gepa-synthesizer-bbbb2222",
        prompt="SYSTEM: alt phrasing.",
        rubric=0.80, verifier=0.85,
    )
    backtest_table = {
        high.variant_id: 0.95,
        mid.variant_id: 0.55,
    }
    outcomes = bridge_gepa_result_to_phase8(
        gate=gate,
        result=_result(high, mid),
        baseline_score=0.5,
        cohort_size=50,
        backtest_fn=lambda v: backtest_table[v.variant_id],
    )
    # Enforcing mode short-circuits on first ACCEPT.
    assert len(outcomes) == 1
    assert outcomes[0].patch_outcome.decision == PatchDecision.ACCEPT
    assert outcomes[0].variant_id == high.variant_id

    # Applier lands the variant.
    record = apply_prompt_variant(
        role="synthesizer",
        bridge_outcome=outcomes[0],
        base_dir=base_dir,
    )
    assert record.variant_id == high.variant_id

    # Pointer round-trips.
    pointer_path = base_dir / "synthesizer" / "current.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    assert pointer["variant_id"] == high.variant_id
    assert pointer["candidate_backtest_score"] == 0.95

    # load_active_variant returns the prompt text.
    active = load_active_variant("synthesizer", base_dir=base_dir)
    assert active == "SYSTEM: you are a precise synthesizer."


# ── All-REJECT → no file lands ─────────────────────────────────────


def test_e2e_all_reject_lands_nothing(base_dir):
    """If every variant fails the gate, the applier refuses each
    one and no file ever appears on disk."""
    gate = SkillPatchGate(
        mode="enforcing", epsilon=0.10, minimum_cohort_size=1,
    )
    variants = [
        _variant(
            variant_id=f"gepa-synthesizer-{i:04x}{i:04x}",
            prompt=f"variant {i}",
        )
        for i in range(3)
    ]
    outcomes = bridge_gepa_result_to_phase8(
        gate=gate,
        result=_result(*variants),
        baseline_score=0.95,
        cohort_size=50,
        backtest_fn=lambda v: 0.5,
    )
    assert all(
        o.patch_outcome.decision == PatchDecision.REJECT for o in outcomes
    )
    for o in outcomes:
        with pytest.raises(PromptApplyError, match="REJECT"):
            apply_prompt_variant(
                role="synthesizer",
                bridge_outcome=o,
                base_dir=base_dir,
            )
    # Nothing landed — no synthesizer dir on disk.
    assert not (base_dir / "synthesizer").exists()
    assert load_active_variant("synthesizer", base_dir=base_dir) is None


# ── Shadow mode → outcomes recorded but applier refuses ─────────


def test_e2e_shadow_mode_records_but_does_not_apply(base_dir):
    """Shadow mode runs every variant; outcomes are SHADOW-marked;
    the applier refuses SHADOW decisions (only ACCEPT lands)."""
    gate = SkillPatchGate(
        mode="shadow", epsilon=0.02, minimum_cohort_size=1,
    )
    variants = [
        _variant(
            variant_id=f"gepa-synthesizer-cccc{i:04x}",
            prompt=f"shadow variant {i}",
        )
        for i in range(3)
    ]
    outcomes = bridge_gepa_result_to_phase8(
        gate=gate,
        result=_result(*variants),
        baseline_score=0.5,
        cohort_size=50,
        backtest_fn=lambda v: 0.9,
    )
    # Shadow walks every variant.
    assert len(outcomes) == 3
    for o in outcomes:
        assert o.patch_outcome.decision == PatchDecision.SHADOW

    # Applier refuses every shadow outcome.
    for o in outcomes:
        with pytest.raises(PromptApplyError, match="SHADOW"):
            apply_prompt_variant(
                role="synthesizer",
                bridge_outcome=o,
                base_dir=base_dir,
            )
    assert load_active_variant("synthesizer", base_dir=base_dir) is None


# ── Re-run after ACCEPT → second accepted variant replaces pointer ─


def test_e2e_sequential_accepts_update_pointer(base_dir):
    """Two sequential bridge runs, each landing a different
    accepted variant: the pointer reflects the latest applied
    variant while both variant files remain for audit."""
    gate = SkillPatchGate(
        mode="enforcing", epsilon=0.02, minimum_cohort_size=1,
    )

    # First run.
    v1 = _variant(
        variant_id="gepa-synthesizer-dddd0001",
        prompt="version 1 system prompt",
    )
    out1 = bridge_gepa_result_to_phase8(
        gate=gate,
        result=_result(v1),
        baseline_score=0.5,
        cohort_size=10,
        backtest_fn=lambda v: 0.95,
    )[0]
    apply_prompt_variant(
        role="synthesizer", bridge_outcome=out1, base_dir=base_dir,
    )
    assert load_active_variant("synthesizer", base_dir=base_dir) == (
        "version 1 system prompt"
    )

    # Second run with a different variant.
    v2 = _variant(
        variant_id="gepa-synthesizer-dddd0002",
        prompt="version 2 — improved",
    )
    out2 = bridge_gepa_result_to_phase8(
        gate=gate,
        result=_result(v2),
        baseline_score=0.5,
        cohort_size=10,
        backtest_fn=lambda v: 0.96,
    )[0]
    apply_prompt_variant(
        role="synthesizer", bridge_outcome=out2, base_dir=base_dir,
    )

    # Pointer reflects the second; both files still on disk for audit.
    assert load_active_variant("synthesizer", base_dir=base_dir) == (
        "version 2 — improved"
    )
    assert (base_dir / "synthesizer" / "gepa-synthesizer-dddd0001.md").exists()
    assert (base_dir / "synthesizer" / "gepa-synthesizer-dddd0002.md").exists()
