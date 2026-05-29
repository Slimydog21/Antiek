"""Read claim→chunk provenance from the EXISTING store — never a parallel one.

The claim→chunk links already exist: every load-bearing claim is a
``ThesisComponent`` whose ``supporting_chunk_ids`` cite the chunks it
rests on (``substrate/schemas/events.py``). The chunk TEXT lives in the
substrate ``chunks`` table (``runtime/db_lock.connect_read`` →
``SELECT text FROM chunks``). This module joins the two so the scorer
gets ``(claim, cited_chunk_ids, chunk_texts)`` tuples without inventing a
second provenance store (Rigor card 4: use the existing provenance).

Two resolution paths, both read-only:

- ``resolve_synthesis_claims(payload, chunk_text_for)`` — given a
  ``SynthesizeDeliveredPayload`` and a chunk-text resolver, build the
  scorer's input. The resolver is injected so the OFFLINE harness can
  resolve from a chunk-text map carried IN the trace fixture (no live DB
  needed), while the live path resolves from the DB.
- ``duckdb_chunk_text_resolver(db_path)`` — the live resolver: one
  read-only query over the existing ``chunks`` table.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Optional, Sequence

# (claim, cited_chunk_ids, chunk_texts)
ClaimChunks = tuple[str, list[str], list[str]]

# A chunk-text resolver maps a chunk_id to its text (or None if unknown).
ChunkTextResolver = Callable[[str], Optional[str]]


def _components(payload: Any) -> list[Any]:
    return list(getattr(payload, "thesis_components", None) or [])


def resolve_synthesis_claims(
    payload: Any,
    chunk_text_for: ChunkTextResolver,
) -> list[ClaimChunks]:
    """Project a synthesis payload + a chunk-text resolver into the
    scorer's ``(claim, cited_chunk_ids, chunk_texts)`` input.

    Reads the EXISTING claim→chunk links off each ThesisComponent's
    ``supporting_chunk_ids``. A chunk_id the resolver can't resolve is
    dropped from ``chunk_texts`` (but kept in ``cited_chunk_ids`` so the
    verdict records what was cited) — an unresolvable citation makes the
    claim *less* grounded, which is the honest behaviour."""
    out: list[ClaimChunks] = []
    for comp in _components(payload):
        claim = getattr(comp, "claim", None)
        if not isinstance(claim, str):
            continue
        chunk_ids = [
            str(cid) for cid in (getattr(comp, "supporting_chunk_ids", None) or [])
        ]
        texts: list[str] = []
        for cid in chunk_ids:
            t = chunk_text_for(cid)
            if t:
                texts.append(t)
        out.append((claim, chunk_ids, texts))
    return out


def mapping_chunk_text_resolver(chunk_texts: Mapping[str, str]) -> ChunkTextResolver:
    """Resolver backed by an in-memory map. Used by the OFFLINE harness
    when the trace fixture carries the chunk text inline (so the eval is
    truly offline — no live DB required)."""

    def _resolve(chunk_id: str) -> Optional[str]:
        return chunk_texts.get(chunk_id)

    return _resolve


def duckdb_chunk_text_resolver(
    db_path: str,
    *,
    chunk_ids: Optional[Sequence[str]] = None,
) -> ChunkTextResolver:
    """Live resolver: read chunk text from the EXISTING ``chunks`` table
    through the read-only connection funnel (``runtime/db_lock``). Loads
    the requested chunk_ids once into a dict so per-claim resolution is
    O(1) and the DB connection is short-lived (read-only — safe alongside
    the single writer)."""
    import os

    from runtime.db_lock import connect_read

    resolved: dict[str, str] = {}
    path = os.path.expanduser(db_path)
    con = connect_read(path)
    try:
        if chunk_ids:
            ids = list({str(c) for c in chunk_ids})
            placeholders = ",".join("?" for _ in ids)
            rows = con.execute(
                f"SELECT chunk_id, text FROM chunks WHERE chunk_id IN ({placeholders})",
                ids,
            ).fetchall()
        else:
            rows = con.execute("SELECT chunk_id, text FROM chunks").fetchall()
        for chunk_id, text in rows:
            if text is not None:
                resolved[str(chunk_id)] = str(text)
    finally:
        con.close()

    def _resolve(chunk_id: str) -> Optional[str]:
        return resolved.get(chunk_id)

    return _resolve
