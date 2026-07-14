"""Private preparation of research intent from verified audio claims."""

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
    ResearchIntent,
    ResearchIntentError,
    ResearchIntentLedger,
    ResearchIntentUnavailableError,
)
from substrate.multimedia.verified_audio_playback import AudioPlaybackMetadata

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
            response.headers.update(_PRIVATE)
            return response

        return private_handler


class ResearchIntentCreateBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expected_revision_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    line_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    question: str = Field(min_length=3, max_length=2000)
    idempotency_key: str = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class AudioEvidenceSourceResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: str
    document_id: str
    locator: str | None
    authority_kind: Literal["canonical_graph", "operator_excerpt"]
    chunk_sha256: str
    start_utf8_byte: int
    end_utf8_byte: int
    span_sha256: str
    exact_text: str


class ResearchIntentResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    intent_id: str
    state: Literal["prepared"]
    asset_id: str
    revision_id: str
    receipt_sha256: str
    audio_sha256: str
    chapter_id: str
    line_id: str
    question: str
    claim_text: str
    follow_up_prompt: str
    evidence_sources: tuple[AudioEvidenceSourceResponse, ...]
    evidence_digest: str
    request_digest: str
    created_at: str
    plan_handoff_status: Literal["blocked_unowned_plan_store"]
    provider_launch_authorized: Literal[False]
    spend_authority_digest: None
    plan_seed: dict[str, str]


@dataclass(frozen=True)
class ResearchIntentRouteRuntime:
    ledger: ResearchIntentLedger
    owner_digest_resolver: Callable[[str], str]
    audio_authority_resolver: Callable[[str, str, str], AudioPlaybackMetadata]


def get_multimedia_research_intent_runtime() -> ResearchIntentRouteRuntime:
    raise HTTPException(status_code=503, detail="research intent runtime is unavailable", headers=_PRIVATE)


multimedia_research_intent_router = APIRouter(
    tags=["multimedia-research-intent"], route_class=_PrivateNoStoreRoute
)


@multimedia_research_intent_router.post(
    "/assets/{asset_id}/research-intents", response_model=ResearchIntentResponse
)
def create_multimedia_research_intent(
    asset_id: str,
    body: ResearchIntentCreateBody,
    response: Response,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: ResearchIntentRouteRuntime = Depends(get_multimedia_research_intent_runtime),
) -> ResearchIntentResponse:
    try:
        owner_digest = runtime.owner_digest_resolver(operator_id)
        metadata = runtime.audio_authority_resolver(
            asset_id, body.expected_revision_id, operator_id
        )
        if metadata.asset_id != asset_id or metadata.revision_id != body.expected_revision_id:
            raise ResearchIntentError("research intent authority identity conflicts")
        claim = next((row for row in metadata.learned_claims if row.line_id == body.line_id), None)
        if claim is None:
            raise LookupError("claim unavailable")
        if claim.evidence_status != "verified_exact" or not claim.evidence_sources:
            raise ResearchIntentError("exact claim evidence is unavailable")
        intent, created = runtime.ledger.create(
            owner_identity_digest=owner_digest,
            idempotency_key=body.idempotency_key,
            asset_id=asset_id,
            revision_id=body.expected_revision_id,
            receipt_sha256=metadata.receipt_sha256,
            audio_sha256=metadata.audio_sha256,
            question=body.question,
            claim=claim,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="research intent authority is unavailable", headers=_PRIVATE) from exc
    except ResearchIntentError as exc:
        raise HTTPException(status_code=409, detail=str(exc), headers=_PRIVATE) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="research intent authority conflicts", headers=_PRIVATE) from exc
    response.status_code = 201 if created else 200
    response.headers.update(_PRIVATE)
    return _response(intent)


@multimedia_research_intent_router.get(
    "/research-intents/{intent_id}", response_model=ResearchIntentResponse
)
def get_multimedia_research_intent(
    intent_id: str,
    response: Response,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: ResearchIntentRouteRuntime = Depends(get_multimedia_research_intent_runtime),
) -> ResearchIntentResponse:
    try:
        intent = runtime.ledger.get(
            owner_identity_digest=runtime.owner_digest_resolver(operator_id),
            intent_id=intent_id,
        )
    except ResearchIntentUnavailableError as exc:
        raise HTTPException(status_code=404, detail="research intent is unavailable", headers=_PRIVATE) from exc
    except (ResearchIntentError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="research intent integrity conflicts", headers=_PRIVATE) from exc
    response.headers.update(_PRIVATE)
    return _response(intent)


def _response(intent: ResearchIntent) -> ResearchIntentResponse:
    values = asdict(intent)
    values["plan_seed"] = intent.plan_seed
    return ResearchIntentResponse(**values)


__all__ = [
    "ResearchIntentCreateBody", "ResearchIntentResponse", "ResearchIntentRouteRuntime",
    "get_multimedia_research_intent_runtime", "multimedia_research_intent_router",
]
