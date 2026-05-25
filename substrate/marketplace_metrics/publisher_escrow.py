"""Publisher escrow accrual + claim rate.

Per Sprint 25+ doc §2 marketplace metrics: 'publisher escrow
accrual + claim rate'. Tracks the §9.10 publisher lifecycle:
pre_onboarded → invited → claimed | opted_out. Claim rate is the
key health signal — if the Kalshi-pattern notification template is
working, claim rate should rise over time.

The substrate ip_holders module owns the state machine; this module
aggregates over its rows.

**Concern + single-writer rule (seam #3).** This module is the escrow
**reporting / aggregation** surface — ``compute_publisher_escrow`` *reads*
publisher rows and accruals and returns a :class:`PublisherEscrowReport`. It is
read-only; it does **not** write escrow.

The seam-#3 collision the four specs left open is "two attribution.py files →
who writes escrow?" The load-bearing fix is single-writer discipline on the
escrow *balance*, mirroring the DuckDB single-writer invariant. The single
escrow-balance writer is ``substrate/ip_holders/__init__.py::accrue_escrow``
(the only ``SET escrow_balance_usd = …`` statement in the tree), reached today
only from ``substrate/speak/contributor.py::accrue_contributions``. Both
attribution concerns (``ad_inventory/attribution.py`` weighting,
``marketplace_metrics`` impression→ip_holder) feed the single
``AccrualContract`` shape (``substrate/contracts/accrual.py``); neither writes
escrow directly. Accrual ≠ disbursement — money leaves escrow only via a path
hard-gated on G2 (lawyer review) + G3 (publisher opt-in).

Naming nuance (honesty, rigor #4): ``docs/decisions/tech-stack-ledger.md`` and
the master spec name *this file* the "single escrow writer." In the live code
this file does not write escrow — it reports it; the actual single writer is
``ip_holders.accrue_escrow``. The invariant the ledger means (exactly one
escrow-balance writer) holds and is the one the guard test enforces. See
``tests/test_seam_single_escrow_writer.py`` and the SPR-03 handoff packet's
open-questions section.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional


@dataclass(frozen=True)
class PublisherStatusCounts:
    pre_onboarded: int = 0
    invited: int = 0
    claimed: int = 0
    opted_out: int = 0

    @property
    def total(self) -> int:
        return self.pre_onboarded + self.invited + self.claimed + self.opted_out

    @property
    def claim_rate(self) -> float:
        """claimed / (invited + claimed + opted_out) — denominator
        excludes pre_onboarded because they were never given the
        choice; including them would dilute the signal."""
        decided = self.invited + self.claimed + self.opted_out
        return (self.claimed / decided) if decided > 0 else 0.0

    @property
    def opt_out_rate(self) -> float:
        decided = self.invited + self.claimed + self.opted_out
        return (self.opted_out / decided) if decided > 0 else 0.0


@dataclass(frozen=True)
class PublisherEscrowReport:
    status_counts: PublisherStatusCounts
    total_escrow_accrued_cents: int
    total_escrow_paid_cents: int
    unclaimed_escrow_cents: int  # accrued but publisher hasn't claimed yet
    publishers_with_nontrivial_accrual: int  # accrual ≥ $10 threshold


def compute_publisher_escrow(
    *,
    publisher_status_rows: Iterable[tuple[str, str]],  # (ip_holder_id, status)
    publisher_accrual_cents: dict[str, int],  # ip_holder_id → accrued cents
    publisher_paid_cents: dict[str, int],  # ip_holder_id → paid cents
    nontrivial_threshold_cents: int = 1_000,  # $10 per §9.5
) -> PublisherEscrowReport:
    counts = {"pre_onboarded": 0, "invited": 0, "claimed": 0, "opted_out": 0}
    claimed_set: set[str] = set()
    for ip_id, status in publisher_status_rows:
        if status in counts:
            counts[status] += 1
        if status == "claimed":
            claimed_set.add(ip_id)

    total_accrued = sum(publisher_accrual_cents.values())
    total_paid = sum(publisher_paid_cents.values())

    # Unclaimed escrow = accrual for ip_holders not yet in 'claimed'.
    unclaimed = sum(
        cents for ip_id, cents in publisher_accrual_cents.items()
        if ip_id not in claimed_set
    )

    nontrivial = sum(
        1 for cents in publisher_accrual_cents.values()
        if cents >= nontrivial_threshold_cents
    )

    return PublisherEscrowReport(
        status_counts=PublisherStatusCounts(**counts),
        total_escrow_accrued_cents=total_accrued,
        total_escrow_paid_cents=total_paid,
        unclaimed_escrow_cents=unclaimed,
        publishers_with_nontrivial_accrual=nontrivial,
    )
