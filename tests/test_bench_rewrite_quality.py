"""Tests for the benchmark rewrite-quality axis (ask #11 recursion success).

Longitudinal self-rewrite improvement. Exercises: improved/regressed/neutral/
unknown verdicts, 4-way decomposition (added_signal/removed_noise/recovered vs
removed_signal/added_noise/lost_signal), net_benefit + improvement_ratio,
regression surface, unevaluated handling, purity/immutability, validation.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.bench_rewrite_quality import (
    BenchRewriteQualityError,
    RewriteQualityReport,
    measure_rewrite_quality,
)

BSIG = "discriminates"
BTRIV = "trivial"
BIMP = "impossible"
BUN = "unattempted"


# --- improved (net positive) ----------------------------------------------


def test_improved_added_signal_and_removed_noise() -> None:
    old = {"a": BSIG, "b": BTRIV, "c": BIMP}
    new = {"a": BSIG, "d": BSIG}  # kept a(signal), dropped b+c(noise), added d(signal)
    r = measure_rewrite_quality(old, new)
    assert r.verdict == "improved"
    assert r.positive_count == 3  # removed_noise(b) + removed_noise(c) + added_signal(d)
    assert r.negative_count == 0
    assert r.net_benefit == 3
    assert r.improvement_ratio == 1.0
    assert r.authority == "advisory"


def test_improved_via_recovery() -> None:
    # noise task 'b' became signal -> recovered (positive)
    old = {"a": BSIG, "b": BTRIV}
    new = {"a": BSIG, "b": BSIG}
    r = measure_rewrite_quality(old, new)
    assert r.verdict == "improved"
    assert r.recovered == 1
    assert r.positive_count == 1
    assert r.negative_count == 0


# --- regressed (net negative) ---------------------------------------------


def test_regressed_dropped_signal_and_added_noise() -> None:
    old = {"a": BSIG, "b": BSIG}
    new = {"b": BSIG, "c": BTRIV}  # dropped a(signal) = removed_signal; added c(noise)
    r = measure_rewrite_quality(old, new)
    assert r.verdict == "regressed"
    assert r.negative_count == 2  # removed_signal(a) + added_noise(c)
    assert r.positive_count == 0
    assert r.net_benefit == -2
    assert r.improvement_ratio == 0.0
    assert r.regressed_signal_count == 1
    assert r.has_regression is True


def test_regressed_via_lost_signal() -> None:
    # retained task 'a' went signal->noise -> lost_signal (regression within retained)
    old = {"a": BSIG, "b": BTRIV}
    new = {"a": BTRIV, "c": BSIG}
    r = measure_rewrite_quality(old, new)
    # positive: removed_noise(b) + added_signal(c) = 2
    # negative: lost_signal(a) = 1
    assert r.positive_count == 2
    assert r.negative_count == 1
    assert r.net_benefit == 1
    assert r.verdict == "improved"  # net positive despite one regression
    assert r.lost_signal == 1
    assert r.regressed_signal_count == 1
    assert r.has_regression is True  # still flagged even though net-improved


# --- neutral (break-even) -------------------------------------------------


def test_neutral_equal_positive_and_negative() -> None:
    old = {"a": BSIG, "b": BTRIV}
    new = {"c": BSIG, "d": BTRIV}  # dropped a(signal)+b(noise), added c(signal)+d(noise)
    r = measure_rewrite_quality(old, new)
    assert r.positive_count == 2  # removed_noise(b) + added_signal(c)
    assert r.negative_count == 2  # removed_signal(a) + added_noise(d)
    assert r.net_benefit == 0
    assert r.verdict == "neutral"
    assert r.improvement_ratio == 0.5


def test_neutral_no_changes() -> None:
    old = {"a": BSIG, "b": BTRIV}
    new = {"a": BSIG, "b": BTRIV}  # identical
    r = measure_rewrite_quality(old, new)
    assert r.positive_count == 0
    assert r.negative_count == 0
    assert r.net_benefit == 0
    assert r.improvement_ratio is None
    assert r.verdict == "neutral"
    assert r.preserved_signal == 1
    assert r.preserved_noise == 1


# --- unknown (defer, never fabricated) ------------------------------------


def test_unknown_both_empty() -> None:
    r = measure_rewrite_quality({}, {})
    assert r.verdict == "unknown"
    assert r.improvement_ratio is None
    assert r.net_benefit == 0


def test_unknown_all_unevaluated() -> None:
    old = {"a": BUN, "b": BUN}
    new = {"a": BUN, "c": BUN}
    r = measure_rewrite_quality(old, new)
    assert r.verdict == "unknown"
    assert r.signal_count_old == 0
    assert r.signal_count_new == 0


# --- unevaluated handling (neutral, never fabricated as noise) ------------


def test_unevaluated_excluded_from_signal_noise() -> None:
    old = {"a": BSIG, "b": BUN}
    new = {"a": BSIG, "c": BUN}  # dropped b(unevaluated), added c(unevaluated)
    r = measure_rewrite_quality(old, new)
    assert r.removed_unevaluated == 1
    assert r.added_unevaluated == 1
    assert r.positive_count == 0
    assert r.negative_count == 0
    assert r.verdict == "neutral"  # only signal task 'a' preserved, no measurable change


def test_unevaluated_to_signal_not_counted_as_change() -> None:
    # retained task 'b' went unevaluated->signal: this is a re-evaluation, not a
    # rewrite change (the task existed before). Treated as neutral retained, not
    # recovered (recovered is noise->signal specifically).
    old = {"a": BSIG, "b": BUN}
    new = {"a": BSIG, "b": BSIG}
    r = measure_rewrite_quality(old, new)
    assert r.recovered == 0  # BUN->BSIG is not "recovered" (that's noise->signal)
    assert r.positive_count == 0
    assert r.negative_count == 0


# --- signal/noise pool tracking -------------------------------------------


def test_signal_and_noise_pool_counts() -> None:
    old = {"a": BSIG, "b": BSIG, "c": BTRIV, "d": BIMP, "e": BUN}
    new = {"a": BSIG, "c": BSIG, "f": BSIG, "g": BTRIV}
    r = measure_rewrite_quality(old, new)
    assert r.signal_count_old == 2  # a, b
    assert r.signal_count_new == 3  # a, c, f
    assert r.noise_count_old == 2  # c(trivial), d(impossible)
    assert r.noise_count_new == 1  # g(trivial)


# --- validation -----------------------------------------------------------


def test_empty_task_id_raises() -> None:
    with pytest.raises(BenchRewriteQualityError, match="empty task_id"):
        measure_rewrite_quality({"": BSIG}, {"x": BSIG})


def test_invalid_band_raises() -> None:
    with pytest.raises(BenchRewriteQualityError, match="invalid band"):
        measure_rewrite_quality({"a": "maybe"}, {"x": BSIG})


# --- purity / immutability ------------------------------------------------


def test_report_is_frozen_and_deterministic() -> None:
    old = {"a": BSIG, "b": BTRIV}
    new = {"a": BSIG, "c": BSIG}
    r1 = measure_rewrite_quality(old, new)
    r2 = measure_rewrite_quality(old, new)
    assert dataclasses.is_dataclass(r1)
    assert r1 == r2  # deterministic
    with pytest.raises(dataclasses.FrozenInstanceError):
        r1.verdict = "tampered"  # type: ignore[misc]
    assert isinstance(r1, RewriteQualityReport)


def test_notes_are_non_empty_and_auditable() -> None:
    r = measure_rewrite_quality({"a": BSIG}, {"a": BSIG, "b": BSIG})
    assert isinstance(r.notes, tuple)
    assert len(r.notes) >= 5
    assert all(isinstance(n, str) and n for n in r.notes)
