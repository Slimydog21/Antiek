"""Tests for substrate.advertisers — advertiser + campaign storage."""

from __future__ import annotations

import os
import tempfile

import pytest

from substrate.advertisers import (
    Advertiser,
    AdvertiserCampaign,
    CampaignStatus,
    InMemoryAdvertiserStore,
    SqliteAdvertiserStore,
    create_advertiser,
    create_campaign,
    list_active_campaigns,
    list_campaigns_for_advertiser,
    update_campaign_status,
)


# ── InMemory store ─────────────────────────────────────────────


def test_create_advertiser_assigns_id():
    store = InMemoryAdvertiserStore()
    advertiser = create_advertiser(
        store, display_name="Vertical SaaS Inc.",
        sector="developer-tools", contact_email="ads@example.com",
    )
    assert advertiser.advertiser_id.startswith("adv-")
    assert store.get_advertiser(advertiser.advertiser_id) is not None


def test_create_campaign_requires_advertiser():
    store = InMemoryAdvertiserStore()
    with pytest.raises(ValueError, match="unknown advertiser_id"):
        create_campaign(
            store, advertiser_id="adv-missing",
            sector="x", intent="trial-signup",
            creative_headline="x", creative_url="x",
            daily_budget_cents=1000,
        )


def test_create_campaign_default_status_is_draft():
    store = InMemoryAdvertiserStore()
    advertiser = create_advertiser(
        store, display_name="X", sector="x", contact_email="x@y.com",
    )
    campaign = create_campaign(
        store, advertiser_id=advertiser.advertiser_id,
        sector="x", intent="trial-signup",
        creative_headline="headline", creative_url="https://x",
        daily_budget_cents=5000,
    )
    assert campaign.status == CampaignStatus.DRAFT


def test_list_campaigns_for_advertiser_filters():
    store = InMemoryAdvertiserStore()
    a1 = create_advertiser(store, display_name="A1", sector="x",
                           contact_email="a1@x")
    a2 = create_advertiser(store, display_name="A2", sector="x",
                           contact_email="a2@x")
    create_campaign(store, advertiser_id=a1.advertiser_id,
                    sector="x", intent="t", creative_headline="h",
                    creative_url="u", daily_budget_cents=100)
    create_campaign(store, advertiser_id=a1.advertiser_id,
                    sector="x", intent="t", creative_headline="h",
                    creative_url="u", daily_budget_cents=100)
    create_campaign(store, advertiser_id=a2.advertiser_id,
                    sector="x", intent="t", creative_headline="h",
                    creative_url="u", daily_budget_cents=100)
    assert len(list_campaigns_for_advertiser(store, a1.advertiser_id)) == 2
    assert len(list_campaigns_for_advertiser(store, a2.advertiser_id)) == 1


def test_list_active_campaigns_filters_status():
    store = InMemoryAdvertiserStore()
    a = create_advertiser(store, display_name="A", sector="x",
                          contact_email="a@x")
    c1 = create_campaign(store, advertiser_id=a.advertiser_id,
                         sector="x", intent="t", creative_headline="h",
                         creative_url="u", daily_budget_cents=100,
                         status=CampaignStatus.ACTIVE)
    c2 = create_campaign(store, advertiser_id=a.advertiser_id,
                         sector="x", intent="t", creative_headline="h",
                         creative_url="u", daily_budget_cents=100,
                         status=CampaignStatus.DRAFT)
    active = list_active_campaigns(store)
    assert {c.campaign_id for c in active} == {c1.campaign_id}


def test_update_campaign_status_preserves_other_fields():
    store = InMemoryAdvertiserStore()
    a = create_advertiser(store, display_name="A", sector="x",
                          contact_email="a@x")
    c = create_campaign(store, advertiser_id=a.advertiser_id,
                        sector="developer-tools", intent="trial-signup",
                        creative_headline="headline", creative_url="https://x",
                        daily_budget_cents=10_000)
    updated = update_campaign_status(store,
                                     campaign_id=c.campaign_id,
                                     new_status=CampaignStatus.ACTIVE)
    assert updated.status == CampaignStatus.ACTIVE
    assert updated.creative_headline == "headline"
    assert updated.daily_budget_cents == 10_000


def test_update_unknown_campaign_raises():
    store = InMemoryAdvertiserStore()
    with pytest.raises(ValueError, match="unknown campaign_id"):
        update_campaign_status(store, campaign_id="cam-missing",
                               new_status=CampaignStatus.ACTIVE)


# ── SQLite store persistence ───────────────────────────────────


def test_sqlite_advertiser_persists_across_reopen(tmp_path):
    db = str(tmp_path / "adv.sqlite")
    s1 = SqliteAdvertiserStore(db_path=db)
    a = create_advertiser(s1, display_name="MegaCorp", sector="finance",
                          contact_email="ads@mega.com")
    s2 = SqliteAdvertiserStore(db_path=db)
    found = s2.get_advertiser(a.advertiser_id)
    assert found is not None
    assert found.display_name == "MegaCorp"


def test_sqlite_campaign_persists_across_reopen(tmp_path):
    db = str(tmp_path / "adv.sqlite")
    s1 = SqliteAdvertiserStore(db_path=db)
    a = create_advertiser(s1, display_name="X", sector="x",
                          contact_email="x@y.com")
    c = create_campaign(s1, advertiser_id=a.advertiser_id,
                        sector="x", intent="trial-signup",
                        target_topics=("python", "tooling"),
                        creative_headline="ship faster", creative_url="https://x",
                        daily_budget_cents=10_000)
    s2 = SqliteAdvertiserStore(db_path=db)
    found = s2.get_campaign(c.campaign_id)
    assert found is not None
    assert found.target_topics == ("python", "tooling")
    assert found.daily_budget_cents == 10_000


def test_sqlite_update_campaign_status_persists(tmp_path):
    db = str(tmp_path / "adv.sqlite")
    store = SqliteAdvertiserStore(db_path=db)
    a = create_advertiser(store, display_name="X", sector="x",
                          contact_email="x@y.com")
    c = create_campaign(store, advertiser_id=a.advertiser_id,
                        sector="x", intent="t", creative_headline="h",
                        creative_url="u", daily_budget_cents=100,
                        status=CampaignStatus.DRAFT)
    update_campaign_status(store, campaign_id=c.campaign_id,
                           new_status=CampaignStatus.ACTIVE)
    reopened = SqliteAdvertiserStore(db_path=db)
    found = reopened.get_campaign(c.campaign_id)
    assert found is not None
    assert found.status == CampaignStatus.ACTIVE
