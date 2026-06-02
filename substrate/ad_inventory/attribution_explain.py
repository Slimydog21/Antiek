"""Explainability: "why did this asset earn this?" (SPR-04 M4).

A read-only trace answering the publisher's (or counsel's) question: of the $X
an asset earned in a period, WHICH impressions/sessions and WHICH chunks
produced it, and which algorithm turned them into the asset's share. Traces the
provenance chain backwards: asset → document → chunk → impression.

This module RECONSTRUCTS the decomposition from substrate-of-truth inputs (the
attribution algorithm's per-chunk weights + the period's impression revenue). It
does not persist, disburse, or write escrow — it explains. The decomposition is
exact: the per-chunk contributions SUM to the asset's attributed total (the
load-bearing conservation property — money is neither created nor destroyed in
the explanation).

DEFERRED INPUT: per-impression revenue is NOT yet persisted by SPR-04 — the
reader-impression revenue ledger is a downstream sprint. Until it lands, the
caller MUST supply the period's impression/revenue figures explicitly; this
module reconstructs from what it is given and never invents an impression count.
"""

from __future__ import annotations

from dataclasses import dataclass

from .attribution import (
    AttributionAlgorithm,
    monetization_eligible,
)


def _chunk_weight(
    *,
    algorithm: AttributionAlgorithm,
    chunk_id: str,
    doc_id: str,
    chunk_to_claim_confidence: dict[str, float],
    document_to_source_tier: dict[str, int],
    claim_load_bearing_scores: dict[str, float],
    chunk_to_claim_id: dict[str, str],
) -> float:
    """The raw (pre-normalization) weight one chunk citation contributes under
    ``algorithm``. Mirrors EXACTLY the per-chunk term inside
    ``compute_attribution_option_*`` so the explanation cannot diverge from the
    computation it explains. Kept in lockstep by the conservation test (the
    per-chunk weights, normalized, reproduce the algorithm's per-document
    shares)."""
    if algorithm == AttributionAlgorithm.OPTION_A_EQUAL_SPLIT:
        return 1.0
    if algorithm == AttributionAlgorithm.OPTION_B_CONFIDENCE_TIMES_TIER:
        confidence = chunk_to_claim_confidence.get(chunk_id, 0.5)
        tier = document_to_source_tier.get(doc_id, 5)
        return confidence * (6 - tier)
    if algorithm == AttributionAlgorithm.OPTION_C_LOAD_BEARING:
        claim_id = chunk_to_claim_id.get(chunk_id)
        if claim_id is None:
            return 0.0
        return claim_load_bearing_scores.get(claim_id, 0.0)
    raise ValueError(f"unknown algorithm: {algorithm!r}")


@dataclass(frozen=True)
class ChunkContribution:
    """One chunk's contribution to an asset's earnings."""

    chunk_id: str
    document_id: str
    weight: float          # raw algorithm weight for this chunk
    share_of_asset: float  # this chunk's fraction of the asset's total weight
    earned_usd_cents: int  # this chunk's slice of the asset's earned dollars


@dataclass(frozen=True)
class AssetEarningExplanation:
    """The full "why did this asset earn this" answer for one asset + period."""

    document_id: str
    ip_holder_id: str | None
    algorithm: str
    period_label: str
    total_earned_usd_cents: int
    asset_share: float                      # the asset's share of the pool [0,1]
    contributing_impression_ids: tuple[str, ...]
    contributing_session_ids: tuple[str, ...]
    per_chunk: tuple[ChunkContribution, ...]
    eligible: bool


def _largest_remainder_cents(
    weights: dict[str, float], total_cents: int,
) -> dict[str, int]:
    """Apportion ``total_cents`` across keys by ``weights`` so the parts sum
    EXACTLY to ``total_cents`` (largest-remainder method). Integer cents can't
    represent a fractional split, so naive rounding would lose or invent a cent;
    largest-remainder conserves the total to the cent — the conservation
    property at the money layer."""
    total_w = sum(weights.values())
    if total_w <= 0 or total_cents == 0:
        return {k: 0 for k in weights}
    exact = {k: (w / total_w) * total_cents for k, w in weights.items()}
    floored = {k: int(v) for k, v in exact.items()}
    remainder = total_cents - sum(floored.values())
    # Hand out the leftover cents to the largest fractional remainders.
    order = sorted(
        weights.keys(),
        key=lambda k: (exact[k] - floored[k]),
        reverse=True,
    )
    for k in order[:remainder]:
        floored[k] += 1
    return floored


def explain_asset_earning(
    *,
    document_id: str,
    algorithm: AttributionAlgorithm,
    period_label: str,
    chunk_to_document: dict[str, str],
    period_revenue_usd_cents: int,
    chunk_to_claim_confidence: dict[str, float] | None = None,
    document_to_source_tier: dict[str, int] | None = None,
    claim_load_bearing_scores: dict[str, float] | None = None,
    chunk_to_claim_id: dict[str, str] | None = None,
    chunk_to_impression_id: dict[str, str] | None = None,
    impression_to_session: dict[str, str] | None = None,
    ip_holder_id: str | None = None,
    content_class: str | None = None,
) -> AssetEarningExplanation:
    """Explain why ``document_id`` earned what it did over ``period_label``.

    ``chunk_to_document`` is the full citation map for the period; the function
    isolates the chunks belonging to ``document_id``, computes each chunk's raw
    weight under ``algorithm``, derives the asset's share of the period pool, and
    apportions ``period_revenue_usd_cents`` down to the chunk (largest-remainder,
    so the per-chunk cents sum to the asset's total to the cent). Traces each
    contributing chunk back to its impression + session.

    If ``content_class`` is supplied and the asset is monetization-ineligible
    (a private upload), the explanation is the honest zero: it earned nothing,
    with the eligibility flag set so the dispute answer is unambiguous."""
    chunk_to_claim_confidence = chunk_to_claim_confidence or {}
    document_to_source_tier = document_to_source_tier or {}
    claim_load_bearing_scores = claim_load_bearing_scores or {}
    chunk_to_claim_id = chunk_to_claim_id or {}
    chunk_to_impression_id = chunk_to_impression_id or {}
    impression_to_session = impression_to_session or {}

    eligible = content_class is None or monetization_eligible(content_class)
    if not eligible:
        return AssetEarningExplanation(
            document_id=document_id,
            ip_holder_id=ip_holder_id,
            algorithm=algorithm.value,
            period_label=period_label,
            total_earned_usd_cents=0,
            asset_share=0.0,
            contributing_impression_ids=(),
            contributing_session_ids=(),
            per_chunk=(),
            eligible=False,
        )

    # Raw weight per chunk across the whole period (the denominator).
    all_weights: dict[str, float] = {}
    for chunk_id, doc_id in chunk_to_document.items():
        all_weights[chunk_id] = _chunk_weight(
            algorithm=algorithm, chunk_id=chunk_id, doc_id=doc_id,
            chunk_to_claim_confidence=chunk_to_claim_confidence,
            document_to_source_tier=document_to_source_tier,
            claim_load_bearing_scores=claim_load_bearing_scores,
            chunk_to_claim_id=chunk_to_claim_id,
        )
    total_weight = sum(all_weights.values())

    asset_chunks = [
        cid for cid, doc in chunk_to_document.items() if doc == document_id
    ]
    asset_weight = sum(all_weights[cid] for cid in asset_chunks)
    asset_share = (asset_weight / total_weight) if total_weight > 0 else 0.0

    # The asset's slice of the period revenue, conserved to the cent.
    asset_total_cents = _largest_remainder_cents(
        {document_id: asset_weight,
         "__rest__": max(0.0, total_weight - asset_weight)},
        period_revenue_usd_cents,
    )[document_id] if total_weight > 0 else 0

    # Decompose the asset's dollars across its own chunks (conserves to cent).
    per_chunk_cents = _largest_remainder_cents(
        {cid: all_weights[cid] for cid in asset_chunks}, asset_total_cents,
    )

    contributions: list[ChunkContribution] = []
    impression_ids: list[str] = []
    session_ids: list[str] = []
    for cid in sorted(asset_chunks):
        share_of_asset = (
            all_weights[cid] / asset_weight if asset_weight > 0 else 0.0
        )
        contributions.append(ChunkContribution(
            chunk_id=cid,
            document_id=document_id,
            weight=all_weights[cid],
            share_of_asset=share_of_asset,
            earned_usd_cents=per_chunk_cents.get(cid, 0),
        ))
        imp = chunk_to_impression_id.get(cid)
        if imp is not None:
            impression_ids.append(imp)
            sess = impression_to_session.get(imp)
            if sess is not None:
                session_ids.append(sess)

    return AssetEarningExplanation(
        document_id=document_id,
        ip_holder_id=ip_holder_id,
        algorithm=algorithm.value,
        period_label=period_label,
        total_earned_usd_cents=asset_total_cents,
        asset_share=asset_share,
        contributing_impression_ids=tuple(dict.fromkeys(impression_ids)),
        contributing_session_ids=tuple(dict.fromkeys(session_ids)),
        per_chunk=tuple(contributions),
        eligible=True,
    )


def explanation_to_json(exp: AssetEarningExplanation) -> dict:
    """Serialize an explanation to a JSON-friendly dict (read-only surface)."""
    return {
        "document_id": exp.document_id,
        "ip_holder_id": exp.ip_holder_id,
        "algorithm": exp.algorithm,
        "period_label": exp.period_label,
        "total_earned_usd_cents": exp.total_earned_usd_cents,
        "asset_share": exp.asset_share,
        "eligible": exp.eligible,
        "contributing_impression_ids": list(exp.contributing_impression_ids),
        "contributing_session_ids": list(exp.contributing_session_ids),
        "per_chunk": [
            {
                "chunk_id": c.chunk_id,
                "document_id": c.document_id,
                "weight": c.weight,
                "share_of_asset": c.share_of_asset,
                "earned_usd_cents": c.earned_usd_cents,
            }
            for c in exp.per_chunk
        ],
    }


__all__ = [
    "AssetEarningExplanation",
    "ChunkContribution",
    "explain_asset_earning",
    "explanation_to_json",
]
