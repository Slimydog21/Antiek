from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api.multimedia_research_plan_routes import (
    ResearchPlanRouteRuntime,
    get_multimedia_research_plan_runtime,
    multimedia_research_plan_router,
)
from substrate.multimedia.research_intent import ResearchIntentLedger
from substrate.multimedia.research_plan import ResearchPlanLedger, ResearchPlanStorageError
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
    runtime = ResearchPlanRouteRuntime(
        plans=ResearchPlanLedger(tmp_path),
        intents=intents,
        owner_digest_resolver=lambda owner: ("a" if owner == "owner-1" else "b") * 64,
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
