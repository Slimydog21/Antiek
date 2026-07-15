"""Authenticated server-derived chapter narration authorization."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from substrate.multimedia.execution_authorization import MultimediaExecutionAuthorizationV2
from substrate.multimedia.execution_authorization_issuer import ExecutionAuthorizationIssuer
from substrate.multimedia.narration_authorization import (
    NarrationAuthorizationError,
    NarrationAuthorizationRequest,
    TrustedNarrationTerms,
    authorize_multimedia_chapter_narration,
)
from substrate.multimedia.read_model import MultimediaAssetRecord, MultimediaAssetStore

from .multimedia_reconciliation_routes import authenticated_multimedia_operator


class NarrationAuthorizationBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    request_id: str = Field(min_length=1, max_length=256)
    expected_revision_id: str = Field(min_length=1, max_length=128)
    chapter_id: str = Field(min_length=1, max_length=128)
    approved_ceiling_microdollars: int = Field(gt=0, le=9_223_372_036_854_775_807, strict=True)
    operator_acknowledged_spend: bool
    voice: str = Field(default="narrator", min_length=1, max_length=128)
    speed: float = Field(default=1.0, ge=0.25, le=4)
    sample_rate_hz: int = Field(default=24_000, ge=8_000, le=48_000, strict=True)
    channels: Literal[1, 2] = 1
    ttl_seconds: int = Field(default=900, ge=60, le=3600, strict=True)


class AsyncNarrationAuthorizationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    authorization_id: str
    request_id: str
    operator_id: str
    asset_id: str
    revision_id: str
    provider: str
    route_policy: str
    model: str
    endpoint_capability: str
    catalog_version: str
    catalog_digest: str
    quote_id: str
    quote_expires_at: str
    recovery_authority_id: str
    recovery_verification_key_digest: str
    approved_ceiling_microdollars: int
    request_body_digest: str
    issued_at: str
    expires_at: str
    signature: str


class NarrationAuthorizationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_id: str
    child_revision_id: str
    request_body_digest: str
    authorization: AsyncNarrationAuthorizationResponse


@dataclass(frozen=True)
class MultimediaNarrationAuthorizationRuntime:
    store: MultimediaAssetStore
    issuer: ExecutionAuthorizationIssuer
    terms_resolver: Callable[[MultimediaAssetRecord, str], TrustedNarrationTerms]
    clock: Callable[[], datetime]
    db_path: str | None = None


def get_multimedia_narration_authorization_runtime() -> MultimediaNarrationAuthorizationRuntime:
    raise HTTPException(status_code=503, detail="multimedia narration authorization is unavailable")


def multimedia_narration_authorization_runtime_from_environment(
    *,
    store: MultimediaAssetStore,
    environ: dict[str, str] | None = None,
) -> MultimediaNarrationAuthorizationRuntime | None:
    values = os.environ if environ is None else environ
    prefix = "ANTIEK_MULTIMEDIA_NARRATION_AUTH_"
    enabled = values.get(f"{prefix}ENABLED", "").strip().lower()
    fields = {
        "db_path": values.get(f"{prefix}DB_PATH", "").strip(),
        "signing_key": values.get(f"{prefix}SIGNING_KEY_HEX", "").strip(),
        "provider": values.get(f"{prefix}PROVIDER", "").strip(),
        "model": values.get(f"{prefix}MODEL", "").strip(),
        "catalog_version": values.get(f"{prefix}CATALOG_VERSION", "").strip(),
        "catalog_digest": values.get(f"{prefix}CATALOG_DIGEST", "").strip(),
        "quote_id": values.get(f"{prefix}QUOTE_ID", "").strip(),
        "quote_ttl": values.get(f"{prefix}QUOTE_TTL_SECONDS", "").strip(),
        "recovery_id": values.get(f"{prefix}RECOVERY_AUTHORITY_ID", "").strip(),
        "recovery_digest": values.get(f"{prefix}RECOVERY_VERIFICATION_KEY_DIGEST", "").strip(),
        "maximum_ceiling": values.get(f"{prefix}MAXIMUM_CEILING_MICRODOLLARS", "").strip(),
    }
    if not enabled and not any(fields.values()):
        return None
    if enabled not in {"1", "true"} or any(not value for value in fields.values()):
        raise RuntimeError("multimedia narration authorization configuration is incomplete")
    try:
        signing_key = bytes.fromhex(fields["signing_key"])
        quote_ttl = int(fields["quote_ttl"])
        maximum_ceiling = int(fields["maximum_ceiling"])
    except ValueError:
        raise RuntimeError("multimedia narration authorization configuration is invalid") from None
    if (
        len(signing_key) < 32
        or len(fields["catalog_digest"]) != 64
        or len(fields["recovery_digest"]) != 64
        or any(character not in "0123456789abcdefABCDEF" for character in fields["catalog_digest"])
        or any(character not in "0123456789abcdefABCDEF" for character in fields["recovery_digest"])
        or quote_ttl < 60
        or quote_ttl > 3600
        or maximum_ceiling <= 0
        or maximum_ceiling > 9_223_372_036_854_775_807
    ):
        raise RuntimeError("multimedia narration authorization configuration is invalid")
    terms = TrustedNarrationTerms(
        provider=fields["provider"],
        model=fields["model"],
        endpoint_capability="text-to-speech",
        catalog_version=fields["catalog_version"],
        catalog_digest=fields["catalog_digest"],
        quote_id=fields["quote_id"],
        quote_ttl_seconds=quote_ttl,
        recovery_authority_id=fields["recovery_id"],
        recovery_verification_key_digest=fields["recovery_digest"],
        maximum_ceiling_microdollars=maximum_ceiling,
    )
    return MultimediaNarrationAuthorizationRuntime(
        store=store,
        issuer=ExecutionAuthorizationIssuer(db_path=fields["db_path"], signing_key=signing_key),
        terms_resolver=lambda _record, _chapter_id: terms,
        clock=lambda: datetime.now(UTC),
        db_path=fields["db_path"],
    )


multimedia_narration_authorization_router = APIRouter(tags=["multimedia-narration"])


@multimedia_narration_authorization_router.post(
    "/assets/{asset_id}/narration-authorizations",
    response_model=NarrationAuthorizationResponse,
)
def authorize_chapter_narration(
    asset_id: str,
    body: NarrationAuthorizationBody,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaNarrationAuthorizationRuntime = Depends(
        get_multimedia_narration_authorization_runtime
    ),
) -> NarrationAuthorizationResponse:
    try:
        result = authorize_multimedia_chapter_narration(
            asset_id,
            NarrationAuthorizationRequest(**body.model_dump()),
            owner_id=operator_id,
            store=runtime.store,
            terms_resolver=runtime.terms_resolver,
            issuer=runtime.issuer,
            clock=runtime.clock,
            db_path=runtime.db_path,
        )
    except NarrationAuthorizationError as exc:
        detail = str(exc)
        status_code = 404 if "unavailable" in detail else 409
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503, detail="multimedia narration authorization is unavailable"
        ) from exc
    authorization: MultimediaExecutionAuthorizationV2 = result.authorization
    return NarrationAuthorizationResponse(
        chapter_id=result.prepared.chapter_id,
        child_revision_id=result.prepared.revision_id,
        request_body_digest=result.prepared.body_digest,
        authorization=AsyncNarrationAuthorizationResponse.model_validate(asdict(authorization)),
    )


__all__ = [
    "MultimediaNarrationAuthorizationRuntime",
    "AsyncNarrationAuthorizationResponse",
    "NarrationAuthorizationBody",
    "NarrationAuthorizationResponse",
    "get_multimedia_narration_authorization_runtime",
    "multimedia_narration_authorization_router",
    "multimedia_narration_authorization_runtime_from_environment",
]
