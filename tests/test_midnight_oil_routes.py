"""API tests for Midnight Oil create → recommend → approve."""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from test_midnight_oil_consent_routes import _client  # noqa: E402


@pytest.fixture
def client(tmp_path):
    return _client(tmp_path)[0]


def test_create_consent_flow(client):
    headers = {"x-test-user": "alice"}
    r = client.post(
        "/midnight-oil/create",
        headers=headers,
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

    # The legacy float approval contract is gone.
    bad = client.post(
        "/midnight-oil/approve",
        headers=headers,
        json={
            "job_id": job_id,
            "ceiling_usd": body["recommended_price_ceiling_usd"] * 0.1,
        },
    )
    assert bad.status_code == 422

    ok = client.post(
        f"/midnight-oil/jobs/{job_id}/spend-consent",
        headers=headers,
        json={"use_recommended": True},
    )
    assert ok.status_code == 200
    approved = ok.json()
    assert approved["ceiling_cents"] > 0
    assert ok.headers["cache-control"] == "no-store"

    got = client.get(f"/midnight-oil/jobs/{job_id}", headers=headers)
    assert got.status_code == 200
    assert got.json()["runnable"] is False
    assert got.json()["view_format"] == "html"


def test_force_below_api(client):
    headers = {"x-test-user": "alice"}
    r = client.post(
        "/midnight-oil/create",
        headers=headers,
        json={"goals": ["g"], "duration_minutes": 30, "model_id": "default"},
    )
    job_id = r.json()["job_id"]
    r2 = client.post(
        f"/midnight-oil/jobs/{job_id}/spend-consent",
        headers=headers,
        json={"ceiling_cents": 1, "force_below": True},
    )
    assert r2.status_code == 200
    assert r2.json()["ceiling_cents"] == 1


def test_job_status_exposes_only_safe_graph_projection_navigation(tmp_path):
    client, deps = _client(tmp_path)
    headers = {"x-test-user": "alice"}
    created = client.post(
        "/midnight-oil/create",
        headers=headers,
        json={"goals": ["g"], "duration_minutes": 30},
    ).json()
    raw = deps.jobs.get_job(created["job_id"])
    assert raw is not None
    node_id = "node-" + "1" * 16
    deliverable_id = "dlv-" + "2" * 16
    raw["graph_projection_state"] = "complete"
    raw["graph_effect_receipt"] = {
        "schema_version": 1,
        "owner_user_id": "alice",
        "deliverable_id": deliverable_id,
        "section_ids": ["sec-" + "3" * 16],
        "node_ids": [node_id],
        "edge_ids": ["edge-" + "4" * 16],
        "html_sha256": "5" * 64,
        "evidence_sha256": "6" * 64,
        "deep_links": [
            f"antiek://deliverable/{deliverable_id}",
            f"antiek://node/{node_id}",
        ],
    }
    deps.jobs.put_job(raw)

    response = client.get(
        f"/midnight-oil/jobs/{created['job_id']}", headers=headers
    )
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["graph_projection_state"] == "complete"
    assert body["graph_node_ids"] == [node_id]
    assert body["graph_deliverable_id"] == deliverable_id
    assert "owner_user_id" not in body
    assert "html_sha256" not in body


def test_job_status_exposes_closed_graph_projection_reason(tmp_path):
    client, deps = _client(tmp_path)
    headers = {"x-test-user": "alice"}
    created = client.post(
        "/midnight-oil/create",
        headers=headers,
        json={"goals": ["g"], "duration_minutes": 30},
    ).json()
    raw = deps.jobs.get_job(created["job_id"])
    assert raw is not None
    raw["graph_projection_state"] = "refused"
    raw["graph_projection_reason"] = "claim_coverage_missing"
    deps.jobs.put_job(raw)

    body = client.get(
        f"/midnight-oil/jobs/{created['job_id']}", headers=headers
    ).json()
    assert body["graph_projection_state"] == "refused"
    assert body["graph_projection_reason"] == "claim_coverage_missing"


def test_create_rejects_empty_goals(client):
    r = client.post(
        "/midnight-oil/create",
        headers={"x-test-user": "alice"},
        json={"goals": ["  "], "duration_minutes": 10},
    )
    assert r.status_code == 422
