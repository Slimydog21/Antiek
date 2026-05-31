"""Operator-curated Substack subscription manifest — loader + driver.

Substack publications are an operator-curated LIST, not a crawl (out of scope:
any feed-discovery spider). The repo ships only ``subscriptions.example.json``;
the real operator manifest is gitignored
(``acquisition/substack/subscriptions.json`` / ``subscriptions.local.json``) or
operator-supplied. This mirrors how ``acquisition/opt_in`` ships an
``example_manifest.json`` and never live data.

Manifest schema (a list of entries under ``"publications"``):

    {
      "publications": [
        {"name": "...", "feed_url": "https://x.substack.com/feed"},
        {"name": "...", "base_url": "https://x.substack.com"},
        {"name": "...", "base_url": "https://www.customdomain.com",
         "source_tier": 4}
      ]
    }

Each entry MUST resolve to a feed URL via ``resolve_feed_url``: an explicit
``feed_url`` wins; else ``base_url`` gets ``/feed`` appended. Custom-domain
publications (not ``*.substack.com``) that still expose ``/feed`` are supported
— resolution is purely structural, no host allowlist.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from .adapter import (
    DEFAULT_SUBSTACK_SOURCE_TIER,
    PublicationIngestSummary,
    ingest_publication_feed,
)


@dataclass
class Subscription:
    """One operator-subscribed publication."""

    name: str
    feed_url: str
    source_tier: int = DEFAULT_SUBSTACK_SOURCE_TIER


class SubscriptionManifestError(ValueError):
    """Raised on a malformed manifest entry — names the offending entry."""


def resolve_feed_url(entry: dict) -> str:
    """Resolve an entry to its feed URL deterministically.

    - explicit ``feed_url`` → returned as-is;
    - else ``base_url`` → ``base_url.rstrip('/') + '/feed'`` (works for
      ``*.substack.com`` AND custom domains; a base already ending in ``/feed``
      is left intact);
    - else raise ``SubscriptionManifestError``.
    """
    feed_url = entry.get("feed_url")
    if feed_url:
        return feed_url
    base_url = entry.get("base_url")
    if base_url:
        base = base_url.rstrip("/")
        if base.endswith("/feed"):
            return base
        return base + "/feed"
    raise SubscriptionManifestError(
        "entry must have 'feed_url' or 'base_url': "
        f"{json.dumps(entry, sort_keys=True)}"
    )


def _parse_entry(entry, index: int) -> Subscription:
    if not isinstance(entry, dict):
        raise SubscriptionManifestError(
            f"publications[{index}] is not an object: {entry!r}"
        )
    name = entry.get("name")
    if not name:
        raise SubscriptionManifestError(
            f"publications[{index}] is missing a 'name': "
            f"{json.dumps(entry, sort_keys=True)}"
        )
    try:
        feed_url = resolve_feed_url(entry)
    except SubscriptionManifestError as exc:
        raise SubscriptionManifestError(
            f"publications[{index}] ({name!r}) has no resolvable feed: {exc}"
        ) from exc
    source_tier = entry.get("source_tier", DEFAULT_SUBSTACK_SOURCE_TIER)
    if not isinstance(source_tier, int):
        raise SubscriptionManifestError(
            f"publications[{index}] ({name!r}) source_tier must be an int, "
            f"got {source_tier!r}"
        )
    return Subscription(name=name, feed_url=feed_url, source_tier=source_tier)


def load_subscriptions(path: str) -> list[Subscription]:
    """Parse and validate a subscriptions manifest.

    Raises ``SubscriptionManifestError`` (a ``ValueError`` subclass) — never a
    bare ``KeyError`` — on a malformed entry, naming the offending entry by
    index and name. Returns the resolved ``Subscription`` list.
    """
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict) or "publications" not in data:
        raise SubscriptionManifestError(
            f"manifest must be an object with a 'publications' list: {path}"
        )
    publications = data["publications"]
    if not isinstance(publications, list):
        raise SubscriptionManifestError(
            f"'publications' must be a list in: {path}"
        )
    return [_parse_entry(entry, i) for i, entry in enumerate(publications)]


def ingest_subscriptions(
    path: str,
    *,
    investigation_id: str,
    db_path: Optional[str] = None,
    max_posts: Optional[int] = None,
    embedder=None,
    client=None,
) -> list[PublicationIngestSummary]:
    """Driver: load the manifest and ingest every publication's feed.

    Iterates the manifest and calls ``ingest_publication_feed`` per entry,
    aggregating per-publication results (the way ``podcasts.ingest_feed``
    aggregates per-episode results). Cross-feed idempotency holds because
    identity is the post GUID via ``on_conflict="ignore"`` — a duplicate GUID
    appearing in two feeds in one run is written exactly once.

    NOTE: a single ``client`` is reused across all feeds only in tests where a
    ``MockTransport`` handler routes by request URL; in production each feed uses
    a fresh default client (pass ``client=None``).
    """
    subscriptions = load_subscriptions(path)
    summaries: list[PublicationIngestSummary] = []
    for sub in subscriptions:
        summaries.append(
            ingest_publication_feed(
                sub.feed_url,
                investigation_id=investigation_id,
                db_path=db_path,
                max_posts=max_posts,
                source_tier=sub.source_tier,
                embedder=embedder,
                client=client,
            )
        )
    return summaries
