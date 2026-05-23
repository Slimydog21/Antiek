"""Video frame extraction (Sprint 30+ thread 4).

Acquisition adapter that takes a video source (file path or URL),
extracts frames at specified timestamps, and emits
``visual.frame_identified`` events. The visual bridge handler at
``interfaces/research/api/visual.py`` then dispatches the role
against each extracted frame.

Frame-picking strategies (caller selects):

  - "uniform" — sample every N seconds (default 30s).
  - "from_timestamps" — caller supplies explicit timestamps_ms.
  - "scene_change" — DEFERRED (needs a scene-change detection
    pass; out of substrate scope).

Backend protocol:

  - Production wires ``FfmpegFrameExtractor`` which shells out to
    ffmpeg.
  - Tests wire ``StubFrameExtractor`` which returns synthetic
    frame dicts (no real ffmpeg call).

The substrate stays ffmpeg-agnostic at the protocol layer; the
adapter handles binary discovery + invocation.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from typing import Optional, Protocol


# Default uniform sampling interval. Most operator-facing videos
# (lectures, podcasts, interviews) have 30s as a reasonable
# information-density window; tunable per call.
DEFAULT_UNIFORM_INTERVAL_S: int = 30

# Max frames per video. Protects against operator accidentally
# pointing at a 10-hour stream and producing 1200 frames worth of
# vision-role dispatch.
DEFAULT_MAX_FRAMES: int = 200


class FrameExtractionError(Exception):
    """Surfaces ffmpeg invocation failures, missing binary, etc."""


@dataclass(frozen=True)
class ExtractedFrame:
    """One frame produced by the extractor. ``frame_data_uri`` is
    the inline data: URL the visual provider consumes; ``timestamp_ms``
    is the source-clip offset."""

    page_or_frame_id: str
    timestamp_ms: int
    frame_data_uri: str
    frame_width_px: Optional[int] = None
    frame_height_px: Optional[int] = None


class FrameExtractor(Protocol):
    """Protocol any extractor satisfies."""

    name: str

    def extract(
        self,
        *,
        video_source: str,
        timestamps_ms: list[int],
    ) -> list[ExtractedFrame]: ...


# ── ffmpeg-backed extractor ────────────────────────────────────────


class FfmpegFrameExtractor:
    """Shell out to ffmpeg for frame extraction at exact timestamps.

    The substrate's invariant: every extracted frame's data URI is
    a small base64-encoded PNG. The visual provider's
    AnthropicVisionProvider accepts data: URLs directly.

    Configuration:
      - ``ffmpeg_path``: explicit binary path; default uses
        ``shutil.which("ffmpeg")``.
      - ``max_width_px``: downscale frames so the data URI doesn't
        blow up the vision-model context. Default 1024px wide
        (preserves aspect ratio).
    """

    name = "ffmpeg"

    def __init__(
        self,
        *,
        ffmpeg_path: Optional[str] = None,
        max_width_px: int = 1024,
    ):
        self._ffmpeg_path = ffmpeg_path
        self._max_width_px = max_width_px

    def _resolve_ffmpeg(self) -> str:
        path = self._ffmpeg_path or shutil.which("ffmpeg")
        if not path:
            raise FrameExtractionError(
                "ffmpeg binary not found. Install ffmpeg or pass "
                "ffmpeg_path= to the extractor."
            )
        return path

    def extract(
        self,
        *,
        video_source: str,
        timestamps_ms: list[int],
    ) -> list[ExtractedFrame]:
        import base64
        import tempfile

        ffmpeg = self._resolve_ffmpeg()
        frames: list[ExtractedFrame] = []
        with tempfile.TemporaryDirectory(prefix="antiek-frame-") as tmpdir:
            for idx, ts_ms in enumerate(timestamps_ms):
                out_path = os.path.join(tmpdir, f"frame_{idx:04d}.png")
                ts_seconds = ts_ms / 1000.0
                # -ss seek, -i input, -frames:v 1 single frame,
                # -vf scale downscale, -y overwrite.
                args = [
                    ffmpeg, "-y", "-loglevel", "error",
                    "-ss", f"{ts_seconds:.3f}",
                    "-i", video_source,
                    "-frames:v", "1",
                    "-vf", f"scale={self._max_width_px}:-1",
                    out_path,
                ]
                try:
                    subprocess.run(
                        args, check=True, capture_output=True,
                        timeout=60,
                    )
                except subprocess.CalledProcessError as exc:
                    raise FrameExtractionError(
                        f"ffmpeg failed at ts {ts_ms}ms: "
                        f"{exc.stderr.decode('utf-8', errors='replace')[:200]}",
                    ) from exc
                except subprocess.TimeoutExpired as exc:
                    raise FrameExtractionError(
                        f"ffmpeg timed out at ts {ts_ms}ms",
                    ) from exc
                with open(out_path, "rb") as fh:
                    data = fh.read()
                b64 = base64.b64encode(data).decode("ascii")
                data_uri = f"data:image/png;base64,{b64}"
                frames.append(ExtractedFrame(
                    page_or_frame_id=f"frame-{ts_ms}",
                    timestamp_ms=ts_ms,
                    frame_data_uri=data_uri,
                ))
        return frames


# ── Stub for tests ────────────────────────────────────────────────


@dataclass
class StubFrameExtractor:
    """Test injection. Returns synthetic frames; no ffmpeg call."""

    name: str = "stub_extractor"
    canned_data_uri: str = "data:image/png;base64,AAAA"
    calls: list[dict] = field(default_factory=list)

    def extract(
        self,
        *,
        video_source: str,
        timestamps_ms: list[int],
    ) -> list[ExtractedFrame]:
        self.calls.append({
            "video_source": video_source,
            "timestamps_ms": list(timestamps_ms),
        })
        return [
            ExtractedFrame(
                page_or_frame_id=f"frame-{ts}",
                timestamp_ms=ts,
                frame_data_uri=self.canned_data_uri,
            )
            for ts in timestamps_ms
        ]


# ── Timestamp planning ────────────────────────────────────────────


def plan_uniform_timestamps(
    *,
    duration_ms: int,
    interval_s: int = DEFAULT_UNIFORM_INTERVAL_S,
    max_frames: int = DEFAULT_MAX_FRAMES,
    start_offset_ms: int = 1_000,
) -> list[int]:
    """Build uniform-sample timestamps. ``start_offset_ms`` shifts
    the first sample off zero (frame 0 is often a black title card)."""
    if duration_ms <= 0:
        return []
    if interval_s <= 0:
        raise ValueError("interval_s must be positive")
    interval_ms = interval_s * 1000
    timestamps: list[int] = []
    ts = start_offset_ms
    while ts < duration_ms and len(timestamps) < max_frames:
        timestamps.append(ts)
        ts += interval_ms
    return timestamps


def extract_uniform(
    extractor: FrameExtractor,
    *,
    video_source: str,
    duration_ms: int,
    interval_s: int = DEFAULT_UNIFORM_INTERVAL_S,
    max_frames: int = DEFAULT_MAX_FRAMES,
) -> list[ExtractedFrame]:
    """Convenience: plan uniform timestamps + run extraction."""
    timestamps = plan_uniform_timestamps(
        duration_ms=duration_ms,
        interval_s=interval_s,
        max_frames=max_frames,
    )
    return extractor.extract(
        video_source=video_source,
        timestamps_ms=timestamps,
    )


__all__ = [
    "DEFAULT_MAX_FRAMES",
    "DEFAULT_UNIFORM_INTERVAL_S",
    "ExtractedFrame",
    "FfmpegFrameExtractor",
    "FrameExtractionError",
    "FrameExtractor",
    "StubFrameExtractor",
    "extract_uniform",
    "plan_uniform_timestamps",
]
