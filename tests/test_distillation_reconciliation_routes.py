from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api.distillation_reconciliation_routes import (
    DistillationProviderReconciliationAuthority,
    DistillationReconciliationRuntime,
    distillation_reconciliation_router,
    get_distillation_reconciliation_runtime,
)
from runtime.research_runner.protocol import (
    BillingUnit,
    BoundedUsage,
    CostProjection,
    CostProjectionRequest,
    ProjectionDisposition,
    ProjectionRate,
)
from runtime.research_runner.provider_gateway import (
    PaidRouteAuthorityIdentity,
    ProviderCapabilities,
    ProviderReconciliation,
    ReconciliationStatus,
    canonical_digest,
)
from substrate.distillation_dispatch import DistillationDispatchJournal
from substrate.research_spend import (
    FallbackChainManifest,
    FallbackRouteManifest,
    PaidHoldIntent,
    ResearchSpendLedger,
    RunBinding,
)


def _projection_request() -> CostProjectionRequest:
    return CostProjectionRequest(
        seam_id="wrestling.distillation.synthesizer",
        provider="provider-1",
        model="model-1",
        operation="synthesize",
        bounded_usage=(BoundedUsage(BillingUnit.CALL, 1),),
    )


def _project(request: CostProjectionRequest) -> CostProjection:
    return CostProjection(
        seam_id=request.seam_id,
        provider=request.provider,
        model=request.model,
        operation=request.operation,
        bounded_usage=request.bounded_usage,
        rates=(ProjectionRate(BillingUnit.CALL, Decimal("0.80")),),
        rate_snapshot="rates-v1",
        currency="USD",
        maximum_cost_usd=Decimal("0.80"),
        reservation_cents=80,
        disposition=ProjectionDisposition.HOLD_ELIGIBLE,
    )


def _route_authorizer(request, adapter) -> PaidRouteAuthorityIdentity:
    return PaidRouteAuthorityIdentity(
        provider_kind="test",
        provider_id=request.provider,
        endpoint=adapter.endpoint,
        model=request.model,
        seam_id=request.seam_id,
        operation=request.operation,
        rate_snapshot="rates-v1",
        currency="USD",
        rates=(ProjectionRate(BillingUnit.CALL, Decimal("0.80")),),
    )


class FakeReconciliationAdapter:
    provider = "provider-1"
    model = "model-1"
    endpoint = "https://provider-1.example/v1"
    capabilities = ProviderCapabilities(True, True, True, frozenset({BillingUnit.CALL}))

    def __init__(self, status: ReconciliationStatus, actual_cents: int | None = None):
        self.status = status
        self.actual_cents = actual_cents
        self.reconcile_calls: list[tuple[str, str]] = []
        self.send_calls = 0

    def send_once(self, *args, **kwargs):
        self.send_calls += 1
        raise AssertionError("reconciliation action must never send")

    def reconcile(self, *, provider_idempotency_key: str, authorized_endpoint: str):
        self.reconcile_calls.append((provider_idempotency_key, authorized_endpoint))
        return ProviderReconciliation(
            self.status,
            {"provider_lookup": self.status.value},
            self.actual_cents,
        )


def _seed(tmp_path, *, owner_id: str = "owner-1") -> DistillationReconciliationRuntime:
    command_db = str(tmp_path / "graph.duckdb")
    spend_db = tmp_path / "spend.sqlite3"
    binding = RunBinding("run-1", owner_id, "session-1", "plan-1", 1)
    ledger = ResearchSpendLedger(spend_db)
    ledger.ensure_schema()
    ledger.create_or_reopen_run("create-run", binding, 200)
    projection_request = _projection_request()
    projection = _project(projection_request)
    authority = _route_authorizer(
        projection_request,
        FakeReconciliationAdapter(ReconciliationStatus.UNKNOWN),
    )
    intent = PaidHoldIntent(
        reservation_key="reservation-1",
        seam_id="wrestling.distillation.synthesizer",
        provider="provider-1",
        model="model-1",
        operation="synthesize",
        operation_digest="operation-digest",
        projection_digest=canonical_digest(projection),
        rate_snapshot="rates-v1",
        provider_idempotency_key="provider-key-1",
        route_authority_digest=canonical_digest(authority),
    )
    route = FallbackRouteManifest(
        fallback_index=0,
        seam_id=intent.seam_id,
        provider=intent.provider,
        model=intent.model,
        operation=intent.operation,
        operation_digest=intent.operation_digest,
        projection_digest=intent.projection_digest,
        rate_snapshot=intent.rate_snapshot,
        projected_max_cents=80,
        reservation_key=intent.reservation_key,
        provider_idempotency_key=intent.provider_idempotency_key,
        route_authority_digest=intent.route_authority_digest,
    )
    manifest = FallbackChainManifest(
        chain_id="chain-1",
        logical_operation_id="evt-request",
        operation_digest=intent.operation_digest,
        routes=(route,),
    )
    ledger.register_fallback_manifest("register-chain", binding, manifest)
    ledger.issue_fallback_approval(
        "approve-chain",
        binding,
        manifest.chain_id,
        expected_manifest_sha256=canonical_digest(manifest),
        expected_ceiling_cents=200,
    )
    hold = ledger.reserve_paid("reserve-hold", binding, intent, 80)

    journal = DistillationDispatchJournal(command_db)
    journal.reserve(
        "evt-request",
        {"schema": "test.v1", "prompt_sha256": "a" * 64},
        investigation_id="inv-1",
        document_id="doc-1",
    )
    journal.authorize_sending(
        "evt-request",
        spend_run_id=binding.run_id,
        fallback_chain_id=manifest.chain_id,
        manifest_sha256=canonical_digest(manifest),
        fallback_index=0,
        hold_id=hold.hold_id,
    )
    journal.mark_ambiguous("evt-request", hold_id=hold.hold_id)
    return DistillationReconciliationRuntime(command_db, spend_db)


def _app(runtime: DistillationReconciliationRuntime, *, owner_id: str, method: str) -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def identity(request: Request, call_next):
        request.state.user_id = owner_id
        request.state.auth_method = method
        return await call_next(request)

    app.include_router(distillation_reconciliation_router)
    app.dependency_overrides[get_distillation_reconciliation_runtime] = lambda: runtime
    return app


def test_owner_reads_redacted_executable_reserved_hold(tmp_path) -> None:
    runtime = _seed(tmp_path)
    ledger = ResearchSpendLedger(runtime.spend_db_path)
    before_events = ledger.events("run-1")
    before_command = DistillationDispatchJournal(runtime.command_db_path).load("evt-request")

    response = TestClient(_app(runtime, owner_id="owner-1", method="antiek_session_cookie")).get(
        "/research/distillation/commands/evt-request/reconciliation"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["command_state"] == "ambiguous"
    assert body["next_action"] == "release_proven_unsent"
    assert body["action_executable"] is True
    assert body["held_cents"] == 80
    assert body["holds"] == [
        {
            "fallback_index": 0,
            "hold_id": body["current_hold_id"],
            "provider": "provider-1",
            "model": "model-1",
            "state": "reserved",
            "projected_max_cents": 80,
            "actual_cents": None,
            "is_current": True,
            "evidence_requirement": "ledger_proven_unsent",
        }
    ]
    serialized = response.text
    for forbidden in (
        "provider-key-1",
        "reservation-1",
        "authority-digest",
        "projection-digest",
        "prompt_sha256",
    ):
        assert forbidden not in serialized
    assert ledger.events("run-1") == before_events
    assert (
        DistillationDispatchJournal(runtime.command_db_path).load("evt-request") == before_command
    )


def test_unauthenticated_local_mode_is_rejected(tmp_path) -> None:
    runtime = _seed(tmp_path)
    response = TestClient(_app(runtime, owner_id="owner-1", method="unauthenticated_local")).get(
        "/research/distillation/commands/evt-request/reconciliation"
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "authentication required"}


def test_foreign_owner_and_missing_command_are_indistinguishable(tmp_path) -> None:
    runtime = _seed(tmp_path)
    client = TestClient(_app(runtime, owner_id="owner-2", method="cloudflare_access_email"))
    foreign = client.get("/research/distillation/commands/evt-request/reconciliation")
    missing = client.get("/research/distillation/commands/missing/reconciliation")
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json() == {"detail": "command unavailable"}


def test_substituted_command_hold_returns_value_free_conflict(tmp_path) -> None:
    runtime = _seed(tmp_path)
    import duckdb

    with duckdb.connect(runtime.command_db_path) as connection:
        connection.execute(
            "UPDATE distillation_dispatch_commands SET hold_id='substituted' "
            "WHERE request_event_id='evt-request'"
        )
    response = TestClient(_app(runtime, owner_id="owner-1", method="bearer_token")).get(
        "/research/distillation/commands/evt-request/reconciliation"
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "reconciliation evidence conflicts"}


@pytest.mark.parametrize(
    ("target_state", "expected_action", "expected_requirement", "expected_actual"),
    [
        ("dispatch_possible", "provider_lookup_required", "authoritative_provider_lookup", None),
        ("unknown", "provider_lookup_required", "authoritative_provider_lookup", None),
        ("released", "none", "terminal_no_action", None),
        ("settled", "none", "terminal_no_action", 60),
    ],
)
def test_view_derives_guidance_from_authoritative_hold_state(
    tmp_path,
    target_state: str,
    expected_action: str,
    expected_requirement: str,
    expected_actual: int | None,
) -> None:
    runtime = _seed(tmp_path)
    ledger = ResearchSpendLedger(runtime.spend_db_path)
    command = DistillationDispatchJournal(runtime.command_db_path).load("evt-request")
    assert command.hold_id is not None
    hold_id = command.hold_id
    if target_state == "dispatch_possible":
        ledger.mark_dispatch_possible("mark-send", hold_id)
    elif target_state == "unknown":
        ledger.mark_dispatch_possible("mark-send", hold_id)
        ledger.mark_unknown("mark-unknown", hold_id, {"timeout": True})
    elif target_state == "released":
        ledger.release("release", hold_id, {"provider_not_sent": True})
    else:
        ledger.mark_dispatch_possible("mark-send", hold_id)
        ledger.settle("settle", hold_id, 60, {"provider_receipt": "receipt"})

    response = TestClient(_app(runtime, owner_id="owner-1", method="bearer_token")).get(
        "/research/distillation/commands/evt-request/reconciliation"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["next_action"] == expected_action
    assert body["action_executable"] is False
    assert body["holds"][0]["state"] == target_state
    assert body["holds"][0]["evidence_requirement"] == expected_requirement
    assert body["holds"][0]["actual_cents"] == expected_actual


def test_openapi_declares_read_only_reconciliation_contract(tmp_path) -> None:
    runtime = _seed(tmp_path)
    schema = _app(runtime, owner_id="owner-1", method="bearer_token").openapi()
    operation = schema["paths"]["/research/distillation/commands/{request_event_id}/reconciliation"]
    assert set(operation) == {"get"}
    response_schema = operation["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert response_schema["$ref"].endswith("DistillationReconciliationResponse")


def test_canonical_app_mounts_reconciliation_route() -> None:
    from interfaces.research.api.app import create_app

    def mounted_paths(routes) -> set[str]:
        paths: set[str] = set()
        for route in routes:
            path = getattr(route, "path", None)
            if isinstance(path, str):
                paths.add(path)
            original_router = getattr(route, "original_router", None)
            if original_router is not None:
                paths.update(mounted_paths(original_router.routes))
        return paths

    assert "/research/distillation/commands/{request_event_id}/reconciliation" in (
        mounted_paths(create_app().routes)
    )


def test_canonical_app_exposes_injected_provider_authority_resolver() -> None:
    from interfaces.research.api.app import create_app

    resolver = object()
    app = create_app(
        register_wrestling=False,
        register_providers=False,
        distillation_provider_authority_resolver=resolver,
    )

    assert app.state.distillation_provider_authority_resolver is resolver


@pytest.mark.parametrize("target_state", ["dispatch_possible", "unknown"])
def test_view_reports_provider_action_only_for_configured_server_resolver(
    tmp_path, target_state
) -> None:
    runtime = _seed(tmp_path)
    ledger = ResearchSpendLedger(runtime.spend_db_path)
    command = DistillationDispatchJournal(runtime.command_db_path).load("evt-request")
    assert command.hold_id is not None
    ledger.mark_dispatch_possible("mark-send", command.hold_id)
    if target_state == "unknown":
        ledger.mark_unknown("mark-unknown", command.hold_id, {"timeout": True})
    availability_calls = 0
    resolution_calls = 0

    class Resolver:
        def available_for(self, **_identity):
            nonlocal availability_calls
            availability_calls += 1
            return True

        def __call__(self, **_identity):
            nonlocal resolution_calls
            resolution_calls += 1
            raise AssertionError("the read model must not resolve provider authority")

    runtime = DistillationReconciliationRuntime(
        runtime.command_db_path,
        runtime.spend_db_path,
        Resolver(),
    )
    response = TestClient(_app(runtime, owner_id="owner-1", method="bearer_token")).get(
        "/research/distillation/commands/evt-request/reconciliation"
    )

    assert response.status_code == 200
    assert response.json()["next_action"] == "provider_lookup_required"
    assert response.json()["action_executable"] is True
    assert availability_calls == 1
    assert resolution_calls == 0


def test_view_and_action_fail_closed_when_resolver_rejects_exact_hold(tmp_path) -> None:
    runtime = _seed(tmp_path)
    ledger = ResearchSpendLedger(runtime.spend_db_path)
    command = DistillationDispatchJournal(runtime.command_db_path).load("evt-request")
    assert command.hold_id is not None
    ledger.mark_dispatch_possible("mark-send", command.hold_id)
    resolution_calls = 0

    class Resolver:
        def available_for(self, **_identity):
            return False

        def __call__(self, **_identity):
            nonlocal resolution_calls
            resolution_calls += 1
            raise AssertionError("unavailable authority must never resolve")

    runtime = DistillationReconciliationRuntime(
        runtime.command_db_path,
        runtime.spend_db_path,
        Resolver(),
    )
    client = TestClient(_app(runtime, owner_id="owner-1", method="bearer_token"))
    view = client.get("/research/distillation/commands/evt-request/reconciliation")
    action = client.post(
        "/research/distillation/commands/evt-request/reconciliation/actions/check-provider",
        json=_provider_terms(runtime, state="dispatch_possible"),
    )

    assert view.status_code == 200
    assert view.json()["action_executable"] is False
    assert action.status_code == 409
    assert action.json() == {"detail": "reconciliation action conflicts"}
    assert resolution_calls == 0
    assert ledger.balance("run-1").held_cents == 80


def _release_terms(**overrides) -> dict[str, object]:
    terms: dict[str, object] = {
        "expected_command_state": "ambiguous",
        "expected_spend_run_id": "run-1",
        "expected_fallback_chain_id": "chain-1",
        "expected_manifest_sha256": "",
        "expected_fallback_index": 0,
        "expected_hold_id": "",
        "expected_hold_state": "reserved",
    }
    terms.update(overrides)
    return terms


def _authoritative_release_terms(runtime: DistillationReconciliationRuntime) -> dict[str, object]:
    command = DistillationDispatchJournal(runtime.command_db_path).load("evt-request")
    assert command.manifest_sha256 is not None
    assert command.hold_id is not None
    return _release_terms(
        expected_manifest_sha256=command.manifest_sha256,
        expected_hold_id=command.hold_id,
    )


def _provider_terms(runtime: DistillationReconciliationRuntime, *, state: str) -> dict[str, object]:
    terms = _authoritative_release_terms(runtime)
    terms["expected_hold_state"] = state
    return terms


def _provider_runtime(
    runtime: DistillationReconciliationRuntime,
    adapter: FakeReconciliationAdapter,
    resolver_calls: list[dict[str, object]],
) -> DistillationReconciliationRuntime:
    history = ResearchSpendLedger(runtime.spend_db_path).fallback_history("owner-1")
    approval_id = history.items[0].approval_id
    assert approval_id is not None

    class Resolver:
        def available_for(self, **_identity):
            return True

        def __call__(self, **identity):
            resolver_calls.append(identity)
            return DistillationProviderReconciliationAuthority(
                adapter=adapter,
                projection_request=_projection_request(),
                approval_id=approval_id,
                projector=_project,
                route_authorizer=_route_authorizer,
            )

    return DistillationReconciliationRuntime(
        runtime.command_db_path,
        runtime.spend_db_path,
        Resolver(),
    )


def test_owner_releases_exact_reserved_hold_and_replay_is_idempotent(tmp_path) -> None:
    runtime = _seed(tmp_path)
    client = TestClient(_app(runtime, owner_id="owner-1", method="antiek_session_cookie"))
    terms = _authoritative_release_terms(runtime)
    path = (
        "/research/distillation/commands/evt-request/reconciliation/actions/release-proven-unsent"
    )

    first = client.post(path, json=terms)
    second = client.post(path, json=terms)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["next_action"] == "none"
    assert first.json()["held_cents"] == 0
    assert first.json()["holds"][-1]["state"] == "released"
    ledger = ResearchSpendLedger(runtime.spend_db_path)
    assert [event.event_kind for event in ledger.events("run-1")].count("hold_released") == 1


@pytest.mark.parametrize(
    "changed",
    [
        {"expected_manifest_sha256": "b" * 64},
        {"expected_hold_id": "substituted-hold"},
        {"expected_fallback_index": 1},
    ],
)
def test_release_rejects_stale_or_substituted_terms(tmp_path, changed) -> None:
    runtime = _seed(tmp_path)
    terms = _authoritative_release_terms(runtime)
    terms.update(changed)
    response = TestClient(_app(runtime, owner_id="owner-1", method="bearer_token")).post(
        "/research/distillation/commands/evt-request/reconciliation/actions/release-proven-unsent",
        json=terms,
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "reconciliation action conflicts"}
    assert ResearchSpendLedger(runtime.spend_db_path).balance("run-1").held_cents == 80


def test_foreign_owner_cannot_release_reserved_hold(tmp_path) -> None:
    runtime = _seed(tmp_path)
    response = TestClient(_app(runtime, owner_id="owner-2", method="cloudflare_access_email")).post(
        "/research/distillation/commands/evt-request/reconciliation/actions/release-proven-unsent",
        json=_authoritative_release_terms(runtime),
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "command unavailable"}
    assert ResearchSpendLedger(runtime.spend_db_path).balance("run-1").held_cents == 80


def test_release_requires_ambiguous_command_state(tmp_path) -> None:
    runtime = _seed(tmp_path)
    import duckdb

    with duckdb.connect(runtime.command_db_path) as connection:
        connection.execute(
            "UPDATE distillation_dispatch_commands SET state='sending',ambiguous_at=NULL "
            "WHERE request_event_id='evt-request'"
        )
    response = TestClient(_app(runtime, owner_id="owner-1", method="bearer_token")).post(
        "/research/distillation/commands/evt-request/reconciliation/actions/release-proven-unsent",
        json=_authoritative_release_terms(runtime),
    )
    assert response.status_code == 409
    assert ResearchSpendLedger(runtime.spend_db_path).balance("run-1").held_cents == 80


def test_release_request_bounds_fail_before_mutation(tmp_path) -> None:
    runtime = _seed(tmp_path)
    terms = _authoritative_release_terms(runtime)
    terms["expected_hold_id"] = "x" * 513
    response = TestClient(_app(runtime, owner_id="owner-1", method="bearer_token")).post(
        "/research/distillation/commands/evt-request/reconciliation/actions/release-proven-unsent",
        json=terms,
    )
    assert response.status_code == 422
    assert ResearchSpendLedger(runtime.spend_db_path).balance("run-1").held_cents == 80


@pytest.mark.parametrize("target_state", ["dispatch_possible", "unknown"])
def test_release_never_restores_provider_possible_exposure(tmp_path, target_state) -> None:
    runtime = _seed(tmp_path)
    ledger = ResearchSpendLedger(runtime.spend_db_path)
    command = DistillationDispatchJournal(runtime.command_db_path).load("evt-request")
    assert command.hold_id is not None
    ledger.mark_dispatch_possible("mark-send", command.hold_id)
    if target_state == "unknown":
        ledger.mark_unknown("mark-unknown", command.hold_id, {"timeout": True})

    response = TestClient(_app(runtime, owner_id="owner-1", method="bearer_token")).post(
        "/research/distillation/commands/evt-request/reconciliation/actions/release-proven-unsent",
        json=_authoritative_release_terms(runtime),
    )

    assert response.status_code == 409
    assert ledger.hold(command.hold_id).state.value == target_state
    assert ledger.balance("run-1").held_cents == 80


@pytest.mark.parametrize(
    ("provider_status", "actual_cents", "expected_state", "expected_held"),
    [
        (ReconciliationStatus.CHARGED, 60, "settled", 0),
        (ReconciliationStatus.NOT_FOUND, None, "released", 0),
        (ReconciliationStatus.UNKNOWN, None, "unknown", 80),
    ],
)
def test_provider_check_applies_only_authoritative_reconciliation(
    tmp_path,
    provider_status,
    actual_cents,
    expected_state,
    expected_held,
) -> None:
    runtime = _seed(tmp_path)
    ledger = ResearchSpendLedger(runtime.spend_db_path)
    command = DistillationDispatchJournal(runtime.command_db_path).load("evt-request")
    assert command.hold_id is not None
    ledger.mark_dispatch_possible("mark-send", command.hold_id)
    ledger.mark_unknown("mark-unknown", command.hold_id, {"timeout": True})
    adapter = FakeReconciliationAdapter(provider_status, actual_cents)
    resolver_calls: list[dict[str, object]] = []
    runtime = _provider_runtime(runtime, adapter, resolver_calls)

    response = TestClient(_app(runtime, owner_id="owner-1", method="bearer_token")).post(
        "/research/distillation/commands/evt-request/reconciliation/actions/check-provider",
        json=_provider_terms(runtime, state="unknown"),
    )

    assert response.status_code == 200
    assert response.json()["holds"][-1]["state"] == expected_state
    assert response.json()["held_cents"] == expected_held
    assert len(resolver_calls) == len(adapter.reconcile_calls) == 1
    assert adapter.send_calls == 0


def test_provider_check_fails_closed_without_server_authority(tmp_path) -> None:
    runtime = _seed(tmp_path)
    ledger = ResearchSpendLedger(runtime.spend_db_path)
    command = DistillationDispatchJournal(runtime.command_db_path).load("evt-request")
    assert command.hold_id is not None
    ledger.mark_dispatch_possible("mark-send", command.hold_id)

    response = TestClient(_app(runtime, owner_id="owner-1", method="bearer_token")).post(
        "/research/distillation/commands/evt-request/reconciliation/actions/check-provider",
        json=_provider_terms(runtime, state="dispatch_possible"),
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "reconciliation action conflicts"}
    assert ledger.hold(command.hold_id).state.value == "dispatch_possible"
    assert ledger.balance("run-1").held_cents == 80


def test_provider_check_rejects_client_provider_authority_fields(tmp_path) -> None:
    runtime = _seed(tmp_path)
    ledger = ResearchSpendLedger(runtime.spend_db_path)
    command = DistillationDispatchJournal(runtime.command_db_path).load("evt-request")
    assert command.hold_id is not None
    ledger.mark_dispatch_possible("mark-send", command.hold_id)
    terms = _provider_terms(runtime, state="dispatch_possible")
    terms.update(
        {
            "provider": "substituted",
            "endpoint": "https://attacker.invalid",
            "actual_cents": 0,
            "evidence": {"provider_lookup": "not_found"},
        }
    )

    response = TestClient(_app(runtime, owner_id="owner-1", method="bearer_token")).post(
        "/research/distillation/commands/evt-request/reconciliation/actions/check-provider",
        json=terms,
    )

    assert response.status_code == 422
    assert ledger.hold(command.hold_id).state.value == "dispatch_possible"


def test_provider_check_terminal_replay_never_requeries_provider(tmp_path) -> None:
    runtime = _seed(tmp_path)
    ledger = ResearchSpendLedger(runtime.spend_db_path)
    command = DistillationDispatchJournal(runtime.command_db_path).load("evt-request")
    assert command.hold_id is not None
    ledger.mark_dispatch_possible("mark-send", command.hold_id)
    adapter = FakeReconciliationAdapter(ReconciliationStatus.NOT_FOUND)
    resolver_calls: list[dict[str, object]] = []
    runtime = _provider_runtime(runtime, adapter, resolver_calls)
    client = TestClient(_app(runtime, owner_id="owner-1", method="bearer_token"))
    path = "/research/distillation/commands/evt-request/reconciliation/actions/check-provider"
    terms = _provider_terms(runtime, state="dispatch_possible")

    first = client.post(path, json=terms)
    replay = client.post(path, json=terms)

    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert len(resolver_calls) == 1
    assert len(adapter.reconcile_calls) == 1
    assert adapter.send_calls == 0


@pytest.mark.parametrize(
    ("owner_id", "changed", "expected_status"),
    [
        ("owner-1", {"expected_hold_id": "stale-hold"}, 409),
        ("owner-1", {"expected_manifest_sha256": "b" * 64}, 409),
        ("owner-2", {}, 404),
    ],
)
def test_provider_check_rejects_stale_terms_and_foreign_owner(
    tmp_path, owner_id, changed, expected_status
) -> None:
    runtime = _seed(tmp_path)
    ledger = ResearchSpendLedger(runtime.spend_db_path)
    command = DistillationDispatchJournal(runtime.command_db_path).load("evt-request")
    assert command.hold_id is not None
    ledger.mark_dispatch_possible("mark-send", command.hold_id)
    adapter = FakeReconciliationAdapter(ReconciliationStatus.NOT_FOUND)
    resolver_calls: list[dict[str, object]] = []
    runtime = _provider_runtime(runtime, adapter, resolver_calls)
    terms = _provider_terms(runtime, state="dispatch_possible")
    terms.update(changed)

    response = TestClient(_app(runtime, owner_id=owner_id, method="bearer_token")).post(
        "/research/distillation/commands/evt-request/reconciliation/actions/check-provider",
        json=terms,
    )

    assert response.status_code == expected_status
    assert resolver_calls == []
    assert adapter.reconcile_calls == []
    assert ledger.balance("run-1").held_cents == 80
