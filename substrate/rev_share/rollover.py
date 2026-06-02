"""Below-threshold rollover ledger (Sprint 23-24).

Per master-spec §9.5:
- $10 minimum payout threshold
- Below-threshold balances roll over to next month
- 12-month rollover ceiling; at month 9 a notice goes out;
  at month 12 the balance forfeits to the platform residual
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import UTC, datetime

MINIMUM_PAYOUT_USD_CENTS = 1000  # §9.5 — $10
ROLLOVER_CEILING_MONTHS = 12
NOTICE_MONTH = 9


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class RolloverState(str, enum.Enum):
    ACCRUING = "accruing"
    NOTICE_SENT = "notice_sent"
    SETTLED = "settled"
    FORFEITED = "forfeited"


@dataclass
class RolloverEntry:
    """One creator's rolling balance."""

    recipient_ref: str
    balance_cents: int = 0
    accrual_started_month: int | None = None  # months-since-epoch index
    state: RolloverState = RolloverState.ACCRUING
    last_event_at: str = field(default_factory=_now_iso)
    history: list[tuple[str, str, int]] = field(default_factory=list)


@dataclass
class RolloverLedger:
    """Aggregates per-recipient rolling balances."""

    entries: dict[str, RolloverEntry] = field(default_factory=dict)

    def entry_for(self, recipient_ref: str) -> RolloverEntry:
        if recipient_ref not in self.entries:
            self.entries[recipient_ref] = RolloverEntry(recipient_ref=recipient_ref)
        return self.entries[recipient_ref]


def accrue(
    ledger: RolloverLedger,
    *,
    recipient_ref: str,
    cents: int,
    current_month_index: int,
) -> RolloverEntry:
    """Add cents to a recipient's rolling balance.

    `current_month_index` is months-since-epoch (any monotonic int that
    increments by 1 each month — caller's choice of epoch)."""
    entry = ledger.entry_for(recipient_ref)
    if entry.accrual_started_month is None:
        entry.accrual_started_month = current_month_index
    entry.balance_cents += cents
    entry.history.append((_now_iso(), "accrue", cents))
    entry.last_event_at = _now_iso()
    return entry


def settle_or_rollover(
    ledger: RolloverLedger,
    *,
    recipient_ref: str,
    current_month_index: int,
) -> tuple[RolloverState, int]:
    """Evaluate at month-close: settle, roll over, notify, or forfeit.

    Returns (new_state, settled_cents). settled_cents > 0 only when
    the balance crossed the §9.5 minimum and we routed it; or when
    the balance forfeited (settled_cents = balance going to platform).
    """
    entry = ledger.entry_for(recipient_ref)
    months_held = 0
    if entry.accrual_started_month is not None:
        months_held = current_month_index - entry.accrual_started_month

    if entry.balance_cents >= MINIMUM_PAYOUT_USD_CENTS:
        settled = entry.balance_cents
        entry.balance_cents = 0
        entry.state = RolloverState.SETTLED
        entry.accrual_started_month = None
        entry.history.append((_now_iso(), "settle", settled))
        entry.last_event_at = _now_iso()
        return (RolloverState.SETTLED, settled)

    if months_held >= ROLLOVER_CEILING_MONTHS:
        forfeited = entry.balance_cents
        entry.balance_cents = 0
        entry.state = RolloverState.FORFEITED
        entry.accrual_started_month = None
        entry.history.append((_now_iso(), "forfeit", forfeited))
        entry.last_event_at = _now_iso()
        return (RolloverState.FORFEITED, forfeited)

    if months_held >= NOTICE_MONTH and entry.state == RolloverState.ACCRUING:
        entry.state = RolloverState.NOTICE_SENT
        entry.history.append((_now_iso(), "notice", entry.balance_cents))
        entry.last_event_at = _now_iso()

    return (entry.state, 0)


def is_forfeitable(entry: RolloverEntry, current_month_index: int) -> bool:
    if entry.accrual_started_month is None:
        return False
    if entry.balance_cents >= MINIMUM_PAYOUT_USD_CENTS:
        return False
    return (current_month_index - entry.accrual_started_month) >= ROLLOVER_CEILING_MONTHS
