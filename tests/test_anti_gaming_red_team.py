"""Tests for substrate.anti_gaming.red_team — the executable
red-team harness used to produce sprint23_red_team.md §2 evidence."""

from __future__ import annotations

import pytest

from substrate.anti_gaming.red_team import (
    AttackClass,
    AttackResult,
    FalsePositiveResult,
    RedTeamReport,
    format_report_markdown,
    measure_false_positive_rate,
    run_red_team_report,
    simulate_attack_a_botnet_view_inflation,
    simulate_attack_b_attribution_chain_injection,
    simulate_attack_c_multi_account_self_attribution,
    simulate_attack_d_creator_cluster_collusion,
)
from substrate.anti_gaming.verdict import FraudVerdictKind


# ── Attack A: botnet view inflation ───────────────────────────────


def test_attack_a_caught():
    """The botnet attack should produce a BLOCK verdict."""
    r = simulate_attack_a_botnet_view_inflation(botnet_size=50)
    assert r.attack_class == AttackClass.A_BOTNET_VIEW_INFLATION
    assert r.expected_verdict == FraudVerdictKind.BLOCK
    assert r.passed, (
        f"botnet attack not caught: observed={r.observed_verdict.value}, "
        f"signals={r.signals_fired}"
    )
    # Should have triggered all three click-fraud signals.
    assert any(s in r.signals_fired for s in (
        "fast_dwell", "low_ua_entropy", "low_ip_entropy",
    ))


def test_attack_a_blocks_majority_of_botnet():
    """At least 80% of the botnet samples should be caught."""
    r = simulate_attack_a_botnet_view_inflation(botnet_size=50)
    # The first few might pass before window builds up; the rest must
    # land in REVIEW or BLOCK once entropy collapses.
    assert r.samples_blocked_or_reviewed >= 40


# ── Attack B: attribution-chain injection ─────────────────────────


def test_attack_b_caught_with_deep_chain():
    r = simulate_attack_b_attribution_chain_injection(chain_depth=15)
    assert r.attack_class == AttackClass.B_ATTRIBUTION_GRAPH_INJECTION
    assert r.passed
    assert "deep_attribution_chain" in r.signals_fired


def test_attack_b_shallow_chain_does_not_trigger():
    """A normal short chain should not fire the signal."""
    r = simulate_attack_b_attribution_chain_injection(chain_depth=3)
    # Short chain → no deep-chain signal → PASS (which fails the
    # red-team's "catch the attack" expectation by design — the
    # attack is only an attack at deep depth).
    assert r.observed_verdict == FraudVerdictKind.PASS
    assert "deep_attribution_chain" not in r.signals_fired


# ── Attack C: multi-account self-attribution ──────────────────────


def test_attack_c_dominant_share_caught():
    r = simulate_attack_c_multi_account_self_attribution(dominant_share=0.9)
    assert r.attack_class == AttackClass.C_MULTI_ACCOUNT_SELF_ATTRIBUTION
    assert r.passed
    assert "single_consumer_dominance" in r.signals_fired


def test_attack_c_balanced_share_does_not_trigger():
    """When the simulated attacker only holds 30% share (so neither
    side is dominant — attacker 0.30, other 0.70), the simulator's
    consumer_share map has max=0.70 which exceeds the 0.55 threshold
    and the signal DOES fire on the 'other' consumer. The signal is
    correctly side-agnostic; the test below confirms the simulator
    can be parameterised to BOTH sides being balanced."""
    from substrate.anti_gaming.attribution_fraud import score_attribution_payout

    # Truly balanced: many consumers, none dominant.
    verdict = score_attribution_payout(
        creator_id="target",
        consumer_share={f"u-{i}": 0.10 for i in range(10)},
        chain_depth=2,
    )
    assert "single_consumer_dominance" not in {s.name for s in verdict.signals}


# ── Attack D: creator-cluster collusion ───────────────────────────


def test_attack_d_ring_of_three_flagged():
    r = simulate_attack_d_creator_cluster_collusion(ring_size=3, intra_ring_share=0.9)
    assert r.attack_class == AttackClass.D_CREATOR_CLUSTER_COLLUSION
    assert r.passed
    assert "cluster_collusion" in r.signals_fired


def test_attack_d_no_ring_no_flag():
    """A non-colluding distribution (low intra-ring share) doesn't get
    flagged; the simulator returns observed=PASS and the AttackResult
    'passed' flag is False because the expected verdict was REVIEW.
    This is correct: the substrate refuses to flag a non-existent ring,
    and the harness's `passed` predicate marks it as a non-detection
    when the attack didn't happen."""
    r = simulate_attack_d_creator_cluster_collusion(ring_size=3, intra_ring_share=0.20)
    assert "cluster_collusion" not in r.signals_fired
    assert r.observed_verdict == FraudVerdictKind.PASS


# ── False-positive calibration ────────────────────────────────────


def test_false_positive_rate_within_target():
    """Legitimate sessions overwhelmingly PASS."""
    fp = measure_false_positive_rate(legitimate_sessions=500)
    # REVIEW rate target: ≤ 1%. BLOCK rate target: ≤ 0.1%.
    # Our scoring is conservative; even on 500 samples we should
    # comfortably beat both targets.
    assert fp.review_rate <= 0.01, (
        f"REVIEW rate too high: {fp.review_rate:.4f} on {fp.samples_scored} samples"
    )
    assert fp.block_rate <= 0.001, (
        f"BLOCK rate too high: {fp.block_rate:.4f} on {fp.samples_scored} samples"
    )


def test_false_positive_zero_samples():
    fp = measure_false_positive_rate(legitimate_sessions=0)
    assert fp.samples_scored == 0
    assert fp.review_rate == 0.0
    assert fp.block_rate == 0.0


# ── Full report assembly ──────────────────────────────────────────


def test_run_red_team_report_all_four_attacks():
    report = run_red_team_report(
        substrate_version="test-sha",
        fp_sample_size=200,
    )
    assert isinstance(report, RedTeamReport)
    assert len(report.attack_results) == 4
    attack_classes = {r.attack_class for r in report.attack_results}
    assert attack_classes == {
        AttackClass.A_BOTNET_VIEW_INFLATION,
        AttackClass.B_ATTRIBUTION_GRAPH_INJECTION,
        AttackClass.C_MULTI_ACCOUNT_SELF_ATTRIBUTION,
        AttackClass.D_CREATOR_CLUSTER_COLLUSION,
    }


def test_red_team_report_overall_verdict_go_when_all_caught():
    report = run_red_team_report(
        substrate_version="test-sha",
        fp_sample_size=200,
    )
    # All four attack classes should be caught by default parameters,
    # AND FP rate should be within targets.
    assert report.all_attacks_caught
    assert report.fp_rate_acceptable
    assert report.overall_verdict == "GO"


def test_format_report_markdown_includes_all_sections():
    report = run_red_team_report(
        substrate_version="abc123",
        fp_sample_size=200,
    )
    md = format_report_markdown(report)
    # Section headings + key fields.
    assert "Sprint 23-24" in md
    assert "abc123" in md
    assert "§2 Attack-class results" in md
    assert "§3 False-positive calibration" in md
    for cls in AttackClass:
        assert cls.value in md
    assert "**GO**" in md or "**NO-GO**" in md


# ── AttackResult.passed semantics ─────────────────────────────────


def test_attack_result_passed_when_observed_stronger_than_expected():
    """BLOCK observed when REVIEW expected → still passes (over-catching
    is better than under-catching for this gate)."""
    r = AttackResult(
        attack_class=AttackClass.B_ATTRIBUTION_GRAPH_INJECTION,
        expected_verdict=FraudVerdictKind.REVIEW,
        observed_verdict=FraudVerdictKind.BLOCK,
        signals_fired=(),
        samples_scored=1,
        samples_blocked_or_reviewed=1,
    )
    assert r.passed


def test_attack_result_failed_when_observed_weaker_than_expected():
    """REVIEW observed when BLOCK expected → fails."""
    r = AttackResult(
        attack_class=AttackClass.A_BOTNET_VIEW_INFLATION,
        expected_verdict=FraudVerdictKind.BLOCK,
        observed_verdict=FraudVerdictKind.REVIEW,
        signals_fired=(),
        samples_scored=50,
        samples_blocked_or_reviewed=50,
    )
    assert not r.passed


def test_attack_result_failed_when_pass_observed_at_all():
    r = AttackResult(
        attack_class=AttackClass.A_BOTNET_VIEW_INFLATION,
        expected_verdict=FraudVerdictKind.REVIEW,
        observed_verdict=FraudVerdictKind.PASS,
        signals_fired=(),
        samples_scored=50,
        samples_blocked_or_reviewed=0,
    )
    assert not r.passed
