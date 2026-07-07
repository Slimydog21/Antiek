"""Supersession detector + classifier seam (SPR-02 M2 + M4).

Contradictions become TASKS, not actions. ``detect_recent`` / ``detect_for_edge``
scan for structurally-contradicting edges and write CANDIDATE rows into
``supersession_candidates``; they NEVER mutate an edge. Only ``apply_review``
(SPR-02 M3, ``apply.py``) changes an edge, and only on an explicit reviewer
decision.

Contradiction rule (deterministic, structural): two edges that share a
``source_node_id`` and ``relation`` but point at different ``target_node_id``s
and are BOTH currently valid (``valid_until IS NULL``) are a candidate. The
``old``/``new`` labelling defaults to earlier-``valid_from``-is-old (tiebreak
``edge_id``); the reviewer — not this module — decides what actually supersedes.

Every candidate write requires a ``LockedConnection`` (the DuckDB single-writer
invariant); the same locked connection is used for the read scan.
"""

from __future__ import annotations

from datetime import UTC, datetime

from .supersession import (
    DEFAULT_UNCLASSIFIED_VERDICT,
    SupersessionVerdict,
    new_candidate_id,
)

try:
    from runtime.db_lock import LockedConnection
except ImportError:  # pragma: no cover — direct-script fallback
    import os
    import sys

    sys.path.insert(
        0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    from runtime.db_lock import LockedConnection


def classify_contradiction(old_edge_id: str, new_edge_id: str) -> SupersessionVerdict:
    """Classifier seam (SPR-02 M4). The DEFAULT backend is rule-based and
    conservative: it returns ``DEFAULT_UNCLASSIFIED_VERDICT`` (``uncertainty``),
    which forces the candidate into human review rather than asserting a
    supersession. An optional LLM backend — OFF by default — would route through
    ``substrate/dispatch/`` to judge whether the pair is a genuine supersession,
    two coexisting frames, or an extraction error, and set ``contradiction_type``
    accordingly. It is deliberately deferred: the deterministic candidate path is
    proven first, and the LLM adds a dispatch dependency plus a per-call cost
    surface. This mirrors the groundedness scorer's shipped lexical default
    alongside its off-by-default ``llm_judge`` backend — the reliable
    deterministic path ships; the smarter path is a documented seam."""
    return DEFAULT_UNCLASSIFIED_VERDICT


def _require_locked(con: object) -> None:
    if not isinstance(con, LockedConnection):
        raise TypeError(
            f"supersession candidate writes require a LockedConnection "
            f"(got {type(con).__name__}); use runtime.db_lock.connect_write."
        )


_OPEN_DUP_SQL = (
    "SELECT candidate_id FROM supersession_candidates "
    "WHERE status = 'open' AND "
    "((old_edge_id = ? AND new_edge_id = ?) OR "
    " (old_edge_id = ? AND new_edge_id = ?))"
)

_INSERT_SQL = (
    "INSERT INTO supersession_candidates "
    "(candidate_id, investigation_id, old_edge_id, new_edge_id, "
    " contradiction_type, reasoning, status, created_at) "
    "VALUES (?, ?, ?, ?, ?, ?, 'open', ?)"
)


def _order_pair(a_id: str, a_vf: datetime, b_id: str, b_vf: datetime) -> tuple[str, str]:
    """old = earlier valid_from (tiebreak edge_id); new = the other."""
    return (a_id, b_id) if (a_vf, a_id) <= (b_vf, b_id) else (b_id, a_id)


def _write_candidate(
    con: LockedConnection, old_id: str, new_id: str, investigation_id: str
) -> str | None:
    """Write one open candidate for (old, new) unless an open candidate for that
    pair already exists (either orientation). Returns candidate_id or None.
    NEVER touches the edges table."""
    if con.execute(_OPEN_DUP_SQL, [old_id, new_id, new_id, old_id]).fetchone():
        return None
    verdict = classify_contradiction(old_id, new_id)
    cid = new_candidate_id()
    con.execute(
        _INSERT_SQL,
        [
            cid,
            investigation_id,
            old_id,
            new_id,
            verdict.contradiction_type,
            verdict.reasoning,
            datetime.now(UTC),
        ],
    )
    return cid


def detect_recent(con: LockedConnection, since: datetime | None = None) -> list[str]:
    """Batch sweep (the primary, safe wiring): find every pair of currently-valid
    contradicting edges and write an open candidate for each new pair. Returns the
    candidate_ids written. Does NOT mutate edges."""
    _require_locked(con)
    sql = (
        "SELECT e1.edge_id, e1.valid_from, e2.edge_id, e2.valid_from, "
        "       e1.investigation_id, e2.investigation_id "
        "FROM edges e1 JOIN edges e2 "
        "  ON e1.source_node_id = e2.source_node_id "
        " AND e1.relation = e2.relation "
        " AND e1.target_node_id <> e2.target_node_id "
        " AND e1.valid_until IS NULL AND e2.valid_until IS NULL "
        " AND e1.edge_id < e2.edge_id"
    )
    params: list[datetime] = []
    if since is not None:
        sql += " AND (e1.extracted_at >= ? OR e2.extracted_at >= ?)"
        params = [since, since]
    written: list[str] = []
    for e1, vf1, e2, vf2, inv1, inv2 in con.execute(sql, params).fetchall():
        old_id, new_id = _order_pair(e1, vf1, e2, vf2)
        cid = _write_candidate(con, old_id, new_id, inv1 or inv2)
        if cid is not None:
            written.append(cid)
    return written


def detect_for_edge(con: LockedConnection, new_edge_id: str) -> str | None:
    """Detect contradictions involving a single (just-added) edge. Same rule as
    ``detect_recent``, scoped to ``new_edge_id``. Returns the first candidate_id
    written, or None. Does NOT mutate edges."""
    _require_locked(con)
    row = con.execute(
        "SELECT source_node_id, target_node_id, relation, valid_until, "
        "valid_from, investigation_id FROM edges WHERE edge_id = ?",
        [new_edge_id],
    ).fetchone()
    if row is None:
        return None
    src, tgt, rel, valid_until, vf, inv = row
    if valid_until is not None:
        return None  # not currently valid → nothing to surface
    conflicts = con.execute(
        "SELECT edge_id, valid_from, investigation_id FROM edges "
        "WHERE source_node_id = ? AND relation = ? AND target_node_id <> ? "
        "AND valid_until IS NULL AND edge_id <> ?",
        [src, rel, tgt, new_edge_id],
    ).fetchall()
    for other_id, other_vf, other_inv in conflicts:
        old_id, new_id = _order_pair(new_edge_id, vf, other_id, other_vf)
        cid = _write_candidate(con, old_id, new_id, inv or other_inv)
        if cid is not None:
            return cid
    return None
