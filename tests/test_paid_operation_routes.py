from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api.paid_operation_routes import (
    PaidOperationRouteRuntime,
    authenticated_paid_operation_subject,
    paid_operation_router,
    set_paid_operation_runtime,
)
from substrate.paid_operations import (
    ConsentKeyring,
    PaidOperationConsentService,
    PaidOperationStore,
    Subject,
)
from tests.test_paid_operation_store import collective_payload


def _client(tmp_path: Path, *, owner: str = "owner-1", account: str = "acct-1") -> tuple[TestClient, PaidOperationStore]:
    db = tmp_path / "authority.sqlite3"
    store = PaidOperationStore(db)
    service = PaidOperationConsentService(
        store,
        ConsentKeyring(active_key_id="key-1", keys={"key-1": b"k" * 32}),
        clock_ms=lambda: 1_100,
        nonce_factory=lambda: b"n" * 32,
        ttl_ms=500,
    )
    app = FastAPI()
    set_paid_operation_runtime(PaidOperationRouteRuntime(consent=service))

    def subject_override(request: Request) -> Subject:
        assert "owner_user_id" not in request.query_params
        return Subject(owner_user_id=owner, account_id=account)

    app.dependency_overrides[authenticated_paid_operation_subject] = subject_override
    app.include_router(paid_operation_router)
    return TestClient(app), store


def test_issue_route_no_store_and_conflict_is_token_free(tmp_path: Path) -> None:
    client, store = _client(tmp_path)
    store.create_or_replay(Subject("owner-1", "acct-1"), "op-1", "collective_interrogation_v1", collective_payload())

    response = client.post("/paid-operations/op-1/consent", json={"owner_user_id": "attacker"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, private"
    token = response.json()["token"]

    conflict = client.post("/paid-operations/op-1/consent", json={})
    assert conflict.status_code == 409
    body = conflict.json()
    assert body["detail"]["code"] == "consent_already_issued"
    assert token not in conflict.text
    assert "token" not in body["detail"]["operation"]


def test_route_foreign_and_absent_are_identical_404(tmp_path: Path) -> None:
    client, store = _client(tmp_path, owner="owner-2", account="acct-1")
    store.create_or_replay(Subject("owner-1", "acct-1"), "op-1", "collective_interrogation_v1", collective_payload())

    foreign = client.post("/paid-operations/op-1/consent", json={})
    absent = client.post("/paid-operations/op-missing/consent", json={})
    assert foreign.status_code == absent.status_code == 404
    assert foreign.json() == absent.json() == {"detail": {"code": "paid_operation_unavailable"}}


def test_queue_route_redacts_unclaimable_token_and_enqueues_once(tmp_path: Path) -> None:
    client, store = _client(tmp_path)
    subject = Subject("owner-1", "acct-1")
    store.create_or_replay(subject, "op-1", "collective_interrogation_v1", collective_payload())
    token = client.post("/paid-operations/op-1/consent", json={}).json()["token"]

    bad = client.post(
        "/paid-operations/op-1/queue",
        headers={"X-Antiek-Paid-Consent": token + "x"},
        json={"options": {}},
    )
    assert bad.status_code == 409
    assert token not in bad.text

    first = client.post(
        "/paid-operations/op-1/queue",
        headers={"X-Antiek-Paid-Consent": token},
        json={"options": {"attempt": 1}},
    )
    second = client.post("/paid-operations/op-1/queue", json={"options": {"attempt": 1}})
    assert first.status_code == second.status_code == 200
    assert first.json()["queue"] == second.json()["queue"]
    drift = client.post("/paid-operations/op-1/queue", json={"options": {"attempt": 2}})
    assert drift.status_code == 409
    assert token not in drift.text


def test_oversized_bearer_is_redacted_by_handler(tmp_path: Path) -> None:
    client, store = _client(tmp_path)
    subject = Subject("owner-1", "acct-1")
    store.create_or_replay(subject, "op-1", "collective_interrogation_v1", collective_payload())
    token = client.post("/paid-operations/op-1/consent", json={}).json()["token"]

    response = client.post(
        "/paid-operations/op-1/queue",
        headers={"X-Antiek-Paid-Consent": token + ("x" * 4096)},
        json={"options": {}},
    )
    assert response.status_code == 409
    assert token not in response.text


def test_subject_rejects_unauthenticated_local_and_uses_server_account() -> None:
    import pytest
    from fastapi import HTTPException

    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    request.state.user_id = "owner-1"
    request.state.account_id = "acct-1"
    request.state.auth_method = "unauthenticated_local"
    with pytest.raises(HTTPException) as exc_info:
        authenticated_paid_operation_subject(request)
    assert exc_info.value.status_code == 401

    request.state.auth_method = "antiek_session_cookie"
    assert authenticated_paid_operation_subject(request) == Subject("owner-1", "acct-1")
