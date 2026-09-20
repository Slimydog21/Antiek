"""Link Monster — platform classification.

One URL in, one platform label out. The label drives the extraction
ladder (``oembed.py``) and the document_type mapping (``store.py``).
Host matching is deliberately conservative: unknown hosts fall to
``generic`` (the URL adapter's lane) rather than raising, so the
Monster never refuses a link just because a host pattern is missing.

Stable contract — the platform Literal is the vocabulary every other
Link Monster module keys on. Add a new platform by extending
``_HOST_RULES`` and the ``Platform`` Literal together; keep the
Literal in lock-step with the document_type map in ``store.py``.
"""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlparse

Platform = Literal[
    "youtube",
    "x",
    "instagram",
    "tiktok",
    "substack",
    "generic",
]

# Host suffix -> platform. Longest-suffix-first so ``music.youtube.com``
# hits youtube before generic. Suffixes are matched on the host with
# leading dots trimmed, so ``x.com`` also matches ``www.x.com`` and
# ``mobile.twitter.com`` matches ``twitter.com``.
_HOST_RULES: tuple[tuple[str, Platform], ...] = (
    ("youtube.com", "youtube"),
    ("youtu.be", "youtube"),
    ("x.com", "x"),
    ("twitter.com", "x"),
    ("instagram.com", "instagram"),
    ("instagr.am", "instagram"),
    ("tiktok.com", "tiktok"),
    ("substack.com", "substack"),
)

# Substack custom domains carry no substack.com suffix; they are
# detected at digest time via og:site_name / meta generator (see
# oembed.py: _detect_substack_custom_domain). Pure-host classification
# cannot see them — that is an honest limitation, not a bug.

_SUFFIX_ALIASES = {
    "www": "",
    "m": "",
    "mobile": "",
    "music": "",
    "vm": "",
    "vt": "",
}


def normalize_host(host: str) -> str:
    """Lowercase, strip trailing dot, drop one well-known mobile/www
    label from the front. Returns the host usable for suffix matching."""
    h = host.lower().rstrip(".")
    parts = h.split(".")
    if len(parts) > 1 and parts[0] in _SUFFIX_ALIASES:
        h = ".".join(parts[1:])
    return h


def classify(url: str) -> Platform:
    """Classify a URL string into a Platform. Never raises for a
    parseable http(s) URL; garbage input raises ValueError so the
    route can return a typed 400 instead of a 500."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(f"unsupported URL: {url!r}")
    host = normalize_host(parsed.hostname)
    for suffix, platform in _HOST_RULES:
        if host == suffix or host.endswith("." + suffix):
            return platform
    return "generic"


def platform_label(platform: Platform) -> str:
    """Human label for the platform (feed chips, provenance chips)."""
    return {
        "youtube": "YouTube",
        "x": "X",
        "instagram": "Instagram",
        "tiktok": "TikTok",
        "substack": "Substack",
        "generic": "Web",
    }[platform]


# document_type values the store layer maps platforms to (must be
# members of the substrate's third-party vocabulary — see
# substrate/constants.THIRD_PARTY_DOCUMENT_TYPES for the deny-by-
# default content_class guard that keys off these exact strings).
PLATFORM_DOCUMENT_TYPE: dict[Platform, str] = {
    "youtube": "video_transcript",
    "x": "social_thread",
    "instagram": "web_link",
    "tiktok": "web_link",
    "substack": "newsletter_post",
    "generic": "web_article",
}

# oEmbed endpoints per platform (None = no standard public endpoint;
# those platforms ride the OpenGraph/DOM rungs of the ladder).
PLATFORM_OEMBED_ENDPOINT: dict[Platform, str | None] = {
    "youtube": "https://www.youtube.com/oembed",
    "x": "https://publish.twitter.com/oembed",
    "instagram": "https://api.instagram.com/oembed",
    "tiktok": "https://www.tiktok.com/oembed",
    "substack": None,
    "generic": None,
}
