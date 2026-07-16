"""Authenticated HTTP boundary for server-routed canonical twin embedding."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field

from runtime.db_lock import connect_write
from runtime.research_runner.provider_gateway import (
    DispatchIneligible,
    PaidFallbackOutcomeUnknown,
    deterministic_key,
)
from substrate.research_spend import (
    BindingConflict,
    IdempotencyConflict,
    InvalidTransition,
    LedgerIntegrityError,
    RunBinding,
    SpendCeilingExceeded,
)
from substrate.twin_recursion.canonical_embedding import (
    BudgetedCanonicalTwinEmbedder,
    CanonicalEmbeddingPreview,
    CanonicalTwinEmbeddingError,
)
from substrate.twin_recursion.embedding_routes import (
    CanonicalEmbeddingRouteRegistry,
    CanonicalEmbeddingRouteUnavailable,
)

_PRIVATE_HEADERS = {
    "Cache-Control": "private, no-store",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
}
_EMBEDDING_AUTH_METHODS = frozenset({"antiek_session_cookie", "bearer_token"})


class _PrivateRoute(APIRoute):
    def get_route_handler(self):  # type: ignore[no-untyped-def]
        handler = super().get_route_handler()

        async def private_handler(request):  # type: ignore[no-untyped-def]
            try:
                result = await handler(request)
            except RequestValidationError as exc:
                return JSONResponse(
                    status_code=422,
                    content={"detail": jsonable_encoder(exc.errors())},
                    headers=_PRIVATE_HEADERS,
                )
            except HTTPException as exc:
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": jsonable_encoder(exc.detail)},
                    headers={**_PRIVATE_HEADERS, **(exc.headers or {})},
                )
            result.headers.update(_PRIVATE_HEADERS)
            return result

        return private_handler


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmbeddingRunRequest(_Body):
    route_id: str = Field(min_length=1, max_length=128)


class EmbeddingPreviewResponse(_Body):
    operation_digest: str
    chain_id: str
    manifest_sha256: str
    ceiling_cents: int
    currency: str
    maximum_chain_exposure_cents: int


class EmbeddingApprovalRequest(EmbeddingRunRequest):
    preview: EmbeddingPreviewResponse


class EmbeddingApprovalResponse(_Body):
    approval_id: str
    operation_digest: str


class EmbeddingExecutionRequest(EmbeddingRunRequest):
    approval_id: str = Field(min_length=1, max_length=512)


class EmbeddingExecutionResponse(_Body):
    document_id: str
    chunk_id: str
    vector_sha256: str
    hold_id: str
    actual_cents: int
    replayed: bool


@dataclass(frozen=True)
class CanonicalTwinEmbeddingRunAuthority:
    owner_id: str
    source_asset_id: str
    source_hash: str
    route_id: str
    binding: RunBinding
    ceiling_cents: int


@dataclass(frozen=True)
class CanonicalTwinEmbeddingRouteRuntime:
    db_path: str
    embedder: BudgetedCanonicalTwinEmbedder
    registry: CanonicalEmbeddingRouteRegistry
    run_authority_resolver: Callable[[str, str, str, str], CanonicalTwinEmbeddingRunAuthority]


def get_canonical_twin_embedding_runtime() -> CanonicalTwinEmbeddingRouteRuntime:
    raise HTTPException(status_code=503, detail="canonical twin embedding unavailable")


canonical_twin_embedding_router = APIRouter(
    tags=["canonical-twin-embedding"], route_class=_PrivateRoute
)


def authenticated_canonical_embedding_operator(request: Request) -> str:
    method = getattr(request.state, "auth_method", None)
    owner_id = getattr(request.state, "user_id", None)
    if method not in _EMBEDDING_AUTH_METHODS or not isinstance(owner_id, str):
        raise HTTPException(status_code=401, detail="authentication required")
    owner_id = owner_id.strip()
    if not owner_id:
        raise HTTPException(status_code=401, detail="authentication required")
    return owner_id


def register_canonical_twin_embedding_routes(
    app: FastAPI, *, runtime: CanonicalTwinEmbeddingRouteRuntime | None = None
) -> None:
    @app.middleware("http")
    async def canonical_embedding_private_headers(request, call_next):  # type: ignore[no-untyped-def]
        result = await call_next(request)
        if "/canonical-twin/embedding" in request.url.path:
            result.headers.update(_PRIVATE_HEADERS)
        return result

    app.include_router(canonical_twin_embedding_router)
    if runtime is not None:
        app.dependency_overrides[get_canonical_twin_embedding_runtime] = lambda: runtime


def _binding(
    runtime: CanonicalTwinEmbeddingRouteRuntime,
    owner_id: str,
    source_asset_id: str,
    source_hash: str,
    body: EmbeddingRunRequest,
) -> tuple[RunBinding, int]:
    try:
        authority = runtime.run_authority_resolver(
            owner_id, source_asset_id, source_hash, body.route_id
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="canonical twin embedding unavailable") from exc
    if (
        type(authority) is not CanonicalTwinEmbeddingRunAuthority
        or authority.owner_id != owner_id
        or authority.source_asset_id != source_asset_id
        or authority.source_hash != source_hash
        or authority.route_id != body.route_id
        or type(authority.binding) is not RunBinding
        or authority.binding.owner_id != owner_id
        or isinstance(authority.ceiling_cents, bool)
        or not isinstance(authority.ceiling_cents, int)
        or not 1 <= authority.ceiling_cents <= 9_223_372_036_854_775_807
    ):
        raise HTTPException(status_code=503, detail="canonical twin embedding unavailable")
    return authority.binding, authority.ceiling_cents


def _resolve(runtime: CanonicalTwinEmbeddingRouteRuntime, route_id: str):  # type: ignore[no-untyped-def]
    try:
        return runtime.registry.resolve(route_id)
    except CanonicalEmbeddingRouteUnavailable as exc:
        raise HTTPException(status_code=503, detail="canonical twin embedding unavailable") from exc


def _ensure_run(
    runtime: CanonicalTwinEmbeddingRouteRuntime,
    binding: RunBinding,
    ceiling_cents: int,
) -> None:
    try:
        runtime.embedder.gateway.create_or_reopen_run(binding, ceiling_cents=ceiling_cents)
    except LedgerIntegrityError as exc:
        raise HTTPException(status_code=503, detail="canonical twin embedding unavailable") from exc
    except (
        BindingConflict,
        IdempotencyConflict,
        InvalidTransition,
        SpendCeilingExceeded,
    ) as exc:
        raise HTTPException(status_code=409, detail="embedding run authority changed") from exc


def _prepare(
    *,
    runtime: CanonicalTwinEmbeddingRouteRuntime,
    owner_id: str,
    source_asset_id: str,
    source_hash: str,
    body: EmbeddingRunRequest,
) -> tuple[CanonicalEmbeddingPreview, RunBinding]:
    route = _resolve(runtime, body.route_id)
    binding, ceiling_cents = _binding(runtime, owner_id, source_asset_id, source_hash, body)
    _ensure_run(runtime, binding, ceiling_cents)
    try:
        with connect_write(runtime.db_path, purpose="canonical_twin_embedding_preview") as con:
            preview = runtime.embedder.prepare(
                con,
                binding=binding,
                source_asset_id=source_asset_id,
                source_hash=source_hash,
                projection_request=route.projection_request,
                adapter=route.adapter,
            )
            return preview, binding
    except CanonicalTwinEmbeddingError as exc:
        raise HTTPException(status_code=404, detail="canonical twin unavailable") from exc
    except DispatchIneligible as exc:
        raise HTTPException(status_code=409, detail="embedding preview refused") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="canonical twin embedding unavailable") from exc


def _response(preview: CanonicalEmbeddingPreview) -> EmbeddingPreviewResponse:
    value = preview.preparation
    return EmbeddingPreviewResponse(
        operation_digest=preview.operation_digest,
        chain_id=value.chain_id,
        manifest_sha256=value.manifest_sha256,
        ceiling_cents=value.ceiling_cents,
        currency=value.currency,
        maximum_chain_exposure_cents=value.maximum_chain_exposure_cents,
    )


@canonical_twin_embedding_router.post(
    "/reader/sources/{source_asset_id}/canonical-twin/embedding/preview",
    response_model=EmbeddingPreviewResponse,
)
def preview_canonical_twin_embedding(
    source_asset_id: str,
    body: EmbeddingRunRequest,
    response: Response,
    source_hash: str = Query(min_length=1, max_length=512),
    owner_id: str = Depends(authenticated_canonical_embedding_operator),
    runtime: CanonicalTwinEmbeddingRouteRuntime = Depends(get_canonical_twin_embedding_runtime),
) -> EmbeddingPreviewResponse:
    preview, _ = _prepare(
        runtime=runtime,
        owner_id=owner_id,
        source_asset_id=source_asset_id,
        source_hash=source_hash,
        body=body,
    )
    response.headers.update(_PRIVATE_HEADERS)
    return _response(preview)


@canonical_twin_embedding_router.post(
    "/reader/sources/{source_asset_id}/canonical-twin/embedding/approve",
    response_model=EmbeddingApprovalResponse,
)
def approve_canonical_twin_embedding(
    source_asset_id: str,
    body: EmbeddingApprovalRequest,
    response: Response,
    source_hash: str = Query(min_length=1, max_length=512),
    owner_id: str = Depends(authenticated_canonical_embedding_operator),
    runtime: CanonicalTwinEmbeddingRouteRuntime = Depends(get_canonical_twin_embedding_runtime),
) -> EmbeddingApprovalResponse:
    current, binding = _prepare(
        runtime=runtime,
        owner_id=owner_id,
        source_asset_id=source_asset_id,
        source_hash=source_hash,
        body=body,
    )
    supplied = body.preview
    if _response(current) != supplied:
        raise HTTPException(status_code=409, detail="embedding preview changed")
    command_key = deterministic_key(
        "canonical-embedding-approval", binding.run_id, current.operation_digest
    )
    try:
        approval = runtime.embedder.approve(
            command_key=command_key, binding=binding, preview=current
        )
    except (CanonicalTwinEmbeddingError, DispatchIneligible) as exc:
        raise HTTPException(status_code=409, detail="embedding preview changed") from exc
    response.headers.update(_PRIVATE_HEADERS)
    return EmbeddingApprovalResponse(
        approval_id=approval.approval_id,
        operation_digest=current.operation_digest,
    )


@canonical_twin_embedding_router.post(
    "/reader/sources/{source_asset_id}/canonical-twin/embedding/execute",
    response_model=EmbeddingExecutionResponse,
)
def execute_canonical_twin_embedding(
    source_asset_id: str,
    body: EmbeddingExecutionRequest,
    response: Response,
    source_hash: str = Query(min_length=1, max_length=512),
    owner_id: str = Depends(authenticated_canonical_embedding_operator),
    runtime: CanonicalTwinEmbeddingRouteRuntime = Depends(get_canonical_twin_embedding_runtime),
) -> EmbeddingExecutionResponse:
    route = _resolve(runtime, body.route_id)
    binding, ceiling_cents = _binding(runtime, owner_id, source_asset_id, source_hash, body)
    _ensure_run(runtime, binding, ceiling_cents)
    try:
        with connect_write(runtime.db_path, purpose="canonical_twin_embedding_execute") as con:
            result = runtime.embedder.embed(
                con,
                binding=binding,
                source_asset_id=source_asset_id,
                source_hash=source_hash,
                projection_request=route.projection_request,
                adapter=route.adapter,
                approval_id=body.approval_id,
            )
    except PaidFallbackOutcomeUnknown as exc:
        raise HTTPException(status_code=409, detail="embedding reconciliation pending") from exc
    except (CanonicalTwinEmbeddingError, DispatchIneligible) as exc:
        raise HTTPException(status_code=409, detail="embedding execution refused") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="canonical twin embedding unavailable") from exc
    response.headers.update(_PRIVATE_HEADERS)
    return EmbeddingExecutionResponse.model_validate(result.__dict__)


__all__ = [
    "CanonicalTwinEmbeddingRunAuthority",
    "CanonicalTwinEmbeddingRouteRuntime",
    "EmbeddingApprovalRequest",
    "EmbeddingApprovalResponse",
    "EmbeddingExecutionRequest",
    "EmbeddingExecutionResponse",
    "EmbeddingPreviewResponse",
    "EmbeddingRunRequest",
    "authenticated_canonical_embedding_operator",
    "canonical_twin_embedding_router",
    "get_canonical_twin_embedding_runtime",
    "register_canonical_twin_embedding_routes",
]
