"""Tests for the insight→question derivation axis (asks #1/#4).

Measures whether open questions derive from the artifact's own insights (the
recursive note-taker's core loop). Exercises fully_derived/partially_derived/
floating/unknown verdicts, the floating-vs-unknown distinction, orphan insights,
min_overlap gating, all-glue exclusion, validation, purity/immutability.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.insight_question_derivation import (
    InsightText,
    QuestionText,
    measure_insight_question_derivation,
)

# --- unknown (need both sides) --------------------------------------------


def test_unknown_when_no_questions() -> None:
    r = measure_insight_question_derivation(
        [InsightText("i1", "alpha beta")], []
    )
    assert r.verdict == "unknown"
    assert r.measurable_question_count == 0
    assert r.derivation_ratio is None
    assert r.authority == "advisory"


def test_unknown_when_no_insights() -> None:
    r = measure_insight_question_derivation(
        [], [QuestionText("q1", "alpha beta")]
    )
    assert r.verdict == "unknown"
    assert r.measurable_insight_count == 0
    assert r.derivation_ratio is None


def test_unknown_when_all_glue_on_one_side() -> None:
    # All questions are stop-words -> 0 measurable -> unknown.
    r = measure_insight_question_derivation(
        [InsightText("i1", "alpha")], [QuestionText("q1", "the of and")]
    )
    assert r.verdict == "unknown"
    assert r.unmeasurable_question_count == 1


# --- fully_derived --------------------------------------------------------


def test_fully_derived_all_questions_trace_to_insights() -> None:
    r = measure_insight_question_derivation(
        [InsightText("i1", "alpha beta"), InsightText("i2", "gamma delta")],
        [QuestionText("q1", "alpha?"), QuestionText("q2", "gamma echo?")],
    )
    assert r.verdict == "fully_derived"
    assert r.derived_question_count == 2
    assert r.floating_question_count == 0
    assert r.derivation_ratio == 1.0
    assert r.floating_question_ids == ()


def test_fully_derived_boundary_exactly_one() -> None:
    # One question shares exactly 1 term (min_overlap default 1) -> derived.
    r = measure_insight_question_derivation(
        [InsightText("i1", "alpha beta")], [QuestionText("q1", "alpha gamma?")]
    )
    assert r.verdict == "fully_derived"
    assert r.derivation_ratio == 1.0


# --- floating -------------------------------------------------------------


def test_floating_no_question_derives() -> None:
    r = measure_insight_question_derivation(
        [InsightText("i1", "alpha beta")],
        [QuestionText("q1", "gamma?"), QuestionText("q2", "delta?")],
    )
    assert r.verdict == "floating"
    assert r.derived_question_count == 0
    assert r.floating_question_count == 2
    assert r.derivation_ratio == 0.0  # real measured 0.0
    assert r.floating_question_ids == ("q1", "q2")


def test_floating_distinct_from_unknown() -> None:
    # No questions = unknown; questions present but none derive = floating.
    r_unknown = measure_insight_question_derivation(
        [InsightText("i1", "alpha")], []
    )
    r_floating = measure_insight_question_derivation(
        [InsightText("i1", "alpha")], [QuestionText("q1", "beta?")]
    )
    assert r_unknown.verdict == "unknown"
    assert r_floating.verdict == "floating"


# --- partially_derived ----------------------------------------------------


def test_partially_derived_mixed() -> None:
    r = measure_insight_question_derivation(
        [InsightText("i1", "alpha beta")],
        [QuestionText("q1", "alpha?"), QuestionText("q2", "gamma?")],
    )
    assert r.verdict == "partially_derived"
    assert r.derived_question_count == 1
    assert r.floating_question_count == 1
    assert r.derivation_ratio == 0.5
    assert r.floating_question_ids == ("q2",)


def test_partially_derived_one_of_three() -> None:
    r = measure_insight_question_derivation(
        [InsightText("i1", "alpha"), InsightText("i2", "beta")],
        [QuestionText("q1", "alpha?"), QuestionText("q2", "gamma?"), QuestionText("q3", "delta?")],
    )
    assert r.verdict == "partially_derived"
    assert r.derivation_ratio == pytest.approx(1 / 3)


# --- orphan insights (reverse direction) ----------------------------------


def test_orphan_insight_count() -> None:
    # i1 seeds q1 (alpha), i2 seeds nothing -> orphan 1.
    r = measure_insight_question_derivation(
        [InsightText("i1", "alpha"), InsightText("i2", "beta")],
        [QuestionText("q1", "alpha?")],
    )
    assert r.verdict == "fully_derived"
    assert r.orphan_insight_count == 1


def test_no_orphan_insights_when_all_seed() -> None:
    r = measure_insight_question_derivation(
        [InsightText("i1", "alpha"), InsightText("i2", "beta")],
        [QuestionText("q1", "alpha?"), QuestionText("q2", "beta?")],
    )
    assert r.orphan_insight_count == 0


# --- min_overlap ----------------------------------------------------------


def test_min_overlap_gates_derivation() -> None:
    # q1 shares 1 term (alpha); min_overlap 2 -> floating.
    r_default = measure_insight_question_derivation(
        [InsightText("i1", "alpha beta")], [QuestionText("q1", "alpha gamma?")]
    )
    assert r_default.verdict == "fully_derived"
    r_strict = measure_insight_question_derivation(
        [InsightText("i1", "alpha beta")], [QuestionText("q1", "alpha gamma?")],
        min_overlap=2,
    )
    assert r_strict.verdict == "floating"
    assert r_strict.min_overlap == 2


def test_min_overlap_two_allows_two_shared() -> None:
    r = measure_insight_question_derivation(
        [InsightText("i1", "alpha beta gamma")],
        [QuestionText("q1", "alpha beta delta?")],
        min_overlap=2,
    )
    assert r.verdict == "fully_derived"


# --- all-glue exclusion ---------------------------------------------------


def test_all_glue_excluded_from_both_sides() -> None:
    r = measure_insight_question_derivation(
        [
            InsightText("i1", "alpha"),
            InsightText("i2", "the of and"),  # glue -> excluded
        ],
        [
            QuestionText("q1", "alpha?"),
            QuestionText("q2", "is was"),  # glue -> excluded
        ],
    )
    assert r.unmeasurable_insight_count == 1
    assert r.unmeasurable_question_count == 1
    assert r.measurable_insight_count == 1
    assert r.measurable_question_count == 1
    assert r.verdict == "fully_derived"


def test_none_text_treated_as_glue() -> None:
    r = measure_insight_question_derivation(
        [InsightText("i1", None), InsightText("i2", "alpha")],
        [QuestionText("q1", "alpha?")],
    )
    assert r.unmeasurable_insight_count == 1
    assert r.verdict == "fully_derived"


# --- validation -----------------------------------------------------------


def test_invalid_min_overlap_raises() -> None:
    with pytest.raises(ValueError):
        measure_insight_question_derivation([], [], min_overlap=0)
    with pytest.raises(ValueError):
        measure_insight_question_derivation([], [], min_overlap=-1)


# --- purity / determinism / immutability ---------------------------------


def test_deterministic_same_inputs_same_report() -> None:
    insights = [InsightText("i1", "alpha beta")]
    questions = [QuestionText("q1", "alpha?"), QuestionText("q2", "gamma?")]
    assert measure_insight_question_derivation(insights, questions) == \
        measure_insight_question_derivation(insights, questions)


def test_report_is_frozen_immutable() -> None:
    r = measure_insight_question_derivation(
        [InsightText("i1", "alpha")], [QuestionText("q1", "alpha?")]
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.verdict = "floating"  # type: ignore[misc]


def test_notes_carry_context() -> None:
    r = measure_insight_question_derivation(
        [InsightText("i1", "alpha")],
        [QuestionText("q1", "alpha?"), QuestionText("q2", "beta?")],
    )
    assert any("derived" in note for note in r.notes)
    assert any("floating" in note for note in r.notes)
    assert any("orphan" in note for note in r.notes)
