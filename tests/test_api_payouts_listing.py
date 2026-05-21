"""Payout transfers audit listing endpoint tests."""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


@pytest.fixture()
def isolated_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-payout-listing-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    try:
        from substrate.graph import ensure_initialized
        ensure_initialized(db_path)
        yield db_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _client():
    return TestClient(create_app(register_wrestling=False))


def _seed_transfer(
    db_path: str,
    *,
    status: str,
    recipient_account_id: str | None = "acct_X",
    amount_usd_cents: int = 100,
) -> str:
    """Seed one transfer row directly via the substrate (bypasses the
    Stripe provider; the row format matches transfer_initiator output)."""
    from runtime.db_lock import connect_write

    attempt_id = f"xfer-{uuid.uuid4().hex[:10]}"
    decision_id = f"rs-{uuid.uuid4().hex[:10]}"
    with connect_write(db_path, purpose="test:seed_payout") as con:
        con.execute(
            "INSERT INTO payout_transfers ("
            "transfer_attempt_id, decision_id, stripe_transfer_id, "
            "recipient_account_id, amount_usd_cents, status, note"
            ") VALUES (?, ?, NULL, ?, ?, ?, 'seeded')",
            [attempt_id, decision_id, recipient_account_id,
             amount_usd_cents, status],
        )
    return attempt_id


# ── Empty state ────────────────────────────────────────────────────


def test_payouts_listing_empty(isolated_db):
    client = _client()
    resp = client.get("/payouts/transfers")
    assert resp.status_code == 200
    assert resp.json() == {"transfers": []}


# ── Newest first ordering ─────────────────────────────────────────


def test_payouts_listing_newest_first(isolated_db):
    """initiated_at ascends naturally with sequential inserts → the
    endpoint orders DESC, so the listing returns latest-first."""
    client = _client()
    for _ in range(3):
        _seed_transfer(isolated_db, status="transferred")
    resp = client.get("/payouts/transfers")
    body = resp.json()
    assert len(body["transfers"]) == 3
    timestamps = [t["initiated_at"] for t in body["transfers"]]
    assert timestamps == sorted(timestamps, reverse=True)


# ── Status filter ─────────────────────────────────────────────────


def test_payouts_listing_filter_by_status(isolated_db):
    client = _client()
    _seed_transfer(isolated_db, status="transferred")
    _seed_transfer(isolated_db, status="skipped_escrow")
    _seed_transfer(isolated_db, status="failed")
    resp = client.get("/payouts/transfers?status=transferred")
    body = resp.json()
    assert len(body["transfers"]) == 1
    assert body["transfers"][0]["status"] == "transferred"


# ── Recipient filter ──────────────────────────────────────────────


def test_payouts_listing_filter_by_recipient(isolated_db):
    client = _client()
    _seed_transfer(isolated_db, status="transferred", recipient_account_id="acct_X")
    _seed_transfer(isolated_db, status="transferred", recipient_account_id="acct_Y")
    _seed_transfer(isolated_db, status="transferred", recipient_account_id="acct_X")
    resp = client.get("/payouts/transfers?recipient_account_id=acct_X")
    body = resp.json()
    assert len(body["transfers"]) == 2
    for t in body["transfers"]:
        assert t["recipient_account_id"] == "acct_X"


# ── Limit ──────────────────────────────────────────────────────────


def test_payouts_listing_respects_limit(isolated_db):
    client = _client()
    for _ in range(5):
        _seed_transfer(isolated_db, status="transferred")
    resp = client.get("/payouts/transfers?limit=2")
    body = resp.json()
    assert len(body["transfers"]) == 2


# ── Composite filter ──────────────────────────────────────────────


def test_payouts_listing_combines_filters(isolated_db):
    client = _client()
    _seed_transfer(isolated_db, status="transferred", recipient_account_id="acct_X")
    _seed_transfer(isolated_db, status="failed", recipient_account_id="acct_X")
    _seed_transfer(isolated_db, status="transferred", recipient_account_id="acct_Y")
    resp = client.get(
        "/payouts/transfers?status=transferred&recipient_account_id=acct_X",
    )
    body = resp.json()
    assert len(body["transfers"]) == 1
    assert body["transfers"][0]["status"] == "transferred"
    assert body["transfers"][0]["recipient_account_id"] == "acct_X"
