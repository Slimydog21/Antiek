"""Authenticated commands for one-shot Krea visual submission and polling."""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from integrations.krea.client import KreaClient
from substrate.multimedia.read_model import MultimediaAssetStore
from substrate.multimedia.visual_generation import (
    VisualGenerationError,
    poll_visual_generation,
    submit_visual_generation,
)

from .multimedia_reconciliation_routes import authenticated_multimedia_operator
from .multimedia_visual_authorization_routes import (
    MultimediaVisualAuthorizationRuntime,
    multimedia_visual_authorization_runtime_from_environment,
)


class SubmitVisualGenerationBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: str = Field(min_length=1, max_length=128)
    expected_revision_id: str = Field(min_length=1, max_length=128)


class PollVisualGenerationBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_revision_id: str = Field(min_length=1, max_length=128)


class VisualGenerationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    execution_id: str
    authorization_id: str
    provider_job_id: str | None
    status: str
    candidate_count: int


@dataclass(frozen=True, repr=False)
class MultimediaVisualGenerationRuntime:
    authority: MultimediaVisualAuthorizationRuntime
    client: KreaClient
    execution_db_path: str
    clock: Callable[[], datetime]


def get_multimedia_visual_generation_runtime() -> MultimediaVisualGenerationRuntime:
    raise HTTPException(status_code=503, detail="multimedia visual generation is unavailable")


def multimedia_visual_generation_runtime_from_environment(
    *, store: MultimediaAssetStore, environ: dict[str, str] | None = None
) -> MultimediaVisualGenerationRuntime | None:
    values = os.environ if environ is None else environ
    token = values.get("ANTIEK_MULTIMEDIA_VISUAL_GENERATION_KREA_TOKEN", "").strip()
    expected_account = values.get(
        "ANTIEK_MULTIMEDIA_VISUAL_GENERATION_KREA_ACCOUNT_IDENTITY_DIGEST", ""
    ).strip()
    execution_db_path = values.get(
        "ANTIEK_MULTIMEDIA_VISUAL_GENERATION_DB_PATH", ""
    ).strip()
    authority = multimedia_visual_authorization_runtime_from_environment(
        store=store, environ=dict(values)
    )
    if authority is None and not token and not expected_account and not execution_db_path:
        return None
    if authority is None or not token or not expected_account or not execution_db_path:
        raise RuntimeError("multimedia visual generation configuration is incomplete")
    try:
        client = KreaClient(token)
    except ValueError:
        raise RuntimeError("multimedia visual generation configuration is invalid") from None
    if (
        len(expected_account) != 64
        or any(character not in "0123456789abcdef" for character in expected_account)
        or not hashlib.sha256(token.split(":", 1)[0].encode()).hexdigest() == expected_account
        or client.account_identity_digest != expected_account
        or execution_db_path == authority.db_path
    ):
        raise RuntimeError("multimedia visual generation configuration is invalid")
    _private_db_parent(execution_db_path)
    return MultimediaVisualGenerationRuntime(
        authority=authority, client=client, execution_db_path=execution_db_path,
        clock=lambda: datetime.now(UTC),
    )


multimedia_visual_generation_router = APIRouter(tags=["multimedia-visual-generation"])


@multimedia_visual_generation_router.post(
    "/assets/{asset_id}/visual-generations", response_model=VisualGenerationResponse
)
def submit_multimedia_visual_generation(
    asset_id: str,
    body: SubmitVisualGenerationBody,
    owner_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaVisualGenerationRuntime = Depends(
        get_multimedia_visual_generation_runtime
    ),
) -> VisualGenerationResponse:
    authority = runtime.authority
    try:
        result = submit_visual_generation(
            asset_id=asset_id, request_id=body.request_id,
            expected_revision_id=body.expected_revision_id, owner_id=owner_id,
            store=authority.store, registry=authority.registry, terms=authority.terms,
            db_path=runtime.execution_db_path, signing_key=authority.signing_key,
            client=runtime.client, now=runtime.clock(),
        )
    except VisualGenerationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="multimedia visual generation is unavailable") from exc
    return VisualGenerationResponse.model_validate(asdict(result))


@multimedia_visual_generation_router.post(
    "/assets/{asset_id}/visual-generations/{execution_id}/poll",
    response_model=VisualGenerationResponse,
)
def poll_multimedia_visual_generation(
    asset_id: str,
    execution_id: str,
    body: PollVisualGenerationBody,
    owner_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaVisualGenerationRuntime = Depends(
        get_multimedia_visual_generation_runtime
    ),
) -> VisualGenerationResponse:
    authority = runtime.authority
    try:
        result = poll_visual_generation(
            asset_id=asset_id, execution_id=execution_id,
            expected_revision_id=body.expected_revision_id, owner_id=owner_id,
            store=authority.store, db_path=runtime.execution_db_path,
            signing_key=authority.signing_key, client=runtime.client,
            now=runtime.clock(),
        )
    except VisualGenerationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return VisualGenerationResponse.model_validate(asdict(result))


def _private_db_parent(value: str) -> None:
    path = Path(value)
    try:
        metadata = path.parent.lstat()
    except OSError:
        raise RuntimeError("multimedia visual generation database path is invalid") from None
    if (
        not path.is_absolute() or path.is_symlink() or path.parent.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise RuntimeError("multimedia visual generation database path is invalid")


__all__ = [
    "MultimediaVisualGenerationRuntime", "PollVisualGenerationBody",
    "SubmitVisualGenerationBody", "VisualGenerationResponse",
    "get_multimedia_visual_generation_runtime", "multimedia_visual_generation_router",
    "multimedia_visual_generation_runtime_from_environment",
]
