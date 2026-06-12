"""Parallel Search provider — DRW gather (SPR-DRL-08)."""

from __future__ import annotations

from .adapter import discover, promote_discovery
from .client import (
    COST_PER_SEARCH_USD,
    ParallelClient,
    ParallelClientError,
    ParallelSearchResult,
)

__all__ = [
    "COST_PER_SEARCH_USD",
    "ParallelClient",
    "ParallelClientError",
    "ParallelSearchResult",
    "discover",
    "promote_discovery",
]