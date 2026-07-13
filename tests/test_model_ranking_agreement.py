"""Tests for the model ranking-agreement axis (ask #11)."""

from __future__ import annotations

import math
from dataclasses import FrozenInstanceError

import pytest

from substrate.model_ranking_agreement import (
    ModelRankingAgreementReport,
    measure_model_ranking_agreement,
)

# Three canonical tasks ranked identically by both models.
_CONCORD = (
    [("t1", 0.9), ("t2", 0.5), ("t3", 0.1)],
    [("t1", 0.8), ("t2", 0.4), ("t3", 0.2)],
)


def test_no_shared_tasks_is_unknown() -> None:
    report = measure_model_ranking_agreement([("x", 0.1)], [("y", 0.2)])
    assert report.verdict == "unknown"
    assert report.shared_task_count == 0
    assert report.kendall_tau is None
    assert report.agreement_ratio is None
    assert report.dropped_from_a == 1
    assert report.dropped_from_b == 1
    assert report.dropped_labels_a == ("x",)
    assert report.dropped_labels_b == ("y",)
    assert report.concordant_pairs == 0
    assert report.authority == "advisory"


def test_single_shared_task_is_base_case() -> None:
    report = measure_model_ranking_agreement([("t1", 0.5)], [("t1", 0.7)])
    assert report.verdict == "single_task"
    assert report.shared_task_count == 1
    assert report.kendall_tau is None
    assert report.agreement_ratio is None
    assert report.rank_ordering_a == ("t1",)
    assert report.rank_ordering_b == ("t1",)


def test_perfect_concordance_tau_one() -> None:
    # 3 shared, all 3 pairs same sign -> tau = (3-0)/sqrt(3*3) = 1.0
    report = measure_model_ranking_agreement(*_CONCORD)
    assert report.verdict == "concordant_ranking"
    assert report.shared_task_count == 3
    assert report.concordant_pairs == 3
    assert report.discordant_pairs == 0
    assert report.tie_pairs_a == 0
    assert report.tie_pairs_b == 0
    assert report.kendall_tau == pytest.approx(1.0)
    assert report.agreement_ratio == pytest.approx(1.0)
    assert report.rank_ordering_a == ("t1", "t2", "t3")
    assert report.rank_ordering_b == ("t1", "t2", "t3")


def test_perfect_inversion_tau_negative_one() -> None:
    # B inverts the ordering -> all 3 pairs discordant -> tau = (0-3)/3 = -1.0
    a = [("t1", 0.9), ("t2", 0.5), ("t3", 0.1)]
    b = [("t1", 0.1), ("t2", 0.5), ("t3", 0.9)]
    report = measure_model_ranking_agreement(a, b)
    assert report.verdict == "inverted_ranking"
    assert report.concordant_pairs == 0
    assert report.discordant_pairs == 3
    assert report.kendall_tau == pytest.approx(-1.0)
    assert report.agreement_ratio == pytest.approx(0.0)
    assert report.rank_ordering_b == ("t3", "t2", "t1")


def test_mixed_ordering_is_independent() -> None:
    # 2 concordant, 1 discordant -> tau = (2-1)/3 ~= 0.333 (between thresholds)
    a = [("t1", 0.9), ("t2", 0.5), ("t3", 0.1)]
    b = [("t1", 0.5), ("t2", 0.9), ("t3", 0.1)]
    report = measure_model_ranking_agreement(a, b)
    assert report.verdict == "independent_ranking"
    assert report.concordant_pairs == 2
    assert report.discordant_pairs == 1
    assert report.kendall_tau == pytest.approx(1 / 3)
    assert report.agreement_ratio == pytest.approx(2 / 3)


def test_near_zero_real_tau_is_carried_not_deferred() -> None:
    # independent carries a REAL measured tau, never None
    report = measure_model_ranking_agreement(
        [("t1", 0.9), ("t2", 0.5), ("t3", 0.1)],
        [("t1", 0.5), ("t2", 0.9), ("t3", 0.1)],
    )
    assert report.kendall_tau is not None
    assert report.kendall_tau == pytest.approx(1 / 3)


def test_all_tie_in_one_model_is_unmeasurable() -> None:
    # A ties every pair -> denom_sq = (3-3)*(3-0) = 0 -> tau undefined -> unmeasurable
    a = [("t1", 0.5), ("t2", 0.5), ("t3", 0.5)]
    b = [("t1", 0.9), ("t2", 0.5), ("t3", 0.1)]
    report = measure_model_ranking_agreement(a, b)
    assert report.verdict == "unmeasurable"
    assert report.kendall_tau is None
    assert report.tie_pairs_a == 3
    assert report.tie_pairs_b == 0
    assert report.concordant_pairs == 0
    assert report.agreement_ratio is None  # zero comparable pairs


def test_partial_tie_in_b_still_concordant() -> None:
    # (t1,t2) tied in B -> tie_b=1; 2 concordant -> tau = 2/sqrt(6) ~= 0.8165
    a = [("t1", 0.9), ("t2", 0.5), ("t3", 0.1)]
    b = [("t1", 0.5), ("t2", 0.5), ("t3", 0.1)]
    report = measure_model_ranking_agreement(a, b)
    assert report.verdict == "concordant_ranking"
    assert report.concordant_pairs == 2
    assert report.discordant_pairs == 0
    assert report.tie_pairs_a == 0
    assert report.tie_pairs_b == 1
    assert report.kendall_tau == pytest.approx(2 / math.sqrt(6))
    assert report.agreement_ratio == pytest.approx(1.0)


def test_dropped_tasks_surfaced_and_auditable() -> None:
    # shared {t1,t2}; t4 only in A, t3 only in B
    a = [("t1", 0.9), ("t2", 0.5), ("t4", 0.3)]
    b = [("t1", 0.8), ("t2", 0.4), ("t3", 0.2)]
    report = measure_model_ranking_agreement(a, b)
    assert report.shared_task_count == 2
    assert report.dropped_from_a == 1
    assert report.dropped_labels_a == ("t4",)
    assert report.dropped_from_b == 1
    assert report.dropped_labels_b == ("t3",)
    # one pair, concordant -> tau 1.0
    assert report.concordant_pairs == 1
    assert report.kendall_tau == pytest.approx(1.0)
    assert report.verdict == "concordant_ranking"


def test_rank_ordering_ties_broken_by_label_asc() -> None:
    # A: c=0.9 best, then a=0.5,b=0.5 tie -> label asc -> (c, a, b)
    a = [("b", 0.5), ("a", 0.5), ("c", 0.9)]
    b = [("a", 0.1), ("b", 0.2), ("c", 0.3)]
    report = measure_model_ranking_agreement(a, b)
    assert report.rank_ordering_a == ("c", "a", "b")
    assert report.rank_ordering_b == ("c", "b", "a")


def test_custom_thresholds_change_verdict_boundary() -> None:
    # tau ~= 0.333: independent at +/-0.6, concordant at 0.3, inverted at 0.4? no (0.333<0.4)
    a = [("t1", 0.9), ("t2", 0.5), ("t3", 0.1)]
    b = [("t1", 0.5), ("t2", 0.9), ("t3", 0.1)]
    assert measure_model_ranking_agreement(a, b, concordance_threshold=0.6).verdict == "independent_ranking"
    assert measure_model_ranking_agreement(a, b, concordance_threshold=0.3).verdict == "concordant_ranking"


def test_threshold_validation_rejects_out_of_range() -> None:
    a = [("t1", 0.5)]
    b = [("t1", 0.5)]
    with pytest.raises(ValueError, match="concordance_threshold"):
        measure_model_ranking_agreement(a, b, concordance_threshold=0.0)
    with pytest.raises(ValueError, match="concordance_threshold"):
        measure_model_ranking_agreement(a, b, concordance_threshold=1.5)
    with pytest.raises(ValueError, match="discordance_threshold"):
        measure_model_ranking_agreement(a, b, discordance_threshold=0.0)
    with pytest.raises(ValueError, match="discordance_threshold"):
        measure_model_ranking_agreement(a, b, discordance_threshold=-1.5)


def test_report_is_frozen_and_deterministic() -> None:
    first = measure_model_ranking_agreement(*_CONCORD)
    second = measure_model_ranking_agreement(*_CONCORD)
    assert first == second  # deterministic + value-equal (frozen dataclass)
    with pytest.raises(FrozenInstanceError):
        first.verdict = "tampered"  # type: ignore[misc]


def test_report_type_and_fields_complete() -> None:
    report: ModelRankingAgreementReport = measure_model_ranking_agreement(*_CONCORD)
    assert isinstance(report, ModelRankingAgreementReport)
    assert isinstance(report.rank_ordering_a, tuple)
    assert isinstance(report.dropped_labels_a, tuple)
    assert isinstance(report.notes, tuple)
    assert report.concordance_threshold == 0.60
    assert report.discordance_threshold == -0.60
    assert report.authority == "advisory"
