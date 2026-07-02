"""Thread-navigation API tests (antiek-unified SPR-06).

The router is the HTTP edge of the derived thread view. These tests keep the
route honest: it serializes reconstructed threads, refuses copied/forked
threads, and returns a degenerate one-hop thread when no seam has fired.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api import thread as thread_api


NODE = "insight-api-1"


def _seam_event(
    event_id: str,
    action_type: str,
    *,
    entity_id: str = NODE,
    entity_kind: str = "insight_node",
    provenance_ref: str,
    emitted_at: str,
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "action_type": action_type,
        "emitted_at": emitted_at,
        "payload": {
            "entity_id": entity_id,
            "entity_kind": entity_kind,
            "provenance_ref": provenance_ref,
            "terminates": True,
        },
    }


def _client(monkeypatch, events: list[dict[str, Any]]) -> TestClient:
    monkeypatch.setattr(thread_api, "_collect_seam_events", lambda events_dir=None: events)
    app = FastAPI()
    app.include_router(thread_api.make_router(events_dir="/ignored"))
    return TestClient(app)


def test_thread_route_serializes_ordered_thread(monkeypatch) -> None:
    client = _client(
        monkeypatch,
        [
            _seam_event(
                "evt-2",
                "seam.read_to_write",
                provenance_ref="evt-1",
                emitted_at="2026-05-25T10:01:00",
            ),
            _seam_event(
                "evt-1",
                "seam.research_to_read",
                provenance_ref="evt-origin",
                emitted_at="2026-05-25T10:00:00",
            ),
        ],
    )

    response = client.get(f"/thread/{NODE}")

    assert response.status_code == 200
    body = response.json()
    assert body["canonical_entity_id"] == NODE
    assert body["is_degenerate"] is False
    assert [hop["workflow"] for hop in body["hops"]] == ["research", "read", "write"]
    assert [hop["entity_id"] for hop in body["hops"]] == [NODE, NODE, NODE]
    assert body["hops"][1]["seam_event_id"] == "evt-1"
    assert body["hops"][2]["seam_event_id"] == "evt-2"


def test_thread_route_refuses_copied_entity(monkeypatch) -> None:
    client = _client(
        monkeypatch,
        [
            _seam_event(
                "evt-1",
                "seam.research_to_read",
                provenance_ref="evt-origin",
                emitted_at="2026-05-25T10:00:00",
            ),
            _seam_event(
                "evt-2",
                "seam.read_to_write",
                entity_id=f"{NODE}-COPY",
                provenance_ref="evt-1",
                emitted_at="2026-05-25T10:01:00",
            ),
        ],
    )

    response = client.get(f"/thread/{NODE}")

    assert response.status_code == 409
    assert "copied entity" in response.json()["detail"]


def test_thread_route_accepts_outline_block_trace_reference(monkeypatch) -> None:
    events = [
        _seam_event(
            "evt-1",
            "seam.research_to_read",
            provenance_ref="evt-origin",
            emitted_at="2026-05-25T10:00:00",
        ),
        _seam_event(
            "evt-2",
            "seam.read_to_write",
            provenance_ref="evt-1",
            emitted_at="2026-05-25T10:01:00",
        ),
        _seam_event(
            "evt-3",
            "seam.write_to_read",
            entity_id="oblk-api-1",
            entity_kind="outline_block",
            provenance_ref="evt-2",
            emitted_at="2026-05-25T10:02:00",
        ),
    ]
    client = _client(monkeypatch, events)

    response = client.get(f"/thread/{NODE}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert [hop["workflow"] for hop in body["hops"]] == [
        "research",
        "read",
        "write",
        "read",
    ]
    assert body["hops"][-1]["entity_id"] == "oblk-api-1"
    assert body["hops"][-1]["entity_kind"] == "outline_block"


def test_thread_route_can_start_from_outline_block_reference(monkeypatch) -> None:
    client = _client(
        monkeypatch,
        [
            _seam_event(
                "evt-1",
                "seam.research_to_read",
                provenance_ref="evt-origin",
                emitted_at="2026-05-25T10:00:00",
            ),
            _seam_event(
                "evt-2",
                "seam.read_to_write",
                provenance_ref="evt-1",
                emitted_at="2026-05-25T10:01:00",
            ),
            _seam_event(
                "evt-3",
                "seam.write_to_read",
                entity_id="oblk-api-1",
                entity_kind="outline_block",
                provenance_ref="evt-2",
                emitted_at="2026-05-25T10:02:00",
            ),
        ],
    )

    response = client.get("/thread/oblk-api-1")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["canonical_entity_id"] == NODE
    assert body["canonical_entity_kind"] == "insight_node"
    assert body["hops"][-1]["entity_id"] == "oblk-api-1"
    assert body["hops"][-1]["entity_kind"] == "outline_block"


def test_thread_route_returns_degenerate_thread_when_no_seam_exists(monkeypatch) -> None:
    client = _client(monkeypatch, [])

    response = client.get(f"/thread/{NODE}")

    assert response.status_code == 200
    body = response.json()
    assert body["is_degenerate"] is True
    assert [hop["workflow"] for hop in body["hops"]] == ["research"]
    assert body["hops"][0]["seam_event_id"] is None
