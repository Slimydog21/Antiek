"""Validate stale-refresh promotion candidates before graph deposit.

GF-4o records a promotion *candidate* event from the reading UI. This module
is the backend preflight for the eventual single-writer deposit: it proves the
candidate cites real chunks and identifies the primary chunk/document pair a
future ``promote_insight`` call would need. It deliberately performs no graph
write and emits no event.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

ValidationReason = Literal[
    "ready",
    "missing_supporting_chunks",
    "unresolved_supporting_chunks",
]


@dataclass(frozen=True)
class ResolvedPromotionChunk:
    chunk_id: str
    source_document_id: str


@dataclass(frozen=True)
class PromotionCandidateValidation:
    depositable: bool
    reason: ValidationReason
    primary_chunk_id: str | None
    primary_source_document_id: str | None
    resolved_chunks: tuple[ResolvedPromotionChunk, ...]
    unresolved_chunk_ids: tuple[str, ...]


def validate_promotion_candidate(
    con: Any,
    *,
    supporting_chunk_ids: Sequence[str],
) -> PromotionCandidateValidation:
    """Resolve a candidate's supporting chunks against the graph DB.

    A refreshed knowledge unit cannot be honestly deposited without a
    claim->chunk->document grounding link. The UI candidate may carry stale,
    malformed, or absent chunk ids, so this preflight is intentionally strict:
    every non-empty cited chunk id must resolve to a ``chunks`` row with a
    document id before the candidate is ``ready``.
    """
    chunk_ids = _dedupe_nonempty(supporting_chunk_ids)
    if not chunk_ids:
        return PromotionCandidateValidation(
            depositable=False,
            reason="missing_supporting_chunks",
            primary_chunk_id=None,
            primary_source_document_id=None,
            resolved_chunks=(),
            unresolved_chunk_ids=(),
        )

    placeholders = ", ".join(["?"] * len(chunk_ids))
    rows = con.execute(
        "SELECT chunk_id, document_id FROM chunks "
        f"WHERE chunk_id IN ({placeholders})",
        list(chunk_ids),
    ).fetchall()
    resolved_by_id = {
        str(chunk_id): str(document_id)
        for chunk_id, document_id in rows
        if chunk_id and document_id
    }
    unresolved = tuple(
        chunk_id for chunk_id in chunk_ids if chunk_id not in resolved_by_id
    )
    resolved = tuple(
        ResolvedPromotionChunk(
            chunk_id=chunk_id,
            source_document_id=resolved_by_id[chunk_id],
        )
        for chunk_id in chunk_ids
        if chunk_id in resolved_by_id
    )
    if unresolved:
        return PromotionCandidateValidation(
            depositable=False,
            reason="unresolved_supporting_chunks",
            primary_chunk_id=None,
            primary_source_document_id=None,
            resolved_chunks=resolved,
            unresolved_chunk_ids=unresolved,
        )

    primary = resolved[0]
    return PromotionCandidateValidation(
        depositable=True,
        reason="ready",
        primary_chunk_id=primary.chunk_id,
        primary_source_document_id=primary.source_document_id,
        resolved_chunks=resolved,
        unresolved_chunk_ids=(),
    )


def _dedupe_nonempty(values: Sequence[str]) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        chunk_id = value.strip()
        if not chunk_id or chunk_id in seen:
            continue
        seen.add(chunk_id)
        out.append(chunk_id)
    return tuple(out)
