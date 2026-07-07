from __future__ import annotations

import hashlib

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
