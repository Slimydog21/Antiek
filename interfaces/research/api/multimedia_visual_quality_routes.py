"""Authenticated visual quality assessments and read-only routing advice."""

from __future__ import annotations

import os
import stat
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from substrate.multimedia.read_model import MultimediaAssetStore
from substrate.multimedia.visual_quality_advisory import (
    RUBRIC_VERSION,
    VisualQualityAdvisoryError,
    VisualQualityAdvisoryIntegrityError,
    VisualQualityAdvisoryRegistry,
    VisualQualityAssessmentRequest,
)

from .multimedia_reconciliation_routes import authenticated_multimedia_operator
from .multimedia_visual_generation_routes import (
    MultimediaVisualGenerationRuntime,
)


class VisualQualityAssessmentBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    expected_revision_id: str = Field(
        min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
    )
    disposition: Literal["accepted", "rejected"]
    prompt_fidelity: Literal["pass", "fail"]
    technical_acceptability: Literal["pass", "fail"]
    visual_coherence: Literal["pass", "fail"]
    production_usable: Literal["pass", "fail"]
    reason_codes: tuple[
        Literal[
            "prompt_mismatch",
            "technical_artifact",
            "visual_incoherence",
            "not_production_usable",
            "unsafe_or_misleading",
            "other",
        ],
        ...,
    ] = Field(default=(), max_length=8)


class VisualQualityAssessmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assessment_id: str
    request_id: str
    execution_id: str
    candidate_id: str
    asset_id: str
    revision_id: str
    artifact_sha256: str
    rubric_version: str
    disposition: Literal["accepted", "rejected"]
    prompt_fidelity: Literal["pass", "fail"]
    technical_acceptability: Literal["pass", "fail"]
    visual_coherence: Literal["pass", "fail"]
    production_usable: Literal["pass", "fail"]
    reason_codes: tuple[str, ...]
    assessed_at: str
    quality_score: float


class VisualRoutingCohortKeyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    generation_kind: Literal["image", "video"]
    provider: str
    model: str
    route_policy: str
    catalog_version: str
    catalog_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    rubric_version: str


class VisualRoutingCohortResponse(BaseModel):
    key: VisualRoutingCohortKeyResponse
    n_executions: int
    n_assets: int
    n_materialized_candidates: int
    n_assessed_candidates: int
    n_accepted: int
    assessment_coverage: float
    mean_quality: float | None
    acceptance_rate: float | None
    quality_lower_bound: float | None
    charged_cents_total: int | None
    charged_cents_per_assessed_candidate: float | None
    charged_cents_per_accepted_candidate: float | None
    efficiency_score: float | None
    eligible: bool
    ineligibility_reasons: tuple[str, ...]


class VisualRoutingRecommendationResponse(BaseModel):
    cohort: VisualRoutingCohortKeyResponse
    efficiency_score: float


class VisualRoutingAdvisoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    formula_version: str
    rubric_version: str
    as_of: str
    cohorts: tuple[VisualRoutingCohortResponse, ...]
    exclusions: dict[str, int]
    recommendation: VisualRoutingRecommendationResponse | None


@dataclass(frozen=True, repr=False)
class MultimediaVisualQualityRuntime:
    store: MultimediaAssetStore
    registry: VisualQualityAdvisoryRegistry
    clock: Callable[[], datetime]


def get_multimedia_visual_quality_runtime() -> MultimediaVisualQualityRuntime:
    raise HTTPException(status_code=503, detail="multimedia visual quality is unavailable")


def multimedia_visual_quality_runtime_from_environment(
    *,
    store: MultimediaAssetStore,
    environ: dict[str, str] | None = None,
    generation_runtime: MultimediaVisualGenerationRuntime | None = None,
) -> MultimediaVisualQualityRuntime | None:
    values = os.environ if environ is None else environ
    execution_db_path = values.get("ANTIEK_MULTIMEDIA_VISUAL_QUALITY_DB_PATH", "").strip()
    key_value = values.get("ANTIEK_MULTIMEDIA_VISUAL_QUALITY_SIGNING_KEY_HEX", "").strip()
    if generation_runtime is not None:
        if execution_db_path or key_value:
            raise RuntimeError("multimedia visual quality configuration is ambiguous")
        execution_db_path = generation_runtime.execution_db_path
        signing_key = generation_runtime.authority.signing_key
    elif not execution_db_path and not key_value:
        return None
    elif not execution_db_path or not key_value:
        raise RuntimeError("multimedia visual quality configuration is incomplete")
    else:
        try:
            signing_key = bytes.fromhex(key_value)
        except ValueError:
            raise RuntimeError("multimedia visual quality configuration is invalid") from None
        if len(signing_key) < 32:
            raise RuntimeError("multimedia visual quality configuration is invalid")
    _private_db_parent(execution_db_path)
    return MultimediaVisualQualityRuntime(
        store=store,
        registry=VisualQualityAdvisoryRegistry(
            db_path=execution_db_path,
            signing_key=signing_key,
        ),
        clock=lambda: datetime.now(UTC),
    )


multimedia_visual_quality_router = APIRouter(tags=["multimedia-visual-quality"])


@multimedia_visual_quality_router.post(
    "/assets/{asset_id}/visual-candidates/{candidate_id}/quality-assessment",
    response_model=VisualQualityAssessmentResponse,
)
def assess_multimedia_visual_candidate_quality(
    asset_id: str,
    candidate_id: str,
    body: VisualQualityAssessmentBody,
    owner_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaVisualQualityRuntime = Depends(get_multimedia_visual_quality_runtime),
) -> VisualQualityAssessmentResponse:
    try:
        assessment = runtime.registry.assess(
            asset_id=asset_id,
            candidate_id=candidate_id,
            request=VisualQualityAssessmentRequest(**body.model_dump()),
            owner_id=owner_id,
            store=runtime.store,
            now=runtime.clock(),
        )
    except VisualQualityAdvisoryIntegrityError as exc:
        raise HTTPException(status_code=503, detail="multimedia visual quality is unavailable") from exc
    except VisualQualityAdvisoryError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return VisualQualityAssessmentResponse.model_validate(asdict(assessment))


@multimedia_visual_quality_router.get(
    "/routing-recommendations/visuals",
    response_model=VisualRoutingAdvisoryResponse,
)
def get_multimedia_visual_routing_advisory(
    as_of: datetime | None = Query(default=None),
    generation_kind: Literal["image", "video"] | None = Query(default=None),
    rubric_version: str = Query(default=RUBRIC_VERSION, min_length=1, max_length=64),
    owner_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaVisualQualityRuntime = Depends(get_multimedia_visual_quality_runtime),
) -> VisualRoutingAdvisoryResponse:
    now = runtime.clock()
    cutoff = now if as_of is None else as_of
    if (
        cutoff.tzinfo is None
        or cutoff.utcoffset() is None
        or cutoff > now
        or cutoff < datetime(2020, 1, 1, tzinfo=UTC)
    ):
        raise HTTPException(status_code=422, detail="as_of must be a bounded UTC timestamp")
    try:
        report = runtime.registry.report(
            owner_id=owner_id,
            as_of=cutoff,
            generation_kind=generation_kind,
            rubric_version=rubric_version,
        )
    except VisualQualityAdvisoryIntegrityError as exc:
        raise HTTPException(status_code=503, detail="multimedia visual quality is unavailable") from exc
    except VisualQualityAdvisoryError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return VisualRoutingAdvisoryResponse.model_validate(asdict(report))


def _private_db_parent(value: str) -> None:
    path = Path(value)
    try:
        metadata = path.parent.lstat()
    except OSError:
        raise RuntimeError("multimedia visual quality database path is invalid") from None
    if (
        not path.is_absolute()
        or path.is_symlink()
        or path.parent.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise RuntimeError("multimedia visual quality database path is invalid")


__all__ = [
    "MultimediaVisualQualityRuntime",
    "VisualQualityAssessmentBody",
    "VisualQualityAssessmentResponse",
    "VisualRoutingAdvisoryResponse",
    "get_multimedia_visual_quality_runtime",
    "multimedia_visual_quality_router",
    "multimedia_visual_quality_runtime_from_environment",
]
