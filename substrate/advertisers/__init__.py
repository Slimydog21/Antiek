"""Advertiser + campaign storage (Sprint 23-24 §3 deliverable).

Per Sprint 23-24 doc Phase 5 + §3 deliverable grid:
*"An operator-only advertiser console at
`apps/reading/src/modes/AdvertiserConsole/` handles inventory entry,
targeting rules (sector + intent), creative upload (image + URL +
click-out), and per-campaign performance reporting."*

The React surface already exists; this module is the substrate
backing — Advertiser + AdCampaign storage with a Protocol-backed
store (InMemory for tests, SQLite for persistence; promotable to
Postgres at production).
"""

from .store import (
    Advertiser,
    AdvertiserCampaign,
    AdvertiserStore,
    InMemoryAdvertiserStore,
    SqliteAdvertiserStore,
    CampaignStatus,
    create_advertiser,
    create_campaign,
    list_campaigns_for_advertiser,
    list_active_campaigns,
    update_campaign_status,
)

__all__ = [
    "Advertiser",
    "AdvertiserCampaign",
    "AdvertiserStore",
    "CampaignStatus",
    "InMemoryAdvertiserStore",
    "SqliteAdvertiserStore",
    "create_advertiser",
    "create_campaign",
    "list_active_campaigns",
    "list_campaigns_for_advertiser",
    "update_campaign_status",
]
