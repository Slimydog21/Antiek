"""Midnight Oil deposit product route (residual bh)."""

from __future__ import annotations

import os
import sys
from dataclasses import replace

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from test_midnight_oil_consent_routes import _client  # noqa: E402

from substrate.midnight_oil.job_store import OperationState  # noqa: E402


def test_deposit_is_closed_until_durable_terminal_state(tmp_path):
    client, _ = _client(tmp_path)
    headers = {"x-test-user": "alice"}

    created = client.post(
        "/midnight-oil/create",
        headers=headers,
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

    d1 = client.post(
        "/midnight-oil/deposit",
        headers=headers,
        json={
            "job_id": job_id,
            "include_progress_html": True,
            "mark_complete": True,
        },
    )
    assert d1.status_code == 409
    assert "terminal state" in d1.text
    assert "html" not in d1.json()

    wrong_owner = client.post(
        "/midnight-oil/deposit",
        headers={"x-test-user": "mallory"},
        json={"job_id": job_id, "include_progress_html": True},
    )
    assert wrong_owner.status_code == 404


def test_deposit_rejects_legacy_asset_drift_even_at_terminal_state(tmp_path):
    client, deps = _client(tmp_path)
    headers = {"x-test-user": "alice"}
    created = client.post(
        "/midnight-oil/create",
        headers=headers,
        json={"goals": ["research"], "duration_minutes": 10},
    ).json()
    job_id = created["job_id"]
    legacy = deps.jobs.get_job(job_id)
    assert legacy is not None
    legacy["asset_id"] = "victim-asset"
    deps.jobs.put_job(legacy)
    original_get = deps.owner_jobs.get_job

    def terminal_get(*, owner_user_id: str, job_id: str):
        row = original_get(owner_user_id=owner_user_id, job_id=job_id)
        return None if row is None else replace(row, operation_state=OperationState.COMPLETE)

    deps.owner_jobs.get_job = terminal_get  # type: ignore[method-assign]
    response = client.post("/midnight-oil/deposit", headers=headers, json={"job_id": job_id})
    assert response.status_code == 409
    assert "reconciliation" in response.text


def test_deposit_uses_exact_authorized_snapshot_across_legacy_race(tmp_path):
    client, deps = _client(tmp_path)
    headers = {"x-test-user": "alice"}
    created = client.post(
        "/midnight-oil/create",
        headers=headers,
        json={"goals": ["research"], "duration_minutes": 10},
    ).json()
    job_id = created["job_id"]
    safe = deps.jobs.get_job(job_id)
    assert safe is not None
    victim = {**safe, "asset_id": "victim-asset", "goals": ["changed"]}
    reads = 0

    def racing_get(requested_job_id: str):
        nonlocal reads
        assert requested_job_id == job_id
        reads += 1
        return dict(safe if reads == 1 else victim)

    deps.jobs.get_job = racing_get  # type: ignore[method-assign]
    original_get = deps.owner_jobs.get_job

    def terminal_get(*, owner_user_id: str, job_id: str):
        row = original_get(owner_user_id=owner_user_id, job_id=job_id)
        return None if row is None else replace(row, operation_state=OperationState.COMPLETE)

    deps.owner_jobs.get_job = terminal_get  # type: ignore[method-assign]
    response = client.post(
        "/midnight-oil/deposit", headers=headers, json={"job_id": job_id}
    )
    assert response.status_code == 200, response.text
    assert response.json()["asset_id"] == "asset-owned"
    # Another subsystem may observe the mutable store, but deposit must remain
    # bound to the first snapshot that passed the authority comparison.
    assert reads >= 2
