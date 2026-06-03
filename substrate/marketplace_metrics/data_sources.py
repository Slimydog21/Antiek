"""DB-query helpers that produce the input dicts for assemble_snapshot.

Substrate-scaffold honesty: only `ip_holders` carries the data
needed for the publisher report today; the rev_share decisions
table and the advertiser_spend table do not yet exist as persisted
substrate state (Sprint 23-24's rev_share module accrues in-process
to a RolloverLedger; the ad_inventory module does not persist
per-period advertiser spend).

This module returns what IS queryable + empty maps for what isn't.
The marketplace_metrics compute_* functions handle empty inputs
gracefully. As the persistence layer matures, the empty branches
get replaced with real queries — the call sites do not change.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol


class _DBConn(Protocol):
    """Minimal DuckDB-shaped read-only connection contract."""

    def execute(self, sql: str, params: list | None = None) -> _DBConn: ...
    def fetchall(self) -> list[tuple]: ...


def fetch_publisher_status_rows(con: _DBConn) -> list[tuple[str, str]]:
    """Return [(ip_holder_id, status), ...] from the ip_holders table.

    Single source of truth for the publisher loop. Empty list when
    the table is empty (pre-cohort)."""
    try:
        rows = con.execute(
            "SELECT ip_holder_id, status FROM ip_holders"
        ).fetchall()
    except Exception:
        return []
    return [(row[0], row[1]) for row in rows]


def fetch_publisher_accrual_cents(con: _DBConn) -> dict[str, int]:
    """Return ip_holder_id → accrued cents from `ip_holders.escrow_balance_usd`.

    DECIMAL→cents conversion in Python to avoid SQL-side precision drift."""
    try:
        rows = con.execute(
            "SELECT ip_holder_id, escrow_balance_usd FROM ip_holders"
        ).fetchall()
    except Exception:
        return {}
    out: dict[str, int] = {}
    for row in rows:
        ip_id = row[0]
        balance_usd = row[1] or 0
        try:
            cents = int(round(float(balance_usd) * 100))
        except (TypeError, ValueError):
            cents = 0
        out[ip_id] = cents
    return out


def fetch_publisher_paid_cents(con: _DBConn) -> dict[str, int]:
    """Return ip_holder_id → cents paid (currently always empty).

    The payout_transfers table tracks transfers by stripe_account_id,
    not by ip_holder_id. Linking them requires a stripe_accounts
    table that doesn't exist yet (Stripe account state lives in the
    MockStripeProvider's memory or RealStripeProvider's remote
    state). Once a substrate-side mirror table lands, this becomes
    a JOIN. For now we return an empty map — the publisher report
    handles it correctly: `total_escrow_paid_cents = 0`.
    """
    return {}


def fetch_creator_paid_cents(con: _DBConn) -> dict[str, int]:
    """Return creator_user_id → cents paid (currently always empty).

    Same constraint as fetch_publisher_paid_cents — needs the
    not-yet-built substrate-side mirror of Stripe Connect accounts.
    Creator distribution from an empty map is well-defined: zero
    creators above threshold, which the health classifier reads as
    'unhealthy creator loop'. That is the correct signal for an
    empty cohort.
    """
    return {}


def collect_snapshot_inputs(
    con: _DBConn,
    *,
    creator_paid_cents_override: Mapping[str, int] | None = None,
    current_advertiser_spend_override: Mapping[str, int] | None = None,
    prior_advertiser_spend_override: Mapping[str, int] | None = None,
) -> dict:
    """Assemble the input dict for assemble_snapshot from a DB conn.

    Overrides let the operator-only dashboard inject manually-entered
    creator + advertiser totals before the substrate persists them
    natively. None means 'use substrate query'; an explicit empty
    dict means 'no data, accept the empty branch'.
    """
    return {
        "creator_paid_cents": (
            dict(creator_paid_cents_override)
            if creator_paid_cents_override is not None
            else fetch_creator_paid_cents(con)
        ),
        "publisher_status_rows": fetch_publisher_status_rows(con),
        "publisher_accrual_cents": fetch_publisher_accrual_cents(con),
        "publisher_paid_cents": fetch_publisher_paid_cents(con),
        "current_advertiser_spend": (
            dict(current_advertiser_spend_override)
            if current_advertiser_spend_override is not None
            else {}
        ),
        "prior_advertiser_spend": (
            dict(prior_advertiser_spend_override)
            if prior_advertiser_spend_override is not None
            else {}
        ),
    }
