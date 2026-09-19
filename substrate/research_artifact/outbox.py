"""Durable artifact-event outbox used when file and event commits cannot be atomic."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from substrate.event_log import append_event_once, prepare_typed_event
from substrate.schemas.events import ArtifactGeneratedPayload, Event

from .authority import ArtifactAuthority
from .observability import record_counter
from .storage import (
    FilesystemArtifactStore,
    UnsafeArtifactState,
    _atomic_write,
    _private_dir,
    _read_regular,
)


@dataclass(frozen=True)
class PendingArtifactEvent:
    path: Path
    event: Event
    expected_storage_hash: str | None = None


@dataclass(frozen=True)
class ArtifactEventReconcileResult:
    attempted: int
    delivered: int
    pending: int
    quarantined: int


def _root(authority: ArtifactAuthority, root: Path | None) -> Path:
    return Path(root or authority.account_dir().parents[1])


def stage_event(
    authority: ArtifactAuthority,
    *,
    event_key: str,
    payload: dict[str, Any],
    role: str,
    expected_storage_hash: str | None = None,
    root: Path | None = None,
) -> PendingArtifactEvent:
    storage_root = _root(authority, root)
    directory = authority.account_dir(storage_root) / "pending-events"
    _private_dir(storage_root, directory)
    key = hashlib.sha256(event_key.encode("utf-8")).hexdigest()
    path = directory / f"{key}.json"
    typed_payload = ArtifactGeneratedPayload.model_validate(payload)
    event = prepare_typed_event(
        authority.event_stream_id,
        typed_payload,
        event_id=f"evt-artifact-{key[:32]}",
        role=role,
        # The logical event key is stable across crash replay. Its timestamp
        # must be stable too because append_event_once validates the complete
        # immutable envelope rather than treating an ID collision as success.
        emitted_at=datetime.fromtimestamp(int(key[:8], 16), tz=UTC),
    )
    event_json = event.model_dump(mode="json")
    if expected_storage_hash is not None and (
        len(expected_storage_hash) != 64
        or any(character not in "0123456789abcdef" for character in expected_storage_hash)
    ):
        raise ValueError("artifact event storage hash is invalid")
    record_body = {
        "version": 3,
        "event_stream_id": authority.event_stream_id,
        "event": event_json,
        "expected_storage_hash": expected_storage_hash,
    }
    record = {
        **record_body,
        "record_fingerprint": hashlib.sha256(
            json.dumps(record_body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }
    _atomic_write(
        storage_root,
        path,
        json.dumps(record, sort_keys=True, separators=(",", ":")).encode(),
    )
    return PendingArtifactEvent(
        path=path, event=event, expected_storage_hash=expected_storage_hash
    )


def complete_event(
    authority: ArtifactAuthority,
    pending: PendingArtifactEvent | Path,
    *,
    root: Path | None = None,
) -> None:
    storage_root = _root(authority, root)
    expected_parent = authority.account_dir(storage_root) / "pending-events"
    path = pending.path if isinstance(pending, PendingArtifactEvent) else pending
    if path.parent != expected_parent:
        raise ValueError("artifact event outbox path escaped account scope")
    path.unlink(missing_ok=True)
    directory_fd = os.open(expected_parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def mark_event_pending(authority: ArtifactAuthority, *, root: Path | None = None) -> None:
    record_counter(
        _root(authority, root),
        "artifact_event_pending_total",
        account_digest=authority.account_digest,
    )


def _legacy_event(path: Path, record: dict[str, Any]) -> Event:
    payload = ArtifactGeneratedPayload.model_validate(record.get("payload"))
    role = record.get("role")
    if not isinstance(role, str) or not role or role != role.strip():
        raise ValueError("legacy artifact event role is invalid")
    emitted_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    return prepare_typed_event(
        str(record.get("event_stream_id") or ""),
        payload,
        event_id=f"evt-artifact-{path.stem[:32]}",
        role=role,
        emitted_at=emitted_at,
    )


def _read_pending(authority: ArtifactAuthority, path: Path) -> PendingArtifactEvent:
    record = json.loads(_read_regular(path).decode("utf-8"))
    if not isinstance(record, dict):
        raise ValueError("artifact event record is invalid")
    if record.get("event_stream_id") != authority.event_stream_id:
        raise ValueError("artifact event record crosses authority")
    if record.get("version") == 1:
        event = _legacy_event(path, record)
        expected_storage_hash = None
    elif record.get("version") == 2:
        event_raw = record.get("event")
        if not isinstance(event_raw, dict):
            raise ValueError("artifact event envelope is invalid")
        canonical = json.dumps(event_raw, sort_keys=True, separators=(",", ":"))
        if (
            not isinstance(record.get("event_fingerprint"), str)
            or not hashlib.sha256(canonical.encode()).hexdigest() == record["event_fingerprint"]
        ):
            raise ValueError("artifact event fingerprint mismatch")
        event = Event.model_validate(event_raw)
        expected_storage_hash = None
    elif record.get("version") == 3:
        record_body = {
            key: value for key, value in record.items() if key != "record_fingerprint"
        }
        canonical = json.dumps(record_body, sort_keys=True, separators=(",", ":"))
        if set(record) != {
            "version",
            "event_stream_id",
            "event",
            "expected_storage_hash",
            "record_fingerprint",
        } or record.get("record_fingerprint") != hashlib.sha256(
            canonical.encode()
        ).hexdigest():
            raise ValueError("artifact event record fingerprint mismatch")
        event = Event.model_validate(record.get("event"))
        expected_storage_hash = record.get("expected_storage_hash")
        if expected_storage_hash is not None and (
            not isinstance(expected_storage_hash, str)
            or len(expected_storage_hash) != 64
            or any(
                character not in "0123456789abcdef"
                for character in expected_storage_hash
            )
        ):
            raise ValueError("artifact event storage hash is invalid")
    else:
        raise ValueError("artifact event record version is unsupported")
    if event.investigation_id != authority.event_stream_id:
        raise ValueError("artifact event envelope crosses authority")
    ArtifactGeneratedPayload.model_validate(event.payload)
    return PendingArtifactEvent(
        path=path, event=event, expected_storage_hash=expected_storage_hash
    )


def reconcile_pending_events(
    authority: ArtifactAuthority,
    *,
    events_dir: str | None = None,
    root: Path | None = None,
    limit: int = 100,
) -> ArtifactEventReconcileResult:
    """Deliver exact staged envelopes once and quarantine malformed records."""
    if not 1 <= limit <= 10_000:
        raise ValueError("artifact event reconciliation limit is invalid")
    storage_root = _root(authority, root)
    directory = authority.account_dir(storage_root) / "pending-events"
    quarantine = authority.account_dir(storage_root) / "quarantined-events"
    _private_dir(storage_root, directory)
    attempted = delivered = quarantined = 0

    def quarantine_record(path: Path) -> None:
        nonlocal quarantined
        _private_dir(storage_root, quarantine)
        destination = quarantine / path.name
        if destination.exists() or destination.is_symlink():
            raise UnsafeArtifactState("artifact event quarantine collision") from None
        os.replace(path, destination)
        quarantined += 1

    for path in sorted(directory.glob("*.json"))[:limit]:
        attempted += 1
        try:
            pending = _read_pending(authority, path)
        # fmt: off -- keep Python 3.11-compatible multi-exception syntax.
        except (OSError, ValueError, json.JSONDecodeError, UnsafeArtifactState):
            # fmt: on
            quarantine_record(path)
            continue
        try:
            if pending.expected_storage_hash is None:
                append_event_once(pending.event, events_dir=events_dir)
                complete_event(authority, pending, root=storage_root)
            else:
                store = FilesystemArtifactStore(storage_root)
                with store.mutation_lock(authority):
                    current = store._read_locked(authority).encode()
                    if hashlib.sha256(current).hexdigest() != pending.expected_storage_hash:
                        raise ValueError("artifact event references superseded bytes")
                    append_event_once(pending.event, events_dir=events_dir)
                    complete_event(authority, pending, root=storage_root)
            delivered += 1
        except ValueError:
            quarantine_record(path)
        # fmt: off -- keep Python 3.11-compatible multi-exception syntax.
        except (OSError, RuntimeError, UnsafeArtifactState):
            # fmt: on
            # A transient persistence failure keeps the exact envelope pending.
            break
    pending_count = len(list(directory.glob("*.json")))
    return ArtifactEventReconcileResult(
        attempted=attempted,
        delivered=delivered,
        pending=pending_count,
        quarantined=quarantined,
    )
