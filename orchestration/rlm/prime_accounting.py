"""Copy settled owner attempts into Prime's audit ledger without a second charge."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .prime_ledger import PrimeLedger, ProjectionReceipt

if TYPE_CHECKING:
    from substrate.byot_usage.ledger import ByotUsageLedger


def drain_owner_attempt_projections(
    byot: ByotUsageLedger, prime: PrimeLedger, *, limit: int = 100
) -> tuple[ProjectionReceipt, ...]:
    """Project one bounded page, then acknowledge only its exact event digests.

    A crash after a Prime commit but before the BYOT acknowledgement leaves the
    event pending. Repeating this drain returns the same Prime receipt and does
    not reserve or charge again.
    """
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("limit must be an integer from 1 to 1000")
    receipts: list[ProjectionReceipt] = []
    for event in byot.pending_projection_events(after_sequence=0, limit=limit):
        receipt = prime.project_owner_attempt(event)
        byot.acknowledge_projection(event.sequence, event.digest)
        receipts.append(receipt)
    return tuple(receipts)
