"""Hard budget derived from crash-conservative journal state."""

from __future__ import annotations

from decimal import Decimal

from .journal import Journal, charged_cost


class HardBudget:
    def __init__(
        self,
        cap_usd: Decimal | str | int | float,
        journal: Journal,
        *,
        wedge_id: str | None = None,
    ) -> None:
        self._cap = Decimal(str(cap_usd))
        self._journal = journal
        self._wedge_id = wedge_id
        if self._cap < 0:
            raise ValueError("cap_usd must be non-negative")

    @property
    def cap_usd(self) -> Decimal:
        return self._cap

    @property
    def journal(self) -> Journal:
        return self._journal

    @property
    def wedge_id(self) -> str | None:
        return self._wedge_id

    @property
    def total_charged(self) -> Decimal:
        total = Decimal("0")
        for record in self._journal.replay().values():
            if self._wedge_id is not None and record.wedge_id != self._wedge_id:
                continue
            # Outstanding reservations, timeouts, and failures are conservative;
            # successful calls release the unused portion of their estimate.
            total += charged_cost(record)
        return total

    @property
    def spent(self) -> Decimal:
        return sum(
            (
                record.cost_usd
                for record in self._journal.replay().values()
                if record.cost_usd > 0
                and (self._wedge_id is None or record.wedge_id == self._wedge_id)
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
