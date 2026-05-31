"""Substack RSS feed client — fetch and parse subscribed-publication posts.

Cloned byte-for-byte in structure from ``acquisition/podcasts/client.py``:
a thin client that downloads + parses an RSS feed into typed dataclasses,
with an injectable ``httpx.Client`` so tests can supply a ``MockTransport``
without hitting the network.

Feed parsing uses ``feedparser`` (the ``[rss]`` optional extra). The import
is guarded so the package can be imported without the extra installed; the
error only fires when you actually try to fetch a feed — same guard +
``pip install -e '.[rss]'`` hint as ``podcasts/client.py``.

A subscribed Substack publication exposes its feed at ``<publication>/feed``.
Each ``<item>`` usually carries the full post HTML in ``content:encoded``
(feedparser surfaces this as ``entry.content[0].value``); paid/paywalled
posts arrive TRUNCATED — see ``detect_truncation`` for the full-vs-truncated
heuristic. We store ONLY what the feed returned; we never fabricate a body.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx

from substrate.text import html_to_markdown


# Reuse the exact import-guard message shape from podcasts/client.py:22-25.
_FEEDPARSER_HINT = (
    "feedparser is required for substack ingestion. "
    "Install it with: pip install -e '.[rss]'"
)


# ---------------------------------------------------------------------------
# Truncation (paywall) detection constants.
#
# Source: real Substack paid-post RSS samples end the truncated body with one
# of these publisher-inserted markers (the feed itself stops there — there is
# no remainder to fetch, and fetching the public page would be a distinct
# acquisition-ToS question this connector does not own). The strings below are
# transcribed from observed paywalled-feed footers; matched case-insensitively
# as substrings of the rendered markdown body.
# ---------------------------------------------------------------------------
TRUNCATION_MARKERS: tuple[str, ...] = (
    "this post is for paid subscribers",
    "this post is for paying subscribers",
    "subscribe to keep reading",
    "subscribe to read more",
    "keep reading with a 7-day free trial",
    "read the full post",
    "this episode is for paid subscribers",
    "upgrade to paid to read",
)

# Below this stripped-text length we treat a body as suspiciously short — a
# weak secondary signal, only fires when the entry ALSO advertised more
# content (a ``summary`` longer than the rendered body). Justified: a genuine
# full Substack essay is typically thousands of characters; an entry whose
# rendered body is under ~280 chars yet whose summary is longer is almost
# certainly a teaser/truncation. Conservative on purpose — markers are the
# primary signal; this only adds the "short_body" reason, never removes one.
MIN_FULL_BODY_CHARS = 280

# Truncation reason tags persisted in document metadata.
TRUNCATION_REASON_MARKER = "marker"
TRUNCATION_REASON_SHORT = "short_body"
TRUNCATION_REASON_NONE = "none"


@dataclass
class Post:
    """A single Substack post parsed from a feed entry.

    ``body_html`` holds exactly what the feed returned (full or truncated);
    ``body_markdown`` is the chunker-friendly rendering via the shared
    ``html_to_markdown`` extractor that ``acquisition/urls`` uses.
    """

    guid: str
    title: str
    body_html: str
    body_markdown: str
    published_at: Optional[datetime]
    post_url: Optional[str] = None
    author: str = ""
    truncated: bool = False
    truncation_reason: str = TRUNCATION_REASON_NONE


@dataclass
class Publication:
    """A Substack publication feed: publication-level metadata + posts."""

    feed_url: str
    title: str
    posts: list[Post]
    description: str = ""


def _require_feedparser():
    try:
        import feedparser  # noqa: WPS433 (runtime import is intentional)
    except ImportError as exc:  # pragma: no cover - import guard
        raise ImportError(_FEEDPARSER_HINT) from exc
    return feedparser


def substack_doc_id(guid: str) -> str:
    """Deterministic document id for a Substack post keyed on GUID.

    Same shape as ``podcast_doc_id`` (``doc-pod-…``) and ``url_doc_id``
    (``doc-url-…``): ``doc-sub-<sha256(guid)[:16]>``.
    """
    if not guid:
        raise ValueError("guid must be non-empty")
    digest = hashlib.sha256(guid.encode("utf-8")).hexdigest()[:16]
    return f"doc-sub-{digest}"


def _parse_published(entry) -> Optional[datetime]:
    """Extract a UTC datetime from a feed entry, if present.

    Mirrors ``podcasts/client.py:_parse_published``.
    """
    for attr in ("published_parsed", "updated_parsed"):
        struct = getattr(entry, attr, None) or (
            entry.get(attr) if hasattr(entry, "get") else None
        )
        if struct:
            try:
                return datetime(*struct[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
    return None


def _entry_guid(entry) -> str:
    """GUID identity: entry id/guid, falling back to link. Empty if none."""
    return (
        entry.get("id")
        or entry.get("guid")
        or entry.get("link")
        or ""
    )


def _entry_body_html(entry) -> str:
    """Full post HTML: ``content:encoded`` first, else ``summary``.

    feedparser surfaces ``content:encoded`` as ``entry.content[0].value``.
    We never look beyond the feed for a missing body.
    """
    content = entry.get("content") or []
    if content:
        first = content[0]
        val = first.get("value") if hasattr(first, "get") else None
        if val:
            return val
    return entry.get("summary", "") or ""


def _stripped_len(markdown: str) -> int:
    """Length of the body with surrounding whitespace stripped."""
    return len(markdown.strip())


def detect_truncation(
    *, body_markdown: str, summary_html: str = ""
) -> tuple[bool, str]:
    """Full-vs-truncated heuristic. Returns ``(truncated, reason)``.

    Primary signal: a case-insensitive substring match against the documented
    ``TRUNCATION_MARKERS`` (publisher-inserted paywall footers). Secondary,
    weaker signal: an abnormally short rendered body (< ``MIN_FULL_BODY_CHARS``)
    WHILE the entry advertised more (a ``summary`` longer than the body) — this
    catches teaser entries that lack an explicit marker.

    This NEVER alters the body. It only reports a verdict; the caller stores
    exactly what the feed returned (rigor #1: a truncated body stays truncated).
    """
    haystack = body_markdown.lower()
    for marker in TRUNCATION_MARKERS:
        if marker in haystack:
            return True, TRUNCATION_REASON_MARKER
    body_len = _stripped_len(body_markdown)
    if body_len < MIN_FULL_BODY_CHARS:
        # Only fire the short-body signal when the entry advertised more.
        summary_len = len((summary_html or "").strip())
        if summary_len > body_len:
            return True, TRUNCATION_REASON_SHORT
    return False, TRUNCATION_REASON_NONE


def fetch_feed(
    feed_url: str,
    *,
    max_posts: Optional[int] = None,
    client: Optional[httpx.Client] = None,
) -> Publication:
    """Download and parse a Substack RSS feed into a ``Publication``.

    A caller may inject an ``httpx.Client`` (e.g. backed by a
    ``MockTransport``) for testing; otherwise a default client is used.
    Identical download/parse shape to ``podcasts.fetch_feed``.
    """
    feedparser = _require_feedparser()
    owns_client = client is None
    if client is None:
        client = httpx.Client(timeout=30.0, follow_redirects=True)
    try:
        resp = client.get(feed_url)
        resp.raise_for_status()
        raw = resp.content
    finally:
        if owns_client:
            client.close()

    parsed = feedparser.parse(raw)
    pub_title = ""
    pub_description = ""
    if getattr(parsed, "feed", None):
        pub_title = parsed.feed.get("title", "") or ""
        pub_description = parsed.feed.get("description", "") or ""

    posts: list[Post] = []
    entries = parsed.entries or []
    if max_posts is not None:
        entries = entries[:max_posts]
    for entry in entries:
        guid = _entry_guid(entry)
        if not guid:
            # Rigor #3 edge case: no GUID and no link — skip, never mint a
            # random id. (Caller-visible: the post simply does not ingest.)
            continue
        title = entry.get("title", "") or ""
        body_html = _entry_body_html(entry)
        # Render to chunker-friendly markdown via the SHARED extractor that
        # acquisition/urls uses (substrate.text.html_to_markdown) — do not
        # hand-roll a parser. We discard the extracted <title> here (we use
        # the feed entry title) and keep only the markdown body.
        _extracted_title, body_markdown = html_to_markdown(body_html)
        summary_html = entry.get("summary", "") or ""
        truncated, reason = detect_truncation(
            body_markdown=body_markdown, summary_html=summary_html
        )
        author = entry.get("author", "") or ""
        post_url = entry.get("link")
        posts.append(
            Post(
                guid=guid,
                title=title,
                body_html=body_html,
                body_markdown=body_markdown,
                published_at=_parse_published(entry),
                post_url=post_url,
                author=author,
                truncated=truncated,
                truncation_reason=reason,
            )
        )
    return Publication(
        feed_url=feed_url,
        title=pub_title,
        posts=posts,
        description=pub_description,
    )
