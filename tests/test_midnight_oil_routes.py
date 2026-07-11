"""API tests for Midnight Oil create → recommend → approve."""

from __future__ import annotations

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.midnight_oil.job_store import SqliteDurableJobStore  # noqa: E402
from tests.midnight_oil_route_test_support import register_authenticated_midnight_oil  # noqa: E402

CONSENT_RESPONSE_FIELDS = {
    "token",
    "operation_id",
    "ceiling_cents",
    "expires_at_ms",
    "job_id",
    "status",
    "force_below_recommended",
}


@pytest.fixture
def client(tmp_path):
    app = FastAPI()
    register_authenticated_midnight_oil(app, tmp_path)
    return TestClient(app)


def test_create_approve_flow(client):
    r = client.post(
        "/midnight-oil/create",
        json={
            "goals": ["Deep-research residual gaps in Antiek workstation."],
            "duration_minutes": 60,
            "model_id": "default",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["recommended_price_ceiling_usd"] > 0
    assert body["status"] == "awaiting_approval"
    assert body["view_format"] == "html"
    assert body["runnable"] is False
    assert "html" in body
    job_id = body["job_id"]

    # Below without force → 400
    bad = client.post(
        "/midnight-oil/approve",
        json={
            "job_id": job_id,
            "ceiling_cents": 1,
        },
    )
    assert bad.status_code == 400

    ok = client.post(
        "/midnight-oil/approve",
        json={"job_id": job_id, "use_recommended": True},
    )
    assert ok.status_code == 200
    approved = ok.json()
    assert set(approved) == CONSENT_RESPONSE_FIELDS
    assert approved["status"] == "approved"
    assert approved["token"]
    assert approved["operation_id"]
    assert ok.headers["cache-control"] == "no-store"
    assert approved["ceiling_cents"] == int(body["recommended_price_ceiling_usd"] * 100)

    got = client.get(f"/midnight-oil/jobs/{job_id}")
    assert got.status_code == 200
    assert got.json()["status"] == "approved"
    assert got.json()["view_format"] == "html"


def test_force_below_api(client, tmp_path):
    r = client.post(
        "/midnight-oil/create",
        json={"goals": ["g"], "duration_minutes": 30, "model_id": "default"},
    )
    job_id = r.json()["job_id"]
    r2 = client.post(
        "/midnight-oil/approve",
        json={"job_id": job_id, "ceiling_cents": 1, "force_below": True},
    )
    assert r2.status_code == 200
    assert r2.json()["force_below_recommended"] is True
    reopened = SqliteDurableJobStore(str(tmp_path / "midnight-oil-jobs.sqlite3")).get_job_for_owner(
        job_id, "__operator__"
    )
    assert reopened is not None and reopened.authority is not None
    assert reopened.status == "approved"
    assert reopened.authority.approved_ceiling_cents == 1
    assert reopened.authority.consent_granted_by_user_id == "__operator__"
    assert reopened.authority.operation_id == r2.json()["operation_id"]
    assert reopened.force_below_recommended is True


def test_create_rejects_empty_goals(client):
    r = client.post(
        "/midnight-oil/create",
        json={"goals": ["  "], "duration_minutes": 10},
    )
    assert r.status_code == 400
