"""Personal-graph partition primitives (master-spec §13.2).

A user's personal graph contains both private-facing and
public-facing partitions INSIDE the personal graph. Moving content
between partitions is the operator-action that promotes a private
note to the collective graph (or demotes back). This module is the
state-machine.

Per master-spec §13.9 quality gate: promotion to public-facing
triggers verification + voice-style scoring + source-tier validation
BEFORE the content becomes eligible for attribution. This module
exposes the partition transition; the gate logic lives in
`compounding/quality_gate/` (Sprint 22+ follow-on).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import UTC, datetime


class PartitionKind(str, enum.Enum):
    """The two partitions inside a user's personal graph (§13.2)."""

    PRIVATE = "private"
    PUBLIC = "public"


class PartitionInvariantViolation(Exception):
    """Raised when a substrate operation would violate the
    physical-separation invariant.

    Per master-spec §13.2: 'A query against a user's private-facing
    notes cannot, by schema design, write into the collective graph.'
    This is enforced at the database layer, not by policy."""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class PartitionAssignment:
    """A content-item-to-partition assignment with provenance."""

    item_id: str
    item_kind: str  # "note" | "document" | "chunk" | "claim" | "notebook"
    user_id: str
    partition: PartitionKind
    assigned_at: str
    assigned_by_action: str  # operator action or system rule that produced this


def assign_to_partition(
    *,
    item_id: str,
    item_kind: str,
    user_id: str,
    partition: PartitionKind,
    assigned_by_action: str = "user_explicit",
) -> PartitionAssignment:
    """Initial assignment of an item to a partition. Defaults to
    PRIVATE per master-spec §4.5 brainstorming workstation privacy
    posture ('Notebook starts content_class user_owned')."""
    return PartitionAssignment(
        item_id=item_id,
        item_kind=item_kind,
        user_id=user_id,
        partition=partition,
        assigned_at=_now_iso(),
        assigned_by_action=assigned_by_action,
    )


def move_to_partition(
    *,
    assignment: PartitionAssignment,
    new_partition: PartitionKind,
    triggered_by_action: str,
) -> PartitionAssignment:
    """Move an item between partitions. Records the transition with
    provenance.

    Per master-spec §13.9 quality gate: moving to PUBLIC triggers
    verification + voice-style + source-tier validation BEFORE
    promotion. The gate runs at the API layer; this function only
    records the transition (the API endpoint enforces the gate)."""
    return PartitionAssignment(
        item_id=assignment.item_id,
        item_kind=assignment.item_kind,
        user_id=assignment.user_id,
        partition=new_partition,
        assigned_at=_now_iso(),
        assigned_by_action=triggered_by_action,
    )


def validate_partition(
    *,
    item_owner_user_id: str,
    accessing_user_id: str,
    partition: PartitionKind,
) -> None:
    """Validate that an access is allowed under the
    physical-separation invariant.

    Rules:
    - PRIVATE items: only the owner can read or write.
    - PUBLIC items: any user can read; only the owner can write or
      change partition.

    Raises PartitionInvariantViolation on disallowed access.
    """
    if partition == PartitionKind.PRIVATE:
        if item_owner_user_id != accessing_user_id:
            raise PartitionInvariantViolation(
                f"user {accessing_user_id!r} cannot access private item "
                f"owned by {item_owner_user_id!r} — physical-separation "
                f"invariant per master-spec §13.2"
            )
    # PUBLIC reads are unrestricted; writes are checked separately by
    # caller (the API layer's authorization check).
