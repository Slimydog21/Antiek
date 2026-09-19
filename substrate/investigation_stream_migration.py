"""Crash-safe building blocks for explicit legacy/composite stream migration."""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import hmac
import json
import os
import secrets
import stat
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from substrate.investigation_streams import (
    STREAM_LAYOUT_VERSION,
    StreamStorageState,
    _atomic_create_at,
    _authority_root_fd,
    _canonical,
    _directory_fd,
    _identity_record,
    _index_record,
    _legacy_lease_state_at,
    _operation_lock,
    _parse_exact,
    _read_at,
    _relative_paths,
    _state_record,
    _verify_key_anchor,
    resolve_investigation_stream,
)
from substrate.investigation_tenancy import (
    InvestigationAuthority,
    InvestigationOwnershipConflict,
    _registry_lock,
    _transition_legacy_lease_storage_state_unlocked,
    legacy_lease_storage_state,
)
from substrate.schemas.events import Event

Checkpoint = Callable[[str], None]


class MigrationVerificationError(RuntimeError):
    """Durable destination does not equal the locked canonical source."""


@dataclass(frozen=True)
class MigrationLimits:
    max_rows: int = 1_000_000
    max_file_bytes: int = 512 * 1024 * 1024
    max_total_bytes: int = 1024 * 1024 * 1024

    def __post_init__(self) -> None:
        if min(self.max_rows, self.max_file_bytes, self.max_total_bytes) <= 0:
            raise ValueError("migration limits must be positive")
        if self.max_file_bytes > self.max_total_bytes:
            raise ValueError("file byte limit cannot exceed total byte limit")


@dataclass(frozen=True)
class CanonicalStreamSnapshot:
    prefix_rows: tuple[dict[str, Any], ...]
    tail_rows: tuple[dict[str, Any], ...]
    rows: tuple[dict[str, Any], ...]
    content_digest: str
    source_bytes: int


@dataclass(frozen=True)
class MigrationReceipt:
    source_digest: str
    stream_digest: str
    transition: str
    disposition: str
    row_count: int
    source_bytes: int
    destination_bytes: int
    content_digest: str

    def as_dict(self) -> dict[str, object]:
        return {
            "source_digest": self.source_digest,
            "stream_digest": self.stream_digest,
            "transition": self.transition,
            "disposition": self.disposition,
            "row_count": self.row_count,
            "source_bytes": self.source_bytes,
            "destination_bytes": self.destination_bytes,
            "content_digest": self.content_digest,
        }


@dataclass(frozen=True)
class _LockedMigration:
    root_fd: int
    tenancy_fd: int
    stream_fd: int
    legacy_jsonl_name: str
    legacy_parquet_name: str
    composite_jsonl_name: str
    composite_parquet_name: str


_JOURNAL_VERSION = 1


def _checkpoint(callback: Checkpoint | None, name: str) -> None:
    if callback is not None:
        callback(name)


def _receipt_digest(authority: InvestigationAuthority, domain: bytes) -> str:
    return hmac.new(
        bytes.fromhex(authority.stream_key),
        b"antiek-w3d\x00" + domain,
        hashlib.sha256,
    ).hexdigest()


def _journal_identity(authority: InvestigationAuthority) -> dict[str, object]:
    return {
        "version": _JOURNAL_VERSION,
        "key_id": authority.key_id,
        "account_digest": authority.account_digest,
        "investigation_digest": authority.investigation_digest,
        "stream_key": authority.stream_key,
    }


def _journal_fd(authority: InvestigationAuthority, tenancy_fd: int) -> int:
    del authority
    return _directory_fd(tenancy_fd, ("stream-migrations",), create=True)


def _journal_name(authority: InvestigationAuthority, direction: str) -> str:
    direction_key = {
        "legacy_to_composite": "forward",
        "composite_to_legacy": "rollback",
    }.get(direction)
    if direction_key is None:
        raise ValueError("unsupported investigation migration direction")
    return f"{authority.stream_key}.{direction_key}.json"


def _load_or_create_journal(
    authority: InvestigationAuthority,
    locked: _LockedMigration,
    *,
    direction: str,
) -> dict[str, object]:
    directory_fd = _journal_fd(authority, locked.tenancy_fd)
    try:
        name = _journal_name(authority, direction)
        raw = _read_at(directory_fd, name)
        identity = _journal_identity(authority)
        if raw is None:
            record = {
                **identity,
                "direction": direction,
                "operation_digest": _receipt_digest(
                    authority, b"operation-" + secrets.token_bytes(32)
                ),
                "phase": "started",
            }
            _publish_bytes_at(
                directory_fd,
                name,
                _canonical(record),
                checkpoint=None,
                checkpoint_prefix="journal",
                operation_tag=str(record["operation_digest"]),
            )
            return record
        try:
            record = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvestigationOwnershipConflict(
                "investigation migration journal is invalid"
            ) from exc
        if (
            not isinstance(record, dict)
            or any(record.get(key) != value for key, value in identity.items())
            or record.get("direction") != direction
            or not isinstance(record.get("operation_digest"), str)
            or len(record["operation_digest"]) != 64
            or any(
                ch not in "0123456789abcdef"
                for ch in record["operation_digest"]
            )
            or record.get("phase")
            not in {
                "started",
                "snapshotted",
                "data_verified",
                "metadata_published",
                "quarantined",
                "flipped",
                "complete",
            }
        ):
            raise InvestigationOwnershipConflict(
                "investigation migration journal is invalid"
            )
        return record
    finally:
        os.close(directory_fd)


def _update_journal(
    authority: InvestigationAuthority,
    locked: _LockedMigration,
    record: dict[str, object],
    *,
    phase: str,
    snapshot: CanonicalStreamSnapshot | None = None,
    reason_code: str | None = None,
) -> None:
    updated = {**record, "phase": phase}
    if snapshot is not None:
        updated.update(
            {
                "row_count": len(snapshot.rows),
                "source_bytes": snapshot.source_bytes,
                "content_digest": snapshot.content_digest,
            }
        )
    if reason_code is not None:
        updated["reason_code"] = reason_code
    directory_fd = _journal_fd(authority, locked.tenancy_fd)
    try:
        _publish_bytes_at(
            directory_fd,
            _journal_name(authority, str(record["direction"])),
            _canonical(updated),
            checkpoint=None,
            checkpoint_prefix="journal",
            operation_tag=str(record["operation_digest"]),
        )
    finally:
        os.close(directory_fd)
    record.clear()
    record.update(updated)


def _open_lock_at(directory_fd: int, name: str) -> int:
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(name, flags, 0o600, dir_fd=directory_fd)
    except OSError as exc:
        raise RuntimeError("investigation migration lock is unsafe") from exc
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        os.close(fd)
        raise RuntimeError("investigation migration lock is unsafe")
    return fd


@contextmanager
def _migration_locks(
    authority: InvestigationAuthority, *, expected_state: StreamStorageState
) -> Iterator[_LockedMigration]:
    """Pin namespaces and exclude resolver/append/seal in their established order."""
    with ExitStack() as stack:
        root_fd = _authority_root_fd(authority)
        stack.callback(os.close, root_fd)
        tenancy_fd = _directory_fd(root_fd, (".tenancy",), create=False)
        stack.callback(os.close, tenancy_fd)
        paths = _relative_paths(authority)
        with _registry_lock(authority.root):
            lease_state = _legacy_lease_state_at(authority, tenancy_fd)
            if lease_state != expected_state.value:
                raise InvestigationOwnershipConflict(
                    "investigation storage state changed during migration"
                )
            with _operation_lock(tenancy_fd, exclusive=True):
                # Only a verified lease owner may initialize W3 control/data paths.
                # W2-only roots acquire their immutable key-generation anchor here.
                _verify_key_anchor(authority, tenancy_fd, create=True)
                stream_fd = _directory_fd(root_fd, paths["stream_dir"], create=True)
                stack.callback(os.close, stream_fd)
                lock_specs = sorted(
                    (
                        ("composite", stream_fd, f"{authority.stream_key}.jsonl.lock"),
                        ("legacy", root_fd, f"{authority.investigation_id}.jsonl.lock"),
                    ),
                    key=lambda item: item[0],
                )
                lock_fds: list[int] = []
                try:
                    for _label, directory_fd, name in lock_specs:
                        fd = _open_lock_at(directory_fd, name)
                        lock_fds.append(fd)
                        fcntl.flock(fd, fcntl.LOCK_EX)
                    yield _LockedMigration(
                        root_fd=root_fd,
                        tenancy_fd=tenancy_fd,
                        stream_fd=stream_fd,
                        legacy_jsonl_name=f"{authority.investigation_id}.jsonl",
                        legacy_parquet_name=f"{authority.investigation_id}.parquet",
                        composite_jsonl_name=f"{authority.stream_key}.jsonl",
                        composite_parquet_name=f"{authority.stream_key}.parquet",
                    )
                finally:
                    for fd in reversed(lock_fds):
                        with contextlib.suppress(OSError):
                            fcntl.flock(fd, fcntl.LOCK_UN)
                        os.close(fd)


def _read_regular_bytes_at(
    directory_fd: int, name: str, *, limit: int
) -> bytes | None:
    try:
        fd = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=directory_fd,
        )
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise RuntimeError("investigation migration source is unsafe") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise RuntimeError("investigation migration source is unsafe")
        if info.st_size > limit:
            raise ValueError("investigation migration file exceeds byte limit")
        chunks: list[bytes] = []
        total = 0
        while chunk := os.read(fd, min(64 * 1024, limit + 1)):
            total += len(chunk)
            if total > limit:
                raise ValueError("investigation migration file exceeds byte limit")
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def _canonical_event(authority: InvestigationAuthority, row: object) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise ValueError("event stream contains a non-object row")
    try:
        event = Event.model_validate(row)
    except (TypeError, ValueError) as exc:
        raise ValueError("event stream contains an invalid event") from exc
    if not event.event_id:
        raise ValueError("event stream contains an empty event id")
    if event.investigation_id != authority.investigation_id:
        raise ValueError("event stream crosses authorized investigation")
    return event.model_dump(mode="json")


def _deduplicate_ordered(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    result: list[dict[str, Any]] = []
    seen: dict[str, bytes] = {}
    for row in rows:
        event_id = str(row["event_id"])
        canonical = _canonical(row)
        previous = seen.get(event_id)
        if previous is not None:
            if previous != canonical:
                raise ValueError(f"event id collision: {event_id}")
            continue
        seen[event_id] = canonical
        result.append(row)
    return tuple(result)


def _parse_jsonl(
    authority: InvestigationAuthority, raw: bytes | None
) -> tuple[dict[str, Any], ...]:
    if raw is None:
        return ()
    if raw and not raw.endswith(b"\n"):
        raise ValueError("event stream contains a truncated JSON line")
    rows: list[dict[str, Any]] = []
    for line in raw.splitlines():
        if not line:
            continue
        try:
            decoded = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("event stream contains malformed JSON") from exc
        rows.append(_canonical_event(authority, decoded))
    return tuple(rows)


def _parse_parquet(
    authority: InvestigationAuthority, raw: bytes | None
) -> tuple[dict[str, Any], ...]:
    if raw is None:
        return ()
    try:
        import pyarrow as pa
        import pyarrow.parquet as parquet

        rows = parquet.read_table(pa.BufferReader(raw)).to_pylist()
    except ImportError as exc:  # pragma: no cover - dependency is required in deployment
        raise RuntimeError("pyarrow is required for sealed stream migration") from exc
    except Exception as exc:
        raise ValueError("event stream contains malformed Parquet") from exc
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("payload"), str):
            with contextlib.suppress(TypeError, json.JSONDecodeError):
                row = {**row, "payload": json.loads(row["payload"])}
        normalized.append(_canonical_event(authority, row))
    return tuple(normalized)


def _snapshot(
    authority: InvestigationAuthority,
    directory_fd: int,
    *,
    jsonl_name: str,
    parquet_name: str,
    limits: MigrationLimits,
) -> CanonicalStreamSnapshot:
    parquet_raw = _read_regular_bytes_at(
        directory_fd, parquet_name, limit=limits.max_file_bytes
    )
    jsonl_raw = _read_regular_bytes_at(
        directory_fd, jsonl_name, limit=limits.max_file_bytes
    )
    if parquet_raw is None and jsonl_raw is None:
        raise ValueError("investigation migration source is empty")
    source_bytes = len(parquet_raw or b"") + len(jsonl_raw or b"")
    if source_bytes > limits.max_total_bytes:
        raise ValueError("investigation migration exceeds total byte limit")
    prefix_rows = _deduplicate_ordered(list(_parse_parquet(authority, parquet_raw)))
    parsed_tail = _deduplicate_ordered(list(_parse_jsonl(authority, jsonl_raw)))
    # Validate cross-representation collisions over the full ordered union,
    # then publish an actually deduplicated tail rather than merely reporting one.
    rows = _deduplicate_ordered([*prefix_rows, *parsed_tail])
    prefix_ids = {str(row["event_id"]) for row in prefix_rows}
    tail_rows = tuple(
        row for row in parsed_tail if str(row["event_id"]) not in prefix_ids
    )
    if not rows:
        raise ValueError("investigation migration source has no events")
    if len(rows) > limits.max_rows:
        raise ValueError("investigation migration exceeds row limit")
    content = b"\n".join(_canonical(row) for row in rows)
    return CanonicalStreamSnapshot(
        prefix_rows=prefix_rows,
        tail_rows=tail_rows,
        rows=rows,
        content_digest=hashlib.sha256(content).hexdigest(),
        source_bytes=source_bytes,
    )


def _jsonl_bytes(rows: tuple[dict[str, Any], ...]) -> bytes:
    if not rows:
        return b""
    return b"".join(_canonical(row) + b"\n" for row in rows)


def _parquet_bytes(rows: tuple[dict[str, Any], ...]) -> bytes:
    if not rows:
        return b""
    import pyarrow as pa
    import pyarrow.parquet as parquet

    serialized: list[dict[str, Any]] = []
    for row in rows:
        copied = dict(row)
        if isinstance(copied.get("payload"), (dict, list)):
            copied["payload"] = json.dumps(
                copied["payload"], sort_keys=True, separators=(",", ":")
            )
        serialized.append(copied)
    sink = pa.BufferOutputStream()
    parquet.write_table(pa.Table.from_pylist(serialized), sink, compression="zstd")
    return sink.getvalue().to_pybytes()


def _publish_bytes_at(
    directory_fd: int,
    name: str,
    payload: bytes | None,
    *,
    checkpoint: Checkpoint | None,
    checkpoint_prefix: str,
    operation_tag: str | None = None,
) -> None:
    if payload is None:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(name, dir_fd=directory_fd)
            os.fsync(directory_fd)
        return
    if operation_tag is not None:
        if len(operation_tag) != 64 or any(
            ch not in "0123456789abcdef" for ch in operation_tag
        ):
            raise RuntimeError("investigation migration operation tag is invalid")
        owned_prefix = f".{name}.w3d-{operation_tag}-"
        changed = False
        for entry in os.listdir(directory_fd):
            if not entry.startswith(owned_prefix) or not entry.endswith(".tmp"):
                continue
            info = os.stat(entry, dir_fd=directory_fd, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise RuntimeError("investigation migration temporary is unsafe")
            os.unlink(entry, dir_fd=directory_fd)
            changed = True
        if changed:
            os.fsync(directory_fd)
    tag = operation_tag or secrets.token_hex(32)
    temporary = f".{name}.w3d-{tag}-{secrets.token_hex(12)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(temporary, flags, 0o600, dir_fd=directory_fd)
    try:
        written = 0
        while written < len(payload):
            written += os.write(fd, payload[written:])
        os.fsync(fd)
        _checkpoint(checkpoint, f"{checkpoint_prefix}_temp_fsynced")
    finally:
        os.close(fd)
    try:
        reread = _read_regular_bytes_at(
            directory_fd,
            temporary,
            limit=max(len(payload), 1),
        )
        if reread != payload:
            raise MigrationVerificationError(
                "investigation migration temporary verification failed"
            )
        _checkpoint(checkpoint, f"{checkpoint_prefix}_temp_verified")
        os.replace(
            temporary,
            name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        os.fsync(directory_fd)
        _checkpoint(checkpoint, f"{checkpoint_prefix}_published")
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=directory_fd)


def _publish_composite_metadata(
    authority: InvestigationAuthority, locked: _LockedMigration
) -> None:
    paths = _relative_paths(authority)
    allocation_fd = _directory_fd(
        locked.tenancy_fd, paths["allocation_dir"][1:], create=True
    )
    state_fd = _directory_fd(locked.tenancy_fd, paths["state_dir"][1:], create=True)
    index_fd = _directory_fd(locked.tenancy_fd, paths["index_dir"][1:], create=True)
    try:
        name = f"{authority.stream_key}.json"
        records = (
            (allocation_fd, _identity_record(authority), "allocation"),
            (state_fd, _state_record(authority), "state"),
            (index_fd, _index_record(authority), "index"),
        )
        for directory_fd, record, label in records:
            if not _atomic_create_at(directory_fd, name, _canonical(record)):
                _parse_exact(
                    _read_at(directory_fd, name),
                    record,
                    f"investigation stream {label} is invalid",
                )
    finally:
        os.close(index_fd)
        os.close(state_fd)
        os.close(allocation_fd)


def _archive_legacy_data(
    authority: InvestigationAuthority,
    locked: _LockedMigration,
    *,
    checkpoint: Checkpoint | None,
) -> None:
    """Move post-flip legacy bytes out of the globally scanned namespace."""
    backup_fd = _directory_fd(
        locked.tenancy_fd,
        (
            "legacy-stream-backups",
            authority.investigation_digest[:2],
            authority.investigation_digest,
        ),
        create=True,
    )
    try:
        for suffix, source_name in (
            ("parquet", locked.legacy_parquet_name),
            ("jsonl", locked.legacy_jsonl_name),
        ):
            try:
                info = os.stat(
                    source_name,
                    dir_fd=locked.root_fd,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise RuntimeError("investigation legacy backup source is unsafe")
            os.replace(
                source_name,
                f"{authority.investigation_digest}.{suffix}",
                src_dir_fd=locked.root_fd,
                dst_dir_fd=backup_fd,
            )
            os.fsync(backup_fd)
            os.fsync(locked.root_fd)
            _checkpoint(checkpoint, f"legacy_{suffix}_archived")
    finally:
        os.close(backup_fd)
    _checkpoint(checkpoint, "legacy_archived")


def _assert_snapshot_equal(
    expected: CanonicalStreamSnapshot, actual: CanonicalStreamSnapshot
) -> None:
    if actual.rows != expected.rows or actual.content_digest != expected.content_digest:
        raise MigrationVerificationError(
            "investigation migration canonical verification failed"
        )


def migrate_legacy_to_composite(
    authority: InvestigationAuthority,
    *,
    limits: MigrationLimits | None = None,
    checkpoint: Checkpoint | None = None,
) -> MigrationReceipt:
    """Copy, verify, publish, then flip one leased legacy stream."""
    limits = limits or MigrationLimits()
    with _migration_locks(
        authority, expected_state=StreamStorageState.LEGACY
    ) as locked:
        journal = _load_or_create_journal(
            authority,
            locked,
            direction="legacy_to_composite",
        )
        try:
            source = _snapshot(
                authority,
                locked.root_fd,
                jsonl_name=locked.legacy_jsonl_name,
                parquet_name=locked.legacy_parquet_name,
                limits=limits,
            )
        except ValueError:
            _update_journal(
                authority,
                locked,
                journal,
                phase="quarantined",
                reason_code="source_validation_failed",
            )
            raise
        _update_journal(
            authority,
            locked,
            journal,
            phase="snapshotted",
            snapshot=source,
        )
        _checkpoint(checkpoint, "source_snapshotted")
        parquet_payload = (
            _parquet_bytes(source.prefix_rows) if source.prefix_rows else None
        )
        jsonl_payload = _jsonl_bytes(source.tail_rows) if source.tail_rows else None
        _publish_bytes_at(
            locked.stream_fd,
            locked.composite_parquet_name,
            parquet_payload,
            checkpoint=checkpoint,
            checkpoint_prefix="parquet",
            operation_tag=str(journal["operation_digest"]),
        )
        _publish_bytes_at(
            locked.stream_fd,
            locked.composite_jsonl_name,
            jsonl_payload,
            checkpoint=checkpoint,
            checkpoint_prefix="jsonl",
            operation_tag=str(journal["operation_digest"]),
        )
        destination = _snapshot(
            authority,
            locked.stream_fd,
            jsonl_name=locked.composite_jsonl_name,
            parquet_name=locked.composite_parquet_name,
            limits=limits,
        )
        _assert_snapshot_equal(source, destination)
        _update_journal(
            authority,
            locked,
            journal,
            phase="data_verified",
            snapshot=source,
        )
        _checkpoint(checkpoint, "data_verified")
        _publish_composite_metadata(authority, locked)
        _update_journal(
            authority,
            locked,
            journal,
            phase="metadata_published",
            snapshot=source,
        )
        _checkpoint(checkpoint, "metadata_published")
        if _legacy_lease_state_at(authority, locked.tenancy_fd) != "legacy":
            raise InvestigationOwnershipConflict(
                "investigation storage state changed during migration"
            )
        _transition_legacy_lease_storage_state_unlocked(
            authority,
            expected="legacy",
            desired="composite",
        )
        _update_journal(
            authority,
            locked,
            journal,
            phase="flipped",
            snapshot=source,
        )
        _checkpoint(checkpoint, "lease_flipped")
        _archive_legacy_data(authority, locked, checkpoint=checkpoint)
        _update_journal(
            authority,
            locked,
            journal,
            phase="complete",
            snapshot=source,
        )
    resolved = resolve_investigation_stream(authority)
    if resolved.state is not StreamStorageState.COMPOSITE:
        raise RuntimeError("investigation migration cutover verification failed")
    destination_bytes = len(parquet_payload or b"") + len(jsonl_payload or b"")
    return MigrationReceipt(
        source_digest=_receipt_digest(authority, b"legacy-source"),
        stream_digest=_receipt_digest(authority, b"composite-stream"),
        transition="legacy_to_composite",
        disposition="migrated",
        row_count=len(source.rows),
        source_bytes=source.source_bytes,
        destination_bytes=destination_bytes,
        content_digest=source.content_digest,
    )


def rollback_composite_to_legacy(
    authority: InvestigationAuthority,
    *,
    limits: MigrationLimits | None = None,
    checkpoint: Checkpoint | None = None,
) -> MigrationReceipt:
    """Refresh legacy from complete composite state, verify, then flip last."""
    limits = limits or MigrationLimits()
    with _migration_locks(
        authority, expected_state=StreamStorageState.COMPOSITE
    ) as locked:
        journal = _load_or_create_journal(
            authority,
            locked,
            direction="composite_to_legacy",
        )
        source = _snapshot(
            authority,
            locked.stream_fd,
            jsonl_name=locked.composite_jsonl_name,
            parquet_name=locked.composite_parquet_name,
            limits=limits,
        )
        _update_journal(
            authority,
            locked,
            journal,
            phase="snapshotted",
            snapshot=source,
        )
        _checkpoint(checkpoint, "rollback_source_snapshotted")
        parquet_payload = (
            _parquet_bytes(source.prefix_rows) if source.prefix_rows else None
        )
        jsonl_payload = _jsonl_bytes(source.tail_rows) if source.tail_rows else None
        _publish_bytes_at(
            locked.root_fd,
            locked.legacy_parquet_name,
            parquet_payload,
            checkpoint=checkpoint,
            checkpoint_prefix="rollback_parquet",
            operation_tag=str(journal["operation_digest"]),
        )
        _publish_bytes_at(
            locked.root_fd,
            locked.legacy_jsonl_name,
            jsonl_payload,
            checkpoint=checkpoint,
            checkpoint_prefix="rollback_jsonl",
            operation_tag=str(journal["operation_digest"]),
        )
        destination = _snapshot(
            authority,
            locked.root_fd,
            jsonl_name=locked.legacy_jsonl_name,
            parquet_name=locked.legacy_parquet_name,
            limits=limits,
        )
        _assert_snapshot_equal(source, destination)
        _update_journal(
            authority,
            locked,
            journal,
            phase="data_verified",
            snapshot=source,
        )
        _checkpoint(checkpoint, "rollback_data_verified")
        if _legacy_lease_state_at(authority, locked.tenancy_fd) != "composite":
            raise InvestigationOwnershipConflict(
                "investigation storage state changed during rollback"
            )
        _transition_legacy_lease_storage_state_unlocked(
            authority,
            expected="composite",
            desired="legacy",
        )
        _update_journal(
            authority,
            locked,
            journal,
            phase="flipped",
            snapshot=source,
        )
        _checkpoint(checkpoint, "rollback_lease_flipped")
        _update_journal(
            authority,
            locked,
            journal,
            phase="complete",
            snapshot=source,
        )
    resolved = resolve_investigation_stream(authority)
    if resolved.state is not StreamStorageState.LEGACY:
        raise RuntimeError("investigation rollback cutover verification failed")
    destination_bytes = len(parquet_payload or b"") + len(jsonl_payload or b"")
    return MigrationReceipt(
        source_digest=_receipt_digest(authority, b"composite-source"),
        stream_digest=_receipt_digest(authority, b"legacy-stream"),
        transition="composite_to_legacy",
        disposition="rolled_back",
        row_count=len(source.rows),
        source_bytes=source.source_bytes,
        destination_bytes=destination_bytes,
        content_digest=source.content_digest,
    )


def _verify_completed_direction(
    authority: InvestigationAuthority,
    *,
    state: StreamStorageState,
    direction: str,
    disposition: str,
    limits: MigrationLimits,
) -> MigrationReceipt:
    with _migration_locks(authority, expected_state=state) as locked:
        journal = _load_or_create_journal(
            authority,
            locked,
            direction=direction,
        )
        if state is StreamStorageState.COMPOSITE:
            directory_fd = locked.stream_fd
            jsonl_name = locked.composite_jsonl_name
            parquet_name = locked.composite_parquet_name
        else:
            directory_fd = locked.root_fd
            jsonl_name = locked.legacy_jsonl_name
            parquet_name = locked.legacy_parquet_name
        snapshot = _snapshot(
            authority,
            directory_fd,
            jsonl_name=jsonl_name,
            parquet_name=parquet_name,
            limits=limits,
        )
        if (
            direction == "legacy_to_composite"
            and state is StreamStorageState.COMPOSITE
        ):
            _archive_legacy_data(authority, locked, checkpoint=None)
        _update_journal(
            authority,
            locked,
            journal,
            phase="complete",
            snapshot=snapshot,
        )
    resolved = resolve_investigation_stream(authority)
    if resolved.state is not state:
        raise RuntimeError("investigation migration resume verification failed")
    return MigrationReceipt(
        source_digest=_receipt_digest(authority, f"{direction}-source".encode()),
        stream_digest=_receipt_digest(authority, f"{state.value}-stream".encode()),
        transition=direction,
        disposition=disposition,
        row_count=len(snapshot.rows),
        source_bytes=snapshot.source_bytes,
        destination_bytes=snapshot.source_bytes,
        content_digest=snapshot.content_digest,
    )


def resume_legacy_to_composite(
    authority: InvestigationAuthority,
    *,
    limits: MigrationLimits | None = None,
    checkpoint: Checkpoint | None = None,
) -> MigrationReceipt:
    """Resume forward copy from the durable lease, never from journal claims."""
    limits = limits or MigrationLimits()
    state = legacy_lease_storage_state(authority)
    if state == StreamStorageState.LEGACY.value:
        return migrate_legacy_to_composite(
            authority,
            limits=limits,
            checkpoint=checkpoint,
        )
    if state == StreamStorageState.COMPOSITE.value:
        return _verify_completed_direction(
            authority,
            state=StreamStorageState.COMPOSITE,
            direction="legacy_to_composite",
            disposition="resumed_after_flip",
            limits=limits,
        )
    raise InvestigationOwnershipConflict("investigation migration state is invalid")


def resume_composite_to_legacy(
    authority: InvestigationAuthority,
    *,
    limits: MigrationLimits | None = None,
    checkpoint: Checkpoint | None = None,
) -> MigrationReceipt:
    """Resume rollback from the durable lease and selected source authority."""
    limits = limits or MigrationLimits()
    state = legacy_lease_storage_state(authority)
    if state == StreamStorageState.COMPOSITE.value:
        return rollback_composite_to_legacy(
            authority,
            limits=limits,
            checkpoint=checkpoint,
        )
    if state == StreamStorageState.LEGACY.value:
        return _verify_completed_direction(
            authority,
            state=StreamStorageState.LEGACY,
            direction="composite_to_legacy",
            disposition="resumed_after_flip",
            limits=limits,
        )
    raise InvestigationOwnershipConflict("investigation migration state is invalid")


def composite_stream_path(authority: InvestigationAuthority) -> Path:
    """Test/operator helper returning the opaque stream directory only."""
    return authority.root / "streams" / f"v{STREAM_LAYOUT_VERSION}" / authority.stream_key[:2]
