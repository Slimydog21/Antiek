"""Fail-closed launch readiness for the durable legal-policy boundary."""

from __future__ import annotations

import secrets
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from runtime.db_lock import LockedConnection

from .policy_store import (
    LegalPolicyAuthority,
    LegalPolicyDenied,
    PolicySnapshot,
    evaluate_document,
    load_global_policy_admin_capability,
    policy_snapshot,
)

READINESS_SCHEMA_VERSION = 1
WRITE_ENFORCEMENT_VERSION = 1
READ_ENFORCEMENT_VERSION = 1
_REQUIRED_TABLES = frozenset(
    {
        "legal_policy_events",
        "legal_policy_mutation_attempts",
        "legal_policy_lease_recoveries",
        "legal_document_admissions",
        "legal_chunk_admissions",
        "legal_document_custody_seals",
        "legal_policy_dispatch_leases",
    }
)


@dataclass(frozen=True)
class LegalPolicyReadiness:
    schema_version: int
    policy_snapshot_sha256: str | None
    issuer_state: Literal["configured", "not_configured", "invalid"]
    write_enforcement_version: int
    read_enforcement_version: int
    migration_state: Literal["current", "missing", "invalid"]
    production_defensible: bool
    reason_code: str | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PolicySnapshotLegalGate:
    """Immutable URL gate backed by the exact reviewed durable snapshot."""

    snapshot: PolicySnapshot

    def check_url(self, url: str):
        from . import LegalGateVerdict

        verdict = evaluate_document(self.snapshot, url=url)
        allowed = verdict.decision == "allow"
        return LegalGateVerdict(
            allowed=allowed,
            reason=(
                None
                if allowed
                else verdict.reason_code or "no_explicit_external_allow"
            ),
            gate_kind="durable_sql_policy",
        )


@dataclass(frozen=True)
class DispatchLeaseRecovery:
    lease_id: str
    holder_investigation_digest: str
    policy_snapshot_sha256: str
    terminal_event_fingerprint: str
    idempotency_replayed: bool


def list_policy_dispatch_leases(
    con: LockedConnection, authority: LegalPolicyAuthority
) -> tuple[dict[str, object], ...]:
    if authority.account_digest is None:
        raise LegalPolicyDenied("provider dispatch requires account policy authority")
    rows = con.execute(
        "SELECT lease_id, holder_investigation_id, holder_investigation_digest, "
        "policy_snapshot_sha256, acquired_at, expires_at "
        "FROM legal_policy_dispatch_leases WHERE account_digest = ? ORDER BY acquired_at",
        [authority.account_digest],
    ).fetchall()
    return tuple(
        {
            "lease_id": row[0],
            "holder_investigation_id": row[1],
            "holder_investigation_digest": row[2],
            "policy_snapshot_sha256": row[3],
            "acquired_at": row[4],
            "diagnostic_deadline": row[5],
        }
        for row in rows
    )


def recover_policy_dispatch_lease(
    con: LockedConnection,
    authority: LegalPolicyAuthority,
    *,
    lease_id: str,
    holder_investigation_digest: str,
    terminal_event_fingerprint: str,
    idempotency_key_digest: str,
) -> DispatchLeaseRecovery:
    """Delete a lease only after the API has supplied exact terminal evidence.

    This primitive verifies every durable binding and makes receipt insertion
    plus deletion one transaction owned by its caller. It never considers the
    diagnostic deadline.
    """
    if authority.account_digest is None:
        raise LegalPolicyDenied("provider dispatch requires account policy authority")
    for value, label in (
        (holder_investigation_digest, "holder digest"),
        (terminal_event_fingerprint, "terminal event fingerprint"),
        (idempotency_key_digest, "idempotency key digest"),
    ):
        if not isinstance(value, str) or len(value) != 64 or any(
            ch not in "0123456789abcdef" for ch in value
        ):
            raise LegalPolicyDenied(f"dispatch recovery {label} is malformed")
    prior = con.execute(
        "SELECT lease_id, holder_investigation_digest, policy_snapshot_sha256, "
        "terminal_event_fingerprint FROM legal_policy_lease_recoveries "
        "WHERE account_digest = ? AND idempotency_key_digest = ?",
        [authority.account_digest, idempotency_key_digest],
    ).fetchone()
    if prior is not None:
        if prior[0] != lease_id or prior[1] != holder_investigation_digest:
            raise LegalPolicyDenied("dispatch recovery idempotency key conflict")
        return DispatchLeaseRecovery(prior[0], prior[1], prior[2], prior[3], True)
    already = con.execute(
        "SELECT idempotency_key_digest FROM legal_policy_lease_recoveries "
        "WHERE account_digest = ? AND lease_id = ?",
        [authority.account_digest, lease_id],
    ).fetchone()
    if already is not None:
        raise LegalPolicyDenied("dispatch lease was already recovered")
    row = con.execute(
        "SELECT holder_investigation_digest, policy_snapshot_sha256 "
        "FROM legal_policy_dispatch_leases WHERE account_digest = ? AND lease_id = ?",
        [authority.account_digest, lease_id],
    ).fetchone()
    if row is None or row[0] != holder_investigation_digest:
        raise LegalPolicyDenied("dispatch lease is not recoverable")
    con.execute(
        "INSERT INTO legal_policy_lease_recoveries "
        "(account_digest, idempotency_key_digest, lease_id, "
        "holder_investigation_digest, terminal_event_fingerprint, "
        "policy_snapshot_sha256) VALUES (?, ?, ?, ?, ?, ?)",
        [authority.account_digest, idempotency_key_digest, lease_id,
         holder_investigation_digest, terminal_event_fingerprint, row[1]],
    )
    deleted = con.execute(
        "DELETE FROM legal_policy_dispatch_leases WHERE account_digest = ? "
        "AND lease_id = ? AND holder_investigation_digest = ? RETURNING lease_id",
        [authority.account_digest, lease_id, holder_investigation_digest],
    ).fetchone()
    if deleted != (lease_id,):
        raise LegalPolicyDenied("dispatch lease recovery lost its durable claim")
    return DispatchLeaseRecovery(lease_id, holder_investigation_digest, row[1],
                                 terminal_event_fingerprint, False)


def legal_policy_readiness(
    con: LockedConnection,
    authority: LegalPolicyAuthority | None,
    *,
    at: datetime | None = None,
) -> LegalPolicyReadiness:
    """Return launch truth without ever converting corruption into readiness."""
    if not isinstance(con, LockedConnection):
        raise TypeError("legal-policy readiness requires a LockedConnection")
    checked_at = datetime.now(UTC) if at is None else at
    if checked_at.tzinfo is None:
        raise ValueError("readiness time must be timezone-aware")

    try:
        rows = con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
        present = {str(row[0]) for row in rows}
    except Exception:
        return _closed("invalid", "migration_introspection_failed")
    if not _REQUIRED_TABLES.issubset(present):
        return _closed("missing", "legal_policy_migrations_missing")

    snapshot_sha256: str | None = None
    if authority is not None:
        try:
            snapshot_sha256 = policy_snapshot(con, authority, at=checked_at).snapshot_sha256
        except (LegalPolicyDenied, ValueError, TypeError):
            return _closed("invalid", "policy_snapshot_invalid")

    try:
        load_global_policy_admin_capability()
    except LegalPolicyDenied:
        issuer_state: Literal["configured", "not_configured", "invalid"] = "not_configured"
        issuer_reason = "global_policy_issuer_not_configured"
    except ValueError:
        issuer_state = "invalid"
        issuer_reason = "global_policy_issuer_invalid"
    else:
        issuer_state = "configured"
        issuer_reason = None

    return LegalPolicyReadiness(
        schema_version=READINESS_SCHEMA_VERSION,
        policy_snapshot_sha256=snapshot_sha256,
        issuer_state=issuer_state,
        write_enforcement_version=WRITE_ENFORCEMENT_VERSION,
        read_enforcement_version=READ_ENFORCEMENT_VERSION,
        migration_state="current",
        production_defensible=issuer_state == "configured" and snapshot_sha256 is not None,
        reason_code=(
            issuer_reason
            if issuer_reason is not None
            else ("policy_snapshot_context_required" if snapshot_sha256 is None else None)
        ),
    )


def require_policy_snapshot(
    con: LockedConnection,
    authority: LegalPolicyAuthority,
    *,
    expected_sha256: str,
    at: datetime | None = None,
) -> None:
    """Refuse a launch claim unless its reviewed policy snapshot is exact."""
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise LegalPolicyDenied("reviewed legal-policy snapshot is malformed")
    current = policy_snapshot(
        con, authority, at=datetime.now(UTC) if at is None else at
    ).snapshot_sha256
    if current != expected_sha256:
        raise LegalPolicyDenied("legal-policy snapshot changed after launch review")


def snapshot_legal_gate(
    con: LockedConnection,
    authority: LegalPolicyAuthority,
    *,
    expected_sha256: str,
    at: datetime | None = None,
) -> PolicySnapshotLegalGate:
    checked_at = datetime.now(UTC) if at is None else at
    snapshot = policy_snapshot(con, authority, at=checked_at)
    if snapshot.snapshot_sha256 != expected_sha256:
        raise LegalPolicyDenied("legal-policy snapshot changed after launch review")
    return PolicySnapshotLegalGate(snapshot)


def claim_policy_dispatch_lease(
    con: LockedConnection,
    authority: LegalPolicyAuthority,
    *,
    holder_investigation_digest: str,
    holder_investigation_id: str | None = None,
    expected_sha256: str,
    ttl_seconds: int = 300,
) -> tuple[str, PolicySnapshotLegalGate]:
    """Atomically pin an exact snapshot across one provider dispatch.

    ``expires_at`` is operational evidence for stale-lease diagnosis, not an
    automatic safety release. Policy mutation treats every row as active until
    the holder explicitly releases it. A crashed worker can therefore require
    operator recovery, but it can never silently let old policy keep fetching
    after a timed unlock.
    """
    if authority.account_digest is None:
        raise LegalPolicyDenied("provider dispatch requires account policy authority")
    if (
        not isinstance(holder_investigation_digest, str)
        or len(holder_investigation_digest) != 64
    ):
        raise LegalPolicyDenied("provider dispatch holder is malformed")
    if holder_investigation_id is not None and (
        not isinstance(holder_investigation_id, str)
        or not holder_investigation_id.strip()
        or holder_investigation_id != holder_investigation_id.strip()
        or len(holder_investigation_id) > 300
    ):
        raise LegalPolicyDenied("provider dispatch holder identity is malformed")
    if not isinstance(ttl_seconds, int) or not 1 <= ttl_seconds <= 900:
        raise ValueError("policy dispatch lease TTL must be between 1 and 900 seconds")
    existing_holder = con.execute(
        "SELECT lease_id FROM legal_policy_dispatch_leases WHERE account_digest = ? "
        "AND holder_investigation_digest = ? LIMIT 1",
        [authority.account_digest, holder_investigation_digest],
    ).fetchone()
    if existing_holder is not None:
        raise LegalPolicyDenied("provider dispatch holder already has an active lease")
    gate = snapshot_legal_gate(con, authority, expected_sha256=expected_sha256)
    lease_id = f"lpdl-{secrets.token_hex(16)}"
    acquired_at = datetime.now(UTC)
    expires_at = acquired_at + timedelta(seconds=ttl_seconds)
    con.execute(
        "INSERT INTO legal_policy_dispatch_leases "
        "(lease_id, account_digest, policy_snapshot_sha256, "
        "holder_investigation_digest, acquired_at, expires_at, holder_investigation_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            lease_id,
            authority.account_digest,
            expected_sha256,
            holder_investigation_digest,
            acquired_at,
            expires_at,
            holder_investigation_id,
        ],
    )
    return lease_id, gate


def release_policy_dispatch_lease(
    con: LockedConnection,
    authority: LegalPolicyAuthority,
    *,
    lease_id: str,
    holder_investigation_digest: str,
) -> None:
    if authority.account_digest is None:
        raise LegalPolicyDenied("provider dispatch requires account policy authority")
    row = con.execute(
        "DELETE FROM legal_policy_dispatch_leases WHERE lease_id = ? "
        "AND account_digest = ? AND holder_investigation_digest = ? RETURNING lease_id",
        [lease_id, authority.account_digest, holder_investigation_digest],
    ).fetchone()
    if row != (lease_id,):
        raise LegalPolicyDenied("provider dispatch lease release denied")


def _closed(
    migration_state: Literal["missing", "invalid"], reason_code: str
) -> LegalPolicyReadiness:
    return LegalPolicyReadiness(
        schema_version=READINESS_SCHEMA_VERSION,
        policy_snapshot_sha256=None,
        issuer_state="invalid",
        write_enforcement_version=0,
        read_enforcement_version=0,
        migration_state=migration_state,
        production_defensible=False,
        reason_code=reason_code,
    )


__all__ = [
    "READINESS_SCHEMA_VERSION",
    "READ_ENFORCEMENT_VERSION",
    "WRITE_ENFORCEMENT_VERSION",
    "LegalPolicyReadiness",
    "PolicySnapshotLegalGate",
    "DispatchLeaseRecovery",
    "legal_policy_readiness",
    "list_policy_dispatch_leases",
    "recover_policy_dispatch_lease",
    "claim_policy_dispatch_lease",
    "release_policy_dispatch_lease",
    "require_policy_snapshot",
    "snapshot_legal_gate",
]
