from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

import substrate.multimedia.execution_authorization_issuer as authorization_issuer
from interfaces.research.api.multimedia_execution_routes import (
    create_multimedia_execution_router,
)
from runtime.db_lock import connect_write
from substrate.multimedia.execution_authorization import (
    MultimediaExecutionAuthorization,
    execute_authorized_call,
)
from substrate.multimedia.execution_authorization_issuer import (
    ExecutionAuthorizationIssueConflict,
    ExecutionAuthorizationIssuer,
    ExecutionAuthorizationIssueRequest,
)
from substrate.multimedia.read_model import CreateMultimediaDraftRequest, MultimediaAssetStore

KEY = b"multimedia-execution-route-signing-key"
NOW = datetime(2026, 7, 11, 2, 0, tzinfo=UTC)


def _asset(root: Path, *, approved: bool = True, route_policy: str = "balanced"):
    store = MultimediaAssetStore(root)
    record = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="high-bypass turbofan history",
            target_minutes=20,
            mode="hybrid",
            route_policy=route_policy,
            sources=("High bypass ratios improved propulsive efficiency.",),
        )
    )
    return store.approve_dry_run(record.asset.asset_id) if approved else record


def _client(tmp_path: Path, *, now: datetime = NOW) -> TestClient:
    app = FastAPI()

    @app.middleware("http")
    async def identity(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.headers.get("x-test-auth") == "yes":
            request.state.auth_method = "bearer_token"
            request.state.user_id = request.headers.get("x-test-user", "operator")
        return await call_next(request)

    app.include_router(
        create_multimedia_execution_router(
            db_path=str(tmp_path / "execution.duckdb"),
            signing_key=KEY,
            asset_store_root=str(tmp_path / "assets"),
            clock=lambda: now,
        )
    )
    return TestClient(app)


def _body(record, **overrides: object) -> dict[str, object]:  # type: ignore[no-untyped-def]
    body: dict[str, object] = {
        "request_id": "approval-1",
        "revision_id": record.asset.revision_id,
        "provider": "krea",
        "route_policy": record.asset.route_policy,
        "approved_ceiling_cents": 250,
        "ttl_seconds": 900,
    }
    body.update(overrides)
    return body


def _post(client: TestClient, asset_id: str, body: dict[str, object], *, user: str = "operator"):
    return client.post(
        f"/multimedia/assets/{asset_id}/execution-authorizations",
        headers={"x-test-auth": "yes", "x-test-user": user},
        json=body,
    )


def test_authenticated_issue_is_durable_and_exactly_idempotent(tmp_path: Path) -> None:
    record = _asset(tmp_path / "assets")
    client = _client(tmp_path)
    response = _post(client, record.asset.asset_id, _body(record))
    assert response.status_code == 201, response.text
    receipt = response.json()
    assert receipt["operator_id"] == "operator"
    assert receipt["asset_id"] == record.asset.asset_id
    assert receipt["revision_id"] == record.asset.revision_id
    assert receipt["approved_ceiling_cents"] == 250
    assert "signing_key" not in response.text

    restarted = _client(tmp_path, now=NOW + timedelta(minutes=5))
    replay = _post(restarted, record.asset.asset_id, _body(record))
    assert replay.status_code == 201
    assert replay.json() == receipt


def test_conflicting_idempotency_replay_fails_closed(tmp_path: Path) -> None:
    record = _asset(tmp_path / "assets")
    client = _client(tmp_path)
    assert _post(client, record.asset.asset_id, _body(record)).status_code == 201
    conflict = _post(
        client,
        record.asset.asset_id,
        _body(record, approved_ceiling_cents=251),
    )
    assert conflict.status_code == 409


def test_authenticated_revocation_is_exact_and_operator_bound(tmp_path: Path) -> None:
    record = _asset(tmp_path / "assets")
    client = _client(tmp_path)
    issued = _post(client, record.asset.asset_id, _body(record))
    assert issued.status_code == 201
    route = "/multimedia/execution-authorizations/revoke"
    revoked = client.post(
        route,
        headers={"x-test-auth": "yes", "x-test-user": "operator"},
        json=issued.json(),
    )
    assert revoked.status_code == 200, revoked.text
    replay = client.post(
        route,
        headers={"x-test-auth": "yes", "x-test-user": "operator"},
        json=issued.json(),
    )
    assert replay.status_code == 200
    assert replay.json() == revoked.json()

    wrong_operator = client.post(
        route,
        headers={"x-test-auth": "yes", "x-test-user": "other"},
        json=issued.json(),
    )
    assert wrong_operator.status_code == 403

    consumed_issue = _post(
        client,
        record.asset.asset_id,
        _body(record, request_id="consumed-before-revoke"),
    )
    consumed = MultimediaExecutionAuthorization.from_dict(consumed_issue.json())
    execute_authorized_call(
        consumed,
        signing_key=KEY,
        db_path=str(tmp_path / "execution.duckdb"),
        operator_id="operator",
        asset_id=record.asset.asset_id,
        revision_id=record.asset.revision_id,
        provider="krea",
        route_policy="balanced",
        projected_max_cents=250,
        now=NOW,
        call=lambda: ("completed", 1),
    )
    consumed_revoke = client.post(
        route,
        headers={"x-test-auth": "yes", "x-test-user": "operator"},
        json=consumed_issue.json(),
    )
    assert consumed_revoke.status_code == 409


def test_issuer_serializes_identical_and_conflicting_concurrent_requests(tmp_path: Path) -> None:
    issuer = ExecutionAuthorizationIssuer(
        db_path=str(tmp_path / "concurrent.duckdb"),
        signing_key=KEY,
    )
    base = ExecutionAuthorizationIssueRequest(
        request_id="concurrent-approval",
        operator_id="operator",
        asset_id="asset-1",
        revision_id="rev-1",
        provider="krea",
        route_policy="balanced",
        approved_ceiling_cents=250,
        ttl_seconds=900,
    )
    with ThreadPoolExecutor(max_workers=8) as pool:
        receipts = list(pool.map(lambda _: issuer.issue(base, now=NOW), range(16)))
    assert {receipt.authorization_id for receipt in receipts} == {receipts[0].authorization_id}

    conflicts = [
        ExecutionAuthorizationIssueRequest(
            **{
                **base.__dict__,
                "request_id": "conflicting-approval",
                "approved_ceiling_cents": 300 + index,
            }
        )
        for index in range(8)
    ]

    def race(request: ExecutionAuthorizationIssueRequest) -> str:
        try:
            return issuer.issue(request, now=NOW).authorization_id
        except ExecutionAuthorizationIssueConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(race, conflicts))
    assert outcomes.count("conflict") == 7
    assert len({value for value in outcomes if value != "conflict"}) == 1


def test_idempotency_is_operator_scoped(tmp_path: Path) -> None:
    record = _asset(tmp_path / "assets")
    client = _client(tmp_path)
    first = _post(client, record.asset.asset_id, _body(record), user="alice")
    second = _post(client, record.asset.asset_id, _body(record), user="bob")
    assert first.status_code == second.status_code == 201
    assert first.json()["operator_id"] == "alice"
    assert second.json()["operator_id"] == "bob"
    assert first.json()["authorization_id"] != second.json()["authorization_id"]


def test_issuer_rolls_back_failure_and_rejects_corrupted_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = str(tmp_path / "rollback.duckdb")
    issuer = ExecutionAuthorizationIssuer(db_path=db_path, signing_key=KEY)
    request = ExecutionAuthorizationIssueRequest(
        request_id="rollback-approval",
        operator_id="operator",
        asset_id="asset-1",
        revision_id="rev-1",
        provider="krea",
        route_policy="balanced",
        approved_ceiling_cents=250,
        ttl_seconds=900,
    )
    original = authorization_issuer.issue_execution_authorization

    def fail_issue(**_kwargs: object):  # type: ignore[no-untyped-def]
        raise RuntimeError("injected issuance failure")

    monkeypatch.setattr(authorization_issuer, "issue_execution_authorization", fail_issue)
    with pytest.raises(RuntimeError, match="injected issuance failure"):
        issuer.issue(request, now=NOW)
    monkeypatch.setattr(authorization_issuer, "issue_execution_authorization", original)
    receipt = issuer.issue(request, now=NOW)

    with connect_write(db_path, purpose="test-corrupt-multimedia-authorization") as con:
        con.execute(
            "UPDATE multimedia_execution_authorization_issues "
            "SET receipt_json = 'not-json' WHERE operator_id = ? AND request_id = ?",
            [receipt.operator_id, receipt.request_id],
        )
    with pytest.raises(RuntimeError, match="stored multimedia authorization is malformed"):
        issuer.issue(request, now=NOW)


def test_requires_auth_current_ready_revision_and_matching_route(tmp_path: Path) -> None:
    ready = _asset(tmp_path / "assets")
    planned = _asset(tmp_path / "assets", approved=False)
    client = _client(tmp_path)
    route = f"/multimedia/assets/{ready.asset.asset_id}/execution-authorizations"
    assert client.post(route, json=_body(ready)).status_code == 401
    assert _post(client, "missing", _body(ready)).status_code == 404
    assert _post(client, ready.asset.asset_id, _body(ready, revision_id="stale")).status_code == 409
    assert _post(client, planned.asset.asset_id, _body(planned)).status_code == 409
    assert (
        _post(client, ready.asset.asset_id, _body(ready, route_policy="cheapest")).status_code
        == 409
    )

    cheapest = _asset(tmp_path / "assets", route_policy="cheapest")
    assert _post(client, cheapest.asset.asset_id, _body(cheapest)).status_code == 409


@pytest.mark.parametrize("value", ["250", 250.0, True, 0, 2**100])
def test_ceiling_is_strict_positive_bigint(tmp_path: Path, value: object) -> None:
    record = _asset(tmp_path / "assets")
    response = _post(
        _client(tmp_path),
        record.asset.asset_id,
        _body(record, approved_ceiling_cents=value),
    )
    assert response.status_code == 422


@pytest.mark.parametrize("value", ["900", 900.0, True, 59, 3601])
def test_ttl_is_strict_and_bounded(tmp_path: Path, value: object) -> None:
    record = _asset(tmp_path / "assets")
    response = _post(
        _client(tmp_path),
        record.asset.asset_id,
        _body(record, ttl_seconds=value),
    )
    assert response.status_code == 422


def test_request_rejects_blank_ids_and_client_controlled_secret_fields(tmp_path: Path) -> None:
    record = _asset(tmp_path / "assets")
    client = _client(tmp_path)
    assert _post(client, record.asset.asset_id, _body(record, request_id="   ")).status_code == 422
    assert (
        _post(client, record.asset.asset_id, _body(record, signing_key="client-key")).status_code
        == 422
    )


def test_new_surface_has_no_dispatch_network_or_client_secret_authority() -> None:
    root = Path(__file__).parents[1]
    paths = (
        root / "substrate" / "multimedia" / "execution_authorization_issuer.py",
        root / "interfaces" / "research" / "api" / "multimedia_execution_routes.py",
    )
    imported: set[str] = set()
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
    assert imported.isdisjoint({"httpx", "requests", "urllib", "socket", "subprocess", "krea"})
