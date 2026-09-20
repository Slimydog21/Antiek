"""Owner-bound private preview and explicit generated visual attestation."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from substrate.multimedia.artifact_quarantine import Resolver, Transport
from substrate.multimedia.read_model import MultimediaAssetStore
from substrate.multimedia.visual_candidate_review import (
    VisualCandidateReviewError,
    attest_visual_candidate,
    preview_visual_candidate,
)

from .multimedia_reconciliation_routes import authenticated_multimedia_operator
from .multimedia_visual_candidate_routes import (
    MultimediaVisualCandidateRuntime,
    multimedia_visual_candidate_runtime_from_environment,
)


class AttestVisualCandidateBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_revision_id: str = Field(min_length=1, max_length=128)
    operator_acknowledged_generated_provenance: bool


class VisualCandidateAttestationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_receipt_id: str
    reviewer_id: str
    attested_at: str


@dataclass(frozen=True, repr=False)
class MultimediaVisualReviewRuntime:
    candidates: MultimediaVisualCandidateRuntime
    operator_signing_key: bytes
    clock: Callable[[], datetime]


def get_multimedia_visual_review_runtime() -> MultimediaVisualReviewRuntime:
    raise HTTPException(status_code=503, detail="multimedia visual review is unavailable")


def multimedia_visual_review_runtime_from_environment(
    *,
    store: MultimediaAssetStore,
    environ: dict[str, str] | None = None,
    resolver: Resolver | None = None,
    transport: Transport | None = None,
) -> MultimediaVisualReviewRuntime | None:
    values = os.environ if environ is None else environ
    key_value = values.get("ANTIEK_MULTIMEDIA_VISUAL_REVIEW_OPERATOR_SIGNING_KEY_HEX", "").strip()
    candidates = multimedia_visual_candidate_runtime_from_environment(
        store=store, environ=dict(values), resolver=resolver, transport=transport
    )
    if candidates is None and not key_value:
        return None
    if candidates is None or not key_value:
        raise RuntimeError("multimedia visual review configuration is incomplete")
    try:
        key = bytes.fromhex(key_value)
    except ValueError:
        raise RuntimeError("multimedia visual review configuration is invalid") from None
    quarantine_key = candidates.generation.authority.signing_key
    if len(key) != 32 or key == quarantine_key:
        raise RuntimeError("multimedia visual review configuration is invalid")
    return MultimediaVisualReviewRuntime(candidates, key, lambda: datetime.now(UTC))


multimedia_visual_review_router = APIRouter(tags=["multimedia-visual-review"])


@multimedia_visual_review_router.get(
    "/assets/{asset_id}/visual-candidates/{candidate_id}/content"
)
def preview_multimedia_visual_candidate(
    asset_id: str,
    candidate_id: str,
    revision_id: str = Query(min_length=1, max_length=128),
    owner_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaVisualReviewRuntime = Depends(get_multimedia_visual_review_runtime),
) -> Response:
    generation = runtime.candidates.generation
    authority = generation.authority
    try:
        preview = preview_visual_candidate(
            asset_id=asset_id, candidate_id=candidate_id,
            expected_revision_id=revision_id, owner_id=owner_id,
            store=authority.store, db_path=generation.execution_db_path,
            quarantine_signing_key=authority.signing_key,
        )
    except VisualCandidateReviewError as exc:
        raise HTTPException(status_code=404, detail="visual candidate is unavailable") from exc
    return Response(
        content=preview.content,
        media_type=preview.media_type,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        },
    )


@multimedia_visual_review_router.post(
    "/assets/{asset_id}/visual-candidates/{candidate_id}/attestation",
    response_model=VisualCandidateAttestationResponse,
)
def attest_multimedia_visual_candidate(
    asset_id: str,
    candidate_id: str,
    body: AttestVisualCandidateBody,
    owner_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaVisualReviewRuntime = Depends(get_multimedia_visual_review_runtime),
) -> VisualCandidateAttestationResponse:
    generation = runtime.candidates.generation
    authority = generation.authority
    try:
        result = attest_visual_candidate(
            asset_id=asset_id, candidate_id=candidate_id,
            expected_revision_id=body.expected_revision_id, owner_id=owner_id,
            operator_acknowledged_generated_provenance=(
                body.operator_acknowledged_generated_provenance
            ),
            store=authority.store, db_path=generation.execution_db_path,
            quarantine_signing_key=authority.signing_key,
            operator_signing_key=runtime.operator_signing_key, now=runtime.clock(),
        )
    except VisualCandidateReviewError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return VisualCandidateAttestationResponse.model_validate(asdict(result))


__all__ = [
    "AttestVisualCandidateBody", "MultimediaVisualReviewRuntime",
    "VisualCandidateAttestationResponse", "get_multimedia_visual_review_runtime",
    "multimedia_visual_review_router", "multimedia_visual_review_runtime_from_environment",
]
