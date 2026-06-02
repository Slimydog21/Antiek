"""Discovery adapter — Wedge 1 of the Exa & Browserbase integration.

Two entry points:

* ``discover(query=..., investigation_id=...)`` — calls the Exa client,
  checks the daily budget, emits one ``DiscoveryProposedPayload`` event
  per result, and returns a list of typed ``DiscoveryProposed`` objects
  for operator review. **No graph writes.**

* ``promote_discovery(discovery, investigation_id=...)`` — consults the
  legal gate, routes through ``acquisition/urls/adapter.ingest_url`` on
  Allowed, emits ``DiscoverySelectedPayload``. The single substrate-
  write seam is preserved at ``ingest_url``.

Spec: `docs/integration_exa_browserbase.md` §6. The promotion path is
the only code path that consults the legal gate (per §3 the gate
sits between discovery and ingestion).

What this module does NOT do:

* Does NOT call Exa's ``/contents``. That's Wedge 3 (PHASE 2).
* Does NOT auto-ingest. Every promotion is operator-mediated.
* Does NOT bypass the legal gate. Promotion that hits the gate's
  ``allowed=False`` verdict emits ``decision="rejected_by_legal_gate"``
  with no graph write.
"""

from __future__ import annotations

import hashlib
import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from urllib.parse import urlparse

# Repo root on path for direct invocation (matches the pattern used by
# acquisition/urls/adapter.py).
_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

# Tier allowlists live in substrate/constants.py per spec §6.6 —
# tier assignment is a substrate decision, not a search-API one.
# Import here so the adapter can consult them; never define them
# here.
from substrate.constants import (  # noqa: E402
    CURATED_NEWS_TIER_3 as _CURATED_NEWS_TIER_3,
)
from substrate.constants import (
    RESEARCH_HOSTS_TIER_2 as _RESEARCH_HOSTS_TIER_2,
)
from substrate.event_log import emit_typed  # noqa: E402
from substrate.legal_gate import LegalGate, default_legal_gate  # noqa: E402
from substrate.schemas.events import (  # noqa: E402
    DiscoveryProposedPayload,
    DiscoverySelectedPayload,
)

from .budget import check_and_reserve  # noqa: E402
from .cache import DEFAULT_TTL_SECONDS, cache_key, lookup, store  # noqa: E402
from .client import ExaClient, ExaSearchCategory, ExaSearchResult  # noqa: E402

_DISCOVERY_ID_PREFIX = "disc-exa-"


# ── Operator-facing types ─────────────────────────────────────────


@dataclass(frozen=True)
class DiscoveryProposed:
    """Python representation of a ``DiscoveryProposedPayload`` event,
    returned by ``discover(...)`` for operator review.

    The fields mirror the payload; the dataclass is the friendlier
    surface for operator-side code (avoids forcing callers to import
    the Pydantic model and call ``.model_dump()``).
    """

    discovery_id: str
    provider: str
    query: str
    url: str
    title: str | None
    published_date: str | None
    author: str | None
    relevance_score: float | None
    suggested_tier: int
    text_snippet_preview: str | None
    # Backward-compat read fallback. Per spec §14.7 the canonical
    # location is `provider_specific["response_id"]`; the top-level
    # mirror stays so callers reading v6-v8 events still see the
    # value. New emitters write to `provider_specific`; read paths
    # prefer it.
    provider_response_id: str | None
    cost_usd_estimate: float
    proposed_event_id: str | None
    # Spec §14.7 overflow bag — provider-shaped fields live here.
    # Defaults to {} on the runtime dataclass for ergonomic
    # construction in tests; the underlying payload's
    # `provider_specific` defaults the same.
    provider_specific: dict = field(default_factory=dict)


@dataclass(frozen=True)
class DiscoveryPromotionResult:
    """Result of ``promote_discovery(...)``. Mirrors the structure of
    ``DiscoverySelectedPayload`` plus the resulting ``IngestUrlResult``
    when ingestion ran.
    """

    discovery_id: str
    decision: str  # one of: ingested, rejected_by_legal_gate, rejected_by_operator, fetch_failed
    document_id: str | None
    selected_event_id: str | None
    rejection_reason: str | None
    legal_gate_kind: str
    chunks_written: int = 0


class DiscoveryBudgetExceeded(RuntimeError):
    """Raised when a ``discover(...)`` call would push today's Exa
    spend past ``EXA_DAILY_BUDGET_USD``. Per spec §6.7 there is NO
    silent fallback. The operator must wait or raise the cap."""


# ── Tier suggestion heuristic ─────────────────────────────────────


def suggest_tier(url: str, category: str | None = None) -> int:
    """Spec §6.6 heuristic.

    - Tier 1: primary source. NEVER auto-assigned; operator-only.
    - Tier 2: known-good research (arXiv, *.gov, *.edu, doi.org, *.ac.uk).
    - Tier 3: known-good news (curated allowlist).
    - Tier 4: general web (default).
    """
    if category == "research paper":
        return 2
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return 4
    if not host:
        return 4
    # Strip leading "www." for matching.
    if host.startswith("www."):
        host = host[4:]
    if host in _RESEARCH_HOSTS_TIER_2:
        return 2
    suffixes_tier_2 = (".gov", ".edu", ".ac.uk")
    if any(host.endswith(s) for s in suffixes_tier_2) or host == "doi.org":
        return 2
    if host in _CURATED_NEWS_TIER_3:
        return 3
    return 4


# ── Stable discovery id ───────────────────────────────────────────


def _discovery_id(url: str, investigation_id: str, query: str = "") -> str:
    """Stable handle for one proposal.

    Per spec §6.5 cross-query behavior: the SAME URL discovered via
    TWO different queries in the SAME investigation MUST produce
    TWO different `discovery_id`s. The formula at §6.2 was
    illustrative — the load-bearing semantic is "each gets its own
    DiscoveryProposed event (different discovery_id)." Including
    `query` in the hash satisfies that.

    For backward compatibility, the `query` parameter defaults to
    empty. Existing test callsites that compute discovery_id without
    a query (verifying within-investigation stability) still pass.
    """
    h = hashlib.sha256(
        f"{url}\x1f{investigation_id}\x1f{query}".encode()
    ).hexdigest()[:16]
    return f"{_DISCOVERY_ID_PREFIX}{h}"


# ── discover() ────────────────────────────────────────────────────


def discover(
    *,
    query: str,
    investigation_id: str,
    num_results: int = 10,
    category: ExaSearchCategory | None = None,
    include_domains: Iterable[str] | None = None,
    exclude_domains: Iterable[str] | None = None,
    start_published_date: str | None = None,
    end_published_date: str | None = None,
    client: ExaClient | None = None,
    daily_budget_usd: float | None = None,
    events_dir: str | None = None,
    db_path: str | None = None,
    use_cache: bool = True,
    cache_ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> list[DiscoveryProposed]:
    """Run an Exa search; emit DiscoveryProposed events; return the
    proposals for operator review.

    No graph writes happen here. Promotion to ingestion is a separate
    call to ``promote_discovery(...)``.

    Per spec §6.5 — same `(query, investigation_id, params)` within
    24h short-circuits to the cached proposal list. No re-emission of
    DiscoveryProposed events on cache hit (the first call's events
    are the audit trail). Cache lookup is best-effort; a missing
    substrate DB just falls through to the live Exa call.

    Per spec §6.7: pre-call budget check is mandatory. The check
    pre-reserves the call's optimistic cost; if the call returns
    fewer results than expected (or fails), the next call sees the
    optimistic state and may refuse early. The operator can adjust
    ``EXA_DAILY_BUDGET_USD`` upward to relax.

    Raises ``DiscoveryBudgetExceeded`` when the cap would be exceeded.
    Raises ``ExaClientError`` on Exa-side failures.
    """
    if not query.strip():
        raise ValueError("discover: empty query")
    if not investigation_id.strip():
        raise ValueError("discover: empty investigation_id")
    # Spec §14.1 — discovery events live in a separate JSONL dir from
    # substrate events. Lazy-import to avoid the
    # acquisition.search.__init__ → acquisition.search.exa.adapter
    # circular import.
    if events_dir is None:
        from acquisition.search import default_discovery_events_dir  # noqa: PLC0415
        events_dir = default_discovery_events_dir()

    # Per spec §6.5 cache check — runs BEFORE the budget reservation
    # so cache hits don't consume budget.
    if use_cache:
        resolved_db = db_path or _default_db_path_or_none()
        if resolved_db:
            ckey = cache_key(
                query=query,
                investigation_id=investigation_id,
                provider="exa",
                num_results=num_results,
                category=category,
                include_domains=list(include_domains) if include_domains else None,
                exclude_domains=list(exclude_domains) if exclude_domains else None,
                start_published_date=start_published_date,
                end_published_date=end_published_date,
            )
            cached = lookup(ckey, db_path=resolved_db)
            if cached is not None:
                return [_hydrate_proposed(d) for d in cached]

    # Per spec §6.7 — optimistic reservation BEFORE the call.
    from .client import COST_PER_SEARCH_USD  # local import; cheap, avoids cycles

    check_and_reserve(COST_PER_SEARCH_USD, cap_override=daily_budget_usd)

    cli = client or ExaClient()
    response = cli.search(
        query=query,
        num_results=num_results,
        category=category,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
        start_published_date=start_published_date,
        end_published_date=end_published_date,
    )

    proposals: list[DiscoveryProposed] = []
    for r in response.results:
        proposals.append(
            _emit_proposed(
                r,
                query=query,
                investigation_id=investigation_id,
                category=category,
                events_dir=events_dir,
            )
        )

    # Persist to cache on success — cache only valid results,
    # never errors.
    if use_cache:
        resolved_db = db_path or _default_db_path_or_none()
        if resolved_db and proposals:
            try:
                # Initialize schema on first use so the table exists.
                from substrate.graph import ensure_initialized
                ensure_initialized(resolved_db)
                store(
                    cache_key(
                        query=query,
                        investigation_id=investigation_id,
                        provider="exa",
                        num_results=num_results,
                        category=category,
                        include_domains=list(include_domains) if include_domains else None,
                        exclude_domains=list(exclude_domains) if exclude_domains else None,
                        start_published_date=start_published_date,
                        end_published_date=end_published_date,
                    ),
                    proposals=proposals,
                    query=query,
                    investigation_id=investigation_id,
                    provider="exa",
                    ttl_seconds=cache_ttl_seconds,
                    db_path=resolved_db,
                )
            except Exception:
                # Cache failures are non-fatal — we already have the
                # proposals to return. Log later when the substrate
                # has a logging convention; for now, suppress.
                pass

    return proposals


def _default_db_path_or_none() -> str | None:
    """Resolve the substrate DuckDB path if configured, else None.

    Tests that don't want cache touch the substrate set
    ``use_cache=False`` explicitly; production code paths inherit
    ``ANTIEK_DUCKDB_PATH`` resolution.
    """
    try:
        from substrate.graph import default_db_path
        return default_db_path()
    except Exception:
        return None


def _hydrate_proposed(d: dict) -> DiscoveryProposed:
    """Rebuild a DiscoveryProposed dataclass from a cached dict.

    Spec §14.7 read precedence: prefer ``provider_specific["response_id"]``
    over the top-level ``provider_response_id`` field. v6-v8 cached
    rows that pre-date provider_specific still resolve via the
    top-level fallback.
    """
    provider_specific = d.get("provider_specific") or {}
    response_id = (
        provider_specific.get("response_id")
        if isinstance(provider_specific, dict)
        else None
    )
    # Backward compat: if provider_specific didn't carry response_id,
    # fall back to the top-level field.
    if response_id is None:
        response_id = d.get("provider_response_id")
    return DiscoveryProposed(
        discovery_id=d["discovery_id"],
        provider=d.get("provider", "exa"),
        query=d.get("query", ""),
        url=d.get("url", ""),
        title=d.get("title"),
        published_date=d.get("published_date"),
        author=d.get("author"),
        relevance_score=d.get("relevance_score"),
        suggested_tier=int(d.get("suggested_tier", 4)),
        text_snippet_preview=d.get("text_snippet_preview"),
        provider_response_id=response_id,
        cost_usd_estimate=float(d.get("cost_usd_estimate") or 0.0),
        proposed_event_id=d.get("proposed_event_id"),
        provider_specific=(
            provider_specific if isinstance(provider_specific, dict) else {}
        ),
    )


def find_similar(
    *,
    url: str,
    investigation_id: str,
    num_results: int = 10,
    exclude_source_domain: bool = True,
    client: ExaClient | None = None,
    daily_budget_usd: float | None = None,
    events_dir: str | None = None,
) -> list[DiscoveryProposed]:
    """Spec §17.3 — findSimilar ships in Wedge 1.

    Each result is emitted as a ``DiscoveryProposed`` event with the
    originating ``url`` recorded in the ``query`` field. This is the
    same event shape — a single review surface handles both.
    """
    if not url.strip():
        raise ValueError("find_similar: empty url")
    if not investigation_id.strip():
        raise ValueError("find_similar: empty investigation_id")
    # Spec §14.1 — separate discovery events dir.
    if events_dir is None:
        from acquisition.search import default_discovery_events_dir  # noqa: PLC0415
        events_dir = default_discovery_events_dir()

    from .client import COST_PER_FIND_SIMILAR_USD

    check_and_reserve(COST_PER_FIND_SIMILAR_USD, cap_override=daily_budget_usd)

    cli = client or ExaClient()
    response = cli.find_similar(
        url=url,
        num_results=num_results,
        exclude_source_domain=exclude_source_domain,
    )
    proposals: list[DiscoveryProposed] = []
    for r in response.results:
        proposals.append(
            _emit_proposed(
                r,
                query=url,  # for findSimilar, the query IS the seed URL
                investigation_id=investigation_id,
                category=None,
                events_dir=events_dir,
            )
        )
    return proposals


def _emit_proposed(
    r: ExaSearchResult,
    *,
    query: str,
    investigation_id: str,
    category: str | None,
    events_dir: str | None,
) -> DiscoveryProposed:
    discovery_id = _discovery_id(r.url, investigation_id, query)
    tier = suggest_tier(r.url, category=category)
    # Spec §14.7 — Exa-specific provenance data lives in
    # provider_specific rather than as top-level fields. Today we
    # have one such field (response_id); future Exa-shaped data
    # (autoprompt_string, subpages, exa_filter, etc.) joins here
    # without bumping the schema. Top-level `provider_response_id`
    # stays for backward-compat reads of v6-v8 events.
    provider_specific: dict = {}
    if r.provider_response_id is not None:
        provider_specific["response_id"] = r.provider_response_id
    payload = DiscoveryProposedPayload(
        discovery_id=discovery_id,
        provider="exa",
        query=query,
        url=r.url,
        title=r.title,
        published_date=r.published_date,
        author=r.author,
        relevance_score=r.relevance_score,
        suggested_tier=tier,
        text_snippet_preview=r.text_snippet_preview,
        # Leave top-level None — the canonical write goes into
        # provider_specific. Read paths consult both (provider_specific
        # is preferred when present per `_hydrate_proposed`).
        provider_response_id=None,
        cost_usd_estimate=r.cost_usd_estimate,
        provider_specific=provider_specific,
    )
    event_id = emit_typed(
        investigation_id,
        payload,
        role="acquisition",
        policy_id="acquisition/search/exa",
        events_dir=events_dir,
    )
    return DiscoveryProposed(
        discovery_id=discovery_id,
        provider="exa",
        query=query,
        url=r.url,
        title=r.title,
        published_date=r.published_date,
        author=r.author,
        relevance_score=r.relevance_score,
        suggested_tier=tier,
        text_snippet_preview=r.text_snippet_preview,
        # Operator-facing dataclass exposes the response_id as a
        # top-level convenience (read from provider_specific) AND
        # carries the full bag for any caller that wants other
        # Exa-shaped data.
        provider_response_id=r.provider_response_id,
        cost_usd_estimate=r.cost_usd_estimate,
        proposed_event_id=event_id,
        provider_specific=provider_specific,
    )


# ── promote_discovery() ───────────────────────────────────────────


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
    """Promote a prior discovery to ingestion.

    Flow per spec §3 (the single architectural decision):

      1. Consult the legal gate (the seam at
         ``substrate/legal_gate``). On ``allowed=False``, emit a
         ``DiscoverySelectedPayload{decision="rejected_by_legal_gate"}``
         with no graph write and return.
      2. On Allowed: call ``acquisition/urls/adapter.ingest_url``,
         which is the single substrate-write seam for URL-sourced
         documents. ``url_doc_id`` deduplicates downstream — re-
         promoting an already-ingested discovery is idempotent at
         the graph level.
      3. Emit ``DiscoverySelectedPayload{decision="ingested"}`` with
         the resulting ``document_id``.

    Per spec §6.8: this is the only function that takes a discovery
    from proposed-state to ingestion. There is no auto-promote path.
    """
    # Spec §14.1 — separate discovery events dir.
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
            policy_id="acquisition/search/exa",
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

    # Allowed — route through ingest_url. Import locally so this
    # adapter doesn't pull in the URL fetch stack on import (cheap
    # for tests that only exercise discover()).
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
        # Fetch / extraction / DB error — emit fetch_failed so the
        # trajectory shows we tried. Don't swallow the underlying
        # error; surface to the caller via the typed result.
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
            policy_id="acquisition/search/exa",
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
        policy_id="acquisition/search/exa",
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


def reject_discovery(
    discovery: DiscoveryProposed,
    *,
    investigation_id: str,
    reason: str | None = None,
    events_dir: str | None = None,
) -> DiscoveryPromotionResult:
    """Operator-side dismissal of a proposal without ingestion.

    Emits ``DiscoverySelectedPayload{decision="rejected_by_operator"}``
    so the audit trail records the operator considered and declined
    the proposal. The trajectory log shows the full review history
    even when nothing was ingested.
    """
    # Spec §14.1 — separate discovery events dir.
    if events_dir is None:
        from acquisition.search import default_discovery_events_dir  # noqa: PLC0415
        events_dir = default_discovery_events_dir()

    selected = DiscoverySelectedPayload(
        discovery_id=discovery.discovery_id,
        document_id=None,
        decision="rejected_by_operator",
        rejection_reason=reason,
    )
    event_id = emit_typed(
        investigation_id,
        selected,
        role="acquisition",
        policy_id="acquisition/search/exa",
        events_dir=events_dir,
    )
    return DiscoveryPromotionResult(
        discovery_id=discovery.discovery_id,
        decision="rejected_by_operator",
        document_id=None,
        selected_event_id=event_id,
        rejection_reason=reason,
        legal_gate_kind="placeholder",  # gate not consulted on operator-reject
    )


__all__ = [
    "DiscoveryBudgetExceeded",
    "DiscoveryPromotionResult",
    "DiscoveryProposed",
    "discover",
    "find_similar",
    "promote_discovery",
    "reject_discovery",
    "suggest_tier",
]
