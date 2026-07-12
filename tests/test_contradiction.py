"""Tests for the artifact-level contradiction detector.

Exercises the two-stage precision design (same-subject Jaccard + asymmetric
negation), the lexical-floor honesty, the <2-insights honesty rule, the
contradiction surface, and purity/immutability/determinism.

Fixtures use deliberate nonsense-token vocabularies so Jaccard is countable and
no accidental shared common words perturb the overlap.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.deep_research_quality.contradiction import (
    ContradictionError,
    ContradictionPair,
    ContradictionReport,
    detect_contradictions,
)
from substrate.research_artifact.schema import (
    ArtifactInsight,
    ResearchArtifactBody,
)


def _artifact(
    insights: list[tuple[str, str]],
    *,
    investigation_id: str = "inv-test",
) -> ResearchArtifactBody:
    return ResearchArtifactBody(
        investigation_id=investigation_id,
        problem_question="the question",
        insights=[ArtifactInsight(node_id=nid, text=text) for nid, text in insights],
    )


# --- two-stage precision: contradiction requires BOTH conditions ----------
# Nonsense tokens: alpha/beta/gamma are distinctive (non-stop-word). Negation
# carried by "not" (a stop-word, so it never inflates Jaccard) or a negation
# verb. This makes every Jaccard exactly countable.


def test_same_subject_asymmetric_negation_is_a_contradiction() -> None:
    # A: "alpha beta" -> {alpha, beta} (not negated)
    # B: "alpha beta gamma not" -> {alpha, beta, gamma} (negated via stop-word "not")
    # Jaccard 2/3 ~= 0.667 >= 0.30; asymmetric negation -> contradiction.
    art = _artifact(
        [
            ("i1", "alpha beta"),
            ("i2", "alpha beta gamma not"),
        ]
    )
    report = detect_contradictions(art)
    assert len(report.contradiction_pairs) == 1
    pair = report.contradiction_pairs[0]
    assert isinstance(pair, ContradictionPair)
    assert pair.node_id_a == "i1"
    assert pair.node_id_b == "i2"
    assert pair.subject_overlap == pytest.approx(2 / 3)
    assert pair.shared_subject_terms == ("alpha", "beta")
    assert pair.negated_side == "b"


def test_same_subject_both_negated_is_not_a_contradiction() -> None:
    art = _artifact(
        [
            ("i1", "alpha beta not present"),
            ("i2", "alpha beta gamma not present"),
        ]
    )
    report = detect_contradictions(art)
    assert report.contradiction_pairs == ()


def test_different_subjects_with_negation_is_not_a_contradiction() -> None:
    # No shared distinctive terms -> Jaccard 0 < 0.30.
    art = _artifact(
        [
            ("i1", "alpha beta present"),
            ("i2", "kappa lambda not present"),
        ]
    )
    report = detect_contradictions(art)
    assert report.contradiction_pairs == ()


def test_high_overlap_no_negation_is_redundancy_not_contradiction() -> None:
    art = _artifact(
        [
            ("i1", "alpha beta gamma present"),
            ("i2", "alpha beta gamma delta present"),
        ]
    )
    report = detect_contradictions(art)
    assert report.contradiction_pairs == ()


# --- honesty rules: too few insights --------------------------------------


def test_empty_artifact() -> None:
    report = detect_contradictions(_artifact([]))
    assert report.insight_count == 0
    assert report.pair_count == 0
    assert report.max_subject_overlap is None
    assert report.contradiction_ratio == pytest.approx(0.0)
    assert report.contradiction_pairs == ()


def test_single_insight() -> None:
    report = detect_contradictions(_artifact([("i1", "alpha beta gamma")]))
    assert report.insight_count == 1
    assert report.pair_count == 0
    assert report.max_subject_overlap is None
    assert report.contradiction_pairs == ()


# --- subject threshold ----------------------------------------------------


def test_below_subject_threshold_not_flagged() -> None:
    # A: {alpha}  B: {alpha, beta, gamma, delta, epsilon, zeta}
    # Jaccard 1/6 ~= 0.167 < 0.30; asymmetric negation but too little overlap.
    art = _artifact(
        [
            ("i1", "alpha"),
            ("i2", "alpha beta gamma delta epsilon zeta not"),
        ]
    )
    report = detect_contradictions(art)
    assert report.contradiction_pairs == ()
    assert report.max_subject_overlap == pytest.approx(1 / 6)
    assert any("below subject threshold" in n for n in report.notes)


def test_custom_threshold_catches_more() -> None:
    # Same low-overlap pair: 1/6 ~= 0.167. Not at 0.30; flagged at 0.15.
    art = _artifact(
        [
            ("i1", "alpha"),
            ("i2", "alpha beta gamma delta epsilon zeta not"),
        ]
    )
    assert detect_contradictions(art).contradiction_pairs == ()
    assert len(detect_contradictions(art, subject_threshold=0.15).contradiction_pairs) == 1


# --- contradiction surface ------------------------------------------------


def test_contradiction_ratio() -> None:
    # i1-i2 conflict; i3 distinct from both.
    art = _artifact(
        [
            ("i1", "alpha beta"),
            ("i2", "alpha beta gamma not"),
            ("i3", "omega sigma theta"),
        ]
    )
    report = detect_contradictions(art)
    assert len(report.contradiction_pairs) == 1
    assert report.contradicting_insight_ids == ("i1", "i2")
    assert report.contradiction_ratio == pytest.approx(2 / 3)


def test_pairs_sorted_by_overlap_desc() -> None:
    # i1-i2 overlap 2/3; i3-i4 overlap 3/3=1.0. The 1.0 pair sorts first.
    art = _artifact(
        [
            ("i1", "alpha beta"),
            ("i2", "alpha beta gamma not"),
            ("i3", "kappa lambda mu"),
            ("i4", "kappa lambda mu not"),
        ]
    )
    report = detect_contradictions(art)
    assert len(report.contradiction_pairs) == 2
    assert report.contradiction_pairs[0].subject_overlap == pytest.approx(1.0)
    assert report.contradiction_pairs[1].subject_overlap == pytest.approx(2 / 3)


def test_pair_count_is_n_choose_2() -> None:
    for n in range(6):
        insights = [(f"i{k}", f"alpha{k} beta{k}") for k in range(n)]
        report = detect_contradictions(_artifact(insights))
        assert report.pair_count == n * (n - 1) // 2


def test_overlap_in_unit_interval() -> None:
    art = _artifact(
        [
            ("i1", "alpha beta gamma delta epsilon present"),
            ("i2", "alpha beta zeta eta theta not present"),
            ("i3", "kappa lambda mu nu xi present"),
        ]
    )
    report = detect_contradictions(art)
    for pair in report.contradiction_pairs:
        assert 0.0 <= pair.subject_overlap <= 1.0
    if report.max_subject_overlap is not None:
        assert 0.0 <= report.max_subject_overlap <= 1.0


def test_negated_side_correct() -> None:
    art = _artifact(
        [
            ("a", "alpha beta"),
            ("b", "alpha beta not"),
        ]
    )
    assert detect_contradictions(art).contradiction_pairs[0].negated_side == "b"
    art2 = _artifact(
        [
            ("a", "alpha beta not"),
            ("b", "alpha beta"),
        ]
    )
    assert detect_contradictions(art2).contradiction_pairs[0].negated_side == "a"


# --- negation markers -----------------------------------------------------


@pytest.mark.parametrize("neg_word", ["not", "never", "cannot", "fails", "without", "lacks"])
def test_various_negation_markers_detected(neg_word: str) -> None:
    art = _artifact(
        [
            ("i1", "alpha beta"),
            ("i2", f"alpha beta {neg_word}"),
        ]
    )
    report = detect_contradictions(art)
    assert len(report.contradiction_pairs) == 1


# --- provenance / purity --------------------------------------------------


def test_artifact_id_carried_through() -> None:
    art = _artifact([("i1", "alpha"), ("i2", "beta")], investigation_id="inv-777")
    assert detect_contradictions(art).artifact_id == "inv-777"


def test_authority_is_always_advisory() -> None:
    art = _artifact([("i1", "alpha beta"), ("i2", "gamma delta")])
    assert detect_contradictions(art).authority == "advisory"


def test_report_is_immutable() -> None:
    art = _artifact([("i1", "alpha beta"), ("i2", "alpha beta not")])
    report = detect_contradictions(art)
    assert isinstance(report, ContradictionReport)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.contradiction_ratio = 1.0  # type: ignore[misc]
    pair = report.contradiction_pairs[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        pair.subject_overlap = 0.0  # type: ignore[misc]


def test_determinism_same_artifact_same_report() -> None:
    art = _artifact(
        [
            ("i1", "alpha beta"),
            ("i2", "alpha beta not"),
            ("i3", "omega sigma theta"),
        ]
    )
    assert detect_contradictions(art) == detect_contradictions(art)


def test_notes_describe_findings() -> None:
    art = _artifact(
        [
            ("i1", "alpha beta"),
            ("i2", "alpha beta not"),
        ]
    )
    joined = " | ".join(detect_contradictions(art).notes)
    assert "lexical floor" in joined.lower()
    assert "contradiction ratio" in joined.lower()
    assert "wrestle" in joined.lower()


# --- validation -----------------------------------------------------------


@pytest.mark.parametrize("bad", [0.0, -0.1, 1.0001, 2.0])
def test_validation_rejects_bad_threshold(bad: float) -> None:
    with pytest.raises(ContradictionError, match="subject_threshold"):
        detect_contradictions(_artifact([("i1", "a"), ("i2", "b")]), subject_threshold=bad)


def test_public_api_exports() -> None:
    from substrate.deep_research_quality import contradiction as mod

    assert set(mod.__all__) == {
        "ContradictionError",
        "ContradictionPair",
        "ContradictionReport",
        "detect_contradictions",
    }
    assert issubclass(mod.ContradictionError, ValueError)
    assert dataclasses.is_dataclass(mod.ContradictionPair)
    assert dataclasses.is_dataclass(mod.ContradictionReport)
