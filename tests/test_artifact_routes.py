"""ANT-AHT — research artifact HTTP routes."""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from substrate.event_log import ActionType, log_event
from substrate.graph import ensure_initialized
from substrate.graph.insight_question import promote_insight


@pytest.fixture
def api_env(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="ra-api-")
    db = os.path.join(tmpdir, "t.duckdb")
    events = os.path.join(tmpdir, "events")
    arts = os.path.join(tmpdir, "artifacts")
    os.makedirs(events, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", arts)
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    ensure_initialized(db)
    return {"db": db, "events": events, "arts": arts}


def _client():
    return TestClient(create_app(register_wrestling=False))


def _complete(investigation_id: str, events: str) -> None:
    log_event(
        investigation_id,
        ActionType.INVESTIGATION_COMPLETED,
        payload={"thesis_summary": "done"},
        events_dir=events,
    )


def test_post_export_artifact(api_env):
    promote_insight(
        text="API export insight.",
        investigation_id="inv-api",
        confidence="moderate",
        source_document_id="doc-1",
    )
    client = _client()
    resp = client.post("/research/inv-api/artifact/export")
    assert resp.status_code == 200
    body = resp.json()
    assert body["investigation_id"] == "inv-api"
    assert body["path"]
    assert body["content_hash"]
    assert body["size_bytes"] > 0
    assert os.path.isfile(body["path"])


def test_get_artifact_blocks_empty(api_env):
    client = _client()
    resp = client.get("/research/inv-empty/artifact/blocks")
    assert resp.status_code == 200
    body = resp.json()
    assert body["investigation_id"] == "inv-empty"
    assert body["blocks"] == []


def test_get_artifact_blocks_after_insight(api_env):
    promote_insight(
        text="Outline block source.",
        investigation_id="inv-blocks",
        confidence="high",
        source_document_id="doc-2",
    )
    client = _client()
    resp = client.get("/research/inv-blocks/artifact/blocks")
    assert resp.status_code == 200
    blocks = resp.json()["blocks"]
    assert len(blocks) >= 1
    assert blocks[0]["investigation_id"] == "inv-blocks"
    assert blocks[0]["kind"] in ("insight", "question", "synthesis")


def test_compose_preview_create_view_member_and_delete(api_env):
    for iid, text in [("inv-one", "One"), ("inv-two", "Two")]:
        promote_insight(text=text, investigation_id=iid, source_document_id="doc")
        _complete(iid, api_env["events"])
    client = _client()
    selection = ["inv-one", "inv-two"]
    preview = client.post("/research/artifact-composes/preview", json={"investigation_ids": selection})
    assert preview.status_code == 200
    reviewed = preview.json()
    created = client.post("/research/artifact-composes", json={"investigation_ids": selection, "selection_fingerprint": reviewed["selection_fingerprint"]})
    assert created.status_code == 200
    draft = created.json()
    assert draft["view_url"].endswith("/view")
    view = client.get(draft["view_url"])
    assert view.status_code == 200
    assert view.headers["content-type"].startswith("text/html")
    assert "file://" not in view.text
    promote_insight(text="Later source change", investigation_id="inv-one", source_document_id="doc-later")
    member = client.get(f"/research/artifact-composes/{draft['compose_id']}/member/0")
    assert member.status_code == 200
    assert 'id="antiek-artifact-v1"' in member.text
    assert "Later source change" not in member.text
    assert "Add note to artifact" not in member.text
    assert "<script>" not in member.text
    assert client.delete(f"/research/artifact-composes/{draft['compose_id']}").status_code == 204
    assert client.delete(f"/research/artifact-composes/{draft['compose_id']}").status_code == 404
    assert client.get(draft["view_url"]).status_code == 404


def test_compose_stale_fingerprint_is_conflict(api_env):
    for iid, text in [("inv-one", "One"), ("inv-two", "Two")]:
        promote_insight(text=text, investigation_id=iid, source_document_id="doc")
        _complete(iid, api_env["events"])
    client = _client()
    response = client.post("/research/artifact-composes", json={"investigation_ids": ["inv-one", "inv-two"], "selection_fingerprint": "0" * 64})
    assert response.status_code == 409


def test_compose_rejects_path_like_id_before_event_lookup(api_env):
    response = _client().post(
        "/research/artifact-composes/preview",
        json={"investigation_ids": ["../outside", "inv-two"]},
    )
    assert response.status_code == 422


def test_compose_uses_latest_terminal_state(api_env):
    for iid in ("inv-one", "inv-two"):
        promote_insight(text=iid, investigation_id=iid, source_document_id="doc")
        _complete(iid, api_env["events"])
    log_event(
        "inv-one",
        ActionType.INVESTIGATION_CHASE_HALTED,
        payload={"reason": "budget"},
        events_dir=api_env["events"],
    )
    response = _client().post(
        "/research/artifact-composes/preview",
        json={"investigation_ids": ["inv-one", "inv-two"]},
    )
    assert response.status_code == 409
