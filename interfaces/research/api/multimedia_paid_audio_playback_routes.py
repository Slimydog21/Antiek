"""Authenticated, receipt-verified playback for paid audio lessons."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import BinaryIO

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from substrate.multimedia.read_model import MultimediaAudioProductionLink
from substrate.multimedia.verified_audio_playback import AudioPlaybackMetadata
from substrate.multimedia.verified_paid_audio_playback import VerifiedPaidAudioPlaybackRuntime
from substrate.multimedia.verified_playback import UnsatisfiableMediaRange, VerifiedPlaybackError

from .multimedia_local_audible_routes import AudioChapterPlaybackResponse
from .multimedia_reconciliation_routes import authenticated_multimedia_operator


class PaidAudioPlaybackResponse(BaseModel):
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
    learned_claims: tuple[dict[str, object], ...]
    chapters: tuple[AudioChapterPlaybackResponse, ...]
    audio_url: str


@dataclass(frozen=True)
class PaidAudioPlaybackRouteRuntime:
    playback: VerifiedPaidAudioPlaybackRuntime
    asset_authority_resolver: Callable[[str, str], tuple[str, MultimediaAudioProductionLink | None]]


def get_multimedia_paid_audio_playback_runtime() -> PaidAudioPlaybackRouteRuntime:
    raise HTTPException(status_code=503, detail="paid audio playback is unavailable")


multimedia_paid_audio_playback_router = APIRouter(tags=["multimedia-paid-audio-playback"])


@multimedia_paid_audio_playback_router.get(
    "/assets/{asset_id}/audio-playback", response_model=PaidAudioPlaybackResponse
)
def get_paid_audio_playback(
    asset_id: str,
    revision_id: str,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: PaidAudioPlaybackRouteRuntime = Depends(get_multimedia_paid_audio_playback_runtime),
) -> PaidAudioPlaybackResponse:
    owner_digest, link = _registered(runtime, asset_id, revision_id, operator_id)
    try:
        metadata = runtime.playback.metadata(
            asset_id=asset_id, revision_id=revision_id, owner_digest=owner_digest
        )
    except VerifiedPlaybackError as exc:
        raise HTTPException(
            status_code=404, detail="verified paid audio playback is unavailable"
        ) from exc
    _assert_link(metadata, link)
    values = dict(metadata.__dict__)
    values["learned_claims"] = tuple(claim.__dict__ for claim in metadata.learned_claims)
    values["chapters"] = tuple(chapter.__dict__ for chapter in metadata.chapters)
    return PaidAudioPlaybackResponse(
        **values,
        audio_url=f"/multimedia/assets/{asset_id}/audio-playback/{revision_id}/audio",
    )


@multimedia_paid_audio_playback_router.get("/assets/{asset_id}/audio-playback/{revision_id}/audio")
def stream_paid_audio_playback(
    asset_id: str,
    revision_id: str,
    range_header: str | None = Header(default=None, alias="Range"),
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: PaidAudioPlaybackRouteRuntime = Depends(get_multimedia_paid_audio_playback_runtime),
) -> Response:
    owner_digest, link = _registered(runtime, asset_id, revision_id, operator_id)
    try:
        metadata = runtime.playback.metadata(
            asset_id=asset_id, revision_id=revision_id, owner_digest=owner_digest
        )
        _assert_link(metadata, link)
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
            status_code=404, detail="verified paid audio playback is unavailable"
        ) from exc
    if media.receipt_sha256 != link.receipt_sha256 or media.sha256 != link.audio_sha256:
        if media.stream is not None:
            media.stream.close()
        raise HTTPException(status_code=409, detail="paid audio production registration conflicts")
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
            media_type=media.media_type,
            headers=headers,
        )
    return Response(
        content=media.payload,
        status_code=206 if partial else 200,
        media_type=media.media_type,
        headers=headers,
    )


def _registered(
    runtime: PaidAudioPlaybackRouteRuntime, asset_id: str, revision_id: str, operator_id: str
) -> tuple[str, MultimediaAudioProductionLink]:
    try:
        current, link = runtime.asset_authority_resolver(asset_id, operator_id)
    except (KeyError, LookupError, ValueError) as exc:
        raise HTTPException(
            status_code=404, detail="verified paid audio playback is unavailable"
        ) from exc
    if current != revision_id:
        raise HTTPException(status_code=409, detail="paid audio playback revision is not current")
    if link is None or link.asset_id != asset_id or link.revision_id != revision_id:
        raise HTTPException(status_code=404, detail="verified paid audio playback is unavailable")
    return link.owner_identity_digest, link


def _assert_link(metadata: AudioPlaybackMetadata, link: MultimediaAudioProductionLink) -> None:
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
        raise HTTPException(status_code=409, detail="paid audio production registration conflicts")


def _stream_and_close(stream: BinaryIO) -> Iterator[bytes]:
    try:
        while chunk := stream.read(1024 * 1024):
            yield chunk
    finally:
        stream.close()
