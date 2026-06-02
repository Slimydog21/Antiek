"""CRDT scaffold protocols + op types.

The shape is intentionally backend-agnostic. A real implementation
(Automerge, Yjs, or an in-house design) plugs in here.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

# Vector-clock representation: { actor_id -> counter }. Comparisons
# are partial-order; two clocks may be unordered (concurrent).
VectorClock = Mapping[str, int]


@dataclasses.dataclass(frozen=True, slots=True)
class OpId:
    """Globally-unique identifier for a CRDT op.

    Two-tuple: (actor, counter). The actor's monotonic per-actor
    counter ensures uniqueness without a coordinator. Ordering across
    actors is via the vector clock embedded in each op.
    """

    actor: str
    counter: int

    def __str__(self) -> str:
        return f"{self.actor}#{self.counter}"


@dataclasses.dataclass(frozen=True, slots=True)
class GrantOp:
    """Actor with edit permission on the doc grants it to subject."""

    op_id: OpId
    clock: tuple[tuple[str, int], ...]
    """Sorted tuple snapshot of the vector clock at the time of the op.
    Tuple-of-tuples instead of a dict so the op is hashable and frozen.
    """
    granter: str
    subject: str
    doc_id: str

    @property
    def vclock(self) -> VectorClock:
        return dict(self.clock)


@dataclasses.dataclass(frozen=True, slots=True)
class RevokeOp:
    """Actor with admin permission revokes edit permission from subject."""

    op_id: OpId
    clock: tuple[tuple[str, int], ...]
    revoker: str
    subject: str
    doc_id: str

    @property
    def vclock(self) -> VectorClock:
        return dict(self.clock)


@dataclasses.dataclass(frozen=True, slots=True)
class EditOp:
    """Actor edits the doc payload. Authorization is checked at merge
    time, not at write time — the scaffold's central property.
    """

    op_id: OpId
    clock: tuple[tuple[str, int], ...]
    editor: str
    doc_id: str
    payload_diff: str
    """A real implementation uses a structural diff; we model as a
    string for testability. The grant/revoke logic doesn't depend on
    payload shape.
    """

    @property
    def vclock(self) -> VectorClock:
        return dict(self.clock)


AccessControlOp = GrantOp | RevokeOp | EditOp


def causally_precedes(a: VectorClock, b: VectorClock) -> bool:
    """Returns True iff vector clock ``a`` strictly happened-before ``b``.

    Strict: a < b means a[k] <= b[k] for every k, and a[k] < b[k] for at
    least one k. Concurrent ops are neither a < b nor b < a.
    """
    if a == b:
        return False
    strict_less_seen = False
    keys = set(a) | set(b)
    for k in keys:
        av = a.get(k, 0)
        bv = b.get(k, 0)
        if av > bv:
            return False
        if av < bv:
            strict_less_seen = True
    return strict_less_seen


def are_concurrent(a: VectorClock, b: VectorClock) -> bool:
    """Two ops are concurrent if neither happened-before the other."""
    return not causally_precedes(a, b) and not causally_precedes(b, a)


@runtime_checkable
class CRDTBackend(Protocol):
    """The contract every CRDT backend (test fake or real) satisfies.

    A backend owns one logical document and maintains a replica of the
    op set. Multiple backends merge to converge.
    """

    actor_id: str
    """The local actor identifier. Determines who "owns" new ops on
    this replica.
    """

    def apply(self, op: AccessControlOp) -> None:
        """Apply an op locally. Updates the local vector clock and op
        set. Idempotent — applying the same op twice is a no-op.
        """
        ...

    def merge(self, other: CRDTBackend) -> None:
        """Merge another replica's ops into this one. After merge, both
        replicas should converge on the same access-control + edit
        state if the merge is mutual (both directions).
        """
        ...

    def ops(self) -> Sequence[AccessControlOp]:
        """All ops known to this replica, in insertion order. Insertion
        order is NOT semantically meaningful — the vector clocks are.
        """
        ...

    def vclock(self) -> VectorClock:
        """The current vector clock — max per-actor counter seen."""
        ...

    def make_grant(self, granter: str, subject: str, doc_id: str) -> GrantOp:
        """Construct a fresh grant op stamped with this replica's
        current vclock and the next per-actor counter.
        """
        ...

    def make_revoke(self, revoker: str, subject: str, doc_id: str) -> RevokeOp:
        ...

    def make_edit(
        self, editor: str, doc_id: str, payload_diff: str
    ) -> EditOp:
        ...


@dataclasses.dataclass
class ConvergenceTrace:
    """Test helper. Records each replica's final-state snapshot after
    merge so a test can assert all replicas saw the same thing.
    """

    replica_snapshots: dict[str, dict[str, Any]] = dataclasses.field(
        default_factory=dict
    )

    def record(self, replica_label: str, snapshot: dict[str, Any]) -> None:
        self.replica_snapshots[replica_label] = snapshot

    def all_converged(self) -> bool:
        """All replicas have the same snapshot."""
        snapshots = list(self.replica_snapshots.values())
        if len(snapshots) < 2:
            return True
        first = snapshots[0]
        return all(s == first for s in snapshots[1:])

    def divergence_report(self) -> str:
        """Human-readable diff of where replicas disagree."""
        if self.all_converged():
            return "all replicas converged"
        labels = list(self.replica_snapshots)
        lines = ["replicas did NOT converge:"]
        for label, snap in self.replica_snapshots.items():
            lines.append(f"  {label}: {snap!r}")
        return "\n".join(lines)
