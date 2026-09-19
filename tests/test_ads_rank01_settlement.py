"""Rank 0.1 fill settlement — settled only behind legal + pricing gates."""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest

from runtime.db_lock import connect_write
from substrate.ad_inventory.advertiser_onboarding import (
    activate_advertiser,
    approve_advertiser,
    save_record,
    submit_application,
)
from substrate.ad_inventory.fill_decisions import decide_fills
from substrate.ad_inventory.fill_settlement import (
    FillSettlementError,
    settle_fill_decision,
)
from substrate.ad_inventory.rank0_honesty import (
    PAID_FILL_REQUIRES,
    SETTLEMENT_REQUIRES,
    SettlementGateError,
    assert_paid_fill_advertiser_active,
    assert_settlement_allowed,
    website_ads_honesty,
)


@pytest.fixture()
def db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-rank01-")
    path = os.path.join(tmpdir, "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", path)
    try:
        from substrate.graph import ensure_initialized

        ensure_initialized(path)
        yield path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _seed_ad_fill(con):
    return decide_fills(
        con,
        owner_user_id="__operator__",
        window_id="win:rank01",
        document_id=None,
        page_index=None,
        lens="read",
        positions=("bottom",),
        select_fills=lambda: [
            {
                "position": "bottom",
                "kind": "ad",
                "revenue_usd_cents": 0,
                "ad": {
                    "inventory_id": "inv:1",
                    "advertiser_display_name": "Acme",
                    "creative_url": "/mark-32.png",
                    "landing_url": "https://example.com/",
                },
                "house": None,
            }
        ],
    )



def _seed_active_advertiser(con, advertiser_id: str = "adv:acme"):
    """PENDING → APPROVED → ACTIVE under legal gate (no invented budget cents)."""
    from substrate.ad_inventory.advertiser_onboarding import AdvertiserRegistry

    registry = AdvertiserRegistry()
    pending = submit_application(
        registry,
        display_name="Acme",
        contact_email="ads@example.com",
        verticals=("research",),
        audience_intents=("academic",),
        advertiser_id=advertiser_id,
    )
    aid = pending.advertiser_id
    approve_advertiser(registry, advertiser_id=aid)
    activate_advertiser(registry, advertiser_id=aid, legal_gate_passed=True)
    for rec in registry.records:
        save_record(con, rec)
    return aid

def _seed_house_fill(con):
    return decide_fills(
        con,
        owner_user_id="__operator__",
        window_id="win:house",
        document_id=None,
        page_index=None,
        lens="read",
        positions=("bottom",),
        select_fills=lambda: [
            {
                "position": "bottom",
                "kind": "house",
                "revenue_usd_cents": 0,
                "ad": None,
                "house": None,
            }
        ],
    )


def test_honesty_envelope_rank01_gates_closed():
    h = website_ads_honesty()
    assert h["settlement_open"] is False
    assert h["settlement_path"] == "settle_fill_decision"
    assert h["settlement_requires"] == list(SETTLEMENT_REQUIRES)
    assert h["price_status_default"] == "unpriced"
    assert h["revenue_usd_cents_until_pricing"] == 0
    assert "rank01" in h["rank01_decision_ref"]
    assert h["paid_fill_gated"] is True
    assert h["paid_fill_requires"] == list(PAID_FILL_REQUIRES)
    assert h["applovin_alignment"] == "antiek_owned_creatives_no_max_sdk"


def test_assert_settlement_denied_without_legal():
    with pytest.raises(SettlementGateError, match="legal_gate"):
        assert_settlement_allowed(
            revenue_usd_cents=100,
            legal_gate_passed=False,
            pricing_authority_ref="budget:acme-2026-09",
        )


def test_assert_settlement_denied_without_authority():
    with pytest.raises(SettlementGateError, match="pricing_authority"):
        assert_settlement_allowed(
            revenue_usd_cents=100,
            legal_gate_passed=True,
            pricing_authority_ref="  ",
        )


def test_assert_settlement_denied_zero_cents():
    with pytest.raises(SettlementGateError, match="> 0"):
        assert_settlement_allowed(
            revenue_usd_cents=0,
            legal_gate_passed=True,
            pricing_authority_ref="budget:acme",
        )


def test_assert_paid_fill_requires_active():
    with pytest.raises(SettlementGateError, match="advertiser_id required"):
        assert_paid_fill_advertiser_active(
            advertiser_id=None, advertiser_status="active"
        )
    with pytest.raises(SettlementGateError, match="not active"):
        assert_paid_fill_advertiser_active(
            advertiser_id="adv:acme", advertiser_status="approved"
        )
    assert_paid_fill_advertiser_active(
        advertiser_id="adv:acme", advertiser_status="active"
    )




def test_decide_fills_stays_unpriced_zero(db):
    with connect_write(db, purpose="test:decide", timeout_s=10) as con:
        d = _seed_ad_fill(con)
    assert d.price_status == "unpriced"
    assert d.revenue_usd_cents == 0


def test_settle_denied_without_legal(db):
    with connect_write(db, purpose="test:settle-deny-legal", timeout_s=10) as con:
        d = _seed_ad_fill(con)
        with pytest.raises(SettlementGateError, match="legal_gate"):
            settle_fill_decision(
                con,
                decision_id=d.decision_id,
                revenue_usd_cents=250,
                legal_gate_passed=False,
                pricing_authority_ref="budget:acme",
            )


def test_settle_denied_for_house_only(db):
    with connect_write(db, purpose="test:settle-deny-house", timeout_s=10) as con:
        d = _seed_house_fill(con)
        with pytest.raises(FillSettlementError, match="house-only"):
            settle_fill_decision(
                con,
                decision_id=d.decision_id,
                revenue_usd_cents=250,
                legal_gate_passed=True,
                pricing_authority_ref="budget:acme",
            )


def test_settle_denied_without_advertiser(db):
    with connect_write(db, purpose="test:settle-deny-adv", timeout_s=10) as con:
        d = _seed_ad_fill(con)
        with pytest.raises(SettlementGateError, match="advertiser_id required"):
            settle_fill_decision(
                con,
                decision_id=d.decision_id,
                revenue_usd_cents=250,
                legal_gate_passed=True,
                pricing_authority_ref="budget:acme",
                advertiser_id=None,
            )


def test_settle_denied_for_non_active_advertiser(db):
    with connect_write(db, purpose="test:settle-deny-status", timeout_s=10) as con:
        d = _seed_ad_fill(con)
        # unknown id → not active
        with pytest.raises(SettlementGateError, match="not active"):
            settle_fill_decision(
                con,
                decision_id=d.decision_id,
                revenue_usd_cents=250,
                legal_gate_passed=True,
                pricing_authority_ref="budget:acme",
                advertiser_id="adv:unknown",
            )


def test_settle_ok_with_legal_and_authority(db):
    with connect_write(db, purpose="test:settle-ok", timeout_s=10) as con:
        d = _seed_ad_fill(con)
        aid = _seed_active_advertiser(con, advertiser_id="adv:acme")
        settled = settle_fill_decision(
            con,
            decision_id=d.decision_id,
            revenue_usd_cents=250,
            legal_gate_passed=True,
            pricing_authority_ref="budget:acme-2026-09",
            advertiser_id=aid,
        )
        assert settled.price_status == "settled"
        assert settled.revenue_usd_cents == 250
        # Idempotent same cents
        again = settle_fill_decision(
            con,
            decision_id=d.decision_id,
            revenue_usd_cents=250,
            legal_gate_passed=True,
            pricing_authority_ref="budget:acme-2026-09",
            advertiser_id=aid,
        )
        assert again.price_status == "settled"
        assert again.revenue_usd_cents == 250


def test_resolve_window_value_only_when_settled(db):
    from interfaces.research.api.ad_routes import resolve_window_value_cents

    with connect_write(db, purpose="test:resolve", timeout_s=10) as con:
        d = _seed_ad_fill(con)
        assert (
            resolve_window_value_cents(
                owner_user_id="__operator__",
                window_id="win:rank01",
                con=con,
            )
            == 0
        )
        aid = _seed_active_advertiser(con, advertiser_id="adv:acme-resolve")
        settle_fill_decision(
            con,
            decision_id=d.decision_id,
            revenue_usd_cents=400,
            legal_gate_passed=True,
            pricing_authority_ref="budget:acme",
            advertiser_id=aid,
        )
        assert (
            resolve_window_value_cents(
                owner_user_id="__operator__",
                window_id="win:rank01",
                con=con,
            )
            == 400
        )


def test_fills_api_honesty_reports_settlement_closed(db):
    from fastapi.testclient import TestClient

    from interfaces.research.api.app import create_app

    client = TestClient(create_app())
    resp = client.post(
        "/api/ad/fills",
        json={
            "window_id": "win:honesty-rank01",
            "lens": "read",
            "positions": ["bottom"],
            "document_id": None,
            "page_index": None,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["fills"][0]["price_status"] == "unpriced"
    assert body["fills"][0]["revenue_usd_cents"] == 0
    h = body["honesty"]
    assert h["settlement_open"] is False
    assert h["settlement_path"] == "settle_fill_decision"
    assert "rank_0_1_pricing_authority_ref" in h["settlement_requires"]
    assert h["paid_fill_gated"] is True
    assert "active_advertiser_id" in h["paid_fill_requires"]
