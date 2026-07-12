"""Tests for substrate.deep_research_quality.problem_question_coverage."""

from __future__ import annotations

import math

import pytest

from substrate.deep_research_quality.problem_question_coverage import (
    ProblemQuestionCoverageError,
    ProblemQuestionCoverageReport,
    score_problem_question_coverage,
)
from substrate.research_artifact.schema import (
    ArtifactInsight,
    ResearchArtifactBody,
)


def _body(
    question: str = "What is the impact of scaling laws on reasoning?",
    insights: list[ArtifactInsight] | None = None,
    synthesis: str | None = None,
    investigation_id: str = "inv-1",
) -> ResearchArtifactBody:
    return ResearchArtifactBody(
        investigation_id=investigation_id,
        problem_question=question,
        insights=list(insights) if insights is not None else [],
        synthesis_excerpt=synthesis,
    )


def _insight(node: str, text: str, source: str | None = "src-1") -> ArtifactInsight:
    return ArtifactInsight(node_id=node, text=text, source_document_id=source)


# --- stop-word stripping: the score measures signal words, not grammar ---------


def test_stop_words_stripped_from_question() -> None:
    """Function words don't count; only the question's distinctive terms do."""
    report = score_problem_question_coverage(
        _body(
            question="what is the impact of scaling laws on reasoning",
            insights=[_insight("n1", "scaling laws impact reasoning")],
        )
    )
    # distinctive: {impact, scaling, laws, reasoning}; all 4 in output => 1.0
    assert report.total_distinctive_terms == 4
    assert report.score == 1.0
    assert report.unmatched_terms == ()


def test_stop_word_only_question_is_not_measured() -> None:
    """A question with no signal words has nothing measurable."""
    report = score_problem_question_coverage(
        _body(question="what is the of and the", insights=[_insight("n1", "anything")])
    )
    assert report.measured is False
    assert report.total_distinctive_terms == 0
    assert report.score == 0.0


# --- the drift failure mode: the gap no other axis catches -------------------


def test_drift_unmatched_terms_reported() -> None:
    """Output that misses a key question term shows it as drift."""
    report = score_problem_question_coverage(
        _body(
            question="how do scaling laws affect reasoning and efficiency",
            insights=[_insight("n1", "scaling laws govern reasoning")],
        )
    )
    # distinctive: {scaling, laws, affect, reasoning, efficiency}
    # output covers scaling, laws, reasoning -> misses affect, efficiency
    assert report.total_distinctive_terms == 5
    assert set(report.matched_terms) == {"scaling", "laws", "reasoning"}
    assert set(report.unmatched_terms) == {"affect", "efficiency"}
    assert report.score == pytest.approx(3 / 5)
    assert any("DRIFT" in n for n in report.notes)


def test_synthesis_counts_toward_coverage() -> None:
    """A term present only in the synthesis still counts as covered."""
    report = score_problem_question_coverage(
        _body(
            question="does efficiency matter",
            insights=[_insight("n1", "something else entirely")],
            synthesis="efficiency is the key constraint",
        )
    )
    # distinctive: {efficiency, matter}; efficiency in synthesis, matter absent
    assert "efficiency" in report.matched_terms
    assert "matter" in report.unmatched_terms
    assert report.score == pytest.approx(0.5)


def test_partial_coverage_score_is_exact_ratio() -> None:
    report = score_problem_question_coverage(
        _body(
            question="alpha beta gamma delta epsilon",
            insights=[_insight("n1", "alpha gamma epsilon")],
        )
    )
    # 3 of 5 distinctive present
    assert report.score == pytest.approx(0.6)


# --- orthogonality: nothing to measure --------------------------------------


def test_empty_output_is_not_measured() -> None:
    """No insights and no synthesis => nothing to cover the question with."""
    report = score_problem_question_coverage(
        _body(question="does reasoning scale", insights=[], synthesis=None)
    )
    assert report.measured is False
    assert report.score == 0.0
    # unmatched lists ALL question terms (the whole question is uncovered)
    assert set(report.unmatched_terms) == {"reasoning", "scale"}


def test_empty_question_rejected() -> None:
    with pytest.raises(ProblemQuestionCoverageError):
        score_problem_question_coverage(_body(question="   "))


def test_whitespace_only_synthesis_treated_as_absent() -> None:
    """Synthesis that is only whitespace contributes no tokens."""
    report = score_problem_question_coverage(
        _body(
            question="does reasoning scale",
            insights=[],
            synthesis="   ",
        )
    )
    assert report.measured is False  # no searchable output text


# --- honesty: pure, deterministic, advisory ---------------------------------


def test_pure_and_idempotent() -> None:
    body = _body(
        question="does reasoning scale",
        insights=[_insight("n1", "reasoning scales"), _insight("n2", "scale")],
    )
    assert score_problem_question_coverage(body) == score_problem_question_coverage(body)


def test_authority_is_advisory() -> None:
    report = score_problem_question_coverage(
        _body(question="reasoning", insights=[_insight("n1", "reasoning")])
    )
    assert report.authority == "advisory"


def test_report_is_frozen_value() -> None:
    report = score_problem_question_coverage(
        _body(question="reasoning", insights=[_insight("n1", "reasoning")])
    )
    assert isinstance(report, ProblemQuestionCoverageReport)
    with pytest.raises((AttributeError, Exception)):
        report.score = 0.5  # type: ignore[misc]


def test_investigation_id_carried() -> None:
    report = score_problem_question_coverage(
        _body(
            question="reasoning",
            insights=[_insight("n1", "reasoning")],
            investigation_id="inv-xyz",
        )
    )
    assert report.investigation_id == "inv-xyz"


def test_notes_declare_lexical_scope() -> None:
    report = score_problem_question_coverage(
        _body(question="reasoning", insights=[_insight("n1", "reasoning")])
    )
    assert any("lexical coverage" in n for n in report.notes)
    assert any("LLM-judge" in n for n in report.notes)


# --- dedup + normalization ---------------------------------------------------


def test_repeated_question_term_counted_once() -> None:
    """A term repeated in the question contributes once to the denominator."""
    report = score_problem_question_coverage(
        _body(
            question="reasoning reasoning reasoning",
            insights=[_insight("n1", "reasoning")],
        )
    )
    assert report.total_distinctive_terms == 1
    assert report.score == 1.0


def test_case_and_punctuation_normalized() -> None:
    report = score_problem_question_coverage(
        _body(
            question="Does REASONING Scale?!",
            insights=[_insight("n1", "reasoning scale matters")],
        )
    )
    # distinctive after lowercasing: {reasoning, scale}
    assert report.total_distinctive_terms == 2
    assert report.score == 1.0


def test_non_alphanumeric_tokens_excluded() -> None:
    report = score_problem_question_coverage(
        _body(
            question="c++ vs rust",
            insights=[_insight("n1", "rust is fast")],
        )
    )
    # tokens: c, vs(lowercased) stripped? 'vs' not in stopwords -> distinctive
    # distinctive: {c, vs, rust}; output has {rust} -> 1/3
    assert report.score == pytest.approx(1 / 3)


def test_no_stemming_or_synonymy_lexical_floor() -> None:
    """Lexical = exact token match only; inflections/synonyms count as a miss.

    This is the load-bearing honesty property: the score is a coverage FLOOR,
    not semantic relevance. A stemmer or synonym map would mask drift behind a
    false match; pure tokenization surfaces it honestly (notes flag LLM-judge
    as the only path to semantic relevance).
    """
    report = score_problem_question_coverage(
        _body(
            question="impact of scaling",  # distinctive: {impact, scaling}
            insights=[_insight("n1", "effects of scale")],  # synonym + inflection
        )
    )
    assert set(report.unmatched_terms) == {"impact", "scaling"}
    assert report.score == 0.0
    assert any("DRIFT" in n for n in report.notes)


def test_score_in_unit_interval() -> None:
    """Score is always a finite float in [0, 1]."""
    bodies = [
        _body(question="reasoning", insights=[]),  # no output
        _body(question="the of and", insights=[_insight("n", "x")]),  # no signal
        _body(
            question="alpha beta gamma",
            insights=[_insight("n", "alpha beta gamma")],
        ),
    ]
    for body in bodies:
        report = score_problem_question_coverage(body)
        assert isinstance(report.score, float)
        assert math.isfinite(report.score)
        assert 0.0 <= report.score <= 1.0
