"""Access-control resolution on top of a CRDT backend.

The core property the scaffold defends:

    For a given edit op, the SAME edit either succeeds on every replica
    or fails on every replica — never half-half.

This is the property Kleppmann names in the interview as the open
problem that Automerge solves. Without it, decentralized access control
diverges and replicas become permanently inconsistent.

Resolution rule (derives from the vector clocks, NOT from wall-clock):

    is_edit_authorized(edit, ops):
        latest_revoke   = most-recent revoke op of edit.editor for doc_id
                          that causally-precedes edit
        latest_grant    = most-recent grant op of edit.editor for doc_id
                          that causally-precedes edit
        # An edit concurrent with a revoke is treated identically across
        # replicas because the rule uses the local op set, which converges
        # under set-union.
        if latest_revoke != None and (
            latest_grant == None or
            causally_precedes(latest_grant.vclock, latest_revoke.vclock)
        ):
            return FAIL — revoke is in effect
        if latest_grant != None:
            return ACCEPT — grant is in effect
        return FAIL — no grant ever issued

Critical: the rule does NOT consult the edit's own clock against
wall-clock-derived timestamps. A backdated edit (Kleppmann's malicious
case) is detectable because its op_id.counter cannot be less than the
actor's counter the OTHER replicas have seen — vector clocks are
monotonic per-actor.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Sequence

from .interfaces import (
    AccessControlOp,
    EditOp,
    GrantOp,
    RevokeOp,
    VectorClock,
    causally_precedes,
)


class EditOutcome(str, enum.Enum):
    ACCEPTED = "accepted"
    """The edit is authorized; merge it into the document state."""

    REJECTED_NO_GRANT = "rejected_no_grant"
    """The editor was never granted permission; reject."""

    REJECTED_REVOKED = "rejected_revoked"
    """A grant existed but was superseded by a revoke; reject."""

    REJECTED_BACKDATED = "rejected_backdated"
    """The edit's vclock is suspiciously stale relative to known ops.
    The malicious-actor case.
    """


def _latest(
    ops: Iterable[AccessControlOp],
    *,
    subject: str,
    doc_id: str,
    kind: type,
    bounded_by: VectorClock | None = None,
) -> AccessControlOp | None:
    """Return the latest op of ``kind`` whose subject == ``subject``
    and doc_id == ``doc_id``, optionally only counting ops that
    causally-precede ``bounded_by``. "Latest" by counter within actor;
    tie-break by actor id (lexical) to be deterministic across replicas.
    """
    candidates: list[AccessControlOp] = []
    for op in ops:
        if not isinstance(op, kind):
            continue
        op_subject = getattr(op, "subject", None) or getattr(op, "editor", None)
        if op_subject != subject:
            continue
        if op.doc_id != doc_id:
            continue
        if bounded_by is not None and causally_precedes(
            bounded_by, op.vclock
        ):
            # Op is causally AFTER the bound; skip. Concurrent ops
            # ARE included — the resolution rule tie-breaks them
            # deterministically (revoke wins).
            continue
        candidates.append(op)
    if not candidates:
        return None
    # Sort deterministically: by counter desc, then by actor lexical.
    candidates.sort(
        key=lambda o: (-o.op_id.counter, o.op_id.actor),
    )
    return candidates[0]


def is_edit_authorized(
    edit: EditOp,
    ops: Sequence[AccessControlOp],
    *,
    max_clock_skew: int = 1000,
) -> EditOutcome:
    """Returns the authorization outcome for ``edit`` against the
    replica's known ``ops``.

    ``max_clock_skew`` defends against backdated-edit attacks. If the
    edit's actor counter is less than the highest counter any replica
    has seen for that actor (i.e., the actor has "gone backwards"),
    that's evidence of forgery. The 1000-default tolerates legitimate
    out-of-order delivery while blocking obvious backdating.
    """
    # Backdated-edit defense.
    max_seen_for_actor = 0
    for op in ops:
        if op.op_id.actor == edit.op_id.actor:
            max_seen_for_actor = max(max_seen_for_actor, op.op_id.counter)
    if edit.op_id.counter + max_clock_skew < max_seen_for_actor:
        return EditOutcome.REJECTED_BACKDATED

    # Find latest revoke + latest grant that causally-precede the edit.
    latest_revoke = _latest(
        ops, subject=edit.editor, doc_id=edit.doc_id, kind=RevokeOp,
        bounded_by=edit.vclock,
    )
    latest_grant = _latest(
        ops, subject=edit.editor, doc_id=edit.doc_id, kind=GrantOp,
        bounded_by=edit.vclock,
    )

    if latest_grant is None:
        return EditOutcome.REJECTED_NO_GRANT

    if latest_revoke is not None:
        # Both exist. Which is "more recent"? Use causal order; if
        # neither precedes the other (concurrent), tie-break: revoke
        # WINS over concurrent grant. This is the conservative choice
        # — Kleppmann's interview specifically calls out that
        # revoke-then-edit and edit-then-revoke must produce the same
        # outcome; tying to revoke-wins ensures both replicas agree.
        if causally_precedes(latest_grant.vclock, latest_revoke.vclock):
            return EditOutcome.REJECTED_REVOKED
        if causally_precedes(latest_revoke.vclock, latest_grant.vclock):
            return EditOutcome.ACCEPTED
        # Concurrent: revoke wins.
        return EditOutcome.REJECTED_REVOKED

    return EditOutcome.ACCEPTED


class Document:
    """An access-controlled document. Thin facade — the real work is
    in the resolution rule above.
    """

    def __init__(self, doc_id: str) -> None:
        self.doc_id = doc_id

    def materialized_payload(
        self, ops: Sequence[AccessControlOp]
    ) -> str:
        """Apply the access-control rule to every edit op, in deterministic
        order, accumulating accepted ones into a concatenated string.
        Returns the materialized payload — equal across replicas.
        """
        # Deterministic op ordering: by counter, then actor lexical.
        sorted_edits = sorted(
            (op for op in ops if isinstance(op, EditOp) and op.doc_id == self.doc_id),
            key=lambda o: (o.op_id.counter, o.op_id.actor),
        )
        accepted: list[str] = []
        for edit in sorted_edits:
            outcome = is_edit_authorized(edit, ops)
            if outcome == EditOutcome.ACCEPTED:
                accepted.append(edit.payload_diff)
        return "".join(accepted)
