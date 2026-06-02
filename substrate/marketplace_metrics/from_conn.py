"""Glue: input dict → MarketplaceSnapshot, and DB conn → MarketplaceSnapshot.

The API endpoint at /marketplace/snapshot calls
`build_snapshot_from_conn` with a substrate read connection +
optional operator overrides.
"""

from __future__ import annotations

from collections.abc import Mapping

from .advertiser_retention import compute_advertiser_retention
from .creator_distribution import compute_creator_distribution
from .dashboard import MarketplaceSnapshot, assemble_snapshot
from .data_sources import collect_snapshot_inputs
from .publisher_escrow import compute_publisher_escrow


def build_snapshot_from_inputs(
    *,
    creator_paid_cents: Mapping[str, int],
    publisher_status_rows: list[tuple[str, str]],
    publisher_accrual_cents: Mapping[str, int],
    publisher_paid_cents: Mapping[str, int],
    current_advertiser_spend: Mapping[str, int],
    prior_advertiser_spend: Mapping[str, int],
) -> MarketplaceSnapshot:
    """Pure-functional dict → snapshot. No I/O."""
    creators = compute_creator_distribution(dict(creator_paid_cents))
    publishers = compute_publisher_escrow(
        publisher_status_rows=publisher_status_rows,
        publisher_accrual_cents=dict(publisher_accrual_cents),
        publisher_paid_cents=dict(publisher_paid_cents),
    )
    advertisers = compute_advertiser_retention(
        current_period_spend=current_advertiser_spend,
        prior_period_spend=prior_advertiser_spend,
    )
    return assemble_snapshot(
        creators=creators,
        publishers=publishers,
        advertisers=advertisers,
    )


def build_snapshot_from_conn(
    con,
    *,
    creator_paid_cents_override: Mapping[str, int] | None = None,
    current_advertiser_spend_override: Mapping[str, int] | None = None,
    prior_advertiser_spend_override: Mapping[str, int] | None = None,
) -> MarketplaceSnapshot:
    """DB conn → snapshot. Reads ip_holders; accepts overrides for
    data not yet in substrate."""
    inputs = collect_snapshot_inputs(
        con,
        creator_paid_cents_override=creator_paid_cents_override,
        current_advertiser_spend_override=current_advertiser_spend_override,
        prior_advertiser_spend_override=prior_advertiser_spend_override,
    )
    return build_snapshot_from_inputs(**inputs)
