"""Twin-substrate search — intelligent retrieval over the distilled twin layer.

The operator's vision (ask #14 + the recursive-note-taker idea, ask #4): every
information asset has a *twin* — the LLM-proposed insights and questions the
asset surfaces. That twin substrate is a **distilled** knowledge layer, richer
for retrieval than raw passages: an insight or question is already the
*signal*, not the noise. This module is the pure search engine over that layer
— the "intelligent search over my dream of an infinite information platform"
made real for the part of the graph that matters most.

**Distinct from** ``substrate/graph/search.py``. That module does **semantic**
(cosine-embedding) retrieval over raw content chunks. This module does
**lexical** (term-frequency) retrieval over the **twin** layer (insights +
questions), and is the substrate the semantic layer or the routes layer composes
with: materialize twins into records → index → query. Keeping it lexical + pure
means it carries **no embedding dependency** (zero-import, testable in isolation);
a future routes layer can re-rank its hits with embeddings if it wants.

**Pure — no I/O, no network, no embedding model.** ``TwinIndex`` is an in-memory
inverted index built from the records handed to it; ``search_twins`` is a pure
function over that index. The caller owns persistence and embedding re-rank.

**Honesty rules (load-bearing):**

  * **Empty query → empty hits.** Not "everything matches." A blank query is not
    a search; returning all records would silently pretend the user asked for
    everything (no inventing relevance).
  * **Empty index → empty hits.** No records, no results — never a fabricated hit.
  * **Only matching records score > 0.** A record with zero query-term overlap
    gets score 0.0 and is excluded; the engine never returns a "best guess" that
    shares no terms with the query.
  * **Scoring is transparent.** Each ``TwinSearchHit`` carries ``matched_terms``
    and ``term_frequency`` so the operator can see *why* a hit ranked — no black-
    box relevance. Score = sum over matched terms of (term_freq_in_record × idf),
    where idf = log(1 + n_records / (1 + n_records_containing_term)). Simple,
    auditable, hard to vary.
  * **Provenance is carried through.** Every hit retains the record's
    ``provenance`` tuple — the operator can always trace a hit back to the asset
    and the role/event that produced it.
  * **kind_filter is honest.** ``None`` = search all kinds; a specific kind
    (``"insight"`` / ``"question"`` / ``"note"``) restricts to that kind. An
    unknown kind string yields empty (not an error) — the caller may have stale
    data; honest-empty beats a crash.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

_VALID_KINDS = frozenset({"insight", "question", "note"})
_TOKEN_RE = re.compile(r"[a-z0-9]+")


class TwinSearchError(ValueError):
    """A search input violates a load-bearing invariant."""


@dataclass(frozen=True)
class TwinSearchRecord:
    """One searchable twin-substrate item.

    ``kind`` is ``"insight"`` | ``"question"`` | ``"note"``. ``provenance`` is an
    opaque tuple of ids (asset_id, role, event_id, …) the caller chooses; the
    pure index carries it through verbatim so a hit is always traceable.
    """

    asset_id: str
    record_id: str
    kind: str
    text: str
    provenance: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in _VALID_KINDS:
            raise TwinSearchError(
                f"kind {self.kind!r} not in {_VALID_KINDS}; "
                "use one of insight/question/note"
            )
        if not self.record_id.strip():
            raise TwinSearchError("record_id must be non-empty")


@dataclass(frozen=True)
class TwinSearchHit:
    """One ranked search result. ``score`` is transparent and auditable."""

    record: TwinSearchRecord
    score: float
    matched_terms: tuple[str, ...]
    term_frequency: dict[str, int]


@dataclass
class TwinIndex:
    """In-memory inverted index over twin-substrate records.

    Built via ``TwinIndex.build(records)``. Stores term→record frequency (for
    idf), per-record term frequency, and the original records. Pure value: no
    mutation after build; ``search_twins`` reads it without side effects.
    """

    records: tuple[TwinSearchRecord, ...] = ()
    _by_id: dict[str, TwinSearchRecord] = field(default_factory=dict)
    _term_freq: dict[str, dict[str, int]] = field(default_factory=dict)  # term -> {record_id: count}
    _doc_freq: dict[str, int] = field(default_factory=dict)  # term -> # records containing it
    _kind_index: dict[str, set[str]] = field(default_factory=dict)  # kind -> {record_id}

    @classmethod
    def build(cls, records: list[TwinSearchRecord]) -> TwinIndex:
        by_id: dict[str, TwinSearchRecord] = {}
        rec_list: list[TwinSearchRecord] = []
        term_freq: dict[str, dict[str, int]] = {}
        doc_freq: dict[str, int] = {}
        kind_index: dict[str, set[str]] = {}
        for rec in records:
            if rec.record_id in by_id:
                raise TwinSearchError(
                    f"duplicate record_id {rec.record_id!r}; ids must be unique"
                )
            by_id[rec.record_id] = rec
            rec_list.append(rec)
            kind_index.setdefault(rec.kind, set()).add(rec.record_id)
            seen: set[str] = set()
            for token in _TOKEN_RE.findall(rec.text.lower()):
                term_freq.setdefault(token, {}).setdefault(rec.record_id, 0)
                term_freq[token][rec.record_id] += 1
                seen.add(token)
            for term in seen:
                doc_freq[term] = doc_freq.get(term, 0) + 1
        return cls(
            records=tuple(rec_list),
            _by_id=by_id,
            _term_freq=term_freq,
            _doc_freq=doc_freq,
            _kind_index=kind_index,
        )

    @property
    def size(self) -> int:
        return len(self.records)

    def _idf(self, term: str) -> float:
        n = self.size
        df = self._doc_freq.get(term, 0)
        return math.log(1 + n / (1 + df))


def _tokenize(query: str) -> list[str]:
    return _TOKEN_RE.findall(query.lower())


def search_twins(
    index: TwinIndex,
    query: str,
    *,
    limit: int = 10,
    kind_filter: str | None = None,
) -> list[TwinSearchHit]:
    """Rank the twin substrate against a lexical query. Pure.

    Returns hits sorted by score descending, then by record_id (stable tie-break).
    Only records sharing ≥1 query term are returned. ``kind_filter`` restricts to
    one kind (``None`` = all). ``limit`` caps the result count (``<= 0`` → empty).
    """
    if kind_filter is not None and kind_filter not in _VALID_KINDS:
        return []  # honest empty for an unknown/stale kind
    if limit <= 0:
        return []

    terms = _tokenize(query)
    if not terms:
        return []  # empty query → empty hits (never "everything matches")

    candidate_ids: set[str] = set()
    for term in terms:
        candidate_ids |= set(index._term_freq.get(term, {}).keys())

    if kind_filter is not None:
        candidate_ids &= index._kind_index.get(kind_filter, set())

    hits: list[TwinSearchHit] = []
    for rid in candidate_ids:
        rec = index._by_id[rid]
        matched: list[str] = []
        tf_map: dict[str, int] = {}
        score = 0.0
        for term in terms:
            tf = index._term_freq.get(term, {}).get(rid, 0)
            if tf > 0:
                matched.append(term)
                tf_map[term] = tf
                score += tf * index._idf(term)
        if score <= 0.0 or not matched:
            continue
        hits.append(
            TwinSearchHit(
                record=rec,
                score=score,
                matched_terms=tuple(sorted(set(matched))),
                term_frequency=tf_map,
            )
        )

    hits.sort(key=lambda h: (-h.score, h.record.record_id))
    return hits[:limit]


__all__ = [
    "TwinSearchError",
    "TwinSearchRecord",
    "TwinSearchHit",
    "TwinIndex",
    "search_twins",
]
