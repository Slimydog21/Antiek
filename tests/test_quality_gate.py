"""Quality gate tests (master-spec §13.9, Sprint 19)."""

from __future__ import annotations

from compounding.quality_gate import (
    QualityGate,
    QualityGateReason,
    SourceTierResult,
    VerificationResult,
    VoiceStyleResult,
    evaluate_notebook_for_public,
)

# ── Component verdicts ──────────────────────────────────────────────


def test_verification_passes_above_threshold():
    gate = QualityGate(verification_threshold=0.6)
    v = VerificationResult(score=0.75, threshold=0.6, passed=True)
    vs = VoiceStyleResult(0.0, 0, 1.0, passed=True)
    st = SourceTierResult(1, 0.8, passed=True)
    verdict = gate.evaluate(verification=v, voice_style=vs, source_tier=st)
    assert verdict.accepted is True


def test_verification_fail_blocks_promotion():
    gate = QualityGate()
    v = VerificationResult(score=0.4, threshold=0.6, passed=False)
    vs = VoiceStyleResult(0.0, 0, 1.0, passed=True)
    st = SourceTierResult(1, 0.8, passed=True)
    verdict = gate.evaluate(verification=v, voice_style=vs, source_tier=st)
    assert verdict.accepted is False
    assert QualityGateReason.VERIFICATION_FAILED in verdict.reasons


def test_voice_style_fail_blocks_promotion():
    gate = QualityGate()
    v = VerificationResult(0.8, 0.6, passed=True)
    vs = VoiceStyleResult(20.0, 5, 0.05, passed=False)  # slop indicators high
    st = SourceTierResult(1, 0.8, passed=True)
    verdict = gate.evaluate(verification=v, voice_style=vs, source_tier=st)
    assert verdict.accepted is False
    assert QualityGateReason.VOICE_STYLE_FAILED in verdict.reasons


def test_source_tier_fail_blocks_promotion():
    """Per master-spec §13.9: contributions citing only Tier-4/5
    sources are routed to private (not public-graph)."""
    gate = QualityGate()
    v = VerificationResult(0.8, 0.6, passed=True)
    vs = VoiceStyleResult(0.0, 0, 1.0, passed=True)
    st = SourceTierResult(4, 0.0, passed=False)
    verdict = gate.evaluate(verification=v, voice_style=vs, source_tier=st)
    assert verdict.accepted is False
    assert QualityGateReason.SOURCE_TIER_TOO_LOW in verdict.reasons


def test_all_three_must_pass_for_acceptance():
    """AND-discipline: passing 2 of 3 is NOT acceptance per §13.9."""
    gate = QualityGate()
    v = VerificationResult(0.8, 0.6, passed=True)
    vs = VoiceStyleResult(0.0, 0, 1.0, passed=True)
    st = SourceTierResult(5, 0.0, passed=False)  # fail
    verdict = gate.evaluate(verification=v, voice_style=vs, source_tier=st)
    assert verdict.accepted is False


# ── End-to-end evaluation ───────────────────────────────────────────


def test_evaluate_notebook_passes_clean_high_quality():
    """Clean prose, Tier-1 citations, decent rubric score."""
    text = (
        "Neutral-atom platforms have demonstrated single-qubit gate "
        "error rates below 10⁻³ at 100-qubit scale. The cross-comparison "
        "with trapped-ion systems shows similar performance at "
        "operational depth though with longer gate times."
    )
    verdict = evaluate_notebook_for_public(
        text_content=text,
        cited_chunk_tiers=[1, 1, 2, 2],
        corpus_sector_terms=["neutral-atom", "trapped-ion", "gate error", "qubit"],
        rubric_score=0.85,
    )
    assert verdict.accepted is True


def test_evaluate_notebook_rejects_slop():
    """LLM-slop prose triggers the voice-style failure."""
    text = (
        "It is important to note that neutral-atom platforms—indeed—have "
        "demonstrated—single—qubit gate—error rates—below 10⁻³. Furthermore, "
        "it is worth noting that the cross-comparison—indeed—shows similar "
        "performance. Additionally, it can be argued that the data is robust."
    )
    verdict = evaluate_notebook_for_public(
        text_content=text,
        cited_chunk_tiers=[1, 2],
        corpus_sector_terms=["neutral-atom"],
        rubric_score=0.85,
    )
    assert verdict.accepted is False
    assert QualityGateReason.VOICE_STYLE_FAILED in verdict.reasons


def test_evaluate_notebook_rejects_low_tier_only():
    """Contribution citing only Tier-4/5 sources is rejected."""
    text = "Clean prose with no slop patterns and reasonable sector vocab."
    verdict = evaluate_notebook_for_public(
        text_content=text,
        cited_chunk_tiers=[4, 5, 5, 4],
        corpus_sector_terms=[],
        rubric_score=0.85,
    )
    assert verdict.accepted is False
    assert QualityGateReason.SOURCE_TIER_TOO_LOW in verdict.reasons


def test_evaluate_notebook_rejects_no_citations():
    """A public-graph contribution must cite sources."""
    text = "Clean prose but no citations."
    verdict = evaluate_notebook_for_public(
        text_content=text,
        cited_chunk_tiers=[],
        corpus_sector_terms=[],
        rubric_score=0.85,
    )
    assert verdict.accepted is False


def test_evaluate_notebook_rejects_low_rubric_score():
    """A contribution that the rubric scores low is rejected."""
    text = "Reasonably clean prose with vocab."
    verdict = evaluate_notebook_for_public(
        text_content=text,
        cited_chunk_tiers=[1, 2],
        corpus_sector_terms=["vocab"],
        rubric_score=0.3,  # below default threshold 0.6
    )
    assert verdict.accepted is False
    assert QualityGateReason.VERIFICATION_FAILED in verdict.reasons
