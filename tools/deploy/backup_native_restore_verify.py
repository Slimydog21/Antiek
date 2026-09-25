"""Verify a closed native DuckDB archive against a source observation.

The caller must establish source authority and quiescence, freeze the archive
inode, and run this component under an external OS sandbox with resource limits.
This component cannot prove those conditions or verify an upload. DuckDB's
read-only and external-access settings are additional restrictions, not an OS
sandbox. Companion files are admitted and hash-bound but not interpreted.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from tools.deploy.backup_archive_admission import (
    AdmissionReport,
    AdmittedMember,
    ArchiveAdmissionError,
    admit_archive,
)
from tools.deploy.backup_content_digest import CONTENT_SCHEME
from tools.deploy.backup_restore_verify import (
    _DUCKDB_VERSION,
    ObservationLimits,
    RestoreLimits,
    RestoreRefused,
    SnapshotObservation,
    _bounded_name,
    _catalog_digest,
    observe_snapshot,
)

NATIVE_ARCHIVE_FORMAT = "antiek-native-duckdb-v1"
NATIVE_REPORT_SCHEME = "antiek-closed-native-archive-restore-v1"
_ROOT = re.compile(r"antiek-backup\.[A-Za-z0-9]{8}\Z")
_NATIVE_MEMBER = re.compile(r"antiek-backup\.[A-Za-z0-9]{8}/native/antiek\.duckdb\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_FORBIDDEN_COMPANION = re.compile(
    r"(?:\.parquet|\.duckdb(?:[.\-].*)?|\.db(?:[.\-].*)?|\.sqlite(?:[.\-].*)?|"
    r"\.wal|\-wal|\.lock|\.lck|\.tmp)\Z",
    re.IGNORECASE,
)
_READ_FLAGS = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC
_READ_CHUNK = 64 * 1024
_ADMISSION_ERRORS = (ArchiveAdmissionError, OSError)
_NATIVE_OPEN_ERRORS = (duckdb.Error, OSError, ValueError)
_DUCKDB_CONFIG: dict[str, str | bool | int | float | list[str]] = {
    "enable_external_access": "false",
    "autoload_known_extensions": "false",
    "autoinstall_known_extensions": "false",
    "allow_community_extensions": "false",
    "allow_unsigned_extensions": "false",
}


@dataclass(frozen=True)
class NativeRestoreReport:
    report_scheme: str
    archive_format: str
    archive_sha256: str
    archive_bytes: int
    native_member_path: str
    native_member_sha256: str
    native_member_bytes: int
    source_observation_sha256: str
    restored_observation_sha256: str
    source_counts: Mapping[str, int]
    restored_counts: Mapping[str, int]
    source_catalog_sha256: str
    restored_catalog_sha256: str
    source_content_sha256: Mapping[str, str]
    restored_content_sha256: Mapping[str, str]
    content_scheme: str
    duckdb_version: str

    def canonical_bytes(self) -> bytes:
        return json.dumps(vars(self), sort_keys=True, separators=(",", ":")).encode("ascii")

    @classmethod
    def from_canonical_bytes(cls, raw: bytes, *, limits: RestoreLimits) -> NativeRestoreReport:
        if not isinstance(raw, bytes) or len(raw) > limits.observation.report_bytes:
            raise RestoreRefused("REPORT_FORMAT")

        def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            value: dict[str, Any] = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError()
                value[key] = item
            return value

        try:
            value = json.loads(raw.decode("ascii"), object_pairs_hook=unique_pairs)
            if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
                raise ValueError()
            if (
                value["report_scheme"] != NATIVE_REPORT_SCHEME
                or value["archive_format"] != NATIVE_ARCHIVE_FORMAT
                or value["content_scheme"] != CONTENT_SCHEME
                or value["duckdb_version"] != _DUCKDB_VERSION
                or type(value["native_member_path"]) is not str
                or not _NATIVE_MEMBER.fullmatch(value["native_member_path"])
            ):
                raise ValueError()
            for field in (
                "archive_sha256",
                "native_member_sha256",
                "source_observation_sha256",
                "restored_observation_sha256",
                "source_catalog_sha256",
                "restored_catalog_sha256",
            ):
                if type(value[field]) is not str or not _SHA256.fullmatch(value[field]):
                    raise ValueError()
            if (
                type(value["archive_bytes"]) is not int
                or not 0 < value["archive_bytes"] <= limits.archive.compressed_bytes
                or type(value["native_member_bytes"]) is not int
                or not 0 < value["native_member_bytes"] <= limits.archive.member_bytes
                or value["native_member_bytes"] > limits.archive.expanded_bytes
            ):
                raise ValueError()
            for field in (
                "source_counts",
                "restored_counts",
                "source_content_sha256",
                "restored_content_sha256",
            ):
                entries = value[field]
                if type(entries) is not dict or len(entries) > limits.observation.tables:
                    raise ValueError()
                for name, item in entries.items():
                    _bounded_name(name, limits.observation)
                    if field.endswith("counts"):
                        if type(item) is not int or item < 0:
                            raise ValueError()
                    elif type(item) is not str or not _SHA256.fullmatch(item):
                        raise ValueError()
            if (
                value["source_observation_sha256"] != value["restored_observation_sha256"]
                or value["source_catalog_sha256"] != value["restored_catalog_sha256"]
                or value["source_counts"] != value["restored_counts"]
                or value["source_content_sha256"] != value["restored_content_sha256"]
                or set(value["source_counts"]) != set(value["source_content_sha256"])
            ):
                raise ValueError()
            report = cls(**value)
            if report.canonical_bytes() != raw:
                raise ValueError()
            return report
        except (ValueError, TypeError, UnicodeError, KeyError, RecursionError) as exc:
            raise RestoreRefused("REPORT_FORMAT") from exc


def _admitted_native(report: AdmissionReport, destination: Path) -> tuple[Path, AdmittedMember]:
    members = report.members
    roots = {member.path.split("/", 1)[0] for member in members}
    if len(roots) != 1:
        raise RestoreRefused("NATIVE_LAYOUT_INVALID")
    root = roots.pop()
    if not _ROOT.fullmatch(root):
        raise RestoreRefused("NATIVE_LAYOUT_INVALID")
    native_dir = f"{root}/native"
    native_name = f"{native_dir}/antiek.duckdb"
    directories = {member.path for member in members if member.sha256 is None}
    files = {member.path: member for member in members if member.sha256 is not None}
    if not {root, native_dir} <= directories or native_name not in files:
        raise RestoreRefused("NATIVE_LAYOUT_INVALID")
    companion_dirs = {f"{root}/research_events", f"{root}/knowledge_skills"}
    for path in directories:
        if path in {root, native_dir} or path in companion_dirs:
            continue
        if not any(path.startswith(f"{tree}/") for tree in companion_dirs):
            raise RestoreRefused("NATIVE_LAYOUT_INVALID")
        if any(_FORBIDDEN_COMPANION.search(part) for part in path.split("/")):
            raise RestoreRefused("NATIVE_LAYOUT_INVALID")
    for path in files:
        if path == native_name or path == f"{root}/source_manifest.json":
            continue
        if not any(path.startswith(f"{tree}/") for tree in companion_dirs):
            raise RestoreRefused("NATIVE_LAYOUT_INVALID")
        if any(_FORBIDDEN_COMPANION.search(part) for part in path.split("/")):
            raise RestoreRefused("NATIVE_LAYOUT_INVALID")
    return destination / native_name, files[native_name]


def _file_fingerprint(path: Path, byte_limit: int) -> tuple[int, int, int, str]:
    try:
        fd = os.open(path, _READ_FLAGS)
    except OSError:
        raise RestoreRefused("NATIVE_FILE_MISMATCH") from None
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= byte_limit:
            raise RestoreRefused("NATIVE_FILE_MISMATCH")
        digest = hashlib.sha256()
        size = 0
        while chunk := os.read(fd, _READ_CHUNK):
            size += len(chunk)
            if size > byte_limit:
                raise RestoreRefused("NATIVE_FILE_MISMATCH")
            digest.update(chunk)
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
        ) or size != before.st_size:
            raise RestoreRefused("NATIVE_FILE_MISMATCH")
        return before.st_dev, before.st_ino, size, digest.hexdigest()
    except OSError:
        raise RestoreRefused("NATIVE_FILE_MISMATCH") from None
    finally:
        try:
            os.close(fd)
        except OSError:
            raise RestoreRefused("NATIVE_FILE_MISMATCH") from None


def _observe_native(path: Path, *, scratch: Path, limits: ObservationLimits) -> SnapshotObservation:
    try:
        connection = duckdb.connect(str(path), read_only=True, config=_DUCKDB_CONFIG)
        try:
            connection.execute("BEGIN TRANSACTION")
            try:
                return observe_snapshot(connection, scratch_parent=scratch, limits=limits)
            finally:
                connection.execute("ROLLBACK")
        finally:
            connection.close()
    except RestoreRefused:
        raise
    except _NATIVE_OPEN_ERRORS:
        raise RestoreRefused("NATIVE_OPEN_OR_OBSERVATION_FAILED") from None


def verify_closed_native_archive(
    *,
    archive: Path,
    source_report_bytes: bytes,
    scratch_parent: Path,
    limits: RestoreLimits,
) -> NativeRestoreReport:
    """Compare a closed native archive with an authenticated source observation."""
    expected = SnapshotObservation.from_canonical_bytes(
        source_report_bytes, limits=limits.observation
    )
    try:
        scratch = Path(tempfile.mkdtemp(prefix="antiek-native-restore-", dir=scratch_parent))
    except OSError:
        raise RestoreRefused("SCRATCH_FAILED") from None
    try:
        scratch.chmod(0o700)
        admitted = scratch / "admitted"
        admitted.mkdir(mode=0o700)
        admitted.chmod(0o700)
        try:
            admission = admit_archive(archive, admitted, limits=limits.archive)
        except _ADMISSION_ERRORS:
            raise RestoreRefused("ARCHIVE_ADMISSION_FAILED") from None
        native_path, member = _admitted_native(admission, admitted)
        before = _file_fingerprint(native_path, limits.archive.member_bytes)
        if before[2:] != (member.size, member.sha256):
            raise RestoreRefused("NATIVE_FILE_MISMATCH")
        try:
            actual = _observe_native(native_path, scratch=scratch, limits=limits.observation)
        finally:
            after = _file_fingerprint(native_path, limits.archive.member_bytes)
            try:
                native_members = set(native_path.parent.iterdir())
            except OSError:
                raise RestoreRefused("NATIVE_FILE_MISMATCH") from None
            if after != before or native_members != {native_path}:
                raise RestoreRefused("NATIVE_FILE_MISMATCH")
        if set(actual.tables) != set(expected.tables):
            raise RestoreRefused("TABLE_SET_MISMATCH")
        if actual.catalog_objects != expected.catalog_objects:
            raise RestoreRefused("CATALOG_MISMATCH")
        if any(
            actual.tables[name].row_count != expected.tables[name].row_count
            for name in expected.tables
        ):
            raise RestoreRefused("COUNT_MISMATCH")
        if any(
            actual.tables[name].content_sha256 != expected.tables[name].content_sha256
            for name in expected.tables
        ):
            raise RestoreRefused("CONTENT_MISMATCH")
        source_digest = hashlib.sha256(source_report_bytes).hexdigest()
        restored_digest = hashlib.sha256(actual.canonical_bytes()).hexdigest()
        if source_digest != restored_digest:
            raise RestoreRefused("OBSERVATION_MISMATCH")
        report = NativeRestoreReport(
            report_scheme=NATIVE_REPORT_SCHEME,
            archive_format=NATIVE_ARCHIVE_FORMAT,
            archive_sha256=admission.archive_sha256,
            archive_bytes=admission.compressed_bytes,
            native_member_path=member.path,
            native_member_sha256=before[3],
            native_member_bytes=before[2],
            source_observation_sha256=source_digest,
            restored_observation_sha256=restored_digest,
            source_counts={name: item.row_count for name, item in expected.tables.items()},
            restored_counts={name: item.row_count for name, item in actual.tables.items()},
            source_catalog_sha256=_catalog_digest(expected),
            restored_catalog_sha256=_catalog_digest(actual),
            source_content_sha256={
                name: item.content_sha256 for name, item in expected.tables.items()
            },
            restored_content_sha256={
                name: item.content_sha256 for name, item in actual.tables.items()
            },
            content_scheme=CONTENT_SCHEME,
            duckdb_version=_DUCKDB_VERSION,
        )
        if len(report.canonical_bytes()) > limits.observation.report_bytes:
            raise RestoreRefused("REPORT_SIZE")
        return report
    except OSError:
        raise RestoreRefused("SCRATCH_FAILED") from None
    finally:
        try:
            shutil.rmtree(scratch)
        except OSError:
            raise RestoreRefused("CLEANUP_FAILED") from None
