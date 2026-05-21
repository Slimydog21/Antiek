"""Wedge 3 — Exa `/contents` corroboration primitive.

Spec: `docs/integration_exa_browserbase.md` §8. PHASE 2 wedge. This
module ships the **client-side primitive only** — the function the
verifier tier (or any caller) invokes to consult Exa for claim
corroboration.

What's NOT in scope of this module (per spec §8.4 — these are
substrate decisions, not Exa-spec side effects):

  - The verifier-tier multi-turn dispatch wiring that lets the
    verifier-tier model call this as a tool. That requires
    `substrate/dispatch/` changes.
  - The calibration eval set (≥20 misleading-pair fixtures) that
    gates production-scoring activation. That's a data deliverable
    operator-curated; out of code scope.
  - Promotion of looked-up URLs into the substrate graph. NEVER.
    The spec at §8.3 is load-bearing: snippets stay out of the
    graph; if the operator wants a lookup result as substrate
    evidence, they promote the URL via the standard
    `acquisition/urls/adapter.ingest_url` path (which is exactly
    what `acquisition/search/exa.promote_discovery` does for the
    discovery layer).

Caller pattern:

    from acquisition.search.exa.lookup import exa_lookup_claim

    results = exa_lookup_claim(
        claim_text="Tesla delivered 462,890 vehicles in Q3 2025",
        k=3,
        investigation_id="inv-...",
    )
    # `results` is a list[ExaLookupResult]. The verifier tier reads
    # the snippets as context; the substrate's claim-grounding
    # verdict still anchors to ingested chunks, not to these
    # snippets.

The function emits exactly one `VerifierLookupPayload` event per
call — even an empty-results call records that the verifier
considered an external lookup. Budget is consulted via the same
`acquisition/search/exa/budget.py` daily-cap path as discover().
"""

from __future__ import annotations

import os
import sys
from typing import List, Optional

# Repo root on path for direct invocation.
_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from substrate.event_log import emit_typed  # noqa: E402
from substrate.schemas.events import (  # noqa: E402
    ExaLookupResult,
    VerifierLookupPayload,
)

from .budget import check_and_reserve  # noqa: E402
from .client import COST_PER_SEARCH_USD, ExaClient  # noqa: E402


MAX_K = 20


def exa_lookup_claim(
    *,
    claim_text: str,
    investigation_id: str,
    k: int = 3,
    require_published_after: Optional[str] = None,
    client: Optional[ExaClient] = None,
    daily_budget_usd: Optional[float] = None,
    events_dir: Optional[str] = None,
) -> List[ExaLookupResult]:
    """Search Exa for ≤k pages whose text appears to support or
    refute ``claim_text``. Returns the typed ``ExaLookupResult``
    list. Emits exactly one ``VerifierLookupPayload`` event
    regardless of result count.

    **No graph writes.** The verifier-tier consumer reads the
    snippets as context; the substrate's claim-grounding verdict
    stays anchored to ingested chunks. Promotion of a result URL
    into the graph requires the operator to call
    ``acquisition.urls.adapter.ingest_url`` separately.

    Raises:
        ValueError: when ``claim_text`` or ``investigation_id`` is
            empty, or ``k`` is out of [1, 20].
        DiscoveryBudgetExceeded: when the daily Exa budget is
            exhausted (same cap as discover()).
        ExaClientError: on Exa-side errors.
    """
    if not claim_text.strip():
        raise ValueError("exa_lookup_claim: empty claim_text")
    if not investigation_id.strip():
        raise ValueError("exa_lookup_claim: empty investigation_id")
    if k < 1 or k > MAX_K:
        raise ValueError(f"exa_lookup_claim: k must be 1..{MAX_K}")

    # Per spec §6.7 — optimistic budget reservation BEFORE the
    # Exa call. Same per-search cost as discover(); the call
    # shape is identical (POST /search with text=true).
    check_and_reserve(COST_PER_SEARCH_USD, cap_override=daily_budget_usd)

    cli = client or ExaClient()
    # Use the claim text as the query. Exa's neural search handles
    # natural-language claims directly — no need for the verifier
    # to pre-extract keywords. The result snippets are what the
    # verifier consumes.
    response = cli.search(
        query=claim_text,
        num_results=k,
        start_published_date=require_published_after,
    )

    results: List[ExaLookupResult] = []
    for r in response.results:
        # The Exa client already truncated snippets at 300 chars
        # for `discover()` output. For verifier lookup the
        # snippet ceiling is higher (≤2000 chars in the payload
        # schema) because the verifier benefits from more context.
        # The Exa SDK side of this is handled at /search-time;
        # what we have here is the already-truncated short form.
        # When migrating to /contents (which returns full text)
        # the longer cap matters.
        results.append(
            ExaLookupResult(
                url=r.url,
                title=r.title,
                published_date=r.published_date,
                text_snippet=r.text_snippet_preview,
                relevance_score=r.relevance_score,
                provider_response_id=r.provider_response_id,
            )
        )

    # Per spec §8.2 — emit exactly one event per call, even on
    # empty results. The trajectory's audit trail records that
    # the verifier considered an external lookup.
    total_cost = sum(
        (r.cost_usd_estimate for r in response.results),
        start=0.0,
    ) or COST_PER_SEARCH_USD
    emit_typed(
        investigation_id,
        VerifierLookupPayload(
            tool="exa.search_contents",
            query=claim_text,
            claim_text=claim_text,
            k_requested=k,
            results=results,
            cost_usd_estimate=total_cost,
        ),
        role="verifier",
        policy_id="acquisition/search/exa/lookup",
        events_dir=events_dir,
    )
    return results


__all__ = [
    "MAX_K",
    "exa_lookup_claim",
]
