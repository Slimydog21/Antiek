"""Money-math tests for ``earn_split_for_synthesis`` (AFA-S3-M3 core).

Exhaustive because this is a payout path: every cent is asserted, and the two invariants
most likely to be silently broken by a future refactor — §9.10 earn-gate retention and
cent conservation — get their own named tests so a regression names itself.
"""

from __future__ import annotations

import pytest

from substrate.ad_inventory.synthesis_earn_split import (
    SourceEarnLine,
    earn_split_for_synthesis,
)
from substrate.attribution.algorithms import AttributionClaim

# content-class strings, pinned from retrieval_gate (see test at import of those consts).
PUBLIC = "public_domain"
RESTRICTED = "restricted_pending_opt_in"  # earns to escrow (§9.10)
PERSONAL = "personal_reading"  # never earns


def _claim(idx: int, chunk_id: str, c2d: dict[str, str], tiers: dict[str, int],
           confidence: str = "high") -> AttributionClaim:
    return AttributionClaim(
        claim_index=idx, chunk_ids=(chunk_id,), confidence=confidence,
        chunk_to_document=c2d, document_to_tier=tiers,
    )


def _lines_by_doc(lines: list[SourceEarnLine]) -> dict[str, SourceEarnLine]:
    return {ln.document_id: ln for ln in lines}


# --------------------------------------------------------------------------- #
# Invariant 1 — the §9.10 earn gate (the PR #203 trap, tested head-on)
# --------------------------------------------------------------------------- #

def test_personal_reading_excluded_restricted_retained() -> None:
    """The load-bearing gate distinction: ``personal_reading`` earns NOTHING (no line),
    while ``restricted_pending_opt_in`` is RETAINED and earns to escrow (§9.10). Reusing
    the display gate here would wrongly drop the restricted source — this asserts we do not."""
    c2d = {"cP": "D_public", "cR": "D_restricted", "cX": "D_personal"}
    tiers = {"D_public": 1, "D_restricted": 1, "D_personal": 1}
    content = {"D_public": PUBLIC, "D_restricted": RESTRICTED, "D_personal": PERSONAL}
    holders = {"D_public": "h_pub", "D_restricted": "h_rest", "D_personal": "h_pers"}
    claims = [
        _claim(0, "cP", c2d, tiers),
        _claim(1, "cR", c2d, tiers),
        _claim(2, "cX", c2d, tiers),
    ]

    lines = earn_split_for_synthesis(
        claims=claims, doc_to_content_class=content, doc_to_ip_holder=holders,
        total_cents=300, algorithm="A",
    )
    by_doc = _lines_by_doc(lines)

    assert "D_personal" not in by_doc, "personal_reading must never earn"
    assert "D_restricted" in by_doc, "restricted_pending_opt_in must earn to escrow (§9.10)"
    # The two survivors split 300 equally after the personal source is removed.
    assert by_doc["D_public"].cents == 150
    assert by_doc["D_restricted"].cents == 150
    assert by_doc["D_restricted"].ip_holder_id == "h_rest"


def test_all_sources_personal_yields_empty_split() -> None:
    """Every source ``personal_reading`` → nothing attributable → empty split (the caller
    routes the whole amount to the house; no invented owner)."""
    c2d = {"c1": "D1", "c2": "D2"}
    tiers = {"D1": 1, "D2": 1}
    content = {"D1": PERSONAL, "D2": PERSONAL}
    claims = [_claim(0, "c1", c2d, tiers), _claim(1, "c2", c2d, tiers)]
    lines = earn_split_for_synthesis(
        claims=claims, doc_to_content_class=content, doc_to_ip_holder={},
        total_cents=500, algorithm="A",
    )
    assert lines == []


# --------------------------------------------------------------------------- #
# Invariant 2 — conservation to the cent
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("total", [0, 1, 2, 99, 100, 101, 333, 1_000_000])
def test_cents_conserved(total: int) -> None:
    """Sum of per-source cents equals the input (no cent minted or lost), across awkward
    totals that stress the largest-remainder rounding."""
    c2d = {"cX": "D1", "cW": "D1", "cY": "D2", "cZ": "D3"}  # D1:2 chunks, D2:1, D3:1
    tiers = {"D1": 1, "D2": 2, "D3": 3}
    content = {"D1": PUBLIC, "D2": PUBLIC, "D3": PUBLIC}
    claims = [
        _claim(0, "cX", c2d, tiers), _claim(1, "cW", c2d, tiers),
        _claim(2, "cY", c2d, tiers), _claim(3, "cZ", c2d, tiers),
    ]
    lines = earn_split_for_synthesis(
        claims=claims, doc_to_content_class=content,
        doc_to_ip_holder={"D1": "h1", "D2": "h2", "D3": "h3"},
        total_cents=total, algorithm="B",
    )
    assert sum(ln.cents for ln in lines) == total


# --------------------------------------------------------------------------- #
# Invariant 3 — per-citation multiplicity preserved (closes divergence Cause B)
# --------------------------------------------------------------------------- #

def test_multiplicity_a_source_grounding_two_claims_earns_double() -> None:
    """A source grounding TWO thesis-components earns ~2x one grounding a single component.
    A flat chunk→document map would collapse this to 1x (the input-shape bug); taking
    claim structure preserves it. Option A isolates the effect (no tier/confidence)."""
    c2d = {"cX": "D1", "cY": "D2"}
    tiers = {"D1": 1, "D2": 1}
    content = {"D1": PUBLIC, "D2": PUBLIC}
    # cX (→D1) grounds claim0 AND claim1; cY (→D2) grounds claim2. So D1:2 citations, D2:1.
    claims = [
        _claim(0, "cX", c2d, tiers),
        _claim(1, "cX", c2d, tiers),
        _claim(2, "cY", c2d, tiers),
    ]
    lines = _lines_by_doc(earn_split_for_synthesis(
        claims=claims, doc_to_content_class=content,
        doc_to_ip_holder={"D1": "h1", "D2": "h2"}, total_cents=300, algorithm="A",
    ))
    assert lines["D1"].cents == 200  # 2/3 of 300
    assert lines["D2"].cents == 100  # 1/3 of 300


# --------------------------------------------------------------------------- #
# Honest-zero + malformed-input guards
# --------------------------------------------------------------------------- #

def test_unowned_source_produces_none_holder_line() -> None:
    """A source with no resolved owner earns a line with ip_holder_id=None — an honest
    'unknown owner' the caller routes to the house, never an invented holder."""
    c2d = {"c1": "D1"}
    tiers = {"D1": 1}
    lines = earn_split_for_synthesis(
        claims=[_claim(0, "c1", c2d, tiers)], doc_to_content_class={"D1": PUBLIC},
        doc_to_ip_holder={"D1": None}, total_cents=100, algorithm="A",
    )
    assert lines == [SourceEarnLine(document_id="D1", ip_holder_id=None, share=1.0, cents=100)]


def test_empty_claims_and_zero_cents_are_empty() -> None:
    assert earn_split_for_synthesis(
        claims=[], doc_to_content_class={}, doc_to_ip_holder={},
        total_cents=100, algorithm="A") == []
    assert earn_split_for_synthesis(
        claims=[_claim(0, "c1", {"c1": "D1"}, {"D1": 1})],
        doc_to_content_class={"D1": PUBLIC}, doc_to_ip_holder={"D1": "h1"},
        total_cents=0, algorithm="A") == []


def test_negative_cents_and_unknown_algorithm_raise() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        earn_split_for_synthesis(
            claims=[], doc_to_content_class={}, doc_to_ip_holder={},
            total_cents=-1, algorithm="A")
    with pytest.raises(ValueError, match="unknown algorithm"):
        earn_split_for_synthesis(
            claims=[], doc_to_content_class={}, doc_to_ip_holder={},
            total_cents=100, algorithm="Z")
