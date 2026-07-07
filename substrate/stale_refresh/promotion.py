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

from substrate.event_log import emit_typed
from substrate.graph.insight_question import promote_insight
from substrate.schemas import (
    StaleReuseRefreshPromotionCandidatePayload,
    StaleReuseRefreshPromotionResultPayload,
)

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


@dataclass(frozen=True)
class PromotionAttempt:
    validation: PromotionCandidateValidation
    result_event_id: str
    deposited_node_id: str | None
    resolved_stale_edge_ids: tuple[str, ...]


def promote_refresh_candidate(
    con: Any,
    *,
    investigation_id: str,
    candidate: StaleReuseRefreshPromotionCandidatePayload,
    candidate_event_id: str | None = None,
    events_dir: str | None = None,
) -> PromotionAttempt:
    """Validate and, when grounded, deposit a refreshed stale-reuse candidate.

    The graph write goes through ``promote_insight`` only after validation
    proves every cited supporting chunk resolves. Every attempt emits a typed
    result event so non-depositability is visible in the parent trajectory.
    """
    validation = validate_promotion_candidate(
        con,
        supporting_chunk_ids=candidate.supporting_chunk_ids,
    )
    deposited_node_id: str | None = None
    if validation.depositable:
        deposited_node_id = promote_insight(
            text=candidate.summary,
            investigation_id=investigation_id,
            confidence="unknown",
            source_document_id=validation.primary_source_document_id,
            chunk_id=validation.primary_chunk_id,
            metadata={
                "stale_refresh": {
                    "source_unit_id": candidate.unit_id,
                    "source_investigation_id": candidate.source_investigation_id,
                    "refresh_investigation_id": candidate.refresh_investigation_id,
                    "candidate_event_id": candidate_event_id,
                }
            },
            con=con,
            dedup=True,
        )

    resolved_stale_edge_ids: list[str] = []
    if deposited_node_id:
        resolved_stale_edge_ids = _resolve_stale_edges(
            con,
            investigation_id=investigation_id,
            edge_ids=candidate.stale_advisory_edge_ids,
            parent_event_id=candidate_event_id,
            events_dir=events_dir,
        )

    result_event_id = emit_typed(
        investigation_id,
        StaleReuseRefreshPromotionResultPayload(
            unit_id=candidate.unit_id,
            source_investigation_id=candidate.source_investigation_id,
            refresh_investigation_id=candidate.refresh_investigation_id,
            status="deposited" if deposited_node_id else "not_depositable",
            reason=validation.reason,
            summary=candidate.summary,
            deposited_node_id=deposited_node_id,
            primary_chunk_id=validation.primary_chunk_id,
            primary_source_document_id=validation.primary_source_document_id,
            supporting_chunk_ids=list(candidate.supporting_chunk_ids),
            unresolved_chunk_ids=list(validation.unresolved_chunk_ids),
            resolved_stale_edge_ids=resolved_stale_edge_ids,
            candidate_event_id=candidate_event_id,
        ),
        parent_event_id=candidate_event_id,
        role="connector",
        events_dir=events_dir,
    )
    return PromotionAttempt(
        validation=validation,
        result_event_id=result_event_id,
        deposited_node_id=deposited_node_id,
        resolved_stale_edge_ids=tuple(resolved_stale_edge_ids),
    )


def _resolve_stale_edges(
    con: Any,
    *,
    investigation_id: str,
    edge_ids: Sequence[str],
    parent_event_id: str | None,
    events_dir: str | None,
) -> list[str]:
    """Emit staleness-resolution events for classified stale advisory edges."""
    deduped = _dedupe_nonempty(edge_ids)
    if not deduped:
        return []

    try:
        from middleware.temporal import classify_relation, emit_staleness_resolve
    except ImportError:  # pragma: no cover — direct-script fallback
        from temporal import (  # type: ignore[import-not-found,no-redef]
            classify_relation,
            emit_staleness_resolve,
        )

    resolved: list[str] = []
    for edge_id in deduped:
        row = con.execute(
            "SELECT relation FROM edges WHERE edge_id = ? AND valid_until IS NULL",
            [edge_id],
        ).fetchone()
        if row is None:
            continue
        claim_class = classify_relation(str(row[0]))
        if claim_class is None:
            continue
        emit_staleness_resolve(
            investigation_id=investigation_id,
            flag_id=f"stale-{edge_id}-{claim_class}",
            entity_kind="edge",
            entity_id=edge_id,
            status="refreshed",
            notes="resolved by stale refresh promotion",
            parent_event_id=parent_event_id,
            events_dir=events_dir,
        )
        resolved.append(edge_id)
    return resolved


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
