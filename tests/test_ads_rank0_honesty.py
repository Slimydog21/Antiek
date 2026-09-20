"""Rank 0 website ads honesty — no fake cents, no MAX-on-web."""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient

from substrate.ad_inventory.rank0_honesty import (
    SPEAK_CONTRIBUTOR_SHARE,
    SPEAK_PLATFORM_SHARE,
    assert_unpriced_zero,
    website_ads_honesty,
)
from substrate.trust_center import build_publication


def test_website_ads_honesty_shape():
    h = website_ads_honesty()
    assert h["surface"] == "website"
    assert h["serving_model"] == "antiek_owned_creatives"
    assert h["max_sdk_on_web"] is False
    assert h["fill_ladder"] == ["house", "manual_sponsor", "lead_gen"]
    assert h["price_status_default"] == "unpriced"
    assert h["revenue_usd_cents_until_pricing"] == 0
    assert h["speak_contributor_share"] == SPEAK_CONTRIBUTOR_SHARE == 0.70
    assert h["speak_platform_share"] == SPEAK_PLATFORM_SHARE == 0.30
    assert h["money_model"] == "no_fake_cents_until_settled_pricing"
    assert "applovin-website-mvp" in h["decision_ref"]
    assert h["settlement_open"] is False
    assert h["settlement_path"] == "settle_fill_decision"
    assert "rank_0_1_pricing_authority_ref" in h["settlement_requires"]
    assert h["paid_fill_gated"] is True
    assert h["paid_fill_default"] == "unpriced_zero"
    assert h["applovin_alignment"] == "antiek_owned_creatives_no_max_sdk"
    assert "active_advertiser_id" in h["paid_fill_requires"]
    assert "paid-fill-gated" in h["paid_fill_decision_ref"]


def test_assert_unpriced_zero_rejects_fake_cents():
    assert_unpriced_zero(0, "unpriced")
    with pytest.raises(ValueError, match="fake cents"):
        assert_unpriced_zero(1, "unpriced")


def test_trust_publication_includes_website_ads():
    payload = build_publication()
    assert payload.website_ads["max_sdk_on_web"] is False
    assert payload.as_dict()["website_ads"]["revenue_usd_cents_until_pricing"] == 0


@pytest.fixture()
def isolated_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-ads-rank0-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    try:
        from substrate.graph import ensure_initialized

        ensure_initialized(db_path)
        yield db_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_fills_response_carries_honesty_and_stays_unpriced(isolated_db):
    from interfaces.research.api.app import create_app

    client = TestClient(create_app())
    resp = client.post(
        "/api/ad/fills",
        json={
            "window_id": "win:rank0-honesty-test",
            "lens": "read",
            "positions": ["bottom"],
            "document_id": None,
            "page_index": None,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "honesty" in body
    h = body["honesty"]
    assert h["max_sdk_on_web"] is False
    assert h["revenue_usd_cents_until_pricing"] == 0
    assert h["money_model"] == "no_fake_cents_until_settled_pricing"
    for fill in body["fills"]:
        assert fill["revenue_usd_cents"] == 0
        assert fill["price_status"] == "unpriced"


def test_trust_center_endpoint_publishes_website_ads(isolated_db):
    from interfaces.research.api.app import create_app

    client = TestClient(create_app())
    resp = client.get("/trust-center")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["website_ads"]["serving_model"] == "antiek_owned_creatives"
    assert body["website_ads"]["max_sdk_on_web"] is False
    assert body["website_ads"]["paid_fill_gated"] is True
    assert body["website_ads"]["paid_fill_default"] == "unpriced_zero"
