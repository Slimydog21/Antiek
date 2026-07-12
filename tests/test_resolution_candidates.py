"""Tests for resolution-candidate discovery (insight -> prior question).

Exercises: Jaccard overlap, the candidate-not-confirmed defer, escalated
questions as valid targets, empty-defer, self-reference skip, prior de-dup,
deterministic sort, counts, validation, purity/immutability. Fixtures use BARE
NONSENSE TOKENS (alpha/beta/gamma) so every ratio is exactly countable.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.cross_reference.resolution_candidates import (
    ResolutionCandidate,
    ResolutionCandidateError,
    ResolutionCandidateReport,
    _distinctive_terms,
    _jaccard,
    discover_resolution_candidates,
)
from substrate.research_artifact.schema import (
    ArtifactInsight,
    ArtifactQuestion,
    ResearchArtifactBody,
)


def _artifact(
    investigation_id: str,
    *,
    insights: list[str] | None = None,
    questions: list[str] | None = None,
    escalated: bool = False,
) -> ResearchArtifactBody:
    return ResearchArtifactBody(
        investigation_id=investigation_id,
        problem_question="the question",
        insights=[
            ArtifactInsight(node_id=f"{investigation_id}-i{k}", text=t)
            for k, t in enumerate(insights or [])
        ],
        open_questions=[
            ArtifactQuestion(
                node_id=f"{investigation_id}-q{k}",
                text=t,
                escalated=escalated,
            )
            for k, t in enumerate(questions or [])
        ],
    )


def _artifact_with_mixed_questions(
    investigation_id: str,
    insights: list[str],
    questions: list[tuple[str, bool]],  # (text, escalated)
) -> ResearchArtifactBody:
    return ResearchArtifactBody(
        investigation_id=investigation_id,
        problem_question="the question",
        insights=[
            ArtifactInsight(node_id=f"{investigation_id}-i{k}", text=t)
            for k, t in enumerate(insights)
        ],
        open_questions=[
            ArtifactQuestion(
                node_id=f"{investigation_id}-q{k}", text=t, escalated=esc
            )
            for k, (t, esc) in enumerate(questions)
        ],
    )


# --- primitives (shared with #1945, re-verified here) ----------------------


def test_jaccard_basic() -> None:
    a = frozenset({"alpha", "beta", "gamma"})
    b = frozenset({"alpha", "beta", "delta"})
    assert _jaccard(a, b) == pytest.approx(0.5)


def test_distinctive_terms_strips_glue() -> None:
    assert _distinctive_terms("the alpha and the beta is gamma") == frozenset(
        {"alpha", "beta", "gamma"}
    )


# --- core discovery --------------------------------------------------------


def test_finds_candidate_above_floor() -> None:
    focus = _artifact("inv-focus", insights=["alpha beta gamma"])
    prior = _artifact("inv-prior", questions=["alpha beta delta"])
    report = discover_resolution_candidates(focus, [prior])
    # Jaccard {alpha,beta}/{alpha,beta,gamma,delta} = 2/4 = 0.5 >= 0.30
    assert len(report.candidates) == 1
    cand = report.candidates[0]
    assert cand.overlap_score == pytest.approx(0.5)
    assert set(cand.shared_terms) == {"alpha", "beta"}
    assert cand.focus_insight_node_id == "inv-focus-i0"
    assert cand.prior_question_node_id == "inv-prior-q0"
    assert cand.prior_investigation_id == "inv-prior"
    assert cand.escalated is False


def test_no_candidate_below_floor() -> None:
    # share only 1 of 5 -> 0.2 < 0.30
    focus = _artifact("inv-focus", insights=["alpha beta gamma"])
    prior = _artifact("inv-prior", questions=["alpha delta epsilon"])
    report = discover_resolution_candidates(focus, [prior])
    assert report.candidates == ()


def test_disjoint_subject_no_candidate() -> None:
    focus = _artifact("inv-focus", insights=["alpha beta"])
    prior = _artifact("inv-prior", questions=["gamma delta"])
    report = discover_resolution_candidates(focus, [prior])
    assert report.candidates == ()


# --- honesty rules: empty defer -------------------------------------------


def test_empty_focus_insights_no_candidates() -> None:
    focus = _artifact("inv-focus", questions=["alpha beta"])
    prior = _artifact("inv-prior", questions=["alpha beta gamma"])
    report = discover_resolution_candidates(focus, [prior])
    assert report.candidates == ()


def test_empty_priors_no_candidates() -> None:
    focus = _artifact("inv-focus", insights=["alpha beta gamma"])
    report = discover_resolution_candidates(focus, [])
    assert report.candidates == ()
    assert report.prior_investigation_count == 0
    assert report.prior_open_question_count == 0


def test_prior_with_no_open_questions_no_candidates() -> None:
    focus = _artifact("inv-focus", insights=["alpha beta gamma"])
    prior = _artifact("inv-prior", insights=["alpha beta gamma"])  # no questions
    report = discover_resolution_candidates(focus, [prior])
    assert report.candidates == ()
    assert report.prior_investigation_count == 1
    assert report.prior_open_question_count == 0


# --- honesty rules: self-reference + de-dup --------------------------------


def test_self_reference_skipped() -> None:
    focus = _artifact("inv-A", insights=["alpha beta"], questions=["alpha beta"])
    report = discover_resolution_candidates(focus, [focus])
    # prior shares focus investigation_id -> skipped (intra-artifact is #1929)
    assert report.candidates == ()
    assert report.prior_investigation_count == 0


def test_duplicate_prior_ids_deduplicated() -> None:
    focus = _artifact("inv-focus", insights=["alpha beta gamma"])
    dup1 = _artifact("inv-prior", questions=["alpha beta delta"])
    dup2 = _artifact("inv-prior", questions=["alpha beta epsilon"])  # same id
    report = discover_resolution_candidates(focus, [dup1, dup2])
    assert report.prior_investigation_count == 1
    assert len(report.candidates) == 1  # only dup1's question examined


# --- escalated questions are valid targets --------------------------------


def test_escalated_question_is_valid_target() -> None:
    focus = _artifact("inv-focus", insights=["alpha beta gamma"])
    prior = _artifact("inv-prior", questions=["alpha beta delta"], escalated=True)
    report = discover_resolution_candidates(focus, [prior])
    assert len(report.candidates) == 1
    assert report.candidates[0].escalated is True  # flagged but not excluded


def test_mixed_escalated_and_not_both_candidates() -> None:
    focus = _artifact("inv-focus", insights=["alpha beta"])
    prior = _artifact_with_mixed_questions(
        "inv-prior",
        insights=[],
        questions=[("alpha beta gamma", True), ("alpha beta delta", False)],
    )
    report = discover_resolution_candidates(focus, [prior])
    assert len(report.candidates) == 2
    escalated_flags = {c.escalated for c in report.candidates}
    assert escalated_flags == {True, False}


# --- sorting + determinism -------------------------------------------------


def test_sorted_by_overlap_desc() -> None:
    focus = _artifact("inv-focus", insights=["alpha beta gamma"])
    strong = _artifact("inv-strong", questions=["alpha beta gamma delta"])  # 3/4=0.75
    weak = _artifact("inv-weak", questions=["alpha beta delta"])  # 2/4=0.5
    report = discover_resolution_candidates(focus, [weak, strong])
    scores = [c.overlap_score for c in report.candidates]
    assert scores == sorted(scores, reverse=True)
    assert report.candidates[0].prior_investigation_id == "inv-strong"


def test_determinism_same_inputs_same_report() -> None:
    focus = _artifact("inv-focus", insights=["alpha beta gamma"])
    prior = _artifact("inv-prior", questions=["alpha beta delta"])
    a = discover_resolution_candidates(focus, [prior])
    b = discover_resolution_candidates(focus, [prior])
    assert a == b


def test_tiebreak_by_node_ids_stable() -> None:
    focus = _artifact("inv-focus", insights=["alpha beta"])
    p_b = _artifact("inv-B", questions=["alpha beta"])  # 1.0
    p_a = _artifact("inv-A", questions=["alpha beta"])  # 1.0
    report = discover_resolution_candidates(focus, [p_b, p_a])
    assert report.candidates[0].prior_investigation_id == "inv-A"
    assert report.candidates[1].prior_investigation_id == "inv-B"


# --- counts ---------------------------------------------------------------


def test_counts_reflect_examined_and_connected() -> None:
    focus = _artifact("inv-focus", insights=["alpha beta gamma"])
    connected = _artifact(
        "inv-conn", questions=["alpha beta delta"]
    )  # 0.5 -> candidate
    unconnected = _artifact(
        "inv-none", questions=["zeta eta theta"]
    )  # 0.0 -> none
    empty_q = _artifact("inv-emptyq", questions=[])  # no questions
    report = discover_resolution_candidates(focus, [connected, unconnected, empty_q])
    assert report.prior_investigation_count == 3
    assert report.prior_open_question_count == 2  # empty_q has none
    assert report.connected_prior_count == 1


def test_multiple_questions_in_one_prior() -> None:
    focus = _artifact("inv-focus", insights=["alpha beta"])
    prior = _artifact_with_mixed_questions(
        "inv-prior",
        insights=[],
        questions=[("alpha beta gamma", False), ("zeta eta", False)],
    )
    report = discover_resolution_candidates(focus, [prior])
    assert len(report.candidates) == 1  # only the alpha-beta question matches
    assert report.prior_open_question_count == 2
    assert report.connected_prior_count == 1


# --- provenance / auditability --------------------------------------------


def test_shared_terms_non_empty_for_every_candidate() -> None:
    focus = _artifact("inv-focus", insights=["alpha beta gamma"])
    prior = _artifact("inv-prior", questions=["alpha beta delta"])
    report = discover_resolution_candidates(focus, [prior])
    for c in report.candidates:
        assert len(c.shared_terms) > 0


def test_overlap_score_in_unit_interval() -> None:
    focus = _artifact("inv-focus", insights=["alpha beta gamma delta"])
    priors = [
        _artifact(f"inv-{k}", questions=[" ".join(["alpha", "beta", "gamma", "delta", "epsilon"][: k + 1])])
        for k in range(1, 5)
    ]
    report = discover_resolution_candidates(focus, priors, min_overlap=0.01)
    for c in report.candidates:
        assert 0.0 <= c.overlap_score <= 1.0


def test_focus_investigation_id_carried_through() -> None:
    focus = _artifact("inv-777", insights=["alpha beta"])
    prior = _artifact("inv-prior", questions=["alpha beta"])
    assert discover_resolution_candidates(focus, [prior]).focus_investigation_id == "inv-777"


def test_authority_is_always_advisory() -> None:
    focus = _artifact("inv-focus", insights=["alpha beta"])
    prior = _artifact("inv-prior", questions=["alpha beta"])
    assert discover_resolution_candidates(focus, [prior]).authority == "advisory"


def test_report_is_immutable() -> None:
    report = discover_resolution_candidates(
        _artifact("inv-focus", insights=["alpha beta"]),
        [_artifact("inv-p", questions=["alpha beta"])],
    )
    assert isinstance(report, ResolutionCandidateReport)
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.connected_prior_count = 99  # type: ignore[misc]


def test_candidate_is_immutable() -> None:
    report = discover_resolution_candidates(
        _artifact("inv-focus", insights=["alpha beta"]),
        [_artifact("inv-p", questions=["alpha beta"])],
    )
    cand = report.candidates[0]
    assert isinstance(cand, ResolutionCandidate)
    with pytest.raises(dataclasses.FrozenInstanceError):
        cand.overlap_score = 0.0  # type: ignore[misc]


# --- custom min_overlap ----------------------------------------------------


def test_custom_min_overlap_filters() -> None:
    focus = _artifact("inv-focus", insights=["alpha beta gamma"])
    prior = _artifact("inv-prior", questions=["alpha beta gamma delta"])  # 0.75
    assert len(discover_resolution_candidates(focus, [prior]).candidates) == 1
    assert (
        len(discover_resolution_candidates(focus, [prior], min_overlap=0.80).candidates)
        == 0
    )


def test_boundary_overlap_is_included() -> None:
    focus = _artifact("inv-focus", insights=["alpha beta gamma"])
    prior = _artifact("inv-prior", questions=["alpha beta delta"])  # 0.5
    assert len(discover_resolution_candidates(focus, [prior]).candidates) == 1
    assert (
        len(discover_resolution_candidates(focus, [prior], min_overlap=0.5).candidates)
        == 1
    )


# --- validation ------------------------------------------------------------


@pytest.mark.parametrize("bad", [0.0, -0.1, 1.0001, 2.0])
def test_validation_rejects_bad_min_overlap(bad: float) -> None:
    with pytest.raises(ResolutionCandidateError, match="min_overlap"):
        discover_resolution_candidates(
            _artifact("inv-focus", insights=["alpha beta"]),
            [_artifact("inv-p", questions=["alpha beta"])],
            min_overlap=bad,
        )


# --- public api exports ----------------------------------------------------


def test_public_api_exports() -> None:
    from substrate.cross_reference import resolution_candidates as mod

    assert set(mod.__all__) == {
        "ResolutionCandidate",
        "ResolutionCandidateError",
        "ResolutionCandidateReport",
        "discover_resolution_candidates",
    }
    assert issubclass(mod.ResolutionCandidateError, ValueError)
    assert dataclasses.is_dataclass(mod.ResolutionCandidateReport)
    assert dataclasses.is_dataclass(mod.ResolutionCandidate)
