"""Persist-before-return wrapper for PR #760's Substack RSS client."""

from __future__ import annotations

from typing import Protocol

from acquisition.corpus_bridge import from_substack

from .store import SubstackSnapshotError, SubstackSnapshotStore


class FeedClient(Protocol):
    def feed(self) -> list[dict[str, object]]: ...


class CachedSubstackFeed:
    def __init__(
        self, client: FeedClient, store: SubstackSnapshotStore, *, publication: str
    ) -> None:
        self._client, self._store = client, store
        self._publication = publication

    def sync(self) -> tuple[dict[str, object], ...]:
        raw = self._client.feed()
        if type(raw) is not list or any(type(item) is not dict for item in raw):
            raise SubstackSnapshotError("feed must return an exact list of exact dicts")
        records = tuple(
            {
                "url": item.get("url"),
                "title": item.get("title"),
                "body_html": item.get("body_html"),
                "accessible": item.get("accessible"),
                "fetched_at": item.get("fetched_at"),
                "publication": self._publication,
            }
            for item in raw
        )
        # Reuse the corpus trust boundary before any bytes become authoritative.
        from_substack(
            tuple(
                {key: value for key, value in item.items() if key != "publication"}
                for item in records
            )
        )
        return self._store.publish(records)
