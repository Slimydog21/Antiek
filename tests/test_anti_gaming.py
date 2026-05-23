"""Anti-gaming detector tests (Sprint 23-24 substrate)."""

from __future__ import annotations

import pytest

from substrate.anti_gaming import (
    AntiGamingDetector,
    FraudVerdictKind,
    SessionBurstWindow,
    detect_creator_cluster_collusion,
    ip_subnet_entropy,
    run_full_check,
    score_attribution_payout,
    score_click_event,
    score_view_event,
    ua_entropy,
)


# ── Click fraud ────────────────────────────────────────────────────


def test_ua_entropy_low_when_homogeneous():
    h = ua_entropy(["Mozilla/5.0 bot"] * 20)
    assert h < 0.1


def test_ua_entropy_high_when_diverse():
    h = ua_entropy([f"UA-{i}" for i in range(20)])
    assert h > 0.95


def test_ip_subnet_entropy_collapses_within_24():
    h = ip_subnet_entropy([f"192.168.1.{i}" for i in range(40)])
    # All inside the same /24 — entropy should be near 0.
    assert h < 0.1


def test_click_fast_dwell_is_review_or_block():
    v = score_click_event(
        dwell_seconds=0.2,
        window_ua_entropy=1.0,
        window_ip_entropy=1.0,
    )
    assert v.kind in {FraudVerdictKind.REVIEW, FraudVerdictKind.BLOCK}


def test_click_clean_event_passes():
    v = score_click_event(
        dwell_seconds=8.0,
        window_ua_entropy=1.0,
        window_ip_entropy=1.0,
    )
    assert v.kind == FraudVerdictKind.PASS


def test_click_all_three_signals_blocks():
    v = score_click_event(
        dwell_seconds=0.05,
        window_ua_entropy=0.05,
        window_ip_entropy=0.05,
    )
    assert v.kind == FraudVerdictKind.BLOCK


# ── View fraud ─────────────────────────────────────────────────────


def test_session_burst_window_rolls():
    w = SessionBurstWindow(window_seconds=60.0, threshold_per_minute=30)
    for i in range(40):
        w.record(float(i))  # one per second
    rate = w.rate_per_minute()
    # ~40 impressions across 40s — extrapolated to per-minute ~ 40.
    assert rate >= 30.0


def test_view_short_dwell_review():
    v = score_view_event(
        dwell_ms=10,
        session_rate_per_minute=5,
        is_repeat_impression=False,
    )
    assert v.kind in {FraudVerdictKind.REVIEW, FraudVerdictKind.BLOCK}


def test_view_repeat_impression_review():
    v = score_view_event(
        dwell_ms=2000,
        session_rate_per_minute=2,
        is_repeat_impression=True,
    )
    assert v.kind in {FraudVerdictKind.REVIEW, FraudVerdictKind.BLOCK}


def test_view_clean_event_passes():
    v = score_view_event(
        dwell_ms=2500,
        session_rate_per_minute=4,
        is_repeat_impression=False,
    )
    assert v.kind == FraudVerdictKind.PASS


# ── Attribution fraud ─────────────────────────────────────────────


def test_attribution_dominance_review():
    v = score_attribution_payout(
        creator_id="c-1",
        consumer_share={"u-1": 0.9, "u-2": 0.1},
        chain_depth=3,
    )
    assert v.kind in {FraudVerdictKind.REVIEW, FraudVerdictKind.BLOCK}


def test_attribution_clean_passes():
    v = score_attribution_payout(
        creator_id="c-1",
        consumer_share={f"u-{i}": 0.1 for i in range(10)},
        chain_depth=3,
    )
    assert v.kind == FraudVerdictKind.PASS


def test_creator_cluster_collusion_flagged():
    # Three creators routing 80%+ of outbound to each other.
    pairwise = {
        ("c-1", "c-2"): 60,
        ("c-1", "c-3"): 30,
        ("c-1", "outside"): 10,
        ("c-2", "c-1"): 70,
        ("c-2", "c-3"): 20,
        ("c-2", "outside"): 10,
        ("c-3", "c-1"): 50,
        ("c-3", "c-2"): 40,
        ("c-3", "outside"): 10,
    }
    verdicts = detect_creator_cluster_collusion(
        creator_pairwise_attribution=pairwise,
        creators=["c-1", "c-2", "c-3"],
    )
    flagged = {v.subject_ref for v in verdicts if v.kind != FraudVerdictKind.PASS}
    assert "c-1" in flagged or "c-2" in flagged or "c-3" in flagged


# ── Composite detector ────────────────────────────────────────────


def test_run_full_check_clean_session_passes():
    d = AntiGamingDetector()
    # Seed the click scorer with realistic diversity.
    for i in range(20):
        d.click_scorer.record(user_agent=f"UA-{i}", ip=f"10.{i}.0.1")
    v = run_full_check(
        d,
        session_id="s-1",
        user_agent="UA-fresh",
        ip="10.99.0.1",
        dwell_seconds=8.0,
        view_dwell_ms=2500,
        ad_id="ad-1",
        ts_seconds=100.0,
        creator_id="c-1",
        chain_depth=3,
    )
    assert v.kind == FraudVerdictKind.PASS


def test_run_full_check_botnet_session_blocks():
    d = AntiGamingDetector()
    for _ in range(50):
        d.click_scorer.record(user_agent="Mozilla/5.0 bot", ip="1.2.3.4")
    v = run_full_check(
        d,
        session_id="s-bot",
        user_agent="Mozilla/5.0 bot",
        ip="1.2.3.4",
        dwell_seconds=0.05,
        view_dwell_ms=10,
        ad_id="ad-1",
        ts_seconds=100.0,
    )
    assert v.kind == FraudVerdictKind.BLOCK
