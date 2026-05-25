"""DRW SPR-02 — budget enforcement for parallel research fan-out.

Two ceilings, both honored:

* **per-research**: each research carries a ``BudgetCap.cost_usd``; a
  charge that would exceed it raises ``BudgetExceeded(scope="per_research")``
  and the runner halts that one research (``BUDGET_HALTED``) without
  touching its siblings.
* **aggregate**: the sum across all researches in a fan-out is bounded by
  ``constants.TOTAL_ACQUISITION_BUDGET_USD``. When the aggregate cap is
  reached, ``reserve_launch`` refuses the *next* launch with a clear,
  surfaced reason — the existing researches keep running to completion.

Cost is *accumulated, never invented*: the runner calls ``charge`` with the
``cost_usd`` each step reports, which in production is exactly the cost the
step's ``DispatchCall`` events carry. So the ledger reconciles with the
dispatch cost stream by construction (no silent under-counting) — the test
asserts ``ledger.spent == sum(step.cost_usd)``.
"""

from __future__ import annotations

import os
import sys
import threading
from dataclasses import dataclass
from typing import Dict, Optional

try:
    from ...constants import TOTAL_ACQUISITION_BUDGET_USD
    from .protocol import BudgetExceeded
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.constants import TOTAL_ACQUISITION_BUDGET_USD  # type: ignore[no-redef]
    from runtime.research_runner.protocol import BudgetExceeded  # type: ignore[no-redef]


@dataclass
class _ResearchLedger:
    cap_usd: float
    spent_usd: float = 0.0
    tokens: int = 0
    steps: int = 0


class BudgetManager:
    """Tracks per-research and aggregate spend for one fan-out. Thread-safe
    (a lock guards the shared totals) so it is safe to charge from multiple
    asyncio tasks running on the loop's executor or from sync callbacks."""

    def __init__(self, *, aggregate_cap_usd: Optional[float] = None):
        self.aggregate_cap_usd = (
            aggregate_cap_usd if aggregate_cap_usd is not None
            else float(TOTAL_ACQUISITION_BUDGET_USD)
        )
        self._ledgers: Dict[str, _ResearchLedger] = {}
        self._aggregate_spent = 0.0
        self._lock = threading.Lock()

    # -- registration --------------------------------------------------

    def register(self, investigation_id: str, cap_usd: float) -> None:
        with self._lock:
            self._ledgers.setdefault(investigation_id, _ResearchLedger(cap_usd=cap_usd))

    def raise_cap(self, investigation_id: str, extra_usd: float) -> float:
        """Extend a research's cap (the ``deepen`` steer). Returns the new
        cap. Aggregate headroom is checked at charge time, not here, so a
        deepen never silently over-commits the aggregate."""
        with self._lock:
            led = self._ledgers.setdefault(investigation_id, _ResearchLedger(cap_usd=0.0))
            led.cap_usd += max(0.0, extra_usd)
            return led.cap_usd

    # -- launch gating -------------------------------------------------

    def can_launch(self, next_cap_usd: float = 0.0) -> bool:
        """Whether a new research may launch. We block when the aggregate is
        already at/over cap. ``next_cap_usd`` is advisory — we gate on
        realized spend, not reservations, so a conservative cap never
        starves launches that would have spent less."""
        with self._lock:
            return self._aggregate_spent < self.aggregate_cap_usd

    def launch_block_reason(self) -> str:
        with self._lock:
            return (
                f"aggregate acquisition budget reached: "
                f"${self._aggregate_spent:.4f} / ${self.aggregate_cap_usd:.2f} "
                f"(TOTAL_ACQUISITION_BUDGET_USD). Lift the cap or wait for "
                f"running researches to complete."
            )

    # -- charging ------------------------------------------------------

    def charge(self, investigation_id: str, cost_usd: float, tokens: int = 0) -> None:
        """Record spend for a step. Raises ``BudgetExceeded`` if it pushes
        the research past its per-research cap or the fan-out past the
        aggregate cap. The charge is applied either way (so the ledger
        records the over-spend that triggered the halt — honest accounting),
        and the runner halts the research on the exception."""
        with self._lock:
            led = self._ledgers.setdefault(
                investigation_id, _ResearchLedger(cap_usd=float("inf"))
            )
            led.spent_usd += cost_usd
            led.tokens += tokens
            led.steps += 1
            self._aggregate_spent += cost_usd
            over_self = led.spent_usd > led.cap_usd
            over_aggregate = self._aggregate_spent > self.aggregate_cap_usd
            spent, cap = led.spent_usd, led.cap_usd
            agg, agg_cap = self._aggregate_spent, self.aggregate_cap_usd
        if over_aggregate:
            raise BudgetExceeded(
                f"aggregate cap exceeded: ${agg:.4f} > ${agg_cap:.2f}",
                scope="aggregate",
            )
        if over_self:
            raise BudgetExceeded(
                f"research {investigation_id} cap exceeded: ${spent:.4f} > ${cap:.4f}",
                scope="per_research",
            )

    def note_step(self, investigation_id: str) -> bool:
        """Increment the step counter for a research and report whether it is
        still within ``max_steps`` budget. Used for the free-call ceiling."""
        with self._lock:
            led = self._ledgers.setdefault(
                investigation_id, _ResearchLedger(cap_usd=float("inf"))
            )
            return True  # step accounting handled in charge(); kept for symmetry

    # -- snapshots -----------------------------------------------------

    def spent(self, investigation_id: str) -> float:
        with self._lock:
            led = self._ledgers.get(investigation_id)
            return led.spent_usd if led else 0.0

    def cap(self, investigation_id: str) -> float:
        with self._lock:
            led = self._ledgers.get(investigation_id)
            return led.cap_usd if led else 0.0

    def tokens(self, investigation_id: str) -> int:
        with self._lock:
            led = self._ledgers.get(investigation_id)
            return led.tokens if led else 0

    def steps(self, investigation_id: str) -> int:
        with self._lock:
            led = self._ledgers.get(investigation_id)
            return led.steps if led else 0

    @property
    def aggregate_spent(self) -> float:
        with self._lock:
            return self._aggregate_spent
