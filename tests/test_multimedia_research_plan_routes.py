from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api.multimedia_research_plan_routes import (
    ResearchPlanRouteRuntime,
    get_multimedia_research_plan_runtime,
    multimedia_research_plan_router,
)
from substrate.multimedia.research_intent import ResearchIntentLedger
from substrate.multimedia.research_plan import (
    InvestigationActivationQuote,
    ResearchPlanLedger,
    ResearchPlanStorageError,
)
from substrate.research_spend import ResearchSpendLedger, RunBinding
from substrate.research_spend.ledger import MAX_AUTHORITY_CENTS
from tests.test_multimedia_research_intent import _create


def _client(tmp_path) -> TestClient:
    intents = ResearchIntentLedger(tmp_path)
    _create(intents)
    app = FastAPI()

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        request.state.auth_method = "antiek_session_cookie"
        request.state.user_id = request.headers.get("x-owner", "owner-1")
        return await call_next(request)

    app.include_router(multimedia_research_plan_router, prefix="/multimedia")
    def quote(prepared, policy):
        def canonical(value):
            return json.dumps(
                value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()

        prepared_digest = hashlib.sha256(canonical(asdict(prepared))).hexdigest()
        workload_digest = hashlib.sha256(canonical({
            "investigation_id": prepared.investigation_id,
            "prepared_integrity_digest": prepared_digest,
            "total_node_count": prepared.total_node_count,
            "leaf_question_count": prepared.leaf_question_count,
        })).hexdigest()
        now = datetime.now(UTC)
        return InvestigationActivationQuote(
            schema_version=1, route_policy=policy, resolved_tier="standard",
            provider="server-provider", model="server-model", dispatch_config_digest="d" * 64,
            pricing_source="server-pricebook", pricing_digest="e" * 64,
            workload_digest=workload_digest, quoted_ceiling_cents=250, quote_id="quote-123",
            issued_at=now.isoformat().replace("+00:00", "Z"),
            expires_at=(now + timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
        )

    runtime = ResearchPlanRouteRuntime(
        plans=ResearchPlanLedger(tmp_path),
        intents=intents,
        owner_digest_resolver=lambda owner: ("a" if owner == "owner-1" else "b") * 64,
        activation_quote_resolver=quote,
        spend_ledger=ResearchSpendLedger(tmp_path / "research-spend.sqlite3"),
    )
    app.dependency_overrides[get_multimedia_research_plan_runtime] = lambda: runtime
    return TestClient(app)


def test_handoff_get_approve_contract_is_private_and_replay_stable(tmp_path) -> None:
    client = _client(tmp_path)
    runtime = client.app.dependency_overrides[get_multimedia_research_plan_runtime]()
    intent_id = runtime.intents.get(
        owner_identity_digest="a" * 64,
        intent_id=_create(runtime.intents, key="other-key-1234567")[0].intent_id,
    ).intent_id
    body = {"idempotency_key": "handoff-123456789"}
    created = client.post(f"/multimedia/research-intents/{intent_id}/plan", json=body)
    replay = client.post(f"/multimedia/research-intents/{intent_id}/plan", json=body)
    assert created.status_code == 201 and replay.status_code == 200
    assert created.json() == replay.json()
    plan_id = created.json()["plan_id"]
    read = client.get(f"/multimedia/research-plans/{plan_id}")
    approved = client.post(
        f"/multimedia/research-plans/{plan_id}/approve",
        json={"expected_plan_version": 1},
    )
    approval_replay = client.post(
        f"/multimedia/research-plans/{plan_id}/approve",
        json={"expected_plan_version": 1},
    )
    assert read.json()["state"] == "draft"
    assert approved.status_code == 200 and approved.json() == approval_replay.json()
    assert approved.json()["state"] == "approved"
    assert approved.json()["research_launched"] is False
    assert all(row.headers["cache-control"] == "private, no-store" for row in (
        created, replay, read, approved, approval_replay,
    ))


def test_foreign_absent_stale_and_validation_responses_are_private(tmp_path) -> None:
    client = _client(tmp_path)
    runtime = client.app.dependency_overrides[get_multimedia_research_plan_runtime]()
    intent, _ = _create(runtime.intents, key="other-key-1234567")
    created = client.post(
        f"/multimedia/research-intents/{intent.intent_id}/plan",
        json={"idempotency_key": "handoff-123456789"},
    )
    plan_id = created.json()["plan_id"]
    responses = [
        client.get(f"/multimedia/research-plans/{plan_id}", headers={"x-owner": "owner-2"}),
        client.get("/multimedia/research-plans/mrp_missing"),
        client.post(f"/multimedia/research-plans/{plan_id}/approve", json={"expected_plan_version": 2}),
        client.post(f"/multimedia/research-plans/{plan_id}/approve", json={"approver": "forged"}),
    ]
    assert [row.status_code for row in responses] == [404, 404, 409, 422]
    assert responses[0].json() == responses[1].json()
    assert all(row.headers["cache-control"] == "private, no-store" for row in responses)


def test_routes_do_not_invoke_execution_or_legacy_cascade_collaborators(tmp_path) -> None:
    client = _client(tmp_path)
    runtime = client.app.dependency_overrides[get_multimedia_research_plan_runtime]()
    intent, _ = _create(runtime.intents, key="other-key-1234567")
    forbidden = (
        "interfaces.research.api.cascade_routes.build_plan",
        "interfaces.research.api.cascade_routes.persist_tree",
        "interfaces.research.api.cascade_routes.approve_plan",
        "interfaces.research.api.cascade_routes.ResearchProviderGateway",
        "interfaces.research.api.cascade_routes.CascadeSession",
    )
    with (
        patch(forbidden[0]) as build,
        patch(forbidden[1]) as persist,
        patch(forbidden[2]) as legacy_approve,
        patch(forbidden[3]) as provider,
        patch(forbidden[4]) as launch,
    ):
        created = client.post(
            f"/multimedia/research-intents/{intent.intent_id}/plan",
            json={"idempotency_key": "handoff-123456789"},
        )
        client.get(f"/multimedia/research-plans/{created.json()['plan_id']}")
        client.post(
            f"/multimedia/research-plans/{created.json()['plan_id']}/approve",
            json={"expected_plan_version": 1},
        )
    assert all(spy.call_count == 0 for spy in (build, persist, legacy_approve, provider, launch))


def test_unexpected_authority_failure_is_private(tmp_path) -> None:
    client = _client(tmp_path)
    runtime = client.app.dependency_overrides[get_multimedia_research_plan_runtime]()
    with patch.object(
        runtime.plans, "get", side_effect=ResearchPlanStorageError("ledger unavailable")
    ):
        response = client.get("/multimedia/research-plans/mrp_" + "a" * 48)
    assert response.status_code == 500
    assert response.json() == {"detail": "research plan authority is unavailable"}
    assert response.headers["cache-control"] == "private, no-store"


def test_edit_route_is_strict_private_and_reopens_approval(tmp_path) -> None:
    client = _client(tmp_path)
    runtime = client.app.dependency_overrides[get_multimedia_research_plan_runtime]()
    intent, _ = _create(runtime.intents, key="other-key-1234567")
    created = client.post(
        f"/multimedia/research-intents/{intent.intent_id}/plan",
        json={"idempotency_key": "handoff-123456789"},
    )
    plan_id = created.json()["plan_id"]
    root_id = created.json()["tree"]["root"]["node_id"]
    client.post(
        f"/multimedia/research-plans/{plan_id}/approve",
        json={"expected_plan_version": 1},
    )
    body = {
        "idempotency_key": "mutation-12345678", "expected_plan_version": 1,
        "operations": [{"type": "add_child", "parent_node_id": root_id,
                        "position": 0, "question": "A child question?"}],
    }
    edited = client.post(f"/multimedia/research-plans/{plan_id}/edits", json=body)
    replay = client.post(f"/multimedia/research-plans/{plan_id}/edits", json=body)
    malformed = client.post(
        f"/multimedia/research-plans/{plan_id}/edits",
        json={**body, "operations": [{**body["operations"][0], "unknown": True}]},
    )
    assert edited.status_code == 200 and edited.json() == replay.json()
    assert edited.json()["plan_version"] == 2 and edited.json()["state"] == "draft"
    assert "approved_by_owner_digest" not in edited.json()
    assert malformed.status_code == 422
    assert all(response.headers["cache-control"] == "private, no-store"
               for response in (edited, replay, malformed))


def test_prepared_investigation_routes_are_strict_private_and_immutable(tmp_path) -> None:
    client = _client(tmp_path)
    runtime = client.app.dependency_overrides[get_multimedia_research_plan_runtime]()
    intent, _ = _create(runtime.intents, key="other-key-1234567")
    plan = client.post(
        f"/multimedia/research-intents/{intent.intent_id}/plan",
        json={"idempotency_key": "handoff-123456789"},
    ).json()
    client.post(
        f"/multimedia/research-plans/{plan['plan_id']}/approve",
        json={"expected_plan_version": 1},
    )
    body = {"idempotency_key": "prepare-123456789", "expected_plan_version": 1}
    created = client.post(
        f"/multimedia/research-plans/{plan['plan_id']}/investigation", json=body
    )
    replay = client.post(
        f"/multimedia/research-plans/{plan['plan_id']}/investigation", json=body
    )
    read = client.get(f"/multimedia/investigations/{created.json()['investigation_id']}")
    foreign = client.get(
        f"/multimedia/investigations/{created.json()['investigation_id']}",
        headers={"x-owner": "owner-2"},
    )
    absent = client.get("/multimedia/investigations/mpi_missing")
    malformed = client.post(
        f"/multimedia/research-plans/{plan['plan_id']}/investigation",
        json={**body, "owner_identity_digest": "a" * 64},
    )
    padded_key = client.post(
        f"/multimedia/research-plans/{plan['plan_id']}/investigation",
        json={**body, "idempotency_key": " prepare-123456789"},
    )
    assert created.status_code == 201 and replay.status_code == read.status_code == 200
    assert created.json() == replay.json() == read.json()
    assert "idempotency_key" not in created.json() and "owner_identity_digest" not in created.json()
    assert created.json()["background_work_authorized"] is False
    assert foreign.status_code == absent.status_code == 404 and foreign.json() == absent.json()
    assert malformed.status_code == 422
    assert padded_key.status_code == 422
    assert all(response.headers["cache-control"] == "private, no-store"
               for response in (created, replay, read, foreign, absent, malformed, padded_key))


def test_activation_authorization_routes_are_private_strict_and_owner_scoped(tmp_path) -> None:
    client = _client(tmp_path)
    runtime = client.app.dependency_overrides[get_multimedia_research_plan_runtime]()
    intent, _ = _create(runtime.intents, key="other-key-1234567")
    plan = client.post(
        f"/multimedia/research-intents/{intent.intent_id}/plan",
        json={"idempotency_key": "handoff-123456789"},
    ).json()
    client.post(
        f"/multimedia/research-plans/{plan['plan_id']}/approve",
        json={"expected_plan_version": 1},
    )
    prepared = client.post(
        f"/multimedia/research-plans/{plan['plan_id']}/investigation",
        json={"idempotency_key": "prepare-123456789", "expected_plan_version": 1},
    ).json()
    path = f"/multimedia/investigations/{prepared['investigation_id']}"
    body = {
        "idempotency_key": "activate-12345678", "route_policy": "balanced",
        "approved_ceiling_cents": 300, "ttl_seconds": 3600,
    }
    created = client.post(path + "/activation-authorizations", json=body)
    unavailable_resolver = Mock(side_effect=RuntimeError("quote service unavailable"))
    client.app.dependency_overrides[get_multimedia_research_plan_runtime] = lambda: (
        ResearchPlanRouteRuntime(
            plans=runtime.plans, intents=runtime.intents,
            owner_digest_resolver=runtime.owner_digest_resolver,
            activation_quote_resolver=unavailable_resolver,
        )
    )
    replay = client.post(path + "/activation-authorizations", json=body)
    read = client.get(path + "/activation-authorization")
    foreign = client.get(path + "/activation-authorization", headers={"x-owner": "owner-2"})
    malformed = client.post(
        path + "/activation-authorizations", json={**body, "provider": "forged"}
    )
    assert created.status_code == 201 and replay.status_code == read.status_code == 200
    unavailable_resolver.assert_not_called()
    assert created.json() == replay.json() == read.json()
    assert foreign.status_code == 404 and malformed.status_code == 422
    assert "owner_identity_digest" not in created.json() and "idempotency_key" not in created.json()
    assert created.json()["execution_started"] is False
    assert created.json()["background_work_authorized"] is False
    assert all(response.headers["cache-control"] == "private, no-store"
               for response in (created, replay, read, foreign, malformed))


def test_activation_consumption_bootstraps_exact_pristine_run_and_replays(tmp_path) -> None:
    client = _client(tmp_path)
    runtime = client.app.dependency_overrides[get_multimedia_research_plan_runtime]()
    intent, _ = _create(runtime.intents, key="consume-intent-123")
    plan = client.post(
        f"/multimedia/research-intents/{intent.intent_id}/plan",
        json={"idempotency_key": "handoff-consume-123"},
    ).json()
    client.post(f"/multimedia/research-plans/{plan['plan_id']}/approve",
                json={"expected_plan_version": 1})
    prepared = client.post(
        f"/multimedia/research-plans/{plan['plan_id']}/investigation",
        json={"idempotency_key": "prepare-consume-123", "expected_plan_version": 1},
    ).json()
    path = f"/multimedia/investigations/{prepared['investigation_id']}"
    authorization = client.post(path + "/activation-authorizations", json={
        "idempotency_key": "activate-consume-12", "route_policy": "balanced",
        "approved_ceiling_cents": 300, "ttl_seconds": 3600,
    }).json()
    body = {"authorization_id": authorization["authorization_id"],
            "idempotency_key": "consume-request-123"}
    created = client.post(path + "/activation-consumptions", json=body)
    replay = client.post(path + "/activation-consumptions", json=body)
    read = client.get(path + "/launch-reservation")
    assert created.status_code == 201 and replay.status_code == read.status_code == 200
    assert created.json() == replay.json() == read.json()
    receipt = created.json()
    assert receipt["ready"] is True and receipt["reserved_cents"] == 300
    assert "idempotency_key" not in receipt and "owner_identity_digest" not in receipt
    balance = runtime.spend_ledger.balance(receipt["spend_run_id"])
    assert balance.ceiling_cents == 300
    assert balance.authorized_spent_cents == balance.held_cents == 0
    foreign = client.get(path + "/launch-reservation", headers={"x-owner": "owner-2"})
    assert foreign.status_code == 404


def _launch_api_fixture(client: TestClient, approved_cents: int = 300):
    runtime = client.app.dependency_overrides[get_multimedia_research_plan_runtime]()
    intent, _ = _create(runtime.intents, key="launch-fixture-intent")
    plan = client.post(
        f"/multimedia/research-intents/{intent.intent_id}/plan",
        json={"idempotency_key": "launch-fixture-handoff"},
    ).json()
    client.post(
        f"/multimedia/research-plans/{plan['plan_id']}/approve",
        json={"expected_plan_version": 1},
    )
    prepared = client.post(
        f"/multimedia/research-plans/{plan['plan_id']}/investigation",
        json={"idempotency_key": "launch-fixture-prepare", "expected_plan_version": 1},
    ).json()
    path = f"/multimedia/investigations/{prepared['investigation_id']}"
    authorization = client.post(path + "/activation-authorizations", json={
        "idempotency_key": "launch-fixture-authorize", "route_policy": "balanced",
        "approved_ceiling_cents": approved_cents, "ttl_seconds": 3600,
    }).json()
    body = {
        "authorization_id": authorization["authorization_id"],
        "idempotency_key": "launch-fixture-consume",
    }
    return runtime, path, body


def test_launch_api_enforces_supported_ceiling_boundary_and_above(tmp_path) -> None:
    boundary_root = tmp_path / "boundary"
    boundary_root.mkdir()
    boundary_client = _client(boundary_root)
    _runtime, path, body = _launch_api_fixture(boundary_client, MAX_AUTHORITY_CENTS)
    accepted = boundary_client.post(path + "/activation-consumptions", json=body)
    assert accepted.status_code == 201
    assert accepted.json()["reserved_cents"] == MAX_AUTHORITY_CENTS

    above_root = tmp_path / "above"
    above_root.mkdir()
    above_client = _client(above_root)
    runtime, path, body = _launch_api_fixture(above_client, MAX_AUTHORITY_CENTS + 1)
    rejected = above_client.post(path + "/activation-consumptions", json=body)
    assert rejected.status_code == 409
    assert rejected.json() == {"detail": "activation consumption conflicts"}
    with sqlite3.connect(runtime.plans.path) as connection:
        assert connection.execute(
            "SELECT count(*) FROM multimedia_investigation_launch_reservations"
        ).fetchone()[0] == 0


def test_committed_launch_recovers_by_exact_post_while_get_never_creates(tmp_path) -> None:
    client = _client(tmp_path)
    runtime, path, body = _launch_api_fixture(client)
    unavailable = ResearchPlanRouteRuntime(
        plans=runtime.plans, intents=runtime.intents,
        owner_digest_resolver=runtime.owner_digest_resolver,
        activation_quote_resolver=runtime.activation_quote_resolver, spend_ledger=None,
    )
    client.app.dependency_overrides[get_multimedia_research_plan_runtime] = lambda: unavailable
    failed = client.post(path + "/activation-consumptions", json=body)
    assert failed.status_code == 503
    reservation = runtime.plans.get_investigation_launch_reservation(
        owner_identity_digest="a" * 64, investigation_id=path.rsplit("/", 1)[-1],
    )

    fresh_path = tmp_path / "recovery-spend.sqlite3"
    fresh_ledger = ResearchSpendLedger(fresh_path)
    recovery_runtime = ResearchPlanRouteRuntime(
        plans=runtime.plans, intents=runtime.intents,
        owner_digest_resolver=runtime.owner_digest_resolver,
        activation_quote_resolver=Mock(side_effect=AssertionError("replay resolved quote")),
        spend_ledger=fresh_ledger,
    )
    client.app.dependency_overrides[get_multimedia_research_plan_runtime] = lambda: recovery_runtime
    verify_only = client.get(path + "/launch-reservation")
    assert verify_only.status_code == 503
    assert not fresh_path.exists()
    recovered = client.post(path + "/activation-consumptions", json=body)
    assert recovered.status_code == 200 and recovered.json()["ready"] is True
    assert recovered.json()["launch_reservation_id"] == reservation.launch_reservation_id
    recovery_runtime.activation_quote_resolver.assert_not_called()
    with sqlite3.connect(fresh_path) as connection:
        assert connection.execute("SELECT count(*) FROM research_spend_holds").fetchone()[0] == 0


def test_conflicting_existing_spend_run_is_private_409(tmp_path) -> None:
    client = _client(tmp_path)
    runtime, path, body = _launch_api_fixture(client)
    no_spend = ResearchPlanRouteRuntime(
        plans=runtime.plans, intents=runtime.intents,
        owner_digest_resolver=runtime.owner_digest_resolver,
        activation_quote_resolver=runtime.activation_quote_resolver, spend_ledger=None,
    )
    client.app.dependency_overrides[get_multimedia_research_plan_runtime] = lambda: no_spend
    assert client.post(path + "/activation-consumptions", json=body).status_code == 503
    reservation = runtime.plans.get_investigation_launch_reservation(
        owner_identity_digest="a" * 64, investigation_id=path.rsplit("/", 1)[-1],
    )
    runtime.spend_ledger.ensure_schema()
    binding = RunBinding(
        run_id=reservation.spend_run_id, owner_id="a" * 64,
        session_id=reservation.session_id,
        plan_digest=reservation.launch_manifest_digest,
        approval_revision=reservation.source_plan_version,
    )
    runtime.spend_ledger.create_or_reopen_run(
        "conflicting-bootstrap-command", binding, reservation.reserved_cents - 1,
    )
    client.app.dependency_overrides[get_multimedia_research_plan_runtime] = lambda: runtime
    conflict = client.post(path + "/activation-consumptions", json=body)
    assert conflict.status_code == 409
    assert conflict.json() == {"detail": "launch reservation integrity conflicts"}


def test_activation_absence_does_not_invoke_quote_resolver(tmp_path) -> None:
    client = _client(tmp_path)
    runtime = client.app.dependency_overrides[get_multimedia_research_plan_runtime]()
    resolver = Mock()
    client.app.dependency_overrides[get_multimedia_research_plan_runtime] = lambda: (
        ResearchPlanRouteRuntime(
            plans=runtime.plans, intents=runtime.intents,
            owner_digest_resolver=runtime.owner_digest_resolver,
            activation_quote_resolver=resolver,
        )
    )
    response = client.post(
        "/multimedia/investigations/mpi_" + "a" * 48 + "/activation-authorizations",
        json={"idempotency_key": "activate-12345678", "route_policy": "balanced",
              "approved_ceiling_cents": 300, "ttl_seconds": 3600},
    )
    assert response.status_code == 404
    resolver.assert_not_called()
    assert response.headers["cache-control"] == "private, no-store"


def test_activation_non_quote_resolver_result_is_private_unavailable(tmp_path) -> None:
    client = _client(tmp_path)
    runtime = client.app.dependency_overrides[get_multimedia_research_plan_runtime]()
    intent, _ = _create(runtime.intents, key="other-key-1234567")
    plan = client.post(
        f"/multimedia/research-intents/{intent.intent_id}/plan",
        json={"idempotency_key": "handoff-123456789"},
    ).json()
    client.post(
        f"/multimedia/research-plans/{plan['plan_id']}/approve",
        json={"expected_plan_version": 1},
    )
    prepared = client.post(
        f"/multimedia/research-plans/{plan['plan_id']}/investigation",
        json={"idempotency_key": "prepare-123456789", "expected_plan_version": 1},
    ).json()
    client.app.dependency_overrides[get_multimedia_research_plan_runtime] = lambda: (
        ResearchPlanRouteRuntime(
            plans=runtime.plans, intents=runtime.intents,
            owner_digest_resolver=runtime.owner_digest_resolver,
            activation_quote_resolver=lambda *_: object(),
        )
    )
    response = client.post(
        f"/multimedia/investigations/{prepared['investigation_id']}"
        "/activation-authorizations",
        json={"idempotency_key": "activate-12345678", "route_policy": "balanced",
              "approved_ceiling_cents": 300, "ttl_seconds": 3600},
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "activation quote authority is unavailable"}
    assert response.headers["cache-control"] == "private, no-store"
