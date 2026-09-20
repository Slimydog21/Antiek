"""Authenticated Krea-result quarantine and safe candidate metadata."""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from substrate.multimedia.artifact_quarantine import Resolver, Transport
from substrate.multimedia.quarantine_transport import PinnedTLSTransport, SocketResolver
from substrate.multimedia.read_model import MultimediaAssetStore
from substrate.multimedia.visual_candidate_materialization import (
    VisualCandidateMaterializationError,
    materialize_visual_candidates,
)

from .multimedia_reconciliation_routes import authenticated_multimedia_operator
from .multimedia_visual_generation_routes import (
    MultimediaVisualGenerationRuntime,
    multimedia_visual_generation_runtime_from_environment,
)

_HOST = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


class MaterializeVisualCandidatesBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    authority_request_id: str = Field(min_length=1, max_length=128)
    expected_revision_id: str = Field(min_length=1, max_length=128)


class MaterializedVisualCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: str
    artifact_receipt_id: str
    media_type: str
    byte_count: int


class MaterializedVisualCandidatesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    execution_id: str
    candidates: tuple[MaterializedVisualCandidateResponse, ...]


@dataclass(frozen=True, repr=False)
class MultimediaVisualCandidateRuntime:
    generation: MultimediaVisualGenerationRuntime
    resolver: Resolver
    transport: Transport
    allowlisted_hosts: frozenset[str]
    quarantine_dir: str
    clock: Callable[[], datetime]


def get_multimedia_visual_candidate_runtime() -> MultimediaVisualCandidateRuntime:
    raise HTTPException(status_code=503, detail="multimedia visual candidates are unavailable")


def multimedia_visual_candidate_runtime_from_environment(
    *,
    store: MultimediaAssetStore,
    environ: dict[str, str] | None = None,
    resolver: Resolver | None = None,
    transport: Transport | None = None,
) -> MultimediaVisualCandidateRuntime | None:
    values = os.environ if environ is None else environ
    hosts_value = values.get("ANTIEK_MULTIMEDIA_VISUAL_CANDIDATE_ALLOWED_HOSTS", "").strip()
    quarantine_dir = values.get("ANTIEK_MULTIMEDIA_VISUAL_CANDIDATE_QUARANTINE_DIR", "").strip()
    generation = multimedia_visual_generation_runtime_from_environment(
        store=store, environ=dict(values)
    )
    if generation is None and not hosts_value and not quarantine_dir:
        return None
    if generation is None or not hosts_value or not quarantine_dir:
        raise RuntimeError("multimedia visual candidate configuration is incomplete")
    hosts = frozenset(value.strip().lower() for value in hosts_value.split(",") if value.strip())
    if not hosts or len(hosts) > 16 or any(not _HOST.fullmatch(value) for value in hosts):
        raise RuntimeError("multimedia visual candidate configuration is invalid")
    _private_directory(quarantine_dir)
    return MultimediaVisualCandidateRuntime(
        generation=generation,
        resolver=resolver or SocketResolver(),
        transport=transport or PinnedTLSTransport(),
        allowlisted_hosts=hosts,
        quarantine_dir=quarantine_dir,
        clock=lambda: datetime.now(UTC),
    )


multimedia_visual_candidate_router = APIRouter(tags=["multimedia-visual-candidates"])


@multimedia_visual_candidate_router.post(
    "/assets/{asset_id}/visual-generations/{execution_id}/materialize",
    response_model=MaterializedVisualCandidatesResponse,
)
def materialize_multimedia_visual_candidates(
    asset_id: str,
    execution_id: str,
    body: MaterializeVisualCandidatesBody,
    owner_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaVisualCandidateRuntime = Depends(
        get_multimedia_visual_candidate_runtime
    ),
) -> MaterializedVisualCandidatesResponse:
    generation = runtime.generation
    authority = generation.authority
    try:
        candidates = materialize_visual_candidates(
            asset_id=asset_id, execution_id=execution_id,
            authority_request_id=body.authority_request_id,
            expected_revision_id=body.expected_revision_id, owner_id=owner_id,
            store=authority.store, registry=authority.registry, terms=authority.terms,
            db_path=generation.execution_db_path, signing_key=authority.signing_key,
            client=generation.client, resolver=runtime.resolver, transport=runtime.transport,
            allowlisted_hosts=runtime.allowlisted_hosts,
            quarantine_dir=runtime.quarantine_dir, now=runtime.clock(),
        )
    except VisualCandidateMaterializationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return MaterializedVisualCandidatesResponse(
        execution_id=execution_id,
        candidates=tuple(
            MaterializedVisualCandidateResponse.model_validate(asdict(row))
            for row in candidates
        ),
    )


def _private_directory(value: str) -> None:
    path = Path(value)
    try:
        metadata = path.lstat()
    except OSError:
        raise RuntimeError("multimedia visual candidate quarantine is invalid") from None
    if (
        not path.is_absolute() or path.is_symlink() or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise RuntimeError("multimedia visual candidate quarantine is invalid")


__all__ = [
    "MaterializeVisualCandidatesBody", "MaterializedVisualCandidateResponse",
    "MaterializedVisualCandidatesResponse", "MultimediaVisualCandidateRuntime",
    "get_multimedia_visual_candidate_runtime", "multimedia_visual_candidate_router",
    "multimedia_visual_candidate_runtime_from_environment",
]
