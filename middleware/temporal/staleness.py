"""Staleness rule (Researchmaxx spec §D.3).

Pure-function temporal layer: given a graph edge's relation and age,
decide whether it should be flagged for refresh. The TTL per claim
class lives in ``substrate.constants.STALENESS_TTL_DAYS`` so tuning is
one-file and traceable.

Stale flags are **advisory** — they queue the entity for refresh in the
next investigation that touches it, NOT auto-invalidate the claim.
That asymmetry is by design (architecture_notes §4).

Migrated from
``~/.hermes/skills/research/graph-research-substrate/scripts/staleness.py``
(2026-05-16). The pure rule logic and emit helpers land here; the
DB-touching ``scan()`` is deferred until the ``edges`` and
``stale_flags`` tables exist in Antiek.
"""

from __future__ import annotations

import os
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal

try:
    from substrate.constants import RELATION_TO_CLAIM_CLASS, STALENESS_TTL_DAYS
    from substrate.event_log import emit_typed
    from substrate.schemas import (
        StalenessFlaggedPayload,
        StalenessResolution,
        StalenessResolvePayload,
    )
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.constants import RELATION_TO_CLAIM_CLASS, STALENESS_TTL_DAYS
    from substrate.event_log import emit_typed
    from substrate.schemas import (
        StalenessFlaggedPayload,
        StalenessResolution,
        StalenessResolvePayload,
    )


# ---------------------------------------------------------------------------
# Pure rule logic
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StalenessVerdict:
    """Result of evaluating one edge for staleness. ``is_stale`` is the
    binary outcome. ``claim_class`` is None when the relation isn't
    classifiable — in that case the edge is skipped (not flagged).
    """

    is_stale: bool
    claim_class: str | None
    ttl_days: int | None
    age_days: int


@dataclass(frozen=True)
class StalenessFlag:
    """One advisory stale-edge flag emitted by a graph scan."""

    flag_id: str
    edge_id: str
    relation: str
    claim_class: str
    ttl_days: int
    age_days: int
    event_id: str | None


@dataclass(frozen=True)
class StalenessScanResult:
    """Summary from scanning graph edges for advisory staleness."""

    scanned: int
    flagged: tuple[StalenessFlag, ...]
    unclassified: int


def classify_relation(relation: str | None) -> str | None:
    """Map a graph relation string → claim_class key in STALENESS_TTL_DAYS.
    Returns None when no mapping is known (heuristic substring match
    handled here for slight variations like ``raised_series_a``)."""
    if not relation:
        return None
    rel = relation.lower().strip()
    if rel in RELATION_TO_CLAIM_CLASS:
        return RELATION_TO_CLAIM_CLASS[rel]
    # Substring fallback so suffixed variants are caught.
    for key, cls in RELATION_TO_CLAIM_CLASS.items():
        if key in rel:
            return cls
    return None


def evaluate_staleness(relation: str | None, age_days: int) -> StalenessVerdict:
    """Decide whether an edge with the given relation and age is stale.

    Returns a ``StalenessVerdict``. The scanner walks edges, calls this
    once per edge, and emits ``GRAPH_STALENESS_FLAGGED`` for each
    verdict where ``is_stale`` is True.
    """
    if age_days < 0:
        raise ValueError(f"age_days must be non-negative, got {age_days}")

    claim_class = classify_relation(relation)
    if claim_class is None:
        return StalenessVerdict(
            is_stale=False, claim_class=None, ttl_days=None, age_days=age_days,
        )
    ttl = STALENESS_TTL_DAYS[claim_class]
    return StalenessVerdict(
        is_stale=age_days > ttl,
        claim_class=claim_class,
        ttl_days=ttl,
        age_days=age_days,
    )


_DEFAULT_EDGE_VALID_FROM = datetime(1970, 1, 1)


def _as_utc_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    raise TypeError(f"unsupported timestamp value {value!r}")


def _source_timestamp(
    *,
    published_at: Any,
    valid_from: Any,
    extracted_at: Any,
) -> datetime:
    published = _as_utc_datetime(published_at)
    if published is not None:
        return published

    valid = _as_utc_datetime(valid_from)
    if valid is not None and valid.replace(tzinfo=None) != _DEFAULT_EDGE_VALID_FROM:
        return valid

    extracted = _as_utc_datetime(extracted_at)
    if extracted is None:
        raise ValueError("edge row is missing extracted_at")
    return extracted


def _age_days(as_of: datetime, source_time: datetime) -> int:
    as_of = as_of.replace(tzinfo=UTC) if as_of.tzinfo is None else as_of.astimezone(UTC)
    if source_time > as_of:
        return 0
    return (as_of.date() - source_time.date()).days


def _flag_id(edge_id: str, claim_class: str) -> str:
    return f"stale-{edge_id}-{claim_class}"


def scan_graph_edge_staleness(
    con: Any,
    *,
    investigation_id: str,
    as_of: datetime | None = None,
    limit: int | None = None,
    emit_events: bool = True,
) -> StalenessScanResult:
    """Scan graph edges and emit advisory stale-edge events.

    This is intentionally read-only with respect to DuckDB. The durable record is
    the typed event stream; no ``stale_flags`` table is introduced in this slice.
    Source age prefers the document ``published_at`` timestamp, then an explicit
    edge ``valid_from`` if present, then ``extracted_at``. The schema default
    ``1970-01-01`` is treated as "unknown", not as a genuinely 56-year-old
    claim.
    """
    if not investigation_id:
        raise ValueError("investigation_id is required")
    if limit is not None and limit < 0:
        raise ValueError("limit must be non-negative")

    now = as_of or datetime.now(UTC)
    now = now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)

    sql = """
        SELECT e.edge_id, e.relation, e.valid_from, e.extracted_at, d.published_at
        FROM edges e
        LEFT JOIN documents d ON d.document_id = e.source_document_id
        WHERE e.valid_until IS NULL
        ORDER BY e.edge_id ASC
    """
    params: list[Any] = []
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)

    rows = con.execute(sql, params).fetchall()
    flags: list[StalenessFlag] = []
    unclassified = 0
    for edge_id, relation, valid_from, extracted_at, published_at in rows:
        source_time = _source_timestamp(
            published_at=published_at,
            valid_from=valid_from,
            extracted_at=extracted_at,
        )
        verdict = evaluate_staleness(relation, _age_days(now, source_time))
        if verdict.claim_class is None:
            unclassified += 1
            continue
        if not verdict.is_stale:
            continue
        assert verdict.ttl_days is not None
        flag_id = _flag_id(str(edge_id), verdict.claim_class)
        event_id = None
        if emit_events:
            event_id = emit_staleness_flagged(
                investigation_id=investigation_id,
                flag_id=flag_id,
                edge_id=str(edge_id),
                relation=str(relation),
                claim_class=verdict.claim_class,
                ttl_days=verdict.ttl_days,
                age_days=verdict.age_days,
            )
        flags.append(
            StalenessFlag(
                flag_id=flag_id,
                edge_id=str(edge_id),
                relation=str(relation),
                claim_class=verdict.claim_class,
                ttl_days=verdict.ttl_days,
                age_days=verdict.age_days,
                event_id=event_id,
            )
        )

    return StalenessScanResult(
        scanned=len(rows),
        flagged=tuple(flags),
        unclassified=unclassified,
    )


# ---------------------------------------------------------------------------
# Event emit helpers
# ---------------------------------------------------------------------------


def new_flag_id() -> str:
    """Allocate a fresh stable id for a stale flag. Mirrors the original
    Researchmaxx flag_id format (uuid4)."""
    return str(uuid.uuid4())


def emit_staleness_flagged(
    *,
    investigation_id: str,
    flag_id: str,
    edge_id: str,
    relation: str,
    claim_class: str,
    ttl_days: int,
    age_days: int,
    parent_event_id: str | None = None,
) -> str | None:
    """Emit a GRAPH_STALENESS_FLAGGED event. Returns event_id."""
    return emit_typed(
        investigation_id,
        StalenessFlaggedPayload(
            flag_id=flag_id,
            edge_id=edge_id,
            relation=relation,
            claim_class=claim_class,
            ttl_days=ttl_days,
            age_days=age_days,
        ),
        parent_event_id=parent_event_id,
        role="tier_assigner",  # the closest role catalog match; staleness scanner runs as a system role
    )


def emit_staleness_resolve(
    *,
    investigation_id: str,
    flag_id: str,
    entity_kind: Literal["edge", "node"],
    entity_id: str,
    status: StalenessResolution,
    notes: str = "",
    parent_event_id: str | None = None,
    events_dir: str | None = None,
) -> str | None:
    """Emit a STALENESS_RESOLVE event when a flag is resolved.

    ``status`` must be one of {"refreshed", "confirmed_stale", "dismissed"}
    (enforced by the Pydantic Literal on StalenessResolvePayload).
    ``entity_kind`` is currently always 'edge' but the Literal allows
    'node' for future expansion.
    """
    return emit_typed(
        investigation_id,
        StalenessResolvePayload(
            flag_id=flag_id,
            entity_kind=entity_kind,
            entity_id=entity_id,
            status=status,
            notes=notes,
        ),
        parent_event_id=parent_event_id,
        role="tier_assigner",
        events_dir=events_dir,
    )
