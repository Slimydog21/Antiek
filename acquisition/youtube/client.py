"""YouTube metadata + transcript client.

Wraps ``youtube-transcript-api`` for the cheap path (community
captions / auto-captions) and falls back to caller-injected audio
download + transcription when captions don't exist. The transcript
fetch is read-only and unauthenticated; YouTube doesn't require an
API key for this surface.

The default video metadata path uses ``yt-dlp``. When an owner has a
connected Data API key, ``fetch_with_data_api`` uses that key for metadata.

────────────────────────────────────────────────────────────────────
ToS RISK — read before using this connector (SPR-07)
────────────────────────────────────────────────────────────────────
This connector's transcript-fetch path (``youtube-transcript-api`` over
YouTube's unofficial ``timedtext`` endpoint) and its default metadata path
(``yt-dlp``) **violate YouTube's Terms of Service regardless of
personal use** — the ToS prohibit accessing content other than through
the public interface / the official API, and personal/non-commercial
intent does NOT cure that breach. The Personal-Reading Lane
(``content_class='personal_reading'``) cures the *copyright-serving*
problem (a scraped transcript is never served publicly, ad-attributed,
or trained on); it does **not** cure this *acquisition-ToS* problem.

The only ToS-clean caption path is the official ``captions.download``
YouTube Data API, which is **owner-only** (you can only pull captions
for videos on channels you own/manage) and is therefore out of scope
for a general reading connector — flagged as an open question, not
implemented here.

Consequently this connector is **operator-only and low-volume** by
design: there is a per-process fetch cap (``YOUTUBE_MAX_FETCHES_PER_RUN``)
and there is deliberately **no crawler / channel fan-out / playlist
batch** entrypoint. Ingest one explicitly-supplied video id/URL per call.

Caption provenance (SPR-07): ``youtube-transcript-api`` distinguishes
human-authored captions from YouTube auto-captions via the
``is_generated`` flag on each transcript track. We surface that as
``YouTubeVideo.caption_kind`` so the reader knows auto-captions are
materially less reliable. When the underlying library cannot report
generated-vs-manual for a track, we record ``"unknown"`` — we never
silently default a guessed track to ``"human"``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# ── Operator-only, low-volume rate cap (SPR-07) ──────────────────────
# The transcript-scrape path breaches YouTube ToS (see module docstring),
# so acquisition is deliberately bounded. A human operator reads a
# *handful* of videos in a session — a lecture, a talk, a podcast — not
# hundreds; anything larger is a crawler, which is explicitly forbidden
# (no channel/playlist fan-out). 25 fetches per process gives generous
# headroom for a real reading session while making a runaway loop or an
# accidental batch fail loudly and early. The cap is in-process only (no
# DB, no daemon, no queue) and resets per process, consistent with the
# §16 box-bounded / single-writer invariant — it is a guardrail, not a
# distributed rate limiter.
YOUTUBE_MAX_FETCHES_PER_RUN = 25

_fetch_count = 0


class YouTubeRateCapExceeded(RuntimeError):
    """Raised when YouTube acquisition exceeds
    ``YOUTUBE_MAX_FETCHES_PER_RUN`` within a single process. Signals that
    the operator-only / low-volume posture is being violated (e.g. an
    accidental batch or a crawler-shaped loop). Reset the counter with
    ``reset_youtube_fetch_counter()`` if you intend a fresh session."""


def note_youtube_fetch() -> int:
    """Record one YouTube acquisition against the per-process cap and
    return the new count. Raises ``YouTubeRateCapExceeded`` once the cap
    is passed. The at-cap fetch is allowed; the (cap+1)-th raises."""
    global _fetch_count
    if _fetch_count >= YOUTUBE_MAX_FETCHES_PER_RUN:
        raise YouTubeRateCapExceeded(
            f"YouTube acquisition cap reached: "
            f"{YOUTUBE_MAX_FETCHES_PER_RUN} fetches per process. This "
            f"connector is operator-only / low-volume — no crawler or "
            f"batch fan-out. Start a new process (or call "
            f"reset_youtube_fetch_counter()) for a fresh reading session."
        )
    _fetch_count += 1
    return _fetch_count


def reset_youtube_fetch_counter() -> None:
    """Reset the per-process YouTube fetch counter to zero (new session /
    test isolation). In-process only — there is no persisted state."""
    global _fetch_count
    _fetch_count = 0


# Match a standard YouTube watch URL OR an 11-char video id directly.
_VIDEO_ID_RE = re.compile(
    r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)?"
    r"([A-Za-z0-9_-]{11})(?:[?&].*)?$"
)


def parse_video_id(url_or_id: str) -> str | None:
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


# Caption-provenance values for ``YouTubeVideo.caption_kind`` (SPR-07).
# "human"   — a manually-authored / community caption track.
# "auto"    — a YouTube auto-generated (ASR) caption track; materially
#             less reliable, so the reader is told the truth.
# "unknown" — captions exist but the library could not report
#             generated-vs-manual for the track (honest fallback; we do
#             NOT guess "human").
# "missing" — no captions were available at all.
CAPTION_KIND_HUMAN = "human"
CAPTION_KIND_AUTO = "auto"
CAPTION_KIND_UNKNOWN = "unknown"
CAPTION_KIND_MISSING = "missing"
METADATA_SOURCE_YT_DLP = "yt_dlp"
METADATA_SOURCE_DATA_API = "youtube_data_api"


@dataclass(frozen=True)
class YouTubeVideo:
    """A fetched YouTube video record. ``transcript`` may be empty when
    no captions are available — callers should fall back to whisper
    on the audio (the adapter wires this).

    ``caption_kind`` (SPR-07) records caption provenance —
    ``"human" | "auto" | "unknown" | "missing"`` — derived from the
    caption API's per-track ``is_generated`` flag, never inferred or
    hardcoded. ``"unknown"`` is the honest value when the library cannot
    report generated-vs-manual; we never default a guessed track to
    ``"human"``."""

    video_id: str
    title: str
    channel: str
    duration_seconds: int
    upload_date: datetime | None
    description: str
    transcript: list[TranscriptSegment] = field(default_factory=list)
    transcript_source: str = "unknown"  # "youtube" | "whisper" | "missing"
    watch_url: str = ""
    caption_kind: str = CAPTION_KIND_MISSING  # see CAPTION_KIND_* above
    metadata_source: str = METADATA_SOURCE_YT_DLP


# ---------------------------------------------------------------------------
# Metadata + transcript fetch
# ---------------------------------------------------------------------------


def _fetch_metadata(video_id: str) -> dict[str, Any]:
    """Pull video metadata via yt-dlp. Lazy import keeps the optional
    dep out of test paths that don't exercise it."""
    try:
        from yt_dlp import YoutubeDL  # type: ignore[import-untyped]
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


def _segments_from_raw(raw: Any) -> list[TranscriptSegment]:
    """Normalize youtube-transcript-api's list-of-dicts into our
    immutable ``TranscriptSegment`` records, dropping empty lines."""
    return [
        TranscriptSegment(
            text=r.get("text", "").strip(),
            start_seconds=float(r.get("start", 0.0)),
            duration_seconds=float(r.get("duration", 0.0)),
        )
        for r in raw
        if r.get("text", "").strip()
    ]


def _fetch_transcript(video_id: str) -> tuple[list[TranscriptSegment], str]:
    """Pull captions via youtube-transcript-api. Returns
    ``(segments, caption_kind)``; ``([], "missing")`` when captions are
    absent.

    Caption provenance (SPR-07) is read from the real API: each track
    returned by ``list_transcripts()`` carries an ``is_generated`` flag
    distinguishing YouTube auto-captions (``True`` → ``"auto"``) from
    human/community captions (``False`` → ``"human"``). When the library
    is too old to expose ``list_transcripts``/``is_generated``, or the
    flag cannot be read for the resolved track, we fall back to the flat
    ``get_transcript`` path and record ``"unknown"`` — we never guess
    ``"human"``.

    NOTE (intellectual honesty): the ``is_generated``/``list_transcripts``
    surface was verified against the documented youtube-transcript-api
    API; the library is an optional ``[youtube]`` extra and may be absent
    in some environments, in which case this path raises ImportError and
    only the caller-injected ``video=`` seam (tests, batch) is exercised.
    """
    try:
        from youtube_transcript_api import (
            YouTubeTranscriptApi,
        )
        from youtube_transcript_api._errors import (
            NoTranscriptFound,
            TranscriptsDisabled,
        )
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "acquisition.youtube requires youtube-transcript-api. Run "
            "`pip install -e '.[youtube]'`."
        ) from e

    # Preferred path: enumerate tracks so we can read per-track
    # is_generated (auto vs human). pragma: no cover — needs live lib+net.
    if hasattr(YouTubeTranscriptApi, "list_transcripts"):  # pragma: no cover
        try:
            track_list = YouTubeTranscriptApi.list_transcripts(video_id)
            track = None
            try:
                track = track_list.find_manually_created_transcript(["en"])
            except Exception:
                try:
                    track = track_list.find_generated_transcript(["en"])
                except Exception:
                    track = next(iter(track_list), None)
            if track is not None:
                raw = track.fetch()
                segments = _segments_from_raw(raw)
                if not segments:
                    return [], CAPTION_KIND_MISSING
                is_generated = getattr(track, "is_generated", None)
                if is_generated is True:
                    return segments, CAPTION_KIND_AUTO
                if is_generated is False:
                    return segments, CAPTION_KIND_HUMAN
                # Track exists but provenance unreadable — honest unknown.
                return segments, CAPTION_KIND_UNKNOWN
        except (NoTranscriptFound, TranscriptsDisabled):
            return [], CAPTION_KIND_MISSING
        except Exception:
            # Fall through to the flat path below.
            pass

    # Fallback path: flat get_transcript can't report provenance →
    # honest "unknown" when captions are present.
    try:
        # youtube-transcript-api >= 1.0 removed the flat classmethod
        # ``get_transcript``; ``fetch`` is the supported surface and returns
        # FetchedTranscriptSnippet dataclasses (text/start/duration).
        fetched = YouTubeTranscriptApi().fetch(video_id)
        raw = [
            {"text": s.text, "start": float(s.start), "duration": float(s.duration)}
            for s in fetched
        ]
    except (NoTranscriptFound, TranscriptsDisabled):
        return [], CAPTION_KIND_MISSING
    except Exception:  # pragma: no cover — defensive for transient errors
        return [], CAPTION_KIND_MISSING

    segments = _segments_from_raw(raw)
    if not segments:
        return [], CAPTION_KIND_MISSING
    return segments, CAPTION_KIND_UNKNOWN


def fetch(url_or_id: str, *, want_transcript: bool = True) -> YouTubeVideo:
    """Public entry point: parse the video id, fetch metadata + (optional)
    transcript, return a ``YouTubeVideo`` record.

    ToS RISK (SPR-07): this triggers the ToS-gray scrape path described in
    the module docstring. It is rate-capped per process via
    ``note_youtube_fetch()`` and raises ``YouTubeRateCapExceeded`` past
    ``YOUTUBE_MAX_FETCHES_PER_RUN`` to keep the connector operator-only /
    low-volume — never a crawler."""
    note_youtube_fetch()
    video_id = parse_video_id(url_or_id)
    if not video_id:
        raise ValueError(f"unrecognized YouTube URL/id: {url_or_id!r}")
    meta = _fetch_metadata(video_id)
    transcript: list[TranscriptSegment] = []
    transcript_source = "missing"
    caption_kind = CAPTION_KIND_MISSING
    if want_transcript:
        transcript, caption_kind = _fetch_transcript(video_id)
        transcript_source = "youtube" if transcript else "missing"
    upload_date: datetime | None = None
    upload_raw = meta.get("upload_date")
    if upload_raw and len(upload_raw) == 8:
        try:
            upload_date = datetime.strptime(upload_raw, "%Y%m%d").replace(
                tzinfo=UTC,
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
        caption_kind=caption_kind,
        metadata_source=METADATA_SOURCE_YT_DLP,
    )


def _parse_rfc3339(value: str | None) -> datetime | None:
    """``2026-08-12T00:00:00Z`` -> an aware UTC datetime; None if unreadable."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def fetch_with_data_api(
    connector: Any,
    url_or_id: str,
    *,
    want_transcript: bool = True,
) -> YouTubeVideo:
    """Build a ``YouTubeVideo`` whose METADATA comes from the owner's own key.

    ``connector`` is a resolved ``runtime.connectors.youtube.YouTubeDataConnector``
    (anything with ``video_metadata(video_id)``). Title, channel, description,
    duration and publish date arrive through ``videos.list`` on the official
    Data API at 1 quota unit of the owner's meter, instead of through yt-dlp.

    Captions are NOT on that path. The only official caption endpoint,
    ``captions.download``, is limited to videos on channels the caller owns,
    so when ``want_transcript`` is set the transcript still comes from the
    unofficial timedtext path in ``_fetch_transcript``. That remains the open
    ToS question described in this module's docstring, and this function does
    not cure it; it is still counted against the per-process cap for the same
    reason, and the count happens before the metadata call so a capped request
    spends nothing.
    """
    video_id = parse_video_id(url_or_id)
    if not video_id:
        raise ValueError(f"unrecognized YouTube URL/id: {url_or_id!r}")
    if want_transcript:
        # Counted BEFORE the metadata call so a capped request never spends
        # the owner's quota unit on a video it will not ingest.
        note_youtube_fetch()
    meta = connector.video_metadata(video_id)
    transcript: list[TranscriptSegment] = []
    transcript_source = "missing"
    caption_kind = CAPTION_KIND_MISSING
    if want_transcript:
        # Captions: still the unofficial timedtext scrape, the open ToS
        # question. Only the metadata above moved to the official API.
        transcript, caption_kind = _fetch_transcript(video_id)
        transcript_source = "youtube" if transcript else "missing"
    return YouTubeVideo(
        video_id=video_id,
        title=meta.title or "(untitled)",
        channel=meta.channel_title,
        duration_seconds=int(meta.duration_seconds),
        upload_date=_parse_rfc3339(meta.published_at),
        description=meta.description,
        transcript=transcript,
        transcript_source=transcript_source,
        watch_url=f"https://www.youtube.com/watch?v={video_id}",
        caption_kind=caption_kind,
        metadata_source=METADATA_SOURCE_DATA_API,
    )
