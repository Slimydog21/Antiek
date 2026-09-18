"""Antiek-hosted agent compute capacity (managed CPU slider + ACU meter).

Doctrine: BYO Token + BYO Tools; NO BYO CPU by default. Antiek manages agent
compute and research traces; owners pick a monthly ACU budget. Token spend
stays on the BYOT usage ledger.

1 ACU = one investigation start (see ``acu_meter``). No fake billing.
"""

from .store import (
    CAPACITY_TIERS,
    CapacityEvaluation,
    ComputeCapacity,
    ensure_table,
    evaluate_capacity,
    get_capacity,
    set_capacity,
    tier_default_units,
)
from .acu_meter import (
    ACU_PER_INVESTIGATION_START,
    CAPACITY_WARN_HEADER,
    CapacityGateResult,
    gate_investigation_start,
    record_investigation_start_acu,
)

__all__ = [
    "ACU_PER_INVESTIGATION_START",
    "CAPACITY_TIERS",
    "CAPACITY_WARN_HEADER",
    "CapacityEvaluation",
    "CapacityGateResult",
    "ComputeCapacity",
    "ensure_table",
    "evaluate_capacity",
    "gate_investigation_start",
    "get_capacity",
    "record_investigation_start_acu",
    "set_capacity",
    "tier_default_units",
]
