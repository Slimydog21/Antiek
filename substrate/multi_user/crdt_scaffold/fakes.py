"""Test-grade in-memory CRDT backend.

Vector-clock-stamped ops; merge is set-union; idempotent apply.

This is NOT a real CRDT — it doesn't compress, doesn't sign ops,
doesn't persist. It's structurally sufficient for the grant/revoke
race tests in tests/test_crdt_grant_revoke_race.py. The Protocol it
satisfies is the same one a real Automerge-backed implementation will.
"""

from __future__ import annotations

import secrets
from typing import Sequence

from .interfaces import (
    AccessControlOp,
    CRDTBackend,
    EditOp,
    GrantOp,
    OpId,
    RevokeOp,
    VectorClock,
)


def fresh_actor_id() -> str:
    """Cryptographically-random actor id. Tests use this so two
    replicas never accidentally collide on actor identity.
    """
    return secrets.token_hex(4)


class OpInMemoryBackend:
    """One replica of a CRDT document. All state is in-process.

    The internal representation is:
        _ops: dict[OpId, AccessControlOp]  — set of known ops (keyed
              for de-dup; insertion order preserved per dict semantics)
        _counter: int                      — per-actor monotonic counter
        _clock: dict[str, int]             — vector clock

    apply(op) is idempotent. merge(other) replays the union of ops.
    The fake doesn't bother compressing — ops accumulate.
    """

    def __init__(self, actor_id: str) -> None:
        self.actor_id = actor_id
        self._ops: dict[OpId, AccessControlOp] = {}
        self._counter: int = 0
        self._clock: dict[str, int] = {}

    # --- CRDTBackend protocol --------------------------------------

    def apply(self, op: AccessControlOp) -> None:
        if op.op_id in self._ops:
            return  # idempotent — already known
        self._ops[op.op_id] = op
        # Advance our clock: per-actor max of (existing, op's clock,
        # op's own counter).
        op_clock = dict(op.clock)
        for k, v in op_clock.items():
            self._clock[k] = max(self._clock.get(k, 0), v)
        # The op's actor's counter must be reflected even if not in
        # the op's clock (defensive).
        self._clock[op.op_id.actor] = max(
            self._clock.get(op.op_id.actor, 0), op.op_id.counter
        )

    def merge(self, other: "OpInMemoryBackend") -> None:
        for op in other._ops.values():
            self.apply(op)

    def ops(self) -> Sequence[AccessControlOp]:
        return tuple(self._ops.values())

    def vclock(self) -> VectorClock:
        return dict(self._clock)

    # --- Op factories ----------------------------------------------

    def _next_op_id(self) -> OpId:
        self._counter += 1
        return OpId(actor=self.actor_id, counter=self._counter)

    def _stamp_clock(self) -> tuple[tuple[str, int], ...]:
        """Snapshot the current vclock, bumped for the upcoming op."""
        snapshot = dict(self._clock)
        snapshot[self.actor_id] = self._counter + 1
        return tuple(sorted(snapshot.items()))

    def make_grant(
        self, granter: str, subject: str, doc_id: str
    ) -> GrantOp:
        op = GrantOp(
            op_id=self._next_op_id(),
            clock=self._stamp_clock(),
            granter=granter,
            subject=subject,
            doc_id=doc_id,
        )
        self.apply(op)
        return op

    def make_revoke(
        self, revoker: str, subject: str, doc_id: str
    ) -> RevokeOp:
        op = RevokeOp(
            op_id=self._next_op_id(),
            clock=self._stamp_clock(),
            revoker=revoker,
            subject=subject,
            doc_id=doc_id,
        )
        self.apply(op)
        return op

    def make_edit(
        self, editor: str, doc_id: str, payload_diff: str
    ) -> EditOp:
        op = EditOp(
            op_id=self._next_op_id(),
            clock=self._stamp_clock(),
            editor=editor,
            doc_id=doc_id,
            payload_diff=payload_diff,
        )
        self.apply(op)
        return op


# Structural Protocol check at import time — fail loudly if the fake
# drifts out of conformance.
assert isinstance(OpInMemoryBackend("test"), CRDTBackend), (
    "OpInMemoryBackend no longer satisfies CRDTBackend Protocol"
)
