"""Midnight Oil deposit product route (residual bh)."""

from __future__ import annotations

import os
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api.engagement_routes import (  # noqa: E402
    register_engagement_routes,
    reset_engagement_stores,
)
from tests.midnight_oil_route_test_support import register_authenticated_midnight_oil  # noqa: E402


def test_create_approve_deposit_progress_double_run(tmp_path):
    reset_engagement_stores()
    app = FastAPI()
    register_authenticated_midnight_oil(app, tmp_path)
    register_engagement_routes(app)
    client = TestClient(app)

    created = client.post(
        "/midnight-oil/create",
        json={
            "goals": ["Map residual risks in retrieval-augmented generation."],
            "duration_minutes": 30,
            "model_id": "test-model",
        },
    )
    assert created.status_code == 200, created.text
    job_id = created.json()["job_id"]
    assert created.json()["status"] == "awaiting_approval"
    assert created.json()["view_format"] == "html"

    approved = client.post(
        "/midnight-oil/approve",
        json={"job_id": job_id, "use_recommended": True},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    d1 = client.post(
        "/midnight-oil/deposit",
        json={
            "job_id": job_id,
            "include_progress_html": True,
            "mark_complete": True,
        },
    )
    assert d1.status_code == 409, d1.text
    assert d1.json() == {"detail": "Midnight Oil dispatch is disabled"}
    unchanged = client.get(f"/midnight-oil/jobs/{job_id}").json()
    assert unchanged["spawn_ids"] == []
    assert unchanged["status"] == "approved"

    # Second deposit remains honest / does not crash
    d2 = client.post(
        "/midnight-oil/deposit",
        json={"job_id": job_id, "include_progress_html": True},
    )
    assert d2.status_code == 409
    assert d2.json() == {"detail": "Midnight Oil dispatch is disabled"}
