"""Authenticated owner-only HTTP projection of current reviewed twin promotions."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field

from runtime.db_lock import connect_authority_read
from substrate.twin_recursion.current_citations import (
    CurrentCanonicalTwinNodeCitations,
    read_current_canonical_twin_node_citations,
)
from substrate.twin_recursion.read_routes import (
    CurrentTwinPromotionReadRegistry,
    CurrentTwinPromotionReadUnavailable,
)

from .canonical_twin_embedding_routes import authenticated_canonical_embedding_operator

_PRIVATE_HEADERS = {
    "Cache-Control": "private, no-store",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
}


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


class _Response(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CurrentNodeResponse(_Response):
    node_id: str
    candidate_id: str
    review_id: str
    kind: str
    text: str
    owner_id: str
    status: str
    authority: str


class CurrentCitationResponse(_Response):
    citation_id: str
    node_id: str
    owner_id: str
    candidate_id: str
    candidate_digest: str
    review_id: str
    ordinal: int
    citation_kind: str
    document_id: str
    chunk_id: str
    range_start: int | None
    range_end: int | None
    text_sha256: str
    chunk_sha256: str
    document_sha256: str | None
    source_envelope_sha256: str | None
    content_class: str | None
    citation_schema: str = Field(alias="schema")


class CurrentPromotionResponse(_Response):
    node: CurrentNodeResponse
    citations: tuple[CurrentCitationResponse, ...]
    status: str
    authority: str


@dataclass(frozen=True)
class CurrentTwinPromotionRouteRuntime:
    registry: CurrentTwinPromotionReadRegistry

    def __post_init__(self) -> None:
        if type(self.registry) is not CurrentTwinPromotionReadRegistry:
            raise TypeError("route runtime requires the exact read registry")


def get_current_twin_promotion_runtime() -> CurrentTwinPromotionRouteRuntime:
    raise HTTPException(status_code=503, detail="current twin promotion unavailable")


current_twin_promotion_router = APIRouter(
    tags=["current-twin-promotion"], route_class=_PrivateRoute
)


def register_current_twin_promotion_routes(
    app: FastAPI, *, runtime: CurrentTwinPromotionRouteRuntime | None = None
) -> None:
    @app.middleware("http")
    async def current_promotion_private_headers(request, call_next):  # type: ignore[no-untyped-def]
        result = await call_next(request)
        if request.url.path == "/reader/promotions" or request.url.path.startswith(
            "/reader/promotions/"
        ):
            result.headers.update(_PRIVATE_HEADERS)
        return result

    app.include_router(current_twin_promotion_router)
    if runtime is not None:
        app.dependency_overrides[get_current_twin_promotion_runtime] = lambda: runtime


@current_twin_promotion_router.get(
    "/reader/promotions/{candidate_id}", response_model=CurrentPromotionResponse
)
def read_current_twin_promotion(
    candidate_id: str,
    response: Response,
    owner_id: str = Depends(authenticated_canonical_embedding_operator),
    runtime: CurrentTwinPromotionRouteRuntime = Depends(get_current_twin_promotion_runtime),
) -> CurrentPromotionResponse:
    try:
        route = runtime.registry.resolve(owner_id)
        promotions, twins = route.open_readers()
        with connect_authority_read(
            route.graph_db_path,
            expected_db_identity=route.graph_identity,
            expected_lock_identity=route.lock_identity,
        ) as con:
            route.require_current()
            view = read_current_canonical_twin_node_citations(
                con,
                promotions,
                twins,
                owner_id=owner_id,
                candidate_id=candidate_id,
            )
            route.require_current()
    except CurrentTwinPromotionReadUnavailable as exc:
        raise HTTPException(status_code=404, detail="current twin promotion not found") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="current twin promotion unavailable") from exc
    if type(view) is not CurrentCanonicalTwinNodeCitations:
        raise HTTPException(status_code=404, detail="current twin promotion not found")
    response.headers.update(_PRIVATE_HEADERS)
    result: CurrentPromotionResponse = CurrentPromotionResponse.model_validate(
        view, from_attributes=True
    )
    return result


__all__ = [
    "CurrentCitationResponse",
    "CurrentNodeResponse",
    "CurrentPromotionResponse",
    "CurrentTwinPromotionRouteRuntime",
    "current_twin_promotion_router",
    "get_current_twin_promotion_runtime",
    "read_current_twin_promotion",
    "register_current_twin_promotion_routes",
]
