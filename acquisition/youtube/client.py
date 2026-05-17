"""YouTube metadata + transcript client.

Wraps ``youtube-transcript-api`` for the cheap path (community
captions / auto-captions) and falls back to caller-injected audio
download + transcription when captions don't exist. The transcript
fetch is read-only and unauthenticated; YouTube doesn't require an
API key for this surface.

The video metadata path uses ``yt-dlp`` for the same reason — no API
key, no rate limit dance for one-off fetches.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


# Match a standard YouTube watch URL OR an 11-char video id directly.
_VIDEO_ID_RE = re.compile(
    r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)?"
    r"([A-Za-z0-9_-]{11})(?:[?&].*)?$"
)


def parse_video_id(url_or_id: str) -> Optional[str]:
    """Normalize a YouTube watch URL / shorts URL / shortlink / bare id
    to the 11-character video_id. Returns None if unparseable."""
    s = url_or_id.strip()
    # If it's already an 11-char id, accept it directly.
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", s):
        return s
    m = _VIDEO_ID_RE.search(s)
    if m:
        return m.group(1)
    return None


@dataclass(frozen=True)
class TranscriptSegment:
    """One transcript line with start/duration timestamps."""

    text: str
    start_seconds: float
    duration_seconds: float


@dataclass(frozen=True)
class YouTubeVideo:
    """A fetched YouTube video record. ``transcript`` may be empty when
    no captions are available — callers should fall back to whisper
    on the audio (the adapter wires this)."""

    video_id: str
    title: str
    channel: str
    duration_seconds: int
    upload_date: Optional[datetime]
    description: str
    transcript: List[TranscriptSegment] = field(default_factory=list)
    transcript_source: str = "unknown"  # "youtube" | "whisper" | "missing"
    watch_url: str = ""


# ---------------------------------------------------------------------------
# Metadata + transcript fetch
# ---------------------------------------------------------------------------


def _fetch_metadata(video_id: str) -> dict:
    """Pull video metadata via yt-dlp. Lazy import keeps the optional
    dep out of test paths that don't exercise it."""
    try:
        from yt_dlp import YoutubeDL  # type: ignore[import-not-found]
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "acquisition.youtube requires yt-dlp. Run "
            "`pip install -e '.[youtube]'`."
        ) from e

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(
            f"https://www.youtube.com/watch?v={video_id}",
            download=False,
        )
    return info or {}


def _fetch_transcript(video_id: str) -> List[TranscriptSegment]:
    """Pull captions via youtube-transcript-api. Returns [] when
    captions are absent."""
    try:
        from youtube_transcript_api import (  # type: ignore[import-not-found]
            YouTubeTranscriptApi,
        )
        from youtube_transcript_api._errors import (  # type: ignore[import-not-found]
            NoTranscriptFound,
            TranscriptsDisabled,
        )
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "acquisition.youtube requires youtube-transcript-api. Run "
            "`pip install -e '.[youtube]'`."
        ) from e

    try:
        raw = YouTubeTranscriptApi.get_transcript(video_id)
    except (NoTranscriptFound, TranscriptsDisabled):
        return []
    except Exception:  # pragma: no cover — defensive for transient errors
        return []

    return [
        TranscriptSegment(
            text=r.get("text", "").strip(),
            start_seconds=float(r.get("start", 0.0)),
            duration_seconds=float(r.get("duration", 0.0)),
        )
        for r in raw
        if r.get("text", "").strip()
    ]


def fetch(url_or_id: str, *, want_transcript: bool = True) -> YouTubeVideo:
    """Public entry point: parse the video id, fetch metadata + (optional)
    transcript, return a ``YouTubeVideo`` record."""
    video_id = parse_video_id(url_or_id)
    if not video_id:
        raise ValueError(f"unrecognized YouTube URL/id: {url_or_id!r}")
    meta = _fetch_metadata(video_id)
    transcript: List[TranscriptSegment] = []
    transcript_source = "missing"
    if want_transcript:
        transcript = _fetch_transcript(video_id)
        transcript_source = "youtube" if transcript else "missing"
    upload_date: Optional[datetime] = None
    upload_raw = meta.get("upload_date")
    if upload_raw and len(upload_raw) == 8:
        try:
            upload_date = datetime.strptime(upload_raw, "%Y%m%d").replace(
                tzinfo=timezone.utc,
            )
        except ValueError:
            upload_date = None
    return YouTubeVideo(
        video_id=video_id,
        title=meta.get("title") or "(untitled)",
        channel=meta.get("uploader") or meta.get("channel") or "",
        duration_seconds=int(meta.get("duration") or 0),
        upload_date=upload_date,
        description=meta.get("description") or "",
        transcript=transcript,
        transcript_source=transcript_source,
        watch_url=f"https://www.youtube.com/watch?v={video_id}",
    )
