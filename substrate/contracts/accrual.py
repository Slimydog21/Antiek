"""Accrual contract — the single shape that reaches escrow (seam #3).

The four-workflow stack has two attribution concerns, deliberately kept
separate:

* ``ad_inventory/attribution.py`` — contribution weighting (split A/B/C).
* ``marketplace_metrics/attribution.py`` — impression → ip_holder attribution.

The real risk is never "two attribution modules"; it is **two writers to
escrow**. So this contract names the single shape both concerns emit, and the
decision record pins the single escrow *writer*:
``marketplace_metrics/publisher_escrow.py`` (seam #3).

**Accrual ≠ disbursement.** Money accrues into per-ip-holder escrow from day
one — even with zero buyers, in which case the amount is honestly ``0`` and the
share is still recorded (no fictional balances; verified against
``substrate/speak/contributor.py`` ``accrue_contributions`` L209-223). Money
only *leaves* escrow via a disbursement path that is hard-gated on **G2**
(lawyer review) and **G3** (publisher opt-in). The contract carries
``disbursable`` and fixes it ``False`` — there is no field a producer can set
to make an accrual disbursable; that is a gate decision, not a data flag.

Canonical unit is **integer cents** — the single escrow writer's unit
(``publisher_escrow.compute_publisher_escrow`` works in cents, verified
L53-59). The Speak path quantizes its ``Decimal`` USD to cents at the escrow
boundary, so both concerns converge on one integer wire shape (avoids float
drift and the Decimal-in-TypeScript problem).
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

# Which attribution concern produced the accrual. Both emit this same shape.
AccrualSource = Literal["publisher_impression", "speak_contribution"]


class AccrualContract(BaseModel):
    """One accrual line as the single escrow writer consumes it. A
    ``share_fraction`` is present for contributor splits and ``None`` for
    direct publisher-impression accrual. ``slop_gated`` lines accrue ``0`` —
    slop does not earn (≤0.70 rubric)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    accrual_id: str
    source: AccrualSource
    # every accrual targets an ip_holder (even null, before claim/mapping).
    ip_holder_id: Optional[str] = None
    # impression_ref (publisher) or interview_id (speak) — the originating ref.
    source_ref: str
    # integer cents; the single escrow writer's unit. Zero-buyer safe: 0 is a
    # real, honest balance, not a missing one.
    amount_cents: int = 0
    # contributor split fraction in [0, 1]; None for publisher-impression.
    share_fraction: Optional[float] = None
    slop_gated: bool = False
    # accrual is never disbursable at the data layer — disbursement is a
    # G2+G3 gate decision, not a producer-settable flag.
    disbursable: Literal[False] = False
