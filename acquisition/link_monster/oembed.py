"""Link Monster — extraction ladder (oEmbed → OpenGraph → DOM).

The ladder is the "extract as much information as possible" engine.
Each rung is optional and independent; a rung that fails (endpoint
down, 404, paywall, no meta) simply contributes nothing and the next
rung runs. Every field that IS extracted carries its provenance so the
digest is honest about where each fact came from.

Rungs:

1. platform oEmbed (X, YouTube, Instagram, TikTok — public endpoints)
2. OpenGraph / Twitter-Card meta from a guarded GET of the page
3. DOM text extraction — delegated to ``acquisition/urls.extract``
   (the existing readability-grade extractor) by ``digest.py``

This module touches NO DuckDB and NO db_lock — the single-writer
invariant is untouched (mirrors krea_routes' posture).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from .fetchguard import MAX_BODY_BYTES, GuardedPage, fetch_guarded
from .platforms import Platform

Provenance = str  # "oembed" | "og" | "dom" | "platform" | "none"

_OG_KEYS = (
    "og:title", "og:description", "og:image", "og:site_name",
    "og:video", "og:video:type", "og:video:width", "og:video:height",
    "og:type", "article:published_time", "article:author",
    "twitter:title", "twitter:description", "twitter:image",
    "twitter:player", "twitter:player:width", "twitter:player:height",
)


@dataclass(frozen=True)
class OEmbedPacket:
    """Normalized oEmbed response (platform rung of the ladder)."""
    provider_name: str | None
    title: str | None
    author_name: str | None
    author_url: str | None
    thumbnail_url: str | None
    html_fragment: str | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OGPacket:
    """Normalized OpenGraph / Twitter-Card meta (second rung)."""
    title: str | None
    description: str | None
    image_url: str | None
    site_name: str | None
    video_url: str | None
    video_width: int | None
    video_height: int | None
    published_at: datetime | None
    author: str | None
    canonical_url: str | None
    raw: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Rung 1 — platform oEmbed
# ---------------------------------------------------------------------------


def _parse_oembed(body: bytes) -> dict[str, Any] | None:
    try:
        data = __import__("json").loads(body.decode("utf-8", errors="replace"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return data


def fetch_oembed(
    url: str,
    platform: Platform,
    *,
    client: httpx.Client | None = None,
    timeout_s: float = 8.0,
) -> OEmbedPacket | None:
    """Rung 1. Returns None on any failure (endpoint absent, non-200,
    unparseable) — the ladder falls through, never raises."""
    from .platforms import PLATFORM_OEMBED_ENDPOINT

    endpoint = PLATFORM_OEMBED_ENDPOINT.get(platform)
    if not endpoint:
        return None
    own = client is None
    if client is None:
        client = httpx.Client(timeout=timeout_s, follow_redirects=True,
                              headers={"User-Agent": "AntiekLinkMonster/1.0 (+https://antiek.ai)"})
    try:
        from acquisition.arxiv.rate_governor import govern_if_arxiv

        # arXiv-boundary discipline (same rule as fetchguard): the oEmbed
        # endpoint is a fixed non-arXiv host today, but the boundary is
        # enforced at the send for the same bypass-proof reason.
        resp = govern_if_arxiv(
            endpoint,
            lambda: client.get(endpoint, params={"url": url, "format": "json"}),
        )
        if resp.status_code != 200:
            return None
        data = _parse_oembed(resp.content)
        if data is None:
            return None
        return OEmbedPacket(
            provider_name=(
                str(data["provider_name"]) if data.get("provider_name") else None
            ),
            title=str(data["title"]) if data.get("title") else None,
            author_name=str(data["author_name"]) if data.get("author_name") else None,
            author_url=str(data["author_url"]) if data.get("author_url") else None,
            thumbnail_url=(
                str(data["thumbnail_url"]) if data.get("thumbnail_url") else None
            ),
            html_fragment=str(data["html"]) if data.get("html") else None,
            raw=data,
        )
    except Exception:
        return None
    finally:
        if own:
            client.close()


# ---------------------------------------------------------------------------
# Rung 2 — OpenGraph / Twitter-Card meta
# ---------------------------------------------------------------------------


_META_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\']([^"\']+)["\'][^>]+content=["\']([^"\']*)["\']',
    re.IGNORECASE,
)
_META_RE_ALT = re.compile(
    r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_CANONICAL_RE = re.compile(
    r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']', re.IGNORECASE
)


def _strip_tags(fragment: str) -> str:
    return re.sub(r"<[^>]+>", "", fragment).strip()


def _parse_opengraph(body: bytes) -> dict[str, str]:
    text = body.decode("utf-8", errors="replace")[: MAX_BODY_BYTES]
    meta: dict[str, str] = {}
    for pat in (_META_RE, _META_RE_ALT):
        for key, val in pat.findall(text):
            meta[key.lower()] = html.unescape(val.strip())
    return meta


def og_from_body(body: bytes, *, canonical_url: str | None = None) -> OGPacket | None:
    """Parse OpenGraph / Twitter-Card meta from an already-fetched HTML
    body (the digest orchestrator's single-guarded-fetch path). Returns
    None when no meta is present — the ladder falls through to DOM."""
    meta = _parse_opengraph(body)
    if not meta:
        return None
    decoded = body.decode("utf-8", errors="replace")
    title_match = _TITLE_RE.search(decoded)
    title = (
        meta.get("og:title")
        or meta.get("twitter:title")
        or (_strip_tags(title_match.group(1)) if title_match else None)
    )
    published_at: datetime | None = None
    raw_pub = meta.get("article:published_time")
    if raw_pub:
        try:
            published_at = datetime.fromisoformat(raw_pub.replace("Z", "+00:00"))
            if published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=UTC)
        except Exception:
            published_at = None
    w = meta.get("og:video:width") or meta.get("twitter:player:width")
    h = meta.get("og:video:height") or meta.get("twitter:player:height")
    canon_match = _CANONICAL_RE.search(decoded)
    return OGPacket(
        title=title,
        description=meta.get("og:description") or meta.get("twitter:description"),
        image_url=meta.get("og:image") or meta.get("twitter:image"),
        site_name=meta.get("og:site_name"),
        video_url=meta.get("og:video") or meta.get("twitter:player"),
        video_width=int(w) if w and w.isdigit() else None,
        video_height=int(h) if h and h.isdigit() else None,
        published_at=published_at,
        author=meta.get("article:author") or meta.get("author"),
        canonical_url=canonical_url or (canon_match.group(1) if canon_match else None),
        raw=meta,
    )


def fetch_opengraph(
    url: str,
    *,
    client: httpx.Client | None = None,
    timeout_s: float = 10.0,
) -> OGPacket | None:
    """Rung 2. Guarded fetch (SSRF-checked, redirects re-checked) of the
    page, then OpenGraph/Twitter-Card meta extraction. Returns None on
    transport failure, non-HTML content, or an empty meta set — the
    ladder falls through to the DOM rung."""
    try:
        page: GuardedPage = fetch_guarded(
            url, client=client, timeout_s=timeout_s,
        )
    except Exception:
        return None
    ctype = page.headers.get("content-type", "")
    if "html" not in ctype.lower() and page.body.lstrip()[:1] != b"<":
        return None
    return og_from_body(page.body, canonical_url=str(page.final_url))


# ---------------------------------------------------------------------------
# Rung 3 — DOM text extraction (delegated; see digest.py)
# ---------------------------------------------------------------------------

# Substack custom-domain detection: the OG site_name for a Substack
# publication is the publication name and the page carries a Substack
# generator meta. We look for the generator marker; it is the only
# reliable cross-domain signal.
_SUBSTACK_GENERATOR_RE = re.compile(
    r'<meta[^>]+name=["\']generator["\'][^>]+content=["\'][^>]*[Ss]ubstack',
    re.IGNORECASE,
)


def looks_like_substack(body: bytes) -> bool:
    """True when the page declares a Substack generator — used to
    reclassify a custom-domain Substack publication from ``generic`` to
    ``substack`` after the OG pass (honest upgrade of the classification,
    recorded in the digest's provenance)."""
    return bool(_SUBSTACK_GENERATOR_RE.search(
        body.decode("utf-8", errors="replace")[: MAX_BODY_BYTES]
    ))
