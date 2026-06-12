"""Discovery adapter — Parallel Search for DRW gather (SPR-DRL-08).

``discover`` calls the Parallel Search client and emits ``DiscoveryProposed``
events. ``promote_discovery`` routes through ``ingest_url`` — the single
substrate-write seam. No Parallel Task API; no direct graph writes.
"""

from __future__ import annotations

import hashlib
import os
import sys
from typing import Any

_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from acquisition.search.exa.adapter import (  # noqa: E402
    DiscoveryPromotionResult,
    DiscoveryProposed,
    suggest_tier,
)
from substrate.event_log import emit_typed  # noqa: E402
from substrate.legal_gate import LegalGate, default_legal_gate  # noqa: E402
from substrate.schemas.events import (  # noqa: E402
    DiscoveryProposedPayload,
    DiscoverySelectedPayload,
)

from .client import COST_PER_SEARCH_USD, ParallelClient, ParallelSearchResult  # noqa: E402

_DISCOVERY_ID_PREFIX = "disc-parallel-"
_POLICY_ID = "acquisition/search/parallel"


def _discovery_id(url: str, investigation_id: str, query: str = "") -> str:
    h = hashlib.sha256(
        f"{url}\x1f{investigation_id}\x1f{query}".encode()
    ).hexdigest()[:16]
    return f"{_DISCOVERY_ID_PREFIX}{h}"


def _search_queries_from_objective(objective: str) -> list[str]:
    """Derive 2–3 keyword queries from a sub-question (Parallel API guidance)."""
    text = objective.strip()
    if not text:
        raise ValueError("discover: empty objective")
    words = text.split()
    if len(words) <= 6:
        return [text]
    mid = max(3, len(words) // 2)
    q1 = " ".join(words[:6])
    q2 = " ".join(words[mid : mid + 6])
    return [q1, q2]


def discover(
    *,
    query: str,
    investigation_id: str,
    num_results: int = 10,
    client: ParallelClient | None = None,
    events_dir: str | None = None,
    session_id: str | None = None,
) -> list[DiscoveryProposed]:
    """Run Parallel Search; emit DiscoveryProposed events; return proposals."""
    if not query.strip():
        raise ValueError("discover: empty query")
    if not investigation_id.strip():
        raise ValueError("discover: empty investigation_id")
    if events_dir is None:
        from acquisition.search import default_discovery_events_dir  # noqa: PLC0415

        events_dir = default_discovery_events_dir()

    cli = client or ParallelClient()
    response = cli.search(
        objective=query,
        search_queries=_search_queries_from_objective(query),
        max_results=num_results,
        session_id=session_id,
    )

    proposals: list[DiscoveryProposed] = []
    for r in response.results:
        if not r.url:
            continue
        proposals.append(
            _emit_proposed(
                r,
                query=query,
                investigation_id=investigation_id,
                events_dir=events_dir,
                search_id=response.search_id,
            )
        )
    return proposals


def _emit_proposed(
    r: ParallelSearchResult,
    *,
    query: str,
    investigation_id: str,
    events_dir: str | None,
    search_id: str | None,
) -> DiscoveryProposed:
    discovery_id = _discovery_id(r.url, investigation_id, query)
    tier = suggest_tier(r.url)
    provider_specific: dict[str, Any] = {}
    if search_id is not None:
        provider_specific["search_id"] = search_id
    payload = DiscoveryProposedPayload(
        discovery_id=discovery_id,
        provider="parallel",
        query=query,
        url=r.url,
        title=r.title,
        published_date=r.published_date,
        author=None,
        relevance_score=None,
        suggested_tier=tier,
        text_snippet_preview=r.text_snippet_preview,
        provider_response_id=None,
        cost_usd_estimate=r.cost_usd_estimate or COST_PER_SEARCH_USD,
        provider_specific=provider_specific,
    )
    event_id = emit_typed(
        investigation_id,
        payload,
        role="acquisition",
        policy_id=_POLICY_ID,
        events_dir=events_dir,
    )
    return DiscoveryProposed(
        discovery_id=discovery_id,
        provider="parallel",
        query=query,
        url=r.url,
        title=r.title,
        published_date=r.published_date,
        author=None,
        relevance_score=None,
        suggested_tier=tier,
        text_snippet_preview=r.text_snippet_preview,
        provider_response_id=search_id,
        cost_usd_estimate=r.cost_usd_estimate or COST_PER_SEARCH_USD,
        proposed_event_id=event_id,
        provider_specific=provider_specific,
    )


def promote_discovery(
    discovery: DiscoveryProposed,
    *,
    investigation_id: str,
    source_tier: int | None = None,
    legal_gate: LegalGate | None = None,
    db_path: str | None = None,
    embedder: object | None = None,
    events_dir: str | None = None,
) -> DiscoveryPromotionResult:
    """Promote a prior discovery to ingestion via ``ingest_url``."""
    if events_dir is None:
        from acquisition.search import default_discovery_events_dir  # noqa: PLC0415

        events_dir = default_discovery_events_dir()

    gate = legal_gate or default_legal_gate()
    verdict = gate.check_url(discovery.url)

    if not verdict.allowed:
        selected = DiscoverySelectedPayload(
            discovery_id=discovery.discovery_id,
            document_id=None,
            decision="rejected_by_legal_gate",
            rejection_reason=verdict.reason,
        )
        event_id = emit_typed(
            investigation_id,
            selected,
            role="acquisition",
            policy_id=_POLICY_ID,
            events_dir=events_dir,
        )
        return DiscoveryPromotionResult(
            discovery_id=discovery.discovery_id,
            decision="rejected_by_legal_gate",
            document_id=None,
            selected_event_id=event_id,
            rejection_reason=verdict.reason,
            legal_gate_kind=verdict.gate_kind,
        )

    from acquisition.urls.adapter import ingest_url

    tier = source_tier if source_tier is not None else discovery.suggested_tier
    try:
        ingest_result = ingest_url(
            discovery.url,
            investigation_id=investigation_id,
            source_tier=tier,
            db_path=db_path,
            embedder=embedder,  # type: ignore[arg-type]
        )
    except Exception as e:
        selected = DiscoverySelectedPayload(
            discovery_id=discovery.discovery_id,
            document_id=None,
            decision="fetch_failed",
            rejection_reason=f"{type(e).__name__}: {e}",
        )
        event_id = emit_typed(
            investigation_id,
            selected,
            role="acquisition",
            policy_id=_POLICY_ID,
            events_dir=events_dir,
        )
        return DiscoveryPromotionResult(
            discovery_id=discovery.discovery_id,
            decision="fetch_failed",
            document_id=None,
            selected_event_id=event_id,
            rejection_reason=f"{type(e).__name__}: {e}",
            legal_gate_kind=verdict.gate_kind,
        )

    selected = DiscoverySelectedPayload(
        discovery_id=discovery.discovery_id,
        document_id=ingest_result.document_id,
        decision="ingested",
    )
    event_id = emit_typed(
        investigation_id,
        selected,
        role="acquisition",
        policy_id=_POLICY_ID,
        events_dir=events_dir,
    )
    return DiscoveryPromotionResult(
        discovery_id=discovery.discovery_id,
        decision="ingested",
        document_id=ingest_result.document_id,
        selected_event_id=event_id,
        rejection_reason=None,
        legal_gate_kind=verdict.gate_kind,
        chunks_written=ingest_result.chunks_written,
    )


__all__ = [
    "discover",
    "promote_discovery",
]