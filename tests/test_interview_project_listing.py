"""Per-project interview listing endpoint tests."""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


@pytest.fixture()
def isolated_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-iv-index-")
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


def test_list_interviews_for_missing_project_returns_empty(isolated_db):
    client = _client()
    resp = client.get("/interview-projects/does-not-exist/interviews")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_interviews_returns_invited_set(isolated_db):
    client = _client()
    # Create a project.
    resp = client.post(
        "/interview-projects",
        json={
            "title": "Test project",
            "topic_description": "x",
            "must_cover": ["q1", "q2"],
        },
    )
    assert resp.status_code in (200, 201), resp.text
    project = resp.json()
    pid = project["project_id"]

    # Invite two informants.
    for handle in ["alice", "bob"]:
        r = client.post(
            "/interviews",
            json={"project_id": pid, "informant_handle": handle},
        )
        assert r.status_code in (200, 201), r.text

    # List them.
    resp = client.get(f"/interview-projects/{pid}/interviews")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    handles = sorted(row["informant_handle"] for row in body)
    assert handles == ["alice", "bob"]
    # Status defaults to invited.
    for row in body:
        assert row["status"] in {"invited", "in_progress", "completed", "declined", "incomplete"}
        assert row["turn_count"] == 0


def test_list_interviews_orders_oldest_first(isolated_db):
    client = _client()
    resp = client.post(
        "/interview-projects", json={"title": "P", "must_cover": []},
    )
    pid = resp.json()["project_id"]
    handles = ["first", "second", "third"]
    for h in handles:
        client.post(
            "/interviews", json={"project_id": pid, "informant_handle": h},
        )
    resp = client.get(f"/interview-projects/{pid}/interviews")
    body = resp.json()
    listed = [row["informant_handle"] for row in body]
    assert listed == handles  # oldest first per the endpoint contract


def test_list_interviews_scoped_to_one_project(isolated_db):
    client = _client()
    r1 = client.post(
        "/interview-projects", json={"title": "A", "must_cover": []},
    )
    r2 = client.post(
        "/interview-projects", json={"title": "B", "must_cover": []},
    )
    pid1 = r1.json()["project_id"]
    pid2 = r2.json()["project_id"]
    client.post("/interviews", json={"project_id": pid1, "informant_handle": "a1"})
    client.post("/interviews", json={"project_id": pid1, "informant_handle": "a2"})
    client.post("/interviews", json={"project_id": pid2, "informant_handle": "b1"})

    body1 = client.get(f"/interview-projects/{pid1}/interviews").json()
    body2 = client.get(f"/interview-projects/{pid2}/interviews").json()
    assert len(body1) == 2
    assert len(body2) == 1
    assert body2[0]["informant_handle"] == "b1"
