"""Read-only corpus adapter over validated CORE metadata snapshots."""

from __future__ import annotations

import datetime
import math
from typing import cast

from substrate.corpus_contract import (
    CorpusContractError,
    CorpusDocument,
    CorpusHit,
    CorpusMiss,
    FetchResult,
    Provenance,
)

_SNIPPET_MAX = 200


def _content(record: dict[str, object]) -> str:
    title = str(record["title"])
    abstract = record["abstract"]
    authors = cast(list[str], record["authors"])
    parts = [title]
    if authors:
        parts.append("Authors: " + ", ".join(str(item) for item in authors))
    if abstract is not None:
        parts.append(str(abstract))
    return "\n\n".join(parts)


class CoreCorpusAdapter:
    def __init__(self, records: tuple[dict[str, object], ...]) -> None:
        if type(records) is not tuple or any(type(item) is not dict for item in records):
            raise CorpusContractError("CORE records must be an exact tuple of exact dicts")
        self._records = records

    def search(self, query: str) -> tuple[CorpusHit, ...]:
        if type(query) is not str:
            raise CorpusContractError("query must be an exact str")
        wanted = query.strip()
        if not wanted:
            return ()
        if wanted != query or "\n" in wanted or "\r" in wanted:
            raise CorpusContractError("query must be trimmed and single-line")
        folded = wanted.casefold()
        hits: list[CorpusHit] = []
        for record in self._records:
            text = "\n".join(
                part
                for part in (
                    str(record["id"]),
                    str(record["doi"] or ""),
                    _content(record),
                )
                if part
            )
            haystack = text.casefold()
            at = haystack.find(folded)
            if at < 0:
                continue
            score = float(haystack.count(folded)) + float(len(folded)) / max(1, len(haystack))
            if not math.isfinite(score):
                raise CorpusContractError("CORE search score is not finite")
            start = max(0, at - 80)
            end = min(len(text), start + _SNIPPET_MAX)
            snippet = text[max(0, end - _SNIPPET_MAX) : end]
            hits.append(CorpusHit(id=str(record["id"]), score=score, snippet=snippet))
        return tuple(sorted(hits, key=lambda hit: (-hit.score, hit.id)))

    def fetch(self, id: str) -> FetchResult:
        if type(id) is not str or not id.strip():
            raise CorpusContractError("id must be a nonempty exact str")
        for record in self._records:
            if record["id"] != id:
                continue
            fetched_at = record["fetched_at"]
            if type(fetched_at) not in {int, float} or isinstance(fetched_at, bool):
                raise CorpusContractError("CORE fetched_at violated the validated snapshot")
            return CorpusDocument(
                content=_content(record),
                provenance=Provenance(
                    source_kind="core",
                    origin_ref=id,
                    retrieved_at=datetime.datetime.fromtimestamp(
                        float(cast(int | float, fetched_at)), tz=datetime.UTC
                    ),
                    # This corpus contains metadata/abstracts only. A provider's
                    # declared full-text license is preserved in the snapshot but
                    # never promoted into metadata redistribution authority.
                    license_class="source_terms_governed_metadata",
                ),
            )
        return CorpusMiss(id=id)
