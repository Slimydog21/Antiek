"""Rank 0.1 fill settlement — settled cents ONLY behind legal + pricing gates.

``decide_fills`` always persists ``unpriced`` / $0 (a render decision, not a
bill). The sole authority that may flip a row to ``settled`` is
``settle_fill_decision``, which **denies** settlement unless:

1. ``legal_gate_passed`` is True (Rank 0.2 / advertiser activate invariant)
2. ``pricing_authority_ref`` is a non-empty operator/billing reference
3. ``revenue_usd_cents > 0`` (never invent; never settle at $0 as "priced")

House-only fill snapshots cannot be settled (library promo is not a bill).

Cited by: docs/decisions/applovin-website-mvp-attribution-ledger-2026-09-17.md
Ranks: docs/specs/ad-v1-scalable-2026-08-12.md Rank 0.1 / 0.2
"""

from __future__ import annotations

import json
from typing import Any

from substrate.ad_inventory.fill_decisions import FillDecision, _from_row, ensure_table
from substrate.ad_inventory.rank0_honesty import assert_settlement_allowed


class FillSettlementError(ValueError):
    """Settlement refused — gates missing or invariant violated."""


def _fills_are_house_only(fills_json: str) -> bool:
    try:
        fills = json.loads(fills_json)
    except (TypeError, json.JSONDecodeError):
        return False
    if not fills:
        return True
    return all(str(f.get("kind", "")) == "house" for f in fills)


def settle_fill_decision(
    con: Any,
    *,
    decision_id: str,
    revenue_usd_cents: int,
    legal_gate_passed: bool,
    pricing_authority_ref: str,
    advertiser_id: str | None = None,
) -> FillDecision:
    """Flip an existing fill decision to ``settled`` under Rank 0.1 gates.

    Does **not** invent cents — the caller supplies ``revenue_usd_cents`` from
    a real budget/authority; this function only records them when gates pass.
    """
    assert_settlement_allowed(
        revenue_usd_cents=revenue_usd_cents,
        legal_gate_passed=legal_gate_passed,
        pricing_authority_ref=pricing_authority_ref,
    )
    ensure_table(con)
    row = con.execute(
        """
        SELECT decision_id, owner_user_id, window_id, document_id, page_index,
               lens, positions_json, fills_json, revenue_usd_cents, price_status
        FROM ad_fill_decisions WHERE decision_id = ?
        """,
        [decision_id],
    ).fetchone()
    if row is None:
        raise FillSettlementError(f"unknown decision_id {decision_id!r}")
    if str(row[9]) == "settled":
        # Idempotent replay of the same settlement.
        existing = _from_row(row, replayed=True)
        if existing.revenue_usd_cents != int(revenue_usd_cents):
            raise FillSettlementError(
                f"decision_id {decision_id!r} already settled at "
                f"{existing.revenue_usd_cents} cents; cannot re-settle at "
                f"{revenue_usd_cents}"
            )
        return existing
    if _fills_are_house_only(str(row[7])):
        raise FillSettlementError(
            f"cannot settle decision_id {decision_id!r}: house-only fill "
            "(library promo is never a bill)"
        )
    # Optional advertiser stamp is audit-only for Rank 0.1; not required to
    # mint cents, but when supplied must be non-empty.
    if advertiser_id is not None and not str(advertiser_id).strip():
        raise FillSettlementError("advertiser_id when supplied must be non-empty")

    con.execute(
        """
        UPDATE ad_fill_decisions
        SET revenue_usd_cents = ?, price_status = 'settled'
        WHERE decision_id = ? AND price_status = 'unpriced'
        """,
        [int(revenue_usd_cents), decision_id],
    )
    updated = con.execute(
        """
        SELECT decision_id, owner_user_id, window_id, document_id, page_index,
               lens, positions_json, fills_json, revenue_usd_cents, price_status
        FROM ad_fill_decisions WHERE decision_id = ?
        """,
        [decision_id],
    ).fetchone()
    if updated is None or str(updated[9]) != "settled":
        raise FillSettlementError(
            f"failed to settle decision_id {decision_id!r}"
        )
    return _from_row(updated, replayed=False)


__all__ = [
    "FillSettlementError",
    "settle_fill_decision",
]
