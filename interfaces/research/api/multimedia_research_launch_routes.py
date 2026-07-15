"""Strict private transport for durable multimedia research launch execution."""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field

from substrate.multimedia.research_launch_executor import MultimediaResearchLaunchExecutor
from substrate.multimedia.research_plan import ResearchPlanError, ResearchPlanUnavailableError
from substrate.research_spend import (
    BindingConflict,
    IdempotencyConflict,
    LaunchExecutionSnapshot,
    LedgerIntegrityError,
    RunNotFound,
)

from .multimedia_reconciliation_routes import authenticated_multimedia_operator

_PRIVATE = {"Cache-Control": "private, no-store"}


class _PrivateRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def wrapped(request: Request) -> Response:
            try:
                response = await handler(request)
            except RequestValidationError as exc:
                return JSONResponse(
                    status_code=422, content={"detail": exc.errors()}, headers=_PRIVATE
                )
            except HTTPException as exc:
                exc.headers = {**(exc.headers or {}), **_PRIVATE}
                raise
            response.headers.update(_PRIVATE)
            return response

        return wrapped


class MaterializeBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    launch_reservation_id: str = Field(pattern=r"^mlr_[0-9a-f]{48}$")
    idempotency_key: str = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class AdvanceBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    command_key: str = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class LaunchExecutionResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    execution_id: str
    launch_reservation_id: str
    state: str
    operation_count: int
    operation_totals: dict[str, int]
    next_ordinal: int | None
    blocked_reason: str | None
    recovery_reason: str | None
    execution_started: bool
    ceiling_cents: int
    authorized_spent_cents: int
    held_cents: int
    observed_provider_spend_cents: int


def get_multimedia_research_launch_executor() -> MultimediaResearchLaunchExecutor:
    raise HTTPException(
        status_code=503, detail="launch execution authority is unavailable", headers=_PRIVATE
    )


router = APIRouter(tags=["multimedia-research-launch"], route_class=_PrivateRoute)


def _owner(runtime: MultimediaResearchLaunchExecutor, operator_id: str) -> str:
    # The plan ledger is keyed by the server's owner digest; production wiring replaces
    # this marker on the executor to keep authentication policy out of substrate code.
    resolver = getattr(runtime, "owner_digest_resolver", None)
    if resolver is None:
        raise HTTPException(status_code=503, detail="launch execution authority is unavailable")
    return resolver(operator_id)


def _project(
    runtime: MultimediaResearchLaunchExecutor, snapshot: LaunchExecutionSnapshot
) -> LaunchExecutionResponse:
    run = runtime.spend.balance(snapshot.run_id)
    totals = Counter(item.intent.state.value for item in snapshot.operations)
    selectable = [
        item.intent.ordinal
        for item in snapshot.operations
        if item.intent.state.value
        in {"pending", "claimed", "dispatch_possible", "unknown", "settled"}
    ]
    blocked = next(
        (item.intent.blocked_reason for item in snapshot.operations if item.intent.blocked_reason),
        None,
    )
    recovery = "provider_reconciliation_required" if snapshot.state == "recovery_required" else None
    execution_started = any(
        item.intent.state.value not in {"pending", "blocked_provider_ineligible"}
        for item in snapshot.operations
    )
    return LaunchExecutionResponse(
        execution_id=snapshot.intent.execution_id,
        launch_reservation_id=snapshot.intent.launch_reservation_id,
        state=snapshot.state,
        operation_count=len(snapshot.operations),
        operation_totals=dict(sorted(totals.items())),
        next_ordinal=min(selectable) if selectable else None,
        blocked_reason=blocked,
        recovery_reason=recovery,
        execution_started=execution_started,
        ceiling_cents=run.ceiling_cents,
        authorized_spent_cents=run.authorized_spent_cents,
        held_cents=run.held_cents,
        observed_provider_spend_cents=run.observed_provider_spend_cents,
    )


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, (ResearchPlanUnavailableError, LookupError, RunNotFound)):
        return HTTPException(
            status_code=404, detail="launch execution is unavailable", headers=_PRIVATE
        )
    if isinstance(
        exc, (BindingConflict, IdempotencyConflict, LedgerIntegrityError, ResearchPlanError)
    ):
        return HTTPException(
            status_code=409, detail="launch execution integrity conflicts", headers=_PRIVATE
        )
    return HTTPException(
        status_code=503, detail="launch execution authority is unavailable", headers=_PRIVATE
    )


@router.post(
    "/investigations/{investigation_id}/launch-executions", response_model=LaunchExecutionResponse
)
def materialize(
    investigation_id: str,
    body: MaterializeBody,
    response: Response,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaResearchLaunchExecutor = Depends(get_multimedia_research_launch_executor),
):
    try:
        snapshot, created = runtime.materialize(
            owner_id=_owner(runtime, operator_id),
            investigation_id=investigation_id,
            launch_reservation_id=body.launch_reservation_id,
            command_key=body.idempotency_key,
        )
    except Exception as exc:
        raise _translate(exc) from exc
    response.status_code = 201 if created else 200
    return _project(runtime, snapshot)


@router.post(
    "/investigations/{investigation_id}/launch-execution/advance",
    response_model=LaunchExecutionResponse,
)
def advance(
    investigation_id: str,
    body: AdvanceBody,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaResearchLaunchExecutor = Depends(get_multimedia_research_launch_executor),
):
    try:
        return _project(
            runtime,
            runtime.advance(
                owner_id=_owner(runtime, operator_id),
                investigation_id=investigation_id,
                command_key=body.command_key,
            ),
        )
    except Exception as exc:
        raise _translate(exc) from exc


@router.get(
    "/investigations/{investigation_id}/launch-execution", response_model=LaunchExecutionResponse
)
def get_execution(
    investigation_id: str,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaResearchLaunchExecutor = Depends(get_multimedia_research_launch_executor),
):
    try:
        return _project(
            runtime,
            runtime.get(owner_id=_owner(runtime, operator_id), investigation_id=investigation_id),
        )
    except Exception as exc:
        raise _translate(exc) from exc


__all__ = ["get_multimedia_research_launch_executor", "router"]
