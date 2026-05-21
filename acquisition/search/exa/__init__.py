"""Exa search provider — Wedge 1 of the Exa & Browserbase integration spec.

See `docs/integration_exa_browserbase.md` §6.
"""

from __future__ import annotations

from .adapter import (
    DiscoveryBudgetExceeded,
    DiscoveryPromotionResult,
    DiscoveryProposed,
    discover,
    find_similar,
    promote_discovery,
    reject_discovery,
    suggest_tier,
)
from .budget import DEFAULT_DAILY_BUDGET_USD, BudgetState
from .client import ExaClient, ExaClientError, ExaSearchCategory, ExaSearchResult

__all__ = [
    "BudgetState",
    "DEFAULT_DAILY_BUDGET_USD",
    "DiscoveryBudgetExceeded",
    "DiscoveryPromotionResult",
    "DiscoveryProposed",
    "ExaClient",
    "ExaClientError",
    "ExaSearchCategory",
    "ExaSearchResult",
    "discover",
    "find_similar",
    "promote_discovery",
    "reject_discovery",
    "suggest_tier",
]
