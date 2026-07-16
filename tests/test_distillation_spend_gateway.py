from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from runtime.research_runner.distillation_execution import (
    ApprovedDistillationTicket,
    DistillationApprovalRequirement,
    DistillationProviderValue,
    DistillationSpendGateway,
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
    DispatchIneligible,
    PaidFallbackRoute,
    PaidRouteAuthorityIdentity,
    ProviderCapabilities,
    ProviderReconciliation,
    ProviderSuccess,
    ReconciliationStatus,
    ResearchProviderGateway,
)
from substrate.research_spend import IdempotencyConflict, ResearchSpendLedger, RunBinding


def _binding() -> RunBinding:
    return RunBinding("distill-run", "owner-1", "session-1", "plan-1", 1)


def _request() -> CostProjectionRequest:
    return CostProjectionRequest(
        seam_id="wrestling.distillation.synthesizer",
        provider="qualified-provider",
        model="qualified-model",
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
        rate_snapshot="qualified-rates-v1",
        currency="USD",
        maximum_cost_usd=Decimal("0.80"),
        reservation_cents=80,
        disposition=ProjectionDisposition.HOLD_ELIGIBLE,
    )


class Adapter:
    provider = "qualified-provider"
    model = "qualified-model"
    endpoint = "https://qualified.example/v1"
    capabilities = ProviderCapabilities(
        durable_idempotency=True,
        authoritative_reconciliation=True,
        hidden_retries_disabled=True,
        billing_units=frozenset({BillingUnit.CALL}),
    )

    def __init__(self) -> None:
        self.send_calls: list[str] = []

    def send_once(self, operation, *, provider_idempotency_key, authorized_endpoint):
        assert authorized_endpoint == self.endpoint
        self.send_calls.append(provider_idempotency_key)
        return ProviderSuccess(
            DistillationProviderValue("answer", 7),
            actual_cents=72,
            evidence={"provider_receipt": "receipt-1"},
        )

    def reconcile(self, *, provider_idempotency_key, authorized_endpoint):
        return ProviderReconciliation(
            ReconciliationStatus.CHARGED,
            {"provider_lookup": "charged"},
            actual_cents=72,
        )


def _authorize(request, adapter) -> PaidRouteAuthorityIdentity:
    return PaidRouteAuthorityIdentity(
        provider_kind="qualified-test",
        provider_id=adapter.provider,
        endpoint=adapter.endpoint,
        model=adapter.model,
        seam_id=request.seam_id,
        operation=request.operation,
        rate_snapshot="qualified-rates-v1",
        currency="USD",
        rates=(ProjectionRate(BillingUnit.CALL, Decimal("0.80")),),
    )


def _authority(tmp_path, *, adapter: Adapter | None = None):
    selected = adapter or Adapter()
    gateway = ResearchProviderGateway(
        ResearchSpendLedger(tmp_path / "spend.sqlite3"),
        projector=_project,
        fallback_route_authorizer=_authorize,
    )
    authority = DistillationSpendGateway(
        gateway,
        binding=_binding(),
        ceiling_cents=200,
        routes=(PaidFallbackRoute(_request(), selected),),
    )
    return authority, selected


def test_prepare_exposes_exact_terms_without_hold_or_send(tmp_path) -> None:
    authority, adapter = _authority(tmp_path)

    prepared = authority.prepare("evt-request", "bounded prompt")

    assert isinstance(prepared, DistillationApprovalRequirement)
    assert prepared.reason == "approval_required"
    assert prepared.manifest_sha256 is not None
    assert prepared.maximum_chain_exposure_cents == 80
    assert authority.gateway.ledger.balance("distill-run").held_cents == 0
    assert [event.event_kind for event in authority.gateway.ledger.events("distill-run")] == [
        "run_created"
    ]
    assert adapter.send_calls == []


def test_exact_approval_yields_ticket_hold_before_send_and_settlement(tmp_path) -> None:
    authority, adapter = _authority(tmp_path)
    requirement = authority.prepare("evt-request", "bounded prompt")
    assert isinstance(requirement, DistillationApprovalRequirement)
    preparation = authority.gateway.prepare_paid_fallbacks(
        _binding(),
        logical_operation_id="evt-request",
        operation=authority._operation("evt-request", "bounded prompt"),
        routes=authority.routes,
    )
    authority.gateway.approve_paid_fallbacks(
        "operator-approval-command", _binding(), preparation
    )

    ticket = authority.prepare("evt-request", "bounded prompt")
    assert isinstance(ticket, ApprovedDistillationTicket)
    result = authority.execute(ticket)

    assert result.value.text == "answer"
    assert len(adapter.send_calls) == 1
    balance = authority.gateway.ledger.balance("distill-run")
    assert (balance.authorized_spent_cents, balance.held_cents) == (72, 0)
    assert [event.event_kind for event in authority.gateway.ledger.events("distill-run")] == [
        "run_created",
        "hold_reserved",
        "dispatch_possible",
        "hold_settled",
    ]


def test_changed_prompt_cannot_reuse_manifest_or_approval(tmp_path) -> None:
    authority, _ = _authority(tmp_path)
    authority.prepare("evt-request", "first prompt")
    with pytest.raises(IdempotencyConflict):
        authority.prepare("evt-request", "changed prompt")


def test_unqualified_adapter_refuses_before_hold_or_send(tmp_path) -> None:
    authority, adapter = _authority(tmp_path)
    adapter.capabilities = replace(
        adapter.capabilities, authoritative_reconciliation=False
    )
    with pytest.raises(DispatchIneligible, match="hard-ceiling capabilities"):
        authority.prepare("evt-request", "bounded prompt")
    assert authority.gateway.ledger.balance("distill-run").held_cents == 0
    assert adapter.send_calls == []
