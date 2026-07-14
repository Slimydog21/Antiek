"""Owner-private multimedia research-plan handoff and approval routes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Literal

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
    ResearchPlan,
    ResearchPlanError,
    ResearchPlanLedger,
    ResearchPlanStorageError,
    ResearchPlanUnavailableError,
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


class ResearchPlanRootResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["research_question"]
    question: str
    source_intent_id: str
    source_intent_digest: str
    source_evidence_digest: str
    children: tuple[()]


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
    approved_by_owner_digest: str | None
    research_launched: Literal[False]
    provider_launch_authorized: Literal[False]
    spend_authority_digest: None


@dataclass(frozen=True)
class ResearchPlanRouteRuntime:
    plans: ResearchPlanLedger
    intents: ResearchIntentLedger
    owner_digest_resolver: Callable[[str], str]


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


def _private_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="research plan is unavailable", headers=_PRIVATE)


def _private_unavailable() -> HTTPException:
    return HTTPException(
        status_code=500, detail="research plan authority is unavailable", headers=_PRIVATE
    )


def _response(plan: ResearchPlan) -> ResearchPlanResponse:
    return ResearchPlanResponse(**asdict(plan))


__all__ = [
    "ResearchPlanApproveBody", "ResearchPlanHandoffBody", "ResearchPlanResponse",
    "ResearchPlanRouteRuntime", "get_multimedia_research_plan_runtime",
    "multimedia_research_plan_router",
]
