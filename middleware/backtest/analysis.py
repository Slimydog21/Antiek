"""Backtest pure helpers + ``backtest()`` entry point.

Researchmaxx ``scripts/backtest.py`` is structurally a sequence of
DB queries + small projections. The projections are pure and ship
here. The DB queries (``graph_at_time.diff_between``,
``load_synthesis``, the ``edges`` / ``chunk_tier_overrides`` selects)
landed in Sprint 10 day 4-5 — ``backtest()`` is fully wired and
called in production at ``interfaces/research/api/app.py:5364``.

The shape and contract are settled now so the schema, the cohort
module, and the operator CLI can all be written against the same
``BacktestReport`` dataclass without waiting for the DB layer.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC
from typing import Any

from .types import (
    ArchivedSynthesis,
    BacktestReport,
    ChunkTierChange,
    SupersededEdge,
)


def project_superseded_edges(rows: Iterable[tuple]) -> tuple[SupersededEdge, ...]:
    """Project a DB row iterable into ``SupersededEdge`` records.

    Expected column order (mirrors the upstream query):
    ``(edge_id, superseded_by, valid_until, source, target, relation)``.
    """
    return tuple(
        SupersededEdge(
            edge_id=str(r[0]),
            superseded_by=str(r[1]) if r[1] is not None else None,
            valid_until=str(r[2]),
            source=str(r[3]),
            target=str(r[4]),
            relation=str(r[5]),
        )
        for r in rows
    )


def project_chunk_tier_changes(rows: Iterable[tuple]) -> tuple[ChunkTierChange, ...]:
    """Project a DB row iterable into ``ChunkTierChange`` records.

    Expected column order:
    ``(chunk_id, original_tier, override_tier, reason, set_at)``.
    """
    return tuple(
        ChunkTierChange(
            chunk_id=str(r[0]),
            original_tier=int(r[1]),
            override_tier=int(r[2]),
            reason=str(r[3]),
            set_at=str(r[4]),
        )
        for r in rows
    )


def build_report(
    *,
    archive: ArchivedSynthesis,
    added_edges_since: int,
    superseded_edges_since: int,
    cited_edges_now_superseded: tuple[SupersededEdge, ...],
    chunks_retired_downward: tuple[ChunkTierChange, ...],
    outcomes: list[dict[str, Any]],
) -> BacktestReport:
    """Assemble the report once the DB-loader has produced its parts.

    Pure projection — the loader (``backtest()``) hands pieces
    to a single constructor rather than wiring 8 keyword arguments at
    every call site."""
    return BacktestReport(
        synthesis_id=archive.synthesis_id,
        synthesis_timestamp=archive.synthesis_timestamp,
        target_question=archive.target_question,
        status=archive.status,
        implicit_recommendation=archive.implicit_recommendation,
        substrate_manifest_counts=dict(archive.substrate_manifest_counts),
        added_edges_since=int(added_edges_since),
        superseded_edges_since=int(superseded_edges_since),
        cited_edges_now_superseded=cited_edges_now_superseded,
        chunks_retired_downward=chunks_retired_downward,
        outcomes=tuple(outcomes),
    )


def backtest(con: Any, synthesis_id: str) -> BacktestReport:
    """Full backtest entry point (Sprint 10 day 4-5 — wired).

    Reads the archived synthesis, counts added/closed edges since
    its timestamp, loads the cited-edges-that-have-since-been-
    superseded subset, loads tier-override changes for the cited
    chunks, loads all outcomes recorded against the synthesis, and
    composes a ``BacktestReport`` via ``build_report``.

    ``con`` may be any duckdb-compatible connection (read-only is
    fine — this path never writes)."""
    from datetime import datetime

    from middleware.archive.archive import load_synthesis

    from .db import (
        archived_synthesis_from_row,
        count_added_edges_since,
        count_superseded_edges_since,
        load_chunk_tier_changes_since,
        load_outcomes_for_synthesis,
        load_superseded_cited_edges,
    )

    row = load_synthesis(con, synthesis_id)
    if row is None:
        raise KeyError(f"synthesis_id not found: {synthesis_id!r}")

    archive = archived_synthesis_from_row(row)
    # Normalize to naive UTC — matches the convention used at the
    # write boundary in archive/outcomes/source_tier. DuckDB TIMESTAMP
    # is tz-naive; comparing a tz-aware Python datetime against a
    # naive column silently returns no rows.
    since = datetime.fromisoformat(archive.synthesis_timestamp)
    if since.tzinfo is not None:
        since = since.astimezone(UTC).replace(tzinfo=None)

    cited_chunks = tuple(row.substrate_manifest.get("chunk", ()) or ())
    cited_edges = tuple(row.substrate_manifest.get("edge", ()) or ())

    return build_report(
        archive=archive,
        added_edges_since=count_added_edges_since(con, since),
        superseded_edges_since=count_superseded_edges_since(con, since),
        cited_edges_now_superseded=load_superseded_cited_edges(
            con, cited_edges, since,
        ),
        chunks_retired_downward=load_chunk_tier_changes_since(
            con, since, chunk_ids=cited_chunks,
        ),
        outcomes=load_outcomes_for_synthesis(con, synthesis_id),
    )
