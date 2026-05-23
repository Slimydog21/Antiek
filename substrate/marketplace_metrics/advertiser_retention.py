"""Advertiser spend + retention — Sprint 25+ programmatic-gate input.

Per Sprint 25+ doc §2: 'advertiser spend + retention.' Retention is
measured by the count of advertisers active in the current period
who were ALSO active in the prior period. Above a doc-defined
spend threshold per §9.6, advertiser self-service unlocks; this
report supplies the number the operator uses to flip that gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping


@dataclass(frozen=True)
class AdvertiserActivity:
    advertiser_id: str
    current_period_spend_cents: int
    prior_period_spend_cents: int

    @property
    def is_retained(self) -> bool:
        return self.prior_period_spend_cents > 0 and self.current_period_spend_cents > 0


@dataclass(frozen=True)
class AdvertiserRetentionReport:
    advertiser_count_current: int
    advertiser_count_prior: int
    retained_advertiser_count: int
    new_advertiser_count: int
    churned_advertiser_count: int
    total_spend_current_cents: int
    total_spend_prior_cents: int
    retention_rate: float  # retained / prior_count
    activities: tuple[AdvertiserActivity, ...]

    @property
    def crosses_self_service_threshold(self) -> bool:
        """§9.6 self-service threshold default = $50K/mo. Caller can
        also check this against an operator-overridden threshold."""
        return self.total_spend_current_cents >= 5_000_000


def compute_advertiser_retention(
    *,
    current_period_spend: Mapping[str, int],  # advertiser_id → cents
    prior_period_spend: Mapping[str, int],
) -> AdvertiserRetentionReport:
    current_ids = set(current_period_spend.keys())
    prior_ids = set(prior_period_spend.keys())

    retained = current_ids & prior_ids
    new = current_ids - prior_ids
    churned = prior_ids - current_ids

    activities: list[AdvertiserActivity] = []
    for adv_id in sorted(current_ids | prior_ids):
        activities.append(AdvertiserActivity(
            advertiser_id=adv_id,
            current_period_spend_cents=current_period_spend.get(adv_id, 0),
            prior_period_spend_cents=prior_period_spend.get(adv_id, 0),
        ))

    retention_rate = (
        (len(retained) / len(prior_ids)) if prior_ids else 0.0
    )

    return AdvertiserRetentionReport(
        advertiser_count_current=len(current_ids),
        advertiser_count_prior=len(prior_ids),
        retained_advertiser_count=len(retained),
        new_advertiser_count=len(new),
        churned_advertiser_count=len(churned),
        total_spend_current_cents=sum(current_period_spend.values()),
        total_spend_prior_cents=sum(prior_period_spend.values()),
        retention_rate=retention_rate,
        activities=tuple(activities),
    )
