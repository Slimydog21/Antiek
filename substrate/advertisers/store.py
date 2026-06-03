"""Advertiser + AdvertiserCampaign storage + CRUD operations."""

from __future__ import annotations

import enum
import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class CampaignStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DRAFT = "draft"
    REJECTED = "rejected"


@dataclass(frozen=True)
class Advertiser:
    """One advertiser organisation in the inventory pool."""

    advertiser_id: str
    display_name: str
    sector: str  # broad category — vertical-saas | consulting | recruiting | other
    contact_email: str
    stripe_customer_id: str | None  # populated once first invoice settles
    created_at: str = field(default_factory=_now_iso)


@dataclass(frozen=True)
class AdvertiserCampaign:
    """One campaign — single creative + budget + targeting."""

    campaign_id: str
    advertiser_id: str
    sector: str
    sub_sector: str | None
    intent: str
    target_topics: tuple[str, ...]
    creative_headline: str
    creative_url: str
    daily_budget_cents: int
    status: CampaignStatus = CampaignStatus.DRAFT
    impressions: int = 0
    clicks: int = 0
    spend_cents: int = 0
    created_at: str = field(default_factory=_now_iso)


class AdvertiserStore(Protocol):
    def upsert_advertiser(self, advertiser: Advertiser) -> None: ...
    def get_advertiser(self, advertiser_id: str) -> Advertiser | None: ...
    def list_advertisers(self) -> list[Advertiser]: ...
    def upsert_campaign(self, campaign: AdvertiserCampaign) -> None: ...
    def get_campaign(self, campaign_id: str) -> AdvertiserCampaign | None: ...
    def list_campaigns(self) -> list[AdvertiserCampaign]: ...


@dataclass
class InMemoryAdvertiserStore:
    advertisers: dict[str, Advertiser] = field(default_factory=dict)
    campaigns: dict[str, AdvertiserCampaign] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def upsert_advertiser(self, advertiser: Advertiser) -> None:
        with self._lock:
            self.advertisers[advertiser.advertiser_id] = advertiser

    def get_advertiser(self, advertiser_id: str) -> Advertiser | None:
        with self._lock:
            return self.advertisers.get(advertiser_id)

    def list_advertisers(self) -> list[Advertiser]:
        with self._lock:
            return list(self.advertisers.values())

    def upsert_campaign(self, campaign: AdvertiserCampaign) -> None:
        with self._lock:
            self.campaigns[campaign.campaign_id] = campaign

    def get_campaign(self, campaign_id: str) -> AdvertiserCampaign | None:
        with self._lock:
            return self.campaigns.get(campaign_id)

    def list_campaigns(self) -> list[AdvertiserCampaign]:
        with self._lock:
            return list(self.campaigns.values())


@dataclass
class SqliteAdvertiserStore:
    db_path: str
    _conn: sqlite3.Connection | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        d = os.path.dirname(self.db_path)
        if d:
            os.makedirs(d, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS advertisers (
                advertiser_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                sector TEXT NOT NULL,
                contact_email TEXT NOT NULL,
                stripe_customer_id TEXT,
                created_at TEXT NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS advertiser_campaigns (
                campaign_id TEXT PRIMARY KEY,
                advertiser_id TEXT NOT NULL,
                sector TEXT NOT NULL,
                sub_sector TEXT,
                intent TEXT NOT NULL,
                target_topics TEXT NOT NULL,
                creative_headline TEXT NOT NULL,
                creative_url TEXT NOT NULL,
                daily_budget_cents INTEGER NOT NULL,
                status TEXT NOT NULL,
                impressions INTEGER NOT NULL DEFAULT 0,
                clicks INTEGER NOT NULL DEFAULT 0,
                spend_cents INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (advertiser_id) REFERENCES advertisers(advertiser_id)
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_campaigns_status ON advertiser_campaigns(status)"
        )
        self._conn.commit()

    def upsert_advertiser(self, advertiser: Advertiser) -> None:
        assert self._conn is not None
        with self._lock:
            self._conn.execute("""
                INSERT INTO advertisers (
                    advertiser_id, display_name, sector, contact_email,
                    stripe_customer_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(advertiser_id) DO UPDATE SET
                    display_name=excluded.display_name,
                    sector=excluded.sector,
                    contact_email=excluded.contact_email,
                    stripe_customer_id=excluded.stripe_customer_id
            """, (
                advertiser.advertiser_id, advertiser.display_name,
                advertiser.sector, advertiser.contact_email,
                advertiser.stripe_customer_id, advertiser.created_at,
            ))
            self._conn.commit()

    def get_advertiser(self, advertiser_id: str) -> Advertiser | None:
        assert self._conn is not None
        with self._lock:
            row = self._conn.execute(
                "SELECT advertiser_id, display_name, sector, contact_email, "
                "stripe_customer_id, created_at FROM advertisers "
                "WHERE advertiser_id = ?",
                (advertiser_id,),
            ).fetchone()
        if row is None:
            return None
        return Advertiser(
            advertiser_id=row[0], display_name=row[1], sector=row[2],
            contact_email=row[3], stripe_customer_id=row[4], created_at=row[5],
        )

    def list_advertisers(self) -> list[Advertiser]:
        assert self._conn is not None
        with self._lock:
            rows = self._conn.execute(
                "SELECT advertiser_id, display_name, sector, contact_email, "
                "stripe_customer_id, created_at FROM advertisers"
            ).fetchall()
        return [
            Advertiser(
                advertiser_id=r[0], display_name=r[1], sector=r[2],
                contact_email=r[3], stripe_customer_id=r[4], created_at=r[5],
            ) for r in rows
        ]

    def upsert_campaign(self, campaign: AdvertiserCampaign) -> None:
        assert self._conn is not None
        with self._lock:
            self._conn.execute("""
                INSERT INTO advertiser_campaigns (
                    campaign_id, advertiser_id, sector, sub_sector, intent,
                    target_topics, creative_headline, creative_url,
                    daily_budget_cents, status, impressions, clicks,
                    spend_cents, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(campaign_id) DO UPDATE SET
                    sector=excluded.sector,
                    sub_sector=excluded.sub_sector,
                    intent=excluded.intent,
                    target_topics=excluded.target_topics,
                    creative_headline=excluded.creative_headline,
                    creative_url=excluded.creative_url,
                    daily_budget_cents=excluded.daily_budget_cents,
                    status=excluded.status,
                    impressions=excluded.impressions,
                    clicks=excluded.clicks,
                    spend_cents=excluded.spend_cents
            """, (
                campaign.campaign_id, campaign.advertiser_id,
                campaign.sector, campaign.sub_sector, campaign.intent,
                ",".join(campaign.target_topics),
                campaign.creative_headline, campaign.creative_url,
                campaign.daily_budget_cents, campaign.status.value,
                campaign.impressions, campaign.clicks, campaign.spend_cents,
                campaign.created_at,
            ))
            self._conn.commit()

    def get_campaign(self, campaign_id: str) -> AdvertiserCampaign | None:
        assert self._conn is not None
        with self._lock:
            row = self._conn.execute(
                "SELECT campaign_id, advertiser_id, sector, sub_sector, intent, "
                "target_topics, creative_headline, creative_url, "
                "daily_budget_cents, status, impressions, clicks, spend_cents, "
                "created_at FROM advertiser_campaigns WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
        if row is None:
            return None
        return AdvertiserCampaign(
            campaign_id=row[0], advertiser_id=row[1], sector=row[2],
            sub_sector=row[3], intent=row[4],
            target_topics=tuple(row[5].split(",")) if row[5] else (),
            creative_headline=row[6], creative_url=row[7],
            daily_budget_cents=row[8], status=CampaignStatus(row[9]),
            impressions=row[10], clicks=row[11], spend_cents=row[12],
            created_at=row[13],
        )

    def list_campaigns(self) -> list[AdvertiserCampaign]:
        assert self._conn is not None
        with self._lock:
            rows = self._conn.execute(
                "SELECT campaign_id, advertiser_id, sector, sub_sector, intent, "
                "target_topics, creative_headline, creative_url, "
                "daily_budget_cents, status, impressions, clicks, spend_cents, "
                "created_at FROM advertiser_campaigns"
            ).fetchall()
        return [
            AdvertiserCampaign(
                campaign_id=r[0], advertiser_id=r[1], sector=r[2],
                sub_sector=r[3], intent=r[4],
                target_topics=tuple(r[5].split(",")) if r[5] else (),
                creative_headline=r[6], creative_url=r[7],
                daily_budget_cents=r[8], status=CampaignStatus(r[9]),
                impressions=r[10], clicks=r[11], spend_cents=r[12],
                created_at=r[13],
            ) for r in rows
        ]


def create_advertiser(
    store: AdvertiserStore,
    *,
    display_name: str,
    sector: str,
    contact_email: str,
) -> Advertiser:
    """Create a new advertiser. Returns the created row."""
    advertiser = Advertiser(
        advertiser_id=f"adv-{uuid.uuid4().hex[:12]}",
        display_name=display_name,
        sector=sector,
        contact_email=contact_email,
        stripe_customer_id=None,
    )
    store.upsert_advertiser(advertiser)
    return advertiser


def create_campaign(
    store: AdvertiserStore,
    *,
    advertiser_id: str,
    sector: str,
    intent: str,
    creative_headline: str,
    creative_url: str,
    daily_budget_cents: int,
    sub_sector: str | None = None,
    target_topics: tuple[str, ...] = (),
    status: CampaignStatus = CampaignStatus.DRAFT,
) -> AdvertiserCampaign:
    """Create a new campaign. Verifies the advertiser exists."""
    advertiser = store.get_advertiser(advertiser_id)
    if advertiser is None:
        raise ValueError(f"unknown advertiser_id {advertiser_id!r}")
    campaign = AdvertiserCampaign(
        campaign_id=f"cam-{uuid.uuid4().hex[:12]}",
        advertiser_id=advertiser_id,
        sector=sector,
        sub_sector=sub_sector,
        intent=intent,
        target_topics=target_topics,
        creative_headline=creative_headline,
        creative_url=creative_url,
        daily_budget_cents=daily_budget_cents,
        status=status,
    )
    store.upsert_campaign(campaign)
    return campaign


def list_campaigns_for_advertiser(
    store: AdvertiserStore,
    advertiser_id: str,
) -> list[AdvertiserCampaign]:
    return [c for c in store.list_campaigns() if c.advertiser_id == advertiser_id]


def list_active_campaigns(store: AdvertiserStore) -> list[AdvertiserCampaign]:
    return [c for c in store.list_campaigns() if c.status == CampaignStatus.ACTIVE]


def update_campaign_status(
    store: AdvertiserStore,
    *,
    campaign_id: str,
    new_status: CampaignStatus,
) -> AdvertiserCampaign:
    existing = store.get_campaign(campaign_id)
    if existing is None:
        raise ValueError(f"unknown campaign_id {campaign_id!r}")
    updated = AdvertiserCampaign(
        campaign_id=existing.campaign_id,
        advertiser_id=existing.advertiser_id,
        sector=existing.sector,
        sub_sector=existing.sub_sector,
        intent=existing.intent,
        target_topics=existing.target_topics,
        creative_headline=existing.creative_headline,
        creative_url=existing.creative_url,
        daily_budget_cents=existing.daily_budget_cents,
        status=new_status,
        impressions=existing.impressions,
        clicks=existing.clicks,
        spend_cents=existing.spend_cents,
        created_at=existing.created_at,
    )
    store.upsert_campaign(updated)
    return updated
