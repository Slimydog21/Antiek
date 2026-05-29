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


# Algorithm-math version stamp (SPR-04 M3/M5). Bump this WHENEVER the math
# in compute_attribution_option_{a,b,c} changes — a different weighting, a
# different default, a different tie-break. The audit record
# (attribution_audit.py) stamps this alongside every computation so a payout
# can be reconstructed against the exact math that produced it months later or
# in front of counsel (defensibility, rigor #5). The version is intentionally
# NOT the global ANTIEK_PARAM_VERSION: that tracks the whole substrate; this
# tracks ONLY the contribution-weighting math, so a payout dispute points at a
# single, narrow surface. test_attribution_golden.py enforces that a math tweak
# without a bump trips a golden mismatch.
ATTRIBUTION_ALGORITHM_VERSION = "attr-math-v1"


class AttributionAlgorithm(str, enum.Enum):
    """The three attribution options from master-spec §9.3."""

    OPTION_A_EQUAL_SPLIT = "equal_split_per_chunk_citation"
    OPTION_B_CONFIDENCE_TIMES_TIER = "claim_confidence_times_source_tier"
    OPTION_C_LOAD_BEARING = "load_bearing_via_secondary_pass"


# ---------------------------------------------------------------------------
# Monetization-eligibility — the EARN gate (SPR-04 M2)
# ---------------------------------------------------------------------------
#
# Orthogonal to §9.0 servability. §9.0 (substrate/contracts/servable.py +
# constants.py §I) gates whether a body RENDERS full text. Monetization
# eligibility gates whether an asset EARNS. The two answer different questions
# off the SAME field (documents.content_class), so they cannot drift:
#
#   * A gated copyrighted-but-public asset (content_class=
#     'restricted_pending_opt_in') is eligible-to-earn — its body stays
#     non-servable (escrow accrues to its pre-onboarded holder per §9.10).
#   * A private public-domain upload (content_class='user_owned') is
#     INELIGIBLE — it is not exposed to the public graph, so no ad reading
#     session can surface it and it must never appear in an attribution split.
#
# The eligibility decision is DERIVED from content_class, never stored: a
# second stored truth would drift from the graph-visibility gate in
# substrate/graph/search.py (which already excludes 'user_owned' from any
# non-owner retrieval). One field, two derivations.

# The content_class values that mean "exposed to the public Antiek graph"
# (i.e. a public reading session can surface the asset). Mirrors the
# documents.content_class vocabulary documented at schema.py L405-411 and the
# retrieval visibility in search.py. 'user_owned' is the ONLY private class
# (only the owner_user_id can retrieve it — schema.py L410) and is therefore
# the only ineligible-to-earn class. A NULL / unknown content_class is treated
# as ineligible (deny-by-default for the EARN gate, matching the deny-by-default
# posture of the §9.0 RENDER gate).
PUBLIC_GRAPH_CONTENT_CLASSES: frozenset[str] = frozenset({
    "public_domain",              # out-of-copyright / CC0; public + servable
    "opt_in_licensed",            # publisher claimed via §9.10; public + servable
    "source_declared_open",       # source-declared open (CC-BY/CC-BY-SA); public + servable; accrues into pool/escrow
    "user_public_contribution",   # user-posted to the public graph (§13.9)
    "restricted_pending_opt_in",  # gated-but-public: body withheld, EARNS to escrow
})

# TWO DISTINCT EARN GATES — do not "harmonize" them. This module's
# monetization_eligible() is the OUTER gate: "may this asset accrue ad revenue
# into the pool/escrow at all", keyed only on public-graph membership. It is
# deliberately WIDER than collective_graph.eligibility.is_attribution_eligible(),
# the INNER payout gate that decides whether an accrued amount is released to a
# *claimed IP holder* — that gate additionally excludes 'restricted_pending_opt_in'
# (body withheld, holder not yet onboarded → escrow, no payout) and
# 'opt_in_licensed' without ip_holder_claimed. The two giving OPPOSITE answers
# for 'restricted_pending_opt_in' is intended by §9.10: such an asset EARNS (into
# escrow) but is NOT yet PAID OUT. A future maintainer must not collapse these
# into one predicate — the escrow layer depends on the gap.
#
# The single private (graph-excluded) class. Named so a dispute answer can
# cite WHICH class made an asset ineligible.
PRIVATE_GRAPH_CONTENT_CLASS = "user_owned"


@dataclass(frozen=True)
class EligibilityDecision:
    """Why an asset is (in)eligible to earn — the answer to a publisher dispute.

    ``deciding_field`` names the classification field the decision was derived
    from (always ``content_class`` today); ``deciding_value`` is the value that
    field held. Together they let a dispute be answered without re-deriving:
    "your asset earned $0 because content_class='user_owned' (a private upload
    not in the public graph)" — vs a servability denial, which is a different
    gate entirely (``servable`` here records the §9.0 answer so the two can be
    shown to be decoupled)."""

    eligible: bool
    deciding_field: str
    deciding_value: Optional[str]
    reason: str


def eligibility_decision(content_class: Optional[str]) -> EligibilityDecision:
    """Derive the monetization-eligibility decision from an asset's
    ``content_class`` (the EARN gate). Returns the full decision object so a
    dispute is answerable; :func:`monetization_eligible` is the boolean shortcut.

    Deny-by-default: a NULL/unknown class is ineligible (it has not been
    affirmatively placed in the public graph)."""
    if content_class in PUBLIC_GRAPH_CONTENT_CLASSES:
        return EligibilityDecision(
            eligible=True,
            deciding_field="content_class",
            deciding_value=content_class,
            reason=(
                f"content_class={content_class!r} is exposed to the public "
                "graph (eligible to earn; orthogonal to §9.0 body servability)"
            ),
        )
    if content_class == PRIVATE_GRAPH_CONTENT_CLASS:
        return EligibilityDecision(
            eligible=False,
            deciding_field="content_class",
            deciding_value=content_class,
            reason=(
                "content_class='user_owned' is a private upload not exposed to "
                "the public graph (only the owner can retrieve it); it earns "
                "nothing and never appears in an attribution split"
            ),
        )
    # NULL / unrecognised → deny-by-default for the earn gate.
    return EligibilityDecision(
        eligible=False,
        deciding_field="content_class",
        deciding_value=content_class,
        reason=(
            f"content_class={content_class!r} is not an affirmed public-graph "
            "class; deny-by-default (ineligible to earn)"
        ),
    )


def monetization_eligible(content_class: Optional[str]) -> bool:
    """True iff an asset is publicly searchable in the Antiek graph and may
    therefore EARN (servable-body or gated-body alike). False for a private
    user upload (``content_class='user_owned'``) or unknown provenance.

    Derived from ``content_class`` — the same field §9.0 servability derives
    from — so the earn gate cannot drift from the graph-visibility gate. See
    :func:`eligibility_decision` for the field-level dispute answer."""
    return eligibility_decision(content_class).eligible


def eligible_shares(
    shares: dict[str, float],
    document_to_content_class: dict[str, Optional[str]],
) -> dict[str, float]:
    """Drop ineligible documents from an attribution split, then renormalize
    the survivors to sum to 1.0 (conservation — the pool is conserved across
    only the eligible assets).

    An ineligible asset (private upload) accrues NOTHING: it is removed before
    the split, never zero-weighted-but-present. If every document is ineligible
    the result is empty (the honest answer — no eligible asset to attribute to,
    no invented money)."""
    kept = {
        doc_id: w
        for doc_id, w in shares.items()
        if monetization_eligible(document_to_content_class.get(doc_id))
    }
    total = sum(kept.values())
    if total <= 0:
        return {}
    return {doc_id: w / total for doc_id, w in kept.items()}


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
