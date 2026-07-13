"""Immutable acquisition snapshots behind the two-verb corpus contract."""

from __future__ import annotations

import datetime
import math
from dataclasses import dataclass

from substrate.corpus_contract import (
    CorpusContractError,
    CorpusDocument,
    CorpusHit,
    CorpusMiss,
    FetchResult,
    Provenance,
)

_SNIPPET_MAX = 200


@dataclass(frozen=True)
class _Entry:
    id: str
    source_kind: str
    search_text: str
    content: str | None
    retrieved_at: datetime.datetime
    license_class: str
    miss_reason: str = "content unavailable by source policy"


def _score(text: str, query: str) -> float:
    folded, needle = text.casefold(), query.casefold()
    return float(folded.count(needle)) + float(len(needle)) / max(1, len(folded))


def _snippet(text: str, query: str) -> str:
    at = text.casefold().find(query.casefold())
    start = max(0, at - 80)
    end = min(len(text), start + _SNIPPET_MAX)
    return text[max(0, end - _SNIPPET_MAX) : end]


class AcquisitionCorpusAdapter:
    """A detached snapshot; no reader or mutable record handle is retained."""

    def __init__(self, entries: tuple[_Entry, ...]) -> None:
        if type(entries) is not tuple:
            raise CorpusContractError("entries must be an exact tuple")
        if any(type(entry) is not _Entry for entry in entries):
            raise CorpusContractError("entries must contain exact normalized records")
        ids = tuple(entry.id for entry in entries)
        if len(ids) != len(set(ids)):
            raise CorpusContractError("duplicate acquisition record id")
        self._entries = entries

    def search(self, query: str) -> tuple[CorpusHit, ...]:
        if type(query) is not str:
            raise CorpusContractError("query must be an exact str")
        wanted = query.strip()
        if not wanted:
            return ()
        if "\n" in wanted or "\r" in wanted:
            raise CorpusContractError("query must be a single line")
        hits = tuple(
            CorpusHit(
                id=entry.id,
                score=_score(entry.search_text, wanted),
                snippet=_snippet(entry.search_text, wanted),
            )
            for entry in self._entries
            if wanted.casefold() in entry.search_text.casefold()
        )
        assert all(math.isfinite(hit.score) for hit in hits)
        return tuple(sorted(hits, key=lambda hit: (-hit.score, hit.id)))

    def fetch(self, id: str) -> FetchResult:
        if type(id) is not str or not id.strip():
            raise CorpusContractError("id must be a nonempty exact str")
        for entry in self._entries:
            if entry.id != id:
                continue
            if entry.content is None:
                return CorpusMiss(id=id, reason=entry.miss_reason)
            return CorpusDocument(
                content=entry.content,
                provenance=Provenance(
                    source_kind=entry.source_kind,
                    origin_ref=entry.id,
                    retrieved_at=entry.retrieved_at,
                    license_class=entry.license_class,
                ),
            )
        return CorpusMiss(id=id)
