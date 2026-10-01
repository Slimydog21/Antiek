"""API integration: POST /events/typed for ai.action.applied +
POST /ai/undo to invert. End-to-end Wedge 4 acceptance.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from substrate.auth import mint_magic_link_token


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_DB_PATH", str(tmp_path / "test.duckdb"))
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "notebook-test@example.test")
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "notebook-test-" + "x" * 48)
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    from interfaces.research.api.app import create_app
    client = TestClient(create_app(register_wrestling=False, register_providers=False))
    assert client.get(
        f"/auth/callback?token={mint_magic_link_token('notebook-test@example.test')}",
        follow_redirects=False,
    ).status_code == 302
    return client


def _seed_notebook_block(client: TestClient) -> tuple[str, str]:
    """Create a notebook + one prose block; return (notebook_id, block_id)."""
    r = client.post("/notebooks", json={"title": "T"})
    assert r.status_code == 201, r.text
    nb_id = r.json()["notebook_id"]
    r = client.post(
        f"/notebooks/{nb_id}/blocks",
        json={
            "block_type": "prose",
            "content": {
                "type": "paragraph",
                "content": [{"type": "text", "text": "old"}],
            },
        },
    )
    assert r.status_code == 201, r.text
    # The endpoint returns the full notebook; pick the last block.
    blocks = r.json()["blocks"]
    block_id = blocks[-1]["block_id"]
    return nb_id, block_id


def test_notebook_block_undo_requires_server_receipt(client: TestClient):
    """An applied telemetry event cannot invert a notebook block."""
    nb_id, block_id = _seed_notebook_block(client)

    # Apply a normal block edit, then record the AI telemetry event.
    # block_type is immutable through this endpoint.
    r = client.patch(
        f"/notebooks/{nb_id}/blocks/{block_id}",
        json={"ref_id": "c-1"},
    )
    assert r.status_code == 200, r.text

    # Emit the ai.action.applied event capturing the inversion data.
    r = client.post(
        "/events/typed",
        json={
            "investigation_id": "inv-test",
            "payload": {
                "action_type": "ai.action.applied",
                "target_kind": "notebook_block",
                "target_id": block_id,
                "operator_prompt": "make this a claim card",
                "prev_state": {
                    "block_id": block_id,
                    "notebook_id": nb_id,
                    "block_type": "prose",
                    "ref_id": None,
                    "content_json": {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "old"}],
                    },
                },
                "next_state": {
                    "block_id": block_id,
                    "block_type": "claim_card",
                    "ref_id": "c-1",
                },
                "prev_state_hash": "x" * 64,
            },
        },
    )
    assert r.status_code == 201, r.text
    applied_event_id = r.json()["event_id"]

    before = client.get(f"/notebooks/{nb_id}").json()["blocks"]

    # The event has no server-issued mutation receipt.
    r = client.post(
        "/ai/undo",
        json={"event_id": applied_event_id, "investigation_id": "inv-test"},
    )
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["code"] == "notebook_undo_requires_server_receipt"

    # No inverse occurred.
    r = client.get(f"/notebooks/{nb_id}")
    assert r.status_code == 200
    assert r.json()["blocks"] == before


def test_undo_unknown_event_404(client: TestClient):
    r = client.post(
        "/ai/undo",
        json={"event_id": "evt-doesnotexist", "investigation_id": "inv-test"},
    )
    assert r.status_code == 404
    body = r.json()
    assert body["detail"]["code"] == "applied_event_not_found"


def test_undo_wrong_action_type_422(client: TestClient):
    """Pointing /ai/undo at a non-ai event returns 422."""
    # Emit a non-AI typed event first.
    r = client.post(
        "/events/typed",
        json={
            "investigation_id": "inv-test",
            "payload": {
                "action_type": "rubric.scored",
                "rubric_id": "r-1",
                "final_score": 0.9,
            },
        },
    )
    assert r.status_code == 201, r.text
    other_event_id = r.json()["event_id"]

    r = client.post(
        "/ai/undo",
        json={"event_id": other_event_id, "investigation_id": "inv-test"},
    )
    assert r.status_code == 422
    body = r.json()
    assert body["detail"]["code"] == "wrong_action_type"
