from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from interfaces.research.api.auth import SESSION_COOKIE_NAME
from interfaces.research.api.broadcast import EventBroadcaster
from substrate.auth import mint_session_cookie

_SECRET = "owner-api-test-" + "x" * 48
_EMAIL = "owner@example.test"
_OWNER = "owner-1"
_CHOICE = {
    "authority": "user_model",
    "provider_id": "owner-provider",
    "model_id": "owner-model",
}


class RecordingBus(EventBroadcaster):
    def __init__(self) -> None:
        super().__init__()
        self.events = []
        self.failures = 0

    async def broadcast(self, event) -> None:
        if self.failures:
            self.failures -= 1
            raise RuntimeError("private broadcaster detail")
        self.events.append(event)


@pytest.fixture
def owner_api(monkeypatch, tmp_path):
    events = tmp_path / "events"
    events.mkdir(mode=0o700)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    monkeypatch.setenv("ANTIEK_OWNER_LAUNCH_DB", str(tmp_path / "launches.sqlite3"))
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", _SECRET)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", _EMAIL)
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    bus = RecordingBus()
    app = create_app(
        broadcaster=bus,
        register_wrestling=False,
        register_providers=False,
        cors_origins=[],
    )
    bus.unregister_all_handlers()
    client = TestClient(app)
    client.cookies.set(
        SESSION_COOKIE_NAME,
        mint_session_cookie(user_id=_OWNER, email=_EMAIL),
    )
    return client, bus, events


def _body(operation_id: str = "op-1") -> dict[str, object]:
    return {
        "question": "Which evidence is strongest?",
        "operation_id": operation_id,
        "model_choice": _CHOICE,
    }


def _start_rows(events: Path) -> list[dict[str, object]]:
    rows = []
    for path in events.glob("*.jsonl"):
        rows.extend(json.loads(line) for line in path.read_text().splitlines())
    return [row for row in rows if row["action_type"] == "investigation.start_requested"]


def test_exact_concurrent_owner_requests_are_one_event_and_one_response(owner_api):
    client, bus, events = owner_api
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(lambda _: client.post("/investigations", json=_body()), range(8)))

    assert {response.status_code for response in responses} == {202}
    normalized = [
        {key: value for key, value in response.json().items() if key != "owner_model_status"}
        for response in responses
    ]
    assert len({json.dumps(body, sort_keys=True) for body in normalized}) == 1
    assert {response.json()["owner_model_status"] for response in responses} <= {"queued", "replayed"}
    assert len(_start_rows(events)) == 1
    assert len(bus.events) == 1


@pytest.mark.parametrize(
    ("mutation", "status", "detail"),
    [
        ({"model_choice": {**_CHOICE, "model_id": "other"}}, 409, "owner_model_operation_conflict"),
        ({"investigation_id": "inv-alias"}, 409, "owner_model_operation_conflict"),
    ],
)
def test_operation_conflicts_are_constant(owner_api, mutation, status, detail):
    client, _, _ = owner_api
    assert client.post("/investigations", json=_body()).status_code == 202
    body = {**_body(), **mutation}
    response = client.post("/investigations", json=body)
    assert response.status_code == status
    assert response.json() == {"detail": detail}
    assert "other" not in response.text and "inv-alias" not in response.text


def test_unsigned_forged_and_cross_owner_requests_fail_closed(owner_api, monkeypatch):
    client, _, _ = owner_api
    unsigned = TestClient(client.app)
    assert unsigned.post("/investigations", json=_body()).status_code == 401
    unsigned.cookies.set(SESSION_COOKIE_NAME, "forged.cookie")
    assert unsigned.post("/investigations", json=_body()).status_code == 401

    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", f"{_EMAIL},other@example.test")
    other = TestClient(client.app)
    other.cookies.set(
        SESSION_COOKIE_NAME,
        mint_session_cookie(user_id="owner-2", email="other@example.test"),
    )
    first = client.post("/investigations", json=_body("shared-op"))
    second = other.post("/investigations", json=_body("shared-op"))
    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json() == {"detail": "owner_model_operation_conflict"}


@pytest.mark.parametrize(
    "body",
    [
        {"question": "Which evidence is strongest?", "operationId": "op", "model_choice": _CHOICE},
        {"question": "Which evidence is strongest?", "operation_id": "op", "modelChoice": _CHOICE},
        {
            "question": "Which evidence is strongest?",
            "operation_id": "op",
            "model_choice": {
                "authority": "user_model",
                "providerId": "owner-provider",
                "modelId": "owner-model",
            },
        },
    ],
)
def test_owner_selection_aliases_are_rejected_without_reflection(owner_api, body):
    client, _, events = owner_api
    response = client.post("/investigations", json=body)
    assert response.status_code == 422
    assert response.json() == {"detail": "model_selection_invalid"}
    assert "owner-provider" not in response.text and "owner-model" not in response.text
    assert _start_rows(events) == []


def test_strict_append_failure_is_constant_503_without_value_leak(owner_api, monkeypatch):
    client, _, events = owner_api

    def fail(*args, **kwargs):
        raise OSError("secret provider owner-model /tmp/private")

    monkeypatch.setattr("interfaces.research.api.app.emit_typed", fail)
    response = client.post("/investigations", json=_body())
    assert response.status_code == 503
    assert response.json() == {"detail": "owner_model_start_pending"}
    assert "secret" not in response.text and "owner-model" not in response.text
    assert _start_rows(events) == []


def test_append_then_broadcast_failure_retries_without_duplicate_event(owner_api):
    client, bus, events = owner_api
    bus.failures = 1

    failed = client.post("/investigations", json=_body())
    retried = client.post("/investigations", json=_body())

    assert failed.status_code == 503
    assert failed.json() == {"detail": "owner_model_start_pending"}
    assert retried.status_code == 202
    assert retried.json()["owner_model_status"] == "replayed"
    assert len(_start_rows(events)) == 1
    assert len(bus.events) == 1
