"""SPR-03 proofs for the hard-ceiling provider boundary."""

from __future__ import annotations

import json
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
    PaidHoldState,
    ResearchSpendLedger,
    RunBinding,
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
    capabilities = ProviderCapabilities(True, True, True)

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

    def send_once(self, operation: object, *, provider_idempotency_key: str):
        self.send_calls.append(provider_idempotency_key)
        if isinstance(self.send_result, BaseException):
            raise self.send_result
        return self.send_result

    def reconcile(self, *, provider_idempotency_key: str) -> ProviderReconciliation:
        self.reconcile_calls.append(provider_idempotency_key)
        return self.reconciliation


def _gateway(tmp_path: Path, *, ceiling: int = 200) -> ResearchProviderGateway:
    gateway = ResearchProviderGateway(
        ResearchSpendLedger(tmp_path / "spend.sqlite3"), projector=_project
    )
    gateway.create_or_reopen_run(_binding(), ceiling_cents=ceiling)
    return gateway


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


def test_primary_success_never_reserves_or_sends_fallback(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path)
    primary = FakeAdapter()
    fallback = FakeAdapter()
    fallback.provider, fallback.model = "fallback-provider", "fallback-model"

    result = gateway.dispatch_paid_fallbacks(
        _binding(),
        logical_operation_id="op",
        operation={"prompt": "bounded"},
        routes=(_fallback_route(primary), _fallback_route(fallback)),
    )

    assert result.outcome is PaidFallbackOutcome.SETTLED
    assert result.fallback_index == 0
    assert result.value_available is True
    assert (result.requested_provider, result.actual_provider) == (
        "test-provider",
        "test-provider",
    )
    assert len(result.attempts) == 1
    assert len(primary.send_calls) == 1
    assert fallback.send_calls == []
    assert len(gateway.ledger.events("run-1")) == 4


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
        ResearchSpendLedger(tmp_path / "spend.sqlite3"), projector=project
    )
    gateway.create_or_reopen_run(_binding(), ceiling_cents=200)
    primary = FakeAdapter()
    primary.send_result = ProviderNotSent("not accepted", evidence={"accepted": False})
    fallback = FakeAdapter()
    fallback.provider, fallback.model = "fallback-provider", "fallback-model"
    fallback.send_result = ProviderSuccess(
        "fallback-answer", 55, {"provider_receipt": "fallback-receipt"}
    )

    result = gateway.dispatch_paid_fallbacks(
        _binding(),
        logical_operation_id="op",
        operation={"prompt": "bounded"},
        routes=(_fallback_route(primary), _fallback_route(fallback)),
    )

    assert result.outcome is PaidFallbackOutcome.SETTLED
    assert result.fallback_index == 1
    assert result.value == "fallback-answer"
    assert result.value_available is True
    assert result.actual_provider == "fallback-provider"
    assert [attempt.hold.projected_max_cents for attempt in result.attempts] == [100, 60]
    first, second = result.attempts
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

    with pytest.raises(PaidFallbackOutcomeUnknown) as unknown:
        gateway.dispatch_paid_fallbacks(
            _binding(),
            logical_operation_id="op",
            operation={"prompt": "bounded"},
            routes=(_fallback_route(primary), _fallback_route(fallback)),
        )
    assert unknown.value.fallback_index == 0
    assert unknown.value.completed_attempts == ()
    assert fallback.send_calls == []
    assert gateway.ledger.balance("run-1").held_cents == 100


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
    first = gateway.dispatch_paid_fallbacks(
        _binding(), logical_operation_id="op", operation={"prompt": "bounded"}, routes=routes
    )
    primary_calls, fallback_calls = len(primary.send_calls), len(fallback.send_calls)

    replay = gateway.dispatch_paid_fallbacks(
        _binding(), logical_operation_id="op", operation={"prompt": "bounded"}, routes=routes
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
    gateway.dispatch_paid_fallbacks(
        _binding(), logical_operation_id="op", operation={"prompt": "bounded"}, routes=routes
    )
    calls = (len(primary.send_calls), len(fallback.send_calls))

    with pytest.raises(IdempotencyConflict):
        gateway.dispatch_paid_fallbacks(
            _binding(),
            logical_operation_id="op",
            operation={"prompt": "bounded"},
            routes=routes[:1],
        )
    assert (len(primary.send_calls), len(fallback.send_calls)) == calls


def test_projection_route_mismatch_is_refused_before_reservation(tmp_path: Path) -> None:
    def mismatched(request: CostProjectionRequest) -> CostProjection:
        return replace(_project(request), provider="other-provider")

    gateway = ResearchProviderGateway(
        ResearchSpendLedger(tmp_path / "spend.sqlite3"), projector=mismatched
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
    gateway = ResearchProviderGateway(ledger, projector=_project)
    gateway.create_or_reopen_run(_binding(), ceiling_cents=200)
    primary = FakeAdapter()
    primary.send_result = ProviderNotSent("not accepted", evidence={"accepted": False})
    fallback = FakeAdapter()
    fallback.provider, fallback.model = "fallback-provider", "fallback-model"
    routes = (_fallback_route(primary), _fallback_route(fallback))

    with pytest.raises(RuntimeError, match="before fallback reserve"):
        gateway.dispatch_paid_fallbacks(
            _binding(),
            logical_operation_id="op",
            operation={"prompt": "bounded"},
            routes=routes,
        )
    assert len(primary.send_calls) == 1
    assert fallback.send_calls == []
    assert gateway.ledger.balance("run-1").held_cents == 0

    reopened = ResearchProviderGateway(ResearchSpendLedger(db_path), projector=_project)
    replay = reopened.dispatch_paid_fallbacks(
        _binding(),
        logical_operation_id="op",
        operation={"prompt": "bounded"},
        routes=routes,
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
        def send_once(self, operation: object, *, provider_idempotency_key: str):
            self.send_calls.append(provider_idempotency_key)
            raise ProviderNotSent("not accepted", evidence={"accepted": False})

    class IdempotentSuccessAdapter(FakeAdapter):
        def __init__(self) -> None:
            super().__init__()
            self.accepted_keys: set[str] = set()
            self.acceptance_count = 0
            self.reused_response_count = 0
            self._lock = threading.Lock()

        def send_once(self, operation: object, *, provider_idempotency_key: str):
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
    barrier = threading.Barrier(2)

    def run_chain(_worker: int):
        barrier.wait()
        return gateway.dispatch_paid_fallbacks(
            _binding(),
            logical_operation_id="op",
            operation={"prompt": "bounded"},
            routes=routes,
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
    adapter.capabilities = ProviderCapabilities(True, False, True)
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
    adapter.capabilities = ProviderCapabilities(True, True, True)
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
