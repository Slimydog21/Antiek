from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime.db_lock import connect_write
from services.html_projection.island import embed_island
from substrate.graph import ensure_initialized
from substrate.research_artifact.paths import artifact_source_path_for
from substrate.research_artifact.store import ResearchArtifactStore


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture()
def feedback_api(monkeypatch, tmp_path):
    db_path = str(tmp_path / "graph.duckdb")
    artifacts = tmp_path / "artifacts"
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(artifacts))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_FEEDBACK_ENABLED", "1")
    ensure_initialized(db_path)
    text = "Evidence needs a primary citation."
    model = {
        "title": "Research",
        "content": [],
        "research_artifact": {
            "schema_version": 1,
            "investigation_id": "inv-1",
            "problem_question": "Question?",
            "insights": [
                {
                    "node_id": "insight-1",
                    "text": text,
                    "source_document_id": "doc-1",
                    "confidence": "high",
                }
            ],
            "open_questions": [],
            "synthesis_excerpt": None,
            "synthesis_withheld": False,
            "source_event_ids": [],
            "agent_notes": [],
        },
    }
    island = embed_island(model)
    source = f"<html><body>{island}</body></html>".encode()
    store = ResearchArtifactStore(db_path)
    source_hash = _sha(source)
    store.save_source(
        "artifact-1",
        "inv-1",
        "__operator__",
        artifact_source_path_for("artifact-1", source_hash),
        source,
    )
    rendered = f"<html><body><main>{island}</main></body></html>"
    content_hash = _sha(rendered.encode())
    assert store.add_version(
        "artifact-1", "__operator__", "stone", rendered, content_hash
    )[0] == 1
    with connect_write(db_path, purpose="test/seed-feedback-route-rights") as con:
        con.execute(
            "INSERT INTO documents ("
            "document_id, source_tier, document_type, owner_user_id, content_class"
            ") VALUES ('doc-1', 1, 'paper', '__operator__', 'public_domain')"
        )
    return TestClient(create_app(register_wrestling=False)), source_hash, content_hash, text


def test_operator_creates_and_reads_version_bound_feedback(feedback_api) -> None:
    client, source_hash, content_hash, text = feedback_api
    response = client.post(
        "/artifacts/artifact-1/versions/1/feedback/threads",
        headers={"Idempotency-Key": "feedback-key-0001"},
        json={
            "investigation_id": "inv-1",
            "artifact_content_sha256": content_hash,
            "artifact_source_sha256": source_hash,
            "anchor": {
                "normalization": "unicode-nfc-v1",
                "node_id": "insight-1",
                "node_text_sha256": _sha(text.encode()),
                "start_scalar": 0,
                "end_scalar": 8,
                "quote": "Evidence",
                "prefix": "",
                "suffix": " needs a primary citation.",
            },
            "body_markdown": "Please add the primary citation.",
        },
    )

    assert response.status_code == 201, response.text
    created = response.json()
    assert created["artifact"]["version"] == 1
    assert created["work"]["state"] == "queued"
    assert created["items"][0]["body_markdown"] == "Please add the primary citation."
    loaded = client.get(f"/feedback/threads/{created['thread_id']}")
    assert loaded.status_code == 200
    assert loaded.json() == created
    assert loaded.headers["ETag"].startswith('"')
    unchanged = client.get(
        f"/feedback/threads/{created['thread_id']}",
        headers={"If-None-Match": loaded.headers["ETag"]},
    )
    assert unchanged.status_code == 304
    assert unchanged.content == b""
    resolved = client.post(
        f"/feedback/threads/{created['thread_id']}/resolve",
        headers={"Idempotency-Key": "feedback-resolve-0001"},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["state"] == "resolved"
    changed = client.get(
        f"/feedback/threads/{created['thread_id']}",
        headers={"If-None-Match": loaded.headers["ETag"]},
    )
    assert changed.status_code == 200
    assert changed.headers["ETag"] != loaded.headers["ETag"]


def test_feedback_create_requires_idempotency_key(feedback_api) -> None:
    client, source_hash, content_hash, text = feedback_api
    response = client.post(
        "/artifacts/artifact-1/versions/1/feedback/threads",
        json={
            "investigation_id": "inv-1",
            "artifact_content_sha256": content_hash,
            "artifact_source_sha256": source_hash,
            "anchor": {
                "normalization": "unicode-nfc-v1",
                "node_id": "insight-1",
                "node_text_sha256": _sha(text.encode()),
                "start_scalar": 0,
                "end_scalar": 8,
                "quote": "Evidence",
                "prefix": "",
                "suffix": " needs a primary citation.",
            },
            "body_markdown": "Please add the primary citation.",
        },
    )

    assert response.status_code == 400
