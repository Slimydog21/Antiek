"""ANT-AHT — research artifact HTTP routes."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
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
    assert body["twin_notes_path"]
    assert body["content_hash"]
    assert body["size_bytes"] > 0
    assert os.path.isfile(body["path"])
    assert os.path.isfile(body["twin_notes_path"])


def test_get_artifact_html_renders_by_investigation_id(api_env):
    promote_insight(
        text="HTML view insight.",
        investigation_id="inv-html-view",
        confidence="moderate",
        source_document_id="doc-1",
    )
    client = _client()
    resp = client.get("/research/inv-html-view/artifact/html")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert resp.headers["x-antiek-investigation-id"] == "inv-html-view"
    assert resp.headers["x-antiek-content-hash"]
    assert "HTML view insight." in resp.text


def test_get_artifact_twin_notes_renders_by_investigation_id(api_env):
    promote_insight(
        text="Twin route insight.",
        investigation_id="inv-notes-view",
        confidence="moderate",
        source_document_id="doc-1",
    )
    client = _client()
    resp = client.get("/research/inv-notes-view/artifact/twin-notes.html")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert resp.headers["x-antiek-investigation-id"] == "inv-notes-view"
    assert resp.headers["x-antiek-content-hash"]
    assert "Twin route insight." in resp.text


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


def test_post_compose_artifacts_writes_draft_merge(api_env):
    for iid, text in [("inv-api-a", "API A"), ("inv-api-b", "API B")]:
        promote_insight(
            text=text,
            investigation_id=iid,
            confidence="moderate",
            source_document_id="doc-compose",
        )
    client = _client()
    resp = client.post(
        "/research/artifacts/compose",
        json={
            "investigation_ids": ["inv-api-a", "inv-api-b"],
            "write_draft_merge": True,
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert os.path.isfile(body["path"])
    assert os.path.isfile(body["draft_merge_path"])
    assert len(body["members"]) == 2
    assert all(member["twin_notes_path"] for member in body["members"])


def test_get_compose_draft_merge_html_renders_by_investigation_ids(api_env):
    for iid, text in [("inv-view-a", "View A"), ("inv-view-b", "View B")]:
        promote_insight(
            text=text,
            investigation_id=iid,
            confidence="moderate",
            source_document_id="doc-compose",
        )
    client = _client()
    resp = client.get(
        "/research/artifacts/compose/draft-merge.html",
        params=[("investigation_ids", "inv-view-a"), ("investigation_ids", "inv-view-b")],
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert resp.headers["x-antiek-compose-count"] == "2"
    assert resp.headers["x-antiek-compose-members"] == "inv-view-a,inv-view-b"
    assert "Draft merge of 2 research artifacts" in resp.text
    assert "View A" in resp.text
    assert "View B" in resp.text


def test_post_compose_artifacts_requires_two_ids(api_env):
    client = _client()
    resp = client.post(
        "/research/artifacts/compose",
        json={"investigation_ids": ["one"]},
    )

    assert resp.status_code == 400
    assert "at least two" in resp.json()["detail"]


def _source_merge_ready_packet(client: TestClient) -> tuple[dict, dict[str, str]]:
    for iid, text in [("inv-src-a", "Source merge A"), ("inv-src-b", "Source merge B")]:
        promote_insight(
            text=text,
            investigation_id=iid,
            confidence="moderate",
            source_document_id="doc-source-merge",
        )
    compose = client.post(
        "/research/artifacts/compose",
        json={
            "investigation_ids": ["inv-src-a", "inv-src-b"],
            "write_draft_merge": True,
        },
    )
    assert compose.status_code == 200
    body = compose.json()
    member_hashes = {
        member["investigation_id"]: member["content_hash"]
        for member in body["members"]
    }
    return (
        {
            "kind": "antiek.reader.source_merge_review_packet",
            "document_id": "doc-source-merge",
            "title": "Source Merge Book",
            "parent_reading_thread_id": "read-doc-source-merge",
            "draft_merge_path": body["draft_merge_path"],
            "compose_index_path": body["path"],
            "member_investigation_ids": ["inv-src-a", "inv-src-b"],
            "requested_investigation_ids": ["inv-src-a", "inv-src-b"],
            "hash_conflict_count": 0,
            "hash_conflicts": [],
            "source_book_mutated": False,
            "twin_document_mutated": False,
            "no_spend": True,
        },
        member_hashes,
    )


def test_source_merge_apply_requires_operator_acknowledgements(api_env):
    client = _client()
    packet, hashes = _source_merge_ready_packet(client)

    resp = client.post(
        "/research/artifacts/source-merge/apply",
        json={
            "reviewed_packet": packet,
            "expected_content_hashes": hashes,
        },
    )

    assert resp.status_code == 409
    assert resp.json()["detail"] == "source_merge_operator_acknowledgement_required"


def test_source_merge_apply_refuses_stale_review_packet(api_env):
    client = _client()
    packet, hashes = _source_merge_ready_packet(client)
    hashes["inv-src-a"] = "stale-" + hashes["inv-src-a"]

    resp = client.post(
        "/research/artifacts/source-merge/apply",
        json={
            "reviewed_packet": packet,
            "expected_content_hashes": hashes,
            "acknowledge_reviewed_draft": True,
            "acknowledge_source_book_mutation": True,
            "acknowledge_twin_document_mutation": True,
        },
    )

    assert resp.status_code == 409
    assert resp.json()["detail"] == "source_merge_stale_review_packet"


def test_source_merge_apply_requires_hash_conflict_acknowledgement(api_env):
    client = _client()
    packet, hashes = _source_merge_ready_packet(client)
    packet["hash_conflict_count"] = 1
    packet["hash_conflicts"] = [["inv-src-a", "inv-src-b"]]

    resp = client.post(
        "/research/artifacts/source-merge/apply",
        json={
            "reviewed_packet": packet,
            "expected_content_hashes": hashes,
            "acknowledge_reviewed_draft": True,
            "acknowledge_source_book_mutation": True,
            "acknowledge_twin_document_mutation": True,
            "acknowledge_hash_conflicts": False,
        },
    )

    assert resp.status_code == 409
    assert resp.json()["detail"] == "source_merge_hash_conflicts_acknowledgement_required"


def test_source_merge_apply_records_deterministic_receipt(api_env):
    client = _client()
    packet, hashes = _source_merge_ready_packet(client)

    resp = client.post(
        "/research/artifacts/source-merge/apply",
        json={
            "reviewed_packet": packet,
            "expected_content_hashes": hashes,
            "acknowledge_reviewed_draft": True,
            "acknowledge_source_book_mutation": True,
            "acknowledge_twin_document_mutation": True,
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "applied"
    assert body["document_id"] == "doc-source-merge"
    assert body["source_revision_id"].startswith("srcmerge-doc-source-merge-")
    assert body["twin_revision_id"].startswith("twinmerge-doc-source-merge-")
    assert body["member_investigation_ids"] == ["inv-src-a", "inv-src-b"]
    assert body["hash_conflicts_acknowledged"] is False
    assert body["event_id"]

    again = client.post(
        "/research/artifacts/source-merge/apply",
        json={
            "reviewed_packet": packet,
            "expected_content_hashes": hashes,
            "acknowledge_reviewed_draft": True,
            "acknowledge_source_book_mutation": True,
            "acknowledge_twin_document_mutation": True,
        },
    )
    assert again.status_code == 200
    assert again.json() == body


def test_source_merge_apply_emits_metadata_only_audit_event(api_env):
    client = _client()
    packet, hashes = _source_merge_ready_packet(client)

    resp = client.post(
        "/research/artifacts/source-merge/apply",
        json={
            "reviewed_packet": packet,
            "expected_content_hashes": hashes,
            "acknowledge_reviewed_draft": True,
            "acknowledge_source_book_mutation": True,
            "acknowledge_twin_document_mutation": True,
        },
    )

    assert resp.status_code == 200
    events_path = Path(api_env["events"]) / "read-doc-source-merge.jsonl"
    rows = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    event = rows[-1]
    assert event["event_id"] == resp.json()["event_id"]
    assert event["action_type"] == "source_merge.applied"
    assert event["document_id"] == "doc-source-merge"
    assert event["payload"]["source_book_body_rewritten"] is False
    assert event["payload"]["twin_document_body_rewritten"] is False
    assert "Source merge A" not in json.dumps(event)
    assert "Source merge B" not in json.dumps(event)


def test_get_compose_draft_merge_html_requires_two_ids(api_env):
    client = _client()
    resp = client.get(
        "/research/artifacts/compose/draft-merge.html",
        params={"investigation_ids": "one"},
    )

    assert resp.status_code == 400
    assert "at least two" in resp.json()["detail"]
