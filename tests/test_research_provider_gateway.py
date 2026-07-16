"""SPR-03 proofs for the hard-ceiling provider boundary."""

from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from runtime.research_runner.protocol import (
    BillingUnit,
    BoundedUsage,
    CostProjection,
    CostProjectionRequest,
    ProjectionDisposition,
    ProjectionRate,
)
from runtime.research_runner.provider_gateway import (
    HARD_MODE_DISPATCH_POLICY,
    DispatchIneligible,
    PaidFallbackOutcome,
    PaidFallbackOutcomeUnknown,
    PaidFallbackRoute,
    PaidRouteAuthorityIdentity,
    ProviderCapabilities,
    ProviderNotSent,
    ProviderOutcomeUnknown,
    ProviderReconciliation,
    ProviderSuccess,
    ReconciliationStatus,
    ResearchProviderGateway,
)
from substrate.research_spend import (
    IdempotencyConflict,
    InvalidTransition,
    PaidHoldSnapshot,
    PaidHoldState,
    ResearchSpendLedger,
    RunBinding,
    RunNotFound,
    RunStatus,
    SpendCeilingExceeded,
    ZeroCostState,
    ZeroReplayClass,
)


def _binding(run_id: str = "run-1") -> RunBinding:
    return RunBinding(run_id, "owner-1", "session-root-1", "plan-digest", 4)


def test_every_inventoried_dispatch_has_a_hard_mode_disposition() -> None:
    inventory_path = (
        Path(__file__).resolve().parents[1]
        / "runtime"
        / "research_runner"
        / "dispatch_inventory.json"
    )
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    assert {item["seam_id"] for item in inventory} == set(HARD_MODE_DISPATCH_POLICY)
    assert set(HARD_MODE_DISPATCH_POLICY.values()) == {
        "refused_before_dispatch",
        "zero_cost_receipt",
        "unreachable_when_exa_is_refused",
        "unreachable_when_tail_is_refused",
    }


def _request() -> CostProjectionRequest:
    return CostProjectionRequest(
        seam_id="test.paid",
        provider="test-provider",
        model="test-model",
        operation="generate",
        bounded_usage=(BoundedUsage(BillingUnit.CALL, 1),),
    )


def _project(request: CostProjectionRequest) -> CostProjection:
    if request.seam_id == "cascade.gather.contract_stub":
        return CostProjection(
            seam_id=request.seam_id,
            provider=request.provider,
            model=request.model,
            operation=request.operation,
            bounded_usage=request.bounded_usage,
            rates=(ProjectionRate(BillingUnit.LOCAL_OPERATION, Decimal(0)),),
            rate_snapshot="antiek-local-v1",
            currency="USD",
            maximum_cost_usd=Decimal(0),
            reservation_cents=0,
            disposition=ProjectionDisposition.ZERO_COST_RECEIPT,
        )
    return CostProjection(
        seam_id=request.seam_id,
        provider=request.provider,
        model=request.model,
        operation=request.operation,
        bounded_usage=request.bounded_usage,
        rates=(ProjectionRate(BillingUnit.CALL, Decimal("1.00")),),
        rate_snapshot="test-authority-v1",
        currency="USD",
        maximum_cost_usd=Decimal("1.00"),
        reservation_cents=100,
        disposition=ProjectionDisposition.HOLD_ELIGIBLE,
    )


class FakeAdapter:
    provider = "test-provider"
    model = "test-model"
    endpoint = "https://test-provider.example/v1"
    capabilities = ProviderCapabilities(
        True, True, True, frozenset({BillingUnit.CALL})
    )

    def __init__(self) -> None:
        self.send_calls: list[str] = []
        self.reconcile_calls: list[str] = []
        self.send_result: object = ProviderSuccess(
            "answer", 80, {"provider_receipt": "receipt-1"}
        )
        self.reconciliation = ProviderReconciliation(
            ReconciliationStatus.CHARGED,
            {"provider_lookup": "charged"},
            actual_cents=80,
        )

    def send_once(
        self, operation: object, *, provider_idempotency_key: str, authorized_endpoint: str
    ):
        assert authorized_endpoint == self.endpoint
        self.send_calls.append(provider_idempotency_key)
        if isinstance(self.send_result, BaseException):
            raise self.send_result
        return self.send_result

    def reconcile(
        self, *, provider_idempotency_key: str, authorized_endpoint: str
    ) -> ProviderReconciliation:
        assert authorized_endpoint == self.endpoint
        self.reconcile_calls.append(provider_idempotency_key)
        return self.reconciliation


def _gateway(tmp_path: Path, *, ceiling: int = 200) -> ResearchProviderGateway:
    gateway = ResearchProviderGateway(
        ResearchSpendLedger(tmp_path / "spend.sqlite3"),
        projector=_project,
        fallback_route_authorizer=_authorize_fallback,
    )
    gateway.create_or_reopen_run(_binding(), ceiling_cents=ceiling)
    return gateway


def _authorize_fallback(
    request: CostProjectionRequest, adapter: FakeAdapter
) -> PaidRouteAuthorityIdentity:
    assert (adapter.provider, adapter.model) == (request.provider, request.model)
    return PaidRouteAuthorityIdentity(
        provider_kind="test",
        provider_id=request.provider,
        endpoint=f"https://{request.provider}.example/v1",
        model=request.model,
        seam_id=request.seam_id,
        operation=request.operation,
        rate_snapshot="test-authority-v1",
        currency="USD",
        rates=(ProjectionRate(BillingUnit.CALL, Decimal("1.00")),),
    )


def test_hold_is_durable_before_exactly_one_provider_send(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path)
    adapter = FakeAdapter()

    result = gateway.dispatch_paid(
        _binding(),
        logical_operation_id="leaf-1:step-1",
        projection_request=_request(),
        operation={"prompt": "bounded"},
        adapter=adapter,
    )

    assert len(adapter.send_calls) == 1
    assert result.value == "answer"
    assert result.hold.state is PaidHoldState.SETTLED
    assert (result.run.authorized_spent_cents, result.run.held_cents) == (80, 0)
    assert [event.event_kind for event in gateway.ledger.events("run-1")] == [
        "run_created",
        "hold_reserved",
        "dispatch_possible",
        "hold_settled",
    ]


def test_timeout_retains_full_hold_and_replay_reconciles_without_send(
    tmp_path: Path,
) -> None:
    gateway = _gateway(tmp_path)
    adapter = FakeAdapter()
    adapter.send_result = TimeoutError("lost response")

    with pytest.raises(ProviderOutcomeUnknown) as unknown:
        gateway.dispatch_paid(
            _binding(),
            logical_operation_id="leaf-1:step-1",
            projection_request=_request(),
            operation={"prompt": "bounded"},
            adapter=adapter,
        )
    assert gateway.ledger.hold(unknown.value.hold_id).state is PaidHoldState.UNKNOWN
    assert gateway.ledger.balance("run-1").held_cents == 100

    recovered = gateway.dispatch_paid(
        _binding(),
        logical_operation_id="leaf-1:step-1",
        projection_request=_request(),
        operation={"prompt": "bounded"},
        adapter=adapter,
    )
    assert len(adapter.send_calls) == 1
    assert len(adapter.reconcile_calls) == 1
    assert recovered.recovered
    assert recovered.hold.state is PaidHoldState.SETTLED


def test_authoritative_not_found_releases_ambiguous_hold(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path)
    adapter = FakeAdapter()
    adapter.send_result = TimeoutError("lost response")
    adapter.reconciliation = ProviderReconciliation(
        ReconciliationStatus.NOT_FOUND, {"provider_lookup": "not_found"}
    )
    with pytest.raises(ProviderOutcomeUnknown) as unknown:
        gateway.dispatch_paid(
            _binding(),
            logical_operation_id="op",
            projection_request=_request(),
            operation={"prompt": "bounded"},
            adapter=adapter,
        )
    result = gateway.recover_paid(unknown.value.hold_id, adapter)
    assert result.hold.state is PaidHoldState.RELEASED
    assert result.run.held_cents == 0
    assert len(adapter.send_calls) == 1


def _ambiguous_manifest_hold(
    gateway: ResearchProviderGateway, adapter: FakeAdapter
) -> tuple[str, PaidFallbackRoute[str]]:
    adapter.send_result = TimeoutError("lost response")
    route = _fallback_route(adapter)
    approval_id = _approve_fallbacks(gateway, (route,))
    with pytest.raises(PaidFallbackOutcomeUnknown) as unknown:
        gateway.dispatch_paid_fallbacks(
            _binding(),
            logical_operation_id="op",
            operation={"prompt": "bounded"},
            routes=(route,),
            approval_id=approval_id,
        )
    return unknown.value.hold_id, route


def _reconcile_only(
    gateway: ResearchProviderGateway,
    hold_id: str,
    adapter: FakeAdapter,
    route: PaidFallbackRoute[str],
):
    history = gateway.ledger.fallback_history("owner-1").items[0]
    assert history.approval_id is not None
    return gateway.reconcile_paid_only(
        hold_id,
        adapter,
        owner_id="owner-1",
        chain_id=history.chain_id,
        fallback_index=0,
        approval_id=history.approval_id,
        projection_request=route.projection_request,
    )


def test_reconciliation_only_settles_without_another_send(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path)
    adapter = FakeAdapter()
    hold_id, route = _ambiguous_manifest_hold(gateway, adapter)

    result = _reconcile_only(gateway, hold_id, adapter, route)

    assert result.recovered
    assert result.hold.state is PaidHoldState.SETTLED
    assert result.run.authorized_spent_cents == 80
    assert len(adapter.send_calls) == 1
    assert len(adapter.reconcile_calls) == 1


def test_reconciliation_only_authoritative_not_found_releases(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path)
    adapter = FakeAdapter()
    adapter.reconciliation = ProviderReconciliation(
        ReconciliationStatus.NOT_FOUND, {"provider_lookup": "not_found"}
    )
    hold_id, route = _ambiguous_manifest_hold(gateway, adapter)

    result = _reconcile_only(gateway, hold_id, adapter, route)

    assert result.hold.state is PaidHoldState.RELEASED
    assert result.run.held_cents == 0
    assert len(adapter.send_calls) == 1
    assert len(adapter.reconcile_calls) == 1


def test_reconciliation_only_unknown_retains_full_hold(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path)
    adapter = FakeAdapter()
    adapter.reconciliation = ProviderReconciliation(
        ReconciliationStatus.UNKNOWN, {"provider_lookup": "pending"}
    )
    hold_id, route = _ambiguous_manifest_hold(gateway, adapter)

    with pytest.raises(ProviderOutcomeUnknown, match="remains unknown"):
        _reconcile_only(gateway, hold_id, adapter, route)

    assert gateway.ledger.hold(hold_id).state is PaidHoldState.UNKNOWN
    assert gateway.ledger.balance("run-1").held_cents == 100
    assert len(adapter.send_calls) == 1
    assert len(adapter.reconcile_calls) == 1


def test_reconciliation_only_rejects_reserved_hold_before_lookup(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path)
    adapter = FakeAdapter()
    route = _fallback_route(adapter)
    approval_id = _approve_fallbacks(gateway, (route,))
    observed: list[PaidHoldSnapshot] = []

    def stop_before_send(_index: int, hold: PaidHoldSnapshot) -> None:
        observed.append(hold)
        raise RuntimeError("stop before send marker")

    with pytest.raises(RuntimeError, match="stop before send marker"):
        gateway.dispatch_paid_fallbacks(
            _binding(), logical_operation_id="op", operation={"prompt": "bounded"},
            routes=(route,), approval_id=approval_id,
            on_hold_authorized=stop_before_send,
        )
    hold = observed[0]

    with pytest.raises(DispatchIneligible, match="no provider outcome"):
        _reconcile_only(gateway, hold.hold_id, adapter, route)

    assert gateway.ledger.hold(hold.hold_id).state is PaidHoldState.RESERVED
    assert adapter.send_calls == adapter.reconcile_calls == []


def test_reconciliation_only_terminal_replay_does_not_lookup(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path)
    adapter = FakeAdapter()
    route = _fallback_route(adapter)
    approval_id = _approve_fallbacks(gateway, (route,))
    completed = gateway.dispatch_paid_fallbacks(
        _binding(), logical_operation_id="op", operation={"prompt": "bounded"},
        routes=(route,), approval_id=approval_id,
    )
    completed_hold = completed.attempts[0].hold
    adapter.endpoint = "https://rotated-after-terminal.example/v1"

    replay = _reconcile_only(gateway, completed_hold.hold_id, adapter, route)

    assert replay.recovered
    assert replay.hold == completed_hold
    assert len(adapter.send_calls) == 1
    assert adapter.reconcile_calls == []


def test_reconciliation_only_refuses_non_manifest_hold(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path)
    adapter = FakeAdapter()
    adapter.send_result = TimeoutError("lost response")
    with pytest.raises(ProviderOutcomeUnknown) as unknown:
        gateway.dispatch_paid(
            _binding(), logical_operation_id="op", projection_request=_request(),
            operation={"prompt": "bounded"}, adapter=adapter,
        )

    with pytest.raises(RunNotFound):
        gateway.reconcile_paid_only(
            unknown.value.hold_id,
            adapter,
            owner_id="owner-1",
            chain_id="missing-chain",
            fallback_index=0,
            approval_id="missing-approval",
            projection_request=_request(),
        )

    assert gateway.ledger.balance("run-1").held_cents == 100
    assert adapter.reconcile_calls == []


def test_reconciliation_only_rejects_reservation_substitution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway = _gateway(tmp_path)
    adapter = FakeAdapter()
    hold_id, route = _ambiguous_manifest_hold(gateway, adapter)
    load = gateway.ledger.hold
    approved_load = gateway.ledger.approved_fallback_hold
    calls = 0

    def substituted(*args) -> PaidHoldSnapshot:
        nonlocal calls
        calls += 1
        hold = approved_load(*args)
        if calls == 2:
            return replace(
                hold,
                intent=replace(hold.intent, reservation_key="substituted-reservation"),
            )
        return hold

    monkeypatch.setattr(gateway.ledger, "approved_fallback_hold", substituted)
    with pytest.raises(DispatchIneligible, match="reservation changed"):
        _reconcile_only(gateway, hold_id, adapter, route)

    assert adapter.reconcile_calls == []
    assert load(hold_id).state is PaidHoldState.UNKNOWN


def test_reconciliation_only_rejects_adapter_and_capability_drift(
    tmp_path: Path,
) -> None:
    gateway = _gateway(tmp_path)
    adapter = FakeAdapter()
    hold_id, route = _ambiguous_manifest_hold(gateway, adapter)
    mismatched = FakeAdapter()
    mismatched.provider = "other-provider"
    with pytest.raises(DispatchIneligible, match="does not match"):
        _reconcile_only(gateway, hold_id, mismatched, route)

    adapter.capabilities = ProviderCapabilities(
        True, True, True, frozenset({BillingUnit.LOCAL_OPERATION})
    )
    with pytest.raises(DispatchIneligible, match="billing units"):
        _reconcile_only(gateway, hold_id, adapter, route)

    assert adapter.reconcile_calls == mismatched.reconcile_calls == []
    assert gateway.ledger.balance("run-1").held_cents == 100


def test_reconciliation_only_rejects_changed_live_route_authority(
    tmp_path: Path,
) -> None:
    endpoint = ["https://first.example/v1"]

    def authorize(request, adapter):
        return replace(_authorize_fallback(request, adapter), endpoint=endpoint[0])

    gateway = ResearchProviderGateway(
        ResearchSpendLedger(tmp_path / "spend.sqlite3"),
        projector=_project,
        fallback_route_authorizer=authorize,
    )
    gateway.create_or_reopen_run(_binding(), ceiling_cents=200)
    adapter = FakeAdapter()
    route = _fallback_route(adapter)
    adapter.endpoint = endpoint[0]
    hold_id, _ = _ambiguous_manifest_hold(gateway, adapter)
    endpoint[0] = "https://replacement.example/v1"
    adapter.endpoint = endpoint[0]

    with pytest.raises(DispatchIneligible, match="authority changed"):
        _reconcile_only(gateway, hold_id, adapter, route)

    assert adapter.reconcile_calls == []
    assert gateway.ledger.balance("run-1").held_cents == 100


def test_reconciliation_only_not_found_never_advances_fallback(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path)
    primary = FakeAdapter()
    primary.send_result = TimeoutError("lost response")
    primary.reconciliation = ProviderReconciliation(
        ReconciliationStatus.NOT_FOUND, {"provider_lookup": "not_found"}
    )
    fallback = FakeAdapter()
    fallback.provider, fallback.model = "fallback-provider", "fallback-model"
    routes = (_fallback_route(primary), _fallback_route(fallback))
    approval_id = _approve_fallbacks(gateway, routes)
    with pytest.raises(PaidFallbackOutcomeUnknown) as unknown:
        gateway.dispatch_paid_fallbacks(
            _binding(), logical_operation_id="op", operation={"prompt": "bounded"},
            routes=routes, approval_id=approval_id,
        )

    result = _reconcile_only(gateway, unknown.value.hold_id, primary, routes[0])

    assert result.hold.state is PaidHoldState.RELEASED
    assert primary.send_calls and len(primary.reconcile_calls) == 1
    assert fallback.send_calls == fallback.reconcile_calls == []
    assert len(gateway.ledger.fallback_history("owner-1").items[0].routes) == 2


def test_process_death_after_provider_return_reconciles_without_second_send(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "spend.sqlite3"

    def fail(name: str) -> None:
        if name == "settle:before_commit":
            raise RuntimeError("injected process death")

    crashing_ledger = ResearchSpendLedger(db_path, failure_injector=fail)
    gateway = ResearchProviderGateway(crashing_ledger, projector=_project)
    gateway.create_or_reopen_run(_binding(), ceiling_cents=200)
    adapter = FakeAdapter()
    with pytest.raises(RuntimeError, match="process death"):
        gateway.dispatch_paid(
            _binding(),
            logical_operation_id="op",
            projection_request=_request(),
            operation={"prompt": "bounded"},
            adapter=adapter,
        )
    assert len(adapter.send_calls) == 1

    reopened = ResearchProviderGateway(ResearchSpendLedger(db_path), projector=_project)
    result = reopened.dispatch_paid(
        _binding(),
        logical_operation_id="op",
        projection_request=_request(),
        operation={"prompt": "bounded"},
        adapter=adapter,
    )
    assert result.recovered
    assert result.hold.state is PaidHoldState.SETTLED
    assert len(adapter.send_calls) == 1
    assert len(adapter.reconcile_calls) == 1


def test_process_death_after_send_marker_reconciles_without_first_send(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "spend.sqlite3"

    def fail(name: str) -> None:
        if name == "mark_dispatch_possible:after_commit":
            raise RuntimeError("injected death after marker")

    gateway = ResearchProviderGateway(
        ResearchSpendLedger(db_path, failure_injector=fail), projector=_project
    )
    gateway.create_or_reopen_run(_binding(), ceiling_cents=200)
    adapter = FakeAdapter()
    with pytest.raises(RuntimeError, match="after marker"):
        gateway.dispatch_paid(
            _binding(),
            logical_operation_id="op",
            projection_request=_request(),
            operation={"prompt": "bounded"},
            adapter=adapter,
        )
    assert not adapter.send_calls

    adapter.reconciliation = ProviderReconciliation(
        ReconciliationStatus.NOT_FOUND, {"provider_lookup": "not_found"}
    )
    reopened = ResearchProviderGateway(ResearchSpendLedger(db_path), projector=_project)
    result = reopened.dispatch_paid(
        _binding(),
        logical_operation_id="op",
        projection_request=_request(),
        operation={"prompt": "bounded"},
        adapter=adapter,
    )
    assert result.hold.state is PaidHoldState.RELEASED
    assert not adapter.send_calls
    assert len(adapter.reconcile_calls) == 1


def test_closed_unknown_run_accepts_evidence_only_reconciliation(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path)
    adapter = FakeAdapter()
    adapter.send_result = TimeoutError("lost response")
    with pytest.raises(ProviderOutcomeUnknown) as unknown:
        gateway.dispatch_paid(
            _binding(),
            logical_operation_id="op",
            projection_request=_request(),
            operation={"prompt": "bounded"},
            adapter=adapter,
        )
    closed = gateway.ledger.close_execution("close", "run-1", "operator stop")
    assert closed.status is RunStatus.CLOSED_UNRESOLVED
    result = gateway.recover_paid(unknown.value.hold_id, adapter)
    assert result.run.status is RunStatus.CLOSED_RECONCILED
    assert result.run.authorized_spent_cents == 80
    assert len(adapter.send_calls) == 1


def test_final_headroom_concurrency_allows_one_gateway_send(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path, ceiling=100)
    adapter = FakeAdapter()
    adapter.send_result = ProviderSuccess(
        "answer", 100, {"provider_receipt": "final-cent"}
    )
    barrier = threading.Barrier(2)

    def dispatch(worker: int) -> str:
        barrier.wait()
        try:
            gateway.dispatch_paid(
                _binding(),
                logical_operation_id=f"op-{worker}",
                projection_request=_request(),
                operation={"prompt": f"bounded-{worker}"},
                adapter=adapter,
            )
            return "sent"
        except SpendCeilingExceeded:
            return "ceiling"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(dispatch, range(2)))
    assert sorted(outcomes) == ["ceiling", "sent"]
    assert len(adapter.send_calls) == 1
    assert gateway.ledger.balance("run-1").authorized_spent_cents == 100


def test_definite_not_sent_releases_without_blind_retry(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path)
    adapter = FakeAdapter()
    adapter.send_result = ProviderNotSent(
        "provider rejected before acceptance", evidence={"accepted": False}
    )
    result = gateway.dispatch_paid(
        _binding(),
        logical_operation_id="op",
        projection_request=_request(),
        operation={"prompt": "bounded"},
        adapter=adapter,
    )
    assert result.hold.state is PaidHoldState.RELEASED
    assert result.run.available_cents == 200


def _fallback_route(adapter: FakeAdapter) -> PaidFallbackRoute[str]:
    adapter.endpoint = f"https://{adapter.provider}.example/v1"
    return PaidFallbackRoute(
        CostProjectionRequest(
            seam_id="test.paid",
            provider=adapter.provider,
            model=adapter.model,
            operation="generate",
            bounded_usage=(BoundedUsage(BillingUnit.CALL, 1),),
        ),
        adapter,
    )


def _approve_fallbacks(
    gateway: ResearchProviderGateway,
    routes: tuple[PaidFallbackRoute[str], ...],
    *,
    logical_operation_id: str = "op",
    operation: object | None = None,
) -> str:
    operation_payload = {"prompt": "bounded"} if operation is None else operation
    preparation = gateway.prepare_paid_fallbacks(
        _binding(),
        logical_operation_id=logical_operation_id,
        operation=operation_payload,
        routes=routes,
    )
    return gateway.approve_paid_fallbacks(
        f"approve-{preparation.chain_id}", _binding(), preparation
    ).approval_id


def test_primary_success_never_reserves_or_sends_fallback(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path)
    primary = FakeAdapter()
    fallback = FakeAdapter()
    fallback.provider, fallback.model = "fallback-provider", "fallback-model"
    routes = (_fallback_route(primary), _fallback_route(fallback))
    approval_id = _approve_fallbacks(gateway, routes)
    observed: list[tuple[int, str]] = []

    result = gateway.dispatch_paid_fallbacks(
        _binding(),
        logical_operation_id="op",
        operation={"prompt": "bounded"},
        routes=routes,
        approval_id=approval_id,
        on_hold_authorized=lambda index, hold: observed.append((index, hold.hold_id)),
    )

    assert result.outcome is PaidFallbackOutcome.SETTLED
    assert result.fallback_index == 0
    assert result.value_available is True
    assert (result.requested_provider, result.actual_provider) == (
        "test-provider",
        "test-provider",
    )
    assert len(result.attempts) == 1
    assert observed == [(0, result.attempts[0].hold.hold_id)]
    assert len(primary.send_calls) == 1
    assert fallback.send_calls == []
    assert len(gateway.ledger.events("run-1")) == 4


def test_valid_fallback_chain_without_approval_never_reserves_or_sends(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path)
    adapter = FakeAdapter()

    with pytest.raises(DispatchIneligible, match="durable fallback approval"):
        gateway.dispatch_paid_fallbacks(
            _binding(),
            logical_operation_id="op",
            operation={"prompt": "bounded"},
            routes=(_fallback_route(adapter),),
        )

    assert gateway.ledger.fallback_history("owner-1").items[0].outcome.value == "unattempted"
    assert [event.event_kind for event in gateway.ledger.events("run-1")] == ["run_created"]
    assert adapter.send_calls == []


def test_fallback_manifest_is_durable_before_first_reservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway = _gateway(tmp_path)
    adapter = FakeAdapter()
    routes = (_fallback_route(adapter),)
    approval_id = _approve_fallbacks(gateway, routes)

    def fail_before_reservation(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated reserve crash")

    monkeypatch.setattr(gateway.ledger, "reserve_paid", fail_before_reservation)
    with pytest.raises(RuntimeError, match="simulated reserve crash"):
        gateway.dispatch_paid_fallbacks(
            _binding(),
            logical_operation_id="op",
            operation={"prompt": "bounded"},
            routes=routes,
            approval_id=approval_id,
        )

    chain = gateway.ledger.fallback_history("owner-1").items[0]
    assert chain.outcome.value == "unattempted"
    assert chain.routes[0].state.value == "unattempted"
    assert adapter.send_calls == []


def test_fallback_refuses_without_server_route_authority(tmp_path: Path) -> None:
    gateway = ResearchProviderGateway(
        ResearchSpendLedger(tmp_path / "spend.sqlite3"), projector=_project
    )
    gateway.create_or_reopen_run(_binding(), ceiling_cents=200)
    adapter = FakeAdapter()

    with pytest.raises(DispatchIneligible, match="authority is not configured"):
        gateway.dispatch_paid_fallbacks(
            _binding(),
            logical_operation_id="op",
            operation={"prompt": "bounded"},
            routes=(_fallback_route(adapter),),
        )
    assert adapter.send_calls == []
    assert len(gateway.ledger.events("run-1")) == 1


def test_changed_endpoint_authority_conflicts_with_existing_lineage(tmp_path: Path) -> None:
    endpoint = ["https://first.example/v1"]

    def authorize(request, _adapter):
        return replace(_authorize_fallback(request, _adapter), endpoint=endpoint[0])

    gateway = ResearchProviderGateway(
        ResearchSpendLedger(tmp_path / "spend.sqlite3"),
        projector=_project,
        fallback_route_authorizer=authorize,
    )
    gateway.create_or_reopen_run(_binding(), ceiling_cents=200)
    adapter = FakeAdapter()
    route = _fallback_route(adapter)
    adapter.endpoint = endpoint[0]
    approval_id = _approve_fallbacks(gateway, (route,))
    gateway.dispatch_paid_fallbacks(
        _binding(),
        logical_operation_id="op",
        operation={"prompt": "bounded"},
        routes=(route,),
        approval_id=approval_id,
    )
    endpoint[0] = "https://replacement.example/v1"
    adapter.endpoint = endpoint[0]

    with pytest.raises(IdempotencyConflict):
        gateway.dispatch_paid_fallbacks(
            _binding(),
            logical_operation_id="op",
            operation={"prompt": "bounded"},
            routes=(route,),
            approval_id=approval_id,
        )


def test_fallback_refuses_same_snapshot_with_divergent_authoritative_rates(
    tmp_path: Path,
) -> None:
    def divergent(request, adapter):
        return replace(
            _authorize_fallback(request, adapter),
            rates=(ProjectionRate(BillingUnit.CALL, Decimal("0.01")),),
        )

    gateway = ResearchProviderGateway(
        ResearchSpendLedger(tmp_path / "spend.sqlite3"),
        projector=_project,
        fallback_route_authorizer=divergent,
    )
    gateway.create_or_reopen_run(_binding(), ceiling_cents=200)
    adapter = FakeAdapter()

    with pytest.raises(DispatchIneligible, match="exact projected rates"):
        gateway.dispatch_paid_fallbacks(
            _binding(),
            logical_operation_id="op",
            operation={"prompt": "bounded"},
            routes=(_fallback_route(adapter),),
        )
    assert adapter.send_calls == []
    assert len(gateway.ledger.events("run-1")) == 1


def test_concurrent_replay_cannot_reconcile_before_sender_finishes(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path)
    send_started = threading.Event()
    allow_send = threading.Event()

    class SlowAdapter(FakeAdapter):
        def send_once(
            self,
            operation: object,
            *,
            provider_idempotency_key: str,
            authorized_endpoint: str,
        ):
            assert authorized_endpoint == self.endpoint
            self.send_calls.append(provider_idempotency_key)
            send_started.set()
            assert allow_send.wait(timeout=5)
            return ProviderSuccess("answer", 80, {"provider_receipt": "slow"})

    adapter = SlowAdapter()
    routes = (_fallback_route(adapter),)
    approval_id = _approve_fallbacks(gateway, routes)

    def dispatch():
        return gateway.dispatch_paid_fallbacks(
            _binding(),
            logical_operation_id="op",
            operation={"prompt": "bounded"},
            routes=routes,
            approval_id=approval_id,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        sender = pool.submit(dispatch)
        assert send_started.wait(timeout=5)
        replay = pool.submit(dispatch)
        assert not replay.done()
        allow_send.set()
        first = sender.result(timeout=5)
        second = replay.result(timeout=5)

    assert first.outcome is second.outcome is PaidFallbackOutcome.SETTLED
    assert len(adapter.send_calls) == 1
    assert adapter.reconcile_calls == []


def test_dispatch_guard_uses_database_inode_across_hard_link_paths(tmp_path: Path) -> None:
    original = tmp_path / "spend.sqlite3"
    gateway = ResearchProviderGateway(ResearchSpendLedger(original), projector=_project)
    gateway.create_or_reopen_run(_binding(), ceiling_cents=200)
    alias = tmp_path / "same-database.sqlite3"
    os.link(original, alias)
    first = ResearchSpendLedger(original)
    second = ResearchSpendLedger(alias)
    entered = threading.Event()

    def wait_on_alias() -> None:
        with second.dispatch_guard("same-reservation"):
            entered.set()

    pool = ThreadPoolExecutor(max_workers=1)
    try:
        with first.dispatch_guard("same-reservation"):
            waiter = pool.submit(wait_on_alias)
            assert not entered.wait(timeout=0.05)
            assert not waiter.done()
        waiter.result(timeout=5)
        assert entered.is_set()
    finally:
        pool.shutdown(wait=True)


def test_fallback_recovery_requires_unchanged_live_authority(tmp_path: Path) -> None:
    endpoint = ["https://first.example/v1"]

    def authorize(request, adapter):
        return replace(_authorize_fallback(request, adapter), endpoint=endpoint[0])

    gateway = ResearchProviderGateway(
        ResearchSpendLedger(tmp_path / "spend.sqlite3"),
        projector=_project,
        fallback_route_authorizer=authorize,
    )
    gateway.create_or_reopen_run(_binding(), ceiling_cents=200)
    adapter = FakeAdapter()
    adapter.send_result = TimeoutError("lost response")
    route = _fallback_route(adapter)
    adapter.endpoint = endpoint[0]
    approval_id = _approve_fallbacks(gateway, (route,))
    with pytest.raises(PaidFallbackOutcomeUnknown) as unknown:
        gateway.dispatch_paid_fallbacks(
            _binding(),
            logical_operation_id="op",
            operation={"prompt": "bounded"},
            routes=(route,),
            approval_id=approval_id,
        )

    with pytest.raises(DispatchIneligible, match="requires exact"):
        gateway.recover_paid(unknown.value.hold_id, adapter)
    endpoint[0] = "https://replacement.example/v1"
    adapter.endpoint = endpoint[0]
    with pytest.raises(DispatchIneligible, match="authority changed"):
        gateway.recover_paid(
            unknown.value.hold_id,
            adapter,
            projection_request=route.projection_request,
        )
    assert adapter.reconcile_calls == []


def test_authoritative_release_uses_separate_fallback_hold_and_key(tmp_path: Path) -> None:
    def project(request: CostProjectionRequest) -> CostProjection:
        cents = 60 if request.provider == "fallback-provider" else 100
        return replace(
            _project(request),
            rates=(
                ProjectionRate(BillingUnit.CALL, Decimal(cents) / Decimal(100)),
            ),
            maximum_cost_usd=Decimal(cents) / Decimal(100),
            reservation_cents=cents,
            rate_snapshot=f"{request.provider}-rates",
        )

    gateway = ResearchProviderGateway(
        ResearchSpendLedger(tmp_path / "spend.sqlite3"),
        projector=project,
        fallback_route_authorizer=lambda request, adapter: replace(
            _authorize_fallback(request, adapter),
            rate_snapshot=f"{request.provider}-rates",
            rates=(
                ProjectionRate(
                    BillingUnit.CALL,
                    Decimal(60 if request.provider == "fallback-provider" else 100)
                    / Decimal(100),
                ),
            ),
        ),
    )
    gateway.create_or_reopen_run(_binding(), ceiling_cents=200)
    primary = FakeAdapter()
    primary.send_result = ProviderNotSent("not accepted", evidence={"accepted": False})
    fallback = FakeAdapter()
    fallback.provider, fallback.model = "fallback-provider", "fallback-model"
    fallback.send_result = ProviderSuccess(
        "fallback-answer", 55, {"provider_receipt": "fallback-receipt"}
    )
    routes = (_fallback_route(primary), _fallback_route(fallback))
    approval_id = _approve_fallbacks(gateway, routes)
    observed: list[tuple[int, str]] = []

    result = gateway.dispatch_paid_fallbacks(
        _binding(),
        logical_operation_id="op",
        operation={"prompt": "bounded"},
        routes=routes,
        approval_id=approval_id,
        on_hold_authorized=lambda index, hold: observed.append((index, hold.hold_id)),
    )

    assert result.outcome is PaidFallbackOutcome.SETTLED
    assert result.fallback_index == 1
    assert result.value == "fallback-answer"
    assert result.value_available is True
    assert result.actual_provider == "fallback-provider"
    assert [attempt.hold.projected_max_cents for attempt in result.attempts] == [100, 60]
    first, second = result.attempts
    assert observed == [(0, first.hold.hold_id), (1, second.hold.hold_id)]
    assert first.hold.hold_id != second.hold.hold_id
    assert first.hold.intent.provider_idempotency_key != (
        second.hold.intent.provider_idempotency_key
    )
    assert first.hold.state is PaidHoldState.RELEASED
    assert second.hold.state is PaidHoldState.SETTLED
    assert result.run.authorized_spent_cents == 55


def test_ambiguous_primary_halts_before_fallback_send(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path)
    primary = FakeAdapter()
    primary.send_result = TimeoutError("lost response")
    fallback = FakeAdapter()
    fallback.provider, fallback.model = "fallback-provider", "fallback-model"
    routes = (_fallback_route(primary), _fallback_route(fallback))
    approval_id = _approve_fallbacks(gateway, routes)
    observed: list[str] = []

    def observe(fallback_index: int, hold: PaidHoldSnapshot) -> None:
        assert fallback_index == 0
        assert primary.send_calls == []
        observed.append(hold.hold_id)

    with pytest.raises(PaidFallbackOutcomeUnknown) as unknown:
        gateway.dispatch_paid_fallbacks(
            _binding(),
            logical_operation_id="op",
            operation={"prompt": "bounded"},
            routes=routes,
            approval_id=approval_id,
            on_hold_authorized=observe,
        )
    assert unknown.value.fallback_index == 0
    assert unknown.value.completed_attempts == ()
    assert fallback.send_calls == []
    assert gateway.ledger.balance("run-1").held_cents == 100
    assert observed == [unknown.value.hold_id]

    observed.clear()

    def observe_before_reconcile(fallback_index: int, hold: PaidHoldSnapshot) -> None:
        assert fallback_index == 0
        assert primary.reconcile_calls == []
        observed.append(hold.hold_id)

    recovered = gateway.dispatch_paid_fallbacks(
        _binding(),
        logical_operation_id="op",
        operation={"prompt": "bounded"},
        routes=routes,
        approval_id=approval_id,
        on_hold_authorized=observe_before_reconcile,
    )
    assert recovered.outcome is PaidFallbackOutcome.SETTLED
    assert observed == [unknown.value.hold_id]
    assert len(primary.reconcile_calls) == 1


def test_fallback_preflight_refuses_every_route_before_ledger_mutation(
    tmp_path: Path,
) -> None:
    gateway = _gateway(tmp_path)
    primary = FakeAdapter()
    fallback = FakeAdapter()
    fallback.provider, fallback.model = "fallback-provider", "fallback-model"
    fallback.capabilities = ProviderCapabilities(True, False, True)

    with pytest.raises(DispatchIneligible, match="capabilities"):
        gateway.dispatch_paid_fallbacks(
            _binding(),
            logical_operation_id="op",
            operation={"prompt": "bounded"},
            routes=(_fallback_route(primary), _fallback_route(fallback)),
        )
    assert primary.send_calls == fallback.send_calls == []
    assert [event.event_kind for event in gateway.ledger.events("run-1")] == [
        "run_created"
    ]


def test_replay_reuses_released_and_settled_route_lineage_without_send(
    tmp_path: Path,
) -> None:
    gateway = _gateway(tmp_path)
    primary = FakeAdapter()
    primary.send_result = ProviderNotSent("not accepted", evidence={"accepted": False})
    fallback = FakeAdapter()
    fallback.provider, fallback.model = "fallback-provider", "fallback-model"
    routes = (_fallback_route(primary), _fallback_route(fallback))
    approval_id = _approve_fallbacks(gateway, routes)
    first = gateway.dispatch_paid_fallbacks(
        _binding(), logical_operation_id="op", operation={"prompt": "bounded"},
        routes=routes, approval_id=approval_id,
    )
    primary_calls, fallback_calls = len(primary.send_calls), len(fallback.send_calls)

    replay = gateway.dispatch_paid_fallbacks(
        _binding(), logical_operation_id="op", operation={"prompt": "bounded"},
        routes=routes, approval_id=approval_id,
    )
    assert replay.outcome is PaidFallbackOutcome.SETTLED
    assert replay.fallback_index == 1
    assert replay.value is None
    assert replay.value_available is False
    assert [item.hold.hold_id for item in replay.attempts] == [
        item.hold.hold_id for item in first.attempts
    ]
    assert all(item.recovered for item in replay.attempts)
    assert (len(primary.send_calls), len(fallback.send_calls)) == (
        primary_calls,
        fallback_calls,
    )


def test_replay_with_shortened_chain_conflicts_before_another_send(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path)
    primary = FakeAdapter()
    primary.send_result = ProviderNotSent("not accepted", evidence={"accepted": False})
    fallback = FakeAdapter()
    fallback.provider, fallback.model = "fallback-provider", "fallback-model"
    routes = (_fallback_route(primary), _fallback_route(fallback))
    approval_id = _approve_fallbacks(gateway, routes)
    gateway.dispatch_paid_fallbacks(
        _binding(), logical_operation_id="op", operation={"prompt": "bounded"},
        routes=routes, approval_id=approval_id,
    )
    calls = (len(primary.send_calls), len(fallback.send_calls))

    with pytest.raises(IdempotencyConflict):
        gateway.dispatch_paid_fallbacks(
            _binding(),
            logical_operation_id="op",
            operation={"prompt": "bounded"},
            routes=routes[:1],
            approval_id=approval_id,
        )
    assert (len(primary.send_calls), len(fallback.send_calls)) == calls


def test_projection_route_mismatch_is_refused_before_reservation(tmp_path: Path) -> None:
    def mismatched(request: CostProjectionRequest) -> CostProjection:
        return replace(_project(request), provider="other-provider")

    gateway = ResearchProviderGateway(
        ResearchSpendLedger(tmp_path / "spend.sqlite3"),
        projector=mismatched,
        fallback_route_authorizer=_authorize_fallback,
    )
    gateway.create_or_reopen_run(_binding(), ceiling_cents=200)
    adapter = FakeAdapter()
    with pytest.raises(DispatchIneligible, match="projection differs"):
        gateway.dispatch_paid_fallbacks(
            _binding(),
            logical_operation_id="op",
            operation={"prompt": "bounded"},
            routes=(_fallback_route(adapter),),
        )
    assert adapter.send_calls == []
    assert [event.event_kind for event in gateway.ledger.events("run-1")] == [
        "run_created"
    ]


def test_process_death_after_primary_release_replays_into_one_fallback_hold(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "spend.sqlite3"

    class CrashBeforeSecondReserveLedger(ResearchSpendLedger):
        def __init__(self, path: Path) -> None:
            super().__init__(path)
            self.reserve_calls = 0

        def reserve_paid(self, command_key, binding, intent, projected_max_cents):
            self.reserve_calls += 1
            if self.reserve_calls == 2:
                raise RuntimeError("process death before fallback reserve")
            return super().reserve_paid(command_key, binding, intent, projected_max_cents)

    ledger = CrashBeforeSecondReserveLedger(db_path)
    gateway = ResearchProviderGateway(
        ledger, projector=_project, fallback_route_authorizer=_authorize_fallback
    )
    gateway.create_or_reopen_run(_binding(), ceiling_cents=200)
    primary = FakeAdapter()
    primary.send_result = ProviderNotSent("not accepted", evidence={"accepted": False})
    fallback = FakeAdapter()
    fallback.provider, fallback.model = "fallback-provider", "fallback-model"
    routes = (_fallback_route(primary), _fallback_route(fallback))
    approval_id = _approve_fallbacks(gateway, routes)

    with pytest.raises(RuntimeError, match="before fallback reserve"):
        gateway.dispatch_paid_fallbacks(
            _binding(),
            logical_operation_id="op",
            operation={"prompt": "bounded"},
            routes=routes,
            approval_id=approval_id,
        )
    assert len(primary.send_calls) == 1
    assert fallback.send_calls == []
    assert gateway.ledger.balance("run-1").held_cents == 0

    reopened = ResearchProviderGateway(
        ResearchSpendLedger(db_path),
        projector=_project,
        fallback_route_authorizer=_authorize_fallback,
    )
    replay = reopened.dispatch_paid_fallbacks(
        _binding(),
        logical_operation_id="op",
        operation={"prompt": "bounded"},
        routes=routes,
        approval_id=approval_id,
    )
    assert replay.fallback_index == 1
    assert replay.attempts[0].recovered is True
    assert len(primary.send_calls) == 1
    assert len(fallback.send_calls) == 1
    holds = [event.hold_id for event in reopened.ledger.events("run-1") if event.hold_id]
    assert len(set(holds)) == 2


def test_concurrent_same_plan_has_one_provider_acceptance_per_route(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path)

    class RejectedAdapter(FakeAdapter):
        def send_once(
            self,
            operation: object,
            *,
            provider_idempotency_key: str,
            authorized_endpoint: str,
        ):
            assert authorized_endpoint == self.endpoint
            self.send_calls.append(provider_idempotency_key)
            raise ProviderNotSent("not accepted", evidence={"accepted": False})

    class IdempotentSuccessAdapter(FakeAdapter):
        def __init__(self) -> None:
            super().__init__()
            self.accepted_keys: set[str] = set()
            self.acceptance_count = 0
            self.reused_response_count = 0
            self._lock = threading.Lock()

        def send_once(
            self,
            operation: object,
            *,
            provider_idempotency_key: str,
            authorized_endpoint: str,
        ):
            assert authorized_endpoint == self.endpoint
            self.send_calls.append(provider_idempotency_key)
            with self._lock:
                if provider_idempotency_key in self.accepted_keys:
                    self.reused_response_count += 1
                else:
                    self.accepted_keys.add(provider_idempotency_key)
                    self.acceptance_count += 1
            return ProviderSuccess("answer", 80, {"provider_receipt": "same-operation"})

    primary = RejectedAdapter()
    primary.reconciliation = ProviderReconciliation(
        ReconciliationStatus.NOT_FOUND, {"provider_lookup": "not_found"}
    )
    fallback = IdempotentSuccessAdapter()
    fallback.provider, fallback.model = "fallback-provider", "fallback-model"
    routes = (_fallback_route(primary), _fallback_route(fallback))
    approval_id = _approve_fallbacks(gateway, routes)
    barrier = threading.Barrier(2)

    def run_chain(_worker: int):
        barrier.wait()
        return gateway.dispatch_paid_fallbacks(
            _binding(),
            logical_operation_id="op",
            operation={"prompt": "bounded"},
            routes=routes,
            approval_id=approval_id,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run_chain, range(2)))
    assert all(result.outcome is PaidFallbackOutcome.SETTLED for result in results)
    assert fallback.acceptance_count == 1
    assert fallback.acceptance_count + fallback.reused_response_count == len(
        fallback.send_calls
    )
    assert len(fallback.accepted_keys) == 1
    assert len({call for call in fallback.send_calls}) == 1
    assert gateway.ledger.balance("run-1").authorized_spent_cents == 80


def test_equivalent_terminal_outcome_converges_across_different_evidence(
    tmp_path: Path,
) -> None:
    gateway = _gateway(tmp_path)
    adapter = FakeAdapter()
    settled = gateway.dispatch_paid(
        _binding(),
        logical_operation_id="settled",
        projection_request=_request(),
        operation={"prompt": "bounded"},
        adapter=adapter,
    )
    converged = gateway._settle_or_converge(  # noqa: SLF001
        f"research-settle-command:{settled.hold.hold_id}",
        settled.hold,
        80,
        {"provider_lookup": "same charge, different evidence"},
    )
    assert converged.authorized_spent_cents == 80

    released_adapter = FakeAdapter()
    released_adapter.provider, released_adapter.model = "released-provider", "released-model"
    released_adapter.send_result = ProviderNotSent(
        "not accepted", evidence={"accepted": False}
    )
    released = gateway.dispatch_paid(
        _binding(),
        logical_operation_id="released",
        projection_request=_fallback_route(released_adapter).projection_request,
        operation={"prompt": "bounded"},
        adapter=released_adapter,
    )
    converged_release = gateway._release_or_converge(  # noqa: SLF001
        f"research-not-sent-command:{released.hold.hold_id}",
        released.hold,
        {"provider_lookup": "same absence, different evidence"},
    )
    assert converged_release.authorized_spent_cents == 80


def test_actual_above_projection_is_observed_and_freezes_run(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path)
    adapter = FakeAdapter()
    adapter.send_result = ProviderSuccess(
        "answer", 175, {"provider_receipt": "breach"}
    )
    result = gateway.dispatch_paid(
        _binding(),
        logical_operation_id="op",
        projection_request=_request(),
        operation={"prompt": "bounded"},
        adapter=adapter,
    )
    assert result.run.authorized_spent_cents == 100
    assert result.run.observed_provider_spend_cents == 175
    assert result.run.status is RunStatus.CEILING_BREACHED
    with pytest.raises(InvalidTransition):
        gateway.dispatch_paid(
            _binding(),
            logical_operation_id="next",
            projection_request=_request(),
            operation={"prompt": "next"},
            adapter=adapter,
        )
    assert len(adapter.send_calls) == 1


def test_incapable_adapter_and_real_catalog_route_fail_before_send(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path)
    adapter = FakeAdapter()
    adapter.capabilities = ProviderCapabilities(
        True, False, True, frozenset({BillingUnit.CALL})
    )
    with pytest.raises(DispatchIneligible, match="capabilities"):
        gateway.dispatch_paid(
            _binding(),
            logical_operation_id="op",
            projection_request=_request(),
            operation={"prompt": "bounded"},
            adapter=adapter,
        )
    assert not adapter.send_calls

    real_gateway = ResearchProviderGateway(gateway.ledger)
    exa_request = CostProjectionRequest(
        seam_id="cascade.gather.exa.search",
        provider="exa",
        model="search",
        operation="search",
        bounded_usage=(BoundedUsage(BillingUnit.CALL, 1),),
    )
    adapter.capabilities = ProviderCapabilities(
        True, True, True, frozenset({BillingUnit.CALL})
    )
    adapter.provider, adapter.model = "exa", "search"
    with pytest.raises(DispatchIneligible):
        real_gateway.dispatch_paid(
            _binding(),
            logical_operation_id="exa-op",
            projection_request=exa_request,
            operation={"query": "history of flight"},
            adapter=adapter,
        )
    assert not adapter.send_calls


def test_adapter_billing_units_must_match_projection_before_send(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path)
    adapter = FakeAdapter()
    adapter.capabilities = ProviderCapabilities(
        True, True, True, frozenset({BillingUnit.INPUT_TOKEN})
    )

    with pytest.raises(DispatchIneligible, match="billing units"):
        gateway.dispatch_paid(
            _binding(),
            logical_operation_id="op",
            projection_request=_request(),
            operation={"prompt": "bounded"},
            adapter=adapter,
        )
    assert not adapter.send_calls


def test_reserved_restart_is_provably_unsent_and_released(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path)
    adapter = FakeAdapter()
    projection = _project(_request())
    operation = {"prompt": "bounded"}
    from runtime.research_runner.provider_gateway import canonical_digest, deterministic_key
    from substrate.research_spend import PaidHoldIntent

    identity = ("run-1", "op", canonical_digest(operation))
    intent = PaidHoldIntent(
        deterministic_key("research-reservation", *identity),
        "test.paid",
        "test-provider",
        "test-model",
        "generate",
        canonical_digest(operation),
        canonical_digest(projection),
        "test-authority-v1",
        deterministic_key(
            "research-provider", "test-provider", "test-model", *identity
        ),
    )
    hold = gateway.ledger.reserve_paid("injected-reserve", _binding(), intent, 100)
    result = gateway.recover_paid(hold.hold_id, adapter)
    assert result.hold.state is PaidHoldState.RELEASED
    assert not adapter.send_calls
    assert not adapter.reconcile_calls


def test_prepared_zero_cost_replay_is_not_falsely_completed(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path)
    zero_request = CostProjectionRequest(
        seam_id="cascade.gather.contract_stub",
        provider="antiek",
        model="contract-stub",
        operation="gather",
        bounded_usage=(BoundedUsage(BillingUnit.LOCAL_OPERATION, 1),),
    )
    receipt = gateway.prepare_zero_cost(
        _binding(),
        logical_operation_id="leaf-1:gather",
        projection_request=zero_request,
        operation_payload={"question": "why"},
        replay_class=ZeroReplayClass.CHECKPOINT_RESUMABLE,
    )
    assert receipt.attempt.state is ZeroCostState.PREPARED
    assert gateway.ledger.recovery_work("run-1")[-1].action == "resume"

    replay = gateway.prepare_zero_cost(
        _binding(),
        logical_operation_id="leaf-1:gather",
        projection_request=zero_request,
        operation_payload={"question": "why"},
        replay_class=ZeroReplayClass.CHECKPOINT_RESUMABLE,
    )
    assert replay.attempt.attempt_id == receipt.attempt.attempt_id
    assert replay.replayed
    assert replay.attempt.state is ZeroCostState.PREPARED
    completed = gateway.complete_zero_cost(replay, outcome={"steps": 2})
    assert completed.state is ZeroCostState.COMPLETED
    terminal_replay = gateway.prepare_zero_cost(
        _binding(),
        logical_operation_id="leaf-1:gather",
        projection_request=zero_request,
        operation_payload={"question": "why"},
        replay_class=ZeroReplayClass.CHECKPOINT_RESUMABLE,
    )
    assert terminal_replay.replayed
    assert terminal_replay.attempt.state is ZeroCostState.COMPLETED
    assert gateway.complete_zero_cost(
        replace(replay, attempt=completed), outcome={"steps": 2}
    ) == completed
