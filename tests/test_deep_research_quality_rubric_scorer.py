"""Tests for the deep-research quality rubric scorer.

Each test locks one falsifiable honesty invariant from the spec.
"""

from __future__ import annotations

import math

import pytest

from substrate.deep_research_quality.rubric_scorer import (
    DRQualityScore,
    RubricAxisScore,
    score_deep_research_quality,
)
from substrate.research_artifact.schema import (
    ArtifactInsight,
    ArtifactQuestion,
    ResearchArtifactBody,
)


def _body(
    *,
    investigation_id: str = "inv-1",
    insights: list[ArtifactInsight] | None = None,
    open_questions: list[ArtifactQuestion] | None = None,
    synthesis_excerpt: str | None = None,
    synthesis_withheld: bool = False,
    source_event_ids: list[str] | None = None,
) -> ResearchArtifactBody:
    return ResearchArtifactBody(
        investigation_id=investigation_id,
        problem_question="What is X?",
        insights=insights or [],
        open_questions=open_questions or [],
        synthesis_excerpt=synthesis_excerpt,
        synthesis_withheld=synthesis_withheld,
        source_event_ids=source_event_ids or [],
        agent_notes=[],
    )


def _axis(score: DRQualityScore, name: str) -> RubricAxisScore:
    for a in score.axes:
        if a.axis == name:
            return a
    raise AssertionError(f"axis {name} missing")


def test_scores_always_finite_in_unit_range_even_with_huge_counts() -> None:
    # Invariant 1: score finite in [0,1]; clamp, never overflow.
    huge = [ArtifactInsight(node_id=f"n{i}", text="t") for i in range(100_000)]
    body = _body(insights=huge)
    score = score_deep_research_quality(body)
    for a in score.axes:
        assert math.isfinite(a.score)
        assert 0.0 <= a.score <= 1.0
    assert math.isfinite(score.overall)
    assert 0.0 <= score.overall <= 1.0


def test_unmeasured_axes_excluded_from_overall() -> None:
    # Invariant 2: measured=False axes contribute 0.0 and are excluded from mean.
    body = _body(
        synthesis_withheld=True,  # grounding unmeasurable
        insights=[ArtifactInsight(node_id="n1", text="t", source_document_id="d1")],
        open_questions=[ArtifactQuestion(node_id="q1", text="q?")],
    )
    score = score_deep_research_quality(body)
    grounding = _axis(score, "grounding_completeness")
    assert grounding.measured is False
    assert grounding.score == 0.0
    # citation_density=1.0 (1/1 cited), uncertainty=1.0, synth_present=0.0;
    # grounding AND conflict_resolution excluded (no synthesis to evaluate) → 3 measured axes
    expected = (1.0 + 1.0 + 0.0) / 3
    assert score.overall == pytest.approx(expected)
    assert score.measured_count == 3
    conflict = _axis(score, "conflict_resolution")
    assert conflict.measured is False


def test_empty_artifact_does_not_raise_and_overall_zero() -> None:
    # Invariant 3: empty artifact never raises; citation_density unmeasurable.
    body = _body()  # no insights, no synthesis, no questions
    score = score_deep_research_quality(body)
    assert score.overall == 0.0
    citation = _axis(score, "citation_density")
    assert citation.measured is False
    # uncertainty + synthesis_present are measured; conflict needs synthesis (unmeasured)
    assert score.measured_count == 2
    assert _axis(score, "conflict_resolution").measured is False
    assert _axis(score, "uncertainty_surfacing").score == 0.0
    assert _axis(score, "synthesis_present").score == 0.0


def test_scores_derivable_and_deterministic() -> None:
    # Invariant 4: same input -> same output; reasons are deterministic.
    body = _body(
        insights=[
            ArtifactInsight(node_id="n1", text="t", source_document_id="d1"),
            ArtifactInsight(node_id="n2", text="t"),  # uncited
        ],
        open_questions=[ArtifactQuestion(node_id="q1", text="q?")],
        synthesis_excerpt="The claim holds, however with caveats.",
    )
    s1 = score_deep_research_quality(body)
    s2 = score_deep_research_quality(body)
    assert s1 == s2
    citation = _axis(s1, "citation_density")
    assert citation.score == 0.5  # 1 of 2 cited
    assert "1/2" in citation.reason
    conflict = _axis(s1, "conflict_resolution")
    assert conflict.score == 1.0
    assert "however" in conflict.reason or "caveat" in conflict.reason


def test_authority_advisory_no_mutation_marker() -> None:
    # Invariant 5: authority is advisory; the function is pure (no mutation).
    body = _body(synthesis_excerpt="plain synthesis text")
    score = score_deep_research_quality(body)
    assert score.authority == "deep_research_quality_rubric_advisory"
    # conflict_resolution with no marker is neutral 0.5, not a failure
    conflict = _axis(score, "conflict_resolution")
    assert conflict.score == 0.5


def test_booleans_never_coerce_to_scores() -> None:
    # Invariant 6: scores are explicit literals/clamped arithmetic, not float(bool).
    body = _body(
        insights=[ArtifactInsight(node_id="n1", text="t", source_document_id="d1")],
        synthesis_excerpt="grounded",
        open_questions=[ArtifactQuestion(node_id="q1", text="q?")],
    )
    score = score_deep_research_quality(body)
    # grounding_completeness: measured, non-empty excerpt -> 1.0 (explicit literal)
    grounding = _axis(score, "grounding_completeness")
    assert grounding.score == 1.0
    # synthesis_present: present -> 1.0 (explicit literal)
    synth = _axis(score, "synthesis_present")
    assert synth.score == 1.0
    # citation_density: 1/1 -> 1.0 (clamped arithmetic)
    assert _axis(score, "citation_density").score == 1.0
    assert score.investigation_id == "inv-1"
    assert len(score.axes) == 5
