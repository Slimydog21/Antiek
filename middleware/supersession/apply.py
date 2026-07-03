"""Supersession review write-path (SPR-02 M3).

``apply_review`` is the ONLY function in the supersession layer that mutates an
edge, and it does so only on an explicit reviewer decision from the closed
four-decision set. Detection (``db.py``) never touches an edge; the reviewer,
through this function, is what changes a belief.

The edge mutation and the candidate update happen in one transaction; the audit
event is emitted only AFTER that commit, so no event ever advertises a write that
did not land. Requires a ``LockedConnection`` (the DuckDB single-writer
invariant). Applying an already-reviewed candidate raises rather than mutating an
edge a second time.
"""

from __future__ import annotations

from datetime import UTC, datetime

from .db import _require_locked
from .supersession import emit_for_decision, validate_decision


def apply_review(
    con,
    candidate_id: str,
    decision: str,
    reviewer: str,
    review_notes: str = "",
) -> str | None:
    """Apply a reviewer's decision to a supersession candidate.

    | decision           | edge effect                                    |
    |--------------------|------------------------------------------------|
    | apply_supersession | old.valid_until=now, old.superseded_by=new     |
    | dismiss_new        | new.valid_until=now (the new edge was wrong)   |
    | dismiss_old        | old.valid_until=now (the old edge was wrong)   |
    | coexist            | no edge change — both remain valid             |

    Marks the candidate ``reviewed`` and emits the matching audit event. Returns
    the emitted event id (or None). Raises ``ValueError`` on an unknown or
    already-reviewed candidate, or an invalid decision; ``TypeError`` without a
    ``LockedConnection``.

    Transaction ownership: ``apply_review`` manages its own ``BEGIN``/``COMMIT``
    (matching ``archive_synthesis_via_db``) — do not call it inside an outer
    transaction on the same connection, or the inner ``COMMIT`` would close the
    caller's transaction early. The audit event is emitted only after the commit
    so it never advertises a write that did not land."""
    _require_locked(con)
    validate_decision(decision)
    row = con.execute(
        "SELECT old_edge_id, new_edge_id, investigation_id, status "
        "FROM supersession_candidates WHERE candidate_id = ?",
        [candidate_id],
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown supersession candidate {candidate_id!r}")
    old_edge_id, new_edge_id, investigation_id, status = row
    if status == "reviewed":
        raise ValueError(
            f"candidate {candidate_id!r} is already reviewed; refusing to "
            "re-apply (would double-mutate an edge)"
        )

    now = datetime.now(UTC)
    con.execute("BEGIN")
    try:
        if decision == "apply_supersession":
            con.execute(
                "UPDATE edges SET valid_until = ?, superseded_by = ? "
                "WHERE edge_id = ?",
                [now, new_edge_id, old_edge_id],
            )
        elif decision == "dismiss_new":
            con.execute(
                "UPDATE edges SET valid_until = ? WHERE edge_id = ?",
                [now, new_edge_id],
            )
        elif decision == "dismiss_old":
            con.execute(
                "UPDATE edges SET valid_until = ? WHERE edge_id = ?",
                [now, old_edge_id],
            )
        # decision == "coexist": no edge change.
        con.execute(
            "UPDATE supersession_candidates SET status = 'reviewed', "
            "decision = ?, reviewer = ?, review_notes = ?, reviewed_at = ? "
            "WHERE candidate_id = ?",
            [decision, reviewer, review_notes, now, candidate_id],
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise

    # Audit event only after the commit — never advertise a write that did not land.
    return emit_for_decision(
        decision=decision,
        investigation_id=investigation_id or "",
        candidate_id=candidate_id,
        old_edge_id=old_edge_id,
        new_edge_id=new_edge_id,
        reviewer=reviewer,
        valid_until=now,
        review_notes=review_notes,
    )
