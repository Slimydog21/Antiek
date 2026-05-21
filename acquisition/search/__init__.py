"""Discovery layer — sits upstream of the URL adapter.

Per `docs/integration_exa_browserbase.md` §3, the discovery layer
proposes URLs but does NOT write to the substrate graph. Promotion
to the graph (via `acquisition/urls/adapter.ingest_url`) is operator-
mediated and emitted as `DiscoverySelectedPayload`.

Module layout (Wedge 1 ships Exa only; future siblings extend here):

    acquisition/search/
        __init__.py                — this module
        exa/
            client.py              — typed Exa HTTP client (httpx)
            adapter.py             — discover() + promote_discovery()
            budget.py              — daily budget sidecar

Public surface re-exports the operator-facing names from the Exa
adapter for ergonomic import (`from acquisition.search import discover`).
"""

from __future__ import annotations

from .exa.adapter import (
    DiscoveryBudgetExceeded,
    DiscoveryPromotionResult,
    DiscoveryProposed,
    discover,
    promote_discovery,
)

__all__ = [
    "DiscoveryBudgetExceeded",
    "DiscoveryPromotionResult",
    "DiscoveryProposed",
    "discover",
    "promote_discovery",
]
