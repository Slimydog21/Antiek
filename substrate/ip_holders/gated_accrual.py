"""Gated-mass-ingest escrow accrual — the §9 gated revenue source (SPR-02 M6).

When the rights classifier (``acquisition.licenses_core.classify``) classes a
fetched work GATED for an in-copyright reason (a rights holder exists), this
module accrues escrow to a ``pre_onboarded`` ip_holder. It is a NEW sanctioned
revenue SOURCE for the escrow ledger — peer to Speak's contributor split, the
Read book/publisher escrow, and the per-second frame-attention border — and it
routes through the ONE low-level writer (``ip_holders.accrue_escrow``), never a
second escrow-balance writer (collision #3 / seam #3 invariant; see
``tests/test_seam_single_escrow_writer.py``).

Escrow ACCRUES only — it never disburses. ``payout.py`` / ``stripe_connect``
are not imported here; whether the publisher receives the money is the separate
``claim`` → Stripe Connect path, operator-gated on G2/G3. The accrual fires for
exactly the gated-in-copyright case and is a no-op for everything else:
``classify`` sets ``accrual_eligible=True`` only when the work gates AND a
rights holder exists, so a public-domain / open-licensed servable work (no
rights holder to pay) accrues nothing.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from . import accrue_escrow, create_pre_onboarded, list_all


def accrue_gated_escrow(
    con: Any,
    classification: Any,
    *,
    rights_holder_name: str,
    amount_usd: Decimal,
) -> str | None:
    """Accrue escrow for a GATED in-copyright work to its pre-onboarded rights
    holder. The thin seam a connector calls after classification.

    Refuses to accrue unless ``classification.accrual_eligible`` is True:
      - a public-domain / open-licensed (servable) work has NO rights holder to
        pay -> ``accrual_eligible=False`` -> returns None, accrues nothing;
      - a gated in-copyright work with a known rights holder ->
        ``accrual_eligible=True`` -> escrow accrues to the holder.

    Returns the ip_holder_id the escrow accrued to, or None when nothing
    accrued (not accrual-eligible). Idempotent on ``rights_holder_name`` so
    re-ingesting the same holder's works doesn't fan out duplicate accounts."""
    if not getattr(classification, "accrual_eligible", False):
        return None
    holder_id = _find_or_create_pre_onboarded(con, rights_holder_name)
    accrue_escrow(con, holder_id, amount_usd)
    return holder_id


def _find_or_create_pre_onboarded(con: Any, display_name: str) -> str:
    """Find a pre-onboarded holder by display name, or create one. Mirrors the
    book-ingest convention (``substrate.books.ingest.resolve_or_create_ip_holder``)
    so escrow accrual and book registration land on the SAME account."""
    for holder in list_all(con):
        if holder.display_name == display_name:
            return holder.ip_holder_id
    return create_pre_onboarded(con, display_name=display_name)
