"""Backtest DB query layer (Sprint 10 day 4-5).

Read-only loaders. None of these write — backtest analytics walks
the substrate, never mutates it. The loaders return the projected
dataclasses (``SupersededEdge``, ``ChunkTierChange``) the
``analysis.build_report`` shape expects.

Synthesis-row reading lives in ``middleware.archive.archive``
(``load_synthesis``) — same disciplined separation as upstream:
the archive module owns the syntheses table, this module owns the
diff + outcomes queries.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from .analysis import (
    project_chunk_tier_changes,
    project_superseded_edges,
)
from .types import ArchivedSynthesis, ChunkTierChange, SupersededEdge


def _naive_utc(ts: datetime) -> datetime:
    """Normalize tz-aware → naive UTC for DuckDB comparison.
    DuckDB TIMESTAMP is tz-naive; tz-aware parameters silently
    miss rows. Single normalization point for every loader here."""
    if ts.tzinfo is not None:
        return ts.astimezone(UTC).replace(tzinfo=None)
    return ts


# ---------------------------------------------------------------------------
# Edges since
# ---------------------------------------------------------------------------


def count_added_edges_since(con: Any, since: datetime) -> int:
    """Number of edges extracted after ``since``."""
    (n,) = con.execute(
        "SELECT COUNT(*) FROM edges WHERE extracted_at > ?",
        [_naive_utc(since)],
    ).fetchone()
    return int(n)


def count_superseded_edges_since(con: Any, since: datetime) -> int:
    """Number of edges closed (``valid_until > since``) after the
    synthesis was archived. ``superseded_by`` may be null when the
    closure wasn't a contradiction (e.g. document-level retraction)."""
    (n,) = con.execute(
        "SELECT COUNT(*) FROM edges "
        "WHERE valid_until IS NOT NULL AND valid_until > ?",
        [_naive_utc(since)],
    ).fetchone()
    return int(n)


def load_superseded_cited_edges(
    con: Any, edge_ids: tuple[str, ...], since: datetime,
) -> tuple[SupersededEdge, ...]:
    """For a synthesis's cited edges, return those that have been
    closed since the archive timestamp. The projection enriches each
    row with the source/target node labels + relation, mirroring
    Researchmaxx's backtest column order."""
    if not edge_ids:
        return ()
    rows = con.execute(
        "SELECT e.edge_id, e.superseded_by, e.valid_until, "
        " ns.canonical_label AS source_label, "
        " nt.canonical_label AS target_label, e.relation "
        "FROM edges e "
        "JOIN nodes ns ON ns.node_id = e.source_node_id "
        "JOIN nodes nt ON nt.node_id = e.target_node_id "
        "WHERE e.edge_id = ANY(?) "
        "  AND e.valid_until IS NOT NULL AND e.valid_until > ?",
        [list(edge_ids), _naive_utc(since)],
    ).fetchall()
    return project_superseded_edges(rows)


# ---------------------------------------------------------------------------
# Chunk tier changes
# ---------------------------------------------------------------------------


def load_chunk_tier_changes_since(
    con: Any,
    since: datetime,
    *,
    chunk_ids: tuple[str, ...] | None = None,
) -> tuple[ChunkTierChange, ...]:
    """Tier overrides recorded after ``since``. When ``chunk_ids`` is
    set, restrict to that subset (the synthesis's cited chunks)."""
    if chunk_ids is not None and not chunk_ids:
        return ()
    since_naive = _naive_utc(since)
    if chunk_ids is None:
        rows = con.execute(
            "SELECT chunk_id, original_tier, override_tier, reason, set_at "
            "FROM chunk_tier_overrides WHERE set_at > ? ORDER BY set_at",
            [since_naive],
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT chunk_id, original_tier, override_tier, reason, set_at "
            "FROM chunk_tier_overrides "
            "WHERE set_at > ? AND chunk_id = ANY(?) "
            "ORDER BY set_at",
            [since_naive, list(chunk_ids)],
        ).fetchall()
    return project_chunk_tier_changes(rows)


# ---------------------------------------------------------------------------
# Outcomes
# ---------------------------------------------------------------------------


def load_outcomes_for_synthesis(
    con: Any, synthesis_id: str,
) -> list[dict]:
    """All observer-recorded outcomes for a synthesis, oldest first.
    Returns a list of plain dicts so callers can serialize directly
    into ``BacktestReport.outcomes`` (which expects
    ``tuple[dict, ...]``)."""
    rows = con.execute(
        "SELECT outcome_id, observer, observed_at, "
        " thesis_outcomes, falsification_outcomes, "
        " execution_risk_outcomes, decision_alignment, notes "
        "FROM outcomes WHERE synthesis_id = ? ORDER BY observed_at",
        [synthesis_id],
    ).fetchall()

    def _maybe_json(raw: str | None) -> Any:
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    out: list[dict] = []
    for r in rows:
        out.append({
            "outcome_id": r[0],
            "observer": r[1],
            "observed_at": (
                r[2].isoformat() if hasattr(r[2], "isoformat") else str(r[2])
            ),
            "thesis_outcomes": _maybe_json(r[3]) or [],
            "falsification_outcomes": _maybe_json(r[4]) or [],
            "execution_risk_outcomes": _maybe_json(r[5]) or [],
            "decision_alignment": _maybe_json(r[6]),
            "notes": r[7],
        })
    return out


# ---------------------------------------------------------------------------
# Convenience: extract the backtest-input shape from a loaded row
# ---------------------------------------------------------------------------


def archived_synthesis_from_row(row: Any) -> ArchivedSynthesis:
    """Convert ``ArchivedSynthesisRow`` (from
    ``middleware.archive.load_synthesis``) into ``ArchivedSynthesis``
    (the input shape ``analysis.build_report`` accepts). Drops the
    role outputs — backtest only reads the cohort-level metadata."""
    return ArchivedSynthesis(
        synthesis_id=row.synthesis_id,
        synthesis_timestamp=row.synthesis_timestamp,
        target_question=row.target_question,
        status=row.status,
        implicit_recommendation=row.implicit_recommendation,
        substrate_manifest=dict(row.substrate_manifest),
        substrate_manifest_counts=dict(row.substrate_manifest_counts),
    )
