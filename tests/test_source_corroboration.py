"""Tests for the source-corroboration axis (do sources converge? ask #1).

Exercises: independently_confirmed/single_source verdicts, corroboration_rate +
max_source_agreement, distinct-source counting, same-source exclusion (redundancy's
lane), ungrounded/all-glue exclusion, subset matching, custom threshold,
purity/immutability, validation. Fixtures use BARE NONSENSE TOKENS.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.deep_research_quality.source_corroboration import (
    ClaimCorroboration,
    SourceCorroborationError,
    SourceCorroborationReport,
    measure_source_corroboration,
)
from substrate.research_artifact.schema import (
    ArtifactInsight,
    ArtifactQuestion,
    ResearchArtifactBody,
)


def _artifact(insights: list[tuple[str, str | None, str]]) -> ResearchArtifactBody:
    """insights = list of (text, source_id_or_None, node_id)."""
    return ResearchArtifactBody(
        investigation_id="art",
        problem_question="the problem",
        insights=[
            ArtifactInsight(node_id=nid or f"i{k}", text=t, source_document_id=sid)
            for k, (t, sid, nid) in enumerate(insights)
        ],
        open_questions=[ArtifactQuestion(node_id="q0", text="the question")],
    )


# --- independent confirmation (the triangulation signal) ------------------


def test_two_sources_same_claim_is_confirmed() -> None:
    art = _artifact([
        ("alpha beta gamma", "src-a", "i0"),
        ("alpha beta gamma", "src-b", "i1"),
    ])
    r = measure_source_corroboration(art)
    assert r.confirmed_claims == 2
    assert r.single_source_claims == 0
    assert r.corroboration_rate == 1.0
    assert r.max_source_agreement == 2
    assert r.verdict == "strongly_corroborated"
    by_node = {c.node_id: c for c in r.claim_corroborations}
    assert by_node["i0"].verdict == "independently_confirmed"
    assert by_node["i0"].confirmation_count == 2
    assert by_node["i0"].source_ids == ("src-a", "src-b")


def test_three_sources_triangulate() -> None:
    art = _artifact([
        ("alpha beta", "src-a", "i0"),
        ("alpha beta", "src-b", "i1"),
        ("alpha beta", "src-c", "i2"),
    ])
    r = measure_source_corroboration(art)
    assert r.max_source_agreement == 3
    assert r.confirmed_claims == 3
    assert r.corroboration_rate == 1.0


# --- single source (no independent confirmation) --------------------------


def test_unique_claims_are_single_source() -> None:
    art = _artifact([
        ("alpha beta", "src-a", "i0"),
        ("gamma delta", "src-b", "i1"),  # different claim, different source
    ])
    r = measure_source_corroboration(art)
    assert r.confirmed_claims == 0
    assert r.single_source_claims == 2
    assert r.corroboration_rate == 0.0
    assert r.verdict == "mostly_single_source"


# --- same source matching is NOT independent confirmation -----------------


def test_same_source_repeats_not_independent() -> None:
    # Two insights from the SAME source making the same claim: NOT corroboration
    # (that's redundancy #1939's lane). Each claim is single-source.
    art = _artifact([
        ("alpha beta gamma", "src-a", "i0"),
        ("alpha beta gamma", "src-a", "i1"),
    ])
    r = measure_source_corroboration(art)
    assert r.confirmed_claims == 0
    assert r.single_source_claims == 2
    assert r.corroboration_rate == 0.0
    by_node = {c.node_id: c for c in r.claim_corroborations}
    assert by_node["i0"].confirmation_count == 1  # only src-a


# --- ungrounded / all-glue exclusion --------------------------------------


def test_ungrounded_excluded_from_rate() -> None:
    art = _artifact([
        ("alpha beta", "src-a", "i0"),
        ("gamma delta", None, "i1"),  # ungrounded (no source)
    ])
    r = measure_source_corroboration(art)
    assert r.ungrounded_claims == 1
    assert r.confirmed_claims == 0
    assert r.single_source_claims == 1
    assert r.corroboration_rate == 0.0  # only the grounded claim counts


def test_all_glue_excluded() -> None:
    art = _artifact([
        ("alpha beta", "src-a", "i0"),
        ("the and of", "src-b", "i1"),  # all-glue (no distinctive terms)
    ])
    r = measure_source_corroboration(art)
    assert r.unmeasurable_claims == 1
    assert r.single_source_claims == 1


def test_unknown_when_no_grounded_claims() -> None:
    art = _artifact([
        ("alpha beta", None, "i0"),  # ungrounded
    ])
    r = measure_source_corroboration(art)
    assert r.corroboration_rate is None
    assert r.verdict == "unknown"
    assert r.ungrounded_claims == 1


# --- subset matching (overlap-coefficient design) -------------------------


def test_subset_claim_corroborates() -> None:
    # src-a: rich claim {alpha,beta,gamma,delta}; src-b: subset {alpha,beta}.
    # overlap-coeff = |{alpha,beta}| / min(4,2) = 2/2 = 1.0 -> corroborate.
    art = _artifact([
        ("alpha beta gamma delta", "src-a", "i0"),
        ("alpha beta", "src-b", "i1"),
    ])
    r = measure_source_corroboration(art)
    assert r.confirmed_claims == 2
    by_node = {c.node_id: c for c in r.claim_corroborations}
    assert by_node["i1"].match_overlap == 1.0


# --- custom threshold -----------------------------------------------------


def test_custom_threshold_changes_verdict() -> None:
    # {alpha,beta,gamma} vs {alpha,beta,zzz}: overlap = 2/min(3,3) = 0.667.
    art = _artifact([
        ("alpha beta gamma", "src-a", "i0"),
        ("alpha beta zzz", "src-b", "i1"),
    ])
    loose = measure_source_corroboration(art, match_threshold=0.50)
    assert loose.confirmed_claims == 2  # 0.667 >= 0.50 -> corroborate
    strict = measure_source_corroboration(art, match_threshold=0.70)
    assert strict.confirmed_claims == 0  # 0.667 < 0.70 -> no corroboration


# --- verdict bands --------------------------------------------------------


def test_verdict_bands() -> None:
    # 5 grounded: 2 confirmed (40%), 3 single_source -> "corroborated" (>=30%)
    art = _artifact([
        ("alpha beta", "src-a", "i0"),
        ("alpha beta", "src-b", "i1"),  # confirmed pair
        ("gamma delta", "src-a", "i2"),
        ("epsilon zeta", "src-a", "i3"),
        ("eta theta", "src-a", "i4"),
    ])
    r = measure_source_corroboration(art)
    assert r.confirmed_claims == 2
    assert r.single_source_claims == 3
    assert r.corroboration_rate == pytest.approx(0.40)
    assert r.verdict == "corroborated"
    assert r.authority == "advisory"


# --- validation -----------------------------------------------------------


@pytest.mark.parametrize("bad", [-0.1, 1.5])
def test_bad_threshold_raises(bad: float) -> None:
    art = _artifact([("alpha beta", "src-a", "i0")])
    with pytest.raises(SourceCorroborationError, match="match_threshold"):
        measure_source_corroboration(art, match_threshold=bad)


# --- purity / immutability ------------------------------------------------


def test_report_is_frozen_and_deterministic() -> None:
    art = _artifact([
        ("alpha beta", "src-a", "i0"),
        ("alpha beta", "src-b", "i1"),
    ])
    r1 = measure_source_corroboration(art)
    r2 = measure_source_corroboration(art)
    assert dataclasses.is_dataclass(r1)
    assert isinstance(r1.claim_corroborations, tuple)
    assert all(isinstance(c, ClaimCorroboration) for c in r1.claim_corroborations)
    assert r1 == r2  # deterministic
    with pytest.raises(dataclasses.FrozenInstanceError):
        r1.verdict = "tampered"  # type: ignore[misc]
    assert isinstance(r1, SourceCorroborationReport)


def test_notes_are_non_empty_and_auditable() -> None:
    art = _artifact([("alpha beta", "src-a", "i0")])
    r = measure_source_corroboration(art)
    assert isinstance(r.notes, tuple)
    assert len(r.notes) >= 5
    assert all(isinstance(n, str) and n for n in r.notes)
