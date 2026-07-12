"""Tests for the confidence-calibration axis (ask #7 — epistemic honesty).

Exercises: bucketing (high/medium/low), calibration score, verdict bands
(well_calibrated / flat / miscalibrated / unknown), unlabeled-defer,
single-bucket-flat, purity/immutability.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.deep_research_quality.confidence_calibration import (
    ConfidenceCalibrationReport,
    measure_confidence_calibration,
)
from substrate.research_artifact.schema import (
    ArtifactInsight,
    ArtifactQuestion,
    ResearchArtifactBody,
)


def _artifact(
    insights: list[ArtifactInsight],
    investigation_id: str = "inv-test",
) -> ResearchArtifactBody:
    return ResearchArtifactBody(
        investigation_id=investigation_id,
        problem_question="the question",
        insights=insights,
        open_questions=[ArtifactQuestion(node_id="q0", text="q")],
    )


def _insight(
    text: str = "finding",
    confidence: str | None = None,
    source: str | None = None,
) -> ArtifactInsight:
    return ArtifactInsight(
        node_id=text.replace(" ", "-"),
        text=text,
        source_document_id=source,
        confidence=confidence,
    )


# --- bucketing -------------------------------------------------------------


def test_high_marker_bucketed_high() -> None:
    report = measure_confidence_calibration(
        _artifact([_insight(confidence="high", source="s1")])
    )
    assert report.high_confidence_count == 1


def test_low_marker_bucketed_low() -> None:
    report = measure_confidence_calibration(
        _artifact([_insight(confidence="uncertain", source="s1")])
    )
    assert report.low_confidence_count == 1


def test_unrecognized_bucketed_medium() -> None:
    report = measure_confidence_calibration(
        _artifact([_insight(confidence="banana", source="s1")])
    )
    assert report.medium_confidence_count == 1
    assert report.high_confidence_count == 0
    assert report.low_confidence_count == 0


# --- verdict: well_calibrated ----------------------------------------------


def test_well_calibrated_high_grounded_low_not() -> None:
    report = measure_confidence_calibration(
        _artifact([
            _insight(confidence="high", source="s1"),
            _insight(confidence="high", source="s2"),
            _insight(confidence="low"),
            _insight(confidence="low"),
        ])
    )
    assert report.high_grounded_rate == pytest.approx(1.0)
    assert report.low_grounded_rate == pytest.approx(0.0)
    assert report.calibration_score == pytest.approx(1.0)
    assert report.verdict == "well_calibrated"


def test_well_calibrated_boundary() -> None:
    # 3 high grounded + 1 high not, 0 low grounded + 3 low not
    # high_rate = 0.75, low_rate = 0.0, score = 0.75 > 0.25
    report = measure_confidence_calibration(
        _artifact([
            _insight(confidence="high", source="s1"),
            _insight(confidence="high", source="s2"),
            _insight(confidence="high", source="s3"),
            _insight(confidence="high"),
            _insight(confidence="low"),
            _insight(confidence="low"),
            _insight(confidence="low"),
        ])
    )
    assert report.high_grounded_rate == pytest.approx(0.75)
    assert report.low_grounded_rate == pytest.approx(0.0)
    assert report.verdict == "well_calibrated"


# --- verdict: miscalibrated (inverted) -------------------------------------


def test_miscalibrated_high_ungrounded_low_grounded() -> None:
    report = measure_confidence_calibration(
        _artifact([
            _insight(confidence="high"),
            _insight(confidence="high"),
            _insight(confidence="low", source="s1"),
            _insight(confidence="low", source="s2"),
        ])
    )
    assert report.high_grounded_rate == pytest.approx(0.0)
    assert report.low_grounded_rate == pytest.approx(1.0)
    assert report.calibration_score == pytest.approx(-1.0)
    assert report.verdict == "miscalibrated"


# --- verdict: flat ---------------------------------------------------------


def test_flat_similar_grounding_rates() -> None:
    # 2 high grounded of 4 (0.5), 1 low grounded of 2 (0.5) -> score 0.0 -> flat
    report = measure_confidence_calibration(
        _artifact([
            _insight(confidence="high", source="s1"),
            _insight(confidence="high", source="s2"),
            _insight(confidence="high"),
            _insight(confidence="high"),
            _insight(confidence="low", source="s3"),
            _insight(confidence="low"),
        ])
    )
    assert report.high_grounded_rate == pytest.approx(0.5)
    assert report.low_grounded_rate == pytest.approx(0.5)
    assert report.calibration_score == pytest.approx(0.0)
    assert report.verdict == "flat"


def test_flat_single_bucket_all_high() -> None:
    report = measure_confidence_calibration(
        _artifact([
            _insight(confidence="high", source="s1"),
            _insight(confidence="high"),
        ])
    )
    assert report.high_confidence_count == 2
    assert report.low_confidence_count == 0
    assert report.verdict == "flat"
    assert report.calibration_score == pytest.approx(0.0)


def test_flat_all_medium() -> None:
    report = measure_confidence_calibration(
        _artifact([_insight(confidence="moderate", source="s1")])
    )
    assert report.medium_confidence_count == 1
    assert report.verdict == "flat"


# --- verdict: unknown (no labels) ------------------------------------------


def test_unknown_all_unlabeled() -> None:
    report = measure_confidence_calibration(
        _artifact([
            _insight(confidence=None, source="s1"),
            _insight(confidence=None),
        ])
    )
    assert report.unlabeled_insight_count == 2
    assert report.labeled_insight_count == 0
    assert report.calibration_score is None
    assert report.verdict == "unknown"


def test_unknown_no_insights() -> None:
    report = measure_confidence_calibration(_artifact([]))
    assert report.labeled_insight_count == 0
    assert report.verdict == "unknown"


# --- unlabeled excluded from calibration -----------------------------------


def test_unlabeled_excluded_but_counted() -> None:
    report = measure_confidence_calibration(
        _artifact([
            _insight(confidence="high", source="s1"),
            _insight(confidence=None, source="s2"),
            _insight(confidence=None),
        ])
    )
    assert report.labeled_insight_count == 1
    assert report.unlabeled_insight_count == 2
    # Only 1 labeled insight in single bucket -> flat
    assert report.verdict == "flat"


# --- calibration score range -----------------------------------------------


def test_calibration_score_in_range() -> None:
    report = measure_confidence_calibration(
        _artifact([
            _insight(confidence="high", source="s1"),
            _insight(confidence="low"),
        ])
    )
    assert report.calibration_score is not None
    assert -1.0 <= report.calibration_score <= 1.0


# --- provenance / purity ---------------------------------------------------


def test_artifact_id_carried_through() -> None:
    report = measure_confidence_calibration(
        _artifact([_insight(confidence="high")], investigation_id="inv-777")
    )
    assert report.artifact_id == "inv-777"


def test_authority_is_always_advisory() -> None:
    report = measure_confidence_calibration(
        _artifact([_insight(confidence="high", source="s1")])
    )
    assert report.authority == "advisory"


def test_report_is_immutable() -> None:
    report = measure_confidence_calibration(
        _artifact([_insight(confidence="high", source="s1")])
    )
    assert isinstance(report, ConfidenceCalibrationReport)
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.verdict = "flat"  # type: ignore[misc]


def test_determinism_same_inputs_same_report() -> None:
    art = _artifact([
        _insight(confidence="high", source="s1"),
        _insight(confidence="low"),
    ])
    assert measure_confidence_calibration(art) == measure_confidence_calibration(art)


def test_notes_describe_verdict() -> None:
    report = measure_confidence_calibration(
        _artifact([_insight(confidence="high", source="s1"), _insight(confidence="low")])
    )
    joined = " | ".join(report.notes).lower()
    assert "epistemic" in joined or "honest" in joined


# --- public api exports ----------------------------------------------------


def test_public_api_exports() -> None:
    from substrate.deep_research_quality import confidence_calibration as mod

    assert set(mod.__all__) == {
        "ConfidenceCalibrationReport",
        "measure_confidence_calibration",
    }
    assert dataclasses.is_dataclass(mod.ConfidenceCalibrationReport)
