"""Link Monster — the digest orchestrator.

``digest_url`` is the single entry point: validate → classify →
extraction ladder (oEmbed → OpenGraph → DOM / platform client) →
assemble the ``LinkDigest`` packet. Storage is a separate step
(``store.py``) so the packet is testable and reusable without a DB.

Honesty contract (mirrors krea_routes):

- Every rung of the ladder is optional; a failing rung contributes
  nothing and the next runs. The digest records *what was actually
  obtained*, with per-field provenance — nothing is invented.
- YouTube transcript extraction rides the existing
  ``acquisition/youtube`` client (yt-dlp-backed, rate-capped). When
  yt-dlp is absent or the fetch fails, the digest degrades to
  metadata-only and says so (``transcript: null`` + provenance).
- The SSRF guard (``fetchguard.py``) runs on every outbound fetch,
  including every redirect hop. A blocked target is a typed
  ``UnsafeUrlError``, never a hang and never a 500.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from .fetchguard import (
    GuardedPage,
    UnsafeUrlError,
    fetch_guarded,
    validate_url,
)
from .oembed import (
    OEmbedPacket,
    OGPacket,
    fetch_oembed,
    looks_like_substack,
    og_from_body,
)
from .platforms import Platform, classify, platform_label

# YouTube video id extraction (watch, shorts, youtu.be, embed).
_YT_ID_RE = re.compile(
    r"(?:v=|shorts/|embed/|youtu\.be/|live/)([A-Za-z0-9_-]{11})"
)


@dataclass(frozen=True)
class VideoInfo:
    provider: str
    video_id: str | None
    url: str
    thumbnail_url: str | None = None
    duration_seconds: int | None = None
    channel: str | None = None
    upload_date: datetime | None = None
    caption_kind: str | None = None


@dataclass(frozen=True)
class TranscriptInfo:
    source: str  # "youtube" | "missing"
    caption_kind: str | None
    chars: int
    segments: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class TextInfo:
    markdown: str
    chars: int
    word_count: int
    source: str  # "dom" | "oembed" | "none"


@dataclass(frozen=True)
class LinkDigest:
    """The full extraction packet for one link. Serialized into
    documents.metadata by store.py and returned verbatim by the API."""

    url: str
    final_url: str
    platform: Platform
    platform_label: str
    title: str | None
    author: str | None
    author_url: str | None
    published_at: datetime | None
    description: str | None
    site_name: str | None
    thumbnail_url: str | None
    image_urls: list[str]
    video: VideoInfo | None
    transcript: TranscriptInfo | None
    text: TextInfo | None
    provenance: dict[str, str]  # field -> "oembed" | "og" | "dom" | "platform" | "none"
    outcome: str  # "meal" (body) | "snack" (metadata only)
    artifacts: dict[str, int]  # counts: images, videos, transcript_chars, text_chars
    digested_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_jsonable(self) -> dict[str, Any]:
        def iso(v: datetime | None) -> str | None:
            return v.isoformat() if v else None

        return {
            "url": self.url,
            "final_url": self.final_url,
            "platform": self.platform,
            "platform_label": self.platform_label,
            "title": self.title,
            "author": self.author,
            "author_url": self.author_url,
            "published_at": iso(self.published_at),
            "description": self.description,
            "site_name": self.site_name,
            "thumbnail_url": self.thumbnail_url,
            "image_urls": self.image_urls,
            "video": (
                {
                    "provider": self.video.provider,
                    "video_id": self.video.video_id,
                    "url": self.video.url,
                    "thumbnail_url": self.video.thumbnail_url,
                    "duration_seconds": self.video.duration_seconds,
                    "channel": self.video.channel,
                    "upload_date": iso(self.video.upload_date),
                    "caption_kind": self.video.caption_kind,
                }
                if self.video
                else None
            ),
            "transcript": (
                {
                    "source": self.transcript.source,
                    "caption_kind": self.transcript.caption_kind,
                    "chars": self.transcript.chars,
                    "segments": self.transcript.segments,
                }
                if self.transcript
                else None
            ),
            "text": (
                {
                    "markdown": self.text.markdown,
                    "chars": self.text.chars,
                    "word_count": self.text.word_count,
                    "source": self.text.source,
                }
                if self.text
                else None
            ),
            "provenance": self.provenance,
            "outcome": self.outcome,
            "artifacts": self.artifacts,
            "digested_at": iso(self.digested_at),
        }


@dataclass(frozen=True)
class DigestResult:
    """What ``digest_url`` returns: the packet plus the stable doc id
    the store layer will use (so the route can dedupe before writing)."""

    document_id: str
    digest: LinkDigest
    already_digested: bool = False


def _youtube_video_id(url: str) -> str | None:
    m = _YT_ID_RE.search(url)
    return m.group(1) if m else None


def _word_count(text: str) -> int:
    return len(text.split())


def _digest_text_from_dom(body: bytes, final_url: str) -> TextInfo | None:
    """Rung 3 — DOM text via the existing readability-grade extractor
    (acquisition/urls/extract.html_to_markdown). Returns None when the
    page yields nothing substantive."""
    try:
        from acquisition.urls.extract import html_to_markdown
    except Exception:
        return None
    try:
        doc = html_to_markdown(body, base_url=final_url)
    except Exception:
        return None
    md = (doc.markdown or "").strip()
    if _word_count(md) < 10:
        return None
    return TextInfo(markdown=md, chars=len(md), word_count=_word_count(md), source="dom")


def _digest_youtube(
    url: str,
    oembed: OEmbedPacket | None,
    og: OGPacket | None,
) -> tuple[VideoInfo | None, TranscriptInfo | None]:
    """Deep YouTube extraction: metadata + timed transcript via the
    existing acquisition/youtube client (yt-dlp). Any failure degrades
    to oEmbed/OG metadata only — never raises."""
    video_id = _youtube_video_id(url)
    if not video_id:
        return None, None
    video: VideoInfo | None = None
    transcript: TranscriptInfo | None = None
    try:
        from acquisition.youtube.client import fetch as fetch_youtube

        yt = fetch_youtube(video_id, want_transcript=True)
        video = VideoInfo(
            provider="youtube",
            video_id=video_id,
            url=yt.watch_url or f"https://www.youtube.com/watch?v={video_id}",
            thumbnail_url=(
                f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
            ),
            duration_seconds=yt.duration_seconds or None,
            channel=yt.channel or None,
            upload_date=yt.upload_date,
            caption_kind=yt.caption_kind,
        )
        if yt.transcript:
            segments = [
                {
                    "start": round(seg.start_seconds, 2),
                    "duration": round(seg.duration_seconds, 2),
                    "text": seg.text,
                }
                for seg in yt.transcript
            ]
            chars = sum(len(str(seg["text"])) for seg in segments)
            transcript = TranscriptInfo(
                source="youtube",
                caption_kind=yt.caption_kind,
                chars=chars,
                segments=segments,
            )
        else:
            transcript = TranscriptInfo(
                source="missing", caption_kind=yt.caption_kind, chars=0
            )
    except Exception:
        # yt-dlp absent, rate-capped, network-failed — metadata-only.
        transcript = TranscriptInfo(source="missing", caption_kind=None, chars=0)
    return video, transcript


def digest_url(
    url: str,
    *,
    client: httpx.Client | None = None,
    timeout_s: float = 15.0,
) -> DigestResult:
    """The Monster's mouth: classify, guard, ladder-extract, assemble.
    Raises UnsafeUrlError (typed 422) on blocked targets; raises
    httpx.HTTPStatusError/TimeoutException (typed 502) on transport
    failures. Everything else degrades gracefully into the packet."""
    url = validate_url(url)
    platform = classify(url)
    provenance: dict[str, str] = {}

    # Rung 1 — platform oEmbed (metadata-heavy platforms skip straight
    # to the guarded page fetch when no endpoint exists).
    oembed = fetch_oembed(url, platform, client=client, timeout_s=timeout_s)
    if oembed is not None:
        provenance["oembed"] = "ok"
        for f in ("title", "author_name", "thumbnail_url"):
            provenance[f] = "oembed"
    else:
        provenance["oembed"] = "none"

    # Rung 2 — OpenGraph via a single guarded fetch (reused for DOM).
    page: GuardedPage | None = None
    og: OGPacket | None = None
    try:
        page = fetch_guarded(url, client=client, timeout_s=timeout_s)
        og = og_from_body(page.body, canonical_url=str(page.final_url))
    except UnsafeUrlError:
        raise
    except Exception:
        og = None
    if og is not None:
        provenance["og"] = "ok"
        for f in ("title", "description", "image_url", "site_name", "published_at", "author"):
            if getattr(og, f):
                provenance[f] = "og"
    else:
        provenance["og"] = "none"

    # Substack custom-domain reclassification (honest upgrade).
    effective_platform = platform
    if platform == "generic" and page is not None and looks_like_substack(page.body):
        effective_platform = "substack"
        provenance["platform"] = "reclassified:substack"

    final_url = page.final_url if page else url

    # Rung 3 — deep extraction per platform.
    video: VideoInfo | None = None
    transcript: TranscriptInfo | None = None
    text: TextInfo | None = None
    if effective_platform == "youtube":
        video, transcript = _digest_youtube(final_url, oembed, og)
        if video is not None:
            provenance["video"] = "platform"
        if transcript is not None and transcript.chars:
            provenance["transcript"] = "platform"
    # DOM text runs only on full-text platforms (generic web, Substack).
    # YouTube / X / Instagram / TikTok pages are JS shells: html_to_markdown
    # on them fabricates noise from scripts, not content — the honest body
    # for those platforms is the transcript (YouTube) or the OG description
    # (already captured). A YouTube link with no transcript is a snack.
    if text is None and page is not None and effective_platform in ("generic", "substack"):
        text = _digest_text_from_dom(page.body, final_url)
        if text is not None:
            provenance["text"] = "dom"

    # Assemble fields (oEmbed wins over OG for author/title — the
    # platform's own structured data is more reliable; OG fills gaps).
    title = (oembed.title if oembed and oembed.title else None) or (og.title if og else None)
    author = (oembed.author_name if oembed and oembed.author_name else None) or (og.author if og else None)
    author_url = oembed.author_url if oembed else None
    published_at = og.published_at if og else None
    description = (_strip_html(oembed.html_fragment) if oembed and oembed.html_fragment else None) or (og.description if og else None)
    site_name = og.site_name if og else None
    thumbnail = (oembed.thumbnail_url if oembed and oembed.thumbnail_url else None) or (og.image_url if og else None)
    image_urls = [u for u in [og.image_url if og else None, oembed.thumbnail_url if oembed else None] if u]

    # Outcome: a meal has body (text or transcript); a snack is metadata-only.
    body_chars = (transcript.chars if transcript else 0) + (text.chars if text else 0)
    outcome = "meal" if body_chars > 0 else "snack"

    digest = LinkDigest(
        url=url,
        final_url=final_url,
        platform=effective_platform,
        platform_label=platform_label(effective_platform),
        title=title,
        author=author,
        author_url=author_url,
        published_at=published_at,
        description=description,
        site_name=site_name,
        thumbnail_url=thumbnail,
        image_urls=image_urls,
        video=video,
        transcript=transcript,
        text=text,
        provenance=provenance,
        outcome=outcome,
        artifacts={
            "images": len(image_urls),
            "videos": 1 if video else 0,
            "transcript_chars": transcript.chars if transcript else 0,
            "text_chars": text.chars if text else 0,
            "body_chars": body_chars,
        },
    )
    from .store import link_monster_doc_id

    return DigestResult(document_id=link_monster_doc_id(final_url), digest=digest)


def _strip_html(fragment: str) -> str:
    import re as _re

    return _re.sub(r"<[^>]+>", "", fragment).strip()
