"""Tests for the twin-question-support axis (phantom-question detection).

Exercises: supported/unsupported/unmeasurable verdicts, support ratio, support
rate, escalated-unsupported subset, empty-defer, custom threshold, purity/
immutability, validation. Fixtures use BARE NONSENSE TOKENS so ratios are exact.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.deep_research_quality.twin_question_support import (
    QuestionSupport,
    TwinQuestionSupportError,
    TwinQuestionSupportReport,
    measure_twin_question_support,
)
from substrate.research_artifact.schema import (
    ArtifactInsight,
    ArtifactQuestion,
    ResearchArtifactBody,
)


def _twin(
    questions: list[tuple[str, bool]],  # (text, escalated)
    *,
    investigation_id: str = "inv-twin",
) -> ResearchArtifactBody:
    return ResearchArtifactBody(
        investigation_id=investigation_id,
        problem_question="the question",
        insights=[ArtifactInsight(node_id="i0", text="insight")],
        open_questions=[
            ArtifactQuestion(node_id=f"q{k}", text=t, escalated=e)
            for k, (t, e) in enumerate(questions)
        ],
    )


# --- core: supported question ---------------------------------------------


def test_supported_question() -> None:
    source = "alpha beta gamma delta"
    twin = _twin([("alpha beta", False)])  # both terms in source -> ratio 1.0
    report = measure_twin_question_support(twin, source)
    assert report.supported_count == 1
    assert report.question_support_rate == pytest.approx(1.0)
    assert report.question_supports[0].verdict == "supported"
    assert report.question_supports[0].unsupported_terms == ()


def test_partial_support_at_threshold() -> None:
    # 2 of 4 terms supported -> ratio 0.5 >= 0.50 -> supported
    source = "alpha beta"
    twin = _twin([("alpha beta gamma delta", False)])
    report = measure_twin_question_support(twin, source)
    assert report.question_supports[0].support_ratio == pytest.approx(0.5)
    assert report.question_supports[0].verdict == "supported"
    assert set(report.question_supports[0].unsupported_terms) == {"gamma", "delta"}


# --- core: unsupported (phantom) ------------------------------------------


def test_unsupported_question_phantom() -> None:
    source = "alpha beta"
    twin = _twin([("gamma delta epsilon", False)])  # zero overlap
    report = measure_twin_question_support(twin, source)
    assert report.unsupported_count == 1
    assert report.question_support_rate == pytest.approx(0.0)
    assert report.question_supports[0].verdict == "unsupported"
    assert set(report.question_supports[0].unsupported_terms) == {
        "gamma", "delta", "epsilon"
    }


def test_just_below_threshold_unsupported() -> None:
    # 1 of 3 terms -> 0.33 < 0.50 -> unsupported
    source = "alpha"
    twin = _twin([("alpha beta gamma", False)])
    report = measure_twin_question_support(twin, source)
    assert report.question_supports[0].verdict == "unsupported"


# --- honesty: unmeasurable ------------------------------------------------


def test_question_no_distinctive_terms_unmeasurable() -> None:
    source = "alpha beta"
    twin = _twin([("the and is of", False)])  # all glue (incl interrogatives)
    report = measure_twin_question_support(twin, source)
    assert report.unmeasurable_count == 1
    assert report.question_supports[0].verdict == "unmeasurable"
    assert report.question_supports[0].support_ratio is None


def test_interrogative_only_unmeasurable() -> None:
    # "why" / "how" / "what" are stop-words here (interrogatives stripped)
    twin = _twin([("why how what", False)])
    report = measure_twin_question_support(twin, "alpha beta")
    assert report.unmeasurable_count == 1


def test_empty_source_all_unmeasurable() -> None:
    twin = _twin([("alpha beta", False), ("gamma delta", False)])
    report = measure_twin_question_support(twin, "")
    assert report.unmeasurable_count == 2
    assert report.question_support_rate is None


def test_empty_twin_no_questions() -> None:
    report = measure_twin_question_support(_twin([]), "alpha beta")
    assert report.supported_count == 0
    assert report.question_support_rate is None
    assert report.verdict == "unknown"


# --- escalated-unsupported subset (the acute risk) -----------------------


def test_escalated_unsupported_counted() -> None:
    source = "alpha beta"
    twin = _twin([
        ("gamma delta", True),    # unsupported AND escalated -> acute
        ("gamma delta", False),   # unsupported, not escalated
        ("alpha beta", True),     # supported + escalated (not risky)
    ])
    report = measure_twin_question_support(twin, source)
    assert report.unsupported_count == 2
    assert report.escalated_unsupported_count == 1


def test_escalated_supported_not_counted_risky() -> None:
    source = "alpha beta"
    twin = _twin([("alpha beta", True)])  # supported + escalated
    report = measure_twin_question_support(twin, source)
    assert report.escalated_unsupported_count == 0


def test_escalated_flag_carried_through() -> None:
    source = "alpha beta"
    twin = _twin([("alpha beta", True), ("gamma delta", False)])
    report = measure_twin_question_support(twin, source)
    assert report.question_supports[0].escalated is True
    assert report.question_supports[1].escalated is False


# --- support rate + verdict -----------------------------------------------


def test_support_rate_mixed() -> None:
    source = "alpha beta gamma"
    twin = _twin([
        ("alpha beta", False),    # supported
        ("alpha beta", False),    # supported
        ("delta epsilon", False),  # unsupported
    ])
    report = measure_twin_question_support(twin, source)
    assert report.supported_count == 2
    assert report.unsupported_count == 1
    assert report.question_support_rate == pytest.approx(2 / 3)


def test_verdict_grounded() -> None:
    source = "alpha beta"
    twin = _twin([("alpha beta", False), ("alpha beta", False)])
    report = measure_twin_question_support(twin, source)
    assert report.question_support_rate == pytest.approx(1.0)
    assert report.verdict == "grounded"


def test_verdict_ungrounded() -> None:
    source = "alpha beta"
    twin = _twin([("gamma delta", False), ("epsilon zeta", False)])
    report = measure_twin_question_support(twin, source)
    assert report.question_support_rate == pytest.approx(0.0)
    assert report.verdict == "ungrounded"


def test_rate_excludes_unmeasurable() -> None:
    source = "alpha beta"
    twin = _twin([
        ("alpha beta", False),     # supported
        ("the and is of", False),  # unmeasurable
    ])
    report = measure_twin_question_support(twin, source)
    assert report.supported_count == 1
    assert report.unmeasurable_count == 1
    assert report.question_support_rate == pytest.approx(1.0)


# --- custom threshold -----------------------------------------------------


def test_custom_threshold_changes_verdict() -> None:
    source = "alpha beta"
    twin = _twin([("alpha beta gamma delta", False)])  # ratio 0.5
    assert measure_twin_question_support(twin, source).question_supports[0].verdict == "supported"
    assert (
        measure_twin_question_support(twin, source, support_threshold=0.75).question_supports[0].verdict
        == "unsupported"
    )


def test_threshold_zero_all_supported() -> None:
    source = "alpha"
    twin = _twin([("gamma delta", False)])  # ratio 0.0 >= 0.0 -> supported
    report = measure_twin_question_support(twin, source, support_threshold=0.0)
    assert report.supported_count == 1


# --- ratio range ----------------------------------------------------------


def test_support_ratio_in_unit_interval() -> None:
    source = "alpha beta gamma"
    twin = _twin([
        ("alpha", False),
        ("alpha beta", False),
        ("alpha beta gamma delta", False),
    ])
    report = measure_twin_question_support(twin, source)
    for s in report.question_supports:
        if s.support_ratio is not None:
            assert 0.0 <= s.support_ratio <= 1.0


# --- provenance / purity --------------------------------------------------


def test_artifact_id_carried_through() -> None:
    twin = _twin([("alpha beta", False)], investigation_id="inv-777")
    report = measure_twin_question_support(twin, "alpha beta")
    assert report.artifact_id == "inv-777"


def test_authority_is_always_advisory() -> None:
    twin = _twin([("alpha beta", False)])
    assert measure_twin_question_support(twin, "alpha beta").authority == "advisory"


def test_report_is_immutable() -> None:
    report = measure_twin_question_support(_twin([("alpha beta", False)]), "alpha beta")
    assert isinstance(report, TwinQuestionSupportReport)
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.question_support_rate = 0.0  # type: ignore[misc]


def test_question_support_is_immutable() -> None:
    report = measure_twin_question_support(_twin([("alpha beta", False)]), "alpha beta")
    s = report.question_supports[0]
    assert isinstance(s, QuestionSupport)
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.support_ratio = 0.0  # type: ignore[misc]


def test_determinism_same_inputs_same_report() -> None:
    twin = _twin([("alpha beta", True), ("gamma delta", False)])
    source = "alpha beta gamma"
    assert measure_twin_question_support(twin, source) == measure_twin_question_support(twin, source)


def test_notes_describe_verdict() -> None:
    report = measure_twin_question_support(_twin([("alpha beta", False)]), "alpha beta")
    joined = " | ".join(report.notes).lower()
    assert "phantom" in joined or "unground" in joined


# --- validation -----------------------------------------------------------


@pytest.mark.parametrize("bad", [-0.1, 1.1, 2.0])
def test_validation_rejects_bad_threshold(bad: float) -> None:
    with pytest.raises(TwinQuestionSupportError, match="support_threshold"):
        measure_twin_question_support(
            _twin([("alpha beta", False)]), "alpha beta", support_threshold=bad
        )


# --- public api exports ---------------------------------------------------


def test_public_api_exports() -> None:
    from substrate.deep_research_quality import twin_question_support as mod

    assert set(mod.__all__) == {
        "QuestionSupport",
        "TwinQuestionSupportError",
        "TwinQuestionSupportReport",
        "measure_twin_question_support",
    }
    assert issubclass(mod.TwinQuestionSupportError, ValueError)
    assert dataclasses.is_dataclass(mod.QuestionSupport)
    assert dataclasses.is_dataclass(mod.TwinQuestionSupportReport)
