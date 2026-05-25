"""Property-based tests for Speak's load-bearing invariants.

Example tests pin behaviour at chosen points; these pin it across the
whole input space, so a careless edit to one of the spec's "hard to
vary" rules trips immediately:

  • the BINDING RULE — public publishing ⇒ algorithmic split ALWAYS,
    with no override (economics_mode.resolve_policy);
  • CORROBORATION ≠ TRUTH — confidence rises but never reaches certainty
    (corroboration.confidence_for);
  • the INDEPENDENCE GUARD — a repeated/​shared attestation never inflates
    the independent count (independence.count_independent);
  • a FAIR SPLIT — the attribution shares Speak routes the 70% slice by
    always sum to 1 over the contributing sources
    (ad_inventory.attribution Option B).

Skips entirely if hypothesis isn't installed (opt-in dep, matching
tests/properties/strategies.py).
"""

from __future__ import annotations

import pytest

hypothesis = pytest.importorskip("hypothesis", reason="hypothesis not installed")
from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from substrate.ad_inventory.attribution import compute_attribution_option_b  # noqa: E402
from substrate.speak.corroboration import confidence_for  # noqa: E402
from substrate.speak.economics_mode import (  # noqa: E402
    MARGIN_PRIVATE_PUBLISHED,
    MARGIN_PUBLIC,
    resolve_policy,
)
from substrate.speak.independence import count_independent  # noqa: E402

_INVITATIONS = ["private", "public"]
_PUBLISHINGS = ["never_published", "public"]


# ---------------------------------------------------------------------------
# The binding rule: public ⇒ split, always; never_published ⇒ creator pays.
# ---------------------------------------------------------------------------


@given(st.sampled_from(_INVITATIONS), st.sampled_from(_PUBLISHINGS))
def test_split_applies_iff_public(invitation: str, publishing: str):
    policy = resolve_policy(invitation, publishing)
    # The rule, over EVERY cell: split is exactly "is it public" — the
    # invitation dimension can never turn it off (no creator override).
    assert policy.split_applies == (publishing == "public")


@given(st.sampled_from(_INVITATIONS), st.sampled_from(_PUBLISHINGS))
def test_creator_carries_cost_iff_never_published(invitation: str, publishing: str):
    policy = resolve_policy(invitation, publishing)
    assert policy.creator_carries_cost == (publishing == "never_published")
    # Margin is a strict function of publishing, regardless of invitation.
    expected_margin = MARGIN_PUBLIC if publishing == "public" else MARGIN_PRIVATE_PUBLISHED
    assert policy.inference_margin == expected_margin


@given(st.sampled_from(_INVITATIONS), st.sampled_from(_PUBLISHINGS))
def test_split_and_creator_cost_are_mutually_exclusive(invitation: str, publishing: str):
    # You either route the contributor split (public) or the creator
    # carries cost (never-published) — never both, never neither.
    policy = resolve_policy(invitation, publishing)
    assert policy.split_applies != policy.creator_carries_cost


# ---------------------------------------------------------------------------
# Corroboration ≠ truth: confidence is monotone, bounded, never certain.
# ---------------------------------------------------------------------------


@given(st.integers(min_value=1, max_value=100_000))
def test_confidence_in_bounds_and_never_certain(n: int):
    c = confidence_for(n)
    assert 0.5 <= c <= 0.95          # starts at one source, capped below 1.0
    assert c < 1.0                   # no amount of attestation proves truth


@given(
    st.integers(min_value=1, max_value=10_000),
    st.integers(min_value=1, max_value=10_000),
)
def test_confidence_monotone_nondecreasing(a: int, b: int):
    lo, hi = min(a, b), max(a, b)
    assert confidence_for(hi) >= confidence_for(lo)


def test_confidence_single_source_is_half():
    assert confidence_for(1) == 0.5


# ---------------------------------------------------------------------------
# Independence guard: a repeated/shared attestation never inflates the count.
# ---------------------------------------------------------------------------


def _members() -> st.SearchStrategy[list[dict]]:
    member = st.fixed_dictionaries({
        "interview_id": st.text(min_size=1, max_size=6,
                                alphabet="abcdef").map(lambda s: f"iv-{s}"),
        "independence_key": st.one_of(
            st.none(),
            st.sampled_from(["rumor-A", "rumor-B", "rumor-C"]),
        ),
        "stance": st.sampled_from(["attests", "attests", "contradicts"]),
    })
    return st.lists(member, max_size=12)


@given(_members())
def test_count_never_exceeds_attesters(members: list[dict]):
    attesters = [m for m in members if m.get("stance", "attests") == "attests"]
    assert 0 <= count_independent(members) <= len(attesters)


@given(_members())
def test_duplication_does_not_inflate(members: list[dict]):
    # Replaying every attestation a second time is the same evidence,
    # not twice as much — the count must be unchanged.
    assert count_independent(members + members) == count_independent(members)


@given(_members())
def test_contradictions_do_not_count_as_independent_attestation(members: list[dict]):
    attests_only = [m for m in members if m.get("stance", "attests") == "attests"]
    assert count_independent(members) == count_independent(attests_only)


@given(st.integers(min_value=1, max_value=10), st.text(min_size=1, max_size=8))
def test_shared_rumor_key_collapses_to_one(n: int, key: str):
    # N people who all heard it from the same origin (one shared key) =
    # one attestation, not N.
    members = [{"interview_id": f"iv-{i}", "independence_key": key, "stance": "attests"}
               for i in range(n)]
    assert count_independent(members) == 1


@given(st.integers(min_value=1, max_value=10))
def test_distinct_interviewees_no_key_are_each_independent(n: int):
    members = [{"interview_id": f"iv-{i}", "independence_key": None, "stance": "attests"}
               for i in range(n)]
    assert count_independent(members) == n


# ---------------------------------------------------------------------------
# Fair split: attribution Option B shares sum to 1 over contributing sources.
# ---------------------------------------------------------------------------


@st.composite
def _attribution_inputs(draw):
    n_docs = draw(st.integers(min_value=1, max_value=5))
    doc_ids = [f"doc-{i}" for i in range(n_docs)]
    n_chunks = draw(st.integers(min_value=1, max_value=15))
    chunk_to_document: dict[str, str] = {}
    chunk_to_conf: dict[str, float] = {}
    for c in range(n_chunks):
        cid = f"chunk-{c}"
        chunk_to_document[cid] = draw(st.sampled_from(doc_ids))
        # Confidence strictly > 0 and tier in 1..5 ⇒ (6-tier) ≥ 1 ⇒ all
        # weights positive ⇒ a well-defined split exists.
        chunk_to_conf[cid] = draw(st.floats(min_value=0.01, max_value=1.0))
    document_to_tier = {d: draw(st.integers(min_value=1, max_value=5)) for d in doc_ids}
    return chunk_to_document, chunk_to_conf, document_to_tier


@settings(max_examples=200)
@given(_attribution_inputs())
def test_attribution_shares_sum_to_one(inputs):
    chunk_to_document, chunk_to_conf, document_to_tier = inputs
    result = compute_attribution_option_b(
        page_id="p",
        chunk_to_document=chunk_to_document,
        chunk_to_claim_confidence=chunk_to_conf,
        document_to_source_tier=document_to_tier,
    )
    assert result.shares, "non-empty contribution must yield a split"
    assert all(0.0 <= v <= 1.0 for v in result.shares.values())
    assert abs(sum(result.shares.values()) - 1.0) < 1e-9
