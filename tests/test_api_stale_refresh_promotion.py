from __future__ import annotations

import hashlib
import json
import os

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api import create_app
from processing.embedding import _reset_default_provider, set_default_embedding_provider
from runtime.db_lock import connect_write
from substrate.event_log import trajectory
from substrate.graph.insight_question import knowledge_unit_of
from substrate.graph.ops import insert_chunk, insert_document
from substrate.graph.schema import init_database_at_path


class _FakeEmbedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [b / 255.0 for b in digest[: self.dimension]]


@pytest.fixture(autouse=True)
def _isolated_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    db_path = str(tmp_path / "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    init_database_at_path(db_path)
    set_default_embedding_provider(_FakeEmbedding())
    yield db_path
    _reset_default_provider()


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _seed_refresh_chunk(db_path: str) -> None:
    with connect_write(db_path, purpose="test/api-stale-refresh-seed") as con:
        insert_document(
            con,
            document_id="doc-refresh",
            source_tier=2,
            document_type="paper",
            title="Refresh Evidence",
        )
        insert_chunk(
            con,
            document_id="doc-refresh",
            chunk_id="chunk-refresh-1",
            chunk_index=0,
            text="Refresh evidence one.",
        )


def _post_candidate(client: TestClient) -> str:
    response = client.post(
        "/events/typed",
        json={
            "investigation_id": "inv-parent",
            "payload": {
                "action_type": "stale_reuse.refresh.promotion_candidate",
                "unit_id": "unit-stale",
                "source_investigation_id": "inv-source",
                "refresh_investigation_id": "inv-refresh",
                "summary": "Source claim remains current after refresh.",
                "supporting_chunk_ids": ["chunk-refresh-1"],
                "accepted_event_id": "evt-accepted",
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["event_id"]


def _write_event(investigation_id: str, row: dict) -> None:
    events_dir = os.environ["ANTIEK_RESEARCH_EVENTS_DIR"]
    os.makedirs(events_dir, exist_ok=True)
    path = os.path.join(events_dir, f"{investigation_id}.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def test_stale_refresh_promotion_endpoint_deposits_recorded_candidate(
    client: TestClient,
    _isolated_runtime: str,
):
    _seed_refresh_chunk(_isolated_runtime)
    candidate_event_id = _post_candidate(client)

    response = client.post(
        "/stale-refresh/promotions/process",
        json={
            "investigation_id": "inv-parent",
            "candidate_event_id": candidate_event_id,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["action_type"] == "stale_reuse.refresh.promotion_result"
    assert body["status"] == "deposited"
    assert body["reason"] == "ready"
    assert body["primary_chunk_id"] == "chunk-refresh-1"
    assert body["primary_source_document_id"] == "doc-refresh"
    assert body["deposited_node_id"]

    with connect_write(_isolated_runtime, purpose="test/api-stale-refresh-read") as con:
        unit = knowledge_unit_of(
            con,
            body["deposited_node_id"],
            content_class="public_domain",
        )
    assert unit.investigation_id == "inv-parent"
    assert unit.provenance.source_document_id == "doc-refresh"
    assert unit.provenance.chunk_id == "chunk-refresh-1"

    result_events = [
        event
        for event in trajectory("inv-parent")
        if event["action_type"] == "stale_reuse.refresh.promotion_result"
    ]
    assert len(result_events) == 1
    assert result_events[0]["event_id"] == body["event_id"]
    assert result_events[0]["parent_event_id"] == candidate_event_id


def test_stale_refresh_promotion_endpoint_404s_unknown_candidate(
    client: TestClient,
):
    response = client.post(
        "/stale-refresh/promotions/process",
        json={
            "investigation_id": "inv-parent",
            "candidate_event_id": "evt-missing",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "candidate_event_not_found"


def test_stale_refresh_promotion_endpoint_rejects_wrong_event_type(
    client: TestClient,
):
    event_response = client.post(
        "/events/typed",
        json={
            "investigation_id": "inv-parent",
            "payload": {
                "action_type": "dispatch.call",
                "provider": "p",
                "model": "m",
                "tier": "flash",
                "target_role": "decomposer",
                "input_tokens": 1,
                "output_tokens": 1,
                "cost_usd": 0.0,
                "latency_ms": 1,
                "prompt_hash": "h",
            },
        },
    )
    assert event_response.status_code == 201, event_response.text

    response = client.post(
        "/stale-refresh/promotions/process",
        json={
            "investigation_id": "inv-parent",
            "candidate_event_id": event_response.json()["event_id"],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "wrong_action_type"


def test_stale_refresh_resolutions_endpoint_lists_latest_resolution_per_entity(
    client: TestClient,
):
    _write_event(
        "inv-old",
        {
            "event_id": "evt-old",
            "investigation_id": "inv-old",
            "action_type": "graph.staleness.resolve",
            "emitted_at": "2026-07-07T15:00:00Z",
            "payload": {
                "action_type": "graph.staleness.resolve",
                "flag_id": "stale-edge-one-personnel",
                "entity_kind": "edge",
                "entity_id": "edge-one",
                "status": "refreshed",
                "notes": "older resolution",
            },
        },
    )
    _write_event(
        "inv-new",
        {
            "event_id": "evt-new",
            "investigation_id": "inv-new",
            "action_type": "graph.staleness.resolve",
            "parent_event_id": "evt-candidate",
            "emitted_at": "2026-07-07T15:05:00Z",
            "payload": {
                "action_type": "graph.staleness.resolve",
                "flag_id": "stale-edge-one-personnel",
                "entity_kind": "edge",
                "entity_id": "edge-one",
                "status": "confirmed_stale",
                "notes": "newer resolution",
            },
        },
    )
    _write_event(
        "inv-other",
        {
            "event_id": "evt-other",
            "investigation_id": "inv-other",
            "action_type": "graph.staleness.resolve",
            "emitted_at": "2026-07-07T15:02:00Z",
            "payload": {
                "action_type": "graph.staleness.resolve",
                "flag_id": "stale-edge-two-market",
                "entity_kind": "edge",
                "entity_id": "edge-two",
                "status": "dismissed",
                "notes": "",
            },
        },
    )
    _write_event(
        "inv-malformed",
        {
            "event_id": "evt-malformed",
            "investigation_id": "inv-malformed",
            "action_type": "graph.staleness.resolve",
            "emitted_at": "2026-07-07T15:06:00Z",
            "payload": {
                "action_type": "graph.staleness.resolve",
                "entity_kind": "edge",
                "entity_id": "edge-bad",
                "status": "invented",
            },
        },
    )

    response = client.get("/stale-refresh/resolutions")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["count"] == 2
    assert body["resolutions"][0] == {
        "event_id": "evt-new",
        "investigation_id": "inv-new",
        "emitted_at": "2026-07-07T15:05:00Z",
        "parent_event_id": "evt-candidate",
        "flag_id": "stale-edge-one-personnel",
        "entity_kind": "edge",
        "entity_id": "edge-one",
        "status": "confirmed_stale",
        "notes": "newer resolution",
    }
    assert body["resolutions"][1]["entity_id"] == "edge-two"

    filtered = client.get("/stale-refresh/resolutions", params={"entity_id": "edge-two"})
    assert filtered.status_code == 200, filtered.text
    assert filtered.json()["count"] == 1
    assert filtered.json()["resolutions"][0]["event_id"] == "evt-other"
