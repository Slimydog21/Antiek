"""Tests for the evidence-specificity axis (concrete vs vague findings).

Exercises: numeric-marker detection, specificity ratio, concrete/vague/unmeasurable
verdicts, mean ratio, synthesis specificity (withheld/absent), custom threshold,
purity/immutability, validation. Fixtures use exactly-countable token sets.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.deep_research_quality.evidence_specificity import (
    EvidenceSpecificityError,
    EvidenceSpecificityReport,
    InsightSpecificity,
    measure_evidence_specificity,
)
from substrate.research_artifact.schema import (
    ArtifactInsight,
    ArtifactQuestion,
    ResearchArtifactBody,
)


def _artifact(
    insights: list[str],
    *,
    investigation_id: str = "inv-x",
    synthesis_excerpt: str | None = None,
    synthesis_withheld: bool = False,
) -> ResearchArtifactBody:
    return ResearchArtifactBody(
        investigation_id=investigation_id,
        problem_question="the question",
        insights=[
            ArtifactInsight(node_id=f"i{k}", text=t) for k, t in enumerate(insights)
        ],
        open_questions=[ArtifactQuestion(node_id="q0", text="q")],
        synthesis_excerpt=synthesis_excerpt,
        synthesis_withheld=synthesis_withheld,
    )


# --- core: numeric-marker detection ----------------------------------------


def test_concrete_insight() -> None:
    # 5 tokens (model 4 scored 86.4 percent); 2 numeric (4, 86.4) -> 0.4 -> concrete
    a = _artifact(["model 4 scored 86.4 percent"])
    report = measure_evidence_specificity(a)
    assert report.concrete_count == 1
    assert report.insight_specificities[0].specificity_ratio == pytest.approx(0.4)
    assert report.insight_specificities[0].verdict == "concrete"
    assert set(report.insight_specificities[0].markers) == {"4", "86.4"}
    assert report.insight_specificities[0].token_count == 5


def test_vague_insight_no_numbers() -> None:
    # qualitative hand-wave -> 0.0 -> vague
    a = _artifact(["the model performs really well overall"])
    report = measure_evidence_specificity(a)
    assert report.vague_count == 1
    assert report.insight_specificities[0].specificity_ratio == pytest.approx(0.0)
    assert report.insight_specificities[0].verdict == "vague"
    assert report.insight_specificities[0].markers == ()


# --- honesty: unmeasurable -------------------------------------------------


def test_empty_insight_unmeasurable() -> None:
    a = _artifact([""])
    report = measure_evidence_specificity(a)
    assert report.unmeasurable_count == 1
    assert report.insight_specificities[0].verdict == "unmeasurable"
    assert report.insight_specificities[0].specificity_ratio is None
    assert report.insight_specificities[0].token_count == 0


def test_whitespace_only_unmeasurable() -> None:
    a = _artifact(["   "])
    report = measure_evidence_specificity(a)
    assert report.unmeasurable_count == 1
    assert report.mean_specificity_ratio is None


def test_empty_artifact_no_insights() -> None:
    report = measure_evidence_specificity(_artifact([]))
    assert report.concrete_count == 0
    assert report.vague_count == 0
    assert report.mean_specificity_ratio is None
    assert report.verdict == "unknown"


# --- mean + verdict --------------------------------------------------------


def test_mean_and_evidence_rich() -> None:
    # insight1 "1 2 alpha" -> 3 tok 2 num -> 0.667 concrete
    # insight2 "alpha beta gamma" -> 3 tok 0 num -> 0.0 vague
    # mean 0.333 -> evidence_rich
    a = _artifact(["1 2 alpha", "alpha beta gamma"])
    report = measure_evidence_specificity(a)
    assert report.mean_specificity_ratio == pytest.approx(1 / 3)
    assert report.concrete_count == 1
    assert report.vague_count == 1
    assert report.verdict == "evidence_rich"


def test_verdict_mixed_below_threshold_band() -> None:
    # each insight: 12 tokens, 1 numeric -> 1/12 ~ 0.083 (vague per-insight)
    # mean 0.083 -> in [0.05, 0.10) -> mixed (aggregation lifts verdict)
    low = "1 alpha beta gamma delta epsilon zeta eta theta iota kappa lambda"
    a = _artifact([low, low])
    report = measure_evidence_specificity(a)
    assert report.vague_count == 2
    assert report.verdict == "mixed"


def test_verdict_qualitative() -> None:
    a = _artifact(["vague claim here", "another soft claim"])
    report = measure_evidence_specificity(a)
    assert report.mean_specificity_ratio == pytest.approx(0.0)
    assert report.verdict == "qualitative"


def test_mean_excludes_unmeasurable() -> None:
    # "1 2 alpha beta" -> 4 tok 2 num -> 0.5 concrete; "" unmeasurable
    a = _artifact(["1 2 alpha beta", ""])
    report = measure_evidence_specificity(a)
    assert report.mean_specificity_ratio == pytest.approx(0.5)  # only the measurable one


# --- total markers ---------------------------------------------------------


def test_total_markers_accumulates() -> None:
    # "score 86 and 90" -> 4 tok 2 num (86,90); "model 4" -> 2 tok 1 num (4)
    a = _artifact(["score 86 and 90", "model 4"])
    report = measure_evidence_specificity(a)
    assert report.total_markers == 3


# --- synthesis specificity -------------------------------------------------


def test_synthesis_specificity_measured() -> None:
    a = _artifact(["score 86"], synthesis_excerpt="the model scored 86 on benchmark")
    report = measure_evidence_specificity(a)
    assert report.synthesis_marker_count == 1
    assert report.synthesis_specificity_ratio is not None
    assert report.synthesis_specificity_ratio > 0.0


def test_synthesis_withheld_is_none() -> None:
    a = _artifact(["score 86"], synthesis_excerpt="hidden excerpt", synthesis_withheld=True)
    report = measure_evidence_specificity(a)
    assert report.synthesis_marker_count is None
    assert report.synthesis_specificity_ratio is None


def test_synthesis_absent_is_none() -> None:
    a = _artifact(["score 86"])  # no synthesis_excerpt (None)
    report = measure_evidence_specificity(a)
    assert report.synthesis_marker_count is None
    assert report.synthesis_specificity_ratio is None


# --- custom threshold ------------------------------------------------------


def test_custom_threshold_changes_verdict() -> None:
    # "model 4 scored 86 percent" -> 5 tok 2 num -> 0.4
    a = _artifact(["model 4 scored 86 percent"])
    assert measure_evidence_specificity(a).insight_specificities[0].verdict == "concrete"
    assert (
        measure_evidence_specificity(a, concreteness_threshold=0.6).insight_specificities[0].verdict
        == "vague"
    )


def test_threshold_one_all_vague() -> None:
    # 0.4 < 1.0 -> vague at threshold 1.0
    a = _artifact(["model 4 scored 86 percent"])
    report = measure_evidence_specificity(a, concreteness_threshold=1.0)
    assert report.insight_specificities[0].verdict == "vague"


def test_threshold_zero_all_concrete() -> None:
    # 0.0 >= 0.0 -> concrete at threshold 0.0
    a = _artifact(["vague claim"])
    report = measure_evidence_specificity(a, concreteness_threshold=0.0)
    assert report.insight_specificities[0].verdict == "concrete"


# --- ratio range -----------------------------------------------------------


def test_specificity_ratio_in_unit_interval() -> None:
    a = _artifact(["1 2 3 4", "nothing here", "model 4 worked today"])
    report = measure_evidence_specificity(a)
    for s in report.insight_specificities:
        if s.specificity_ratio is not None:
            assert 0.0 <= s.specificity_ratio <= 1.0


# --- provenance / purity ---------------------------------------------------


def test_artifact_id_carried_through() -> None:
    a = _artifact(["score 86"], investigation_id="inv-999")
    report = measure_evidence_specificity(a)
    assert report.artifact_id == "inv-999"


def test_authority_is_always_advisory() -> None:
    assert measure_evidence_specificity(_artifact(["score 86"])).authority == "advisory"


def test_report_is_immutable() -> None:
    report = measure_evidence_specificity(_artifact(["score 86"]))
    assert isinstance(report, EvidenceSpecificityReport)
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.mean_specificity_ratio = 0.0  # type: ignore[misc]


def test_insight_specificity_is_immutable() -> None:
    report = measure_evidence_specificity(_artifact(["score 86"]))
    s = report.insight_specificities[0]
    assert isinstance(s, InsightSpecificity)
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.specificity_ratio = 0.0  # type: ignore[misc]


def test_determinism_same_inputs_same_report() -> None:
    a = _artifact(["model 4 scored 86", "vague claim"])
    assert measure_evidence_specificity(a) == measure_evidence_specificity(a)


def test_notes_describe_verdict() -> None:
    report = measure_evidence_specificity(_artifact(["score 86"]))
    joined = " | ".join(report.notes).lower()
    assert "concrete" in joined or "qualitative" in joined


# --- validation ------------------------------------------------------------


@pytest.mark.parametrize("bad", [-0.1, 1.1, 2.0])
def test_validation_rejects_bad_threshold(bad: float) -> None:
    with pytest.raises(EvidenceSpecificityError, match="concreteness_threshold"):
        measure_evidence_specificity(_artifact(["score 86"]), concreteness_threshold=bad)


# --- public api exports ----------------------------------------------------


def test_public_api_exports() -> None:
    from substrate.deep_research_quality import evidence_specificity as mod

    assert set(mod.__all__) == {
        "EvidenceSpecificityError",
        "EvidenceSpecificityReport",
        "InsightSpecificity",
        "measure_evidence_specificity",
    }
    assert issubclass(mod.EvidenceSpecificityError, ValueError)
    assert dataclasses.is_dataclass(mod.InsightSpecificity)
    assert dataclasses.is_dataclass(mod.EvidenceSpecificityReport)
