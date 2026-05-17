"""Tests for the FastAPI substrate surface.

What this file proves:

1. ``/health`` returns version + schema version + subscriber count.
2. ``POST /events/typed`` accepts a discriminated TypedPayload, validates
   it against the Pydantic schema, emits a typed event, and returns the
   event_id.
3. Wrestling action_types require document_id on the envelope; the API
   rejects with 422 (architecture_notes §9.1).
4. Non-wrestling typed events (DispatchCall, ContextPackAssembled) post
   cleanly without document_id.
5. ``GET /trajectory/{id}`` returns the events for an investigation,
   ordered by emission time.
6. Posting a malformed payload (missing required field, wrong literal
   value) yields 422 with the Pydantic error.
7. The WebSocket ``/ws/events`` connects, receives the event broadcast
   when a typed event is posted, and respects the ``investigation_id``
   filter.
"""

from __future__ import annotations

import os
import sys

import pytest
from fastapi.testclient import TestClient

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from interfaces.research.api import create_app  # noqa: E402
from substrate.constants import ANTIEK_PARAM_VERSION  # noqa: E402
from substrate.schemas import EVENT_SCHEMA_VERSION  # noqa: E402


@pytest.fixture(autouse=True)
def _events_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_health_returns_versions(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["param_version"] == ANTIEK_PARAM_VERSION
    assert body["schema_version"] == EVENT_SCHEMA_VERSION
    assert body["subscriber_count"] == 0


# ---------------------------------------------------------------------------
# POST /events/typed
# ---------------------------------------------------------------------------


def test_post_typed_dispatch_call(client: TestClient):
    """Non-wrestling event — document_id is None and the post succeeds."""
    payload = {
        "action_type": "dispatch.call",
        "provider": "openai-compat",
        "model": "deepseek-flash",
        "tier": "flash",
        "target_role": "decomposer",
        "input_tokens": 100,
        "output_tokens": 25,
        "cost_usd": 0.0001,
        "latency_ms": 200,
        "prompt_hash": "sha256:abc",
    }
    r = client.post(
        "/events/typed",
        json={"investigation_id": "inv-1", "payload": payload, "role": "decomposer"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["action_type"] == "dispatch.call"
    assert body["event_id"].startswith("evt-")


def test_post_typed_wrestling_event_requires_document_id(client: TestClient):
    """Wrestling action_types must carry document_id on the envelope.
    The API returns 422 rather than letting the Pydantic validator
    raise a generic 500 server error."""
    payload = {
        "action_type": "document.loaded",
        "media_type": "pdf",
        "content_hash": "sha:doc",
        "size_bytes": 1000,
    }
    r = client.post(
        "/events/typed",
        json={"investigation_id": "inv-2", "payload": payload},  # no document_id
    )
    assert r.status_code == 422
    assert "document_id" in r.text


def test_post_typed_wrestling_event_with_document_id(client: TestClient):
    payload = {
        "action_type": "document.loaded",
        "media_type": "pdf",
        "content_hash": "sha:doc",
        "size_bytes": 1000,
        "title": "paper.pdf",
        "page_count": 12,
    }
    r = client.post(
        "/events/typed",
        json={
            "investigation_id": "inv-2",
            "document_id": "doc-A",
            "payload": payload,
        },
    )
    assert r.status_code == 201
    assert r.json()["action_type"] == "document.loaded"


def test_post_typed_malformed_payload_returns_422(client: TestClient):
    """Missing the required ``provider`` field on a DispatchCall payload."""
    payload = {
        "action_type": "dispatch.call",
        # missing provider, model, tier, etc.
    }
    r = client.post(
        "/events/typed",
        json={"investigation_id": "inv-3", "payload": payload},
    )
    assert r.status_code == 422


def test_post_typed_unknown_action_type_returns_422(client: TestClient):
    """The discriminator must match a registered variant."""
    r = client.post(
        "/events/typed",
        json={
            "investigation_id": "inv-4",
            "payload": {"action_type": "not.a.real.action", "x": 1},
        },
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /trajectory
# ---------------------------------------------------------------------------


def test_get_trajectory_returns_emitted_events_in_order(client: TestClient):
    # Emit 3 events for the same investigation.
    base = {
        "action_type": "dispatch.call",
        "provider": "p", "model": "m", "tier": "flash", "target_role": "decomposer",
        "input_tokens": 1, "output_tokens": 1, "cost_usd": 0.0, "latency_ms": 1,
        "prompt_hash": "h",
    }
    for _ in range(3):
        r = client.post(
            "/events/typed",
            json={"investigation_id": "inv-T", "payload": base},
        )
        assert r.status_code == 201

    r = client.get("/trajectory/inv-T")
    assert r.status_code == 200
    body = r.json()
    assert body["investigation_id"] == "inv-T"
    assert body["count"] == 3
    assert len(body["events"]) == 3
    # All should be dispatch.call events.
    assert all(e["action_type"] == "dispatch.call" for e in body["events"])
    # Emitted_at strings are monotonically non-decreasing (sorted by
    # emit time by the trajectory loader).
    timestamps = [e["emitted_at"] for e in body["events"]]
    assert timestamps == sorted(timestamps)


def test_get_trajectory_unknown_investigation_returns_empty(client: TestClient):
    r = client.get("/trajectory/never-existed")
    assert r.status_code == 200
    assert r.json()["count"] == 0


def test_get_trajectory_limit_returns_last_n(client: TestClient):
    base = {
        "action_type": "dispatch.call",
        "provider": "p", "model": "m", "tier": "flash", "target_role": "decomposer",
        "input_tokens": 1, "output_tokens": 1, "cost_usd": 0.0, "latency_ms": 1,
        "prompt_hash": "h",
    }
    for i in range(5):
        # vary prompt_hash so events are distinguishable.
        client.post(
            "/events/typed",
            json={"investigation_id": "inv-L", "payload": {**base, "prompt_hash": f"h{i}"}},
        )
    r = client.get("/trajectory/inv-L?limit=2")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    # Last two — h3 and h4.
    hashes = [e["payload"]["prompt_hash"] for e in body["events"]]
    assert hashes == ["h3", "h4"]


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------


def test_websocket_receives_broadcast_after_post(client: TestClient):
    """End-to-end: open WS, POST event, receive the event on WS."""
    with client.websocket_connect("/ws/events") as ws:
        payload = {
            "action_type": "dispatch.call",
            "provider": "p", "model": "m", "tier": "flash", "target_role": "r",
            "input_tokens": 1, "output_tokens": 1, "cost_usd": 0.0, "latency_ms": 1,
            "prompt_hash": "h-ws",
        }
        r = client.post(
            "/events/typed",
            json={"investigation_id": "inv-WS", "payload": payload},
        )
        assert r.status_code == 201
        event_id = r.json()["event_id"]

        # The first frame should be our event.
        frame = ws.receive_json()
        assert frame["event_id"] == event_id
        assert frame["payload"]["action_type"] == "dispatch.call"
        assert frame["investigation_id"] == "inv-WS"


def test_websocket_investigation_filter_excludes_other_investigations(client: TestClient):
    """A WebSocket subscribed to inv-X should NOT receive events for inv-Y."""
    with client.websocket_connect("/ws/events?investigation_id=inv-X") as ws:
        base = {
            "action_type": "dispatch.call",
            "provider": "p", "model": "m", "tier": "flash", "target_role": "r",
            "input_tokens": 1, "output_tokens": 1, "cost_usd": 0.0, "latency_ms": 1,
            "prompt_hash": "h",
        }
        # Emit one for inv-Y (should be filtered out) and one for inv-X.
        client.post("/events/typed",
                    json={"investigation_id": "inv-Y", "payload": base})
        r2 = client.post("/events/typed",
                         json={"investigation_id": "inv-X", "payload": base})
        target_id = r2.json()["event_id"]

        frame = ws.receive_json()
        # Must be the inv-X event — inv-Y was filtered server-side.
        assert frame["investigation_id"] == "inv-X"
        assert frame["event_id"] == target_id


def test_websocket_health_subscriber_count_reflects_connection(client: TestClient):
    """Subscriber count goes up while WS is open, back down on close."""
    pre = client.get("/health").json()["subscriber_count"]
    assert pre == 0
    with client.websocket_connect("/ws/events"):
        during = client.get("/health").json()["subscriber_count"]
        assert during == 1
    post = client.get("/health").json()["subscriber_count"]
    assert post == 0
