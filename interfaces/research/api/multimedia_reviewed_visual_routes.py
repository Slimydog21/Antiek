"""Authenticated routes for owner-bound reviewed visual sets."""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

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
from substrate.multimedia.visual_selection import ReviewedVisualSelection

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
        "catalog_path": values.get(f"{prefix}CATALOG_PATH", "").strip(),
    }
    if not enabled and not any(fields.values()):
        return None
    if enabled not in {"1", "true"} or any(not field for field in fields.values()):
        raise RuntimeError("multimedia reviewed visual configuration is incomplete")
    try:
        integrity_key = bytes.fromhex(fields["integrity_key"])
    except ValueError:
        raise RuntimeError("multimedia reviewed visual configuration is invalid") from None
    if len(integrity_key) < 32:
        raise RuntimeError("multimedia reviewed visual configuration is invalid")
    candidates = _load_candidate_catalog(fields["catalog_path"])

    def resolve(record, chapter_id: str, candidate_id: str) -> ReviewedVisualSelection:
        candidate = candidates.get(candidate_id)
        if candidate is None:
            raise LookupError("candidate is unavailable")
        asset_id, revision_id, bound_chapter, selection = candidate
        if (
            asset_id != record.asset.asset_id
            or revision_id != record.asset.revision_id
            or bound_chapter != chapter_id
        ):
            raise LookupError("candidate is unavailable")
        return selection

    return MultimediaReviewedVisualRuntime(
        store=store,
        registry=ReviewedVisualRegistry(
            db_path=fields["db_path"], integrity_key=integrity_key
        ),
        candidate_resolver=resolve,
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


def _load_candidate_catalog(
    path_value: str,
) -> dict[str, tuple[str, str, str, ReviewedVisualSelection]]:
    try:
        metadata = os.lstat(path_value)
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError("multimedia reviewed visual catalog is invalid")
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise RuntimeError("multimedia reviewed visual catalog must be private")
        if metadata.st_size <= 0 or metadata.st_size > 4 * 1024 * 1024:
            raise RuntimeError("multimedia reviewed visual catalog is invalid")
        fd = os.open(path_value, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise RuntimeError("multimedia reviewed visual catalog is unavailable") from exc
    try:
        opened = os.fstat(fd)
        if (metadata.st_dev, metadata.st_ino) != (opened.st_dev, opened.st_ino):
            raise RuntimeError("multimedia reviewed visual catalog changed while reading")
        chunks: list[bytes] = []
        total = 0
        while chunk := os.read(fd, 1024 * 1024):
            total += len(chunk)
            if total > 4 * 1024 * 1024:
                raise RuntimeError("multimedia reviewed visual catalog is invalid")
            chunks.append(chunk)
        after = os.fstat(fd)
        if (opened.st_size, opened.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise RuntimeError("multimedia reviewed visual catalog changed while reading")
        payload = b"".join(chunks)
    finally:
        os.close(fd)
    if len(payload) != metadata.st_size:
        raise RuntimeError("multimedia reviewed visual catalog changed while reading")
    try:
        decoded = json.loads(payload)
        if not isinstance(decoded, dict) or decoded.get("schema_version") != 1:
            raise ValueError
        rows = decoded.get("candidates")
        if not isinstance(rows, list) or not rows or len(rows) > 4096:
            raise ValueError
        catalog: dict[str, tuple[str, str, str, ReviewedVisualSelection]] = {}
        for row in rows:
            if not isinstance(row, dict) or set(row) != {
                "asset_id",
                "candidate_id",
                "chapter_id",
                "revision_id",
                "selection",
            }:
                raise ValueError
            candidate_id = str(row["candidate_id"])
            if not candidate_id or len(candidate_id) > 128 or candidate_id in catalog:
                raise ValueError
            catalog[candidate_id] = (
                str(row["asset_id"]),
                str(row["revision_id"]),
                str(row["chapter_id"]),
                ReviewedVisualSelection.model_validate(row["selection"]),
            )
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise RuntimeError("multimedia reviewed visual catalog is invalid") from exc
    return catalog


__all__ = [
    "MultimediaReviewedVisualRuntime",
    "RegisterReviewedVisualsBody",
    "ReviewedVisualSetResponse",
    "VisualCandidateBindingBody",
    "get_multimedia_reviewed_visual_runtime",
    "multimedia_reviewed_visual_router",
    "multimedia_reviewed_visual_runtime_from_environment",
]
