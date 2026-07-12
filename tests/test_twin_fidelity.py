"""Tests for the twin-fidelity axis (ask #4 — twin hallucination detection).

Exercises: support ratio, supported/unsupported/unmeasurable verdicts, fidelity
rate, empty-defer, custom threshold, purity/immutability. Fixtures use BARE
NONSENSE TOKENS so every ratio is exactly countable.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.deep_research_quality.twin_fidelity import (
    InsightFidelity,
    TwinFidelityError,
    TwinFidelityReport,
    measure_twin_fidelity,
)
from substrate.research_artifact.schema import (
    ArtifactInsight,
    ArtifactQuestion,
    ResearchArtifactBody,
)


def _twin(
    insights: list[str],
    investigation_id: str = "inv-twin",
) -> ResearchArtifactBody:
    return ResearchArtifactBody(
        investigation_id=investigation_id,
        problem_question="the question",
        insights=[
            ArtifactInsight(node_id=f"i{k}", text=t) for k, t in enumerate(insights)
        ],
        open_questions=[ArtifactQuestion(node_id="q0", text="q")],
    )


# --- core: supported insight -----------------------------------------------


def test_supported_insight() -> None:
    source = "alpha beta gamma delta"
    twin = _twin(["alpha beta"])  # both terms in source -> ratio 1.0
    report = measure_twin_fidelity(twin, source)
    assert report.supported_count == 1
    assert report.unsupported_count == 0
    assert report.fidelity_rate == pytest.approx(1.0)
    assert report.insight_fidelities[0].verdict == "supported"
    assert report.insight_fidelities[0].unsupported_terms == ()


def test_partial_support_at_threshold() -> None:
    # 2 of 4 terms supported -> ratio 0.5 >= 0.50 threshold -> supported
    source = "alpha beta"
    twin = _twin(["alpha beta gamma delta"])
    report = measure_twin_fidelity(twin, source)
    assert report.insight_fidelities[0].support_ratio == pytest.approx(0.5)
    assert report.insight_fidelities[0].verdict == "supported"
    assert set(report.insight_fidelities[0].unsupported_terms) == {"gamma", "delta"}


# --- core: unsupported insight (hallucination) -----------------------------


def test_unsupported_insight_hallucination() -> None:
    source = "alpha beta"
    twin = _twin(["gamma delta epsilon"])  # zero overlap -> ratio 0.0 -> unsupported
    report = measure_twin_fidelity(twin, source)
    assert report.unsupported_count == 1
    assert report.fidelity_rate == pytest.approx(0.0)
    assert report.insight_fidelities[0].verdict == "unsupported"
    assert set(report.insight_fidelities[0].unsupported_terms) == {"gamma", "delta", "epsilon"}


def test_just_below_threshold_unsupported() -> None:
    # 1 of 3 terms -> ratio 0.33 < 0.50 -> unsupported
    source = "alpha"
    twin = _twin(["alpha beta gamma"])
    report = measure_twin_fidelity(twin, source)
    assert report.insight_fidelities[0].verdict == "unsupported"


# --- honesty: unmeasurable -------------------------------------------------


def test_insight_no_distinctive_terms_unmeasurable() -> None:
    source = "alpha beta"
    twin = _twin(["the and is of"])  # all glue -> no distinctive terms
    report = measure_twin_fidelity(twin, source)
    assert report.unmeasurable_count == 1
    assert report.insight_fidelities[0].verdict == "unmeasurable"
    assert report.insight_fidelities[0].support_ratio is None


def test_empty_source_all_unmeasurable() -> None:
    twin = _twin(["alpha beta", "gamma delta"])
    report = measure_twin_fidelity(twin, "")
    assert report.unmeasurable_count == 2
    assert report.fidelity_rate is None


def test_empty_twin_no_insights() -> None:
    report = measure_twin_fidelity(_twin([]), "alpha beta")
    assert report.supported_count == 0
    assert report.fidelity_rate is None


# --- fidelity rate ---------------------------------------------------------


def test_fidelity_rate_mixed() -> None:
    source = "alpha beta gamma"
    twin = _twin([
        "alpha beta",          # supported (1.0)
        "alpha beta",          # supported (1.0)
        "delta epsilon zeta",  # unsupported (0.0)
    ])
    report = measure_twin_fidelity(twin, source)
    assert report.supported_count == 2
    assert report.unsupported_count == 1
    assert report.fidelity_rate == pytest.approx(2 / 3)


def test_fidelity_rate_excludes_unmeasurable() -> None:
    source = "alpha beta"
    twin = _twin([
        "alpha beta",      # supported
        "gamma delta",     # unsupported
        "the and is of",   # unmeasurable (excluded)
    ])
    report = measure_twin_fidelity(twin, source)
    assert report.supported_count == 1
    assert report.unsupported_count == 1
    assert report.unmeasurable_count == 1
    assert report.fidelity_rate == pytest.approx(0.5)  # 1/(1+1), unmeasurable excluded


# --- custom threshold ------------------------------------------------------


def test_custom_threshold_changes_verdict() -> None:
    source = "alpha beta"
    twin = _twin(["alpha beta gamma delta"])  # ratio 0.5
    # default 0.50 -> supported; strict 0.75 -> unsupported
    assert measure_twin_fidelity(twin, source).insight_fidelities[0].verdict == "supported"
    assert (
        measure_twin_fidelity(twin, source, support_threshold=0.75).insight_fidelities[0].verdict
        == "unsupported"
    )


def test_threshold_zero_all_supported() -> None:
    source = "alpha"
    twin = _twin(["gamma delta"])  # ratio 0.0 >= 0.0 -> supported
    report = measure_twin_fidelity(twin, source, support_threshold=0.0)
    assert report.supported_count == 1


# --- support ratio range ---------------------------------------------------


def test_support_ratio_in_unit_interval() -> None:
    source = "alpha beta gamma"
    twin = _twin(["alpha", "alpha beta", "alpha beta gamma delta"])
    report = measure_twin_fidelity(twin, source)
    for f in report.insight_fidelities:
        if f.support_ratio is not None:
            assert 0.0 <= f.support_ratio <= 1.0


# --- provenance / purity ---------------------------------------------------


def test_artifact_id_carried_through() -> None:
    twin = _twin(["alpha beta"], investigation_id="inv-777")
    report = measure_twin_fidelity(twin, "alpha beta")
    assert report.artifact_id == "inv-777"


def test_authority_is_always_advisory() -> None:
    assert measure_twin_fidelity(_twin(["alpha beta"]), "alpha beta").authority == "advisory"


def test_report_is_immutable() -> None:
    report = measure_twin_fidelity(_twin(["alpha beta"]), "alpha beta")
    assert isinstance(report, TwinFidelityReport)
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.fidelity_rate = 0.0  # type: ignore[misc]


def test_insight_fidelity_is_immutable() -> None:
    report = measure_twin_fidelity(_twin(["alpha beta"]), "alpha beta")
    f = report.insight_fidelities[0]
    assert isinstance(f, InsightFidelity)
    with pytest.raises(dataclasses.FrozenInstanceError):
        f.support_ratio = 0.0  # type: ignore[misc]


def test_determinism_same_inputs_same_report() -> None:
    twin = _twin(["alpha beta", "gamma delta"])
    source = "alpha beta gamma"
    assert measure_twin_fidelity(twin, source) == measure_twin_fidelity(twin, source)


def test_notes_describe_verdict() -> None:
    report = measure_twin_fidelity(_twin(["alpha beta"]), "alpha beta")
    joined = " | ".join(report.notes).lower()
    assert "hallucinat" in joined or "poisoning" in joined


# --- validation ------------------------------------------------------------


@pytest.mark.parametrize("bad", [-0.1, 1.1, 2.0])
def test_validation_rejects_bad_threshold(bad: float) -> None:
    with pytest.raises(TwinFidelityError, match="support_threshold"):
        measure_twin_fidelity(_twin(["alpha beta"]), "alpha beta", support_threshold=bad)


# --- public api exports ----------------------------------------------------


def test_public_api_exports() -> None:
    from substrate.deep_research_quality import twin_fidelity as mod

    assert set(mod.__all__) == {
        "InsightFidelity",
        "TwinFidelityError",
        "TwinFidelityReport",
        "measure_twin_fidelity",
    }
    assert issubclass(mod.TwinFidelityError, ValueError)
    assert dataclasses.is_dataclass(mod.InsightFidelity)
    assert dataclasses.is_dataclass(mod.TwinFidelityReport)
