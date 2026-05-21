"""Advertiser onboarding API tests (Sprint 23-24 phase 5)."""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


@pytest.fixture()
def isolated_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-api-advertisers-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    try:
        from substrate.graph import ensure_initialized
        ensure_initialized(db_path)
        yield db_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _client():
    return TestClient(
        create_app(register_wrestling=False, register_providers=False),
    )


# ── Happy paths through the full state machine ──────────────────────


def test_submit_lands_in_pending_review(isolated_db):
    c = _client()
    r = c.post(
        "/advertisers/applications",
        json={
            "display_name": "Acme Recruiting",
            "contact_email": "ops@acme.example",
            "verticals": ["recruiting", "saas"],
            "audience_intents": ["hiring_manager"],
            "monthly_budget_usd_cents": 50000,
            "advertiser_id": "adv-acme",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["advertiser_id"] == "adv-acme"
    assert body["status"] == "pending_review"
    assert body["verticals"] == ["recruiting", "saas"]


def test_approve_then_activate_requires_legal_gate(isolated_db):
    c = _client()
    c.post(
        "/advertisers/applications",
        json={
            "display_name": "X",
            "contact_email": "x@y",
            "verticals": [],
            "advertiser_id": "adv-x",
        },
    )
    # Approve.
    r = c.post(
        "/advertisers/adv-x/approve",
        json={"operator_notes": "vetted"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "approved"
    assert "vetted" in r.json()["operator_notes"]

    # Activate WITHOUT legal gate → 409 legal_gate.
    r = c.post(
        "/advertisers/adv-x/activate",
        json={"legal_gate_passed": False},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["error"]["code"] == "legal_gate"

    # Activate WITH legal gate → 200, ACTIVE.
    r = c.post(
        "/advertisers/adv-x/activate",
        json={"legal_gate_passed": True},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "active"


def test_full_suspend_then_churn(isolated_db):
    c = _client()
    c.post(
        "/advertisers/applications",
        json={
            "display_name": "X",
            "contact_email": "x@y",
            "verticals": [],
            "advertiser_id": "adv-x",
        },
    )
    c.post("/advertisers/adv-x/approve", json={"operator_notes": ""})
    c.post(
        "/advertisers/adv-x/activate", json={"legal_gate_passed": True},
    )
    r = c.post(
        "/advertisers/adv-x/suspend",
        json={"reason": "brand-safety review"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "suspended"
    assert "brand-safety review" in r.json()["operator_notes"]

    r = c.post("/advertisers/adv-x/churn")
    assert r.status_code == 200
    assert r.json()["status"] == "churned"


# ── Refusal modes ──────────────────────────────────────────────────


def test_reject_then_re_approve_refused(isolated_db):
    c = _client()
    c.post(
        "/advertisers/applications",
        json={
            "display_name": "X", "contact_email": "x@y", "verticals": [],
            "advertiser_id": "adv-x",
        },
    )
    r = c.post(
        "/advertisers/adv-x/reject", json={"rejection_reason": "off-brand"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"
    # Cannot re-approve.
    r = c.post(
        "/advertisers/adv-x/approve", json={"operator_notes": ""},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["error"]["code"] == "invalid_transition"


def test_duplicate_advertiser_id_refused(isolated_db):
    c = _client()
    payload = {
        "display_name": "A", "contact_email": "a@x", "verticals": [],
        "advertiser_id": "adv-dup",
    }
    r1 = c.post("/advertisers/applications", json=payload)
    assert r1.status_code == 201
    r2 = c.post("/advertisers/applications", json=payload)
    assert r2.status_code == 409
    assert r2.json()["detail"]["error"]["code"] == "duplicate_advertiser_id"


def test_unknown_advertiser_returns_404(isolated_db):
    c = _client()
    r = c.get("/advertisers/nope")
    assert r.status_code == 404
    assert r.json()["detail"]["error"]["code"] == "advertiser_not_found"


def test_approve_unknown_id_returns_404(isolated_db):
    c = _client()
    r = c.post("/advertisers/nope/approve", json={"operator_notes": ""})
    assert r.status_code == 404
    assert r.json()["detail"]["error"]["code"] == "advertiser_not_found"


# ── Listing endpoints ──────────────────────────────────────────────


def test_list_includes_only_latest_record_per_id(isolated_db):
    c = _client()
    c.post(
        "/advertisers/applications",
        json={
            "display_name": "X", "contact_email": "x@y", "verticals": [],
            "advertiser_id": "adv-x",
        },
    )
    c.post("/advertisers/adv-x/approve", json={"operator_notes": ""})
    r = c.get("/advertisers")
    assert r.status_code == 200
    body = r.json()
    assert len(body["advertisers"]) == 1
    assert body["advertisers"][0]["status"] == "approved"


def test_serving_returns_only_active(isolated_db):
    c = _client()
    # PENDING.
    c.post(
        "/advertisers/applications",
        json={
            "display_name": "P", "contact_email": "p@x", "verticals": [],
            "advertiser_id": "adv-p",
        },
    )
    # ACTIVE.
    c.post(
        "/advertisers/applications",
        json={
            "display_name": "A", "contact_email": "a@x", "verticals": [],
            "advertiser_id": "adv-a",
        },
    )
    c.post("/advertisers/adv-a/approve", json={"operator_notes": ""})
    c.post(
        "/advertisers/adv-a/activate", json={"legal_gate_passed": True},
    )
    r = c.get("/advertisers/serving")
    assert r.status_code == 200
    ids = [a["advertiser_id"] for a in r.json()["advertisers"]]
    assert ids == ["adv-a"]


# ── Persistence round-trip across requests ─────────────────────────


def test_full_audit_trail_persisted(isolated_db):
    """Each state transition appends a row; reading back recovers all
    of them in audit order."""
    c = _client()
    c.post(
        "/advertisers/applications",
        json={
            "display_name": "X", "contact_email": "x@y", "verticals": [],
            "advertiser_id": "adv-trail",
        },
    )
    c.post("/advertisers/adv-trail/approve", json={"operator_notes": ""})
    c.post(
        "/advertisers/adv-trail/activate", json={"legal_gate_passed": True},
    )
    c.post(
        "/advertisers/adv-trail/suspend", json={"reason": "audit"},
    )

    import duckdb
    con = duckdb.connect(isolated_db, read_only=True)
    try:
        rows = con.execute(
            "SELECT status FROM advertisers WHERE advertiser_id = ? "
            "ORDER BY row_inserted_at",
            ["adv-trail"],
        ).fetchall()
    finally:
        con.close()
    assert [r[0] for r in rows] == [
        "pending_review", "approved", "active", "suspended",
    ]
