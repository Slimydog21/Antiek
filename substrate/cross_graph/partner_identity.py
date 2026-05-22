"""Partner-substrate identity + signed tokens (Sprint 30+ thread 1).

Per the Sprint 30+ breakdown thread 1: "Antiek instances at different
organisations can opt-in expose collective-graph slices to each other
under negotiated terms. Substrate retains the single-writer invariant
per instance; federation lives at the application-protocol layer."

This module is the substrate primitive that lets two Antiek instances
prove their identity to each other. The protocol is deliberately
boring — HMAC-SHA256 over a JSON-canonical payload using a shared
secret negotiated out-of-band between operators. No PKI, no asymmetric
crypto, no certificate authorities; production may layer those on top,
but the substrate primitive stays at the bytes level so it can be
audited in a sitting.

Key invariants:

- A partner's ``shared_secret`` never leaves the issuing instance's
  process memory in the clear once stored. The substrate stores it
  via ``substrate/multi_user/encryption.py``-style at-rest encryption
  in production; the in-memory dataclass here carries the raw secret
  for the duration of a request only.
- ``PartnerTrustState`` is a strict three-state machine:
  PENDING_HANDSHAKE → TRUSTED → REVOKED. REVOKED is terminal; a
  re-trusted partner gets a fresh ``partner_id``.
- Tokens carry an expiry; clock-skew between instances is bounded
  by ``DEFAULT_CLOCK_SKEW_SECONDS``. Expired tokens are NEVER
  accepted; the caller must re-issue.
- The substrate refuses any federation operation against a non-TRUSTED
  partner — this gate lives in ``federation.py`` and consumes this
  module's verification primitive.

Substrate-only. The handshake protocol (how two operators exchange
the shared secret in the first place) is operator-driven and not
specified here.
"""

from __future__ import annotations

import enum
import hashlib
import hmac
import json
import secrets
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional


# Optional hook fired after EVERY partner state transition. Signature:
# (newly-landed record). The audit-event bridge in event_emit.py uses
# this to convert the record to a typed Event and broadcast. Hooks are
# fired by the substrate state functions themselves (no longer
# the caller's job) — this closes the §13.7 audit gap where the
# breakdown's "every state transition lands in the event log" was
# enforced only when callers remembered to call the hook factory.
PartnerStateChangeHook = Callable[["PartnerSubstrate"], None]


# Tokens older than this are rejected. 5 minutes is the same window
# used by the master-spec §13.7 audit policy for cross-instance
# operations — long enough to survive network hops, short enough to
# bound replay risk.
DEFAULT_TOKEN_TTL_SECONDS: int = 300

# Bounded clock skew between instances. Federation-protocol calls
# must arrive within (ttl + skew) of issuance; otherwise rejected.
DEFAULT_CLOCK_SKEW_SECONDS: int = 30

# Shared-secret length. 256 bits of entropy via secrets.token_bytes.
SHARED_SECRET_BYTE_LEN: int = 32


def _now_unix() -> int:
    return int(time.time())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class PartnerTrustState(str, enum.Enum):
    """Three-state machine for a partner-substrate identity record."""

    PENDING_HANDSHAKE = "pending_handshake"
    TRUSTED = "trusted"
    REVOKED = "revoked"


class PartnerIdentityError(Exception):
    """Surfaces structural issues — unknown partner, invalid state
    transition, malformed token. Token-verification failures return
    None rather than raising so callers can branch on the result."""


@dataclass(frozen=True)
class PartnerSubstrate:
    """One partner-substrate identity record. Audit-friendly: every
    state change appends a new frozen record (mirrors AdvertiserRecord
    in advertiser_onboarding.py)."""

    partner_id: str
    display_name: str
    substrate_url: str  # e.g. "https://partner.example.com"
    shared_secret_hex: str  # never logged; HMAC key
    state: PartnerTrustState
    registered_at: str
    last_state_change_at: str
    operator_notes: str = ""
    revocation_reason: Optional[str] = None


@dataclass
class PartnerRegistry:
    """In-memory partner registry. Persistence lives in
    ``substrate/graph/schema.py`` (table: ``federation_partners``);
    the in-memory shape mirrors the row contract for tests and offline
    analysis. The shared_secret_hex is at-rest-encrypted in the
    persisted form (production wiring); the in-memory form is plain.

    Like ``AdvertiserRegistry``, the records list is append-only so
    the audit trail is preserved across state transitions."""

    records: list[PartnerSubstrate] = field(default_factory=list)

    def latest(self, partner_id: str) -> Optional[PartnerSubstrate]:
        """Return the most recent record for a partner, or None."""
        for r in reversed(self.records):
            if r.partner_id == partner_id:
                return r
        return None

    def all_trusted(self) -> list[PartnerSubstrate]:
        """Return latest records for every partner whose current state
        is TRUSTED. Deterministic ordering by partner_id."""
        latest_by_id: dict[str, PartnerSubstrate] = {}
        for r in self.records:
            latest_by_id[r.partner_id] = r
        trusted = [
            r for r in latest_by_id.values()
            if r.state is PartnerTrustState.TRUSTED
        ]
        trusted.sort(key=lambda r: r.partner_id)
        return trusted


def generate_shared_secret() -> str:
    """Produce a fresh HMAC shared secret. Operators exchange this
    out-of-band during the federation handshake; both instances store
    it via ``register_partner``. Hex-encoded for human-shareability."""
    return secrets.token_bytes(SHARED_SECRET_BYTE_LEN).hex()


def register_partner(
    registry: PartnerRegistry,
    *,
    display_name: str,
    substrate_url: str,
    shared_secret_hex: str,
    partner_id: Optional[str] = None,
    operator_notes: str = "",
    on_state_change: Optional[PartnerStateChangeHook] = None,
) -> PartnerSubstrate:
    """Register a new partner substrate. Lands in PENDING_HANDSHAKE.

    If ``on_state_change`` is provided, it fires AFTER the record
    lands in the registry — wire the audit-event bridge in here so
    every transition lands in the event log.
    """
    pid = partner_id or f"prt-{uuid.uuid4().hex[:12]}"
    if registry.latest(pid) is not None:
        raise PartnerIdentityError(
            f"partner_id {pid!r} already registered; use a fresh id "
            "or revoke the existing record first"
        )
    now = _now_iso()
    record = PartnerSubstrate(
        partner_id=pid,
        display_name=display_name,
        substrate_url=substrate_url,
        shared_secret_hex=shared_secret_hex,
        state=PartnerTrustState.PENDING_HANDSHAKE,
        registered_at=now,
        last_state_change_at=now,
        operator_notes=operator_notes,
    )
    registry.records.append(record)
    if on_state_change is not None:
        on_state_change(record)
    return record


def trust_partner(
    registry: PartnerRegistry,
    *,
    partner_id: str,
    operator_notes: str = "",
    on_state_change: Optional[PartnerStateChangeHook] = None,
) -> PartnerSubstrate:
    """Promote PENDING_HANDSHAKE → TRUSTED. Operator-driven."""
    current = registry.latest(partner_id)
    if current is None:
        raise PartnerIdentityError(f"unknown partner_id {partner_id!r}")
    if current.state is not PartnerTrustState.PENDING_HANDSHAKE:
        raise PartnerIdentityError(
            f"cannot trust partner_id {partner_id!r} in state "
            f"{current.state.value!r}; only PENDING_HANDSHAKE may be trusted"
        )
    new_record = PartnerSubstrate(
        partner_id=current.partner_id,
        display_name=current.display_name,
        substrate_url=current.substrate_url,
        shared_secret_hex=current.shared_secret_hex,
        state=PartnerTrustState.TRUSTED,
        registered_at=current.registered_at,
        last_state_change_at=_now_iso(),
        operator_notes=operator_notes or current.operator_notes,
    )
    registry.records.append(new_record)
    if on_state_change is not None:
        on_state_change(new_record)
    return new_record


def revoke_partner(
    registry: PartnerRegistry,
    *,
    partner_id: str,
    revocation_reason: str,
    on_state_change: Optional[PartnerStateChangeHook] = None,
) -> PartnerSubstrate:
    """REVOKED is terminal."""
    current = registry.latest(partner_id)
    if current is None:
        raise PartnerIdentityError(f"unknown partner_id {partner_id!r}")
    if current.state is PartnerTrustState.REVOKED:
        raise PartnerIdentityError(
            f"partner_id {partner_id!r} is already REVOKED; original "
            f"reason: {current.revocation_reason!r}"
        )
    new_record = PartnerSubstrate(
        partner_id=current.partner_id,
        display_name=current.display_name,
        substrate_url=current.substrate_url,
        shared_secret_hex=current.shared_secret_hex,
        state=PartnerTrustState.REVOKED,
        registered_at=current.registered_at,
        last_state_change_at=_now_iso(),
        operator_notes=current.operator_notes,
        revocation_reason=revocation_reason,
    )
    registry.records.append(new_record)
    if on_state_change is not None:
        on_state_change(new_record)
    return new_record


def _canonical_payload(payload: dict[str, Any]) -> bytes:
    """Deterministic JSON encoding. Sorted keys, no extra whitespace.
    HMAC must be computed over identical bytes on both sides."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("ascii")


def generate_partner_token(
    *,
    shared_secret_hex: str,
    payload: dict[str, Any],
    ttl_seconds: int = DEFAULT_TOKEN_TTL_SECONDS,
    issued_at_unix: Optional[int] = None,
) -> str:
    """Produce an HMAC-SHA256-signed token over the payload.

    Format: ``v1.{b64-payload}.{b64-issued_at}.{b64-expires_at}.{hex-sig}``

    The version prefix lets us evolve the format without ambiguity.
    The signature covers (payload, issued_at, expires_at) — tampering
    with any field fails verification.

    Args:
        shared_secret_hex: the hex-encoded shared secret from the
            PartnerSubstrate record.
        payload: arbitrary JSON-serializable dict. The caller defines
            the schema; common fields are partner_id, op_kind, nonce.
        ttl_seconds: token validity window in seconds.
        issued_at_unix: optional override (used by tests for clock
            manipulation); defaults to current unix time.
    """
    iat = issued_at_unix if issued_at_unix is not None else _now_unix()
    exp = iat + ttl_seconds
    payload_bytes = _canonical_payload(payload)
    sig_input = (
        payload_bytes
        + b"|"
        + str(iat).encode("ascii")
        + b"|"
        + str(exp).encode("ascii")
    )
    key = bytes.fromhex(shared_secret_hex)
    sig = hmac.new(key, sig_input, hashlib.sha256).hexdigest()
    # Base64-style URL-safe encoding via urlsafe_b64encode would
    # add a runtime dep on base64 here; instead we use hex which is
    # equally deterministic and audit-friendly.
    return f"v1.{payload_bytes.hex()}.{iat}.{exp}.{sig}"


def verify_partner_token(
    *,
    shared_secret_hex: str,
    token: str,
    now_unix: Optional[int] = None,
    clock_skew_seconds: int = DEFAULT_CLOCK_SKEW_SECONDS,
) -> Optional[dict[str, Any]]:
    """Verify a token and return the payload, or None if invalid.

    Returns None for: malformed token, bad version, tampered payload,
    expired token, or token from the future (clock skew exceeded).

    NEVER raises on cryptographic failure — returns None so callers
    branch cleanly. Raises only on programmer error (e.g. empty
    shared_secret_hex)."""
    if not shared_secret_hex:
        raise PartnerIdentityError("shared_secret_hex must be non-empty")
    parts = token.split(".")
    if len(parts) != 5:
        return None
    version, payload_hex, iat_str, exp_str, sig_hex = parts
    if version != "v1":
        return None
    try:
        payload_bytes = bytes.fromhex(payload_hex)
        iat = int(iat_str)
        exp = int(exp_str)
    except ValueError:
        return None

    sig_input = (
        payload_bytes
        + b"|"
        + str(iat).encode("ascii")
        + b"|"
        + str(exp).encode("ascii")
    )
    try:
        key = bytes.fromhex(shared_secret_hex)
    except ValueError:
        raise PartnerIdentityError("shared_secret_hex is not valid hex")
    expected_sig = hmac.new(key, sig_input, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_sig, sig_hex):
        return None

    now = now_unix if now_unix is not None else _now_unix()
    if now > exp + clock_skew_seconds:
        return None
    if now + clock_skew_seconds < iat:
        # Token from the future beyond allowed skew → reject.
        return None

    try:
        payload = json.loads(payload_bytes)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def is_partner_trusted(
    registry: PartnerRegistry, partner_id: str,
) -> bool:
    """Convenience check: True iff the partner's latest record is
    TRUSTED. Federation operations gate on this — see federation.py."""
    current = registry.latest(partner_id)
    if current is None:
        return False
    return current.state is PartnerTrustState.TRUSTED


# ── Persistence (Sprint 30+ thread 1) ──────────────────────────────


def ensure_table(con: Any) -> None:
    """Defensive table-creation. Canonical schema lives in
    ``substrate/graph/schema.py`` and runs at boot via ``init_database``;
    this is a no-op on a fully-initialized DB. Read-only connections
    fail silently — matching the federation_config_store posture."""
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS federation_partners (
                attempt_id              TEXT PRIMARY KEY,
                partner_id              TEXT NOT NULL,
                display_name            TEXT NOT NULL,
                substrate_url           TEXT NOT NULL,
                shared_secret_hex       TEXT NOT NULL,
                state                   TEXT NOT NULL CHECK (state IN (
                    'pending_handshake', 'trusted', 'revoked'
                )),
                registered_at           TIMESTAMP NOT NULL,
                last_state_change_at    TIMESTAMP NOT NULL,
                operator_notes          TEXT NOT NULL DEFAULT '',
                revocation_reason       TEXT,
                row_inserted_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    except Exception:
        pass


def _ts(s: str) -> str:
    """Normalize an ISO string the dataclass carries into a value
    DuckDB's TIMESTAMP accepts. The dataclass already produces
    ``…Z`` form; DuckDB tolerates this directly."""
    return s


def save_record(con: Any, record: PartnerSubstrate) -> str:
    """Append one ``PartnerSubstrate`` record to the federation_partners
    table. Returns the attempt_id assigned to the row. Idempotent on
    (partner_id, state, last_state_change_at) — re-saving the same
    record returns the existing attempt_id instead of inserting a
    duplicate."""
    ensure_table(con)
    existing = con.execute(
        "SELECT attempt_id FROM federation_partners "
        "WHERE partner_id = ? AND state = ? AND last_state_change_at = ? "
        "ORDER BY row_inserted_at LIMIT 1",
        [record.partner_id, record.state.value, _ts(record.last_state_change_at)],
    ).fetchone()
    if existing is not None:
        return existing[0]

    attempt_id = f"prtrec-{uuid.uuid4().hex[:12]}"
    con.execute(
        """
        INSERT INTO federation_partners (
            attempt_id, partner_id, display_name, substrate_url,
            shared_secret_hex, state, registered_at, last_state_change_at,
            operator_notes, revocation_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            attempt_id,
            record.partner_id,
            record.display_name,
            record.substrate_url,
            record.shared_secret_hex,
            record.state.value,
            _ts(record.registered_at),
            _ts(record.last_state_change_at),
            record.operator_notes,
            record.revocation_reason,
        ],
    )
    return attempt_id


def load_registry(con: Any) -> PartnerRegistry:
    """Reconstruct an in-memory ``PartnerRegistry`` from persisted
    state. Rows are returned in row_inserted_at order so the audit
    trail (and ``latest()`` semantics) match what the in-memory
    registry produced before persistence."""
    ensure_table(con)
    rows = con.execute(
        """
        SELECT partner_id, display_name, substrate_url, shared_secret_hex,
               state, registered_at, last_state_change_at,
               operator_notes, revocation_reason
        FROM federation_partners
        ORDER BY row_inserted_at, attempt_id
        """
    ).fetchall()
    registry = PartnerRegistry()
    for r in rows:
        registered_at = (
            r[5].isoformat() if hasattr(r[5], "isoformat") else str(r[5])
        )
        last_state_change_at = (
            r[6].isoformat() if hasattr(r[6], "isoformat") else str(r[6])
        )
        registry.records.append(PartnerSubstrate(
            partner_id=r[0],
            display_name=r[1],
            substrate_url=r[2],
            shared_secret_hex=r[3],
            state=PartnerTrustState(r[4]),
            registered_at=registered_at,
            last_state_change_at=last_state_change_at,
            operator_notes=r[7] or "",
            revocation_reason=r[8],
        ))
    return registry


__all__ = [
    "DEFAULT_CLOCK_SKEW_SECONDS",
    "DEFAULT_TOKEN_TTL_SECONDS",
    "PartnerIdentityError",
    "PartnerRegistry",
    "PartnerStateChangeHook",
    "PartnerSubstrate",
    "PartnerTrustState",
    "SHARED_SECRET_BYTE_LEN",
    "ensure_table",
    "generate_partner_token",
    "generate_shared_secret",
    "is_partner_trusted",
    "load_registry",
    "register_partner",
    "revoke_partner",
    "save_record",
    "trust_partner",
    "verify_partner_token",
]
