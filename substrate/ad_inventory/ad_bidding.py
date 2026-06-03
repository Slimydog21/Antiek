"""Lead-gen ad inventory mechanism (master-spec §9.4 Option C).

Sprint 23+ Phase 4 work. Lead-gen ad slot shows a relevant service
offering (consulting, recruiting, vertical SaaS) targeted by the
synthesis topic. Higher CPMs than display, more aligned with audience
intent. Builds on the existing substrate's topic classification
(decomposer already produces topic categories)."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class BiddingPolicy(str, enum.Enum):
    """Per master-spec §9.4 phased approach."""

    MANUAL_SPONSOR = "manual_sponsor"      # Phase 1: single sponsor pays flat monthly
    LEAD_GEN_VERTICAL = "lead_gen_vertical"  # Phase 3: curated vertical ad slots
    PROGRAMMATIC_AUCTION = "programmatic_auction"  # Phase 4+ (only at scale)


@dataclass(frozen=True)
class AdInventoryItem:
    """One ad available to show on a page. Curated by operator (in
    LEAD_GEN_VERTICAL mode); auction-resolved in PROGRAMMATIC."""

    inventory_id: str
    advertiser_display_name: str
    target_topics: tuple[str, ...]  # e.g. ('quantum', 'defense')
    cpm_usd: Decimal
    creative_url: str  # the actual banner / lead-gen creative
    landing_url: str


@dataclass(frozen=True)
class AdImpression:
    """One served ad. Connects synthesis page → ad inventory → ad
    revenue. The revenue then flows through attribution to creators
    (master-spec §13.9) and publishers (§9.10)."""

    impression_id: str
    inventory_id: str
    page_id: str  # synthesis page that showed the ad
    investigation_id: str | None
    revenue_usd_cents: int  # what the advertiser paid for this impression
    served_at: str = field(default_factory=_now_iso)


@dataclass
class LeadGenAdInventory:
    """Operator-curated lead-gen ad slots. Sprint 23+ Phase 4 default."""

    items: list[AdInventoryItem] = field(default_factory=list)

    def add(self, item: AdInventoryItem) -> None:
        self.items.append(item)

    def by_topics(self, topics: list[str]) -> list[AdInventoryItem]:
        """Return inventory matching ANY of the given topic tags."""
        target_set = {t.lower() for t in topics}
        return [
            item for item in self.items
            if any(t.lower() in target_set for t in item.target_topics)
        ]


def select_lead_gen_ad(
    inventory: LeadGenAdInventory,
    *,
    page_topics: list[str],
) -> AdInventoryItem | None:
    """Pick the highest-CPM ad whose target_topics intersect
    page_topics. Returns None if no inventory matches."""
    candidates = inventory.by_topics(page_topics)
    if not candidates:
        return None
    return max(candidates, key=lambda i: i.cpm_usd)
