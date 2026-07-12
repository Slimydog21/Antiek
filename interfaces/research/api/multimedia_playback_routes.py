"""Authenticated delivery of receipt-verified multimedia media bytes."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import BinaryIO

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from substrate.multimedia.verified_playback import (
    UnsatisfiableMediaRange,
    VerifiedPlaybackError,
    VerifiedPlaybackRuntime,
)

from .multimedia_reconciliation_routes import authenticated_multimedia_operator


class MultimediaPlaybackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str
    revision_id: str
    duration_seconds: float
    video_sha256: str
    audio_sha256: str
    video_size_bytes: int
    audio_size_bytes: int
    width_px: int
    height_px: int
    chapter_ids: tuple[str, ...]
    video_url: str
    audio_url: str


@dataclass(frozen=True)
class MultimediaPlaybackRouteRuntime:
    playback: VerifiedPlaybackRuntime
    asset_revision_resolver: Callable[[str, str], str]


def get_multimedia_playback_runtime() -> MultimediaPlaybackRouteRuntime:
    raise HTTPException(status_code=503, detail="multimedia playback is unavailable")


def multimedia_playback_runtime_from_environment(
    environ: dict[str, str] | None = None,
) -> MultimediaPlaybackRouteRuntime | None:
    values = os.environ if environ is None else environ
    enabled = values.get("ANTIEK_MULTIMEDIA_PLAYBACK_ENABLED", "").strip().lower()
    root = values.get("ANTIEK_MULTIMEDIA_VIDEO_RECEIPT_ROOT", "").strip()
    key_names = (
        "ANTIEK_MULTIMEDIA_VIDEO_RECEIPT_KEY_HEX",
        "ANTIEK_MULTIMEDIA_NARRATION_KEY_HEX",
        "ANTIEK_MULTIMEDIA_VISUAL_KEY_HEX",
        "ANTIEK_MULTIMEDIA_RENDER_KEY_HEX",
    )
    raw_keys = tuple(values.get(name, "").strip() for name in key_names)
    if not any((enabled, root, *raw_keys)):
        return None
    if enabled not in {"1", "true"} or not root or any(not value for value in raw_keys):
        raise RuntimeError("multimedia playback configuration is incomplete")
    try:
        keys = tuple(bytes.fromhex(value) for value in raw_keys)
    except ValueError:
        raise RuntimeError("multimedia playback configuration is invalid") from None
    if any(len(key) < 32 for key in keys):
        raise RuntimeError("multimedia playback configuration is invalid")
    playback = VerifiedPlaybackRuntime(root, *keys)
    return MultimediaPlaybackRouteRuntime(
        playback=playback,
        asset_revision_resolver=lambda _asset_id, _operator_id: (_ for _ in ()).throw(
            LookupError("multimedia asset is unavailable")
        ),
    )


multimedia_playback_router = APIRouter(tags=["multimedia-playback"])


@multimedia_playback_router.get(
    "/assets/{asset_id}/playback",
    response_model=MultimediaPlaybackResponse,
)
def get_multimedia_playback(
    asset_id: str,
    revision_id: str,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaPlaybackRouteRuntime = Depends(get_multimedia_playback_runtime),
) -> MultimediaPlaybackResponse:
    _assert_current(runtime, asset_id, revision_id, operator_id)
    try:
        metadata = runtime.playback.metadata(asset_id=asset_id, revision_id=revision_id)
    except VerifiedPlaybackError as exc:
        raise HTTPException(status_code=404, detail="verified multimedia playback is unavailable") from exc
    base = f"/multimedia/assets/{asset_id}/playback/{revision_id}"
    return MultimediaPlaybackResponse(
        **metadata.__dict__,
        video_url=f"{base}/video",
        audio_url=f"{base}/audio",
    )


@multimedia_playback_router.get("/assets/{asset_id}/playback/{revision_id}/{kind}")
def stream_multimedia_playback(
    asset_id: str,
    revision_id: str,
    kind: str,
    range_header: str | None = Header(default=None, alias="Range"),
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: MultimediaPlaybackRouteRuntime = Depends(get_multimedia_playback_runtime),
) -> Response:
    if kind not in {"video", "audio"}:
        raise HTTPException(status_code=404, detail="verified multimedia playback is unavailable")
    _assert_current(runtime, asset_id, revision_id, operator_id)
    try:
        media = runtime.playback.read(
            asset_id=asset_id,
            revision_id=revision_id,
            kind=kind,  # type: ignore[arg-type]
            range_header=range_header,
        )
    except UnsatisfiableMediaRange as exc:
        return Response(
            status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE,
            headers={"Content-Range": f"bytes */{exc.total}", "Cache-Control": "private, no-store"},
        )
    except VerifiedPlaybackError as exc:
        raise HTTPException(status_code=404, detail="verified multimedia playback is unavailable") from exc
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
    return Response(content=media.payload, status_code=206 if partial else 200, media_type=media.media_type, headers=headers)


def _stream_and_close(stream: BinaryIO) -> Iterator[bytes]:
    try:
        while chunk := stream.read(1024 * 1024):
            yield chunk
    finally:
        stream.close()


def _assert_current(
    runtime: MultimediaPlaybackRouteRuntime,
    asset_id: str,
    revision_id: str,
    operator_id: str,
) -> None:
    try:
        current = runtime.asset_revision_resolver(asset_id, operator_id)
    except (KeyError, LookupError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="verified multimedia playback is unavailable") from exc
    if current != revision_id:
        raise HTTPException(status_code=409, detail="multimedia playback revision is not current")


__all__ = [
    "MultimediaPlaybackResponse",
    "MultimediaPlaybackRouteRuntime",
    "get_multimedia_playback_runtime",
    "multimedia_playback_router",
    "multimedia_playback_runtime_from_environment",
]
