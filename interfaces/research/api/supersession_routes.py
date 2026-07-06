"""Supersession review surface — the REST API that turns detected
contradictions into TASKS, not silent data drift (GF-5/GF-6 activation).

A standalone ``APIRouter`` mirroring ``write_routes.py``: kept in its own module
(not inlined into the hot ``app.py`` factory) per CLAUDE.md, included with ONE
line — ``app.include_router(supersession_router)`` — and fully testable alone.

Two endpoints over the ``supersession_candidates`` review queue:

  • ``GET /supersession/candidates`` — list candidates (open by default) with
    the two contradicting edges resolved to human-readable node labels, so a
    reviewer can see ``"X —causes→ A"`` vs ``"X —causes→ B"`` without a second
    round-trip.
  • ``POST /supersession/{candidate_id}/review`` — apply one of the closed
    four-decision set via ``apply_review`` (the ONLY edge-mutating path), which
    manages its own transaction and emits the audit event only after commit.

Detection (writing the candidate rows) is wired best-effort in
``processing/extraction/extract.py`` after each successful extraction: it runs
in its OWN connection after the extraction transaction commits, so a detection
failure can never break extraction (invariant #1). This module is the other
half — without a review path, detection is the "reachable but unfinished" smell
this codebase rejects.

Auth is the app's global middleware (single-operator workstation) — these
handlers carry none, matching ``write_routes.py``. Mutating an edge's belief is
operator-only by construction.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import duckdb
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from middleware.supersession.apply import apply_review
from runtime.db_lock import connect_write
from substrate.graph import default_db_path

supersession_router = APIRouter()


@contextmanager
def _read() -> Iterator[duckdb.DuckDBPyConnection]:
    # Open read-only DIRECTLY off default_db_path() — do NOT route through
    # ensure_initialized: that calls init_database_at_path -> connect_write,
    # acquiring the EXCLUSIVE single-writer flock, which would serialize this
    # read behind every graph writer (notably the continuous-research cycle)
    # and block until the lock frees. A read-only DuckDB connection coexists
    # with the active writer (verified in prod: returns concurrently). The
    # schema is initialized at deploy/startup; on a never-initialized DB the
    # query 500s, which is the correct failure for a review endpoint hitting a
    # graph that doesn't yet exist.
    con = duckdb.connect(default_db_path(), read_only=True)
    try:
        yield con
    finally:
        con.close()


# Resolve both edges of a candidate to node labels in one query so the review
# UI shows the actual contradiction (source —relation→ target) for old + new
# without a follow-up lookup. LEFT JOINs: a candidate's edge_id is a soft ref
# and should always resolve (the detector only stores ids it just read), but a
# LEFT JOIN keeps the candidate visible even if an edge was since archived.
_CANDIDATES_SQL = """
SELECT
    c.candidate_id, c.investigation_id, c.contradiction_type, c.reasoning,
    c.status, c.decision, c.reviewer, c.review_notes, c.created_at,
    c.reviewed_at, c.old_edge_id, c.new_edge_id,
    o.relation AS old_relation, o.source_node_id AS old_source_node_id,
    ns.canonical_label AS old_source_label, o.target_node_id AS old_target_node_id,
    nt.canonical_label AS old_target_label,
    n.relation AS new_relation, n.source_node_id AS new_source_node_id,
    ms.canonical_label AS new_source_label, n.target_node_id AS new_target_node_id,
    mt.canonical_label AS new_target_label
FROM supersession_candidates c
LEFT JOIN edges o ON o.edge_id = c.old_edge_id
LEFT JOIN edges n ON n.edge_id = c.new_edge_id
LEFT JOIN nodes ns ON ns.node_id = o.source_node_id
LEFT JOIN nodes nt ON nt.node_id = o.target_node_id
LEFT JOIN nodes ms ON ms.node_id = n.source_node_id
LEFT JOIN nodes mt ON mt.node_id = n.target_node_id
{where}
ORDER BY c.created_at DESC
LIMIT ?
"""


def _edge_view(
    relation: str | None,
    source_id: str | None,
    source_label: str | None,
    target_id: str | None,
    target_label: str | None,
) -> dict[str, Any]:
    return {
        "relation": relation,
        "source_node_id": source_id,
        "source_label": source_label,
        "target_node_id": target_id,
        "target_label": target_label,
    }


@supersession_router.get("/supersession/candidates")
def list_candidates(
    status: str = Query(default="open"),
    investigation_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    """List supersession review candidates with both edges resolved to labels.

    ``status`` defaults to ``open`` (the review queue); pass ``reviewed`` (or
    ``all``) to inspect history. ``investigation_id`` optionally scopes. Returns
    newest-first so the freshest contradictions surface first."""
    if status not in ("open", "reviewed", "all"):
        raise HTTPException(
            status_code=400,
            detail="status must be one of: open, reviewed, all",
        )
    params: list[Any] = []
    clauses: list[str] = []
    if status != "all":
        clauses.append("c.status = ?")
        params.append(status)
    if investigation_id is not None:
        clauses.append("c.investigation_id = ?")
        params.append(investigation_id)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = _CANDIDATES_SQL.format(where=where)
    params.append(limit)
    with _read() as con:
        rows = con.execute(sql, params).fetchall()
    candidates = [
        {
            "candidate_id": r[0],
            "investigation_id": r[1],
            "contradiction_type": r[2],
            "reasoning": r[3],
            "status": r[4],
            "decision": r[5],
            "reviewer": r[6],
            "review_notes": r[7],
            "created_at": r[8].isoformat() if r[8] else None,
            "reviewed_at": r[9].isoformat() if r[9] else None,
            "old_edge_id": r[10],
            "new_edge_id": r[11],
            "old_edge": _edge_view(r[12], r[13], r[14], r[15], r[16]),
            "new_edge": _edge_view(r[17], r[18], r[19], r[20], r[21]),
        }
        for r in rows
    ]
    return {"candidates": candidates, "count": len(candidates)}


class ReviewCandidateRequest(BaseModel):
    # The closed four-decision set (middleware/supersession/supersession.py
    # REVIEW_DECISIONS). apply_review validates membership and raises
    # ValueError -> 400 for anything else, so this is a single source of truth.
    decision: str = Field(..., min_length=1, max_length=32)
    reviewer: str = Field(default="operator", min_length=1, max_length=64)
    review_notes: str = Field(default="", max_length=2000)


@supersession_router.post("/supersession/{candidate_id}/review", status_code=200)
def review_candidate(
    candidate_id: str, req: ReviewCandidateRequest
) -> dict[str, Any]:
    """Apply a reviewer decision to a supersession candidate.

    Delegates to ``apply_review`` — the ONLY edge-mutating path — which manages
    its own transaction (do not call inside an outer one) and emits the audit
    event only after commit. ``apply_supersession``/``dismiss_*`` close an edge
    (``valid_until = now``); ``coexist`` leaves both valid. Re-reviewing an
    already-reviewed candidate is refused (409) to prevent a double mutation."""
    con = connect_write(default_db_path(), purpose="supersession.review")
    try:
        event_id = apply_review(
            con, candidate_id, req.decision, req.reviewer, req.review_notes
        )
    except ValueError as exc:
        message = str(exc)
        lowered = message.lower()
        if "unknown" in lowered:
            code = 404
        elif "already reviewed" in lowered:
            code = 409
        else:  # invalid decision (validate_decision)
            code = 400
        raise HTTPException(status_code=code, detail=message) from exc
    finally:
        con.close()
    return {
        "candidate_id": candidate_id,
        "status": "reviewed",
        "decision": req.decision,
        "reviewer": req.reviewer,
        "event_id": event_id,
    }
