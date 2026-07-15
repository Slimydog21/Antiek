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
    ProviderCapabilities,
    ProviderNotSent,
    ProviderOutcomeUnknown,
    ProviderReconciliation,
    ProviderSuccess,
    ReconciliationStatus,
    ResearchProviderGateway,
)
from substrate.research_spend import (
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
