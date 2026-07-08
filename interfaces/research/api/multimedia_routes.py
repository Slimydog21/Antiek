"""Multimedia REST routes.

Dry-run only: these routes persist/reopen multimedia assets and run deterministic
planner/audio/video/steering/hardening seams without live provider spend.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException

from substrate.multimedia.read_model import (
    CreateMultimediaDraftRequest,
    LiveProviderExecutionRequest,
    MultimediaAssetList,
    MultimediaAssetRecord,
    MultimediaAssetStore,
    MultimediaJobList,
    ProviderExecutionWorkerRequest,
    SteeringRequest,
)

multimedia_router = APIRouter(prefix="/multimedia", tags=["multimedia"])
_STORE = MultimediaAssetStore()


def get_store() -> MultimediaAssetStore:
    return _STORE


@multimedia_router.post("/assets", response_model=MultimediaAssetRecord, status_code=201)
def create_multimedia_asset(request: CreateMultimediaDraftRequest) -> MultimediaAssetRecord:
    return get_store().create_draft(request)


@multimedia_router.get("/assets", response_model=MultimediaAssetList)
def list_multimedia_assets() -> MultimediaAssetList:
    return get_store().list_assets()


@multimedia_router.get("/assets/{asset_id}", response_model=MultimediaAssetRecord)
def get_multimedia_asset(asset_id: str) -> MultimediaAssetRecord:
    try:
        return get_store().get(asset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"multimedia asset {asset_id!r} not found") from exc


@multimedia_router.get("/assets/{asset_id}/jobs", response_model=MultimediaJobList)
def list_multimedia_jobs(asset_id: str) -> MultimediaJobList:
    try:
        return get_store().list_jobs(asset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"multimedia asset {asset_id!r} not found") from exc


@multimedia_router.post("/assets/{asset_id}/approve-dry-run", response_model=MultimediaAssetRecord)
def approve_multimedia_dry_run(asset_id: str) -> MultimediaAssetRecord:
    try:
        return get_store().approve_dry_run(asset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"multimedia asset {asset_id!r} not found") from exc


@multimedia_router.post("/assets/{asset_id}/steer", response_model=MultimediaAssetRecord)
def steer_multimedia_asset(asset_id: str, request: SteeringRequest) -> MultimediaAssetRecord:
    try:
        return get_store().apply_steering(asset_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"multimedia asset {asset_id!r} not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@multimedia_router.post("/assets/{asset_id}/hardening", response_model=MultimediaAssetRecord)
def run_multimedia_hardening(asset_id: str) -> MultimediaAssetRecord:
    try:
        return get_store().run_hardening(asset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"multimedia asset {asset_id!r} not found") from exc


@multimedia_router.post("/assets/{asset_id}/prepare-live-execution", response_model=MultimediaAssetRecord)
def prepare_multimedia_live_execution(
    asset_id: str,
    request: LiveProviderExecutionRequest,
) -> MultimediaAssetRecord:
    try:
        return get_store().prepare_live_execution(asset_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"multimedia asset {asset_id!r} not found") from exc


@multimedia_router.post("/assets/{asset_id}/run-provider-worker", response_model=MultimediaAssetRecord)
def run_multimedia_provider_worker(
    asset_id: str,
    request: ProviderExecutionWorkerRequest | None = None,
) -> MultimediaAssetRecord:
    try:
        return get_store().run_provider_execution_worker(asset_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"multimedia asset {asset_id!r} not found") from exc


def register_multimedia_routes(app: FastAPI) -> None:
    app.include_router(multimedia_router)


__all__ = ["get_store", "multimedia_router", "register_multimedia_routes"]
