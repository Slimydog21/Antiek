"""Authenticated private HTTP adapter for canonical advisory twin reading."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict

from runtime.db_lock import connect_read
from substrate.twin_recursion.canonical_reader import (
    CanonicalTwinReader,
    CanonicalTwinReaderNotFound,
)
from substrate.twin_recursion.ledger import TwinRecursionLedger

from .multimedia_reconciliation_routes import authenticated_multimedia_operator

_PRIVATE_HEADERS = {
    "Cache-Control": "private, no-store",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
}


class CanonicalTwinReaderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: str
    source_asset_id: str
    source_hash: str
    title: str
    html_fragment: str
    authority: str
    authority_label: str
    shareable: bool


@dataclass(frozen=True)
class CanonicalTwinReaderRouteRuntime:
    db_path: str
    ledger: TwinRecursionLedger


def get_canonical_twin_reader_runtime() -> CanonicalTwinReaderRouteRuntime:
    raise HTTPException(status_code=503, detail="canonical twin reader unavailable")


class _PrivateNoStoreRoute(APIRoute):
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


canonical_twin_reader_router = APIRouter(
    tags=["canonical-twin-reader"], route_class=_PrivateNoStoreRoute
)


def register_canonical_twin_reader_routes(
    app: FastAPI, *, db_path: str, ledger_path: str | None
) -> None:
    """Mount the route and configure it only for an existing canonical ledger."""
    @app.middleware("http")
    async def canonical_twin_private_headers(request, call_next):  # type: ignore[no-untyped-def]
        result = await call_next(request)
        if request.url.path.startswith("/reader/sources/"):
            result.headers.update(_PRIVATE_HEADERS)
        return result

    app.include_router(canonical_twin_reader_router)
    if ledger_path is None or not ledger_path.strip():
        return
    resolved = Path(ledger_path).expanduser()
    if not resolved.is_file():
        raise RuntimeError("configured canonical twin ledger does not exist")
    runtime = CanonicalTwinReaderRouteRuntime(
        db_path, TwinRecursionLedger.open_read_only(resolved)
    )
    app.dependency_overrides[get_canonical_twin_reader_runtime] = lambda: runtime


@canonical_twin_reader_router.get(
    "/reader/sources/{source_asset_id}/canonical-twin",
    response_model=CanonicalTwinReaderResponse,
)
def read_canonical_twin(
    source_asset_id: str,
    response: Response,
    source_hash: str = Query(min_length=1, max_length=512),
    owner_id: str = Depends(authenticated_multimedia_operator),
    runtime: CanonicalTwinReaderRouteRuntime = Depends(get_canonical_twin_reader_runtime),
) -> CanonicalTwinReaderResponse:
    try:
        with connect_read(runtime.db_path) as con:
            view = CanonicalTwinReader(con, runtime.ledger).read_by_source(
                owner_id=owner_id,
                source_asset_id=source_asset_id,
                source_hash=source_hash,
            )
    except (CanonicalTwinReaderNotFound, ValueError) as exc:
        raise HTTPException(status_code=404, detail="canonical twin not found") from exc
    response.headers.update(_PRIVATE_HEADERS)
    return CanonicalTwinReaderResponse.model_validate(view.__dict__)


__all__ = [
    "CanonicalTwinReaderResponse",
    "CanonicalTwinReaderRouteRuntime",
    "canonical_twin_reader_router",
    "get_canonical_twin_reader_runtime",
    "register_canonical_twin_reader_routes",
]
