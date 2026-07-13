"""Tests for the search precision/recall axis (ask #14).

Measures result-SET quality (precision = noise rate, recall = coverage) with
ground-truth relevance labels — distinct from search_quality #1957 (ranking ORDER
via NDCG with lexical estimation). Exercises high_quality/noisy/incomplete/
adequate/unknown verdicts, precision/recall/f1 math, the None-defer boundaries,
deduplication, validation, purity/immutability.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.search_precision_recall import (
    SearchPrecisionRecallError,
    measure_search_precision_recall,
)

# --- unknown --------------------------------------------------------------


def test_unknown_when_nothing_returned_and_nothing_relevant() -> None:
    r = measure_search_precision_recall([], [], 0)
    assert r.verdict == "unknown"
    assert r.returned_count == 0
    assert r.total_relevant == 0
    assert r.precision is None
    assert r.recall is None
    assert r.f1 is None
    assert r.authority == "advisory"


# --- high_quality ---------------------------------------------------------


def test_high_quality_both_strong() -> None:
    # returned 8 of 10 relevant, all 8 relevant -> precision 1.0, recall 0.8.
    returned = [f"r{i}" for i in range(8)]
    relevant = list(returned)
    r = measure_search_precision_recall(returned, relevant, 10)
    assert r.verdict == "high_quality"
    assert r.precision == 1.0
    assert r.recall == 0.8
    assert r.true_positives == 8
    assert r.false_positives == 0


def test_high_quality_boundary_inclusive() -> None:
    # precision 0.80, recall 0.80 exactly -> high_quality (>=).
    returned = [f"r{i}" for i in range(8)] + [f"n{i}" for i in range(2)]
    relevant = [f"r{i}" for i in range(8)]
    r = measure_search_precision_recall(returned, relevant, 10)
    assert r.precision == pytest.approx(0.80)
    assert r.recall == pytest.approx(0.80)
    assert r.verdict == "high_quality"


# --- noisy ----------------------------------------------------------------


def test_noisy_low_precision() -> None:
    # 10 returned, 2 relevant -> precision 0.2 < 0.30 low_threshold.
    returned = ["r0", "r1"] + [f"n{i}" for i in range(8)]
    relevant = ["r0", "r1"]
    r = measure_search_precision_recall(returned, relevant, 2)
    assert r.verdict == "noisy"
    assert r.precision == pytest.approx(0.2)
    assert r.recall == 1.0
    assert r.false_positives == 8


# --- incomplete -----------------------------------------------------------


def test_incomplete_low_recall() -> None:
    # 10 relevant in corpus, only 2 returned -> recall 0.2 < 0.30.
    returned = ["r0", "r1"]
    relevant = ["r0", "r1"]
    r = measure_search_precision_recall(returned, relevant, 10)
    assert r.verdict == "incomplete"
    assert r.recall == pytest.approx(0.2)
    assert r.precision == 1.0
    assert r.false_negatives == 0  # both relevant items in the label set were returned


def test_incomplete_nothing_returned_but_relevant_exists() -> None:
    # Nothing returned but 5 relevant exist -> precision None, recall 0.0.
    r = measure_search_precision_recall([], [], 5)
    assert r.verdict == "incomplete"
    assert r.precision is None
    assert r.recall == 0.0


# --- adequate -------------------------------------------------------------


def test_adequate_moderate_both() -> None:
    # precision 0.5, recall 0.5 -> neither < low (0.30) nor both >= high (0.80).
    returned = ["r0", "r1", "n0", "n1"]
    relevant = ["r0", "r1"]
    r = measure_search_precision_recall(returned, relevant, 4)
    assert r.precision == 0.5
    assert r.recall == 0.5
    assert r.verdict == "adequate"


# --- f1 calculation -------------------------------------------------------


def test_f1_harmonic_mean() -> None:
    # precision 2/3, recall 2/5 -> f1 = 2*(2/3)*(2/5)/((2/3)+(2/5)) = 0.5.
    returned = ["a", "b", "c"]
    relevant = ["a", "b"]
    r = measure_search_precision_recall(returned, relevant, 5)
    assert r.precision == pytest.approx(2 / 3)
    assert r.recall == pytest.approx(2 / 5)
    assert r.f1 == pytest.approx(0.5)


def test_f1_none_when_precision_none() -> None:
    # Nothing returned -> precision None -> f1 None.
    r = measure_search_precision_recall([], [], 5)
    assert r.precision is None
    assert r.f1 is None


def test_f1_none_when_both_zero() -> None:
    # precision 0.0 and recall 0.0 -> precision+recall = 0 -> f1 None.
    returned = ["n0", "n1"]
    relevant = ["r0", "r1"]
    r = measure_search_precision_recall(returned, relevant, 4)
    assert r.precision == 0.0
    assert r.recall == 0.0
    assert r.f1 is None


# --- deduplication --------------------------------------------------------


def test_duplicate_returned_ids_deduplicated() -> None:
    returned = ["a", "a", "a", "b"]
    relevant = ["a", "b"]
    r = measure_search_precision_recall(returned, relevant, 2)
    assert r.returned_count == 2
    assert r.precision == 1.0


# --- precision None boundary ----------------------------------------------


def test_precision_none_when_nothing_returned() -> None:
    r = measure_search_precision_recall([], ["a", "b"], 5)
    assert r.precision is None  # defer, never 1.0 or 0.0
    assert r.recall == 0.0


# --- recall None boundary -------------------------------------------------


def test_recall_none_when_no_relevant_in_corpus() -> None:
    # total_relevant 0 but items returned -> recall None (all noise).
    r = measure_search_precision_recall(["a", "b"], [], 0)
    assert r.recall is None  # defer, never 1.0
    assert r.precision == 0.0
    assert r.verdict == "noisy"


# --- custom thresholds ----------------------------------------------------


def test_custom_thresholds_shift_verdict() -> None:
    # precision 0.5, recall 0.5: adequate at default, high at 0.50/0.50.
    returned = ["r0", "r1", "n0", "n1"]
    relevant = ["r0", "r1"]
    r_default = measure_search_precision_recall(returned, relevant, 4)
    assert r_default.verdict == "adequate"
    r_loose = measure_search_precision_recall(returned, relevant, 4, high_threshold=0.50)
    assert r_loose.verdict == "high_quality"


# --- validation -----------------------------------------------------------


def test_negative_total_relevant_raises() -> None:
    with pytest.raises(SearchPrecisionRecallError):
        measure_search_precision_recall([], [], -1)


def test_invalid_high_threshold_raises() -> None:
    with pytest.raises(SearchPrecisionRecallError):
        measure_search_precision_recall([], [], 1, high_threshold=0.0)
    with pytest.raises(SearchPrecisionRecallError):
        measure_search_precision_recall([], [], 1, high_threshold=1.01)


def test_invalid_low_threshold_raises() -> None:
    with pytest.raises(SearchPrecisionRecallError):
        measure_search_precision_recall([], [], 1, low_threshold=-0.1)
    with pytest.raises(SearchPrecisionRecallError):
        measure_search_precision_recall([], [], 1, low_threshold=1.0)


def test_high_must_exceed_low_raises() -> None:
    with pytest.raises(SearchPrecisionRecallError):
        measure_search_precision_recall([], [], 1, high_threshold=0.30, low_threshold=0.30)


# --- purity / determinism / immutability ---------------------------------


def test_deterministic_same_inputs_same_report() -> None:
    returned = ["a", "b", "c"]
    relevant = ["a", "b"]
    assert measure_search_precision_recall(returned, relevant, 5) == \
        measure_search_precision_recall(returned, relevant, 5)


def test_report_is_frozen_immutable() -> None:
    r = measure_search_precision_recall(["a"], ["a"], 1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.verdict = "noisy"  # type: ignore[misc]


def test_notes_carry_context() -> None:
    r = measure_search_precision_recall(["a", "b"], ["a"], 3)
    assert any("precision" in note for note in r.notes)
    assert any("recall" in note for note in r.notes)
