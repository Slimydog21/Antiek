"""Golden + property tests locking attribution behavior (SPR-04 M5).

Golden: fixed inputs → known per-asset outputs for A/B/C, hand-derived below so
a third party can verify the numbers. Property: conservation (shares sum to the
pool, none negative, none exceeding the pool) + Option B monotonicity in
confidence and tier. Edge cases enumerated: zero impressions, single asset,
ties, chunks-but-no-impressions.

These tests BITE: a deliberate math tweak (e.g. changing Option B's (6 - tier)
to (5 - tier)) makes the golden assertions fail. A passing test that didn't
exercise a real attribution computation would be a fake gate — every assertion
here runs the real compute_* functions.
"""

from __future__ import annotations

import json
import os
from fractions import Fraction

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from substrate.ad_inventory.attribution import (
    compute_attribution_option_a,
    compute_attribution_option_b,
    compute_attribution_option_c,
)

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "attribution")


def _load_golden(name: str) -> dict:
    with open(os.path.join(_FIXTURE_DIR, name)) as f:
        return json.load(f)


# ── Golden: fixed inputs → known outputs (hand-derived) ─────────────────────


def test_golden_option_a():
    """A — equal split per citation. doc-A has 2 of 3 citations → 2/3; doc-B 1/3."""
    g = _load_golden("golden_two_docs.json")
    shares = compute_attribution_option_a(
        page_id="p", chunk_to_document=g["inputs"]["chunk_to_document"],
    ).shares
    assert shares["doc-A"] == pytest.approx(2 / 3)
    assert shares["doc-B"] == pytest.approx(1 / 3)
    assert shares == pytest.approx(g["expected"]["A"])


def test_golden_option_b():
    """B — confidence × (6 - tier).
    doc-A: ch-1(1.0×5) + ch-3(0.4×5) = 7 ; doc-B: ch-2(1.0×2) = 2 ; total 9.
    → doc-A 7/9, doc-B 2/9."""
    g = _load_golden("golden_two_docs.json")
    shares = compute_attribution_option_b(
        page_id="p",
        chunk_to_document=g["inputs"]["chunk_to_document"],
        chunk_to_claim_confidence=g["inputs"]["chunk_to_claim_confidence"],
        document_to_source_tier=g["inputs"]["document_to_source_tier"],
    ).shares
    assert shares["doc-A"] == pytest.approx(7 / 9)
    assert shares["doc-B"] == pytest.approx(2 / 9)
    assert shares == pytest.approx(g["expected"]["B"])


def test_golden_option_c():
    """C — load-bearing score per claim.
    doc-A: cl-1(0.9) + cl-3(0.1) = 1.0 ; doc-B: cl-2(0.3) = 0.3 ; total 1.3.
    → doc-A 1.0/1.3, doc-B 0.3/1.3."""
    g = _load_golden("golden_two_docs.json")
    shares = compute_attribution_option_c(
        page_id="p",
        chunk_to_document=g["inputs"]["chunk_to_document"],
        claim_load_bearing_scores=g["inputs"]["claim_load_bearing_scores"],
        chunk_to_claim_id=g["inputs"]["chunk_to_claim_id"],
    ).shares
    assert shares["doc-A"] == pytest.approx(float(Fraction(10, 13)))
    assert shares["doc-B"] == pytest.approx(float(Fraction(3, 13)))
    assert shares == pytest.approx(g["expected"]["C"])


# ── Edge cases (enumerated per the acceptance criteria) ─────────────────────


def test_edge_zero_impressions_empty_split():
    """No citations → empty split (no invented money)."""
    assert compute_attribution_option_a(page_id="p", chunk_to_document={}).shares == {}
    assert compute_attribution_option_b(
        page_id="p", chunk_to_document={},
        chunk_to_claim_confidence={}, document_to_source_tier={},
    ).shares == {}
    assert compute_attribution_option_c(
        page_id="p", chunk_to_document={},
        claim_load_bearing_scores={}, chunk_to_claim_id={},
    ).shares == {}


def test_edge_single_asset_gets_everything():
    """One asset → it gets the whole pool (share 1.0)."""
    s = compute_attribution_option_a(
        page_id="p", chunk_to_document={"ch-1": "doc-A", "ch-2": "doc-A"},
    ).shares
    assert s == {"doc-A": pytest.approx(1.0)}


def test_edge_ties_split_equally():
    """Two assets, identical citations/weights → equal split, deterministic."""
    s = compute_attribution_option_b(
        page_id="p",
        chunk_to_document={"ch-1": "doc-A", "ch-2": "doc-B"},
        chunk_to_claim_confidence={"ch-1": 1.0, "ch-2": 1.0},
        document_to_source_tier={"doc-A": 2, "doc-B": 2},
    ).shares
    assert s["doc-A"] == pytest.approx(0.5)
    assert s["doc-B"] == pytest.approx(0.5)


def test_edge_chunks_but_no_load_bearing_score_excluded_in_c():
    """Option C: a chunk whose claim has no load-bearing score contributes 0.
    A doc with ONLY such chunks appears with an honest 0.0 share (it was cited
    but earned no attributable weight) while the other doc absorbs the full
    pool. Conservation still holds (0 doesn't create or destroy money)."""
    s = compute_attribution_option_c(
        page_id="p",
        chunk_to_document={"ch-1": "doc-A", "ch-2": "doc-B"},
        claim_load_bearing_scores={"cl-1": 0.5},  # cl-2 (doc-B) has no score
        chunk_to_claim_id={"ch-1": "cl-1", "ch-2": "cl-2"},
    ).shares
    assert s["doc-A"] == pytest.approx(1.0)
    assert s["doc-B"] == pytest.approx(0.0)
    assert sum(s.values()) == pytest.approx(1.0)


def test_edge_option_b_unknown_tier_defaults_to_5():
    """A doc with no tier entry defaults to tier 5 (factor 1) — documented
    fallback, not a crash."""
    s = compute_attribution_option_b(
        page_id="p",
        chunk_to_document={"ch-1": "doc-A", "ch-2": "doc-B"},
        chunk_to_claim_confidence={"ch-1": 1.0, "ch-2": 1.0},
        document_to_source_tier={"doc-A": 1},  # doc-B missing → tier 5, factor 1
    ).shares
    # doc-A: 1.0×5 = 5 ; doc-B: 1.0×1 = 1 ; total 6.
    assert s["doc-A"] == pytest.approx(5 / 6)
    assert s["doc-B"] == pytest.approx(1 / 6)


# ── Property: conservation + non-negativity (all three algorithms) ──────────

_DOCS = ["doc-A", "doc-B", "doc-C"]
_CHUNK_TO_DOC = st.dictionaries(
    keys=st.sampled_from(["ch-1", "ch-2", "ch-3", "ch-4", "ch-5"]),
    values=st.sampled_from(_DOCS),
    min_size=1, max_size=5,
)
_CONF = st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False)
_TIER = st.integers(min_value=1, max_value=5)


@settings(max_examples=200)
@given(ctd=_CHUNK_TO_DOC)
def test_property_option_a_conserves_pool(ctd):
    shares = compute_attribution_option_a(page_id="p", chunk_to_document=ctd).shares
    _assert_conserved(shares)


@settings(max_examples=200)
@given(
    ctd=_CHUNK_TO_DOC,
    conf=st.data(),
    tiers=st.data(),
)
def test_property_option_b_conserves_pool(ctd, conf, tiers):
    chunk_conf = {ch: conf.draw(_CONF) for ch in ctd}
    doc_tier = {doc: tiers.draw(_TIER) for doc in set(ctd.values())}
    shares = compute_attribution_option_b(
        page_id="p", chunk_to_document=ctd,
        chunk_to_claim_confidence=chunk_conf, document_to_source_tier=doc_tier,
    ).shares
    _assert_conserved(shares)


@settings(max_examples=200)
@given(ctd=_CHUNK_TO_DOC, lb=st.data())
def test_property_option_c_conserves_pool(ctd, lb):
    chunk_to_claim = {ch: f"cl-{ch}" for ch in ctd}
    lb_scores = {
        f"cl-{ch}": lb.draw(st.floats(min_value=0.0, max_value=1.0,
                                      allow_nan=False, allow_infinity=False))
        for ch in ctd
    }
    shares = compute_attribution_option_c(
        page_id="p", chunk_to_document=ctd,
        claim_load_bearing_scores=lb_scores, chunk_to_claim_id=chunk_to_claim,
    ).shares
    _assert_conserved(shares)


def _assert_conserved(shares: dict):
    """The load-bearing invariant: the split never creates or destroys money.
    Per-asset shares sum to the pool (1.0), none negative, none exceeding the
    pool. An empty split (zero total weight) is the honest exception."""
    if not shares:
        return
    total = sum(shares.values())
    assert total == pytest.approx(1.0)
    for v in shares.values():
        assert v >= 0.0
        assert v <= 1.0 + 1e-9


# ── Property: Option B monotonic in confidence and tier ─────────────────────


@settings(max_examples=200)
@given(
    conf_lo=st.floats(min_value=0.05, max_value=0.5, allow_nan=False),
    delta=st.floats(min_value=0.05, max_value=0.5, allow_nan=False),
)
def test_property_option_b_monotonic_in_confidence(conf_lo, delta):
    """Raising doc-A's claim confidence (holding doc-B fixed) cannot DECREASE
    doc-A's share — higher-confidence claims earn at least as much."""
    base = compute_attribution_option_b(
        page_id="p",
        chunk_to_document={"ch-1": "doc-A", "ch-2": "doc-B"},
        chunk_to_claim_confidence={"ch-1": conf_lo, "ch-2": 0.5},
        document_to_source_tier={"doc-A": 3, "doc-B": 3},
    ).shares
    raised = compute_attribution_option_b(
        page_id="p",
        chunk_to_document={"ch-1": "doc-A", "ch-2": "doc-B"},
        chunk_to_claim_confidence={"ch-1": conf_lo + delta, "ch-2": 0.5},
        document_to_source_tier={"doc-A": 3, "doc-B": 3},
    ).shares
    assert raised["doc-A"] >= base["doc-A"] - 1e-9


@settings(max_examples=200)
@given(tier_hi=st.integers(min_value=2, max_value=5))
def test_property_option_b_monotonic_in_tier(tier_hi):
    """Improving doc-A's tier (lower number = higher trust) cannot DECREASE its
    share — higher-tier sources earn at least as much."""
    base = compute_attribution_option_b(
        page_id="p",
        chunk_to_document={"ch-1": "doc-A", "ch-2": "doc-B"},
        chunk_to_claim_confidence={"ch-1": 1.0, "ch-2": 1.0},
        document_to_source_tier={"doc-A": tier_hi, "doc-B": 3},
    ).shares
    improved = compute_attribution_option_b(
        page_id="p",
        chunk_to_document={"ch-1": "doc-A", "ch-2": "doc-B"},
        chunk_to_claim_confidence={"ch-1": 1.0, "ch-2": 1.0},
        document_to_source_tier={"doc-A": tier_hi - 1, "doc-B": 3},  # better tier
    ).shares
    assert improved["doc-A"] >= base["doc-A"] - 1e-9
