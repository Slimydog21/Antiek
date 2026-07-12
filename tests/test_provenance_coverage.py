"""Tests for the research-artifact provenance-coverage (integrity) axis.

Exercises the load-bearing invariants: sourcing coverage over insights, the
empty-artifact honesty rule (None never fabricated 0), the fabrication-risk
intersection (unsourced ∧ confidence-present), the sourcing-status partition,
immutability/determinism, provenance, and public-API exports.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.deep_research_quality.provenance_coverage import (
    ProvenanceCoverageReport,
    measure_provenance_coverage,
)
from substrate.research_artifact.schema import (
    ArtifactInsight,
    ResearchArtifactBody,
)


def _artifact(
    insights: list[tuple[str, str | None, str | None]],
    *,
    investigation_id: str = "inv-test",
) -> ResearchArtifactBody:
    """Build an artifact from (node_id, source_document_id, confidence) tuples."""
    return ResearchArtifactBody(
        investigation_id=investigation_id,
        problem_question="the question",
        insights=[
            ArtifactInsight(node_id=nid, text=f"insight text {nid}", source_document_id=src, confidence=conf)
            for nid, src, conf in insights
        ],
    )


# --- core coverage --------------------------------------------------------


def test_all_sourced_yields_full_coverage() -> None:
    art = _artifact(
        [
            ("i1", "doc-a", None),
            ("i2", "doc-b", "high"),
            ("i3", "doc-c", "low"),
        ]
    )
    report = measure_provenance_coverage(art)
    assert report.insight_count == 3
    assert report.sourced_count == 3
    assert report.unsourced_count == 0
    assert report.sourcing_coverage == pytest.approx(1.0)
    assert report.unsourced_insight_ids == ()
    assert report.sourced_insight_ids == ("i1", "i2", "i3")


def test_all_unsourced_yields_zero_coverage() -> None:
    art = _artifact([("i1", None, None), ("i2", None, None)])
    report = measure_provenance_coverage(art)
    assert report.sourced_count == 0
    assert report.unsourced_count == 2
    assert report.sourcing_coverage == pytest.approx(0.0)
    assert report.unsourced_insight_ids == ("i1", "i2")
    assert report.sourced_insight_ids == ()


def test_mixed_coverage() -> None:
    art = _artifact(
        [
            ("i1", "doc-a", None),
            ("i2", None, None),
            ("i3", "doc-b", "high"),
            ("i4", None, None),
        ]
    )
    report = measure_provenance_coverage(art)
    assert report.sourced_count == 2
    assert report.unsourced_count == 2
    assert report.sourcing_coverage == pytest.approx(0.5)
    assert report.sourced_insight_ids == ("i1", "i3")
    assert report.unsourced_insight_ids == ("i2", "i4")


def test_coverage_in_unit_interval() -> None:
    for art in [
        _artifact([("i1", "doc-a", None)]),
        _artifact([("i1", None, None)]),
        _artifact([("i1", "doc-a", None), ("i2", None, None)]),
    ]:
        cov = measure_provenance_coverage(art).sourcing_coverage
        assert cov is not None and 0.0 <= cov <= 1.0


# --- honesty rules: empty artifact ----------------------------------------


def test_empty_artifact_yields_none_coverage() -> None:
    report = measure_provenance_coverage(_artifact([]))
    assert report.insight_count == 0
    assert report.sourced_count == 0
    assert report.unsourced_count == 0
    assert report.sourcing_coverage is None
    assert report.confidence_transparency is None
    assert report.unsourced_insight_ids == ()
    assert report.sourced_insight_ids == ()
    assert report.unsourced_confident_count == 0
    assert any("not measurable" in n for n in report.notes)


# --- whitespace-only source treated as unsourced --------------------------


def test_whitespace_only_source_is_unsourced() -> None:
    art = _artifact([("i1", "   ", None), ("i2", "doc-a", None)])
    report = measure_provenance_coverage(art)
    assert report.unsourced_insight_ids == ("i1",)
    assert report.sourced_insight_ids == ("i2",)
    assert report.sourcing_coverage == pytest.approx(0.5)


def test_empty_string_source_is_unsourced() -> None:
    art = _artifact([("i1", "", None)])
    report = measure_provenance_coverage(art)
    assert report.unsourced_count == 1
    assert report.sourced_count == 0
    assert report.sourcing_coverage == pytest.approx(0.0)


# --- fabrication-risk intersection (unsourced AND confident) --------------


def test_unsourced_confident_intersection_is_the_risk_set() -> None:
    art = _artifact(
        [
            ("i1", "doc-a", "high"),     # sourced + confident -> NOT risk
            ("i2", None, "high"),        # unsourced + confident -> RISK
            ("i3", None, "low"),         # unsourced + confident -> RISK
            ("i4", None, None),          # unsourced + no confidence -> not risk
            ("i5", "doc-b", None),       # sourced + no confidence -> not risk
        ]
    )
    report = measure_provenance_coverage(art)
    assert report.unsourced_confident_count == 2
    assert report.unsourced_confident_insight_ids == ("i2", "i3")
    assert any("FABRICATION-RISK" in n for n in report.notes)


def test_sourced_confident_is_not_in_risk_set() -> None:
    art = _artifact([("i1", "doc-a", "high")])
    report = measure_provenance_coverage(art)
    assert report.unsourced_confident_count == 0
    assert report.unsourced_confident_insight_ids == ()


def test_no_risk_note_when_no_unsourced_confident() -> None:
    art = _artifact([("i1", None, None), ("i2", "doc-a", "high")])
    report = measure_provenance_coverage(art)
    assert not any("FABRICATION-RISK" in n for n in report.notes)


# --- confidence transparency ---------------------------------------------


def test_confidence_transparency_ratio() -> None:
    art = _artifact(
        [
            ("i1", "doc-a", "high"),
            ("i2", "doc-b", "low"),
            ("i3", "doc-c", None),
        ]
    )
    report = measure_provenance_coverage(art)
    assert report.confidence_present_count == 2
    assert report.confidence_transparency == pytest.approx(2 / 3)


def test_full_confidence_transparency_suppresses_note() -> None:
    art = _artifact([("i1", "doc-a", "high"), ("i2", "doc-b", "low")])
    report = measure_provenance_coverage(art)
    assert report.confidence_transparency == pytest.approx(1.0)
    # the "transparency < 100%" note should NOT fire when everything declares
    assert not any("confidence transparency" in n.lower() for n in report.notes)


# --- sourcing-status partition -------------------------------------------


def test_sourced_and_unsourced_partition_all_insights() -> None:
    art = _artifact(
        [
            ("i1", "doc-a", None),
            ("i2", None, None),
            ("i3", "doc-b", "high"),
        ]
    )
    report = measure_provenance_coverage(art)
    union = set(report.sourced_insight_ids) | set(report.unsourced_insight_ids)
    assert union == {"i1", "i2", "i3"}
    assert not (set(report.sourced_insight_ids) & set(report.unsourced_insight_ids))
    assert report.sourced_count + report.unsourced_count == report.insight_count


def test_risk_set_is_subset_of_unsourced() -> None:
    art = _artifact(
        [
            ("i1", None, "high"),
            ("i2", None, None),
        ]
    )
    report = measure_provenance_coverage(art)
    assert set(report.unsourced_confident_insight_ids).issubset(
        set(report.unsourced_insight_ids)
    )


# --- provenance / purity --------------------------------------------------


def test_artifact_id_carried_through() -> None:
    art = _artifact([("i1", "doc-a", None)], investigation_id="inv-999")
    assert measure_provenance_coverage(art).artifact_id == "inv-999"


def test_authority_is_always_advisory() -> None:
    assert measure_provenance_coverage(_artifact([("i1", "doc-a", None)])).authority == "advisory"


def test_report_is_immutable() -> None:
    report = measure_provenance_coverage(_artifact([("i1", "doc-a", None)]))
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.sourcing_coverage = 0.0  # type: ignore[misc]


def test_determinism_same_artifact_same_report() -> None:
    art = _artifact([("i1", "doc-a", "high"), ("i2", None, None)])
    assert measure_provenance_coverage(art) == measure_provenance_coverage(art)


def test_isinstance_report_type() -> None:
    art = _artifact([("i1", "doc-a", None)])
    assert isinstance(measure_provenance_coverage(art), ProvenanceCoverageReport)


def test_notes_describe_findings() -> None:
    art = _artifact([("i1", None, "high"), ("i2", "doc-a", None)])
    joined = " | ".join(measure_provenance_coverage(art).notes)
    assert "structural" in joined.lower()
    assert "provenance coverage 50%" in joined.lower()
    assert "fabrication-risk" in joined.lower()


def test_confidence_value_is_opaque_not_parsed() -> None:
    # any non-None confidence counts as "present"; the value is never ranked.
    art = _artifact(
        [
            ("i1", None, "super-duper-confident"),
            ("i2", None, "0.01"),
        ]
    )
    report = measure_provenance_coverage(art)
    assert report.confidence_present_count == 2
    assert report.unsourced_confident_count == 2


# --- public API -----------------------------------------------------------


def test_public_api_exports() -> None:
    from substrate.deep_research_quality import provenance_coverage as mod

    assert set(mod.__all__) == {
        "ProvenanceCoverageReport",
        "measure_provenance_coverage",
    }
    assert dataclasses.is_dataclass(mod.ProvenanceCoverageReport)
