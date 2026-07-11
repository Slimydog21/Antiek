"""Midnight Oil offline worker run product path (residual bn)."""

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
from substrate.midnight_oil import (  # noqa: E402
    approve_price_ceiling,
    create_with_recommended_ceiling,
    run_job_offline,
)
from substrate.midnight_oil.ceiling import ModelPricing  # noqa: E402
from substrate.midnight_oil.job import InMemoryJobStore  # noqa: E402
from tests.midnight_oil_route_test_support import register_authenticated_midnight_oil  # noqa: E402


def test_run_job_offline_completes_goals():
    store = InMemoryJobStore()
    created = create_with_recommended_ceiling(
        ("Goal A", "Goal B"),
        60,
        store=store,
        pricing=ModelPricing("m", 1.0, 3.0),
    )
    approve_price_ceiling(created.job.job_id, store=store, use_recommended=True)
    out = run_job_offline(created.job.job_id, store=store, spent_per_goal=0.05)
    assert out["status"] == "complete"
    assert out["offline"] is True
    assert out["view_format"] == "html"
    assert len(out["spawn_ids"]) == 2
    assert out["spent_usd"] == 0.1
    assert out["html"]
    assert "application/pdf" not in out["html"].lower()


def test_run_rejects_unapproved():
    store = InMemoryJobStore()
    created = create_with_recommended_ceiling(
        ("g",), 10, store=store, pricing=ModelPricing("m", 1.0, 3.0)
    )
    try:
        run_job_offline(created.job.job_id, store=store)
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "approved" in str(exc).lower()


def test_api_run_and_auto_deposit(tmp_path):
    reset_engagement_stores()
    app = FastAPI()
    register_authenticated_midnight_oil(app, tmp_path)
    register_engagement_routes(app)
    client = TestClient(app)

    c = client.post(
        "/midnight-oil/create",
        json={
            "goals": ["Chase arxiv attention paper questions"],
            "duration_minutes": 30,
            "model_id": "offline-stub",
        },
    )
    assert c.status_code == 200
    job_id = c.json()["job_id"]
    a = client.post(
        "/midnight-oil/approve",
        json={"job_id": job_id, "use_recommended": True},
    )
    assert a.status_code == 200
    assert a.json()["status"] == "approved"

    r1 = client.post(
        "/midnight-oil/run",
        json={"job_id": job_id, "auto_deposit": True, "spent_per_goal": 0.05},
    )
    assert r1.status_code == 400, r1.text
    assert r1.json() == {"detail": "spend consent header is required"}
    unchanged = client.get(f"/midnight-oil/jobs/{job_id}")
    assert unchanged.status_code == 200
    assert unchanged.json()["spawn_ids"] == []

    # Unapproved run fails
    c2 = client.post(
        "/midnight-oil/create",
        json={"goals": ["x"], "duration_minutes": 5},
    )
    bad = client.post(
        "/midnight-oil/run",
        json={"job_id": c2.json()["job_id"]},
    )
    assert bad.status_code == 400
    assert bad.json() == {"detail": "spend consent header is required"}
