"""ANT-AHT — research artifact HTTP routes."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_REPO = str(Path(__file__).resolve().parents[1])
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

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
    workspace = client.post(
        f"/research/artifact-composes/{draft['compose_id']}/write-workspace", json={}
    )
    assert workspace.status_code == 201
    receipt = workspace.json()
    assert receipt["write_url"] == f"/write/{receipt['deliverable_id']}"
    assert receipt["member_count"] == 2
    assert receipt["reused"] is False
    reused = client.post(
        f"/research/artifact-composes/{draft['compose_id']}/write-workspace", json={}
    )
    assert reused.status_code == 200
    assert reused.json()["deliverable_id"] == receipt["deliverable_id"]
    assert reused.json()["reused"] is True
    protected = client.delete(f"/research/artifact-composes/{draft['compose_id']}")
    assert protected.status_code == 409
    assert "provenance source" in protected.json()["detail"]
    assert client.get(draft["view_url"]).status_code == 200


def test_compose_interrogation_preview_route_receipt_and_statuses(api_env):
    for iid, text in [("inv-one", "One evidence"), ("inv-two", "Two evidence")]:
        promote_insight(text=text, investigation_id=iid, source_document_id="doc")
        _complete(iid, api_env["events"])
    client = _client()
    selection = ["inv-one", "inv-two"]
    preview = client.post(
        "/research/artifact-composes/preview",
        json={"investigation_ids": selection},
    ).json()
    draft = client.post(
        "/research/artifact-composes",
        json={
            "investigation_ids": selection,
            "selection_fingerprint": preview["selection_fingerprint"],
        },
    ).json()

    response = client.post(
        f"/research/artifact-composes/{draft['compose_id']}/interrogations/preview",
        json={
            "prompt": "Compare the evidence.",
            "selection_fingerprint": draft["selection_fingerprint"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == 1
    assert body["compose_id"] == draft["compose_id"]
    assert body["selection_fingerprint"] == draft["selection_fingerprint"]
    assert len(body["prompt_hash"]) == 64
    assert body["provider_called"] is False
    assert body["context_chars"] == len(body["context"])
    assert body["context_chars"] <= body["max_context_chars"]
    assert [r["investigation_id"] for r in body["member_receipts"]] == selection

    assert client.post(
        "/research/artifact-composes/cmp-000000000000000000000000/interrogations/preview",
        json={"prompt": "Question?", "selection_fingerprint": draft["selection_fingerprint"]},
    ).status_code == 404
    assert client.post(
        f"/research/artifact-composes/{draft['compose_id']}/interrogations/preview",
        json={"prompt": "Question?", "selection_fingerprint": "0" * 64},
    ).status_code == 409
    assert client.post(
        f"/research/artifact-composes/{draft['compose_id']}/interrogations/preview",
        json={"prompt": "", "selection_fingerprint": draft["selection_fingerprint"]},
    ).status_code == 422


def test_compose_interrogation_preview_route_integrity_conflict(api_env):
    for iid, text in [("inv-one", "One evidence"), ("inv-two", "Two evidence")]:
        promote_insight(text=text, investigation_id=iid, source_document_id="doc")
        _complete(iid, api_env["events"])
    client = _client()
    selection = ["inv-one", "inv-two"]
    preview = client.post(
        "/research/artifact-composes/preview",
        json={"investigation_ids": selection},
    ).json()
    draft = client.post(
        "/research/artifact-composes",
        json={
            "investigation_ids": selection,
            "selection_fingerprint": preview["selection_fingerprint"],
        },
    ).json()
    member_path = os.path.join(
        api_env["arts"], "composes", draft["compose_id"], "members", "0.html"
    )
    with open(member_path, encoding="utf-8") as handle:
        content = handle.read()
    with open(member_path, "w", encoding="utf-8") as handle:
        handle.write(content.replace('"investigation_id": "inv-one"', '"investigation_id": "inv-x"'))

    response = client.post(
        f"/research/artifact-composes/{draft['compose_id']}/interrogations/preview",
        json={
            "prompt": "Question?",
            "selection_fingerprint": draft["selection_fingerprint"],
        },
    )
    assert response.status_code == 409


def test_compose_write_route_missing_invalid_kind_and_integrity_conflict(api_env):
    client = _client()
    assert client.post(
        "/research/artifact-composes/cmp-000000000000000000000000/write-workspace", json={}
    ).status_code == 404
    assert client.post(
        "/research/artifact-composes/cmp-000000000000000000000000/write-workspace",
        json={"deliverable_kind": "surprise"},
    ).status_code == 422

    for iid, text in [("inv-one", "One"), ("inv-two", "Two")]:
        promote_insight(text=text, investigation_id=iid, source_document_id="doc")
        _complete(iid, api_env["events"])
    preview = client.post(
        "/research/artifact-composes/preview",
        json={"investigation_ids": ["inv-one", "inv-two"]},
    ).json()
    draft = client.post(
        "/research/artifact-composes",
        json={
            "investigation_ids": ["inv-one", "inv-two"],
            "selection_fingerprint": preview["selection_fingerprint"],
        },
    ).json()
    member_path = os.path.join(
        api_env["arts"], "composes", draft["compose_id"], "members", "0.html"
    )
    with open(member_path, "a", encoding="utf-8") as handle:
        handle.write("corrupt outside canonical body")
    # Non-canonical surrounding HTML does not alter the immutable machine body.
    assert client.post(
        f"/research/artifact-composes/{draft['compose_id']}/write-workspace", json={}
    ).status_code == 201
    with open(member_path, encoding="utf-8") as handle:
        content = handle.read()
    with open(member_path, "w", encoding="utf-8") as handle:
        handle.write(content.replace("inv-one", "inv-swapped"))
    # The first call already mapped it; integrity is still revalidated before reuse.
    assert client.post(
        f"/research/artifact-composes/{draft['compose_id']}/write-workspace", json={}
    ).status_code == 409


def test_unpromoted_compose_can_still_be_deleted(api_env):
    for iid in ("inv-one", "inv-two"):
        promote_insight(text=iid, investigation_id=iid, source_document_id="doc")
        _complete(iid, api_env["events"])
    client = _client()
    selection = ["inv-one", "inv-two"]
    preview = client.post(
        "/research/artifact-composes/preview", json={"investigation_ids": selection}
    ).json()
    draft = client.post(
        "/research/artifact-composes",
        json={
            "investigation_ids": selection,
            "selection_fingerprint": preview["selection_fingerprint"],
        },
    ).json()
    url = f"/research/artifact-composes/{draft['compose_id']}"
    assert client.delete(url).status_code == 204
    assert client.delete(url).status_code == 404


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
