"""Tests for the insight-novelty axis (added value beyond synthesis).

Exercises: novel/derivative/unmeasurable verdicts, novelty ratio, novelty rate,
mean ratio, synthesis-withheld defer, synthesis-absent defer, custom threshold,
purity/immutability, validation. Fixtures use BARE NONSENSE TOKENS so the
set-difference ratios are exactly countable.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.deep_research_quality.insight_novelty import (
    InsightNovelty,
    InsightNoveltyError,
    InsightNoveltyReport,
    measure_insight_novelty,
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


# --- core: novel insight ---------------------------------------------------


def test_novel_insight() -> None:
    # synthesis "alpha beta"; insight "gamma delta epsilon" (0 overlap) -> ratio 1.0
    a = _artifact(["gamma delta epsilon"], synthesis_excerpt="alpha beta")
    report = measure_insight_novelty(a)
    assert report.novel_count == 1
    assert report.insight_novelties[0].novelty_ratio == pytest.approx(1.0)
    assert report.insight_novelties[0].verdict == "novel"
    assert set(report.insight_novelties[0].novel_terms) == {"gamma", "delta", "epsilon"}


def test_derivative_insight() -> None:
    # synthesis "alpha beta gamma delta"; insight "alpha beta gamma" (all in synth)
    # -> ratio 0.0 -> derivative
    a = _artifact(["alpha beta gamma"], synthesis_excerpt="alpha beta gamma delta")
    report = measure_insight_novelty(a)
    assert report.derivative_count == 1
    assert report.insight_novelties[0].novelty_ratio == pytest.approx(0.0)
    assert report.insight_novelties[0].verdict == "derivative"
    assert report.insight_novelties[0].novel_terms == ()


def test_partial_novelty_at_threshold() -> None:
    # synthesis "alpha beta"; insight "alpha beta gamma delta" -> 2/4 novel -> 0.5
    a = _artifact(["alpha beta gamma delta"], synthesis_excerpt="alpha beta")
    report = measure_insight_novelty(a)
    assert report.insight_novelties[0].novelty_ratio == pytest.approx(0.5)
    assert report.insight_novelties[0].verdict == "novel"  # 0.5 >= 0.50
    assert set(report.insight_novelties[0].novel_terms) == {"gamma", "delta"}


def test_just_below_threshold_derivative() -> None:
    # synthesis "alpha beta gamma"; insight "alpha beta gamma delta epsilon" -> 2/5 = 0.4
    a = _artifact(
        ["alpha beta gamma delta epsilon"], synthesis_excerpt="alpha beta gamma"
    )
    report = measure_insight_novelty(a)
    assert report.insight_novelties[0].novelty_ratio == pytest.approx(0.4)
    assert report.insight_novelties[0].verdict == "derivative"


# --- honesty: unmeasurable -------------------------------------------------


def test_insight_no_distinctive_terms_unmeasurable() -> None:
    a = _artifact(["the and is of"], synthesis_excerpt="alpha beta")
    report = measure_insight_novelty(a)
    assert report.unmeasurable_count == 1
    assert report.insight_novelties[0].verdict == "unmeasurable"
    assert report.insight_novelties[0].novelty_ratio is None


def test_synthesis_withheld_all_unmeasurable() -> None:
    a = _artifact(
        ["alpha beta", "gamma delta"],
        synthesis_excerpt="alpha beta",
        synthesis_withheld=True,
    )
    report = measure_insight_novelty(a)
    assert report.unmeasurable_count == 2
    assert report.novelty_rate is None
    assert report.mean_novelty_ratio is None
    assert report.verdict == "unknown"


def test_synthesis_absent_all_unmeasurable() -> None:
    a = _artifact(["alpha beta", "gamma delta"])  # synthesis_excerpt=None
    report = measure_insight_novelty(a)
    assert report.unmeasurable_count == 2
    assert report.novelty_rate is None
    assert report.verdict == "unknown"


def test_empty_artifact_no_insights() -> None:
    report = measure_insight_novelty(_artifact([], synthesis_excerpt="alpha beta"))
    assert report.novel_count == 0
    assert report.novelty_rate is None
    assert report.verdict == "unknown"


# --- novelty rate + verdict ------------------------------------------------


def test_novelty_rate_mixed() -> None:
    a = _artifact(
        ["gamma delta epsilon", "alpha beta gamma", "zeta eta theta"],
        synthesis_excerpt="alpha beta",
    )
    # i0: 3/3 novel=1.0 novel; i1: 1/3 novel=0.33 derivative; i2: 3/3 novel=1.0 novel
    report = measure_insight_novelty(a)
    assert report.novel_count == 2
    assert report.derivative_count == 1
    assert report.novelty_rate == pytest.approx(2 / 3)


def test_verdict_high_novelty() -> None:
    a = _artifact(
        ["gamma delta", "epsilon zeta", "eta theta"],
        synthesis_excerpt="alpha beta",
    )
    report = measure_insight_novelty(a)
    assert report.novelty_rate == pytest.approx(1.0)
    assert report.verdict == "high_novelty"


def test_verdict_derivative() -> None:
    a = _artifact(
        ["alpha beta", "beta alpha", "alpha"],
        synthesis_excerpt="alpha beta",
    )
    report = measure_insight_novelty(a)
    # all derivative -> rate 0.0 -> verdict derivative
    assert report.novelty_rate == pytest.approx(0.0)
    assert report.verdict == "derivative"


def test_mean_novelty_ratio() -> None:
    # i0 ratio 1.0, i1 ratio 0.0 -> mean 0.5
    a = _artifact(
        ["gamma delta", "alpha beta"],
        synthesis_excerpt="alpha beta",
    )
    report = measure_insight_novelty(a)
    assert report.mean_novelty_ratio == pytest.approx(0.5)


def test_rate_excludes_unmeasurable() -> None:
    a = _artifact(
        ["gamma delta", "the and is of"],  # novel + unmeasurable
        synthesis_excerpt="alpha beta",
    )
    report = measure_insight_novelty(a)
    assert report.novel_count == 1
    assert report.unmeasurable_count == 1
    assert report.novelty_rate == pytest.approx(1.0)  # only the measurable one


# --- custom threshold ------------------------------------------------------


def test_custom_threshold_changes_verdict() -> None:
    # ratio 0.5: novel at 0.50, derivative at 0.60
    a = _artifact(["alpha beta gamma delta"], synthesis_excerpt="alpha beta")
    assert measure_insight_novelty(a).insight_novelties[0].verdict == "novel"
    assert (
        measure_insight_novelty(a, novelty_threshold=0.60).insight_novelties[0].verdict
        == "derivative"
    )


def test_threshold_one_requires_fully_novel() -> None:
    # ratio 0.5 < 1.0 -> derivative at threshold 1.0
    a = _artifact(["alpha beta gamma delta"], synthesis_excerpt="alpha beta")
    report = measure_insight_novelty(a, novelty_threshold=1.0)
    assert report.insight_novelties[0].verdict == "derivative"


def test_threshold_zero_all_novel() -> None:
    # ratio 0.0 >= 0.0 -> novel at threshold 0.0
    a = _artifact(["alpha beta"], synthesis_excerpt="alpha beta")
    report = measure_insight_novelty(a, novelty_threshold=0.0)
    assert report.insight_novelties[0].verdict == "novel"


# --- ratio range -----------------------------------------------------------


def test_novelty_ratio_in_unit_interval() -> None:
    a = _artifact(
        ["alpha beta", "gamma delta", "alpha gamma"],
        synthesis_excerpt="alpha beta",
    )
    report = measure_insight_novelty(a)
    for n in report.insight_novelties:
        if n.novelty_ratio is not None:
            assert 0.0 <= n.novelty_ratio <= 1.0


# --- provenance / purity ---------------------------------------------------


def test_artifact_id_carried_through() -> None:
    a = _artifact(["gamma delta"], investigation_id="inv-777", synthesis_excerpt="alpha")
    report = measure_insight_novelty(a)
    assert report.artifact_id == "inv-777"


def test_authority_is_always_advisory() -> None:
    a = _artifact(["gamma delta"], synthesis_excerpt="alpha")
    assert measure_insight_novelty(a).authority == "advisory"


def test_report_is_immutable() -> None:
    report = measure_insight_novelty(
        _artifact(["gamma delta"], synthesis_excerpt="alpha")
    )
    assert isinstance(report, InsightNoveltyReport)
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.novelty_rate = 0.0  # type: ignore[misc]


def test_insight_novelty_is_immutable() -> None:
    report = measure_insight_novelty(
        _artifact(["gamma delta"], synthesis_excerpt="alpha")
    )
    n = report.insight_novelties[0]
    assert isinstance(n, InsightNovelty)
    with pytest.raises(dataclasses.FrozenInstanceError):
        n.novelty_ratio = 0.0  # type: ignore[misc]


def test_determinism_same_inputs_same_report() -> None:
    a = _artifact(["gamma delta", "alpha"], synthesis_excerpt="alpha beta")
    assert measure_insight_novelty(a) == measure_insight_novelty(a)


def test_notes_describe_verdict() -> None:
    report = measure_insight_novelty(
        _artifact(["gamma delta"], synthesis_excerpt="alpha")
    )
    joined = " | ".join(report.notes).lower()
    assert "novelty" in joined or "synthesis" in joined


# --- validation ------------------------------------------------------------


@pytest.mark.parametrize("bad", [-0.1, 1.1, 2.0])
def test_validation_rejects_bad_threshold(bad: float) -> None:
    with pytest.raises(InsightNoveltyError, match="novelty_threshold"):
        measure_insight_novelty(
            _artifact(["gamma delta"], synthesis_excerpt="alpha"),
            novelty_threshold=bad,
        )


# --- public api exports ----------------------------------------------------


def test_public_api_exports() -> None:
    from substrate.deep_research_quality import insight_novelty as mod

    assert set(mod.__all__) == {
        "InsightNovelty",
        "InsightNoveltyError",
        "InsightNoveltyReport",
        "measure_insight_novelty",
    }
    assert issubclass(mod.InsightNoveltyError, ValueError)
    assert dataclasses.is_dataclass(mod.InsightNovelty)
    assert dataclasses.is_dataclass(mod.InsightNoveltyReport)
