"""Tests for the twin-coverage axis (did the twin capture the source? ask #4).

Recall complement to twin_fidelity #1954 (precision). Exercises:
complete/partial/insight_loss/question_loss/loss/unknown verdicts, per-type
coverage ratios, subset capture (overlap-coefficient), all-glue exclusion,
custom threshold, matched-evidence auditability, purity/immutability, validation.
Fixtures use BARE NONSENSE TOKENS with hand-counted ratios.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.deep_research_quality.twin_coverage import (
    SourceItemCoverage,
    TwinCoverageError,
    TwinCoverageReport,
    measure_twin_coverage,
)
from substrate.research_artifact.schema import (
    ArtifactInsight,
    ArtifactQuestion,
    ResearchArtifactBody,
)


def _artifact(
    *,
    investigation_id: str,
    insights: list[str] | None = None,
    questions: list[str] | None = None,
) -> ResearchArtifactBody:
    return ResearchArtifactBody(
        investigation_id=investigation_id,
        problem_question="the problem",
        insights=[
            ArtifactInsight(node_id=f"{investigation_id}-i{k}", text=t)
            for k, t in enumerate(insights or [])
        ],
        open_questions=[
            ArtifactQuestion(
                node_id=f"{investigation_id}-q{k}", text=t, escalated=False
            )
            for k, t in enumerate(questions or [])
        ],
    )


# --- complete -------------------------------------------------------------


def test_complete_capture_insights_and_questions() -> None:
    source = _artifact(
        investigation_id="src", insights=["alpha beta", "gamma delta"],
        questions=["epsilon zeta"],
    )
    twin = _artifact(
        investigation_id="twin", insights=["alpha beta", "gamma delta"],
        questions=["epsilon zeta"],
    )
    r = measure_twin_coverage(source, twin)
    assert r.verdict == "complete"
    assert r.insight_coverage == 1.0
    assert r.question_coverage == 1.0
    assert r.authority == "advisory"
    assert r.source_id == "src"
    assert r.twin_id == "twin"


def test_complete_when_questions_not_measurable_but_insights_all_captured() -> None:
    # source has insights + all-glue questions; twin captures all insights.
    source = _artifact(investigation_id="src", insights=["alpha beta"], questions=["the and of"])
    twin = _artifact(investigation_id="twin", insights=["alpha beta"], questions=["the and of"])
    r = measure_twin_coverage(source, twin)
    assert r.question_coverage is None
    assert r.insight_coverage == 1.0
    assert r.verdict == "complete"


# --- insight loss (the recall failure this axis catches) ------------------


def test_insight_loss_twin_dropped_findings() -> None:
    # source has 3 insights; twin captured only 1 -> 1/3 < 0.50 -> insight_loss.
    source = _artifact(
        investigation_id="src", insights=["alpha beta", "gamma delta", "epsilon zeta"],
    )
    twin = _artifact(investigation_id="twin", insights=["alpha beta"])
    r = measure_twin_coverage(source, twin)
    assert r.insight_coverage == pytest.approx(1 / 3)
    assert r.verdict == "insight_loss"
    assert r.captured_insights == 1
    assert r.dropped_insights == 2
    # the faithful-but-incomplete twin: twin_fidelity would PASS (the 1 insight
    # is grounded), but coverage FAILS — the load-bearing distinction.
    assert r.dropped_insights == 2


# --- question loss --------------------------------------------------------


def test_question_loss_twin_dropped_questions() -> None:
    source = _artifact(
        investigation_id="src", questions=["alpha beta", "gamma delta", "epsilon zeta"],
    )
    twin = _artifact(investigation_id="twin", questions=["alpha beta"])
    r = measure_twin_coverage(source, twin)
    assert r.insight_coverage is None  # source had no insights
    assert r.question_coverage == pytest.approx(1 / 3)
    assert r.verdict == "question_loss"


# --- both lost -> loss ----------------------------------------------------


def test_both_lost() -> None:
    source = _artifact(
        investigation_id="src",
        insights=["alpha beta", "gamma delta", "epsilon zeta"],
        questions=["eta theta", "iota kappa", "mu nu"],
    )
    twin = _artifact(investigation_id="twin", insights=["alpha beta"], questions=["eta theta"])
    r = measure_twin_coverage(source, twin)
    assert r.insight_coverage == pytest.approx(1 / 3)
    assert r.question_coverage == pytest.approx(1 / 3)
    assert r.verdict == "loss"


# --- partial (most captured, some dropped) --------------------------------


def test_partial_majority_captured() -> None:
    # 4 source insights, twin captured 3 -> 0.75 >= 0.50 but < 1.0 -> partial.
    source = _artifact(
        investigation_id="src",
        insights=["alpha beta", "gamma delta", "epsilon zeta", "eta theta"],
    )
    twin = _artifact(
        investigation_id="twin", insights=["alpha beta", "gamma delta", "epsilon zeta"],
    )
    r = measure_twin_coverage(source, twin)
    assert r.insight_coverage == 0.75
    assert r.verdict == "partial"
    assert r.captured_insights == 3
    assert r.dropped_insights == 1


# --- subset capture (overlap-coefficient design) --------------------------


def test_rich_source_insight_with_subset_twin_is_captured() -> None:
    # source insight {alpha,beta,gamma,delta,epsilon} (5); twin insight
    # {alpha,beta,gamma,delta} (4) is a subset: overlap-coeff =
    # |{alpha,beta,gamma,delta}| / min(5,4) = 4/4 = 1.0 -> captured (not
    # penalised for the source's extra length, which Jaccard would punish).
    source = _artifact(investigation_id="src", insights=["alpha beta gamma delta epsilon"])
    twin = _artifact(investigation_id="twin", insights=["alpha beta gamma delta"])
    r = measure_twin_coverage(source, twin)
    assert r.insight_coverage == 1.0
    assert r.verdict == "complete"


# --- all-glue / unmeasurable ----------------------------------------------


def test_unknown_when_source_all_glue() -> None:
    source = _artifact(investigation_id="src", insights=["the and of"], questions=["is was be"])
    twin = _artifact(investigation_id="twin", insights=["alpha beta"])
    r = measure_twin_coverage(source, twin)
    assert r.insight_coverage is None
    assert r.question_coverage is None
    assert r.unmeasurable_insights == 1
    assert r.unmeasurable_questions == 1
    assert r.verdict == "unknown"


def test_glue_items_excluded_from_coverage_ratio() -> None:
    # source has 1 measurable + 1 all-glue insight; twin captures the measurable.
    source = _artifact(investigation_id="src", insights=["alpha beta", "the and of"])
    twin = _artifact(investigation_id="twin", insights=["alpha beta"])
    r = measure_twin_coverage(source, twin)
    assert r.insight_coverage == 1.0  # 1 of 1 measurable
    assert r.unmeasurable_insights == 1
    assert r.captured_insights == 1
    assert r.dropped_insights == 0
    assert r.verdict == "complete"


# --- matched evidence auditability ----------------------------------------


def test_matched_twin_node_recorded() -> None:
    source = _artifact(investigation_id="src", insights=["alpha beta", "gamma delta"])
    twin = _artifact(investigation_id="twin", insights=["alpha beta", "gamma delta"])
    r = measure_twin_coverage(source, twin)
    # each source insight matched the corresponding twin insight
    by_src = {c.source_node_id: c for c in r.insight_captures}
    assert by_src["src-i0"].verdict == "captured"
    assert by_src["src-i0"].matched_twin_node_id is not None
    assert by_src["src-i0"].best_overlap == 1.0


def test_dropped_item_has_no_strong_match() -> None:
    source = _artifact(investigation_id="src", insights=["alpha beta", "zzz yyy"])
    twin = _artifact(investigation_id="twin", insights=["alpha beta"])
    r = measure_twin_coverage(source, twin)
    by_src = {c.source_node_id: c for c in r.insight_captures}
    assert by_src["src-i0"].verdict == "captured"
    assert by_src["src-i1"].verdict == "dropped"
    assert by_src["src-i1"].matched_twin_node_id is None  # no twin node matched


# --- custom threshold -----------------------------------------------------


def test_custom_threshold_changes_verdict() -> None:
    # source insight {alpha,beta,gamma} vs twin {alpha,beta,gamma,zzz}:
    # overlap-coeff = 3/3 = 1.0 -> captured at any threshold.
    # Use a partial-overlap case instead: {alpha,beta,gamma} vs {alpha,beta,zzz}
    # = 2/min(3,3) = 0.667.
    source = _artifact(investigation_id="src", insights=["alpha beta gamma"])
    twin = _artifact(investigation_id="twin", insights=["alpha beta zzz"])
    loose = measure_twin_coverage(source, twin, capture_threshold=0.50)
    assert loose.insight_coverage == 1.0  # 0.667 >= 0.50 -> captured
    assert loose.verdict == "complete"
    strict = measure_twin_coverage(source, twin, capture_threshold=0.70)
    assert strict.insight_coverage == 0.0  # 0.667 < 0.70 -> dropped
    assert strict.verdict == "insight_loss"


# --- validation -----------------------------------------------------------


@pytest.mark.parametrize("bad", [-0.1, 1.5])
def test_bad_threshold_raises(bad: float) -> None:
    source = _artifact(investigation_id="src", insights=["alpha beta"])
    twin = _artifact(investigation_id="twin", insights=["alpha beta"])
    with pytest.raises(TwinCoverageError, match="capture_threshold"):
        measure_twin_coverage(source, twin, capture_threshold=bad)


# --- purity / immutability ------------------------------------------------


def test_report_is_frozen_and_deterministic() -> None:
    source = _artifact(investigation_id="src", insights=["alpha beta", "gamma delta"])
    twin = _artifact(investigation_id="twin", insights=["alpha beta", "gamma delta"])
    r1 = measure_twin_coverage(source, twin)
    r2 = measure_twin_coverage(source, twin)
    assert dataclasses.is_dataclass(r1)
    assert isinstance(r1.insight_captures, tuple)
    assert all(isinstance(c, SourceItemCoverage) for c in r1.insight_captures)
    assert r1 == r2  # deterministic
    with pytest.raises(dataclasses.FrozenInstanceError):
        r1.verdict = "tampered"  # type: ignore[misc]
    assert isinstance(r1, TwinCoverageReport)


def test_notes_are_non_empty_and_auditable() -> None:
    source = _artifact(investigation_id="src", insights=["alpha beta"])
    twin = _artifact(investigation_id="twin", insights=["alpha beta"])
    r = measure_twin_coverage(source, twin)
    assert isinstance(r.notes, tuple)
    assert len(r.notes) >= 5
    assert all(isinstance(n, str) and n for n in r.notes)
