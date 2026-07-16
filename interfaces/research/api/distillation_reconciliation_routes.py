"""Authenticated, read-only distillation reconciliation evidence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from substrate.distillation_dispatch import DistillationDispatchJournal
from substrate.graph import default_db_path
from substrate.research_spend import (
    LedgerIntegrityError,
    PaidHoldState,
    ResearchSpendLedger,
    RunNotFound,
    default_research_spend_db_path,
)

_AUTHENTICATED_METHODS = frozenset(
    {
        "antiek_session_cookie",
        "cloudflare_access_email",
        "cloudflare_service_token",
        "bearer_token",
    }
)
@dataclass(frozen=True)
class DistillationReconciliationRuntime:
    command_db_path: str
    spend_db_path: Path


class DistillationHoldEvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fallback_index: int
    hold_id: str
    provider: str
    model: str
    state: str
    projected_max_cents: int
    actual_cents: int | None
    is_current: bool
    evidence_requirement: Literal[
        "ledger_proven_unsent",
        "authoritative_provider_lookup",
        "terminal_no_action",
    ]


class DistillationReconciliationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_event_id: str
    command_state: str
    spend_run_id: str
    fallback_chain_id: str
    manifest_sha256: str
    current_fallback_index: int
    current_hold_id: str
    currency: Literal["USD"]
    ceiling_cents: int
    authorized_spent_cents: int
    held_cents: int
    available_cents: int
    next_action: Literal[
        "release_proven_unsent",
        "provider_lookup_required",
        "none",
    ]
    action_executable: Literal[False]
    holds: tuple[DistillationHoldEvidenceResponse, ...]


def get_distillation_reconciliation_runtime() -> DistillationReconciliationRuntime:
    return DistillationReconciliationRuntime(
        command_db_path=default_db_path(),
        spend_db_path=default_research_spend_db_path(),
    )


def authenticated_distillation_operator(request: Request) -> str:
    method = getattr(request.state, "auth_method", None)
    operator_id = getattr(request.state, "user_id", None)
    if method not in _AUTHENTICATED_METHODS or not isinstance(operator_id, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
        )
    operator_id = operator_id.strip()
    if not operator_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
        )
    return operator_id


distillation_reconciliation_router = APIRouter(
    prefix="/research/distillation",
    tags=["distillation-reconciliation"],
)


@distillation_reconciliation_router.get(
    "/commands/{request_event_id}/reconciliation",
    response_model=DistillationReconciliationResponse,
)
def get_distillation_reconciliation(
    request_event_id: str,
    operator_id: str = Depends(authenticated_distillation_operator),
    runtime: DistillationReconciliationRuntime = Depends(
        get_distillation_reconciliation_runtime
    ),
) -> DistillationReconciliationResponse:
    if not request_event_id or len(request_event_id.encode("utf-8")) > 512:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="command unavailable")
    try:
        command_journal = DistillationDispatchJournal.open_read_only(
            runtime.command_db_path
        )
        command = command_journal.load_read_only(request_event_id)
    except (KeyError, RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="command unavailable"
        ) from exc
    ledger = ResearchSpendLedger(runtime.spend_db_path)
    try:
        owner_probe = ledger.balance_read_only(command.spend_run_id or "")
    except (KeyError, LedgerIntegrityError, RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="command unavailable"
        ) from exc
    if owner_probe.binding.owner_id != operator_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="command unavailable")
    try:
        command, correlations = command_journal.reconciliation_snapshot(
            request_event_id
        )
        if (
            command.spend_run_id is None
            or command.fallback_chain_id is None
            or command.manifest_sha256 is None
            or command.fallback_index is None
            or command.hold_id is None
        ):
            raise LedgerIntegrityError("command spend correlation is incomplete")
        run, chain, spend_holds = ledger.reconciliation_snapshot(
            operator_id,
            command.spend_run_id,
            command.fallback_chain_id,
            tuple((item.fallback_index, item.hold_id) for item in correlations),
        )
        if chain.manifest_sha256 != command.manifest_sha256:
            raise LedgerIntegrityError("command fallback authority differs from spend ledger")
        holds = []
        for correlation, hold in zip(correlations, spend_holds, strict=True):
            route = chain.routes[correlation.fallback_index]
            if (
                hold.run_id != command.spend_run_id
                or hold.intent.seam_id != route.seam_id
                or hold.intent.provider != route.provider
                or hold.intent.model != route.model
                or hold.intent.operation != route.operation
                or hold.projected_max_cents != route.projected_max_cents
            ):
                raise LedgerIntegrityError("command hold differs from fallback route")
            holds.append(
                DistillationHoldEvidenceResponse(
                    fallback_index=correlation.fallback_index,
                    hold_id=hold.hold_id,
                    provider=route.provider,
                    model=route.model,
                    state=hold.state.value,
                    projected_max_cents=hold.projected_max_cents,
                    actual_cents=hold.actual_cents,
                    is_current=correlation.fallback_index == command.fallback_index,
                    evidence_requirement=_evidence_requirement(hold.state),
                )
            )
        if not holds or holds[-1].hold_id != command.hold_id:
            raise LedgerIntegrityError("command current hold differs from spend lineage")
    except RunNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="command unavailable"
        ) from exc
    except (IndexError, KeyError, LedgerIntegrityError, RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="reconciliation evidence conflicts",
        ) from exc

    current_state = PaidHoldState(holds[-1].state)
    return DistillationReconciliationResponse(
        request_event_id=command.request_event_id,
        command_state=command.state.value,
        spend_run_id=command.spend_run_id,
        fallback_chain_id=command.fallback_chain_id,
        manifest_sha256=command.manifest_sha256,
        current_fallback_index=command.fallback_index,
        current_hold_id=command.hold_id,
        currency="USD",
        ceiling_cents=run.ceiling_cents,
        authorized_spent_cents=run.authorized_spent_cents,
        held_cents=run.held_cents,
        available_cents=run.available_cents,
        next_action=_next_action(current_state),
        action_executable=False,
        holds=tuple(holds),
    )


def _evidence_requirement(
    state: PaidHoldState,
) -> Literal[
    "ledger_proven_unsent",
    "authoritative_provider_lookup",
    "terminal_no_action",
]:
    if state is PaidHoldState.RESERVED:
        return "ledger_proven_unsent"
    if state in (PaidHoldState.DISPATCH_POSSIBLE, PaidHoldState.UNKNOWN):
        return "authoritative_provider_lookup"
    return "terminal_no_action"


def _next_action(
    state: PaidHoldState,
) -> Literal["release_proven_unsent", "provider_lookup_required", "none"]:
    if state is PaidHoldState.RESERVED:
        return "release_proven_unsent"
    if state in (PaidHoldState.DISPATCH_POSSIBLE, PaidHoldState.UNKNOWN):
        return "provider_lookup_required"
    return "none"


__all__ = [
    "DistillationReconciliationRuntime",
    "DistillationReconciliationResponse",
    "authenticated_distillation_operator",
    "distillation_reconciliation_router",
    "get_distillation_reconciliation_runtime",
]
