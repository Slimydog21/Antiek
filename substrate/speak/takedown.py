"""Speak SPR-01 M5 — takedown path.

An interviewee or the subject can demand removal of their statements /
attribution. A takedown is stronger than a consent revocation: it
reaches *already-published* content. On takedown:

  • the target (an interview, a claim, or the subject) is recorded as
    actively taken down;
  • affected content flips OUT of publishable — the publish gate
    refuses it (``publish_gate.is_blocked_by_takedown``);
  • any served publication for the project is purged from served
    output (``served = FALSE``, ``taken_down = TRUE``);
  • the action is audited (``speak.takedown.requested``).

A takedown is reversible only by re-consent (``reverse_takedown``,
audited as ``speak.takedown.reversed``) — not by a silent flag flip.

Why purge rather than serve-then-takedown-on-complaint: a defamation
harm is far more expensive after publication than before (the same
pre/post asymmetry Read cites from Bartz), and a takedown cannot unring
a defamation bell. So takedown is a hard purge, and the primary gate is
verification-*before*-publish (M3), not removal-after-harm.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.books.takedown import take_down as take_down_book

from .events import (
    SPEAK_TAKEDOWN_REQUESTED,
    SPEAK_TAKEDOWN_REVERSED,
    record_speak_event,
)
from .ids import new_takedown_id
from .schema import ensure_speak_schema

_TARGET_KINDS = frozenset({"interview", "claim", "subject"})


@dataclass(frozen=True)
class Takedown:
    takedown_id: str
    project_id: str
    target_kind: str
    target_id: str
    status: str  # 'active' | 'reversed'
    reason: str | None


def request_takedown(
    con: Any,
    *,
    project_id: str,
    target_kind: str,
    target_id: str,
    requested_by: str | None = None,
    reason: str | None = None,
) -> str:
    """Record + enact a takedown. Returns the ``takedown_id``.

    Purges served output: any publication for the project is flipped to
    ``served = FALSE, taken_down = TRUE``. The publish gate consults
    active takedowns, so the affected content cannot be re-published
    until the takedown is reversed by re-consent."""
    ensure_speak_schema(con)
    if target_kind not in _TARGET_KINDS:
        raise ValueError(f"unknown takedown target_kind: {target_kind!r}")
    tid = new_takedown_id()
    con.execute(
        "INSERT INTO speak_takedowns "
        "(takedown_id, project_id, target_kind, target_id, requested_by, "
        " reason, status) VALUES (?, ?, ?, ?, ?, ?, 'active')",
        [tid, project_id, target_kind, target_id, requested_by, reason],
    )
    # Purge served publications for this project (a takedown reaching
    # published content). Specific-target serving is re-evaluated by the
    # publish gate; the conservative purge here ensures nothing affected
    # keeps being served in the meantime.
    con.execute(
        "UPDATE speak_publications SET served = FALSE, taken_down = TRUE "
        "WHERE project_id = ? AND served = TRUE",
        [project_id],
    )
    # Speak publications are materialized as registered HTML Read assets. A
    # Speak-only flag is insufficient: purge every derived body and close the
    # shared Read gate in the same write lock.
    derived_documents = con.execute(
        "SELECT d.document_id FROM documents d "
        "JOIN book_assets b ON b.document_id = d.document_id "
        "WHERE json_extract_string(d.metadata, '$.project_id') = ? "
        "AND json_extract_string(d.metadata, '$.provenance_class') = 'speak_derived' "
        "AND COALESCE(b.taken_down, FALSE) = FALSE",
        [project_id],
    ).fetchall()
    for (document_id,) in derived_documents:
        # The derived chunks contain the same prose and are independently
        # retrievable. Purge them before mutating the referenced document;
        # this also avoids DuckDB's update-on-referenced-row limitation.
        con.execute("DELETE FROM chunks WHERE document_id = ?", [document_id])
        take_down_book(
            con,
            document_id,
            reason=reason or f"Speak {target_kind} takedown",
        )
    record_speak_event(
        SPEAK_TAKEDOWN_REQUESTED,
        {"takedown_id": tid, "target_kind": target_kind,
         "target_id": target_id, "requested_by": requested_by},
        project_id=project_id,
    )
    return tid


def reverse_takedown(con: Any, *, takedown_id: str, project_id: str | None = None) -> None:
    """Reverse a takedown — only legitimate after re-consent. Audited.
    Does NOT auto-re-serve a publication; re-publishing goes back through
    the publish gate."""
    ensure_speak_schema(con)
    row = con.execute(
        "SELECT project_id FROM speak_takedowns WHERE takedown_id = ?",
        [takedown_id],
    ).fetchone()
    if row is None:
        raise ValueError(f"takedown {takedown_id!r} not found")
    con.execute(
        "UPDATE speak_takedowns SET status = 'reversed', "
        "reversed_at = CURRENT_TIMESTAMP WHERE takedown_id = ?",
        [takedown_id],
    )
    record_speak_event(
        SPEAK_TAKEDOWN_REVERSED,
        {"takedown_id": takedown_id},
        project_id=project_id or row[0],
    )


def is_taken_down(con: Any, *, target_kind: str, target_id: str) -> bool:
    """Whether an active takedown covers this target."""
    row = con.execute(
        "SELECT 1 FROM speak_takedowns "
        "WHERE target_kind = ? AND target_id = ? AND status = 'active' LIMIT 1",
        [target_kind, target_id],
    ).fetchone()
    return row is not None


def active_takedowns(con: Any, project_id: str) -> list[Takedown]:
    rows = con.execute(
        "SELECT takedown_id, project_id, target_kind, target_id, status, reason "
        "FROM speak_takedowns WHERE project_id = ? AND status = 'active' "
        "ORDER BY requested_at",
        [project_id],
    ).fetchall()
    return [
        Takedown(takedown_id=r[0], project_id=r[1], target_kind=r[2],
                 target_id=r[3], status=r[4], reason=r[5])
        for r in rows
    ]
