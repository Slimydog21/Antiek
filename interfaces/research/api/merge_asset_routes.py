"""ID-only authenticated API for canonical merge drafts and inert previews."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from substrate.graph import default_db_path
from substrate.graph.schema import init_database_at_path
from substrate.research_artifact.merge_draft import (
    Draft,
    MergeDraftError,
    MergeDraftNotFound,
    MergeDraftRepository,
    Review,
)

from .multimedia_reconciliation_routes import authenticated_multimedia_operator


class CreateMergeDraftBody(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
    projection_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    intent: Literal["create", "revise"]
    title: str = Field(min_length=1, max_length=512)
    asset_kind: Literal["document", "analysis", "synthesis", "composite"]
    target_asset_id: str | None = Field(default=None, min_length=1, max_length=512)
    expected_parent_revision_id: str | None = Field(default=None, min_length=1, max_length=512)
    expected_parent_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class DraftResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    draft_id: str
    canonical_sha256: str
    manifest_sha256: str
    sanitizer_policy: str
    sanitizer_version: str


class ReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    review_id: str
    draft_id: str
    canonical_sha256: str
    manifest_sha256: str
    acknowledgement_version: str


def get_merge_draft_repository() -> MergeDraftRepository:
    projection_root = os.environ.get("ANTIEK_HTML_OBJECT_ROOT", "").strip()
    if not projection_root:
        raise HTTPException(status_code=503, detail="merge draft service is unavailable")
    return MergeDraftRepository(db_path=default_db_path(), projection_root=Path(projection_root))


merge_asset_router = APIRouter(
    prefix="/research/derived-assets/merge", tags=["derived-asset-merge"]
)


@merge_asset_router.post("/drafts", response_model=DraftResponse, status_code=201)
def create_merge_draft(
    body: CreateMergeDraftBody,
    owner_id: str = Depends(authenticated_multimedia_operator),
    repository: MergeDraftRepository = Depends(get_merge_draft_repository),
) -> DraftResponse:
    try:
        draft = repository.create_draft(owner_user_id=owner_id, **body.model_dump())
    except MergeDraftError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _draft_response(draft)


@merge_asset_router.post(
    "/drafts/{draft_id}/reviews", response_model=ReviewResponse, status_code=201
)
def create_merge_review(
    draft_id: str,
    owner_id: str = Depends(authenticated_multimedia_operator),
    repository: MergeDraftRepository = Depends(get_merge_draft_repository),
) -> ReviewResponse:
    try:
        review = repository.create_review(owner_user_id=owner_id, draft_id=draft_id)
    except MergeDraftNotFound as exc:
        raise HTTPException(status_code=404, detail="merge draft not found") from exc
    except MergeDraftError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _review_response(review)


@merge_asset_router.get("/previews/{opaque_id}", response_class=Response)
def preview_merge_draft(
    opaque_id: str,
    owner_id: str = Depends(authenticated_multimedia_operator),
    repository: MergeDraftRepository = Depends(get_merge_draft_repository),
) -> Response:
    try:
        draft = repository.load_preview(owner_user_id=owner_id, opaque_id=opaque_id)
    except MergeDraftNotFound as exc:
        raise HTTPException(status_code=404, detail="merge preview not found") from exc
    except MergeDraftError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(
        content=draft.canonical_html.encode("utf-8"),
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Security-Policy": (
                "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; "
                "form-action 'none'; sandbox"
            ),
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
        },
    )


def _draft_response(draft: Draft) -> DraftResponse:
    return DraftResponse(
        draft_id=draft.draft_id,
        canonical_sha256=draft.canonical_sha256,
        manifest_sha256=draft.manifest_sha256,
        sanitizer_policy=draft.sanitizer_policy,
        sanitizer_version=draft.sanitizer_version,
    )


def _review_response(review: Review) -> ReviewResponse:
    return ReviewResponse(
        review_id=review.review_id,
        draft_id=review.draft_id,
        canonical_sha256=review.canonical_sha256,
        manifest_sha256=review.manifest_sha256,
        acknowledgement_version=review.acknowledgement_version,
    )


def register_merge_asset_routes(app: object) -> None:
    from fastapi import FastAPI

    if not isinstance(app, FastAPI):
        raise TypeError("app must be FastAPI")
    app.router.on_startup.append(_initialize_merge_schema)
    app.include_router(merge_asset_router)


def _initialize_merge_schema() -> None:
    """Apply V17 during process startup, never inside a request."""
    init_database_at_path(default_db_path())


__all__ = ["get_merge_draft_repository", "merge_asset_router", "register_merge_asset_routes"]
