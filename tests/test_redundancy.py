"""Tests for the research-artifact insight-redundancy detector.

Exercises the load-bearing invariants: Jaccard near-duplicate detection over
distinctive terms, the lexical-floor honesty (no stemming, stop-words stripped),
the redundancy surface (pairs, implicated insights, ratio), the honesty rules
(max_similarity None when <2 insights), purity/immutability/determinism,
provenance, and input validation.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.deep_research_quality.redundancy import (
    RedundancyError,
    RedundancyReport,
    RedundantPair,
    detect_redundancy,
)
from substrate.research_artifact.schema import (
    ArtifactInsight,
    ResearchArtifactBody,
)


def _artifact(
    insights: list[tuple[str, str]],
    *,
    investigation_id: str = "inv-test",
    problem_question: str = "the question",
) -> ResearchArtifactBody:
    return ResearchArtifactBody(
        investigation_id=investigation_id,
        problem_question=problem_question,
        insights=[ArtifactInsight(node_id=nid, text=text) for nid, text in insights],
    )


# --- core detection -------------------------------------------------------


def test_near_duplicate_pair_flagged() -> None:
    # distinctive A: transformer attention scales model size (5)
    # distinctive B: transformer attention scales model size quadratically (6)
    # Jaccard 5/6 ~= 0.833 >= 0.70 -> flagged
    art = _artifact(
        [
            ("i1", "transformer attention scales with model size"),
            ("i2", "transformer attention scales with model size quadratically"),
        ]
    )
    report = detect_redundancy(art)
    assert isinstance(report, RedundancyReport)
    assert len(report.redundant_pairs) == 1
    pair = report.redundant_pairs[0]
    assert isinstance(pair, RedundantPair)
    assert pair.node_id_a == "i1"
    assert pair.node_id_b == "i2"
    assert pair.similarity == pytest.approx(5 / 6)
    assert pair.shared_terms == ("attention", "model", "scales", "size", "transformer")


def test_exact_duplicate_flagged_at_one() -> None:
    art = _artifact(
        [
            ("i1", "the model uses self attention"),
            ("i2", "the model uses self attention"),
        ]
    )
    report = detect_redundancy(art)
    assert len(report.redundant_pairs) == 1
    assert report.redundant_pairs[0].similarity == pytest.approx(1.0)


def test_distinct_insights_have_no_redundancy() -> None:
    art = _artifact(
        [
            ("i1", "quantum coherence limits error rates"),
            ("i2", "supply chain logistics optimization model"),
            ("i3", "photosynthesis chlorophyll light absorption"),
        ]
    )
    report = detect_redundancy(art)
    assert report.redundant_pairs == ()
    assert report.redundancy_ratio == pytest.approx(0.0)
    assert report.redundant_insight_ids == ()


def test_below_threshold_not_flagged_but_max_similarity_reported() -> None:
    # distinctive A: alpha beta gamma delta epsilon (5)
    # distinctive B: alpha beta gamma zeta eta (5)
    # intersection 3, union 7 -> 3/7 ~= 0.4286 < 0.70 (not flagged)
    art = _artifact(
        [
            ("i1", "alpha beta gamma delta epsilon"),
            ("i2", "alpha beta gamma zeta eta"),
        ]
    )
    report = detect_redundancy(art)
    assert report.redundant_pairs == ()
    assert report.max_similarity == pytest.approx(3 / 7)
    assert any("below threshold" in n for n in report.notes)


def test_custom_threshold_catches_more() -> None:
    art = _artifact(
        [
            ("i1", "alpha beta gamma delta epsilon"),
            ("i2", "alpha beta gamma zeta eta"),
        ]
    )
    # 3/7 ~= 0.4286: not at 0.70, flagged at 0.40
    assert detect_redundancy(art).redundant_pairs == ()
    assert len(detect_redundancy(art, threshold=0.40).redundant_pairs) == 1


# --- lexical floor honesty ------------------------------------------------


def test_stop_words_stripped_so_glue_does_not_inflate() -> None:
    # "the model is good" vs "the model is bad": only {model} shared among signal
    # words -> 1/3 ~= 0.333 (not flagged). Without stripping, "the model is"
    # would inflate it to 0.75 (a false positive).
    art = _artifact(
        [
            ("i1", "the model is good"),
            ("i2", "the model is bad"),
        ]
    )
    report = detect_redundancy(art)
    assert report.redundant_pairs == ()
    assert report.max_similarity == pytest.approx(1 / 3)


def test_no_stemming_scale_neq_scales() -> None:
    # {model, scales, well} vs {model, scale, good} -> 1/5 = 0.2 (not flagged)
    art = _artifact(
        [
            ("i1", "the model scales well"),
            ("i2", "the model scale is good"),
        ]
    )
    report = detect_redundancy(art)
    assert report.redundant_pairs == ()
    assert report.max_similarity == pytest.approx(0.2)


def test_shared_terms_exclude_stop_words() -> None:
    art = _artifact(
        [
            ("i1", "the model is efficient"),
            ("i2", "a model was efficient"),
        ]
    )
    report = detect_redundancy(art)
    assert len(report.redundant_pairs) == 1
    assert report.redundant_pairs[0].shared_terms == ("efficient", "model")
    assert report.redundant_pairs[0].similarity == pytest.approx(1.0)


# --- honesty rules: too-few / empty insights ------------------------------


def test_empty_artifact() -> None:
    report = detect_redundancy(_artifact([]))
    assert report.insight_count == 0
    assert report.pair_count == 0
    assert report.max_similarity is None
    assert report.redundancy_ratio == pytest.approx(0.0)
    assert report.redundant_pairs == ()


def test_single_insight() -> None:
    report = detect_redundancy(_artifact([("i1", "alpha beta gamma")]))
    assert report.insight_count == 1
    assert report.pair_count == 0
    assert report.max_similarity is None
    assert report.redundant_pairs == ()


def test_two_empty_term_insights_score_zero() -> None:
    # both stop-word-only -> empty distinctive sets -> Jaccard 0.0, not flagged.
    art = _artifact([("i1", "the of a"), ("i2", "is the was")])
    report = detect_redundancy(art)
    assert report.pair_count == 1
    assert report.max_similarity == pytest.approx(0.0)
    assert report.redundant_pairs == ()


# --- redundancy surface ---------------------------------------------------


def test_redundancy_ratio() -> None:
    # A,B near-dup (0.75); C,D distinct from each other and from A,B.
    art = _artifact(
        [
            ("i1", "alpha beta gamma"),
            ("i2", "alpha beta gamma delta"),
            ("i3", "completely different topic"),
            ("i4", "another unique subject matter"),
        ]
    )
    report = detect_redundancy(art)
    # i1 vs i2: 3/4 = 0.75 >= 0.70 -> flagged
    assert len(report.redundant_pairs) == 1
    assert report.redundant_insight_ids == ("i1", "i2")
    assert report.redundancy_ratio == pytest.approx(0.5)
    assert report.pair_count == 6


def test_transitive_cluster_implies_all_insights() -> None:
    # A-B 0.8 flagged, A-C 0.8 flagged, B-C 4/6 ~= 0.667 NOT flagged.
    # All three are implicated via the two flagged pairs.
    art = _artifact(
        [
            ("A", "alpha beta gamma delta"),
            ("B", "alpha beta gamma delta epsilon"),
            ("C", "alpha beta gamma delta zeta"),
        ]
    )
    report = detect_redundancy(art)
    assert {p.node_id_a for p in report.redundant_pairs} | {
        p.node_id_b for p in report.redundant_pairs
    } == {"A", "B", "C"}
    assert report.redundant_insight_ids == ("A", "B", "C")
    assert report.redundancy_ratio == pytest.approx(1.0)


def test_redundant_pairs_sorted_by_similarity_then_ids() -> None:
    # A-B exact (1.0); A-C and B-C both 0.8; (A,C) before (B,C) by id ordering.
    art = _artifact(
        [
            ("A", "alpha beta gamma delta"),
            ("B", "alpha beta gamma delta"),
            ("C", "alpha beta gamma delta epsilon"),
        ]
    )
    report = detect_redundancy(art)
    sims = [p.similarity for p in report.redundant_pairs]
    assert sims == sorted(sims, reverse=True)
    assert report.redundant_pairs[0].similarity == pytest.approx(1.0)
    assert report.redundant_pairs[0].node_id_a == "A"
    assert report.redundant_pairs[0].node_id_b == "B"
    # the two 0.8 pairs: (A,C) then (B,C)
    rest = report.redundant_pairs[1:]
    assert (rest[0].node_id_a, rest[0].node_id_b) == ("A", "C")
    assert (rest[1].node_id_a, rest[1].node_id_b) == ("B", "C")


def test_pair_count_is_n_choose_2() -> None:
    for n in range(6):
        insights = [(f"i{k}", f"unique token set number {k}") for k in range(n)]
        report = detect_redundancy(_artifact(insights))
        assert report.pair_count == n * (n - 1) // 2


def test_similarity_in_unit_interval() -> None:
    art = _artifact(
        [
            ("i1", "alpha beta gamma delta epsilon"),
            ("i2", "alpha beta zeta eta theta"),
            ("i3", "kappa lambda mu nu xi"),
        ]
    )
    report = detect_redundancy(art)
    for pair in report.redundant_pairs:
        assert 0.0 <= pair.similarity <= 1.0
    if report.max_similarity is not None:
        assert 0.0 <= report.max_similarity <= 1.0


# --- provenance / purity --------------------------------------------------


def test_artifact_id_carried_through() -> None:
    art = _artifact([("i1", "a"), ("i2", "b")], investigation_id="inv-777")
    assert detect_redundancy(art).artifact_id == "inv-777"


def test_authority_is_always_advisory() -> None:
    art = _artifact([("i1", "a"), ("i2", "b")])
    assert detect_redundancy(art).authority == "advisory"


def test_report_and_pairs_are_immutable() -> None:
    art = _artifact(
        [
            ("i1", "alpha beta gamma"),
            ("i2", "alpha beta gamma delta"),
        ]
    )
    report = detect_redundancy(art)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.redundancy_ratio = 1.0  # type: ignore[misc]
    pair = report.redundant_pairs[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        pair.similarity = 0.0  # type: ignore[misc]


def test_determinism_same_artifact_same_report() -> None:
    art = _artifact(
        [
            ("i1", "alpha beta gamma delta"),
            ("i2", "alpha beta gamma delta epsilon"),
            ("i3", "kappa lambda"),
        ]
    )
    assert detect_redundancy(art) == detect_redundancy(art)


def test_notes_describe_findings() -> None:
    art = _artifact(
        [
            ("i1", "alpha beta gamma"),
            ("i2", "alpha beta gamma delta"),
        ]
    )
    joined = " | ".join(detect_redundancy(art).notes)
    assert "lexical floor" in joined.lower()
    assert "compared 1 insight pair" in joined.lower()
    assert "1 redundant pair" in joined.lower()
    assert "at/above threshold" in joined.lower()


# --- validation -----------------------------------------------------------


@pytest.mark.parametrize("bad", [0.0, -0.1, 1.0001, 2.0])
def test_validation_rejects_bad_threshold(bad: float) -> None:
    with pytest.raises(RedundancyError, match="threshold"):
        detect_redundancy(_artifact([("i1", "a"), ("i2", "b")]), threshold=bad)


def test_threshold_one_is_valid() -> None:
    # only exact duplicates flagged at threshold 1.0
    art = _artifact(
        [
            ("i1", "alpha beta gamma delta"),
            ("i2", "alpha beta gamma delta epsilon"),
            ("i3", "alpha beta gamma delta"),
        ]
    )
    report = detect_redundancy(art, threshold=1.0)
    # i1-i3 exact (1.0) flagged; i1-i2 (0.8) and i2-i3 (0.8) not.
    assert len(report.redundant_pairs) == 1
    assert {report.redundant_pairs[0].node_id_a, report.redundant_pairs[0].node_id_b} == {
        "i1",
        "i3",
    }


def test_public_api_exports() -> None:
    from substrate.deep_research_quality import redundancy as mod

    assert set(mod.__all__) == {
        "RedundancyError",
        "RedundantPair",
        "RedundancyReport",
        "detect_redundancy",
    }
    assert issubclass(mod.RedundancyError, ValueError)
    assert dataclasses.is_dataclass(mod.RedundantPair)
    assert dataclasses.is_dataclass(mod.RedundancyReport)
