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
from interfaces.research.api.midnight_oil_routes import (  # noqa: E402
    register_midnight_oil_routes,
    reset_midnight_oil_store,
)


def test_create_approve_deposit_progress_double_run():
    reset_midnight_oil_store()
    reset_engagement_stores()
    app = FastAPI()
    register_midnight_oil_routes(app)
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
    assert approved.json()["runnable"] is True

    d1 = client.post(
        "/midnight-oil/deposit",
        json={
            "job_id": job_id,
            "include_progress_html": True,
            "mark_complete": True,
        },
    )
    assert d1.status_code == 200, d1.text
    body1 = d1.json()
    assert body1["view_format"] == "html"
    assert body1["twin_count"] >= 1
    assert body1["html"]
    assert "application/pdf" not in body1["html"].lower()
    assert body1["progress_seeded"] is True
    assert body1["progress"] is not None
    assert body1["progress"]["latest_stage"] == "complete"
    assert body1["usage_recorded"] is True

    # Second deposit remains honest / does not crash
    d2 = client.post(
        "/midnight-oil/deposit",
        json={"job_id": job_id, "include_progress_html": True},
    )
    assert d2.status_code == 200
    assert d2.json()["view_format"] == "html"
    assert d2.json()["job_id"] == job_id
