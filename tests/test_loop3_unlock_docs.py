"""Loop 3 unlock docs must track verifier substrate without unlocking RL."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "loop_3_unlock_criteria.md"


def test_loop3_unlock_doc_tracks_shipped_verifiers_without_unlocking() -> None:
    text = DOC.read_text(encoding="utf-8")
    compact = " ".join(text.split())

    assert text.count("— UNCHECKED") == 5
    assert "- [x]" not in text
    assert "Evidence verifier substrate is shipped" in text
    assert "live evidence remains absent" in text
    assert "substrate/loop_3/evidence_status.py" in text
    assert "criterion remains unchecked" in compact.lower()

    for module in (
        "compounding.verification.trajectory_volume",
        "compounding.verification.sft_readiness",
        "compounding.verification.reward_signal",
        "compounding.verification.open_weight_justification",
        "compounding.verification.eval_headroom",
    ):
        assert module in text

    assert "loop3_unlocked_by_this_probe" not in text
    assert "RL training command is issued" in text
    assert "Partial completion does not justify partial training" in text


def test_loop3_unlock_doc_does_not_preserve_stale_not_started_claims() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "**Current state:** Not started." not in text
    assert "scorer not implemented, no production emissions" not in text
    assert "No eval set, no baseline, no GEPA run, no ceiling" not in text
    assert "No argument exists." not in text
