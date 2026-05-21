"""Budget cap for prompt-autoresearch iterations.

Per integration_autoresearch.md §5.4: cost runaway is the failure
mode. Hard caps per iteration and per run. Sprint 19 ratification
default is $5/run total."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


class BudgetExceeded(Exception):
    """Raised when an iteration would push spend past the run cap."""


@dataclass
class BudgetCap:
    """Track spend per iteration + total. Hard fail on cap breach."""

    total_cap_usd: Decimal = Decimal("5.00")
    per_iteration_cap_usd: Decimal = Decimal("0.30")
    spent_total_usd: Decimal = Decimal("0.00")
    iteration_count: int = 0
    cap_breaches: list[dict] = field(default_factory=list)

    def will_breach(self, projected_iteration_cost_usd: Decimal) -> bool:
        if projected_iteration_cost_usd > self.per_iteration_cap_usd:
            return True
        if self.spent_total_usd + projected_iteration_cost_usd > self.total_cap_usd:
            return True
        return False

    def record_iteration_cost(self, cost_usd: Decimal) -> None:
        """Record actual iteration cost. Raises BudgetExceeded if the
        new running total exceeds the cap."""
        if cost_usd > self.per_iteration_cap_usd:
            self.cap_breaches.append({
                "kind": "per_iteration",
                "iteration": self.iteration_count,
                "cost_usd": str(cost_usd),
            })
            raise BudgetExceeded(
                f"iteration {self.iteration_count} cost ${cost_usd} "
                f"exceeds per-iteration cap ${self.per_iteration_cap_usd}"
            )
        if self.spent_total_usd + cost_usd > self.total_cap_usd:
            self.cap_breaches.append({
                "kind": "total",
                "iteration": self.iteration_count,
                "cost_usd": str(cost_usd),
                "running_total": str(self.spent_total_usd + cost_usd),
            })
            raise BudgetExceeded(
                f"running total ${self.spent_total_usd + cost_usd} "
                f"exceeds run cap ${self.total_cap_usd}"
            )
        self.spent_total_usd += cost_usd
        self.iteration_count += 1
