"""Authenticated listening progress GET/PUT routes for multimedia audio."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from substrate.multimedia.listening_progress import (
    AudioIdentity,
    ListeningProgressCheckpointRequest,
    ListeningProgressError,
    ListeningProgressIntegrityConflict,
    ListeningProgressProjection,
    ListeningProgressStore,
)

from .multimedia_reconciliation_routes import authenticated_multimedia_operator


@dataclass(frozen=True)
class ListeningProgressRouteRuntime:
    store: ListeningProgressStore
    audio_identity_resolver: Callable[[str, str], AudioIdentity]


_NO_STORE_HEADERS = {
    "Cache-Control": "private, no-store",
    "X-Content-Type-Options": "nosniff",
}


def get_listening_progress_runtime() -> ListeningProgressRouteRuntime:
    raise HTTPException(status_code=503, detail="listening progress is unavailable")


def listening_progress_runtime(
    store: ListeningProgressStore,
    *,
    audio_identity_resolver: Callable[[str, str], AudioIdentity],
) -> ListeningProgressRouteRuntime:
    return ListeningProgressRouteRuntime(
        store=store,
        audio_identity_resolver=audio_identity_resolver,
    )


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
                    headers=_NO_STORE_HEADERS,
                )
            except HTTPException as exc:
                headers = {**_NO_STORE_HEADERS, **(exc.headers or {})}
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": jsonable_encoder(exc.detail)},
                    headers=headers,
                )
            result.headers.update(_NO_STORE_HEADERS)
            return result

        return private_handler


multimedia_listening_progress_router = APIRouter(
    tags=["multimedia-listening-progress"], route_class=_PrivateNoStoreRoute
)


@multimedia_listening_progress_router.get(
    "/assets/{asset_id}/listening-progress",
    response_model=ListeningProgressProjection,
)
def get_listening_progress(
    asset_id: str,
    revision_id: str,
    response: Response,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: ListeningProgressRouteRuntime = Depends(get_listening_progress_runtime),
) -> ListeningProgressProjection:
    try:
        audio_identity = runtime.audio_identity_resolver(asset_id, operator_id)
    except (KeyError, LookupError, ValueError) as exc:
        raise HTTPException(
            status_code=404, detail="multimedia asset not found"
        ) from exc
    try:
        projection = runtime.store.read(
            asset_id,
            owner_id=operator_id,
            revision_id=revision_id,
            audio_identity=audio_identity,
        )
    except ListeningProgressIntegrityConflict as exc:
        raise HTTPException(status_code=409, detail=exc.code) from exc
    except ListeningProgressError as exc:
        status = 404 if "not_audio" in exc.code else 409
        raise HTTPException(status_code=status, detail=exc.code) from exc
    response.headers.update(_NO_STORE_HEADERS)
    return projection


@multimedia_listening_progress_router.put(
    "/assets/{asset_id}/listening-progress",
    response_model=ListeningProgressProjection,
)
def put_listening_progress(
    asset_id: str,
    body: ListeningProgressCheckpointRequest,
    response: Response,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: ListeningProgressRouteRuntime = Depends(get_listening_progress_runtime),
) -> ListeningProgressProjection:
    try:
        audio_identity = runtime.audio_identity_resolver(asset_id, operator_id)
    except (KeyError, LookupError, ValueError) as exc:
        raise HTTPException(
            status_code=404, detail="multimedia asset not found"
        ) from exc
    try:
        projection = runtime.store.checkpoint(
            asset_id,
            body,
            owner_id=operator_id,
            audio_identity=audio_identity,
        )
    except ListeningProgressIntegrityConflict as exc:
        raise HTTPException(status_code=409, detail=exc.code) from exc
    except ListeningProgressError as exc:
        status = 404 if "not_audio" in exc.code else 409
        raise HTTPException(status_code=status, detail=exc.code) from exc
    response.headers.update(_NO_STORE_HEADERS)
    return projection


__all__ = [
    "ListeningProgressRouteRuntime",
    "get_listening_progress_runtime",
    "listening_progress_runtime",
    "multimedia_listening_progress_router",
]
