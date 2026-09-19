from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api.engagement_routes import (
    bind_council_execution,
    get_account_engagement_store,
    register_engagement_routes,
    reset_engagement_stores,
)
from substrate.engagement_spine import (
    HighlightSelection,
    attach_source_references,
    complete_spawn,
    spawn_from_highlight,
)
from substrate.engagement_spine.collective_council import (
    CouncilCallResult,
    get_council_plan,
)
from substrate.midnight_oil.budget_ledger import BudgetLedger
from substrate.multi_user.auth import UserClaims


def _authenticated_client():
    reset_engagement_stores()
    app = FastAPI()

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        claims = UserClaims(
            user_id="alice",
            email=None,
            scopes=frozenset({"private_research"}),
            issued_at="2026-07-15T00:00:00Z",
        )
        request.state.user_claims = claims
        request.state.user_id = claims.user_id
        request.state.scopes = claims.scopes
        request.state.auth_method = "test_authenticated"
        return await call_next(request)

    register_engagement_routes(app, unauthenticated_local=False)
    return TestClient(app), get_account_engagement_store("alice"), app


def test_http_preflight_approval_and_unconfigured_run_is_zero_dispatch() -> None:
    client, store, _app = _authenticated_client()
    spawn = spawn_from_highlight(
        HighlightSelection(asset_id="paper", selection_text="Reviewed evidence"),
        store=store,
    )
    attach_source_references(spawn.spawn_id, ["arxiv:1706.03762"], store=store)
    complete_spawn(spawn.spawn_id, store=store, output_text="Reviewed finding")

    response = client.post(
        "/engagement/council/preflight",
        json={
            "collective_id": "reviewed-collective",
            "shared_prompt": "Assess the reviewed finding.",
            "members": [
                {
                    "spawn_id": spawn.spawn_id,
                    "role": "critic",
                    "model_id": "test/member",
                    "projected_max_cents": 40,
                }
            ],
            "synthesizer_model_id": "test/synth",
            "synthesizer_projected_max_cents": 60,
            "approved_ceiling_cents": 100,
        },
    )
    assert response.status_code == 200, response.text
    preflight = response.json()
    assert preflight["state"] == "preflight"

    approval = client.post(
        f"/engagement/council/{preflight['plan_id']}/approve",
        json={
            "expected_input_sha256": preflight["input_sha256"],
            "approved_ceiling_cents": 100,
        },
    )
    assert approval.status_code == 200, approval.text
    assert approval.json()["state"] == "approved"

    run = client.post(
        f"/engagement/council/{preflight['plan_id']}/run", json={"max_workers": 1}
    )
    assert run.status_code == 503
    assert store.get_document(preflight["plan_id"])["state"] == "approved"


def test_council_status_is_authenticated_no_store_and_fail_closed() -> None:
    client, _store, app = _authenticated_client()
    response = client.get("/engagement/council/status")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "view_format": "html",
        "product_panel": "collective_council_status",
        "substrate_available": True,
        "executor_installed": False,
        "ledger_installed": False,
        "live_ready": False,
        "offline_convergence_available": True,
        "operator_gated": True,
        "notes": [
            "Paid council execution is unavailable until an operator installs both the durable budget ledger and executor."
        ],
    }
    app.state.engagement_council_executor = object()
    partial = client.get("/engagement/council/status").json()
    assert partial["executor_installed"] is True
    assert partial["ledger_installed"] is False
    assert partial["live_ready"] is False


def test_council_status_rejects_missing_authentication() -> None:
    reset_engagement_stores()
    app = FastAPI()
    register_engagement_routes(app, unauthenticated_local=False)
    response = TestClient(app).get("/engagement/council/status")
    assert response.status_code == 401
    local_app = FastAPI()
    register_engagement_routes(local_app, unauthenticated_local=True)
    assert TestClient(local_app).get("/engagement/council/status").status_code == 401


def test_configured_http_run_result_and_offline_convergence(tmp_path) -> None:
    client, store, app = _authenticated_client()
    spawn = spawn_from_highlight(
        HighlightSelection(asset_id="paper", selection_text="Reviewed evidence"),
        store=store,
    )
    attach_source_references(spawn.spawn_id, ["arxiv:1706.03762"], store=store)
    complete_spawn(spawn.spawn_id, store=store, output_text="Reviewed finding")
    preflight = client.post(
        "/engagement/council/preflight",
        json={
            "collective_id": "reviewed-collective",
            "shared_prompt": "Assess the reviewed finding.",
            "members": [
                {
                    "spawn_id": spawn.spawn_id,
                    "role": "critic",
                    "model_id": "test/member",
                    "projected_max_cents": 40,
                }
            ],
            "synthesizer_model_id": "test/synth",
            "synthesizer_projected_max_cents": 60,
            "approved_ceiling_cents": 100,
        },
    ).json()
    client.post(
        f"/engagement/council/{preflight['plan_id']}/approve",
        json={
            "expected_input_sha256": preflight["input_sha256"],
            "approved_ceiling_cents": 100,
        },
    )
    plan = get_council_plan(preflight["plan_id"], store=store)

    class Executor:
        def execute(self, *, role, **_kwargs):
            member = plan.members[0]
            return CouncilCallResult(
                text="Council synthesis" if role == "synthesizer" else "Member finding",
                actual_cents=30 if role == "synthesizer" else 20,
                provider_receipt_id=f"provider-{role}",
                cited_spawn_ids=(member.spawn_id,),
                cited_source_ref_ids=(member.source_ref_ids[0],),
            )

    bind_council_execution(
        app,
        ledger=BudgetLedger(str(tmp_path / "council-budget.duckdb")),
        executor=Executor(),
    )
    status = client.get("/engagement/council/status")
    assert status.status_code == 200
    assert status.json()["live_ready"] is True
    run = client.post(
        f"/engagement/council/{plan.plan_id}/run", json={"max_workers": 1}
    )
    assert run.status_code == 200, run.text
    assert run.json()["state"] == "complete"

    result = client.get(
        f"/engagement/council/results/{run.json()['result_id']}"
    )
    assert result.status_code == 200, result.text
    assert len(result.json()["result_sha256"]) == 64
    convergence = client.post(
        f"/engagement/council/{plan.plan_id}/converge",
        json={
            "result_id": run.json()["result_id"],
            "expected_result_sha256": result.json()["result_sha256"],
            "mode": "offline_collective",
            "promotion_note_ids": [],
        },
    )
    assert convergence.status_code == 200, convergence.text
    assert convergence.json()["state"] == "complete"
    assert convergence.json()["merge_output"]["source_mutated"] is False


def test_council_rejects_ownerless_local_compatibility() -> None:
    reset_engagement_stores()
    app = FastAPI()
    register_engagement_routes(app, unauthenticated_local=True)
    response = TestClient(app).post(
        "/engagement/council/preflight",
        json={
            "collective_id": "x",
            "shared_prompt": "question",
            "members": [
                {
                    "spawn_id": "foreign",
                    "role": "critic",
                    "model_id": "model",
                    "projected_max_cents": 1,
                }
            ],
            "synthesizer_model_id": "synth",
            "synthesizer_projected_max_cents": 1,
            "approved_ceiling_cents": 2,
        },
    )
    assert response.status_code == 401
