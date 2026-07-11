"""Persist-before-return wrapper for PR #760's cursor-paged OpenAlex client."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from .store import OpenAlexSnapshotError, OpenAlexSnapshotStore


class WorksClient(Protocol):
    def works(self, *, search: str) -> Iterator[dict[str, object]]: ...


class CachedOpenAlexSearch:
    def __init__(self, client: WorksClient, store: OpenAlexSnapshotStore) -> None:
        self._client, self._store = client, store

    def sync(self, query: str, *, max_records: int) -> tuple[dict[str, object], ...]:
        if type(query) is not str or not query.strip() or query != query.strip():
            raise OpenAlexSnapshotError("query must be a trimmed nonempty exact str")
        if (
            type(max_records) is not int
            or isinstance(max_records, bool)
            or not 1 <= max_records <= 100
        ):
            raise OpenAlexSnapshotError("max_records must be an exact int in 1..100")
        selected: list[dict[str, object]] = []
        for item in self._client.works(search=query):
            if type(item) is not dict:
                raise OpenAlexSnapshotError("OpenAlex client yielded a non-dict record")
            selected.append(
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "abstract_inverted_index": item.get("abstract_inverted_index"),
                    "fetched_at": item.get("fetched_at"),
                }
            )
            if len(selected) == max_records:
                break
        if not selected:
            raise OpenAlexSnapshotError("OpenAlex search returned no records")
        return self._store.publish(tuple(selected))
