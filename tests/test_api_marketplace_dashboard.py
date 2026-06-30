"""Marketplace metrics + payout dashboard API route tests."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


@pytest.fixture()
def isolated_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-api-marketplace-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    try:
        from substrate.graph import ensure_initialized

        ensure_initialized(db_path)
        yield db_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _client() -> TestClient:
    return TestClient(
        create_app(register_wrestling=False, register_providers=False),
    )


def test_marketplace_snapshot_get_returns_live_empty_state(isolated_db):
    c = _client()

    resp = c.get("/marketplace/snapshot")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["creators"]["creator_count"] == 0
    assert body["publishers"]["status_counts"]["total"] == 0
    assert body["advertisers"]["advertiser_count_current"] == 0
    assert body["health"] in {"watch", "unhealthy"}


def test_marketplace_snapshot_post_applies_operator_overrides(isolated_db):
    c = _client()

    resp = c.post(
        "/marketplace/snapshot",
        json={
            "creator_paid_cents": {"creator-a": 1500, "creator-b": 2500},
            "current_advertiser_spend": {"adv-a": 5000},
            "prior_advertiser_spend": {"adv-a": 4000, "adv-b": 1000},
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["creators"]["creator_count"] == 2
    assert body["creators"]["total_paid_cents"] == 4000
    assert body["advertisers"]["retained_advertiser_count"] == 1
    assert body["advertisers"]["churned_advertiser_count"] == 1


def test_marketplace_snapshot_post_rejects_bad_override(isolated_db):
    c = _client()

    resp = c.post(
        "/marketplace/snapshot",
        json={"current_advertiser_spend": {"adv-bad": -1}},
    )

    assert resp.status_code == 422
    assert resp.json()["detail"]["error"]["code"] == "invalid_marketplace_override"


def test_marketplace_snapshot_uses_operator_auth_when_configured(isolated_db, monkeypatch):
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "op-secret")
    c = _client()

    blocked = c.get("/marketplace/snapshot")
    allowed = c.get(
        "/marketplace/snapshot",
        headers={"Authorization": "Bearer op-secret"},
    )

    assert blocked.status_code == 401
    assert blocked.json()["error"]["code"] == "operator_auth_required"
    assert allowed.status_code == 200


def test_operator_payout_dashboard_empty(isolated_db):
    c = _client()

    resp = c.get("/operator/payouts/dashboard")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["current_month_label"]
    assert body["lines"] == []
    assert body["platform_residual_month_cents"] == 0
    assert body["unallocated_rounding_month_cents"] == 0


def test_operator_payout_dashboard_uses_operator_auth_when_configured(
    isolated_db, monkeypatch,
):
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "op-secret")
    c = _client()

    blocked = c.get("/operator/payouts/dashboard")
    allowed = c.get(
        "/operator/payouts/dashboard",
        headers={"Authorization": "Bearer op-secret"},
    )

    assert blocked.status_code == 401
    assert blocked.json()["error"]["code"] == "operator_auth_required"
    assert allowed.status_code == 200


def test_operator_payout_dashboard_aggregates_transfers_and_rollovers(isolated_db):
    from runtime.db_lock import connect_write
    from substrate.billing.kyc import KycRecord, KycState, save_record

    with connect_write(isolated_db, purpose="test:seed_dashboard") as con:
        con.execute(
            """
            INSERT INTO ip_holders (
                ip_holder_id, display_name, legal_contact_email, status,
                escrow_balance_usd
            ) VALUES ('pub-1', 'MIT Press', 'legal@mit.example', 'claimed', 12.34)
            """
        )
        con.execute(
            """
            INSERT INTO payout_transfers (
                transfer_attempt_id, decision_id, stripe_transfer_id,
                recipient_account_id, amount_usd_cents, status, note
            ) VALUES
                ('xfer-creator', 'dec-creator', NULL, 'creator-1', 1200, 'transferred', 'ok'),
                ('xfer-publisher', 'dec-publisher', NULL, 'pub-1', 700, 'skipped_escrow', 'held'),
                ('xfer-platform', 'dec-platform', NULL, NULL, 300, 'skipped_platform', 'residual'),
                ('xfer-failed', 'dec-failed', NULL, 'creator-1', 9999, 'failed', 'ignored')
            """
        )
        save_record(
            con,
            KycRecord(
                recipient_ref="creator-1",
                state=KycState.COMPLETED,
                last_state_change_at="2026-06-01T00:00:00Z",
                operator_notes="seeded",
            ),
        )
        con.execute(
            """
            INSERT INTO rollover_ledger (
                recipient_ref, balance_cents, accrual_started_month, state
            ) VALUES ('creator-2', 450, 100, 'accruing')
            """
        )

    c = _client()
    resp = c.get("/operator/payouts/dashboard")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    by_ref = {line["recipient_ref"]: line for line in body["lines"]}
    assert by_ref["creator-1"]["recipient_kind"] == "creator"
    assert by_ref["creator-1"]["current_month_cents"] == 1200
    assert by_ref["creator-1"]["lifetime_cents"] == 1200
    assert by_ref["creator-1"]["kyc_complete"] is True
    assert by_ref["pub-1"]["recipient_kind"] == "publisher"
    assert by_ref["pub-1"]["recipient_name"] == "MIT Press"
    assert by_ref["pub-1"]["status"] == "active"
    assert by_ref["creator-2"]["current_month_cents"] == 450
    assert by_ref["creator-2"]["status"] == "pending_kyc"
    assert body["platform_residual_month_cents"] == 300


def test_operator_payout_dashboard_separates_lifetime_from_current_month(
    isolated_db,
):
    from runtime.db_lock import connect_write

    with connect_write(isolated_db, purpose="test:seed_historical_dashboard") as con:
        con.execute(
            """
            INSERT INTO payout_transfers (
                transfer_attempt_id, decision_id, stripe_transfer_id,
                recipient_account_id, amount_usd_cents, status, note, initiated_at
            ) VALUES
                ('xfer-old', 'dec-old', NULL, 'creator-1', 900, 'transferred',
                 'historical', TIMESTAMP '2020-01-01 00:00:00'),
                ('xfer-now', 'dec-now', NULL, 'creator-1', 100, 'transferred',
                 'current', CURRENT_TIMESTAMP)
            """
        )

    c = _client()
    resp = c.get("/operator/payouts/dashboard")

    assert resp.status_code == 200, resp.text
    (line,) = resp.json()["lines"]
    assert line["recipient_ref"] == "creator-1"
    assert line["current_month_cents"] == 100
    assert line["lifetime_cents"] == 1000


def test_payout_dashboard_adapter_imports_no_payout_initiator():
    source = Path("interfaces/research/api/payout_dashboard.py").read_text(
        encoding="utf-8",
    )
    assert "transfer_initiator" not in source
    assert "stripe_connect" not in source


def test_operator_payout_dashboard_source_failures_are_not_empty_states(
    isolated_db,
):
    from runtime.db_lock import connect_write

    with connect_write(isolated_db, purpose="test:break_dashboard_source") as con:
        con.execute("DROP TABLE payout_transfers")
        con.execute("CREATE TABLE payout_transfers (broken TEXT)")

    c = _client()
    resp = c.get("/operator/payouts/dashboard")

    assert resp.status_code == 503
    assert resp.json()["detail"]["error"]["code"] == (
        "payout_dashboard_source_unavailable"
    )
