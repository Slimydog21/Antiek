"""ID-only authenticated API for canonical merge drafts and inert previews."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from runtime.research_runner.derived_companion_execution import (
    project_derived_companion_execution,
)
from substrate.graph import default_db_path
from substrate.graph.schema import init_database_at_path
from substrate.research_artifact.derived_asset_library import (
    DerivedAssetIntegrity,
    DerivedAssetLibrary,
    DerivedAssetUnavailable,
)
from substrate.research_artifact.derived_asset_retrieval import (
    DerivedAssetRetrievalIntegrity,
    search_derived_asset,
)
from substrate.research_artifact.derived_citation_source import DerivedCitationConflict
from substrate.research_artifact.derived_companion_repository import (
    CompanionIdempotencyConflict,
    CompanionStaleRevision,
    DerivedCompanionRepository,
)
from substrate.research_artifact.evidence_collection_repository import (
    EvidenceCollectionConflict,
    EvidenceCollectionRepository,
    EvidenceCollectionUnavailable,
)
from substrate.research_artifact.evidence_manifest_repository import (
    EvidenceManifestConflict,
    EvidenceManifestRepository,
    EvidenceManifestUnavailable,
)
from substrate.research_artifact.merge_commit import (
    MergeCommitError,
    MergeCommitNotFound,
    MergeCommitResult,
    apply_review,
    restore,
)
from substrate.research_artifact.merge_draft import (
    Draft,
    MergeDraftError,
    MergeDraftNotFound,
    MergeDraftRepository,
    Review,
)
from substrate.schemas import DerivedCitationSource

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
    projection_ids: tuple[str, ...]


class ReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    review_id: str
    draft_id: str
    canonical_sha256: str
    manifest_sha256: str
    acknowledgement_version: str


class ApplyReviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operation_id: str = Field(pattern=r"^op_[0-9a-f]{32}$")
    expected_generation: int | None = Field(default=None, ge=1)


class RestoreAssetBody(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operation_id: str = Field(pattern=r"^op_[0-9a-f]{32}$")
    selected_revision_id: str = Field(pattern=r"^rev_[0-9a-f]{32}$")
    expected_revision_id: str = Field(pattern=r"^rev_[0-9a-f]{32}$")
    expected_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_generation: int = Field(ge=1)


class DerivedAssetSearchBody(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
    query: str = Field(min_length=1, max_length=8000)
    top_k: int = Field(default=6, ge=1, le=12)


class DerivedCompanionEvidenceBody(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
    client_turn_id: str = Field(min_length=8, max_length=128)
    question: str = Field(min_length=1, max_length=8000)
    expected_revision_id: str | None = Field(default=None, pattern=r"^rev_[0-9a-f]{32}$")
    expected_content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class EvidenceCollectionCreateBody(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
    label: str = Field(min_length=1, max_length=512)
    sources: tuple[DerivedCitationSource, ...] = Field(min_length=2, max_length=6)


class EvidenceCollectionLaunchBody(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
    question: str = Field(min_length=3, max_length=8000)
    topic_slug: str | None = Field(default=None, max_length=512)
    max_sub_questions: int = Field(default=8, ge=1, le=20)
    parent_investigation_id: str | None = Field(default=None, max_length=512)
    research_tier: Literal["fast", "deep"] | None = None


class EvidenceManifestCreateBody(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
    label: str = Field(min_length=1, max_length=512)
    collection_ids: tuple[str, ...] = Field(min_length=2, max_length=8)


class EvidenceManifestLaunchBody(EvidenceCollectionLaunchBody):
    pass


class MergeCommitResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operation_id: str
    derived_asset_id: str
    revision_id: str
    content_sha256: str
    generation: int
    replayed: bool


def get_merge_draft_repository() -> MergeDraftRepository:
    projection_root = os.environ.get("ANTIEK_HTML_OBJECT_ROOT", "").strip()
    if not projection_root:
        raise HTTPException(status_code=503, detail="merge draft service is unavailable")
    return MergeDraftRepository(db_path=default_db_path(), projection_root=Path(projection_root))


merge_asset_router = APIRouter(
    prefix="/research/derived-assets/merge", tags=["derived-asset-merge"]
)
derived_asset_router = APIRouter(prefix="/research/derived-assets", tags=["derived-assets"])

NO_STORE = {"Cache-Control": "private, no-store"}
FRAME_HEADERS = {
    **NO_STORE,
    "Content-Security-Policy": (
        "default-src 'none'; frame-ancestors 'self'; base-uri 'none'; form-action 'none'; sandbox"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


def _library() -> DerivedAssetLibrary:
    return DerivedAssetLibrary(db_path=default_db_path())


def _library_error(exc: Exception) -> HTTPException:
    if isinstance(exc, DerivedAssetUnavailable):
        return HTTPException(404, "derived asset is unavailable", headers=NO_STORE)
    return HTTPException(409, "derived asset integrity conflict", headers=NO_STORE)


def _collection_repository() -> EvidenceCollectionRepository:
    return EvidenceCollectionRepository(db_path=default_db_path())


def _collection_error(exc: Exception) -> HTTPException:
    if isinstance(exc, EvidenceCollectionUnavailable):
        return HTTPException(404, "evidence collection is unavailable", headers=NO_STORE)
    return HTTPException(409, "evidence collection integrity conflict", headers=NO_STORE)


def _manifest_repository() -> EvidenceManifestRepository:
    return EvidenceManifestRepository(db_path=default_db_path())


def _manifest_error(exc: Exception) -> HTTPException:
    if isinstance(exc, EvidenceManifestUnavailable):
        return HTTPException(404, "evidence manifest is unavailable", headers=NO_STORE)
    return HTTPException(409, "evidence manifest integrity conflict", headers=NO_STORE)


@derived_asset_router.post("/evidence-manifests", status_code=201)
def create_evidence_manifest(
    body: EvidenceManifestCreateBody,
    request: Request,
    owner_id: str = Depends(authenticated_multimedia_operator),
) -> Response:
    key = request.headers.get("Idempotency-Key")
    if key is None:
        raise HTTPException(422, "Idempotency-Key is required", headers=NO_STORE)
    try:
        result = _manifest_repository().create(
            owner_user_id=owner_id, idempotency_key=key, **body.model_dump()
        )
    except (
        EvidenceManifestUnavailable,
        EvidenceManifestConflict,
        EvidenceCollectionUnavailable,
        EvidenceCollectionConflict,
        DerivedAssetUnavailable,
        DerivedAssetIntegrity,
        DerivedAssetRetrievalIntegrity,
        DerivedCitationConflict,
    ) as exc:
        raise _manifest_error(exc) from None
    except ValueError:
        raise HTTPException(422, "evidence manifest request is invalid", headers=NO_STORE) from None
    return Response(
        _canonical_response(result),
        status_code=201,
        media_type="application/json",
        headers={**NO_STORE, "ETag": result["etag"]},
    )


@derived_asset_router.get("/evidence-manifests")
async def list_evidence_manifests(request: Request) -> Response:
    if request.query_params or await request.body():
        raise HTTPException(422, "evidence manifest request is invalid", headers=NO_STORE)
    try:
        result = _manifest_repository().list(
            owner_user_id=authenticated_multimedia_operator(request)
        )
    except EvidenceManifestConflict as exc:
        raise _manifest_error(exc) from None
    return Response(_canonical_response(result), media_type="application/json", headers=NO_STORE)


@derived_asset_router.get("/evidence-manifests/{manifest_id}")
async def read_evidence_manifest(manifest_id: str, request: Request) -> Response:
    if request.query_params or await request.body():
        raise HTTPException(422, "evidence manifest request is invalid", headers=NO_STORE)
    try:
        result = _manifest_repository().read(
            owner_user_id=authenticated_multimedia_operator(request), manifest_id=manifest_id
        )
    except (
        EvidenceManifestUnavailable,
        EvidenceManifestConflict,
        EvidenceCollectionUnavailable,
        EvidenceCollectionConflict,
        DerivedAssetUnavailable,
        DerivedAssetIntegrity,
        DerivedAssetRetrievalIntegrity,
        DerivedCitationConflict,
    ) as exc:
        raise _manifest_error(exc) from None
    return Response(
        _canonical_response(result),
        media_type="application/json",
        headers={**NO_STORE, "ETag": result["etag"]},
    )


@derived_asset_router.post("/evidence-collections", status_code=201)
def create_evidence_collection(
    body: EvidenceCollectionCreateBody,
    request: Request,
    owner_id: str = Depends(authenticated_multimedia_operator),
) -> Response:
    key = request.headers.get("Idempotency-Key")
    if key is None:
        raise HTTPException(422, "Idempotency-Key is required", headers=NO_STORE)
    try:
        result = _collection_repository().create(
            owner_user_id=owner_id, idempotency_key=key, **body.model_dump()
        )
    except (
        EvidenceCollectionUnavailable,
        EvidenceCollectionConflict,
        DerivedAssetUnavailable,
        DerivedAssetIntegrity,
        DerivedAssetRetrievalIntegrity,
        DerivedCitationConflict,
    ) as exc:
        raise _collection_error(exc) from None
    except ValueError:
        raise HTTPException(
            422, "evidence collection request is invalid", headers=NO_STORE
        ) from None
    return Response(
        _canonical_response(result),
        status_code=201,
        media_type="application/json",
        headers={**NO_STORE, "ETag": result["etag"]},
    )


@derived_asset_router.get("/evidence-collections")
async def list_evidence_collections(request: Request) -> Response:
    if await request.body():
        raise HTTPException(422, "evidence collection request is invalid", headers=NO_STORE)
    asset_id = request.query_params.get("asset_id")
    revision_id = request.query_params.get("revision_id")
    if set(request.query_params) - {"asset_id", "revision_id"}:
        raise HTTPException(422, "evidence collection request is invalid", headers=NO_STORE)
    result = _collection_repository().list(
        owner_user_id=authenticated_multimedia_operator(request),
        asset_id=asset_id,
        revision_id=revision_id,
    )
    return Response(_canonical_response(result), media_type="application/json", headers=NO_STORE)


@derived_asset_router.get("/evidence-collections/{collection_id}")
async def read_evidence_collection(collection_id: str, request: Request) -> Response:
    if request.query_params or await request.body():
        raise HTTPException(422, "evidence collection request is invalid", headers=NO_STORE)
    try:
        result = _collection_repository().read(
            owner_user_id=authenticated_multimedia_operator(request),
            collection_id=collection_id,
        )
    except (
        EvidenceCollectionUnavailable,
        EvidenceCollectionConflict,
        DerivedAssetUnavailable,
        DerivedAssetIntegrity,
        DerivedAssetRetrievalIntegrity,
        DerivedCitationConflict,
    ) as exc:
        raise _collection_error(exc) from None
    return Response(
        _canonical_response(result),
        media_type="application/json",
        headers={**NO_STORE, "ETag": result["etag"]},
    )


def _canonical_response(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@derived_asset_router.get("")
async def discover_derived_assets(request: Request) -> Response:
    if request.query_params or await request.body():
        raise HTTPException(422, "derived asset request is invalid", headers=NO_STORE)
    try:
        result = _library().discover(authenticated_multimedia_operator(request))
    except (DerivedAssetUnavailable, DerivedAssetIntegrity) as exc:
        raise _library_error(exc) from None
    return Response(
        json.dumps(result, separators=(",", ":")), media_type="application/json", headers=NO_STORE
    )


@derived_asset_router.get("/assets/{asset_id}/revisions")
async def derived_asset_history(asset_id: str, request: Request) -> Response:
    if request.query_params or await request.body():
        raise HTTPException(422, "derived asset request is invalid", headers=NO_STORE)
    try:
        result = _library().history(authenticated_multimedia_operator(request), asset_id)
    except (DerivedAssetUnavailable, DerivedAssetIntegrity) as exc:
        raise _library_error(exc) from None
    return Response(
        json.dumps(result, separators=(",", ":")), media_type="application/json", headers=NO_STORE
    )


@derived_asset_router.get("/assets/{asset_id}/current/frame-preview")
async def current_derived_asset_preview(asset_id: str, request: Request) -> Response:
    if request.query_params or await request.body():
        raise HTTPException(422, "derived asset request is invalid", headers=NO_STORE)
    try:
        content = _library().current_preview(authenticated_multimedia_operator(request), asset_id)
    except (DerivedAssetUnavailable, DerivedAssetIntegrity) as exc:
        raise _library_error(exc) from None
    return Response(content, media_type="text/html; charset=utf-8", headers=FRAME_HEADERS)


@derived_asset_router.get("/assets/{asset_id}/revisions/{revision_id}/frame-preview")
async def exact_derived_asset_preview(
    asset_id: str, revision_id: str, request: Request
) -> Response:
    if request.query_params or await request.body():
        raise HTTPException(422, "derived asset request is invalid", headers=NO_STORE)
    try:
        content = _library().revision_preview(
            authenticated_multimedia_operator(request), asset_id, revision_id
        )
    except (DerivedAssetUnavailable, DerivedAssetIntegrity) as exc:
        raise _library_error(exc) from None
    return Response(content, media_type="text/html; charset=utf-8", headers=FRAME_HEADERS)


def _reading_response(*, owner_id: str, asset_id: str, revision_id: str | None = None) -> Response:
    try:
        result = _library().reading(owner_id, asset_id, revision_id)
    except (DerivedAssetUnavailable, DerivedAssetIntegrity) as exc:
        raise _library_error(exc) from None
    return Response(
        json.dumps(result, separators=(",", ":")),
        media_type="application/json",
        headers=NO_STORE,
    )


@derived_asset_router.get("/assets/{asset_id}/reading")
async def current_derived_asset_reading(asset_id: str, request: Request) -> Response:
    if request.query_params or await request.body():
        raise HTTPException(422, "derived asset request is invalid", headers=NO_STORE)
    return _reading_response(owner_id=authenticated_multimedia_operator(request), asset_id=asset_id)


@derived_asset_router.get("/assets/{asset_id}/revisions/{revision_id}/reading")
async def exact_derived_asset_reading(
    asset_id: str, revision_id: str, request: Request
) -> Response:
    if request.query_params or await request.body():
        raise HTTPException(422, "derived asset request is invalid", headers=NO_STORE)
    return _reading_response(
        owner_id=authenticated_multimedia_operator(request),
        asset_id=asset_id,
        revision_id=revision_id,
    )


def _search_response(
    *,
    owner_id: str,
    asset_id: str,
    body: DerivedAssetSearchBody,
    revision_id: str | None = None,
) -> Response:
    try:
        result = search_derived_asset(
            db_path=default_db_path(),
            owner_user_id=owner_id,
            asset_id=asset_id,
            revision_id=revision_id,
            **body.model_dump(),
        )
    except (DerivedAssetUnavailable, DerivedAssetIntegrity) as exc:
        raise _library_error(exc) from None
    except DerivedAssetRetrievalIntegrity:
        raise HTTPException(
            409, "derived asset retrieval integrity conflict", headers=NO_STORE
        ) from None
    except ValueError:
        raise HTTPException(
            422, "derived asset retrieval request is invalid", headers=NO_STORE
        ) from None
    return Response(
        json.dumps(result, separators=(",", ":")), media_type="application/json", headers=NO_STORE
    )


def _companion_evidence_response(
    *,
    owner_id: str,
    asset_id: str,
    body: DerivedCompanionEvidenceBody,
    revision_id: str | None = None,
) -> Response:
    try:
        result = DerivedCompanionRepository(db_path=default_db_path()).prepare_evidence(
            owner_user_id=owner_id,
            asset_id=asset_id,
            revision_id=revision_id,
            **body.model_dump(),
        )
    except (DerivedAssetUnavailable, DerivedAssetIntegrity) as exc:
        raise _library_error(exc) from None
    except DerivedAssetRetrievalIntegrity:
        raise HTTPException(
            409, "derived asset retrieval integrity conflict", headers=NO_STORE
        ) from None
    except CompanionIdempotencyConflict:
        raise HTTPException(409, "companion idempotency conflict", headers=NO_STORE) from None
    except CompanionStaleRevision as exc:
        return Response(
            json.dumps(
                {"detail": "stale current revision", "current": exc.scope}, separators=(",", ":")
            ),
            status_code=409,
            media_type="application/json",
            headers=NO_STORE,
        )
    except ValueError:
        raise HTTPException(422, "derived companion request is invalid", headers=NO_STORE) from None
    result["execution"] = _companion_execution(result["scope"])
    return Response(
        json.dumps(result, separators=(",", ":")), media_type="application/json", headers=NO_STORE
    )


def _companion_conversation_response(
    *,
    owner_id: str,
    asset_id: str,
    revision_id: str | None = None,
) -> Response:
    try:
        result = DerivedCompanionRepository(db_path=default_db_path()).conversation(
            owner_user_id=owner_id, asset_id=asset_id, revision_id=revision_id
        )
    except (DerivedAssetUnavailable, DerivedAssetIntegrity) as exc:
        raise _library_error(exc) from None
    result["execution"] = _companion_execution(result["scope"])
    return Response(
        json.dumps(result, separators=(",", ":")), media_type="application/json", headers=NO_STORE
    )


def _companion_execution(scope: dict[str, Any]) -> dict[str, Any]:
    return project_derived_companion_execution(
        derived_asset_id=str(scope["derived_asset_id"]),
        revision_id=str(scope["revision_id"]),
        content_sha256=str(scope["content_sha256"]),
        generation=int(scope["generation"]),
    )


@derived_asset_router.post("/assets/{asset_id}/search")
def search_current_derived_asset(
    asset_id: str,
    body: DerivedAssetSearchBody,
    owner_id: str = Depends(authenticated_multimedia_operator),
) -> Response:
    return _search_response(owner_id=owner_id, asset_id=asset_id, body=body)


@derived_asset_router.post("/assets/{asset_id}/revisions/{revision_id}/search")
def search_exact_derived_asset(
    asset_id: str,
    revision_id: str,
    body: DerivedAssetSearchBody,
    owner_id: str = Depends(authenticated_multimedia_operator),
) -> Response:
    return _search_response(
        owner_id=owner_id, asset_id=asset_id, revision_id=revision_id, body=body
    )


@derived_asset_router.post("/assets/{asset_id}/companion/evidence")
def prepare_current_companion_evidence(
    asset_id: str,
    body: DerivedCompanionEvidenceBody,
    owner_id: str = Depends(authenticated_multimedia_operator),
) -> Response:
    return _companion_evidence_response(owner_id=owner_id, asset_id=asset_id, body=body)


@derived_asset_router.get("/assets/{asset_id}/companion")
async def read_current_companion(asset_id: str, request: Request) -> Response:
    if request.query_params or await request.body():
        raise HTTPException(422, "derived companion request is invalid", headers=NO_STORE)
    return _companion_conversation_response(
        owner_id=authenticated_multimedia_operator(request), asset_id=asset_id
    )


@derived_asset_router.post("/assets/{asset_id}/revisions/{revision_id}/companion/evidence")
def prepare_exact_companion_evidence(
    asset_id: str,
    revision_id: str,
    body: DerivedCompanionEvidenceBody,
    owner_id: str = Depends(authenticated_multimedia_operator),
) -> Response:
    return _companion_evidence_response(
        owner_id=owner_id, asset_id=asset_id, revision_id=revision_id, body=body
    )


@derived_asset_router.get("/assets/{asset_id}/revisions/{revision_id}/companion")
async def read_exact_companion(asset_id: str, revision_id: str, request: Request) -> Response:
    if request.query_params or await request.body():
        raise HTTPException(422, "derived companion request is invalid", headers=NO_STORE)
    return _companion_conversation_response(
        owner_id=authenticated_multimedia_operator(request),
        asset_id=asset_id,
        revision_id=revision_id,
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
    return _draft_response(draft, projection_ids=body.projection_ids)


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


@merge_asset_router.post("/reviews/{review_id}/apply", response_model=MergeCommitResponse)
def apply_merge_review(
    review_id: str,
    body: ApplyReviewBody,
    response: Response,
    owner_id: str = Depends(authenticated_multimedia_operator),
) -> MergeCommitResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        result = apply_review(
            review_id=review_id,
            operation_id=body.operation_id,
            expected_generation=body.expected_generation,
            owner_user_id=owner_id,
            db_path=default_db_path(),
        )
    except MergeCommitNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail="merge authority not found",
            headers={"Cache-Control": "no-store"},
        ) from exc
    except MergeCommitError as exc:
        raise HTTPException(
            status_code=409,
            detail="merge command refused",
            headers={"Cache-Control": "no-store"},
        ) from exc
    return _commit_response(result)


@merge_asset_router.post("/assets/{asset_id}/restore", response_model=MergeCommitResponse)
def restore_merge_asset(
    asset_id: str,
    body: RestoreAssetBody,
    response: Response,
    owner_id: str = Depends(authenticated_multimedia_operator),
) -> MergeCommitResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        result = restore(
            derived_asset_id=asset_id,
            owner_user_id=owner_id,
            db_path=default_db_path(),
            **body.model_dump(),
        )
    except MergeCommitNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail="merge authority not found",
            headers={"Cache-Control": "no-store"},
        ) from exc
    except MergeCommitError as exc:
        raise HTTPException(
            status_code=409,
            detail="merge command refused",
            headers={"Cache-Control": "no-store"},
        ) from exc
    return _commit_response(result)


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


@merge_asset_router.get("/frame-previews/{opaque_id}", response_class=Response)
def frame_preview_merge_draft(
    opaque_id: str,
    owner_id: str = Depends(authenticated_multimedia_operator),
    repository: MergeDraftRepository = Depends(get_merge_draft_repository),
) -> Response:
    """Serve the same inert stored bytes in an empty-sandbox same-origin frame."""
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
                "default-src 'none'; frame-ancestors 'self'; base-uri 'none'; "
                "form-action 'none'; sandbox"
            ),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
            "Referrer-Policy": "no-referrer",
        },
    )


def _draft_response(draft: Draft, *, projection_ids: tuple[str, ...]) -> DraftResponse:
    return DraftResponse(
        draft_id=draft.draft_id,
        canonical_sha256=draft.canonical_sha256,
        manifest_sha256=draft.manifest_sha256,
        sanitizer_policy=draft.sanitizer_policy,
        sanitizer_version=draft.sanitizer_version,
        projection_ids=projection_ids,
    )


def _review_response(review: Review) -> ReviewResponse:
    return ReviewResponse(
        review_id=review.review_id,
        draft_id=review.draft_id,
        canonical_sha256=review.canonical_sha256,
        manifest_sha256=review.manifest_sha256,
        acknowledgement_version=review.acknowledgement_version,
    )


def _commit_response(result: MergeCommitResult) -> MergeCommitResponse:
    return MergeCommitResponse(**result.__dict__)


def register_merge_asset_routes(app: object) -> None:
    from fastapi import FastAPI

    if not isinstance(app, FastAPI):
        raise TypeError("app must be FastAPI")
    app.router.on_startup.append(_initialize_merge_schema)
    app.include_router(derived_asset_router)
    app.include_router(merge_asset_router)


def _initialize_merge_schema() -> None:
    """Apply V18 during process startup, never inside a request."""
    init_database_at_path(default_db_path())


__all__ = [
    "derived_asset_router",
    "get_merge_draft_repository",
    "merge_asset_router",
    "register_merge_asset_routes",
]
