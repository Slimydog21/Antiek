"""Tests for cross-reference polarity classification.

Exercises: contradiction detection (asymmetric negation), compatible
classification, symmetric-negation edge, negation-window boundary, empty-defer,
self-reference skip, prior de-dup, deterministic sort, counts, validation, and
purity/immutability. Fixtures use BARE NONSENSE TOKENS + explicit negation so
every classification is unambiguous.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.cross_reference.polarity import (
    CrossPolarityError,
    CrossReferencePair,
    PolarityReport,
    _distinctive_terms,
    _negated_terms,
    _tokenize,
    classify_cross_reference_polarity,
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
        insights=[
            ArtifactInsight(node_id=f"{investigation_id}-i{k}", text=t)
            for k, t in enumerate(insights)
        ],
    )


# --- tokenization + negation primitives ------------------------------------


def test_tokenize_expands_contractions() -> None:
    # "don't" -> "dont" so it survives as a clean negation token
    assert "dont" in _tokenize("alpha don't beta")
    assert "don" not in _tokenize("alpha don't beta")


def test_distinctive_terms_excludes_negation_markers() -> None:
    # negation markers are NOT distinctive terms (no subject signal)
    terms = _distinctive_terms("alpha not beta never gamma")
    assert "alpha" in terms
    assert "beta" in terms
    assert "gamma" in terms
    assert "not" not in terms
    assert "never" not in terms


def test_negated_terms_detects_preceding_marker() -> None:
    tokens = ["alpha", "not", "beta"]
    negated = _negated_terms(tokens, frozenset({"beta"}), window=4)
    assert negated == frozenset({"beta"})


def test_negated_terms_outside_window_not_negated() -> None:
    # "not" is 5 tokens before "epsilon" -> outside window=4
    tokens = ["not", "alpha", "beta", "gamma", "delta", "epsilon"]
    negated = _negated_terms(tokens, frozenset({"epsilon"}), window=4)
    assert negated == frozenset()


def test_negated_terms_within_window_boundary() -> None:
    # "not" is exactly 4 tokens before "epsilon" -> inside window=4 (lookback starts at i-4)
    # tokens: [not, alpha, beta, gamma, epsilon], "epsilon" at 4, lookback [0:4] includes "not"
    tokens = ["not", "alpha", "beta", "gamma", "epsilon"]
    negated = _negated_terms(tokens, frozenset({"epsilon"}), window=4)
    assert negated == frozenset({"epsilon"})


def test_negated_terms_no_marker_not_negated() -> None:
    tokens = ["alpha", "beta", "gamma"]
    negated = _negated_terms(tokens, frozenset({"gamma"}), window=4)
    assert negated == frozenset()


# --- core: contradiction detection -----------------------------------------


def test_contradiction_asymmetric_negation() -> None:
    # focus asserts "stable"; prior negates it -> contradiction
    focus = _artifact("inv-focus", ["alpha beta stable"])
    prior = _artifact("inv-prior", ["alpha beta not stable"])
    report = classify_cross_reference_polarity(focus, [prior])
    assert len(report.contradictions) == 1
    assert len(report.compatibles) == 0
    pair = report.contradictions[0]
    assert pair.polarity == "cross_contradiction"
    assert "stable" in pair.negated_terms
    assert set(pair.shared_terms) == {"alpha", "beta", "stable"}


def test_contradiction_reversed_negation() -> None:
    # focus negates; prior asserts -> still asymmetric -> contradiction
    focus = _artifact("inv-focus", ["alpha beta not stable"])
    prior = _artifact("inv-prior", ["alpha beta stable"])
    report = classify_cross_reference_polarity(focus, [prior])
    assert len(report.contradictions) == 1
    assert "stable" in report.contradictions[0].negated_terms


def test_compatible_no_negation() -> None:
    focus = _artifact("inv-focus", ["alpha beta stable"])
    prior = _artifact("inv-prior", ["alpha beta stable gamma"])
    report = classify_cross_reference_polarity(focus, [prior])
    assert len(report.contradictions) == 0
    assert len(report.compatibles) == 1
    assert report.compatibles[0].polarity == "cross_compatible"
    assert report.compatibles[0].negated_terms == ()


def test_symmetric_negation_is_compatible() -> None:
    # BOTH negate "stable" -> symmetric -> NOT a contradiction -> compatible
    focus = _artifact("inv-focus", ["alpha beta not stable"])
    prior = _artifact("inv-prior", ["alpha beta not stable"])
    report = classify_cross_reference_polarity(focus, [prior])
    assert len(report.contradictions) == 0
    assert len(report.compatibles) == 1


def test_partial_overlap_below_floor_not_classified() -> None:
    # share only 1 of 5 terms -> 0.2 < 0.30 floor -> no pair at all
    focus = _artifact("inv-focus", ["alpha beta gamma"])
    prior = _artifact("inv-prior", ["alpha not delta epsilon"])
    report = classify_cross_reference_polarity(focus, [prior])
    assert report.contradictions == ()
    assert report.compatibles == ()


def test_mixed_contradiction_and_compatible() -> None:
    focus = _artifact("inv-focus", ["alpha beta stable"])
    conflicting = _artifact("inv-conf", ["alpha beta not stable"])
    aligned = _artifact("inv-align", ["alpha beta stable gamma"])
    report = classify_cross_reference_polarity(focus, [conflicting, aligned])
    assert len(report.contradictions) == 1
    assert len(report.compatibles) == 1
    assert report.contradictions[0].prior_investigation_id == "inv-conf"
    assert report.compatibles[0].prior_investigation_id == "inv-align"


def test_contraction_negation_detected() -> None:
    # "doesn't" -> "doesnt" -> negation marker
    focus = _artifact("inv-focus", ["alpha beta stable"])
    prior = _artifact("inv-prior", ["alpha beta doesnt stable"])
    report = classify_cross_reference_polarity(focus, [prior])
    assert len(report.contradictions) == 1
    assert "stable" in report.contradictions[0].negated_terms


# --- honesty rules: empty defer -------------------------------------------


def test_empty_focus_no_pairs() -> None:
    focus = _artifact("inv-focus", [])
    prior = _artifact("inv-prior", ["alpha beta"])
    report = classify_cross_reference_polarity(focus, [prior])
    assert report.contradictions == ()
    assert report.compatibles == ()


def test_empty_priors_no_pairs() -> None:
    focus = _artifact("inv-focus", ["alpha beta"])
    report = classify_cross_reference_polarity(focus, [])
    assert report.contradictions == ()
    assert report.compatibles == ()
    assert report.prior_investigation_count == 0


# --- honesty rules: self-reference + de-dup --------------------------------


def test_self_reference_skipped() -> None:
    focus = _artifact("inv-A", ["alpha beta not stable"])
    same = _artifact("inv-A", ["alpha beta stable"])
    report = classify_cross_reference_polarity(focus, [same])
    # prior shares focus investigation_id -> skipped (within-artifact is #1943)
    assert report.contradictions == ()
    assert report.compatibles == ()
    assert report.prior_investigation_count == 0


def test_duplicate_prior_ids_deduplicated() -> None:
    focus = _artifact("inv-focus", ["alpha beta stable"])
    dup1 = _artifact("inv-prior", ["alpha beta not stable"])
    dup2 = _artifact("inv-prior", ["alpha beta stable"])  # same id -> dropped
    report = classify_cross_reference_polarity(focus, [dup1, dup2])
    assert report.prior_investigation_count == 1
    assert len(report.contradictions) == 1  # only dup1 examined


# --- sorting + determinism -------------------------------------------------


def test_sorted_by_overlap_desc() -> None:
    focus = _artifact("inv-focus", ["alpha beta gamma"])
    strong = _artifact("inv-strong", ["alpha beta not gamma delta"])  # 3/4=0.75
    weak = _artifact("inv-weak", ["alpha beta not gamma"])  # 3/3=1.0
    report = classify_cross_reference_polarity(focus, [strong, weak])
    scores = [p.overlap_score for p in report.contradictions]
    assert scores == sorted(scores, reverse=True)
    assert report.contradictions[0].prior_investigation_id == "inv-weak"


def test_determinism_same_inputs_same_report() -> None:
    focus = _artifact("inv-focus", ["alpha beta not stable"])
    prior = _artifact("inv-prior", ["alpha beta stable"])
    a = classify_cross_reference_polarity(focus, [prior])
    b = classify_cross_reference_polarity(focus, [prior])
    assert a == b


# --- counts ---------------------------------------------------------------


def test_counts_reflect_examined_and_connected() -> None:
    focus = _artifact("inv-focus", ["alpha beta stable"])
    conf = _artifact("inv-conf", ["alpha beta not stable"])
    align = _artifact("inv-align", ["alpha beta stable delta"])
    unrelated = _artifact("inv-none", ["zeta eta theta"])
    report = classify_cross_reference_polarity(focus, [conf, align, unrelated])
    assert report.prior_investigation_count == 3
    assert report.contradiction_prior_count == 1
    assert report.compatible_prior_count == 1


# --- provenance / auditability --------------------------------------------


def test_shared_terms_non_empty_for_every_pair() -> None:
    focus = _artifact("inv-focus", ["alpha beta stable"])
    conf = _artifact("inv-conf", ["alpha beta not stable"])
    align = _artifact("inv-align", ["alpha beta stable delta"])
    report = classify_cross_reference_polarity(focus, [conf, align])
    for pair in report.contradictions + report.compatibles:
        assert len(pair.shared_terms) > 0


def test_contradiction_negated_terms_non_empty() -> None:
    focus = _artifact("inv-focus", ["alpha beta stable"])
    prior = _artifact("inv-prior", ["alpha beta not stable"])
    report = classify_cross_reference_polarity(focus, [prior])
    for pair in report.contradictions:
        assert len(pair.negated_terms) > 0


def test_compatible_negated_terms_empty() -> None:
    focus = _artifact("inv-focus", ["alpha beta stable"])
    prior = _artifact("inv-prior", ["alpha beta stable delta"])
    report = classify_cross_reference_polarity(focus, [prior])
    for pair in report.compatibles:
        assert pair.negated_terms == ()


def test_overlap_score_in_unit_interval() -> None:
    focus = _artifact("inv-focus", ["alpha beta gamma delta"])
    priors = [
        _artifact(f"inv-{k}", [" ".join(["alpha", "beta", "gamma", "delta", "epsilon"][: k + 1])])
        for k in range(1, 5)
    ]
    report = classify_cross_reference_polarity(focus, priors, min_overlap=0.01)
    for pair in report.contradictions + report.compatibles:
        assert 0.0 <= pair.overlap_score <= 1.0


def test_focus_investigation_id_carried_through() -> None:
    focus = _artifact("inv-777", ["alpha beta stable"])
    prior = _artifact("inv-prior", ["alpha beta not stable"])
    assert classify_cross_reference_polarity(focus, [prior]).focus_investigation_id == "inv-777"


def test_authority_is_always_advisory() -> None:
    focus = _artifact("inv-focus", ["alpha beta"])
    prior = _artifact("inv-prior", ["alpha beta"])
    assert classify_cross_reference_polarity(focus, [prior]).authority == "advisory"


def test_report_is_immutable() -> None:
    report = classify_cross_reference_polarity(
        _artifact("inv-focus", ["alpha beta"]), [_artifact("inv-p", ["alpha beta"])]
    )
    assert isinstance(report, PolarityReport)
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.contradiction_prior_count = 99  # type: ignore[misc]


def test_pair_is_immutable() -> None:
    report = classify_cross_reference_polarity(
        _artifact("inv-focus", ["alpha beta"]),
        [_artifact("inv-p", ["alpha beta"])],
    )
    pair = report.compatibles[0]
    assert isinstance(pair, CrossReferencePair)
    with pytest.raises(dataclasses.FrozenInstanceError):
        pair.overlap_score = 0.0  # type: ignore[misc]


# --- custom params ---------------------------------------------------------


def test_custom_min_overlap_filters() -> None:
    focus = _artifact("inv-focus", ["alpha beta gamma"])  # 3 terms
    prior = _artifact("inv-prior", ["alpha beta not gamma delta"])  # overlap 3/4=0.75
    assert (
        len(classify_cross_reference_polarity(focus, [prior]).contradictions) == 1
    )
    assert (
        len(classify_cross_reference_polarity(focus, [prior], min_overlap=0.80).contradictions)
        == 0
    )


def test_custom_negation_window_changes_detection() -> None:
    # "not" + 5 stop-word fillers before shared terms. At window=4 the negation
    # is outside the lookback of every shared term; at window=6 it reaches "alpha".
    focus = _artifact("inv-focus", ["alpha beta stable"])
    prior = _artifact("inv-prior", ["not the the the the the alpha beta stable"])
    # window 4: "not" too far from all shared terms -> no asym negation -> compatible
    r4 = classify_cross_reference_polarity(focus, [prior], negation_window=4)
    assert len(r4.contradictions) == 0
    assert len(r4.compatibles) == 1
    # window 6: "not" reaches "alpha" (6 tokens back) -> asym negation -> contradiction
    r6 = classify_cross_reference_polarity(focus, [prior], negation_window=6)
    assert len(r6.contradictions) == 1


def test_negation_window_recorded_in_report() -> None:
    report = classify_cross_reference_polarity(
        _artifact("inv-focus", ["alpha beta"]),
        [_artifact("inv-p", ["alpha beta"])],
        negation_window=3,
    )
    assert report.negation_window == 3


# --- validation ------------------------------------------------------------


@pytest.mark.parametrize("bad", [0.0, -0.1, 1.0001, 2.0])
def test_validation_rejects_bad_min_overlap(bad: float) -> None:
    with pytest.raises(CrossPolarityError, match="min_overlap"):
        classify_cross_reference_polarity(
            _artifact("inv-focus", ["alpha beta"]),
            [_artifact("inv-p", ["alpha beta"])],
            min_overlap=bad,
        )


@pytest.mark.parametrize("bad", [0, -1])
def test_validation_rejects_bad_window(bad: int) -> None:
    with pytest.raises(CrossPolarityError, match="negation_window"):
        classify_cross_reference_polarity(
            _artifact("inv-focus", ["alpha beta"]),
            [_artifact("inv-p", ["alpha beta"])],
            negation_window=bad,
        )


# --- public api exports ----------------------------------------------------


def test_public_api_exports() -> None:
    from substrate.cross_reference import polarity as mod

    assert set(mod.__all__) == {
        "CrossPolarityError",
        "CrossReferencePair",
        "PolarityReport",
        "classify_cross_reference_polarity",
    }
    assert issubclass(mod.CrossPolarityError, ValueError)
    assert dataclasses.is_dataclass(mod.PolarityReport)
    assert dataclasses.is_dataclass(mod.CrossReferencePair)
