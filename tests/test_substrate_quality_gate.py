"""Tests for substrate.quality_gate — §13.9 public-notes ingest gate."""

from __future__ import annotations

from substrate.quality_gate import (
    CandidateNote,
    CheckResultKind,
    QualityGateVerdict,
    SourceTierBounds,
    check_source_tier,
    check_verification,
    check_voice_style,
    run_quality_gate,
)


def _good_note() -> CandidateNote:
    return CandidateNote(
        note_id="note-1",
        user_id="u-1",
        prose=(
            "The Hippo dispatch posture matured along two axes in 2026. "
            "The Hermes verify-tier acquired a chaos test that ratified "
            "the OAuth-refresh-503 translation rule. The chaos test "
            "landed without changes to dispatch code; the bridge "
            "absorbed the translation responsibility cleanly. The "
            "synthesizer tier began its measurement window against "
            "Grok 4.3 on long-form English research writing. The "
            "verdict will land at Sprint 20."
        ),
        claims=("c-1", "c-2"),
        claim_evidence={
            "c-1": ("chunk-a", "chunk-b"),
            "c-2": ("chunk-c",),
        },
        cited_source_tiers=(1, 2),
    )


# ── verification check ──────────────────────────────────────────


def test_verification_passes_when_every_claim_has_evidence():
    note = _good_note()
    r = check_verification(note)
    assert r.kind == CheckResultKind.PASS
    assert r.score == 1.0


def test_verification_fails_on_zero_claims():
    note = CandidateNote(
        note_id="note-2", user_id="u-1", prose="any prose",
        claims=(), claim_evidence={}, cited_source_tiers=(),
    )
    r = check_verification(note)
    assert r.kind == CheckResultKind.FAIL
    assert "zero claims" in r.reasons[0]


def test_verification_fails_when_some_claim_missing_evidence():
    note = CandidateNote(
        note_id="note-3", user_id="u-1", prose="any",
        claims=("c-1", "c-2", "c-3"),
        claim_evidence={"c-1": ("chunk-a",)},
        cited_source_tiers=(),
    )
    r = check_verification(note)
    assert r.kind == CheckResultKind.FAIL
    assert "without evidence" in r.reasons[0]
    assert abs(r.score - (1 / 3)) < 1e-9


# ── source_tier check ──────────────────────────────────────────


def test_source_tier_passes_when_all_in_bounds():
    note = CandidateNote(
        note_id="n", user_id="u-1", prose="x",
        claims=("c-1",), claim_evidence={"c-1": ("ch-a",)},
        cited_source_tiers=(1, 2, 3),
    )
    r = check_source_tier(note)
    assert r.kind == CheckResultKind.PASS


def test_source_tier_fails_when_tier_too_high():
    note = CandidateNote(
        note_id="n", user_id="u-1", prose="x",
        claims=("c-1",), claim_evidence={"c-1": ("ch-a",)},
        cited_source_tiers=(1, 4, 5),
    )
    r = check_source_tier(note)
    assert r.kind == CheckResultKind.FAIL
    assert "outside tier range" in r.reasons[0]


def test_source_tier_passes_when_no_cited_sources():
    note = CandidateNote(
        note_id="n", user_id="u-1", prose="x",
        claims=("c-1",), claim_evidence={"c-1": ("ch-a",)},
        cited_source_tiers=(),
    )
    r = check_source_tier(note)
    assert r.kind == CheckResultKind.PASS


def test_source_tier_custom_bounds():
    note = CandidateNote(
        note_id="n", user_id="u-1", prose="x",
        claims=("c-1",), claim_evidence={"c-1": ("ch-a",)},
        cited_source_tiers=(2, 3),
    )
    bounds = SourceTierBounds(min_acceptable=1, max_acceptable=1)
    r = check_source_tier(note, bounds=bounds)
    assert r.kind == CheckResultKind.FAIL


# ── voice_style check ──────────────────────────────────────────


def test_voice_style_passes_on_clean_prose():
    note = _good_note()
    r = check_voice_style(note)
    assert r.kind == CheckResultKind.PASS


def test_voice_style_fails_on_slop_prose():
    note = CandidateNote(
        note_id="n", user_id="u-1",
        prose=(
            "Key takeaways:\n"
            "- The first point is important\n"
            "- The second point is also important\n"
            "- Moreover, the third point matters\n"
            "- Furthermore, the fourth point\n"
            "- In addition, the fifth point\n"
            "- Additionally, the sixth point\n"
            "- Perhaps the seventh point\n"
            "- It could be argued that the eighth point\n"
            "In conclusion, all takeaways are important."
        ),
        claims=("c-1",), claim_evidence={"c-1": ("ch-a",)},
        cited_source_tiers=(1,),
    )
    r = check_voice_style(note)
    assert r.kind == CheckResultKind.FAIL


# ── full gate composition ──────────────────────────────────────


def test_full_gate_all_pass_returns_pass_public():
    note = _good_note()
    result = run_quality_gate(
        note,
        verification_check=check_verification,
        voice_style_check=check_voice_style,
        source_tier_check=check_source_tier,
    )
    assert result.verdict == QualityGateVerdict.PASS_PUBLIC
    assert len(result.passed_checks) == 3
    assert len(result.failed_checks) == 0


def test_full_gate_verification_fail_returns_reject():
    note = CandidateNote(
        note_id="n", user_id="u-1", prose="x",
        claims=(), claim_evidence={}, cited_source_tiers=(),
    )
    result = run_quality_gate(
        note,
        verification_check=check_verification,
        voice_style_check=check_voice_style,
        source_tier_check=check_source_tier,
    )
    assert result.verdict == QualityGateVerdict.REJECT


def test_full_gate_voice_style_fail_reroutes_private():
    note = CandidateNote(
        note_id="n", user_id="u-1",
        prose=(
            "Key takeaways:\n"
            "- bullet one\n- bullet two\n- bullet three\n"
            "- bullet four\n- bullet five\n- bullet six\n"
            "- bullet seven\n- bullet eight\n"
            "Moreover, in conclusion."
        ),
        claims=("c-1",), claim_evidence={"c-1": ("ch-a",)},
        cited_source_tiers=(1,),
    )
    result = run_quality_gate(
        note,
        verification_check=check_verification,
        voice_style_check=check_voice_style,
        source_tier_check=check_source_tier,
    )
    assert result.verdict == QualityGateVerdict.REROUTE_PRIVATE


def test_full_gate_source_tier_fail_reroutes_private():
    note = _good_note()
    bad_tier = CandidateNote(
        note_id=note.note_id, user_id=note.user_id, prose=note.prose,
        claims=note.claims, claim_evidence=note.claim_evidence,
        cited_source_tiers=(5,),
    )
    result = run_quality_gate(
        bad_tier,
        verification_check=check_verification,
        voice_style_check=check_voice_style,
        source_tier_check=check_source_tier,
    )
    assert result.verdict == QualityGateVerdict.REROUTE_PRIVATE


def test_full_gate_minimal_only_verification_check():
    note = _good_note()
    result = run_quality_gate(note, verification_check=check_verification)
    assert result.verdict == QualityGateVerdict.PASS_PUBLIC
    assert len(result.checks) == 1
