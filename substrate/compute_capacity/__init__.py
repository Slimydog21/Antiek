"""Antiek-hosted agent compute capacity (managed CPU slider).

Doctrine (vision map pillar 3): BYO Token + BYO Tools; NO BYO CPU by default.
Antiek manages agent compute and research traces; the owner picks a monthly
capacity tier / unit budget for a predictable bill. Token spend stays on the
BYOT usage ledger — this module is *compute quota*, not LLM cents.

Honesty: used units stay ``unmetered`` until a real meter exists. No fake
billing. Enforcement defaults OFF (soft/hard are flag-gated stubs).
"""

from .store import (
    CAPACITY_TIERS,
    ComputeCapacity,
    CapacityEvaluation,
    ensure_table,
    evaluate_capacity,
    get_capacity,
    set_capacity,
    tier_default_units,
)

__all__ = [
    "CAPACITY_TIERS",
    "ComputeCapacity",
    "CapacityEvaluation",
    "ensure_table",
    "evaluate_capacity",
    "get_capacity",
    "set_capacity",
    "tier_default_units",
]
