"""Hard budget derived from crash-conservative journal state."""

from __future__ import annotations

from decimal import Decimal

from .journal import Journal


class HardBudget:
    def __init__(self, cap_usd: Decimal | str | int | float, journal: Journal) -> None:
        self._cap = Decimal(str(cap_usd))
        self._journal = journal
        if self._cap < 0:
            raise ValueError("cap_usd must be non-negative")

    @property
    def cap_usd(self) -> Decimal:
        return self._cap

    @property
    def journal(self) -> Journal:
        return self._journal

    @property
    def total_charged(self) -> Decimal:
        total = Decimal("0")
        for record in self._journal.replay().values():
            # Outstanding reservations, timeouts, and failures are conservatively
            # charged at the reservation. Successful calls use at least that amount:
            # underestimation must never make the approved ceiling porous.
            total += (
                record.cost_usd
                if record.status == "ok"
                else max(record.reserved_usd, record.cost_usd)
            )
        return total

    @property
    def spent(self) -> Decimal:
        return sum(
            (
                record.cost_usd
                for record in self._journal.replay().values()
                if record.status == "ok"
            ),
            Decimal("0"),
        )

    @property
    def reserved(self) -> Decimal:
        return self.total_charged - self.spent

    @property
    def available(self) -> Decimal:
        return self._cap - self.total_charged

    def can_start(self, estimated_cost: Decimal | str | int | float) -> bool:
        estimate = Decimal(str(estimated_cost))
        if estimate < 0:
            raise ValueError("estimated_cost must be non-negative")
        return self.total_charged + estimate <= self._cap
