"""Creator payout self-service API tests."""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


@pytest.fixture()
def isolated_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-api-creator-payouts-")
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


def test_me_payouts_returns_current_user_rollover_and_transfers(isolated_db):
    from runtime.db_lock import connect_write

    with connect_write(isolated_db, purpose="test:seed_me_payouts") as con:
        con.execute(
            """
            INSERT INTO rollover_ledger (
                recipient_ref, balance_cents, accrual_started_month, state
            ) VALUES ('__operator__', 450, 100, 'notice_sent')
            """
        )
        con.execute(
            """
            INSERT INTO payout_transfers (
                transfer_attempt_id, decision_id, stripe_transfer_id,
                recipient_account_id, amount_usd_cents, status, note
            ) VALUES
                ('xfer-me-paid', 'dec-me-paid', 'tr_me', '__operator__', 1200,
                 'transferred', 'paid'),
                ('xfer-me-failed', 'dec-me-failed', NULL, '__operator__', 300,
                 'failed', 'retry later'),
                ('xfer-other', 'dec-other', NULL, 'other-user', 9999,
                 'transferred', 'must not leak')
            """
        )

    resp = _client().get("/me/payouts")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user_id"] == "__operator__"
    assert body["current_balance_cents"] == 450
    assert body["minimum_payout_cents"] == 1000
    assert body["rollover_state"] == "notice_sent"
    assert body["rollover_started_month"] == 100
    assert body["total_paid_cents"] == 1200
    assert body["accrual_history"] == [
        {
            "at": body["accrual_history"][0]["at"],
            "kind": "notice_sent",
            "cents": 450,
        },
    ]
    transfer_ids = {t["transfer_attempt_id"] for t in body["transfers"]}
    assert transfer_ids == {"xfer-me-paid", "xfer-me-failed"}
    assert all("decision_id" not in t for t in body["transfers"])


def test_me_payouts_empty_state(isolated_db):
    resp = _client().get("/me/payouts")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user_id"] == "__operator__"
    assert body["current_balance_cents"] == 0
    assert body["minimum_payout_cents"] == 1000
    assert body["rollover_state"] == "accruing"
    assert body["rollover_started_month"] is None
    assert body["accrual_history"] == []
    assert body["transfers"] == []
    assert body["total_paid_cents"] == 0


def test_me_payouts_uses_operator_auth_when_configured(isolated_db, monkeypatch):
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "op-secret")
    c = _client()

    blocked = c.get("/me/payouts")
    allowed = c.get(
        "/me/payouts",
        headers={"Authorization": "Bearer op-secret"},
    )

    assert blocked.status_code == 401
    assert blocked.json()["error"]["code"] == "operator_auth_required"
    assert allowed.status_code == 200

