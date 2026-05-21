"""GEPA-approved prompt variant applier tests."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from compounding.skill_growth import (
    AppliedPromptRecord,
    BridgeOutcome,
    PatchDecision,
    PatchOutcome,
    PromptApplyError,
    apply_prompt_variant,
    load_active_variant,
)


@pytest.fixture()
def base_dir():
    tmpdir = tempfile.mkdtemp(prefix="antiek-prompt-applier-")
    try:
        yield Path(tmpdir)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _outcome(
    *,
    decision: PatchDecision = PatchDecision.ACCEPT,
    variant_id: str = "gepa-synthesizer-deadbeef",
    prompt: str = "system: you are a careful synthesizer.\n",
    rationale: str = "test variant",
    baseline: float = 0.70,
    candidate: float = 0.85,
    cohort_size: int = 100,
) -> BridgeOutcome:
    return BridgeOutcome(
        variant_id=variant_id,
        variant_prompt=prompt,
        variant_rationale=rationale,
        patch_outcome=PatchOutcome(
            patch_id="patch-1",
            decision=decision,
            baseline_backtest_score=baseline,
            candidate_backtest_score=candidate,
            delta=candidate - baseline,
            epsilon_required=0.02,
            cohort_size=cohort_size,
            notes="test outcome",
        ),
    )


# ── Decision gating ────────────────────────────────────────────────


def test_refuses_to_apply_shadow_decision(base_dir):
    with pytest.raises(PromptApplyError, match="SHADOW"):
        apply_prompt_variant(
            role="synthesizer",
            bridge_outcome=_outcome(decision=PatchDecision.SHADOW),
            base_dir=base_dir,
        )


def test_refuses_to_apply_reject_decision(base_dir):
    with pytest.raises(PromptApplyError, match="REJECT"):
        apply_prompt_variant(
            role="synthesizer",
            bridge_outcome=_outcome(decision=PatchDecision.REJECT),
            base_dir=base_dir,
        )


# ── Path sanitization ──────────────────────────────────────────────


def test_rejects_unsafe_role_name(base_dir):
    with pytest.raises(PromptApplyError, match="role"):
        apply_prompt_variant(
            role="../traversal",
            bridge_outcome=_outcome(),
            base_dir=base_dir,
        )


def test_rejects_uppercase_role(base_dir):
    with pytest.raises(PromptApplyError, match="role"):
        apply_prompt_variant(
            role="Synthesizer",
            bridge_outcome=_outcome(),
            base_dir=base_dir,
        )


def test_rejects_unsafe_variant_id(base_dir):
    with pytest.raises(PromptApplyError, match="variant_id"):
        apply_prompt_variant(
            role="synthesizer",
            bridge_outcome=_outcome(variant_id="../traversal"),
            base_dir=base_dir,
        )


# ── Apply path ─────────────────────────────────────────────────────


def test_apply_writes_variant_file_and_pointer(base_dir):
    record = apply_prompt_variant(
        role="synthesizer",
        bridge_outcome=_outcome(),
        base_dir=base_dir,
    )
    assert isinstance(record, AppliedPromptRecord)
    variant_path = base_dir / "synthesizer" / "gepa-synthesizer-deadbeef.md"
    pointer_path = base_dir / "synthesizer" / "current.json"
    assert variant_path.exists()
    assert pointer_path.exists()
    text = variant_path.read_text(encoding="utf-8")
    assert "careful synthesizer" in text

    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    assert pointer["role"] == "synthesizer"
    assert pointer["variant_id"] == "gepa-synthesizer-deadbeef"
    assert pointer["baseline_backtest_score"] == 0.70
    assert pointer["candidate_backtest_score"] == 0.85
    assert abs(pointer["delta"] - 0.15) < 1e-9


def test_apply_is_idempotent_on_same_content(base_dir):
    """Re-applying the same variant_id with the same content
    succeeds; the second call is a no-op on the variant file."""
    apply_prompt_variant(
        role="synthesizer",
        bridge_outcome=_outcome(),
        base_dir=base_dir,
    )
    apply_prompt_variant(
        role="synthesizer",
        bridge_outcome=_outcome(),
        base_dir=base_dir,
    )
    variant_path = base_dir / "synthesizer" / "gepa-synthesizer-deadbeef.md"
    assert variant_path.read_text(encoding="utf-8").count("synthesizer") >= 1


def test_apply_raises_on_variant_id_content_collision(base_dir):
    """Same variant_id with different content should never happen
    under content-addressing; if it does, the applier refuses."""
    apply_prompt_variant(
        role="synthesizer",
        bridge_outcome=_outcome(prompt="version A"),
        base_dir=base_dir,
    )
    with pytest.raises(PromptApplyError, match="collision"):
        apply_prompt_variant(
            role="synthesizer",
            bridge_outcome=_outcome(prompt="version B (different content)"),
            base_dir=base_dir,
        )


def test_apply_then_new_variant_updates_pointer(base_dir):
    """Pointer file overwrites when a new variant lands."""
    apply_prompt_variant(
        role="synthesizer",
        bridge_outcome=_outcome(variant_id="gepa-synthesizer-aaaaaaaa", prompt="v1"),
        base_dir=base_dir,
    )
    apply_prompt_variant(
        role="synthesizer",
        bridge_outcome=_outcome(variant_id="gepa-synthesizer-bbbbbbbb", prompt="v2"),
        base_dir=base_dir,
    )
    pointer_path = base_dir / "synthesizer" / "current.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    assert pointer["variant_id"] == "gepa-synthesizer-bbbbbbbb"
    # Both variant files remain on disk for audit.
    assert (base_dir / "synthesizer" / "gepa-synthesizer-aaaaaaaa.md").exists()
    assert (base_dir / "synthesizer" / "gepa-synthesizer-bbbbbbbb.md").exists()


# ── Load active variant ────────────────────────────────────────────


def test_load_active_returns_none_when_no_pointer(base_dir):
    assert load_active_variant("synthesizer", base_dir=base_dir) is None


def test_load_active_returns_current_text(base_dir):
    apply_prompt_variant(
        role="synthesizer",
        bridge_outcome=_outcome(prompt="hello system prompt"),
        base_dir=base_dir,
    )
    text = load_active_variant("synthesizer", base_dir=base_dir)
    assert text == "hello system prompt"


def test_load_active_returns_latest_after_replacement(base_dir):
    apply_prompt_variant(
        role="synthesizer",
        bridge_outcome=_outcome(variant_id="gepa-synthesizer-aaaaaaaa", prompt="v1"),
        base_dir=base_dir,
    )
    apply_prompt_variant(
        role="synthesizer",
        bridge_outcome=_outcome(variant_id="gepa-synthesizer-bbbbbbbb", prompt="v2"),
        base_dir=base_dir,
    )
    assert load_active_variant("synthesizer", base_dir=base_dir) == "v2"


def test_load_active_returns_none_on_orphan_pointer(base_dir):
    """If the pointer references a missing variant file, return None
    rather than raise — degrades safely."""
    apply_prompt_variant(
        role="synthesizer",
        bridge_outcome=_outcome(),
        base_dir=base_dir,
    )
    variant_path = base_dir / "synthesizer" / "gepa-synthesizer-deadbeef.md"
    os.remove(variant_path)
    assert load_active_variant("synthesizer", base_dir=base_dir) is None
