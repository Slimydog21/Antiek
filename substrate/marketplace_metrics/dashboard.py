"""Composite marketplace snapshot + health classifier.

Per Sprint 25+ doc §4 exit criteria: 'operator can answer
"is the marketplace healthy" without manual SQL.' This module
takes the three economic-loop reports and rolls them into a single
MarketplaceSnapshot with a derived MarketplaceHealth verdict.

Health is HEALTHY / WATCH / UNHEALTHY. Each branch documents the
specific signal that fired so the operator can see WHY, not just
the verdict. This is the input to the §9.4 'is programmatic display
warranted' gate and the Sprint 30+ federation thread-trigger
evaluation.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from .advertiser_retention import AdvertiserRetentionReport
from .creator_distribution import CreatorEarningsDistribution
from .publisher_escrow import PublisherEscrowReport


class MarketplaceHealth(str, enum.Enum):
    HEALTHY = "healthy"
    WATCH = "watch"
    UNHEALTHY = "unhealthy"


@dataclass(frozen=True)
class MarketplaceSnapshot:
    creators: CreatorEarningsDistribution
    publishers: PublisherEscrowReport
    advertisers: AdvertiserRetentionReport
    health: MarketplaceHealth
    health_signals: tuple[str, ...]


# Thresholds derived from the Sprint 25+ doc §4 exit criteria.
HEALTHY_CREATOR_COUNT_MIN = 30  # > 30 active monthly-earning creators
HEALTHY_PUBLISHER_CLAIM_RATE_MIN = 0.20  # at least 20% claim from invited
HEALTHY_ADVERTISER_RETENTION_MIN = 0.50  # at least half last month's advertisers retained
WATCH_CREATOR_COUNT_MIN = 10
WATCH_PUBLISHER_CLAIM_RATE_MIN = 0.05


def classify_health(
    *,
    creators: CreatorEarningsDistribution,
    publishers: PublisherEscrowReport,
    advertisers: AdvertiserRetentionReport,
) -> tuple[MarketplaceHealth, tuple[str, ...]]:
    """Derive the health verdict + per-signal reasons.

    Returns (verdict, reasons). reasons is non-empty regardless of
    verdict — HEALTHY reports the positive signals, WATCH/UNHEALTHY
    reports the failing ones so the operator sees the specific
    weakness.
    """
    signals: list[str] = []
    bad_signals = 0
    watch_signals = 0

    # Creator loop.
    paid_creators = sum(1 for b in creators.buckets if b.lower_cents >= 1_000 for _ in range(b.creator_count))
    # The above generator is awkward; use a direct count:
    paid_creator_count = sum(
        b.creator_count for b in creators.buckets if b.lower_cents >= 1_000
    )
    if paid_creator_count >= HEALTHY_CREATOR_COUNT_MIN:
        signals.append(f"creators_above_threshold={paid_creator_count} (healthy)")
    elif paid_creator_count >= WATCH_CREATOR_COUNT_MIN:
        signals.append(f"creators_above_threshold={paid_creator_count} (watch; below {HEALTHY_CREATOR_COUNT_MIN})")
        watch_signals += 1
    else:
        signals.append(f"creators_above_threshold={paid_creator_count} (unhealthy; below {WATCH_CREATOR_COUNT_MIN})")
        bad_signals += 1

    # Publisher loop.
    rate = publishers.status_counts.claim_rate
    if rate >= HEALTHY_PUBLISHER_CLAIM_RATE_MIN:
        signals.append(f"publisher_claim_rate={rate:.2f} (healthy)")
    elif rate >= WATCH_PUBLISHER_CLAIM_RATE_MIN:
        signals.append(f"publisher_claim_rate={rate:.2f} (watch; below {HEALTHY_PUBLISHER_CLAIM_RATE_MIN:.2f})")
        watch_signals += 1
    else:
        signals.append(f"publisher_claim_rate={rate:.2f} (unhealthy; below {WATCH_PUBLISHER_CLAIM_RATE_MIN:.2f})")
        bad_signals += 1

    # Advertiser loop.
    if advertisers.advertiser_count_prior == 0:
        signals.append("advertiser_retention=n/a (no prior period; watch)")
        watch_signals += 1
    elif advertisers.retention_rate >= HEALTHY_ADVERTISER_RETENTION_MIN:
        signals.append(f"advertiser_retention={advertisers.retention_rate:.2f} (healthy)")
    else:
        signals.append(f"advertiser_retention={advertisers.retention_rate:.2f} (unhealthy; below {HEALTHY_ADVERTISER_RETENTION_MIN:.2f})")
        bad_signals += 1

    if bad_signals >= 2:
        return (MarketplaceHealth.UNHEALTHY, tuple(signals))
    if bad_signals == 1 or watch_signals >= 2:
        return (MarketplaceHealth.WATCH, tuple(signals))
    if watch_signals == 1:
        return (MarketplaceHealth.WATCH, tuple(signals))
    return (MarketplaceHealth.HEALTHY, tuple(signals))


def assemble_snapshot(
    *,
    creators: CreatorEarningsDistribution,
    publishers: PublisherEscrowReport,
    advertisers: AdvertiserRetentionReport,
) -> MarketplaceSnapshot:
    health, signals = classify_health(
        creators=creators, publishers=publishers, advertisers=advertisers,
    )
    return MarketplaceSnapshot(
        creators=creators,
        publishers=publishers,
        advertisers=advertisers,
        health=health,
        health_signals=signals,
    )
