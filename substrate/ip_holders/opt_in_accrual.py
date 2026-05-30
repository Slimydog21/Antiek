"""Publisher opt-in escrow accrual — the §9.10 servable-by-grant revenue source.

When a publisher submits their OWN catalog with a valid serving grant, the
opt-in intake lane (``acquisition.opt_in.intake``) ingests the work servable
(``opt_in_licensed``) and seeds escrow to the publisher's pre-onboarded
``ip_holder`` at intake — the acknowledgement that a servable opt-in work begins
accruing to its holder. This module is the SUBSTRATE-LAYER seam the intake lane
calls so the escrow write stays under ``substrate/`` with the other sanctioned
revenue sources (Speak's contributor split, Read's book/publisher escrow, the
per-second frame-attention border, the gated-mass-ingest accrual) — NOT a
cross-layer ``accrue_escrow`` call reaching out of ``acquisition/``.

It is a NEW sanctioned revenue SOURCE for the escrow ledger and routes through
the ONE low-level writer (``ip_holders.accrue_escrow``), never a second
escrow-balance writer (collision #3 / seam #3 invariant; see
``tests/test_seam_single_escrow_writer.py``). This module is added to
``_SANCTIONED_ESCROW_CALLERS`` there — the seam's intended path for a new
sanctioned source.

Escrow ACCRUES only — it never disburses. ``payout.py`` / ``stripe_connect``
are not imported here; whether the publisher receives the money is the separate
``claim`` -> Stripe Connect path, operator-gated on G2/G3. The caller passes a
connection from ``runtime.db_lock.connect_write`` (the single-writer lock) so
this participates in the writer transaction and never opens a second connection.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from . import accrue_escrow


def accrue_opt_in_escrow(
    con: Any, ip_holder_id: str, amount_usd: Decimal
) -> None:
    """Accrue the opt-in intake seed to a granted publisher's holder.

    The thin seam ``acquisition.opt_in.intake.ingest_entry`` calls for a
    SERVABLE opt-in work. Delegates to the ONE low-level writer
    (``ip_holders.accrue_escrow``), which rejects a non-positive amount — so the
    intake lane's positive seed contract is enforced at the writer, not duplicated
    here. Accrual only; disbursement stays operator-gated (G2/G3)."""
    accrue_escrow(con, ip_holder_id, amount_usd)


__all__ = ["accrue_opt_in_escrow"]
