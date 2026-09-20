"""Podcast acquisition client.

Two ingestion paths:

1. **RSS feed → list episodes.** Operator provides a podcast's RSS feed
   URL. ``fetch_feed`` returns a ``Podcast`` with metadata + episode
   list. Each ``Episode`` carries the audio enclosure URL + any
   transcript URL we can detect in the feed entry.

2. **Single episode → fetch transcript.** ``fetch_episode_transcript``
   pulls a transcript when the episode entry advertises one (via
   ``podcast:transcript`` namespace, ``itunes:transcript``, or a
   linked ``.txt`` / ``.vtt`` / ``.srt`` file).

What this does NOT do (Sprint 12 scope):
  - Whisper transcription of audio. Substantial work + cost
    ($0.006/min) + needs an OpenAI key. Episodes without a published
    transcript are flagged ``no_transcript`` and skipped on ingest.
  - Pacing across episodes for a full-feed bulk ingest. The adapter
    handles one episode at a time; bulk-ingest is a caller concern.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

# --- VTT / SRT regex ---------------------------------------------------------
# We strip cue numbering, timestamps, and tag artifacts so the
# transcript reads as plain text after extraction.
_VTT_TIMESTAMP_RE = re.compile(
    r"^\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}.*$",
    re.MULTILINE,
)
_SRT_TIMESTAMP_RE = re.compile(
    r"^\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}.*$",
    re.MULTILINE,
)
_VTT_HEADER_RE = re.compile(r"^WEBVTT.*$", re.MULTILINE)
_SRT_CUE_NUMBER_RE = re.compile(r"^\d+\s*$", re.MULTILINE)
_VTT_TAG_RE = re.compile(r"<[^>]+>")
DEFAULT_TIMEOUT_S = 30.0
DEFAULT_USER_AGENT = "Antiek/0.1 (acquisition.podcasts)"


@dataclass(frozen=True)
class Episode:
    """One episode from an RSS feed."""

    episode_id: str  # GUID from RSS, or computed hash of audio_url
    title: str
    description: str
    published_at: datetime | None
    duration_seconds: int  # 0 when not advertised
    audio_url: str | None
    transcript_url: str | None
    episode_url: str | None  # web page for the episode, if distinct


@dataclass(frozen=True)
class Podcast:
    """A podcast's RSS feed + episode list."""

    feed_url: str
    title: str
    author: str
    description: str
    language: str
    episodes: list[Episode] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Feed fetch + parse
# ---------------------------------------------------------------------------


def _as_optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _detect_transcript_url(entry: Mapping[str, Any]) -> str | None:
    """Look for a transcript URL in an RSS entry. Supports:
      - <podcast:transcript url="..." type="text/plain | text/vtt | text/srt"/>
        (Podcasting 2.0 namespace, parsed by feedparser as
        ``podcast_transcript`` or similar)
      - <itunes:transcript> (rarer)
      - A link in <links> with type matching transcript-ish MIME

    Returns the first URL found, or None."""
    # feedparser populates `entry.podcast_transcript` for the
    # Podcasting 2.0 namespace, but the exact attribute name varies
    # by version. We probe a few likely candidates.
    for key in ("podcast_transcripts", "podcast_transcript", "transcripts"):
        val = entry.get(key) if isinstance(entry, dict) else getattr(entry, key, None)
        if not val:
            continue
        if isinstance(val, list) and val:
            for v in val:
                url = _as_optional_str(
                    v.get("url") if isinstance(v, dict) else getattr(v, "url", None)
                )
                if url:
                    return url
        elif isinstance(val, dict):
            url = _as_optional_str(val.get("url"))
            if url:
                return url
    # Scan generic links for transcript-flavored MIME types
    links = entry.get("links") if isinstance(entry, dict) else getattr(entry, "links", None)
    if isinstance(links, list):
        for link in links:
            rel = (link.get("rel") if isinstance(link, dict) else getattr(link, "rel", None)) or ""
            mtype = (link.get("type") if isinstance(link, dict) else getattr(link, "type", None)) or ""
            href = _as_optional_str(
                link.get("href") if isinstance(link, dict) else getattr(link, "href", None)
            ) or ""
            if not href:
                continue
            if (
                "transcript" in rel.lower()
                or "transcript" in mtype.lower()
                or any(href.lower().endswith(ext) for ext in (".vtt", ".srt", ".txt"))
            ):
                return href
    return None


def _detect_audio_url(entry: Mapping[str, Any]) -> str | None:
    """Find the audio enclosure URL. feedparser exposes RSS enclosures
    as ``entry.enclosures``; we accept anything with audio/* MIME."""
    enclosures = (
        entry.get("enclosures") if isinstance(entry, dict)
        else getattr(entry, "enclosures", None)
    )
    if not enclosures:
        return None
    for enc in enclosures:
        mtype = (
            enc.get("type") if isinstance(enc, dict)
            else getattr(enc, "type", None)
        ) or ""
        href = _as_optional_str(
            enc.get("href") if isinstance(enc, dict)
            else getattr(enc, "href", enc.get("url") if isinstance(enc, dict) else None)
        )
        if href and (
            mtype.startswith("audio/") or any(
                href.lower().endswith(ext) for ext in (".mp3", ".m4a", ".aac", ".ogg", ".wav")
            )
        ):
            return href
    return None


def _parse_duration(entry: Mapping[str, Any]) -> int:
    """Parse ``itunes:duration`` into seconds. Accepts ``HH:MM:SS``,
    ``MM:SS``, or raw seconds string. Returns 0 when unparseable."""
    val = (
        entry.get("itunes_duration") if isinstance(entry, dict)
        else getattr(entry, "itunes_duration", None)
    )
    if not val:
        return 0
    s = str(val).strip()
    try:
        parts = [int(p) for p in s.split(":")]
        if len(parts) == 3:
            hours, minutes, seconds = parts
            return hours * 3600 + minutes * 60 + seconds
        if len(parts) == 2:
            minutes, seconds = parts
            return minutes * 60 + seconds
        if len(parts) == 1:
            (seconds,) = parts
            return seconds
    except ValueError:
        pass
    return 0


def _parse_published(entry: Mapping[str, Any]) -> datetime | None:
    """Parse the entry's published timestamp. feedparser already
    converts ``pubDate`` into ``published_parsed`` (time.struct_time);
    we convert to UTC datetime."""
    parsed = (
        entry.get("published_parsed") if isinstance(entry, dict)
        else getattr(entry, "published_parsed", None)
    )
    if not parsed:
        return None
    try:
        import time as _time
        epoch = _time.mktime(parsed)
        return datetime.fromtimestamp(epoch, tz=UTC)
    except (TypeError, ValueError):
        return None


def fetch_feed(
    feed_url: str,
    *,
    max_episodes: int | None = None,
    client: httpx.Client | None = None,
) -> Podcast:
    """Fetch + parse an RSS feed. Returns a ``Podcast`` with episodes.

    ``max_episodes`` (newest-first) caps the list — useful when a
    long-running podcast has 500+ episodes and you only want the
    most recent N."""
    try:
        import feedparser  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "acquisition.podcasts requires feedparser. Run "
            "`pip install -e '.[rss]'`."
        ) from e

    # Download via httpx so caller can inject MockTransport in tests.
    # Host-global arXiv governance (SPR-09 root fix): ``feed_url`` is an
    # arbitrary caller-supplied URL, routed through ``govern_if_arxiv`` so an
    # arXiv host (if ever passed) is held under the host-global gate; any other
    # host is fetched directly (unchanged).
    from acquisition.arxiv.rate_governor import canonical_arxiv_throttle, govern_if_arxiv

    headers = {"User-Agent": DEFAULT_USER_AGENT}
    if client is not None:
        def _send() -> httpx.Response:
            return client.get(feed_url, headers=headers, timeout=DEFAULT_TIMEOUT_S)

        r = govern_if_arxiv(feed_url, _send, throttle=canonical_arxiv_throttle())
    else:
        with httpx.Client(
            follow_redirects=True,
            timeout=DEFAULT_TIMEOUT_S,  # module default; same pattern as acquisition/papers/core.py DEFAULT_TIMEOUT_S
        ) as c:
            def _send() -> httpx.Response:
                return c.get(feed_url, headers=headers, timeout=DEFAULT_TIMEOUT_S)

            r = govern_if_arxiv(feed_url, _send, throttle=canonical_arxiv_throttle())
    r.raise_for_status()

    parsed = feedparser.parse(r.content)
    channel = parsed.get("feed", {}) if hasattr(parsed, "get") else parsed.feed

    entries = parsed.entries if hasattr(parsed, "entries") else []
    if max_episodes is not None:
        entries = entries[:max_episodes]

    episodes: list[Episode] = []
    for entry in entries:
        eid = (
            (entry.get("id") if isinstance(entry, dict) else getattr(entry, "id", None))
            or (entry.get("guid") if isinstance(entry, dict) else getattr(entry, "guid", None))
            or _detect_audio_url(entry)
            or (entry.get("link") if isinstance(entry, dict) else getattr(entry, "link", None))
        )
        if not eid:
            continue
        episodes.append(Episode(
            episode_id=str(eid),
            title=(entry.get("title") if isinstance(entry, dict) else getattr(entry, "title", "")) or "",
            description=(
                entry.get("summary") if isinstance(entry, dict) else getattr(entry, "summary", "")
            ) or "",
            published_at=_parse_published(entry),
            duration_seconds=_parse_duration(entry),
            audio_url=_detect_audio_url(entry),
            transcript_url=_detect_transcript_url(entry),
            episode_url=(
                entry.get("link") if isinstance(entry, dict) else getattr(entry, "link", None)
            ),
        ))

    return Podcast(
        feed_url=feed_url,
        title=(channel.get("title") if isinstance(channel, dict) else getattr(channel, "title", "")) or "",
        author=(channel.get("author") if isinstance(channel, dict) else getattr(channel, "author", "")) or "",
        description=(channel.get("subtitle") if isinstance(channel, dict) else getattr(channel, "subtitle", "")) or "",
        language=(channel.get("language") if isinstance(channel, dict) else getattr(channel, "language", "")) or "",
        episodes=episodes,
    )


# ---------------------------------------------------------------------------
# Transcript fetch
# ---------------------------------------------------------------------------


def _clean_vtt(text: str) -> str:
    """Strip WEBVTT header, cue timestamps, and inline tags. Returns
    the prose-only body."""
    text = _VTT_HEADER_RE.sub("", text)
    text = _VTT_TIMESTAMP_RE.sub("", text)
    text = _VTT_TAG_RE.sub("", text)
    # Drop standalone numeric cue ids and collapse blank lines.
    text = _SRT_CUE_NUMBER_RE.sub("", text)
    return "\n".join(line for line in text.splitlines() if line.strip())


def _clean_srt(text: str) -> str:
    """Strip SRT cue numbers and timestamps."""
    text = _SRT_TIMESTAMP_RE.sub("", text)
    text = _SRT_CUE_NUMBER_RE.sub("", text)
    return "\n".join(line for line in text.splitlines() if line.strip())


def fetch_episode_transcript(
    transcript_url: str,
    *,
    client: httpx.Client | None = None,
) -> str:
    """Fetch a transcript file and normalize to plain text. Returns
    the cleaned text, or an empty string when the fetch fails."""
    # Host-global arXiv governance (SPR-09 root fix): ``transcript_url`` is an
    # arbitrary caller-supplied URL, routed through ``govern_if_arxiv``.
    from acquisition.arxiv.rate_governor import canonical_arxiv_throttle, govern_if_arxiv

    headers = {"User-Agent": DEFAULT_USER_AGENT}
    try:
        if client is not None:
            def _send() -> httpx.Response:
                return client.get(transcript_url, headers=headers, timeout=DEFAULT_TIMEOUT_S)

            r = govern_if_arxiv(transcript_url, _send, throttle=canonical_arxiv_throttle())
        else:
            with httpx.Client(
                follow_redirects=True,
                timeout=DEFAULT_TIMEOUT_S,  # module default; same pattern as acquisition/papers/core.py DEFAULT_TIMEOUT_S
            ) as c:
                def _send() -> httpx.Response:
                    return c.get(transcript_url, headers=headers, timeout=DEFAULT_TIMEOUT_S)

                r = govern_if_arxiv(transcript_url, _send, throttle=canonical_arxiv_throttle())
        r.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException):
        return ""
    body = r.text
    # Detect format heuristically by URL extension + content sniffing.
    url_lower = transcript_url.lower()
    if url_lower.endswith(".vtt") or body.lstrip().startswith("WEBVTT"):
        return _clean_vtt(body)
    if url_lower.endswith(".srt"):
        return _clean_srt(body)
    # Plain text (or HTML — caller can post-process if needed)
    return body.strip()
