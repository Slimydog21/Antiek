"""CRDT scaffold for the eventual Sprint-22 grant/revoke race resolution.

DDIA-execution SPR-09. Anchors philosophy P1 (substrate single-writer,
local-first) and P10 (decentralized access control as a research wedge
for S22 — Automerge-style CRDT preferred over consensus).

Important: SCAFFOLD ONLY. No production toggle. The fakes here are
test-grade; the real CRDT backend (likely Automerge via Rust binding,
or Yjs via py-y-crdt) lands in a separate operator-authorized sprint
after the §13.4 multi-user compounding gate closes.

The exposed surface:

    CRDTBackend       — Protocol every backend must satisfy
    AccessControlOp   — discriminated union: Grant / Revoke / Edit
    Document          — the access-controlled document object
    OpInMemoryBackend — the test-grade vector-clock fake
    ConvergenceTrace  — the test helper that proves all replicas agree

What the scaffold defends:

- I-CRDT-1: grant + concurrent edit converge. If user X is granted edit
  permission and they make an edit before the grant has propagated to
  all replicas, the edit either succeeds on all replicas or fails on
  all replicas — never half-half.
- I-CRDT-2: revoke + concurrent edit converge. Same property, reversed.
  The exact scenario Kleppmann's interview names as the open problem
  that Automerge solves.
- I-CRDT-3: backdated-edit attack resistance. A revoked user cannot
  forge a low-timestamp edit to slip past access control. We use
  vector clocks, not wall-clock; the access-control decision uses op
  causality, not op timestamp.

What's deferred to the eventual real implementation:

- Network transport (gossip / pub-sub).
- Persistence (today: in-memory; production: backed by substrate event_log).
- Encryption (every CRDT op should be signed by the originating actor).
- Garbage collection (CRDT ops accumulate; production needs compaction).

The scaffold's job is to make the eventual flip a one-config-line change.
"""

from .interfaces import (
    AccessControlOp,
    CRDTBackend,
    ConvergenceTrace,
    EditOp,
    GrantOp,
    OpId,
    RevokeOp,
)
from .access_control import (
    Document,
    EditOutcome,
    is_edit_authorized,
)
from .fakes import (
    OpInMemoryBackend,
    fresh_actor_id,
)

__all__ = [
    # Interfaces
    "AccessControlOp",
    "CRDTBackend",
    "ConvergenceTrace",
    "EditOp",
    "GrantOp",
    "OpId",
    "RevokeOp",
    # Access control
    "Document",
    "EditOutcome",
    "is_edit_authorized",
    # Fakes
    "OpInMemoryBackend",
    "fresh_actor_id",
]
