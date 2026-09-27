from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from interfaces.research.api.auth import SESSION_COOKIE_NAME
from interfaces.research.api.broadcast import EventBroadcaster
from substrate.auth import mint_session_cookie


class RecordingBus(EventBroadcaster):
    def __init__(self) -> None:
        super().__init__()
        self.events = []

    async def broadcast(self, event) -> None:
        self.events.append(event)


@pytest.fixture
def typed_api(monkeypatch, tmp_path):
    events = tmp_path / "events"
    events.mkdir(mode=0o700)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "typed-owner-test-" + "x" * 48)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "owner@example.test")
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    bus = RecordingBus()
    app = create_app(
        broadcaster=bus,
        register_wrestling=False,
        register_providers=False,
        cors_origins=[],
    )
    bus.unregister_all_handlers()
    owner = TestClient(app)
    owner.cookies.set(
        SESSION_COOKIE_NAME,
        mint_session_cookie(user_id="owner-1", email="owner@example.test"),
    )
    return owner, bus, events


def _event_rows(events):
    return [
        json.loads(line)
        for path in events.glob("*.jsonl")
        for line in path.read_text().splitlines()
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {"action_type": "investigation.start_requested", "question": "Who pays?"},
        {
            "action_type": "investigation.start_requested",
            "question": "Who pays?",
            "owner_user_id": "owner-1",
            "owner_operation_id": "op-forged",
            "owner_model_choices": {
                "decomposer": {
                    "authority": "user_model",
                    "provider_id": "forged-provider",
                    "model_id": "forged-model",
                }
            },
        },
    ],
)
def test_signed_owner_cannot_start_through_generic_event_route(typed_api, payload):
    owner, bus, events = typed_api
    response = owner.post(
        "/events/typed",
        json={
            "investigation_id": "inv-typed-owner",
            "payload": payload,
            "role": "operator",
            "policy_id": "operator-cli",
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "connect_model"}
    assert _event_rows(events) == []
    assert bus.events == []


def test_machine_can_still_submit_start_event(typed_api, monkeypatch):
    owner, bus, events = typed_api
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "machine-token")
    machine = TestClient(owner.app)
    response = machine.post(
        "/events/typed",
        json={
            "investigation_id": "inv-typed-machine",
            "payload": {
                "action_type": "investigation.start_requested",
                "question": "Who pays?",
            },
            "role": "operator",
        },
        headers={"Authorization": "Bearer machine-token"},
    )

    assert response.status_code == 201, response.text
    assert len(_event_rows(events)) == 1
    assert len(bus.events) == 1
