"""Substack RSS feed client — fetch and parse subscribed-publication posts.

Cloned in structure from ``acquisition/podcasts/client.py`` (and reusing the
HTML→markdown extractor ``acquisition/urls`` uses): a thin client that
downloads + parses an RSS feed into typed dataclasses, with an injectable
``httpx.Client`` so tests can supply a ``MockTransport`` without hitting the
network.

Feed parsing uses ``feedparser`` (the ``[rss]`` optional extra). The import is
guarded so the package can be imported without the extra installed; the error
only fires when you actually try to fetch a feed — same guard +
``pip install -e '.[rss]'`` hint as ``podcasts/client.py:209-213``.

A subscribed Substack publication exposes its feed at ``<publication>/feed``.
Each ``<item>`` usually carries the full post HTML in ``content:encoded``
(feedparser surfaces this as ``entry.content[0].value``); paid/paywalled posts
arrive TRUNCATED — see ``detect_truncation``. We store ONLY what the feed
returned; we never fabricate a body.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

import httpx

# Reuse the SHARED HTML→markdown extractor that acquisition/urls uses (rigor #4:
# do not hand-roll a parser). It takes raw bytes/str and returns a MarkdownDoc.
from acquisition.urls.extract import html_to_markdown

DEFAULT_USER_AGENT = "Antiek/0.1 (acquisition.substack)"
DEFAULT_TIMEOUT_S = 30.0


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
# weak SECONDARY signal that fires only when the entry ALSO advertised more
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
    ``acquisition.urls.extract.html_to_markdown`` extractor.
    """

    guid: str
    title: str
    body_html: str
    body_markdown: str
    published_at: datetime | None
    post_url: str | None = None
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
        import feedparser  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - import guard
        raise ImportError(
            "acquisition.substack requires feedparser. Run "
            "`pip install -e '.[rss]'`."
        ) from exc
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


def _parse_published(entry) -> datetime | None:
    """Extract a UTC datetime from a feed entry, if present.

    Mirrors ``podcasts/client.py:_parse_published`` (feedparser converts
    ``pubDate`` into a ``published_parsed`` struct_time; we convert to UTC).
    """
    for attr in ("published_parsed", "updated_parsed"):
        struct = (
            entry.get(attr) if hasattr(entry, "get") else getattr(entry, attr, None)
        )
        if struct:
            try:
                import time as _time

                epoch = _time.mktime(struct)  # type: ignore[arg-type]
                return datetime.fromtimestamp(epoch, tz=UTC)
            except (TypeError, ValueError, OverflowError):
                continue
    return None


def _entry_get(entry, key: str, default=""):
    if hasattr(entry, "get"):
        return entry.get(key, default)
    return getattr(entry, key, default)


def _entry_guid(entry) -> str:
    """GUID identity: entry id/guid, falling back to link. Empty if none."""
    return (
        _entry_get(entry, "id", "")
        or _entry_get(entry, "guid", "")
        or _entry_get(entry, "link", "")
        or ""
    )


def _entry_body_html(entry) -> str:
    """Full post HTML: ``content:encoded`` first, else ``summary``.

    feedparser surfaces ``content:encoded`` as ``entry.content[0].value``.
    We never look beyond the feed for a missing body.
    """
    content = _entry_get(entry, "content", None) or []
    if content:
        first = content[0]
        val = (
            first.get("value")
            if hasattr(first, "get")
            else getattr(first, "value", None)
        )
        if val:
            return val
    return _entry_get(entry, "summary", "") or ""


def _render_body_markdown(
    body_html: str, *, title: str, base_url: str | None
) -> str:
    """Render an RSS body FRAGMENT to chunker-friendly markdown.

    The shared ``acquisition.urls.extract.html_to_markdown`` is a readability
    MAIN-CONTENT extractor: it expects a full HTML *document* and returns the
    article body, discarding chrome. An RSS ``content:encoded`` value is a body
    FRAGMENT (bare ``<p>…`` markup), which the extractor would drop as
    non-article (verified: a bare fragment renders to a 0-length body). So we
    wrap the fragment in a minimal ``<html><body><article>`` document and feed
    THAT to the same extractor (rigor #4: reuse the project extractor, do NOT
    hand-roll a parser; we only give it the structure it expects). The
    ``<article>`` element is the readability anchor; the feed entry title is kept
    by the caller regardless of what the extractor parses.
    """
    if not body_html.strip():
        return ""
    safe_title = (title or "").replace("<", " ").replace(">", " ")
    document = (
        "<!DOCTYPE html><html><head><title>"
        + safe_title
        + "</title></head><body><article>"
        + body_html
        + "</article></body></html>"
    )
    md_doc = html_to_markdown(document.encode("utf-8"), base_url=base_url)
    return md_doc.markdown


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
    body_len = len(body_markdown.strip())
    if body_len < MIN_FULL_BODY_CHARS:
        # Only fire the short-body signal when the entry advertised more.
        summary_len = len((summary_html or "").strip())
        if summary_len > body_len:
            return True, TRUNCATION_REASON_SHORT
    return False, TRUNCATION_REASON_NONE


def fetch_feed(
    feed_url: str,
    *,
    max_posts: int | None = None,
    client: httpx.Client | None = None,
) -> Publication:
    """Download and parse a Substack RSS feed into a ``Publication``.

    A caller may inject an ``httpx.Client`` (e.g. backed by a ``MockTransport``)
    for testing; otherwise a default short-lived client is used. Identical
    download/parse shape to ``podcasts.fetch_feed``.
    """
    feedparser = _require_feedparser()
    headers = {"User-Agent": DEFAULT_USER_AGENT}

    # HOST-GLOBAL arXiv GOVERNANCE (compliance boundary): every raw external HTTP
    # egress in the tree must route through the host-global arXiv governor so an
    # arXiv host can never be hit un-spaced (the historical IP-ban hole),
    # REGARDLESS of which module it lives in. A Substack feed host is never arXiv,
    # so ``govern_if_arxiv`` calls ``_send`` directly with zero overhead — but the
    # wrap is the sanctioned, scanner-visible pattern (tools/lint/
    # rate_governor_check, mirroring acquisition/urls/client.py), not an allowlist
    # exception, so a future feed_url change cannot silently re-open the hole.
    from acquisition.arxiv.rate_governor import govern_if_arxiv

    if client is not None:
        def _send() -> httpx.Response:
            return client.get(feed_url, headers=headers, timeout=DEFAULT_TIMEOUT_S)

        r = cast("httpx.Response", govern_if_arxiv(feed_url, _send))
    else:
        with httpx.Client(
            follow_redirects=True,
            timeout=DEFAULT_TIMEOUT_S,  # module default; same pattern as acquisition/papers/core.py DEFAULT_TIMEOUT_S
        ) as c:
            def _send() -> httpx.Response:
                return c.get(feed_url, headers=headers, timeout=DEFAULT_TIMEOUT_S)

            r = cast("httpx.Response", govern_if_arxiv(feed_url, _send))
    r.raise_for_status()
    raw = r.content

    parsed = feedparser.parse(raw)
    channel = (
        parsed.get("feed", {})
        if hasattr(parsed, "get")
        else getattr(parsed, "feed", {})
    )
    pub_title = (
        channel.get("title", "")
        if hasattr(channel, "get")
        else getattr(channel, "title", "")
    ) or ""
    pub_description = (
        channel.get("description", "")
        if hasattr(channel, "get")
        else getattr(channel, "description", "")
    ) or ""

    posts: list[Post] = []
    entries = (parsed.entries if hasattr(parsed, "entries") else []) or []
    if max_posts is not None:
        entries = entries[:max_posts]
    for entry in entries:
        guid = _entry_guid(entry)
        if not guid:
            # Rigor #3 edge case: no GUID and no link — skip, never mint a
            # random id. (Caller-visible: the post simply does not ingest.)
            continue
        title = _entry_get(entry, "title", "") or ""
        body_html = _entry_body_html(entry)
        link = _entry_get(entry, "link", None) or None
        # Render to chunker-friendly markdown via the SHARED extractor that
        # acquisition/urls uses (wrapped so the readability extractor sees a
        # document, not a bare fragment — see _render_body_markdown).
        body_markdown = _render_body_markdown(body_html, title=title, base_url=link)
        summary_html = _entry_get(entry, "summary", "") or ""
        truncated, reason = detect_truncation(
            body_markdown=body_markdown, summary_html=summary_html
        )
        posts.append(
            Post(
                guid=guid,
                title=title,
                body_html=body_html,
                body_markdown=body_markdown,
                published_at=_parse_published(entry),
                post_url=link,
                author=_entry_get(entry, "author", "") or "",
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
