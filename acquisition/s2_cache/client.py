"""Persist-before-return wrapper for PR #760's Semantic Scholar client."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from typing import Protocol, cast

from .store import S2SnapshotError, S2SnapshotStore


class S2Enricher(Protocol):
    def enrich(self, ids: list[str], fields: tuple[str, ...]) -> list[dict[str, object]]: ...


class CachedS2Enricher:
    """Calls the governed client, then atomically publishes the entire response."""

    def __init__(
        self,
        client: S2Enricher,
        store: S2SnapshotStore,
        *,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._client, self._store, self._now = client, store, now

    def enrich(self, ids: list[str]) -> tuple[dict[str, object], ...]:
        if type(ids) is not list or not ids:
            raise S2SnapshotError("ids must be a nonempty exact list")
        if any(type(id) is not str or not id.strip() or id != id.strip() for id in ids):
            raise S2SnapshotError("ids must contain trimmed nonempty exact strings")
        if len(ids) != len(set(ids)):
            raise S2SnapshotError("ids must be unique")
        raw = self._client.enrich(list(ids), fields=("title", "abstract"))
        if (
            type(raw) is not list
            or len(raw) != len(ids)
            or any(type(item) is not dict for item in raw)
        ):
            raise S2SnapshotError("S2 response must contain one exact dict per requested id")
        timestamp = self._now()
        if type(timestamp) not in {int, float} or isinstance(timestamp, bool):
            raise S2SnapshotError("clock must return a finite nonnegative Unix timestamp")
        numeric = float(cast(int | float, timestamp))
        if not math.isfinite(numeric) or numeric < 0:
            raise S2SnapshotError("clock must return a finite nonnegative Unix timestamp")
        snapshots: list[dict[str, object]] = []
        for requested_id, item in zip(ids, raw, strict=True):
            if frozenset(item) != {"paperId", "title", "abstract"}:
                raise S2SnapshotError("S2 response record must have exact requested fields")
            paper_id, title = item.get("paperId"), item.get("title")
            abstract = item.get("abstract")
            snapshots.append(
                {
                    "paperId": paper_id,
                    "requestedId": requested_id,
                    "title": title,
                    "abstract": abstract,
                    "fetched_at": numeric,
                    "source": "semantic_scholar",
                }
            )
        return self._store.publish(tuple(snapshots))
