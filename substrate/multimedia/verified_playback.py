"""Owner-gated, receipt-verified media delivery for multimedia assets."""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Literal

from .educational_video_receipt import EducationalVideoReceipt, receipt_file_path

_MAX_MEDIA_BYTES = 512 * 1024 * 1024
_MAX_RANGE_BYTES = 8 * 1024 * 1024


class VerifiedPlaybackError(RuntimeError):
    """Playback authority or media bytes failed verification."""


class UnsatisfiableMediaRange(VerifiedPlaybackError):
    def __init__(self, total: int) -> None:
        super().__init__("media range is unsatisfiable")
        self.total = total


@dataclass(frozen=True)
class PlaybackMediaMetadata:
    asset_id: str
    revision_id: str
    receipt_sha256: str
    duration_seconds: float
    video_sha256: str
    audio_sha256: str
    video_size_bytes: int
    audio_size_bytes: int
    width_px: int
    height_px: int
    chapter_ids: tuple[str, ...]


@dataclass(frozen=True)
class MediaByteRange:
    payload: bytes | None
    stream: BinaryIO | None
    start: int
    end: int
    total: int
    sha256: str
    receipt_sha256: str
    media_type: Literal["video/mp4", "audio/wav"]


@dataclass(frozen=True)
class VerifiedPlaybackRuntime:
    receipt_root: str
    receipt_key: bytes
    narration_key: bytes
    visual_key: bytes
    render_key: bytes

    def __post_init__(self) -> None:
        try:
            receipt_file_path(self.receipt_root, "configuration-probe", "revision-probe")
        except (OSError, ValueError) as exc:
            raise ValueError("playback receipt root is invalid") from exc

    def metadata(self, *, asset_id: str, revision_id: str) -> PlaybackMediaMetadata:
        receipt = self._receipt(asset_id, revision_id)
        receipt_sha256 = hashlib.sha256(receipt.to_json().encode("utf-8")).hexdigest()
        render = receipt.render.manifest
        narration = receipt.narration.manifest
        return PlaybackMediaMetadata(
            asset_id=asset_id,
            revision_id=revision_id,
            receipt_sha256=receipt_sha256,
            duration_seconds=render.duration_seconds,
            video_sha256=render.output_sha256,
            audio_sha256=narration.output_sha256,
            video_size_bytes=_verified_size(render.output_path, render.output_sha256),
            audio_size_bytes=_verified_size(narration.output_path, narration.output_sha256),
            width_px=render.width_px,
            height_px=render.height_px,
            chapter_ids=render.chapter_ids,
        )

    def read(
        self,
        *,
        asset_id: str,
        revision_id: str,
        kind: Literal["video", "audio"],
        range_header: str | None,
    ) -> MediaByteRange:
        receipt = self._receipt(asset_id, revision_id)
        receipt_sha256 = hashlib.sha256(receipt.to_json().encode("utf-8")).hexdigest()
        if kind == "video":
            path = receipt.render.manifest.output_path
            digest = receipt.render.manifest.output_sha256
            media_type: Literal["video/mp4", "audio/wav"] = "video/mp4"
        else:
            path = receipt.narration.manifest.output_path
            digest = receipt.narration.manifest.output_sha256
            media_type = "audio/wav"
        snapshot, size = _capture_verified_file(path, digest)
        close_snapshot = True
        try:
            start, end = _parse_range(range_header, size)
            if range_header is None and size > _MAX_RANGE_BYTES:
                payload = None
                stream: BinaryIO | None = snapshot
                close_snapshot = False
            else:
                snapshot.seek(start)
                payload = _read_stream_exact(snapshot, end - start + 1)
                stream = None
        finally:
            if close_snapshot:
                snapshot.close()
        return MediaByteRange(
            payload=payload,
            stream=stream,
            start=start,
            end=end,
            total=size,
            sha256=digest,
            receipt_sha256=receipt_sha256,
            media_type=media_type,
        )

    def _receipt(self, asset_id: str, revision_id: str) -> EducationalVideoReceipt:
        try:
            path = receipt_file_path(self.receipt_root, asset_id, revision_id)
            receipt = EducationalVideoReceipt.reopen_from_file(
                path,
                self.receipt_key,
                self.narration_key,
                self.visual_key,
                self.render_key,
            )
        except (OSError, ValueError, RuntimeError) as exc:
            raise VerifiedPlaybackError("verified playback is unavailable") from exc
        if receipt.asset_id != asset_id or receipt.revision_id != revision_id:
            raise VerifiedPlaybackError("verified playback identity conflicts")
        return receipt


def _verified_size(path: str, digest: str) -> int:
    descriptor, size, _identity = _open_verified(path, digest)
    os.close(descriptor)
    return size


def _capture_verified_file(path: str, expected_sha256: str) -> tuple[BinaryIO, int]:
    descriptor, size, identity = _open_private(path)
    snapshot = tempfile.TemporaryFile(mode="w+b")  # noqa: SIM115 - ownership transfers to caller
    try:
        hasher = hashlib.sha256()
        remaining = size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                raise VerifiedPlaybackError("media was truncated while reading")
            snapshot.write(chunk)
            hasher.update(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1) or hasher.hexdigest() != expected_sha256:
            raise VerifiedPlaybackError("media digest conflicts")
        after = os.fstat(descriptor)
        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) != identity:
            raise VerifiedPlaybackError("media changed while reading")
        _verify_path_identity(path, identity)
        snapshot.flush()
        snapshot.seek(0)
        return snapshot, size
    except BaseException:
        snapshot.close()
        raise
    finally:
        os.close(descriptor)


def _open_verified(path: str, expected_sha256: str) -> tuple[int, int, tuple[int, int, int, int, int]]:
    descriptor, size, identity = _open_private(path)
    try:
        hasher = hashlib.sha256()
        remaining = size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                raise VerifiedPlaybackError("media was truncated while verifying")
            hasher.update(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1) or hasher.hexdigest() != expected_sha256:
            raise VerifiedPlaybackError("media digest conflicts")
        after = os.fstat(descriptor)
        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) != identity:
            raise VerifiedPlaybackError("media changed while verifying")
        _verify_path_identity(path, identity)
        os.lseek(descriptor, 0, os.SEEK_SET)
        return descriptor, size, identity
    except BaseException:
        os.close(descriptor)
        raise


def _open_private(path: str) -> tuple[int, int, tuple[int, int, int, int, int]]:
    absolute = os.path.abspath(path)
    if absolute != os.path.realpath(path):
        raise VerifiedPlaybackError("media path is unsafe")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(absolute, flags)
    except OSError:
        raise VerifiedPlaybackError("media is unavailable") from None
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
            or not 0 < info.st_size <= _MAX_MEDIA_BYTES
        ):
            raise VerifiedPlaybackError("media is not private and bounded")
        identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        return descriptor, info.st_size, identity
    except BaseException:
        os.close(descriptor)
        raise


def _verify_path_identity(path: str, identity: tuple[int, int, int, int, int]) -> None:
    try:
        current = Path(os.path.abspath(path)).lstat()
    except OSError:
        raise VerifiedPlaybackError("media changed while verifying") from None
    if stat.S_ISLNK(current.st_mode) or (current.st_dev, current.st_ino) != identity[:2]:
        raise VerifiedPlaybackError("media changed while verifying")


def _parse_range(value: str | None, size: int) -> tuple[int, int]:
    if value is None:
        return 0, size - 1
    if not value.startswith("bytes=") or "," in value:
        raise UnsatisfiableMediaRange(size)
    bounds = value[6:].split("-", 1)
    if len(bounds) != 2:
        raise UnsatisfiableMediaRange(size)
    try:
        if not bounds[0]:
            length = int(bounds[1])
            if length <= 0:
                raise ValueError
            start, end = max(0, size - length), size - 1
        else:
            start = int(bounds[0])
            end = size - 1 if not bounds[1] else int(bounds[1])
    except ValueError:
        raise UnsatisfiableMediaRange(size) from None
    if start < 0 or start >= size or end < start:
        raise UnsatisfiableMediaRange(size)
    end = min(end, size - 1)
    if end - start + 1 > _MAX_RANGE_BYTES:
        end = start + _MAX_RANGE_BYTES - 1
    return start, end


def _read_exact(descriptor: int, count: int) -> bytes:
    chunks: list[bytes] = []
    remaining = count
    while remaining:
        chunk = os.read(descriptor, min(remaining, 1024 * 1024))
        if not chunk:
            raise VerifiedPlaybackError("media was truncated while reading")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _read_stream_exact(stream: BinaryIO, count: int) -> bytes:
    chunks: list[bytes] = []
    remaining = count
    while remaining:
        chunk = stream.read(min(remaining, 1024 * 1024))
        if not chunk:
            raise VerifiedPlaybackError("verified snapshot was truncated")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


__all__ = [
    "MediaByteRange",
    "PlaybackMediaMetadata",
    "UnsatisfiableMediaRange",
    "VerifiedPlaybackError",
    "VerifiedPlaybackRuntime",
]
