"""Tests for the source-authority axis (evidence-base reputation).

Exercises: cited-source collection + dedup, tiering (authoritative/mid/low_quality/
unscored), authority rate, mean authority, empty-defer, unscored-exclusion,
custom thresholds, purity/immutability, validation. Fixtures use stable source
ids so the authority map lookups are exactly countable.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.deep_research_quality.source_authority import (
    SourceAuthorityAssessment,
    SourceAuthorityError,
    SourceAuthorityReport,
    measure_source_authority,
)
from substrate.research_artifact.schema import (
    ArtifactInsight,
    ArtifactQuestion,
    ResearchArtifactBody,
)


def _artifact(
    *,
    source_event_ids: list[str] | None = None,
    insight_sources: list[str | None] | None = None,
    investigation_id: str = "inv-x",
) -> ResearchArtifactBody:
    insights: list[ArtifactInsight] = [
        ArtifactInsight(node_id=f"i{k}", text=t, source_document_id=sid)
        for k, (t, sid) in enumerate(zip(["finding a", "finding b"], insight_sources or [], strict=False))
    ]
    return ResearchArtifactBody(
        investigation_id=investigation_id,
        problem_question="the question",
        insights=insights,
        open_questions=[ArtifactQuestion(node_id="q0", text="q")],
        source_event_ids=source_event_ids or [],
    )


_AUTH = {"arxiv:1": 0.9, "nature:1": 0.95, "blog:1": 0.1, "medium:1": 0.5}


# --- core: tiering ---------------------------------------------------------


def test_all_authoritative() -> None:
    a = _artifact(source_event_ids=["arxiv:1", "nature:1"])
    report = measure_source_authority(a, _AUTH)
    assert report.cited_count == 2
    assert report.authoritative_count == 2
    assert report.low_quality_count == 0
    assert report.mid_count == 0
    assert report.authority_rate == pytest.approx(1.0)
    assert report.mean_authority == pytest.approx((0.9 + 0.95) / 2)
    assert report.verdict == "authoritative"


def test_low_quality_sourced() -> None:
    a = _artifact(source_event_ids=["blog:1"])
    report = measure_source_authority(a, _AUTH)
    assert report.low_quality_count == 1
    assert report.authoritative_count == 0
    assert report.authority_rate == pytest.approx(0.0)
    assert report.verdict == "unverified"


def test_mid_tier() -> None:
    a = _artifact(source_event_ids=["medium:1"])  # 0.5 -> mid
    report = measure_source_authority(a, _AUTH)
    assert report.mid_count == 1
    assert report.authoritative_count == 0
    assert report.low_quality_count == 0


def test_mixed_verdict() -> None:
    # 1 authoritative of 3 scored -> 0.33 -> mixed (>= 0.30)
    a = _artifact(source_event_ids=["arxiv:1", "blog:1", "medium:1"])
    report = measure_source_authority(a, _AUTH)
    assert report.scored_count == 3
    assert report.authoritative_count == 1
    assert report.authority_rate == pytest.approx(1 / 3)
    assert report.verdict == "mixed"


# --- dedup -----------------------------------------------------------------


def test_dedup_across_event_ids_and_provenance() -> None:
    a = _artifact(
        source_event_ids=["arxiv:1"],
        insight_sources=["arxiv:1", "nature:1"],  # arxiv:1 dup with event id
    )
    report = measure_source_authority(a, _AUTH)
    assert report.cited_count == 2  # arxiv:1 deduped, nature:1 added


def test_unique_sources_not_weighted_by_citation() -> None:
    # same source cited via 2 insights + 1 event -> counts once
    a = _artifact(
        source_event_ids=["arxiv:1"],
        insight_sources=["arxiv:1", "arxiv:1"],
    )
    report = measure_source_authority(a, _AUTH)
    assert report.cited_count == 1


# --- honesty: unscored -----------------------------------------------------


def test_unscored_excluded_from_mean_and_rate() -> None:
    a = _artifact(source_event_ids=["arxiv:1", "unknown:1"])
    report = measure_source_authority(a, _AUTH)
    assert report.scored_count == 1
    assert report.unscored_count == 1
    # rate = authoritative(1)/scored(1) = 1.0 (unknown excluded)
    assert report.authority_rate == pytest.approx(1.0)
    assert report.mean_authority == pytest.approx(0.9)


def test_all_unscored_defers() -> None:
    a = _artifact(source_event_ids=["mystery:1", "mystery:2"])
    report = measure_source_authority(a, _AUTH)
    assert report.unscored_count == 2
    assert report.scored_count == 0
    assert report.mean_authority is None
    assert report.authority_rate is None
    assert report.verdict == "unknown"


# --- honesty: empty --------------------------------------------------------


def test_no_cited_sources_defers() -> None:
    a = _artifact()
    report = measure_source_authority(a, _AUTH)
    assert report.cited_count == 0
    assert report.authority_rate is None
    assert report.mean_authority is None
    assert report.verdict == "unknown"


def test_empty_authority_map_all_unscored() -> None:
    a = _artifact(source_event_ids=["arxiv:1", "blog:1"])
    report = measure_source_authority(a, {})
    assert report.cited_count == 2
    assert report.unscored_count == 2
    assert report.scored_count == 0
    assert report.authority_rate is None
    assert report.verdict == "unknown"


def test_none_source_ids_ignored() -> None:
    # insight with source_document_id=None should not appear as a cited source
    a = _artifact(insight_sources=[None, "arxiv:1"])
    report = measure_source_authority(a, _AUTH)
    assert report.cited_count == 1


# --- custom thresholds -----------------------------------------------------


def test_custom_authoritative_threshold() -> None:
    # arxiv:1 = 0.9; at threshold 0.95 it's mid not authoritative
    a = _artifact(source_event_ids=["arxiv:1"])
    default = measure_source_authority(a, _AUTH)
    assert default.assessments[0].tier == "authoritative"
    strict = measure_source_authority(a, _AUTH, authoritative_threshold=0.95)
    assert strict.assessments[0].tier == "mid"


def test_custom_low_quality_threshold() -> None:
    # medium:1 = 0.5; at low threshold 0.6 it's low_quality
    a = _artifact(source_event_ids=["medium:1"])
    default = measure_source_authority(a, _AUTH)
    assert default.assessments[0].tier == "mid"
    strict = measure_source_authority(a, _AUTH, low_quality_threshold=0.6)
    assert strict.assessments[0].tier == "low_quality"


# --- rate range ------------------------------------------------------------


def test_authority_rate_in_unit_interval() -> None:
    a = _artifact(source_event_ids=["arxiv:1", "blog:1", "medium:1"])
    report = measure_source_authority(a, _AUTH)
    if report.authority_rate is not None:
        assert 0.0 <= report.authority_rate <= 1.0


# --- provenance / purity ---------------------------------------------------


def test_artifact_id_carried_through() -> None:
    a = _artifact(source_event_ids=["arxiv:1"], investigation_id="inv-777")
    report = measure_source_authority(a, _AUTH)
    assert report.artifact_id == "inv-777"


def test_authority_is_always_advisory() -> None:
    a = _artifact(source_event_ids=["arxiv:1"])
    assert measure_source_authority(a, _AUTH).authority == "advisory"


def test_report_is_immutable() -> None:
    report = measure_source_authority(_artifact(source_event_ids=["arxiv:1"]), _AUTH)
    assert isinstance(report, SourceAuthorityReport)
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.authority_rate = 0.0  # type: ignore[misc]


def test_assessment_is_immutable() -> None:
    report = measure_source_authority(_artifact(source_event_ids=["arxiv:1"]), _AUTH)
    s = report.assessments[0]
    assert isinstance(s, SourceAuthorityAssessment)
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.score = 0.0  # type: ignore[misc]


def test_determinism_same_inputs_same_report() -> None:
    a = _artifact(source_event_ids=["arxiv:1", "blog:1"])
    auth = {"arxiv:1": 0.9, "blog:1": 0.1}
    assert measure_source_authority(a, auth) == measure_source_authority(a, auth)


def test_notes_describe_verdict() -> None:
    report = measure_source_authority(_artifact(source_event_ids=["arxiv:1"]), _AUTH)
    joined = " | ".join(report.notes).lower()
    assert "authoritative" in joined or "unverified" in joined


# --- validation ------------------------------------------------------------


@pytest.mark.parametrize("bad", [-0.1, 1.1, 2.0])
def test_validation_rejects_bad_authoritative_threshold(bad: float) -> None:
    with pytest.raises(SourceAuthorityError, match="authoritative_threshold"):
        measure_source_authority(
            _artifact(source_event_ids=["arxiv:1"]), _AUTH, authoritative_threshold=bad
        )


@pytest.mark.parametrize("bad", [-0.1, 1.1, 2.0])
def test_validation_rejects_bad_low_threshold(bad: float) -> None:
    with pytest.raises(SourceAuthorityError, match="low_quality_threshold"):
        measure_source_authority(
            _artifact(source_event_ids=["arxiv:1"]), _AUTH, low_quality_threshold=bad
        )


def test_validation_rejects_inverted_thresholds() -> None:
    with pytest.raises(SourceAuthorityError, match="must not exceed"):
        measure_source_authority(
            _artifact(source_event_ids=["arxiv:1"]),
            _AUTH,
            authoritative_threshold=0.2,
            low_quality_threshold=0.8,
        )


# --- public api exports ----------------------------------------------------


def test_public_api_exports() -> None:
    from substrate.deep_research_quality import source_authority as mod

    assert set(mod.__all__) == {
        "SourceAuthorityAssessment",
        "SourceAuthorityError",
        "SourceAuthorityReport",
        "measure_source_authority",
    }
    assert issubclass(mod.SourceAuthorityError, ValueError)
    assert dataclasses.is_dataclass(mod.SourceAuthorityAssessment)
    assert dataclasses.is_dataclass(mod.SourceAuthorityReport)
