"""Tests for substrate.deep_research_quality.source_diversity — breadth+evenness axis."""

from __future__ import annotations

import math

import pytest

from substrate.deep_research_quality.source_diversity import (
    SourceDiversityError,
    SourceDiversityReport,
    score_source_diversity,
)
from substrate.research_artifact.schema import (
    ArtifactInsight,
    ResearchArtifactBody,
)


def _body(
    insights: list[ArtifactInsight], investigation_id: str = "inv-1"
) -> ResearchArtifactBody:
    return ResearchArtifactBody(
        investigation_id=investigation_id,
        problem_question="What makes a deep research output high quality?",
        insights=list(insights),
    )


def _insight(node: str, source: str | None, text: str = "t") -> ArtifactInsight:
    return ArtifactInsight(node_id=node, text=text, source_document_id=source)


# --- orthogonality: ungrounded artifact defers to citation_density ----------


def test_no_sources_is_not_measured() -> None:
    """Zero grounded insights => diversity of nothing is unknown, never fabricated."""
    report = score_source_diversity(_body([_insight("n1", None), _insight("n2", None)]))

    assert report.measured is False
    assert report.score == 0.0
    assert report.distinct_source_count == 0
    assert report.total_cited_insights == 0
    assert report.total_insights == 2
    assert report.monoculture is False


def test_blank_source_ids_excluded_as_ungrounded() -> None:
    """A blank/whitespace source id is ungrounded, not a source."""
    report = score_source_diversity(
        _body([_insight("n1", "   "), _insight("n2", "src-A")])
    )

    assert report.total_cited_insights == 1
    assert report.distinct_source_count == 1
    assert report.measured is True


# --- monoculture: the failure mode citation_density cannot see --------------


def test_monoculture_all_one_source_scores_zero() -> None:
    """20 insights all citing ONE source: grounded (passes density) but a monoculture."""
    insights = [_insight(f"n{i}", "src-only") for i in range(20)]
    report = score_source_diversity(_body(insights))

    assert report.measured is True
    assert report.score == 0.0  # all same source => P(two differ) = 0
    assert report.distinct_source_count == 1
    assert report.evenness is None  # single source has no distribution to balance
    assert report.top_source_share == 1.0
    assert report.monoculture is True
    assert any("MONOCULTURE" in n for n in report.notes)


def test_dominant_source_90pct_is_monoculture() -> None:
    # 9 insights cite src-A, 1 cites src-B => top share 0.9 >= 0.80 threshold
    insights = [_insight(f"a{i}", "src-A") for i in range(9)] + [_insight("b1", "src-B")]
    report = score_source_diversity(_body(insights))

    assert report.monoculture is True
    assert report.distinct_source_count == 2
    assert report.top_source_share == pytest.approx(0.9)
    assert report.evenness is not None
    assert report.evenness < 1.0  # unbalanced


def test_balanced_two_sources_not_monoculture() -> None:
    insights = [_insight(f"a{i}", "src-A") for i in range(5)] + [
        _insight(f"b{i}", "src-B") for i in range(5)
    ]
    report = score_source_diversity(_body(insights))

    assert report.monoculture is False  # top share 0.5 < 0.80
    assert report.top_source_share == 0.5
    assert report.evenness == 1.0  # perfectly balanced


# --- breadth + evenness: the Gini-Simpson score ----------------------------


def test_all_distinct_sources_maximizes_score() -> None:
    """Every insight a unique source => maximal diversity for that count."""
    insights = [_insight(f"n{i}", f"src-{i}") for i in range(6)]
    report = score_source_diversity(_body(insights))

    assert report.distinct_source_count == 6
    assert report.evenness == 1.0
    # Gini-Simpson with n equally-common = 1 - 1/n = (n-1)/n
    assert report.score == pytest.approx(1.0 - 1.0 / 6.0)
    assert report.score < 1.0  # honest ceiling: never a spurious 1.0


def test_score_is_probability_two_draws_differ() -> None:
    """Gini-Simpson = 1 - sum(p^2) = P(two random cited insights differ)."""
    # 3 src-A, 1 src-B => shares 0.75, 0.25 => 1 - (0.5625 + 0.0625) = 0.375
    insights = [_insight("a1", "A"), _insight("a2", "A"), _insight("a3", "A"), _insight("b1", "B")]
    report = score_source_diversity(_body(insights))

    assert report.score == pytest.approx(0.375)


def test_more_breadth_scores_higher_at_equal_evenness() -> None:
    """10 distinct > 2 distinct when both are perfectly even."""
    two = score_source_diversity(
        _body([_insight("a", "A"), _insight("b", "B")])
    )
    ten = score_source_diversity(
        _body([_insight(f"n{i}", f"src-{i}") for i in range(10)])
    )
    assert two.evenness == 1.0
    assert ten.evenness == 1.0
    assert ten.score > two.score  # breadth raises the combined score


def test_evenness_independent_of_count() -> None:
    """2 sources 50/50 and 4 sources 25/25/25/25 both have evenness 1.0."""
    two = score_source_diversity(_body([_insight("a", "A"), _insight("b", "B")]))
    four = score_source_diversity(
        _body([_insight("a", "A"), _insight("b", "B"), _insight("c", "C"), _insight("d", "D")])
    )
    assert two.evenness == 1.0
    assert four.evenness == 1.0
    assert four.distinct_source_count > two.distinct_source_count  # breadth differs


# --- honesty: pure, deterministic, advisory --------------------------------


def test_pure_and_idempotent() -> None:
    body = _body([_insight("a", "A"), _insight("b", "B"), _insight("c", "A")])
    assert score_source_diversity(body) == score_source_diversity(body)


def test_authority_is_advisory() -> None:
    report = score_source_diversity(_body([_insight("a", "A"), _insight("b", "B")]))
    assert report.authority == "advisory"


def test_report_is_frozen_value() -> None:
    report = score_source_diversity(_body([_insight("a", "A")]))
    assert isinstance(report, SourceDiversityReport)
    # frozen dataclass: cannot reassign
    with pytest.raises((AttributeError, Exception)):
        report.score = 0.5  # type: ignore[misc]


def test_investigation_id_carried() -> None:
    report = score_source_diversity(
        _body([_insight("a", "A")], investigation_id="inv-xyz")
    )
    assert report.investigation_id == "inv-xyz"


def test_notes_honest_about_ceiling() -> None:
    report = score_source_diversity(_body([_insight("a", "A"), _insight("b", "B")]))
    assert any("(n-1)/n" in n for n in report.notes)


# --- input validation ------------------------------------------------------


def test_mixed_grounded_and_ungrounded_only_cited_count() -> None:
    insights = [_insight("a", "A"), _insight("b", "A"), _insight("c", None), _insight("d", "  ")]
    report = score_source_diversity(_body(insights))

    assert report.total_insights == 4
    assert report.total_cited_insights == 2  # only the two src-A
    assert report.distinct_source_count == 1
    assert report.score == 0.0  # both cite the same source


def test_monoculture_dominance_threshold_is_configurable() -> None:
    # 70/30 split: not a monoculture at 0.80, IS at 0.60
    insights = [_insight(f"a{i}", "A") for i in range(7)] + [
        _insight(f"b{i}", "B") for i in range(3)
    ]
    loose = score_source_diversity(_body(insights), monoculture_dominance=0.60)
    strict = score_source_diversity(_body(insights), monoculture_dominance=0.80)
    assert loose.monoculture is True
    assert strict.monoculture is False


@pytest.mark.parametrize("bad", [0.0, -0.1, 1.5, float("nan")])
def test_bad_dominance_rejected(bad: float) -> None:
    with pytest.raises(SourceDiversityError):
        score_source_diversity(_body([_insight("a", "A")]), monoculture_dominance=bad)


def test_score_in_unit_interval() -> None:
    """The score is always a finite float in [0, 1]."""
    bodies = [
        _body([_insight("a", None)]),  # ungrounded
        _body([_insight("a", "A")]),  # single
        _body([_insight(f"n{i}", f"src-{i}") for i in range(50)]),  # all distinct
    ]
    for body in bodies:
        report = score_source_diversity(body)
        assert isinstance(report.score, float)
        assert math.isfinite(report.score)
        assert 0.0 <= report.score <= 1.0
