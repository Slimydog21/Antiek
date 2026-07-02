"""AFA-S2 (M2) — GIVT classifier fixture pairs.

Every GIVT rule ships as a caught-bad fixture AND a passed-good near-miss (the
sprint's unit of progress: a rule with only the caught-bad case is untested
against its false-positive cost). Plus a determinism property and a whole-honest-
session guard (the pipeline-level false-positive check).
"""

from __future__ import annotations

from substrate.ad_inventory.frame_attention import (
    FrameAttentionSample,
    FrameSecond,
    WindowFrameBatch,
)
from substrate.anti_gaming.frame_ivt import (
    DEFAULT_DAILY_ASSET_DWELL_CAP_MS,
    MIN_SIVT_WINDOW_SECONDS,
    REASON_CONSTANT_ATTENTION,
    REASON_DUPLICATE_INDEX,
    REASON_FOCUS_MARATHON,
    REASON_IMPOSSIBLE_GEOMETRY,
    REASON_NON_MONOTONIC,
    REASON_OVERSIZED_BATCH,
    clamp_countable_dwell,
    classify_batch,
)
from substrate.anti_gaming.verdict import FraudVerdictKind


def _sample(asset_id="doc-1", area=0.6, prominence=0.7, dwell=800):
    return FrameAttentionSample(
        asset_id=asset_id,
        viewport_area_fraction=area,
        prominence=prominence,
        focused_dwell_ms=dwell,
    )


def _second(index, samples=None):
    return FrameSecond(
        second_index=index,
        lens="read",
        samples=tuple(samples if samples is not None else [_sample()]),
    )


def _batch(seconds, window_id="win:read:s2test"):
    return WindowFrameBatch(
        window_id=window_id,
        seconds=tuple(seconds),
        ad_value_usd_cents=0,
    )


def _reasons(result):
    return {c.reason for c in result.seconds if c.reason is not None}


# ── Rule 1: non-monotonic / duplicate second_index ───────────────────────────


def test_duplicate_index_is_caught():
    # Index 1 appears twice — replay of a second.
    result = classify_batch(_batch([_second(0), _second(1), _second(1)]))
    assert REASON_DUPLICATE_INDEX in _reasons(result)
    # The DUPLICATE occurrence (position 2) is the invalid one; the first two
    # seconds stay valid.
    assert result.invalid_positions == frozenset({2})


def test_regression_index_is_caught():
    # 0, 2, 1 — the third second's index regresses below the second's.
    result = classify_batch(_batch([_second(0), _second(2), _second(1)]))
    assert REASON_NON_MONOTONIC in _reasons(result)
    assert 2 in result.invalid_positions


def test_single_dropped_tick_gap_passes():
    # 0, 1, 3 — the 1 Hz sampler missed second 2 (tab hidden a beat). LEGITIMATE:
    # gaps are allowed, only order/duplication is invalid.
    result = classify_batch(_batch([_second(0), _second(1), _second(3)]))
    assert _reasons(result) == set()
    assert result.window_verdict.kind is FraudVerdictKind.PASS


# ── Rule 2: impossible sample geometry ───────────────────────────────────────


def test_dwell_with_zero_area_is_caught():
    # focused_dwell_ms > 0 but the asset occupied zero viewport area — you cannot
    # focus-dwell on something that is not on screen.
    bad = _second(0, samples=[_sample(area=0.0, prominence=0.0, dwell=1000)])
    result = classify_batch(_batch([bad]))
    assert REASON_IMPOSSIBLE_GEOMETRY in _reasons(result)


def test_prominence_with_zero_area_is_caught():
    bad = _second(0, samples=[_sample(area=0.0, prominence=0.9, dwell=0)])
    result = classify_batch(_batch([bad]))
    assert REASON_IMPOSSIBLE_GEOMETRY in _reasons(result)


def test_tiny_but_nonzero_area_passes():
    # A barely-visible asset (1% of viewport) briefly dwelt on is a REAL edge of
    # legitimate reading, not impossible — it must pass.
    ok = _second(0, samples=[_sample(area=0.01, prominence=0.05, dwell=250)])
    result = classify_batch(_batch([ok]))
    assert _reasons(result) == set()


def test_zero_area_zero_dwell_passes():
    # An off-screen asset with zero dwell is consistent (not impossible) — it
    # simply earns nothing; it is not fraud.
    ok = _second(0, samples=[_sample(area=0.0, prominence=0.0, dwell=0)])
    result = classify_batch(_batch([ok]))
    assert _reasons(result) == set()


# ── Rule 3: oversized batch ──────────────────────────────────────────────────


def test_oversized_batch_is_caught():
    # With a small ceiling for the test: 4 seconds > max 3 → the WHOLE batch is
    # fabricated and BLOCKs.
    result = classify_batch(
        _batch([_second(i) for i in range(4)]), max_window_seconds=3
    )
    assert _reasons(result) == {REASON_OVERSIZED_BATCH}
    assert result.invalid_positions == frozenset({0, 1, 2, 3})
    assert result.window_verdict.kind is FraudVerdictKind.BLOCK


def test_batch_at_the_ceiling_passes():
    result = classify_batch(
        _batch([_second(i) for i in range(3)]), max_window_seconds=3
    )
    assert _reasons(result) == set()
    assert result.window_verdict.kind is FraudVerdictKind.PASS


# ── Window verdict ladder ────────────────────────────────────────────────────


def test_mostly_invalid_batch_blocks():
    # 3 of 4 seconds duplicate-invalid → fraction 0.75 → BLOCK.
    result = classify_batch(
        _batch([_second(0), _second(0), _second(0), _second(0)])
    )
    assert result.window_verdict.kind is FraudVerdictKind.BLOCK


def test_small_minority_invalid_only_reviews():
    # 1 of 5 seconds impossible → fraction 0.2 → below REVIEW(0.45): PASS with a
    # counted exclusion. (An isolated bad second does not condemn the window; the
    # M5 filter still excludes that one second.)
    good = [_second(i) for i in range(4)]
    bad = _second(4, samples=[_sample(area=0.0, dwell=900)])
    result = classify_batch(_batch(good + [bad]))
    assert result.window_verdict.kind is FraudVerdictKind.PASS
    assert result.counts_by_reason() == {REASON_IMPOSSIBLE_GEOMETRY: 1}


# ── Honest-session guard + determinism ───────────────────────────────────────


def test_whole_honest_session_passes_all_rules():
    # A realistic read: monotonic indices with one dropped-tick gap, real
    # geometry that jitters, a lens the sampler supports.
    seconds = [
        _second(0, [_sample(area=0.6, prominence=0.8, dwell=1000)]),
        _second(1, [_sample(area=0.55, prominence=0.6, dwell=1000)]),
        _second(2, [_sample(area=0.7, prominence=0.9, dwell=250)]),  # scrolled
        _second(4, [_sample(area=0.5, prominence=0.4, dwell=1000)]),  # gap @3
        _second(5, [_sample(area=0.65, prominence=0.75, dwell=1000)]),
    ]
    result = classify_batch(_batch(seconds))
    assert _reasons(result) == set()
    assert result.window_verdict.kind is FraudVerdictKind.PASS
    assert result.counts_by_reason() == {}


def test_classification_is_deterministic():
    seconds = [_second(0), _second(1), _second(1), _second(5)]
    r1 = classify_batch(_batch(seconds))
    r2 = classify_batch(_batch(seconds))
    # The DECISION (kind + per-second validity + reasons) is identical across
    # runs — only the audit decided_at (metadata) may differ.
    assert r1.window_verdict.kind is r2.window_verdict.kind
    assert [(c.position, c.valid, c.reason) for c in r1.seconds] == [
        (c.position, c.valid, c.reason) for c in r2.seconds
    ]


# ── SIVT (M3): behavioural implausibility over a long-enough window ───────────

_N = MIN_SIVT_WINDOW_SECONDS + 4  # comfortably over the SIVT evaluation floor


def _window_signatures(fn):
    """Build a long window; ``fn(i)`` returns the samples for second i."""
    return _batch([_second(i, fn(i)) for i in range(_N)])


def test_sivt_not_evaluated_below_window_floor():
    # A SHORT constant window (identical vectors) is NOT judged by SIVT — too
    # little signal to call a pattern. Presumed innocent.
    short = _batch([_second(i, [_sample()]) for i in range(MIN_SIVT_WINDOW_SECONDS - 5)])
    result = classify_batch(short)
    assert result.window_verdict.kind is FraudVerdictKind.PASS
    assert REASON_CONSTANT_ATTENTION not in _reasons_window(result)


def _reasons_window(result):
    return {s.name for s in result.window_verdict.signals}


def test_constant_attention_signature_is_caught():
    # Every second an IDENTICAL sample vector over a long window — replayed /
    # synthetic; real reading jitters. dwell=800 so the marathon rule stays out.
    result = classify_batch(
        _window_signatures(lambda i: [_sample(area=0.6, prominence=0.7, dwell=800)])
    )
    assert REASON_CONSTANT_ATTENTION in _reasons_window(result)
    assert result.window_verdict.kind is FraudVerdictKind.REVIEW  # heuristic → REVIEW


def test_jittering_long_read_passes_constant_attention():
    # A real long read: geometry jitters second to second (scroll/pause), so the
    # modal signature never dominates.
    def samples(i):
        return [
            _sample(
                area=0.4 + (i % 7) * 0.05,
                prominence=0.3 + (i % 5) * 0.1,
                dwell=1000 if i % 4 else 250,
            )
        ]

    result = classify_batch(_window_signatures(samples))
    assert REASON_CONSTANT_ATTENTION not in _reasons_window(result)
    assert result.window_verdict.kind is FraudVerdictKind.PASS


def test_focus_marathon_is_caught():
    # Perfect pinned dwell + frozen area + no glancing over a long window. Vary
    # prominence slightly so the CONSTANT-attention rule stays out and this
    # isolates the marathon signal.
    def samples(i):
        return [_sample(area=0.6, prominence=0.70 + (i % 2) * 0.03, dwell=1000)]

    result = classify_batch(_window_signatures(samples))
    assert REASON_FOCUS_MARATHON in _reasons_window(result)
    assert REASON_CONSTANT_ATTENTION not in _reasons_window(result)
    assert result.window_verdict.kind is FraudVerdictKind.REVIEW


def test_long_read_with_glances_passes_marathon():
    # A real long read holds focus but glances/scrolls (250ms seconds) and its
    # area varies — the marathon rule must not fire.
    def samples(i):
        return [
            _sample(
                area=0.5 + (i % 6) * 0.04,
                prominence=0.6,
                dwell=250 if i % 5 == 0 else 1000,
            )
        ]

    result = classify_batch(_window_signatures(samples))
    assert REASON_FOCUS_MARATHON not in _reasons_window(result)
    assert result.window_verdict.kind is FraudVerdictKind.PASS


def test_max_severity_sivt_review_not_diluted_by_low_givt():
    # A long constant window (SIVT REVIEW, 0.6) with ONE extra impossible-geometry
    # second (GIVT, fraction ~1/31 ≈ 0.03). Mean would be (0.6+0.03)/2 ≈ 0.31 →
    # PASS (WRONG — dilutes the heuristic). Max-severity keeps it at REVIEW: a
    # weak GIVT fact must not downgrade the SIVT concern, and vice versa.
    good = [_second(i, [_sample(area=0.6, prominence=0.7, dwell=800)]) for i in range(_N)]
    bad = _second(_N, [_sample(area=0.0, prominence=0.0, dwell=900)])  # impossible
    result = classify_batch(_batch(good + [bad]))
    # window signal set carries the SIVT reason + the GIVT fraction signal;
    # the per-second GIVT reason lives in the reported counts.
    assert REASON_CONSTANT_ATTENTION in _reasons_window(result)
    assert REASON_IMPOSSIBLE_GEOMETRY in result.counts_by_reason()
    assert result.window_verdict.kind is FraudVerdictKind.REVIEW  # NOT diluted to PASS


# ── M4: per-(user, asset, day) saturation cap (pure clamp) ───────────────────


def test_dwell_under_cap_is_fully_counted():
    counted, clamped = clamp_countable_dwell(0, 5000, cap_ms=10_000)
    assert (counted, clamped) == (5000, 0)


def test_dwell_crossing_cap_is_partially_clamped():
    # 8000 prior + 5000 incremental, cap 10_000 → only 2000 counts, 3000 clamped.
    counted, clamped = clamp_countable_dwell(8000, 5000, cap_ms=10_000)
    assert (counted, clamped) == (2000, 3000)


def test_dwell_already_at_cap_counts_nothing():
    counted, clamped = clamp_countable_dwell(10_000, 4000, cap_ms=10_000)
    assert (counted, clamped) == (0, 4000)


def test_dwell_over_cap_counts_nothing():
    counted, clamped = clamp_countable_dwell(12_000, 4000, cap_ms=10_000)
    assert (counted, clamped) == (0, 4000)


def test_dwell_exactly_reaching_cap_boundary():
    counted, clamped = clamp_countable_dwell(6000, 4000, cap_ms=10_000)
    assert (counted, clamped) == (4000, 0)


def test_zero_or_negative_incremental_is_noop():
    assert clamp_countable_dwell(0, 0, cap_ms=10_000) == (0, 0)
    assert clamp_countable_dwell(5000, -100, cap_ms=10_000) == (0, 0)


def test_conservation_counted_plus_clamped_equals_incremental():
    # The clamp never invents or loses dwell: counted + clamped == incremental
    # for every prior/incremental combination (the reported-exclusion invariant).
    for prior in (0, 3000, 9999, 10_000, 20_000):
        for inc in (0, 1, 4000, 10_000):
            counted, clamped = clamp_countable_dwell(prior, inc, cap_ms=10_000)
            assert counted + clamped == max(inc, 0)


def test_default_cap_is_a_generous_ceiling():
    # The un-calibrated default is a "no honest single-document day exceeds this"
    # ceiling (6h of countable dwell), not a tuned percentile — documented as a
    # calibration follow-up. A normal window's worth of dwell is far under it.
    assert DEFAULT_DAILY_ASSET_DWELL_CAP_MS == 21_600_000
    counted, clamped = clamp_countable_dwell(0, 600_000, )  # 10 min, default cap
    assert (counted, clamped) == (600_000, 0)
