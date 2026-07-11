"""Multimedia REST routes.

Dry-run only: these routes persist/reopen multimedia assets and run deterministic
planner/audio/video/steering/hardening seams without live provider spend.
"""

from __future__ import annotations

import os
from dataclasses import replace

from fastapi import APIRouter, Depends, FastAPI, HTTPException

from substrate.multimedia.read_model import (
    CreateMultimediaDraftRequest,
    LiveProviderExecutionRequest,
    MultimediaAssetList,
    MultimediaAssetRecord,
    MultimediaAssetStore,
    MultimediaJobList,
    SteeringRequest,
)

from .multimedia_reconciliation_routes import (
    authenticated_multimedia_operator,
    get_multimedia_reconciliation_runtime,
    multimedia_reconciliation_router,
    multimedia_reconciliation_runtime_from_environment,
)

multimedia_router = APIRouter(prefix="/multimedia", tags=["multimedia"])
multimedia_router.include_router(multimedia_reconciliation_router)
_STORE = MultimediaAssetStore()


def get_store() -> MultimediaAssetStore:
    return _STORE


@multimedia_router.post("/assets", response_model=MultimediaAssetRecord, status_code=201)
def create_multimedia_asset(
    request: CreateMultimediaDraftRequest,
    operator_id: str = Depends(authenticated_multimedia_operator),
) -> MultimediaAssetRecord:
    return get_store().create_draft(request, owner_id=operator_id)


@multimedia_router.get("/assets", response_model=MultimediaAssetList)
def list_multimedia_assets(
    operator_id: str = Depends(authenticated_multimedia_operator),
) -> MultimediaAssetList:
    return get_store().list_assets(owner_id=operator_id)


@multimedia_router.get("/assets/{asset_id}", response_model=MultimediaAssetRecord)
def get_multimedia_asset(
    asset_id: str,
    operator_id: str = Depends(authenticated_multimedia_operator),
) -> MultimediaAssetRecord:
    try:
        return get_store().get(asset_id, owner_id=operator_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="multimedia asset not found") from exc


@multimedia_router.get("/assets/{asset_id}/jobs", response_model=MultimediaJobList)
def list_multimedia_jobs(
    asset_id: str,
    operator_id: str = Depends(authenticated_multimedia_operator),
) -> MultimediaJobList:
    try:
        return get_store().list_jobs(asset_id, owner_id=operator_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="multimedia asset not found") from exc


@multimedia_router.post("/assets/{asset_id}/approve-dry-run", response_model=MultimediaAssetRecord)
def approve_multimedia_dry_run(
    asset_id: str,
    operator_id: str = Depends(authenticated_multimedia_operator),
) -> MultimediaAssetRecord:
    try:
        return get_store().approve_dry_run(asset_id, owner_id=operator_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="multimedia asset not found") from exc


@multimedia_router.post("/assets/{asset_id}/steer", response_model=MultimediaAssetRecord)
def steer_multimedia_asset(
    asset_id: str,
    request: SteeringRequest,
    operator_id: str = Depends(authenticated_multimedia_operator),
) -> MultimediaAssetRecord:
    try:
        return get_store().apply_steering(asset_id, request, owner_id=operator_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="multimedia asset not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@multimedia_router.post("/assets/{asset_id}/hardening", response_model=MultimediaAssetRecord)
def run_multimedia_hardening(
    asset_id: str,
    operator_id: str = Depends(authenticated_multimedia_operator),
) -> MultimediaAssetRecord:
    try:
        return get_store().run_hardening(asset_id, owner_id=operator_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="multimedia asset not found") from exc


@multimedia_router.post("/assets/{asset_id}/prepare-live-execution", response_model=MultimediaAssetRecord)
def prepare_multimedia_live_execution(
    asset_id: str,
    request: LiveProviderExecutionRequest,
    operator_id: str = Depends(authenticated_multimedia_operator),
) -> MultimediaAssetRecord:
    try:
        return get_store().prepare_live_execution(asset_id, request, owner_id=operator_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="multimedia asset not found") from exc


def register_multimedia_routes(app: FastAPI) -> None:
    legacy_owner = os.environ.get("ANTIEK_MULTIMEDIA_LEGACY_OWNER_ID", "").strip()
    if legacy_owner:
        get_store().migrate_legacy_assets(owner_id=legacy_owner)
    app.include_router(multimedia_router)
    runtime = multimedia_reconciliation_runtime_from_environment()
    if runtime is not None:
        runtime = replace(
            runtime,
            asset_revision_resolver=lambda asset_id, operator_id: get_store()
            .get(asset_id, owner_id=operator_id)
            .asset.revision_id,
        )
        app.dependency_overrides[get_multimedia_reconciliation_runtime] = lambda: runtime


__all__ = ["get_store", "multimedia_router", "register_multimedia_routes"]
