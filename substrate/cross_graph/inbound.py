"""Inbound federation handler (Sprint 30+ thread 1, receiver side).

The symmetric counterpart to ``federate_outbound_citation``. When
Instance A federates a citation outbound, Instance B accepts it
through this module.

Acceptance gates, in order:

  1. ``config.allowed_partner_substrates`` — the receiver's own
     operator-level policy must list A as an accepted source.
  2. Partner is registered + TRUSTED in B's ``PartnerRegistry``.
  3. The signed token verifies against B's stored shared_secret_hex
     for A (round-trip with ``verify_partner_token``).
  4. The payload schema matches the outbound contract — required
     fields present, op_kind correct.
  5. The nonce has not been seen recently (replay defense via the
     ``NonceLedger``). A captured token within its TTL window cannot
     be accepted twice.

On success the handler materializes an ``InboundCitationOutcome``
carrying a freshly-minted ``CrossGraphReference`` (B's view of the
same citation A recorded outbound) plus the revenue-routing handle
the partner sent. The receiver's attribution pipeline picks this up
and credits the referenced user's account on this instance.

Per the master-spec single-writer invariant: the handler itself
runs in-process and returns the outcome; persistence to the events
table is the caller's responsibility (same posture as
``ad_inventory.event_subscription``).
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from .federation import CrossGraphReference, FederationConfig
from .partner_identity import (
    DEFAULT_CLOCK_SKEW_SECONDS,
    DEFAULT_TOKEN_TTL_SECONDS,
    PartnerRegistry,
    is_partner_trusted,
    verify_partner_token,
)


# The replay window is the maximum age a nonce could still be inside
# its token's validity, plus the clock-skew tolerance. Inbound tokens
# older than this are rejected upstream by verify_partner_token, so
# we only need to remember nonces this far back.
DEFAULT_NONCE_RETENTION_SECONDS: int = (
    DEFAULT_TOKEN_TTL_SECONDS + DEFAULT_CLOCK_SKEW_SECONDS
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _now_unix() -> int:
    import time
    return int(time.time())


class InboundRejection(str, enum.Enum):
    """Concrete reasons an inbound citation is refused. The handler
    NEVER raises on rejection — it returns an ``InboundCitationOutcome``
    with ``accepted=False`` and a populated ``rejection`` so the caller
    can log the refusal as a typed audit event."""

    PARTNER_NOT_ALLOWED = "partner_not_allowed"
    PARTNER_NOT_REGISTERED = "partner_not_registered"
    PARTNER_NOT_TRUSTED = "partner_not_trusted"
    TOKEN_INVALID = "token_invalid"  # signature / expiry / malformed
    PAYLOAD_MALFORMED = "payload_malformed"
    REPLAY_DETECTED = "replay_detected"


# Fields the outbound payload must carry. Mirrors the schema produced
# by federate_outbound_citation; tightening either side requires
# updating both.
_REQUIRED_PAYLOAD_FIELDS: tuple[str, ...] = (
    "op_kind",
    "reference_id",
    "referencing_user_id",
    "referencing_investigation_id",
    "referenced_user_id",
    "referenced_note_id",
    "revenue_routing_handle",
    "nonce",
)


@dataclass
class NonceLedger:
    """Bounded-size nonce store for replay defense.

    Stores ``{nonce: expires_at_unix}`` and prunes lazily on every
    access. The retention window is intentionally short (default 5m
    30s) because a token outside that window already fails token
    expiry — the ledger only needs to remember things that could
    still be inside their TTL.

    Single-instance in-memory only. Multi-process deployments need
    a shared store (Redis-equivalent) — that's a Sprint 30+ wiring
    decision and is out of scope for the substrate primitive."""

    retention_seconds: int = DEFAULT_NONCE_RETENTION_SECONDS
    seen: dict[str, int] = field(default_factory=dict)

    def _prune(self, now_unix: int) -> None:
        """Drop entries whose retention has passed. O(n) but n is
        bounded by retention_seconds * peak-rps which is small for
        any realistic federation deployment."""
        cutoff = now_unix
        dead = [n for n, exp in self.seen.items() if exp <= cutoff]
        for n in dead:
            del self.seen[n]

    def remember(
        self, nonce: str, *, now_unix: Optional[int] = None,
    ) -> bool:
        """Record a nonce as seen. Returns True if this was a
        first-time observation; False if the nonce was already in
        the ledger (i.e. replay detected)."""
        now = now_unix if now_unix is not None else _now_unix()
        self._prune(now)
        if nonce in self.seen:
            return False
        self.seen[nonce] = now + self.retention_seconds
        return True


@dataclass(frozen=True)
class InboundCitationOutcome:
    """Result of handling one inbound federation request.

    On accept: ``accepted=True``, ``reference`` carries the receiver's
    materialized ``CrossGraphReference`` and ``revenue_routing_handle``
    carries the opaque handle the sender supplied.

    On reject: ``accepted=False``, ``rejection`` names the gate that
    refused, and ``detail`` carries a short operator-readable string
    (NEVER the raw token, NEVER the shared secret — these would
    leak into audit logs)."""

    accepted: bool
    rejection: Optional[InboundRejection] = None
    detail: str = ""
    reference: Optional[CrossGraphReference] = None
    revenue_routing_handle: Optional[str] = None
    received_at: str = field(default_factory=_now_iso)


def _refuse(reason: InboundRejection, detail: str) -> InboundCitationOutcome:
    return InboundCitationOutcome(
        accepted=False, rejection=reason, detail=detail,
    )


# Optional callback the substrate fires for EVERY inbound outcome —
# accepted or refused. Signature is (outcome, partner_id) so the
# audit-emit bridge can build the right event type. Audit-side wiring
# belongs to the caller, not the substrate primitive.
InboundOutcomeHook = Callable[["InboundCitationOutcome", str], None]


def accept_inbound_citation(
    *,
    config: FederationConfig,
    partner_registry: PartnerRegistry,
    nonce_ledger: NonceLedger,
    partner_id: str,
    token: str,
    now_unix: Optional[int] = None,
    on_outcome: Optional[InboundOutcomeHook] = None,
) -> InboundCitationOutcome:
    """Verify + record one inbound federation citation.

    Returns an ``InboundCitationOutcome``. Never raises on a
    rejection — callers branch on ``outcome.accepted``.

    Args:
        config: this instance's FederationConfig. Inbound-side
            policy: a partner must be in
            ``allowed_partner_substrates`` to send TO us, mirroring
            the outbound check. The two opt-in / attribution flags
            apply to outbound only; they're not re-checked here
            because the sender already enforced them.
        partner_registry: this instance's view of registered
            partners.
        nonce_ledger: replay-defense ledger. Caller should supply
            the SAME instance across requests so nonces actually
            de-duplicate.
        partner_id: which partner is claiming to have sent this
            token. Used to look up the shared secret.
        token: the signed token from the sender.
        now_unix: optional clock override for tests.
        on_outcome: optional callback fired with (outcome, partner_id)
            for EVERY outcome — accepted or refused. The audit-emit
            bridge wires in here. Refused outcomes fire too so the
            event log records the typed rejection reason; silent drops
            are impossible.
    """
    def _finalize(outcome: InboundCitationOutcome) -> InboundCitationOutcome:
        if on_outcome is not None:
            on_outcome(outcome, partner_id)
        return outcome

    if partner_id not in config.allowed_partner_substrates:
        return _finalize(_refuse(
            InboundRejection.PARTNER_NOT_ALLOWED,
            f"partner_id {partner_id!r} not in allowed_partner_substrates",
        ))

    partner = partner_registry.latest(partner_id)
    if partner is None:
        return _finalize(_refuse(
            InboundRejection.PARTNER_NOT_REGISTERED,
            f"partner_id {partner_id!r} unknown to this instance",
        ))
    if not is_partner_trusted(partner_registry, partner_id):
        return _finalize(_refuse(
            InboundRejection.PARTNER_NOT_TRUSTED,
            f"partner_id {partner_id!r} state={partner.state.value!r}",
        ))

    payload = verify_partner_token(
        shared_secret_hex=partner.shared_secret_hex,
        token=token,
        now_unix=now_unix,
    )
    if payload is None:
        return _finalize(_refuse(
            InboundRejection.TOKEN_INVALID,
            "token signature, expiry, or format invalid",
        ))

    # Schema check — every required field must be a non-empty string.
    for f in _REQUIRED_PAYLOAD_FIELDS:
        v = payload.get(f)
        if not isinstance(v, str) or not v:
            return _finalize(_refuse(
                InboundRejection.PAYLOAD_MALFORMED,
                f"payload field {f!r} missing or not a non-empty string",
            ))
    if payload["op_kind"] != "outbound_citation":
        return _finalize(_refuse(
            InboundRejection.PAYLOAD_MALFORMED,
            f"op_kind={payload['op_kind']!r}; expected 'outbound_citation'",
        ))

    if not nonce_ledger.remember(payload["nonce"], now_unix=now_unix):
        return _finalize(_refuse(
            InboundRejection.REPLAY_DETECTED,
            f"nonce {payload['nonce']!r} already seen within retention window",
        ))

    # Materialize the receiver-side reference. The reference_id is
    # this instance's own; we don't reuse the sender's reference_id
    # so the two sides have distinct local identifiers (the
    # sender's id rides in payload['reference_id'] for joining).
    reference = CrossGraphReference(
        reference_id=f"xref-in-{uuid.uuid4().hex[:12]}",
        referencing_user_id=payload["referencing_user_id"],
        referencing_investigation_id=payload["referencing_investigation_id"],
        referenced_user_id=payload["referenced_user_id"],
        referenced_note_id=payload["referenced_note_id"],
        federated_substrate_id=partner_id,
    )
    return _finalize(InboundCitationOutcome(
        accepted=True,
        reference=reference,
        revenue_routing_handle=payload["revenue_routing_handle"],
    ))


# ── Persistence (Sprint 30+ thread 1) ──────────────────────────────


def ensure_nonce_table(con: Any) -> None:
    """Defensive table-creation for the persistent nonce ledger.
    Canonical schema lives in ``substrate/graph/schema.py``."""
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS federation_nonces (
                nonce            TEXT PRIMARY KEY,
                partner_id       TEXT NOT NULL,
                accepted_at_unix BIGINT NOT NULL,
                expires_at_unix  BIGINT NOT NULL
            )
            """
        )
    except Exception:
        pass


def prune_expired_nonces(
    con: Any, *, now_unix: Optional[int] = None,
) -> int:
    """Delete every nonce whose ``expires_at_unix`` has passed. Returns
    the count of rows removed. Safe to call from any code path —
    used by ``remember_nonce_persistent`` opportunistically before
    a write, and by callers that want explicit pruning."""
    ensure_nonce_table(con)
    now = now_unix if now_unix is not None else _now_unix()
    cur = con.execute(
        "DELETE FROM federation_nonces WHERE expires_at_unix <= ?",
        [now],
    )
    # DuckDB's execute returns the result wrapper; rowcount sits on
    # the cursor object on supported builds. Falls back to 0 if not
    # exposed — pruning is best-effort, not load-bearing.
    return int(getattr(cur, "rowcount", 0) or 0)


def remember_nonce_persistent(
    con: Any,
    *,
    nonce: str,
    partner_id: str,
    retention_seconds: int = DEFAULT_NONCE_RETENTION_SECONDS,
    now_unix: Optional[int] = None,
) -> bool:
    """Atomically claim a nonce in the persistent ledger.

    Returns True iff this was a first-time observation; False if the
    nonce was already present (replay).

    Prunes expired rows before the claim attempt so a nonce that has
    aged out is reusable. The substrate uses the PRIMARY KEY constraint
    on ``nonce`` as the conflict gate — concurrent claims serialize
    through DuckDB's single-writer invariant.
    """
    ensure_nonce_table(con)
    now = now_unix if now_unix is not None else _now_unix()
    prune_expired_nonces(con, now_unix=now)
    existing = con.execute(
        "SELECT 1 FROM federation_nonces WHERE nonce = ?", [nonce],
    ).fetchone()
    if existing is not None:
        return False
    con.execute(
        """
        INSERT INTO federation_nonces (
            nonce, partner_id, accepted_at_unix, expires_at_unix
        ) VALUES (?, ?, ?, ?)
        """,
        [nonce, partner_id, now, now + retention_seconds],
    )
    return True


def load_active_nonces(
    con: Any, *, now_unix: Optional[int] = None,
) -> NonceLedger:
    """Reconstruct an in-memory ``NonceLedger`` from the persistent
    table, dropping any rows that have already expired. Used at
    process startup so the in-memory ledger inherits the prior
    substrate's replay-defense state."""
    ensure_nonce_table(con)
    now = now_unix if now_unix is not None else _now_unix()
    rows = con.execute(
        "SELECT nonce, expires_at_unix FROM federation_nonces "
        "WHERE expires_at_unix > ?",
        [now],
    ).fetchall()
    ledger = NonceLedger()
    for nonce, exp in rows:
        ledger.seen[nonce] = int(exp)
    return ledger


__all__ = [
    "DEFAULT_NONCE_RETENTION_SECONDS",
    "InboundCitationOutcome",
    "InboundOutcomeHook",
    "InboundRejection",
    "NonceLedger",
    "accept_inbound_citation",
    "ensure_nonce_table",
    "load_active_nonces",
    "prune_expired_nonces",
    "remember_nonce_persistent",
]
