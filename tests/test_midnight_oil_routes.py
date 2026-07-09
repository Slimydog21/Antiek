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

from interfaces.research.api.midnight_oil_routes import (  # noqa: E402
    register_midnight_oil_routes,
    reset_midnight_oil_store,
)


@pytest.fixture
def client():
    reset_midnight_oil_store()
    app = FastAPI()
    register_midnight_oil_routes(app)
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
            "ceiling_usd": body["recommended_price_ceiling_usd"] * 0.1,
        },
    )
    assert bad.status_code == 400

    ok = client.post(
        "/midnight-oil/approve",
        json={"job_id": job_id, "use_recommended": True},
    )
    assert ok.status_code == 200
    approved = ok.json()
    assert approved["status"] == "approved"
    assert approved["runnable"] is True
    assert (
        approved["approved_ceiling_usd"]
        == body["recommended_price_ceiling_usd"]
    )

    got = client.get(f"/midnight-oil/jobs/{job_id}")
    assert got.status_code == 200
    assert got.json()["status"] == "approved"
    assert got.json()["view_format"] == "html"


def test_force_below_api(client):
    r = client.post(
        "/midnight-oil/create",
        json={"goals": ["g"], "duration_minutes": 30, "model_id": "default"},
    )
    job_id = r.json()["job_id"]
    r2 = client.post(
        "/midnight-oil/approve",
        json={"job_id": job_id, "ceiling_usd": 0.01, "force_below": True},
    )
    assert r2.status_code == 200
    assert r2.json()["force_below_recommended"] is True


def test_create_rejects_empty_goals(client):
    r = client.post(
        "/midnight-oil/create",
        json={"goals": ["  "], "duration_minutes": 10},
    )
    assert r.status_code == 400
