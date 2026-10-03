"""ANT-AHT — research artifact HTTP routes."""

from __future__ import annotations

import dataclasses
import json
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime.db_lock import connect_write
from substrate.graph import default_db_path, ensure_initialized
from substrate.graph.insight_question import promote_insight
from substrate.graph.ops import insert_document
from substrate.research_artifact.paths import artifact_source_path_for
from substrate.research_artifact.source_merge import (
    commit_source_merge_review,
    preview_source_merge_review,
)
from substrate.research_artifact.store import ResearchArtifactStore


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
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)
    ensure_initialized(db)
    with connect_write(db, purpose="test/artifact-readable-source") as con:
        insert_document(
            con, document_id="doc-1", source_tier=2, document_type="web",
            raw_text="Artifact source evidence.", content_class="public_domain",
            owner_user_id="__operator__",
        )
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
    resp = client.get("/research/inv-html-view/artifact.html")

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

def test_get_artifact_status_missing(api_env):
    response = _client().get("/research/inv-missing/artifact")
    assert response.status_code == 404


def test_get_artifact_status_returns_authoritative_identity(api_env):
    source = artifact_source_path_for("artifact-authoritative", "a" * 64)
    ResearchArtifactStore(default_db_path()).save_source(
        "artifact-authoritative", "inv-status", "__operator__", source, b"<html></html>"
    )
    response = _client().get("/research/inv-status/artifact")
    assert response.status_code == 200
    assert response.json() == {
        "artifact_id": "artifact-authoritative",
        "investigation_id": "inv-status",
        "selected_style": None,
        "latest_version": 0,
    }


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


def _source_merge_commit_payload(packet: dict, hashes: dict[str, str], preview: dict) -> dict:
    """The body the retired commit route accepted, and the arguments that seed
    a committed merge for the restore tests."""
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


def _source_merge_restore_payload(commit: dict, *, acknowledged: bool = True) -> dict:
    return {
        "document_id": commit["document_id"],
        "parent_reading_thread_id": "read-doc-source-merge",
        "source_revision_id": commit["source_revision_id"],
        "twin_revision_id": commit["twin_revision_id"],
        "expected_after_source_hash": commit["after_source_hash"],
        "expected_before_source_hash": commit["before_source_hash"],
        "acknowledge_restore": acknowledged,
        "operator_reviewer": "pytest",
    }


def _source_merge_preview_evidence(packet: dict, hashes: dict[str, str]) -> dict:
    """The revision ids and hashes a commit binds to, from the substrate preview."""
    with connect_write(os.environ["ANTIEK_DUCKDB_PATH"], purpose="test/source_merge_preview") as con:
        preview = preview_source_merge_review(
            con,
            document_id=packet["document_id"],
            draft_merge_path=packet["draft_merge_path"],
            compose_index_path=packet["compose_index_path"],
            member_investigation_ids=packet["member_investigation_ids"],
            expected_content_hashes=hashes,
            hash_conflicts=packet["hash_conflicts"],
        )
    return dataclasses.asdict(preview)


def _committed_source_merge(client: TestClient) -> tuple[dict, dict, dict[str, str]]:
    """A merge committed before the commit route was retired, as prod may hold.

    The commit route now answers 410 (T6: a merge never writes the source), so
    the commit is seeded through the substrate with the arguments the route
    passed; restore, the undo for such a commit, is still tested through its
    route.
    """
    packet, hashes = _source_merge_ready_packet(client)
    payload = _source_merge_commit_payload(packet, hashes, _source_merge_preview_evidence(packet, hashes))
    with connect_write(os.environ["ANTIEK_DUCKDB_PATH"], purpose="test/source_merge_seed_commit") as con:
        receipt = commit_source_merge_review(
            con,
            document_id=packet["document_id"],
            parent_reading_thread_id=packet["parent_reading_thread_id"],
            draft_merge_path=packet["draft_merge_path"],
            compose_index_path=packet["compose_index_path"],
            member_investigation_ids=packet["member_investigation_ids"],
            expected_content_hashes=payload["expected_content_hashes"],
            hash_conflicts=packet["hash_conflicts"],
            expected_source_revision_id=payload["expected_source_revision_id"],
            expected_twin_revision_id=payload["expected_twin_revision_id"],
            expected_before_source_hash=payload["expected_before_source_hash"],
            expected_after_source_hash=payload["expected_after_source_hash"],
            expected_before_twin_hash=payload["expected_before_twin_hash"],
            expected_after_twin_hash=payload["expected_after_twin_hash"],
            operator_reviewer=payload["operator_reviewer"],
        )
    assert receipt.writes_performed is True
    return packet, dataclasses.asdict(receipt), hashes


def test_source_merge_restore_requires_acknowledgement(api_env):
    client = _client()
    _packet, commit, _hashes = _committed_source_merge(client)
    payload = _source_merge_restore_payload(commit, acknowledged=False)

    resp = client.post("/research/artifacts/source-merge/restore", json=payload)

    assert resp.status_code == 409
    assert resp.json()["detail"] == "source_merge_restore_acknowledgement_required"


def test_source_merge_restore_refuses_binding_mismatch(api_env):
    client = _client()
    _packet, commit, _hashes = _committed_source_merge(client)
    payload = _source_merge_restore_payload(commit)
    payload["expected_after_source_hash"] = "stale-" + payload["expected_after_source_hash"]

    resp = client.post("/research/artifacts/source-merge/restore", json=payload)

    assert resp.status_code == 409
    assert resp.json()["detail"] == "source_merge_restore_binding_mismatch"


def test_source_merge_restore_refuses_when_current_source_drifted(api_env):
    client = _client()
    _packet, commit, _hashes = _committed_source_merge(client)
    with connect_write(os.environ["ANTIEK_DUCKDB_PATH"], purpose="test/source_restore_drift") as con:
        con.execute(
            "UPDATE documents SET raw_text = ? WHERE document_id = ?",
            ["operator edit after merge", "doc-source-merge"],
        )

    resp = client.post(
        "/research/artifacts/source-merge/restore",
        json=_source_merge_restore_payload(commit),
    )

    assert resp.status_code == 409
    assert resp.json()["detail"] == "source_merge_restore_current_hash_mismatch"


def test_source_merge_restore_reverts_source_body_and_emits_metadata_event(api_env):
    client = _client()
    _packet, commit, _hashes = _committed_source_merge(client)

    resp = client.post(
        "/research/artifacts/source-merge/restore",
        json=_source_merge_restore_payload(commit),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "restored"
    assert body["writes_performed"] is True
    assert body["restored_source_hash"] == commit["before_source_hash"]
    with connect_write(os.environ["ANTIEK_DUCKDB_PATH"], purpose="test/read_source_after_restore") as con:
        (raw_text,) = con.execute(
            "SELECT raw_text FROM documents WHERE document_id = ?",
            ["doc-source-merge"],
        ).fetchone()
    assert raw_text == "Original source book body."

    events_path = Path(api_env["events"]) / "read-doc-source-merge.jsonl"
    rows = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    event = rows[-1]
    assert event["event_id"] == body["event_id"]
    assert event["action_type"] == "source_merge.restored"
    assert event["payload"]["source_book_body_restored"] is True
    assert event["payload"]["restored_source_hash"] == commit["before_source_hash"]
    assert "Source merge A" not in json.dumps(event)
    assert "Source merge B" not in json.dumps(event)


def test_source_merge_restore_is_idempotent_after_restore(api_env):
    client = _client()
    _packet, commit, _hashes = _committed_source_merge(client)
    payload = _source_merge_restore_payload(commit)

    first = client.post("/research/artifacts/source-merge/restore", json=payload)
    second = client.post("/research/artifacts/source-merge/restore", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    first_body = first.json()
    second_body = second.json()
    assert first_body["writes_performed"] is True
    assert second_body["writes_performed"] is False
    assert {**first_body, "writes_performed": False} == second_body


def test_get_compose_draft_merge_html_requires_two_ids(api_env):
    client = _client()
    resp = client.get(
        "/research/artifacts/compose/draft-merge.html",
        params={"investigation_ids": "one"},
    )

    assert resp.status_code == 400
    assert "at least two" in resp.json()["detail"]


def test_get_artifact_html_inline_script_free(api_env):
    """Daily-use HTML-native view: inline disposition + zero-script projection."""
    promote_insight(
        text="HTML-native research finding.",
        investigation_id="inv-html-view",
        confidence="moderate",
        source_document_id="doc-1",
    )
    client = _client()
    resp = client.get("/research/inv-html-view/artifact.html")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    disp = resp.headers.get("content-disposition", "")
    assert "inline" in disp
    assert "attachment" not in disp
    assert "HTML-native research finding" in resp.text
    assert "<script" not in resp.text.lower()
    assert resp.headers.get("x-antiek-html-projection") == "script-free; disposition=inline"
