"""Authenticated, research-only HTTP surface for licensed derivation."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from substrate.licensed_access import (
    Deriver,
    LicensedAccessConflict,
    LicensedAccessDenied,
    LicensedAccessUnavailable,
    TollBitLicensedAccess,
)

_AUTH_METHODS = {"antiek_session_cookie", "cloudflare_access_email",
                 "cloudflare_service_token", "bearer_token"}


class LicensedResearchRequest(BaseModel):
    url: str = Field(min_length=8, max_length=4096)
    max_price_micros: int = Field(ge=0, le=1_000_000_000, strict=True)


class LicensedResearchResponse(BaseModel):
    transaction_id: str
    idempotency_key: str
    request_digest: str
    owner_identity_digest: str
    canonical_url: str
    content_digest: str
    license_type: str
    license_id: str
    permission: str
    price_micros: int
    currency: str
    citation: str
    snippet: str
    summary: str
    created_at: str
    receipt_mac: str


def _owner(request: Request) -> str:
    method = getattr(request.state, "auth_method", None)
    owner = getattr(request.state, "user_id", None)
    if method not in _AUTH_METHODS or not isinstance(owner, str) or not owner.strip():
        raise HTTPException(status_code=401, detail="licensed research requires authentication")
    return owner.strip()


def create_licensed_research_router(
    *, service: TollBitLicensedAccess,
    deriver: Deriver,
) -> APIRouter:
    router = APIRouter(prefix="/research/licensed", tags=["licensed-research"])

    @router.post("/summarize", response_model=LicensedResearchResponse)
    def summarize(
        request: Request,
        body: LicensedResearchRequest,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> LicensedResearchResponse:
        try:
            receipt = service.acquire(
                owner_id=_owner(request), url=body.url,
                max_price_micros=body.max_price_micros,
                idempotency_key=idempotency_key, deriver=deriver,
            )
            # Every MAC-covered field is returned, making the signed receipt
            # independently reconstructable and verifiable.
            result: LicensedResearchResponse = LicensedResearchResponse.model_validate(
                receipt.__dict__
            )
            return result
        except LicensedAccessConflict as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="licensed operation conflict") from exc
        except LicensedAccessDenied as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="licensed access denied") from exc
        except LicensedAccessUnavailable as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                detail="licensed research provider unavailable") from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail="invalid licensed research request") from exc

    return router


__all__ = ["LicensedResearchRequest", "LicensedResearchResponse",
           "create_licensed_research_router"]
