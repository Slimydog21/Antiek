from __future__ import annotations

import os
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


@pytest.fixture()
def isolated_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-ad-fill-decisions-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    from substrate.graph import ensure_initialized

    ensure_initialized(db_path)
    try:
        yield db_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _client() -> TestClient:
    return TestClient(create_app(register_wrestling=False, register_providers=False))


def _seed_advertiser_and_inventory(db_path: str, *, status: str = "active") -> None:
    from runtime.db_lock import connect_write
    from substrate.ad_inventory.inventory_persistence import upsert_inventory

    with connect_write(db_path, purpose="test:seed-fill-inventory") as con:
        con.execute(
            """
            INSERT INTO advertisers (
                attempt_id, advertiser_id, display_name, contact_email,
                status, submitted_at, last_status_change_at
            ) VALUES ('attempt-1', 'adv-1', 'Buyer', 'buyer@example.test',
                      ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            [status],
        )
        upsert_inventory(
            con,
            inventory_id="inv-1",
            advertiser_id="adv-1",
            advertiser_display_name="Buyer",
            creative_url="https://cdn.example.test/ad.png",
            landing_url="https://buyer.example.test/",
            cpm_usd_cents=2500,
            target_topics=("read",),
        )


def _request(window_id: str = "window-1") -> dict:
    return {
        "window_id": window_id,
        "document_id": "doc-1",
        "page_index": 3,
        "lens": "read",
        "positions": ["top", "bottom", "left"],
    }


def test_multi_edge_fill_uses_only_active_advertiser_inventory(isolated_db):
    _seed_advertiser_and_inventory(isolated_db)
    response = _client().post("/api/ad/fills", json=_request())
    assert response.status_code == 200, response.text
    body = response.json()
    assert [fill["position"] for fill in body["fills"]] == _request()["positions"]
    assert {fill["kind"] for fill in body["fills"]} == {"ad"}
    assert {fill["ad"]["inventory_id"] for fill in body["fills"]} == {"inv-1"}
    assert all(fill["revenue_usd_cents"] == 0 for fill in body["fills"])
    assert all(fill["price_status"] == "unpriced" for fill in body["fills"])
    assert set(body) == {"window_id", "fills"}


@pytest.mark.parametrize("status", ["approved", "suspended", "churned"])
def test_non_active_advertiser_can_never_fill(isolated_db, status):
    _seed_advertiser_and_inventory(isolated_db, status=status)
    body = _client().post("/api/ad/fills", json=_request()).json()
    assert {fill["kind"] for fill in body["fills"]} == {"house"}
    assert all(fill["revenue_usd_cents"] == 0 for fill in body["fills"])


def test_exact_retry_replays_snapshot_after_inventory_deactivation(isolated_db):
    _seed_advertiser_and_inventory(isolated_db)
    client = _client()
    first = client.post("/api/ad/fills", json=_request()).json()

    from runtime.db_lock import connect_write
    from substrate.ad_inventory.inventory_persistence import deactivate_inventory

    with connect_write(isolated_db, purpose="test:deactivate") as con:
        deactivate_inventory(con, inventory_id="inv-1")

    replay = client.post("/api/ad/fills", json=_request()).json()
    assert replay["fills"][0]["fill_decision_id"] == first["fills"][0]["fill_decision_id"]
    assert replay["fills"] == first["fills"]

    fresh = client.post("/api/ad/fills", json=_request("window-2")).json()
    assert fresh["fills"][0]["fill_decision_id"] != first["fills"][0]["fill_decision_id"]
    assert {fill["kind"] for fill in fresh["fills"]} == {"house"}


def test_concurrent_exact_requests_persist_one_decision(isolated_db):
    _seed_advertiser_and_inventory(isolated_db)
    client = _client()

    def fetch():
        response = client.post("/api/ad/fills", json=_request())
        assert response.status_code == 200, response.text
        return response.json()

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(lambda _: fetch(), range(4)))
    assert len({outcome["fills"][0]["fill_decision_id"] for outcome in outcomes}) == 1
    from runtime.db_lock import connect_read

    con = connect_read(isolated_db)
    try:
        assert con.execute("SELECT count(*) FROM ad_fill_decisions").fetchone()[0] == 1
    finally:
        con.close()


def test_latest_advertiser_state_controls_serving(isolated_db):
    _seed_advertiser_and_inventory(isolated_db)
    from runtime.db_lock import connect_write

    with connect_write(isolated_db, purpose="test:suspend-latest") as con:
        con.execute(
            """
            INSERT INTO advertisers (
                attempt_id, advertiser_id, display_name, contact_email,
                status, submitted_at, last_status_change_at
            ) VALUES ('attempt-2', 'adv-1', 'Buyer', 'buyer@example.test',
                      'suspended', CURRENT_TIMESTAMP,
                      CURRENT_TIMESTAMP + INTERVAL 1 SECOND)
            """
        )
    body = _client().post("/api/ad/fills", json=_request()).json()
    assert {fill["kind"] for fill in body["fills"]} == {"house"}


def test_invalid_or_duplicate_edges_fail_closed(isolated_db):
    client = _client()
    for positions in (["top", "top"], ["top", "middle"], []):
        payload = _request()
        payload["positions"] = positions
        response = client.post("/api/ad/fills", json=payload)
        assert response.status_code == 422


def test_client_cannot_supply_price_or_winner(isolated_db):
    payload = _request()
    payload["revenue_usd_cents"] = 99_999
    payload["inventory_id"] = "invented-winner"
    response = _client().post("/api/ad/fills", json=payload)
    assert response.status_code == 422


def test_changed_request_for_same_owner_window_conflicts(isolated_db):
    client = _client()
    first = client.post("/api/ad/fills", json=_request())
    assert first.status_code == 200
    changed = _request()
    changed["positions"] = ["top"]
    response = client.post("/api/ad/fills", json=changed)
    assert response.status_code == 409
    assert response.json() == {"detail": "ad_fill_window_conflict"}


def test_window_namespace_is_unique_at_sql_layer():
    import duckdb

    from substrate.ad_inventory.fill_decisions import decide_fills

    con = duckdb.connect(":memory:")
    common = {
        "owner_user_id": "owner-1",
        "window_id": "window-1",
        "document_id": None,
        "page_index": None,
        "lens": "read",
        "positions": ("top",),
        "select_fills": lambda: [{
            "position": "top", "kind": "house", "ad": None,
            "house": None, "revenue_usd_cents": 0,
        }],
    }
    decide_fills(con, **common)
    with pytest.raises(duckdb.ConstraintException):
        con.execute(
            """
            INSERT INTO ad_fill_decisions (
                decision_id, request_fingerprint, owner_user_id, window_id,
                lens, positions_json, fills_json, revenue_usd_cents, price_status
            ) VALUES ('manual', 'different', 'owner-1', 'window-1', 'read',
                      '[]', '[]', 0, 'unpriced')
            """
        )


def test_legacy_client_priced_impression_route_is_tombstoned(isolated_db):
    client = _client()
    response = client.post(
        "/ad-impressions",
        json={
            "impression_id": "imp-client-priced",
            "inventory_id": "inv-fake",
            "page_id": "page-1",
            "revenue_usd_cents": 500_000,
            "attribution_shares": {"doc-1": 1.0},
            "document_to_recipient": {"doc-1": ["creator", "attacker", False]},
        },
    )
    assert response.status_code == 410
    assert response.json() == {
        "detail": "client_priced_ad_impressions_disabled"
    }

    from runtime.db_lock import connect_read

    con = connect_read(isolated_db)
    try:
        assert con.execute("SELECT count(*) FROM payout_decisions").fetchone()[0] == 0
    finally:
        con.close()


def test_decision_ledger_selector_runs_once_on_replay():
    import duckdb

    from substrate.ad_inventory.fill_decisions import decide_fills

    con = duckdb.connect(":memory:")
    calls = 0

    def select():
        nonlocal calls
        calls += 1
        return [
            {
                "position": "top",
                "kind": "house",
                "revenue_usd_cents": 0,
                "ad": None,
                "house": None,
            }
        ]

    kwargs = {
        "owner_user_id": "owner-1",
        "window_id": "window-1",
        "document_id": "doc-1",
        "page_index": 3,
        "lens": "read",
        "positions": ("top",),
        "select_fills": select,
    }
    first = decide_fills(con, **kwargs)
    second = decide_fills(con, **kwargs)
    assert calls == 1
    assert first.decision_id == second.decision_id
    assert first.replayed is False
    assert second.replayed is True
