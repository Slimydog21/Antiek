"""Reference adapter: twin notes corpus.

Read-only adapter over the twin-note store shape.  The injectable reader
mirrors the real store's fields (``note_id``, ``asset_id``, ``kind``,
``text``, ``source_spawn_id``, ``investigation_id``) — grep
``substrate.engagement_spine.twin`` for the source of truth.

Search is honest substring matching over note text; no embedding dependency.
The adapter accepts a ``TwinNoteReader`` (a read-only protocol), never an
``EngagementStore`` (which has ``put_twin``).  Zero writes are
interface-proven: there is no write method on the reader, and the adapter
exposes none.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

from ..protocol import CorpusAdapter, CorpusDocument, CorpusHit, CorpusMiss, FetchResult, Provenance


@runtime_checkable
class TwinNoteReader(Protocol):
    """Read-only view of the twin-note store.

    Mirrors ``EngagementStore.list_twins`` but exposes NO write surface.
    The adapter accepts this, not ``EngagementStore``, so zero writes are
    structural — not conventional.
    """

    def list_twins(self, asset_id: str) -> list[dict[str, Any]]:
        """Return twin-note dicts for *asset_id*.

        Each dict has at least ``note_id``, ``asset_id``, ``kind``, ``text``.
        Optional: ``source_spawn_id``, ``investigation_id``.
        """
        ...


def _snippet(text: str, query: str, *, radius: int = 80) -> str:
    """Extract a snippet around the first occurrence of *query* in *text*.

    Returns a window of *radius* characters on each side of the match,
    with ellipsis markers when truncated.
    """
    idx = text.lower().find(query.lower())
    if idx < 0:
        # Fallback: head of text
        trimmed = text[: radius * 2]
        return trimmed + ("…" if len(text) > radius * 2 else "")
    start = max(0, idx - radius)
    end = min(len(text), idx + len(query) + radius)
    snippet = text[start:end]
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return prefix + snippet + suffix


def _score(text: str, query: str) -> float:
    """Score relevance of *text* to *query* via substring matching.

    Returns 1.0 for an exact (case-insensitive) match of the full query,
    scaled down by how much of the text the query covers.  Returns 0.0
    when there is no match.
    """
    q = query.lower()
    t = text.lower()
    if q not in t:
        return 0.0
    # Coverage ratio — longer matches relative to text length score higher.
    return round(len(q) / max(len(t), 1), 6)


class TwinNotesCorpusAdapter:
    """CorpusAdapter over twin notes for a single asset.

    ``reader`` is injectable and read-only (``TwinNoteReader`` protocol).
    ``asset_id`` scopes the corpus to one asset's twin substrate.
    """

    def __init__(self, reader: TwinNoteReader, asset_id: str) -> None:
        self._reader = reader
        self._asset_id = asset_id.strip()
        if not self._asset_id:
            raise ValueError("asset_id is required")

    def search(self, query: str) -> Sequence[CorpusHit]:
        """Lexical substring search over twin-note text.

        Returns hits ordered by descending score.  Empty query → no hits.
        """
        q = (query or "").strip()
        if not q:
            return ()
        notes = self._reader.list_twins(self._asset_id)
        hits: list[CorpusHit] = []
        for note in notes:
            text = str(note.get("text") or "")
            s = _score(text, q)
            if s > 0:
                hits.append(
                    CorpusHit(
                        id=str(note["note_id"]),
                        score=s,
                        snippet=_snippet(text, q),
                    )
                )
        hits.sort(key=lambda h: h.score, reverse=True)
        return tuple(hits)

    def fetch(self, id: str) -> FetchResult:
        """Fetch a twin note by id, or return a typed miss.

        Scans the asset's notes (the store has no global index by note_id).
        """
        notes = self._reader.list_twins(self._asset_id)
        for note in notes:
            if note.get("note_id") == id:
                text = str(note.get("text") or "")
                kind = str(note.get("kind") or "unknown")
                return CorpusDocument(
                    content=text,
                    provenance=Provenance(
                        source_kind=f"twin_note:{kind}",
                        origin_ref=str(note.get("asset_id") or self._asset_id),
                        retrieved_at=_dt_now(),
                    ),
                )
        return CorpusMiss(id=id)


def _dt_now() -> "datetime.datetime":
    """UTC now — isolated for testability."""
    import datetime

    return datetime.datetime.now(datetime.timezone.utc)
