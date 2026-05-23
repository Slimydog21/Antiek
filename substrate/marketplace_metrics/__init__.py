"""Marketplace metrics — Sprint 25+ §2 marketplace metrics dashboard
data layer.

Per the Sprint 25+ deliverable: 'one operator-only surface that
aggregates the three economic loops: creator earnings distribution
(median, p90, long-tail mass), publisher escrow accrual + claim rate,
advertiser spend + retention. The dashboard is the input to the
Sprint 30+ federation/programmatic decision and to the §9.4 "is
programmatic display warranted" gate.'

This is the substrate side; the React MarketplaceMetrics surface
consumes the dashboard snapshot at /marketplace/snapshot when the
endpoint is wired.

Pure-functional design: every function takes the relevant log /
ledger as input and returns a typed result. No I/O; tests cover all
branches.
"""

from .creator_distribution import (
    CreatorEarningsDistribution,
    EarningsBucket,
    compute_creator_distribution,
)
from .publisher_escrow import (
    PublisherEscrowReport,
    PublisherStatusCounts,
    compute_publisher_escrow,
)
from .advertiser_retention import (
    AdvertiserRetentionReport,
    AdvertiserActivity,
    compute_advertiser_retention,
)
from .dashboard import (
    MarketplaceSnapshot,
    MarketplaceHealth,
    assemble_snapshot,
    classify_health,
)
from .data_sources import (
    collect_snapshot_inputs,
    fetch_creator_paid_cents,
    fetch_publisher_accrual_cents,
    fetch_publisher_paid_cents,
    fetch_publisher_status_rows,
)
from .from_conn import build_snapshot_from_inputs, build_snapshot_from_conn

__all__ = [
    "AdvertiserActivity",
    "AdvertiserRetentionReport",
    "CreatorEarningsDistribution",
    "EarningsBucket",
    "MarketplaceHealth",
    "MarketplaceSnapshot",
    "PublisherEscrowReport",
    "PublisherStatusCounts",
    "assemble_snapshot",
    "build_snapshot_from_conn",
    "build_snapshot_from_inputs",
    "classify_health",
    "collect_snapshot_inputs",
    "compute_advertiser_retention",
    "compute_creator_distribution",
    "compute_publisher_escrow",
    "fetch_creator_paid_cents",
    "fetch_publisher_accrual_cents",
    "fetch_publisher_paid_cents",
    "fetch_publisher_status_rows",
]
