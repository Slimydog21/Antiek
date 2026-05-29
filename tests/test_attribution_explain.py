"""Explainability: "why did this asset earn this?" (SPR-04 M4).

The load-bearing assertion: per-chunk contributions SUM to the asset's
attributed total. Works for all three algorithms. Traces asset → document →
chunk → impression → session.
"""

from __future__ import annotations

import pytest

from substrate.ad_inventory.attribution import (
    AttributionAlgorithm,
    PRIVATE_GRAPH_CONTENT_CLASS,
    compute_attribution_option_a,
    compute_attribution_option_b,
    compute_attribution_option_c,
)
from substrate.ad_inventory.attribution_explain import (
    explain_asset_earning,
    explanation_to_json,
)


def _period():
    return {
        "chunk_to_document": {
            "ch-1": "doc-A", "ch-2": "doc-B", "ch-3": "doc-A", "ch-4": "doc-B",
        },
        "chunk_to_claim_confidence": {
            "ch-1": 1.0, "ch-2": 0.75, "ch-3": 0.4, "ch-4": 1.0,
        },
        "document_to_source_tier": {"doc-A": 1, "doc-B": 3},
        "claim_load_bearing_scores": {
            "cl-1": 0.9, "cl-2": 0.4, "cl-3": 0.2, "cl-4": 0.6,
        },
        "chunk_to_claim_id": {
            "ch-1": "cl-1", "ch-2": "cl-2", "ch-3": "cl-3", "ch-4": "cl-4",
        },
        "chunk_to_impression_id": {
            "ch-1": "imp-1", "ch-2": "imp-2", "ch-3": "imp-1", "ch-4": "imp-3",
        },
        "impression_to_session": {
            "imp-1": "sess-1", "imp-2": "sess-1", "imp-3": "sess-2",
        },
    }


# ── Per-chunk contributions sum to the asset total (all three algorithms) ──


@pytest.mark.parametrize("algorithm", list(AttributionAlgorithm))
def test_per_chunk_sums_to_asset_total(algorithm):
    p = _period()
    exp = explain_asset_earning(
        document_id="doc-A",
        algorithm=algorithm,
        period_label="2026-05",
        period_revenue_usd_cents=10_000,
        **p,
    )
    chunk_sum = sum(c.earned_usd_cents for c in exp.per_chunk)
    assert chunk_sum == exp.total_earned_usd_cents


@pytest.mark.parametrize("algorithm", list(AttributionAlgorithm))
def test_asset_share_matches_real_algorithm_share(algorithm):
    """The explanation's asset_share equals the share the REAL compute_*
    function gives the asset — the explanation cannot diverge from the math."""
    p = _period()
    if algorithm == AttributionAlgorithm.OPTION_A_EQUAL_SPLIT:
        shares = compute_attribution_option_a(
            page_id="p", chunk_to_document=p["chunk_to_document"],
        ).shares
    elif algorithm == AttributionAlgorithm.OPTION_B_CONFIDENCE_TIMES_TIER:
        shares = compute_attribution_option_b(
            page_id="p",
            chunk_to_document=p["chunk_to_document"],
            chunk_to_claim_confidence=p["chunk_to_claim_confidence"],
            document_to_source_tier=p["document_to_source_tier"],
        ).shares
    else:
        shares = compute_attribution_option_c(
            page_id="p",
            chunk_to_document=p["chunk_to_document"],
            claim_load_bearing_scores=p["claim_load_bearing_scores"],
            chunk_to_claim_id=p["chunk_to_claim_id"],
        ).shares
    exp = explain_asset_earning(
        document_id="doc-A", algorithm=algorithm, period_label="2026-05",
        period_revenue_usd_cents=10_000, **p,
    )
    assert exp.asset_share == pytest.approx(shares["doc-A"])


# ── Two-asset cents conserve across the period ──────────────────────────────


def test_two_assets_cents_conserve_to_the_period_total():
    """doc-A + doc-B earnings sum to the period revenue (no cent lost/invented)."""
    p = _period()
    a = explain_asset_earning(
        document_id="doc-A", algorithm=AttributionAlgorithm.OPTION_B_CONFIDENCE_TIMES_TIER,
        period_label="2026-05", period_revenue_usd_cents=9_999, **p,
    )
    b = explain_asset_earning(
        document_id="doc-B", algorithm=AttributionAlgorithm.OPTION_B_CONFIDENCE_TIMES_TIER,
        period_label="2026-05", period_revenue_usd_cents=9_999, **p,
    )
    assert a.total_earned_usd_cents + b.total_earned_usd_cents == 9_999


# ── Trace: asset → document → chunk → impression → session ──────────────────


def test_trace_links_chunks_to_impressions_and_sessions():
    p = _period()
    exp = explain_asset_earning(
        document_id="doc-A", algorithm=AttributionAlgorithm.OPTION_A_EQUAL_SPLIT,
        period_label="2026-05", period_revenue_usd_cents=10_000, **p,
    )
    # doc-A is cited by ch-1 and ch-3.
    assert {c.chunk_id for c in exp.per_chunk} == {"ch-1", "ch-3"}
    # Both trace to imp-1 (deduped), which traces to sess-1.
    assert exp.contributing_impression_ids == ("imp-1",)
    assert exp.contributing_session_ids == ("sess-1",)


def test_explanation_json_shape():
    p = _period()
    exp = explain_asset_earning(
        document_id="doc-A", algorithm=AttributionAlgorithm.OPTION_B_CONFIDENCE_TIMES_TIER,
        period_label="2026-05", period_revenue_usd_cents=10_000,
        ip_holder_id="iph-1", **p,
    )
    j = explanation_to_json(exp)
    assert j["document_id"] == "doc-A"
    assert j["ip_holder_id"] == "iph-1"
    assert j["algorithm"] == "claim_confidence_times_source_tier"
    assert len(j["per_chunk"]) == 2
    assert sum(c["earned_usd_cents"] for c in j["per_chunk"]) == j["total_earned_usd_cents"]


# ── Ineligible asset: the honest zero ───────────────────────────────────────


def test_ineligible_private_upload_earns_zero():
    p = _period()
    exp = explain_asset_earning(
        document_id="doc-A", algorithm=AttributionAlgorithm.OPTION_B_CONFIDENCE_TIMES_TIER,
        period_label="2026-05", period_revenue_usd_cents=10_000,
        content_class=PRIVATE_GRAPH_CONTENT_CLASS, **p,
    )
    assert exp.eligible is False
    assert exp.total_earned_usd_cents == 0
    assert exp.per_chunk == ()


def test_eligible_gated_public_asset_earns():
    p = _period()
    exp = explain_asset_earning(
        document_id="doc-A", algorithm=AttributionAlgorithm.OPTION_B_CONFIDENCE_TIMES_TIER,
        period_label="2026-05", period_revenue_usd_cents=10_000,
        content_class="restricted_pending_opt_in", **p,
    )
    assert exp.eligible is True
    assert exp.total_earned_usd_cents > 0
