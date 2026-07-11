"""Authenticated issuance API for one-shot multimedia execution authority."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from substrate.multimedia.execution_authorization import (
    MAX_CENTS,
    MultimediaExecutionAuthorization,
)
from substrate.multimedia.execution_authorization_issuer import (
    ExecutionAuthorizationIssueConflict,
    ExecutionAuthorizationIssuer,
    ExecutionAuthorizationIssueRequest,
)
from substrate.multimedia.read_model import MultimediaAssetStore

_AUTHENTICATED_METHODS = frozenset(
    {
        "antiek_session_cookie",
        "cloudflare_access_email",
        "cloudflare_service_token",
        "bearer_token",
    }
)


class ExecutionAuthorizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    request_id: str = Field(min_length=1, max_length=256)
    revision_id: str = Field(min_length=1, max_length=256)
    provider: Literal["krea"] = "krea"
    route_policy: Literal["cheapest", "balanced", "highest_quality"]
    approved_ceiling_cents: int = Field(ge=1, le=MAX_CENTS, strict=True)
    ttl_seconds: int = Field(default=900, ge=60, le=3600, strict=True)


class ExecutionAuthorizationResponse(BaseModel):
    version: int
    authorization_id: str
    request_id: str
    operator_id: str
    asset_id: str
    revision_id: str
    provider: str
    route_policy: str
    approved_ceiling_cents: int
    issued_at: str
    expires_at: str
    signature: str


def create_multimedia_execution_router(
    *,
    db_path: str,
    signing_key: bytes,
    asset_store_root: str,
    clock: Callable[[], datetime] | None = None,
) -> APIRouter:
    issuer = ExecutionAuthorizationIssuer(db_path=db_path, signing_key=signing_key)
    store = MultimediaAssetStore(asset_store_root)
    read_clock = clock or (lambda: datetime.now(UTC))
    router = APIRouter(prefix="/multimedia", tags=["multimedia-execution"])

    @router.post(
        "/assets/{asset_id}/execution-authorizations",
        response_model=ExecutionAuthorizationResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def issue_authorization(
        asset_id: str,
        body: ExecutionAuthorizationRequest,
        request: Request,
    ) -> ExecutionAuthorizationResponse:
        operator_id = _operator_id(request)
        try:
            record = store.get(asset_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="multimedia asset not found",
            ) from exc
        if record.asset.revision_id != body.revision_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="authorization revision is not current",
            )
        if str(record.asset.status) != "ready":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="multimedia asset must have an approved dry run",
            )
        if record.asset.route_policy != body.route_policy:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="authorization route does not match the current asset",
            )
        if body.route_policy == "cheapest":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="cheapest route uses the local no-spend provider",
            )
        try:
            receipt = issuer.issue(
                ExecutionAuthorizationIssueRequest(
                    request_id=body.request_id,
                    operator_id=operator_id,
                    asset_id=asset_id,
                    revision_id=body.revision_id,
                    provider=body.provider,
                    route_policy=body.route_policy,
                    approved_ceiling_cents=body.approved_ceiling_cents,
                    ttl_seconds=body.ttl_seconds,
                ),
                now=read_clock(),
            )
        except ExecutionAuthorizationIssueConflict as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        return _response(receipt)

    return router


def _operator_id(request: Request) -> str:
    method = getattr(request.state, "auth_method", None)
    operator_id = getattr(request.state, "user_id", None)
    if method not in _AUTHENTICATED_METHODS or not isinstance(operator_id, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    operator_id = operator_id.strip()
    if not operator_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    return operator_id


def _response(receipt: MultimediaExecutionAuthorization) -> ExecutionAuthorizationResponse:
    return ExecutionAuthorizationResponse.model_validate(receipt.to_dict())


__all__ = [
    "ExecutionAuthorizationRequest",
    "ExecutionAuthorizationResponse",
    "create_multimedia_execution_router",
]
