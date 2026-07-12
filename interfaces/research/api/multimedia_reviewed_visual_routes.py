"""Authenticated routes for owner-bound reviewed visual sets."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from substrate.multimedia.generated_visual_candidate_resolver import (
    GeneratedVisualCandidateResolver,
)
from substrate.multimedia.read_model import MultimediaAssetStore
from substrate.multimedia.reviewed_visual_registry import (
    RegisterReviewedVisualsRequest,
    ReviewedVisualRegistry,
    ReviewedVisualRegistryError,
    ReviewedVisualSetReceipt,
    VisualCandidateBinding,
    VisualCandidateResolver,
    get_reviewed_visuals,
    register_reviewed_visuals,
)
from substrate.multimedia.visual_authorization import VisualAuthorizationRegistry
from substrate.multimedia.visual_evidence_authority import VisualEvidenceAuthority

from .multimedia_reconciliation_routes import authenticated_multimedia_operator


class VisualCandidateBindingBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    chapter_id: str = Field(min_length=1, max_length=128)
    candidate_id: str = Field(min_length=1, max_length=128)


class RegisterReviewedVisualsBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    request_id: str = Field(min_length=1, max_length=128)
    expected_revision_id: str = Field(min_length=1, max_length=128)
    bindings: tuple[VisualCandidateBindingBody, ...] = Field(min_length=1, max_length=64)


class ReviewedVisualSetResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    set_id: str
    asset_id: str
    revision_id: str
    chapter_ids: tuple[str, ...]
    scene_ids: tuple[str, ...]
    candidate_ids: tuple[str, ...]
    selection_digest: str
    created_at: str


@dataclass(frozen=True)
class MultimediaReviewedVisualRuntime:
    store: MultimediaAssetStore
    registry: ReviewedVisualRegistry
    candidate_resolver: VisualCandidateResolver
    clock: Callable[[], datetime]


def get_multimedia_reviewed_visual_runtime() -> MultimediaReviewedVisualRuntime:
    raise HTTPException(status_code=503, detail="multimedia reviewed visuals are unavailable")


def multimedia_reviewed_visual_runtime_from_environment(
    *,
    store: MultimediaAssetStore,
    environ: dict[str, str] | None = None,
) -> MultimediaReviewedVisualRuntime | None:
    values = os.environ if environ is None else environ
    prefix = "ANTIEK_MULTIMEDIA_REVIEWED_VISUAL_"
    enabled = values.get(f"{prefix}ENABLED", "").strip().lower()
    fields = {
        "db_path": values.get(f"{prefix}DB_PATH", "").strip(),
        "integrity_key": values.get(f"{prefix}INTEGRITY_KEY_HEX", "").strip(),
        "authority_db_path": values.get(f"{prefix}AUTHORITY_DB_PATH", "").strip(),
        "authority_key": values.get(f"{prefix}AUTHORITY_SIGNING_KEY_HEX", "").strip(),
        "execution_db_path": values.get(f"{prefix}EXECUTION_DB_PATH", "").strip(),
        "execution_key": values.get(f"{prefix}EXECUTION_SIGNING_KEY_HEX", "").strip(),
        "operator_verify_key": values.get(f"{prefix}OPERATOR_VERIFY_KEY_HEX", "").strip(),
        "evidence_key": values.get(f"{prefix}EVIDENCE_AUTHORITY_KEY_HEX", "").strip(),
        "reviewer_ids": values.get(f"{prefix}AUTHORIZED_REVIEWER_IDS", "").strip(),
    }
    if not enabled and not any(fields.values()):
        return None
    if enabled not in {"1", "true"} or any(not field for field in fields.values()):
        raise RuntimeError("multimedia reviewed visual configuration is incomplete")
    try:
        integrity_key = bytes.fromhex(fields["integrity_key"])
        authority_key = bytes.fromhex(fields["authority_key"])
        execution_key = bytes.fromhex(fields["execution_key"])
        operator_verify_key = bytes.fromhex(fields["operator_verify_key"])
        evidence_key = bytes.fromhex(fields["evidence_key"])
    except ValueError:
        raise RuntimeError("multimedia reviewed visual configuration is invalid") from None
    if (
        len(integrity_key) < 32
        or len(authority_key) < 32
        or len(execution_key) < 32
        or len(operator_verify_key) != 32
        or len(evidence_key) < 32
    ):
        raise RuntimeError("multimedia reviewed visual configuration is invalid")
    reviewers = frozenset(
        value.strip() for value in fields["reviewer_ids"].split(",") if value.strip()
    )
    if not reviewers:
        raise RuntimeError("multimedia reviewed visual configuration is invalid")
    try:
        resolver = GeneratedVisualCandidateResolver(
            execution_db_path=fields["execution_db_path"],
            execution_signing_key=execution_key,
            authorization_registry=VisualAuthorizationRegistry(
                db_path=fields["authority_db_path"], signing_key=authority_key
            ),
            evidence_authority=VisualEvidenceAuthority(
                db_path=fields["execution_db_path"],
                operator_verify_key=operator_verify_key,
                evidence_authority_key=evidence_key,
                authorized_reviewer_ids=reviewers,
            ),
        )
    except ValueError:
        raise RuntimeError("multimedia reviewed visual configuration is invalid") from None

    return MultimediaReviewedVisualRuntime(
        store=store,
        registry=ReviewedVisualRegistry(
            db_path=fields["db_path"], integrity_key=integrity_key
        ),
        candidate_resolver=resolver,
        clock=lambda: datetime.now(UTC),
    )


multimedia_reviewed_visual_router = APIRouter(tags=["multimedia-reviewed-visuals"])


@multimedia_reviewed_visual_router.post(
    "/assets/{asset_id}/reviewed-visuals", response_model=ReviewedVisualSetResponse
)
def register_multimedia_reviewed_visuals(
    asset_id: str,
    body: RegisterReviewedVisualsBody,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaReviewedVisualRuntime = Depends(
        get_multimedia_reviewed_visual_runtime
    ),
) -> ReviewedVisualSetResponse:
    request = RegisterReviewedVisualsRequest(
        request_id=body.request_id,
        expected_revision_id=body.expected_revision_id,
        bindings=tuple(
            VisualCandidateBinding(row.chapter_id, row.candidate_id) for row in body.bindings
        ),
    )
    try:
        receipt = register_reviewed_visuals(
            asset_id,
            request,
            owner_id=operator_id,
            store=runtime.store,
            registry=runtime.registry,
            candidate_resolver=runtime.candidate_resolver,
            clock=runtime.clock,
        )
    except ReviewedVisualRegistryError as exc:
        detail = str(exc)
        status = 404 if "unavailable" in detail else 409
        raise HTTPException(status_code=status, detail=detail) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503, detail="multimedia reviewed visuals are unavailable"
        ) from exc
    return _response(receipt)


@multimedia_reviewed_visual_router.get(
    "/assets/{asset_id}/reviewed-visuals", response_model=ReviewedVisualSetResponse
)
def read_multimedia_reviewed_visuals(
    asset_id: str,
    revision_id: str = Query(min_length=1, max_length=128),
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaReviewedVisualRuntime = Depends(
        get_multimedia_reviewed_visual_runtime
    ),
) -> ReviewedVisualSetResponse:
    try:
        resolved = get_reviewed_visuals(
            asset_id,
            revision_id,
            owner_id=operator_id,
            store=runtime.store,
            registry=runtime.registry,
        )
    except ReviewedVisualRegistryError as exc:
        raise HTTPException(status_code=404, detail="reviewed visual set is unavailable") from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503, detail="multimedia reviewed visuals are unavailable"
        ) from exc
    return _response(resolved.receipt)


def _response(receipt: ReviewedVisualSetReceipt) -> ReviewedVisualSetResponse:
    return ReviewedVisualSetResponse.model_validate(asdict(receipt))


__all__ = [
    "MultimediaReviewedVisualRuntime",
    "RegisterReviewedVisualsBody",
    "ReviewedVisualSetResponse",
    "VisualCandidateBindingBody",
    "get_multimedia_reviewed_visual_runtime",
    "multimedia_reviewed_visual_router",
    "multimedia_reviewed_visual_runtime_from_environment",
]
