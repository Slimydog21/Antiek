"""ANT-AHT — research artifact HTTP routes."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime.db_lock import connect_write
from substrate.graph import ensure_initialized
from substrate.graph.insight_question import promote_insight
from substrate.graph.ops import insert_document


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
    with connect_write(os.environ["ANTIEK_DUCKDB_PATH"], purpose="test/source_merge_source_doc") as con:
        insert_document(
            con,
            document_id="doc-source-merge",
            source_tier=2,
            document_type="book",
            title="Source Merge Book",
            raw_text="Original source book body.",
            on_conflict="ignore",
        )
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


def test_source_merge_preview_returns_revision_evidence_without_writes(api_env):
    client = _client()
    packet, hashes = _source_merge_ready_packet(client)

    resp = client.post(
        "/research/artifacts/source-merge/preview",
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
    assert body["status"] == "previewed"
    assert body["document_id"] == "doc-source-merge"
    assert body["source_revision_id"].startswith("srcmerge-doc-source-merge-")
    assert body["twin_revision_id"].startswith("twinmerge-doc-source-merge-")
    assert body["member_investigation_ids"] == ["inv-src-a", "inv-src-b"]
    assert body["before_source_hash"] != body["after_source_hash"]
    assert body["before_twin_hash"] != body["after_twin_hash"]
    assert body["source_bytes_after"] > body["source_bytes_before"]
    assert body["twin_bytes_after"] > 0
    assert body["writes_performed"] is False


def test_source_merge_preview_does_not_mutate_source_or_emit_event(api_env):
    client = _client()
    packet, hashes = _source_merge_ready_packet(client)

    resp = client.post(
        "/research/artifacts/source-merge/preview",
        json={
            "reviewed_packet": packet,
            "expected_content_hashes": hashes,
            "acknowledge_reviewed_draft": True,
            "acknowledge_source_book_mutation": True,
            "acknowledge_twin_document_mutation": True,
        },
    )

    assert resp.status_code == 200
    with connect_write(os.environ["ANTIEK_DUCKDB_PATH"], purpose="test/read_source_after_preview") as con:
        (raw_text,) = con.execute(
            "SELECT raw_text FROM documents WHERE document_id = ?",
            ["doc-source-merge"],
        ).fetchone()
    assert raw_text == "Original source book body."
    assert not (Path(api_env["events"]) / "read-doc-source-merge.jsonl").exists()


def test_source_merge_preview_refuses_missing_source_document(api_env):
    client = _client()
    packet, hashes = _source_merge_ready_packet(client)
    packet["document_id"] = "doc-source-merge-missing"

    resp = client.post(
        "/research/artifacts/source-merge/preview",
        json={
            "reviewed_packet": packet,
            "expected_content_hashes": hashes,
            "acknowledge_reviewed_draft": True,
            "acknowledge_source_book_mutation": True,
            "acknowledge_twin_document_mutation": True,
        },
    )

    assert resp.status_code == 409
    assert resp.json()["detail"] == "source_merge_source_document_not_found"


def _source_merge_preview_body(client: TestClient, packet: dict, hashes: dict[str, str]) -> dict:
    resp = client.post(
        "/research/artifacts/source-merge/preview",
        json={
            "reviewed_packet": packet,
            "expected_content_hashes": hashes,
            "acknowledge_reviewed_draft": True,
            "acknowledge_source_book_mutation": True,
            "acknowledge_twin_document_mutation": True,
        },
    )
    assert resp.status_code == 200
    return resp.json()


def _source_merge_commit_payload(packet: dict, hashes: dict[str, str], preview: dict) -> dict:
    return {
        "reviewed_packet": packet,
        "expected_content_hashes": hashes,
        "acknowledge_reviewed_draft": True,
        "acknowledge_source_book_mutation": True,
        "acknowledge_twin_document_mutation": True,
        "acknowledge_body_rewrite": True,
        "expected_source_revision_id": preview["source_revision_id"],
        "expected_twin_revision_id": preview["twin_revision_id"],
        "expected_before_source_hash": preview["before_source_hash"],
        "expected_after_source_hash": preview["after_source_hash"],
        "expected_before_twin_hash": preview["before_twin_hash"],
        "expected_after_twin_hash": preview["after_twin_hash"],
        "operator_reviewer": "pytest",
    }


def test_source_merge_commit_requires_body_rewrite_acknowledgement(api_env):
    client = _client()
    packet, hashes = _source_merge_ready_packet(client)
    preview = _source_merge_preview_body(client, packet, hashes)
    payload = _source_merge_commit_payload(packet, hashes, preview)
    payload["acknowledge_body_rewrite"] = False

    resp = client.post("/research/artifacts/source-merge/commit", json=payload)

    assert resp.status_code == 409
    assert resp.json()["detail"] == "source_merge_body_rewrite_acknowledgement_required"


def test_source_merge_commit_refuses_preview_hash_mismatch(api_env):
    client = _client()
    packet, hashes = _source_merge_ready_packet(client)
    preview = _source_merge_preview_body(client, packet, hashes)
    payload = _source_merge_commit_payload(packet, hashes, preview)
    payload["expected_after_source_hash"] = "stale-" + payload["expected_after_source_hash"]

    resp = client.post("/research/artifacts/source-merge/commit", json=payload)

    assert resp.status_code == 409
    assert resp.json()["detail"] == "source_merge_preview_binding_mismatch"


def test_source_merge_commit_rewrites_source_body_and_emits_metadata_event(api_env):
    client = _client()
    packet, hashes = _source_merge_ready_packet(client)
    preview = _source_merge_preview_body(client, packet, hashes)

    resp = client.post(
        "/research/artifacts/source-merge/commit",
        json=_source_merge_commit_payload(packet, hashes, preview),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "committed"
    assert body["writes_performed"] is True
    assert body["source_revision_id"] == preview["source_revision_id"]
    assert body["after_source_hash"] == preview["after_source_hash"]

    with connect_write(os.environ["ANTIEK_DUCKDB_PATH"], purpose="test/read_source_after_commit") as con:
        (raw_text,) = con.execute(
            "SELECT raw_text FROM documents WHERE document_id = ?",
            ["doc-source-merge"],
        ).fetchone()
        (twin_body_json,) = con.execute(
            "SELECT twin_body_json FROM source_merge_body_commits WHERE document_id = ?",
            ["doc-source-merge"],
        ).fetchone()
    assert "Original source book body." in raw_text
    assert "antiek-source-merge-start" in raw_text
    assert "Source merge A" in raw_text
    assert "Source merge B" in raw_text
    twin_body = json.loads(twin_body_json)
    assert twin_body["kind"] == "antiek.source_merge.preview_payload"
    assert twin_body["member_investigation_ids"] == ["inv-src-a", "inv-src-b"]

    events_path = Path(api_env["events"]) / "read-doc-source-merge.jsonl"
    rows = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    event = rows[-1]
    assert event["event_id"] == body["event_id"]
    assert event["action_type"] == "source_merge.committed"
    assert event["payload"]["source_book_body_rewritten"] is True
    assert event["payload"]["twin_document_body_rewritten"] is True
    assert event["payload"]["after_source_hash"] == preview["after_source_hash"]
    assert "Source merge A" not in json.dumps(event)
    assert "Source merge B" not in json.dumps(event)


def test_source_merge_commit_is_idempotent_after_rewrite(api_env):
    client = _client()
    packet, hashes = _source_merge_ready_packet(client)
    preview = _source_merge_preview_body(client, packet, hashes)
    payload = _source_merge_commit_payload(packet, hashes, preview)

    first = client.post("/research/artifacts/source-merge/commit", json=payload)
    second = client.post("/research/artifacts/source-merge/commit", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    first_body = first.json()
    second_body = second.json()
    assert first_body["writes_performed"] is True
    assert second_body["writes_performed"] is False
    assert {**first_body, "writes_performed": False} == second_body


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
