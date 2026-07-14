"""Authenticated commands and playback for cheapest local audible experiences."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from typing import BinaryIO, Literal, TypeVar

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from substrate.multimedia.local_audible_workstation import (
    LocalAudiblePreparedSet,
    LocalAudibleWorkstationError,
)
from substrate.multimedia.read_model import MultimediaAudioProductionLink
from substrate.multimedia.verified_playback import (
    UnsatisfiableMediaRange,
    VerifiedPlaybackError,
)

from .multimedia_local_audible_runtime import MultimediaLocalAudibleRuntime
from .multimedia_reconciliation_routes import authenticated_multimedia_operator

_LOG = logging.getLogger(__name__)
T = TypeVar("T")


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LocalAudiblePrepareBody(_Body):
    expected_revision_id: str = Field(min_length=1, max_length=128)


class LocalAudibleCommandBody(LocalAudiblePrepareBody):
    set_id: str = Field(pattern=r"^mmlocalaudibleset_[0-9a-f]{64}$")


class LocalAudibleCapabilityResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    available: bool
    reason: Literal["ready", "unavailable"]
    route_policy: Literal["cheapest"] = "cheapest"
    cost_usd: Literal[0] = 0


class LocalAudibleLearnedClaimResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    chapter_id: str
    claim_text: str
    source_count: int
    follow_up_prompt: str


class LocalAudiblePlaybackResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    asset_id: str
    revision_id: str
    receipt_sha256: str
    audio_sha256: str
    audio_size_bytes: int
    duration_seconds: float
    chapter_ids: tuple[str, ...]
    retention_marker_count: int
    learned_claim_count: int
    source_count: int
    learned_claims: tuple[LocalAudibleLearnedClaimResponse, ...]
    audio_url: str


def get_multimedia_local_audible_runtime_optional() -> MultimediaLocalAudibleRuntime | None:
    return None


def get_multimedia_local_audible_runtime() -> MultimediaLocalAudibleRuntime:
    runtime = get_multimedia_local_audible_runtime_optional()
    if runtime is None:
        raise HTTPException(status_code=503, detail="local audible runtime is unavailable")
    return runtime


multimedia_local_audible_router = APIRouter(tags=["multimedia-local-audible"])


@multimedia_local_audible_router.get(
    "/local-audible/capability", response_model=LocalAudibleCapabilityResponse
)
def get_local_audible_capability(
    _operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaLocalAudibleRuntime | None = Depends(
        get_multimedia_local_audible_runtime_optional
    ),
) -> LocalAudibleCapabilityResponse:
    return LocalAudibleCapabilityResponse(
        available=runtime is not None,
        reason="ready" if runtime is not None else "unavailable",
    )


@multimedia_local_audible_router.post(
    "/assets/{asset_id}/local-audible/prepare", response_model=LocalAudiblePreparedSet
)
def prepare_local_audible(
    asset_id: str,
    body: LocalAudiblePrepareBody,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaLocalAudibleRuntime = Depends(get_multimedia_local_audible_runtime),
) -> LocalAudiblePreparedSet:
    return _command(
        lambda: runtime.workstation.prepare(
            asset_id, body.expected_revision_id, owner_id=operator_id
        )
    )


@multimedia_local_audible_router.get(
    "/assets/{asset_id}/local-audible/{revision_id}/{set_id}",
    response_model=LocalAudiblePreparedSet,
)
def inspect_local_audible(
    asset_id: str,
    revision_id: str,
    set_id: str,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaLocalAudibleRuntime = Depends(get_multimedia_local_audible_runtime),
) -> LocalAudiblePreparedSet:
    return _command(
        lambda: runtime.workstation.inspect(asset_id, revision_id, set_id, owner_id=operator_id)
    )


@multimedia_local_audible_router.post(
    "/assets/{asset_id}/local-audible/produce", response_model=LocalAudiblePreparedSet
)
def produce_local_audible(
    asset_id: str,
    body: LocalAudibleCommandBody,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaLocalAudibleRuntime = Depends(get_multimedia_local_audible_runtime),
) -> LocalAudiblePreparedSet:
    return _command(
        lambda: runtime.workstation.produce(
            asset_id, body.expected_revision_id, body.set_id, owner_id=operator_id
        )
    )


@multimedia_local_audible_router.post(
    "/assets/{asset_id}/local-audible/recover", response_model=LocalAudiblePreparedSet
)
def recover_local_audible(
    asset_id: str,
    body: LocalAudibleCommandBody,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaLocalAudibleRuntime = Depends(get_multimedia_local_audible_runtime),
) -> LocalAudiblePreparedSet:
    return _command(
        lambda: runtime.workstation.recover(
            asset_id, body.expected_revision_id, body.set_id, owner_id=operator_id
        )
    )


@multimedia_local_audible_router.get(
    "/assets/{asset_id}/local-audible/playback",
    response_model=LocalAudiblePlaybackResponse,
)
def get_local_audible_playback(
    asset_id: str,
    revision_id: str,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaLocalAudibleRuntime = Depends(get_multimedia_local_audible_runtime),
) -> LocalAudiblePlaybackResponse:
    owner_digest, link = _registered(runtime, asset_id, revision_id, operator_id)
    try:
        metadata = runtime.playback.metadata(
            asset_id=asset_id, revision_id=revision_id, owner_digest=owner_digest
        )
    except VerifiedPlaybackError as exc:
        raise HTTPException(
            status_code=404, detail="verified local audible playback is unavailable"
        ) from exc
    if (
        metadata.receipt_sha256 != link.receipt_sha256
        or metadata.audio_sha256 != link.audio_sha256
        or metadata.audio_size_bytes != link.audio_size_bytes
        or metadata.duration_seconds != link.duration_seconds
        or metadata.chapter_ids != link.chapter_ids
        or metadata.retention_marker_count != link.retention_marker_count
        or metadata.learned_claim_count != link.learned_claim_count
        or metadata.source_count != link.source_count
    ):
        raise HTTPException(status_code=409, detail="local audible registration conflicts")
    values = dict(metadata.__dict__)
    values["learned_claims"] = tuple(claim.__dict__ for claim in metadata.learned_claims)
    return LocalAudiblePlaybackResponse(
        **values,
        audio_url=f"/multimedia/assets/{asset_id}/local-audible/playback/{revision_id}/audio",
    )


@multimedia_local_audible_router.get(
    "/assets/{asset_id}/local-audible/playback/{revision_id}/audio"
)
def stream_local_audible_playback(
    asset_id: str,
    revision_id: str,
    range_header: str | None = Header(default=None, alias="Range"),
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaLocalAudibleRuntime = Depends(get_multimedia_local_audible_runtime),
) -> Response:
    owner_digest, link = _registered(runtime, asset_id, revision_id, operator_id)
    try:
        media = runtime.playback.read(
            asset_id=asset_id,
            revision_id=revision_id,
            owner_digest=owner_digest,
            range_header=range_header,
        )
    except UnsatisfiableMediaRange as exc:
        return Response(
            status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE,
            headers={
                "Content-Range": f"bytes */{exc.total}",
                "Cache-Control": "private, no-store",
            },
        )
    except VerifiedPlaybackError as exc:
        raise HTTPException(
            status_code=404, detail="verified local audible playback is unavailable"
        ) from exc
    if media.receipt_sha256 != link.receipt_sha256 or media.sha256 != link.audio_sha256:
        if media.stream is not None:
            media.stream.close()
        raise HTTPException(status_code=409, detail="local audible registration conflicts")
    partial = range_header is not None or media.start != 0 or media.end != media.total - 1
    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, no-store",
        "Content-Length": str(media.end - media.start + 1),
        "ETag": f'"sha256-{media.sha256}"',
        "X-Content-Type-Options": "nosniff",
    }
    if partial:
        headers["Content-Range"] = f"bytes {media.start}-{media.end}/{media.total}"
    if media.stream is not None:
        return StreamingResponse(
            _stream_and_close(media.stream),
            status_code=200,
            media_type="audio/wav",
            headers=headers,
        )
    return Response(
        content=media.payload,
        status_code=206 if partial else 200,
        media_type="audio/wav",
        headers=headers,
    )


def _registered(
    runtime: MultimediaLocalAudibleRuntime,
    asset_id: str,
    revision_id: str,
    operator_id: str,
) -> tuple[str, MultimediaAudioProductionLink]:
    try:
        record = runtime.store.get(asset_id, owner_id=operator_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=404, detail="verified local audible playback is unavailable"
        ) from exc
    link = record.audio_production_link
    if record.asset.revision_id != revision_id:
        raise HTTPException(status_code=409, detail="local audible revision is not current")
    if link is None or link.asset_id != asset_id or link.revision_id != revision_id:
        raise HTTPException(
            status_code=404, detail="verified local audible playback is unavailable"
        )
    return str(record.asset.owner_user_id), link


def _command(operation: Callable[[], T]) -> T:  # noqa: UP047 - Python 3.11 support
    try:
        return operation()
    except LocalAudibleWorkstationError as exc:
        unavailable = "unavailable" in str(exc)
        raise HTTPException(
            status_code=404 if unavailable else 409,
            detail=(
                "local audible authority is unavailable"
                if unavailable
                else "local audible authority conflicts"
            ),
        ) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=409, detail="local audible authority conflicts") from exc
    except RuntimeError as exc:
        _LOG.exception("local audible runtime failed")
        raise HTTPException(status_code=503, detail="local audible runtime is unavailable") from exc


def _stream_and_close(stream: BinaryIO) -> Iterator[bytes]:
    try:
        while chunk := stream.read(1024 * 1024):
            yield chunk
    finally:
        stream.close()


__all__ = [
    "LocalAudibleCapabilityResponse",
    "LocalAudibleCommandBody",
    "LocalAudiblePlaybackResponse",
    "LocalAudiblePrepareBody",
    "get_multimedia_local_audible_runtime",
    "get_multimedia_local_audible_runtime_optional",
    "multimedia_local_audible_router",
]
