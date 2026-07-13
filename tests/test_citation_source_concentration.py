"""Tests for the citation-source-concentration axis (HHI over cited sources).

Exercises: HHI values (hand-computed), effective_source_count, the four verdict
states (unknown/single_source/concentrated/diverse), dominant-source identification,
auditable source_breakdown, uncited-insight exclusion, custom-threshold
reclassification, boundary behavior, validation, purity/immutability. Fixtures use
bare source ids so HHI values are exact.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.citation_source_concentration import (
    CitationSourceConcentrationError,
    measure_citation_source_concentration,
)
from substrate.research_artifact.schema import (
    ArtifactInsight,
    ArtifactQuestion,
    ResearchArtifactBody,
)


def _artifact(
    sources: list[str | None],
    *,
    investigation_id: str = "inv-test",
) -> ResearchArtifactBody:
    """Build an artifact whose insights cite the given source_document_ids.

    ``None`` entries produce uncited insights (no source_document_id).
    """
    return ResearchArtifactBody(
        investigation_id=investigation_id,
        problem_question="the question",
        insights=[
            ArtifactInsight(node_id=f"i{k}", text=f"insight {k}", source_document_id=sid)
            for k, sid in enumerate(sources)
        ],
        open_questions=[ArtifactQuestion(node_id="q0", text="a question")],
    )


# --- core: single source (monoculture) -------------------------------------


def test_single_source_monoculture() -> None:
    report = measure_citation_source_concentration(_artifact(["S1", "S1", "S1"]))
    assert report.cited_insight_count == 3
    assert report.distinct_source_count == 1
    assert report.source_concentration_hhi == pytest.approx(1.0)
    assert report.effective_source_count == pytest.approx(1.0)
    assert report.dominant_source_id == "S1"
    assert report.dominant_source_share == pytest.approx(1.0)
    assert report.verdict == "single_source"


def test_single_source_one_insight() -> None:
    report = measure_citation_source_concentration(_artifact(["S1"]))
    assert report.distinct_source_count == 1
    assert report.source_concentration_hhi == pytest.approx(1.0)
    assert report.verdict == "single_source"


# --- core: concentrated (HHI >= threshold) ---------------------------------


def test_two_sources_even_split_at_threshold() -> None:
    # S1: 3, S2: 3 -> HHI = 0.25 + 0.25 = 0.50 >= 0.50 -> concentrated
    report = measure_citation_source_concentration(_artifact(["S1", "S1", "S1", "S2", "S2", "S2"]))
    assert report.distinct_source_count == 2
    assert report.source_concentration_hhi == pytest.approx(0.5)
    assert report.effective_source_count == pytest.approx(2.0)
    assert report.verdict == "concentrated"


def test_dominant_source_skewed() -> None:
    # S1: 4, S2: 1 -> HHI = 0.64 + 0.04 = 0.68
    report = measure_citation_source_concentration(_artifact(["S1", "S1", "S1", "S1", "S2"]))
    assert report.source_concentration_hhi == pytest.approx(0.68)
    assert report.effective_source_count == pytest.approx(1.0 / 0.68)
    assert report.dominant_source_id == "S1"
    assert report.dominant_source_share == pytest.approx(0.8)
    assert report.verdict == "concentrated"


# --- core: diverse (HHI < threshold) ---------------------------------------


def test_three_sources_even_diverse() -> None:
    # S1: 2, S2: 2, S3: 2 -> HHI = 3 * (1/3)^2 = 1/3
    report = measure_citation_source_concentration(
        _artifact(["S1", "S1", "S2", "S2", "S3", "S3"])
    )
    assert report.distinct_source_count == 3
    assert report.source_concentration_hhi == pytest.approx(1.0 / 3.0)
    assert report.effective_source_count == pytest.approx(3.0)
    assert report.verdict == "diverse"


def test_four_sources_one_each_diverse() -> None:
    # HHI = 4 * (0.25)^2 = 0.25
    report = measure_citation_source_concentration(_artifact(["S1", "S2", "S3", "S4"]))
    assert report.source_concentration_hhi == pytest.approx(0.25)
    assert report.effective_source_count == pytest.approx(4.0)
    assert report.verdict == "diverse"


# --- honesty: unknown (nothing cited) --------------------------------------


def test_no_insights_cite_any_source_unknown() -> None:
    report = measure_citation_source_concentration(_artifact([None, None, None]))
    assert report.cited_insight_count == 0
    assert report.uncited_insight_count == 3
    assert report.source_concentration_hhi is None
    assert report.effective_source_count is None
    assert report.dominant_source_id is None
    assert report.dominant_source_share is None
    assert report.source_breakdown == ()
    assert report.verdict == "unknown"


def test_empty_insights_unknown() -> None:
    report = measure_citation_source_concentration(
        ResearchArtifactBody(
            investigation_id="inv-empty",
            problem_question="q",
        )
    )
    assert report.cited_insight_count == 0
    assert report.source_concentration_hhi is None
    assert report.verdict == "unknown"


# --- honesty: uncited excluded, not fabricated -----------------------------


def test_uncited_excluded_from_hhi() -> None:
    # S1: 2 cited, 2 uncited -> HHI over 2 cited = 1.0 (single source among cited)
    report = measure_citation_source_concentration(_artifact(["S1", "S1", None, None]))
    assert report.cited_insight_count == 2
    assert report.uncited_insight_count == 2
    assert report.source_concentration_hhi == pytest.approx(1.0)
    assert report.verdict == "single_source"


def test_blank_source_id_treated_as_uncited() -> None:
    report = measure_citation_source_concentration(_artifact(["S1", "", "  "]))
    assert report.cited_insight_count == 1
    assert report.uncited_insight_count == 2
    assert report.verdict == "single_source"


# --- source_breakdown auditable + sorted -----------------------------------


def test_source_breakdown_sorted_and_auditable() -> None:
    report = measure_citation_source_concentration(
        _artifact(["S2", "S1", "S1", "S3", "S1", "S2"])
    )
    # S1: 3, S2: 2, S3: 1
    assert len(report.source_breakdown) == 3
    first = report.source_breakdown[0]
    assert first.source_id == "S1"
    assert first.citation_count == 3
    assert first.share == pytest.approx(0.5)
    assert report.source_breakdown[1].source_id == "S2"
    assert report.source_breakdown[1].citation_count == 2
    assert report.source_breakdown[2].source_id == "S3"
    assert report.source_breakdown[2].citation_count == 1


def test_source_breakdown_tie_sorted_by_id() -> None:
    # S1: 1, S2: 1 -> tie on count, sort by id asc -> S1 before S2
    report = measure_citation_source_concentration(_artifact(["S2", "S1"]))
    assert report.source_breakdown[0].source_id == "S1"
    assert report.source_breakdown[1].source_id == "S2"


# --- custom threshold ------------------------------------------------------


def test_custom_threshold_reclassifies_concentrated_to_diverse() -> None:
    # 2 sources even split -> HHI 0.50; default >= 0.50 -> concentrated
    artifact = _artifact(["S1", "S1", "S2", "S2"])
    default = measure_citation_source_concentration(artifact)
    assert default.verdict == "concentrated"
    # with threshold 0.51 -> 0.50 < 0.51 -> diverse
    strict = measure_citation_source_concentration(artifact, concentration_threshold=0.51)
    assert strict.verdict == "diverse"


def test_custom_threshold_keeps_single_source() -> None:
    # single source is always single_source regardless of threshold
    report = measure_citation_source_concentration(
        _artifact(["S1", "S1"]), concentration_threshold=0.99
    )
    assert report.verdict == "single_source"


# --- validation ------------------------------------------------------------


@pytest.mark.parametrize("bad", [0.0, -0.01, 1.01])
def test_threshold_out_of_range_rejected(bad: float) -> None:
    with pytest.raises(CitationSourceConcentrationError):
        measure_citation_source_concentration(_artifact(["S1"]), concentration_threshold=bad)


# --- purity / immutability / determinism -----------------------------------


def test_report_is_frozen() -> None:
    report = measure_citation_source_concentration(_artifact(["S1", "S2"]))
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.source_concentration_hhi = 99.0  # type: ignore[misc]


def test_deterministic_repeated_calls() -> None:
    artifact = _artifact(["S1", "S1", "S2", "S3", "S3"])
    first = measure_citation_source_concentration(artifact)
    second = measure_citation_source_concentration(artifact)
    assert first == second


def test_authority_is_advisory() -> None:
    report = measure_citation_source_concentration(_artifact(["S1"]))
    assert report.authority == "advisory"


def test_artifact_id_carried() -> None:
    report = measure_citation_source_concentration(
        _artifact(["S1"], investigation_id="inv-xyz")
    )
    assert report.artifact_id == "inv-xyz"


def test_single_source_distinct_from_unknown() -> None:
    """The binding honesty invariant: single_source (HHI 1.0) never collapses with unknown (None)."""
    monoculture = measure_citation_source_concentration(_artifact(["S1", "S1", "S1"]))
    empty = measure_citation_source_concentration(_artifact([None, None, None]))
    assert monoculture.source_concentration_hhi == pytest.approx(1.0)
    assert monoculture.verdict == "single_source"
    assert empty.source_concentration_hhi is None
    assert empty.verdict == "unknown"
