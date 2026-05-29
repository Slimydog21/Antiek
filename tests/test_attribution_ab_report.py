"""A/B/C comparison surface (SPR-04 M6) — read-only.

The comparison surfaces all three algorithms over the SAME inputs so the
operator can pick the production algorithm. It must NOT write to payout/escrow,
and it documents Option B as the current default.
"""

from __future__ import annotations

import pytest

from substrate.ad_inventory.attribution import AttributionAlgorithm
from substrate.ad_inventory.attribution_audit import (
    compare_algorithms,
    comparison_to_json,
)


def _inputs():
    return {
        "page_id": "page-1",
        "chunk_to_document": {"ch-1": "doc-A", "ch-2": "doc-B", "ch-3": "doc-A"},
        "chunk_to_claim_confidence": {"ch-1": 1.0, "ch-2": 1.0, "ch-3": 0.4},
        "document_to_source_tier": {"doc-A": 1, "doc-B": 4},
        "claim_load_bearing_scores": {"cl-1": 0.9, "cl-2": 0.3, "cl-3": 0.1},
        "chunk_to_claim_id": {"ch-1": "cl-1", "ch-2": "cl-2", "ch-3": "cl-3"},
    }


def test_comparison_has_all_three_columns_per_asset():
    cmp = compare_algorithms(**_inputs())
    assert set(cmp.per_asset.keys()) == {"doc-A", "doc-B"}
    for doc, cols in cmp.per_asset.items():
        assert set(cols.keys()) == {"A", "B", "C"}


def test_each_algorithm_column_conserves_pool():
    """Each algorithm's column sums to 1.0 across the assets (the same pool,
    weighted differently)."""
    cmp = compare_algorithms(**_inputs())
    for algo in ("A", "B", "C"):
        col_sum = sum(cols[algo] for cols in cmp.per_asset.values())
        assert col_sum == pytest.approx(1.0)


def test_option_b_weights_high_tier_higher_than_a():
    """B (tier-weighted) gives the tier-1 doc-A a larger share than A (equal
    split) — the comparison shows the algorithms genuinely differ."""
    cmp = compare_algorithms(**_inputs())
    assert cmp.per_asset["doc-A"]["B"] > cmp.per_asset["doc-A"]["A"]
    assert cmp.per_asset["doc-B"]["B"] < cmp.per_asset["doc-B"]["A"]


def test_default_is_option_b_and_documented():
    cmp = compare_algorithms(**_inputs())
    assert cmp.default_algorithm == AttributionAlgorithm.OPTION_B_CONFIDENCE_TIMES_TIER.value
    assert "§9.3" in cmp.default_rationale
    assert "operator" in cmp.default_rationale.lower()


def test_comparison_json_shape():
    cmp = compare_algorithms(**_inputs())
    j = comparison_to_json(cmp)
    assert j["page_id"] == "page-1"
    assert j["default_algorithm"] == "claim_confidence_times_source_tier"
    assert "per_asset" in j and "doc-A" in j["per_asset"]


def test_asset_absent_from_one_algorithm_is_honest_zero():
    """Option C scores only claims with a load-bearing score; a doc whose only
    claim scored 0 still appears with an honest 0.0 (not absent)."""
    inputs = _inputs()
    # doc-B's only claim (cl-2) gets zero load-bearing → C gives it 0.
    inputs["claim_load_bearing_scores"] = {"cl-1": 1.0, "cl-2": 0.0, "cl-3": 0.5}
    cmp = compare_algorithms(**inputs)
    assert cmp.per_asset["doc-B"]["C"] == 0.0
    # But doc-B still appears (A and B give it a share).
    assert cmp.per_asset["doc-B"]["A"] > 0.0
