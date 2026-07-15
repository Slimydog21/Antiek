"""Authenticated server-derived Krea visual authorization route."""

from __future__ import annotations

import os
import stat
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from substrate.multimedia.read_model import MultimediaAssetStore
from substrate.multimedia.visual_authorization import (
    VisualAuthorizationError,
    VisualAuthorizationRegistry,
    VisualAuthorizationRequest,
    VisualAuthorizationTerms,
)

from .multimedia_narration_authorization_routes import AsyncNarrationAuthorizationResponse
from .multimedia_reconciliation_routes import authenticated_multimedia_operator


class VisualAuthorizationBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: str = Field(min_length=1, max_length=128)
    expected_revision_id: str = Field(min_length=1, max_length=128)
    chapter_id: str = Field(min_length=1, max_length=128)
    approved_ceiling_microdollars: int = Field(gt=0, le=9_223_372_036_854_775_807, strict=True)
    operator_acknowledged_spend: bool
    ttl_seconds: int = Field(default=900, ge=60, le=3600, strict=True)


class VisualQuoteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int
    quote_id: str
    model: str
    endpoint_capability: str
    catalog_version: str
    catalog_digest: str
    request_body_digest: str
    ceiling_microdollars: int
    pricing_source: str
    issued_at: str
    expires_at: str
    signature: str


class VisualAuthorizationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chapter_id: str
    scene_id: str
    width: int
    height: int
    seed: int
    request_body_digest: str
    quote: VisualQuoteResponse
    authorization: AsyncNarrationAuthorizationResponse


@dataclass(frozen=True, repr=False)
class MultimediaVisualAuthorizationRuntime:
    store: MultimediaAssetStore
    registry: VisualAuthorizationRegistry
    terms: VisualAuthorizationTerms
    db_path: str
    signing_key: bytes


def get_multimedia_visual_authorization_runtime() -> MultimediaVisualAuthorizationRuntime:
    raise HTTPException(status_code=503, detail="multimedia visual authorization is unavailable")


def multimedia_visual_authorization_runtime_from_environment(
    *, store: MultimediaAssetStore, environ: dict[str, str] | None = None
) -> MultimediaVisualAuthorizationRuntime | None:
    values = os.environ if environ is None else environ
    prefix = "ANTIEK_MULTIMEDIA_VISUAL_AUTH_"
    enabled = values.get(f"{prefix}ENABLED", "").strip().lower()
    fields = {
        "db_path": values.get(f"{prefix}DB_PATH", "").strip(),
        "signing_key": values.get(f"{prefix}SIGNING_KEY_HEX", "").strip(),
        "recovery_id": values.get(f"{prefix}RECOVERY_AUTHORITY_ID", "").strip(),
        "recovery_digest": values.get(f"{prefix}RECOVERY_VERIFICATION_KEY_DIGEST", "").strip(),
        "maximum_ceiling": values.get(f"{prefix}MAXIMUM_CEILING_MICRODOLLARS", "").strip(),
        "quote_ttl": values.get(f"{prefix}QUOTE_TTL_SECONDS", "").strip(),
    }
    if not enabled and not any(fields.values()):
        return None
    if enabled not in {"1", "true"} or any(not value for value in fields.values()):
        raise RuntimeError("multimedia visual authorization configuration is incomplete")
    try:
        signing_key = bytes.fromhex(fields["signing_key"])
        maximum_ceiling = int(fields["maximum_ceiling"])
        quote_ttl = int(fields["quote_ttl"])
    except ValueError:
        raise RuntimeError("multimedia visual authorization configuration is invalid") from None
    digest = fields["recovery_digest"]
    if (
        len(signing_key) < 32 or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
        or maximum_ceiling <= 0 or maximum_ceiling > 9_223_372_036_854_775_807
        or quote_ttl < 60 or quote_ttl > 3600
        or not fields["recovery_id"] or len(fields["recovery_id"]) > 128
    ):
        raise RuntimeError("multimedia visual authorization configuration is invalid")
    _private_db_parent(fields["db_path"])
    return MultimediaVisualAuthorizationRuntime(
        store=store,
        registry=VisualAuthorizationRegistry(db_path=fields["db_path"], signing_key=signing_key),
        terms=VisualAuthorizationTerms(
            recovery_authority_id=fields["recovery_id"],
            recovery_verification_key_digest=digest,
            maximum_ceiling_microdollars=maximum_ceiling,
            quote_ttl_seconds=quote_ttl,
        ),
        db_path=fields["db_path"],
        signing_key=signing_key,
    )


multimedia_visual_authorization_router = APIRouter(tags=["multimedia-visual-authorization"])


@multimedia_visual_authorization_router.post(
    "/assets/{asset_id}/visual-authorizations", response_model=VisualAuthorizationResponse
)
def authorize_multimedia_visual(
    asset_id: str,
    body: VisualAuthorizationBody,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaVisualAuthorizationRuntime = Depends(
        get_multimedia_visual_authorization_runtime
    ),
) -> VisualAuthorizationResponse:
    try:
        result = runtime.registry.authorize(
            asset_id, VisualAuthorizationRequest(**body.model_dump()),
            owner_id=operator_id, store=runtime.store, terms=runtime.terms,
            now=datetime.now(UTC),
        )
    except VisualAuthorizationError as exc:
        status = 404 if "unavailable" in str(exc) else 409
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="multimedia visual authorization is unavailable") from exc
    return VisualAuthorizationResponse(
        chapter_id=result.chapter_id, scene_id=result.scene_id,
        width=result.width, height=result.height, seed=result.seed,
        request_body_digest=result.request_body_digest,
        quote=VisualQuoteResponse.model_validate(asdict(result.quote)),
        authorization=AsyncNarrationAuthorizationResponse.model_validate(
            asdict(result.authorization)
        ),
    )


def _private_db_parent(value: str) -> None:
    path = Path(value)
    try:
        metadata = path.parent.lstat()
    except OSError:
        raise RuntimeError("multimedia visual authorization database path is invalid") from None
    if (
        not path.is_absolute() or path.is_symlink() or path.parent.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise RuntimeError("multimedia visual authorization database path is invalid")


__all__ = [
    "MultimediaVisualAuthorizationRuntime", "VisualAuthorizationBody",
    "VisualAuthorizationResponse", "get_multimedia_visual_authorization_runtime",
    "multimedia_visual_authorization_router",
    "multimedia_visual_authorization_runtime_from_environment",
]
