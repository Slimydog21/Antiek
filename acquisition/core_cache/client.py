"""Persist-before-return wrapper for the existing CORE search connector."""

from __future__ import annotations

import time
from collections.abc import Callable

from acquisition.papers._pipeline import PaperRecord

from .store import CoreSnapshotError, CoreSnapshotStore

SearchWorks = Callable[[str, int], list[PaperRecord]]


class CachedCoreSearch:
    def __init__(
        self,
        search: SearchWorks,
        store: CoreSnapshotStore,
        *,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._search, self._store, self._now = search, store, now

    def sync(self, query: str, *, max_records: int) -> tuple[dict[str, object], ...]:
        if type(query) is not str or not query.strip() or query != query.strip():
            raise CoreSnapshotError("query must be a trimmed nonempty exact str")
        if type(max_records) is not int or isinstance(max_records, bool) or not 1 <= max_records <= 100:
            raise CoreSnapshotError("max_records must be an exact int in 1..100")
        records = self._search(query, max_records)
        if type(records) is not list or not records or len(records) > max_records:
            raise CoreSnapshotError("CORE search returned an invalid record count")
        fetched_at = self._now()
        selected: list[dict[str, object]] = []
        for item in records:
            if type(item) is not PaperRecord or item.source != "core":
                raise CoreSnapshotError("CORE search returned an invalid paper record")
            selected.append(
                {
                    "id": item.source_id,
                    "title": item.title,
                    "abstract": item.abstract,
                    "doi": item.doi,
                    "arxiv_id": item.arxiv_id,
                    "authors": list(item.authors),
                    "declared_license": item.license,
                    "fetched_at": fetched_at,
                    "source": "core",
                }
            )
        return self._store.publish(tuple(selected))
