"""API integration: POST /events/typed for ai.action.applied +
POST /ai/undo to invert. End-to-end Wedge 4 acceptance.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_DB_PATH", str(tmp_path / "test.duckdb"))
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.delenv("ANTIEK_AUTH_SECRET", raising=False)
    from interfaces.research.api.app import create_app
    return TestClient(create_app(register_wrestling=False, register_providers=False))


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


def test_apply_then_undo_round_trip(client: TestClient):
    """End-to-end: emit ai.action.applied, then POST /ai/undo,
    confirm the block is back to its prev_state."""
    nb_id, block_id = _seed_notebook_block(client)

    # Simulate the AI sidecar's mutation: flip block_type via the
    # patch endpoint. (In real life, the sidecar would call
    # /notebooks/{id}/blocks/{block_id} then emit the event.)
    # Here we directly patch + then emit.
    r = client.patch(
        f"/notebooks/{nb_id}/blocks/{block_id}",
        json={"block_type": "claim_card", "ref_id": "c-1"},
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

    # Undo.
    r = client.post(
        "/ai/undo",
        json={"event_id": applied_event_id, "investigation_id": "inv-test"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["action_type"] == "ai.action.undone"
    undone_event_id = r.json()["event_id"]
    assert undone_event_id != applied_event_id

    # Block should be back to prose.
    r = client.get(f"/notebooks/{nb_id}")
    assert r.status_code == 200
    blocks = r.json()["blocks"]
    assert len(blocks) == 1
    assert blocks[0]["block_type"] == "prose"
    assert blocks[0]["ref_id"] is None


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
