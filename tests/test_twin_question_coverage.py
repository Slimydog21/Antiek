"""Tests for the twin-question-coverage axis (lost-question / recall detection).

Exercises: captured/missed/unmeasurable verdicts, capture rate, the five verdict
states (no_source_questions/unmeasurable/complete/partial/no_capture), best-match
selection, missed_questions evidence, custom threshold, purity/immutability,
validation. Fixtures use BARE NONSENSE TOKENS so Jaccard ratios are exact.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.deep_research_quality.twin_question_coverage import (
    TwinQuestionCoverageError,
    measure_twin_question_coverage,
)
from substrate.research_artifact.schema import (
    ArtifactInsight,
    ArtifactQuestion,
    ResearchArtifactBody,
)


def _twin(
    questions: list[str],
    *,
    investigation_id: str = "inv-twin",
) -> ResearchArtifactBody:
    return ResearchArtifactBody(
        investigation_id=investigation_id,
        problem_question="the question",
        insights=[ArtifactInsight(node_id="i0", text="insight")],
        open_questions=[
            ArtifactQuestion(node_id=f"q{k}", text=t) for k, t in enumerate(questions)
        ],
    )


# --- core: complete capture ------------------------------------------------


def test_complete_capture() -> None:
    source = "alpha beta? gamma delta?"  # 2 source questions
    twin = _twin(["alpha beta", "gamma delta"])  # both near-duplicates
    report = measure_twin_question_coverage(twin, source)
    assert report.source_question_count == 2
    assert report.captured_count == 2
    assert report.missed_count == 0
    assert report.capture_rate == pytest.approx(1.0)
    assert report.verdict == "complete_capture"
    assert report.missed_questions == ()


def test_capture_at_threshold_boundary() -> None:
    # source "alpha beta gamma delta" (4 terms) vs twin "alpha beta": |∩|=2, |∪|=4
    # -> Jaccard 0.50 >= 0.50 threshold -> captured
    source = "alpha beta gamma delta?"
    twin = _twin(["alpha beta"])
    report = measure_twin_question_coverage(twin, source)
    assert report.captured_count == 1
    assert report.capture_rate == pytest.approx(1.0)
    assert report.verdict == "complete_capture"


def test_best_match_among_many_twin_questions() -> None:
    # source "alpha beta gamma" vs ["alpha zeta", "alpha beta gamma delta"]
    # Jaccards: 1/4=0.25, 3/4=0.75 -> best 0.75 >= 0.50 -> captured
    source = "alpha beta gamma?"
    twin = _twin(["alpha zeta", "alpha beta gamma delta"])
    report = measure_twin_question_coverage(twin, source)
    assert report.captured_count == 1
    assert report.missed_count == 0


# --- core: partial capture -------------------------------------------------


def test_partial_capture() -> None:
    source = "alpha beta? gamma delta?"  # 2 source questions
    twin = _twin(["alpha beta"])  # matches q1, drops q2
    report = measure_twin_question_coverage(twin, source)
    assert report.captured_count == 1
    assert report.missed_count == 1
    assert report.capture_rate == pytest.approx(0.5)
    assert report.verdict == "partial_capture"
    assert len(report.missed_questions) == 1
    assert report.missed_questions[0].distinctive_terms == ("delta", "gamma")


# --- core: no capture (honest measured zero) -------------------------------


def test_no_capture_honest_zero() -> None:
    source = "alpha beta gamma?"  # measurable source question
    twin = _twin(["delta epsilon zeta"])  # zero overlap -> Jaccard 0.0
    report = measure_twin_question_coverage(twin, source)
    assert report.captured_count == 0
    assert report.missed_count == 1
    assert report.capture_rate == pytest.approx(0.0)
    assert report.verdict == "no_capture"
    assert len(report.missed_questions) == 1
    assert set(report.missed_questions[0].distinctive_terms) == {
        "alpha", "beta", "gamma"
    }


def test_empty_twin_misses_everything() -> None:
    source = "alpha beta?"  # twin has no questions -> best overlap stays 0.0
    twin = _twin([])
    report = measure_twin_question_coverage(twin, source)
    assert report.twin_question_count == 0
    assert report.missed_count == 1
    assert report.capture_rate == pytest.approx(0.0)
    assert report.verdict == "no_capture"


# --- honesty: no source questions (defer, never fabricated zero) ------------


def test_no_source_questions_defers() -> None:
    source = "alpha beta gamma delta"  # prose, no "?" -> 0 questions
    twin = _twin(["alpha beta"])
    report = measure_twin_question_coverage(twin, source)
    assert report.source_question_count == 0
    assert report.capture_rate is None
    assert report.verdict == "no_source_questions"
    assert report.missed_questions == ()


def test_empty_source_defers() -> None:
    report = measure_twin_question_coverage(_twin(["alpha beta"]), "")
    assert report.source_question_count == 0
    assert report.capture_rate is None
    assert report.verdict == "no_source_questions"


# --- honesty: unmeasurable (all-glue) --------------------------------------


def test_all_glue_questions_unmeasurable() -> None:
    # "why how" / "what where" are all stop-words (interrogatives stripped)
    source = "why how? what where?"
    twin = _twin(["alpha beta"])
    report = measure_twin_question_coverage(twin, source)
    assert report.source_question_count == 2
    assert report.unmeasurable_count == 2
    assert report.capture_rate is None
    assert report.verdict == "unmeasurable"


def test_mixed_measurable_and_unmeasurable() -> None:
    # q1 "alpha beta" measurable (missed, twin empty), q2 "why how" unmeasurable
    source = "alpha beta? why how?"
    twin = _twin([])
    report = measure_twin_question_coverage(twin, source)
    assert report.unmeasurable_count == 1
    assert report.missed_count == 1
    assert report.captured_count == 0
    assert report.capture_rate == pytest.approx(0.0)  # 0 of 1 measurable
    assert report.verdict == "no_capture"
    assert len(report.missed_questions) == 1
    assert set(report.missed_questions[0].distinctive_terms) == {"alpha", "beta"}


# --- custom threshold ------------------------------------------------------


def test_custom_threshold_promotes_miss() -> None:
    # source 4 terms vs twin 2 terms -> Jaccard 0.50
    source = "alpha beta gamma delta?"
    twin = _twin(["alpha beta"])
    loose = measure_twin_question_coverage(twin, source)  # default 0.50 -> captured
    assert loose.captured_count == 1
    strict = measure_twin_question_coverage(
        twin, source, capture_threshold=0.75
    )  # 0.50 < 0.75 -> missed
    assert strict.missed_count == 1
    assert strict.verdict == "no_capture"


def test_custom_threshold_boundary_strict() -> None:
    # source 5 terms vs twin 2 terms -> Jaccard 0.40 < 0.50 -> missed even loose
    source = "alpha beta gamma delta epsilon?"
    twin = _twin(["alpha beta"])
    report = measure_twin_question_coverage(twin, source)
    assert report.missed_count == 1
    assert report.verdict == "no_capture"


# --- validation ------------------------------------------------------------


def test_threshold_below_zero_rejected() -> None:
    with pytest.raises(TwinQuestionCoverageError):
        measure_twin_question_coverage(_twin([]), "alpha beta?", capture_threshold=-0.01)


def test_threshold_above_one_rejected() -> None:
    with pytest.raises(TwinQuestionCoverageError):
        measure_twin_question_coverage(_twin([]), "alpha beta?", capture_threshold=1.01)


# --- purity / immutability -------------------------------------------------


def test_report_is_frozen() -> None:
    report = measure_twin_question_coverage(_twin(["alpha beta"]), "alpha beta?")
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.captured_count = 99  # type: ignore[misc]


def test_deterministic_repeated_calls() -> None:
    twin = _twin(["alpha beta"])
    source = "alpha beta? gamma delta?"
    first = measure_twin_question_coverage(twin, source)
    second = measure_twin_question_coverage(twin, source)
    assert first == second


def test_authority_is_advisory() -> None:
    report = measure_twin_question_coverage(_twin(["alpha beta"]), "alpha beta?")
    assert report.authority == "advisory"


def test_artifact_id_carried() -> None:
    twin = _twin(["alpha beta"], investigation_id="inv-xyz")
    report = measure_twin_question_coverage(twin, "alpha beta?")
    assert report.artifact_id == "inv-xyz"
