"""Authenticated command route for exact educational-video production."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from substrate.multimedia.authorized_production_worker import (
    AuthorizedProductionError,
    AuthorizedProductionRequest,
    AuthorizedProductionRuntime,
    AuthorizedProductionUnavailable,
    ChapterNarrationAuthority,
    produce_authorized_multimedia,
)
from substrate.multimedia.execution_authorization import (
    ExecutionAuthorizationIntegrityError,
    MultimediaExecutionAuthorizationV2,
)
from substrate.multimedia.read_model import MultimediaAssetRecord

from .multimedia_narration_authorization_routes import AsyncNarrationAuthorizationResponse
from .multimedia_reconciliation_routes import authenticated_multimedia_operator

_LOG = logging.getLogger(__name__)


class ChapterNarrationAuthorityBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    chapter_id: str = Field(min_length=1, max_length=128)
    authorization: AsyncNarrationAuthorizationResponse


class AuthorizedProductionBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expected_revision_id: str = Field(min_length=1, max_length=128)
    chapter_authorities: tuple[ChapterNarrationAuthorityBody, ...] = Field(
        min_length=1, max_length=64
    )
    voice: str = Field(default="narrator", min_length=1, max_length=128)
    speed: float = Field(default=1.0, ge=0.25, le=4)
    sample_rate_hz: int = Field(default=24_000, ge=8_000, le=48_000, strict=True)
    channels: Literal[1, 2] = 1


def get_multimedia_production_worker_runtime() -> AuthorizedProductionRuntime:
    raise HTTPException(status_code=503, detail="multimedia production worker is unavailable")


multimedia_production_worker_router = APIRouter(tags=["multimedia-production"])


@multimedia_production_worker_router.post(
    "/assets/{asset_id}/production", response_model=MultimediaAssetRecord
)
def produce_multimedia_asset(
    asset_id: str,
    body: AuthorizedProductionBody,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: AuthorizedProductionRuntime = Depends(
        get_multimedia_production_worker_runtime
    ),
) -> MultimediaAssetRecord:
    try:
        request = AuthorizedProductionRequest(
            expected_revision_id=body.expected_revision_id,
            chapter_authorities=tuple(
                ChapterNarrationAuthority(
                    chapter_id=row.chapter_id,
                    authorization=MultimediaExecutionAuthorizationV2.from_dict(
                        row.authorization.model_dump()
                    ),
                )
                for row in body.chapter_authorities
            ),
            voice=body.voice,
            speed=body.speed,
            sample_rate_hz=body.sample_rate_hz,
            channels=body.channels,
        )
        return produce_authorized_multimedia(
            asset_id, request, owner_id=operator_id, runtime=runtime
        )
    except AuthorizedProductionUnavailable as exc:
        raise HTTPException(
            status_code=404, detail="multimedia production authority is unavailable"
        ) from exc
    except AuthorizedProductionError as exc:
        raise HTTPException(
            status_code=409, detail="multimedia production authority conflicts"
        ) from exc
    except ExecutionAuthorizationIntegrityError as exc:
        raise HTTPException(
            status_code=409, detail="multimedia production authority conflicts"
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=409, detail="multimedia production authority conflicts"
        ) from exc
    except RuntimeError as exc:
        _LOG.exception("multimedia production runtime failed")
        raise HTTPException(
            status_code=503, detail="multimedia production worker is unavailable"
        ) from exc


__all__ = [
    "AuthorizedProductionBody",
    "ChapterNarrationAuthorityBody",
    "get_multimedia_production_worker_runtime",
    "multimedia_production_worker_router",
]
