"""Hard-budget enforcement from the append-only journal.

The budget is a derived view of the journal — it never stores its own
state.  ``spent`` and ``reserved`` are computed by replaying the
journal on every call, so a crash that truncates the journal
automatically reduces the apparent spend.

Cap formula (documented here per Defensibility rigor):

    available = cap_usd - spent - reserved

where:

* ``spent`` = sum of cost_usd for all completed (non-timeout) calls
* ``reserved`` = sum of cost_usd for all timeout calls
  (conservative: the provider may have billed after the client
  stopped waiting, so the full reservation is consumed)

A new call may start only when ``available >= 0``.  Property tests
in the test file prove this invariant for arbitrary cost sequences.
"""

from __future__ import annotations

from decimal import Decimal

from .journal import Journal


class HardBudget:
    """Budget enforcement derived from the journal.

    ``cap_usd`` is the approved hard ceiling.  ``journal`` is the
    append-only source of truth for all realized spend.
    """

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

    def _totals(self) -> tuple[Decimal, Decimal]:
        """Compute (spent, reserved) from current journal state.

        * ``spent`` = sum of cost_usd for all records (ok + error)
        * ``reserved`` = sum of cost_usd for timeout records

        The total charged is ``spent + reserved`` — a timeout's full
        cost is reserved because we cannot know whether the provider
        billed after the client stopped waiting.
        """
        records = self._journal.replay()
        spent = Decimal("0")
        reserved = Decimal("0")
        for rec in records.values():
            if rec.status == "timeout":
                reserved += rec.cost_usd
            else:
                spent += rec.cost_usd
        return spent, reserved

    @property
    def spent(self) -> Decimal:
        """Total USD spent on completed (non-timeout) calls."""
        return self._totals()[0]

    @property
    def reserved(self) -> Decimal:
        """Total USD reserved for timeout calls."""
        return self._totals()[1]

    @property
    def total_charged(self) -> Decimal:
        """Spent + reserved — the full amount consumed against the cap."""
        s, r = self._totals()
        return s + r

    @property
    def available(self) -> Decimal:
        """Remaining budget: cap - spent - reserved."""
        return self._cap - self.total_charged

    def can_start(self, estimated_cost: Decimal | str | int | float) -> bool:
        """Check whether a new call with the given estimated cost fits.

        Returns ``True`` if ``spent + reserved + estimated_cost <= cap``.
        """
        est = Decimal(str(estimated_cost))
        return self._cap >= self.total_charged + est
