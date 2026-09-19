"""Transactional synthesis event intents and exact-authority reconciliation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from runtime.db_lock import LockedConnection
from substrate.event_log import append_event_once_authorized
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.schemas.events import Event


class SynthesisOutboxConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class ReconcileResult:
    attempted: int
    delivered: int
    pending: int


def _require_locked(con: object) -> LockedConnection:
    if not isinstance(con, LockedConnection):
        raise TypeError("synthesis outbox requires a LockedConnection")
    return con


def _canonical_event(event: Event) -> tuple[str, str]:
    raw = json.dumps(
        event.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def stable_synthesis_event_id(
    authority: InvestigationAuthority,
    synthesis_id: str,
    action_type: str,
    *,
    logical_key: str | None = None,
) -> str:
    if not all(
        isinstance(value, str) and value and value == value.strip()
        for value in (synthesis_id, action_type, logical_key or action_type)
    ):
        raise ValueError("stable synthesis event identity is invalid")
    digest = hashlib.sha256(
        b"antiek-synthesis-outbox-v1\0"
        + bytes.fromhex(authority.stream_key)
        + b"\0"
        + synthesis_id.encode()
        + b"\0"
        + action_type.encode()
        + b"\0"
        + (logical_key or action_type).encode()
    ).hexdigest()[:32]
    return f"evt-{digest}"


def stage_synthesis_event(
    con: LockedConnection,
    authority: InvestigationAuthority,
    event: Event,
) -> str:
    """Stage the exact envelope in the caller's existing DB transaction."""
    con = _require_locked(con)
    if not isinstance(authority, InvestigationAuthority):
        raise TypeError("synthesis outbox requires InvestigationAuthority")
    if event.investigation_id != authority.investigation_id or not event.synthesis_id:
        raise ValueError("synthesis outbox event crosses authority")
    parent = con.execute(
        "SELECT synthesis_id, investigation_id, account_digest, "
        "investigation_digest FROM syntheses WHERE synthesis_id = ? "
        "AND account_digest = ? AND investigation_digest = ?",
        [
            event.synthesis_id,
            authority.account_digest,
            authority.investigation_digest,
        ],
    ).fetchone()
    if parent is None:
        raise SynthesisOutboxConflict("synthesis outbox parent authority is missing")
    raw, fingerprint = _canonical_event(event)
    existing = con.execute(
        "SELECT synthesis_id, account_digest, investigation_digest, "
        "event_json, event_fingerprint FROM synthesis_event_outbox "
        "WHERE event_id = ?",
        [event.event_id],
    ).fetchone()
    expected = (
        event.synthesis_id,
        authority.account_digest,
        authority.investigation_digest,
        raw,
        fingerprint,
    )
    if existing is None:
        sequence_no = int(
            con.execute(
                "SELECT coalesce(max(sequence_no), 0) + 1 "
                "FROM synthesis_event_outbox WHERE synthesis_id = ? "
                "AND account_digest = ? AND investigation_digest = ?",
                [
                    event.synthesis_id,
                    authority.account_digest,
                    authority.investigation_digest,
                ],
            ).fetchone()[0]
        )
        con.execute(
            "INSERT INTO synthesis_event_outbox "
            "(event_id, synthesis_id, account_digest, investigation_digest, "
            "event_json, event_fingerprint, sequence_no) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [event.event_id, *expected, sequence_no],
        )
    elif tuple(existing) != expected:
        raise SynthesisOutboxConflict("synthesis outbox event id conflicts")
    return event.event_id


def _error_code(exc: Exception) -> str:
    if isinstance(exc, ValueError):
        return "event_validation_failed"
    if isinstance(exc, RuntimeError):
        return "event_persistence_failed"
    return "event_delivery_failed"


def reconcile_synthesis_events(
    con: LockedConnection,
    authority: InvestigationAuthority,
    *,
    limit: int = 100,
    raise_on_error: bool = False,
) -> ReconcileResult:
    """Append pending envelopes once, then durably acknowledge delivery."""
    con = _require_locked(con)
    if not isinstance(authority, InvestigationAuthority):
        raise TypeError("synthesis outbox requires InvestigationAuthority")
    if not 1 <= limit <= 10_000:
        raise ValueError("synthesis outbox reconciliation limit is invalid")
    rows = con.execute(
        "SELECT event_id, event_json, event_fingerprint "
        "FROM synthesis_event_outbox WHERE account_digest = ? "
        "AND investigation_digest = ? AND delivery_state = 'pending' "
        "AND NOT coalesce(terminal_failure, FALSE) "
        "ORDER BY created_at, synthesis_id, sequence_no, event_id LIMIT ?",
        [authority.account_digest, authority.investigation_digest, limit],
    ).fetchall()
    delivered = 0
    attempted = 0
    for event_id, raw, fingerprint in rows:
        attempted += 1
        try:
            if hashlib.sha256(raw.encode()).hexdigest() != fingerprint:
                raise SynthesisOutboxConflict("synthesis outbox fingerprint mismatch")
            event = Event.model_validate_json(raw)
            if event.event_id != event_id:
                raise SynthesisOutboxConflict("synthesis outbox envelope mismatch")
            append_event_once_authorized(authority, event)
            con.execute(
                "UPDATE synthesis_event_outbox SET delivery_state = 'delivered', "
                "attempt_count = attempt_count + 1, last_error_code = NULL, "
                "delivered_at = CURRENT_TIMESTAMP WHERE event_id = ? "
                "AND delivery_state = 'pending'",
                [event_id],
            )
            delivered += 1
        except Exception as exc:
            permanent = isinstance(exc, (SynthesisOutboxConflict, ValueError))
            con.execute(
                "UPDATE synthesis_event_outbox SET attempt_count = attempt_count + 1, "
                "last_error_code = ?, terminal_failure = ? WHERE event_id = ?",
                [_error_code(exc), permanent, event_id],
            )
            if raise_on_error:
                raise
            if not permanent:
                break
    pending = int(
        con.execute(
            "SELECT count(*) FROM synthesis_event_outbox "
            "WHERE account_digest = ? AND investigation_digest = ? "
            "AND delivery_state = 'pending' "
            "AND NOT coalesce(terminal_failure, FALSE)",
            [authority.account_digest, authority.investigation_digest],
        ).fetchone()[0]
    )
    return ReconcileResult(attempted=attempted, delivered=delivered, pending=pending)
