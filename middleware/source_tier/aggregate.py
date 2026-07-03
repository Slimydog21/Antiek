"""Multi-source tier aggregation (Researchmaxx spec §C.4).

The naive ``min(t)`` aggregation lets a single high-tier source override
multiple contradicting lower-tier sources. The correct rule:

    effective_tier = min t such that at least k sources support the
                     claim at tier ≤ t

With ``k = TIER_AGGREGATE_K`` (default 2 from ``substrate.constants``),
this enforces "two independent sources at the same tier or better." A
claim supported by a single Tier 1 source and three Tier 3 sources gets
effective tier 3 — the level at which it has redundant support — not 1.

Pure function — no DB, no LLM. The DB-touching helpers
(``_tiers_for_chunks``, ``_tiers_for_edges`` in the Researchmaxx source)
are deferred: the ``chunks_effective_tier`` view has no inline consumer
yet (documented YAGNI hold in ``substrate/graph/schema.py``).
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from collections.abc import Iterable

try:
    from ...constants import TIER_AGGREGATE_K, TIER_HIGHEST, TIER_LOWEST
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.constants import (  # type: ignore[no-redef]
        TIER_AGGREGATE_K,
        TIER_HIGHEST,
        TIER_LOWEST,
    )


def effective_tier(tiers: Iterable[int], k: int = TIER_AGGREGATE_K) -> int | None:
    """Lowest ``t`` in [TIER_HIGHEST, TIER_LOWEST] such that at least
    ``k`` sources are at tier ≤ ``t``.

    Returns None if no such t exists — i.e., fewer than ``k`` sources
    total. Tests:

        effective_tier([1])             → None   (one source; can't meet k=2)
        effective_tier([1, 1])          → 1
        effective_tier([1, 3, 3, 3], 2) → 3      (Tier 3 cohort needed)
        effective_tier([2, 2], 2)       → 2
        effective_tier([5, 5, 5], 2)    → 5
    """
    tier_list = list(tiers)
    if len(tier_list) < k:
        return None
    counts = Counter(tier_list)
    running = 0
    for t in range(TIER_HIGHEST, TIER_LOWEST + 1):
        running += counts.get(t, 0)
        if running >= k:
            return t
    return None
