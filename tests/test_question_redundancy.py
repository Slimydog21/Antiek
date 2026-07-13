"""Tests for the question-redundancy axis (near-dup questions — asks #1/#3/#4).

Pure lexical arithmetic — distinctive terms (stop-words stripped), Jaccard by hand.
Use alpha/beta/gamma nonsense tokens so every ratio is exactly countable.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.question_redundancy import (
    OpenQuestionText,
    QuestionRedundancyError,
    measure_question_redundancy,
)


def qs(*pairs: tuple[str, str]) -> list[OpenQuestionText]:
    return [OpenQuestionText(node_id=nid, text=t) for nid, t in pairs]


# --- redundant (>=1 flagged pair) -----------------------------------------


def test_redundant_near_duplicate_pair() -> None:
    # Two questions with identical distinctive terms -> Jaccard 1.0 >= 0.70.
    report = measure_question_redundancy(qs(("q1", "alpha beta gamma"), ("q2", "alpha beta gamma")))
    assert report.verdict == "redundant"
    assert len(report.redundant_pairs) == 1
    assert report.redundant_pairs[0].similarity == 1.0
    assert report.max_similarity == 1.0
    assert report.redundancy_ratio == 1.0
    assert set(report.implicated_question_ids) == {"q1", "q2"}
    assert report.authority == "advisory"


def test_redundant_high_overlap_above_threshold() -> None:
    # q1={alpha,beta,gamma,delta}, q2={alpha,beta,gamma,echo} -> intersection 3, union 5 -> 0.60 < 0.70.
    report = measure_question_redundancy(qs(("q1", "alpha beta gamma delta"), ("q2", "alpha beta gamma echo")))
    assert report.verdict == "distinct"  # 0.60 below threshold
    assert report.max_similarity == pytest.approx(0.60)


def test_redundant_at_threshold_boundary_is_a_hit() -> None:
    # Jaccard exactly 0.70 -> flagged (>= boundary).
    # intersection 7, union 10 -> 0.70.
    q1 = "alpha beta gamma delta echo foxtrot golf"
    q2 = "alpha beta gamma delta echo foxtrot golf hotel india juliet"
    report = measure_question_redundancy(qs(("q1", q1), ("q2", q2)))
    assert report.verdict == "redundant"
    assert report.redundant_pairs[0].similarity == pytest.approx(0.70)


# --- distinct (zero flagged, measured) ------------------------------------


def test_distinct_disjoint_questions() -> None:
    report = measure_question_redundancy(qs(("q1", "alpha beta"), ("q2", "gamma delta")))
    assert report.verdict == "distinct"
    assert len(report.redundant_pairs) == 0
    assert report.max_similarity == 0.0
    assert report.redundancy_ratio == 0.0


def test_distinct_partial_overlap_below_threshold() -> None:
    # intersection 1, union 3 -> 0.333 < 0.70.
    report = measure_question_redundancy(qs(("q1", "alpha beta"), ("q2", "alpha gamma")))
    assert report.verdict == "distinct"
    assert report.max_similarity == pytest.approx(1 / 3)


def test_distinct_is_not_unknown() -> None:
    # Two measurable questions, zero overlap -> distinct (measured), NOT unknown.
    report = measure_question_redundancy(qs(("q1", "alpha"), ("q2", "beta")))
    assert report.verdict == "distinct"
    assert report.redundancy_ratio == 0.0  # real measured, not None


# --- unknown (load-bearing: <2 measurable) -------------------------------


def test_unknown_when_one_question() -> None:
    report = measure_question_redundancy(qs(("q1", "alpha beta")))
    assert report.verdict == "unknown"
    assert report.redundancy_ratio is None
    assert report.max_similarity is None


def test_unknown_when_zero_questions() -> None:
    report = measure_question_redundancy([])
    assert report.verdict == "unknown"


def test_unknown_when_all_glue_questions() -> None:
    report = measure_question_redundancy(qs(("q1", "the and of"), ("q2", "is are was")))
    assert report.verdict == "unknown"
    assert report.unmeasurable_count == 2
    assert report.measurable_question_count == 0


def test_all_glue_excluded_from_measurement() -> None:
    # One real + one all-glue -> only 1 measurable -> unknown.
    report = measure_question_redundancy(qs(("q1", "alpha beta"), ("q2", "the and of")))
    assert report.verdict == "unknown"
    assert report.unmeasurable_count == 1
    assert report.measurable_question_count == 1


# --- implicated + ratio across multiple pairs -----------------------------


def test_three_questions_two_redundant() -> None:
    # q1==q2 (identical), q3 distinct -> q1,q2 implicated; ratio 2/3.
    report = measure_question_redundancy(qs(
        ("q1", "alpha beta"), ("q2", "alpha beta"), ("q3", "gamma delta"),
    ))
    assert report.verdict == "redundant"
    assert len(report.redundant_pairs) == 1
    assert set(report.implicated_question_ids) == {"q1", "q2"}
    assert report.redundancy_ratio == pytest.approx(2 / 3)


def test_all_three_redundant_chain() -> None:
    # q1==q2==q3 identical -> 3 pairs flagged, all implicated, ratio 1.0.
    report = measure_question_redundancy(qs(
        ("q1", "alpha beta"), ("q2", "alpha beta"), ("q3", "alpha beta"),
    ))
    assert report.verdict == "redundant"
    assert len(report.redundant_pairs) == 3
    assert report.redundancy_ratio == 1.0


# --- max_similarity carried even below threshold --------------------------


def test_max_similarity_carried_below_threshold() -> None:
    # 0.60 overlap, below 0.70 threshold — distinct, but max_similarity reported.
    report = measure_question_redundancy(qs(("q1", "alpha beta gamma delta"), ("q2", "alpha beta gamma echo")))
    assert report.verdict == "distinct"
    assert report.max_similarity is not None
    assert report.max_similarity == pytest.approx(0.60)


# --- shared terms auditable -----------------------------------------------


def test_shared_terms_listed_in_pair() -> None:
    report = measure_question_redundancy(qs(("q1", "alpha beta gamma"), ("q2", "alpha beta gamma")))
    pair = report.redundant_pairs[0]
    assert pair.shared_terms == ("alpha", "beta", "gamma")


# --- stop-word floor + case -----------------------------------------------


def test_stop_words_stripped() -> None:
    report = measure_question_redundancy(qs(("q1", "what is alpha beta"), ("q2", "the alpha beta")))
    # distinctive {alpha, beta} in both -> Jaccard 1.0 -> redundant.
    assert report.verdict == "redundant"
    assert report.max_similarity == 1.0


def test_case_insensitive() -> None:
    report = measure_question_redundancy(qs(("q1", "ALPHA Beta"), ("q2", "alpha BETA")))
    assert report.verdict == "redundant"


# --- custom threshold -----------------------------------------------------


def test_custom_threshold_flags_lower_overlap() -> None:
    # 0.60 overlap -> distinct at default 0.70, redundant at threshold 0.50.
    questions = qs(("q1", "alpha beta gamma delta"), ("q2", "alpha beta gamma echo"))
    assert measure_question_redundancy(questions).verdict == "distinct"
    assert measure_question_redundancy(questions, threshold=0.50).verdict == "redundant"


# --- validation -----------------------------------------------------------


def test_threshold_out_of_range_raises() -> None:
    with pytest.raises(QuestionRedundancyError, match="threshold"):
        measure_question_redundancy([], threshold=1.5)
    with pytest.raises(QuestionRedundancyError, match="threshold"):
        measure_question_redundancy([], threshold=-0.1)


def test_empty_node_id_raises() -> None:
    with pytest.raises(QuestionRedundancyError, match="node_id"):
        measure_question_redundancy([OpenQuestionText(node_id="  ", text="alpha")])


def test_duplicate_node_id_raises() -> None:
    with pytest.raises(QuestionRedundancyError, match="duplicate node_id"):
        measure_question_redundancy(qs(("q1", "alpha"), ("q1", "beta")))


# --- purity / determinism -------------------------------------------------


def test_report_is_frozen_and_advisory() -> None:
    report = measure_question_redundancy(qs(("q1", "alpha"), ("q2", "beta")))
    assert report.authority == "advisory"
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.verdict = "tampered"  # type: ignore[misc]


def test_deterministic_same_inputs_same_report() -> None:
    questions = qs(("q1", "alpha beta"), ("q2", "alpha gamma"), ("q3", "delta echo"))
    first = measure_question_redundancy(questions)
    second = measure_question_redundancy(questions)
    assert first == second


def test_notes_carry_provenance() -> None:
    report = measure_question_redundancy(qs(("q1", "alpha beta"), ("q2", "alpha beta")))
    joined = " ".join(report.notes)
    assert "question-redundancy" in joined
    assert "verdict redundant" in joined
