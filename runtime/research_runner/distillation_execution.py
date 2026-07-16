"""Approved hard-ceiling execution seam for wrestling distillation."""

from __future__ import annotations

from dataclasses import dataclass

from substrate.research_spend import FallbackHistoryCursor, RunBinding

from .provider_gateway import (
    PaidFallbackOutcome,
    PaidFallbackPreparation,
    PaidFallbackRoute,
    ResearchProviderGateway,
)


@dataclass(frozen=True, slots=True)
class DistillationProviderValue:
    text: str
    output_tokens: int

    def __post_init__(self) -> None:
        if not self.text:
            raise ValueError("distillation provider text is required")
        if (
            isinstance(self.output_tokens, bool)
            or not isinstance(self.output_tokens, int)
            or self.output_tokens < 0
        ):
            raise ValueError("distillation output_tokens must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class DistillationApprovalRequirement:
    request_event_id: str
    chain_id: str | None
    manifest_sha256: str | None
    ceiling_cents: int | None
    currency: str | None
    maximum_chain_exposure_cents: int | None
    reason: str


@dataclass(frozen=True, slots=True)
class ApprovedDistillationTicket:
    request_event_id: str
    prompt: str
    preparation: PaidFallbackPreparation
    approval_id: str


@dataclass(frozen=True, slots=True)
class DistillationExecutionResult:
    value: DistillationProviderValue
    provider: str
    model: str


class DistillationSpendGateway:
    """Prepare exact approval terms separately from paid execution."""

    def __init__(
        self,
        gateway: ResearchProviderGateway,
        *,
        binding: RunBinding,
        ceiling_cents: int,
        routes: tuple[PaidFallbackRoute[DistillationProviderValue], ...],
    ) -> None:
        if not routes:
            raise ValueError("at least one qualified distillation route is required")
        self.gateway = gateway
        self.binding = binding
        self.ceiling_cents = ceiling_cents
        self.routes = routes

    def prepare(
        self, request_event_id: str, prompt: str
    ) -> DistillationApprovalRequirement | ApprovedDistillationTicket:
        if not request_event_id or not prompt:
            raise ValueError("distillation request identity and prompt are required")
        self.gateway.create_or_reopen_run(self.binding, ceiling_cents=self.ceiling_cents)
        operation = self._operation(request_event_id, prompt)
        preparation = self.gateway.prepare_paid_fallbacks(
            self.binding,
            logical_operation_id=request_event_id,
            operation=operation,
            routes=self.routes,
        )
        approval_id = self._approval_id(preparation.chain_id)
        if approval_id is None:
            return DistillationApprovalRequirement(
                request_event_id=request_event_id,
                chain_id=preparation.chain_id,
                manifest_sha256=preparation.manifest_sha256,
                ceiling_cents=preparation.ceiling_cents,
                currency=preparation.currency,
                maximum_chain_exposure_cents=preparation.maximum_chain_exposure_cents,
                reason="approval_required",
            )
        return ApprovedDistillationTicket(
            request_event_id=request_event_id,
            prompt=prompt,
            preparation=preparation,
            approval_id=approval_id,
        )

    def execute(self, ticket: ApprovedDistillationTicket) -> DistillationExecutionResult:
        operation = self._operation(ticket.request_event_id, ticket.prompt)
        result = self.gateway.dispatch_paid_fallbacks(
            self.binding,
            logical_operation_id=ticket.request_event_id,
            operation=operation,
            routes=self.routes,
            approval_id=ticket.approval_id,
        )
        if (
            result.outcome is not PaidFallbackOutcome.SETTLED
            or not result.value_available
            or not isinstance(result.value, DistillationProviderValue)
            or result.actual_provider is None
            or result.actual_model is None
        ):
            raise RuntimeError("approved distillation execution produced no live value")
        return DistillationExecutionResult(
            value=result.value,
            provider=result.actual_provider,
            model=result.actual_model,
        )

    def _approval_id(self, chain_id: str) -> str | None:
        cursor: FallbackHistoryCursor | None = None
        while True:
            page = self.gateway.ledger.fallback_history(
                self.binding.owner_id, limit=50, cursor=cursor
            )
            for chain in page.items:
                if chain.chain_id == chain_id:
                    return chain.approval_id
            cursor = page.next_cursor
            if cursor is None:
                return None

    @staticmethod
    def _operation(request_event_id: str, prompt: str) -> dict[str, str]:
        return {
            "schema": "antiek.distillation-paid-operation.v1",
            "request_event_id": request_event_id,
            "prompt": prompt,
        }


__all__ = [
    "ApprovedDistillationTicket",
    "DistillationApprovalRequirement",
    "DistillationExecutionResult",
    "DistillationProviderValue",
    "DistillationSpendGateway",
]
