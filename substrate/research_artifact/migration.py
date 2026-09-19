"""Restartable operator-only migration from legacy global ResearchArtifact files."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from .authority import OPERATOR_ACCOUNT_ID, ArtifactAuthority
from .import_notes import parse_body_from_html
from .observability import record_counter
from .storage import (
    FilesystemArtifactStore,
    UnsafeArtifactState,
    _atomic_write,
    _private_dir,
    _read_regular,
)

JOURNAL_VERSION = 1
TOMBSTONE_RETENTION_DAYS = 90
MigrationPhase = str


class MigrationRefused(RuntimeError):
    pass


class CorruptMigrationJournal(MigrationRefused):
    pass


@dataclass(frozen=True)
class Inventory:
    total: int = 0
    valid: int = 0
    corrupt: int = 0
    symlinked: int = 0
    multi_link: int = 0
    oversized: int = 0
    composed: int = 0
    excluded: int = 0
    v1: int = 0
    v2: int = 0
    orphan_sidecar: int = 0


@dataclass(frozen=True)
class MigrationReceipt:
    verdict: str
    account_digest: str
    investigation_digest: str
    source_digest: str
    content_hash: str
    phases: tuple[str, ...]
    tombstone_retention_days: int = TOMBSTONE_RETENTION_DAYS


@dataclass(frozen=True)
class InventoryEntry:
    source_digest: str
    disposition: str


@dataclass(frozen=True)
class InventoryReport:
    inventory: Inventory
    entries: tuple[InventoryEntry, ...]


@dataclass(frozen=True)
class ShadowResolution:
    scoped_exists: bool
    legacy_exists: bool
    hashes_match: bool | None
    enforcement_ready: bool


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_regular_with_identity(path: Path) -> tuple[bytes, os.stat_result]:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise UnsafeArtifactState("legacy source is unsafe") from exc
    try:
        identity = os.fstat(fd)
        if not stat.S_ISREG(identity.st_mode) or identity.st_nlink != 1:
            raise UnsafeArtifactState("legacy source is unsafe")
        chunks: list[bytes] = []
        while chunk := os.read(fd, 1024 * 1024):
            chunks.append(chunk)
        return b"".join(chunks), identity
    finally:
        os.close(fd)


def _entry_checksum(entry: dict[str, object]) -> str:
    unsigned = {key: value for key, value in entry.items() if key != "checksum"}
    raw = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    return _sha(raw)


def _load_journal(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    try:
        raw = _read_regular(path)
    except UnsafeArtifactState as exc:
        raise CorruptMigrationJournal("migration journal storage is unsafe") from exc
    if raw and not raw.endswith(b"\n"):
        raise CorruptMigrationJournal("migration journal is truncated")
    rows: list[dict[str, object]] = []
    previous = "0" * 64
    for sequence, line in enumerate(raw.splitlines(), start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CorruptMigrationJournal("migration journal contains invalid JSON") from exc
        if not isinstance(row, dict):
            raise CorruptMigrationJournal("migration journal row is not an object")
        if row.get("version") != JOURNAL_VERSION or row.get("sequence") != sequence:
            raise CorruptMigrationJournal("migration journal sequence/version mismatch")
        if row.get("previous_checksum") != previous:
            raise CorruptMigrationJournal("migration journal chain mismatch")
        checksum = row.get("checksum")
        if not isinstance(checksum, str) or checksum != _entry_checksum(row):
            raise CorruptMigrationJournal("migration journal checksum mismatch")
        previous = checksum
        rows.append(row)
    _validate_phase_order(rows)
    return rows


_ATTEMPT_PHASES = (
    "locked",
    "published_verified",
    "receipt_prepared",
    "tombstoned",
    "receipt_written",
)


def _validate_phase_order(rows: list[dict[str, object]]) -> None:
    expected = 0
    canonical_facts = rows[0].get("facts") if rows else None
    for row in rows:
        if row.get("facts") != canonical_facts:
            raise CorruptMigrationJournal("migration journal facts mismatch")
        phase = row.get("phase")
        if phase == "locked":
            expected = 1
            continue
        if expected == 0 or expected >= len(_ATTEMPT_PHASES):
            raise CorruptMigrationJournal("migration journal phase has no active attempt")
        if phase != _ATTEMPT_PHASES[expected]:
            raise CorruptMigrationJournal("migration journal phase order mismatch")
        expected += 1


def _append_journal(path: Path, phase: MigrationPhase, facts: dict[str, str]) -> None:
    rows = _load_journal(path)
    row: dict[str, object] = {
        "version": JOURNAL_VERSION,
        "sequence": len(rows) + 1,
        "previous_checksum": str(rows[-1]["checksum"]) if rows else "0" * 64,
        "phase": phase,
        "recorded_at": _now(),
        "facts": facts,
    }
    row["checksum"] = _entry_checksum(row)
    existing = _read_regular(path) if path.exists() else b""
    encoded = json.dumps(row, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    _atomic_write(path.parent, path, existing + encoded)


@contextmanager
def _migration_lock(root: Path, *, timeout_seconds: float = 10.0) -> Iterator[None]:
    lock_dir = root / ".migration"
    _private_dir(root, lock_dir)
    lock_path = lock_dir / "migration.lock"
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise MigrationRefused("migration lock is unsafe") from exc
    with os.fdopen(fd, "a+b") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise MigrationRefused("migration lock is unsafe")
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise MigrationRefused("migration lock lease timed out") from None
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def legacy_inventory(root: Path, *, max_bytes: int = 64 * 1024 * 1024) -> Inventory:
    counts = {field: 0 for field in Inventory.__dataclass_fields__}
    for path in sorted(root.glob("*.html")):
        counts["total"] += 1
        if path.name.startswith("compose-"):
            counts["composed"] += 1
            counts["excluded"] += 1
            continue
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            counts["symlinked"] += 1
            continue
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            counts["multi_link"] += 1
            continue
        if info.st_size > max_bytes:
            counts["oversized"] += 1
            continue
        try:
            body = parse_body_from_html(_read_regular(path).decode("utf-8"))
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
            counts["corrupt"] += 1
        else:
            counts["valid"] += 1
            counts[f"v{body.schema_version}"] += 1
    for sidecar in root.glob("*.meta.json"):
        if not sidecar.with_suffix("").with_suffix(".html").exists():
            counts["orphan_sidecar"] += 1
    return Inventory(**counts)


def legacy_inventory_report(
    root: Path, *, max_bytes: int = 64 * 1024 * 1024
) -> InventoryReport:
    """Deterministic, redacted dry-run receipt with one disposition per source."""
    entries: list[InventoryEntry] = []
    for path in sorted(root.glob("*.html")):
        disposition = "corrupt"
        try:
            info = path.lstat()
            if path.name.startswith("compose-"):
                disposition = "excluded_composed"
            elif stat.S_ISLNK(info.st_mode):
                disposition = "quarantine_symlink"
            elif not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                disposition = "quarantine_multi_link"
            elif info.st_size > max_bytes:
                disposition = "quarantine_oversized"
            else:
                body = parse_body_from_html(_read_regular(path).decode("utf-8"))
                disposition = f"migrate_v{body.schema_version}"
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError, UnsafeArtifactState):
            disposition = "quarantine_corrupt"
        entries.append(InventoryEntry(_sha(path.name.encode()), disposition))
    for sidecar in sorted(root.glob("*.meta.json")):
        if not sidecar.with_suffix("").with_suffix(".html").exists():
            entries.append(InventoryEntry(_sha(sidecar.name.encode()), "quarantine_orphan_sidecar"))
    return InventoryReport(legacy_inventory(root, max_bytes=max_bytes), tuple(entries))


def shadow_resolution(
    authority: ArtifactAuthority, *, root: Path, legacy_source: Path
) -> ShadowResolution:
    """Compare metadata only; never return or serve legacy bytes."""
    if authority.account_id != OPERATOR_ACCOUNT_ID:
        record_counter(root, "artifact_resolution_total", mode="denied")
        return ShadowResolution(False, False, None, False)
    store = FilesystemArtifactStore(root)
    scoped_exists = store.exists(authority)
    legacy_exists = legacy_source.parent.resolve() == root.resolve() and legacy_source.is_file()
    hashes_match: bool | None = None
    if scoped_exists and legacy_exists:
        scoped_hash = _sha(store.read(authority).encode())
        legacy_hash = _sha(_read_regular(legacy_source))
        hashes_match = scoped_hash == legacy_hash
    result = ShadowResolution(
        scoped_exists=scoped_exists,
        legacy_exists=legacy_exists,
        hashes_match=hashes_match,
        enforcement_ready=scoped_exists and (not legacy_exists or hashes_match is True),
    )
    record_counter(
        root,
        "artifact_resolution_total",
        mode="scoped" if result.enforcement_ready else "legacy_shadow",
    )
    return result


def _quarantine(root: Path, source: Path, reason: str) -> None:
    quarantine = root / ".migration" / "quarantine"
    _private_dir(root, quarantine)
    marker = quarantine / f"{_sha(source.name.encode())}.{reason}.json"
    _atomic_write(
        root,
        marker,
        json.dumps(
            {"source_digest": _sha(source.name.encode()), "reason": reason},
            sort_keys=True,
            separators=(",", ":"),
        ).encode(),
    )
    record_counter(root, "artifact_quarantine_total", reason=reason)


def migrate_legacy_artifact(
    source: Path,
    *,
    account_id: str,
    approved: bool,
    root: Path,
    crash_after: Callable[[str], None] | None = None,
) -> MigrationReceipt:
    """Migrate one legacy file; retries resume from durable scoped state."""
    if account_id != OPERATOR_ACCOUNT_ID:
        raise MigrationRefused("legacy artifacts may migrate only to the canonical operator")
    if not approved:
        raise MigrationRefused("migration apply requires explicit operator approval")
    source = source.expanduser().absolute()
    if source.parent.resolve() != root.resolve() or source.suffix != ".html":
        raise MigrationRefused("legacy source must be a root-level artifact HTML file")
    source_digest = _sha(source.name.encode())
    tombstone_dir = root / ".migration" / "tombstones"
    tombstone = tombstone_dir / f"{source_digest}.html"
    phases: list[str] = []

    def checkpoint(phase: str) -> None:
        phases.append(phase)
        record_counter(root, "artifact_migration_total", phase=phase, verdict="ok")
        if crash_after is not None:
            crash_after(phase)

    with _migration_lock(root):
        readable_source = source if source.exists() or source.is_symlink() else tombstone
        try:
            raw, source_identity = _read_regular_with_identity(readable_source)
            body = parse_body_from_html(raw.decode("utf-8"))
        except Exception as exc:
            _quarantine(root, source, "unsafe_or_corrupt")
            raise MigrationRefused("legacy artifact quarantined") from exc

        authority = ArtifactAuthority(account_id, body.investigation_id)
        expected_legacy_stem = body.investigation_id.replace("/", "_")
        if source.stem != expected_legacy_stem:
            _quarantine(root, source, "filename_identity_conflict")
            raise MigrationRefused("legacy filename and embedded identity conflict")
        content_hash = _sha(raw)
        journal = root / ".migration" / "journals" / f"{authority.investigation_digest}.jsonl"
        _private_dir(root, journal.parent)
        try:
            rows = _load_journal(journal)
        except CorruptMigrationJournal:
            _quarantine(root, source, "corrupt_journal")
            raise
        facts = {
            "account_digest": authority.account_digest,
            "investigation_digest": authority.investigation_digest,
            "source_digest": source_digest,
            "content_hash": content_hash,
        }
        if rows:
            first_facts = rows[0].get("facts")
            if first_facts != facts:
                _quarantine(root, source, "identity_conflict")
                raise MigrationRefused("migration journal identity conflict")

        _append_journal(journal, "locked", facts)
        checkpoint("locked")
        store = FilesystemArtifactStore(root)
        if store.exists(authority):
            if store.read(authority).encode() != raw:
                _quarantine(root, source, "scoped_content_conflict")
                raise MigrationRefused("scoped artifact conflicts with legacy content")
        else:
            store.write(authority, raw.decode("utf-8"), migrated_at=_now())
        _append_journal(journal, "published_verified", facts)
        checkpoint("published_verified")

        receipt = MigrationReceipt(
            verdict="prepared",
            account_digest=authority.account_digest,
            investigation_digest=authority.investigation_digest,
            source_digest=source_digest,
            content_hash=content_hash,
            phases=tuple((*phases, "receipt_prepared")),
        )
        receipt_path = root / ".migration" / "receipts" / f"{source_digest}.json"
        _atomic_write(
            root,
            receipt_path,
            json.dumps(asdict(receipt), sort_keys=True, separators=(",", ":")).encode(),
        )
        _append_journal(journal, "receipt_prepared", facts)
        checkpoint("receipt_prepared")

        _private_dir(root, tombstone_dir)
        if source.exists():
            source_dir_fd = os.open(source.parent, os.O_RDONLY)
            tombstone_dir_fd = os.open(tombstone_dir, os.O_RDONLY)
            current_identity = os.stat(
                source.name, dir_fd=source_dir_fd, follow_symlinks=False
            )
            if (current_identity.st_dev, current_identity.st_ino) != (
                source_identity.st_dev,
                source_identity.st_ino,
            ):
                os.close(source_dir_fd)
                os.close(tombstone_dir_fd)
                raise MigrationRefused("legacy source changed during migration")
            if tombstone.exists() or tombstone.is_symlink():
                os.close(source_dir_fd)
                os.close(tombstone_dir_fd)
                raise MigrationRefused("legacy tombstone unexpectedly exists")
            try:
                os.rename(
                    source.name,
                    tombstone.name,
                    src_dir_fd=source_dir_fd,
                    dst_dir_fd=tombstone_dir_fd,
                )
                moved_identity = os.stat(
                    tombstone.name, dir_fd=tombstone_dir_fd, follow_symlinks=False
                )
            finally:
                os.close(source_dir_fd)
                os.close(tombstone_dir_fd)
            if (moved_identity.st_dev, moved_identity.st_ino) != (
                source_identity.st_dev,
                source_identity.st_ino,
            ):
                raise MigrationRefused("legacy source changed during tombstoning")
            if _sha(_read_regular(tombstone)) != content_hash:
                raise MigrationRefused("legacy tombstone content does not match receipt")
            os.chmod(tombstone, 0o600)
            for directory in (source.parent, tombstone_dir):
                directory_fd = os.open(directory, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        elif not tombstone.exists():
            raise MigrationRefused("legacy source and tombstone are both missing")
        elif _sha(_read_regular(tombstone)) != content_hash:
            raise MigrationRefused("legacy tombstone content does not match receipt")
        _append_journal(journal, "tombstoned", facts)
        checkpoint("tombstoned")

        receipt = MigrationReceipt(
            verdict="migrated",
            account_digest=authority.account_digest,
            investigation_digest=authority.investigation_digest,
            source_digest=source_digest,
            content_hash=content_hash,
            phases=tuple(phases),
        )
        _atomic_write(
            root,
            receipt_path,
            json.dumps(asdict(receipt), sort_keys=True, separators=(",", ":")).encode(),
        )
        _append_journal(journal, "receipt_written", facts)
        checkpoint("receipt_written")
        return receipt
