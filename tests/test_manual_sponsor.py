"""Manual sponsor Phase-2 creative resolver + research-lens ledger fill."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from substrate.ad_inventory.manual_sponsor import (
    bidding_policy_wire,
    resolve_manual_sponsor_item,
)


def test_resolve_disabled_by_default():
    assert resolve_manual_sponsor_item(env={}) is None


def test_resolve_requires_enable_name_and_landing():
    assert (
        resolve_manual_sponsor_item(
            env={
                "ANTIEK_MANUAL_SPONSOR_ENABLED": "1",
                "ANTIEK_MANUAL_SPONSOR_NAME": "Acme",
            }
        )
        is None
    )
    item = resolve_manual_sponsor_item(
        env={
            "ANTIEK_MANUAL_SPONSOR_ENABLED": "1",
            "ANTIEK_MANUAL_SPONSOR_NAME": "Acme Labs",
            "ANTIEK_MANUAL_SPONSOR_LANDING_URL": "https://example.com/",
        }
    )
    assert item is not None
    assert item.inventory_id == "manual_sponsor:operator"
    assert item.advertiser_display_name == "Acme Labs"
    assert item.landing_url == "https://example.com/"
    assert item.creative_url == "/mark-32.png"
    assert item.cpm_usd == Decimal("0")
    assert "research" in item.target_topics


def test_bidding_policy_wire_matches_enum():
    assert bidding_policy_wire() == "manual_sponsor"


@pytest.fixture()
def isolated_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-manual-sponsor-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    try:
        from substrate.graph import ensure_initialized

        ensure_initialized(db_path)
        yield db_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_research_fills_persist_manual_sponsor_unpriced(isolated_db, monkeypatch):
    """POST /api/ad/fills with lens=research persists $0 unpriced sponsor fill.

    No fake revenue: cpm is 0 and price_status stays unpriced. bidding_policy
    is stamped in fills_json for ledger audit only.
    """
    monkeypatch.setenv("ANTIEK_MANUAL_SPONSOR_ENABLED", "1")
    monkeypatch.setenv("ANTIEK_MANUAL_SPONSOR_NAME", "Acme Labs")
    monkeypatch.setenv(
        "ANTIEK_MANUAL_SPONSOR_LANDING_URL", "https://example.com/"
    )
    monkeypatch.setenv(
        "ANTIEK_MANUAL_SPONSOR_CREATIVE_URL", "https://example.com/mark.png"
    )

    client = TestClient(
        create_app(register_wrestling=False, register_providers=False)
    )
    resp = client.post(
        "/api/ad/fills",
        json={
            "window_id": "win:research:manual-sponsor:syn-test",
            "lens": "research",
            "positions": ["bottom"],
            "document_id": None,
            "page_index": None,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    fill = body["fills"][0]
    assert fill["kind"] == "ad"
    assert fill["revenue_usd_cents"] == 0
    assert fill["price_status"] == "unpriced"
    assert fill["ad"]["inventory_id"] == "manual_sponsor:operator"
    assert fill["ad"]["advertiser_display_name"] == "Acme Labs"

    from runtime.db_lock import connect_read

    con = connect_read(isolated_db)
    try:
        row = con.execute(
            "SELECT revenue_usd_cents, price_status, fills_json "
            "FROM ad_fill_decisions WHERE window_id = ?",
            ["win:research:manual-sponsor:syn-test"],
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    assert row[0] == 0
    assert row[1] == "unpriced"
    fills = json.loads(row[2])
    assert fills[0]["bidding_policy"] == "manual_sponsor"


def test_research_fills_house_when_sponsor_disabled(isolated_db, monkeypatch):
    monkeypatch.delenv("ANTIEK_MANUAL_SPONSOR_ENABLED", raising=False)
    client = TestClient(
        create_app(register_wrestling=False, register_providers=False)
    )
    resp = client.post(
        "/api/ad/fills",
        json={
            "window_id": "win:research:house-only",
            "lens": "research",
            "positions": ["bottom"],
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["fills"][0]["kind"] == "house"
    assert resp.json()["fills"][0]["revenue_usd_cents"] == 0
