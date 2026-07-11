"""Midnight Oil offline worker run product path (residual bn)."""

from __future__ import annotations

import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from test_midnight_oil_consent_routes import _client  # noqa: E402

from substrate.midnight_oil import (  # noqa: E402
    approve_price_ceiling,
    create_with_recommended_ceiling,
    run_job_offline,
)
from substrate.midnight_oil.ceiling import ModelPricing  # noqa: E402
from substrate.midnight_oil.job import InMemoryJobStore  # noqa: E402


def test_run_job_offline_completes_goals():
    store = InMemoryJobStore()
    created = create_with_recommended_ceiling(
        ("Goal A", "Goal B"),
        60,
        store=store,
        pricing=ModelPricing("m", 1.0, 3.0),
    )
    approve_price_ceiling(
        created.job.job_id, store=store, use_recommended=True
    )
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


def test_api_run_is_closed_until_durable_queue(tmp_path):
    client, _ = _client(tmp_path)
    headers = {"x-test-user": "alice"}

    c = client.post(
        "/midnight-oil/create",
        headers=headers,
        json={
            "goals": ["Chase arxiv attention paper questions"],
            "duration_minutes": 30,
            "model_id": "offline-stub",
        },
    )
    assert c.status_code == 200
    job_id = c.json()["job_id"]
    r1 = client.post(
        "/midnight-oil/run",
        headers=headers,
        json={"job_id": job_id, "auto_deposit": True, "spent_per_goal": 0.05},
    )
    assert r1.status_code == 409
    assert "durable enqueue" in r1.text

    # Unapproved run fails
    c2 = client.post(
        "/midnight-oil/create",
        headers=headers,
        json={"goals": ["x"], "duration_minutes": 5},
    )
    bad = client.post(
        "/midnight-oil/run",
        headers={"x-test-user": "mallory"},
        json={"job_id": c2.json()["job_id"]},
    )
    assert bad.status_code == 404
