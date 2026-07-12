"""Tests for cross-reference discovery (the "referenced" pillar of ask #4).

Exercises the load-bearing invariants: Jaccard overlap, the empty-defer, self-
reference skip, prior de-duplication, deterministic sort, connected counts,
validation, and purity/immutability. Fixtures use BARE NONSENSE TOKENS
(alpha/beta/gamma) so every ratio is exactly countable — the discipline the bar
enforced in #1942/#1943 (common words like "present"/"effective" are distinctive
terms that inflate the math).
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.cross_reference.discovery import (
    CrossReferenceError,
    CrossReferenceReport,
    InsightCrossReference,
    _distinctive_terms,
    _jaccard,
    discover_cross_references,
)
from substrate.research_artifact.schema import (
    ArtifactInsight,
    ResearchArtifactBody,
)


def _artifact(
    investigation_id: str,
    insights: list[str],
) -> ResearchArtifactBody:
    return ResearchArtifactBody(
        investigation_id=investigation_id,
        problem_question="the question",
        insights=[ArtifactInsight(node_id=f"{investigation_id}-i{k}", text=t) for k, t in enumerate(insights)],
    )


# --- distinctive terms + jaccard primitives --------------------------------


def test_distinctive_terms_strips_glue_keeps_content() -> None:
    # "the"/"and"/"is" are glue; alpha/beta are kept content words.
    assert _distinctive_terms("the alpha and the beta is gamma") == frozenset(
        {"alpha", "beta", "gamma"}
    )


def test_distinctive_terms_case_insensitive() -> None:
    assert _distinctive_terms("Alpha BETA gamma") == frozenset({"alpha", "beta", "gamma"})


def test_distinctive_terms_empty_text() -> None:
    assert _distinctive_terms("") == frozenset()
    assert _distinctive_terms("the and is of") == frozenset()


def test_jaccard_basic() -> None:
    a = frozenset({"alpha", "beta", "gamma"})
    b = frozenset({"alpha", "beta", "delta"})
    # shared {alpha,beta}=2, union {alpha,beta,gamma,delta}=4 -> 0.5
    assert _jaccard(a, b) == pytest.approx(0.5)


def test_jaccard_identical() -> None:
    s = frozenset({"alpha", "beta"})
    assert _jaccard(s, s) == pytest.approx(1.0)


def test_jaccard_disjoint() -> None:
    a = frozenset({"alpha", "beta"})
    b = frozenset({"gamma", "delta"})
    assert _jaccard(a, b) == pytest.approx(0.0)


def test_jaccard_empty_union_is_zero() -> None:
    assert _jaccard(frozenset(), frozenset()) == pytest.approx(0.0)


# --- core discovery --------------------------------------------------------


def test_finds_cross_reference_above_floor() -> None:
    focus = _artifact("inv-focus", ["alpha beta gamma"])
    prior = _artifact("inv-prior", ["alpha beta delta"])
    report = discover_cross_references(focus, [prior])
    # Jaccard {alpha,beta} / {alpha,beta,gamma,delta} = 2/4 = 0.5 >= 0.30
    assert len(report.cross_references) == 1
    ref = report.cross_references[0]
    assert ref.overlap_score == pytest.approx(0.5)
    assert set(ref.shared_terms) == {"alpha", "beta"}
    assert ref.focus_insight_node_id == "inv-focus-i0"
    assert ref.prior_insight_node_id == "inv-prior-i0"
    assert ref.prior_investigation_id == "inv-prior"


def test_no_cross_reference_below_floor() -> None:
    # share only 1 of 5 terms -> 0.2 < 0.30 floor
    focus = _artifact("inv-focus", ["alpha beta gamma"])
    prior = _artifact("inv-prior", ["alpha delta epsilon"])
    report = discover_cross_references(focus, [prior])
    assert report.cross_references == ()


def test_disjoint_insights_no_reference() -> None:
    focus = _artifact("inv-focus", ["alpha beta"])
    prior = _artifact("inv-prior", ["gamma delta"])
    report = discover_cross_references(focus, [prior])
    assert report.cross_references == ()


# --- honesty rules: empty defer -------------------------------------------


def test_empty_focus_insights_no_references() -> None:
    focus = _artifact("inv-focus", [])
    prior = _artifact("inv-prior", ["alpha beta gamma"])
    report = discover_cross_references(focus, [prior])
    assert report.cross_references == ()
    assert report.connected_prior_count == 0


def test_empty_priors_no_references() -> None:
    focus = _artifact("inv-focus", ["alpha beta gamma"])
    report = discover_cross_references(focus, [])
    assert report.cross_references == ()
    assert report.prior_investigation_count == 0
    assert report.connected_prior_count == 0


def test_insight_with_no_distinctive_terms_cannot_connect() -> None:
    # "the and is" -> no distinctive terms -> skipped even if a prior matches
    focus = _artifact("inv-focus", ["the and is"])
    prior = _artifact("inv-prior", ["the and is"])
    report = discover_cross_references(focus, [prior])
    assert report.cross_references == ()


# --- honesty rules: self-reference + de-dup --------------------------------


def test_self_reference_skipped() -> None:
    focus = _artifact("inv-A", ["alpha beta gamma"])
    same = _artifact("inv-A", ["alpha beta gamma"])
    report = discover_cross_references(focus, [same])
    # prior shares the focus investigation_id -> skipped (within-artifact is #1939)
    assert report.cross_references == ()
    assert report.prior_investigation_count == 0


def test_duplicate_prior_ids_deduplicated() -> None:
    focus = _artifact("inv-focus", ["alpha beta gamma"])
    dup1 = _artifact("inv-prior", ["alpha beta delta"])
    dup2 = _artifact("inv-prior", ["alpha beta epsilon"])  # same id -> dropped
    report = discover_cross_references(focus, [dup1, dup2])
    assert report.prior_investigation_count == 1
    assert len(report.cross_references) == 1  # only dup1 examined


# --- sorting + determinism -------------------------------------------------


def test_sorted_by_overlap_desc() -> None:
    focus = _artifact("inv-focus", ["alpha beta gamma"])  # one focus insight
    # strong: 0.5 (share alpha,beta), weak: ~0.33 (share alpha only, 2/6... let's check)
    strong = _artifact("inv-strong", ["alpha beta delta"])  # 2/4 = 0.5
    # alpha shared, union {alpha,beta,gamma,epsilon,zeta}=5 -> 1/5 = 0.2 < floor, excluded
    # Use a guaranteed-above-floor weak one: share alpha,beta,gamma of 4 -> 3/4=0.75? no that's strong
    weak = _artifact("inv-weak", ["alpha beta gamma delta"])  # 3/4 = 0.75 -> actually strongest
    report = discover_cross_references(focus, [strong, weak])
    scores = [r.overlap_score for r in report.cross_references]
    assert scores == sorted(scores, reverse=True)
    # weak (0.75) ranks above strong (0.5)
    assert report.cross_references[0].prior_investigation_id == "inv-weak"
    assert report.cross_references[1].prior_investigation_id == "inv-strong"


def test_determinism_same_inputs_same_report() -> None:
    focus = _artifact("inv-focus", ["alpha beta gamma"])
    prior = _artifact("inv-prior", ["alpha beta delta"])
    a = discover_cross_references(focus, [prior])
    b = discover_cross_references(focus, [prior])
    assert a == b


def test_tiebreak_by_node_ids_stable() -> None:
    # Two priors with equal overlap -> ordered by investigation_id then node_id.
    focus = _artifact("inv-focus", ["alpha beta"])
    p_b = _artifact("inv-B", ["alpha beta"])  # identical set -> 1.0
    p_a = _artifact("inv-A", ["alpha beta"])  # identical set -> 1.0
    report = discover_cross_references(focus, [p_b, p_a])
    # both 1.0; tie-break: inv-A before inv-B
    assert report.cross_references[0].prior_investigation_id == "inv-A"
    assert report.cross_references[1].prior_investigation_id == "inv-B"


# --- connected counts ------------------------------------------------------


def test_connected_vs_examined_counts() -> None:
    focus = _artifact("inv-focus", ["alpha beta gamma"])
    connected = _artifact("inv-conn", ["alpha beta delta"])  # 0.5 -> connected
    unconnected = _artifact("inv-none", ["zeta eta theta"])  # 0.0 -> not connected
    report = discover_cross_references(focus, [connected, unconnected])
    assert report.prior_investigation_count == 2
    assert report.connected_prior_count == 1


def test_focus_with_multiple_insights_finds_all_connections() -> None:
    focus = _artifact("inv-focus", ["alpha beta", "gamma delta"])
    prior = _artifact("inv-prior", ["alpha beta epsilon", "gamma delta zeta"])
    report = discover_cross_references(focus, [prior])
    # focus-i0 vs prior-i0: {alpha,beta}/{alpha,beta,epsilon}=2/3=0.667 -> yes
    # focus-i0 vs prior-i1: disjoint -> no
    # focus-i1 vs prior-i0: disjoint -> no
    # focus-i1 vs prior-i1: {gamma,delta}/{gamma,delta,zeta}=2/3=0.667 -> yes
    assert len(report.cross_references) == 2
    assert report.connected_prior_count == 1


# --- provenance / auditability --------------------------------------------


def test_shared_terms_non_empty_for_every_reference() -> None:
    focus = _artifact("inv-focus", ["alpha beta gamma"])
    prior = _artifact("inv-prior", ["alpha beta delta"])
    report = discover_cross_references(focus, [prior])
    for ref in report.cross_references:
        assert len(ref.shared_terms) > 0


def test_overlap_score_in_unit_interval() -> None:
    focus = _artifact("inv-focus", ["alpha beta gamma delta"])
    priors = [
        _artifact(f"inv-{k}", [" ".join(["alpha", "beta", "gamma", "delta", "epsilon"][: k + 1])])
        for k in range(1, 5)
    ]
    report = discover_cross_references(focus, priors, min_overlap=0.01)
    for ref in report.cross_references:
        assert 0.0 <= ref.overlap_score <= 1.0


def test_focus_investigation_id_carried_through() -> None:
    focus = _artifact("inv-777", ["alpha beta"])
    prior = _artifact("inv-prior", ["alpha beta"])
    assert discover_cross_references(focus, [prior]).focus_investigation_id == "inv-777"


def test_authority_is_always_advisory() -> None:
    focus = _artifact("inv-focus", ["alpha beta"])
    prior = _artifact("inv-prior", ["alpha beta"])
    assert discover_cross_references(focus, [prior]).authority == "advisory"


def test_report_is_immutable() -> None:
    report = discover_cross_references(
        _artifact("inv-focus", ["alpha beta"]), [_artifact("inv-p", ["alpha beta"])]
    )
    assert isinstance(report, CrossReferenceReport)
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.connected_prior_count = 99  # type: ignore[misc]


def test_cross_reference_is_immutable() -> None:
    report = discover_cross_references(
        _artifact("inv-focus", ["alpha beta"]), [_artifact("inv-p", ["alpha beta"])]
    )
    ref = report.cross_references[0]
    assert isinstance(ref, InsightCrossReference)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ref.overlap_score = 0.0  # type: ignore[misc]


# --- custom min_overlap ----------------------------------------------------


def test_custom_min_overlap_filters() -> None:
    # 3/4 = 0.75 overlap
    focus = _artifact("inv-focus", ["alpha beta gamma"])
    prior = _artifact("inv-prior", ["alpha beta gamma delta"])
    # default 0.30: included
    assert len(discover_cross_references(focus, [prior]).cross_references) == 1
    # raise to 0.80: excluded (0.75 < 0.80)
    assert (
        len(discover_cross_references(focus, [prior], min_overlap=0.80).cross_references)
        == 0
    )


def test_min_overlap_recorded_in_report() -> None:
    focus = _artifact("inv-focus", ["alpha beta"])
    prior = _artifact("inv-prior", ["alpha beta"])
    report = discover_cross_references(focus, [prior], min_overlap=0.5)
    assert report.min_overlap == pytest.approx(0.5)


def test_boundary_overlap_is_included() -> None:
    # exactly 0.5 with default floor 0.30 -> included (>= is inclusive)
    focus = _artifact("inv-focus", ["alpha beta gamma"])
    prior = _artifact("inv-prior", ["alpha beta delta"])
    report = discover_cross_references(focus, [prior])  # 0.5 >= 0.30
    assert len(report.cross_references) == 1
    # set floor exactly to the overlap -> still included
    assert (
        len(discover_cross_references(focus, [prior], min_overlap=0.5).cross_references)
        == 1
    )


# --- validation ------------------------------------------------------------


@pytest.mark.parametrize("bad", [0.0, -0.1, 1.0001, 2.0])
def test_validation_rejects_bad_min_overlap(bad: float) -> None:
    with pytest.raises(CrossReferenceError, match="min_overlap"):
        discover_cross_references(
            _artifact("inv-focus", ["alpha beta"]),
            [_artifact("inv-p", ["alpha beta"])],
            min_overlap=bad,
        )


def test_min_overlap_one_is_valid() -> None:
    # 1.0 is the inclusive upper bound — only identical term sets qualify
    focus = _artifact("inv-focus", ["alpha beta"])
    identical = _artifact("inv-p", ["alpha beta"])
    distinct = _artifact("inv-q", ["alpha beta gamma"])
    report = discover_cross_references(focus, [identical, distinct], min_overlap=1.0)
    assert len(report.cross_references) == 1  # only the identical set
    assert report.cross_references[0].prior_investigation_id == "inv-p"


# --- public api exports ----------------------------------------------------


def test_public_api_exports() -> None:
    from substrate.cross_reference import discovery as mod

    assert set(mod.__all__) == {
        "CrossReferenceError",
        "CrossReferenceReport",
        "InsightCrossReference",
        "discover_cross_references",
    }
    assert issubclass(mod.CrossReferenceError, ValueError)
    assert dataclasses.is_dataclass(mod.CrossReferenceReport)
    assert dataclasses.is_dataclass(mod.InsightCrossReference)
