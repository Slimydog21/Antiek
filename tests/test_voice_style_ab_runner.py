"""Tests for substrate.voice_style.ab_runner — Sprint 23-24 §4 voice audit."""

from __future__ import annotations

import pytest

from substrate.voice_style import (
    AuditVerdictKind,
    VoiceImpactObservation,
    format_audit_markdown,
    run_voice_impact_audit,
)

GOOD_PROSE = (
    "The Hippo dispatch posture matured along two axes in 2026. "
    "The Hermes verify-tier acquired a chaos test that ratified "
    "the OAuth-refresh translation rule. The chaos test landed "
    "without changes to dispatch code; the bridge absorbed the "
    "translation responsibility cleanly."
)

BAD_PROSE = (
    "Key takeaways:\n- bullet one\n- bullet two\n- bullet three\n"
    "- bullet four\n- bullet five\n- bullet six\n- bullet seven\n"
    "- bullet eight\nIn conclusion."
)


def _obs(cohort: str, prose: str, page_id: str = "p") -> VoiceImpactObservation:
    return VoiceImpactObservation(page_id=page_id, cohort=cohort, prose=prose)


def test_clean_cohorts_pass():
    observations = (
        [_obs("zero_ad", GOOD_PROSE, f"p-{i}") for i in range(10)]
        + [_obs("ad_bearing", GOOD_PROSE, f"p-ad-{i}") for i in range(10)]
    )
    result = run_voice_impact_audit(observations)
    assert result.verdict == AuditVerdictKind.PASS
    assert result.pct_regression == pytest.approx(0.0)
    assert result.ad_bearing.sample_count == 10
    assert result.zero_ad.sample_count == 10


def test_ad_cohort_degradation_fails():
    observations = (
        [_obs("zero_ad", GOOD_PROSE, f"p-{i}") for i in range(10)]
        + [_obs("ad_bearing", BAD_PROSE, f"p-ad-{i}") for i in range(10)]
    )
    result = run_voice_impact_audit(observations)
    assert result.verdict == AuditVerdictKind.FAIL
    assert result.absolute_regression > 0.3


def test_one_cohort_empty_returns_watch():
    observations = [_obs("zero_ad", GOOD_PROSE)]
    result = run_voice_impact_audit(observations)
    assert result.verdict == AuditVerdictKind.WATCH
    assert "insufficient samples" in result.verdict_reason


def test_regression_below_5pct_is_pass():
    """Same prose in both cohorts — regression is 0. Passes."""
    obs = (
        [_obs("zero_ad", GOOD_PROSE, f"p-z-{i}") for i in range(20)]
        + [_obs("ad_bearing", GOOD_PROSE, f"p-a-{i}") for i in range(20)]
    )
    result = run_voice_impact_audit(obs)
    assert result.verdict == AuditVerdictKind.PASS


def test_ad_absolute_below_floor_fails():
    """If ad cohort's mean voice score is below 0.70 absolute,
    FAIL even with small percentage regression."""
    obs = (
        [_obs("zero_ad", BAD_PROSE, f"p-z-{i}") for i in range(10)]
        + [_obs("ad_bearing", BAD_PROSE, f"p-a-{i}") for i in range(10)]
    )
    result = run_voice_impact_audit(obs)
    # Both cohorts at the same low score → 0% regression but absolute
    # is below 0.70 → FAIL.
    assert result.verdict == AuditVerdictKind.FAIL
    assert "absolute floor" in result.verdict_reason


def test_format_audit_markdown_includes_all_sections():
    obs = (
        [_obs("zero_ad", GOOD_PROSE, f"p-z-{i}") for i in range(10)]
        + [_obs("ad_bearing", GOOD_PROSE, f"p-a-{i}") for i in range(10)]
    )
    result = run_voice_impact_audit(obs)
    md = format_audit_markdown(result)
    assert "Sprint 23-24" in md
    assert "Cohort scores" in md
    assert "Verdict" in md
    assert "zero_ad" in md
    assert "ad_bearing" in md
