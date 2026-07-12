"""Tests for question cross-link discovery (question↔question clustering).

Exercises: subject-overlap links, interrogative stripping, transitive-closure
clusters, singleton detection, self-reference skip, within-artifact eligibility,
empty-defer, determinism, validation, purity/immutability. Fixtures use BARE
NONSENSE TOKENS so every ratio is exactly countable.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.cross_reference.question_links import (
    QuestionCluster,
    QuestionLink,
    QuestionLinkError,
    QuestionLinkReport,
    discover_question_links,
)
from substrate.research_artifact.schema import (
    ArtifactQuestion,
    ResearchArtifactBody,
)


def _artifact(
    investigation_id: str,
    questions: list[str],
) -> ResearchArtifactBody:
    return ResearchArtifactBody(
        investigation_id=investigation_id,
        problem_question="the question",
        open_questions=[
            ArtifactQuestion(node_id=f"{investigation_id}-q{k}", text=t)
            for k, t in enumerate(questions)
        ],
    )


# --- core: subject-overlap links -------------------------------------------


def test_finds_link_above_floor() -> None:
    a = _artifact("inv-A", ["alpha beta gamma"])
    b = _artifact("inv-B", ["alpha beta delta"])
    report = discover_question_links([a, b])
    assert len(report.links) == 1
    lk = report.links[0]
    assert lk.overlap_score == pytest.approx(0.5)
    assert set(lk.shared_terms) == {"alpha", "beta"}


def test_no_link_below_floor() -> None:
    # share only 1 of 5 -> 0.2 < 0.30
    a = _artifact("inv-A", ["alpha beta gamma"])
    b = _artifact("inv-B", ["alpha delta epsilon"])
    report = discover_question_links([a, b])
    assert report.links == ()


def test_disjoint_questions_no_link() -> None:
    a = _artifact("inv-A", ["alpha beta"])
    b = _artifact("inv-B", ["gamma delta"])
    report = discover_question_links([a, b])
    assert report.links == ()


# --- interrogative stripping (load-bearing) -------------------------------


def test_interrogatives_do_not_inflate_overlap() -> None:
    # "how what why" are interrogatives — stripped. Only content words count.
    a = _artifact("inv-A", ["how what alpha beta"])
    b = _artifact("inv-B", ["how what gamma delta"])
    report = discover_question_links([a, b])
    # No shared content terms -> no link despite shared interrogatives
    assert report.links == ()


def test_interrogative_question_with_shared_content_links() -> None:
    # shared content: {alpha} / {alpha, work, makes, effective} = 1/4 = 0.25 < 0.30
    # So actually no link at default floor. Use higher-overlap fixture:
    a2 = _artifact("inv-A", ["how does alpha beta work"])
    b2 = _artifact("inv-B", ["what makes alpha beta effective"])
    r2 = discover_question_links([a2, b2])
    # shared: {alpha, beta} / {alpha, beta, work, makes, effective} = 2/5 = 0.4 >= 0.30
    assert len(r2.links) == 1


# --- clusters: transitive closure ------------------------------------------


def test_pair_forms_cluster_of_two() -> None:
    a = _artifact("inv-A", ["alpha beta"])
    b = _artifact("inv-B", ["alpha beta gamma"])
    c = _artifact("inv-C", ["zeta eta"])
    report = discover_question_links([a, b, c])
    sizes = sorted(cl.size for cl in report.clusters)
    assert sizes == [1, 2]  # one singleton, one pair
    pair = next(cl for cl in report.clusters if cl.size == 2)
    assert len(pair.question_node_ids) == 2


def test_transitive_closure_three_question_cluster() -> None:
    # q0-q1 linked (2/3=0.67), q1-q2 linked (2/4=0.5), q0-q2 NOT linked (1/4=0.25)
    # But transitive closure puts all three in one cluster.
    a = _artifact("inv-A", ["alpha beta"])
    b = _artifact("inv-B", ["alpha beta gamma"])
    c = _artifact("inv-C", ["alpha gamma delta"])
    report = discover_question_links([a, b, c])
    # 2 direct links: q0-q1, q1-q2. q0-q2 not directly linked.
    assert len(report.links) == 2
    # But one cluster of size 3 (transitive closure)
    big = [cl for cl in report.clusters if cl.size >= 3]
    assert len(big) == 1
    assert big[0].size == 3


def test_isolated_question_is_singleton() -> None:
    a = _artifact("inv-A", ["alpha beta"])
    b = _artifact("inv-B", ["zeta eta"])
    report = discover_question_links([a, b])
    assert report.singleton_count == 2
    assert report.linked_question_count == 0


def test_cluster_investigation_ids_distinct() -> None:
    a = _artifact("inv-A", ["alpha beta"])
    b = _artifact("inv-B", ["alpha beta gamma"])
    report = discover_question_links([a, b])
    pair = next(cl for cl in report.clusters if cl.size == 2)
    assert set(pair.investigation_ids) == {"inv-A", "inv-B"}


def test_within_artifact_questions_link() -> None:
    # Questions within the SAME artifact are eligible (questions are cross-cutting)
    art = _artifact("inv-A", ["alpha beta gamma", "alpha beta delta"])
    report = discover_question_links([art])
    assert len(report.links) == 1
    assert report.links[0].question_a_investigation_id == "inv-A"
    assert report.links[0].question_b_investigation_id == "inv-A"


# --- honesty rules ---------------------------------------------------------


def test_self_reference_skipped() -> None:
    # The same node_id never links to itself (handled by i < j iteration)
    art = _artifact("inv-A", ["alpha beta", "alpha beta"])
    report = discover_question_links([art])
    # Two distinct questions with identical text -> linked (different node_ids)
    assert len(report.links) == 1


def test_empty_artifacts_no_links() -> None:
    report = discover_question_links([])
    assert report.links == ()
    assert report.clusters == ()
    assert report.total_questions == 0


def test_artifact_with_no_questions_no_links() -> None:
    art = ResearchArtifactBody(
        investigation_id="inv-A",
        problem_question="the question",
        open_questions=[],
    )
    report = discover_question_links([art])
    assert report.links == ()
    assert report.total_questions == 0
    assert report.singleton_count == 0


def test_question_with_no_distinctive_terms_skipped() -> None:
    a = _artifact("inv-A", ["the and is of"])
    b = _artifact("inv-B", ["the and is of"])
    report = discover_question_links([a, b])
    assert report.links == ()


# --- counts ----------------------------------------------------------------


def test_counts_accurate() -> None:
    a = _artifact("inv-A", ["alpha beta", "zeta eta"])
    b = _artifact("inv-B", ["alpha beta gamma"])
    report = discover_question_links([a, b])
    assert report.total_questions == 3
    # "alpha beta" and "alpha beta gamma" linked (2/3=0.67); "zeta eta" singleton
    assert report.linked_question_count == 2
    assert report.singleton_count == 1


def test_all_questions_linked_no_singletons() -> None:
    a = _artifact("inv-A", ["alpha beta", "alpha beta gamma"])
    report = discover_question_links([a])
    assert report.singleton_count == 0
    assert report.linked_question_count == 2


# --- sorting + determinism -------------------------------------------------


def test_links_sorted_by_overlap_desc() -> None:
    a = _artifact("inv-A", ["alpha beta gamma"])
    b = _artifact("inv-B", ["alpha beta gamma delta"])  # 3/4=0.75
    c = _artifact("inv-C", ["alpha beta delta"])  # 2/4=0.5
    report = discover_question_links([a, b, c])
    scores = [lk.overlap_score for lk in report.links]
    assert scores == sorted(scores, reverse=True)


def test_clusters_sorted_by_size_desc() -> None:
    a = _artifact("inv-A", ["alpha beta", "alpha beta gamma", "alpha beta delta"])
    b = _artifact("inv-B", ["zeta eta"])
    report = discover_question_links([a, b])
    sizes = [cl.size for cl in report.clusters]
    assert sizes == sorted(sizes, reverse=True)
    assert sizes[0] == 3  # the alpha-beta cluster


def test_determinism_same_inputs_same_report() -> None:
    a = _artifact("inv-A", ["alpha beta"])
    b = _artifact("inv-B", ["alpha beta gamma"])
    assert discover_question_links([a, b]) == discover_question_links([a, b])


# --- provenance / auditability --------------------------------------------


def test_shared_terms_non_empty_for_every_link() -> None:
    a = _artifact("inv-A", ["alpha beta"])
    b = _artifact("inv-B", ["alpha beta gamma"])
    report = discover_question_links([a, b])
    for lk in report.links:
        assert len(lk.shared_terms) > 0


def test_overlap_score_in_unit_interval() -> None:
    arts = [
        _artifact(f"inv-{k}", [" ".join(["alpha", "beta", "gamma", "delta", "epsilon"][: k + 1])])
        for k in range(1, 5)
    ]
    report = discover_question_links(arts, min_overlap=0.01)
    for lk in report.links:
        assert 0.0 <= lk.overlap_score <= 1.0


def test_authority_is_always_advisory() -> None:
    a = _artifact("inv-A", ["alpha beta"])
    b = _artifact("inv-B", ["alpha beta"])
    assert discover_question_links([a, b]).authority == "advisory"


def test_report_is_immutable() -> None:
    a = _artifact("inv-A", ["alpha beta"])
    b = _artifact("inv-B", ["alpha beta"])
    report = discover_question_links([a, b])
    assert isinstance(report, QuestionLinkReport)
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.linked_question_count = 99  # type: ignore[misc]


def test_link_is_immutable() -> None:
    a = _artifact("inv-A", ["alpha beta"])
    b = _artifact("inv-B", ["alpha beta"])
    report = discover_question_links([a, b])
    lk = report.links[0]
    assert isinstance(lk, QuestionLink)
    with pytest.raises(dataclasses.FrozenInstanceError):
        lk.overlap_score = 0.0  # type: ignore[misc]


def test_cluster_is_immutable() -> None:
    a = _artifact("inv-A", ["alpha beta"])
    b = _artifact("inv-B", ["alpha beta"])
    report = discover_question_links([a, b])
    cl = next(c for c in report.clusters if c.size >= 2)
    assert isinstance(cl, QuestionCluster)
    with pytest.raises(dataclasses.FrozenInstanceError):
        cl.size = 99  # type: ignore[misc]


# --- custom min_overlap ----------------------------------------------------


def test_custom_min_overlap_filters() -> None:
    a = _artifact("inv-A", ["alpha beta gamma"])
    b = _artifact("inv-B", ["alpha beta gamma delta"])  # 0.75
    assert len(discover_question_links([a, b]).links) == 1
    assert len(discover_question_links([a, b], min_overlap=0.80).links) == 0


def test_min_overlap_recorded() -> None:
    a = _artifact("inv-A", ["alpha beta"])
    b = _artifact("inv-B", ["alpha beta"])
    report = discover_question_links([a, b], min_overlap=0.5)
    assert report.min_overlap == pytest.approx(0.5)


# --- validation ------------------------------------------------------------


@pytest.mark.parametrize("bad", [0.0, -0.1, 1.0001, 2.0])
def test_validation_rejects_bad_min_overlap(bad: float) -> None:
    with pytest.raises(QuestionLinkError, match="min_overlap"):
        discover_question_links(
            [_artifact("inv-A", ["alpha beta"])], min_overlap=bad
        )


# --- public api exports ----------------------------------------------------


def test_public_api_exports() -> None:
    from substrate.cross_reference import question_links as mod

    assert set(mod.__all__) == {
        "QuestionCluster",
        "QuestionLink",
        "QuestionLinkError",
        "QuestionLinkReport",
        "discover_question_links",
    }
    assert issubclass(mod.QuestionLinkError, ValueError)
    assert dataclasses.is_dataclass(mod.QuestionLinkReport)
    assert dataclasses.is_dataclass(mod.QuestionLink)
    assert dataclasses.is_dataclass(mod.QuestionCluster)
