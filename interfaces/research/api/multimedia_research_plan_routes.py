"""Owner-private multimedia research-plan handoff and approval routes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field

from substrate.multimedia.research_intent import (
    ResearchIntentError,
    ResearchIntentLedger,
    ResearchIntentUnavailableError,
)
from substrate.multimedia.research_plan import (
    InvestigationActivationAuthorization,
    InvestigationActivationQuote,
    PreparedInvestigation,
    ResearchPlan,
    ResearchPlanError,
    ResearchPlanLedger,
    ResearchPlanStorageError,
    ResearchPlanTooLargeError,
    ResearchPlanUnavailableError,
    ResearchPlanValidationError,
)

from .multimedia_reconciliation_routes import authenticated_multimedia_operator

_PRIVATE = {"Cache-Control": "private, no-store"}


class _PrivateNoStoreRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def private_handler(request: Request) -> Response:
            try:
                response = await handler(request)
            except RequestValidationError as exc:
                return JSONResponse(status_code=422, content={"detail": exc.errors()}, headers=_PRIVATE)
            except HTTPException as exc:
                exc.headers = {**(exc.headers or {}), **_PRIVATE}
                raise
            except Exception:
                return JSONResponse(
                    status_code=500,
                    content={"detail": "research plan authority is unavailable"},
                    headers=_PRIVATE,
                )
            response.headers.update(_PRIVATE)
            return response

        return private_handler


class ResearchPlanHandoffBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    idempotency_key: str = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class ResearchPlanApproveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_plan_version: int = Field(ge=1, strict=True)


class PreparedInvestigationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    expected_plan_version: int = Field(ge=1, strict=True)


class InvestigationActivationAuthorizationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    route_policy: Literal["cheapest", "balanced", "highest_quality"]
    approved_ceiling_cents: int = Field(gt=0, le=9_223_372_036_854_775_807, strict=True)
    ttl_seconds: int = Field(ge=60, le=86400, strict=True)


class ResearchPlanAddChildOperation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    type: Literal["add_child"]
    parent_node_id: str = Field(pattern=r"^mrpn_[0-9a-f]{48}$")
    position: int = Field(ge=0, strict=True)
    question: str = Field(min_length=3, max_length=2000)


class ResearchPlanUpdateQuestionOperation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    type: Literal["update_question"]
    node_id: str = Field(pattern=r"^mrpn_[0-9a-f]{48}$")
    question: str = Field(min_length=3, max_length=2000)


class ResearchPlanMoveSubtreeOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["move_subtree"]
    node_id: str = Field(pattern=r"^mrpn_[0-9a-f]{48}$")
    new_parent_node_id: str = Field(pattern=r"^mrpn_[0-9a-f]{48}$")
    position: int = Field(ge=0, strict=True)


class ResearchPlanRemoveSubtreeOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["remove_subtree"]
    node_id: str = Field(pattern=r"^mrpn_[0-9a-f]{48}$")


ResearchPlanEditOperation = Annotated[
    ResearchPlanAddChildOperation | ResearchPlanUpdateQuestionOperation
    | ResearchPlanMoveSubtreeOperation | ResearchPlanRemoveSubtreeOperation,
    Field(discriminator="type"),
]


class ResearchPlanEditBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    idempotency_key: str = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    expected_plan_version: int = Field(ge=1, strict=True)
    operations: list[ResearchPlanEditOperation] = Field(min_length=1, max_length=64)


class ResearchPlanNodeResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: str
    kind: Literal["research_question"]
    question: str
    children: tuple[ResearchPlanNodeResponse, ...]


class ResearchPlanRootResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: str
    kind: Literal["research_question"]
    question: str
    source_intent_id: str
    source_intent_digest: str
    source_evidence_digest: str
    children: tuple[ResearchPlanNodeResponse, ...]


class ResearchPlanTreeResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    root: ResearchPlanRootResponse


class ResearchPlanResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    plan_id: str
    source_intent_id: str
    source_intent_digest: str
    source_evidence_digest: str
    request_digest: str
    state: Literal["draft", "approved"]
    plan_version: int
    tree: ResearchPlanTreeResponse
    created_at: str
    updated_at: str
    approved_at: str | None
    research_launched: Literal[False]
    provider_launch_authorized: Literal[False]
    spend_authority_digest: None


class PreparedInvestigationResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    investigation_id: str
    source_plan_id: str
    source_plan_version: int
    source_intent_id: str
    source_intent_digest: str
    source_evidence_digest: str
    tree: ResearchPlanTreeResponse
    total_node_count: int
    leaf_question_count: int
    request_digest: str
    state: Literal["prepared"]
    created_at: str
    execution_started: Literal[False]
    background_work_authorized: Literal[False]
    event_authority_digest: None
    graph_authority_digest: None
    provider_authority_digest: None
    spend_authority_digest: None


class InvestigationActivationAuthorizationResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    authorization_id: str
    investigation_id: str
    prepared_integrity_digest: str
    source_plan_id: str
    source_plan_version: int
    source_plan_integrity_digest: str
    source_intent_id: str
    source_intent_digest: str
    source_evidence_digest: str
    total_node_count: int
    leaf_question_count: int
    route_policy: Literal["cheapest", "balanced", "highest_quality"]
    resolved_tier: str
    provider: str
    model: str
    dispatch_config_digest: str
    pricing_source: str
    pricing_digest: str
    workload_digest: str
    quoted_ceiling_cents: int
    quote_id: str
    quote_issued_at: str
    quote_expires_at: str
    quote_digest: str
    approved_ceiling_cents: int
    ttl_seconds: int = Field(ge=60, le=86400, strict=True)
    request_digest: str
    issued_at: str
    expires_at: str
    is_expired: bool
    state: Literal["authorized"]
    execution_started: Literal[False]
    event_authority_digest: None
    graph_authority_digest: None
    provider_authority_digest: None
    spend_reservation_digest: None
    consumed_at: None
    background_work_authorized: Literal[False]


@dataclass(frozen=True)
class ResearchPlanRouteRuntime:
    plans: ResearchPlanLedger
    intents: ResearchIntentLedger
    owner_digest_resolver: Callable[[str], str]
    activation_quote_resolver: (
        Callable[[PreparedInvestigation, str], InvestigationActivationQuote] | None
    ) = None


def get_multimedia_research_plan_runtime() -> ResearchPlanRouteRuntime:
    raise HTTPException(status_code=503, detail="research plan runtime is unavailable", headers=_PRIVATE)


multimedia_research_plan_router = APIRouter(
    tags=["multimedia-research-plan"], route_class=_PrivateNoStoreRoute
)


@multimedia_research_plan_router.post(
    "/research-intents/{intent_id}/plan", response_model=ResearchPlanResponse
)
def handoff_multimedia_research_plan(
    intent_id: str,
    body: ResearchPlanHandoffBody,
    response: Response,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: ResearchPlanRouteRuntime = Depends(get_multimedia_research_plan_runtime),
) -> ResearchPlanResponse:
    try:
        owner_digest = runtime.owner_digest_resolver(operator_id)
        intent = runtime.intents.get(owner_identity_digest=owner_digest, intent_id=intent_id)
        if intent.intent_id != intent_id:
            raise ResearchPlanError("research plan source intent conflicts")
        plan, created = runtime.plans.handoff(
            owner_identity_digest=owner_digest,
            idempotency_key=body.idempotency_key,
            intent=intent,
        )
    except ResearchPlanUnavailableError as exc:
        raise _private_not_found() from exc
    except ResearchPlanStorageError as exc:
        raise _private_unavailable() from exc
    except ResearchPlanError as exc:
        raise HTTPException(status_code=409, detail=str(exc), headers=_PRIVATE) from exc
    except ResearchIntentUnavailableError as exc:
        raise _private_not_found() from exc
    except (ResearchIntentError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="research plan authority conflicts", headers=_PRIVATE) from exc
    response.status_code = 201 if created else 200
    return _response(plan)


@multimedia_research_plan_router.get(
    "/research-plans/{plan_id}", response_model=ResearchPlanResponse
)
def get_multimedia_research_plan(
    plan_id: str,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: ResearchPlanRouteRuntime = Depends(get_multimedia_research_plan_runtime),
) -> ResearchPlanResponse:
    try:
        return _response(runtime.plans.get(
            owner_identity_digest=runtime.owner_digest_resolver(operator_id), plan_id=plan_id
        ))
    except ResearchPlanUnavailableError as exc:
        raise _private_not_found() from exc
    except ResearchPlanStorageError as exc:
        raise _private_unavailable() from exc
    except (ResearchPlanError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="research plan integrity conflicts", headers=_PRIVATE) from exc


@multimedia_research_plan_router.post(
    "/research-plans/{plan_id}/approve", response_model=ResearchPlanResponse
)
def approve_multimedia_research_plan(
    plan_id: str,
    body: ResearchPlanApproveBody,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: ResearchPlanRouteRuntime = Depends(get_multimedia_research_plan_runtime),
) -> ResearchPlanResponse:
    try:
        return _response(runtime.plans.approve(
            owner_identity_digest=runtime.owner_digest_resolver(operator_id),
            plan_id=plan_id,
            expected_plan_version=body.expected_plan_version,
        ))
    except ResearchPlanUnavailableError as exc:
        raise _private_not_found() from exc
    except ResearchPlanStorageError as exc:
        raise _private_unavailable() from exc
    except (ResearchPlanError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc), headers=_PRIVATE) from exc


@multimedia_research_plan_router.post(
    "/research-plans/{plan_id}/edits", response_model=ResearchPlanResponse
)
def edit_multimedia_research_plan(
    plan_id: str,
    body: ResearchPlanEditBody,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: ResearchPlanRouteRuntime = Depends(get_multimedia_research_plan_runtime),
) -> ResearchPlanResponse:
    try:
        return _response(runtime.plans.edit(
            owner_identity_digest=runtime.owner_digest_resolver(operator_id),
            plan_id=plan_id,
            idempotency_key=body.idempotency_key,
            expected_plan_version=body.expected_plan_version,
            operations=[operation.model_dump() for operation in body.operations],
        ))
    except ResearchPlanUnavailableError as exc:
        raise _private_not_found() from exc
    except ResearchPlanTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc), headers=_PRIVATE) from exc
    except ResearchPlanValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc), headers=_PRIVATE) from exc
    except ResearchPlanStorageError as exc:
        raise _private_unavailable() from exc
    except (ResearchPlanError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc), headers=_PRIVATE) from exc


@multimedia_research_plan_router.post(
    "/research-plans/{plan_id}/investigation", response_model=PreparedInvestigationResponse
)
def prepare_multimedia_investigation(
    plan_id: str,
    body: PreparedInvestigationBody,
    response: Response,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: ResearchPlanRouteRuntime = Depends(get_multimedia_research_plan_runtime),
) -> PreparedInvestigationResponse:
    try:
        prepared, created = runtime.plans.prepare_investigation(
            owner_identity_digest=runtime.owner_digest_resolver(operator_id), plan_id=plan_id,
            idempotency_key=body.idempotency_key,
            expected_plan_version=body.expected_plan_version,
        )
    except ResearchPlanUnavailableError as exc:
        raise _private_investigation_not_found() from exc
    except ResearchPlanTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc), headers=_PRIVATE) from exc
    except ResearchPlanStorageError as exc:
        raise _private_unavailable() from exc
    except (ResearchPlanError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc), headers=_PRIVATE) from exc
    response.status_code = 201 if created else 200
    return _prepared_response(prepared)


@multimedia_research_plan_router.get(
    "/investigations/{investigation_id}", response_model=PreparedInvestigationResponse
)
def get_multimedia_prepared_investigation(
    investigation_id: str,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: ResearchPlanRouteRuntime = Depends(get_multimedia_research_plan_runtime),
) -> PreparedInvestigationResponse:
    try:
        return _prepared_response(runtime.plans.get_prepared_investigation(
            owner_identity_digest=runtime.owner_digest_resolver(operator_id),
            investigation_id=investigation_id,
        ))
    except ResearchPlanUnavailableError as exc:
        raise _private_investigation_not_found() from exc
    except ResearchPlanStorageError as exc:
        raise _private_unavailable() from exc
    except (ResearchPlanError, ValueError) as exc:
        raise HTTPException(
            status_code=409, detail="prepared investigation integrity conflicts", headers=_PRIVATE
        ) from exc


@multimedia_research_plan_router.post(
    "/investigations/{investigation_id}/activation-authorizations",
    response_model=InvestigationActivationAuthorizationResponse,
)
def authorize_multimedia_investigation_activation(
    investigation_id: str,
    body: InvestigationActivationAuthorizationBody,
    response: Response,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: ResearchPlanRouteRuntime = Depends(get_multimedia_research_plan_runtime),
) -> InvestigationActivationAuthorizationResponse:
    try:
        owner = runtime.owner_digest_resolver(operator_id)
        def resolve_quote(
            prepared: PreparedInvestigation, route_policy: str,
        ) -> InvestigationActivationQuote:
            if runtime.activation_quote_resolver is None:
                raise HTTPException(
                    status_code=503, detail="activation quote authority is unavailable",
                    headers=_PRIVATE,
                )
            try:
                quote = runtime.activation_quote_resolver(prepared, route_policy)
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=503, detail="activation quote authority is unavailable",
                    headers=_PRIVATE,
                ) from exc
            if not isinstance(quote, InvestigationActivationQuote):
                raise HTTPException(
                    status_code=503, detail="activation quote authority is unavailable",
                    headers=_PRIVATE,
                )
            return quote
        authorization, created = runtime.plans.authorize_investigation_activation(
            owner_identity_digest=owner, investigation_id=investigation_id,
            idempotency_key=body.idempotency_key, route_policy=body.route_policy,
            approved_ceiling_cents=body.approved_ceiling_cents,
            ttl_seconds=body.ttl_seconds, quote_resolver=resolve_quote,
        )
    except ResearchPlanUnavailableError as exc:
        raise _private_investigation_not_found() from exc
    except ResearchPlanValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc), headers=_PRIVATE) from exc
    except ResearchPlanStorageError as exc:
        raise _private_unavailable() from exc
    except ResearchPlanError as exc:
        raise HTTPException(status_code=409, detail=str(exc), headers=_PRIVATE) from exc
    response.status_code = 201 if created else 200
    return _authorization_response(authorization)


@multimedia_research_plan_router.get(
    "/investigations/{investigation_id}/activation-authorization",
    response_model=InvestigationActivationAuthorizationResponse,
)
def get_multimedia_investigation_activation_authorization(
    investigation_id: str,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: ResearchPlanRouteRuntime = Depends(get_multimedia_research_plan_runtime),
) -> InvestigationActivationAuthorizationResponse:
    try:
        authorization = runtime.plans.get_investigation_activation_authorization(
            owner_identity_digest=runtime.owner_digest_resolver(operator_id),
            investigation_id=investigation_id,
        )
        return _authorization_response(authorization)
    except ResearchPlanUnavailableError as exc:
        raise _private_investigation_not_found() from exc
    except ResearchPlanStorageError as exc:
        raise _private_unavailable() from exc
    except ResearchPlanError as exc:
        raise HTTPException(
            status_code=409, detail="activation authorization integrity conflicts", headers=_PRIVATE
        ) from exc


def _private_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="research plan is unavailable", headers=_PRIVATE)


def _private_investigation_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="investigation is unavailable", headers=_PRIVATE)


def _private_unavailable() -> HTTPException:
    return HTTPException(
        status_code=500, detail="research plan authority is unavailable", headers=_PRIVATE
    )


def _response(plan: ResearchPlan) -> ResearchPlanResponse:
    payload = asdict(plan)
    payload.pop("approved_by_owner_digest")
    return ResearchPlanResponse(**payload)


def _prepared_response(prepared: PreparedInvestigation) -> PreparedInvestigationResponse:
    payload = asdict(prepared)
    payload.pop("source_plan_integrity_digest")
    return PreparedInvestigationResponse(**payload)


def _authorization_response(
    authorization: InvestigationActivationAuthorization,
) -> InvestigationActivationAuthorizationResponse:
    return InvestigationActivationAuthorizationResponse(
        **asdict(authorization), is_expired=authorization.is_expired
    )


__all__ = [
    "InvestigationActivationAuthorizationBody", "InvestigationActivationAuthorizationResponse",
    "PreparedInvestigationBody", "PreparedInvestigationResponse", "ResearchPlanApproveBody",
    "ResearchPlanEditBody", "ResearchPlanHandoffBody", "ResearchPlanResponse",
    "ResearchPlanRouteRuntime", "get_multimedia_research_plan_runtime",
    "multimedia_research_plan_router",
]
