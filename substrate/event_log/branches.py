"""The parent-side branch record (specs/antiek-mothership/THREAD-CONTRACT.md §1.3).

Every launch of a child investigation writes ``investigation.branched`` into
the PARENT's trajectory before the child's first event, and the write is
strict: if it cannot be made durable the child is not started. The child's own
``investigation.spawned_from`` stays, pointing back at this event through its
``parent_event_id``.

Why the parent: a child that records its parent only in its own log (the
cascade leaf and chase paths before this) disappears from every reader the
moment that log is lost or corrupted, and the export gate then clears a thesis
built on evidence nobody can read. Recorded here, the edge survives the
child's log, so a lost child stays an unresolved dependency.
"""

from __future__ import annotations

from typing import Literal

from substrate.schemas.events import (
    BranchOrigin,
    InvestigationBranchAbandonedPayload,
    InvestigationBranchedPayload,
    InvestigationReservedPayload,
)

from .events import emit_typed

BranchVia = Literal[
    "chase", "cascade_leaf", "sub_question", "watch_for_later",
    "passage_spin", "reserved_launch", "api",
]


class BranchNotRecorded(RuntimeError):
    """The parent's branch record could not be written; do not start the child."""


def record_branch(
    parent_investigation_id: str,
    child_investigation_id: str,
    *,
    via: BranchVia,
    origin: BranchOrigin | None = None,
    spawn_context: str = "",
    question_id: str | None = None,
    role: str | None = None,
    policy_id: str | None = None,
    events_dir: str | None = None,
) -> str | None:
    """Write ``investigation.branched`` into the parent's log, durably.

    Returns the branch event's id, which the child's ``spawned_from`` carries
    as ``parent_event_id``; ``None`` only when the event log is disabled, in
    which case nothing about the child is logged either. Raises
    ``BranchNotRecorded`` when the write fails (an unwritable log, a parent
    id that is not an event-storage name), so the caller refuses the launch.
    """
    if parent_investigation_id == child_investigation_id:
        raise BranchNotRecorded("an investigation cannot branch to itself")
    payload = InvestigationBranchedPayload(
        child_investigation_id=child_investigation_id,
        via=via,
        origin=origin,
        spawn_context=spawn_context,
        question_id=question_id,
    )
    try:
        return emit_typed(
            parent_investigation_id,
            payload,
            role=role,
            policy_id=policy_id,
            events_dir=events_dir,
            strict_write=True,
        )
    except (OSError, ValueError, RuntimeError) as err:
        raise BranchNotRecorded(
            f"branch {parent_investigation_id} -> {child_investigation_id} not recorded"
        ) from err



def abandon_branch(
    parent_investigation_id: str,
    child_investigation_id: str,
    *,
    branch_event_id: str | None,
    role: str | None = None,
    events_dir: str | None = None,
) -> bool:
    """Record that the launch behind ``branch_event_id`` was refused before the
    child's first event. Only the request that wrote the branch may call this,
    and only after a refusal that precedes any start event (the proof the
    child never started). Best effort: if it cannot be written the branch stays
    a live dependency, which is the fail-closed direction."""
    if branch_event_id is None:
        return False
    try:
        emit_typed(
            parent_investigation_id,
            InvestigationBranchAbandonedPayload(
                child_investigation_id=child_investigation_id,
                branch_event_id=branch_event_id,
                reason="capacity_refused",
            ),
            role=role,
            events_dir=events_dir,
            strict_write=True,
        )
    except (OSError, ValueError, RuntimeError):
        return False
    return True


def record_reservation(
    reserved_investigation_id: str,
    parent_investigation_id: str,
    *,
    question_id: str | None = None,
    role: str | None = None,
    events_dir: str | None = None,
) -> str | None:
    """Write ``investigation.reserved`` into the reserved id's OWN log,
    strictly. A later launch into the id reads its parent from here, and a
    reservation that never runs still leaves a readable log."""
    try:
        return emit_typed(
            reserved_investigation_id,
            InvestigationReservedPayload(
                parent_investigation_id=parent_investigation_id, question_id=question_id,
            ),
            role=role,
            events_dir=events_dir,
            strict_write=True,
        )
    except (OSError, ValueError, RuntimeError) as err:
        raise BranchNotRecorded(
            f"reservation {reserved_investigation_id} of {parent_investigation_id} not recorded"
        ) from err


def reserving_parent(investigation_id: str, *, events_dir: str | None = None) -> str | None:
    """The parent that reserved ``investigation_id``, if it is reserved and has
    not started; None otherwise."""
    from .events import trajectory_read

    rows = trajectory_read(investigation_id, events_dir=events_dir).rows
    started = any(r.get("action_type") == "investigation.start_requested" for r in rows)
    if started:
        return None
    for row in rows:
        if row.get("action_type") == "investigation.reserved":
            payload = row.get("payload")
            parent = payload.get("parent_investigation_id") if isinstance(payload, dict) else None
            if isinstance(parent, str):
                return parent
    return None

