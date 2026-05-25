"""Attribution math — three options per master-spec §9.3.

Sprint 16 telemetry computes all three in parallel for A/B analysis.
Sprint 23-24 Phase 4 payouts use Option B as default; Option C as
premium tier for high-value pages.

**Concern (seam #3 — distinct from the marketplace-metrics one).** This module
is the **contribution-weighting** attribution: given a rendered page, how is
its attribution *split* across the source documents (algorithms A / B / C)? It
produces *shares*, not money, and it does **not** write escrow. The Speak
contributor split (``substrate/speak/contributor.py``) consumes weighting of
this kind to size each contributor's slice.

**Single-writer rule (seam #3).** Two attribution concerns are fine; two
writers to the escrow ledger are not. This module emits/feeds the single
``AccrualContract`` shape (``substrate/contracts/accrual.py``); it never writes
escrow. Exactly one code path increments an escrow balance —
``substrate/ip_holders/__init__.py::accrue_escrow`` (the only
``SET escrow_balance_usd = …`` in the tree), reached today only from
``substrate/speak/contributor.py``. ``tests/test_seam_single_escrow_writer.py``
greps this invariant. See ``docs/decisions/tech-stack-ledger.md`` for the
ledger naming nuance."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Optional


class AttributionAlgorithm(str, enum.Enum):
    """The three attribution options from master-spec §9.3."""

    OPTION_A_EQUAL_SPLIT = "equal_split_per_chunk_citation"
    OPTION_B_CONFIDENCE_TIMES_TIER = "claim_confidence_times_source_tier"
    OPTION_C_LOAD_BEARING = "load_bearing_via_secondary_pass"


@dataclass(frozen=True)
class AttributionResult:
    """Result of running an attribution algorithm against a page render.

    Maps source documents to their share of attribution (sums to 1.0).
    """

    algorithm: AttributionAlgorithm
    page_id: str  # the synthesis page that was rendered
    shares: dict[str, float]  # document_id → share in [0, 1]
    page_attribution_event_id: Optional[str] = None


def compute_attribution_option_a(
    *,
    page_id: str,
    chunk_to_document: dict[str, str],
) -> AttributionResult:
    """Option A — equal split per chunk citation.

    Document gets share = (its chunks cited on page) / (total chunks
    cited on page). Simplest. Fails to weight by importance."""
    if not chunk_to_document:
        return AttributionResult(
            algorithm=AttributionAlgorithm.OPTION_A_EQUAL_SPLIT,
            page_id=page_id,
            shares={},
        )
    counts: dict[str, int] = {}
    for doc_id in chunk_to_document.values():
        counts[doc_id] = counts.get(doc_id, 0) + 1
    total = sum(counts.values())
    shares = {doc_id: cnt / total for doc_id, cnt in counts.items()}
    return AttributionResult(
        algorithm=AttributionAlgorithm.OPTION_A_EQUAL_SPLIT,
        page_id=page_id,
        shares=shares,
    )


def compute_attribution_option_b(
    *,
    page_id: str,
    chunk_to_document: dict[str, str],
    chunk_to_claim_confidence: dict[str, float],
    document_to_source_tier: dict[str, int],
) -> AttributionResult:
    """Option B — weighted by claim_confidence × (6 - source_tier).

    Higher-confidence claims grounded in higher-tier sources contribute
    more. Aligns incentives toward quality. This is the **recommended
    default** for Phase 2 payouts per master-spec §9.3."""
    if not chunk_to_document:
        return AttributionResult(
            algorithm=AttributionAlgorithm.OPTION_B_CONFIDENCE_TIMES_TIER,
            page_id=page_id,
            shares={},
        )
    weights: dict[str, float] = {}
    for chunk_id, doc_id in chunk_to_document.items():
        confidence = chunk_to_claim_confidence.get(chunk_id, 0.5)
        tier = document_to_source_tier.get(doc_id, 5)
        # tier 1=highest trust, 5=lowest; (6 - tier) gives weight 5..1
        contribution = confidence * (6 - tier)
        weights[doc_id] = weights.get(doc_id, 0.0) + contribution

    total = sum(weights.values())
    if total <= 0:
        return AttributionResult(
            algorithm=AttributionAlgorithm.OPTION_B_CONFIDENCE_TIMES_TIER,
            page_id=page_id,
            shares={},
        )
    shares = {doc_id: w / total for doc_id, w in weights.items()}
    return AttributionResult(
        algorithm=AttributionAlgorithm.OPTION_B_CONFIDENCE_TIMES_TIER,
        page_id=page_id,
        shares=shares,
    )


def compute_attribution_option_c(
    *,
    page_id: str,
    chunk_to_document: dict[str, str],
    claim_load_bearing_scores: dict[str, float],
    chunk_to_claim_id: dict[str, str],
) -> AttributionResult:
    """Option C — weighted by 'load-bearing'-ness.

    A secondary LLM pass scores each claim: 'if you removed this
    claim, would the thesis change?' Yes-answers contribute
    disproportionately. Most defensible attribution-wise. Most
    expensive computationally.

    Sprint 23+ premium tier per master-spec §9.3 recommended phased
    approach.

    Args:
        claim_load_bearing_scores: claim_id → load-bearing score in
            [0, 1]; produced by a secondary LLM pass (the substrate
            does NOT score load-bearing here — that's an upstream
            dispatch). Higher = more load-bearing.
        chunk_to_claim_id: chunk_id → claim_id the chunk supports.
    """
    if not chunk_to_document:
        return AttributionResult(
            algorithm=AttributionAlgorithm.OPTION_C_LOAD_BEARING,
            page_id=page_id,
            shares={},
        )
    weights: dict[str, float] = {}
    for chunk_id, doc_id in chunk_to_document.items():
        claim_id = chunk_to_claim_id.get(chunk_id)
        if claim_id is None:
            continue
        score = claim_load_bearing_scores.get(claim_id, 0.0)
        weights[doc_id] = weights.get(doc_id, 0.0) + score

    total = sum(weights.values())
    if total <= 0:
        return AttributionResult(
            algorithm=AttributionAlgorithm.OPTION_C_LOAD_BEARING,
            page_id=page_id,
            shares={},
        )
    shares = {doc_id: w / total for doc_id, w in weights.items()}
    return AttributionResult(
        algorithm=AttributionAlgorithm.OPTION_C_LOAD_BEARING,
        page_id=page_id,
        shares=shares,
    )
